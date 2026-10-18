# Bibliometric Research — Multi-Agent Blueprint

A **reusable, provider-agnostic blueprint** for running an AI-agent-assisted
bibliometric / literature research process. The goal is to gather academic
research on a *study object* and build a **map of distinct viewpoints**, with
full traceability back to verifiable sources.

This repository is a **template**. For every new study you copy it, drop the
study definition into `study/`, and run the pipeline. It is designed so it can
be shared with other people and run against any LLM provider.

---

## Why this structure

The system is deliberately **three agents + a thin orchestrator**:

| Agent          | Role                                                                                           | Sees the web? |
|----------------|------------------------------------------------------------------------------------------------|:-------------:|
| **Retriever**  | Finds and caches evidence from academic sources (and the web). Never writes prose.            | Yes           |
| **Builder**    | Writes the analysis document (MPAs, tech challenges, viewpoints). Uses *only* cached evidence. | **No**        |
| **Critic**     | Reviews the document against the study plan and evidence; suggests improvements.               | No            |

The **Builder never browses**. When it needs something it does not have, it
emits an **evidence request** that the orchestrator routes to the **Retriever**.
This guarantees every claim in the document is backed by a **verifiable,
internally referenced source**.

You (the human) are consulted at explicit checkpoints (see *Human-in-the-loop*
below).

---

## Design principles

1. **Provider-agnostic.** All model calls go through one small interface
   (`core/llm.py`). Adapters for Anthropic, OpenAI, DeepSeek and Google ship in
   the box; add more by implementing one method. The provider is chosen in
   `config.yaml` / environment variables — no other code changes.
2. **Token-optimized by construction.**
   - **Content-addressed local cache** (`cache/`) keyed by a hash of
     (URL / query / file bytes). A source is fetched **once** and reused forever.
   - **Chunked + summarized ingestion**: long PDFs/DOCX are converted to text,
     chunked, and only the relevant chunks are sent to the Builder.
   - **Evidence IDs instead of full text**: agents pass short `ev://…` IDs, not
     whole documents, in their prompts.
3. **Academic-source first.** The Retriever targets indexed sources — **SciELO,
   Scopus, Web of Science, ScienceDirect, Google Scholar** — plus a general web
   fallback. Source adapters live in `agents/retriever/sources.py`.
4. **Traceability & validation.** Every paper becomes a record in
   `registry/papers.jsonl` with a stable ID, DOI/URL, a normalized hash, and a
   metadata block. A `validate` command re-checks that each source still
   resolves (existence validation).
5. **Human-in-the-loop.** The orchestrator pauses at defined checkpoints and
   asks you to confirm/adjust before spending tokens.

---

## Directory layout

```
bibliometric_research/
├── README.md                # this file
├── PLAN.md                  # the plan / methodology (start here)
├── config.example.yaml      # non-secret configuration (copy to config.yaml)
├── .env.example             # secrets (API keys) — never commit .env
├── requirements.txt
│
├── study/                   # ← per-study: copy this template for each study
│   ├── brief.md             # the study object & the questions you ask
│   ├── workplan.md          # what the document must contain (MPAs, challenges…)
│   └── viewpoints.yaml      # optional seed list of expected viewpoints
│
├── core/
│   ├── llm.py               # provider-agnostic LLM interface + adapters
│   ├── cache.py             # content-addressed local cache
│   ├── registry.py          # paper registry (traceability + IDs)
│   ├── evidence.py          # evidence items + ev:// IDs
│   └── orchestrator.py      # runs the 3 agents, handles checkpoints
│
├── agents/
│   ├── retriever/           # Agent 1 — collects + caches evidence
│   │   ├── agent.py
│   │   ├── sources.py       # SciELO / Scopus / WoS / ScienceDirect / Scholar / web
│   │   └── fetch.py         # URL/PDF/DOCX/HTML → clean text (cached)
│   ├── builder/             # Agent 2 — writes the document from evidence only
│   │   └── agent.py
│   └── critic/              # Agent 3 — reviews and suggests improvements
│       └── agent.py
│
├── prompts/                 # provider-agnostic prompt templates
│   ├── retriever.md
│   ├── builder.md
│   └── critic.md
│
├── registry/                # generated: papers.jsonl, evidence.jsonl
├── cache/                   # generated: raw fetches + extracted text
└── output/                  # generated: document drafts, reviews, viewpoint map
```

`cache/`, `registry/`, `output/` and `config.yaml` / `.env` are **generated** and
not meant to be committed.

---

## Quick start

```bash
# 1. Configure
cp config.example.yaml config.yaml

# then export the API key for your chosen provider, e.g.:
#   export ANTHROPIC_API_KEY=sk-...
# (env vars to set are listed at the top of config.example.yaml)

# 2. (optional) install PDF/DOCX text extraction helpers
pip install -r requirements.txt

# 3. Describe your study
#    edit study/brief.md and study/workplan.md

# 4. Run the pipeline (starts with a human checkpoint)
python -m core.orchestrator --study study/

# 5. Validate that every cited source still exists
python -m core.registry validate registry/papers.jsonl
```

No key configured? The system runs with a **`mock` provider** that returns
deterministic placeholder output, so you can test the whole flow for free.

---

## Human-in-the-loop checkpoints

The orchestrator stops and asks you at these points (all confirmable via CLI
prompt or by editing a JSON file in `output/`):

1. **After brief review** — confirm the study object, questions, and the
   search strategy / sources before any fetching.
2. **After retrieval round** — review the evidence list and paper registry;
   add/remove sources before the Builder runs.
3. **After each Builder draft** — review before the Critic runs.
4. **After Critic review** — decide whether to iterate (and on what focus).

Set `checkpoints.enabled: false` in `config.yaml` to run unattended.

---

## Extending

- **New LLM provider** → add an adapter in `core/llm.py`.
- **New academic source** → add a function in `agents/retriever/sources.py`
  returning normalized candidate records.
- **New per-study flavor** → copy `study/`, tweak `workplan.md` and
  `viewpoints.yaml`. No engine code changes required.

See **PLAN.md** for the full methodology and rationale.
