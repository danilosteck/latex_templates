"""The run engine: plan → discover → ingest → outline → draft → critique → freeze.

Design notes
------------
* Checkpoints are *barriers*, not polls: the worker thread blocks on an Event and
  the API releases it. That is what makes "I want to be consulted" real without
  turning the engine into a state machine the UI must reimplement.
* Every phase appends a typed event to `runs/<id>/log.jsonl`. The UI polls that
  file (offset-based), so a browser refresh, a second tab, or a crash never loses
  the narrative of a run.
* The engine never trusts the model for anything checkable: IDs, references,
  quotes, BibTeX and section coverage are computed here.
"""

from __future__ import annotations

import json
import re
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from . import bibtex, ledger as ledger_mod, retrieval
from .agents import AgentFile, estimate_tokens, render_variables, variables_from_brief
from .extract import chunk, excerpt, extract_text, summarize
from .llm import LLMClient, LLMError
from .models import (
    Brief,
    Candidate,
    Evidence,
    Outline,
    OutlineSection,
    Paper,
    ReviewFinding,
    RunState,
    utcnow,
)
from .store import Project

MAX_CHUNKS_PER_PAPER = 6
MAX_EVIDENCE_PER_SECTION = 10
EXCERPT_WORDS = 90


class Cancelled(Exception):
    pass


# ---------------------------------------------------------------------------
# run context
# ---------------------------------------------------------------------------


