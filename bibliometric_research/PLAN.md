# PLAN — Multi-Agent Bibliometric Research Blueprint

This is the plan behind the blueprint. Read it once, then reuse the repository
per study. It is intentionally **simple** and **provider-agnostic**.

---

## 1. Objective

For a given **study object**, gather academic research and build a **map of
distinct academic viewpoints** (not a single narrative). The output should let a
reader see *who* says *what*, *where* it is published, and *why* the views
differ — with every claim traceable to a verifiable source.

The process must be:
- **replicable** per study (a blueprint, not a one-off),
- **shareable** (no proprietary runtime; plain Python + any LLM),
- **token-efficient** (cache aggressively; never pay twice),
- **auditable** (every paper recorded, every source validatable).

---

## 2. The three agents

We keep only three agents plus a thin orchestrator. Simplicity is a feature:
fewer agents = fewer prompts = fewer tokens = easier to reason about.

### Agent 1 — Retriever
**Job:** turn a need for information into **cached, citable evidence**.

- Accepts *retrieval requests*: a query + target source(s) + why it is needed.
- Searches indexed academic sources first
  (**SciELO, Scopus, Web of Science, ScienceDirect, Google Scholar**), then a
  general web fallback.
- For each hit, creates a **paper registry record** (stable ID, DOI/URL,
  metadata, content hash) and an **evidence item** (`ev://<id>`).
- Fetches and caches the full text (PDF/DOCX/HTML → clean text), chunked.
- **Never writes analysis prose.** It only returns evidence IDs + short
  excerpts.

### Agent 2 — Builder
**Job:** write the analysis document requested by the **Workplan**.

- Inputs: `study/workplan.md`, the study brief, and the **evidence items**
  selected for it. It does **not** browse.
- If it lacks information, it does **not** invent it. It emits an
  **evidence request**, and the orchestrator routes it to the Retriever. Only
  after evidence arrives does it continue.
- **Every substantive claim must cite an internal evidence ID** (`ev://…`),
  which resolves to a paper record. No citation, no claim.

### Agent 3 — Critic
**Job:** evaluate the draft against the brief + workplan + evidence and suggest
improvements.

- Checks: coverage of required sections, viewpoint diversity, unsupported
  claims, misused citations, balance/bias, clarity.
- Returns structured findings (severity, location, suggestion) — not a rewrite.
- Drives the **iteration loop** (Builder fixes; Critic re-reviews) until the
  findings are minor or the human stops the loop.

### Orchestrator
Routes work between agents, enforces checkpoints, and owns the budgets (token
budget, max rounds, max fetches). It is *thin* — logic lives in the agents.

---

## 3. Information flow

```
                +-------------------- you (human) --------------------+
                |        confirm brief / sources / drafts            |
                +-------------------------+--------------------------+
                                          |
 study/  ---->  Orchestrator  <-----------+----> output/ (drafts, reviews, map)
 brief.md         |     ^     ^
 workplan.md      |     |     |
                  v     |     |
             +----------+  +--------+
             | Retriever |  | Critic |
             +-----+-----+  +----+---+
                   |             ^
                   v             |
             cache/ + registry/  |
                   ^             |
                   |             |
             +-----+-------------+---+
             |       Builder       |
             +---------------------+
              (only sees evidence
               IDs + excerpts)
```

---

## 4. Token-optimization strategy

Tokens are spent in three places: **retrieval**, **writing**, and **review**.
We attack all three.

1. **Content-addressed cache** (`core/cache.py`)
   - Key = hash of (canonical URL) or (file bytes) or (normalized query).
   - A fetched page/PDF is stored **once**; extracted text is stored separately so
     re-processing is free.
   - Queries are cached too, so repeated searches cost nothing.

2. **Evidence IDs, not full text**
   - Agents communicate short `ev://<id>` references and ≤ N-word excerpts.
   - This keeps prompts small and forces grounding.

3. **Chunk-and-select**
   - Long PDFs become text → chunks. Only chunks relevant to the current task
     are included in a prompt (simple lexical/embedding-free selection by
     default; optional embeddings later).

4. **Structured, bounded prompts**
   - Each prompt template caps excerpt length and asks for compact structured
     output (JSON) to minimize filler.

