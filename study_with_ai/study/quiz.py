"""Amostragem de trechos, geracao das questoes e validacao antes de gravar."""

from __future__ import annotations

import hashlib
import random
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from study import db
from study.config import get_settings
from study.llm.base import LLMError, LLMProvider, get_provider
from study.llm.prompts import INSTRUCAO_SISTEMA, TrechoPrompt, montar_prompt
from study.models import QuizGerado

QUESTOES_POR_TRECHO = 1.5
LIMIAR_JACCARD = 0.8
TOKENS_OVERHEAD_PROMPT = 700
MIN_PALAVRAS_PARA_JACCARD = 4

# Enunciados compartilham muito andaime ("segundo o texto, qual das alternativas").
# Sem remover essas palavras, duas questoes sobre temas distintos parecem iguais.
ESTRUTURAIS = {
    "a", "ao", "aos", "as", "com", "como", "da", "das", "de", "do", "dos", "e", "em",
    "entre", "essa", "esse", "esta", "este", "na", "nas", "no", "nos", "o", "os",
    "ou", "para", "pela", "pelas", "pelo", "pelos", "por", "que", "qual", "quais",
    "se", "sobre", "um", "uma", "uns", "umas", "afirmacao", "afirmacoes", "alternativa",
    "alternativas", "assinale", "autor", "correta", "corretamente", "correto", "das",
    "descreve", "e", "esta", "expressa", "melhor", "opcao", "passagem", "qual",
    "segundo", "seguinte", "seguintes", "tese", "texto", "trecho",
}


class QuizError(RuntimeError):
    pass


@dataclass
class Plano:
    """Trechos escolhidos para uma geracao e o custo estimado."""

    trechos: list[TrechoPrompt]
    tokens_estimados: int


@dataclass
class ResultadoGeracao:
    quiz_id: int
    n_solicitadas: int
    n_geradas: int
    descartadas: list[str] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0


# --- normalizacao e similaridade -------------------------------------------


def _sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


def normalizar(texto: str) -> str:
    """Forma canonica para comparar textos: sem acento, sem pontuacao, caixa baixa."""
    texto = _sem_acento(texto.lower())
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return " ".join(texto.split())


def hash_enunciado(enunciado: str) -> str:
    return hashlib.sha1(normalizar(enunciado).encode("utf-8")).hexdigest()


def _palavras_de_conteudo(texto: str) -> set[str]:
    return {p for p in normalizar(texto).split() if p not in ESTRUTURAIS and len(p) > 2}


def _jaccard(a: str, b: str) -> float:
    ta, tb = _palavras_de_conteudo(a), _palavras_de_conteudo(b)
    # Enunciados curtos demais nao tem conteudo suficiente para um veredito confiavel.
    if len(ta) < MIN_PALAVRAS_PARA_JACCARD or len(tb) < MIN_PALAVRAS_PARA_JACCARD:
        return 0.0
    return len(ta & tb) / len(ta | tb)


# --- amostragem -------------------------------------------------------------


