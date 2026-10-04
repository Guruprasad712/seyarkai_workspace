"""Unit tests for app.runtime.normalise.

Uses duck-typed SimpleNamespace mocks — no ADK or network required.
"""
from types import SimpleNamespace

import pytest

from app.runtime.normalise import normalise


# ---------------------------------------------------------------------------
# Helpers to build mock ADK event shapes
# ---------------------------------------------------------------------------

def _make_part(
    text=None,
    function_call=None,
    function_response=None,
    thought=None,
):
    return SimpleNamespace(
        text=text,
        function_call=function_call,
        function_response=function_response,
        thought=thought,
    )


def _make_fn_call(name, args):
    return SimpleNamespace(name=name, args=args)


def _make_fn_resp(name, response):
    return SimpleNamespace(name=name, response=response)


def _make_event(parts, is_final=True, partial=None, usage_metadata=None):
    content = SimpleNamespace(parts=parts)
    ev = SimpleNamespace(
        content=content,
        partial=partial,
        usage_metadata=usage_metadata,
    )
    ev.is_final_response = lambda: is_final
    return ev


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_spike1_simple_text():
    """spike1 sample: final text, partial=None → one agent.message with text + preview."""
    ev = _make_event(
        parts=[_make_part(text="Hello there!")],
        is_final=True,
        partial=None,
    )
    result = normalise(ev)
    assert len(result) == 1
    assert result[0]["event_type"] == "agent.message"
    assert result[0]["payload"]["text"] == "Hello there!"
    assert result[0]["payload"]["preview"] == "Hello there!"


def test_spike2_function_call():
    """spike2: function_call part → tool.called with tool_name and arguments."""
    ev = _make_event(
        parts=[_make_part(function_call=_make_fn_call("echo", {"message": "hello world"}))],
        is_final=False,
    )
    result = normalise(ev)
    assert len(result) == 1
    assert result[0]["event_type"] == "tool.called"
    assert result[0]["payload"]["tool_name"] == "echo"
    assert result[0]["payload"]["arguments"] == {"message": "hello world"}


def test_spike2_function_response_dict_return():
    """dict return → structuredContent is the dict itself (no 'result' wrapper)."""
    response = {
        "structuredContent": {"results": [{"title": "Doc A"}]},
        "content": [{"type": "text", "text": "{'results': [...]}"}],
        "isError": False,
    }
    ev = _make_event(
        parts=[_make_part(function_response=_make_fn_resp("knowledge_search", response))],
        is_final=False,
    )
    result = normalise(ev)
    assert len(result) == 1
    assert result[0]["event_type"] == "tool.result"
    # structuredContent = the dict directly; summary is str(dict)[:500]
    assert "Doc A" in result[0]["payload"]["summary"]


def test_spike2_function_response_string_wrap_result():
    """Non-dict return with wrap_result=True → structuredContent.result unwrapped."""
    response = {
        "structuredContent": {"result": "ECHO: hello world"},
        "content": [{"type": "text", "text": "ECHO: hello world"}],
        "meta": {"fastmcp": {"wrap_result": True}},
        "isError": False,
    }
    ev = _make_event(
        parts=[_make_part(function_response=_make_fn_resp("echo", response))],
        is_final=False,
    )
    result = normalise(ev)
    assert len(result) == 1
    assert result[0]["event_type"] == "tool.result"
    assert result[0]["payload"]["summary"] == "ECHO: hello world"


def test_function_response_no_structured_content_fallback():
    """No structuredContent → content[0].text fallback."""
    response = {
        "content": [{"type": "text", "text": "plain text result"}],
        "isError": False,
    }
    ev = _make_event(
        parts=[_make_part(function_response=_make_fn_resp("my_tool", response))],
        is_final=False,
    )
    result = normalise(ev)
    assert len(result) == 1
    assert result[0]["event_type"] == "tool.result"
    assert result[0]["payload"]["summary"] == "plain text result"


def test_thought_only_event():
    """Event with only thought parts → empty list (nothing emitted)."""
    ev = _make_event(
        parts=[_make_part(thought=True, text="some internal reasoning")],
        is_final=True,
    )
    result = normalise(ev)
    assert result == []


def test_mixed_thought_and_text():
    """Thought part is stripped; surviving text yields agent.message."""
    ev = _make_event(
        parts=[
            _make_part(thought=True, text="internal thought"),
            _make_part(text="visible answer"),
        ],
        is_final=True,
    )
    result = normalise(ev)
    assert len(result) == 1
    assert result[0]["event_type"] == "agent.message"
    assert result[0]["payload"]["text"] == "visible answer"


