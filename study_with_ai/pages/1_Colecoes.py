"""Gerenciamento de colecoes e ingestao dos PDFs."""

from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from study import db, ui
from study.ingest import pipeline

ui.preparar("Colecoes")
ui.barra_lateral_status()

st.caption(
    "Uma colecao agrupa as referencias de uma disciplina. Os PDFs sao parseados "
    "uma unica vez e o texto fica em cache para as proximas geracoes de quiz."
)

with st.expander("Criar nova colecao", expanded=not db.list_collections()):
    with st.form("nova_colecao"):
        nome = st.text_input("Nome da colecao", placeholder="Etica - Kant")
        if st.form_submit_button("Criar") and nome.strip():
            try:
                db.create_collection(nome)
                st.rerun()
            except sqlite3.IntegrityError:
                st.error(f"Ja existe uma colecao chamada '{nome.strip()}'.")

colecao = ui.seletor_de_colecao("colecao_ingestao")
if colecao is None:
    st.stop()

collection_id = colecao["id"]

st.subheader("Adicionar referencias")
arquivos = st.file_uploader(
    "PDFs com texto embutido (PDFs digitalizados nao sao suportados)",
    type="pdf",
    accept_multiple_files=True,
    key=f"upload_{collection_id}",
)

if arquivos and st.button("Processar", type="primary"):
    barra = st.progress(0.0, text="Processando...")
    for i, arquivo in enumerate(arquivos, start=1):
        barra.progress((i - 1) / len(arquivos), text=f"Processando {arquivo.name}...")
        resultado = pipeline.ingerir_bytes(collection_id, arquivo.name, arquivo.getvalue())
        if resultado.ja_existia:
            st.info(f"**{arquivo.name}**: {resultado.mensagem}")
        elif resultado.qualidade_ok:
            st.success(
                f"**{arquivo.name}**: {resultado.n_paginas} paginas, "
                f"{resultado.n_chunks} trechos, ~{resultado.n_tokens} tokens."
            )
        else:
            st.error(f"**{arquivo.name}**: {resultado.mensagem}")
    barra.progress(1.0, text="Concluido.")

st.subheader("Referencias da colecao")
documentos = db.list_documents(collection_id)

if not documentos:
    st.info("Nenhuma referencia processada nesta colecao ainda.")
else:
    tabela = pd.DataFrame(
        [
            {
                "Arquivo": d["filename"],
                "Paginas": d["n_paginas"],
                "Trechos": d["n_chunks"],
                "Tokens (aprox.)": d["n_tokens"],
                "Qualidade": "OK" if d["qualidade_ok"] else "Problema",
            }
            for d in documentos
        ]
    )
    st.dataframe(tabela, hide_index=True, width="stretch")

    for d in documentos:
        if not d["qualidade_ok"]:
            st.warning(f"**{d['filename']}**: {d['qualidade_msg']}")

    st.divider()
    for d in documentos:
        with st.expander(f"{d['filename']}"):
            c1, c2 = st.columns(2)
            if c1.button("Reprocessar", key=f"reproc_{d['id']}"):
                with st.spinner("Reprocessando..."):
                    try:
                        resultado = pipeline.reprocessar(d["id"])
                        st.success(resultado.mensagem)
                    except (ValueError, FileNotFoundError) as exc:
                        st.error(str(exc))
                st.rerun()
            if c2.button("Remover", key=f"rem_{d['id']}"):
                pipeline.remover_documento(d["id"])
                st.rerun()

            texto = pipeline.texto_parseado(d["id"])
            if texto:
                st.text_area(
                    "Previa do texto parseado",
                    texto[:3000],
                    height=260,
                    key=f"previa_{d['id']}",
                )
                st.download_button(
                    "Baixar texto completo",
                    texto,
                    file_name=f"{d['filename'].removesuffix('.pdf')}.md",
                    key=f"dl_{d['id']}",
                )

st.divider()
with st.expander("Renomear ou excluir a colecao"):
    novo_nome = st.text_input("Novo nome", value=colecao["nome"], key="rename")
    c1, c2 = st.columns(2)
    if c1.button("Renomear") and novo_nome.strip() != colecao["nome"]:
        try:
            db.rename_collection(collection_id, novo_nome)
            st.rerun()
        except sqlite3.IntegrityError:
            st.error("Ja existe uma colecao com esse nome.")
    if c2.button("Excluir colecao", type="secondary"):
        if st.session_state.get("confirmar_exclusao") == collection_id:
            for d in db.list_documents(collection_id):
                pipeline.remover_documento(d["id"])
            db.delete_collection(collection_id)
            st.session_state.pop("confirmar_exclusao", None)
            st.rerun()
        else:
            st.session_state["confirmar_exclusao"] = collection_id
            st.warning(
                "Isto apaga os PDFs, as questoes e o historico desta colecao. "
                "Clique de novo para confirmar."
            )
