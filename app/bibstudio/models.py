"""Domain models.

Everything a project needs to be reproducible is a pydantic model here, so the
same validation runs on the API boundary, when loading from disk, and in tests.

Design note (see APP_PLAN.md §7): structured JSON is canonical. The markdown
files in a project are *rendered* from these models and can be re-imported.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

SourceType = Literal["peer_reviewed", "grey", "web", "unknown"]
FullText = Literal["oa", "paywalled", "abstract_only", "unknown"]
Verified = Literal["yes", "no", "mismatch", "unchecked"]


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(text: str, fallback: str = "project") -> str:
    s = text.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:48] or fallback


# ---------------------------------------------------------------------------
# Brief — the research definition (requirement #2)
# ---------------------------------------------------------------------------


class ResearchQuestion(BaseModel):
    question: str
    why: str = ""


class Theme(BaseModel):
    name: str
    keywords_en: list[str] = Field(default_factory=list)
    keywords_other: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)

    @field_validator("keywords_en", "keywords_other", mode="before")
    @classmethod
    def _split(cls, v: Any) -> list[str]:
        """Accept 'a, b; c' from a plain text input as well as a list."""
        if isinstance(v, str):
            return [p.strip() for p in re.split(r"[,;\n]", v) if p.strip()]
        return v or []


class Viewpoint(BaseModel):
    label: str
    description: str = ""
    proponents: list[str] = Field(default_factory=list)


DEFAULT_SECTIONS = [
    "Executive summary",
    "Scope & method",
    "Viewpoint map",
    "Main points of analysis",
    "Technical / methodological challenges",
    "Evidence gaps & open questions",
    "References",
]


class Deliverable(BaseModel):
    template: str = "article"
    sections: list[str] = Field(default_factory=lambda: list(DEFAULT_SECTIONS))
    length_words: int = 2500
    tone: str = "academic funding committee"
    citation_style: Literal["numeric", "author-year"] = "numeric"
    bibtex: bool = True
    max_rounds: int = 1
    cost_cap_usd: float = 2.0


class Checkpoints(BaseModel):
    candidates: bool = True
    outline: bool = True
    review: bool = True


class Brief(BaseModel):
    title: str
    topic: str
    disciplines: list[str] = Field(default_factory=list)
    year_from: int | None = None
    year_to: int | None = None
    geography: str = "global"
    lit_languages: list[str] = Field(default_factory=lambda: ["en"])
    output_language: str = "pt-BR"
    rqs: list[ResearchQuestion] = Field(default_factory=list)
    themes: list[Theme] = Field(default_factory=list)
    include_peer_reviewed: bool = True
    include_grey: bool = False
    exclude_terms: list[str] = Field(default_factory=list)
    min_sources: int = 20
    max_candidates: int = 40
    max_fetches: int = 40
    viewpoints: list[Viewpoint] = Field(default_factory=list)
    deliverable: Deliverable = Field(default_factory=Deliverable)
    checkpoints: Checkpoints = Field(default_factory=Checkpoints)
    sources_enabled: list[str] = Field(default_factory=lambda: ["openalex", "crossref"])

    @field_validator("year_from", "year_to", mode="before")
    @classmethod
    def _normalise_year(cls, v: Any) -> Any:
        """Accept '2010', 2010, 'any', '' — and repair a 5-digit typo.

        A year like 20100 makes OpenAlex and Crossref answer HTTP 400, which used
        to surface as 'no sources found'. Truncating to the first four digits turns
        an unsearchable project back into a searchable one instead of failing.
        """
        if v in ("", "any", None):
            return None
        digits = re.sub(r"\D", "", str(v))
        if not digits:
            return None
        if len(digits) > 4:
            digits = digits[:4]
        year = int(digits)
        return year if 1000 <= year <= 2100 else None

    def queries(self) -> list[tuple[str, str]]:
        """(theme_name, query_text) pairs. Deterministic; no model needed.

        Each theme yields a combined query plus one query per keyword, because
        strict engines (and multilingual themes) return nothing for a long
        concatenated string while returning plenty for a single term.
        """
        out: list[tuple[str, str]] = []
        for t in self.themes:
            terms = [*t.keywords_en, *t.keywords_other]
            if not terms:
                continue
            out.append((t.name, " ".join(dict.fromkeys(terms))[:200]))
            for term in dict.fromkeys(terms):
                if len(out) >= 8:
                    break
                out.append((t.name, term))
        if not out:
            out.append(("general", self.title or self.topic[:120]))
        # keep the request count bounded; dedupe identical query strings
        seen: set[str] = set()
        bounded: list[tuple[str, str]] = []
        for theme, query in out:
            key = query.lower().strip()
            if key and key not in seen:
                seen.add(key)
                bounded.append((theme, query))
        return bounded[:8]


# ---------------------------------------------------------------------------
# Sources and evidence
# ---------------------------------------------------------------------------


class Candidate(BaseModel):
    """A search hit, not yet ingested."""

    title: str
    source: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str = ""
    doi: str | None = None
    url: str | None = None
    abstract: str = ""
    cited_by: int = 0
    oa_pdf: str | None = None
    score: float = 0.0
    theme: str = ""

    def dedupe_key(self) -> str:
        if self.doi:
            return "doi:" + self.doi.lower()
        if self.url:
            return "url:" + self.url.lower()
        return "title:" + re.sub(r"\W+", "", self.title.lower())[:120] + str(self.year or "")


class Paper(BaseModel):
    id: str  # P-0001
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str = ""
    doi: str | None = None
    url: str | None = None
    source: str = ""
    source_type: SourceType = "unknown"
    full_text: FullText = "unknown"
    abstract: str = ""
    content_hash: str | None = None
    pages: int = 0
    verified: Verified = "unchecked"
    verification_note: str = ""
    queries: list[str] = Field(default_factory=list)
    added_at: str = Field(default_factory=utcnow)


class Evidence(BaseModel):
    """A bounded, citable excerpt. The only thing the author may cite."""

    paper_id: str
    locator: str  # "p.3" | "abstract" | "c3"
    page: int | None = None
    text: str
    summary: str = ""

    @property
    def key(self) -> str:
        return f"{self.paper_id}#{self.locator}"


class OutlineSection(BaseModel):
    heading: str
    brief: str = ""
    evidence: list[str] = Field(default_factory=list)  # paper ids


class Outline(BaseModel):
    sections: list[OutlineSection] = Field(default_factory=list)
    viewpoints: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Project and runs
# ---------------------------------------------------------------------------


class ProjectMeta(BaseModel):
    slug: str
    title: str
    created_at: str = Field(default_factory=utcnow)
    updated_at: str = Field(default_factory=utcnow)
    status: Literal["draft", "ready", "running", "done"] = "draft"


CheckpointKind = Literal["candidates", "outline", "review"]


class CheckpointRequest(BaseModel):
    kind: CheckpointKind
    summary: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class RunState(BaseModel):
    run_id: str
    started_at: str = Field(default_factory=utcnow)
    finished_at: str | None = None
    phase: str = "queued"
    status: Literal["running", "waiting", "done", "failed", "cancelled"] = "running"
    checkpoint: CheckpointRequest | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    error: str | None = None
    provider: str = "mock"
    model: str = "mock-1"
    rounds: int = 0


class ReviewFinding(BaseModel):
    severity: Literal["blocker", "major", "minor", "info"] = "minor"
    target: Literal["researcher", "author", "none"] = "none"
    location: str = ""
    issue: str = ""
    suggestion: str = ""


class Ledger(BaseModel):
    version: str = ""
    paragraphs_without_citation: list[str] = Field(default_factory=list)
    citations_total: int = 0
    citations_resolved: int = 0
    missing: list[str] = Field(default_factory=list)
    quote_checks: int = 0
    quote_mismatches: list[str] = Field(default_factory=list)
    page_mismatches: list[str] = Field(default_factory=list)
    sections_required: list[str] = Field(default_factory=list)
    sections_present: list[str] = Field(default_factory=list)
    sections_missing: list[str] = Field(default_factory=list)
    viewpoints_required: list[str] = Field(default_factory=list)
    viewpoints_covered: list[str] = Field(default_factory=list)
    sources_total: int = 0
    sources_peer_reviewed: int = 0
    sources_grey: int = 0
    sources_doi_verified: int = 0
    verdict: Literal["pass", "unverified", "fail"] = "unverified"

    def compute_verdict(self) -> "Ledger":
        if self.missing or self.sections_missing or self.quote_mismatches or self.page_mismatches:
            self.verdict = "fail"
        elif self.paragraphs_without_citation or self.citations_resolved < self.citations_total:
            self.verdict = "unverified"
        else:
            self.verdict = "pass"
        return self