@dataclass
class RunContext:
    project: Project
    run_id: str
    brief: Brief
    llm: LLMClient
    agents: dict[str, AgentFile]
    state: RunState
    cost_cap_usd: float = 2.0
    cancel_flag: threading.Event = field(default_factory=threading.Event)
    _decision: threading.Event = field(default_factory=threading.Event)
    _payload: dict[str, Any] = field(default_factory=dict)
    candidates: list[Candidate] = field(default_factory=list)
    outline: Outline | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def run_dir(self) -> Path:
        return self.project.run_dir(self.run_id)

    # -- events -------------------------------------------------------------

    def emit(self, kind: str, message: str = "", **data: Any) -> None:
        event = {
            "ts": utcnow(),
            "phase": self.state.phase,
            "kind": kind,
            "message": message,
            "data": data,
        }
        with (self.run_dir / "log.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        self.save_state()

    def save_state(self) -> None:
        self.state.tokens_in = self.llm.tokens_in
        self.state.tokens_out = self.llm.tokens_out
        self.state.cost_usd = round(self.llm.cost_usd, 4)
        self.project.save_run_state(self.state)

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        self.emit("warning", message)

    def check_cancel(self) -> None:
        if self.cancel_flag.is_set():
            raise Cancelled()

    def set_phase(self, phase: str) -> None:
        self.state.phase = phase
        self.emit("phase", phase)

    # -- checkpoints --------------------------------------------------------

    def checkpoint(self, kind: str, summary: str, data: dict[str, Any]) -> dict[str, Any]:
        from .models import CheckpointKind, CheckpointRequest

        kind_literal: CheckpointKind = kind  # type: ignore[assignment]
        self.state.status = "waiting"
        self.state.checkpoint = CheckpointRequest(kind=kind_literal, summary=summary, data=data)
        self.emit("checkpoint", summary, checkpoint_kind=kind, payload=data)
        self._decision.clear()
        self._payload = {}
        while not self._decision.is_set():
            if self.cancel_flag.is_set():
                raise Cancelled()
            self._decision.wait(0.4)
        self.state.status = "running"
        self.state.checkpoint = None
        decision = dict(self._payload)
        self.emit("checkpoint.resolved", decision.get("action", "continue"), decision=decision)
        return decision

    def resolve(self, payload: dict[str, Any]) -> None:
        self._payload = dict(payload)
        self._decision.set()

    # -- LLM accounting -----------------------------------------------------

    def budget_left(self) -> float:
        return max(0.0, self.cost_cap_usd - self.llm.cost_usd)

    def ask(self, agent_id: str, user: str, *, temperature: float | None = None,
            max_tokens: int | None = None):
        agent = self.agents[agent_id]
        system = render_variables(agent.system_prompt(), variables_from_brief(self.brief))
        return self.llm.complete(
            system,
            user,
            temperature=temperature if temperature is not None else agent.temperature(),
            max_tokens=max_tokens or agent.max_tokens(),
        )


# ---------------------------------------------------------------------------
# phases
# ---------------------------------------------------------------------------


def _plan(ctx: RunContext) -> list[tuple[str, str]]:
    ctx.set_phase("plan")
    queries = ctx.brief.queries()
    # Only spend a model call when the form gave us nothing to search with.
    if not ctx.brief.themes and ctx.llm.provider != "mock":
        try:
            data, res = ctx.llm.complete_json(
                ctx.agents["researcher"].system_prompt(),
                f"Study object: {ctx.brief.topic}\nTitle: {ctx.brief.title}\n"
                f"Questions: {'; '.join(rq.question for rq in ctx.brief.rqs)}\n"
                f"Languages: {', '.join(ctx.brief.lit_languages)}",
            )
            for item in data.get("queries", [])[:8]:
                q = str(item.get("query", "")).strip()
                if q:
                    queries.append((str(item.get("theme") or "general"), q))
        except LLMError as exc:
            ctx.warn(f"query planning fell back to the form: {exc}")
    ctx.emit("queries", f"{len(queries)} search queries", queries=[
        {"theme": t, "query": q} for t, q in queries])
    return queries


def _retrieval_context(ctx: RunContext) -> retrieval.RetrievalContext:
    return build_retrieval_context(ctx.brief, ctx.project.workspace)


def build_retrieval_context(brief: Brief, workspace) -> retrieval.RetrievalContext:
    """Shared by the engine and the API's 'test sources' probe."""
    settings = workspace.settings()
    return retrieval.RetrievalContext(
        mailto=str(settings.get("contact_email") or ""),
        openalex_key=str(workspace.openalex_key() or ""),
        year_from=brief.year_from,
        year_to=brief.year_to,
        languages=brief.lit_languages,
        exclude_terms=brief.exclude_terms,
        include_peer_reviewed=brief.include_peer_reviewed,
        include_grey=brief.include_grey,
    )


def _discover(ctx: RunContext, queries: list[tuple[str, str]]) -> list[Candidate]:
    ctx.set_phase("discover")
    rctx = _retrieval_context(ctx)
    sources = ctx.brief.sources_enabled or ["openalex", "crossref"]
    cands = retrieval.search(queries, sources, rctx, limit_per_query=10)
    for warning in rctx.warnings:
        ctx.warn(warning)
    cap = max(5, ctx.brief.max_candidates)
    cands = cands[:cap]
    (ctx.run_dir / "candidates.json").write_text(
        retrieval.dump_candidates(cands), "utf-8")
    ctx.emit("candidates", f"{len(cands)} unique candidates", count=len(cands),
             filtered_out=rctx.filtered_out, sources=rctx.summary(),
             data=[{"title": c.title, "year": c.year, "venue": c.venue,
                    "doi": c.doi, "score": c.score, "theme": c.theme,
                    "oa": bool(c.oa_pdf)} for c in cands[:60]])
    if not cands:
        # Emit the per-source report first so the UI can show it next to the error.
        ctx.emit("diagnose", "search produced no candidates",
                 sources=rctx.summary(), filtered_out=rctx.filtered_out,
                 queries=[{"theme": t, "query": q} for t, q in queries])
        raise RuntimeError(retrieval.failure_report(queries, sources, rctx))
    return cands


def _ingest(ctx: RunContext, cands: list[Candidate]) -> None:
    ctx.set_phase("ingest")
    papers = ctx.project.papers()
    evidence = ctx.project.evidence()
    by_doi = {p.doi.lower(): p for p in papers if p.doi}
    client = httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=True,
                          headers={"User-Agent": retrieval.USER_AGENT})
    fetches = 0
    max_fetches = max(1, ctx.brief.max_fetches)

    for cand in cands:
        ctx.check_cancel()
        existing = by_doi.get((cand.doi or "").lower()) if cand.doi else None
        if existing is not None:
            ctx.emit("source.skipped", f"{existing.id} already registered: {existing.title[:70]}")
            continue

        paper = Paper(
            id=ctx.project.next_paper_id(),
            title=cand.title,
            authors=cand.authors,
            year=cand.year,
            venue=cand.venue,
            doi=cand.doi,
            url=cand.url,
            source=cand.source,
            abstract=cand.abstract,
            queries=[getattr(cand, "_query", cand.theme)],
            source_type="peer_reviewed" if (cand.doi and cand.venue) else "grey",
        )
        items: list[Evidence] = []
        text_blocks: list[tuple[str, str]] = []  # (locator, text)

        if cand.oa_pdf and fetches < max_fetches:
            fetches += 1
            try:
                resp = client.get(cand.oa_pdf)
                if resp.status_code == 200 and len(resp.content) < 25 * 1024 * 1024:
                    blob = ctx.project.workspace.put_blob(resp.content)
                    extracted = extract_text(resp.content)
                    paper.content_hash = blob
                    paper.pages = len(extracted.pages)
                    if extracted.page_based and not extracted.is_thin():
                        paper.full_text = "oa"
                        for i, page in enumerate(extracted.pages, 1):
                            if page.strip():
                                text_blocks.append((f"p.{i}", page))
                    elif not extracted.is_thin():
                        paper.full_text = "oa"
                        text_blocks.append(("text", extracted.text))
                    else:
                        paper.full_text = "abstract_only"
                        paper.verification_note = extracted.note or "extracted text too thin"
                else:
                    paper.full_text = "paywalled"
            except Exception as exc:
                paper.full_text = "paywalled"
                paper.verification_note = f"fetch failed: {type(exc).__name__}"
        else:
            paper.full_text = "abstract_only" if cand.abstract else "paywalled"

        if text_blocks:
            per_paper = 0
            for locator, page_text in text_blocks:
                blocks = list(chunk(page_text))
                for j, block in enumerate(blocks, 1):
                    if per_paper >= MAX_CHUNKS_PER_PAPER:
                        break
                    if locator == "text":
                        loc = f"c{j}"
                        page_no = None
                    elif len(blocks) == 1:
                        loc = locator
                        page_no = int(locator[2:])
                    else:
                        loc = f"{locator}#c{j}"
                        page_no = int(locator[2:])
                    items.append(Evidence(
                        paper_id=paper.id,
                        locator=loc,
                        page=page_no,
                        text=block,
                        summary=summarize(block),
                    ))
                    per_paper += 1
        elif cand.abstract:
            items.append(Evidence(
                paper_id=paper.id, locator="abstract", page=None,
                text=cand.abstract, summary=summarize(cand.abstract)))

        if not items:
            # A record with no text cannot be cited, so registering it only
            # inflates the source count and the bibliography.
            ctx.emit("source.skipped",
                     f"no text available (paywalled, no abstract): {cand.title[:70]}",
                     reason="no_text", doi=cand.doi)
            continue

        papers.append(paper)
        evidence.extend(items)
        by_doi[(cand.doi or "").lower()] = paper
        ctx.project.save_papers(papers)
        ctx.project.save_evidence(evidence)
        ctx.project.write_paper_record(paper)
        ctx.project.write_evidence_record(paper, items)
        ctx.emit("source.added", f"{paper.id} {paper.title[:80]}",
                 paper_id=paper.id, source=paper.source, full_text=paper.full_text,
                 evidence=len(items), year=paper.year, venue=paper.venue,
                 doi=paper.doi, url=paper.url)

    client.close()
    ctx.state.phase = "ingested"
    ctx.emit("ingest.done", f"{len(papers)} sources, {len(evidence)} evidence items",
             sources=len(papers), evidence=len(evidence))


