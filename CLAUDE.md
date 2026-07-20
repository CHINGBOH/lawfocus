# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project pivot (2026-07-20) — read this first

`lawfocus` used to target an enterprise compliance-reasoning system for listed-company governance (deterministic rule engine, five-valued truth execution, RBAC, audit trails, real-company-fact intake). **That scope is superseded.**

The project is now a **personal/small-team legal-system learning tool**: given one law (Company Law, Contract Law, ...), let a user trace every legal concept through the whole legal system — definition, broader/narrower concepts, cross-law references — back to real, versioned article text. No compliance judgments, no governance-fact intake, no rule engine.

Authoritative docs for the current scope:

- `00-项目文档索引与实施顺序.md` — entry point, vision, architecture baseline
- `01-法律体系概念图谱设计.md` — data model for the legal repository + concept graph, RAG index design
- `02-学习工具产品需求与验收标准.md` — user tasks, UI shape, acceptance criteria, explicit non-goals

All prior spec documents (the old `00`–`11` set, the five core formal-semantics regulations, the old UI/product-requirements docs, `GOAL.md`) are moved to `archive/` — see `archive/README.md` for what each one was and why it no longer applies. Do not treat anything under `archive/` as current guidance; it's historical reference only.

**`apps/` (the FastAPI + Vue skeleton described below) still reflects the old compliance-system scope and has not been rebuilt for the new direction.** Until it is, the commands and architecture notes below describe what the existing code does, not what the product is supposed to be. Don't extend the rule engine, RBAC, governance-fact, or compliance-check surfaces further — new work should follow `01`/`02` instead.

## What this repository is (legacy code layer)

