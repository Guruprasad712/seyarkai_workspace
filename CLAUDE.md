# CLAUDE.md

Governed AI Execution Workspace (team Seyarkai) — a hackathon project built from scratch
for the Google Cloud AI Builders Cup. AI agents (Google ADK + Gemini) execute multi-stage
Work Items under human-approved policies, grounded in a freshness-aware knowledge base
(Company Brain, on Vertex AI Search), with checkpoint approvals by assigned reviewers.
Deployed on Google Cloud Run.

## Source of truth
- docs/ARCHITECTURE.md — system shape, decisions, module boundaries, execution lifecycle
- docs/CONTRACTS.md — data model, lifecycles, validation rules, API surface, errors
- docs/KNOWN_LIMITATIONS.md — accepted gaps and trade-offs
- STATUS.md — current day, done, next, credentials register (names only), backlog

If code and docs disagree, stop and ask. Never silently reconcile.

## Clean-room rule
This repository contains only code written during the hackathon. Never import, copy,
or reference any other codebase. Build from the contracts in docs/.

## Stack
- Backend: Python 3.11, FastAPI, async SQLAlchemy 2, Alembic, Postgres
  (local Postgres 16 for development, Cloud SQL in production)
- Runtime: Google ADK (LlmAgent + Runner) with Gemini via Vertex AI (`GOOGLE_GENAI_USE_VERTEXAI=1`); AI Studio key is an unfunded fallback
- Tools: MCP servers built with FastMCP, connected over stdio via ADK MCPToolset
- Knowledge: Vertex AI Search behind a KnowledgeRetriever interface
- Frontend: Next.js (App Router) + TypeScript + Tailwind + shadcn/ui
- Deploy: Cloud Run, Secret Manager, Artifact Registry; CI on GitHub Actions
- No local Docker. Images are built only in CI.

## Repository layout
```
backend/
  app/
    core/         config, db session, security helpers, error types
    auth/         login, current user, role dependencies
    agents/       agents, versions, tool catalog, publish rules
    projects/     projects
    work_items/   work items, worker assignment
    policies/     policies, stages, checkpoints, publish validation, generation
    executions/   engine, checkpoint responses, messages, ask, SSE, artifacts
    runtime/      ADK agent building, stage running, event normalisation (NO DB)
    knowledge/    documents, retrievers, freshness, injection text
    mcp_servers/  knowledge/, docs/ — FastMCP tool processes
    main.py
  alembic/
  tests/
frontend/
deploy/           gcloud deployment scripts (Day 8)
docs/
scratch/          throwaway spikes (gitignored)
```

## Rules
1. No features outside the day's scope. New ideas go to the STATUS.md backlog.
2. Contracts in docs/CONTRACTS.md change only with explicit approval.
3. AI proposes; deterministic rules validate. Generated policies are always drafts.
4. Published policies are immutable and are the only thing executions run.
5. Agents use only tools selected on their published version.
6. Humans act through guidance messages and checkpoints.
7. Events are structured and never contain model thought content or secrets.
8. runtime/ never touches the database; the engine persists everything.
9. Before using any library API (ADK, google-genai, discoveryengine, Next.js), check the
   INSTALLED version's source or docs. Do not rely on memory.
10. Use plan mode. Show the design before broad changes. Ask when a real fork exists.
11. Never write secret values into code, docs, tests, logs or commits. Read them from
    environment variables only.

## Working style
- One module at a time: backend, tests, live curl check, then frontend.
- After each feature: run tests, show the diff, explain changes, flag doc mismatches.
- Every router gets at least one real HTTP test.
- Gemini is never called in CI; mock runtime.run_stage. Live tests use @pytest.mark.live.
- End of session: update STATUS.md and docs/KNOWN_LIMITATIONS.md.

## Lessons checklist

### Backend and data
- Use VARCHAR statuses with app-layer validation. If a native enum is ever used, persist
  `.value` labels explicitly.
- Register every router in main.py; keep a real HTTP test per router.
- Validate before insert and return 4xx; never let an IntegrityError or SQL text reach a
  response.
- Run scripts from backend/ with the virtualenv active; settings files resolve relative
  to the working directory.
- When live behaviour contradicts the code on disk, kill whatever holds the port and
  restart cleanly before debugging. Hot reload has served stale code before.
- Background tasks must open their own database session.
- Test cleanup deletes children before parents and tracks IDs explicitly.

### Policies and execution
- Derive stage sequence from order; renumber on delete; never trust model-supplied sequence.
- Resolve the agent per stage from that stage's agent_version_id.
- Make each stage's prompt stage-specific; identical prompts across stages is a real past bug.
- Store blocking_checkpoint_id; never infer the blocking checkpoint.
- Never persist or stream model thought content.
- Always leave a failed execution in `failed` with a readable error, never stuck in `running`.

### Frontend
- Unwrap errors through one helper (`detail` may be a string or an object with `failures`).
- Inline errors for actions; full-page error only for initial load failure.
- A toggle that would create an invalid server state stays local until the user completes
  the selection.
- Dark-mode `<select>` and `<option>` need explicit backgrounds.
- Check the installed framework's docs for breaking changes (Next.js, ADK) before relying
  on memory.
