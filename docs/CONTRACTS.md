# Contracts

Changes to this file require explicit approval. Code follows this document; if they
disagree, stop and ask.

## D1. Data model (17 tables)

Conventions:
- Primary keys are UUIDs generated in Python.
- Every table has `created_at` and `updated_at` unless stated otherwise.
- Status columns are VARCHAR, validated in the application layer (no native enums).
- Every foreign key is indexed.

### users
| Column | Type | Notes |
|---|---|---|
| id | uuid | PK |
| email | varchar, unique | Login identifier |
| name | varchar | |
| hashed_password | varchar | bcrypt |
| role | varchar | `super_admin` or `member` |
| status | varchar | `active` or `inactive` |

### agents
| Column | Type | Notes |
|---|---|---|
| id | uuid | PK |
| agent_code | varchar, unique | System-assigned `agent-0001` from a Postgres sequence; never editable |
| name | varchar, unique | Case-sensitive unique |
| description | text | |
| role_purpose | varchar | |
| status | varchar | `draft`, `active`, `inactive` |

### agent_versions
| Column | Type | Notes |
|---|---|---|
| id | uuid | PK |
| agent_id | uuid | FK agents |
| version | varchar | `"1.0"`, `"2.0"`, … system-assigned |
| instructions | text | |
| capabilities | jsonb | Array of `{name, description}`; at least one required at save |
| status | varchar | `draft`, `published`, `retired` |
| published_at | timestamptz, nullable | |

### mcp_tools (seeded catalog)
| Column | Type | Notes |
|---|---|---|
| id | uuid | PK |
| name | varchar | Display name, e.g. "Knowledge Search" |
| tool_name | varchar, unique | e.g. `knowledge_search` |
| server_key | varchar | e.g. `knowledge`, `docs` — maps to an MCP server module |
| description | text | Shown to users and to the model |
| status | varchar | `active` or `inactive` |

### agent_version_tools
`agent_version_id` (FK), `mcp_tool_id` (FK); composite PK.

### projects
id, name, description, status (`active`/`inactive`), created_by (FK users).

### work_items
| Column | Type | Notes |
|---|---|---|
| id | uuid | PK |
| project_id | uuid | FK projects |
| name | varchar | Short display title |
| objective | text | What must be achieved |
| description | text | Context, constraints, stakeholders |
| expected_outcome | text | The deliverable, not the process |
| status | varchar | `new`, `in_progress`, `completed` |
| created_by | uuid | FK users |

### work_item_workers
| Column | Type | Notes |
|---|---|---|
| id | uuid | PK |
| work_item_id | uuid | FK work_items |
| worker_type | varchar | `ai_agent` or `human` |
| agent_version_id | uuid, nullable | FK; set iff `ai_agent` |
| user_id | uuid, nullable | FK; set iff `human` |

A CHECK constraint enforces that exactly one of the two FKs is set and that it matches
`worker_type`. The service validates the same rule first and returns 422, so the
constraint never surfaces as a raw error.

### policies
| Column | Type | Notes |
|---|---|---|
| id | uuid | PK |
| work_item_id | uuid | FK |
| version | int | 1, 2, … |
| status | varchar | `draft` or `published` |
| generated_by | varchar | `manual` or `llm` |
| published_by | uuid, nullable | FK users |
| published_at | timestamptz, nullable | |

### policy_stages
| Column | Type | Notes |
|---|---|---|
| id | uuid | PK |
| policy_id | uuid | FK |
| sequence | int | Always 1..n, contiguous, derived from order |
| name | varchar | |
| description | text | The stage's task instruction |
| expected_output | text | |
| agent_version_id | uuid | FK; must be an AI worker on the work item |

All stages are AI tasks. Human involvement happens only through checkpoints.

### checkpoints
| Column | Type | Notes |
|---|---|---|
| id | uuid | PK |
| policy_id | uuid | FK |
| stage_id | uuid, nullable | FK; null only for `final_review` |
| type | varchar | `approval`, `review`, `input`, `final_review` |
| assigned_user_id | uuid | FK users; must be a human worker on the work item |
| instruction | text | What the reviewer should check |

### executions
| Column | Type | Notes |
|---|---|---|
| id | uuid | PK |
| work_item_id | uuid | FK |
| policy_id | uuid | FK |
| execution_number | int | Count of prior executions + 1 |
| status | varchar | See D2 |
| current_stage_id | uuid, nullable | FK; the running stage, or the stage just completed when paused |
| blocking_checkpoint_id | uuid, nullable | FK; set only while paused |
| started_at, completed_at | timestamptz, nullable | |
| error | text, nullable | Human-readable failure reason |

