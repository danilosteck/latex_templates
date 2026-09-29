"""Evolucao do desempenho ao longo do tempo."""

from __future__ import annotations

import altair as alt
import streamlit as st

from study import db, stats, ui

ui.preparar("Progresso")
ui.barra_lateral_status()

ESCALA_SCORE = alt.Scale(domain=[0, 1])

if not db.list_collections():
    st.info("Crie uma colecao e responda alguns quizzes para ver sua evolucao.")
    st.stop()

colecao = ui.seletor_de_colecao("colecao_progresso", incluir_todas=True)
collection_id = colecao["id"] if colecao else None

historico = stats.historico_quizzes(collection_id)
if historico.empty:
    st.info("Nenhum quiz concluido ainda com esse filtro.")
    st.stop()

totais = stats.totais(collection_id)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Quizzes", totais["quizzes"])
c2.metric("Questoes", totais["questoes"])
c3.metric("Score medio", ui.formatar_score(totais["score_medio"]))
c4.metric("Ultimo score", ui.formatar_score(historico["score"].iloc[-1]))

st.divider()
st.subheader("Evolucao geral")

base = alt.Chart(historico).encode(
    x=alt.X("data:T", title="Data"),
    tooltip=[
        alt.Tooltip("id:Q", title="Quiz"),
        alt.Tooltip("data:T", title="Data"),
        alt.Tooltip("colecao:N", title="Colecao"),
        alt.Tooltip("dificuldade:N", title="Nivel"),
        alt.Tooltip("score:Q", title="Score", format=".2f"),
    ],
)
pontos = base.mark_circle(size=90).encode(
    y=alt.Y("score:Q", title="Score", scale=ESCALA_SCORE),
    color=alt.Color("dificuldade:N", title="Nivel"),
)
linha_media = base.mark_line(strokeDash=[6, 4], color="gray").encode(
    y=alt.Y("media_movel:Q", scale=ESCALA_SCORE)
)
st.altair_chart(pontos + linha_media, width="stretch")
st.caption("Cada ponto e um quiz. A linha tracejada e a media movel dos ultimos 5 quizzes.")

st.divider()
st.subheader("Por nivel de dificuldade")

por_nivel = stats.evolucao_por_dificuldade(historico)
grafico_nivel = (
    alt.Chart(por_nivel)
    .mark_line(point=True)
    .encode(
        x=alt.X("data:T", title="Data"),
        y=alt.Y("media_movel_nivel:Q", title="Score (media movel)", scale=ESCALA_SCORE),
        color=alt.Color("dificuldade:N", title="Nivel"),
        tooltip=[
            alt.Tooltip("data:T", title="Data"),
            alt.Tooltip("dificuldade:N", title="Nivel"),
            alt.Tooltip("score:Q", title="Score", format=".2f"),
            alt.Tooltip("media_movel_nivel:Q", title="Media movel", format=".2f"),
        ],
    )
)
st.altair_chart(grafico_nivel, width="stretch")

resumo_nivel = stats.resumo_por_dificuldade(collection_id)
if not resumo_nivel.empty:
    st.dataframe(
        resumo_nivel.rename(
            columns={
                "dificuldade": "Nivel",
                "quizzes": "Quizzes",
                "score_medio": "Score medio",
                "questoes": "Questoes",
            }
        ).style.format({"Score medio": "{:.2f}"}),
        hide_index=True,
        width="stretch",
    )

st.divider()
st.subheader("Por colecao")

resumo_colecao = stats.resumo_por_colecao()
if resumo_colecao.empty:
    st.info("Sem dados por colecao.")
else:
    grafico_colecao = (
        alt.Chart(resumo_colecao)
        .mark_bar()
        .encode(
            x=alt.X("score_medio:Q", title="Score medio", scale=ESCALA_SCORE),
            y=alt.Y("colecao:N", title="", sort="x"),
            tooltip=[
                alt.Tooltip("colecao:N", title="Colecao"),
                alt.Tooltip("quizzes:Q", title="Quizzes"),
                alt.Tooltip("score_medio:Q", title="Score medio", format=".2f"),
            ],
        )
    )
    st.altair_chart(grafico_colecao, width="stretch")

st.divider()
st.subheader("Topicos mais fracos")

topicos = stats.acuracia_por_topico(collection_id)
if topicos.empty:
    st.info(
        f"Ainda nao ha topicos com pelo menos {stats.MIN_RESPOSTAS_POR_TOPICO} "
        "questoes respondidas."
    )
else:
    grafico_topicos = (
        alt.Chart(topicos.head(15))
        .mark_bar()
        .encode(
            x=alt.X("acuracia:Q", title="Acuracia", scale=ESCALA_SCORE),
            y=alt.Y("topico:N", title="", sort="x"),
            tooltip=[
                alt.Tooltip("topico:N", title="Topico"),
                alt.Tooltip("respondidas:Q", title="Respondidas"),
                alt.Tooltip("acertos:Q", title="Acertos"),
                alt.Tooltip("acuracia:Q", title="Acuracia", format=".2f"),
            ],
        )
    )
    st.altair_chart(grafico_topicos, width="stretch")
    st.caption(
        f"Apenas topicos com {stats.MIN_RESPOSTAS_POR_TOPICO} ou mais questoes "
        "respondidas aparecem aqui."
    )
