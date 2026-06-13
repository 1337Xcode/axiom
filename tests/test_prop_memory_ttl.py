"""Property test: session memory TTL is always set to 3600s.

**Validates: Requirement 6.3**

Property 4: Session Memory TTL
For any write operation to session memory, the Redis key session:{contextId}:memory
SHALL have its TTL set (or refreshed) to 3600 seconds.
"""

import os
import sys
import types as builtin_types
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# Add personal_agent to path for import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "personal_agent"))


def _import_redis_memory_module():
    """Import redis_memory module while mocking unavailable third-party modules."""
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
        "redis",
    ]:
        mock_mod = builtin_types.ModuleType(mod_name)
        mock_modules[mod_name] = mock_mod

    # Set up nested module attributes
    mock_modules["google"].__path__ = []
    mock_modules["google.adk"].__path__ = []
    mock_modules["google.adk.agents"].__path__ = []
    mock_modules["google.adk.tools"].__path__ = []
    mock_modules["google.genai"].__path__ = []

    # Add the classes/objects that env_toolset and redis_memory import
    mock_modules["google.adk.agents.readonly_context"].ReadonlyContext = MagicMock
    mock_modules["google.adk.tools"].BaseTool = MagicMock
    mock_modules["google.adk.tools"].FunctionTool = MagicMock
    mock_modules["google.adk.tools"].ToolContext = MagicMock
    mock_modules["google.adk.tools.base_toolset"].BaseToolset = MagicMock
    mock_modules["google.genai.types"] = MagicMock()

    # redis module needs Redis class with from_url
    mock_redis_cls = MagicMock()
    mock_modules["redis"].Redis = mock_redis_cls

    with patch.dict(sys.modules, mock_modules):
        with patch.dict(os.environ, {
            "ENV_API_URL": "http://test:8090",
            "ENV_API_TOKEN": "tok",
            "REDIS_URL": "redis://localhost:6379/0",
        }):
            sys.modules.pop("env_toolset", None)
            sys.modules.pop("redis_memory", None)
            import redis_memory  # noqa: F811

    return redis_memory


# Import module once at module level and keep reference
_redis_memory_mod = _import_redis_memory_module()
write_session_memory = _redis_memory_mod.write_session_memory


# Strategy: valid UUID v4 session IDs
session_ids = st.from_regex(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
    fullmatch=True,
)

# Strategy: arbitrary field combinations from the supported set
field_values = st.dictionaries(
    st.sampled_from(["dob", "email", "phone", "address", "user_id", "user_intent"]),
    st.text(min_size=1, max_size=50),
    min_size=1,
    max_size=4,
)


@pytest.mark.asyncio
@given(ctx_id=session_ids, fields=field_values)
@settings(max_examples=100)
async def test_write_memory_sets_ttl_3600(ctx_id: str, fields: dict):
    """Every write_session_memory call sets TTL to exactly 3600 seconds.

    **Validates: Requirement 6.3**
    """
    mock_redis_client = MagicMock()
    mock_tool_context = MagicMock()
    mock_tool_context.session.id = ctx_id

    with patch.object(_redis_memory_mod, "_get_client", return_value=mock_redis_client):
        await write_session_memory(mock_tool_context, **fields)

    expected_key = f"session:{ctx_id}:memory"
    mock_redis_client.expire.assert_called_once_with(expected_key, 3600)
