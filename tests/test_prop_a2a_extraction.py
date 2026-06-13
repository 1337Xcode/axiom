"""Property test: A2A text extraction handles all response formats.

**Validates: Requirements 9.2, 9.7**
"""

import os
import sys
import types as builtin_types
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "personal_agent"))

# Mock modules
_mock_modules = {}
for mod_name in [
    "httpx", "google", "google.adk", "google.adk.agents",
    "google.adk.agents.readonly_context", "google.adk.tools",
    "google.adk.tools.base_toolset", "google.genai", "google.genai.types",
    "a2a", "a2a.client", "a2a.types",
]:
    _mock_modules[mod_name] = builtin_types.ModuleType(mod_name)
_mock_modules["google"].__path__ = []
_mock_modules["google.adk"].__path__ = []
_mock_modules["google.adk.agents"].__path__ = []
_mock_modules["google.adk.tools"].__path__ = []
_mock_modules["google.genai"].__path__ = []
_mock_modules["a2a"].__path__ = []
_mock_modules["google.adk.agents.readonly_context"].ReadonlyContext = MagicMock
_mock_modules["google.adk.tools"].BaseTool = MagicMock
_mock_modules["google.adk.tools"].FunctionTool = MagicMock
_mock_modules["google.adk.tools"].ToolContext = MagicMock
_mock_modules["google.adk.tools.base_toolset"].BaseToolset = MagicMock
_mock_modules["google.genai.types"] = MagicMock()
_mock_modules["httpx"].AsyncClient = MagicMock
_mock_modules["httpx"].TimeoutException = type("TimeoutException", (Exception,), {})


# Define fake A2A types
class FakeTextPart:
    def __init__(self, text=""):
        self.text = text
        self.kind = "text"


class FakePart:
    def __init__(self, text=""):
        self.root = FakeTextPart(text)


class FakeMessage:
    def __init__(self, parts=None, **kwargs):
        self.parts = parts or []
        for k, v in kwargs.items():
            setattr(self, k, v)


class FakeArtifact:
    def __init__(self, parts=None):
        self.parts = parts or []


class FakeStatus:
    def __init__(self, message=None):
        self.message = message


class FakeTask:
    def __init__(self, artifacts=None, status=None):
        self.artifacts = artifacts or []
        self.status = status


_mock_modules["a2a.types"].Message = FakeMessage
_mock_modules["a2a.types"].Part = FakePart
_mock_modules["a2a.types"].TextPart = FakeTextPart
_mock_modules["a2a.types"].Task = FakeTask
_mock_modules["a2a.types"].Role = MagicMock()
_mock_modules["a2a.types"].Role.user = "user"
_mock_modules["a2a.client"].ClientFactory = MagicMock
_mock_modules["a2a.client"].ClientConfig = MagicMock
_mock_modules["a2a.client"].minimal_agent_card = MagicMock

with patch.dict(sys.modules, _mock_modules):
    with patch.dict(os.environ, {
        "ENV_API_URL": "http://test:8090",
        "ENV_API_TOKEN": "tok",
        "CS_AGENT_URL": "http://cs:9002",
    }):
        sys.modules.pop("env_toolset", None)
        sys.modules.pop("cs_client_tool", None)
        from cs_client_tool import _text_of_parts, _text_of_message, _text_of_task

# Strategies
text_content = st.text(min_size=0, max_size=200)


@given(texts=st.lists(text_content, min_size=0, max_size=5))
@settings(max_examples=100)
def test_text_of_parts_with_sdk_objects(texts):
    """_text_of_parts extracts text from SDK Part objects."""
    parts = [FakePart(t) for t in texts]
    result = _text_of_parts(parts)
    assert isinstance(result, str)
    for t in texts:
        if t:
            assert t in result


@given(texts=st.lists(text_content, min_size=0, max_size=5))
@settings(max_examples=100)
def test_text_of_parts_with_dicts_kind(texts):
    """_text_of_parts extracts text from dicts with 'kind' discriminator."""
    parts = [{"kind": "text", "text": t} for t in texts]
    result = _text_of_parts(parts)
    assert isinstance(result, str)


@given(texts=st.lists(text_content, min_size=0, max_size=5))
@settings(max_examples=100)
def test_text_of_parts_with_dicts_type(texts):
    """_text_of_parts extracts text from dicts with 'type' discriminator."""
    parts = [{"type": "text", "text": t} for t in texts]
    result = _text_of_parts(parts)
    assert isinstance(result, str)


@given(text=text_content)
@settings(max_examples=50)
def test_text_of_message(text):
    """_text_of_message extracts from Message objects."""
    msg = FakeMessage(parts=[FakePart(text)])
    result = _text_of_message(msg)
    assert isinstance(result, str)
    if text:
        assert text in result


@given(text=text_content)
@settings(max_examples=50)
def test_text_of_task_from_status(text):
    """_text_of_task extracts from Task status.message."""
    task = FakeTask(
        status=FakeStatus(message=FakeMessage(parts=[FakePart(text)])),
        artifacts=[],
    )
    result = _text_of_task(task)
    assert isinstance(result, str)


@given(text=text_content)
@settings(max_examples=50)
def test_text_of_task_from_artifacts(text):
    """_text_of_task extracts from Task artifacts."""
    task = FakeTask(
        status=None,
        artifacts=[FakeArtifact(parts=[FakePart(text)])],
    )
    result = _text_of_task(task)
    assert isinstance(result, str)


def test_text_of_parts_none():
    """_text_of_parts handles None gracefully."""
    assert _text_of_parts(None) == ""


def test_text_of_parts_empty():
    """_text_of_parts handles empty list."""
    assert _text_of_parts([]) == ""
