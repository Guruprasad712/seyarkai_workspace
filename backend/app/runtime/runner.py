"""Run a single policy stage with an ADK LlmAgent.

No DB imports. Yields normalised event dicts. Emits a terminal
stage.stream_end dict with final_text and total token counts.
All failures are wrapped in StageError with sanitized messages.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from google.adk.agents import RunConfig
from google.adk.agents.invocation_context import LlmCallsLimitExceededError
from google.adk.runners import InMemoryRunner
from google.genai import types

from app.core.config import settings
from app.runtime.agent import build_agent
from app.runtime.normalise import normalise


class StageError(Exception):
    """Sanitized stage failure — safe to store in execution.error field."""
    pass


def run_stage(
    agent_definition: dict[str, Any],
    task_text: str,
    tool_names: list[str],
    max_llm_calls: int | None = None,
    timeout_seconds: float = 120.0,
    _extra_tools: list[Any] | None = None,
) -> AsyncGenerator[dict, None]:
    """Return an async generator that runs one stage and yields normalised dicts.

    Yields contract event dicts (tool.called, tool.result, agent.message)
    followed by a single engine-internal stage.stream_end dict.

    Raises:
        StageError: on any failure (cap exceeded, timeout, tool crash, etc.)
    """
    return _run_stage_gen(
        agent_definition=agent_definition,
        task_text=task_text,
        tool_names=tool_names,
        max_llm_calls=max_llm_calls,
        timeout_seconds=timeout_seconds,
        _extra_tools=_extra_tools,
    )


async def _run_stage_gen(
    agent_definition: dict[str, Any],
    task_text: str,
    tool_names: list[str],
    max_llm_calls: int | None,
    timeout_seconds: float,
    _extra_tools: list[Any] | None,
) -> AsyncGenerator[dict, None]:
    agent, toolsets = build_agent(
        agent_definition, tool_names, _extra_tools=_extra_tools
    )
    runner = InMemoryRunner(agent=agent, app_name="stage_runner")

    session = await runner.session_service.create_session(
        app_name=runner.app_name,
        user_id="engine",
    )

    _max_calls: int = (
        max_llm_calls if max_llm_calls is not None else settings.MAX_LLM_CALLS_PER_STAGE
    )
    run_config = RunConfig(max_llm_calls=_max_calls)

    total_tokens: dict[str, int] = {
        "prompt_token_count": 0,
        "candidates_token_count": 0,
        "thoughts_token_count": 0,
        "total_token_count": 0,
    }
    final_text: str | None = None

    try:
        async with asyncio.timeout(timeout_seconds):
            try:
                async for event in runner.run_async(
                    user_id="engine",
                    session_id=session.id,
                    new_message=types.Content(
                        role="user",
                        parts=[types.Part(text=task_text)],
                    ),
                    run_config=run_config,
                ):
                    # Accumulate token counts — never emitted per-event
                    um = getattr(event, "usage_metadata", None)
                    if um is not None:
                        total_tokens["prompt_token_count"] += getattr(um, "prompt_token_count", 0) or 0
                        total_tokens["candidates_token_count"] += getattr(um, "candidates_token_count", 0) or 0
                        total_tokens["thoughts_token_count"] += getattr(um, "thoughts_token_count", 0) or 0
                        total_tokens["total_token_count"] += getattr(um, "total_token_count", 0) or 0

                    for emitted in normalise(event):
                        if emitted["event_type"] == "agent.message":
                            final_text = emitted["payload"]["text"]
                        yield emitted

            except LlmCallsLimitExceededError:
                # ADK also prints its own traceback to stderr — expected noise
                raise StageError(f"LLM call cap exceeded ({_max_calls} calls)")

    except asyncio.TimeoutError:
        raise StageError(f"Stage timed out after {timeout_seconds}s")
    except StageError:
        raise
    except Exception as e:
        raise StageError(f"Stage failed: {type(e).__name__}") from None
    finally:
        for toolset in toolsets:
            try:
                await toolset.close()
            except Exception:
                pass

    if not final_text:
        raise StageError("Stage produced no final text")

    yield {
        "event_type": "stage.stream_end",
        "payload": {
            "final_text": final_text,
            "total_tokens": total_tokens,
        },
    }
