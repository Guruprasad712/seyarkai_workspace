# ADK Notes — ground truth from installed source

Verified against installed packages in `scratch/.venv`. Do not rely on memory for any of
this — the source was read directly and all live samples are from real runs.

---

## Versions

| Package | Version |
|---|---|
| `google-adk` | 2.11.0 |
| `fastmcp` | 4.0.10 |

---

## LLM backend: Vertex AI (confirmed working)

| Env var | Value |
|---|---|
| `GOOGLE_GENAI_USE_VERTEXAI` | `true` |
| `GOOGLE_CLOUD_PROJECT` | `project-6c036441-c06e-4a0b-bbf` |
| `GOOGLE_CLOUD_LOCATION` | `us-central1` |
| Auth | Application Default Credentials (`gcloud auth application-default login`) |
| Model | `gemini-2.5-flash` |

**Do NOT set `GOOGLE_API_KEY` in Vertex mode.** When `GOOGLE_CLOUD_PROJECT` and
`GOOGLE_CLOUD_LOCATION` are both set alongside `GOOGLE_GENAI_USE_VERTEXAI=true`, the SDK
nulls out any API key — but having it set can trigger the "Both keys set" warning and
causes confusion. Keep them mutually exclusive.

Entry-point startup pattern (handles both modes):

```python
import os
from dotenv import load_dotenv
load_dotenv("../.env")

# Vertex mode: env vars drive the Client; no API key alias needed.
# API key mode: alias GEMINI_API_KEY → GOOGLE_API_KEY (ADK checks GOOGLE_API_KEY first).
_use_vertex = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("true", "1")
if not _use_vertex and not os.getenv("GOOGLE_API_KEY") and os.getenv("GEMINI_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]
```

### API key mode (fallback)

`GEMINI_API_KEY` prepay credits depleted as of 2026-10-04. If restored, set
`GOOGLE_GENAI_USE_VERTEXAI=false` and the alias block above handles the key.
ADK reads `GOOGLE_API_KEY` first, then `GEMINI_API_KEY` (from `_gcp_metadata.py`).

---

## Imports — confirmed from source and live runs

```python
# Agent and runner
from google.adk.agents import LlmAgent          # LlmAgent; Agent is an alias
from google.adk.runners import InMemoryRunner   # convenience subclass, no session_service needed
from google.adk import Runner                   # full Runner, requires session_service=

# Types (NOT from google.adk — from google.genai)
from google.genai import types                  # types.Content, types.Part, etc.

# RunConfig and callbacks
from google.adk.agents import RunConfig
from google.adk.agents.callback_context import CallbackContext   # type alias for Context
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.agents.invocation_context import LlmCallsLimitExceededError

# MCP toolset
from google.adk.tools import McpToolset                                        # preferred name
from google.adk.tools import MCPToolset                                        # deprecated alias
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

# FastMCP server
from fastmcp import FastMCP
```

---

## Runner

### InMemoryRunner (use for spikes and tests)

```python
runner = InMemoryRunner(agent=agent, app_name="my-app")
# Creates in-memory session/artifact/memory services automatically.
```

### Full Runner (use in production engine)

```python
from google.adk import Runner
runner = Runner(
    agent=agent,             # exactly one of: agent, app, node
    app_name="my-app",       # required when agent= is used
    session_service=...,     # REQUIRED
    artifact_service=None,   # optional
    memory_service=None,     # optional
)
```

### run_async

```python
async for event in runner.run_async(
    user_id="u1",
    session_id=session.id,
    new_message=types.Content(role="user", parts=[types.Part(text="...")]),
    run_config=RunConfig(max_llm_calls=10),   # optional
):
    ...
```

Returns `AsyncGenerator[Event, None]`.

---

## Event shape

`Event` inherits from `LlmResponse`. Key fields:

| Field | Type | Notes |
|---|---|---|
| `event.author` | `str` | `'user'` or agent name |
| `event.content` | `types.Content \| None` | has `.role` and `.parts` |
| `event.content.parts` | `list[types.Part]` | each part has text / function_call / function_response / thought |
| `event.is_final_response()` | `bool` (method) | **method, not property** |
| `event.partial` | `bool \| None` | True = streaming fragment |
| `event.usage_metadata` | `types.GenerateContentResponseUsageMetadata \| None` | token counts |
| `event.error_code` | `str \| None` | set on model error events |
| `event.error_message` | `str \| None` | set on model error events |

Checking parts:

```python
for part in event.content.parts:
    if getattr(part, 'text', None):               # text response
    if getattr(part, 'function_call', None):      # agent wants to call a tool
        part.function_call.name
        part.function_call.args
    if getattr(part, 'function_response', None):  # tool result
        part.function_response.response
    if getattr(part, 'thought', None):            # model thought (do NOT persist or stream)
```

### Live event samples — spike1 (simple text, no tools)

