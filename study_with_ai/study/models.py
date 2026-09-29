"""Modelos Pydantic usados no schema de saida estruturada do LLM."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Dificuldade = Literal["facil", "moderado", "dificil"]

ROTULO_DIFICULDADE: dict[str, str] = {
    "facil": "Facil",
    "moderado": "Moderado",
    "dificil": "Dificil",
}


class Questao(BaseModel):
    chunk_id: int = Field(description="id do trecho de onde a questao foi tirada")
    topico: str = Field(description="tema em ate 4 palavras, ex.: 'imperativo categorico'")
    enunciado: str
    alternativas: list[str] = Field(min_length=4, max_length=4)
    indice_correto: int = Field(ge=0, le=3)
    explicacao: str
    citacao: str = Field(description="trecho copiado literalmente do texto-fonte")


class QuizGerado(BaseModel):
    questoes: list[Questao]
