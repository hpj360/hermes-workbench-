"""LLM provider abstraction for the Workbench agent runtime.

A thin, dependency-free client for OpenAI-compatible Chat Completions APIs.
Uses only :mod:`urllib` so the project keeps its zero-external-dependency
constraint (pydantic / pydantic-settings / python-dotenv only).

Supported providers (all expose ``/chat/completions``):
    * zai/glm  — Zhipu AI (https://open.bigmodel.cn/api/paas/v4)
    * ollama   — local (http://localhost:11434/v1), no API key required
    * openai   — official or compatible
    * openrouter, moonshot, modelscope, novita — OpenAI-compatible

Public surface:
    * :class:`LlmMessage`  — role/content message
    * :class:`LlmResponse` — normalized response
    * :class:`LlmClient`   — chat() / chat_json() methods
    * :func:`make_llm_client` — factory wired to Settings
    * :func:`resolve_provider` — map provider name → (base_url, api_key)

Error hierarchy:
    LlmError
    ├── LlmConfigError  — missing credentials / unknown provider
    └── LlmApiError     — HTTP failure or non-OK JSON payload
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from hermes.config import Settings, get_settings

__all__ = [
    "LlmApiError",
    "LlmClient",
    "LlmConfigError",
    "LlmError",
    "LlmMessage",
    "LlmResponse",
    "make_llm_client",
    "resolve_provider",
]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class LlmError(Exception):
    """Base error for the LLM layer."""


class LlmConfigError(LlmError):
    """Raised when a provider cannot be used (missing key/unknown name)."""


class LlmApiError(LlmError):
    """Raised when the provider HTTP call fails or returns a non-OK payload."""

    def __init__(self, message: str, status_code: int = -1) -> None:
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class LlmMessage:
    """A single chat message."""

    role: str  # "system" | "user" | "assistant"
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class LlmResponse:
    """Normalized LLM response."""

    content: str
    model: str = ""
    finish_reason: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Provider resolution
# ---------------------------------------------------------------------------


def resolve_provider(
    name: str, settings: Settings | None = None
) -> tuple[str, str | None]:
    """Map a provider name to ``(base_url, api_key)``.

    For local providers (e.g. ``ollama``) the api_key may be ``None``.

    Raises :class:`LlmConfigError` when the provider is unknown or a remote
    provider has no API key configured.
    """
    s = settings or get_settings()
    name = (name or "").strip().lower()

    # (settings_attr_base_url, settings_attr_api_key)
    table: dict[str, tuple[str, str | None]] = {
        "ollama": ("ollama_base_url", None),
        "openai": ("openai_base_url", "openai_api_key"),
        "openrouter": ("openrouter_base_url", "openrouter_api_key"),
        "moonshot": ("moonshot_base_url", "moonshot_api_key"),
        "modelscope": ("modelscope_base_url", "modelscope_api_key"),
        "novita": ("novita_base_url", "novita_api_key"),
        "zai/glm": ("zai_base_url", "zai_api_key"),
        "zai": ("zai_base_url", "zai_api_key"),
        "glm": ("zai_base_url", "zai_api_key"),
    }
    if name not in table:
        raise LlmConfigError(f"unknown LLM provider: {name!r}")
    base_attr, key_attr = table[name]
    base_url = getattr(s, base_attr)
    api_key = getattr(s, key_attr) if key_attr else None
    if key_attr and not api_key:
        raise LlmConfigError(
            f"provider {name!r} requires an API key (env var not set)"
        )
    return base_url, api_key


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class LlmClient:
    """OpenAI-compatible Chat Completions client (stdlib only)."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        model: str,
        timeout: float = 60.0,
        temperature: float = 0.2,
    ) -> None:
        # Normalize: ensure base_url has no trailing slash so we can append
        # the path safely.
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.temperature = temperature

    # ---- public API ---------------------------------------------------

    def chat(
        self,
        messages: list[LlmMessage],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> LlmResponse:
        """Call ``POST {base_url}/chat/completions`` and return the response.

        Raises :class:`LlmApiError` on HTTP failure or malformed payload.
        """
        url = f"{self.base_url}/chat/completions"
        body: dict[str, Any] = {
            "model": model or self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": self.temperature if temperature is None else temperature,
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json; charset=utf-8")
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")

        try:
            with urllib.request.urlopen(
                req, timeout=timeout if timeout is not None else self.timeout
            ) as resp:
                raw_bytes = resp.read()
        except urllib.error.HTTPError as e:
            text = ""
            try:
                text = e.read().decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass
            raise LlmApiError(
                f"LLM HTTP {e.code}: {text or e.reason}", status_code=e.code
            ) from e
        except urllib.error.URLError as e:
            raise LlmApiError(f"LLM network error: {e.reason}") from e

        try:
            data = json.loads(raw_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise LlmApiError(f"LLM returned non-JSON body: {e}") from e

        return self._parse_response(data)

    def chat_json(
        self,
        messages: list[LlmMessage],
        *,
        model: str | None = None,
        temperature: float | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Like :meth:`chat` but parses the assistant content as JSON.

        Injects a ``"respond with valid JSON only"`` instruction and falls
        back to extracting the first ``{...}`` or ``[...]`` block when the
        model wraps JSON in prose / markdown fences.
        """
        instr = LlmMessage(
            role="system",
            content="You MUST respond with valid JSON only. No prose, no markdown fences.",
        )
        response = self.chat(
            [instr, *messages],
            model=model,
            temperature=temperature,
            timeout=timeout,
        )
        return _extract_json(response.content)

    # ---- internals -----------------------------------------------------

    def _parse_response(self, data: dict[str, Any]) -> LlmResponse:
        """Extract the assistant message from an OpenAI-style response."""
        try:
            choices = data.get("choices") or []
            if not choices:
                raise LlmApiError(f"LLM response has no choices: {data}")
            first = choices[0]
            msg = first.get("message") or {}
            content = msg.get("content") or ""
            finish = first.get("finish_reason", "")
        except (KeyError, TypeError, IndexError) as e:
            raise LlmApiError(f"malformed LLM response: {e}: {data}") from e
        return LlmResponse(
            content=content,
            model=data.get("model", ""),
            finish_reason=finish,
            raw=data,
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def make_llm_client(
    provider: str | None = None,
    model: str | None = None,
    settings: Settings | None = None,
) -> LlmClient:
    """Build an :class:`LlmClient` from Settings.

    When *provider* or *model* are None, fall back to
    ``Settings.hermes_llm_provider`` / ``Settings.hermes_llm_model``.

    Raises :class:`LlmConfigError` when the provider is unconfigured.
    """
    s = settings or get_settings()
    provider = (provider or s.hermes_llm_provider).strip()
    model = model or s.hermes_llm_model
    base_url, api_key = resolve_provider(provider, settings=s)
    return LlmClient(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout=s.hermes_llm_timeout,
        temperature=s.hermes_llm_temperature,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_json(text: str) -> dict[str, Any]:
    """Best-effort parse of JSON from an LLM response.

    Handles three cases in order:
      1. Whole text is valid JSON.
      2. ```json ... ``` fenced block.
      3. First ``{...}`` substring.
    """
    text = text.strip()
    # Case 1: direct parse
    try:
        v = json.loads(text)
        return v if isinstance(v, dict) else {"value": v}
    except json.JSONDecodeError:
        pass
    # Case 2: strip markdown fences
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        inner = "\n".join(lines).strip()
        try:
            v = json.loads(inner)
            return v if isinstance(v, dict) else {"value": v}
        except json.JSONDecodeError:
            pass
    # Case 3: first {...} block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        fragment = text[start : end + 1]
        try:
            v = json.loads(fragment)
            return v if isinstance(v, dict) else {"value": v}
        except json.JSONDecodeError:
            pass
    raise LlmApiError(f"could not extract JSON from LLM response: {text[:200]!r}")
