FROM grafana/k6:2.4.0@sha256:d41bb79cd8de5a7ad619b53570e3712633e8bff0937010a5c6c57a4747e7a276 AS k6

# Build stage: has pip and a shell, never shipped. Bump both Chainguard digests together: the venv
# is linked to this exact Python, so the runtime below must come from the same build.
FROM cgr.dev/chainguard/python:latest-dev@sha256:08141c5166ee89eac4b79d1ab4dc284c1796b5f264d66f0675742819ac511655 AS build
WORKDIR /app
# The venv gets no pip of its own: the system pip of this stage installs into it, and is left behind.
RUN python -m venv --without-pip venv
COPY requirements.txt .
RUN python -m pip --python /app/venv/bin/python install --no-cache-dir --require-hashes -r requirements.txt

# Runtime: Python 3.15 only, no shell and no package manager, runs as nonroot (65532).
FROM cgr.dev/chainguard/python:latest@sha256:884deb80d867bc984df53f9f2e2a205b9c2922c53ec992fcbeeb1ad7aad711c3
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PATH="/app/venv/bin:$PATH" HOST=0.0.0.0 PORT=8081

COPY --from=build /app/venv /app/venv
COPY --from=k6 /usr/bin/k6 /usr/local/bin/k6
COPY *.py journeys.js ./

EXPOSE 8081
ENTRYPOINT ["python", "server.py"]
