# AI Resume OS / JobOS

Personal, local-only job-search operating system. This repository currently contains the P0 contract baseline and the P1 process scaffold; capture, matching, resume generation, and browser-side integration are not implemented yet.

## Architecture references

- `ARCH-MOD-001`: FastAPI modular monolith with isolated workers.
- `ARCH-SEC-001`: loopback-only host boundary.
- `ARCH-DEP-001`: local Docker Compose topology.
- `ARCH-CONTRACT-001`: documents define semantics; `contracts/` defines shape.
- `ARCH-AIAGENT-001`: contract-first changes, negative safety tests, human review.

## Toolchain

- Node.js 20 and pnpm 9
- Python 3.12
- Docker Desktop with Docker Compose

The repository pins these baselines in `.nvmrc`, `.python-version`, `package.json`, and the Dockerfiles. Host versions outside the baseline may inspect the project, but verification evidence must come from the pinned runtimes.

## Local setup

1. Copy `config/.env.example` to `.env`.
2. Replace the sample PostgreSQL password and leave secret values out of source control.
3. Run `docker compose config` to inspect the resolved local topology.
4. Run `docker compose up --build`.
5. Open `http://127.0.0.1:4173`.

Published ports are explicitly bound to `127.0.0.1`. The scaffold exposes health endpoints only; the extension gateway protocol is not active until pairing authentication is implemented and reviewed.

## Verification

```text
npx --yes pnpm@9.15.5 test
npx --yes pnpm@9.15.5 typecheck
npx --yes pnpm@9.15.5 build
pytest
ruff check services tests
black --check services tests
mypy services
```

Run Python commands with Python 3.12. Contract and safety fixtures are synthetic; never add real account or chat data to tests.
