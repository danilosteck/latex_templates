"""Divisao do texto limpo em chunks com sobreposicao, respeitando headings."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from study.ingest.extract import PaginaExtraida
from study.tokens import estimar_tokens

TOKENS_ALVO = 1000
TOKENS_SOBREPOSICAO = 120
TOKENS_MINIMO = 120

RE_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
RE_MARCACAO = re.compile(r"[*_`]+")


@dataclass
class Bloco:
    texto: str
    pagina: int
    heading: str
    tokens: int


@dataclass
class Chunk:
    ordem: int
    pagina_ini: int
    pagina_fim: int
    heading: str
    texto: str
    n_tokens: int


@dataclass
class _Acumulador:
    blocos: list[Bloco] = field(default_factory=list)

    @property
    def tokens(self) -> int:
        return sum(b.tokens for b in self.blocos)

    def fechar(self, ordem: int) -> Chunk:
        texto = "\n\n".join(b.texto for b in self.blocos).strip()
        paginas = [b.pagina for b in self.blocos]
        return Chunk(
            ordem=ordem,
            pagina_ini=min(paginas),
            pagina_fim=max(paginas),
            heading=self.blocos[0].heading,
            texto=texto,
            n_tokens=estimar_tokens(texto),
        )


def _caminho_heading(pilha: list[tuple[int, str]]) -> str:
    return " > ".join(titulo for _, titulo in pilha)


def _blocos(paginas: list[PaginaExtraida]) -> list[Bloco]:
    """Achata as paginas em paragrafos, carregando o caminho de headings vigente."""
    pilha: list[tuple[int, str]] = []
    saida: list[Bloco] = []

    for pagina in paginas:
        for paragrafo in pagina.texto.split("\n\n"):
            paragrafo = paragrafo.strip()
            if not paragrafo:
                continue

            primeira = paragrafo.splitlines()[0].strip()
            cabecalho = RE_HEADING.match(primeira)
            if cabecalho:
                nivel = len(cabecalho.group(1))
                titulo = RE_MARCACAO.sub("", cabecalho.group(2)).strip()
                while pilha and pilha[-1][0] >= nivel:
                    pilha.pop()
                if titulo:
                    pilha.append((nivel, titulo))

            saida.append(
                Bloco(
                    texto=paragrafo,
                    pagina=pagina.numero,
                    heading=_caminho_heading(pilha),
                    tokens=estimar_tokens(paragrafo),
                )
            )
    return saida


def _sobreposicao(blocos: list[Bloco]) -> list[Bloco]:
    """Ultimos paragrafos do chunk anterior, ate o orcamento de sobreposicao.

    Um paragrafo maior que o orcamento nunca e carregado: ele encheria o chunk
    seguinte sozinho e seria arrastado indefinidamente.
    """
    carregados: list[Bloco] = []
    total = 0
    for bloco in reversed(blocos):
        if bloco.tokens > TOKENS_SOBREPOSICAO or total + bloco.tokens > TOKENS_SOBREPOSICAO:
            break
        carregados.insert(0, bloco)
        total += bloco.tokens
    # Nunca repetir o chunk inteiro: isso duplicaria conteudo indefinidamente.
    if len(carregados) >= len(blocos):
        carregados = carregados[1:]
    return carregados


def dividir(paginas: list[PaginaExtraida]) -> list[Chunk]:
    blocos = _blocos(paginas)
    if not blocos:
        return []

    chunks: list[Chunk] = []
    atual = _Acumulador()

    for bloco in blocos:
        # Um paragrafo maior que o alvo vira um chunk sozinho, sem quebrar frase.
        if bloco.tokens >= TOKENS_ALVO:
            if atual.blocos:
                chunks.append(atual.fechar(len(chunks)))
            atual = _Acumulador(blocos=[bloco])
            chunks.append(atual.fechar(len(chunks)))
            atual = _Acumulador()
            continue

        atual.blocos.append(bloco)
        if atual.tokens >= TOKENS_ALVO:
            chunks.append(atual.fechar(len(chunks)))
            atual = _Acumulador(blocos=_sobreposicao(atual.blocos))

    if atual.blocos:
        sobra = atual.fechar(len(chunks))
        # Uma cauda minuscula se funde ao chunk anterior em vez de virar chunk proprio.
        if sobra.n_tokens < TOKENS_MINIMO and chunks:
            anterior = chunks[-1]
            texto = f"{anterior.texto}\n\n{sobra.texto}"
            chunks[-1] = Chunk(
                ordem=anterior.ordem,
                pagina_ini=anterior.pagina_ini,
                pagina_fim=max(anterior.pagina_fim, sobra.pagina_fim),
                heading=anterior.heading,
                texto=texto,
                n_tokens=estimar_tokens(texto),
            )
        else:
            chunks.append(sobra)

    return chunks
