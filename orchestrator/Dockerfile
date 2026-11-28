# The orchestrator: one run of the agent per container (ADR-0039). Python 3.14, not the MCP image's
# Chainguard 3.15: onnxruntime, under fastembed, has no 3.15 wheel yet. Both stages use the same digest:
# the venv is linked to this exact Python.
FROM python:3.14-slim@sha256:f57c4c23b985d95deea5bc5249e2f9c8a512b4cc9d5d3fd31900cbd2f5f0a604 AS build
WORKDIR /app
# The venv gets no pip of its own: the system pip of this stage installs into it, and is left behind.
RUN python -m venv --without-pip venv
COPY requirements.txt .
RUN python -m pip --python /app/venv/bin/python install --no-cache-dir -r requirements.txt
# The embedding model, downloaded once at build time: a cluster with no access to Hugging Face
# (air-gapped) can still run, and a run never waits for a download.
ENV FASTEMBED_CACHE_PATH=/app/models
# Only what loading the model needs, so a change to the rest of the code does not download it again.
COPY agent/__init__.py agent/knowledge.py agent/
COPY storage/__init__.py storage/db.py storage/
# The download writes some cache files readable by root only; the runtime user must read all of it.
RUN /app/venv/bin/python -c "from agent import knowledge; knowledge.embedder()" \
    && chmod -R a+rX /app/models

FROM python:3.14-slim@sha256:f57c4c23b985d95deea5bc5249e2f9c8a512b4cc9d5d3fd31900cbd2f5f0a604
# The same nonroot user as the MCP image (65532), so the chart sets one identity for both.
RUN groupadd --gid 65532 nonroot \
    && useradd --uid 65532 --gid 65532 --no-create-home --shell /usr/sbin/nologin nonroot
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PATH="/app/venv/bin:$PATH" \
    FASTEMBED_CACHE_PATH=/app/models HF_HUB_OFFLINE=1
COPY --from=build /app/venv /app/venv
COPY --from=build /app/models /app/models
COPY main.py config.py mcp_client.py ./
COPY agent/ agent/
COPY experiments/ experiments/
COPY storage/ storage/
USER 65532
ENTRYPOINT ["python", "main.py"]
