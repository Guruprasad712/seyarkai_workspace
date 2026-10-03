# STATUS

Update at the end of every session. Every Claude Code session starts by reading this file,
CLAUDE.md, and the relevant docs/ sections.

## Current: Day 1 of 10 — Cloud setup, foundation, contracts, CI
Date: 2026-10-02   Region: us-central1

### Done
- [ ] Public repo, .gitignore, secret scanning + push protection
- [ ] Organizer eligibility message sent (reply saved)
- [ ] Project + billing linked (done), $100 budget alert (not confirmed)
- [x] APIs enabled
- [x] Secrets: jwt-secret, db-password, gemini-api-key (3; docs identity is keyless)
- [x] Cloud SQL seyarkai-db RUNNABLE; db + appuser created (connection test via gcloud sql connect not run)
- [x] Vertex AI Search data store created; test document searchable
- [x] Service accounts backend-runtime, docs-generator; Artifact Registry repo
- [x] Local: Postgres 16 `seyarkai_dev` + `seyarkai_test`, Python 3.11, .env populated
- [ ] Local: gcloud + ADC, Node 20+
- [ ] Docs committed (CLAUDE.md, ARCHITECTURE.md, CONTRACTS.md, KNOWN_LIMITATIONS.md)
- [x] Backend scaffold, single migration (17 tables), /health 200, pytest green (2/2)
- [ ] Frontend shell showing backend health
- [ ] CI: pytest + docker build of both images

### Next
Day 2 — Gemini + ADK spike in scratch/, then app/runtime and the knowledge MCP server.

### Blockers / open questions
- 

### Backlog (ideas outside today's scope)
- 

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
