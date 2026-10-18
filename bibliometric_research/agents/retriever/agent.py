"""Agent 1 — Retriever.

Turns *retrieval requests* into cached, citable **evidence items**. It never
writes analysis prose.

Responsibilities
----------------
1. Given the study brief / a set of needs, propose search queries (optionally
   refined by the LLM, but the LLM is not required to browse).
2. Search indexed academic sources (priority order from config/brief).
3. For each hit: mint a stable paper id, upsert the registry record, fetch +
   cache the text, chunk it, and create evidence items with a short summary.
4. Return evidence ids + bounded excerpts — never whole documents.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agents.retriever import fetch, sources
from core.cache import Cache
from core.evidence import EvidenceItem, excerpt
from core.llm import LLM
from core.registry import Paper, Registry, make_paper_id, normalize_doi


@dataclass
class RetrievalResult:
    evidence: list[EvidenceItem] = field(default_factory=list)
    papers_added: int = 0
    fetches: int = 0
    warnings: list[str] = field(default_factory=list)


class RetrieverAgent:
    def __init__(
        self,
        llm: LLM,
        cache: Cache,
        registry: Registry,
        *,
        source_priority: list[str],
        max_fetches: int = 40,
        results_per_query: int = 10,
        max_excerpt_words: int = 80,
        chunk_words: int = 350,
    ) -> None:
        self.llm = llm
        self.cache = cache
        self.registry = registry
        self.source_priority = source_priority
        self.max_fetches = max_fetches
        self.results_per_query = results_per_query
        self.max_excerpt_words = max_excerpt_words
        self.chunk_words = chunk_words
        self._fetches = 0
        self._warnings: list[str] = []

    # -- public -------------------------------------------------------------

    def run(self, brief: str, queries: list[str] | None = None) -> RetrievalResult:
        """Execute retrieval for a brief and/or explicit queries."""
        if queries is None:
            queries = self.propose_queries(brief)
        result = RetrievalResult()
        for q in queries:
            cands = sources.search(q, self.source_priority, self.results_per_query, self.cache)
            for cand in cands:
                if self._fetches >= self.max_fetches:
                    self._warnings.append(
                        f"max_fetches={self.max_fetches} reached; stopping retrieval.")
                    result.warnings = self._warnings
                    return result
                evs = self._ingest(cand, query=q)
                if evs:
                    result.evidence.extend(evs)
                    result.papers_added += 1
        result.fetches = self._fetches
        result.warnings = self._warnings
        return result

    def propose_queries(self, brief: str) -> list[str]:
        """Ask the LLM for compact search queries derived from the brief.

        Falls back to a naive extraction if the LLM is unavailable/mock.
        Queries are cached implicitly via source-result caching.
        """
        system = _PROMPT
        try:
            data = self.llm.complete_json(system, brief)
            queries = [q["query"] for q in data.get("queries", []) if q.get("query")]
            if queries:
                return queries[:8]
        except Exception:
            pass
        # naive fallback: first sentence-ish keywords
        words = [w for w in brief.split() if len(w) > 4][:8]
        return [" ".join(words)] if words else []

    # -- internals ----------------------------------------------------------

    def _ingest(self, cand, query: str) -> list[EvidenceItem]:
        """Register a candidate, fetch/cache text, and produce evidence items."""
        doi = normalize_doi(cand.doi)
        target_url = cand.url or (f"https://doi.org/{doi}" if doi else None)
        if not (doi or target_url):
            self._warnings.append(f"skip (no doi/url): {cand.title[:60]}")
            return []

        try:
            pid = make_paper_id(doi, target_url)
        except ValueError:
            return []

        paper = Paper(
            id=pid, title=cand.title, authors=cand.authors, year=cand.year,
            venue=cand.venue, doi=doi, url=target_url, source=cand.source,
            queries=[query], notes="",
        )
        existing = self.registry.get(pid)
        self.registry.upsert(paper)

        # Abstract-only evidence (cheap, no network fetch of the full text).
        items: list[EvidenceItem] = []
        if cand.abstract:
            items.append(self._mk_item(pid, 0, cand.abstract))
            paper.content_hash = self.cache.hash_str(cand.abstract)
            self.registry.upsert(paper)

        # Try to fetch full text (cached). Abstract-only sources won't have it.
        if target_url:
            text = self._try_fetch_text(target_url)
            if text and len(text.split()) > 40:
                chunks = fetch.chunk_text(text, self.chunk_words)
                for i, chunk in enumerate(chunks):
                    items.append(self._mk_item(pid, i, chunk))
                paper.content_hash = self.cache.hash_bytes(text.encode("utf-8"))
                self.registry.upsert(paper)

        if not items:
            self._warnings.append(f"no text (abstract/full) for {pid} ({cand.source})")
        return items

    def _try_fetch_text(self, url: str) -> str:
        self._fetches += 1
        try:
            return fetch.url_to_text(url, self.cache)
        except Exception as e:  # network / paywall / parse error
            self._warnings.append(f"fetch failed {url}: {type(e).__name__}")
            return ""

    def _mk_item(self, pid: str, chunk: int, text: str) -> EvidenceItem:
        return EvidenceItem(
            ev_id=EvidenceItem.make_id(pid, chunk),
            paper_id=pid,
            chunk=chunk,
            summary=_first_sentences(text, 2),
            excerpt=excerpt(text, self.max_excerpt_words),
            relevance=0.0,
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _first_sentences(text: str, n: int) -> str:
    import re
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(parts[:n]).strip()


_PROMPT = """You are the Retriever agent in a bibliometric research system.
Your job is to propose SEARCH QUERIES (not answers) that will surface academic
literature relevant to the study. Prefer precise, keyword-rich queries suitable
for Scopus / Web of Science / SciELO / Google Scholar. Output ONLY JSON:

{
  "queries": [
    {"query": "string", "sources": ["crossref","openalex"]}
  ]
}

Rules:
- 3 to 8 queries covering different angles / synonyms.
- No prose outside the JSON.
"""
