"""Property test: session memory round-trip preserves all fields.

**Validates: Requirements 6.1, 6.2, 6.6**

Property 3: Session Memory Round-Trip
For any combination of valid session memory fields, writing those fields via
write_session_memory() and then reading via HGETALL with the same contextId
returns a dictionary containing all written field values unchanged.
"""

import os
import sys
import types as builtin_types
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# Add personal_agent to path for import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "personal_agent"))


# Strategy for session memory fields — at least one field required
memory_fields = st.fixed_dictionaries(
    {},
    optional={
        "verified": st.sampled_from(["true", "false"]),
        "dob": st.from_regex(r"\d{4}-\d{2}-\d{2}", fullmatch=True),
        "email": st.emails(),
        "phone": st.from_regex(r"\+?[0-9]{10,15}", fullmatch=True),
        "address": st.text(min_size=5, max_size=100),
        "user_id": st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(whitelist_categories=("L", "N")),
        ),
        "user_intent": st.text(min_size=1, max_size=200),
    },
).filter(lambda d: len(d) >= 1)  # At least one field

session_ids = st.from_regex(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
    fullmatch=True,
)


class FakeRedis:
    """In-memory dict simulating Redis HASH operations (decode_responses=True)."""

    def __init__(self):
        self._store: dict[str, dict[str, str]] = {}

    def hset(self, key: str, mapping: dict | None = None) -> int:
        if key not in self._store:
            self._store[key] = {}
        if mapping:
            self._store[key].update(mapping)
        return len(mapping) if mapping else 0

    def hgetall(self, key: str) -> dict[str, str]:
        return dict(self._store.get(key, {}))

    def expire(self, key: str, ttl: int) -> bool:
        return True  # TTL tested separately in Property 4


def _import_redis_memory_module():
    """Import redis_memory module while mocking unavailable third-party modules.

    Returns the module object so we can patch its _get_client directly.
    """
    mock_modules = {}
    for mod_name in [
        "httpx",
        "google",
        "google.adk",
        "google.adk.agents",
        "google.adk.agents.readonly_context",
        "google.adk.tools",
        "google.adk.tools.base_toolset",
        "google.genai",
        "google.genai.types",
        "redis",
    ]:
        mock_mod = builtin_types.ModuleType(mod_name)
        mock_modules[mod_name] = mock_mod

    # Set up nested module attributes
    mock_modules["google"].__path__ = []
    mock_modules["google.adk"].__path__ = []
    mock_modules["google.adk.agents"].__path__ = []
    mock_modules["google.adk.tools"].__path__ = []
    mock_modules["google.genai"].__path__ = []

    # Add the classes/objects that modules import
    mock_modules["google.adk.agents.readonly_context"].ReadonlyContext = MagicMock
    mock_modules["google.adk.tools"].BaseTool = MagicMock
    mock_modules["google.adk.tools"].FunctionTool = MagicMock
    mock_modules["google.adk.tools"].ToolContext = MagicMock
    mock_modules["google.adk.tools.base_toolset"].BaseToolset = MagicMock
    mock_modules["google.genai.types"] = MagicMock()
    mock_modules["redis"].Redis = MagicMock()

    with patch.dict(sys.modules, mock_modules):
        with patch.dict(
            os.environ,
            {
                "ENV_API_URL": "http://test:8090",
                "ENV_API_TOKEN": "tok",
                "REDIS_URL": "redis://localhost:6379/0",
            },
        ):
            # Remove cached modules to force re-import with mocks
            sys.modules.pop("env_toolset", None)
            sys.modules.pop("redis_memory", None)
            import redis_memory

    return redis_memory


# Import module once at module level
_redis_memory = _import_redis_memory_module()
write_session_memory = _redis_memory.write_session_memory


@pytest.mark.asyncio
@given(ctx_id=session_ids, fields=memory_fields)
@settings(max_examples=100)
async def test_memory_roundtrip(ctx_id: str, fields: dict):
    """Written fields are readable via HGETALL with same contextId.

    **Validates: Requirements 6.1, 6.2, 6.6**
    """
    fake_redis = FakeRedis()

    # Mock tool_context with session.id = ctx_id
    mock_tool_context = MagicMock()
    mock_tool_context.session.id = ctx_id

    # Patch _get_client on the already-imported module object
    original_get_client = _redis_memory._get_client
    _redis_memory._get_client = lambda: fake_redis
    try:
        import asyncio

        result = write_session_memory(mock_tool_context, **fields)
        # Handle both sync and async returns
        if asyncio.iscoroutine(result):
            await result
    finally:
        _redis_memory._get_client = original_get_client

    # Read back from the fake store using same key format
    key = f"session:{ctx_id}:memory"
    stored = fake_redis.hgetall(key)

    # Verify all written fields are preserved unchanged
    for field_name, field_value in fields.items():
        assert field_name in stored, f"Field '{field_name}' missing from stored data"
        assert stored[field_name] == field_value, (
            f"Field '{field_name}' changed: expected {field_value!r}, got {stored[field_name]!r}"
        )

    # Verify last_updated was added automatically
    assert "last_updated" in stored, "last_updated field was not added"


@pytest.mark.asyncio
@given(ctx_id=session_ids, fields=memory_fields)
@settings(max_examples=50)
async def test_memory_roundtrip_preserves_field_count(ctx_id: str, fields: dict):
    """Stored hash contains exactly written fields + last_updated.

    **Validates: Requirements 6.1, 6.2, 6.6**
    """
    fake_redis = FakeRedis()

    mock_tool_context = MagicMock()
    mock_tool_context.session.id = ctx_id

    original_get_client = _redis_memory._get_client
    _redis_memory._get_client = lambda: fake_redis
    try:
        import asyncio

        result = write_session_memory(mock_tool_context, **fields)
        if asyncio.iscoroutine(result):
            await result
    finally:
        _redis_memory._get_client = original_get_client

    key = f"session:{ctx_id}:memory"
    stored = fake_redis.hgetall(key)

    # Stored fields = user fields + last_updated
    expected_keys = set(fields.keys()) | {"last_updated"}
    assert set(stored.keys()) == expected_keys, (
        f"Key mismatch: expected {expected_keys}, got {set(stored.keys())}"
    )
