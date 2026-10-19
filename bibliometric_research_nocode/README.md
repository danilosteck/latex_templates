# Bibliometric Agent Blueprint

A prompt-only, platform-agnostic blueprint for running **multi-viewpoint academic
research** with AI agents. Clone this repository once, then reuse it (or share it)
for every new study object.

You do **not** need Python, JavaScript, or any other programming language.
Everything happens through **markdown prompt templates** that you paste or point
your AI chat tool at (Claude Code, DeepSeek, OpenAI Codex, Gemini, etc.).

---

## What this gives you

- **Three cooperating agents** with clear, separated responsibilities:
  1. **Researcher** (`agents/01-researcher.md`) — finds and enriches information from the web and indexed academic sources, caching everything locally.
  2. **Author** (`agents/02-author.md`) — writes the deliverable using **only** cached, cited material. It never invents; it asks the Researcher when it needs data.
  3. **Critic** (`agents/03-critic.md`) — evaluates the deliverable and the Workplan, verify sources exist, and suggests improvements.
- **Token-optimised workflow**: local caches (`cache/`) mean you fetch each paper/page once and reuse it. You read citations, not full texts, in later steps.
- **Traceability & validation**: every paper lives in `papers/` with a stable ID, a full reference, a URL/DOI, and a `verified` status checkbox. A dedicated validation workflow (`templates/source-validation.md`) checks that sources actually exist.
- **Viewpoint map**: a structured way to capture *different academic viewpoints* on the same object instead of a single narrative.
- **Reusable skills**: self-contained, platform-agnostic prompt procedures in `skills/` (e.g. generating a standard **BibTeX `.bib`** of all consulted references).

---

## Repository layout

```
.
├── README.md                     ← you are here
├── workplan.md                   ← you fill this per study (the "brief")
├── agents/
│   ├── 01-researcher.md          ← Agent 1: web + academic retrieval, caching
│   ├── 02-author.md              ← Agent 2: writes the deliverable from cache
│   └── 03-critic.md              ← Agent 3: evaluation + improvement suggestions
├── templates/
│   ├── paper-record.md           ← one record per analysed paper
│   ├── viewpoint.md              ← one record per academic viewpoint/school
│   ├── cache-entry.md            ← how a cached source is stored/summarised
│   ├── source-validation.md      ← how to verify a source exists
│   ├── search-log.md             ← log of searches run (queries + results)
│   └── bibtex-entry.md           ← BibTeX entry skeletons per source type
├── skills/
│   └── bibtex.md                 ← skill: build/maintain references/library.bib
├── cache/
│   ├── papers/                   ← cached paper summaries / metadata (one file per source)
│   └── web/                      ← cached web pages / grey literature
├── papers/                       ← the searchable index of every paper analysed
│   └── viewpoints/               ← one file per academic viewpoint (the viewpoint map)
├── references/                   ← bibliography + ID registry + BibTeX
│   ├── id-registry.md            ← stable paper IDs (P-XXXX)
│   ├── bibliography.md           ← APA-style line per ID
│   └── library.bib               ← BibTeX of all consulted references (skill output)
├── studies/_template/            ← copy this folder to start a new study
├── examples/                     ← worked, fictional example of the full loop
├── outputs/                      ← generated deliverables live here
├── KICKOFF.md                    ← copy-paste prompts to run each agent
└── workplan.md                   ← you fill this per study (the "brief")
```

> **Principle:** the repository *is* the agent memory. If it isn't in `cache/` or
> `papers/`, the Author agent must not use it.

---

## The workflow (one study)

1. **Set up a study** — copy `studies/_template/` to `studies/<your-object>/`
   and fill in `workplan.md` (the research brief). See "How to start" below.
2. **Run Agent 1 (Researcher)** for the first retrieval round.
   It caches sources and writes paper records.
3. **Run Agent 2 (Author)** to draft the deliverable into `outputs/`.
4. **Run Agent 3 (Critic)** to evaluate and propose fixes.
5. **Loop**: feed the Critic's requests back to Agent 1 (fetch) → Agent 2 (revise),
   until it stabilises.
6. **Validate sources** with `templates/source-validation.md`.
7. **Run the BibTeX skill** (`skills/bibtex.md`) to keep `references/library.bib`
   in sync with the paper records.

---

## Skills

A **skill** is a self-contained, platform-agnostic prompt procedure you can invoke at
any time, independent of the agent loop. It is plain markdown + templates, so it works
in every chat tool.

- **`skills/bibtex.md` — BibTeX Reference File Builder.** Maintains
  `references/library.bib`: one valid BibTeX entry per consulted reference, cite key =
  paper ID (e.g. `P-0007`). Run it in *full pass* (rebuild/update the whole file) or
  *incremental* mode (append one entry when Agent 1 records a new paper). It preserves
  the traceability chain `library.bib → papers/P-XXXX.md → cache/papers/P-XXXX.md → DOI/URL`
  and enforces validation (no duplicates, balanced braces, escaped specials, no invented
  fields). Entry skeletons live in `templates/bibtex-entry.md`.
  The output imports directly into LaTeX, Zotero, Mendeley, JabRef, and Word/Docs
  (BibTeX import) — no plugin or code required.

---

## How to start (plain, no code)

1. Click **"Use this template"** / clone the repo. You now have a private copy.
2. Duplicate `studies/_template/` and rename it, e.g. `studies/urban-heat-islands/`.
   Keep the content folder names — the agents rely on them.
3. Open `workplan.md` in your study folder and fill every section.
4. Open your AI tool with the repo as context (in Claude Code / Codex you can
   `@`-reference files; in a chat window, paste the file contents).
5. Give the agent this kickoff instruction (adjust the paths):

   > You are operating the "Bibliometric Agent Blueprint" in this repository.
   > The study is `studies/urban-heat-islands/`.
   > Read `README.md`, then `agents/01-researcher.md`, and execute Agent 1 for the
   > three search themes listed in `workplan.md`. Follow the caching and
   > traceability rules exactly. Stop and report when the round is done.

6. Repeat for `agents/02-author.md` and `agents/03-critic.md`.

---

## Golden rules (applies to all agents)

- **Cite or omit.** Any factual claim in the deliverable must link to a paper
  record ID (e.g. `[P-0007]`) that maps to a real, verifiable source. The same ID is
  the BibTeX cite key in `references/library.bib`, so LaTeX `\cite{P-0007}` matches.
- **Cache everything read.** If a URL or PDF is consulted, its distilled content
  goes into `cache/` first, with the source URL. Subsequent agents read the cache,
  not the web.
- **Read summaries, not full texts, by default.** Full text is fetched only when
  the Author explicitly asks the Researcher for a specific passage. This is the
  main token-saving lever.
- **One record per paper**, stable IDs (`P-0001`, `P-0002`, …). Never recycle IDs.
- **Never fabricate** a DOI, author, year, or quote. If unsure, mark
  `verified: no` and flag it for the validation step.
- **Platform-agnostic** — write prompts as plain markdown so the same files work
  in any chat tool.

---

## Token-saving tips

- Keep `cache/` and `papers/` in context only when an agent needs them; otherwise
  point to the specific file.
- Store **summaries + key quotes + reference metadata** in cache, not full PDFs.
- Use the paper-record `summary` field as the reusable unit of knowledge.
- The Author agent works from `papers/` index first, fetching cache entries on
  demand, not all at once.

See `templates/cache-entry.md` for the exact format.
