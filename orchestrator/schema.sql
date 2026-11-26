CREATE TABLE IF NOT EXISTS runs (
    id           bigint       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    namespace    text         NOT NULL,
    status       text         NOT NULL DEFAULT 'queued'
                 CHECK (status IN ('queued', 'running', 'completed', 'aborted', 'failed')),
    model        text         NOT NULL,
    max_level    text         NOT NULL CHECK (max_level IN ('observe', 'probe', 'disrupt')),
    roe          jsonb        NOT NULL,
    profile      jsonb,
    focus        jsonb,
    budget_usd   numeric(8,4) NOT NULL,
    spent_usd    numeric(8,4) NOT NULL DEFAULT 0,
    created_at   timestamptz  NOT NULL DEFAULT now(),
    started_at   timestamptz,
    finished_at  timestamptz,
    error        text
);

CREATE UNIQUE INDEX IF NOT EXISTS one_running_run_per_namespace
    ON runs (namespace) WHERE status = 'running';

CREATE TABLE IF NOT EXISTS steps (
    id           bigint       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id       bigint       NOT NULL REFERENCES runs (id),
    seq          int          NOT NULL,
    kind         text         NOT NULL CHECK (kind IN ('llm', 'tool')),
    name         text         NOT NULL,
    input        jsonb,
    output       jsonb,
    allowed      boolean      NOT NULL,
    tokens_in    int,
    tokens_out   int,
    cost_usd     numeric(8,4),
    started_at   timestamptz  NOT NULL DEFAULT now(),
    finished_at  timestamptz,
    UNIQUE (run_id, seq)
);

CREATE TABLE IF NOT EXISTS undo_actions (
    id           bigint       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id       bigint       NOT NULL REFERENCES runs (id),
    step_id      bigint       NOT NULL REFERENCES steps (id),
    action       jsonb        NOT NULL,
    status       text         NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending', 'done', 'failed')),
    created_at   timestamptz  NOT NULL DEFAULT now(),
    done_at      timestamptz
);

CREATE TABLE IF NOT EXISTS findings (
    id              bigint       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id          bigint       NOT NULL REFERENCES runs (id),
    check_name      text         NOT NULL,
    component       text         NOT NULL,
    /* dependency for checks that the target are diffrent service that depends on each other*/
    dependency      text,
    status          text         NOT NULL CHECK (status IN ('confirmed', 'survived')),
    severity        text         NOT NULL CHECK (severity IN ('high', 'medium', 'low')),
    title           text         NOT NULL,
    evidence        jsonb        NOT NULL,
    recommendation  text,
    created_at      timestamptz  NOT NULL DEFAULT now()
);