def _outline(ctx: RunContext) -> Outline:
    ctx.set_phase("outline")
    papers = ctx.project.papers()
    evidence = ctx.project.evidence()
    sections: list[OutlineSection] = []
    for heading in ctx.brief.deliverable.sections:
        if re.match(r"(?i)^references?$", heading.strip()):
            sections.append(OutlineSection(heading=heading, brief="generated from records"))
            continue
        words = {w.lower() for w in re.findall(r"\w{4,}", heading + " " + ctx.brief.topic)}
        scored: list[tuple[int, str]] = []
        for paper in papers:
            hay = (paper.title + " " + paper.abstract).lower()
            hits = sum(1 for w in words if w in hay)
            if paper.id in hay:
                hits += 0
            scored.append((hits, paper.id))
        scored.sort(reverse=True)
        chosen = [pid for hits, pid in scored if hits > 0][:8] or [pid for _, pid in scored[:5]]
        sections.append(OutlineSection(heading=heading, evidence=chosen))
    outline = Outline(sections=sections, viewpoints=[v.label for v in ctx.brief.viewpoints])
    ctx.outline = outline
    (ctx.run_dir / "outline.json").write_text(outline.model_dump_json(indent=2), "utf-8")
    ctx.emit("outline", f"{len(sections)} sections planned",
             sections=[{"heading": s.heading, "evidence": len(s.evidence)} for s in sections])
    return outline


