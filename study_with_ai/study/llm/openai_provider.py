"""Provedor OpenAI/OpenAI-compatible (OpenAI, DeepSeek, etc.)."""

from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from study.llm.base import LLMError, RespostaLLM


def _e_deepseek(base_url: str | None) -> bool:
    return bool(base_url and "deepseek" in base_url.lower())


class OpenAIProvider:
    """Cliente generico para APIs OpenAI-compatible, incluindo DeepSeek."""

    def __init__(self, api_key: str, modelo: str, base_url: str | None = None) -> None:
        self.modelo = modelo
        self.base_url = base_url
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def gerar_json(
        self, instrucao: str, prompt: str, json_schema: dict[str, Any]
    ) -> RespostaLLM:
        # DeepSeek ainda nao suporta response_format=json_schema; usa json_object
        # e emenda o schema no prompt para guiar a saida.
        usar_json_object = _e_deepseek(self.base_url)

        if usar_json_object:
            schema_texto = json.dumps(json_schema, ensure_ascii=False, indent=1)
            instrucao_completa = (
                f"{instrucao}\n\nSua resposta deve ser um objeto JSON valido "
                f"seguindo estritamente este schema:\n{schema_texto}\n"
                "Nao inclua nenhum texto fora do JSON."
            )
            response_format: dict[str, Any] | None = {"type": "json_object"}
        else:
            instrucao_completa = instrucao
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": json_schema.get("title", "QuizSchema"),
                    "schema": json_schema,
                    "strict": False,
                },
            }

        try:
            resposta = self._client.chat.completions.create(
                model=self.modelo,
                messages=[
                    {"role": "system", "content": instrucao_completa},
                    {"role": "user", "content": prompt},
                ],
                response_format=response_format,
                temperature=0.8,
            )
        except Exception as exc:  # noqa: BLE001
            provedor = self.base_url or "OpenAI"
            raise LLMError(f"Falha na chamada ao {provedor}: {exc}") from exc

        if not resposta.choices:
            raise LLMError("O modelo devolveu uma resposta sem choices.")

        texto = (resposta.choices[0].message.content or "").strip()
        if not texto:
            raise LLMError("O modelo devolveu resposta vazia.")

        try:
            dados = json.loads(texto)
        except json.JSONDecodeError as exc:
            raise LLMError(f"O modelo devolveu JSON invalido: {exc}") from exc

        uso = getattr(resposta, "usage", None)
        return RespostaLLM(
            dados=dados,
            tokens_in=getattr(uso, "prompt_tokens", 0) or 0,
            tokens_out=getattr(uso, "completion_tokens", 0) or 0,
            modelo=self.modelo,
        )
