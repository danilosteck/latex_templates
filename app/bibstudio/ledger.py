"""The citation ledger: deterministic checks on a draft.

This is the guarantee the prompt cannot provide (APP_PLAN.md §12). It runs on
every draft, costs nothing, and never asks a model for an opinion about whether a
citation exists.

Checks:
  - every substantive paragraph carries at least one citation
  - every cited ID exists in the project
  - every quoted span is an actual substring of the cited evidence
  - every required section is present
  - every declared viewpoint is represented
  - source mix (peer-reviewed vs grey, DOI verified)
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable

from .extract import normalize_for_match
from .models import Brief, Evidence, Ledger, Paper

QUOTE_RE = re.compile(r"[“\"]([^”\"]{20,400})[”\"]")


def citations(text: str) -> list[tuple[str, int | None]]:
    out: list[tuple[str, int | None]] = []
    for m in re.finditer(r"\[(P-\d{4})(?:\s*,?\s*p\.?\s*(\d+))?\]", text):
        out.append((m.group(1), int(m.group(2)) if m.group(2) else None))
    return out


def cited_ids(text: str) -> list[str]:
    seen: list[str] = []
    for pid, _ in citations(text):
        if pid not in seen:
            seen.append(pid)
    return seen


def split_sections(document: str) -> list[tuple[str, str]]:
    """Split markdown into (heading, body) pairs on ## headings."""
    sections: list[tuple[str, str]] = []
    heading: str | None = None
    buf: list[str] = []
    for line in document.splitlines():
        if re.match(r"^#{1,6}\s+", line):
            if heading is not None:
                sections.append((heading, "\n".join(buf).strip()))
            heading = re.sub(r"^#{1,6}\s+", "", line).strip()
            buf = []
        else:
            buf.append(line)
    if heading is not None:
        sections.append((heading, "\n".join(buf).strip()))
    return sections


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", text).strip()


def _paragraphs(body: str) -> list[str]:
    out: list[str] = []
    for block in re.split(r"\n\s*\n", body):
        block = block.strip()
        if not block:
            continue
        if block.startswith(("#", "|", ">", "```")):
            continue
        out.append(block)
    return out


def check(
    document: str,
    papers: list[Paper],
    evidence: list[Evidence],
    brief: Brief,
) -> Ledger:
    ledger = Ledger()
    by_id = {p.id: p for p in papers}
    ev_by_paper: dict[str, list[str]] = {}
    for ev in evidence:
        ev_by_paper.setdefault(ev.paper_id, []).append(normalize_for_match(ev.text))

    all_cites = citations(document)
    ledger.citations_total = len(all_cites)
    found_ids = {pid for pid, _ in all_cites}
    ledger.missing = sorted(pid for pid in found_ids if pid not in by_id)
    ledger.citations_resolved = sum(1 for pid, _ in all_cites if pid in by_id)

    # a page locator must correspond to a page actually extracted from that source
    pages_by_paper: dict[str, set[int]] = {}
    for ev in evidence:
        if ev.page:
            pages_by_paper.setdefault(ev.paper_id, set()).add(ev.page)
    seen_page_issues: set[str] = set()
    for pid, page in all_cites:
        if page is None or pid not in by_id:
            continue
        if page not in pages_by_paper.get(pid, set()):
            issue = f"[{pid} p.{page}] — no evidence extracted from page {page}"
            if issue not in seen_page_issues:
                seen_page_issues.add(issue)
                ledger.page_mismatches.append(issue)

    # paragraphs without citations
    for block in _paragraphs(document):
        words = block.split()
        if len(words) < 15:
            continue
        if citations(block):
            continue
        snippet = re.sub(r"\s+", " ", block)[:120]
        ledger.paragraphs_without_citation.append(snippet)

    # quotes must exist in the cited source
    for block in _paragraphs(document):
        cites = citations(block)
        if not cites:
            continue
        paper_ids = {pid for pid, _ in cites}
        for quote in QUOTE_RE.findall(block):
            ledger.quote_checks += 1
            needle = normalize_for_match(quote)
            hay = " ".join(
                text for pid in paper_ids for text in ev_by_paper.get(pid, [])
            )
            if needle and needle not in hay:
                ledger.quote_mismatches.append(f"{quote[:70]}… (cited: {', '.join(sorted(paper_ids))})")

    # section coverage
    headings = [h for h, _ in split_sections(document)]
    norm_headings = [_norm(h) for h in headings]
    ledger.sections_required = list(brief.deliverable.sections)
    for required in ledger.sections_required:
        target = _norm(required)
        # tolerate "Main points of analysis (MPA)" matching "Main points of analysis"
        hit = any(target in h or h in target for h in norm_headings if h)
        if hit:
            ledger.sections_present.append(required)
        else:
            ledger.sections_missing.append(required)

    # viewpoint coverage
    doc_norm = _norm(document)
    for vp in brief.viewpoints:
        ledger.viewpoints_required.append(vp.label)
        words = [w for w in _norm(vp.label).split() if len(w) > 4]
        if not words:
            words = _norm(vp.label).split()
        if words and sum(1 for w in words if w in doc_norm) >= max(1, len(words) // 2):
            ledger.viewpoints_covered.append(vp.label)
        elif _norm(vp.label) and _norm(vp.label) in doc_norm:
            ledger.viewpoints_covered.append(vp.label)

    # source mix
    ledger.sources_total = len(papers)
    ledger.sources_peer_reviewed = sum(1 for p in papers if p.source_type == "peer_reviewed")
    ledger.sources_grey = sum(1 for p in papers if p.source_type == "grey")
    ledger.sources_doi_verified = sum(1 for p in papers if p.verified == "yes")
    return ledger.compute_verdict()


def references_markdown(papers: Iterable[Paper], ids: Iterable[str]) -> str:
    """Render the References section from registered records, never from the model."""
    index = {p.id: p for p in papers}
    lines = ["## References", ""]
    for pid in sorted(set(ids)):
        paper = index.get(pid)
        if paper is None:
            lines.append(f"- {pid} — **unresolved citation**")
            continue
        authors = ", ".join(paper.authors[:6]) or "n/a"
        if len(paper.authors) > 6:
            authors += " et al."
        year = paper.year or "n.d."
        venue = f". {paper.venue}" if paper.venue else ""
        doi = f" https://doi.org/{paper.doi}" if paper.doi else (f" {paper.url}" if paper.url else "")
        verified = "" if paper.verified == "yes" else f" _(verification: {paper.verified})_"
        lines.append(f"- **[{pid}]** {authors} ({year}). {paper.title}{venue}.{doi}{verified}")
    if len(lines) == 2:
        lines.append("_No sources cited._")
    return "\n".join(lines)


def ensure_references(document: str, papers: list[Paper]) -> str:
    """Replace or append the References section with the generated one."""
    kept: list[str] = []
    for heading, text in split_sections(document):
        if _norm(heading).startswith("reference"):
            continue
        kept.append(f"## {heading}\n\n{text}".strip())
    # citations are collected from the body only: whatever the model wrote under
    # References is discarded, and must not seed the generated list
    body = "\n\n".join(kept)
    refs = references_markdown(papers, cited_ids(body))
    return "\n\n".join(kept + [refs]).strip() + "\n"