def _evidence_block(evidence: list[Evidence], paper_ids: list[str] | None) -> tuple[str, list[str]]:
    allowed = set(paper_ids) if paper_ids else None
    lines: list[str] = []
    used: list[str] = []
    seen_papers: dict[str, int] = {}
    for ev in evidence:
        if allowed is not None and ev.paper_id not in allowed:
            continue
        if seen_papers.get(ev.paper_id, 0) >= 3:
            continue
        seen_papers[ev.paper_id] = seen_papers.get(ev.paper_id, 0) + 1
        if ev.paper_id not in used:
            used.append(ev.paper_id)
        # render the exact citation form the contract asks for, so the model can
        # copy it instead of inventing a page number
        if ev.page:
            line = f"- [{ev.paper_id} p.{ev.page}]"
        else:
            line = f"- [{ev.paper_id}]"
        if ev.locator == "abstract":
            line += " (abstract)"
        lines.append(f"{line} {ev.summary} | EXCERPT: {excerpt(ev.text, EXCERPT_WORDS)}")
        if len(lines) >= MAX_EVIDENCE_PER_SECTION:
            break
    return ("\n".join(lines) if lines else "(no evidence available)"), used


def _draft(ctx: RunContext, outline: Outline, findings: list[ReviewFinding] | None = None,
           target_sections: list[str] | None = None) -> str:
    ctx.set_phase("draft")
    evidence = ctx.project.evidence()
    papers = ctx.project.papers()
    by_id = {p.id: p for p in papers}
    document_parts: list[str] = []
    word_budget = max(120, ctx.brief.deliverable.length_words // max(1, len(outline.sections)))

    for section in outline.sections:
        ctx.check_cancel()
        if re.match(r"(?i)^references?$", section.heading.strip()):
            continue
        if target_sections and section.heading not in target_sections:
            continue
        if ctx.llm.cost_usd >= ctx.cost_cap_usd:
            ctx.warn(f"cost cap reached (US$ {ctx.cost_cap_usd:.2f}); remaining sections were skipped")
            document_parts.append(
                f"## {section.heading}\n\n_Section not generated: cost cap reached._")
            continue

        block, used_ids = _evidence_block(evidence, section.evidence)
        relevant = findings or []
        local_findings = [f for f in relevant
                          if section.heading.lower() in (f.location or "").lower()]
        findings_block = ""
        if local_findings:
            findings_block = "\n## CRITIC FINDINGS TO ADDRESS IN THIS SECTION\n" + "\n".join(
                f"- [{f.severity}] {f.issue} → {f.suggestion}" for f in local_findings)

        user = (
            f"STUDY: {ctx.brief.title}\n"
            f"OBJECT: {ctx.brief.topic}\n"
            f"QUESTIONS: " + "; ".join(rq.question for rq in ctx.brief.rqs) + "\n"
            f"OUTPUT LANGUAGE: {ctx.brief.output_language}\n"
            f"TONE: {ctx.brief.deliverable.tone}\n"
            f"VIEWPOINTS TO DISTINGUISH: " + (", ".join(v.label for v in ctx.brief.viewpoints) or "(none declared)") + "\n\n"
            f"SECTION: {section.heading}\n"
            f"WORD BUDGET: ~{word_budget} words\n"
            f"SECTION FOCUS: {section.brief or 'Cover what the heading and the research questions require.'}\n"
            f"{findings_block}\n\n"
            f"EVIDENCE (cite these IDs exactly as written):\n{block}\n\n"
            f"Write the section body now. Markdown only, no heading, no references list."
        )
        try:
            res = ctx.ask("author", user)
        except LLMError as exc:
            ctx.warn(f"section '{section.heading}' failed: {exc}")
            document_parts.append(f"## {section.heading}\n\n_Section generation failed: {exc}_")
            continue
        body = _strip_heading(res.text, section.heading)
        document_parts.append(f"## {section.heading}\n\n{body.strip()}")
        ctx.emit("section.done", section.heading, section=section.heading,
                 words=len(body.split()), cost=round(res.cost_usd, 4),
                 tokens_in=res.tokens_in, tokens_out=res.tokens_out,
                 papers=used_ids[:12])

    # citations for registered papers only; references are generated from records
    document = "\n\n".join(document_parts)
    document = ledger_mod.ensure_references(document, papers)
    return document


def _strip_heading(text: str, heading: str) -> str:
    lines = text.strip().splitlines()
    if lines and re.match(r"^#{1,6}\s+", lines[0]):
        first = re.sub(r"^#{1,6}\s+", "", lines[0]).strip().lower()
        if first == heading.strip().lower() or first in heading.strip().lower():
            return "\n".join(lines[1:]).strip()
    return text.strip()


def _critique(ctx: RunContext, document: str) -> tuple[list[ReviewFinding], Any]:
    ctx.set_phase("critique")
    papers = ctx.project.papers()
    evidence = ctx.project.evidence()
    led = ledger_mod.check(document, papers, evidence, ctx.brief)
    findings: list[ReviewFinding] = []

    # deterministic findings first — these are facts, not opinions
    for pid in led.missing[:8]:
        findings.append(ReviewFinding(
            severity="blocker", target="author", location="whole document",
            issue=f"cited ID {pid} is not a registered source",
            suggestion="remove the citation or fetch the source"))
    for section in led.sections_missing:
        findings.append(ReviewFinding(
            severity="major", target="author", location=section,
            issue=f"required section '{section}' is missing",
            suggestion="add the section"))
    if led.paragraphs_without_citation:
        findings.append(ReviewFinding(
            severity="major", target="author", location="several paragraphs",
            issue=f"{len(led.paragraphs_without_citation)} substantive paragraph(s) carry no citation",
            suggestion="cite a source or rephrase as framing"))
    for mismatch in led.quote_mismatches[:5]:
        findings.append(ReviewFinding(
            severity="blocker", target="author", location=mismatch[:60],
            issue="quoted text does not appear in the cited evidence",
            suggestion="quote exactly or paraphrase without quotation marks"))
    if ctx.brief.viewpoints and len(led.viewpoints_covered) < len(led.viewpoints_required):
        missed = [v for v in led.viewpoints_required if v not in led.viewpoints_covered]
        findings.append(ReviewFinding(
            severity="major", target="researcher", location="viewpoint map",
            issue=f"viewpoints not represented: {', '.join(missed)}",
            suggestion="find sources that argue these positions"))

    # model review (adds judgment: balance, rigor, gaps)
    if ctx.llm.provider != "mock" or not findings:
        try:
            user = (
                f"WORKPLAN SECTIONS: {', '.join(ctx.brief.deliverable.sections)}\n"
                f"RESEARCH QUESTIONS: " + "; ".join(rq.question for rq in ctx.brief.rqs) + "\n"
                f"VIEWPOINTS: " + (", ".join(v.label for v in ctx.brief.viewpoints) or "(none)") + "\n"
                f"REGISTERED SOURCES: {len(papers)} (peer-reviewed: "
                f"{sum(1 for p in papers if p.source_type == 'peer_reviewed')})\n"
                f"MECHANICAL CHECKS: citations {led.citations_resolved}/{led.citations_total} resolved, "
                f"{len(led.paragraphs_without_citation)} uncited paragraphs, "
                f"{len(led.sections_missing)} missing sections\n\n"
                f"DRAFT:\n{document[:16000]}"
            )
            data, res = ctx.llm.complete_json(ctx.agents["critic"].system_prompt(), user)
            for item in data.get("findings", [])[:12]:
                try:
                    findings.append(ReviewFinding(
                        severity=item.get("severity", "minor"),
                        target=item.get("target", "none"),
                        location=str(item.get("location", ""))[:200],
                        issue=str(item.get("issue", ""))[:500],
                        suggestion=str(item.get("suggestion", ""))[:500]))
                except Exception:
                    continue
            ctx.emit("critic.done", data.get("summary", "review complete"),
                     findings=len(findings), cost=round(res.cost_usd, 4))
        except LLMError as exc:
            ctx.warn(f"model review unavailable: {exc}")

    review_md = _render_review(document, findings, led, ctx)
    (ctx.run_dir / "outputs").mkdir(parents=True, exist_ok=True)
    (ctx.run_dir / "outputs" / "review-v1.md").write_text(review_md, "utf-8")
    return findings, led


def _render_review(document: str, findings: list[ReviewFinding], led, ctx: RunContext) -> str:
    lines = [
        "# Review",
        "",
        f"- Verdict: **{led.verdict}**",
        f"- Citations: {led.citations_resolved}/{led.citations_total} resolved",
        f"- Uncited paragraphs: {len(led.paragraphs_without_citation)}",
        f"- Sections missing: {', '.join(led.sections_missing) or 'none'}",
        f"- Sources: {led.sources_total} ({led.sources_peer_reviewed} peer-reviewed, "
        f"{led.sources_grey} grey), DOI verified: {led.sources_doi_verified}",
        "",
        "## Findings",
        "",
    ]
    if not findings:
        lines.append("No findings.")
    for f in findings:
        lines.append(f"- **[{f.severity}] → {f.target}** ({f.location}) {f.issue} — _{f.suggestion}_")
    if led.paragraphs_without_citation:
        lines += ["", "## Paragraphs without citation", ""]
        lines += [f"- {p}" for p in led.paragraphs_without_citation[:10]]
    if led.quote_mismatches:
        lines += ["", "## Quote mismatches", ""]
        lines += [f"- {q}" for q in led.quote_mismatches[:10]]
    if led.page_mismatches:
        lines += ["", "## Page locators that do not exist", ""]
        lines += [f"- {p}" for p in led.page_mismatches[:10]]
    return "\n".join(lines) + "\n"


def _validate_sources(ctx: RunContext) -> list[dict[str, str]]:
    papers = ctx.project.papers()
    rctx = _retrieval_context(ctx)
    results: list[dict[str, str]] = []
    # Bounded so a 60-source project does not hammer doi.org for minutes; the
    # report says how many were checked.
    checked = papers[:30]
    if len(papers) > len(checked):
        ctx.warn(f"DOI validation limited to the first {len(checked)} of {len(papers)} sources")
    for paper in checked:
        if not paper.doi:
            paper.verified = "no"
            paper.verification_note = "no DOI"
        else:
            status, note = retrieval.validate_doi(paper.doi, rctx)
            paper.verified = status  # type: ignore[assignment]
            paper.verification_note = note
        results.append({"id": paper.id, "doi": paper.doi or "", "status": paper.verified,
                        "note": paper.verification_note})
        ctx.emit("validation", f"{paper.id}: {paper.verified}", paper_id=paper.id,
                 status=paper.verified)
    ctx.project.save_papers(papers)
    for paper in papers:
        ctx.project.write_paper_record(paper)
    return results


def _freeze(ctx: RunContext, document: str, findings: list[ReviewFinding],
            led) -> None:
    ctx.set_phase("freeze")
    papers = ctx.project.papers()
    run_dir = ctx.run_dir
    (run_dir / "outputs").mkdir(parents=True, exist_ok=True)
    (run_dir / "outputs" / "document-v1.md").write_text(document, "utf-8")

    validation = _validate_sources(ctx)
    led = ledger_mod.check(document, ctx.project.papers(), ctx.project.evidence(), ctx.brief)
    led = led.compute_verdict() if hasattr(led, "compute_verdict") else led
    (run_dir / "outputs" / "document-final.md").write_text(document, "utf-8")

    # references: bib + human bibliography + validation report
    refs = ctx.project.references_dir
    refs.mkdir(parents=True, exist_ok=True)
    if ctx.brief.deliverable.bibtex:
        bib = bibtex.build(papers)
        (refs / "library.bib").write_text(bib, "utf-8")
        problems = bibtex.validate(bib)
        ctx.emit("bibtex", f"{len(papers)} entries", problems=problems)
    bib_md = ["# Bibliography", ""]
    for p in sorted(papers, key=lambda x: x.id):
        authors = ", ".join(p.authors[:6]) or "n/a"
        bib_md.append(f"- **{p.id}** {authors} ({p.year or 'n.d.'}). {p.title}. "
                      f"{p.venue or ''} {'https://doi.org/' + p.doi if p.doi else p.url or ''}")
    (refs / "bibliography.md").write_text("\n".join(bib_md) + "\n", "utf-8")

    v_md = ["# Source validation", "",
            "| ID | DOI | Status | Note |", "|---|---|---|---|"]
    for row in validation:
        v_md.append(f"| {row['id']} | {row['doi'] or '—'} | {row['status']} | {row['note'][:90]} |")
    (refs / "validation.md").write_text("\n".join(v_md) + "\n", "utf-8")

    report = {
        "run_id": ctx.run_id,
        "finished_at": utcnow(),
        "provider": ctx.llm.provider,
        "model": ctx.llm.model,
        "calls": ctx.llm.calls,
        "tokens_in": ctx.llm.tokens_in,
        "tokens_out": ctx.llm.tokens_out,
        "cost_usd": round(ctx.llm.cost_usd, 4),
        "ledger": led.model_dump(),
        "findings": [f.model_dump() for f in findings],
        "validation": validation,
        "warnings": ctx.warnings,
    }
    (run_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), "utf-8")
    ctx.emit("freeze", f"document final — verdict {led.verdict}", verdict=led.verdict,
             cost=round(ctx.llm.cost_usd, 4))


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------


