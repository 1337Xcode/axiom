"""Property test: unlock_and_call_agent_tool atomicity guarantees.

**Validates: Requirements 4.4, 4.5, 4.6**

Property 9: Discoverable Tool Atomicity
For any invocation of unlock_and_call_agent_tool(tool_name, arguments), the
function SHALL call unlock_discoverable_agent_tool(tool_name) immediately followed
by call_discoverable_agent_tool(tool_name, arguments) with no intervening
operations. If unlock fails, the call is not attempted, but no unlock occurs
without an attempted call in the success path.
"""

import os
import sys
import json
import types as builtin_types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Mock third-party modules before importing discoverable_tools
_mock_httpx = MagicMock()
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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cs_agent"))

# Import the module under test with mocked dependencies
with patch.dict(sys.modules, _mock_modules):
    with patch.dict(os.environ, {"ENV_API_URL": "http://test:8090", "ENV_API_TOKEN": "tok"}):
        if "env_toolset" in sys.modules:
            del sys.modules["env_toolset"]
        if "discoverable_tools" in sys.modules:
            del sys.modules["discoverable_tools"]
        import env_toolset
        import discoverable_tools


# Strategy: tool names (non-empty alphanumeric + underscores, like real tool names)
tool_name_strategy = st.from_regex(r"[a-z][a-z0-9_]{2,40}", fullmatch=True)

# Strategy: JSON-compatible argument dicts
json_values = st.recursive(
    st.one_of(
        st.text(max_size=30),
        st.integers(min_value=-100000, max_value=100000),
        st.floats(allow_nan=False, allow_infinity=False),
        st.booleans(),
        st.none(),
    ),
    lambda children: st.one_of(
        st.lists(children, max_size=3),
        st.dictionaries(st.text(min_size=1, max_size=15), children, max_size=3),
    ),
    max_leaves=10,
)

json_arg_dicts = st.dictionaries(
    st.text(
        min_size=1,
        max_size=20,
        alphabet=st.characters(whitelist_categories=("L", "N")),
    ),
    json_values,
    min_size=0,
    max_size=5,
)


@pytest.mark.asyncio
@given(tool_name=tool_name_strategy, args=json_arg_dicts)
@settings(max_examples=100)
async def test_unlock_then_call_on_success(tool_name: str, args: dict) -> None:
    """On success path, unlock is always called first, then call follows.

    **Validates: Requirements 4.4, 4.5, 4.6**

    Verifies: unlock is always called first, call always follows on unlock success.
    Verifies: unlock is never called without an attempted call on the success path.
    """
    call_log: list[tuple[str, str, dict]] = []

    async def mock_post_tool_call(sid, name, arguments):
        call_log.append((sid, name, arguments))
        return {"content": "ok", "error": False}

    mock_tool_context = MagicMock()
    mock_tool_context.session.id = "test-session-123"

    arguments_json = json.dumps(args)

    with patch.object(discoverable_tools, "_post_tool_call", side_effect=mock_post_tool_call):
        with patch.object(discoverable_tools, "session_id", return_value="test-session-123"):
            result = await discoverable_tools.unlock_and_call_agent_tool(
                tool_name, arguments_json, mock_tool_context
            )

    # Must have exactly 2 calls: unlock then call
    assert len(call_log) == 2, f"Expected 2 calls, got {len(call_log)}"

    # First call must be unlock_discoverable_agent_tool with the tool_name
    unlock_sid, unlock_name, unlock_args = call_log[0]
    assert unlock_name == "unlock_discoverable_agent_tool"
    assert unlock_args == {"tool_name": tool_name}
    assert unlock_sid == "test-session-123"

    # Second call must be call_discoverable_agent_tool with tool_name + arguments
    call_sid, call_name, call_args = call_log[1]
    assert call_name == "call_discoverable_agent_tool"
    assert call_args == {"tool_name": tool_name, "arguments": args}
    assert call_sid == "test-session-123"


@pytest.mark.asyncio
@given(tool_name=tool_name_strategy, args=json_arg_dicts)
@settings(max_examples=100)
async def test_no_call_when_unlock_fails(tool_name: str, args: dict) -> None:
    """If unlock fails (error=True), call is never attempted.

    **Validates: Requirements 4.4, 4.5, 4.6**

    Verifies: if unlock fails (error=True), call is never attempted.
    """
    call_log: list[tuple[str, str, dict]] = []

    async def mock_post_tool_call(sid, name, arguments):
        call_log.append((sid, name, arguments))
        # Unlock always returns an error
        if name == "unlock_discoverable_agent_tool":
            return {"error": True, "content": "tool not found"}
        return {"content": "ok", "error": False}

    mock_tool_context = MagicMock()
    mock_tool_context.session.id = "test-session-456"

    arguments_json = json.dumps(args)

    with patch.object(discoverable_tools, "_post_tool_call", side_effect=mock_post_tool_call):
        with patch.object(discoverable_tools, "session_id", return_value="test-session-456"):
            result = await discoverable_tools.unlock_and_call_agent_tool(
                tool_name, arguments_json, mock_tool_context
            )

    # Only 1 call: unlock (which failed)
    assert len(call_log) == 1, f"Expected 1 call (unlock only), got {len(call_log)}"

    # The single call is unlock
    unlock_sid, unlock_name, unlock_args = call_log[0]
    assert unlock_name == "unlock_discoverable_agent_tool"
    assert unlock_args == {"tool_name": tool_name}

    # Result must indicate error
    assert result.get("error") is True
    assert "Unlock failed" in result.get("content", "")


@pytest.mark.asyncio
@given(tool_name=tool_name_strategy, args=json_arg_dicts)
@settings(max_examples=100)
async def test_unlock_never_without_attempted_call_on_success(
    tool_name: str, args: dict
) -> None:
    """Unlock is never called without an attempted call on the success path.

    **Validates: Requirements 4.4, 4.5, 4.6**

    This verifies that whenever unlock succeeds, call is always attempted —
    there is no code path where unlock succeeds but call is skipped.
    """
    call_log: list[tuple[str, str, dict]] = []

    async def mock_post_tool_call(sid, name, arguments):
        call_log.append((sid, name, arguments))
        # Unlock succeeds, call also succeeds
        return {"content": "result", "error": False}

    mock_tool_context = MagicMock()
    mock_tool_context.session.id = "test-session-789"

    arguments_json = json.dumps(args)

    with patch.object(discoverable_tools, "_post_tool_call", side_effect=mock_post_tool_call):
        with patch.object(discoverable_tools, "session_id", return_value="test-session-789"):
            result = await discoverable_tools.unlock_and_call_agent_tool(
                tool_name, arguments_json, mock_tool_context
            )

    # Find all unlock calls in the log
    unlock_calls = [c for c in call_log if c[1] == "unlock_discoverable_agent_tool"]
    call_calls = [c for c in call_log if c[1] == "call_discoverable_agent_tool"]

    # Every unlock must have a corresponding call attempt
    assert len(unlock_calls) == len(call_calls), (
        f"Unlock count ({len(unlock_calls)}) != call count ({len(call_calls)}). "
        f"Unlock without call violates atomicity."
    )

    # Verify ordering: unlock always precedes its call
    for i, (sid, name, _) in enumerate(call_log):
        if name == "call_discoverable_agent_tool":
            # There must be an unlock before this call
            preceding_unlocks = [
                c for c in call_log[:i]
                if c[1] == "unlock_discoverable_agent_tool"
            ]
            assert len(preceding_unlocks) > 0, (
                "call_discoverable_agent_tool found without preceding unlock"
            )
