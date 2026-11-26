"""Postgres access for the orchestrator."""
from pathlib import Path
import psycopg
from psycopg.types.json import Jsonb

SCHEMA_FILE = Path(__file__).parent / "schema.sql"

def connect():
    """Open a connection using the standard PG* environment variables.

    Returns:
        An open psycopg connection, passed as conn to every function in this module.
    """
    return psycopg.connect()


def apply_schema(conn):
    """Create tables and indexes if missing. Safe to run on every start.

    Args:
        conn: open connection from connect().
    """
    conn.execute(SCHEMA_FILE.read_text())
    conn.commit()

# --------- RUNS ----------------

def create_run(conn, namespace, model, max_level, roe, budget_usd, profile=None, focus=None):
    """Insert a queued run and return its id.

    Args:
        conn: open connection from connect().
        namespace: the namespace under test; also the key of the per-namespace lock.
        model: exact model ID, so runs can be compared across models.
        max_level: highest action level the run may use: observe, probe or disrupt.
        roe: the run's Rules of Engagement as a dict, stored as it was at start.
        budget_usd: the run's budget in USD.
        profile: the target application's profile, or None.
        focus: dict with areas, components or checks that narrows the run, or None.

    Returns:
        The new run's id; every other table refers to it.
    """
    row = conn.execute(
        """
        INSERT INTO runs (namespace, model, max_level, roe, profile, focus, budget_usd)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (namespace, model, max_level, Jsonb(roe),
         Jsonb(profile) if profile is not None else None,
         Jsonb(focus) if focus is not None else None,
         budget_usd),
    ).fetchone()
    conn.commit()
    return row[0]


def claim_run(conn, run_id):
    """Move a queued run to running and take the namespace lock.

    Args:
        conn: open connection from connect().
        run_id: the run's id, from create_run.

    Returns:
        True if the run is now running; False if it was not queued or its namespace is locked.
    """
    try:
        cur = conn.execute(
            "UPDATE runs SET status = 'running', started_at = now() "
            "WHERE id = %s AND status = 'queued'",
            (run_id,),
        )
        conn.commit()
        return cur.rowcount == 1
    except psycopg.errors.UniqueViolation:
        conn.rollback()
        return False


def finish_run(conn, run_id, status, error=None):
    """Close a running run as completed, aborted or failed. This releases the lock.

    Args:
        conn: open connection from connect().
        run_id: the run's id, from create_run.
        status: 'completed', 'aborted' (stopped by a safety mechanism) or 'failed'.
        error: why the run ended, for aborted or failed runs.
    """
    conn.execute(
        "UPDATE runs SET status = %s, finished_at = now(), error = %s WHERE id = %s",
        (status, error, run_id),
    )
    conn.commit()

# --------- Steps ----------------

def start_step(conn, run_id, name, args, allowed):
    """Record a tool call before it runs.

    Args:
        conn: open connection from connect().
        run_id: the run's id, from create_run.
        name: full tool name, for example observe__get_workloads or get_check.
        args: the tool's arguments, as they will be sent.
        allowed: whether the orchestrator approved the call; denied calls are recorded too.

    Returns:
        A tuple: the step's id, passed to finish_step, and its step number, shown to the model.
    """
    row = conn.execute(
        """
        INSERT INTO steps (run_id, step, kind, name, input, allowed)
        VALUES (%s, (SELECT coalesce(max(step), 0) + 1 FROM steps WHERE run_id = %s), 'tool', %s, %s, %s)
        RETURNING id, step
        """,
        (run_id, run_id, name, Jsonb(args), allowed),
    ).fetchone()
    conn.commit()
    return row[0], row[1]


def finish_step(conn, step_id, output):
    """Record the result of a tool call.

    Args:
        conn: open connection from connect().
        step_id: from start_step.
        output: what the tool returned, or {"denied": reason}.
    """
    conn.execute(
        "UPDATE steps SET output = %s, finished_at = now() WHERE id = %s",
        (Jsonb(output), step_id),
    )
    conn.commit()


def record_llm_step(conn, run_id, model, output, tokens_in, tokens_out):

    """Record one LLM call: the model's response and its token usage.

    Args:
        conn: open connection from connect().
        run_id: the run's id, from create_run.
        model: the model ID, stored as the step's name.
        output: the response blocks as dicts, including any tool_use blocks.
        tokens_in: response.usage.input_tokens.
        tokens_out: response.usage.output_tokens.
    """
    conn.execute(
        """
        INSERT INTO steps (run_id, step, kind, name, output, allowed, tokens_in, tokens_out, finished_at)
        VALUES (%s, (SELECT coalesce(max(step), 0) + 1 FROM steps WHERE run_id = %s), 'llm', %s, %s, true, %s, %s, now())
        """,
        (run_id, run_id, model, Jsonb(output), tokens_in, tokens_out),
    )
    conn.commit()


# --------- Findings ----------------

def record_finding(conn, run_id, finding):
    """Insert a finding, or replace the run's earlier one for the same check, component and dependency.

    Args:
        conn: open connection from connect().
        run_id: the run's id, from create_run.
        finding: a validated finding with check_name, component, dependency, status, category,
            severity, severity_reason, title, evidence and recommendation.

    Returns:
        A tuple: the finding's id, and True if it replaced an earlier finding.
    """
    row = conn.execute(
        """
        INSERT INTO findings (run_id, check_name, component, dependency, status, category,
                              severity, severity_reason, title, evidence, recommendation)
        VALUES (%(run_id)s, %(check_name)s, %(component)s, %(dependency)s, %(status)s,
                %(category)s, %(severity)s, %(severity_reason)s, %(title)s, %(evidence)s,
                %(recommendation)s)
        ON CONFLICT (run_id, check_name, component, dependency) DO UPDATE SET
            status = EXCLUDED.status,
            category = EXCLUDED.category,
            severity = EXCLUDED.severity,
            severity_reason = EXCLUDED.severity_reason,
            title = EXCLUDED.title,
            evidence = EXCLUDED.evidence,
            recommendation = EXCLUDED.recommendation,
            updated_at = now()
        RETURNING id, updated_at > created_at
        """,
        {**finding, "run_id": run_id, "evidence": Jsonb(finding["evidence"])},
    ).fetchone()
    conn.commit()
    return row[0], row[1]

def evidence_steps(conn, run_id, steps):
    """Which of the given step numbers can be cited as evidence in this run.

    Args:
        conn: open connection from connect().
        run_id: the run's id, from create_run.
        steps: the step numbers the model cited.

    Returns:
        The subset of steps that are allowed, finished, successful calls to an MCP server tool.
    """
    rows = conn.execute(
        """
        SELECT step FROM steps
        WHERE run_id = %s AND step = ANY(%s)
          AND kind = 'tool' AND allowed AND output IS NOT NULL
          AND name LIKE '%%\\_\\_%%'
          AND NOT (output->>'is_error')::boolean
        """,
        (run_id, list(steps)),
    ).fetchall()
    return {row[0] for row in rows}