# Architecture

## Pitch
Not a knowledge assistant that answers questions — a governed execution engine where AI
agents do real work, grounded in company knowledge that knows when it is stale, while
humans stay in control of what matters.

| Pillar | Capability |
|---|---|
| Access knowledge | Company Brain: corpus in Vertex AI Search, injected into every stage, each document labelled with its verification age |
| Collaborate | AI agents and human reviewers assigned to one Work Item in a shared live workspace |
| Make decisions | Checkpoints in a published policy pause execution until the assigned reviewer acts |
| Complete work | Multi-stage, tool-using ADK agents producing a real Google Doc deliverable |

## System diagram
```
                 Next.js (Cloud Run: frontend)
                            │ REST + SSE (fetch streaming, Bearer token)
                            ▼
┌──────────── FastAPI modular monolith (Cloud Run: backend) ────────────┐
│ auth │ agents │ projects │ work_items │ policies │ executions │ knowledge │
│                                                                        │
│ Engine: stages → knowledge injection → ADK run → events → checkpoints  │
│    │                                                                   │
│    ▼                                                                   │
│ runtime: ADK Runner + LlmAgent built from the stage's agent version    │
│    │ tools via ADK MCPToolset (stdio subprocesses, same container)     │
│    ├── mcp_servers.knowledge → knowledge_search → KnowledgeRetriever   │
│    └── mcp_servers.docs      → generate_document → Google Docs API     │
└────────────────────────────────────────────────────────────────────────┘
      │                 │                  │                  │
 Cloud SQL         Secret Manager    Vertex AI Search     Gemini (Vertex AI)
 (Postgres 16)                       (data store)         (AI Studio key = unfunded fallback)
```

## Decisions
| Area | Choice | Why |
|---|---|---|
| Backend | FastAPI, async SQLAlchemy 2, Alembic, Postgres | Relational model fits policies, stages, checkpoints |
| Agent runtime | ADK LlmAgent + Runner, one agent built per stage from that stage's published agent version | Native Google Agent Platform usage |
| Orchestration | Our own stage/checkpoint engine around ADK | Governance is the product; ADK does not provide it |
| LLM | Gemini via Vertex AI (`GOOGLE_GENAI_USE_VERTEXAI=1`); AI Studio key is an unfunded fallback for local dev without ADC | Live runtime uses Vertex; AI Studio key is not funded |
| Models | `GEMINI_MODEL_FAST` (execution, ask), `GEMINI_MODEL_SMART` (policy generation) | Names confirmed on Day 2, never hardcoded |
| Tools | Real MCP servers (FastMCP) over stdio via ADK MCPToolset | Real protocol, nothing extra to deploy |
| Knowledge search | `KnowledgeRetriever` interface; `VertexSearchRetriever` is the only production implementation; `FakeRetriever` for unit tests | Test seam, not a second backend |
| Freshness source of truth | `knowledge_documents.last_verified_at` in the database | Search gives relevance, DB gives freshness; re-verify never touches the index |
| Live updates | SSE endpoint polling `execution_events` | Stateless and restart-safe |
| Background work | FastAPI background task with its own DB session; start returns 202 | Non-blocking UI |
| Cloud Run (backend) | CPU always allocated, min=1, max=1, timeout 3600 s | Background work and SSE survive after response |
| Passwords | `bcrypt` library directly | passlib is unmaintained and breaks on current bcrypt |
| Tenancy | Single tenant | No workspace tables |
| Frontend | Next.js App Router, TS, Tailwind, shadcn/ui | Speed; UX is 10% of the score |
| CI | GitHub Actions: pytest against a Postgres service + docker build of both images | No local Docker |

## Module boundaries
| Module | Owns | Must not |
|---|---|---|
| core | Config, DB session, security helpers, error types | Contain business logic |
| auth | Login, current user, role dependencies | — |
| agents | Agents, versions, tool catalog, publish rules | Know about executions |
| projects, work_items | Projects, work items, worker assignment | — |
| policies | Policies, stages, checkpoints, publish validation, generation | Execute anything |
| executions | Engine, checkpoint responses, messages, ask, SSE, artifacts | Build ADK agents directly (uses runtime) |
| runtime | Building ADK agents, running a stage, normalising events | Touch the database |
| knowledge | Documents, retrievers, freshness, injection text | Know about executions |
| mcp_servers | Tool processes | Write execution rows |

The runtime boundary matters most: it receives everything as arguments (agent definition,
task text, tool config, guidance provider) and yields normalised events. The engine
persists them, so the engine is testable without a model.

## Execution lifecycle
```
POST /work-items/{id}/executions
  → validate: published policy, no active execution, stages non-empty
  → create execution (queued); work item → in_progress
  → 202 {execution_id}
  background task (own DB session):
    running; event execution.started
    for each stage from the current position:
      stage.started
      retrieve knowledge → knowledge.retrieved
      compose task (work item + stage + previous outputs + knowledge + pending guidance)
      runtime.run_stage(...) → tool.called / tool.result / agent.message
      persist stage output as a message; record artifacts from tool results
      stage.completed
      checkpoint on this stage? → waiting_for_approval, STOP
    all stages done: final_review exists → pause, STOP; otherwise completed

POST /executions/{id}/checkpoints/{cid}/respond
  → authorise (assignee or super_admin), record response
  → reject: execution failed
  → approve: final_review → execution + work item completed
             otherwise → resume in a new background task from the next stage
```

## Deployment topology
| Component | Service | Notes |
|---|---|---|
| Frontend | Cloud Run `frontend` | Next.js standalone output |
| Backend + MCP servers | Cloud Run `backend` | MCP servers as stdio subprocesses in the same container |
| Database | Cloud SQL Postgres 16 (`seyarkai-db`) | Cloud SQL Python connector or Unix socket |
| Secrets | Secret Manager | Injected as env vars at deploy |
| Knowledge index | Vertex AI Search data store `knowledge-store` (global) | Relevance only |
| Images | Artifact Registry `seyarkai-images` | Built in CI / Cloud Build |

All regional services (Cloud SQL, Cloud Run, Artifact Registry) use one region, recorded in STATUS.md.
