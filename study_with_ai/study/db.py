"""Acesso ao SQLite: schema, conexao e consultas."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator, Sequence

from study.config import DB_PATH, ensure_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS collections (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    nome       TEXT NOT NULL UNIQUE,
    criado_em  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    filename      TEXT NOT NULL,
    sha256        TEXT NOT NULL UNIQUE,
    n_paginas     INTEGER NOT NULL DEFAULT 0,
    n_chunks      INTEGER NOT NULL DEFAULT 0,
    n_tokens      INTEGER NOT NULL DEFAULT 0,
    parsed_path   TEXT,
    qualidade_ok  INTEGER NOT NULL DEFAULT 1,
    qualidade_msg TEXT,
    criado_em     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ordem       INTEGER NOT NULL,
    pagina_ini  INTEGER NOT NULL,
    pagina_fim  INTEGER NOT NULL,
    heading     TEXT,
    n_tokens    INTEGER NOT NULL,
    texto       TEXT NOT NULL,
    times_used  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);

CREATE TABLE IF NOT EXISTS questions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id    INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    chunk_id         INTEGER REFERENCES chunks(id) ON DELETE SET NULL,
    dificuldade      TEXT NOT NULL,
    enunciado        TEXT NOT NULL,
    alternativas_json TEXT NOT NULL,
    indice_correto   INTEGER NOT NULL,
    explicacao       TEXT NOT NULL,
    citacao          TEXT NOT NULL,
    topico           TEXT NOT NULL,
    stem_hash        TEXT NOT NULL,
    criado_em        TEXT NOT NULL,
    UNIQUE (collection_id, stem_hash)
);
CREATE INDEX IF NOT EXISTS idx_questions_collection ON questions(collection_id);

CREATE TABLE IF NOT EXISTS quizzes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    dificuldade   TEXT NOT NULL,
    n_questoes    INTEGER NOT NULL,
    criado_em     TEXT NOT NULL,
    finalizado_em TEXT,
    score         REAL
);
CREATE INDEX IF NOT EXISTS idx_quizzes_collection ON quizzes(collection_id);

CREATE TABLE IF NOT EXISTS quiz_questions (
    quiz_id     INTEGER NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    posicao     INTEGER NOT NULL,
    PRIMARY KEY (quiz_id, posicao)
);

CREATE TABLE IF NOT EXISTS answers (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    quiz_id          INTEGER NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    question_id      INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    indice_escolhido INTEGER,
    correta          INTEGER NOT NULL,
    respondido_em    TEXT NOT NULL,
    UNIQUE (quiz_id, question_id)
);

CREATE TABLE IF NOT EXISTS llm_calls (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    quiz_id    INTEGER REFERENCES quizzes(id) ON DELETE SET NULL,
    modelo     TEXT NOT NULL,
    tokens_in  INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0,
    criado_em  TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def session() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with session() as conn:
        conn.executescript(SCHEMA)


def query(sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
    with session() as conn:
        return conn.execute(sql, params).fetchall()


def query_one(sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
    with session() as conn:
        return conn.execute(sql, params).fetchone()


def execute(sql: str, params: Sequence[Any] = ()) -> int:
    with session() as conn:
        cur = conn.execute(sql, params)
        return cur.lastrowid or 0


# --- colecoes ---------------------------------------------------------------


def create_collection(nome: str) -> int:
    return execute(
        "INSERT INTO collections (nome, criado_em) VALUES (?, ?)", (nome.strip(), now())
    )


def rename_collection(collection_id: int, nome: str) -> None:
    execute("UPDATE collections SET nome = ? WHERE id = ?", (nome.strip(), collection_id))


def delete_collection(collection_id: int) -> None:
    execute("DELETE FROM collections WHERE id = ?", (collection_id,))


def list_collections() -> list[sqlite3.Row]:
    return query(
        """
        SELECT c.id,
               c.nome,
               c.criado_em,
               COUNT(DISTINCT d.id) AS n_documentos,
               COALESCE(SUM(d.n_chunks), 0) AS n_chunks
        FROM collections c
        LEFT JOIN documents d ON d.collection_id = c.id
        GROUP BY c.id
        ORDER BY c.nome
        """
    )


# --- documentos -------------------------------------------------------------


def document_by_hash(sha256: str) -> sqlite3.Row | None:
    return query_one("SELECT * FROM documents WHERE sha256 = ?", (sha256,))


def list_documents(collection_id: int) -> list[sqlite3.Row]:
    return query(
        "SELECT * FROM documents WHERE collection_id = ? ORDER BY filename",
        (collection_id,),
    )


def delete_document(document_id: int) -> None:
    execute("DELETE FROM documents WHERE id = ?", (document_id,))


def insert_document(
    conn: sqlite3.Connection, collection_id: int, filename: str, sha256: str
) -> int:
    cur = conn.execute(
        """
        INSERT INTO documents (collection_id, filename, sha256, criado_em)
        VALUES (?, ?, ?, ?)
        """,
        (collection_id, filename, sha256, now()),
    )
    return cur.lastrowid or 0


# --- chunks -----------------------------------------------------------------


def collection_chunk_stats(collection_id: int) -> sqlite3.Row | None:
    return query_one(
        """
        SELECT COUNT(ch.id) AS n_chunks, COALESCE(AVG(ch.n_tokens), 0) AS media_tokens
        FROM chunks ch
        JOIN documents d ON d.id = ch.document_id
        WHERE d.collection_id = ?
        """,
        (collection_id,),
    )


def bump_chunk_usage(chunk_ids: Sequence[int]) -> None:
    if not chunk_ids:
        return
    marks = ",".join("?" for _ in chunk_ids)
    execute(
        f"UPDATE chunks SET times_used = times_used + 1 WHERE id IN ({marks})",
        list(chunk_ids),
    )


# --- questoes ---------------------------------------------------------------


def existing_stems(collection_id: int, chunk_ids: Sequence[int], limit: int = 40) -> list[str]:
    if not chunk_ids:
        return []
    marks = ",".join("?" for _ in chunk_ids)
    rows = query(
        f"""
        SELECT enunciado FROM questions
        WHERE collection_id = ? AND chunk_id IN ({marks})
        ORDER BY id DESC LIMIT ?
        """,
        [collection_id, *chunk_ids, limit],
    )
    return [r["enunciado"] for r in rows]


def collection_stem_hashes(collection_id: int) -> set[str]:
    rows = query("SELECT stem_hash FROM questions WHERE collection_id = ?", (collection_id,))
    return {r["stem_hash"] for r in rows}


def collection_stems(collection_id: int) -> list[str]:
    rows = query("SELECT enunciado FROM questions WHERE collection_id = ?", (collection_id,))
    return [r["enunciado"] for r in rows]


def list_bank_questions(
    collection_id: int, dificuldade: str | None = None, topico: str | None = None
) -> list[sqlite3.Row]:
    sql = [
        """
        SELECT q.*, d.filename, ch.pagina_ini, ch.pagina_fim
        FROM questions q
        LEFT JOIN chunks ch ON ch.id = q.chunk_id
        LEFT JOIN documents d ON d.id = ch.document_id
        WHERE q.collection_id = ?
        """
    ]
    params: list[Any] = [collection_id]
    if dificuldade:
        sql.append("AND q.dificuldade = ?")
        params.append(dificuldade)
    if topico:
        sql.append("AND q.topico = ?")
        params.append(topico)
    sql.append("ORDER BY q.id DESC")
    return query(" ".join(sql), params)


def bank_topics(collection_id: int) -> list[str]:
    rows = query(
        "SELECT DISTINCT topico FROM questions WHERE collection_id = ? ORDER BY topico",
        (collection_id,),
    )
    return [r["topico"] for r in rows]


# --- quizzes ----------------------------------------------------------------


def save_quiz(
    collection_id: int,
    dificuldade: str,
    questoes: list[dict[str, Any]],
    tokens_in: int,
    tokens_out: int,
    modelo: str,
) -> int:
    """Grava as questoes no banco (dedup por stem_hash) e monta o quiz."""
    with session() as conn:
        cur = conn.execute(
            """
            INSERT INTO quizzes (collection_id, dificuldade, n_questoes, criado_em)
            VALUES (?, ?, ?, ?)
            """,
            (collection_id, dificuldade, len(questoes), now()),
        )
        quiz_id = cur.lastrowid or 0

        for posicao, q in enumerate(questoes):
            row = conn.execute(
                "SELECT id FROM questions WHERE collection_id = ? AND stem_hash = ?",
                (collection_id, q["stem_hash"]),
            ).fetchone()
            if row:
                question_id = row["id"]
            else:
                qcur = conn.execute(
                    """
                    INSERT INTO questions (
                        collection_id, chunk_id, dificuldade, enunciado, alternativas_json,
                        indice_correto, explicacao, citacao, topico, stem_hash, criado_em
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        collection_id,
                        q["chunk_id"],
                        dificuldade,
                        q["enunciado"],
                        json.dumps(q["alternativas"], ensure_ascii=False),
                        q["indice_correto"],
                        q["explicacao"],
                        q["citacao"],
                        q["topico"],
                        q["stem_hash"],
                        now(),
                    ),
                )
                question_id = qcur.lastrowid or 0

            conn.execute(
                "INSERT INTO quiz_questions (quiz_id, question_id, posicao) VALUES (?, ?, ?)",
                (quiz_id, question_id, posicao),
            )

        conn.execute(
            """
            INSERT INTO llm_calls (quiz_id, modelo, tokens_in, tokens_out, criado_em)
            VALUES (?, ?, ?, ?, ?)
            """,
            (quiz_id, modelo, tokens_in, tokens_out, now()),
        )
    return quiz_id


