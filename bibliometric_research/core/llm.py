"""Provider-agnostic LLM interface.

All agents talk to models through :class:`LLM`. Swap providers by changing
``provider`` in ``config.yaml`` and setting the matching env var — no agent
code changes.

Design goals:
  * One tiny interface: ``complete(system, user) -> str``.
  * Optional JSON helper with a robust fallback parse.
  * A ``mock`` provider so the whole pipeline runs offline for free.
  * Lazy imports: a provider SDK is only imported when it is actually used, so
    you only need to install the SDK for the provider you run.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class LLMError(RuntimeError):
    pass


@dataclass
class LLM:
    """Thin wrapper around a chat-completion API."""

    provider: str = "mock"
    model: str = "mock-1"
    max_output_tokens: int = 1500
    temperature: float = 0.2
    # Running token accounting (best-effort; providers don't always report).
    tokens_used: int = 0
    calls: int = 0
    _log: list[dict[str, Any]] = field(default_factory=list)

    # -- public API ---------------------------------------------------------

    def complete(self, system: str, user: str) -> str:
        """Return the model's text response for one turn."""
        text = self._dispatch(system, user)
        self.calls += 1
        # Rough accounting used for budget checks (≈4 chars/token).
        self.tokens_used += (len(system) + len(user) + len(text)) // 4
        self._log.append({"system": system, "user": user, "response": text})
        return text

    def complete_json(self, system: str, user: str) -> Any:
        """Call the model and parse a JSON object/array from its reply.

        Tolerates markdown fences and leading/trailing prose. Raises
        ``LLMError`` if no JSON can be recovered.
        """
        raw = self.complete(system, user)
        return self._extract_json(raw)

    # -- dispatch -----------------------------------------------------------

    def _dispatch(self, system: str, user: str) -> str:
        p = self.provider.lower()
        if p == "mock":
            return self._mock(system, user)
        if p == "anthropic":
            return self._anthropic(system, user)
        if p == "openai":
            return self._openai(system, user)
        if p == "deepseek":
            return self._openai(system, user, base_url="https://api.deepseek.com/v1",
                                key_env="DEEPSEEK_API_KEY")
        if p == "google":
            return self._google(system, user)
        raise LLMError(f"Unknown provider: {self.provider!r}")

    # -- provider adapters --------------------------------------------------

    def _anthropic(self, system: str, user: str) -> str:
        try:
            import anthropic  # type: ignore
        except ImportError as e:  # pragma: no cover
            raise LLMError("pip install anthropic") from e
        client = anthropic.Anthropic(api_key=_env("ANTHROPIC_API_KEY"))
        resp = client.messages.create(
            model=self.model,
            max_tokens=self.max_output_tokens,
            temperature=self.temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in resp.content if block.type == "text")

    def _openai(self, system: str, user: str, base_url: str | None = None,
                key_env: str = "OPENAI_API_KEY") -> str:
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as e:  # pragma: no cover
            raise LLMError("pip install openai") from e
        kwargs: dict[str, Any] = {"api_key": _env(key_env)}
        if base_url:
            kwargs["base_url"] = base_url
        client = OpenAI(**kwargs)
        resp = client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_output_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""

    def _google(self, system: str, user: str) -> str:
        try:
            import google.generativeai as genai  # type: ignore
        except ImportError as e:  # pragma: no cover
            raise LLMError("pip install google-generativeai") from e
        genai.configure(api_key=_env("GOOGLE_API_KEY"))
        model = genai.GenerativeModel(self.model, system_instruction=system)
        resp = model.generate_content(
            user,
            generation_config={
                "max_output_tokens": self.max_output_tokens,
                "temperature": self.temperature,
            },
        )
        return resp.text

    # -- mock ---------------------------------------------------------------

    def _mock(self, system: str, user: str) -> str:
        """Deterministic offline stub.

        Returns valid, schema-shaped JSON so the pipeline and parsers can be
        exercised without any API key. Content is intentionally generic.
        """
        role = _detect_role(system)
        if role == "retriever":
            return json.dumps({
                "queries": [
                    {"query": "example query derived from brief", "sources": ["crossref", "openalex"]},
                ],
                "note": "[mock] No network calls are made by the mock provider.",
            })
        if role == "builder":
            return json.dumps({
                "document": (
                    "# [Mock document]\n\n"
                    "This is a mock draft generated without an LLM. "
                    "It demonstrates the pipeline wiring.\n\n"
                    "## Evidence requests\n"
                ),
                "evidence_requests": [],
            })
        if role == "critic":
            return json.dumps({
                "findings": [
                    {"severity": "minor", "location": "whole document",
                     "issue": "[mock] Document is a stub.",
                     "suggestion": "Run with a real provider and real evidence."},
                ],
                "overall": "minor",
            })
        return json.dumps({"result": "[mock] ok"})

    # -- JSON recovery ------------------------------------------------------

    @staticmethod
    def _extract_json(raw: str) -> Any:
        text = raw.strip()
        # Strip markdown code fences if present.
        fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
        if fence:
            text = fence.group(1).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Fallback: grab the outermost {...} or [...].
        for open_ch, close_ch in (("{", "}"), ("[", "]")):
            start = text.find(open_ch)
            end = text.rfind(close_ch)
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    continue
        raise LLMError(f"Could not parse JSON from model output:\n{raw[:400]}")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def load_env_file(path: str = ".env") -> int:
    """Load KEY=VALUE pairs from a local ``.env`` file into the environment.

    Dependency-free (no python-dotenv needed). Rules:
      * Lines are ``KEY=VALUE``; ``#`` starts a comment; blank lines ignored.
      * Surrounding single/double quotes on the value are removed.
      * An existing real environment variable always WINS (so you can still
        override on the command line), and blank values are skipped.
    Returns the number of variables actually set. Safe to call when the file
    is missing (returns 0).
    """
    p = Path(path)
    if not p.exists():
        return 0
    set_count = 0
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if not key or not val:
            continue
        if key in os.environ and os.environ[key]:
            continue  # real env var already set -> keep it
        os.environ[key] = val
        set_count += 1
    return set_count


def _env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise LLMError(
            f"Environment variable {name} is not set. "
            f"Export it or switch provider to 'mock' in config.yaml."
        )
    return val


def _detect_role(system: str) -> str:
    low = system.lower()
    for role in ("retriever", "builder", "critic"):
        if role in low:
            return role
    return ""


def build_llm(config: dict) -> LLM:
    """Construct an :class:`LLM` from a parsed config dict."""
    provider = str(config.get("provider", "mock"))
    model = config.get("models", {}).get(provider, "mock-1")
    return LLM(
        provider=provider,
        model=model,
        max_output_tokens=int(config.get("max_output_tokens", 1500)),
    )
