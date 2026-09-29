"""Limpeza do markdown extraido e portao de qualidade."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from study.ingest.extract import PaginaExtraida

LIGADURAS = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\ufb05": "st",
    "\ufb06": "st",
}

# Aspas e travessoes tipograficos viram ASCII: menos tokens, mesma leitura.
PONTUACAO = {
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2013": "-",
    "\u2014": "-",
    "\u2212": "-",
    "\u2026": "...",
}

LETRA = "a-zà-öø-ÿ"
RE_HIFEN_QUEBRA = re.compile(rf"([{LETRA}])-\s+([{LETRA}])")
RE_SO_NUMERO = re.compile(r"^\s*[\[\(]?[ivxlcdmIVXLCDM\d]{1,6}[\]\)]?\s*$")
RE_NOTA_ORFA = re.compile(r"^\s*\[?\d{1,3}\]?\s*$")
RE_ESPACOS = re.compile(r"[ \t\u00a0]+")
RE_LINHAS_VAZIAS = re.compile(r"\n{3,}")

LIMIAR_RECORRENCIA = 0.6
LIMIAR_ESPACOS = 0.08
MIN_CARACTERES = 200


@dataclass
class ResultadoLimpeza:
    paginas: list[PaginaExtraida]
    texto: str
    qualidade_ok: bool
    qualidade_msg: str


def _normalizar(texto: str) -> str:
    for origem, destino in LIGADURAS.items():
        texto = texto.replace(origem, destino)
    texto = unicodedata.normalize("NFKC", texto)
    for origem, destino in PONTUACAO.items():
        texto = texto.replace(origem, destino)
    return texto


def _linhas_recorrentes(paginas: list[PaginaExtraida]) -> set[str]:
    """Linhas curtas que aparecem na maioria das paginas sao cabecalho/rodape."""
    if len(paginas) < 4:
        return set()
    contagem: Counter[str] = Counter()
    for pagina in paginas:
        candidatas = {
            linha.strip()
            for linha in pagina.texto.splitlines()
            if 0 < len(linha.strip()) <= 80
        }
        contagem.update(candidatas)
    minimo = max(3, int(len(paginas) * LIMIAR_RECORRENCIA))
    return {linha for linha, n in contagem.items() if n >= minimo}


def _limpar_pagina(texto: str, descartar: set[str]) -> str:
    texto = _normalizar(texto)
    linhas = []
    for linha in texto.splitlines():
        alvo = linha.strip()
        if alvo in descartar:
            continue
        if RE_SO_NUMERO.match(alvo) or RE_NOTA_ORFA.match(alvo):
            continue
        linhas.append(RE_ESPACOS.sub(" ", linha).rstrip())
    texto = "\n".join(linhas)
    texto = RE_HIFEN_QUEBRA.sub(r"\1\2", texto)
    texto = RE_LINHAS_VAZIAS.sub("\n\n", texto)
    return texto.strip()


def _avaliar_qualidade(texto: str) -> tuple[bool, str]:
    if len(texto) < MIN_CARACTERES:
        return False, (
            "Texto extraido muito curto. O PDF provavelmente e digitalizado "
            "(imagem) e precisaria de OCR, que nao e suportado."
        )
    espacos = sum(1 for c in texto if c.isspace())
    razao = espacos / len(texto)
    if razao < LIMIAR_ESPACOS:
        return False, (
            f"Razao de espacos em branco de {razao:.3f}, abaixo do minimo de "
            f"{LIMIAR_ESPACOS}. O texto saiu com palavras coladas e nao serve "
            "para gerar questoes."
        )
    return True, ""


def limpar(paginas: list[PaginaExtraida]) -> ResultadoLimpeza:
    descartar = _linhas_recorrentes(paginas)
    limpas = [
        PaginaExtraida(numero=p.numero, texto=_limpar_pagina(p.texto, descartar))
        for p in paginas
    ]
    limpas = [p for p in limpas if p.texto]
    texto = "\n\n".join(p.texto for p in limpas)
    ok, msg = _avaliar_qualidade(texto)
    return ResultadoLimpeza(paginas=limpas, texto=texto, qualidade_ok=ok, qualidade_msg=msg)
