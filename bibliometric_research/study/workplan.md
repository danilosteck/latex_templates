# Workplan — required structure of the output document

> The Builder must produce a document matching this structure. Define sections,
> order, depth, and the required output format. Keep it concrete and short.

## Required sections

1. **Scope & method**
   - Study object, questions, sources searched, inclusion/exclusion.
   - How the viewpoint map was built (traceable to evidence IDs).

2. **Landscape overview**
   - Volume/trend of literature, key venues and authors, main clusters.

3. **Map of viewpoints**  ← the core deliverable
   - For each viewpoint: a short neutral description, the *positions* held,
     representative sources (`ev://…`), and what distinguishes it from others.
   - Organize by the viewpoint axes in the brief.
   - Aim for genuine plurality, not a single consensus narrative.

4. **Points of agreement and contestation**
   - Where sources converge; where they directly disagree (and why).

5. **MPAs** (Main Points of Argumentation / Analytical positions)
   - List each with: the claim, supporting evidence IDs, strength, caveats.

6. **Technical challenges & open problems**
   - For each: description, who raises it, evidence IDs, status (open/contested).

7. **Gaps & under-explored angles**
   - Informed by what the evidence does NOT cover.

8. **Reference list**
   - One line per cited paper, resolved from the registry (authors, year, title,
     venue, DOI/URL). Every `ev://…` in the text must appear here.

## Constraints

- Every substantive claim cites at least one `ev://…` internal reference.
- Do NOT introduce facts not present in the evidence. If something is missing,
  emit an **evidence request** instead.
- Neutral, descriptive tone; attribute positions to their sources.
- Target length: ___ words (soft limit to control tokens).

## Output format

- Primary: Markdown (`output/document_vN.md`).
- Structured companion: `output/document_vN.json` (sections + citations), so the
  Critic and the viewpoint-map exporter can read it mechanically.
