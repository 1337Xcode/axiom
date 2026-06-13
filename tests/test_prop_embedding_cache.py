"""Property test: cached embeddings are used without calling _embed().

**Validates: Requirement 5.6**

Property 7: Embedding Cache Utilization
For documents with cached embeddings, build_index() uses cached bytes directly
without calling _embed().
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

# Generate fake document collections with embeddings
EMBEDDING_DIM = 768

doc_strategy = st.lists(
    st.fixed_dictionaries({
        "id": st.text(min_size=3, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))),
        "title": st.text(min_size=1, max_size=50),
        "content": st.text(min_size=1, max_size=100),
    }),
    min_size=1,
    max_size=10,
    unique_by=lambda d: d["id"],
)


def fake_embedding_bytes() -> bytes:
    """768-dim float32 vector as bytes."""
    return struct.pack(f"{EMBEDDING_DIM}f", *([0.1] * EMBEDDING_DIM))


@given(docs=doc_strategy)
@settings(max_examples=30)
def test_cached_embeddings_skip_embed_call(docs: list[dict]):
    """When all docs have cached embeddings, _embed() is never called.

    **Validates: Requirement 5.6**
    """
    # Build cache for ALL documents
    cache = {doc["id"]: fake_embedding_bytes() for doc in docs}

    # Mock Redis pipeline
    mock_pipe = MagicMock()
    mock_redis_client = MagicMock()
    mock_redis_client.pipeline.return_value = mock_pipe
    mock_redis_client.ft.return_value = MagicMock()

    mock_embed = MagicMock()

    mock_modules = {}
    for mod_name in ["redis", "redis.commands", "redis.commands.search",
                     "redis.commands.search.field", "redis.commands.search.index_definition",
                     "google", "google.genai"]:
        mock_modules[mod_name] = builtin_types.ModuleType(mod_name)
    mock_modules["google"].__path__ = []
    mock_modules["google.genai"].__path__ = []
    mock_modules["redis"].Redis = MagicMock()
    mock_modules["redis"].Redis.from_url.return_value = mock_redis_client
    mock_modules["redis"].ResponseError = Exception
    mock_modules["redis.commands.search.field"].TextField = MagicMock()
    mock_modules["redis.commands.search.field"].VectorField = MagicMock()
    mock_modules["redis.commands.search.index_definition"].IndexDefinition = MagicMock()
    mock_modules["redis.commands.search.index_definition"].IndexType = MagicMock()

    with patch.dict(sys.modules, mock_modules):
        with patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379/0"}):
            sys.modules.pop("rag_tools", None)
            sys.modules.pop("ingest", None)
            import ingest

    with patch.object(ingest, "load_documents", return_value=docs):
        with patch.object(ingest, "load_embedding_cache", return_value=cache):
            with patch.object(ingest, "_embed", mock_embed):
                ingest.build_index()

    # _embed should never be called when all docs are cached
    mock_embed.assert_not_called()