def test_partial_event_returns_empty():
    """Streaming fragment (partial=True) → empty list."""
    ev = _make_event(
        parts=[_make_part(text="partial chunk")],
        is_final=False,
        partial=True,
    )
    result = normalise(ev)
    assert result == []


def test_function_call_and_final_text_same_event():
    """One event with both function_call + final text → two dicts."""
    ev = _make_event(
        parts=[
            _make_part(function_call=_make_fn_call("tool_x", {"k": "v"})),
            _make_part(text="here is my answer"),
        ],
        is_final=True,
    )
    result = normalise(ev)
    assert len(result) == 2
    assert result[0]["event_type"] == "tool.called"
    assert result[1]["event_type"] == "agent.message"


def test_no_token_counts_in_normalise_output():
    """normalise() never puts _token_counts on individual dicts."""
    ev = _make_event(
        parts=[_make_part(text="hi")],
        is_final=True,
        usage_metadata=SimpleNamespace(
            prompt_token_count=10,
            candidates_token_count=3,
            thoughts_token_count=5,
            total_token_count=18,
        ),
    )
    result = normalise(ev)
    assert len(result) == 1
    assert "_token_counts" not in result[0]
    assert "_token_counts" not in result[0].get("payload", {})


def test_preview_truncated_to_200():
    """preview is first 200 chars of text; text is full."""
    long_text = "x" * 300
    ev = _make_event(parts=[_make_part(text=long_text)], is_final=True)
    result = normalise(ev)
    assert result[0]["payload"]["text"] == long_text
    assert result[0]["payload"]["preview"] == "x" * 200


def test_non_final_text_skipped():
    """Text on a non-final event is not emitted."""
    ev = _make_event(
        parts=[_make_part(text="streaming fragment")],
        is_final=False,
        partial=None,
    )
    result = normalise(ev)
    assert result == []


# ---------------------------------------------------------------------------
# spike4: google_search sub-agent (GoogleSearchAgentTool) shapes
# Confirmed live 2026-10-04: function_call.name='google_search_agent',
# function_response.response={'result': '<answer>'}
#
# NOTE: google_search is deferred from the MVP catalog (see docs/ADK_NOTES.md).
# These tests exercise the generic ADK agent-call branch in _unwrap_function_response,
# which also covers any future sub-agent tool. They are kept because they pass and
# document the confirmed event shapes.
# ---------------------------------------------------------------------------

def test_google_search_agent_tool_called():
    """function_call from google_search sub-agent wrapping → tool.called."""
    ev = _make_event(
        parts=[_make_part(function_call=_make_fn_call("google_search_agent", {"request": "today's date"}))],
        is_final=False,
    )
    result = normalise(ev)
    assert result == [
        {
            "event_type": "tool.called",
            "payload": {
                "tool_name": "google_search_agent",
                "arguments": {"request": "today's date"},
            },
        }
    ]


def test_google_search_agent_tool_result():
    """function_response from google_search sub-agent → tool.result with answer text.

    ADK agent-call shape: {'result': '<str>'} — no structuredContent, no meta, no content.
    _unwrap_function_response must return the result value directly.
    """
    response_payload = {"result": "Today's date is Friday, October 2, 2026."}
    ev = _make_event(
        parts=[_make_part(function_response=_make_fn_resp("google_search_agent", response_payload))],
        is_final=False,
    )
    result = normalise(ev)
    assert result == [
        {
            "event_type": "tool.result",
            "payload": {
                "tool_name": "google_search_agent",
                "summary": "Today's date is Friday, October 2, 2026.",
            },
        }
    ]


def test_agent_call_result_not_confused_with_fastmcp_wrap():
    """{'result': ...} with no 'content'/'meta' keys → ADK agent-call path, not FastMCP wrap."""
    # FastMCP wrap shape has meta.fastmcp.wrap_result=True AND structuredContent
    # This response has only 'result' — must use the ADK agent-call branch.
    response_payload = {"result": "some answer"}
    ev = _make_event(
        parts=[_make_part(function_response=_make_fn_resp("some_agent", response_payload))],
        is_final=False,
    )
    result = normalise(ev)
    assert result[0]["payload"]["summary"] == "some answer"
