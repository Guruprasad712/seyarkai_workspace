"""Live tests: GoogleSearchTool coexistence with MCP/function tools.

Results from these tests are recorded in docs/ADK_NOTES.md.

Run with:
    python -m pytest tests/test_google_search_coexist.py -m live -s -v
"""
from __future__ import annotations

import contextlib

import pytest

from app.runtime.runner import StageError, run_stage

_AGENT_DEF = {
    "name": "search_coexist_agent",
    "instructions": "You are a concise assistant. Answer briefly.",
}


def _make_adder_tool():
    from google.adk.tools.function_tool import FunctionTool

    def adder_tool(x: int, y: int) -> int:
        """Add two numbers."""
        return x + y

    return FunctionTool(func=adder_tool)


@pytest.mark.live
async def test_google_search_solo():
    """GoogleSearchTool alone (no other tools) — confirms it works on Vertex AI."""
    from google.adk.tools.google_search_tool import GoogleSearchTool

    events: list[dict] = []
    async with contextlib.aclosing(
        run_stage(
            _AGENT_DEF,
            "What is the capital of France? Use google search to find out.",
            tool_names=[],
            _extra_tools=[GoogleSearchTool()],
        )
    ) as gen:
        async for event in gen:
            events.append(event)

    assert any(e["event_type"] == "agent.message" for e in events), (
        f"No agent.message in events: {events}"
    )


@pytest.mark.live
async def test_google_search_with_function_tool_default():
    """GoogleSearchTool (bypass=False) + FunctionTool — expected to fail.

    The Gemini API rejects requests that combine built-in search grounding
    with function call declarations. The exact error is captured here and
    recorded in ADK_NOTES.md.
    """
    from google.adk.tools.google_search_tool import GoogleSearchTool

    adder = _make_adder_tool()

    with pytest.raises(StageError) as exc_info:
        async with contextlib.aclosing(
            run_stage(
                _AGENT_DEF,
                "Add 2 + 3 using adder_tool, then search the web for the result.",
                tool_names=[],
                _extra_tools=[GoogleSearchTool(), adder],
            )
        ) as gen:
            async for _ in gen:
                pass

    error_msg = str(exc_info.value)
    print(f"\n[RECORDED] bypass=False error: {error_msg}")
    # We expect a StageError — the exact message depends on what Gemini returns.
    assert error_msg, "StageError should have a message"


@pytest.mark.live
async def test_google_search_with_function_tool_bypass():
    """GoogleSearchTool(bypass_multi_tools_limit=True) + FunctionTool — expected to pass.

    With bypass=True, ADK wraps GoogleSearchTool in a sub-agent so the Gemini
    API sees it as an agent-call tool, not a built-in grounding tool. This
    sidesteps the coexistence restriction.
    """
    from google.adk.tools.google_search_tool import GoogleSearchTool

    adder = _make_adder_tool()

    events: list[dict] = []
    async with contextlib.aclosing(
        run_stage(
            _AGENT_DEF,
            "Say hello in one sentence.",
            tool_names=[],
            _extra_tools=[GoogleSearchTool(bypass_multi_tools_limit=True), adder],
        )
    ) as gen:
        async for event in gen:
            events.append(event)

    assert any(e["event_type"] == "agent.message" for e in events), (
        f"No agent.message in events: {events}"
    )
    print(f"\n[RECORDED] bypass=True success — events: {[e['event_type'] for e in events]}")


@pytest.mark.live
async def test_sub_agent_llm_call_budget():
    """Does the search sub-agent's LLM call count toward max_llm_calls?

    Set max_llm_calls=1. If sub-agent calls count, the stage hits the cap immediately.
    If they run independently, the stage should complete normally.
    Result is recorded in docs/ADK_NOTES.md.
    """
    from google.adk.tools.google_search_tool import GoogleSearchTool

    adder = _make_adder_tool()
    events: list[dict] = []
    error: StageError | None = None

    try:
        async with contextlib.aclosing(
            run_stage(
                {
                    "name": "budget_test_agent",
                    "instructions": "You are a concise assistant.",
                },
                "Please use google_search_agent to find today's date.",
                tool_names=[],
                max_llm_calls=1,
                _extra_tools=[
                    GoogleSearchTool(bypass_multi_tools_limit=True),
                    adder,
                ],
            )
        ) as gen:
            async for event in gen:
                events.append(event)
    except StageError as e:
        error = e

    if error:
        print(f"\n[RECORDED] Sub-agent calls DO count toward max_llm_calls: {error}")
    else:
        print(
            f"\n[RECORDED] Sub-agent calls do NOT count toward max_llm_calls "
            f"(stage completed). events: {[e['event_type'] for e in events]}"
        )
    # Either outcome is valid — the test records the result.
    assert error is not None or any(e["event_type"] == "agent.message" for e in events)
