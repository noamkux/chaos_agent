"""What the agent remembers: past experiments and conclusions on the same application, searched by the
model through search_knowledge (ADR-0033).

Terms used in this file:
- chunk: one piece of text that is retrieved on its own, with the fields it is filtered on. An experiment
  is one chunk, built by code from its stored JSON; each section of a run's summary is one chunk, the
  model's interpretation, marked kind "summary".
- workload: group/Kind/name, without the namespace, the way discovery names kinds (ADR-0012):
  "apps/Deployment/frontend".
- embedding: 384 numbers for the meaning of a text, from fastembed, computed in this process so no text
  leaves the cluster to be embedded.

Flow: at the end of a run, index_run builds the chunks of that run (experiment_chunks, summary_chunks),
embeds them and stores them; a chunk already stored, by its hash, is skipped. During a run, search filters
on the run's namespace (and a workload, when the model names one) and ranks by similarity.
"""
import hashlib
import json
import re

MODEL_NAME = "BAAI/bge-small-en-v1.5"
DIMENSIONS = 384
SEARCH_LIMIT = 5

# Verdicts of experiments that changed something: not_run (never steady) and refused calls changed nothing.
REMEMBERED_VERDICTS = {"broke", "withstood", "inconclusive"}

_model = None


def workload_of(kind, name):
    """A workload in the form the chunks are filtered on: group/Kind/name."""
    return f"{kind}/{name}"


def content_hash(content):
    """The hash a chunk is stored under, so indexing a run twice stores nothing new."""
    return hashlib.sha256(content.encode()).hexdigest()


def describe_action(action):
    """One line for what an experiment changed, in plain words."""
    if action.get("type") == "node_failure":
        where = f"zone {action['zone']}" if action.get("zone") else f"node {action.get('node')}"
        return f"node_failure ({action.get('mode', 'drain')}) of {where}"
    target = f"{action.get('kind')} {action.get('name')}"
    if action.get("type") == "patch":
        return f"patch of {target}: {json.dumps(action.get('patch'), sort_keys=True)}"
    return f"{action.get('type')} on {target}"


def affected_workloads(action, result):
    """The workloads an experiment touched: its target, or for a node failure every workload whose pods
    moved (placement_events), since a drain of a node is what takes those workloads down."""
    if action.get("type") != "node_failure":
        return [workload_of(action["kind"], action["name"])] if action.get("kind") and action.get("name") else []
    names = set()
    for event in result.get("placement_events") or []:
        # "boutique/apps/Deployment/frontend": the namespace has its own column.
        names.add(event["workload"].split("/", 1)[1])
    return sorted(names)


def journey_lines(result):
    """One line per journey with the numbers a later run needs: success, broken and recovery seconds,
    worst p95 and the errors."""
    lines = []
    for journey, facts in sorted((result.get("journeys") or {}).items()):
        after = facts.get("after_action") or {}
        errors = ", ".join(f"{error} {count}" for error, count in sorted((after.get("errors") or {}).items()))
        lines.append(f"{journey}: success {after.get('success')}, broken {facts.get('broken_s')}s, "
                     f"recovered after {facts.get('recovered_after_s')}s, worst p95 {after.get('worst_p95_ms')} ms"
                     + (f", errors {errors}" if errors else ""))
    return lines


def experiment_chunks(run_id, namespace, steps):
    """One chunk for every run_experiment step that changed something, from its stored input and output.
    steps are rows of {step, started_at, input, output}."""
    chunks = []
    for row in steps:
        result, args = row["output"] or {}, row["input"] or {}
        verdict = result.get("verdict")
        if verdict not in REMEMBERED_VERDICTS:
            continue
        action = args.get("action") or {}
        lines = [f"run {run_id} step {row['step']} ({row['started_at']:%Y-%m-%d}): {describe_action(action)}.",
                 f"Hypothesis: {args.get('hypothesis', '')}",
                 f"Verdict: {verdict}."]
        if verdict == "inconclusive":
            lines.append(f"Reason: {result.get('reason')}.")
        lines += journey_lines(result)
        workloads = affected_workloads(action, result)
        if workloads:
            lines.append("Workloads affected: " + ", ".join(workloads) + ".")
        content = "\n".join(lines)
        chunks.append({"namespace": namespace, "kind": "experiment", "run_id": run_id, "step": row["step"],
                       "workloads": workloads, "action_type": action.get("type"), "verdict": verdict,
                       "content": content, "content_hash": content_hash(content)})
    return chunks