Model: `gemini-2.5-flash`, Vertex AI, prompt: `"Say hello in one sentence."`

```
--- EVENT ---
  author:            'spike1'
  is_final_response: True
  partial:           None
  usage_metadata:    cache_tokens_details=None cached_content_token_count=None
                     candidates_token_count=3
                     prompt_token_count=26
                     thoughts_token_count=16
                     total_token_count=45
                     traffic_type=ON_DEMAND
  text:              'Hello there!'
```

Observations:
- Only **one event** was yielded for a simple text response
- `usage_metadata` is populated on the final event (not None) — includes `thoughts_token_count`
  for the thinking budget even when thoughts are not streamed
- `partial` is `None` (not `False`) on the non-streaming final event

### Live event samples — spike2 (tool call via McpToolset)

Model: `gemini-2.5-flash`, Vertex AI, prompt: `"Echo 'hello world' using the echo tool."`

```
McpToolset class: McpToolset
StdioConnectionParams class: StdioConnectionParams
  author='spike2'  final=False  fn_call=echo({'message': 'hello world'})
  author='spike2'  final=False  fn_resp={'meta': {'fastmcp': {'wrap_result': True}}, 'content': [{'type': 'text', 'text': 'ECHO: hello world'}], 'structuredContent': {'result': 'ECHO: hello world'}, 'isError': False}
  author='spike2'  final=True   text='ECHO: hello world'
```

Observations:
- Three events: function_call → function_response → final text
- Neither the function_call nor function_response events are `is_final_response=True`
- FastMCP wraps the return value: `structuredContent.result` holds the plain return value;
  `content[0].text` holds its string form
- `function_call.args` is a dict: `{'message': 'hello world'}`

### Live event samples — spike3 (before_model_callback + max_llm_calls)

Model: `gemini-2.5-flash`, Vertex AI, `max_llm_calls=2`, with an `adder_tool`

```
RunConfig.max_llm_calls = 2
LlmCallsLimitExceededError import: <class 'google.adk.agents.invocation_context.LlmCallsLimitExceededError'>
  [callback] before_model_callback #1
    ctx type: Context
    req type: LlmRequest
  event: author='spike3'  final=False
  event: author='spike3'  final=False
  [callback] before_model_callback #2
    ctx type: Context
    req type: LlmRequest
  event: author='spike3'  final=False
  event: author='spike3'  final=False
  [callback] before_model_callback #3   ← attempt #3 triggers the limit check
    ctx type: Context
    req type: LlmRequest
  event: author='spike3'  final=True
  CAUGHT LlmCallsLimitExceededError: Max number of llm calls limit of `2` exceeded
```

Observations:
- `before_model_callback` fires once per LLM call attempt, including the one that hits the limit
- At call #3, the limit check fires and raises `LlmCallsLimitExceededError`
- The exception propagates out of `runner.run_async` as a generator exception — the `try/except`
  around the `async for` catches it correctly
- **ADK also logs its own traceback to stderr** after the exception — this is internal noise,
  not a second exception. The engine should treat the caught exception as the authoritative signal.
- The actual `ctx` runtime type is `Context`, not `CallbackContext` (the import alias works,
  but `type(ctx).__name__` prints `'Context'`)

---

## McpToolset — stdio server

```python
toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,       # or 'python', 'node', etc.
            args=["my_server.py"],
        ),
        timeout=10.0,
    ),
)

agent = LlmAgent(
    model="gemini-2.5-flash",
    name="my-agent",
    tools=[toolset],          # attach here
)

# cleanup
await toolset.close()
```

`McpToolset` is **not** a context manager — attach to agent via `tools=`, Runner calls
`close()` on shutdown, or call it manually.

### Minimal FastMCP stdio server

```python
from fastmcp import FastMCP

mcp = FastMCP("server-name")

@mcp.tool()
def my_tool(arg: str) -> str:
    """Description shown to the model."""
    return f"result: {arg}"

if __name__ == "__main__":
    mcp.run(transport="stdio")   # blocking; default transport is already stdio
```

---

## before_model_callback

```python
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse

def before_model_callback(
    ctx: CallbackContext,   # runtime type is Context; CallbackContext is an alias
    req: LlmRequest,
) -> LlmResponse | None:
    # Return None → let the model call proceed.
    # Return an LlmResponse → skip the model call and use this response.
    return None

agent = LlmAgent(..., before_model_callback=before_model_callback)
```

- `CallbackContext` is a type alias for `Context` — `type(ctx).__name__` returns `'Context'`
- Can be sync or async
- Also accepts a list: `before_model_callback=[cb1, cb2]`

---

## RunConfig and max_llm_calls

```python
from google.adk.agents import RunConfig

run_config = RunConfig(max_llm_calls=10)
# Default is 500. Setting <= 0 disables the limit.
# Also overridable via ADK_MAX_LLM_CALLS env var.
```

