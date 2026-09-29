"""Provedor Gemini via google-genai, com saida estruturada por JSON Schema."""

from __future__ import annotations

import json
from typing import Any

from google import genai
from google.genai import types

from study.llm.base import LLMError, RespostaLLM


class GeminiProvider:
    def __init__(self, api_key: str, modelo: str) -> None:
        self.modelo = modelo
        self._client = genai.Client(api_key=api_key)

    def gerar_json(
        self, instrucao: str, prompt: str, json_schema: dict[str, Any]
    ) -> RespostaLLM:
        try:
            resposta = self._client.models.generate_content(
                model=self.modelo,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=instrucao,
                    response_mime_type="application/json",
                    response_json_schema=json_schema,
                    temperature=0.8,
                ),
            )
        except Exception as exc:  # noqa: BLE001 - erros do SDK sao heterogeneos
            raise LLMError(f"Falha na chamada ao Gemini: {exc}") from exc

        texto = (resposta.text or "").strip()
        if not texto:
            motivo = _motivo_de_parada(resposta)
            raise LLMError(f"O modelo devolveu resposta vazia{motivo}.")

        try:
            dados = json.loads(texto)
        except json.JSONDecodeError as exc:
            raise LLMError(f"O modelo devolveu JSON invalido: {exc}") from exc

        uso = getattr(resposta, "usage_metadata", None)
        return RespostaLLM(
            dados=dados,
            tokens_in=getattr(uso, "prompt_token_count", 0) or 0,
            tokens_out=getattr(uso, "candidates_token_count", 0) or 0,
            modelo=self.modelo,
        )


def _motivo_de_parada(resposta: Any) -> str:
    candidatos = getattr(resposta, "candidates", None) or []
    if candidatos and getattr(candidatos[0], "finish_reason", None):
        return f" (motivo: {candidatos[0].finish_reason})"
    return ""
