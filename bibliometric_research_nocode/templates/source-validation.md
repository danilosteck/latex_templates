# Source Existence Validation

> Procedure run by Agent 3 (and available to the human owner) to confirm a cited
> source is real and matches its claims. Output a filled table into the review file.

## For each paper record (sample or all)

| Step | Check | How (prompt-level) | Pass criteria |
|------|-------|--------------------|---------------|
| 1 | DOI resolves | Ask the browser/agent to open `https://doi.org/<DOI>` | Lands on the paper's page |
| 2 | Title/authors/year match | Compare page metadata with `papers/P-XXXX.md` | Exact (allowing minor formatting) |
| 3 | Venue exists | Confirm journal/publisher on the landing page | Matches record |
| 4 | Indexed claim | Confirm presence in WoS/Scopus/SciELO if the record says so | Present, or record corrected |
| 5 | Quote locatable | Search the text for the exact quote | Found at/near stated location |
| 6 | Retraction check | Look for "retracted"/"withdrawn" notices | None, or flagged |
| 7 | Cache integrity | `cache/papers/P-XXXX.md` matches the current source | Consistent |

## Recording

Fill and save in the Critic review under "Source validation sample":

```
| Paper ID | DOI resolves | Metadata match | Quote found | Verdict |
| P-0007   | yes          | yes            | yes         | PASS    |
| P-0011   | no (404)     | n/a            | n/a         | FAIL → re-fetch |
```

## On failure

- **Link rot / 404:** ask Agent 1 to locate the current DOI/landing page and update
  both the paper record and the cache entry.
- **Metadata mismatch:** correct the record; if irreconcilable, mark
  `verified: no` and consider exclusion.
- **Quote not found:** demote the claim (remove the quote or replace it); flag the
  paper as `partial`.
- **Retraction:** exclude from the deliverable, add a note, and tell Agent 2 to revise.

## Human quick-check (no tools)

Even without any special tooling, the owner can validate a source by pasting its
DOI into <https://doi.org> or its title into Google Scholar and eyeballing the first
result against the paper record. This is sufficient for the "does it exist" check.
