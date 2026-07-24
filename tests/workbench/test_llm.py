"""Tests for hermes.workbench.llm (LLM provider abstraction)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from hermes.config import Settings
from hermes.workbench.llm import (
    LlmApiError,
    LlmClient,
    LlmConfigError,
    LlmMessage,
    LlmResponse,
    _extract_json,
    make_llm_client,
    resolve_provider,
)


# ---------------------------------------------------------------------------
# Fake Settings
# ---------------------------------------------------------------------------


class _FakeSettings:
    """Minimal stand-in for Settings with only the fields resolve_provider reads."""

    def __init__(
        self,
        ollama_base_url: str = "http://localhost:11434/v1",
        openai_base_url: str | None = "https://api.openai.com/v1",
        openai_api_key: str | None = None,
        zai_base_url: str = "https://open.bigmodel.cn/api/paas/v4",
        zai_api_key: str | None = None,
        hermes_llm_provider: str = "ollama",
        hermes_llm_model: str = "gpt-3.5-turbo",
        hermes_llm_timeout: float = 30.0,
        hermes_llm_temperature: float = 0.1,
    ) -> None:
        self.ollama_base_url = ollama_base_url
        self.openai_base_url = openai_base_url
        self.openai_api_key = openai_api_key
        self.zai_base_url = zai_base_url
        self.zai_api_key = zai_api_key
        self.hermes_llm_provider = hermes_llm_provider
        self.hermes_llm_model = hermes_llm_model
        self.hermes_llm_timeout = hermes_llm_timeout
        self.hermes_llm_temperature = hermes_llm_temperature


# ---------------------------------------------------------------------------
# resolve_provider
# ---------------------------------------------------------------------------


def test_resolve_provider_ollama_no_key() -> None:
    """ollama should resolve without an API key (local)."""
    s = _FakeSettings()
    base, key = resolve_provider("ollama", settings=s)  # type: ignore[arg-type]
    assert base == "http://localhost:11434/v1"
    assert key is None


def test_resolve_provider_openai_requires_key() -> None:
    """openai should raise LlmConfigError when no API key is set."""
    s = _FakeSettings(openai_api_key=None)
    with pytest.raises(LlmConfigError):
        resolve_provider("openai", settings=s)  # type: ignore[arg-type]


def test_resolve_provider_openai_with_key() -> None:
    """openai should resolve base_url + key when configured."""
    s = _FakeSettings(openai_api_key="sk-xxx")
    base, key = resolve_provider("openai", settings=s)  # type: ignore[arg-type]
    assert key == "sk-xxx"
    assert "openai.com" in base


def test_resolve_provider_zai_aliases() -> None:
    """zai/glm, zai, glm should all map to the Zhipu provider."""
    s = _FakeSettings(zai_api_key="zai-key")
    for alias in ("zai/glm", "zai", "glm", "ZAI", "GLM"):
        _, key = resolve_provider(alias, settings=s)  # type: ignore[arg-type]
        assert key == "zai-key"


def test_resolve_provider_unknown() -> None:
    """unknown provider name should raise LlmConfigError."""
    s = _FakeSettings()
    with pytest.raises(LlmConfigError):
        resolve_provider("nope", settings=s)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# make_llm_client
# ---------------------------------------------------------------------------


def test_make_llm_client_uses_settings_defaults() -> None:
    """make_llm_client should honor Settings.hermes_llm_provider/model."""
    s = _FakeSettings(hermes_llm_provider="ollama", hermes_llm_model="llama3")
    client = make_llm_client(settings=s)  # type: ignore[arg-type]
    assert client.model == "llama3"
    assert client.api_key is None
    assert "localhost:11434" in client.base_url


def test_make_llm_client_override_provider() -> None:
    """explicit provider/model should override Settings defaults."""
    s = _FakeSettings(
        hermes_llm_provider="ollama",
        openai_api_key="sk-xxx",
        hermes_llm_model="default-model",
    )
    client = make_llm_client(provider="openai", model="gpt-4o", settings=s)  # type: ignore[arg-type]
    assert client.model == "gpt-4o"
    assert client.api_key == "sk-xxx"


# ---------------------------------------------------------------------------
# LlmClient.chat
# ---------------------------------------------------------------------------


def _mock_urlopen_response(data: dict[str, Any]) -> Any:
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(data).encode("utf-8")
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def test_llm_client_chat_parses_response() -> None:
    """chat should extract content from choices[0].message.content."""
    client = LlmClient(
        base_url="https://api.example.com/v1",
        api_key="sk-xxx",
        model="gpt-4o",
    )
    fake_data = {
        "model": "gpt-4o",
        "choices": [
            {
                "message": {"role": "assistant", "content": "Hello!"},
                "finish_reason": "stop",
            }
        ],
    }
    with patch("urllib.request.urlopen", return_value=_mock_urlopen_response(fake_data)):
        resp = client.chat([LlmMessage(role="user", content="hi")])
    assert isinstance(resp, LlmResponse)
    assert resp.content == "Hello!"
    assert resp.model == "gpt-4o"
    assert resp.finish_reason == "stop"


def test_llm_client_chat_sets_auth_header() -> None:
    """chat should send Authorization: Bearer <key> when api_key is set."""
    client = LlmClient(
        base_url="https://api.example.com/v1",
        api_key="sk-secret",
        model="gpt-4o",
    )
    captured: dict[str, Any] = {}

    class FakeRequest:
        def __init__(self, url: str, data: bytes, method: str) -> None:
            captured["url"] = url
            captured["method"] = method
            captured["data"] = data
            self._headers: dict[str, str] = {}

        def add_header(self, k: str, v: str) -> None:
            captured.setdefault("headers", {})[k] = v

    fake_data = {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}
    with patch("urllib.request.Request", FakeRequest):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen_response(fake_data)):
            client.chat([LlmMessage(role="user", content="hi")])
    assert captured["headers"]["Authorization"] == "Bearer sk-secret"
    assert captured["headers"]["Content-Type"].startswith("application/json")
    assert captured["url"].endswith("/chat/completions")
    assert captured["method"] == "POST"


def test_llm_client_chat_omits_auth_when_no_key() -> None:
    """chat should not send Authorization header when api_key is None (ollama)."""
    client = LlmClient(
        base_url="http://localhost:11434/v1", api_key=None, model="llama3"
    )
    captured: dict[str, Any] = {}

    class FakeRequest:
        def __init__(self, url: str, data: bytes, method: str) -> None:
            captured["url"] = url
            self._headers: dict[str, str] = {}

        def add_header(self, k: str, v: str) -> None:
            captured.setdefault("headers", {})[k] = v

    fake_data = {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}
    with patch("urllib.request.Request", FakeRequest):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen_response(fake_data)):
            client.chat([LlmMessage(role="user", content="hi")])
    assert "Authorization" not in captured.get("headers", {})


def test_llm_client_chat_http_error_raises_api_error() -> None:
    """chat should raise LlmApiError on HTTP failure."""
    import urllib.error
    client = LlmClient(base_url="https://api.example.com/v1", api_key="k", model="m")
    err = urllib.error.HTTPError(
        url="https://api.example.com/v1/chat/completions",
        code=429,
        msg="Too Many Requests",
        hdrs=None,
        fp=None,
    )
    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(LlmApiError) as exc_info:
            client.chat([LlmMessage(role="user", content="hi")])
    assert exc_info.value.status_code == 429


def test_llm_client_chat_no_choices_raises() -> None:
    """chat should raise LlmApiError when response has no choices."""
    client = LlmClient(base_url="https://api.example.com/v1", api_key="k", model="m")
    with patch("urllib.request.urlopen", return_value=_mock_urlopen_response({"foo": "bar"})):
        with pytest.raises(LlmApiError):
            client.chat([LlmMessage(role="user", content="hi")])


# ---------------------------------------------------------------------------
# LlmClient.chat_json
# ---------------------------------------------------------------------------


def test_llm_client_chat_json_parses_json_content() -> None:
    """chat_json should parse JSON from the assistant content."""
    client = LlmClient(base_url="https://api.example.com/v1", api_key="k", model="m")
    fake_data = {
        "choices": [
            {"message": {"content": '{"plan": [{"skill": "deploy"}]}'}, "finish_reason": "stop"}
        ]
    }
    with patch("urllib.request.urlopen", return_value=_mock_urlopen_response(fake_data)):
        result = client.chat_json([LlmMessage(role="user", content="plan")])
    assert result == {"plan": [{"skill": "deploy"}]}


def test_llm_client_chat_json_extracts_from_fenced_block() -> None:
    """chat_json should handle ```json fenced responses."""
    client = LlmClient(base_url="https://api.example.com/v1", api_key="k", model="m")
    fenced = "```json\n{\"achieved\": true}\n```"
    fake_data = {
        "choices": [{"message": {"content": fenced}, "finish_reason": "stop"}]
    }
    with patch("urllib.request.urlopen", return_value=_mock_urlopen_response(fake_data)):
        result = client.chat_json([LlmMessage(role="user", content="judge")])
    assert result == {"achieved": True}


def test_llm_client_chat_json_extracts_from_prose() -> None:
    """chat_json should extract {...} from prose responses."""
    client = LlmClient(base_url="https://api.example.com/v1", api_key="k", model="m")
    prose = 'Here is the plan: {"steps": [{"skill": "test"}]} hope it helps.'
    fake_data = {
        "choices": [{"message": {"content": prose}, "finish_reason": "stop"}]
    }
    with patch("urllib.request.urlopen", return_value=_mock_urlopen_response(fake_data)):
        result = client.chat_json([LlmMessage(role="user", content="plan")])
    assert result == {"steps": [{"skill": "test"}]}


def test_llm_client_chat_json_unparseable_raises() -> None:
    """chat_json should raise LlmApiError when content has no JSON."""
    client = LlmClient(base_url="https://api.example.com/v1", api_key="k", model="m")
    fake_data = {
        "choices": [{"message": {"content": "no json here at all"}, "finish_reason": "stop"}]
    }
    with patch("urllib.request.urlopen", return_value=_mock_urlopen_response(fake_data)):
        with pytest.raises(LlmApiError):
            client.chat_json([LlmMessage(role="user", content="hi")])


# ---------------------------------------------------------------------------
# _extract_json helper
# ---------------------------------------------------------------------------


def test_extract_json_direct_object() -> None:
    assert _extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_direct_array_wraps() -> None:
    """a bare JSON array should be wrapped as {"value": [...]}."""
    result = _extract_json('[1, 2, 3]')
    assert result == {"value": [1, 2, 3]}


def test_extract_json_fenced() -> None:
    text = "```json\n{\"x\": 2}\n```"
    assert _extract_json(text) == {"x": 2}


def test_extract_json_prose() -> None:
    text = 'result is {"y": 3} done'
    assert _extract_json(text) == {"y": 3}


def test_extract_json_invalid_raises() -> None:
    with pytest.raises(LlmApiError):
        _extract_json("no json at all")
