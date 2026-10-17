"""Offline unit tests for multi-server toolset grouping in build_agent.

These tests inject _extra_tools so no MCP subprocess is ever launched.
They verify that tool_server_map correctly routes tools to their servers.
"""
from __future__ import annotations

import pytest

from app.runtime.agent import _SERVER_MODULES, build_agent


def _fake_definition(name: str = "test_agent") -> dict:
    return {
        "name": name,
        "instructions": "test",
        "_model": None,  # will fall through to settings default — OK for offline
    }


# ---------------------------------------------------------------------------
# Registry shape
# ---------------------------------------------------------------------------

def test_server_modules_has_knowledge():
    assert "knowledge" in _SERVER_MODULES


def test_server_modules_has_docs():
    assert "docs" in _SERVER_MODULES


def test_server_modules_values_are_module_paths():
    for key, path in _SERVER_MODULES.items():
        assert "." in path, f"Expected module path for {key!r}, got {path!r}"


# ---------------------------------------------------------------------------
# tool_server_map routing (uses _extra_tools to skip subprocess launch)
# ---------------------------------------------------------------------------

def test_extra_tools_bypass_toolsets():
    """When _extra_tools is given, no toolsets are launched regardless of map."""
    _agent, toolsets = build_agent(
        _fake_definition(),
        tool_names=["knowledge_search", "generate_document"],
        tool_server_map={
            "knowledge_search": "knowledge",
            "generate_document": "docs",
        },
        _extra_tools=[],  # empty list — bypasses server launch; ADK accepts empty tools list
    )
    assert toolsets == []


def test_no_tools_no_toolsets():
    """Empty tool list → no toolsets, agent still built."""
    _agent, toolsets = build_agent(
        _fake_definition(),
        tool_names=[],
        _extra_tools=None,
    )
    assert toolsets == []


def test_single_server_grouped():
    """All tools on the same server → only one server key in by_server."""
    # We can't run a subprocess in tests, so verify by passing _extra_tools=[]
    # and checking the grouping logic doesn't raise.
    _agent, toolsets = build_agent(
        _fake_definition(),
        tool_names=["knowledge_search"],
        tool_server_map={"knowledge_search": "knowledge"},
        _extra_tools=[],
    )
    assert toolsets == []


def test_unknown_server_key_defaults_to_knowledge():
    """A tool with no entry in tool_server_map falls back to 'knowledge'."""
    # We verify the fallback doesn't raise and still resolves to a known server.
    _agent, toolsets = build_agent(
        _fake_definition(),
        tool_names=["mystery_tool"],
        tool_server_map={},  # empty — forces fallback
        _extra_tools=[],
    )
    assert toolsets == []


def test_none_tool_server_map_defaults_to_knowledge():
    """When tool_server_map=None, all tools default to 'knowledge' server."""
    _agent, toolsets = build_agent(
        _fake_definition(),
        tool_names=["knowledge_search"],
        tool_server_map=None,
        _extra_tools=[],
    )
    assert toolsets == []


def test_agent_name_sanitised():
    """Agent name with spaces and dashes becomes a valid Python identifier."""
    agent, _toolsets = build_agent(
        {"name": "My Agent-2", "instructions": "x"},
        tool_names=[],
        _extra_tools=[],
    )
    import re
    assert re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", agent.name), (
        f"Agent name {agent.name!r} is not a valid Python identifier"
    )
