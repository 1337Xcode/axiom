"""Unit tests for Redis session memory (Plane B) — write and read operations.

Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.8
"""

import importlib
import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helper to import redis_memory modules with mocked dependencies
# ---------------------------------------------------------------------------


def _import_personal_redis_memory(mock_redis_module, redis_url="redis://localhost:6379/0"):
    """Import personal_agent.redis_memory with mocked redis and controlled REDIS_URL."""
    # Remove cached module if present
    for key in list(sys.modules.keys()):
        if "redis_memory" in key:
            del sys.modules[key]

    with patch.dict(os.environ, {"REDIS_URL": redis_url}):
        with patch.dict(sys.modules, {"redis": mock_redis_module}):
            import personal_agent.redis_memory as mod
            importlib.reload(mod)
            return mod


def _import_cs_redis_memory(mock_redis_module, redis_url="redis://localhost:6379/0"):
    """Import cs_agent.redis_memory with mocked redis and controlled REDIS_URL."""
    for key in list(sys.modules.keys()):
        if "redis_memory" in key:
            del sys.modules[key]

    with patch.dict(os.environ, {"REDIS_URL": redis_url}):
        with patch.dict(sys.modules, {"redis": mock_redis_module}):
            import cs_agent.redis_memory as mod
            importlib.reload(mod)
            return mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_redis_module():
    """Create a mock redis module with a controllable Redis client."""
    mock_mod = MagicMock()
    mock_client = MagicMock()
    mock_client.hset = MagicMock()
    mock_client.hgetall = MagicMock(return_value={})
    mock_client.expire = MagicMock()
    mock_mod.Redis.from_url.return_value = mock_client
    return mock_mod, mock_client


@pytest.fixture
def tool_context():
    """Mock ADK ToolContext with a known session.id."""
    ctx = MagicMock()
    ctx.session.id = "session-uuid-12345"
    return ctx


# ---------------------------------------------------------------------------
# Tests: write_session_memory stores fields at correct key
# ---------------------------------------------------------------------------


class TestWriteSessionMemory:
    """Tests for personal_agent.redis_memory.write_session_memory."""

    @pytest.mark.asyncio
    async def test_stores_fields_at_correct_key(self, mock_redis_module, tool_context):
        """write_session_memory stores fields at session:{contextId}:memory."""
        mock_mod, mock_client = mock_redis_module
        mod = _import_personal_redis_memory(mock_mod)

        with patch.object(mod, "_get_client", return_value=mock_client):
            await mod.write_session_memory(tool_context, dob="1990-01-15", email="user@example.com")

        expected_key = "session:session-uuid-12345:memory"
        mock_client.hset.assert_called_once()
        call_args = mock_client.hset.call_args
        # hset is called as hset(key, mapping=...)
        actual_key = call_args[0][0] if call_args[0] else call_args[1].get("name")
        assert actual_key == expected_key

    @pytest.mark.asyncio
    async def test_stores_multiple_fields(self, mock_redis_module, tool_context):
        """write_session_memory passes all provided fields to HSET mapping."""
        mock_mod, mock_client = mock_redis_module
        mod = _import_personal_redis_memory(mock_mod)

        with patch.object(mod, "_get_client", return_value=mock_client):
            await mod.write_session_memory(
                tool_context, dob="1990-01-15", email="user@ex.com", phone="555-1234"
            )

        call_args = mock_client.hset.call_args
        mapping = call_args[1].get("mapping") or call_args.kwargs.get("mapping")
        assert mapping is not None
        assert mapping["dob"] == "1990-01-15"
        assert mapping["email"] == "user@ex.com"
        assert mapping["phone"] == "555-1234"

    @pytest.mark.asyncio
    async def test_last_updated_field_is_set(self, mock_redis_module, tool_context):
        """write_session_memory sets last_updated to current Unix epoch string."""
        mock_mod, mock_client = mock_redis_module
        mod = _import_personal_redis_memory(mock_mod)

        before = int(time.time())
        with patch.object(mod, "_get_client", return_value=mock_client):
            await mod.write_session_memory(tool_context, dob="1990-01-15")
        after = int(time.time())

        call_args = mock_client.hset.call_args
        mapping = call_args[1].get("mapping") or call_args.kwargs.get("mapping")
        assert "last_updated" in mapping
        last_updated = int(mapping["last_updated"])
        assert before <= last_updated <= after

    @pytest.mark.asyncio
    async def test_ttl_set_to_3600(self, mock_redis_module, tool_context):
        """write_session_memory sets TTL to 3600 seconds on the key."""
        mock_mod, mock_client = mock_redis_module
        mod = _import_personal_redis_memory(mock_mod)

        with patch.object(mod, "_get_client", return_value=mock_client):
            await mod.write_session_memory(tool_context, email="a@b.com")

        expected_key = "session:session-uuid-12345:memory"
        mock_client.expire.assert_called_once_with(expected_key, 3600)

    @pytest.mark.asyncio
    async def test_best_effort_redis_failure_no_raise(self, mock_redis_module, tool_context):
        """write_session_memory catches Redis exceptions and does not raise."""
        mock_mod, mock_client = mock_redis_module
        mock_client.hset.side_effect = ConnectionError("Redis unavailable")
        mod = _import_personal_redis_memory(mock_mod)

        with patch.object(mod, "_get_client", return_value=mock_client):
            # Should not raise
            result = await mod.write_session_memory(tool_context, dob="1990-01-15")

        # Function should return gracefully (non-critical failure message)
        assert result is not None

    @pytest.mark.asyncio
    async def test_no_redis_url_skips_silently(self, tool_context):
        """write_session_memory skips when REDIS_URL is empty."""
        mock_mod = MagicMock()
        mod = _import_personal_redis_memory(mock_mod, redis_url="")

        with patch.object(mod, "_get_client", return_value=None):
            result = await mod.write_session_memory(tool_context, dob="1990-01-15")

        # Should not call Redis at all
        mock_mod.Redis.from_url.return_value.hset.assert_not_called()
        assert result is not None


