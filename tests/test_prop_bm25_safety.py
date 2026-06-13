"""Property test: BM25 query is safe for any input.

**Validates: Requirements 5.3, 5.4**

Property 6: BM25 Query Safety
For any input string (including empty strings, special characters, very long
strings, unicode, and strings with only non-word characters), kb_search_bm25
produces a valid RediSearch query without injection and never raises.
"""

import os
import sys
import types as builtin_types
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cs_agent"))

# Mock modules that aren't available in the test environment
_mock_modules = {}
for mod_name in ["redis", "google", "google.genai"]:
    _mock_modules[mod_name] = builtin_types.ModuleType(mod_name)
_mock_modules["google"].__path__ = []
_mock_modules["google.genai"].__path__ = []

# Mock redis client
mock_redis_client = MagicMock()
mock_redis_client.execute_command.return_value = [0]  # empty FT.SEARCH result
_mock_modules["redis"].Redis = MagicMock()
_mock_modules["redis"].Redis.from_url.return_value = mock_redis_client

with patch.dict(sys.modules, _mock_modules):
    with patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379/0"}):
        sys.modules.pop("rag_tools", None)
        from rag_tools import kb_search_bm25


# Strategy: any text including special characters
any_text = st.text(
    min_size=0,
    max_size=500,
    alphabet=st.characters(blacklist_categories=()),  # ALL unicode chars
)


@given(query=any_text)
@settings(max_examples=200)
def test_bm25_never_raises(query: str):
    """kb_search_bm25 never raises regardless of input.

    **Validates: Requirements 5.3, 5.4**
    """
    mock_redis_client.execute_command.return_value = [0]
    result = kb_search_bm25(query)
    assert isinstance(result, list)


@given(query=st.text(alphabet=st.characters(whitelist_categories=("P", "S", "Z")), min_size=0, max_size=100))
@settings(max_examples=100)
def test_bm25_empty_for_non_word_queries(query: str):
    """Queries with no word characters return [] without calling Redis.

    **Validates: Requirements 5.3, 5.4**
    """
    import re
    assume(not re.findall(r"\w+", query))
    mock_redis_client.execute_command.reset_mock()
    result = kb_search_bm25(query)
    assert result == []
    mock_redis_client.execute_command.assert_not_called()


@given(query=st.text(min_size=1, max_size=200, alphabet=st.characters(blacklist_categories=())))
@settings(max_examples=200)
def test_bm25_query_well_formed(query: str):
    """For valid queries with word tokens, FT.SEARCH command is well-formed.

    **Validates: Requirements 5.3, 5.4**

    Verifies:
    - OR-join query contains only alphanumeric/underscore chars and pipe separators
    - No RediSearch special characters (@, |outside-join, {, }, *, ?) leak through
    - Command arguments are properly structured
    """
    import re
    terms = re.findall(r"\w+", query.lower())
    assume(len(terms) > 0)

    mock_redis_client.execute_command.reset_mock()
    mock_redis_client.execute_command.return_value = [0]

    kb_search_bm25(query)

    mock_redis_client.execute_command.assert_called_once()
    call_args = mock_redis_client.execute_command.call_args[0]

    # Verify command structure: FT.SEARCH, index_name, query, LIMIT, ...
    assert call_args[0] == "FT.SEARCH"
    assert call_args[1] == "kb_idx"

    # The query (3rd arg) should be pipe-separated \w+ tokens only
    ft_query = call_args[2]

    # Each segment between pipes must be a valid \w+ token (no injection)
    segments = ft_query.split("|")
    for segment in segments:
        assert re.fullmatch(r"\w+", segment), (
            f"Query segment '{segment}' is not a valid \\w+ token"
        )

    # Verify no duplicates in segments
    assert len(segments) == len(set(segments))