### execution_events
id, execution_id (FK), stage_id (nullable FK), event_type, actor_type
(`system`/`agent`/`human`), actor_id (nullable), payload (jsonb), created_at.
Index on `(execution_id, created_at)`. Append-only; never updated (no `updated_at`).

### messages
| Column | Type | Notes |
|---|---|---|
| id | uuid | PK |
| execution_id | uuid | FK |
| stage_id | uuid, nullable | FK |
| sender_type | varchar | `agent`, `human`, `system` |
| sender_id | uuid, nullable | |
| message_type | varchar | `stage_output`, `guidance`, `question`, `answer`, `error` |
| content | text | |
| consumed_at | timestamptz, nullable | For `guidance`: when injected into a model call |

### checkpoint_responses
id, checkpoint_id (FK), execution_id (FK), responded_by (FK users),
decision (`approve`/`reject`), comment, input (jsonb, nullable).

### artifacts
id, execution_id (FK), stage_id (FK), name, type (`google_doc` or `html`), url, created_at.

### knowledge_documents
| Column | Type | Notes |
|---|---|---|
| id | uuid | PK |
| title | varchar | |
| content | text | |
| source | varchar | Owner or origin, e.g. "Procurement Policy Office" |
| last_verified_at | timestamptz | Source of truth for freshness |
| verified_by | uuid, nullable | FK users |
| external_id | varchar, nullable | Document ID in Vertex AI Search |

## D2. Status lifecycles
| Entity | Transitions |
|---|---|
| Agent | `draft` → `active` (first version published) → `inactive` (manual) |
| Agent version | `draft` → `published` → `retired` (when a newer version is published). At most one published per agent |
| Work item | `new` → `in_progress` (first execution created) → `completed` (final review approved) |
| Policy | `draft` → `published`. Published policies are immutable |
| Execution | `queued` → `running` → `waiting_for_approval` ⇄ `running` → `completed`; `failed` from any non-terminal state |

## D3. Agent contract
- **Create** `POST /agents`: creates the agent and version 1.0 (draft) in one transaction.
  Request: name, description, role_purpose, instructions, capabilities (≥1), tool_ids
  (optional). Duplicate name → 409. Unknown or inactive tool → 422.
- **Add version** `POST /agents/{id}/versions`: new draft, version = highest + 1.0;
  the client pre-fills from the current published version.
- **Edit version** `PATCH /agents/{id}/versions/{vid}`: draft only, otherwise 409.
- **Publish** `POST /agents/{id}/versions/{vid}/publish`: collects all failures:

| Code | Rule |
|---|---|
| not_draft | Version must be draft |
| missing_instructions | Instructions non-empty |
| no_capabilities | At least one capability |
| no_tools | At least one tool |
| inactive_tool | Every tool active |

  On success, in one transaction: version → `published`; any previous published version
  → `retired`; agent → `active` if it was `draft`.
- **Rename** `PATCH /agents/{id}`: name uniqueness check excludes the agent itself.

## D4. Work item contract
- **Create** `POST /projects/{id}/work-items`: name, objective, description,
  expected_outcome (all required), workers (≥1). Each AI worker references a published
  agent version (else 422). Each human worker references an active user. Status is `new`.
- **Edit** `PATCH /work-items/{id}`: text fields only. Worker changes after creation are
  out of scope (P2).
- Detail responses include resolved worker display data (agent name and version, user
  name and email) so the frontend never joins IDs.

## D5. Policy contract
- **Drafts:** at most one draft per work item (409 otherwise). A new version of a
  published policy is a new draft (P1 UI).
- **Stages:** create/update/delete only while draft. Deleting renumbers the rest 1..n.
  A stage with an attached checkpoint cannot be deleted (422 `stage_has_checkpoints`).
  Reorder (P1) sends the full ordered list of stage IDs; the server rewrites sequences in
  one transaction.
- **Checkpoints:** `approval`, `review`, `input` require a `stage_id` in this policy.
  `final_review` must have `stage_id = null`. Every checkpoint needs `assigned_user_id`,
  a human worker on the work item.

Publish validation (collect all failures):