5. **Budgets & short-circuits**
   - `config.yaml` sets `max_fetches`, `max_rounds`, and a soft `token_budget`.
   - The orchestrator stops and asks you before exceeding budgets.

6. **Summarize-then-reuse**
   - The Retriever attaches a 1–3 sentence summary to each evidence item; the
     Builder can often cite using the summary without pulling full text.

---

## 5. Focus on indexed academic sources

Default source priority (configurable per study in `study/brief.md`):

1. **SciELO** (strong for Latin America / open access)
2. **Scopus** and **Web of Science** (via the user's subscription / API keys)
3. **ScienceDirect** (Elsevier)
4. **Google Scholar** (broad discovery; used to *find* DOIs, then resolve them)
5. **Crossref / OpenAlex** (open metadata for validation and deduplication)
6. **General web** (last resort; flagged as non-academic)

Notes on access:
- Scopus, Web of Science and many ScienceDirect full texts require
  **institutional API keys or subscriptions**. Provide them via `.env`. Without
  them the adapter degrades gracefully to metadata-only (via Crossref/OpenAlex)
  and records the limitation.
- Google Scholar has no official API; the adapter treats results as *leads* and
  resolves them to a DOI/Crossref record for a stable, citable ID.

---

## 6. Traceability & validation

### Registry record (one per paper) — `registry/papers.jsonl`
```
{
  "id": "p_<16-hex>",              # stable, derived from normalized DOI or URL
  "title": "...",
  "authors": ["..."],
  "year": 2020,
  "venue": "...",
  "doi": "10.xxxx/...",            # if known
  "url": "https://...",
  "source": "scopus",              # which adapter found it
  "content_hash": "sha256:...",    # of fetched bytes (integrity)
  "fetched_at": "2024-...Z",
  "validated_at": "2024-...Z",     # last existence check
  "status": "ok|unreachable|no_doi",
  "retrieved_by": "retriever",
  "queries": ["..."],              # queries that surfaced it
  "notes": "..."
}
```

### Evidence item — `registry/evidence.jsonl`
```
{
  "ev_id": "ev://p_<16-hex>#c<chunk>",
  "paper_id": "p_<16-hex>",
  "chunk": 3,
  "summary": "1–3 sentence neutral summary",
  "excerpt": "≤ 80 words verbatim",
  "relevance": 0.0-1.0
}
```

### Validation
`python -m core.registry validate registry/papers.jsonl`
- For each record: re-check URL/DOI resolves (HTTP HEAD/GET, or Crossref lookup).
- Update `validated_at` and `status`.
- Report any source that no longer exists → flagged so claims citing it can be
  reviewed.
- This gives you a repeatable **"does this source still exist?"** method
  independent of any LLM.

---

## 7. Human-in-the-loop

Checkpoints (see README) let you steer before tokens are spent:
confirm brief → confirm sources/evidence → confirm each draft → decide iteration.
Everything is also editable on disk (the `output/*.json` checkpoint files), so
the process is scriptable but you stay in control.

---

## 8. Iteration & stopping criteria

The Builder↔Critic loop stops when any of:
- the Critic reports only **minor** findings, or
- `max_rounds` is reached, or
- you accept the draft at a checkpoint, or
- the `token_budget` soft limit is hit.

---

## 9. Per-study replication checklist

1. `cp -r study study_<topic>` (or edit `study/` in a fresh copy of the repo).
2. Fill `study/brief.md`: the object, the questions, the source priorities,
   inclusion/exclusion criteria.
3. Fill `study/workplan.md`: required sections (e.g., MPAs, tech challenges,
   viewpoint map) and the output format.
4. (optional) List expected viewpoints in `study/viewpoints.yaml`.
5. Set the provider + keys in `config.yaml` / `.env`.
6. Run the orchestrator; approve at checkpoints.
7. Run validation; export `output/viewpoint_map.md`.

---

## 10. Explicit non-goals (keep it simple)

- Not a full systematic-review tool (no PRISMA automation by default).
- No vector DB required to start (lexical selection is enough; upgrade later).
- No GUI. CLI + Markdown/JSON files only.
- No silent web browsing by the Builder — by design.
