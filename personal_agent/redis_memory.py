"""Session memory writer (Plane B) — Personal Agent writes, CS Agent reads.

Best-effort enrichment: Redis failures are logged but never propagated.
"""

import logging
import os
import time

import redis
from google.adk.tools import ToolContext

from env_toolset import session_id

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "")
TTL_SECONDS = 3600


def _get_client() -> redis.Redis | None:
    """Get Plane B Redis client, or None if REDIS_URL is empty/unset."""
    if not REDIS_URL:
        return None
    return redis.Redis.from_url(REDIS_URL, decode_responses=True)


async def write_session_memory(tool_context: ToolContext, **fields: str) -> str:
    """Write user details to session memory for the CS Agent to read.

    Stores verification data (DOB, email, phone, address) and user context
    so the CS Agent can fast-path verification without extra conversation turns.

    Supported fields: verified, dob, email, phone, address, user_id, user_intent.
    Pass any combination as keyword arguments.
    """
    client = _get_client()
    if client is None:
        return "Session memory not available (no Redis configured)."

    try:
        key = f"session:{session_id(tool_context)}:memory"
        fields["last_updated"] = str(int(time.time()))
        client.hset(key, mapping=fields)
        client.expire(key, TTL_SECONDS)
        return f"Stored {len(fields) - 1} field(s) in session memory."
    except Exception as e:
        logger.warning(f"Session memory write failed: {e}")
        return "Session memory write failed (non-critical, continuing)."
