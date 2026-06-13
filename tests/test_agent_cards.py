"""Tests for agent card configuration (agents are correctly configured for A2A serving).

**Validates: Requirements 1.3, 1.4**

Since the agents use `to_a2a()` from google-adk which generates agent cards automatically,
we validate the agent configuration properties that feed into card generation:
- Correct agent name (appears in the served agent card)
- Non-empty tools list (maps to capabilities in the card)
- No output_schema (ADK Trap 1: would strip tools from the card)
"""

import os
import sys
import types as builtin_types
from unittest.mock import MagicMock, patch
from pathlib import Path

import pytest

# Add both agent directories to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "personal_agent"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cs_agent"))


# ---------------------------------------------------------------------------
# Module-level mock setup (mirrors conftest pattern)
# ---------------------------------------------------------------------------

def _build_mock_modules() -> dict[str, builtin_types.ModuleType]:
    """Build mock modules for third-party deps not installed in the test env."""
    mocks: dict[str, builtin_types.ModuleType] = {}
    for mod_name in [
        "httpx",
        "redis",
        "google",
        "google.adk",
        "google.adk.agents",
        "google.adk.agents.readonly_context",
        "google.adk.tools",
        "google.adk.tools.base_toolset",
        "google.adk.a2a",
        "google.adk.a2a.utils",
        "google.adk.a2a.utils.agent_to_a2a",
        "google.genai",
        "google.genai.types",
        "a2a",
        "a2a.client",
        "a2a.types",
    ]:
        mocks[mod_name] = builtin_types.ModuleType(mod_name)

    # Set __path__ for packages
    mocks["google"].__path__ = []
    mocks["google.adk"].__path__ = []
    mocks["google.adk.agents"].__path__ = []
    mocks["google.adk.tools"].__path__ = []
    mocks["google.adk.a2a"].__path__ = []
    mocks["google.adk.a2a.utils"].__path__ = []
    mocks["google.genai"].__path__ = []
    mocks["a2a"].__path__ = []

    # Provide mock classes that the production code imports
    mocks["google.adk.agents.readonly_context"].ReadonlyContext = MagicMock
    mocks["google.adk.tools"].BaseTool = MagicMock
    mocks["google.adk.tools"].FunctionTool = MagicMock
    mocks["google.adk.tools"].ToolContext = MagicMock
    mocks["google.adk.tools.base_toolset"].BaseToolset = MagicMock
    mocks["google.genai.types"] = MagicMock()
    mocks["redis"].Redis = MagicMock()
    mocks["httpx"].AsyncClient = MagicMock
    mocks["httpx"].TimeoutException = type("TimeoutException", (Exception,), {})
    mocks["httpx"].HTTPStatusError = type("HTTPStatusError", (Exception,), {})

    # a2a.client mock — provide the names cs_client_tool.py imports
    mocks["a2a.client"].ClientConfig = MagicMock
    mocks["a2a.client"].ClientFactory = MagicMock
    mocks["a2a.client"].minimal_agent_card = MagicMock

    # a2a.types mock — provide the names cs_client_tool.py imports
    mocks["a2a.types"].Message = MagicMock
    mocks["a2a.types"].Part = MagicMock
    mocks["a2a.types"].Role = MagicMock
    mocks["a2a.types"].Task = MagicMock
    mocks["a2a.types"].TextPart = MagicMock

    # LlmAgent mock that captures constructor kwargs
    class _MockLlmAgent:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    mocks["google.adk.agents"].LlmAgent = _MockLlmAgent

    return mocks


# ---------------------------------------------------------------------------
# Import helpers
# ---------------------------------------------------------------------------

def _import_personal_agent():
    """Import personal_agent/agent.py with mocked deps, return root_agent."""
    mock_modules = _build_mock_modules()

    env = {
        "ENV_API_URL": "http://test:8090",
        "ENV_API_TOKEN": "test-token",
        "CS_AGENT_URL": "http://test-cs:9002",
        "REDIS_URL": "redis://localhost:6379/0",
        "MODEL": "gemini-3.5-flash",
    }

    pa_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "personal_agent")
    )
    cs_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "cs_agent")
    )

    with patch.dict(sys.modules, mock_modules):
        with patch.dict(os.environ, env):
            # Clear cached modules to force fresh import from correct directory
            for mod in ["env_toolset", "cs_client_tool", "redis_memory", "agent"]:
                sys.modules.pop(mod, None)

            # Temporarily adjust path: personal_agent first, remove cs_agent
            old_path = sys.path[:]
            sys.path = [pa_dir] + [
                p for p in sys.path
                if os.path.abspath(p) != cs_dir
            ]
            try:
                from agent import root_agent
            finally:
                sys.path = old_path
    return root_agent


