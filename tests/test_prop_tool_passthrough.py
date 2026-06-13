"""Property test: _post_tool_call passes arguments dict unchanged.

**Validates: Requirements 3.4**
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# Mock google.adk modules before importing env_toolset (not installed locally)
_mock_modules = {
    "google": MagicMock(),
    "google.adk": MagicMock(),
    "google.adk.agents": MagicMock(),
    "google.adk.agents.readonly_context": MagicMock(),
    "google.adk.tools": MagicMock(),
    "google.adk.tools.base_toolset": MagicMock(),
    "google.genai": MagicMock(),
    "google.genai.types": MagicMock(),
}

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "personal_agent"))

# Import env_toolset with mocked google modules
with patch.dict(sys.modules, _mock_modules):
    with patch.dict(os.environ, {"ENV_API_URL": "http://test:8090", "ENV_API_TOKEN": "tok"}):
        if "env_toolset" in sys.modules:
            del sys.modules["env_toolset"]
        import env_toolset
        _post_tool_call = env_toolset._post_tool_call

# Strategy for JSON-compatible argument dicts
json_values = st.recursive(
    st.one_of(
        st.text(max_size=50),
        st.integers(min_value=-1000000, max_value=1000000),
        st.floats(allow_nan=False, allow_infinity=False),
        st.booleans(),
        st.none(),
    ),
    lambda children: st.one_of(
        st.lists(children, max_size=5),
        st.dictionaries(st.text(min_size=1, max_size=20), children, max_size=5),
    ),
    max_leaves=20,
)

json_arg_dicts = st.dictionaries(
    st.text(
        min_size=1,
        max_size=20,
        alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    ),
    json_values,
    min_size=1,
    max_size=10,
)


@pytest.mark.asyncio
@given(args=json_arg_dicts)
@settings(max_examples=100)
async def test_post_tool_call_passes_arguments_unchanged(args: dict) -> None:
    """_post_tool_call sends arguments exactly as provided.

    **Validates: Requirements 3.4**

    Property 10: For any arguments dict, _post_tool_call sends them exactly
    as provided with no modification in {"arguments": args}.
    """
    captured_body: dict = {}

    async def mock_post(url, json=None, headers=None):
        captured_body["json"] = json
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"content": "ok", "error": False}
        return resp

    mock_client = AsyncMock()
    mock_client.post = mock_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch.object(env_toolset.httpx, "AsyncClient", return_value=mock_client):
        await _post_tool_call("test-session", "test_tool", args)

    assert captured_body["json"] == {"arguments": args}
