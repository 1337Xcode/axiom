"""Atomic unlock + call for agent-discoverable tools.

Prevents the LLM from splitting unlock/call across turns (Trap 6).
"""

import json
import logging

from google.adk.tools import ToolContext

from env_toolset import session_id, _post_tool_call

logger = logging.getLogger(__name__)


async def unlock_and_call_agent_tool(
    tool_name: str, arguments_json: str, tool_context: ToolContext
) -> dict:
    """Unlock an agent-discoverable tool and immediately call it.

    This is an atomic operation: unlock followed by call. If unlock fails,
    the call is not attempted. If the call fails, the tool remains unlocked
    (retry the call directly, do not re-unlock).

    tool_name: The exact tool name from the knowledge base.
    arguments_json: JSON string of the tool's arguments, e.g. '{"user_id": "abc123"}'.
    """
    sid = session_id(tool_context)

    # Step 1: Unlock the tool
    unlock_result = await _post_tool_call(
        sid, "unlock_discoverable_agent_tool", {"tool_name": tool_name}
    )

    # If unlock failed, return the error without attempting call
    if isinstance(unlock_result, dict) and unlock_result.get("error"):
        return {
            "error": True,
            "content": f"Unlock failed: {unlock_result.get('content', 'unknown error')}",
        }

    # Step 2: Parse arguments
    try:
        arguments = json.loads(arguments_json or "{}")
    except json.JSONDecodeError as e:
        return {"error": True, "content": f"Invalid arguments JSON: {e}"}

    # Step 3: Call the tool
    call_result = await _post_tool_call(
        sid,
        "call_discoverable_agent_tool",
        {"tool_name": tool_name, "arguments": arguments},
    )

    return call_result
