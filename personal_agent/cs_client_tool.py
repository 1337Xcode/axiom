"""A2A client tool: ask_customer_service sends a message to the CS Agent.

Builds an outgoing A2A Message with the session's contextId and sends it to
the CS Agent (via the harness gateway). Handles both Message and Task response
types for cross-pair robustness with unknown external CS agents.
"""

import logging
import os
import uuid
from typing import Any

import httpx
from a2a.client import ClientConfig, ClientFactory, minimal_agent_card
from a2a.types import Message, Part, Role, Task, TextPart
from google.adk.tools import ToolContext

from env_toolset import session_id

logger = logging.getLogger(__name__)

CS_AGENT_URL = os.environ.get("CS_AGENT_URL", "http://cs-agent:9002")

_TIMEOUT_S = 300.0


def _text_of_parts(parts: Any) -> str:
    """Extract text from a list of A2A parts.

    Handles both SDK model objects (Part with .root) and raw dicts. Uses both
    'kind' and 'type' as discriminators for cross-pair robustness with unknown
    external agents that may use either format.
    """
    texts: list[str] = []
    for part in parts or []:
        # SDK model: Part has a .root attribute wrapping the union
        root = getattr(part, "root", part)
        if isinstance(root, TextPart) and root.text:
            texts.append(root.text)
        elif hasattr(root, "text") and root.text:
            # Fallback for any part-like object with a text attribute
            texts.append(root.text)
        elif isinstance(root, dict):
            # Raw dict (possible from non-SDK responses) — check kind or type
            kind = root.get("kind") or root.get("type", "")
            if kind == "text" and root.get("text"):
                texts.append(root["text"])
    return "\n".join(texts)


def _text_of_message(message: Message) -> str:
    """Extract text content from an A2A Message response."""
    return _text_of_parts(message.parts)


def _text_of_task(task: Task) -> str:
    """Extract text content from an A2A Task response.

    Checks both artifacts[].parts and status.message.parts, joining all found
    text content.
    """
    texts: list[str] = []
    # Extract from artifacts
    for artifact in task.artifacts or []:
        text = _text_of_parts(artifact.parts)
        if text:
            texts.append(text)
    # Extract from status.message
    if task.status is not None and task.status.message is not None:
        text = _text_of_message(task.status.message)
        if text:
            texts.append(text)
    return "\n".join(texts)


async def ask_customer_service(message: str, tool_context: ToolContext) -> str:
    """Send a message to Rho-Bank's customer service agent and return its reply.

    Use this for account lookups, policy questions, bank-side operations,
    disputes, and any request where you lack a matching tool or are uncertain.
    The conversation with customer service persists for this whole session,
    so you can ask follow-up questions and they will remember the context.

    message: The message to send to customer service.
    """
    ctx_id = session_id(tool_context)

    outgoing = Message(
        message_id=uuid.uuid4().hex,
        role=Role.user,
        parts=[Part(root=TextPart(text=message))],
        context_id=ctx_id,
    )

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as http_client:
            client = ClientFactory(
                ClientConfig(streaming=False, httpx_client=http_client)
            ).create(minimal_agent_card(CS_AGENT_URL, ["JSONRPC"]))

            reply = ""
            async for event in client.send_message(outgoing):
                if isinstance(event, Message):
                    reply = _text_of_message(event) or reply
                elif isinstance(event, tuple) and isinstance(event[0], Task):
                    reply = _text_of_task(event[0]) or reply
                elif isinstance(event, Task):
                    reply = _text_of_task(event) or reply

        return reply or "[no response from customer service]"

    except httpx.TimeoutException:
        logger.warning("CS agent did not respond within %s seconds", _TIMEOUT_S)
        return "[customer service did not respond within timeout]"
    except Exception as e:
        logger.warning("CS agent communication error: %s: %s", type(e).__name__, e)
        return f"[customer service communication error: {type(e).__name__}]"
