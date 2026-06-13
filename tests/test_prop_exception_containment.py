"""Property test: tool execution exceptions are contained as error dicts.

**Validates: Requirements 3.9, 9.8**
"""

import os
import sys
import types as builtin_types
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "personal_agent"))

# Mock modules
_mock_modules = {}
for mod_name in ["httpx", "google", "google.adk", "google.adk.agents",
                 "google.adk.agents.readonly_context", "google.adk.tools",
                 "google.adk.tools.base_toolset", "google.genai", "google.genai.types"]:
    _mock_modules[mod_name] = builtin_types.ModuleType(mod_name)
_mock_modules["google"].__path__ = []
_mock_modules["google.adk"].__path__ = []
_mock_modules["google.adk.agents"].__path__ = []
_mock_modules["google.adk.tools"].__path__ = []
_mock_modules["google.genai"].__path__ = []
_mock_modules["google.adk.agents.readonly_context"].ReadonlyContext = MagicMock
_mock_modules["google.adk.tools"].BaseTool = MagicMock
_mock_modules["google.adk.tools"].FunctionTool = MagicMock
_mock_modules["google.adk.tools"].ToolContext = MagicMock
_mock_modules["google.adk.tools.base_toolset"].BaseToolset = MagicMock
_mock_modules["google.genai.types"] = MagicMock()

for k, v in _mock_modules.items():
    sys.modules.setdefault(k, v)

# Ensure the mock httpx module has AsyncClient as a MagicMock
_mock_modules["httpx"].AsyncClient = MagicMock

os.environ.setdefault("ENV_API_URL", "http://test:8090")
os.environ.setdefault("ENV_API_TOKEN", "tok")

sys.modules.pop("env_toolset", None)
import env_toolset
_post_tool_call = env_toolset._post_tool_call
call_env_tool = env_toolset.call_env_tool

# Strategies
http_error_codes = st.sampled_from([400, 401, 403, 404, 422, 500, 502, 503])
invalid_json_strings = st.one_of(
    st.just("{invalid"),
    st.just("not json at all"),
    st.just("[unclosed"),
    st.just("{'single': 'quotes'}"),
    st.just("{missing: quotes}"),
    st.just('{"key": undefined}'),
    st.just("{trailing,}"),
)


def _is_invalid_json(s: str) -> bool:
    """Return True if s cannot be parsed by json.loads."""
    import json as _json
    try:
        _json.loads(s)
        return False
    except (ValueError, _json.JSONDecodeError):
        return True


@pytest.mark.asyncio
@given(status_code=http_error_codes)
@settings(max_examples=50)
async def test_post_tool_call_returns_error_dict_on_non_200(status_code: int):
    """_post_tool_call returns error dict on non-200 status (never raises)."""
    async def mock_post(url, json=None, headers=None):
        resp = MagicMock()
        resp.status_code = status_code
        resp.text = f"Error {status_code}"
        return resp

    mock_client = AsyncMock()
    mock_client.post = mock_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch.object(env_toolset.httpx, "AsyncClient", return_value=mock_client):
        result = await _post_tool_call("test-sid", "some_tool", {"arg": "val"})

    assert isinstance(result, dict)
    assert result["error"] is True
    assert isinstance(result["content"], str)
    assert str(status_code) in result["content"]


@pytest.mark.asyncio
@given(bad_json=invalid_json_strings)
@settings(max_examples=50)
async def test_call_env_tool_returns_error_on_invalid_json(bad_json: str):
    """call_env_tool returns error dict for invalid JSON (never raises)."""
    mock_ctx = MagicMock()
    mock_ctx.session.id = "test-session"

    result = await call_env_tool("some_tool", bad_json, mock_ctx)

    assert isinstance(result, dict)
    assert result["error"] is True
    assert "Invalid arguments JSON" in result["content"]


@pytest.mark.asyncio
async def test_call_env_tool_handles_empty_json():
    """call_env_tool handles empty string as empty dict."""
    async def mock_post(url, json=None, headers=None):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"content": "ok", "error": False}
        return resp

    mock_client = AsyncMock()
    mock_client.post = mock_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    mock_ctx = MagicMock()
    mock_ctx.session.id = "test-session"

    with patch.object(env_toolset.httpx, "AsyncClient", return_value=mock_client):
        result = await call_env_tool("some_tool", "", mock_ctx)

    assert isinstance(result, dict)
    assert result.get("error") is False
