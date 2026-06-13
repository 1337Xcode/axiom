"""Property test: _embed() is called in batches of at most 25.

**Validates: Requirement 5.7**

Property 8: Embedding Batch Size
For any N documents needing live embedding, _embed() is called in batches
of at most 25 — the EMBED_BATCH_SIZE constant.
"""

import os
import sys
import struct
import types as builtin_types
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cs_agent"))

EMBEDDING_DIM = 768

# Generate documents of various sizes (1 to 80 unique docs)
doc_strategy = st.lists(
    st.fixed_dictionaries({
        "id": st.text(
            min_size=3,
            max_size=20,
            alphabet=st.characters(whitelist_categories=("L", "N")),
        ),
        "title": st.text(min_size=1, max_size=30),
        "content": st.text(min_size=1, max_size=50),
    }),
    min_size=1,
    max_size=80,
    unique_by=lambda d: d["id"],
)


@given(docs=doc_strategy)
@settings(max_examples=30)
def test_embed_batches_max_25(docs: list[dict]):
    """_embed() is never called with more than 25 texts at once.

    **Validates: Requirement 5.7**
    """
    embed_call_sizes: list[int] = []

    def fake_embed(texts: list[str]) -> list[list[float]]:
        embed_call_sizes.append(len(texts))
        return [[0.1] * EMBEDDING_DIM for _ in texts]

    # Mock Redis client and pipeline
    mock_pipe = MagicMock()
    mock_redis_client = MagicMock()
    mock_redis_client.pipeline.return_value = mock_pipe
    mock_redis_client.ft.return_value = MagicMock()

    # Build mock modules for third-party deps not installed in test env
    mock_modules: dict[str, builtin_types.ModuleType] = {}
    for mod_name in [
        "redis",
        "redis.commands",
        "redis.commands.search",
        "redis.commands.search.field",
        "redis.commands.search.index_definition",
        "google",
        "google.genai",
    ]:
        mock_modules[mod_name] = builtin_types.ModuleType(mod_name)

    mock_modules["google"].__path__ = []
    mock_modules["google.genai"].__path__ = []
    mock_modules["redis"].Redis = MagicMock()
    mock_modules["redis"].Redis.from_url = MagicMock(return_value=mock_redis_client)
    mock_modules["redis"].ResponseError = Exception
    mock_modules["redis.commands.search.field"].TextField = MagicMock()
    mock_modules["redis.commands.search.field"].VectorField = MagicMock()
    mock_modules["redis.commands.search.index_definition"].IndexDefinition = MagicMock()
    mock_modules["redis.commands.search.index_definition"].IndexType = MagicMock()

    with patch.dict(sys.modules, mock_modules):
        with patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379/0"}):
            # Force fresh import with our mocks
            sys.modules.pop("rag_tools", None)
            sys.modules.pop("ingest", None)
            import ingest

    # No cached embeddings — all docs need live embedding
    embed_call_sizes.clear()
    with patch.object(ingest, "load_documents", return_value=docs):
        with patch.object(ingest, "load_embedding_cache", return_value={}):
            with patch.object(ingest, "_embed", side_effect=fake_embed):
                ingest.build_index()

    # Every call to _embed must have at most 25 texts
    for i, size in enumerate(embed_call_sizes):
        assert size <= 25, f"Batch {i} had {size} items, exceeds max of 25"

    # Should have been called at least once (docs exist)
    assert len(embed_call_sizes) > 0, "Expected at least one _embed() call"
