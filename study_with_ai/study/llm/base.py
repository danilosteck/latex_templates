"""Interface comum aos provedores de LLM."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class LLMError(RuntimeError):
    pass


@dataclass
class RespostaLLM:
    dados: dict[str, Any]
    tokens_in: int
    tokens_out: int
    modelo: str


class LLMProvider(Protocol):
    """Provedor capaz de devolver JSON conforme um JSON Schema."""

    modelo: str

    def gerar_json(
        self, instrucao: str, prompt: str, json_schema: dict[str, Any]
    ) -> RespostaLLM: ...


def get_provider() -> LLMProvider:
    """Instancia o provedor configurado no .env."""
    from study.config import get_settings

    settings = get_settings()
    if not settings.is_configured:
        raise LLMError(
            f"Nenhuma chave de API encontrada. Defina {settings.api_key_env_var} "
            "no arquivo .env na raiz do projeto."
        )

    if settings.provider == "gemini":
        from study.llm.gemini import GeminiProvider

        return GeminiProvider(api_key=settings.api_key, modelo=settings.model)

    if settings.provider in ("openai", "deepseek"):
        from study.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(
            api_key=settings.api_key,
            modelo=settings.model,
            base_url=settings.base_url,
        )

    raise LLMError(
        f"Provedor '{settings.provider}' ainda nao implementado. "
        "Use LLM_PROVIDER=gemini, openai ou deepseek."
    )
