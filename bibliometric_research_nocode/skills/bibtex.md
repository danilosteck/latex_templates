# Skill — BibTeX Reference File Builder

> **Platform-agnostic skill.** Written as plain markdown prompts + a template, so it
> works in any AI chat tool (Claude Code, DeepSeek, OpenAI Codex, Gemini, etc.) with
> no code. Its job: maintain a **valid `.bib` file** of every consulted reference, kept
> in sync with the paper records and traceable by paper ID.

## Purpose

Produce and keep updated `references/library.bib` — a standard BibTeX file that anyone
can drop into LaTeX, Zotero, Mendeley, JabRef, or Google Docs/Word (via a BibTeX
import). Every entry maps 1:1 to a paper record (`papers/P-XXXX.md`) and its cache
entry, so the `.bib` is as traceable as the rest of the blueprint.

## The traceability chain this skill preserves

```
references/library.bib   ←  papers/P-XXXX.md  ←  cache/papers/P-XXXX.md  ←  DOI / URL
       (cite key)             (record)              (distilled source)
```

- The **BibTeX cite key** is the paper ID (e.g. `P-0007`), so `\cite{P-0007}` in
  LaTeX matches `[P-0007]` in the deliverable and `P-0007.md` on disk. This is the
  whole point: one stable key, everywhere.
- If a paper has no DOI, the `url` field carries the stable landing page.
- If metadata is incomplete, the entry still goes in but is tagged for validation
  (see "Incomplete entries" below).

## Inputs it reads

1. `papers/P-XXXX.md` records (authoritative metadata per paper).
2. `references/bibliography.md` (APA-style line per ID) and
   `references/id-registry.md` (ID ↔ title/author/year/DOI map).
3. `references/library.bib` (the existing `.bib`, to update without duplicates).

## Entry type selection (BibTeX)

Pick the `@type` from the paper record's `source type` and `venue`:

| Paper record says            | BibTeX entry type |
|-----------------------------|-------------------|
| journal article             | `@article`        |
| conference / proceedings    | `@inproceedings`  |
| book chapter                | `@incollection`   |
| book                        | `@book`           |
| preprint (arXiv/SSRN)       | `@misc`           |
| report / grey (WHO, etc.)   | `@techreport`     |
| web page                    | `@misc`           |
| thesis                      | `@phdthesis` / `@mastersthesis` |

## Field mapping (paper record → BibTeX)

| Paper record field | BibTeX field(s) | Notes |
|--------------------|-----------------|-------|
| Authors (First Last; …) | `author` | Convert to `Last, First and Last, First`. Use `{…}` to protect corporate authors. |
| Title | `title` | Wrap acronyms/capitalisation in `{…}` to protect them. |
| Year | `year` | Digits only. |
| Venue / Journal | `journal` (article) / `booktitle` (inproceedings) / `publisher` (book) | |
| Volume / issue / pages | `volume`, `number`, `pages` | Pages as `12--34`. Omit what you don't have. |
| DOI | `doi` | Without the `https://doi.org/` prefix. |
| Stable URL | `url` | Full URL. |
| Language | `language` (optional) | e.g. `portuguese`. |
| Indexed in | `keywords` (optional) | e.g. `Scopus; SciELO`. |
| Paper ID | cite key | The key itself, e.g. `P-0007`. |

Use the canonical skeleton in `templates/bibtex-entry.md`.

## Procedure (run this skill)

### A. Build / update the whole file (full pass)

1. Read every `papers/P-XXXX.md` record and the existing `references/library.bib`.
2. For each record **not yet in the `.bib`**, add one entry:
   - cite key = paper ID (lower-case not required; keep `P-0007` uppercase for consistency),
   - correct entry type from the table above,
   - map fields per the table,
   - keep field order: `author, title, journal/booktitle, year, volume, number, pages, publisher, doi, url`.
3. For each record **already present**, update only if metadata changed; do not duplicate.
4. Keep entries sorted by paper ID (ascending) so diffs are readable.
5. Preserve this header at the top of the file:

   ```
   % library.bib — Bibliometric Agent Blueprint
   % One entry per consulted reference. Cite key = paper ID (e.g. P-0007).
   % Traceability: cite key -> papers/P-0007.md -> cache/papers/P-0007.md -> DOI/URL
   % Generated/maintained by skills/bibtex.md (prompt-only, no code). Do not hand-edit
   % metadata here without also updating the paper record.
   ```

6. Validate each entry against the checklist below.
7. Report: added N, updated M, skipped K (with reasons), plus any incomplete entries.

### B. Add a single reference (incremental)

When Agent 1 creates a new paper record, append its entry immediately:

1. Grep `references/library.bib` for the cite key — if present, stop (no duplicate).
2. Add the entry in sorted position.
3. Return the exact entry text so the caller can confirm.

### C. Regenerate from the bibliography (fallback)

If a paper record exists but the `.bib` entry is missing or corrupt, rebuild that
entry from `references/bibliography.md` + `references/id-registry.md` instead.

## Incomplete entries (honesty over polish)

If a required field is unknown (e.g. no page numbers, no volume):

- Include the entry anyway with the fields you have.
- Do **not** invent values.
- Add a `note = {metadata incomplete}` field, and list the ID in the skill's report
  so Agent 3 / the human can complete it from the paper record.

Example:

```bibtex
@article{P-0012,
  author  = {Silva, J. and Costa, M.},
  title   = {Urban Heat in Tropical Cities},
  journal = {Journal of Climate Studies},
  year    = {2020},
  doi     = {10.1000/jcs.2020.12},
  note    = {metadata incomplete}
}
```

## Validation checklist (per entry)

- [ ] Cite key equals a real paper ID present in `references/id-registry.md`.
- [ ] Entry type matches the source type.
- [ ] `author`, `title`, `year` present (or marked incomplete).
- [ ] `title`/`author` protect capitalisation with `{…}` where needed.
- [ ] At least one locator: `doi` or `url`.
- [ ] No trailing commas before `}`; braces balanced.
- [ ] No duplicate cite key.
- [ ] Special characters escaped where required: `&` → `\&`, `%` → `\%`, `_` → `\_`,
      `#` → `\#`. Keep UTF-8 accents as-is if the target tool supports Unicode
      (modern BibTeX/biblatex do); otherwise use LaTeX accents (`é` → `{\'e}`).
- [ ] Non-ASCII-safe tools: prefer the accented-letter forms noted above.

## Platform notes (why this stays agnostic)

- The skill is **just instructions + a skeleton**; every AI tool can follow it.
- The `.bib` is a plain text file — no plugin, no script, no build step.
- Any tool that can read files can run the "full pass"; a plain chat can run it by
  pasting `papers/P-XXXX.md` contents and getting entries back to paste into `.bib`.
- Import targets that need no BibTeX: Zotero/Mendeley accept `.bib` directly;
  Google Scholar/Word users can copy the DOI from the `doi` field.

## Token-saving rules

- Do **not** re-emit the whole `.bib` when adding one entry — output only the new
  entry (incremental mode B).
- Read paper records, not cache files, to source metadata (records are shorter).
- In a full pass, process in ID order and skip IDs already present.

## What this skill does NOT do

- It does not fetch or verify sources (that is Agent 1 + `templates/source-validation.md`).
- It does not write the deliverable (that is Agent 2).
- It does not change a paper's verification status — it only mirrors metadata.