| Code | Rule |
|---|---|
| not_draft | Policy is draft |
| no_stages | At least one stage |
| sequence_not_contiguous | Sequences are exactly 1..n (defensive) |
| stage_worker_not_assigned | Each stage's agent version is an AI worker on the work item |
| stage_agent_not_published | Each stage's agent version is still published |
| missing_final_review / multiple_final_reviews | Exactly one final review |
| checkpoint_assignee_invalid | Each assignee is an active human worker on the work item |
| multiple_checkpoints_on_stage | At most one checkpoint per stage |

Failure response:
```json
{"detail": {"error": "publish_validation_failed",
            "failures": ["no_stages: policy has no stages", "..."]}}
```

**Generation** `POST /work-items/{id}/policies/generate` — only when the work item has no
policy yet (P0; regeneration is P1). Gemini structured output with this schema:
```json
{
  "stages": [
    {"name": "string", "description": "string",
     "expected_output": "string", "worker_ref": "string"}
  ],
  "checkpoints": [
    {"type": "approval|review|input|final_review",
     "stage_index": "integer or null", "assignee_ref": "string",
     "instruction": "string"}
  ]
}
```
- `worker_ref` / `assignee_ref` are `work_item_workers.id` values listed in the prompt.
- `stage_index` is the zero-based array position; array order is execution order. The
  model never supplies a sequence number.
- The prompt includes work item text, each AI worker's name, capabilities and tools, and
  each human worker's name. It instructs: prefer AI agents for work, add checkpoints where
  human judgement matters, end with exactly one final review.
- Pre-flight validation runs on the whole proposal before any row is written. Any failure
  → 422 `{"error": "generation_validation_failed", "failures": [...]}` with zero rows
  persisted. Upstream model error → 502. Success creates a draft with
  `generated_by = "llm"`, returned in the policy detail shape.

## D6. Execution contract
- **Start** `POST /work-items/{id}/executions`: requires a published policy (latest
  published version) and no execution in `queued`, `running` or `waiting_for_approval`
  (409). A failed execution may be retried. Returns `202 {"execution_id": ...}`.
