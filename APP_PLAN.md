# Bibliometric Studio — Application Plan (v0 draft, for review)

Status: **plan, with the v0.1 thin slice now built** (see `app/`). Edited as the
build taught us things; the decisions below still describe the intended product.
Cheap-to-reverse choices are decided; expensive ones are in **§2 Decisions to
confirm** with a recommendation.

> **Build status (v0.1 thin slice implemented).** The engine, API and UI described
> in §5–§14 exist in `app/`; see `app/README.md` for what works, what was deferred,
> and the four deliberate deviations: event polling instead of SSE, JSON + directory
> scan instead of a SQLite index, no interrupted-run resume, and no installers yet.
> Packages verified live: OpenAlex, Crossref, Europe PMC and SciELO-as-collection
> all return real hits (four adapter bugs were found and fixed during the build —
> including Crossref rejecting `select=language` with a 400, which had been silently
> returning zero results).

Working name: **Bibliometric Studio** (placeholder — rename freely).

---

## 0. How to read this

- §1 is the one-page summary. Read that first.
- §2 is the list of decisions I need from you before code starts.
- §3–§4 define what exists today and what the product is (and is not).
- §5–§14 are the design: architecture, data model, agent editing, the form,
  the run loop, retrieval, trust, export, screens.
- §15–§16 install/distribution and security.
- §17–§20 testing, milestones, risks, migration.
- §21 open questions that are not blocking.

Traceability of your four requirements:

| Your requirement | Design section | Milestone |
|---|---|---|
| 1. Adjust agents via UI (fields that alter the .md) | §8 | M4 (+ minimal in M1) |
| 2. Initial form with essential research info | §9 | M3 (+ M0 schema) |
| 3. Projects with their own inputs / outputs / evidence | §6, §7 | M1–M2 |
| 4. Install process for non-technical users | §15 | M7 |
| (implicit) research quality must survive the app | §11, §12 | M5–M6 |

---

## 1. Summary and recommendation

Turn the two existing variants into **one product**: a local-first desktop-class
web app that wraps the same *file format* the no-code blueprint already uses.

Three claims drive the design:

1. **The markdown files are the product, not an implementation detail.** Today the
   Python engine hard-codes its prompts in `agents/*/agent.py`; the `.md` files are
   documentation. The app makes the `.md` files the live, versioned, user-editable
   source of truth. This is requirement #1 and it forces a small refactor of the
   existing engine — cheap now, expensive later.
2. **A project folder must stay usable without the app.** Everything the app does
   is saved as plain files in a folder: `brief.md`, `workplan.md`, `agents/*.md`,
   `papers/`, `evidence/`, `outputs/`, `library.bib`. If the app disappears, the
   user can still paste those files into any chat tool and continue. This preserves
   the original "platform-agnostic blueprint" value and is what makes sharing
   with colleagues trivial (zip the folder).
3. **Trust is enforced in code, not in the prompt.** "Cite or omit" cannot be a
   sentence in a prompt a user may edit. The engine keeps a deterministic citation
   ledger and refuses to mark a deliverable final while citations are unresolved.

Recommended shape:

```
Single Python process (FastAPI) serving a bundled React UI
        + project folders on disk (human-readable)
        + SQLite for app state only (index, jobs, revisions, search)
        + plugins: retrieval adapters, LLM providers (both swappable)
Shipped as: one executable per OS (Win .exe, macOS .dmg, Linux AppImage)
        with a first-run wizard; no terminal, no Python install.
Fallback channels: `uv tool install` and a Docker image.
```

Estimated effort (focused 8h days, solo + AI assistance):

- **Thin slice v0.1** — one project, form, run, cited draft, .bib export, run from
  a terminal one-liner: **12–16 days**.
- **v1.0 as specified in this document** — projects, agent editor, checkpoints,
  installers, exports, hardening: **46–58 days** (≈10–12 weeks part-time).

The important structural call: build the thin slice first, in that order, because
the riskiest unknowns (retrieval quality, LLM grounding, cost) are all inside it.

---

## 2. Decisions to confirm

Answer these and the rest of the plan locks. Recommendations in bold.

| # | Decision | Options | Recommendation | Consequence if changed |
|---|---|---|---|---|
| D1 | Distribution | (a) local single binary per OS; (b) Docker image; (c) hosted web service; (d) Electron/Tauri desktop wrapper | **(a)** local binary opening a browser tab | (b) excludes non-tech users; (c) adds accounts, hosting, billing, data-protection duty; (d) +3–4 weeks and a second toolchain |
| D2 | No-key mode | (a) automatic only (user supplies API key); (b) also a "guided" mode: app writes prompts, user pastes into ChatGPT/Claude and pastes results back | **(b), but in M8/after v0.1** | (a) blocks users with institutional-only access or key anxiety; (b) +4–5 days UI |
| D3 | Canonical data | (a) structured JSON is canonical, `.md` is rendered; (b) `.md` is canonical, parsed back | **(a)** | (b) form fields become brittle, validation and undo get hard |
| D4 | UI stack | (a) React+TS+Vite; (b) server-rendered HTMX/Alpine; (c) Tauri/Svelte | **(a)** | (b) faster to start, weaker for live progress/structured editors; (c) see D1 |
| D5 | UI language | (a) PT-BR default + EN toggle; (b) EN only | **(a)**; output-document language is a *separate per-project field* | (a) ~1 extra day; forgetting the split is the real risk |
| D6 | v0.1 scope | (a) thin slice then expand; (b) build the full v1 before showing it | **(a)** | (b) ~3 months before first feedback |
| D7 | Default provider | (a) DeepSeek (current config, cheap); (b) OpenAI; (c) local Ollama; (d) no default, force a choice | **(d) choose on first run, with (a) preselected and (c) supported** | Cheap default matters: a full study is ~$0.10–$1.50 depending on model |
| D8 | Collaboration | (a) none in v1, share by folder/zip; (b) shared library across projects; (c) cloud accounts | **(a) + a shared *source library* option later** | (c) is a different product; avoid until asked |
| D9 | Code signing | (a) unsigned binaries + documented workaround; (b) pay Apple ($99/yr) + Windows cert | **(a) for v0.1, decide before public release** | Unsigned macOS builds trigger Gatekeeper warnings — the single biggest drop-off for non-technical users |
| D10 | Repo consolidation | (a) keep both variants, add `app/`; (b) merge `nocode/` into `app/defaults/` and archive it | **(b) after v0.1 reaches parity** | (a) means maintaining three copies of the same prompts |

