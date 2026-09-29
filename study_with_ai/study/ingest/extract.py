"""Extracao de texto de PDFs para markdown, uma pagina por item."""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass
from pathlib import Path

import pymupdf
import pymupdf4llm


@dataclass
class PaginaExtraida:
    numero: int
    texto: str


class ExtractionError(RuntimeError):
    pass


def paginas_do_pdf(caminho: Path) -> list[PaginaExtraida]:
    """Converte o PDF em markdown por pagina.

    `header`/`footer` desligados fazem o motor de layout descartar cabecalhos,
    rodapes e numeros de pagina. OCR fica desligado: o escopo sao PDFs com texto
    embutido, e liga-lo custa varios segundos por pagina.
    """
    if not caminho.exists():
        raise ExtractionError(f"Arquivo nao encontrado: {caminho}")

    # A engine escreve diagnosticos em stdout, que poluiriam o log do Streamlit.
    ruido = io.StringIO()
    try:
        with contextlib.redirect_stdout(ruido):
            paginas = pymupdf4llm.to_markdown(
                str(caminho),
                page_chunks=True,
                show_progress=False,
                use_ocr=False,
                header=False,
                footer=False,
            )
    except Exception as exc:  # noqa: BLE001 - erro da lib e opaco, queremos a mensagem
        raise ExtractionError(f"Falha ao ler o PDF: {exc}") from exc

    return [
        PaginaExtraida(
            numero=int(p["metadata"].get("page_number") or i + 1),
            texto=p.get("text") or "",
        )
        for i, p in enumerate(paginas)
    ]


def contar_paginas(caminho: Path) -> int:
    with pymupdf.open(str(caminho)) as doc:
        return doc.page_count