# ---------------------------------------------------------------------------
# Tests: read_session_memory returns all fields
# ---------------------------------------------------------------------------


class TestReadSessionMemory:
    """Tests for cs_agent.redis_memory.read_session_memory."""

    @pytest.mark.asyncio
    async def test_returns_all_stored_fields(self, mock_redis_module, tool_context):
        """read_session_memory returns dict with all fields from Redis HGETALL."""
        mock_mod, mock_client = mock_redis_module
        mock_client.hgetall.return_value = {
            "dob": "1990-01-15",
            "email": "user@ex.com",
            "verified": "true",
            "last_updated": "1700000000",
        }
        mod = _import_cs_redis_memory(mock_mod)

        with patch.object(mod, "_get_client", return_value=mock_client):
            result = await mod.read_session_memory(tool_context)

        assert result == {
            "dob": "1990-01-15",
            "email": "user@ex.com",
            "verified": "true",
            "last_updated": "1700000000",
        }

    @pytest.mark.asyncio
    async def test_returns_empty_dict_when_no_data(self, mock_redis_module, tool_context):
        """read_session_memory returns empty dict when key doesn't exist."""
        mock_mod, mock_client = mock_redis_module
        mock_client.hgetall.return_value = {}
        mod = _import_cs_redis_memory(mock_mod)

        with patch.object(mod, "_get_client", return_value=mock_client):
            result = await mod.read_session_memory(tool_context)

        assert result == {}

    @pytest.mark.asyncio
    async def test_reads_from_correct_key(self, mock_redis_module, tool_context):
        """read_session_memory reads from session:{contextId}:memory."""
        mock_mod, mock_client = mock_redis_module
        mod = _import_cs_redis_memory(mock_mod)

        with patch.object(mod, "_get_client", return_value=mock_client):
            await mod.read_session_memory(tool_context)

        expected_key = "session:session-uuid-12345:memory"
        mock_client.hgetall.assert_called_once_with(expected_key)

    @pytest.mark.asyncio
    async def test_best_effort_redis_failure_returns_empty(self, mock_redis_module, tool_context):
        """read_session_memory catches Redis exceptions and returns empty dict."""
        mock_mod, mock_client = mock_redis_module
        mock_client.hgetall.side_effect = ConnectionError("Redis unavailable")
        mod = _import_cs_redis_memory(mock_mod)

        with patch.object(mod, "_get_client", return_value=mock_client):
            result = await mod.read_session_memory(tool_context)

        assert result == {}

    @pytest.mark.asyncio
    async def test_no_redis_url_returns_empty(self, tool_context):
        """read_session_memory returns empty dict when REDIS_URL is empty."""
        mock_mod = MagicMock()
        mod = _import_cs_redis_memory(mock_mod, redis_url="")

        with patch.object(mod, "_get_client", return_value=None):
            result = await mod.read_session_memory(tool_context)

        assert result == {}