def run_pipeline(ctx: RunContext) -> None:
    try:
        queries = _plan(ctx)
        cands = _discover(ctx, queries)
        ctx.candidates = cands

        if ctx.brief.checkpoints.candidates:
            decision = ctx.checkpoint(
                "candidates",
                f"{len(cands)} candidate sources found. Approve to fetch and read them.",
                {"candidates": [
                    {"key": c.dedupe_key(), "title": c.title, "year": c.year,
                     "venue": c.venue, "doi": c.doi, "score": c.score,
                     "oa": bool(c.oa_pdf), "theme": c.theme}
                    for c in cands]},
            )
            if decision.get("action") == "stop":
                ctx.state.status = "cancelled"
                ctx.emit("cancelled", "stopped at the candidate checkpoint")
                return
            keys = decision.get("keys")
            if keys:
                allowed = set(keys)
                cands = [c for c in cands if c.dedupe_key() in allowed]

        _ingest(ctx, cands)
        outline = _outline(ctx)

        if ctx.brief.checkpoints.outline:
            decision = ctx.checkpoint(
                "outline",
                "Review the section plan before the author starts writing.",
                {"sections": [{"heading": s.heading, "evidence": len(s.evidence)}
                              for s in outline.sections]},
            )
            if decision.get("action") == "stop":
                ctx.state.status = "cancelled"
                ctx.emit("cancelled", "stopped at the outline checkpoint")
                return
            headings = decision.get("sections")
            if headings:
                outline.sections = [
                    s for s in outline.sections if s.heading in headings] or outline.sections

        document = _draft(ctx, outline)
        findings, led = _critique(ctx, document)

        rounds_left = max(0, ctx.brief.deliverable.max_rounds - 1)
        while True:
            if ctx.brief.checkpoints.review:
                decision = ctx.checkpoint(
                    "review",
                    f"Review round finished. Verdict: {led.verdict}. "
                    f"{len(findings)} findings.",
                    {"verdict": led.verdict, "findings": [f.model_dump() for f in findings]},
                )
                action = decision.get("action", "accept")
            else:
                serious = any(f.severity in {"blocker", "major"} for f in findings)
                action = "revise" if (serious and rounds_left > 0) else "accept"

            if action != "revise" or rounds_left <= 0:
                if action == "stop":
                    ctx.state.status = "cancelled"
                    ctx.emit("cancelled", "stopped at the review checkpoint")
                    return
                break

            rounds_left -= 1
            ctx.state.rounds += 1
            ctx.emit("revise", f"revising with {len(findings)} findings", round=ctx.state.rounds)
            document = _draft(ctx, outline, findings=findings)
            findings, led = _critique(ctx, document)

        _freeze(ctx, document, findings, led)
        ctx.state.status = "done"
        ctx.state.finished_at = utcnow()
        ctx.emit("done", f"run finished — {led.verdict}")
    except Cancelled:
        ctx.state.status = "cancelled"
        ctx.state.finished_at = utcnow()
        ctx.emit("cancelled", "run cancelled")
    except Exception as exc:  # noqa: BLE001 — surface anything to the UI
        ctx.state.status = "failed"
        ctx.state.error = f"{type(exc).__name__}: {exc}"
        ctx.state.finished_at = utcnow()
        ctx.emit("error", ctx.state.error, traceback=traceback.format_exc()[-2000:])
    finally:
        ctx.save_state()


