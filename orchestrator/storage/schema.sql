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
    step         int          NOT NULL,
    kind         text         NOT NULL CHECK (kind IN ('llm', 'tool')),
    name         text         NOT NULL,
    input        jsonb,
    output       jsonb,
    allowed      boolean      NOT NULL,
    tokens_in    int,
    tokens_out   int,
    cache_read_tokens   int,
    cache_write_tokens  int,
    cost_usd     numeric(8,4),
    started_at   timestamptz  NOT NULL DEFAULT now(),
    finished_at  timestamptz,
    UNIQUE (run_id, step)
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

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id            bigint       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    namespace     text         NOT NULL,
    kind          text         NOT NULL CHECK (kind IN ('experiment', 'summary', 'doc')),
    run_id        bigint       REFERENCES runs (id),
    step          int,
    workloads     text[]       NOT NULL DEFAULT '{}',
    action_type   text,
    verdict       text,
    content       text         NOT NULL,
    content_hash  text         NOT NULL,
    embedding     vector(384)  NOT NULL,
    created_at    timestamptz  NOT NULL DEFAULT now(),
    UNIQUE (namespace, content_hash)
);

CREATE INDEX IF NOT EXISTS knowledge_chunks_workloads
    ON knowledge_chunks USING gin (workloads);
CREATE INDEX IF NOT EXISTS knowledge_chunks_embedding
    ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);