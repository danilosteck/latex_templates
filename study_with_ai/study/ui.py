"""Helpers compartilhados pelas paginas do Streamlit."""

from __future__ import annotations

import sqlite3

import streamlit as st

from study import db
from study.config import get_settings

CONFIG_PAGINA = {"page_icon": "📚", "layout": "wide"}


def preparar(titulo: str) -> None:
    st.set_page_config(page_title=f"{titulo} - Estudo com IA", **CONFIG_PAGINA)
    db.init_db()
    st.title(titulo)


def barra_lateral_status() -> None:
    settings = get_settings()
    with st.sidebar:
        st.caption("Provedor de LLM")
        if settings.is_configured:
            st.success(f"{settings.provider} / {settings.model}")
        else:
            st.error(
                f"Sem chave de API. Preencha `{settings.api_key_env_var}` no arquivo "
                "`.env` na raiz do projeto e recarregue a pagina."
            )


def seletor_de_colecao(
    chave: str, rotulo: str = "Colecao", incluir_todas: bool = False
) -> sqlite3.Row | None:
    """Devolve a colecao escolhida, ou None quando 'Todas' esta selecionada.

    As opcoes do widget sao ids, nao linhas do banco: o Streamlit faz deepcopy
    do valor selecionado, e `sqlite3.Row` nao e copiavel.
    """
    colecoes = db.list_collections()
    if not colecoes:
        st.info("Nenhuma colecao ainda. Crie uma na pagina **Colecoes**.")
        return None

    por_id = {c["id"]: c for c in colecoes}
    opcoes: list[int | None] = list(por_id)
    if incluir_todas:
        opcoes = [None, *opcoes]

    escolhido = st.selectbox(
        rotulo,
        opcoes,
        format_func=lambda i: "Todas as colecoes" if i is None else por_id[i]["nome"],
        key=chave,
    )
    return None if escolhido is None else por_id[escolhido]


def formatar_score(score: float | None) -> str:
    return "-" if score is None else f"{score:.2f}"


LETRAS = ["A", "B", "C", "D"]


def alternativa_rotulada(indice: int, texto: str) -> str:
    letra = LETRAS[indice] if indice < len(LETRAS) else str(indice)
    return f"{letra}) {texto}"


def _fonte(questao: dict) -> str:
    if not questao.get("filename"):
        return "fonte removida"
    return f"{questao['filename']}, p. {questao['pagina_ini']}-{questao['pagina_fim']}"


def mostrar_correcao(correcao) -> None:
    """Renderiza o gabarito comentado de um quiz ja corrigido."""
    c1, c2 = st.columns([1, 3])
    c1.metric("Score", f"{correcao.score:.2f}")
    c2.metric("Acertos", f"{correcao.acertos} de {correcao.total}")

    for item in correcao.itens:
        questao = item.questao
        marca = "Acertou" if item.acertou else "Errou"
        with st.expander(f"{item.posicao + 1}. [{marca}] {questao['enunciado']}", expanded=True):
            for i, alternativa in enumerate(questao["alternativas"]):
                rotulo = alternativa_rotulada(i, alternativa)
                if i == questao["indice_correto"]:
                    st.markdown(f"**{rotulo}** _(correta)_")
                elif i == item.escolhido:
                    st.markdown(f"~~{rotulo}~~ _(sua resposta)_")
                else:
                    st.markdown(rotulo)

            if item.escolhido is None:
                st.caption("Deixada em branco.")

            st.info(questao["explicacao"])
            st.markdown(f"> {questao['citacao']}")
            st.caption(f"Fonte: {_fonte(questao)} | Topico: {questao['topico']}")
