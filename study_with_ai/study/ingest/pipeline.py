"""Orquestracao da ingestao: PDF -> markdown limpo em disco + chunks no SQLite."""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

from study import db
from study.config import document_dir, ensure_dirs
from study.ingest import chunk as chunking
from study.ingest import clean, extract


@dataclass
class ResultadoIngestao:
    filename: str
    document_id: int | None
    n_paginas: int
    n_chunks: int
    n_tokens: int
    qualidade_ok: bool
    mensagem: str
    ja_existia: bool = False


def hash_arquivo(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def ingerir_bytes(collection_id: int, filename: str, dados: bytes) -> ResultadoIngestao:
    """Ingere um PDF. Idempotente: o mesmo conteudo nunca e parseado duas vezes."""
    ensure_dirs()
    sha = hash_arquivo(dados)

    existente = db.document_by_hash(sha)
    if existente is not None:
        return ResultadoIngestao(
            filename=filename,
            document_id=existente["id"],
            n_paginas=existente["n_paginas"],
            n_chunks=existente["n_chunks"],
            n_tokens=existente["n_tokens"],
            qualidade_ok=bool(existente["qualidade_ok"]),
            mensagem="Ja ingerido anteriormente; parse reaproveitado.",
            ja_existia=True,
        )

    with db.session() as conn:
        document_id = db.insert_document(conn, collection_id, filename, sha)

    destino = document_dir(collection_id, document_id)
    destino.mkdir(parents=True, exist_ok=True)
    caminho_pdf = destino / "source.pdf"
    caminho_pdf.write_bytes(dados)

    try:
        paginas = extract.paginas_do_pdf(caminho_pdf)
        resultado = clean.limpar(paginas)
        chunks = chunking.dividir(resultado.paginas)
    except extract.ExtractionError as exc:
        db.delete_document(document_id)
        shutil.rmtree(destino, ignore_errors=True)
        return ResultadoIngestao(
            filename=filename,
            document_id=None,
            n_paginas=0,
            n_chunks=0,
            n_tokens=0,
            qualidade_ok=False,
            mensagem=str(exc),
        )

    caminho_md = destino / "parsed.md"
    caminho_md.write_text(resultado.texto, encoding="utf-8")

    total_tokens = sum(c.n_tokens for c in chunks)
    with db.session() as conn:
        conn.executemany(
            """
            INSERT INTO chunks (document_id, ordem, pagina_ini, pagina_fim, heading, n_tokens, texto)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (document_id, c.ordem, c.pagina_ini, c.pagina_fim, c.heading, c.n_tokens, c.texto)
                for c in chunks
            ],
        )
        conn.execute(
            """
            UPDATE documents
            SET n_paginas = ?, n_chunks = ?, n_tokens = ?, parsed_path = ?,
                qualidade_ok = ?, qualidade_msg = ?
            WHERE id = ?
            """,
            (
                len(paginas),
                len(chunks),
                total_tokens,
                str(caminho_md),
                int(resultado.qualidade_ok),
                resultado.qualidade_msg or None,
                document_id,
            ),
        )

    mensagem = resultado.qualidade_msg or "Processado com sucesso."
    if resultado.qualidade_ok and not chunks:
        resultado.qualidade_ok = False
        mensagem = "Nenhum chunk gerado: o PDF nao produziu texto aproveitavel."

    return ResultadoIngestao(
        filename=filename,
        document_id=document_id,
        n_paginas=len(paginas),
        n_chunks=len(chunks),
        n_tokens=total_tokens,
        qualidade_ok=resultado.qualidade_ok,
        mensagem=mensagem,
    )


def reprocessar(document_id: int) -> ResultadoIngestao:
    """Reparseia um documento ja ingerido, a partir do PDF guardado em disco."""
    doc = db.query_one("SELECT * FROM documents WHERE id = ?", (document_id,))
    if doc is None:
        raise ValueError(f"Documento {document_id} nao encontrado.")

    caminho_pdf = document_dir(doc["collection_id"], document_id) / "source.pdf"
    if not caminho_pdf.exists():
        raise FileNotFoundError(f"PDF original ausente em {caminho_pdf}")

    dados = caminho_pdf.read_bytes()
    collection_id = doc["collection_id"]
    filename = doc["filename"]
    remover_documento(document_id)
    return ingerir_bytes(collection_id, filename, dados)


def remover_documento(document_id: int) -> None:
    doc = db.query_one("SELECT * FROM documents WHERE id = ?", (document_id,))
    if doc is None:
        return
    db.delete_document(document_id)
    shutil.rmtree(document_dir(doc["collection_id"], document_id), ignore_errors=True)


def texto_parseado(document_id: int) -> str:
    doc = db.query_one("SELECT parsed_path FROM documents WHERE id = ?", (document_id,))
    if doc is None or not doc["parsed_path"]:
        return ""
    caminho = Path(doc["parsed_path"])
    return caminho.read_text(encoding="utf-8") if caminho.exists() else ""
