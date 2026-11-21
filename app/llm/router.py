"""Chooses which model answers, and falls back when it fails.

Resolution order for a reply:
  1. the agent's own model override (if set and its provider key exists)
  2. the workspace model (if llm_settings.source == "byok")
  3. the hidden platform default (always last; used first when source == "platform")
Step 3 is only tried after a failure when llm_settings.fallback is true.
The platform default's provider/model/key are never sent to the browser.
"""
from __future__ import annotations

import time

from dataclasses import dataclass

from flask import current_app

from ..db import jload, query_one, utcnow, update
from ..security import decrypt
from ..services.settings import get_section, record_usage
from .providers import LLMError, LLMResult, make_client


@dataclass
class Candidate:
    provider: str
    model: str
    client: object
    is_platform: bool


NO_MODEL = "No AI model is set up yet. An admin can add an API key in Settings › Models."


def _platform_candidate() -> Candidate | None:
    """The hidden platform default, or None when there is none (or it is the test-only placeholder)."""
    cfg = current_app.config
    if not cfg["PLATFORM_LLM_PROVIDER"]:
        return None
    if cfg["PLATFORM_LLM_PROVIDER"] == "mock" and not cfg.get("ENABLE_TEST_TOOLS"):
        return None
    client = make_client(cfg["PLATFORM_LLM_PROVIDER"], cfg["PLATFORM_LLM_API_KEY"],
                         cfg["PLATFORM_LLM_BASE_URL"], cfg["LLM_TIMEOUT_SECONDS"])
    return Candidate(cfg["PLATFORM_LLM_PROVIDER"], cfg["PLATFORM_LLM_MODEL"], client, True)


def _byok_candidate(workspace_id: int, provider: str, model: str) -> Candidate | None:
    if not provider or not model:
        return None
    row = query_one("SELECT api_key_enc, base_url FROM provider_keys WHERE workspace_id = ? AND provider = ?",
                    [workspace_id, provider])
    if not row:
        return None
    key = decrypt(row["api_key_enc"])
    if not key:
        return None
    client = make_client(provider, key, row["base_url"], current_app.config["LLM_TIMEOUT_SECONDS"])
    return Candidate(provider, model, client, False)


def candidates(workspace_id: int, agent: dict | None) -> list[Candidate]:
    llm = get_section(workspace_id, "llm_settings")
    out: list[Candidate] = []
    override = jload(agent.get("model_override")) if agent else None
    if override:
        c = _byok_candidate(workspace_id, override.get("provider"), override.get("model"))
        if c:
            out.append(c)
    if llm["source"] == "byok":
        c = _byok_candidate(workspace_id, llm["provider"], llm["model"])
        if c and not any(x.provider == c.provider and x.model == c.model for x in out):
            out.append(c)
        # Fall back to the platform default, but never to the placeholder model: a "(mock)" answer
        # after a real key fails would look like a working reply. Better to show the real error.
        platform = _platform_candidate()
        if platform and ((llm["fallback"] and platform.provider != "mock") or not out):
            out.append(platform)
    else:
        platform = _platform_candidate()
        if platform:
            out.append(platform)
    return out


# Suggested model when a workspace adds its first key (the Test button lists everything the key can use).
STARTER_MODEL = {"openai": "gpt-4o-mini", "anthropic": "claude-sonnet-4-5", "gemini": "gemini-2.5-flash",
                 "deepseek": "deepseek-chat", "qwen": "qwen-plus", "openai_compatible": ""}


def model_ready(workspace_id: int) -> bool:
    """False when replies would come from the built-in placeholder ("mock") model, i.e. no real AI is set up.
    Says nothing about which provider the hidden platform default uses."""
    found = candidates(workspace_id, None)
    return bool(found) and found[0].provider != "mock"


def generate(workspace_id: int, agent: dict | None, messages: list[dict]) -> LLMResult:
    """Try each candidate in order; raise LLMError only if all fail."""
    llm = get_section(workspace_id, "llm_settings")
    errors = []
    for cand in candidates(workspace_id, agent):
        try:
            result = cand.client.chat(messages, cand.model, float(llm["temperature"]), int(llm["max_tokens"]))
        except LLMError as exc:
            current_app.logger.warning("LLM %s/%s failed: %s", cand.provider, cand.model, exc)
            errors.append(f"{'platform' if cand.is_platform else cand.provider}: {exc}")
            continue
        kind = "platform_tokens" if cand.is_platform else "byok_tokens"
        record_usage(workspace_id, kind, result.input_tokens + result.output_tokens)
        if cand.is_platform:  # never leak which model the platform uses
            result.provider, result.model = "platform", "default"
        return result
    raise LLMError("; ".join(errors) or NO_MODEL)


def describe_active_model(workspace_id: int, agent: dict | None) -> str:
    """Human label for the UI. Never reveals the platform model."""
    found = candidates(workspace_id, agent)
    if not found:
        return "No model set up"
    c = found[0]
    return "Platform default" if c.is_platform else f"{c.provider} · {c.model}"


_MODEL_CACHE: dict = {}          # (workspace_id, provider) -> (time, [model ids])
MODEL_CACHE_SECONDS = 600


def list_models(workspace_id: int, provider: str, fresh: bool = False) -> list[str]:
    """Models the workspace's saved key can use (cached 10 minutes). Raises LLMError if there is no key
    or the provider refuses it."""
    key = (workspace_id, provider)
    hit = _MODEL_CACHE.get(key)
    if hit and not fresh and time.time() - hit[0] < MODEL_CACHE_SECONDS:
        return hit[1]
    row = query_one("SELECT api_key_enc, base_url FROM provider_keys WHERE workspace_id = ? AND provider = ?",
                    [workspace_id, provider])
    if not row:
        raise LLMError("no key saved for this provider")
    client = make_client(provider, decrypt(row["api_key_enc"]), row["base_url"], current_app.config["LLM_TIMEOUT_SECONDS"])
    models = client.list_models()
    _MODEL_CACHE[key] = (time.time(), models)
    return models


def forget_models(workspace_id: int, provider: str) -> None:
    _MODEL_CACHE.pop((workspace_id, provider), None)


def test_key(workspace_id: int, provider: str) -> dict:
    row = query_one("SELECT id, api_key_enc, base_url FROM provider_keys WHERE workspace_id = ? AND provider = ?",
                    [workspace_id, provider])
    if not row:
        raise LLMError("no key saved for this provider")
    client = make_client(provider, decrypt(row["api_key_enc"]), row["base_url"],
                         current_app.config["LLM_TIMEOUT_SECONDS"])
    models = client.list_models()
    _MODEL_CACHE[(workspace_id, provider)] = (time.time(), models)
    update("provider_keys", row["id"], {"verified_at": utcnow()})
    return {"ok": True, "models": models}
