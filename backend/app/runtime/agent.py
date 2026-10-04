"""Build an ADK LlmAgent for a single stage run.

No DB imports. No secrets in code. Model is read from settings.
Vertex env vars are pushed into os.environ before ADK touches them.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.tools import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from app.core.config import settings

_BACKEND_DIR = Path(__file__).resolve().parents[2]  # runtime/ → app/ → backend/

# Map server_key → module path launched as subprocess
_SERVER_MODULES: dict[str, str] = {
    "knowledge": "app.mcp_servers.knowledge",
}

_ENV_PUSHED = False


def _ensure_vertex_env() -> None:
    """Push Vertex AI vars from settings into os.environ (once).

    pydantic-settings reads .env into the Settings object but does NOT
    write to os.environ. ADK checks os.environ directly at client init time,
    so we must propagate them here before building any agent.
    """
    global _ENV_PUSHED
    if _ENV_PUSHED:
        return
    _ENV_PUSHED = True

    if settings.GOOGLE_GENAI_USE_VERTEXAI:
        os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
        if settings.GOOGLE_CLOUD_PROJECT:
            os.environ.setdefault("GOOGLE_CLOUD_PROJECT", settings.GOOGLE_CLOUD_PROJECT)
        if settings.GOOGLE_CLOUD_LOCATION:
            os.environ.setdefault("GOOGLE_CLOUD_LOCATION", settings.GOOGLE_CLOUD_LOCATION)
    # In API key mode (GOOGLE_GENAI_USE_VERTEXAI=false):
    # ADK checks GOOGLE_API_KEY; aliasing from GEMINI_API_KEY is the caller's
    # responsibility (entry-point pattern in ADK_NOTES.md). runtime/ never aliases.


def build_agent(
    agent_definition: dict[str, Any],
    tool_names: list[str],
    *,
    _extra_tools: list[Any] | None = None,
) -> tuple[LlmAgent, list[McpToolset]]:
    """Build an LlmAgent for the given agent definition and tool list.

    Args:
        agent_definition: Dict with keys: name, instructions, capabilities,
            and optionally _model (BaseLlm instance for tests) and
            _before_model_callback (callable for tests).
        tool_names: MCP tool names the agent is allowed to call.
        _extra_tools: Test seam. When provided, these raw ADK tools are passed
            directly and no McpToolset subprocess is launched.
    """
    _ensure_vertex_env()

    # Allow tests to inject a BaseLlm instance directly (bypasses registry)
    model: Any = agent_definition.get("_model") or settings.GEMINI_MODEL_FAST or "gemini-2.5-flash"
    # LlmAgent requires the name to be a valid Python identifier
    raw_name = agent_definition.get("name", "stage_agent")
    name = raw_name.replace("-", "_")
    instructions = agent_definition.get("instructions", "")

    toolsets: list[McpToolset] = []
    adk_tools: list[Any] = []

    if _extra_tools is not None:
        adk_tools = list(_extra_tools)
    elif tool_names:
        # Group by server_key and build one McpToolset per server
        by_server: dict[str, list[str]] = {}
        for tn in tool_names:
            # tool_name maps to server_key via mcp_tools.server_key in the DB;
            # here we use the catalog constant for the knowledge server.
            server_key = "knowledge"  # only server available now
            by_server.setdefault(server_key, []).append(tn)

        for server_key in by_server:
            module = _SERVER_MODULES.get(server_key)
            if not module:
                continue
            toolset = McpToolset(
                connection_params=StdioConnectionParams(
                    server_params=StdioServerParameters(
                        command=sys.executable,
                        args=["-m", module],
                        cwd=str(_BACKEND_DIR),
                        env={**os.environ},
                    ),
                    timeout=10.0,
                ),
            )
            toolsets.append(toolset)
            adk_tools.append(toolset)

    kwargs: dict[str, Any] = dict(
        model=model,
        name=name,
        instruction=instructions,
        tools=adk_tools,
    )
    # Test seam: inject a before_model_callback to count LLM call attempts
    cb = agent_definition.get("_before_model_callback")
    if cb is not None:
        kwargs["before_model_callback"] = cb

    agent = LlmAgent(**kwargs)

    return agent, toolsets
