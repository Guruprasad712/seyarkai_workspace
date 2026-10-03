# Day 1 — Cloud Setup, Foundation, Contracts, CI

Date: 2026-10-02

## Sessions

### Session 1 — Backend scaffold
- Python 3.11 virtualenv with pinned requirements
- `pydantic-settings` config resolving `.env` from repo root
- Async SQLAlchemy 2 engine + session factory
- Alembic migration `0001_initial` — 17 tables per CONTRACTS.md
  - UUID PKs generated in Python
  - JSONB columns: `agent_versions.capabilities`, `execution_events.payload`, `checkpoint_responses.input`
  - `agent_code_seq` Postgres sequence
  - CHECK constraint on `work_item_workers` (ai_agent vs human)
  - Composite PK on `agent_version_tools`
  - Composite index on `execution_events(execution_id, created_at)`
- `GET /health` — `SELECT 1`, returns `{"status":"ok"}` 200 or 503
- Error handlers: 422 / 500 all returning `{"detail": ...}`
- pytest suite: `test_health` + migration round-trip (2/2 green)

### Session 2 — Frontend shell + CORS
- Next.js 16 App Router, TypeScript, Tailwind v4, shadcn/ui
- `frontend/lib/api.ts` — `apiFetch` + `ApiError` + `extractDetail` (unwraps `detail` string or `{failures:[]}`)
- Home page calls `GET /health` on mount — shows loading / green online / red offline
- Placeholder pages: Agents, Projects, Knowledge
- `next.config.ts` — `output: "standalone"`
- `NEXT_PUBLIC_API_URL` env var
- Backend: `CORSMiddleware` reading `CORS_ORIGINS` from settings

### Session 3 — Dockerfiles + CI
- `backend/Dockerfile` — `python:3.11-slim`, non-root user, uvicorn on `$PORT` (default 8080)
- `frontend/Dockerfile` — multi-stage Node 22 standalone build, `NEXT_PUBLIC_API_URL` build ARG, non-root user
- `backend/.dockerignore` / `frontend/.dockerignore`
- `.github/workflows/ci.yml`
  - `backend-tests` job: Postgres 16 service container → alembic upgrade → pytest
  - `docker-build` job: builds both images (no push) — runs only on `dev`/`main` push or PR targeting `dev`/`main`

## Commits
- `56e3ca3` Initial commit
- `2a72d5e` docs: architecture, contracts, limitations and status for Day 1
- `98a3555` feat(backend): Session 1 scaffold
- `f40f757` feat: Session 2 — frontend shell and backend CORS
- `b89c91b` feat: Session 3 — Dockerfiles and CI workflow
- `260581c` ci: restrict docker-build job to dev and main branches
- `ac6bd0f` ci: run full pipeline on PRs targeting dev or main
