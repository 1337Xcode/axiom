"""Property test: Cross-pair robustness of A2A response parsing.

**Validates: Requirements 9.1, 9.3, 9.4, 9.8, 1.5, 1.6**

Property 12: Cross-Pair Robustness
For any incoming A2A message with unexpected fields/formats, agents process
without crashing. Specifically, the text extraction functions in cs_client_tool.py
(_text_of_parts, _text_of_message, _text_of_task) handle various response
formats without raising exceptions — always returning a string (possibly empty).
"""

import os
import sys
import types as builtin_types
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Add personal_agent to path for import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "personal_agent"))


# ---------------------------------------------------------------------------
# Hypothesis strategies for generating arbitrary A2A-like response structures
# ---------------------------------------------------------------------------

# Strategy for arbitrary text content (including empty, unicode, special chars)
arbitrary_text = st.one_of(
    st.text(min_size=0, max_size=500),
    st.just(""),
    st.just(None),
)

# Strategy for part discriminator field names (kind vs type vs missing)
discriminator_key = st.sampled_from(["kind", "type", "kind_and_type", "neither"])

# Strategy for part kind/type values (valid and invalid)
part_kind_value = st.one_of(
    st.just("text"),
    st.just("file"),
    st.just("data"),
    st.just("image"),
    st.just(""),
    st.text(min_size=0, max_size=20),
)


@st.composite
def raw_dict_part(draw):
    """Generate a raw dict representing an A2A part (cross-pair format)."""
    disc = draw(discriminator_key)
    kind_val = draw(part_kind_value)
    text_val = draw(arbitrary_text)

    part = {}
    if disc == "kind":
        part["kind"] = kind_val
    elif disc == "type":
        part["type"] = kind_val
    elif disc == "kind_and_type":
        part["kind"] = kind_val
        part["type"] = draw(part_kind_value)
    # "neither" means no discriminator at all

    if text_val is not None:
        part["text"] = text_val

    # Add random unexpected fields for robustness
    extra_fields = draw(st.dictionaries(
        keys=st.sampled_from(["metadata", "encoding", "mime_type", "uri", "data", "extra"]),
        values=st.one_of(st.text(max_size=50), st.integers(), st.none()),
        max_size=3,
    ))
    part.update(extra_fields)
    return part


@st.composite
def sdk_like_part(draw):
    """Generate an object mimicking an SDK Part with .root attribute."""
    text_val = draw(arbitrary_text)
    has_text_attr = draw(st.booleans())

    root = MagicMock()
    # Decide whether root looks like a TextPart
    if has_text_attr and text_val is not None:
        root.text = text_val
    else:
        root.text = None

    part = MagicMock()
    part.root = root
    return part


@st.composite
def arbitrary_part(draw):
    """Generate any kind of part: raw dict, SDK-like, or completely unexpected."""
    choice = draw(st.sampled_from(["raw_dict", "sdk_like", "none_value", "string", "int", "empty_mock"]))
    if choice == "raw_dict":
        return draw(raw_dict_part())
    elif choice == "sdk_like":
        return draw(sdk_like_part())
    elif choice == "none_value":
        return None
    elif choice == "string":
        return draw(st.text(max_size=100))
    elif choice == "int":
        return draw(st.integers())
    else:
        # Empty mock with no useful attributes
        return MagicMock(spec=[])


# Strategy for parts list (including None, empty, and mixed)
parts_list = st.one_of(
    st.none(),
    st.just([]),
    st.lists(arbitrary_part(), min_size=1, max_size=10),
)


@st.composite
def arbitrary_message(draw):
    """Generate an A2A Message-like object with arbitrary parts."""
    msg = MagicMock()
    msg.parts = draw(parts_list)
    # Add unexpected fields that an external agent might send
    msg.extra_field = draw(st.one_of(st.text(max_size=50), st.none()))
    return msg


@st.composite
def arbitrary_artifact(draw):
    """Generate an A2A artifact-like object with arbitrary parts."""
    artifact = MagicMock()
    artifact.parts = draw(parts_list)
    return artifact


@st.composite
def arbitrary_task(draw):
    """Generate an A2A Task-like object with arbitrary structure."""
    task = MagicMock()

    # artifacts: None, empty list, or list of artifacts
    has_artifacts = draw(st.booleans())
    if has_artifacts:
        task.artifacts = draw(st.lists(arbitrary_artifact(), min_size=0, max_size=5))
    else:
        task.artifacts = draw(st.sampled_from([None, []]))

    # status: None, or object with message
    has_status = draw(st.booleans())
    if has_status:
        has_message = draw(st.booleans())
        if has_message:
            task.status = MagicMock()
            task.status.message = draw(arbitrary_message())
        else:
            task.status = MagicMock()
            task.status.message = None
    else:
        task.status = None

    return task


# ---------------------------------------------------------------------------
# Module import helpers (mocking unavailable third-party deps)
# ---------------------------------------------------------------------------

