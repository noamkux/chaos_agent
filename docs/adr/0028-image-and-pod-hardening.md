# ADR-0028: The MCP image and pods are locked down: pinned digests, hashed dependencies, non-root, read-only

**Status:** Accepted, 2026-11-26
**Related:** ADR-0008 (servers per level), ADR-0016 (denylist)

## Context
The disrupt server can change almost anything in the tested namespaces. Whatever runs in its image runs with those permissions, so the supply chain of that image and the pod it runs in are part of the safety model.

## Options
1. **Tags and an unpinned `pip install`.** Simplest, but an image or a package can change under the same name between two builds.
2. **Pin base images by digest, lock every Python dependency with hashes, and run the pod with the least it needs.**

## Decision
Option 2.
- **Base images by digest:** `grafana/k6:2.4.0@sha256:...` (only the binary is copied) and `python:3.12-slim@sha256:...`.
- **Dependencies:** `requirements.in` is compiled by `pip-compile` into `requirements.txt` with a hash for every package, installed with `pip install --require-hashes`.
- **Non-root:** user 10001, `runAsNonRoot`, `seccompProfile: RuntimeDefault`, `allowPrivilegeEscalation: false`.
- **Read-only root filesystem,** with an emptyDir on `/tmp` for k6's files.
- **A minimal environment for k6:** only `CONFIG_FILE`, `PATH` and `HOME`, so `K6_*` variables on the pod cannot change a measurement, and the server's environment is not visible to it.

## Consequences
- **Gains:** a build is reproducible; a compromised package version or base tag cannot slip in; a process in the pod cannot write to the image or gain privileges.
- **Trade-offs:** updating a dependency means recompiling the lock file; updating a base image means a new digest. In the lab the image tag stays `dev` with a rollout restart, since every new tag on kind is another copy on every node of a small disk; CI builds by digest (ADR-0034).

## In the code
- `servers/mcp/Dockerfile`, `servers/mcp/requirements.in`, `servers/mcp/requirements.txt`.
- `charts/chaos-agent/templates/mcp.yaml`: the pod and container `securityContext`, the `/tmp` emptyDir.
- `servers/mcp/probe.py`: the `env` passed to k6 in `run_k6`.
