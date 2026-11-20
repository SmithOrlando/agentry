"""LLM provider clients behind one interface.

Every client implements:
    chat(messages, model, temperature, max_tokens) -> LLMResult
    list_models() -> list[str]

`messages` is a list of {"role": "system"|"user"|"assistant", "content": str}.
To add a provider: write a class here, register it in PROVIDERS, add it to the
CHECK constraint on provider_keys.provider (new migration) and to the UI list.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import requests


class LLMError(Exception):
    """Raised for any provider failure (network, auth, quota, bad response)."""


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    raw: dict = field(default_factory=dict, repr=False)


def _post(url, *, headers, json, timeout):
    try:
        resp = requests.post(url, headers=headers, json=json, timeout=timeout)
    except requests.RequestException as exc:
        raise LLMError(f"network error: {exc.__class__.__name__}") from exc
    if resp.status_code >= 400:
        # Never include request headers (they hold the key) in the error.
        raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    try:
        return resp.json()
    except ValueError as exc:
        raise LLMError("provider returned non-JSON") from exc


def _get(url, *, headers, timeout, params=None):
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=timeout)
    except requests.RequestException as exc:
        raise LLMError(f"network error: {exc.__class__.__name__}") from exc
    if resp.status_code >= 400:
        raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    return resp.json()


class OpenAICompatible:
    """OpenAI Chat Completions shape. Also used for DeepSeek, Qwen and any
    OpenAI-compatible endpoint (Azure via proxy, OpenRouter, Ollama, vLLM)."""

    DEFAULT_BASE = {
        "openai": "https://api.openai.com/v1",
        "deepseek": "https://api.deepseek.com/v1",
        "qwen": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "openai_compatible": "",
    }

    def __init__(self, provider: str, api_key: str, base_url: str = "", timeout: int = 60):
        self.provider = provider
        self.api_key = api_key
        self.base_url = (base_url or self.DEFAULT_BASE.get(provider, "")).rstrip("/")
        if not self.base_url:
            raise LLMError("base URL is required for an OpenAI-compatible provider")
        self.timeout = timeout

    def _headers(self):
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def chat(self, messages, model, temperature=0.4, max_tokens=500) -> LLMResult:
        data = _post(f"{self.base_url}/chat/completions", headers=self._headers(), timeout=self.timeout,
                     json={"model": model, "messages": messages, "temperature": temperature,
                           "max_tokens": max_tokens})
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("unexpected response shape") from exc
        usage = data.get("usage") or {}
        return LLMResult(text.strip(), self.provider, model, usage.get("prompt_tokens", 0),
                         usage.get("completion_tokens", 0), data)

    def list_models(self) -> list[str]:
        data = _get(f"{self.base_url}/models", headers=self._headers(), timeout=self.timeout)
        return sorted(m["id"] for m in data.get("data", []) if "id" in m)


class Anthropic:
    BASE = "https://api.anthropic.com/v1"
    VERSION = "2023-06-01"

    def __init__(self, api_key: str, base_url: str = "", timeout: int = 60):
        self.provider = "anthropic"
        self.api_key = api_key
        self.base_url = (base_url or self.BASE).rstrip("/")
        self.timeout = timeout

    def _headers(self):
        return {"x-api-key": self.api_key, "anthropic-version": self.VERSION,
                "content-type": "application/json"}

    def chat(self, messages, model, temperature=0.4, max_tokens=500) -> LLMResult:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        turns = [m for m in messages if m["role"] != "system"]
        body = {"model": model, "max_tokens": max_tokens, "temperature": temperature, "messages": turns}
        if system:
            body["system"] = system
        data = _post(f"{self.base_url}/messages", headers=self._headers(), json=body, timeout=self.timeout)
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        usage = data.get("usage") or {}
        return LLMResult(text.strip(), "anthropic", model, usage.get("input_tokens", 0),
                         usage.get("output_tokens", 0), data)

    def list_models(self) -> list[str]:
        data = _get(f"{self.base_url}/models", headers=self._headers(), timeout=self.timeout)
        return sorted(m["id"] for m in data.get("data", []) if "id" in m)


class Gemini:
    BASE = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, api_key: str, base_url: str = "", timeout: int = 60):
        self.provider = "gemini"
        self.api_key = api_key
        self.base_url = (base_url or self.BASE).rstrip("/")
        self.timeout = timeout

    def _headers(self):
        return {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}

    def chat(self, messages, model, temperature=0.4, max_tokens=500) -> LLMResult:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        contents = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
                    for m in messages if m["role"] != "system"]
        body = {"contents": contents,
                "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        data = _post(f"{self.base_url}/models/{model}:generateContent", headers=self._headers(),
                     json=body, timeout=self.timeout)
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("no candidates returned (blocked or empty)") from exc
        usage = data.get("usageMetadata") or {}
        return LLMResult("".join(p.get("text", "") for p in parts).strip(), "gemini", model,
                         usage.get("promptTokenCount", 0), usage.get("candidatesTokenCount", 0), data)

    def list_models(self) -> list[str]:
        data = _get(f"{self.base_url}/models", headers=self._headers(), timeout=self.timeout)
        return sorted(m["name"].split("/", 1)[-1] for m in data.get("models", [])
                      if "generateContent" in m.get("supportedGenerationMethods", []))


class Mock:
    """Offline provider for development and tests. Answers from the context it
    was given so retrieval and routing can be exercised without any API key."""

    def __init__(self, *_, **__):
        self.provider = "mock"

    def chat(self, messages, model="mock-1", temperature=0.0, max_tokens=500) -> LLMResult:
        user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        if "[[FAIL]]" in user:
            raise LLMError("mock failure requested")
        excerpt = ""
        m = re.search(r"<source[^>]*>\s*(.+?)\s*</source>", system, re.S)
        if m:
            excerpt = " ".join(m.group(1).split())[:220]
        reply = f"(mock) {excerpt}" if excerpt else f"(mock) You said: {user[:200]}"
        return LLMResult(reply, "mock", model, len(system + user) // 4, len(reply) // 4)

    def list_models(self) -> list[str]:
        return ["mock-1"]


PROVIDERS = ["openai", "anthropic", "gemini", "deepseek", "qwen", "openai_compatible"]
PROVIDER_LABELS = {"openai": "OpenAI", "anthropic": "Anthropic", "gemini": "Google Gemini",
                   "deepseek": "DeepSeek", "qwen": "Qwen", "openai_compatible": "OpenAI-compatible"}


def make_client(provider: str, api_key: str, base_url: str = "", timeout: int = 60):
    if provider == "mock":
        return Mock()
    if provider == "anthropic":
        return Anthropic(api_key, base_url, timeout)
    if provider == "gemini":
        return Gemini(api_key, base_url, timeout)
    if provider in OpenAICompatible.DEFAULT_BASE:
        return OpenAICompatible(provider, api_key, base_url, timeout)
    raise LLMError(f"unknown provider {provider!r}")