The runnable MVP full-stack skeleton (`apps/`) is a FastAPI + Vue implementation built to satisfy the now-archived spec layer, per `archive/GOAL.md` (the executing agent's build brief for the old scope). `README.md` documents the architecture mapping, quick start, demo accounts, and known limitations; `AGENTS.md` is a denser agent-oriented restatement of the same facts — both describe the legacy compliance-system code, not the new learning-tool direction.

## Commands

These commands operate on the existing `apps/` code (legacy compliance-system scope) and remain accurate for that code until it's rebuilt.

Prerequisites: PostgreSQL 16 (pgvector extension not required), `uv`, Node 22+, `pnpm`.

```bash
make bootstrap   # uv sync (backend) + pnpm install (frontend)

# No local Postgres bootstrap script is included — create roles/DBs manually:
#   CREATE ROLE lawfocus LOGIN PASSWORD 'lawfocus_dev_password';
#   CREATE DATABASE lawfocus_dev  OWNER lawfocus;
#   CREATE DATABASE lawfocus_test OWNER lawfocus;

make migrate     # cd apps/api && uv run alembic upgrade head   (targets lawfocus_dev)
LAWFOCUS_DEMO_PASSWORD='pick-a-dev-password' make seed   # seed script rejects hardcoded passwords
make dev         # uvicorn on :8000 + vite dev server on :5173
make test        # backend pytest (against lawfocus_test) + frontend vitest
make lint        # ruff check + mypy app ; eslint + vue-tsc --noEmit
make e2e         # backend tests/e2e only (AC-01..AC-08 + performance smoke, old-scope acceptance criteria)
make down        # docker compose down
```

Single-package / single-test commands:

```bash
cd apps/api && uv run pytest tests/unit/test_truth.py::test_and_conflict   # one backend test
cd apps/api && uv run pytest tests/integration                            # one backend suite
cd apps/api && uv run uvicorn app.main:app --reload --port 8000
cd apps/web && pnpm vitest run tests/ConceptHyperlink.test.ts             # one frontend test file
cd apps/web && pnpm dev / pnpm build / pnpm lint
```

**Backend tests require a real PostgreSQL database, not SQLite/in-memory.** `apps/api/tests/conftest.py` hardcodes `postgresql+psycopg://lawfocus:lawfocus_dev_password@localhost:5432/lawfocus_test` — the `lawfocus_test` schema must already be migrated (`alembic upgrade head` run against it) before `pytest` will pass. Tests run inside an outer transaction + SAVEPOINT and roll back, so they don't leave data behind, but the schema must exist first.

`docker compose up` is available (`docker-compose.yml` wires db/api/web with health checks) but **has never been run in this sandbox** (no Docker daemon here) — verify it on a machine with Docker before relying on it.

After changing API models/schemas, re-export the OpenAPI contract:

```bash
cd apps/api && uv run python -c "
import json
from app.main import app
json.dump(app.openapi(), open('../../contracts/openapi.json', 'w'), ensure_ascii=False, indent=2)
"
```

## Architecture (legacy code layer, `apps/`)

```
apps/api/   FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL 16 (uv-managed, Python >= 3.12)
  app/api/v1/       route layer: auth/laws/articles/concepts/facts/compliance/rules/rulesets/subjects/audit
  app/core/         pydantic-settings config (LAWFOCUS_ prefix), DB session, JWT security, unified error shape
  app/domain/       DB-independent core invariants: five-valued truth (truth.py), half-open time intervals, rule results
  app/models/       SQLAlchemy models: legal / graph / governance / facts / rules / inference / identity / audit
  app/schemas/      Pydantic request/response models
  app/services/     business services (see mapping table below)
  app/repositories/ data access layer
  migrations/       Alembic migrations
  scripts/          seed_demo.py (idempotent demo seed), import/promote scripts for real-sourced data
  tests/            unit (pure domain logic) / integration (services + API) / e2e (AC-01..08 + perf smoke, old-scope)
apps/web/   Vue 3 + Vite + TypeScript + Vue Router + Pinia + Vitest (pnpm-managed)
  src/views/        three-pane article reader, compliance-check wizard/result, rule center, facts/evidence, audit
  src/components/   ConceptHyperlink.vue, LegalSynthesisPanel.vue ("小综合" panel)
  src/api/          API client; src/stores/ Pinia; src/types/ types mirroring the OpenAPI contract
  tests/            Vitest component/view tests
contracts/openapi.json   exported OpenAPI snapshot — re-export after API model changes (command above)
```

Of this, the parts still conceptually relevant to the new direction are the **legal repository** (`app/models/legal.py`, `app/services/legal_repository_service.py`) and **concept graph** (`app/models/graph.py`, `app/services/concept_service.py`) layers, plus the reader-side frontend (`ArticleReader`, `ConceptHyperlink`). The governance/facts/rules/inference/audit layers implement the archived compliance-system scope and are not part of the new product surface — see `01-法律体系概念图谱设计.md` for what the concept-graph layer should look like going forward instead.

Stack constraints from the archived `GOAL.md` §2 (Neo4j, Z3, Celery, Kubernetes, microservice decomposition deferred) no longer set the direction for new work; they only explain why the existing legacy code looks the way it does.

## Code and doc conventions

- New spec documents (`00`–`02`) are Chinese prose; code identifiers, schema fields, and component names stay English (`PascalCase`/`snake_case`).
- Backend: ruff (line-length 120, `E,F,I,UP,B`, excludes `migrations/versions`) + mypy on `app/` must be clean. Routing layer only parses params and delegates auth; business logic lives in `services/`.
- Frontend: eslint flat config + `vue-tsc --noEmit` must be clean (a few purely-stylistic vue rules are turned off in `eslint.config.js` since this project doesn't run Prettier).
- Concept links must render from the backend's `text_segments[]` structure — no client-side string parsing for hyperlinks. This constraint carries forward unchanged into the new direction (see `01-法律体系概念图谱设计.md` §2).
- Config is env-var driven: `LAWFOCUS_*` (backend, see `apps/api/.env.example`), `VITE_API_BASE_URL` (frontend). Only `.env.example` files are committed — never real secrets (`.gitignore` covers `.env`/`.venv` at root and in `apps/api/`).
- This directory is **not tracked by the parent monorepo's git** — the parent `/home/l/projects/.gitignore` explicitly excludes existing project checkouts (`/*` with an allowlist that doesn't include `lawfocus/`), and `lawfocus/` has no `.git` of its own. There is currently no version control for this project; treat any edit here as directly affecting the only copy on disk.
