"""Configuracao lida do .env e caminhos do projeto."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
LIBRARY_DIR = DATA_DIR / "library"
DB_PATH = DATA_DIR / "study.db"

_PROVIDER_KEY_ENV = {
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


@dataclass(frozen=True)
class Settings:
    provider: str
    model: str
    api_key: str
    max_input_tokens: int

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    @property
    def api_key_env_var(self) -> str:
        return _PROVIDER_KEY_ENV.get(self.provider, "GEMINI_API_KEY")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv(ROOT / ".env")
    provider = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
    model = os.getenv("LLM_MODEL", "gemini-2.5-flash").strip()
    api_key = os.getenv(_PROVIDER_KEY_ENV.get(provider, "GEMINI_API_KEY"), "").strip()
    try:
        max_input_tokens = int(os.getenv("MAX_INPUT_TOKENS", "12000"))
    except ValueError:
        max_input_tokens = 12000
    return Settings(
        provider=provider,
        model=model,
        api_key=api_key,
        max_input_tokens=max_input_tokens,
    )


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)


def document_dir(collection_id: int, document_id: int) -> Path:
    return LIBRARY_DIR / str(collection_id) / str(document_id)
