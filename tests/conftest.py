"""Shared pytest fixtures for AXIOM integration tests."""

import os
import sys
import types as builtin_types
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

# --- Path setup ---
# Add both agent directories to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "personal_agent"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cs_agent"))


# --- Module-level mock setup for third-party deps not installed locally ---
_MOCK_MODULES: dict[str, builtin_types.ModuleType] = {}

_MOCKED_MODULE_NAMES = [
    "httpx",
    "redis",
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
]

for _mod_name in _MOCKED_MODULE_NAMES:
    _mod = builtin_types.ModuleType(_mod_name)
    _MOCK_MODULES[_mod_name] = _mod

_MOCK_MODULES["google"].__path__ = []
_MOCK_MODULES["google.adk"].__path__ = []
_MOCK_MODULES["google.adk.agents"].__path__ = []
_MOCK_MODULES["google.adk.tools"].__path__ = []
_MOCK_MODULES["google.genai"].__path__ = []
_MOCK_MODULES["a2a"].__path__ = []

_MOCK_MODULES["google.adk.agents.readonly_context"].ReadonlyContext = MagicMock
_MOCK_MODULES["google.adk.tools"].BaseTool = MagicMock
_MOCK_MODULES["google.adk.tools"].FunctionTool = MagicMock
_MOCK_MODULES["google.adk.tools"].ToolContext = MagicMock
_MOCK_MODULES["google.adk.tools.base_toolset"].BaseToolset = MagicMock
_MOCK_MODULES["google.genai.types"] = MagicMock()
_MOCK_MODULES["redis"].Redis = MagicMock()

# httpx needs realistic attributes for tests that import production code
_MOCK_MODULES["httpx"].AsyncClient = MagicMock
_MOCK_MODULES["httpx"].TimeoutException = type("TimeoutException", (Exception,), {})
_MOCK_MODULES["httpx"].HTTPStatusError = type("HTTPStatusError", (Exception,), {})


# ---------------------------------------------------------------------------
# Environment variable fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def env_vars():
    """Set required environment variables for all tests (autouse).

    Provides: ENV_API_URL, ENV_API_TOKEN, CS_AGENT_URL, REDIS_URL, MODEL.
    """
    env = {
        "ENV_API_URL": "http://test:8090",
        "ENV_API_TOKEN": "test-token",
        "CS_AGENT_URL": "http://test-cs:9002",
        "REDIS_URL": "redis://localhost:6379/0",
        "MODEL": "gemini-3.5-flash",
    }
    with patch.dict(os.environ, env):
        yield env


# ---------------------------------------------------------------------------
# Module mock fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_modules():
    """Patch sys.modules with mocked third-party deps."""
    with patch.dict(sys.modules, _MOCK_MODULES):
        yield _MOCK_MODULES


# ---------------------------------------------------------------------------
# ADK ToolContext fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_tool_context():
    """Mock ADK ToolContext with a fixed session.id."""
    ctx = MagicMock()
    ctx.session.id = "test-session-abc123"
    return ctx


@pytest.fixture
def mock_tool_context_factory():
    """Factory fixture to create mock contexts with custom session IDs."""

    def _make(session_id: str = "test-session-abc123") -> MagicMock:
        ctx = MagicMock()
        ctx.session.id = session_id
        return ctx

    return _make


# ---------------------------------------------------------------------------
# Redis fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for Plane B (session memory) testing."""
    client = MagicMock()
    client.hset = MagicMock()
    client.hgetall = MagicMock(return_value={})
    client.expire = MagicMock()
    return client


# ---------------------------------------------------------------------------
# httpx response fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_httpx_response():
    """Factory for mock httpx responses with configurable status and body."""

    def _make(
        status_code: int = 200,
        json_data: dict | None = None,
        text: str = "",
    ) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = json_data or {}
        resp.text = text
        resp.raise_for_status = MagicMock()
        if status_code >= 400:
            resp.raise_for_status.side_effect = Exception(
                f"HTTP {status_code}"
            )
        return resp

    return _make


@pytest.fixture
def mock_httpx_success():
    """Mock httpx response for successful tool calls (200 OK)."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"content": "success", "error": False}
    resp.text = '{"content": "success", "error": false}'
    resp.raise_for_status = MagicMock()
    return resp


@pytest.fixture
def mock_httpx_error():
    """Mock httpx response for failed tool calls (422 Validation Error)."""
    resp = MagicMock()
    resp.status_code = 422
    resp.json.return_value = {"content": "Validation error", "error": True}
    resp.text = "Validation error"
    resp.raise_for_status = MagicMock(
        side_effect=Exception("HTTP 422: Validation error")
    )
    return resp


# ---------------------------------------------------------------------------
# Async httpx client fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_async_httpx_client():
    """Mock async httpx.AsyncClient for testing tool calls and A2A messages."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client
