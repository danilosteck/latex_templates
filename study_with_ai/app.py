"""Pagina inicial do app de estudo."""

from __future__ import annotations

import streamlit as st

from study import db, stats, ui

ui.preparar("Estudo com IA")
ui.barra_lateral_status()

st.markdown(
    "Gere questoes de multipla escolha a partir das suas referencias de filosofia, "
    "responda e acompanhe a evolucao ao longo do tempo."
)

totais = stats.totais()
colecoes = db.list_collections()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Colecoes", len(colecoes))
c2.metric("Quizzes concluidos", totais["quizzes"])
c3.metric("Questoes respondidas", totais["questoes"])
c4.metric("Score medio", ui.formatar_score(totais["score_medio"] or None))

st.divider()

if not colecoes:
    st.info(
        "Comece pela pagina **Colecoes**: crie uma colecao (por exemplo, "
        "`Etica - Kant`) e suba os PDFs da disciplina."
    )
else:
    st.subheader("Suas colecoes")
    for c in colecoes:
        st.write(
            f"**{c['nome']}** - {c['n_documentos']} documento(s), {c['n_chunks']} trecho(s)"
        )

st.divider()
st.caption(
    f"Consumo acumulado do LLM: {totais['tokens_in']:,} tokens de entrada e "
    f"{totais['tokens_out']:,} de saida.".replace(",", ".")
)
