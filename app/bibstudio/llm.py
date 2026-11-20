"""LLM providers over plain HTTP.

No vendor SDKs: one httpx call per provider keeps the dependency surface tiny,
makes packaging a single binary realistic, and means a provider outage surfaces as
a clean error instead of an SDK version conflict.

Supported: mock (offline, deterministic), openai-compatible (OpenAI, DeepSeek,
OpenRouter, Ollama/LM Studio, any custom base URL), anthropic.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

# USD per 1M tokens (input, output). Estimates, editable in Settings later.
MODEL_PRICES: dict[str, tuple[float, float]] = {
    "mock-1": (0.0, 0.0),
    "deepseek-chat": (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19),
    "deepseek-flash": (0.14, 0.28),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "gemini-1.5-flash": (0.075, 0.30),
    "llama3.1": (0.0, 0.0),
}

PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "mock": {"label": "Offline demo (no key)", "base_url": "", "default_model": "mock-1"},
    "deepseek": {"label": "DeepSeek", "base_url": "https://api.deepseek.com", "default_model": "deepseek-chat"},
    "openai": {"label": "OpenAI", "base_url": "https://api.openai.com/v1", "default_model": "gpt-4o-mini"},
    "openrouter": {"label": "OpenRouter", "base_url": "https://openrouter.ai/api/v1", "default_model": "openai/gpt-4o-mini"},
    "ollama": {"label": "Ollama / LM Studio (local)", "base_url": "http://localhost:11434/v1", "default_model": "llama3.1"},
    "anthropic": {"label": "Anthropic", "base_url": "https://api.anthropic.com", "default_model": "claude-sonnet-4-5"},
}


class LLMError(RuntimeError):
    pass


@dataclass
class LLMResult:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    provider: str = ""
    model: str = ""


@dataclass
class LLMClient:
    provider: str = "mock"
    model: str = "mock-1"
    api_key: str | None = None
    base_url: str = ""
    temperature: float = 0.2
    max_tokens: int = 2000
    timeout: float = 120.0
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    _log: list[dict[str, Any]] = field(default_factory=list)

    # -- public -------------------------------------------------------------

    def complete(self, system: str, user: str, *, temperature: float | None = None,
                 max_tokens: int | None = None) -> LLMResult:
        temp = self.temperature if temperature is None else temperature
        budget = self.max_tokens if max_tokens is None else max_tokens
        text, tin, tout = self._dispatch(system, user, temp, budget)
        tin = tin or max(1, (len(system) + len(user)) // 4)
        tout = tout or max(1, len(text) // 4)
        price_in, price_out = MODEL_PRICES.get(self.model, (0.0, 0.0))
        cost = (tin * price_in + tout * price_out) / 1_000_000
        self.calls += 1
        self.tokens_in += tin
        self.tokens_out += tout
        self.cost_usd += cost
        result = LLMResult(text=text, tokens_in=tin, tokens_out=tout, cost_usd=cost,
                           provider=self.provider, model=self.model)
        self._log.append({"system": system[:400], "user": user[:400], "text": text[:400]})
        return result

    def complete_json(self, system: str, user: str, **kwargs) -> tuple[Any, LLMResult]:
        res = self.complete(system, user, **kwargs)
        data = extract_json(res.text)
        if data is None:
            raise LLMError(f"model did not return parseable JSON: {res.text[:300]!r}")
        return data, res

    # -- dispatch -----------------------------------------------------------

    def _dispatch(self, system: str, user: str, temperature: float,
                  max_tokens: int) -> tuple[str, int, int]:
        provider = (self.provider or "mock").lower()
        if provider == "mock":
            return self._mock(system, user), 0, 0
        if provider == "anthropic":
            return self._anthropic(system, user, temperature, max_tokens)
        if provider in {"openai", "deepseek", "openrouter", "ollama", "custom"}:
            return self._openai_compatible(system, user, temperature, max_tokens)
        raise LLMError(f"unknown provider: {self.provider}")

    def _openai_compatible(self, system: str, user: str, temperature: float,
                           max_tokens: int) -> tuple[str, int, int]:
        base = self._base_url()
        if not self.api_key and (self.provider or "").lower() not in {"ollama", "custom"}:
            raise LLMError("no API key configured for this provider")
        payload = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        data = self._post(f"{base}/chat/completions", payload, headers)
        try:
            choice = data["choices"][0]
            text = choice["message"].get("content") or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"unexpected response shape: {str(data)[:200]}") from exc
        usage = data.get("usage") or {}
        return text, int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)

    def _anthropic(self, system: str, user: str, temperature: float,
                   max_tokens: int) -> tuple[str, int, int]:
        if not self.api_key:
            raise LLMError("no API key configured for Anthropic")
        base = self.base_url or "https://api.anthropic.com"
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        data = self._post(f"{base}/v1/messages", payload, headers)
        blocks = data.get("content") or []
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        usage = data.get("usage") or {}
        return text, int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0)

    def _post(self, url: str, payload: dict, headers: dict) -> dict:
        last: Exception | None = None
        for attempt in range(3):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(url, json=payload, headers=headers)
                if resp.status_code == 429 or resp.status_code >= 500:
                    last = LLMError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                    time.sleep(1.5 * (attempt + 1))
                    continue
                if resp.status_code >= 400:
                    raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                return resp.json()
            except httpx.ConnectError as exc:
                raise LLMError(
                    f"could not connect to {url}. For a local model, make sure the "
                    f"server is running (e.g. `ollama serve`) and the base URL is right. "
                    f"[{exc}]") from exc
            except httpx.TimeoutException as exc:
                last = exc
                time.sleep(1.0)
            except httpx.HTTPError as exc:
                last = exc
                time.sleep(1.0)
        raise LLMError(f"request failed after retries: {last}")

    def _base_url(self) -> str:
        if self.base_url:
            return self.base_url.rstrip("/")
        preset = PROVIDER_PRESETS.get((self.provider or "").lower(), {})
        base = preset.get("base_url", "")
        if not base:
            raise LLMError("no base_url configured")
        return base.rstrip("/")

    # -- offline mock -------------------------------------------------------

    def _mock(self, system: str, user: str) -> str:
        """Deterministic, schema-correct stub so the pipeline runs with no key."""
        low = system.lower()
        if "search queries" in low or "query planning" in low:
            seed = re.sub(r"\s+", " ", user)[:80]
            return json.dumps({"queries": [
                {"query": f"mock query {i}: {seed}", "theme": "general"} for i in range(1, 3)
            ]})
        if "findings" in low and "critic" in low:
            return json.dumps({
                "findings": [{
                    "severity": "info",
                    "target": "author",
                    "location": "(whole document)",
                    "issue": "Offline demo review: no model was called, so this is a stub.",
                    "suggestion": "Connect a provider in Settings to get a real review.",
                }],
                "summary": "Offline mock review produced one informational finding.",
            })
        heading = _extract_section_heading(user) or "Section"
        pairs = re.findall(r"\[(P-\d{4})(?:\s+p\.(\d+))?\]", user)
        ids = [f"{pid} p.{page}" if page else pid for pid, page in pairs]
        # de-duplicate, keep the first three distinct sources
        seen: list[str] = []
        for cid in ids:
            if cid.split()[0] not in [s.split()[0] for s in seen]:
                seen.append(cid)
        ids = seen[:3]
        if ids:
            body = (
                f"The literature reviewed for this section converges on a small number "
                f"of measurable mechanisms [{ids[0]}]. "
                + (f"A contrasting position holds that the effect is mediated by context "
                   f"rather than by the mechanism itself [{ids[1]}]. " if len(ids) > 1 else "")
                + (f"Methodologically, comparability across studies remains the limiting "
                   f"factor [{ids[2]}]. " if len(ids) > 2 else "")
                + "\n\nThis paragraph is generated by the offline mock provider; connect a "
                  "real model in Settings to produce a substantive draft."
            )
        else:
            body = ("The available evidence for this section is thin. No registered source "
                    "supports a substantive claim here.")
        return f"## {heading}\n\n{body}"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _extract_section_heading(user: str) -> str | None:
    m = re.search(r"SECTION:\s*(.+)", user)
    return m.group(1).strip() if m else None


def extract_json(raw: str) -> Any | None:
    """Recover a JSON object from model output that may include prose or fences."""
    text = (raw or "").strip()
    if not text:
        return None
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            candidate = text[start:end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                # common failure: trailing commas
                repaired = re.sub(r",\s*([}\]])", r"\1", candidate)
                try:
                    return json.loads(repaired)
                except json.JSONDecodeError:
                    continue
    return None


def client_from_settings(settings: dict, api_key: str | None,
                         openalex_key: str | None = None) -> LLMClient:
    provider = (settings.get("provider") or "mock").lower()
    preset = PROVIDER_PRESETS.get(provider, {})
    timeout = float(settings.get("timeout_seconds") or 180)
    return LLMClient(
        provider=provider,
        model=settings.get("model") or preset.get("default_model", "mock-1"),
        api_key=api_key,
        base_url=settings.get("base_url") or preset.get("base_url", ""),
        temperature=float(settings.get("temperature") or 0.2),
        max_tokens=int(settings.get("max_output_tokens") or 2000),
        timeout=timeout,
    )


def estimate_cost(tokens_in: int, tokens_out: int, model: str) -> float:
    price_in, price_out = MODEL_PRICES.get(model, (0.0, 0.0))
    return (tokens_in * price_in + tokens_out * price_out) / 1_000_000