- **Stage task composition** (the stage's user message):
  1. Work item objective, description, expected outcome.
  2. Stage name, description, expected output ("You are performing stage 2 of 3: …").
  3. Previous stage outputs in this execution (truncated to a configured limit).
  4. The knowledge block (D8).
  5. Unconsumed human guidance, then marked consumed.
  The system instruction is the published version's instructions plus capability names.
- **Running a stage:** the engine calls
  `runtime.run_stage(agent_definition, task_text, tools, guidance_provider)`, which builds
  an ADK LlmAgent from the stage's own agent version, runs it with `max_llm_calls` from
  config, and yields normalised events. A `before_model_callback` calls
  `guidance_provider()`; new guidance is appended as a user turn labelled as guidance from
  the named person and marked consumed. Thought parts are discarded.
- **Artifacts:** a `tool.result` from `generate_document` creates an artifacts row and
  emits `artifact.created`.
- **Pausing:** after a stage completes, if a checkpoint is attached: status
  `waiting_for_approval`, set `blocking_checkpoint_id`, emit `checkpoint.triggered` and
  `execution.paused`, stop. After the last stage, the same for the final review.
- **Respond** `POST /executions/{id}/checkpoints/{cid}/respond`, body
  `{decision, comment?, input?}`:
  - 422 if the execution is not waiting or `cid` is not the blocking checkpoint.
  - 403 unless the caller is the assignee or a super admin.
  - Record the response, clear `blocking_checkpoint_id`, emit `checkpoint.resolved`.
  - `reject`: execution `failed` with the comment as error; work item stays `in_progress`.
  - `approve` on final review: execution `completed`, work item `completed`, emit
    `execution.completed`.
  - `approve` otherwise: `running`, emit `execution.resumed`, new background task from the
    next stage.
  - For `input` checkpoints, the input is stored and added as guidance for the next stage.
- **Guidance** `POST /executions/{id}/messages`, body `{content}`: stores a guidance
  message, emits `human.message`. Allowed in any non-terminal state.
- **Ask** `POST /executions/{id}/ask`, body `{question}` (P1): answer-only model call using
  the most recent stage agent's instructions and the conversation; stores Q and A; emits
  `executor.response`. Never changes execution state.
- **Failure:** any unhandled stage exception → `failed` with a readable error, emit
  `execution.failed`. Never left in `running`.
- **Reads:** `GET /executions/{id}` returns status, stages with progress, blocking
  checkpoint (object or null), messages, artifacts. `GET /work-items/{id}/executions`
  lists history.

## D7. Events and streaming
| Event type | Actor | Payload |
|---|---|---|
| execution.started | system | `{execution_number}` |
| stage.started | system | `{sequence, name, agent_name}` |
| knowledge.retrieved | system | `{documents: [{id, title, age_days, freshness}], stale_count}` |
| tool.called | agent | `{tool_name, arguments}` (long values truncated) |
| tool.result | agent | `{tool_name, summary}` (truncated; never full raw output) |
| agent.message | agent | `{message_id, preview}` |
| human.message | human | `{message_id, preview}` |
| executor.response | agent | `{message_id, preview}` |
| artifact.created | agent | `{artifact_id, name, url}` |
| stage.completed | system | `{sequence}` |
| checkpoint.triggered | system | `{checkpoint_id, type, assignee_name}` |
| execution.paused | system | `{reason: "checkpoint"}` |
| checkpoint.resolved | human | `{checkpoint_id, decision}` |
| execution.resumed | system | `{}` |
| execution.completed | system | `{}` |
| execution.failed | system | `{error}` |

Each event is committed as it happens. Payloads never contain model thought content,
secrets or full tool outputs.

**Stream** `GET /executions/{id}/stream?after=<event_id>` (SSE): polls every 500 ms for
newer events; sends `id: <event_id>`, `event: <type>`, `data: <json>`; comment heartbeat
every 15 s; closes when the execution is terminal and all events are sent. The client uses
`fetch` with the Authorization header (no token in the URL), resumes from the last seen ID
after a disconnect, and refetches `GET /executions/{id}` on any `checkpoint.*` or
terminal event.

## D8. Company Brain
Freshness from `last_verified_at`:

| Label | Rule (configurable) |
|---|---|
| fresh | age ≤ `KNOWLEDGE_AGEING_DAYS` (90) |
| ageing | age ≤ `KNOWLEDGE_STALE_DAYS` (180) |
| stale | older than `KNOWLEDGE_STALE_DAYS` |

```
KnowledgeRetriever.search(query: str, top_k: int) -> list[KnowledgeHit]
KnowledgeHit = {document_id, title, snippet, score, last_verified_at, age_days, freshness}
```
- `VertexSearchRetriever`: the only production implementation. Queries the data store,
  maps result IDs to `knowledge_documents` rows, takes freshness from the database.
- `FakeRetriever`: in-memory, unit tests only.

Injection block appended to each stage task:
```
Company knowledge relevant to this stage:
[1] Supplier Payment Terms Policy — last verified 212 days ago — STALE:
    may be outdated; state any reliance on it explicitly and recommend re-verification.
    <snippet>
[2] Supplier Onboarding Policy — last verified 20 days ago — fresh.
    <snippet>
```
The agent instruction includes: cite knowledge by title; call out reliance on stale sources.

Knowledge API: `GET /knowledge` (with freshness); `POST /knowledge` (title, content,
source, optional last_verified_at defaulting to now; also indexes in Vertex AI Search);
`POST /knowledge/{id}/verify` (sets `last_verified_at = now`, `verified_by = caller`,
database only); `GET /knowledge/search?q=` (debug, P1).

Vertex AI Search mapping: each document is imported with `id = knowledge_documents.id`,
its content, and `structData` `{title, source, last_verified_at}`. The database remains
the source of truth for freshness.

## D9. MCP tools
| Tool | Server | Input | Output |
|---|---|---|---|
| knowledge_search | knowledge | `{query: string, top_k?: int}` | `{results: [KnowledgeHit]}` |
| generate_document | docs | `{title: string, content_markdown: string}` | `{document_id, url}` |

- FastMCP apps inside the backend package, launched as `python -m app.mcp_servers.<name>`,
  configured through environment variables.
- Tool and parameter descriptions are explicit (e.g. "query is free-text describing the
  information needed, not a file name").
- `generate_document` uses keyless impersonation of the docs-generator service account
  (short-lived tokens via the IAM Credentials API; no key files), calls the Docs + Drive
  APIs, converts Markdown
  headings, lists and paragraphs to Docs formatting, and shares the result with
  `DOCS_SHARE_WITH` as reader. Fallback: render HTML, store it, return an app URL, record
  the artifact as `html`.
- An agent receives only the tools on its published version; the engine filters by
  `tool_name`.

## D10. Auth
- `POST /auth/login {email, password}` → `{access_token, token_type: "bearer", user}`.
  Wrong password, unknown email and inactive user return the same 401 message.
- JWT HS256, claims `sub` (user ID) and `role`, expiry `JWT_EXPIRE_HOURS` (12).
- `GET /auth/me` returns the current user.
- Every endpoint except login and health requires a valid token.
- Frontend stores the token in localStorage (accepted trade-off, see KNOWN_LIMITATIONS).

| Action | member | super_admin |
|---|---|---|
| Create agents, projects, work items, policies; publish; execute | ✓ | ✓ |
| Send guidance, ask executor | ✓ | ✓ |
| Respond to a checkpoint | Only if assigned | Any |
| Create users | Seed script only (P0) | Seed script only (P0) |

## D11. API surface
| Method | Path | Success | Notes |
|---|---|---|---|
| POST | /auth/login | 200 | |
| GET | /auth/me | 200 | |
| GET | /health | 200 | Checks DB; no auth |
| GET | /users | 200 | Assignment pickers |
| GET | /mcp-tools | 200 | Catalog |
| POST / GET | /agents | 201 / 200 | |
| GET / PATCH | /agents/{id} | 200 | |
| POST | /agents/{id}/versions | 201 | |
| PATCH | /agents/{id}/versions/{vid} | 200 | Draft only |
| POST | /agents/{id}/versions/{vid}/publish | 200 | 422 with failures |
| POST / GET | /projects | 201 / 200 | List includes work item counts |
| GET / PATCH | /projects/{id} | 200 | |
| POST / GET | /projects/{id}/work-items | 201 / 200 | |
| GET / PATCH | /work-items/{id} | 200 | |
| POST / GET | /work-items/{id}/policies | 201 / 200 | |
| POST | /work-items/{id}/policies/generate | 201 | 422 / 502 |
| GET | /policies/{id} | 200 | Stages and checkpoints included |
| POST | /policies/{id}/stages | 201 | |
| PATCH / DELETE | /policies/{id}/stages/{sid} | 200 / 204 | |
| PUT | /policies/{id}/stages/order | 200 | P1 |
| POST | /policies/{id}/checkpoints | 201 | |
| PATCH / DELETE | /policies/{id}/checkpoints/{cid} | 200 / 204 | |
| POST | /policies/{id}/publish | 200 | 422 with failures |
| POST / GET | /work-items/{id}/executions | 202 / 200 | |
| GET | /executions/{id} | 200 | |
| GET | /executions/{id}/stream | 200 | SSE |
| POST | /executions/{id}/messages | 201 | Guidance |
| POST | /executions/{id}/ask | 200 | P1 |
| POST | /executions/{id}/checkpoints/{cid}/respond | 200 | 403 / 422 |
| GET / POST | /knowledge | 200 / 201 | |
| POST | /knowledge/{id}/verify | 200 | |

## D12. Error conventions
- Not found 404; validation 422; conflict (duplicate name, existing draft, active
  execution) 409; unauthenticated 401; not permitted 403; upstream model failure 502.
- Body is always `{"detail": ...}`; `detail` is a string or an object with `error` and
  optionally `failures`.
- The frontend unwraps through one helper that handles both shapes.

## Environment variables
| Variable | Example | Used by |
|---|---|---|
| DATABASE_URL | `postgresql+asyncpg://…` | Backend |
| TEST_DATABASE_URL | local test database, `postgresql+asyncpg://…/seyarkai_test` | pytest |
| JWT_SECRET, JWT_EXPIRE_HOURS | random, `12` | Auth |
| GEMINI_API_KEY | from AI Studio | Runtime, generation |
| GOOGLE_GENAI_USE_VERTEXAI | `false` | Runtime |
| GEMINI_MODEL_FAST, GEMINI_MODEL_SMART | confirmed Day 2 | Runtime, generation |
| MAX_LLM_CALLS_PER_STAGE | `8` | Runtime |
| KNOWLEDGE_AGEING_DAYS, KNOWLEDGE_STALE_DAYS | `90`, `180` | Knowledge |
| KNOWLEDGE_TOP_K | `5` | Knowledge |
| GOOGLE_CLOUD_PROJECT | project ID | Vertex retriever |
| VERTEX_SEARCH_LOCATION, VERTEX_SEARCH_DATA_STORE_ID | `global`, from console | Vertex retriever |
| DOCS_SERVICE_ACCOUNT_EMAIL, DOCS_SHARE_WITH | `docs-generator@project-6c036441-c06e-4a0b-bbf.iam.gserviceaccount.com`, demo email | Docs MCP server |
| CORS_ORIGINS | frontend URL | Backend |
| NEXT_PUBLIC_API_BASE_URL | backend URL | Frontend |