def _import_cs_agent():
    """Import cs_agent/agent.py with mocked deps, return root_agent."""
    mock_modules = _build_mock_modules()

    # CS agent needs policy.md to exist — use a temp content
    policy_content = "# Rho-Bank Policy\nTest policy content."

    env = {
        "ENV_API_URL": "http://test:8090",
        "ENV_API_TOKEN": "test-agent-token",
        "REDIS_URL": "redis://localhost:6379/0",
        "MODEL": "gemini-2.5-flash",
        "KB_POLICY_PATH": "__test_policy_placeholder__",
    }

    cs_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "cs_agent")
    )
    pa_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "personal_agent")
    )

    with patch.dict(sys.modules, mock_modules):
        with patch.dict(os.environ, env):
            # Clear cached modules to force fresh import from correct directory
            for mod in [
                "env_toolset",
                "rag_tools",
                "redis_memory",
                "discoverable_tools",
                "agent",
                "cs_client_tool",
            ]:
                sys.modules.pop(mod, None)
            # Temporarily adjust path: cs_agent first, remove personal_agent
            old_path = sys.path[:]
            sys.path = [cs_dir] + [
                p for p in sys.path
                if os.path.abspath(p) != pa_dir
            ]
            try:
                # Mock Path.read_text so POLICY_PATH doesn't need a real file
                with patch.object(Path, "read_text", return_value=policy_content):
                    from agent import root_agent
            finally:
                sys.path = old_path
    return root_agent


# ---------------------------------------------------------------------------
# Tests: Personal Agent
# ---------------------------------------------------------------------------


class TestPersonalAgentCard:
    """Validate Personal Agent configuration for A2A agent card serving."""

    def test_personal_agent_has_correct_name(self):
        """Personal agent has name 'personal_agent' — used in the agent card.

        **Validates: Requirement 1.3**
        """
        agent = _import_personal_agent()
        assert agent.name == "personal_agent"

    def test_personal_agent_has_tools(self):
        """Personal agent has a non-empty tools list — maps to card capabilities.

        **Validates: Requirement 1.3**
        """
        agent = _import_personal_agent()
        assert hasattr(agent, "tools")
        assert agent.tools is not None
        assert len(agent.tools) > 0

    def test_personal_agent_no_output_schema(self):
        """Personal agent does not use output_schema (ADK Trap 1).

        output_schema causes tools to be stripped from the agent card and LLM
        invocation. This would break all tool-calling capabilities.

        **Validates: Requirement 1.7**
        """
        agent = _import_personal_agent()
        output_schema = getattr(agent, "output_schema", None)
        assert output_schema is None, (
            "Personal agent must NOT use output_schema — "
            "it causes tools to be stripped (ADK Trap 1)"
        )

    def test_personal_agent_has_instruction(self):
        """Personal agent has a non-empty instruction/system prompt.

        **Validates: Requirement 1.3**
        """
        agent = _import_personal_agent()
        assert hasattr(agent, "instruction")
        assert agent.instruction is not None
        assert len(agent.instruction) > 0


# ---------------------------------------------------------------------------
# Tests: CS Agent
# ---------------------------------------------------------------------------


class TestCSAgentCard:
    """Validate CS Agent configuration for A2A agent card serving."""

    def test_cs_agent_has_correct_name(self):
        """CS agent has name 'cs_agent' — used in the agent card.

        **Validates: Requirement 1.4**
        """
        agent = _import_cs_agent()
        assert agent.name == "cs_agent"

    def test_cs_agent_has_tools(self):
        """CS agent has a non-empty tools list — maps to card capabilities.

        **Validates: Requirement 1.4**
        """
        agent = _import_cs_agent()
        assert hasattr(agent, "tools")
        assert agent.tools is not None
        assert len(agent.tools) > 0

    def test_cs_agent_no_output_schema(self):
        """CS agent does not use output_schema (ADK Trap 1).

        output_schema causes tools to be stripped from the agent card and LLM
        invocation. This would break all tool-calling capabilities.

        **Validates: Requirement 1.7**
        """
        agent = _import_cs_agent()
        output_schema = getattr(agent, "output_schema", None)
        assert output_schema is None, (
            "CS agent must NOT use output_schema — "
            "it causes tools to be stripped (ADK Trap 1)"
        )

    def test_cs_agent_has_instruction(self):
        """CS agent has a non-empty instruction/system prompt.

        **Validates: Requirement 1.4**
        """
        agent = _import_cs_agent()
        assert hasattr(agent, "instruction")
        assert agent.instruction is not None
        assert len(agent.instruction) > 0

    def test_cs_agent_instruction_includes_policy(self):
        """CS agent instruction starts with policy.md content (prepended verbatim).

        **Validates: Requirement 1.4**
        """
        agent = _import_cs_agent()
        # The mock policy content we inject
        assert "Rho-Bank Policy" in agent.instruction
