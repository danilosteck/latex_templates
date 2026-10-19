# Workplan — Research Brief

> Fill this in once per study. Every agent reads this file first.
> Keep it short and concrete; the agents infer everything else from it.

## 1. Study object

- **Topic / object of study:** (e.g. "the effect of urban green roofs on city heat islands")
- **Discipline(s):** (e.g. urban climatology, environmental engineering, public policy)
- **Time frame of interest:** (e.g. 2010–present)
- **Geographic scope:** (e.g. global / Brazil / OECD) — leave "global" if none

## 2. Research question(s)

State the questions the deliverable must answer. These are the "skeleton" the
Author agent builds the document around.

- RQ1:
- RQ2:
- RQ3:

## 3. Search themes & seed keywords

The Researcher agent turns each theme into queries for indexed sources.
List synonyms in English **and** other relevant languages (e.g. Portuguese/Spanish
for SciELO).

| Theme | Core keywords (EN) | Extra languages / synonyms | Target sources |
|-------|--------------------|----------------------------|----------------|
| T1    |                    |                            | Web of Science, Scopus, SciELO |
| T2    |                    |                            | Google Scholar, ScienceDirect |
| T3    |                    |                            |                  |

## 4. Viewpoints to map (optional but recommended)

Different academic schools / stances you expect. The Critic uses these to check
the map is balanced and the Author uses them to structure the "viewpoint map".

- Viewpoint A: (e.g. "green infrastructure as primary mitigation")
- Viewpoint B: (e.g. "reflective materials over vegetation")
- Viewpoint C: (e.g. "social equity framing of heat exposure")
- (add more)

## 5. Deliverable specification (the "MPA / tech-challenges" style document)

- **Output file:** `outputs/<slug>-v1.md`
- **Required sections** (check the ones that apply; add your own):
  - [ ] Executive summary
  - [ ] Scope & method
  - [ ] **Viewpoint map** (who argues what, and on what evidence)
  - [ ] Main Points of Analysis (MPA) — grouped by theme/viewpoint
  - [ ] Technical / methodological challenges (per viewpoint or per theme)
  - [ ] Evidence gaps & open questions
  - [ ] References (paper IDs + full references)
- **Length target:** (e.g. ~2500 words)
- **Tone / audience:** (e.g. academic funding committee)
- **Citation style:** (e.g. numeric IDs `[P-00xx]` + footnote to `references/bibliography.md`)
- **BibTeX output:** keep `references/library.bib` updated via `skills/bibtex.md` (cite key = paper ID). [ ] yes  [ ] no

## 6. Inclusion / exclusion criteria

- **Include if:** peer-reviewed, date range, language, relevant to RQ…
- **Exclude if:** non-academic opinion pieces, predatory journals, no accessible source…
- **Minimum number of distinct sources:** (e.g. 20)

## 7. Definitions & assumptions

- Any term the agents must interpret a specific way.

## 8. Constraints

- Max tokens / effort per round: (optional)
- Deadlines or iteration budget: (optional)
