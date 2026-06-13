"""Property test: session memory is best-effort (never raises).

**Validates: Requirements 6.4, 6.5, 6.7**

Property 5: Session Memory Best-Effort
For any Redis failure, the agent catches the exception and continues without
raising — returns a string instead of propagating the error.
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

# ---------------------------------------------------------------------------
# Mock third-party modules that are not installed in the test environment.
# These must stay in sys.modules for the duration of the test so that patch()
# can resolve "redis_memory._get_client" without re-importing the real redis.
# ---------------------------------------------------------------------------
_mock_modules = {}
for _mod_name in [
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
    _mock_modules[_mod_name] = builtin_types.ModuleType(_mod_name)

# Set up nested module __path__ attributes
_mock_modules["google"].__path__ = []
_mock_modules["google.adk"].__path__ = []
_mock_modules["google.adk.agents"].__path__ = []
_mock_modules["google.adk.tools"].__path__ = []
_mock_modules["google.genai"].__path__ = []

# Add the classes/objects that env_toolset and redis_memory import
_mock_modules["google.adk.agents.readonly_context"].ReadonlyContext = MagicMock
_mock_modules["google.adk.tools"].BaseTool = MagicMock
_mock_modules["google.adk.tools"].FunctionTool = MagicMock
_mock_modules["google.adk.tools"].ToolContext = MagicMock
_mock_modules["google.adk.tools.base_toolset"].BaseToolset = MagicMock
_mock_modules["google.genai.types"] = MagicMock()

# Mock Redis module
_mock_modules["redis"].Redis = MagicMock

# Patch sys.modules permanently for this test module
for _k, _v in _mock_modules.items():
    sys.modules.setdefault(_k, _v)

# Set required env vars and import write_session_memory
os.environ.setdefault("ENV_API_URL", "http://test:8090")
os.environ.setdefault("ENV_API_TOKEN", "tok")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

# Force fresh import
sys.modules.pop("env_toolset", None)
sys.modules.pop("redis_memory", None)

from redis_memory import write_session_memory  # noqa: E402

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Various exception types that Redis might throw
exception_types = st.sampled_from([
    ConnectionError("Connection refused"),
    TimeoutError("Operation timed out"),
    OSError("Network unreachable"),
    RuntimeError("Unexpected Redis error"),
    IOError("I/O error"),
])

session_ids = st.from_regex(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
    fullmatch=True,
)


@pytest.mark.asyncio
@given(ctx_id=session_ids, exc=exception_types)
@settings(max_examples=50)
async def test_write_memory_never_raises_on_redis_failure(ctx_id: str, exc: Exception):
    """write_session_memory catches all Redis exceptions and returns gracefully.

    **Validates: Requirements 6.4, 6.5, 6.7**
    """
    mock_redis_client = MagicMock()
    mock_redis_client.hset.side_effect = exc

    mock_tool_context = MagicMock()
    mock_tool_context.session.id = ctx_id

    with patch("redis_memory._get_client", return_value=mock_redis_client):
        # This should NOT raise — best-effort behavior
        result = await write_session_memory(mock_tool_context, dob="1990-01-15")

    # Should return a string (error message), not raise
    assert isinstance(result, str)
    assert "failed" in result.lower() or "not available" in result.lower()


@pytest.mark.asyncio
@given(ctx_id=session_ids, exc=exception_types)
@settings(max_examples=50)
async def test_write_memory_logs_warning_on_failure(ctx_id: str, exc: Exception):
    """write_session_memory logs a warning when Redis raises.

    **Validates: Requirements 6.4, 6.5, 6.7**
    """
    mock_redis_client = MagicMock()
    mock_redis_client.hset.side_effect = exc

    mock_tool_context = MagicMock()
    mock_tool_context.session.id = ctx_id

    with patch("redis_memory._get_client", return_value=mock_redis_client):
        with patch("redis_memory.logger") as mock_logger:
            result = await write_session_memory(mock_tool_context, email="a@b.com")

    # Should have logged a warning
    mock_logger.warning.assert_called_once()
    # And still return a string
    assert isinstance(result, str)


@pytest.mark.asyncio
@given(ctx_id=session_ids)
@settings(max_examples=30)
async def test_write_memory_no_redis_url_returns_gracefully(ctx_id: str):
    """When REDIS_URL is empty, write_session_memory returns without error.

    **Validates: Requirements 6.4, 6.5, 6.7**
    """
    mock_tool_context = MagicMock()
    mock_tool_context.session.id = ctx_id

    with patch("redis_memory._get_client", return_value=None):
        # Should NOT raise when Redis is not configured
        result = await write_session_memory(mock_tool_context, phone="+1234567890")

    assert isinstance(result, str)
    assert "not available" in result.lower() or "no redis" in result.lower()
