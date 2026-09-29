"""Historico de quizzes e navegacao pelo banco de questoes."""

from __future__ import annotations

import json
from datetime import datetime

import pandas as pd
import streamlit as st

from study import db, scoring, ui
from study.models import ROTULO_DIFICULDADE

ui.preparar("Historico")
ui.barra_lateral_status()


def data_legivel(iso: str | None) -> str:
    if not iso:
        return "-"
    return datetime.fromisoformat(iso).astimezone().strftime("%d/%m/%Y %H:%M")


colecao = ui.seletor_de_colecao("colecao_historico", incluir_todas=True)
colecoes = db.list_collections()
if not colecoes:
    st.stop()

collection_id = colecao["id"] if colecao else None

aba_quizzes, aba_banco = st.tabs(["Quizzes realizados", "Banco de questoes"])

with aba_quizzes:
    quizzes = db.list_quizzes(collection_id)
    if not quizzes:
        st.info("Nenhum quiz concluido ainda.")
    else:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "#": q["id"],
                        "Data": data_legivel(q["finalizado_em"]),
                        "Colecao": q["colecao"],
                        "Nivel": ROTULO_DIFICULDADE.get(q["dificuldade"], q["dificuldade"]),
                        "Questoes": q["n_questoes"],
                        "Score": ui.formatar_score(q["score"]),
                    }
                    for q in quizzes
                ]
            ),
            hide_index=True,
            width="stretch",
        )

        # Opcoes sao ids: o Streamlit faz deepcopy do valor e `sqlite3.Row` nao e copiavel.
        por_id = {q["id"]: q for q in quizzes}

        def rotulo_quiz(quiz_id: int) -> str:
            q = por_id[quiz_id]
            nivel = ROTULO_DIFICULDADE.get(q["dificuldade"], q["dificuldade"])
            return (
                f"#{q['id']} - {data_legivel(q['finalizado_em'])} - {q['colecao']} - "
                f"{nivel} - score {ui.formatar_score(q['score'])}"
            )

        escolhido = st.selectbox("Rever um quiz", list(por_id), format_func=rotulo_quiz)

        if escolhido is not None:
            correcao = scoring.carregar_correcao(escolhido)
            if correcao is None:
                st.warning("Este quiz nao tem correcao gravada.")
            else:
                ui.mostrar_correcao(correcao)

            if st.button("Excluir este quiz"):
                if st.session_state.get("confirmar_quiz") == escolhido:
                    db.delete_quiz(escolhido)
                    st.session_state.pop("confirmar_quiz", None)
                    st.rerun()
                else:
                    st.session_state["confirmar_quiz"] = escolhido
                    st.warning(
                        "As questoes continuam no banco, so a tentativa e apagada. "
                        "Clique de novo para confirmar."
                    )

with aba_banco:
    if collection_id is None:
        st.info("Escolha uma colecao especifica para navegar pelo banco de questoes.")
    else:
        c1, c2 = st.columns(2)
        nivel = c1.selectbox(
            "Nivel",
            [None, *ROTULO_DIFICULDADE],
            format_func=lambda d: "Todos" if d is None else ROTULO_DIFICULDADE[d],
        )
        topicos = db.bank_topics(collection_id)
        topico = c2.selectbox(
            "Topico", [None, *topicos], format_func=lambda t: "Todos" if t is None else t
        )

        questoes = db.list_bank_questions(collection_id, nivel, topico)
        if not questoes:
            st.info("Nenhuma questao no banco com esses filtros.")
        else:
            st.caption(f"{len(questoes)} questao(oes) acumulada(s) para esta colecao.")
            for q in questoes:
                alternativas = json.loads(q["alternativas_json"])
                rotulo_nivel = ROTULO_DIFICULDADE.get(q["dificuldade"], q["dificuldade"])
                with st.expander(f"[{rotulo_nivel}] {q['enunciado']}"):
                    for i, alternativa in enumerate(alternativas):
                        texto = ui.alternativa_rotulada(i, alternativa)
                        st.markdown(
                            f"**{texto}** _(correta)_" if i == q["indice_correto"] else texto
                        )
                    st.info(q["explicacao"])
                    st.markdown(f"> {q['citacao']}")
                    origem = (
                        f"{q['filename']}, p. {q['pagina_ini']}-{q['pagina_fim']}"
                        if q["filename"]
                        else "fonte removida"
                    )
                    st.caption(f"Fonte: {origem} | Topico: {q['topico']}")