Pass to `runner.run_async(..., run_config=run_config)`.

### Termination when limit is hit

**An exception is raised, not a terminal event:**

```python
from google.adk.agents.invocation_context import LlmCallsLimitExceededError

try:
    async for event in runner.run_async(..., run_config=run_config):
        ...
except LlmCallsLimitExceededError as e:
    # e.g. "Max number of llm calls limit of `2` exceeded"
    handle_limit(e)
```

The async generator raises `LlmCallsLimitExceededError` mid-iteration. ADK also prints
its own traceback to stderr — ignore it. The engine must catch this exception and set
the execution status to `failed`.

---

## Gotchas

1. `types` is from `google.genai`, not `google.adk`. `from google.adk import types` →
   `ImportError`.

2. `is_final_response()` is a **method** — `event.is_final_response()`, not
   `event.is_final_response`.

3. In API key mode: `GOOGLE_API_KEY` must be set before ADK initialises. Alias from
   `GEMINI_API_KEY` at the top of each entry point. In Vertex mode: do not set any API key.

4. `gemini-2.5-flash` works on Vertex AI (confirmed). Do not use versioned suffixes like
   `-001` — those are 404 on Vertex. Do not use alias names like `gemini-flash-latest` —
   those are not valid Vertex model names.

5. `MCPToolset` is a deprecated alias — use `McpToolset`.

6. `McpToolset` is not a context manager. Call `await toolset.close()` explicitly, or let
   the Runner do it on shutdown.

7. `LlmCallsLimitExceededError` is raised mid-generator, not yielded as an event — wrap
   the `async for` loop in a `try/except`. ADK's stderr traceback after this is internal
   noise; the caught exception is the authoritative signal.

8. `event.partial` is `None` (not `False`) on a non-streaming final event — check with
   `if event.partial` not `if event.partial is False`.

9. `usage_metadata` on a final event includes `thoughts_token_count` — the model uses a
   thinking budget internally even when thoughts are not visible in the event stream.

10. **Windows asyncio subprocess policy (uvicorn `--reload`)**

    ADK's `McpToolset` launches MCP servers as asyncio subprocesses. On Windows,
    `asyncio.subprocess` requires `ProactorEventLoop`. Python 3.11+ defaults to it, so
    no fix is needed on Python 3.11. If a `NotImplementedError` appears at subprocess
    creation (e.g. under an older Python or a framework that forces `SelectorEventLoop`),
    add this at the top of the entry point **before** any `asyncio.run()`:

    ```python
    import asyncio, sys
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    ```

    For uvicorn specifically, pass `--loop asyncio` (which picks the platform default,
    ProactorEventLoop on Windows 3.11+). The `--reload` watchfiles reloader uses a
    separate process and does not change the child server's event loop policy.

    **Confirmed working on Python 3.11.5 / Windows 11 with `uvicorn --reload`** — no
    policy override needed at this Python version.

---

## Google Search Tool + MCP / Function Tool Coexistence

Tested live on Vertex AI (`gemini-2.5-flash`, ADK 2.11.0) — 2026-10-04.

### Result

| Mode | Outcome |
|---|---|
| `GoogleSearchTool()` alone (no other tools) | **PASS** — agent.message returned |
| `GoogleSearchTool()` + `FunctionTool` (bypass=False) | **FAIL** — Gemini API 400 |
| `GoogleSearchTool(bypass_multi_tools_limit=True)` + `FunctionTool` | **PASS** — agent.message returned |

### Exact error (bypass=False with a FunctionTool)

```
google.genai.errors.ClientError: 400 INVALID_ARGUMENT.
  'message': 'Unable to submit request because Multiple tools are supported only
              when they are all search tools.'
  'status': 'INVALID_ARGUMENT'
```

Vertex AI reference: https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/gemini

### Workaround: `bypass_multi_tools_limit=True`

When `bypass_multi_tools_limit=True` is set, ADK wraps `GoogleSearchTool` in a
`GoogleSearchAgentTool` sub-agent (`create_google_search_agent(model)`). The parent
agent sees it as an agent-call tool, not a built-in grounding declaration — so the
Gemini API receives only function calls and no conflicting built-in tool config.

```python
from google.adk.tools.google_search_tool import GoogleSearchTool

# Safe to combine with MCP or FunctionTools:
google_search = GoogleSearchTool(bypass_multi_tools_limit=True)
```

### Recommendation for `build_agent`

When `"google_search"` appears in `tool_names`, instantiate
`GoogleSearchTool(bypass_multi_tools_limit=True)` and append it to `adk_tools`.
Do **not** use the module-level singleton (`from google.adk.tools import google_search`)
because it has `bypass_multi_tools_limit=False` by default.

The alternative — wrapping `google_search` as an MCP tool — is deferred to the backlog.
It would avoid the sub-agent overhead but requires a new MCP server and is not needed
for the MVP.