---

## 3. What exists today (audit)

### 3.1 Inventory

| Path | What it is | Verdict |
|---|---|---|
| `bibliometric_research/` | Python CLI: 3 agents + orchestrator + content-addressed cache + registry + retrieval adapters (Crossref, OpenAlex, SciELO, Scopus, WoS, ScienceDirect, Scholar-as-lead) + mock provider + smoke tests | **Reuse the engine.** Well-factored: `core/llm.py`, `core/cache.py`, `core/registry.py`, `agents/*` |
| `bibliometric_research_nocode/` | Prompt-only blueprint: `agents/01-researcher.md` … `03-critic.md`, `templates/`, `skills/bibtex.md`, `KICKOFF.md`, `workplan.md` | **Becomes the default agent/template pack.** Richer and better written than the Python prompts |
| `study_with_ai/` | Unrelated sandbox (venv, 643 MB) | Ignore |
| `latex_templates/` | Unrelated | Ignore |

Notable facts verified in the repo:

- **Prompts are hard-coded.** `bibliometric_research/agents/builder/agent.py:165`
  defines `_SYSTEM` inline; `prompts/builder.md` says "Inline in
  `agents/builder/agent.py`. Documented here for sharing/editing." So editing
  `.md` files today changes nothing. This is the core work behind requirement #1.
- **Two ID schemes.** Code: `p_<16 hex>` derived from DOI/URL
  (`core/registry.py`). Blueprint: sequential `P-0001`. They cannot be mixed.
- **The builder returns one giant JSON document**, with a retry-at-smaller-size
  fallback (`agent.py:54–88`). Works, but fragile for long documents and gives no
  progress feedback. §10 replaces it with a two-step outline→sections flow.
- **Cache is content-addressed and good** (`core/cache.py`): blobs/text/json keyed
  by sha256, so re-fetch and re-extraction are free. Reuse as-is, but move the
  blob store to the workspace level so projects share it (§6).
- **No page numbers.** `fetch.py` concatenates PDF pages into one string, so the
  `[P-0012 p.4]` promise in the blueprint cannot be kept. §11 fixes it.
- **No key management.** `.env` + env vars only. `.env` is correctly git-ignored
  (verified: not tracked, and the repo has no secrets in history).
- **`.bib` is generated by a prompt** in the blueprint (`skills/bibtex.md`), not by
  code. Should be code (§12).

### 3.2 Live probes of the retrieval sources (run today)

This matters more than anything else in the plan, so it is measured, not assumed.

| Source | Result | Implication |
|---|---|---|
| Crossref `api.crossref.org/works` | **200**, keyless, rich metadata | Primary discovery + metadata normalization |
| OpenAlex `api.openalex.org/works` | **200**, keyless but **shared $0.10/day budget per IP**; a free key gives **$1/day** | Ask for a free key in first-run; treat as primary discovery, cache aggressively |
| Europe PMC REST | **200**, keyless | Add for health/life sciences |
| SciELO `search.scielo.org?output=json` | **403** — bot challenge wall | Current adapter is broken. Do **not** scrape |
| SciELO articlemeta `/api/v1/article/search/` | **404** on that path | Metadata-by-ID works; search does not. Use Crossref DOI-prefix `10.1590` + OpenAlex source filters instead |
| Semantic Scholar Graph API | **429** unauthenticated | Optional adapter, requires free key |

Conclusion: SciELO is a **collection**, not a search engine. Implement it as a
filter over Crossref/OpenAlex (DOI prefix `10.1590`, plus PT/ES titles) and drop
the scraper. This is legal, stable, and gives the same literature.

---

## 4. Product definition

**Who it is for.** A researcher (you, colleagues, students, a lab) who has a
research question, a modest budget for API calls, and no interest in terminals.

**Job to be done.** "Turn my research question into a cited, multi-viewpoint
document I can defend, without inventing sources, and let me see and control
every step."

**What it is not (v1):**

- not a systematic-review/PRISMA machine (no screening workflow, no dual-coder);
- not a citation manager (it exports `.bib`; it does not replace Zotero);
- not multi-user, not cloud, no accounts, no sign-up;
- no embeddings/vector DB (lexical selection + structured evidence is enough;
  add later behind a flag if quality demands it);
- no document editing in-app beyond review-and-regenerate (Word/Google Docs
  remain the writing surface).

**v0.1 acceptance ("definition of done").** A person with no terminal experience:

1. installs by double-clicking one file;
2. pastes one API key, presses "Test";
3. fills the form in under 10 minutes;
4. runs the pipeline and approves two checkpoints;
5. downloads `document.md` + `library.bib` + a validation report;
6. every factual sentence carries a citation and the report shows **0
   unresolved citations**.

Anything not needed for that sentence is out of v0.1.

---

