# STATUS

Update at the end of every session. Every Claude Code session starts by reading this file,
CLAUDE.md, and the relevant docs/ sections.

## Current: Day 3 of 10 — Runtime, knowledge MCP, ADK spikes, tests
Date: 2026-10-04   Region: us-central1

### Done (Days 1–3)
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

### Next
Day 4 — Policy engine: policies, stages, checkpoints, publish validation; policy generation stub.

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
