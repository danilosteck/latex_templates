"""Estimativa de tokens sem dependencia de tokenizer externo.

O objetivo e orcamento, nao precisao contabil: uma media de ~3.6 caracteres por
token aproxima bem textos em portugues nos tokenizers atuais.
"""

from __future__ import annotations

CARACTERES_POR_TOKEN = 3.6


def estimar_tokens(texto: str) -> int:
    if not texto:
        return 0
    return max(1, round(len(texto) / CARACTERES_POR_TOKEN))
