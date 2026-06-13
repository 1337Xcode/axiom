"""Property test: ask_customer_service propagates contextId correctly.

**Validates: Requirements 2.1, 2.2, 2.4, 2.6**

Property 2: contextId Propagation
For any session initiated by the Harness with a given context_id, all outgoing
A2A messages from ask_customer_service() contain context_id equal to
session_id(tool_context).
"""

import os
import sys
import types as builtin_types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# Add personal_agent to path for import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "personal_agent"))


# Strategy: UUID v4-like session IDs (what the harness generates)
uuid_strategy = st.from_regex(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
    fullmatch=True,
)


def _build_mock_modules():
    """Build mock modules for third-party deps not installed in test env."""
    mock_modules = {}
    for mod_name in [
        "google",
        "google.adk",
        "google.adk.agents",
        "google.adk.agents.readonly_context",
        "google.adk.tools",
        "google.adk.tools.base_toolset",
        "google.genai",
        "google.genai.types",
        "a2a",
        "a2a.client",
        "a2a.types",
    ]:
        mock_mod = builtin_types.ModuleType(mod_name)
        mock_modules[mod_name] = mock_mod

    # Set up nested module attributes for google.*
    mock_modules["google"].__path__ = []
    mock_modules["google.adk"].__path__ = []
    mock_modules["google.adk.agents"].__path__ = []
    mock_modules["google.adk.tools"].__path__ = []
    mock_modules["google.genai"].__path__ = []
    mock_modules["a2a"].__path__ = []

    # Add the classes/objects that env_toolset imports
    mock_modules["google.adk.agents.readonly_context"].ReadonlyContext = MagicMock
    mock_modules["google.adk.tools"].BaseTool = MagicMock
    mock_modules["google.adk.tools"].FunctionTool = MagicMock
    mock_modules["google.adk.tools"].ToolContext = MagicMock
    mock_modules["google.adk.tools.base_toolset"].BaseToolset = MagicMock
    mock_modules["google.genai.types"] = MagicMock()

    # A2A SDK types — use real-ish classes that store context_id
    class FakeMessage:
        """Minimal Message stand-in that captures context_id."""

        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    class FakePart:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    class FakeTextPart:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    class FakeRole:
        user = "user"
        agent = "agent"

    class FakeTask:
        pass

    mock_modules["a2a.types"].Message = FakeMessage
    mock_modules["a2a.types"].Part = FakePart
    mock_modules["a2a.types"].TextPart = FakeTextPart
    mock_modules["a2a.types"].Role = FakeRole
    mock_modules["a2a.types"].Task = FakeTask

    # a2a.client mocks
    mock_modules["a2a.client"].ClientFactory = MagicMock
    mock_modules["a2a.client"].ClientConfig = MagicMock
    mock_modules["a2a.client"].minimal_agent_card = MagicMock

    return mock_modules, FakeMessage


_mock_modules, FakeMessage = _build_mock_modules()


@pytest.mark.asyncio
@given(ctx_id=uuid_strategy)
@settings(max_examples=100)
async def test_ask_cs_propagates_context_id(ctx_id: str):
    """ask_customer_service sets context_id == session_id(tool_context).

    **Validates: Requirements 2.1, 2.2, 2.4, 2.6**
    """
    captured_messages: list = []

    # Build an async generator that yields nothing (empty response path)
    async def fake_send_message(message):
        captured_messages.append(message)
        return
        yield  # makes this an async generator

    # Mock the A2A client returned by ClientFactory(...).create(...)
    mock_a2a_client = MagicMock()
    mock_a2a_client.send_message = fake_send_message

    mock_factory_instance = MagicMock()
    mock_factory_instance.create.return_value = mock_a2a_client

    mock_client_factory = MagicMock(return_value=mock_factory_instance)

    # Mock tool_context with session.id = ctx_id
    mock_tool_context = MagicMock()
    mock_tool_context.session.id = ctx_id

    with patch.dict(sys.modules, _mock_modules):
        with patch.dict(os.environ, {
            "ENV_API_URL": "http://test:8090",
            "ENV_API_TOKEN": "tok",
            "CS_AGENT_URL": "http://test-cs:9002",
        }):
            # Clear cached modules to force fresh import with mocks
            sys.modules.pop("env_toolset", None)
            sys.modules.pop("cs_client_tool", None)

            # Patch a2a.client.ClientFactory to our mock
            _mock_modules["a2a.client"].ClientFactory = mock_client_factory

            from cs_client_tool import ask_customer_service

            result = await ask_customer_service("test message", mock_tool_context)

    # The outgoing message must have been created with context_id == ctx_id
    assert len(captured_messages) == 1
    outgoing = captured_messages[0]
    assert outgoing.context_id == ctx_id


@pytest.mark.asyncio
@given(
    ctx_id=st.text(
        min_size=1,
        max_size=100,
        alphabet=st.characters(whitelist_categories=("L", "N", "P", "S")),
    )
)
@settings(max_examples=100)
async def test_ask_cs_propagates_arbitrary_context_id(ctx_id: str):
    """context_id propagation works for any non-empty string, not just UUIDs.

    **Validates: Requirements 2.1, 2.2, 2.4, 2.6**
    """
    captured_messages: list = []

    async def fake_send_message(message):
        captured_messages.append(message)
        return
        yield

    mock_a2a_client = MagicMock()
    mock_a2a_client.send_message = fake_send_message

    mock_factory_instance = MagicMock()
    mock_factory_instance.create.return_value = mock_a2a_client

    mock_client_factory = MagicMock(return_value=mock_factory_instance)

    mock_tool_context = MagicMock()
    mock_tool_context.session.id = ctx_id

    with patch.dict(sys.modules, _mock_modules):
        with patch.dict(os.environ, {
            "ENV_API_URL": "http://test:8090",
            "ENV_API_TOKEN": "tok",
            "CS_AGENT_URL": "http://test-cs:9002",
        }):
            sys.modules.pop("env_toolset", None)
            sys.modules.pop("cs_client_tool", None)

            _mock_modules["a2a.client"].ClientFactory = mock_client_factory

            from cs_client_tool import ask_customer_service

            result = await ask_customer_service("hello", mock_tool_context)

    assert len(captured_messages) == 1
    assert captured_messages[0].context_id == ctx_id