def summary_chunks(run_id, namespace, summary):
    """One chunk for every section of the model's summary, split on its "##" and "###" headings, each
    starting with where it came from so a chunk read alone still says so. Text before the first heading
    is a section of its own."""
    sections, title, lines = [], "Summary", []
    for line in summary.splitlines():
        heading = re.match(r"^#{2,3}\s+(.*)", line)
        if heading:
            if "".join(lines).strip():
                sections.append((title, "\n".join(lines).strip()))
            title, lines = heading.group(1).strip(), []
        else:
            lines.append(line)
    if "".join(lines).strip():
        sections.append((title, "\n".join(lines).strip()))
    chunks = []
    for title, body in sections:
        content = f'run {run_id} summary, section "{title}" (the agent\'s interpretation):\n{body}'
        chunks.append({"namespace": namespace, "kind": "summary", "run_id": run_id, "step": None,
                       "workloads": [], "action_type": None, "verdict": None,
                       "content": content, "content_hash": content_hash(content)})
    return chunks


def embedder():
    """The fastembed model, loaded on first use only (about 70 MB, downloaded once), so code and tests
    that never embed never load it."""
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model = TextEmbedding(MODEL_NAME)
    return _model


def embed_passages(texts):
    """Embeddings for stored chunks, as numpy arrays (register_vector sends them as vector)."""
    return list(embedder().passage_embed(texts))


def embed_query(text):
    """The embedding of a search: bge models are trained with an instruction before a query, and
    query_embed adds it."""
    return next(iter(embedder().query_embed(text)))


def run_texts(conn, run_id):
    """The run's namespace, its judged experiments and the model's last text (its summary)."""
    namespace = conn.execute("SELECT namespace FROM runs WHERE id = %s", (run_id,)).fetchone()[0]
    rows = conn.execute(
        "SELECT step, started_at, input, output FROM steps "
        "WHERE run_id = %s AND name = 'run_experiment' ORDER BY step", (run_id,)).fetchall()
    steps = [{"step": r[0], "started_at": r[1], "input": r[2], "output": r[3]} for r in rows]
    last_llm = conn.execute(
        "SELECT output FROM steps WHERE run_id = %s AND kind = 'llm' ORDER BY step DESC LIMIT 1",
        (run_id,)).fetchone()
    blocks = last_llm[0] if last_llm and last_llm[0] else []
    summary = "\n".join(block.get("text", "") for block in blocks if block.get("type") == "text")
    return namespace, steps, summary


def index_run(conn, run_id, embed=embed_passages):
    """Store every chunk of a run that is not stored yet. Returns how many were added."""
    from pgvector.psycopg import register_vector
    register_vector(conn)
    namespace, steps, summary = run_texts(conn, run_id)
    chunks = experiment_chunks(run_id, namespace, steps) + summary_chunks(run_id, namespace, summary)
    if not chunks:
        return 0
    added = 0
    for chunk, vector in zip(chunks, embed([chunk["content"] for chunk in chunks])):
        cursor = conn.execute(
            """
            INSERT INTO knowledge_chunks (namespace, kind, run_id, step, workloads, action_type, verdict,
                                          content, content_hash, embedding)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
            ON CONFLICT (namespace, content_hash) DO NOTHING
            """,
            (chunk["namespace"], chunk["kind"], chunk["run_id"], chunk["step"], chunk["workloads"],
             chunk["action_type"], chunk["verdict"], chunk["content"], chunk["content_hash"], vector))
        added += cursor.rowcount
    conn.commit()
    return added


def search(conn, namespace, query, workload=None, embed=embed_query):
    """The SEARCH_LIMIT chunks closest in meaning to the query, only from this namespace. With a workload,
    experiments must have touched it; summary sections always compete, by similarity alone, since their
    workloads are not guessed from free text. Returns rows of {run_id, step, kind, content, distance}."""
    from pgvector.psycopg import register_vector
    register_vector(conn)
    rows = conn.execute(
        """
        SELECT run_id, step, kind, content, embedding <=> %s::vector AS distance
        FROM knowledge_chunks
        WHERE namespace = %s AND (%s::text IS NULL OR workloads @> ARRAY[%s::text] OR kind = 'summary')
        ORDER BY distance
        LIMIT %s
        """,
        (embed(query), namespace, workload, workload, SEARCH_LIMIT)).fetchall()
    return [{"run_id": r[0], "step": r[1], "kind": r[2], "content": r[3], "distance": round(float(r[4]), 3)}
            for r in rows]
