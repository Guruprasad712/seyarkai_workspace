"""Tests for the LLM call cap in run_stage.

Offline: uses a fake BaseLlm that always returns a tool-call response,
so the runner keeps looping until the cap fires.
The before_model_callback is injected via agent_definition["_before_model_callback"].
"""
from __future__ import annotations

import contextlib
import os
from collections.abc import AsyncGenerator
from typing import Any

import pytest

from app.runtime.runner import StageError, run_stage


# ---------------------------------------------------------------------------
# Fake BaseLlm that always returns a function_call to the adder_tool
# ---------------------------------------------------------------------------

def _make_fake_llm():
    """Build a BaseLlm subclass that always asks to call 'adder_tool'."""
    from google.adk.models.base_llm import BaseLlm
    from google.adk.models.llm_response import LlmResponse
    from google.genai import types

    class AlwaysCallTool(BaseLlm):
        model: str = "fake-always-call"

        @classmethod
        def supported_models(cls):
            return [r"fake-always-call"]

        async def generate_content_async(
            self, llm_request, stream=False
        ) -> AsyncGenerator[LlmResponse, None]:
            # Always ask to call adder_tool — keeps the loop going
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                name="adder_tool",
                                args={"x": 1, "y": 2},
                            )
                        )
                    ],
                ),
                partial=None,
            )

    return AlwaysCallTool()


def _make_adder_tool():
    """A simple FunctionTool that the fake LLM can call."""
    from google.adk.tools.function_tool import FunctionTool

    def adder_tool(x: int, y: int) -> int:
        """Add two numbers."""
        return x + y

    return FunctionTool(func=adder_tool)


_AGENT_DEF_BASE = {
    "name": "cap_test_agent",
    "instructions": "Test agent.",
}


async def test_cap_off_by_one():
    """before_model_callback fires on the exceeding call (3rd when cap=2).

    Confirms the off-by-one: callback fires on attempt #3 even though the
    cap is 2, because ADK checks the limit on the call that would exceed it.
    run_stage must re-raise as StageError with "cap exceeded".
    """
    callback_calls: list[int] = []

    def counting_cb(ctx, req):
        callback_calls.append(len(callback_calls) + 1)
        return None  # let the call proceed (ADK will raise the limit error)

    fake_llm = _make_fake_llm()
    adder = _make_adder_tool()

    agent_def = {
        **_AGENT_DEF_BASE,
        "_model": fake_llm,
        "_before_model_callback": counting_cb,
    }

    with pytest.raises(StageError) as exc_info:
        async with contextlib.aclosing(
            run_stage(
                agent_def,
                task_text="Add 1 + 2 repeatedly.",
                tool_names=[],
                max_llm_calls=2,
                _extra_tools=[adder],
            )
        ) as gen:
            async for _ in gen:
                pass

    # The callback must have fired 3 times:
    # attempts 1 and 2 succeed; attempt 3 triggers the cap error
    assert len(callback_calls) == 3, (
        f"Expected 3 callback calls (including the exceeding one), got {len(callback_calls)}"
    )
    assert "cap exceeded" in str(exc_info.value).lower(), str(exc_info.value)


@pytest.mark.live
def test_vertex_mode_active():
    """Fail fast if the Vertex environment is not configured for live tests."""
    assert os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("true", "1"), (
        "GOOGLE_GENAI_USE_VERTEXAI must be 'true' for live tests"
    )
    assert os.environ.get("GOOGLE_CLOUD_PROJECT"), "GOOGLE_CLOUD_PROJECT must be set"
    assert os.environ.get("GOOGLE_CLOUD_LOCATION"), "GOOGLE_CLOUD_LOCATION must be set"


@pytest.mark.live
async def test_run_stage_live():
    """Real Vertex AI call: assert at least one agent.message is emitted."""
    agent_def = {
        "name": "live_test_agent",
        "instructions": "You are a concise assistant.",
    }

    events: list[dict] = []
    async with contextlib.aclosing(
        run_stage(agent_def, "Say hello in one sentence.", tool_names=[])
    ) as gen:
        async for event in gen:
            events.append(event)

    assert any(e["event_type"] == "agent.message" for e in events), events
    stream_ends = [e for e in events if e["event_type"] == "stage.stream_end"]
    assert stream_ends, "No stage.stream_end event"
    assert stream_ends[-1]["payload"]["final_text"], "Empty final_text"
