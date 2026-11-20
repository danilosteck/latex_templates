# Bibliometric Studio

Turns the prompt-only blueprint in `../bibliometric_research_nocode/` and the CLI in
`../bibliometric_research/` into one local app: a form, projects, an editable agent
set, a run console with checkpoints, and a cited document with a deterministic
verification report.

Design and rationale: `../APP_PLAN.md` (read §1 and §8 before changing the agent
format).

---

## Run it

```bash
cd app
uv venv --python 3.12 .venv
. .venv/bin/activate
uv pip install -e ".[dev,pdf]"

bibstudio serve            # opens http://127.0.0.1:8765/
bibstudio serve --reload    # dev: restart on backend code changes
```

Useful commands:

```bash
bibstudio doctor                                  # self-test: workspace, key, network, UI bundle
bibstudio run --project my-slug --no-checkpoints  # headless run from the terminal
python -m pytest                                  # engine tests, no network
```

Environment:

- `BIBSTUDIO_HOME` — workspace location (default `~/BibliometricStudio`).
- `BIBSTUDIO_API_KEY` — takes precedence over the stored key.

The app binds `127.0.0.1` only and rejects non-local `Host` headers.

---

## Running a local model (Ollama)

No API key, no cost, and nothing leaves the machine.

```bash
# 1. install (Linux shown; macOS/Windows: download from ollama.com)
curl -fsSL https://ollama.com/install.sh | sh

# 2. start it with a context window large enough for the evidence block
OLLAMA_CONTEXT_LENGTH=8192 ollama serve &

# 3. pull a model that fits your RAM
ollama pull qwen2.5:7b        # ~5 GB, good default for 16 GB RAM
#   llama3.2:3b   ~2 GB, 8 GB RAM
#   qwen2.5:14b   ~9 GB, 32 GB RAM

# 4. in the app: Settings → provider "Ollama / LM Studio (local)" → "Detectar modelos"
```

Notes that matter in practice:

- The default Ollama context is 2048 tokens; the author prompt plus evidence is
  usually larger, so start it with `OLLAMA_CONTEXT_LENGTH=8192` or the model sees a
  truncated evidence block and cites less.
- Small models are weaker at the strict JSON the researcher/critic use. That
  degrades gracefully (the run continues with a warning) — but read the Review tab.
- Set the request timeout in Settings to 300–600s: a 7B model on CPU needs minutes
  for a long section. Cost shows as US$ 0.00.

---

## When a search finds nothing

Two things exist for this, because "no sources found" is not an explanation:

- **Sources → Test sources** runs the project's real queries against the enabled
  APIs and shows, per source: calls, hits, HTTP status, time, errors, plus the
  filters in force. Nothing is stored and no model is called.
- A run that finds nothing now fails with the same report inline: which sources
  were called, how many hits each returned, how many were discarded by filters,
  and tailored hints (widen years, remove excluded terms, add a language).

Discovery runs in a small thread pool (3 queries × 3 APIs sequentially took a
minute; it is now a few seconds). Defaults are OpenAlex + Crossref; Europe PMC and
SciELO are opt-in per project.

---

## What a project looks like on disk

```
~/BibliometricStudio/
├── settings.json               non-secret settings
├── .secrets.json               only if no OS keychain is available (0600)
├── blobs/<sha256>              content-addressed store shared by projects
└── projects/<slug>/
    ├── project.json
    ├── inputs/brief.json       canonical form data
    ├── inputs/brief.md         rendered, hand-editable, re-importable
    ├── inputs/workplan.md      rendered specification for the author
    ├── agents/*.md             the live prompts (edit in the UI or in an editor)
    ├── agents/revisions/       one file per save
    ├── papers.json + papers/P-0001.md        sources, stable IDs
    ├── evidence.json + evidence/P-0001.md    citable excerpts with locators
    ├── runs/<run_id>/
    │   ├── state.json  log.jsonl  candidates.json  outline.json
    │   ├── outputs/document-v1.md, document-final.md, review-v1.md
    │   └── report.json         ledger + findings + DOI validation
    └── references/library.bib, bibliography.md, validation.md
```

Zipping the project folder (or the "Export" button) is a complete, shareable study.
Projects never contain API keys.

---

## How it works

Phases: **plan → discover → ingest → outline → draft → critique → freeze.**

- **Discover** queries OpenAlex, Crossref and Europe PMC (SciELO is a Crossref
  DOI-prefix filter, not a scraper). Failures degrade to warnings; a run never dies
  because one API is down.
- **Ingest** prefers open-access PDFs, extracts **per page**, and stores bounded
  excerpts. A source with no text and no abstract is skipped instead of inflating
  the bibliography.
- **Draft** is per section, so prompts stay small and a failure is retried alone.
- **Critique** is deterministic first (`ledger.py`): unresolved IDs, uncited
  paragraphs, quote mismatches, page locators that do not exist, missing sections,
  viewpoint coverage, source mix. The model only adds judgment on top.
- **Freeze** regenerates `library.bib` in code from `papers.json`, validates DOIs
  against `doi.org` + Crossref, and writes the report. Citations are never trusted
  from the model.

### Agents

Each agent is a markdown file with YAML front-matter and `##` sections. The UI edits
those sections as fields; the engine appends a **locked contract** (citation rules,
JSON schema) that cannot be removed by editing the text. `agents.py` is the single
place that defines that contract.

---

## What is built (v0.1 thin slice)

- [x] Workspace + project store, shareable project zip, import/export
- [x] Brief wizard (object, questions, themes, viewpoints, deliverable) + editing
- [x] Agent editor: fields, raw markdown, revisions, reset, compiled-prompt preview
      with token counts, locked contract panel
- [x] Run engine: phases, event log, checkpoints, cancel, cost/token meter, cost cap
- [x] Retrieval: OpenAlex, Crossref, Europe PMC, SciELO-as-collection, dedupe,
      scoring, OA PDF → per-page extraction, DOI validation
- [x] Deterministic ledger + generated BibTeX + review report
- [x] UI: projects, wizard, overview, sources, run console, document, review,
      agents, settings (PT-BR default, EN toggle)

## Not built yet (deliberate)

- Installers/bundling (§15 of the plan): `uv tool install` / `pipx` only for now
- Guided no-key mode (D2)
- SQLite app index / full-text search across projects (JSON + directory scan today)
- Resume of an interrupted run after a process restart (state is on disk; the
  worker is not re-attached)
- DOCX/PDF export (Markdown + bibliography today)
- Provider price table editing in the UI (table lives in `llm.py`)

---

## Tests

`python -m pytest` — 36 tests, no network:

- agent parsing/round-trip, locked contract, variables
- ledger: unresolved IDs, uncited paragraphs, quote and page mismatches,
  section/viewpoint coverage, verdict
- BibTeX generation and validation, escaping
- store: layout, isolation, ID allocation, revisions, zip round-trip, path safety,
  secrets never in `settings.json`
- engine end-to-end with a fake retriever: full run, checkpoint approve/drop/stop,
  cancel

Live checks were run manually against real APIs (see `../APP_PLAN.md` §3.2 for the
verified status of each source).