def planejar(collection_id: int, n_questoes: int, seed: int | None = None) -> Plano:
    """Sorteia trechos privilegiando os menos usados e alternando entre documentos."""
    linhas = db.query(
        """
        SELECT ch.id, ch.heading, ch.texto, ch.n_tokens, ch.times_used,
               ch.pagina_ini, ch.pagina_fim, d.id AS document_id, d.filename
        FROM chunks ch
        JOIN documents d ON d.id = ch.document_id
        WHERE d.collection_id = ? AND d.qualidade_ok = 1
        """,
        (collection_id,),
    )
    if not linhas:
        raise QuizError(
            "Esta colecao nao tem nenhum trecho aproveitavel. "
            "Adicione PDFs na pagina Colecoes e processe-os."
        )

    rng = random.Random(seed)
    por_documento: dict[int, list[Any]] = defaultdict(list)
    for linha in linhas:
        por_documento[linha["document_id"]].append(linha)

    # Dentro de cada documento, o menos usado vem primeiro; o sorteio desempata.
    for candidatos in por_documento.values():
        rng.shuffle(candidatos)
        candidatos.sort(key=lambda r: r["times_used"])

    alvo = max(2, round(n_questoes / QUESTOES_POR_TRECHO))
    teto_tokens = get_settings().max_input_tokens - TOKENS_OVERHEAD_PROMPT

    documentos = list(por_documento)
    rng.shuffle(documentos)

    escolhidos: list[Any] = []
    tokens = 0
    while len(escolhidos) < alvo and any(por_documento[d] for d in documentos):
        for document_id in documentos:
            if not por_documento[document_id] or len(escolhidos) >= alvo:
                continue
            candidato = por_documento[document_id].pop(0)
            if escolhidos and tokens + candidato["n_tokens"] > teto_tokens:
                por_documento[document_id].clear()
                continue
            escolhidos.append(candidato)
            tokens += candidato["n_tokens"]

    if not escolhidos:
        raise QuizError("Nenhum trecho coube no orcamento de tokens configurado.")

    trechos = [
        TrechoPrompt(
            chunk_id=r["id"],
            origem=f"{r['filename']} (p. {r['pagina_ini']}-{r['pagina_fim']})",
            heading=r["heading"] or "",
            texto=r["texto"],
        )
        for r in escolhidos
    ]
    return Plano(trechos=trechos, tokens_estimados=tokens + TOKENS_OVERHEAD_PROMPT)


def estimar_custo(collection_id: int, n_questoes: int) -> int:
    """Tokens de entrada previstos para uma geracao, para exibir antes de gastar."""
    return planejar(collection_id, n_questoes, seed=0).tokens_estimados


# --- validacao --------------------------------------------------------------


def _citacao_confere(citacao: str, texto_chunk: str) -> bool:
    alvo = normalizar(citacao)
    if len(alvo) < 15:
        return False
    return alvo in normalizar(texto_chunk)