def _build_mock_modules():
    """Build mock modules for third-party deps."""
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
        "a2a",
        "a2a.client",
        "a2a.types",
    ]:
        mock_mod = builtin_types.ModuleType(mod_name)
        mock_modules[mod_name] = mock_mod

    mock_modules["google"].__path__ = []
    mock_modules["google.adk"].__path__ = []
    mock_modules["google.adk.agents"].__path__ = []
    mock_modules["google.adk.tools"].__path__ = []
    mock_modules["google.genai"].__path__ = []
    mock_modules["a2a"].__path__ = []

    mock_modules["google.adk.agents.readonly_context"].ReadonlyContext = MagicMock
    mock_modules["google.adk.tools"].BaseTool = MagicMock
    mock_modules["google.adk.tools"].FunctionTool = MagicMock
    mock_modules["google.adk.tools"].ToolContext = MagicMock
    mock_modules["google.adk.tools.base_toolset"].BaseToolset = MagicMock
    mock_modules["google.genai.types"] = MagicMock()

    # A2A types with realistic structure
    class FakeTextPart:
        def __init__(self, **kwargs):
            self.text = kwargs.get("text", "")

    class FakeMessage:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    class FakePart:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    class FakeRole:
        user = "user"
        agent = "agent"

    class FakeTask:
        pass

    mock_modules["a2a.types"].Message = FakeMessage
    mock_modules["a2a.types"].Part = FakePart
    mock_modules["a2a.types"].TextPart = FakeTextPart
    mock_modules["a2a.types"].Role = FakeRole
    mock_modules["a2a.types"].Task = FakeTask

    mock_modules["a2a.client"].ClientFactory = MagicMock
    mock_modules["a2a.client"].ClientConfig = MagicMock
    mock_modules["a2a.client"].minimal_agent_card = MagicMock

    mock_modules["httpx"].AsyncClient = MagicMock
    mock_modules["httpx"].TimeoutException = type("TimeoutException", (Exception,), {})

    return mock_modules, FakeTextPart


_mock_modules, FakeTextPart = _build_mock_modules()


def _import_text_functions():
    """Import the text extraction functions from cs_client_tool."""
    with patch.dict(sys.modules, _mock_modules):
        with patch.dict(os.environ, {
            "ENV_API_URL": "http://test:8090",
            "ENV_API_TOKEN": "tok",
            "CS_AGENT_URL": "http://test-cs:9002",
        }):
            sys.modules.pop("env_toolset", None)
            sys.modules.pop("cs_client_tool", None)
            from cs_client_tool import _text_of_parts, _text_of_message, _text_of_task
    return _text_of_parts, _text_of_message, _text_of_task


_text_of_parts, _text_of_message, _text_of_task = _import_text_functions()


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@given(parts=parts_list)
@settings(max_examples=300)
def test_text_of_parts_never_crashes(parts):
    """_text_of_parts handles any parts list without raising exceptions.

    **Validates: Requirements 9.1, 9.3, 9.4, 9.8, 1.5, 1.6**
    """
    result = _text_of_parts(parts)
    assert isinstance(result, str)


@given(message=arbitrary_message())
@settings(max_examples=200)
def test_text_of_message_never_crashes(message):
    """_text_of_message handles any Message-like object without raising.

    **Validates: Requirements 9.1, 9.3, 9.4, 9.8, 1.5, 1.6**
    """
    result = _text_of_message(message)
    assert isinstance(result, str)


@given(task=arbitrary_task())
@settings(max_examples=200)
def test_text_of_task_never_crashes(task):
    """_text_of_task handles any Task-like object without raising.

    **Validates: Requirements 9.1, 9.3, 9.4, 9.8, 1.5, 1.6**
    """
    result = _text_of_task(task)
    assert isinstance(result, str)


@given(parts=st.lists(raw_dict_part(), min_size=1, max_size=10))
@settings(max_examples=200)
def test_text_of_parts_handles_raw_dicts(parts):
    """_text_of_parts handles raw dict parts (from non-SDK external agents).

    **Validates: Requirements 9.1, 9.3, 9.4, 9.8, 1.5, 1.6**

    External agents may return raw JSON dicts instead of SDK model objects.
    The function must extract text using both 'kind' and 'type' discriminators.
    """
    result = _text_of_parts(parts)
    assert isinstance(result, str)

    # If any part is a dict with kind/type == "text" and has non-empty text,
    # the result should contain that text
    for part in parts:
        if isinstance(part, dict):
            kind = part.get("kind") or part.get("type", "")
            if kind == "text" and part.get("text"):
                assert part["text"] in result


@given(
    text_content=st.text(min_size=1, max_size=200),
    use_kind=st.booleans(),
)
@settings(max_examples=100)
def test_text_of_parts_extracts_text_from_valid_dicts(text_content, use_kind):
    """When a raw dict part has kind/type='text' and non-empty text, it is extracted.

    **Validates: Requirements 9.1, 9.3, 9.4, 9.8, 1.5, 1.6**
    """
    discriminator = "kind" if use_kind else "type"
    part = {discriminator: "text", "text": text_content}
    result = _text_of_parts([part])
    assert text_content in result


@given(task=arbitrary_task())
@settings(max_examples=200)
def test_text_of_task_returns_string_for_hybrid_formats(task):
    """_text_of_task handles hybrid Task formats (mixed artifacts and status).

    **Validates: Requirements 9.1, 9.3, 9.4, 9.8, 1.5, 1.6**

    External CS agents may return Tasks with varying combinations of
    artifacts, status.message, or both. The extraction must handle all.
    """
    result = _text_of_task(task)
    assert isinstance(result, str)
    # Result is either empty or contains extracted text — never crashes