def quiz_questions(quiz_id: int) -> list[dict[str, Any]]:
    rows = query(
        """
        SELECT q.*, qq.posicao, d.filename, ch.pagina_ini, ch.pagina_fim
        FROM quiz_questions qq
        JOIN questions q ON q.id = qq.question_id
        LEFT JOIN chunks ch ON ch.id = q.chunk_id
        LEFT JOIN documents d ON d.id = ch.document_id
        WHERE qq.quiz_id = ?
        ORDER BY qq.posicao
        """,
        (quiz_id,),
    )
    out = []
    for r in rows:
        item = dict(r)
        item["alternativas"] = json.loads(r["alternativas_json"])
        out.append(item)
    return out


def get_quiz(quiz_id: int) -> sqlite3.Row | None:
    return query_one(
        """
        SELECT qz.*, c.nome AS colecao
        FROM quizzes qz JOIN collections c ON c.id = qz.collection_id
        WHERE qz.id = ?
        """,
        (quiz_id,),
    )


def list_quizzes(collection_id: int | None = None, apenas_finalizados: bool = True) -> list[sqlite3.Row]:
    sql = [
        """
        SELECT qz.*, c.nome AS colecao
        FROM quizzes qz JOIN collections c ON c.id = qz.collection_id
        WHERE 1 = 1
        """
    ]
    params: list[Any] = []
    if collection_id is not None:
        sql.append("AND qz.collection_id = ?")
        params.append(collection_id)
    if apenas_finalizados:
        sql.append("AND qz.finalizado_em IS NOT NULL")
    sql.append("ORDER BY qz.criado_em DESC")
    return query(" ".join(sql), params)


