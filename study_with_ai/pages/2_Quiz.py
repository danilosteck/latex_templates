"""Geracao e resposta de um quiz."""

from __future__ import annotations

import streamlit as st

from study import db, quiz, scoring, ui
from study.config import get_settings
from study.models import ROTULO_DIFICULDADE

ui.preparar("Quiz")
ui.barra_lateral_status()

EM_BRANCO = "(em branco)"

colecao = ui.seletor_de_colecao("colecao_quiz")
if colecao is None:
    st.stop()

collection_id = colecao["id"]
estatisticas = db.collection_chunk_stats(collection_id)
if not estatisticas or not estatisticas["n_chunks"]:
    st.warning("Esta colecao nao tem trechos processados. Suba PDFs na pagina Colecoes.")
    st.stop()

# Trocar de colecao invalida o quiz em andamento.
if st.session_state.get("quiz_colecao") != collection_id:
    st.session_state.pop("quiz_id", None)
    st.session_state.pop("quiz_corrigido", None)
    st.session_state["quiz_colecao"] = collection_id

st.subheader("Configurar")
c1, c2 = st.columns(2)
dificuldade = c1.radio(
    "Nivel de dificuldade",
    list(ROTULO_DIFICULDADE),
    format_func=lambda d: ROTULO_DIFICULDADE[d],
    horizontal=True,
)
n_questoes = c2.slider("Quantidade de questoes", min_value=5, max_value=20, value=10)

try:
    tokens = quiz.estimar_custo(collection_id, n_questoes)
    st.caption(
        f"Estimativa: ~{tokens} tokens de entrada nesta geracao "
        f"({estatisticas['n_chunks']} trechos disponiveis na colecao)."
    )
except quiz.QuizError as exc:
    st.error(str(exc))
    st.stop()

if not get_settings().is_configured:
    st.error("Configure a chave de API no arquivo `.env` para gerar questoes.")
    st.stop()

if st.button("Gerar quiz", type="primary"):
    with st.spinner("Gerando questoes..."):
        try:
            resultado = quiz.gerar(collection_id, dificuldade, n_questoes)
        except quiz.QuizError as exc:
            st.error(str(exc))
            st.stop()

    st.session_state["quiz_id"] = resultado.quiz_id
    st.session_state["quiz_corrigido"] = None
    st.session_state["quiz_avisos"] = resultado.descartadas
    if resultado.n_geradas < resultado.n_solicitadas:
        st.session_state["quiz_avisos"] = [
            f"Foram geradas {resultado.n_geradas} das {resultado.n_solicitadas} "
            "questoes pedidas; as demais nao passaram na validacao.",
            *resultado.descartadas,
        ]
    st.rerun()

quiz_id = st.session_state.get("quiz_id")
if not quiz_id:
    st.info("Configure o nivel e a quantidade, depois gere o quiz.")
    st.stop()

for aviso in st.session_state.get("quiz_avisos") or []:
    st.warning(aviso)

st.divider()
questoes = db.quiz_questions(quiz_id)
corrigido = st.session_state.get("quiz_corrigido")
# O nivel vem do quiz gravado, nao do seletor, que o usuario pode ter mexido depois.
nivel_do_quiz = ROTULO_DIFICULDADE.get(db.get_quiz(quiz_id)["dificuldade"], "")

if corrigido is None:
    st.subheader(f"Quiz #{quiz_id} - {nivel_do_quiz}")
    with st.form(f"respostas_{quiz_id}"):
        escolhas: dict[int, int | None] = {}
        for questao in questoes:
            st.markdown(f"**{questao['posicao'] + 1}. {questao['enunciado']}**")
            opcoes = [EM_BRANCO, *range(len(questao["alternativas"]))]
            escolha = st.radio(
                "Resposta",
                opcoes,
                format_func=lambda o, q=questao: (
                    o if o == EM_BRANCO else ui.alternativa_rotulada(o, q["alternativas"][o])
                ),
                key=f"q_{quiz_id}_{questao['id']}",
                label_visibility="collapsed",
            )
            escolhas[questao["id"]] = None if escolha == EM_BRANCO else escolha
            st.write("")

        if st.form_submit_button("Enviar respostas", type="primary"):
            st.session_state["quiz_corrigido"] = scoring.corrigir(quiz_id, escolhas)
            st.rerun()
else:
    st.subheader(f"Resultado do quiz #{quiz_id}")
    ui.mostrar_correcao(corrigido)
    if st.button("Novo quiz"):
        st.session_state.pop("quiz_id", None)
        st.session_state.pop("quiz_corrigido", None)
        st.session_state.pop("quiz_avisos", None)
        st.rerun()
