"""Map raw ADK Event objects to contract event dicts (CONTRACTS.md D7).

Returns list[dict] — empty means nothing to emit; usually one item;
multiple when a single ADK event carries both a function_call and text.

Token counts are NOT placed on individual dicts here. run_stage accumulates
them from event.usage_metadata and emits them in the terminal stage.stream_end.
"""
from __future__ import annotations

import json
from typing import Any


def _unwrap_function_response(resp: Any) -> str:
    """Extract a summary string from a FastMCP / MCP function_response payload.

    FastMCP shapes (confirmed from source, fastmcp 4.0.10):
    - dict return  → structured_content = the dict itself (no wrap)
    - non-dict return with x-fastmcp-wrap-result → structured_content = {"result": value}
                                                     meta.fastmcp.wrap_result = True
    Fallback: content[0].text
    """
    if not isinstance(resp, dict):
        return str(resp)[:500]

    sc = resp.get("structuredContent")
    if sc is not None:
        meta = resp.get("meta") or {}
        wrap = (meta.get("fastmcp") or {}).get("wrap_result", False)
        raw = sc.get("result") if wrap else sc
        return str(raw)[:500]

    # No structuredContent — fall back to content[0].text
    content = resp.get("content") or []
    if content and isinstance(content[0], dict):
        return str(content[0].get("text", ""))[:500]
    return str(resp)[:500]


def normalise(event: Any) -> list[dict]:
    """Map one ADK Event to zero or more contract event dicts."""
    # Drop streaming fragments: partial is None on non-streaming events (not False)
    if event.partial:
        return []

    content = getattr(event, "content", None)
    if content is None:
        return []

    parts = getattr(content, "parts", None) or []

    # Filter out thought parts — never emit chain-of-thought
    surviving = [p for p in parts if not getattr(p, "thought", None)]

    if not surviving:
        return []

    results: list[dict] = []
    is_final = event.is_final_response()

    for part in surviving:
        fn_call = getattr(part, "function_call", None)
        fn_resp = getattr(part, "function_response", None)
        text = getattr(part, "text", None)

        if fn_call is not None:
            args = fn_call.args or {}
            args_str = json.dumps(args, default=str)
            if len(args_str) > 1000:
                args_str = args_str[:1000] + "…"
                args = {"_truncated": args_str}
            results.append({
                "event_type": "tool.called",
                "payload": {
                    "tool_name": fn_call.name,
                    "arguments": args,
                },
            })

        elif fn_resp is not None:
            summary = _unwrap_function_response(fn_resp.response)
            results.append({
                "event_type": "tool.result",
                "payload": {
                    "tool_name": fn_resp.name,
                    "summary": summary,
                },
            })

        elif text is not None and is_final:
            results.append({
                "event_type": "agent.message",
                "payload": {
                    "text": text,
                    "preview": text[:200],
                },
            })
        # Non-final text fragments: skip

    return results