# ---------------------------------------------------------------------------
# job manager
# ---------------------------------------------------------------------------


class JobManager:
    """Owns worker threads. One process, one user: a dict is enough."""

    def __init__(self) -> None:
        self._jobs: dict[str, RunContext] = {}
        self._lock = threading.Lock()

    def start(self, project: Project) -> RunState:
        brief = project.brief()
        settings = project.workspace.settings()
        from .llm import client_from_settings

        llm = client_from_settings(settings, project.workspace.api_key())
        agents = {
            agent_id: AgentFile.parse(agent_id, project.agent_text(agent_id))
            for agent_id in ("researcher", "author", "critic")
        }
        run_id = project.new_run_id()
        state = RunState(
            run_id=run_id, phase="queued", provider=llm.provider, model=llm.model)
        ctx = RunContext(
            project=project, run_id=run_id, brief=brief, llm=llm, agents=agents,
            state=state, cost_cap_usd=max(0.0, brief.deliverable.cost_cap_usd),
        )
        project.run_dir(run_id).mkdir(parents=True, exist_ok=True)
        ctx.emit("run.started", f"provider={llm.provider} model={llm.model}")
        thread = threading.Thread(target=run_pipeline, args=(ctx,), daemon=True,
                                 name=f"run-{run_id}")
        with self._lock:
            self._jobs[run_id] = ctx
        thread.start()
        return state

    def get(self, run_id: str) -> RunContext | None:
        return self._jobs.get(run_id)

    def decide(self, run_id: str, payload: dict[str, Any]) -> bool:
        ctx = self._jobs.get(run_id)
        if ctx is None or ctx.state.checkpoint is None:
            return False
        ctx.resolve(payload)
        return True

    def cancel(self, run_id: str) -> bool:
        ctx = self._jobs.get(run_id)
        if ctx is None:
            return False
        ctx.cancel_flag.set()
        ctx.resolve({"action": "stop"})
        return True


JOBS = JobManager()
