# STATUS

Update at the end of every session. Every Claude Code session starts by reading this file,
CLAUDE.md, and the relevant docs/ sections.

## Current: Day 5 of 10 — Policy engine (frontend + generation stub)
Date: 2026-10-08   Region: us-central1

### Done (Days 1–4)
- [x] Public repo, .gitignore, secret scanning + push protection
- [x] APIs enabled
- [x] Secrets: jwt-secret, db-password, gemini-api-key (3; docs identity is keyless)
- [x] Cloud SQL seyarkai-db RUNNABLE; db + appuser created
- [x] Vertex AI Search data store created; test document searchable
- [x] Service accounts backend-runtime, docs-generator; Artifact Registry repo
- [x] Local: Postgres 16 `seyarkai_dev` + `seyarkai_test`, Python 3.11, .env populated
- [x] Backend scaffold, single migration (17 tables), /health 200, pytest green
- [x] Frontend shell showing backend health
- [x] CI: pytest (not live/integration) + docker build of both images
- [x] app/runtime: run_stage, normalise events, LLM call cap, thought filtering
- [x] mcp_servers/knowledge: FastMCP server with knowledge_search stub; subprocess smoke test
- [x] ADK spikes: Vertex AI mode confirmed live (`GOOGLE_GENAI_USE_VERTEXAI=1`); GoogleSearchTool coexistence documented in docs/ADK_NOTES.md
- [x] Seed script for mcp_tools (2 tools: knowledge_search, generate_document); idempotency test
- [x] conftest guard: aborts if TEST_DATABASE_URL DB name ≠ `*_test` or equals DATABASE_URL
- [x] CI: drops DATABASE_URL from test step; adds `-m "not live and not integration"`
- [x] requirements.txt: google-adk==2.11.0, google-genai==2.28.0, fastmcp==4.0.10 pinned
- [x] normalise() handles ADK agent-call response shape `{"result": str}`; unit tests
- [x] docs: ARCHITECTURE.md, CONTRACTS.md env table, KNOWN_LIMITATIONS.md updated for Vertex switch
- [x] D3: Auth layer — login, /me, /users, global auth guard middleware, seed script (users + mcp_tools)
- [x] D3: Agents module — CRUD (agent + version), publish with all-failures collection (SELECT FOR UPDATE, concurrent double-publish guard), tool assignment, retire-on-publish
- [x] D3: 53 offline tests passing (including 20 agents tests covering all publish rules); conftest fixture isolation pattern established (no HTTP in fixtures, direct DB inserts + create_access_token)
- [x] D4: Frontend auth — login page, token/user localStorage + cookie mirror, route guard (proxy.ts), AuthProvider context, AppNav with user + logout
- [x] D4: Frontend agents — agent library list, create form (dynamic capabilities + tool checkboxes), agent detail with version management (inline edit, publish with per-failure display, add version pre-filled from published)
- [x] D4: Projects + work items backend — CRUD (projects, work items), worker assignment (ai_agent + human), unique name constraints, migration 0002, 18 tests
- [x] D4: Policy engine backend — policies, stages, checkpoints, publish with all-failures collection, stage renumbering, immutability on published, 28 tests; all 99 offline tests passing
- [x] D4: Policy generation endpoint — POST /work-items/{id}/policies/generate; Gemini via run_stage, structured JSON output, pre-flight validation (all-failures), 201 PolicyOut on success, 422 on validation failure, 502 on LLM error; 7 new tests (6 offline + 1 live); all 107 offline tests passing
- [x] D5: Projects + Work Items frontend — /projects list (inline create form), /projects/[id] detail (work item list + inline create form with agent version + user worker picker), /projects/[id]/work-items/[wiId] detail (read-only fields, workers list, Generate Policy button with 201/409/422/502 result states); new types: Project, WorkerOut, WorkItem in lib/types.ts
- [x] D5: Policy editor UI — /policies/[policyId] three-panel layout (agents left, workflow center, checkpoints right); add/edit/delete/reorder stages; per-stage and final_review checkpoints; publish with inline failure display; auto-nav from work item after generate; read-only published state; new types: StageOut, CheckpointOut, PolicyOut in lib/types.ts

### Next
Day 6 — Execution engine frontend (run work item, execution status, stage events, checkpoint approvals).

### Decision log
- LLM access is Vertex AI via ADC; AI Studio prepay was unfunded so `GOOGLE_GENAI_USE_VERTEXAI=1` is the only working path.
- Web search is deferred: coexistence proven (`bypass_multi_tools_limit=True`), but costs a minimum of 2 LLM calls per search invocation.
- Conftest guard added: tests abort if `TEST_DATABASE_URL` DB name does not end in `_test` or matches `DATABASE_URL`.
- CI runs `-m "not live and not integration"`: no Vertex AI calls or subprocess tests in CI.
- Cloud Run deploy and Cloud SQL migration rehearsal pushed to the Day 8–9 block.

### Blockers / open questions
- None.

### Backlog (ideas outside today's scope)
- google_search as a built-in tool (`server_key="__builtin__"`) — proposal in docs/ADK_NOTES.md; needs approval before implementation

## Credentials register (names and locations only — NEVER values)
| Name | Source | Stored in | Needed by |
|---|---|---|---|
| PROJECT_ID = `project-6c036441-c06e-4a0b-bbf` (project number `337434518869`) | B1 | This file (not secret) | Everything |
| Region = `us-central1` | B1 | This file | Cloud SQL, Run, Registry |
| JWT_SECRET | B4 | Secret Manager `jwt-secret`; local .env uses a different value | Backend |
| DB_PASSWORD | B4 | Secret Manager `db-password` | Cloud SQL (Day 8) |
| Instance connection name = `project-6c036441-c06e-4a0b-bbf:us-central1:seyarkai-db` | B7 | This file | Cloud Run (Day 8) |
| GEMINI_API_KEY | B9 | Secret Manager `gemini-api-key`; local .env | Runtime (Day 2) |
| Gemini key tier = `paid` (key lives in a billed project; confirm in AI Studio) | B9 | This file | Quota planning |
| VERTEX_SEARCH_LOCATION = `global`, VERTEX_SEARCH_DATA_STORE_ID = `knowledge-store` (engine `seyarkai-search`) | B10 | This file | Day 7 |
| docs-generator@project-6c036441-c06e-4a0b-bbf.iam.gserviceaccount.com | B8 | Impersonated, no key (org policy blocks keys) | Day 7 |
| DOCS_SHARE_WITH | your email | Local .env | Day 7 |
| backend-runtime@project-6c036441-c06e-4a0b-bbf.iam.gserviceaccount.com | B8 | This file | Cloud Run (Day 8) |
| Artifact Registry = `us-central1-docker.pkg.dev/project-6c036441-c06e-4a0b-bbf/seyarkai-images` | B8 | This file | Day 8 |
