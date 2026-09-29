"""Correcao das respostas e calculo do score."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from study import db


@dataclass
class ItemCorrigido:
    posicao: int
    questao: dict[str, Any]
    escolhido: int | None
    acertou: bool


@dataclass
class Correcao:
    quiz_id: int
    acertos: int
    total: int
    score: float
    itens: list[ItemCorrigido]


def corrigir(quiz_id: int, respostas: dict[int, int | None]) -> Correcao:
    """respostas: question_id -> indice escolhido. Grava e devolve o resultado."""
    questoes = db.quiz_questions(quiz_id)
    total = len(questoes)
    if total == 0:
        raise ValueError(f"Quiz {quiz_id} nao tem questoes.")

    itens = []
    acertos = 0
    for q in questoes:
        escolhido = respostas.get(q["id"])
        acertou = escolhido == q["indice_correto"]
        acertos += int(acertou)
        itens.append(
            ItemCorrigido(posicao=q["posicao"], questao=q, escolhido=escolhido, acertou=acertou)
        )

    score = acertos / total
    db.save_answers(quiz_id, {q["id"]: respostas.get(q["id"]) for q in questoes}, score)
    return Correcao(quiz_id=quiz_id, acertos=acertos, total=total, score=score, itens=itens)


def carregar_correcao(quiz_id: int) -> Correcao | None:
    """Reconstroi a correcao de um quiz ja finalizado, para revisao."""
    quiz = db.get_quiz(quiz_id)
    if quiz is None or quiz["finalizado_em"] is None:
        return None

    questoes = db.quiz_questions(quiz_id)
    respostas = db.quiz_answers(quiz_id)
    itens = []
    acertos = 0
    for q in questoes:
        resposta = respostas.get(q["id"])
        escolhido = resposta["indice_escolhido"] if resposta else None
        acertou = bool(resposta and resposta["correta"])
        acertos += int(acertou)
        itens.append(
            ItemCorrigido(posicao=q["posicao"], questao=q, escolhido=escolhido, acertou=acertou)
        )

    total = len(questoes)
    return Correcao(
        quiz_id=quiz_id,
        acertos=acertos,
        total=total,
        score=quiz["score"] if quiz["score"] is not None else (acertos / total if total else 0.0),
        itens=itens,
    )
