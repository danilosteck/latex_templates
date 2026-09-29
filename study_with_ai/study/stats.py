"""Agregacoes para a pagina de progresso."""

from __future__ import annotations

import pandas as pd

from study import db
from study.models import ROTULO_DIFICULDADE

MIN_RESPOSTAS_POR_TOPICO = 3


def _filtro_colecao(collection_id: int | None) -> tuple[str, list]:
    if collection_id is None:
        return "", []
    return "AND qz.collection_id = ?", [collection_id]


def historico_quizzes(collection_id: int | None = None) -> pd.DataFrame:
    """Um registro por quiz finalizado, em ordem cronologica."""
    where, params = _filtro_colecao(collection_id)
    linhas = db.query(
        f"""
        SELECT qz.id, qz.criado_em, qz.finalizado_em, qz.score, qz.dificuldade,
               qz.n_questoes, c.nome AS colecao
        FROM quizzes qz
        JOIN collections c ON c.id = qz.collection_id
        WHERE qz.finalizado_em IS NOT NULL {where}
        ORDER BY qz.finalizado_em
        """,
        params,
    )
    df = pd.DataFrame([dict(r) for r in linhas])
    if df.empty:
        return df
    df["data"] = pd.to_datetime(df["finalizado_em"], format="ISO8601", utc=True)
    df["dificuldade"] = df["dificuldade"].map(ROTULO_DIFICULDADE).fillna(df["dificuldade"])
    df["media_movel"] = df["score"].rolling(window=5, min_periods=1).mean()
    df["n"] = range(1, len(df) + 1)
    return df


def evolucao_por_dificuldade(df: pd.DataFrame) -> pd.DataFrame:
    """Media movel calculada dentro de cada nivel de dificuldade."""
    if df.empty:
        return df
    saida = df.sort_values("data").copy()
    saida["media_movel_nivel"] = (
        saida.groupby("dificuldade")["score"].transform(
            lambda s: s.rolling(window=5, min_periods=1).mean()
        )
    )
    return saida


def resumo_por_dificuldade(collection_id: int | None = None) -> pd.DataFrame:
    where, params = _filtro_colecao(collection_id)
    linhas = db.query(
        f"""
        SELECT qz.dificuldade,
               COUNT(*) AS quizzes,
               AVG(qz.score) AS score_medio,
               SUM(qz.n_questoes) AS questoes
        FROM quizzes qz
        WHERE qz.finalizado_em IS NOT NULL {where}
        GROUP BY qz.dificuldade
        """,
        params,
    )
    df = pd.DataFrame([dict(r) for r in linhas])
    if df.empty:
        return df
    df["dificuldade"] = df["dificuldade"].map(ROTULO_DIFICULDADE).fillna(df["dificuldade"])
    ordem = ["Facil", "Moderado", "Dificil"]
    df["_ordem"] = df["dificuldade"].apply(lambda d: ordem.index(d) if d in ordem else 99)
    return df.sort_values("_ordem").drop(columns="_ordem")


def resumo_por_colecao() -> pd.DataFrame:
    linhas = db.query(
        """
        SELECT c.nome AS colecao,
               COUNT(*) AS quizzes,
               AVG(qz.score) AS score_medio
        FROM quizzes qz
        JOIN collections c ON c.id = qz.collection_id
        WHERE qz.finalizado_em IS NOT NULL
        GROUP BY c.id
        ORDER BY score_medio
        """
    )
    return pd.DataFrame([dict(r) for r in linhas])


def acuracia_por_topico(collection_id: int | None = None) -> pd.DataFrame:
    """Topicos mais fracos primeiro, ignorando os com poucas respostas."""
    where, params = _filtro_colecao(collection_id)
    linhas = db.query(
        f"""
        SELECT q.topico,
               COUNT(*) AS respondidas,
               SUM(a.correta) AS acertos,
               AVG(a.correta) AS acuracia
        FROM answers a
        JOIN questions q ON q.id = a.question_id
        JOIN quizzes qz ON qz.id = a.quiz_id
        WHERE 1 = 1 {where}
        GROUP BY q.topico
        HAVING COUNT(*) >= ?
        ORDER BY acuracia ASC, respondidas DESC
        """,
        [*params, MIN_RESPOSTAS_POR_TOPICO],
    )
    return pd.DataFrame([dict(r) for r in linhas])


def totais(collection_id: int | None = None) -> dict[str, float | int]:
    where, params = _filtro_colecao(collection_id)
    linha = db.query_one(
        f"""
        SELECT COUNT(*) AS quizzes,
               COALESCE(SUM(qz.n_questoes), 0) AS questoes,
               COALESCE(AVG(qz.score), 0) AS score_medio
        FROM quizzes qz
        WHERE qz.finalizado_em IS NOT NULL {where}
        """,
        params,
    )
    tokens = db.query_one(
        """
        SELECT COALESCE(SUM(tokens_in), 0) AS tokens_in,
               COALESCE(SUM(tokens_out), 0) AS tokens_out
        FROM llm_calls
        """
    )
    return {
        "quizzes": linha["quizzes"] if linha else 0,
        "questoes": linha["questoes"] if linha else 0,
        "score_medio": linha["score_medio"] if linha else 0.0,
        "tokens_in": tokens["tokens_in"] if tokens else 0,
        "tokens_out": tokens["tokens_out"] if tokens else 0,
    }