## 5. Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    Bibliometric Studio (one process)                     │
│                                                                          │
│   React UI (built, served as static)          FastAPI  /api/*            │
│   ───────────────────────────────             ─────────────────          │
│   Projects · Wizard · Run console             projects, runs, events(SSE)│
│   Sources · Document · Agents · Settings      agents (read/write/preview)│
│   Markdown render w/ citation chips           files (sandboxed), export  │
│                                                                          │
│   ┌──────────────── engine (UI-agnostic, CLI-usable) ─────────────────┐  │
│   │ orchestrator ── jobs ── checkpoints ── budgets/cost               │  │
│   │   ├── retrieval   adapters: openalex, crossref, europepmc,        │  │
│   │   │               scielo(filter), scopus?, wos?, s2?, arxiv,      │  │
│   │   │               unpaywall(OA pdf)                               │  │
│   │   ├── extraction  html→text, pdf→pages, docx, chunker             │  │
│   │   ├── agents      researcher | author | critic  (prompt .md files)│  │
│   │   ├── ledger      deterministic citation + validation checks      │  │
│   │   └── llm         provider adapters + JSON repair + cost table    │  │
│   └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│   store:  filesystem (projects, evidence, artifacts)                     │
│           sqlite app.db (index, jobs, revisions, FTS5)                   │
│           blobs/ content-addressed, shared across projects               │
└──────────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
        Workspace on disk (default ~/BibliometricStudio, user-chosen)
```

Rules that keep it maintainable:

- **engine never imports api**; the CLI (`bibstudio run --project X
  --no-checkpoints`) keeps working, and every automated test drives the engine
  directly. No UI required to test.
- **One event stream.** Every step appends a typed event to
  `runs/<id>/log.jsonl` (`step.started`, `source.added`, `checkpoint.requested`,
  `token.used`, `error`). SSE replays from an event id; the same file is the
  audit trail and the debug attachment users can send you.
- **Everything long-running is a job**, never an inline HTTP handler. Jobs are
  cancellable and resumable; the UI is just a view over `jobs` + events.
- **Provider and adapter are plugins** with a tiny contract and contract tests
  (§17), so a broken API degrades to a warning instead of a crash.

Stack: Python 3.12+ (the existing code already runs on 3.14 here), FastAPI,
Pydantic v2, SQLite (WAL), httpx, pypdf, trafilatura, PyYAML, `keyring`;
frontend React 18 + TypeScript + Vite + Tailwind + shadcn/ui, TanStack Query,
CodeMirror 6 for raw editing, `react-markdown` + `remark-gfm` + sanitizer.

---

## 6. Data model

### 6.1 Workspace

```
~/BibliometricStudio/                  ← user-chosen on first run
├── settings.json                      provider, models, budgets, language (NO secrets)
├── app.db                             index, jobs, revisions, FTS5
├── blobs/<sha256>                     shared content-addressed store (papers, html, pdf)
├── backups/<date>.zip                 optional, last 7
└── projects/
    └── 2026-urban-heat/               ← the unit of isolation and of sharing
```

### 6.2 Project layout (all human-readable; zip = shareable)

```
projects/2026-urban-heat/
├── project.json            id, title, slug, status, created/updated, output language
├── inputs/
│   ├── brief.json          canonical form data (§9)
│   ├── brief.md            rendered (for humans + the no-app workflow)
│   ├── workplan.json       canonical
│   ├── workplan.md         rendered
│   └── attachments/        user-supplied PDFs/DOCX (optionally ingested as sources)
├── agents/
│   ├── researcher.md  author.md  critic.md     project overrides (defaults if absent)
│   ├── revisions/author-0003.md                history, one file per save
│   └── provenance.json                         which default version each override derives from
├── papers/
│   ├── id-registry.json    P-0001 → doi/url/hash
│   └── P-0001.md …         one record per source (blueprint template)
├── evidence/
│   ├── P-0001.c1.md …      chunk-level evidence (summary + quote + locator)
│   └── index.jsonl
├── runs/
│   └── 2026-11-14T10-22/
│       ├── state.json      checkpoint, budget, cursor
│       ├── log.jsonl       event stream / audit trail
│       ├── candidates.json search results awaiting approval
│       ├── outline.json    section → evidence plan
│       ├── outputs/document-v1.md, review-v1.md, document-final.md
│       └── report.json     deterministic checks + validation results
├── references/
│   ├── bibliography.md
│   ├── library.bib         generated by code, not by a model
│   └── validation.md       DOI/title/quote check results
└── exports/                docx/pdf/zip artifacts
```

### 6.3 Invariants

1. **IDs.** `P-0001` is the display/cite key, assigned once, never reused. Dedupe
   is by normalized DOI (fallback: normalized URL, then title+year hash). The DOI
   is stored on the record; if a source is re-found, the existing ID is reused.
   `library.bib` keys = the same `P-0001` (matches `\cite{P-0001}` in LaTeX).
2. **Blobs are shared, records are not.** A paper found in two projects points to
   the same blob (space win) but has two project-local records (so evidence,
   verification state and quotes stay project-scoped). Cross-project reuse is an
   explicit "import these sources" action that copies the record.
3. **Evidence is chunk-scoped.** `ev=P-0007#p3` (page 3) or `#c3` (chunk 3 when
   the source has no pagination). Quotes must be substrings of the stored text
   after whitespace normalization — checked mechanically.
4. **Append-only outputs.** Every run writes new versioned files; nothing is
   silently overwritten. Revisions and runs are never garbage-collected without a
   user action.
5. **No secrets in project folders.** Projects are designed to be zipped and
   emailed; keys live in the OS keychain only.

---

## 7. Canonical data vs markdown (D3)

Decision: **structured JSON is canonical; `.md` is always rendered from it, and
`.md` can be re-imported.**

Why not markdown-first: the form needs typed values, repeatable rows, per-field
validation, and undo. Parsing a `.md` a user edited by hand back into a form is a
source of silent data loss (ambiguity in lists, tables, checkboxes).

Why still render `.md`: it is what the engine actually prompt-builds from, what a
user can paste into any tool, and what preserves the blueprint's portability.

Round-trip contract:

- The rendered `.md` has stable, documented headings (today's `workplan.md`
  headings become the contract).
- "Import/attach `.md`" parses headings → fields; unknown headings are preserved
  verbatim under `extras` and re-emitted unchanged.
- A "Markdown mode" toggle lets power users edit the `.md` directly; on save the
  app shows a parse diff before accepting, and refuses silently lossy saves.

---

## 8. Agent editing through the UI (requirement #1)

### 8.1 File format

Each agent is one markdown file with YAML front-matter and `##` sections:

```markdown
---
id: author
label: Author
version: 3                    # increments on every save
model: null                   # null = app default
temperature: 0.2
max_output_tokens: 4000
enabled: true
variables: [topic, rqs, deliverable_sections, min_sources, output_language]
engine_rules: [cite-or-omit, no-browse, no-fabrication, json-contract]
---
# Author

## Role
Write the deliverable using only material present in evidence/.

## Absolute constraints
…

## Writing procedure
…

## Domain guidance          <!-- user-added section; engine preserves it -->
…
```

### 8.2 How the UI maps fields to the file

- **Front-matter → structured controls** (model, temperature, budget, enabled,
  variables). These change behavior mechanically.
- **Each `##` heading → one labeled field box** with a textarea, the section's
  default text as placeholder when empty, and a "restore default" button.
- **Free-text is advisory.** Anything a user writes here shapes tone and
  procedure, not guarantees (see 8.3).
- **Add section** appends a custom heading; **reorder** is supported (order
  matters for prompt assembly); **delete** is blocked for the sections listed in
  `engine_rules` (they are shown read-only with an explanation).
- **Raw mode** exposes the whole file for power users, validated before save.

### 8.3 Locked rules: what the user cannot break

| Invariant | Why it cannot be prompt-only | Where enforced |
|---|---|---|
| Every claim cites a real evidence id | A user editing "cite or omit" out of the prompt produces unusable output | Ledger scans the draft; unresolved citations block "Final" (§12) |
| Author has no web access | Accidentally enabling browsing silently invents facts | Engine has no browsing tool for that agent; it is a code boundary |
| Builder output must be parseable | Free-text output breaks the pipeline | Schema-validated JSON with repair + one retry |
| DOI/quote must exist | Hallucinated references are the failure mode that matters | Deterministic validation (§12) |
| No ID reuse | Breaks traceability and `.bib` | Registry logic |

The UI displays these as a "Guaranteed by the app" panel — that is the honest
contract: *prompt text = behavior you can shape; code = guarantees you can't
remove by accident.*

### 8.4 Variables and compile preview

- `{{project.topic}}`, `{{workplan.rqs}}`, `{{deliverable.sections}}`,
  `{{min_sources}}`, `{{output_language}}` … resolved at run time.
- **Compile preview** shows the exact system + user prompt that will be sent,
  with a token estimate and per-section token breakdown. Unknown variables are a
  hard warning. This is the feature that makes "editing an agent" comprehensible
  to a non-technical user — otherwise they are editing prose with no feedback.
- **Token meter** next to the editor: "this agent costs ~1.8k input tokens per
  call at this setting".

### 8.5 Revisions, defaults, sharing

- Every save writes `revisions/<agent>-NNNN.md` + a timestamped index entry.
- Diff view: current vs default, current vs previous.
- "Reset agent" and "Reset all agents" (defaults are versioned with the app, so an
  app update can offer "your override is based on v2; v3 changed the procedure —
  view diff").
- **Export agent pack** (zip of the three `.md` + optional project template) and
  **Import pack** — this is how a lab standardizes its method, and how the
  blueprint stays shareable.
- Presets shipped: *Strict academic*, *Fast draft*, *PT/ES literature focus*,
  *Engineering/technical review*.

### 8.6 Per-agent model settings

Model, temperature, max tokens per agent (e.g. cheap model for the query planner,
strong model for the author). Global defaults in Settings; per-agent override in
front-matter. Costs are shown from a price table, editable in Settings.

---

## 9. The initial form (requirement #2)

Six steps + review, ~10 minutes, fully resumable (autosave per field). Every
required field has a "why we ask" tooltip and a worked example.

**Step 1 — Study identity**

| Field | Type | Req | Notes |
|---|---|---|---|
| Project title | text | ✔ | also the slug (`2026-urban-heat`), editable |
| Object of study | textarea | ✔ | one paragraph; the anchor for all queries |
| Disciplines | tag input, suggestions | – | drives source presets |
| Time frame | two years / "any" | – | filters retrieval |
| Geographic scope | text + "global" chip | – | |
| Literature languages | multi (EN/PT/ES/+custom) | ✔ | default EN+PT for a BR user |
| Output language | single | ✔ | **separate** from UI language |

**Step 2 — Research questions**

- Repeatable rows (1–8): question + optional "why it matters".
- Optional "help me refine" (LLM, cheap model) — suggestion only, user edits.

**Step 3 — Search strategy**

- Themes: repeatable rows → *theme name*, *core keywords (EN)*, *synonyms / PT /
  ES*, *preferred sources* (multi-select of the enabled adapters).
- Inclusion/exclusion: peer-reviewed only, year range, languages, exclude terms,
  grey literature on/off.
- Minimum distinct sources (default 20), soft cap on fetches.
- "Suggest themes from my object" (LLM) as a starting point.

**Step 4 — Viewpoints (optional, recommended)**

- Repeatable rows: label, description, expected proponents.
- Import from another project; or LLM suggestions to accept/edit.
- These feed the critic's balance check, so skipping them weakens that check —
  say so in the UI.

**Step 5 — Deliverable**

| Field | Type | Notes |
|---|---|---|
| Template | select | journal article / funding proposal / thesis chapter / technical report / custom |
| Sections | checklist, reorderable, custom | prefilled from template; these become required sections |
| Length target | words | |
| Tone / audience | text | e.g. "funding committee" |
| Citation style | select | numeric `[P-0007]` (default) / author-year + `.bib` |
| BibTeX | toggle | default on |
| Iteration budget | rounds + cost cap | default 3 rounds, US$2 soft cap with a warning |

**Step 6 — Review & create**

- Summary of everything, estimated cost band, "what will happen" 5-line plan.
- Creates the folder, renders `brief.md` + `workplan.md`, copies default agents.
- Optional: "Save as template" (lab reuse).

Validation philosophy: block only what breaks the run (topic, RQ, themes, output
language). Everything else gets defaults and a visible "you can change this
later" hint.

---

## 10. Run engine, checkpoints, cost

### 10.1 Phases and checkpoints

| Phase | What happens | Checkpoint (UI card) |
|---|---|---|
| 0. Plan | LLM proposes queries + themes from brief | — |
| 1. Discover | adapters return candidates; dedupe by DOI; score | **Candidate tray**: "24 candidates — approve all / select / fetch metadata only" |
| 2. Ingest | fetch OA full text where possible; extract; chunk; register IDs | — |
| 3. Outline | LLM proposes section outline + evidence assignment | **Outline review**: reorder, add/remove sections, see evidence per section |
| 4. Draft | per-section generation, streamed | — |
| 5. Critique | deterministic checks + LLM review | **Review**: scores, issues, "request more sources" / "revise sections" |
| 6. Revise | targeted section rewrites + new evidence if requested | loop until pass/budget |
| 7. Freeze | validation pass, `.bib`, exports | **Freeze**: final artifacts + report |

Checkpoints are opt-out in Settings (a "hands-off" checkbox), but on by default —
this is the "I want to be consulted" requirement carried forward.

### 10.2 Why outline → sections instead of one big call

The current builder asks for the whole document as one JSON object (~3–8k output
tokens), which truncates, loses structure, and gives no progress. Splitting:

- the outline is cheap, reviewable, and becomes a checkpoint (large quality win);
- each section sees only its own evidence → smaller prompts, better grounding,
  fewer contradictions;
- a failed section is retried alone;
- the UI can stream section by section (visible progress = trust);
- per-section token accounting enables precise cost estimates.

A final deterministic pass assembles sections, collects cited IDs, renders
references from the registry, and runs the ledger.

### 10.3 Jobs, budgets, failures

- Job states: `queued → running → waiting_checkpoint → running → done` plus
  `needs_key`, `needs_network`, `rate_limited`, `cancelled`, `failed`.
- Resume: state is re-derived from artifacts + `state.json`; a crashed run resumes
  without re-paying for completed sections.
- Budget: pre-flight estimate per phase; running meter (`tokens`, `US$`); soft cap
  → checkpoint "continue / stop"; hard cap in Settings.
- Retry policy: 429/5xx → exponential backoff with jitter; provider invalid key →
  `needs_key` with a direct link to Settings; JSON parse failure → one repair
  attempt then a labelled placeholder (never a silent empty document).
- Error surfaces are human: "OpenAlex asked for a key" not "HTTP 403".

---

## 11. Retrieval design (the real risk)

### 11.1 Adapter table

| Adapter | Auth | Status today | Role |
|---|---|---|---|
| OpenAlex | free key (recommended) | **200 OK** | Primary discovery: filters (year, language, OA, type), concepts, citation counts, `best_oa_location` |
| Crossref | none (polite `mailto`) | **200 OK** | Metadata normalization, DOI resolution, DOI-prefix collection filters |
| Europe PMC | none | **200 OK** | Life/health sciences + OA full text |
| SciELO | none | search **403** (bot wall) | Implemented as **Crossref prefix `10.1590` + OpenAlex source filter**, not scraping |
| arXiv | none | Atom API | Preprints in CS/physics/math |
| Unpaywall | email | — | Best OA PDF locator → feeds the PDF extractor |
| Semantic Scholar | free key | **429 unauth** | Citation graph, "cited by" expansion (optional) |
| Scopus / Web of Science / ScienceDirect | institutional keys | — | Metadata only; graceful degradation when absent |
| Google Scholar | — | — | **No scraping** (ToS). Optional SerpAPI-style key; otherwise manual paste of a DOI list |

Adapter contract tests use recorded JSON fixtures so CI never depends on the
network; one nightly job hits the live endpoints and opens an issue on failure.

### 11.2 Candidate triage (before spending money)

1. Dedupe by normalized DOI → URL → title+year.
2. Filter by inclusion criteria (type, year, language, retractions).
3. Score: relevance to theme keywords + venue quality + citation count + OA
   availability.
4. Present the tray. Default action in automatic mode: take top N (configurable),
   skip outliers. User can pin/exclude.
5. Only approved candidates cause a network fetch. This is the main cost control:
   the current code fetches up to 40 items blindly.

### 11.3 Full text and quotes

- Prefer OA: OpenAlex `best_oa_location` → Unpaywall → direct PDF.
- Extract HTML with trafilatura (much cleaner than the current regex/BS4 path).
- **PDF → per-page text**, so page numbers survive: `evidence/P-0007.c3.md` knows
  it came from page 4, and `[P-0007 p.4]` becomes a true statement.
- If only an abstract is available: store the abstract as page-less evidence,
  mark the record `full_text: paywalled`, and forbid page-locator quotes.
- Never bypass paywalls, never store full texts by default (configurable); store
  summaries + bounded excerpts + locators, which keeps the corpus small and the
  copyright exposure low.

### 11.4 Rate limiting and politeness

Per-host token bucket, `User-Agent` with a contact address from Settings, respect
`Retry-After`, cache every search response forever (queries are stable), and a
global fetch cap per run. A "Sources" screen shows which adapters are active and
which are degraded ("Scopus: no key — configured but inactive").

### 11.5 Prompt injection from sources (new threat, must design for)

Retrieved papers are untrusted input that lands inside the author's prompt.

- Source text is always wrapped in explicit delimiters with a system-level
  statement that content is data, not instructions.
- The author only ever sees summaries/excerpts, never raw full text.
- Excerpts are scanned for instruction-like patterns; hits are flagged in the
  source record and shown in the UI ("this source contains instruction-like text").
- Sources with no DOI/venue (grey/web) are labelled and cannot support a factual
  claim without a visible "grey" badge.
- Markdown rendered in the UI is sanitized (no raw HTML, no `javascript:` URLs) —
  model output is untrusted too.

---

## 12. Trust layer: citations, validation, freeze

**The ledger.** For every output version, the engine computes:

- per-paragraph citation presence (sentences with factual claims and no citation
  are listed, not just counted);
- cited IDs → existence in `papers/`;
- each citation's source type, verification status, and whether the quote is a
  real substring of the stored text (normalized whitespace, accent-insensitive);
- viewpoint coverage vs the workplan list;
- section coverage vs the workplan checklist;
- source mix (peer-reviewed %, grey %, recency, language).

**DOI validation** (keyless): DOI handle API + Crossref metadata → title
similarity (token-set ratio) and year match. Output: `verified` / `mismatch` /
`unresolvable`. This is a code path, testable without an LLM — unlike the current
"ask the critic to validate" approach.

**BibTeX generation** is code, not a prompt: entry type inferred from source type,
fields from the registry, braces escaped, keys = `P-0001`, sorted, deduped. The
critic keeps its "BibTeX integrity" score but now it is checking generated output,
not writing it.

**Freeze gate.** `document-final.md` can be produced with unresolved citations, but
the UI labels it "unverified (3 unresolved)" and the export report carries the
same warning. Silent success is not allowed.

**Review UI.** The critic's report becomes actionable items grouped by target
(→ researcher / → author), each with a button ("fetch this", "revise section 3").
That is the loop closure the blueprint describes, made clickable.

---

## 13. Export and deliverables

| Export | Format | Notes |
|---|---|---|
| Document | `.md`, `.docx` (python-docx or pandoc), `.pdf` (pandoc/LaTeX or headless) | `.docx` is what colleagues actually want; keep styles from the template |
| References | `.bib`, `bibliography.md`, `references.csv` | keys = `P-0001` |
| Evidence | `evidence/` folder + `sources.csv` | auditable appendix |
| Review | `review-*.md`, `report.json` | the audit trail |
| Project | `.zip` (no secrets) | share/reopen elsewhere |
| Validation | `validation.md` | DOI/title/quote checks |

Pandoc as a bundled binary is the pragmatic choice for `.docx`/`.pdf`; if that is
too heavy, `.docx` via python-docx templates and `.pdf` via the browser print
dialog (surprisingly good, zero dependencies).

---

## 14. Screens

1. **Projects** — cards with status, sources count, last run, cost; create/open/
   duplicate/archive/import/export.
2. **Wizard** — §9, six steps, resumable.
3. **Project home** — pipeline status, next action, budget, recent artifacts.
4. **Brief & plan** — the form again, editable, with markdown toggle.
5. **Sources** — table: title, year, venue, type, DOI badge (verified/unverified),
   OA, quotes used, cited-in; filters; manual add (DOI/URL/PDF) and remove.
6. **Run console** — live events, checkpoint cards, cancel/pause, cost meter.
7. **Document** — rendered draft with citation chips (hover → quote + locator),
   version selector, diff between versions, "revise this section".
8. **Review** — scores table, prioritized issues, action buttons.
9. **Agents** — one tab per agent; sectioned editor, compiled-prompt preview,
   token estimate, revisions/diff, reset, import/export pack.
10. **Settings** — provider + key + "Test", models and prices, budgets, language,
    workspace path, adapters status, backups, diagnostics self-test.
11. **Help / Diagnostics** — "why did my run stop?", network/provider/disk
    self-test with copyable report.

Global: single primary action per screen ("Run", "Approve", "Export"), no modal
stacks, keyboard-accessible, empty states that teach.

---

## 15. Installation and distribution (requirement #4)

### 15.1 Options

| Approach | User effort | Your effort | Verdict |
|---|---|---|---|
| `uv tool install bibstudio` | terminal | low | keep for power users |
| Docker image | install Docker, run one line | low | keep for NAS/server users |
| **Single executable per OS** (PyInstaller/PyOxidizer + bundled UI) | **double-click** | medium (CI matrix, signing) | **primary** |
| Electron/Tauri wrapper | double-click | high (+3–4 weeks) | only if native menus/file dialogs become essential |
| Hosted SaaS | browser + account | very high (hosting, GDPR, billing, abuse) | not now |

### 15.2 What the user sees

1. Download `BibliometricStudio-1.0-win.exe` / `.dmg` / `.AppImage`.
2. Double-click → app starts a local server on `127.0.0.1`, picks a free port,
   opens the default browser at `http://127.0.0.1:<port>/?t=<session-token>`.
3. First-run wizard: choose workspace folder → choose AI provider → paste key →
   "Test connection" (green tick) → optional free OpenAlex key (link + why) →
   pick UI language.
4. A system-tray/menu-bar icon (optional) to stop the app; closing the tab does
   not kill a running job, which is stated in the UI.

Platform notes:

- **Windows**: Inno Setup installer (Start-menu shortcut, uninstaller, per-user
  install so no admin prompt). SmartScreen warns on unsigned binaries — decide D9.
- **macOS**: `.dmg`, unsigned → Gatekeeper warning. For non-technical users this
  is a genuine blocker; budget the $99/yr for notarization before public release.
  Universal2 build for Intel+ARM.
- **Linux**: AppImage (works everywhere) + `.deb` if you want apt integration.
- **Updates**: check the GitHub releases API on start; show a non-blocking banner.
  Verify a signature/hash before offering the download.
- **No-key path**: §15.3 keeps the product usable without any key.

### 15.3 Keys and no-key operation

- Keys are stored in the **OS keychain** (`keyring`: macOS Keychain, Windows
  Credential Manager, Secret Service). Fallback with a clear warning: encrypted
  file (`AES-GCM`, key derived from a machine-bound secret) — documented as weaker,
  never plaintext.
- Never in project folders, never in `settings.json`, never exported in a `.zip`.
- **Guided mode (D2)** for users who cannot or will not use an API key: the app
  shows the compiled prompt with a Copy button, the user pastes it into ChatGPT/
  Claude/the institutional tool, pastes the JSON reply back, and the engine
  continues exactly as if it had called the API (validation is identical). This is
  also the offline/air-gapped path and it is *already how the no-code blueprint
  works* — the app just makes it pleasant.

### 15.4 Support-cost reducers (worth building early)

- Diagnostics self-test (network reachability, provider auth, adapter health,
  disk space, write permissions) with a copyable report.
- "Open project folder" and "Open log" buttons in every error surface.
- A `doctor` CLI subcommand with the same checks.
- Version + environment block in every report.

---

## 16. Security and privacy

Local web apps are a real attack surface; treat them as such.

- Bind **127.0.0.1 only**; random per-launch session token in the URL, required on
  every API call; validate the `Host` header (DNS-rebinding defence); no CORS
  wildcard; `SameSite=Strict` cookies.
- All file APIs resolve paths against the workspace root and reject traversal;
  imports go through an upload staging dir.
- Fetching is user-initiated only: http/https only, block private/link-local IP
  ranges and redirects to them (SSRF), cap size and content types.
- Sanitize all rendered markdown (no raw HTML). Cite-chip links open externally
  with `rel="noopener noreferrer"`.
- No telemetry by default. If ever added: opt-in, off by default, documented, and
  never sends project content.
- Data at rest is plain files (user's choice, greppable, git-able). Optional
  "encrypt workspace" is a v2 feature, not v1.
- Project zips exclude keys by construction.
- Prompt-injection handling per §11.5.

---

## 17. Testing and QA

| Layer | What | Tool |
|---|---|---|
| Unit | cache keys, ID assignment/dedupe, chunker, citation ledger, bib generator, form validators, markdown round-trip | pytest |
| Adapter contract | recorded JSON fixtures → normalized candidates; live-network test nightly only | pytest + fixtures |
| Provider contract | each provider adapter against a fake HTTP server; JSON repair paths; 429/timeout handling | pytest + respx |
| Engine E2E | mock provider, temp workspace: full run, checkpoint pause/resume, cancel mid-run, resume after simulated crash | pytest |
| Prompt snapshots | compiled system+user prompt per agent, hashed; a change must be intentional | pytest + snapshots |
| Grounding evals | small fixed set of sources + questions; assert zero unresolved citations, no quote mismatches; run per model | script, manual |
| UI | wizard → run → approve → export, on a mock engine | Playwright |
| Packaging | install + launch + self-test on Win/macOS/Linux | CI matrix |
| Migration | import the existing `bibliometric_research_nocode` folder as a project | pytest |

Non-negotiable gates for v1: zero unresolved citations in the golden run, a
crashed run resumes without duplicating or losing artifacts, and no secret ever
appears in an exported project.

---

## 18. Milestones

Assumes one developer + AI assistance, 8h focused days.

| M | Deliverable | Days | Demo criterion |
|---|---|---|---|
| **M0** | Repo consolidation plan executed in a branch: `app/` skeleton, Pydantic schemas for brief/workplan/agent/evidence, CI (lint+test), decision lock | 2–3 | `pytest` green; schemas round-trip the existing `workplan.md` |
| **M1** | Engine extraction: prompts loaded from `.md` files (front-matter + sections), per-project store, shared blob cache, citation ledger, deterministic `.bib` | 6–8 | CLI run from `.md`-only config produces a cited draft + ledger report |
| **M2** | API + job runner + event stream + checkpoint protocol | 5–6 | `curl` creates a project, starts a run, streams events, resumes after pause |
| **M3** | UI shell: projects, wizard, project home, run console, document viewer | 8–10 | Recorded 10-minute path: empty → project → mock run → read draft |
| **M4** | Agent editor: sectioned fields, compiled preview, revisions/diff, packs | 5–6 | Edit a section, see the prompt change and token count, revert |
| **M5** | Retrieval hardening: adapters + fixtures, candidate tray, OA full text, page locators, rate limiting | 6–8 | A real study with 20+ verified sources and zero DOI mismatches |
| **M6** | Exports (docx/pdf/bib/zip), validation report, freeze gate | 3–4 | Two-page brief exported to `.docx` with working citations + `.bib` |
| **M7** | Packaging: three installers, first-run wizard, keychain, update check, diagnostics | 6–8 | A non-technical colleague installs and completes a run unaided |
| **M8** | Hardening: security review, injection defenses, i18n PT/EN, docs, guided mode (D2) | 5–6 | Security checklist signed off; PT-BR UI complete |
| | **Total** | **46–58** | |

**v0.1 thin slice** (M0 + a trimmed M1 + M2 + M3 + M6, OpenAlex/Crossref only, no
agent editor UI beyond raw file editing, run via `uvx`): **12–16 days**. Ship this
to yourself and two colleagues before building M4–M8; retrieval quality and LLM
grounding will change the design more than any other feedback.

**Cut order if time runs out:** guided mode → PDF export → presets → backups →
per-agent model override → candidate tray (replace with "fetch top N").

---

## 19. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Retrieval fragility (already seen: SciELO 403, S2 429) | high | high | Fixture-tested adapters, graceful degradation, adapter status UI, 3 sources minimum redundancy |
| LLM cost surprise for users | medium | high | Pre-flight estimates, cost meter, hard caps, cheap default, per-agent models |
| Hallucinated citations slip through | medium | high | Deterministic ledger + DOI/quote validation + freeze gate |
| Full texts paywalled / abstract-only | high | medium | OA-first, explicit `paywalled` state, abstract-level claims labelled |
| Prompt editing silently breaks invariants | medium | high | Locked rules in code (§8.3) |
| Install friction (Gatekeeper/SmartScreen) | high | high | Decision D9, first-run wizard, `uvx`/Docker fallbacks |
| Scope creep (multi-user, cloud, RAG) | high | high | Non-goals + milestone gates + cut order |
| Provider API changes | medium | medium | Thin adapters + contract tests |
| Prompt injection from sources | medium | medium | §11.5 |
| Data loss | low | high | Append-only artifacts, revisions, backups, autosave |
| Copyright/ToS exposure | low–medium | medium | No scraping, OA-only full text, store summaries/excerpts |
| Support burden | medium | medium | Diagnostics self-test, human error messages, copyable reports |

---

## 20. Migration from the current repo

1. **Do not move existing folders yet.** Add `app/` alongside; keep both variants
   working while parity is built.
2. The engine moves in as a library: `core/*` → `app/backend/bibstudio/engine/*`
   with imports fixed and tests carried over. Prompt strings extracted to
   `app/defaults/agents/*.md` (composed from the python prompts + the richer
   `nocode/agents/*.md` text).
3. `nocode/templates/*` → `app/defaults/templates/*`; `skills/bibtex.md` becomes
   code + a thin doc.
4. After M5, freeze `bibliometric_research/` and `bibliometric_research_nocode/`
   with a README pointing to the app; delete only after one release cycle.
5. 95 MB of cached blobs stay untracked (already git-ignored: verified). Nothing
   in `.git` needs rewriting; no secrets were ever committed (verified).

---

## 21. Open questions (not blocking)

- Do you want a per-study "publication target" field that adjusts length/tone
  (e.g. journal word limits)? Cheap, high value for academics.
- Should the app support reading a local folder of PDFs you already have as a
  first-class source ("my library" input)? Attachments are in the model; making
  them a retrieval source is a moderate addition.
- Should runs be git-committed automatically per round (`git init` in the project)
  for a diffable audit trail? Strong for a thesis defense, adds a git dependency.
- Do you want a shared, read-only "source library" across projects (same lab,
  same corpus)?
- Is a "review my existing document against the evidence" mode interesting
  (upload a draft → critic + ledger, no generation)? It is a small feature on top
  of the ledger and very useful for revision.

---

## 22. Appendices

### A. Agent file — minimal example

```markdown
---
id: critic
label: Critic
version: 1
temperature: 0.1
enabled: true
engine_rules: [json-contract, no-fabrication]
---
# Critic

## Role
Evaluate the draft against the workplan and the evidence. Do not rewrite it.

## Dimensions
- Requirement coverage (weight 2)
- Evidential grounding (weight 3)
- Viewpoint balance (weight 2)
- Source quality (weight 2)
- Traceability (weight 3)
- Gaps and honesty (weight 1)

## Output
Return JSON matching the review schema. Cite exact section names and paper IDs.
```

Dimensions as structured rows (name + weight) so the report table is generated by
the engine and the user can add a dimension without writing markdown.

### B. Citation ledger output (example)

```json
{
  "version": "document-v1",
  "paragraphs_without_citation": 4,
  "citations": {"total": 63, "resolved": 61, "missing": ["P-0018", "P-0042"]},
  "quote_checks": {"checked": 12, "exact": 11, "mismatch": ["P-0007 p.4"]},
  "sections": {"required": 7, "present": 7, "empty": []},
  "viewpoints": {"required": 3, "represented": 3},
  "sources": {"total": 24, "peer_reviewed": 21, "grey": 3, "doi_verified": 22},
  "verdict": "unverified"
}
```

### C. Glossary

- **Evidence item** — a bounded excerpt from a source plus a locator
  (`P-0007 p.4`), the only thing the author may cite.
- **Candidate** — a search hit not yet ingested.
- **Ledger** — deterministic record of which claims cite what, and whether each
  citation resolves.
- **Checkpoint** — a pause where a human approves before spending more money.
- **Freeze** — marking a document final after validation (with warnings shown if
  unresolved).
- **Guided mode** — no-API-key operation: the app compiles prompts, the user runs
  them in any chat tool and pastes results back.

### D. Effort legend

1 day = 8 focused hours including tests for that slice. Ranges reflect unknowns in
the frontend and packaging, which are the least predictable parts.
