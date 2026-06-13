"""Session memory reader (Plane B) — CS Agent reads what Personal Agent wrote.

Best-effort: Redis failures are logged but never propagated.
"""

import logging
import os

import redis
from google.adk.tools import ToolContext

from env_toolset import session_id

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "")


def _get_client() -> redis.Redis | None:
    """Get Plane B Redis client, or None if REDIS_URL is empty/unset."""
    if not REDIS_URL:
        return None
    return redis.Redis.from_url(REDIS_URL, decode_responses=True)


async def read_session_memory(tool_context: ToolContext) -> dict:
    """Read session memory written by the Personal Agent.

    Returns all stored fields (verified, dob, email, phone, address,
    user_id, user_intent, last_updated) or an empty dict if nothing is
    stored or Redis is unavailable.
    """
    client = _get_client()
    if client is None:
        return {}

    try:
        key = f"session:{session_id(tool_context)}:memory"
        data = client.hgetall(key)
        return data or {}
    except Exception as e:
        logger.warning(f"Session memory read failed: {e}")
        return {}
