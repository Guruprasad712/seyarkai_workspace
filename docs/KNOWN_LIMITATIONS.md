# Known Limitations

Accepted trade-offs for the hackathon build. Each entry: what, why, and what a production
version would do.

| # | Limitation | Why accepted | Production approach |
|---|---|---|---|
| 1 | JWT stored in browser localStorage | Simplest auth for a 10-day build | HttpOnly secure cookies + CSRF protection |
| 2 | Backend runs as a single Cloud Run instance (min=1, max=1) | Background executions run in-process | Durable task queue (Cloud Tasks / Pub/Sub) and horizontal scaling |
| 3 | An execution in progress is lost if the instance restarts mid-run | No durable worker | Resumable executions driven from persisted state by a queue |
| 4 | Knowledge freshness is age-based only (`last_verified_at`) | Clear, explainable signal | Content-change detection, owner workflows, decay modelling |
| 5 | Single tenant; no workspace isolation | No demo value | Workspace/tenant tables and scoped access |
| 6 | Users are created only by a seed script | No user-management UI in P0 | Admin UI or external identity provider |
| 7 | Workers cannot be changed after a work item is created | Out of scope (P2) | Worker edits with policy revalidation |
| 8 | All policy stages are AI tasks; humans participate only via checkpoints | Keeps the engine simple | Human task stages |
| 9 | Cloud SQL uses a shared-core tier (db-f1-micro) | Lowest cost for a demo | Dedicated-core tier sized to load |
| 10 | Cloud SQL backups are disabled | Saves cost; data is seed/demo data | Automated backups and point-in-time recovery |
| 11 | Cloud SQL has a public IP with no authorized networks (access by IAM through the connector only) | Simplest connection path for Cloud Run | Private IP with VPC connector |
| 12 | `GEMINI_API_KEY` is stored in Secret Manager but the key is not funded — live runtime uses `GOOGLE_GENAI_USE_VERTEXAI=1` with ADC/service account; the AI Studio key path is an untested fallback | Vertex AI is the real auth path; keeping the key avoids a cold-start error if ADC fails | Fund the AI Studio key or remove it; always use Vertex AI in production |
