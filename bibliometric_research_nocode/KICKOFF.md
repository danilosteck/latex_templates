# KICKOFF — copy-paste prompts to run a study

> These are the exact prompts to give your AI tool. They reference files in the repo;
> in Claude Code / Codex use `@file`; in a web chat, paste the file contents when asked.
> Replace `STUDY = studies/<your-slug>/` throughout.

---

## Step 0 — setup (once)

> You are operating the **Bibliometric Agent Blueprint** in this repository.
> Read `README.md` to learn the structure. Do not write anything yet. Confirm you
> understand the three agents, the caching rule, and the traceability rule in one
> short paragraph.

---

## Step 1 — Researcher (Agent 1)

> Act as **Agent 1 (Researcher)**. Read `STUDY/workplan.md`, then
> `agents/01-researcher.md` and the templates in `templates/`.
> Execute **one retrieval round** for every theme in the Workplan, following the
> priority source order (Web of Science/Scopus → SciELO → Google Scholar → others).
> For each source: distil into `cache/`, create a paper record `papers/P-XXXX.md`,
> add its BibTeX entry to `references/library.bib` via `skills/bibtex.md`
> (cite key = paper ID), update `references/`. Log queries in
> `templates/search-log.md` (copy its content into `STUDY/search-log.md`). Respect paywalls.
> When done, output a **round report** (added IDs, skipped, gaps remaining).

---

## Step 2 — Author (Agent 2)

> Act as **Agent 2 (Author)**. Read `STUDY/workplan.md`, `agents/02-author.md`,
> and the `papers/` index + `references/bibliography.md`.
> Write the deliverable **using only cached/papers material**. Read individual
> `cache/papers/*.md` files only when you use that source. Cite every factual claim
> with `[P-xxxx]`. Build the **Viewpoint Map** first. If you need data not in cache,
> append a **Fetch Request** to `STUDY/fetch-requests.md` and continue.
> Save to the output path in the Workplan.

---

## Step 3 — Process fetch requests (Agent 1 again)

> Act as **Agent 1 (Researcher)**. Read `STUDY/fetch-requests.md`. Process every
> OPEN request: find an appropriate indexed source, cache it, create a paper record,
> update references, and mark the request DONE with the resulting IDs (or NOT FOUND
> with an explanation). Do not invent sources.

---

## Step 4 — Critic (Agent 3)

> Act as **Agent 3 (Critic)**. Read `STUDY/workplan.md`, the latest deliverable in
> `outputs/`, `agents/03-critic.md`, and `templates/source-validation.md`.
> Score the deliverable on the 9 dimensions (including BibTeX integrity), validate
> ≥5 sources (DOI resolves, metadata match, quote found), and check that
> `references/library.bib` has one valid entry per consulted paper. Produce
> `outputs/<slug>-review-vN.md` using the required review structure. Put fetch needs
> under "→ Agent 1" and edits under "→ Agent 2". Do not edit the deliverable.

---

## Step 5 — Revise (Agent 2) and loop

> Act as **Agent 2 (Author)**. Read the latest review in `outputs/`. Address every
> "→ Agent 2" item. Read the new cache entries added from "→ Agent 1" items. Produce
> the revised deliverable as the next version. Then ask me whether to re-run the Critic.

---

## Step 6 — Freeze

> Save the passing deliverable as `outputs/<slug>-final.md`, run the full
> source-validation pass, and update `STUDY/round-summary.md`. Report the final
> list of paper IDs and their verification status.

---

## Anytime — BibTeX skill (standalone)

> Run the **BibTeX skill** (`skills/bibtex.md`) in full-pass mode. Read every
> `papers/P-XXXX.md` and the existing `references/library.bib`, add any missing
> entries (cite key = paper ID, correct entry type per `templates/bibtex-entry.md`),
> update changed entries, remove duplicates, keep entries sorted by ID, and keep the
> file header. Validate each entry and report added/updated/skipped + any incomplete
> entries. Do not re-emit the whole file if only adding one entry.
