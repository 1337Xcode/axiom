"""Property test: session_id() always returns context.session.id unchanged.

**Validates: Requirements 2.3, 2.5**

Property 1: contextId Identity
For any ADK context with session.id, session_id() returns that exact string
unchanged — no UUID generation, no modification, no substitution.
"""

import sys
import os
import types as builtin_types
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# Add personal_agent to path for import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "personal_agent"))


def _import_session_id():
    """Import session_id while mocking unavailable third-party modules."""
    # Create mock modules for third-party deps not installed in test env
    mock_modules = {}
    for mod_name in [
        "httpx",
        "google",
        "google.adk",
        "google.adk.agents",
        "google.adk.agents.readonly_context",
        "google.adk.tools",
        "google.adk.tools.base_toolset",
        "google.genai",
        "google.genai.types",
    ]:
        mock_mod = builtin_types.ModuleType(mod_name)
        mock_modules[mod_name] = mock_mod

    # Set up nested module attributes
    mock_modules["google"].__path__ = []
    mock_modules["google.adk"].__path__ = []
    mock_modules["google.adk.agents"].__path__ = []
    mock_modules["google.adk.tools"].__path__ = []
    mock_modules["google.genai"].__path__ = []

    # Add the classes/objects that env_toolset imports
    mock_modules["google.adk.agents.readonly_context"].ReadonlyContext = MagicMock
    mock_modules["google.adk.tools"].BaseTool = MagicMock
    mock_modules["google.adk.tools"].FunctionTool = MagicMock
    mock_modules["google.adk.tools"].ToolContext = MagicMock
    mock_modules["google.adk.tools.base_toolset"].BaseToolset = MagicMock
    mock_modules["google.genai.types"] = MagicMock()

    with patch.dict(sys.modules, mock_modules):
        with patch.dict(
            os.environ, {"ENV_API_URL": "http://test:8090", "ENV_API_TOKEN": "tok"}
        ):
            # Remove cached module to force re-import with mocks
            sys.modules.pop("env_toolset", None)
            from env_toolset import session_id

    return session_id


# Import session_id once at module level with mocked deps
session_id = _import_session_id()


@given(session_value=st.text(min_size=1, max_size=200))
@settings(max_examples=200)
def test_session_id_returns_exact_session_id(session_value: str):
    """session_id(context) always returns context.session.id unchanged.

    **Validates: Requirements 2.3, 2.5**
    """
    # Mock the ADK context with session.id set to arbitrary string
    context = MagicMock()
    context.session.id = session_value

    result = session_id(context)

    assert result == session_value
    assert result is context.session.id


@given(
    session_value=st.from_regex(
        r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
        fullmatch=True,
    )
)
@settings(max_examples=100)
def test_session_id_preserves_uuid_format(session_value: str):
    """session_id returns UUID strings exactly as provided (no generation).

    **Validates: Requirements 2.3, 2.5**
    """
    context = MagicMock()
    context.session.id = session_value

    result = session_id(context)

    assert result == session_value