def delete_quiz(quiz_id: int) -> None:
    execute("DELETE FROM quizzes WHERE id = ?", (quiz_id,))


def save_answers(quiz_id: int, respostas: dict[int, int | None], score: float) -> None:
    """respostas: question_id -> indice escolhido (None = em branco)."""
    with session() as conn:
        for question_id, escolhido in respostas.items():
            correto = conn.execute(
                "SELECT indice_correto FROM questions WHERE id = ?", (question_id,)
            ).fetchone()
            acertou = int(correto is not None and escolhido == correto["indice_correto"])
            conn.execute(
                """
                INSERT INTO answers (quiz_id, question_id, indice_escolhido, correta, respondido_em)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (quiz_id, question_id) DO UPDATE SET
                    indice_escolhido = excluded.indice_escolhido,
                    correta = excluded.correta,
                    respondido_em = excluded.respondido_em
                """,
                (quiz_id, question_id, escolhido, acertou, now()),
            )
        conn.execute(
            "UPDATE quizzes SET score = ?, finalizado_em = ? WHERE id = ?",
            (score, now(), quiz_id),
        )


def quiz_answers(quiz_id: int) -> dict[int, sqlite3.Row]:
    rows = query("SELECT * FROM answers WHERE quiz_id = ?", (quiz_id,))
    return {r["question_id"]: r for r in rows}
