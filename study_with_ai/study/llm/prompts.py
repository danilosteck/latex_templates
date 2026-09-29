"""Prompts em pt-BR para geracao das questoes."""

from __future__ import annotations

from dataclasses import dataclass

MAX_CARACTERES_ENUNCIADO_EXISTENTE = 90
MAX_ENUNCIADOS_EXISTENTES = 40

INSTRUCAO_SISTEMA = """Voce e um professor de filosofia que elabora questoes de \
multipla escolha em portugues do Brasil, no nivel de graduacao.

Regras obrigatorias:
1. Toda questao deve ser respondivel apenas com os trechos fornecidos. Nunca use \
conhecimento externo aos trechos.
2. Cada questao tem exatamente 4 alternativas, das quais apenas uma esta correta.
3. Os distratores devem ser plausiveis e do mesmo tamanho aproximado da alternativa \
correta. Nao use "todas as anteriores", "nenhuma das anteriores" nem alternativas \
absurdas.
4. O enunciado nao pode conter a resposta nem pistas gramaticais que a denunciem.
5. O campo "citacao" deve ser copiado LITERALMENTE do trecho indicado em chunk_id, \
palavra por palavra, com 1 a 3 frases. Nao parafraseie, nao corrija, nao abrevie.
6. O campo "chunk_id" deve ser exatamente um dos ids fornecidos.
7. A "explicacao" tem 1 a 3 frases e justifica por que a alternativa correta e correta.
8. O "topico" e um tema curto, de ate 4 palavras, usado para agrupar questoes.
9. Varie o trecho de origem entre as questoes; nao concentre tudo em um unico chunk.
10. Escreva tudo em portugues do Brasil."""

DEFINICOES_DIFICULDADE = {
    "facil": """Nivel FACIL: identificacao direta. A questao cobra o reconhecimento de \
um conceito, de uma definicao ou de uma tese afirmada explicitamente no texto. \
Quem leu o trecho com atencao responde sem inferencia.""",
    "moderado": """Nivel MODERADO: compreensao. A questao cobra a relacao entre dois \
conceitos, a consequencia de um argumento, a distincao entre posicoes proximas ou a \
reformulacao correta de uma tese. Exige entender o texto, nao so localizar a frase.""",
    "dificil": """Nivel DIFICIL: analise. A questao cobra a aplicacao da tese a um caso \
novo, a identificacao de um pressuposto implicito, o contraste entre autores ou \
posicoes, ou a objecao pertinente a um argumento. Os distratores devem representar \
erros de interpretacao verossimeis.""",
}


@dataclass
class TrechoPrompt:
    chunk_id: int
    origem: str
    heading: str
    texto: str


def _bloco_trechos(trechos: list[TrechoPrompt]) -> str:
    partes = []
    for t in trechos:
        cabecalho = f"[chunk_id={t.chunk_id}] {t.origem}"
        if t.heading:
            cabecalho += f" - {t.heading}"
        partes.append(f"{cabecalho}\n{t.texto}")
    return "\n\n---\n\n".join(partes)


def _bloco_evitar(enunciados: list[str]) -> str:
    if not enunciados:
        return ""
    itens = []
    for enunciado in enunciados[:MAX_ENUNCIADOS_EXISTENTES]:
        texto = " ".join(enunciado.split())
        if len(texto) > MAX_CARACTERES_ENUNCIADO_EXISTENTE:
            texto = texto[:MAX_CARACTERES_ENUNCIADO_EXISTENTE].rstrip() + "..."
        itens.append(f"- {texto}")
    return (
        "\nQuestoes ja aplicadas sobre este material (aborde outros aspectos, "
        "nao repita nem reformule estas):\n" + "\n".join(itens) + "\n"
    )


def montar_prompt(
    trechos: list[TrechoPrompt],
    dificuldade: str,
    n_questoes: int,
    enunciados_existentes: list[str],
) -> str:
    return (
        f"{DEFINICOES_DIFICULDADE[dificuldade]}\n\n"
        f"Elabore {n_questoes} questoes de multipla escolha no nivel indicado, "
        f"a partir dos trechos abaixo.\n"
        f"{_bloco_evitar(enunciados_existentes)}"
        f"\nTRECHOS:\n\n{_bloco_trechos(trechos)}"
    )
