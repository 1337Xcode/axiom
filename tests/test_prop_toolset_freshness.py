"""Property test: EnvApiToolset.get_tools() makes a fresh HTTP GET on every call.

**Validates: Requirement 3.3**
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# Mock third-party modules before importing env_toolset (not installed locally)
_mock_httpx = MagicMock()
_mock_httpx.AsyncClient = MagicMock

_mock_modules = {
    "httpx": _mock_httpx,
    "google": MagicMock(),
    "google.adk": MagicMock(),
    "google.adk.agents": MagicMock(),
    "google.adk.agents.readonly_context": MagicMock(),
    "google.adk.tools": MagicMock(),
    "google.adk.tools.base_toolset": MagicMock(),
    "google.genai": MagicMock(),
    "google.genai.types": MagicMock(),
}

# Make BaseToolset a real base class so EnvApiToolset can inherit
_mock_modules["google.adk.tools.base_toolset"].BaseToolset = type(
    "BaseToolset", (), {}
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "personal_agent"))

# Import env_toolset with mocked google modules
with patch.dict(sys.modules, _mock_modules):
    with patch.dict(
        os.environ, {"ENV_API_URL": "http://test:8090", "ENV_API_TOKEN": "tok"}
    ):
        if "env_toolset" in sys.modules:
            del sys.modules["env_toolset"]
        import env_toolset
        EnvApiToolset = env_toolset.EnvApiToolset


@pytest.mark.asyncio
@given(n_calls=st.integers(min_value=1, max_value=10))
@settings(max_examples=50)
async def test_get_tools_makes_fresh_http_get_each_call(n_calls: int) -> None:
    """Each get_tools() invocation triggers a new HTTP GET request.

    **Validates: Requirement 3.3**

    Property 11: For any sequence of get_tools() calls on an EnvApiToolset
    instance with a valid context, each call makes a fresh HTTP GET — no
    results are cached across invocations.
    """
    get_call_count = 0

    async def mock_get(url, headers=None):
        nonlocal get_call_count
        get_call_count += 1
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"tools": []}
        resp.raise_for_status = MagicMock()
        return resp

    mock_client = AsyncMock()
    mock_client.get = mock_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    # Create a mock readonly_context with a session.id
    mock_context = MagicMock()
    mock_context.session.id = "session-freshness-test"

    toolset = EnvApiToolset()

    with patch.object(env_toolset.httpx, "AsyncClient", return_value=mock_client):
        for _ in range(n_calls):
            await toolset.get_tools(readonly_context=mock_context)

    # The number of HTTP GET calls must equal the number of get_tools() calls
    assert get_call_count == n_calls, (
        f"Expected {n_calls} HTTP GET calls but got {get_call_count}. "
        f"get_tools() must not cache results between invocations."
    )