def _validar(
    brutas: list[dict[str, Any]],
    trechos: dict[int, TrechoPrompt],
    stems_conhecidos: list[str],
    hashes_conhecidos: set[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    aprovadas: list[dict[str, Any]] = []
    descartadas: list[str] = []
    stems_locais = list(stems_conhecidos)
    hashes_locais = set(hashes_conhecidos)

    for bruta in brutas:
        resumo = " ".join(str(bruta.get("enunciado", "?")).split())[:60]

        chunk_id = bruta.get("chunk_id")
        if chunk_id not in trechos:
            descartadas.append(f"'{resumo}': chunk_id {chunk_id} nao foi enviado ao modelo.")
            continue

        alternativas = [str(a).strip() for a in bruta.get("alternativas", [])]
        if len(alternativas) != 4 or any(not a for a in alternativas):
            descartadas.append(f"'{resumo}': nao tem 4 alternativas preenchidas.")
            continue
        if len({normalizar(a) for a in alternativas}) != 4:
            descartadas.append(f"'{resumo}': alternativas duplicadas.")
            continue

        indice = bruta.get("indice_correto")
        if not isinstance(indice, int) or not 0 <= indice <= 3:
            descartadas.append(f"'{resumo}': indice_correto fora do intervalo.")
            continue

        citacao = str(bruta.get("citacao", "")).strip()
        if not _citacao_confere(citacao, trechos[chunk_id].texto):
            descartadas.append(f"'{resumo}': a citacao nao aparece literalmente no trecho.")
            continue

        enunciado = " ".join(str(bruta.get("enunciado", "")).split())
        if len(enunciado) < 15:
            descartadas.append(f"'{resumo}': enunciado vazio ou curto demais.")
            continue

        stem_hash = hash_enunciado(enunciado)
        if stem_hash in hashes_locais:
            descartadas.append(f"'{resumo}': questao identica ja existe no banco.")
            continue
        if any(_jaccard(enunciado, s) >= LIMIAR_JACCARD for s in stems_locais):
            descartadas.append(f"'{resumo}': questao quase identica a uma ja existente.")
            continue

        hashes_locais.add(stem_hash)
        stems_locais.append(enunciado)
        aprovadas.append(
            {
                "chunk_id": chunk_id,
                "topico": " ".join(str(bruta.get("topico", "geral")).split())[:60] or "geral",
                "enunciado": enunciado,
                "alternativas": alternativas,
                "indice_correto": indice,
                "explicacao": " ".join(str(bruta.get("explicacao", "")).split()),
                "citacao": citacao,
                "stem_hash": stem_hash,
            }
        )

    return aprovadas, descartadas


# --- geracao ----------------------------------------------------------------


def _chamar(
    provider: LLMProvider,
    plano: Plano,
    dificuldade: str,
    n_questoes: int,
    enunciados_existentes: list[str],
) -> tuple[list[dict[str, Any]], int, int]:
    prompt = montar_prompt(plano.trechos, dificuldade, n_questoes, enunciados_existentes)
    resposta = provider.gerar_json(
        INSTRUCAO_SISTEMA, prompt, QuizGerado.model_json_schema()
    )
    questoes = resposta.dados.get("questoes")
    if not isinstance(questoes, list):
        raise QuizError("O modelo nao devolveu a lista 'questoes'.")
    return questoes, resposta.tokens_in, resposta.tokens_out


def gerar(
    collection_id: int,
    dificuldade: str,
    n_questoes: int,
    provider: LLMProvider | None = None,
) -> ResultadoGeracao:
    if not 5 <= n_questoes <= 20:
        raise QuizError("A quantidade de questoes deve estar entre 5 e 20.")

    provider = provider or get_provider()
    hashes_conhecidos = db.collection_stem_hashes(collection_id)
    stems_colecao = db.collection_stems(collection_id)

    plano = planejar(collection_id, n_questoes)
    trechos = {t.chunk_id: t for t in plano.trechos}
    evitar = db.existing_stems(collection_id, list(trechos))

    try:
        brutas, tokens_in, tokens_out = _chamar(
            provider, plano, dificuldade, n_questoes, evitar
        )
    except LLMError as exc:
        raise QuizError(str(exc)) from exc

    aprovadas, descartadas = _validar(brutas, trechos, stems_colecao, hashes_conhecidos)
    chunks_usados = set(trechos)

    # Uma unica rechamada, com outros trechos, para cobrir o que foi descartado.
    if len(aprovadas) < n_questoes:
        faltam = n_questoes - len(aprovadas)
        try:
            plano2 = planejar(collection_id, faltam)
            trechos2 = {t.chunk_id: t for t in plano2.trechos}
            evitar2 = db.existing_stems(collection_id, list(trechos2))
            brutas2, t_in2, t_out2 = _chamar(
                provider, plano2, dificuldade, faltam, evitar2
            )
            tokens_in += t_in2
            tokens_out += t_out2
            extras, descartadas2 = _validar(
                brutas2,
                trechos2,
                stems_colecao + [q["enunciado"] for q in aprovadas],
                hashes_conhecidos | {q["stem_hash"] for q in aprovadas},
            )
            aprovadas.extend(extras[:faltam])
            descartadas.extend(descartadas2)
            chunks_usados |= set(trechos2)
        except (QuizError, LLMError) as exc:
            descartadas.append(f"A tentativa de completar o quiz falhou: {exc}")

    if not aprovadas:
        raise QuizError(
            "Nenhuma questao passou na validacao. Se o motivo for repeticao, a colecao "
            "ja esgotou os angulos obvios destes trechos: adicione mais referencias ou "
            "troque o nivel de dificuldade. Motivos: " + "; ".join(descartadas[:5])
        )

    aprovadas = aprovadas[:n_questoes]
    settings = get_settings()
    quiz_id = db.save_quiz(
        collection_id=collection_id,
        dificuldade=dificuldade,
        questoes=aprovadas,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        modelo=settings.model,
    )
    db.bump_chunk_usage(sorted(chunks_usados))

    return ResultadoGeracao(
        quiz_id=quiz_id,
        n_solicitadas=n_questoes,
        n_geradas=len(aprovadas),
        descartadas=descartadas,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )
