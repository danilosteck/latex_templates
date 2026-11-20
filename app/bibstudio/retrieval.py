"""Literature retrieval adapters.

Only open, keyless indexes are used by default. Each adapter returns normalized
`Candidate` objects; failures degrade to an empty list plus a warning — a broken
upstream must never crash a run.

Live status verified 2026-11 (see APP_PLAN.md §3.2):
  OpenAlex     200, keyless but a shared per-IP daily budget; a free key gives more
  Crossref     200, keyless (polite pool via mailto)
  Europe PMC   200, keyless
  SciELO       search.scielo.org is behind a bot wall (403) -> implemented as a
               DOI-prefix collection filter over Crossref, never scraped
"""

from __future__ import annotations

import html
import json
import math
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable

import httpx

from .models import Candidate

USER_AGENT = "bibstudio/0.1 (research tool; +https://github.com/)"
TIMEOUT = httpx.Timeout(25.0, connect=10.0)
MAX_BYTES = 25 * 1024 * 1024


@dataclass
class SourceReport:
    """What one source actually did during a search. Surfaced to the user when a
    search comes back empty, because 'no sources found' is not an explanation."""

    name: str
    calls: int = 0
    hits: int = 0
    last_status: int | None = None
    seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"name": self.name, "calls": self.calls, "hits": self.hits,
                "status": self.last_status, "seconds": round(self.seconds, 1),
                "errors": self.errors[:3]}


@dataclass
class RetrievalContext:
    mailto: str = ""
    openalex_key: str = ""
    year_from: int | None = None
    year_to: int | None = None
    languages: list[str] = field(default_factory=list)
    exclude_terms: list[str] = field(default_factory=list)
    include_peer_reviewed: bool = True
    include_grey: bool = False
    warnings: list[str] = field(default_factory=list)
    reports: dict[str, SourceReport] = field(default_factory=dict)
    filtered_out: int = 0
    attempts: int = 3
    client: httpx.Client = field(default_factory=lambda: httpx.Client(
        timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}, follow_redirects=True))

    def note(self, message: str) -> None:
        self.warnings.append(message)

    def report(self, name: str) -> SourceReport:
        return self.reports.setdefault(name, SourceReport(name=name))

    def fail(self, name: str, exc: Exception) -> None:
        """Record a failure with the HTTP status when there is one.

        Call counting lives in ``search`` so a mock adapter and a real one are
        counted the same way.
        """
        rep = self.report(name)
        status = None
        response = getattr(exc, "response", None)
        if response is not None:
            status = getattr(response, "status_code", None)
        rep.last_status = status
        detail = type(exc).__name__ + (f" (HTTP {status})" if status else "")
        # the API's own explanation is what makes a 400 fixable ("invalid year")
        response_text = getattr(response, "text", "") if response is not None else ""
        if response_text:
            detail += ": " + " ".join(response_text[:140].split())
        else:
            message = str(exc)
            if message and status is None:
                detail += f": {message[:120]}"
        rep.errors.append(detail)
        self.warnings.append(f"{name} failed: {detail}")

    def summary(self) -> list[dict]:
        return [self.report(name).as_dict() for name in self.reports]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _clean(text: str | None) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)  # JATS/HTML abstracts from Crossref
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _get(ctx: RetrievalContext, name: str, url: str, params: dict | None = None,
         headers: dict | None = None, timeout: float | None = None) -> dict:
    """GET with two retries on transient failures (429/5xx, network).

    A single rate-limit response used to look exactly like 'no results', which is
    how a run ended with 'no sources found' and no explanation.
    """
    last: Exception | None = None
    for attempt in range(max(1, ctx.attempts)):
        try:
            resp = ctx.client.get(url, params=params, headers=headers, timeout=timeout)
        except Exception as exc:  # network, timeout
            last = exc
            time.sleep(0.8 * (attempt + 1))
            continue
        if resp.status_code in (429, 500, 502, 503, 504):
            last = httpx.HTTPStatusError(
                f"HTTP {resp.status_code}", request=resp.request, response=resp)
            time.sleep(1.2 * (attempt + 1))
            continue
        if resp.status_code >= 400:
            snippet = " ".join((getattr(resp, "text", "") or "")[:200].split())
            message = f"HTTP {resp.status_code}" + (f": {snippet}" if snippet else "")
            raise httpx.HTTPStatusError(message, request=resp.request, response=resp)
        return resp.json()
    raise last or RuntimeError("request failed without a response")


def _as_int(value) -> int | None:
    try:
        return int(str(value)[:4])
    except (TypeError, ValueError):
        return None


def _language_code(lang: str) -> str:
    """Map 'pt-BR' / 'Portuguese' to the 2-letter codes OpenAlex expects."""
    low = (lang or "").lower()
    table = {"portuguese": "pt", "english": "en", "spanish": "es", "french": "fr",
             "german": "de", "italian": "it"}
    if low in table:
        return table[low]
    return low[:2]


def _reconstruct_abstract(inverted: dict | None) -> str:
    """OpenAlex stores abstracts as an inverted index; rebuild the text."""
    if not inverted:
        return ""
    positions: list[tuple[int, str]] = []
    for word, idxs in inverted.items():
        for i in idxs:
            positions.append((int(i), word))
    positions.sort()
    return " ".join(word for _, word in positions)


def score_candidate(cand: Candidate, keywords: Iterable[str]) -> float:
    """Cheap relevance score: keyword coverage + citation weight + OA bonus."""
    words = [w.lower() for w in keywords if len(w) > 2]
    haystack = f"{cand.title} {cand.abstract}".lower()
    hits = sum(1 for w in words if w in haystack)
    coverage = hits / max(1, len(words))
    citations = math.log10(1 + max(0, cand.cited_by)) / 3.0
    oa = 0.1 if cand.oa_pdf else 0.0
    venue = 0.05 if cand.venue else 0.0
    return round(coverage * 2.0 + citations + oa + venue, 4)


def _passes_filters(cand: Candidate, ctx: RetrievalContext) -> bool:
    if not cand.title.strip():
        return False
    if ctx.year_from and cand.year and cand.year < ctx.year_from:
        return False
    if ctx.year_to and cand.year and cand.year > ctx.year_to:
        return False
    low = f"{cand.title} {cand.abstract}".lower()
    if any(term and term.lower() in low for term in ctx.exclude_terms):
        return False
    return True


# ---------------------------------------------------------------------------
# adapters
# ---------------------------------------------------------------------------


def openalex(query: str, limit: int, ctx: RetrievalContext) -> list[Candidate]:
    params: dict[str, str] = {"search": query, "per-page": str(min(limit, 100))}
    filters: list[str] = []
    if ctx.year_from:
        filters.append(f"from_publication_date:{ctx.year_from}-01-01")
    if ctx.year_to:
        filters.append(f"to_publication_date:{ctx.year_to}-12-31")
    if ctx.include_peer_reviewed and not ctx.include_grey:
        filters.append("type:article")
    langs = [c for c in (_language_code(l) for l in ctx.languages) if c]
    if len(langs) == 1:
        filters.append(f"language:{langs[0]}")
    if filters:
        params["filter"] = ",".join(filters)
    if ctx.openalex_key:
        params["api_key"] = ctx.openalex_key
    if ctx.mailto:
        params["mailto"] = ctx.mailto

    try:
        data = _get(ctx, "openalex", "https://api.openalex.org/works", params)
    except Exception as exc:
        ctx.fail("openalex", exc)
        return []

    out: list[Candidate] = []
    for item in data.get("results", []):
        doi = (item.get("doi") or "").replace("https://doi.org/", "") or None
        best = item.get("best_oa_location") or item.get("primary_location") or {}
        loc = item.get("primary_location") or {}
        source_name = ((loc.get("source") or {}).get("display_name") or "")
        out.append(Candidate(
            title=_clean(item.get("title") or item.get("display_name") or ""),
            source="openalex",
            authors=[a.get("author", {}).get("display_name", "")
                     for a in item.get("authorships", [])][:12],
            year=item.get("publication_year"),
            venue=source_name,
            doi=doi,
            url=item.get("id") if not doi else f"https://doi.org/{doi}",
            abstract=_clean(_reconstruct_abstract(item.get("abstract_inverted_index"))),
            cited_by=item.get("cited_by_count") or 0,
            oa_pdf=(best or {}).get("pdf_url") or None,
        ))
    return out


def crossref(query: str, limit: int, ctx: RetrievalContext) -> list[Candidate]:
    params: dict[str, str] = {
        "query": query,
        "rows": str(min(limit, 100)),
        # NB: Crossref rejects unknown `select` values with a 400 (e.g. 'language').
        "select": "DOI,title,author,issued,container-title,abstract,is-referenced-by-count,URL,type",
    }
    filters: list[str] = []
    if ctx.year_from:
        filters.append(f"from-pub-date:{ctx.year_from}-01-01")
    if ctx.year_to:
        filters.append(f"until-pub-date:{ctx.year_to}-12-31")
    if ctx.include_peer_reviewed and not ctx.include_grey:
        filters.append("type:journal-article")
    if filters:
        params["filter"] = ",".join(filters)
    if ctx.mailto:
        params["mailto"] = ctx.mailto

    try:
        data = _get(ctx, "crossref", "https://api.crossref.org/works", params)
    except Exception as exc:
        ctx.fail("crossref", exc)
        return []

    out: list[Candidate] = []
    for item in data.get("message", {}).get("items", []):
        year = None
        for key in ("published-print", "published-online", "issued", "created"):
            parts = (item.get(key) or {}).get("date-parts")
            if parts and parts[0] and parts[0][0]:
                year = int(parts[0][0])
                break
        authors = [f"{a.get('given', '')} {a.get('family', '')}".strip()
                   for a in item.get("author", [])][:12]
        doi = item.get("DOI")
        out.append(Candidate(
            title=_clean((item.get("title") or [""])[0]),
            source="crossref",
            authors=[a for a in authors if a],
            year=year,
            venue=(item.get("container-title") or [""])[0] or "",
            doi=doi,
            url=item.get("URL") or (f"https://doi.org/{doi}" if doi else None),
            abstract=_clean(item.get("abstract")),
            cited_by=item.get("is-referenced-by-count") or 0,
        ))
    return out


def scielo(query: str, limit: int, ctx: RetrievalContext) -> list[Candidate]:
    """SciELO is a collection, not a search engine (its site blocks bots).

    Query Crossref restricted to the SciELO DOI prefix (10.1590) instead.
    """
    params = {
        "query": query,
        "rows": str(min(limit, 100)),
        "filter": "prefix:10.1590",
        "select": "DOI,title,author,issued,container-title,abstract,is-referenced-by-count,URL",
    }
    if ctx.mailto:
        params["mailto"] = ctx.mailto
    try:
        data = _get(ctx, "scielo", "https://api.crossref.org/works", params)
    except Exception as exc:
        ctx.fail("scielo", exc)
        return []
    out: list[Candidate] = []
    for item in data.get("message", {}).get("items", []):
        parts = (item.get("issued") or {}).get("date-parts")
        year = int(parts[0][0]) if parts and parts[0] and parts[0][0] else None
        doi = item.get("DOI")
        out.append(Candidate(
            title=_clean((item.get("title") or [""])[0]),
            source="scielo",
            authors=[f"{a.get('given', '')} {a.get('family', '')}".strip()
                     for a in item.get("author", [])][:12],
            year=year,
            venue=(item.get("container-title") or [""])[0] or "",
            doi=doi,
            url=f"https://doi.org/{doi}" if doi else item.get("URL"),
            abstract=_clean(item.get("abstract")),
            cited_by=item.get("is-referenced-by-count") or 0,
        ))
    for cand in out:
        cand.source = "scielo"
    return out


def europepmc(query: str, limit: int, ctx: RetrievalContext) -> list[Candidate]:
    # Europe PMC has no filter API in the REST search; year limits go in the query.
    if ctx.year_from or ctx.year_to:
        query = (f"({query}) AND PUB_YEAR:[{ctx.year_from or 1900} "
                 f"TO {ctx.year_to or 2100}]")
    params = {
        "query": query,
        "format": "json",
        "pageSize": str(min(limit, 100)),
        "resultType": "core",
    }
    try:
        # Europe PMC is the slowest of the open sources (5-25s for resultType=core);
        # a short per-request timeout keeps it from stalling the whole search.
        data = _get(ctx, "europepmc",
                    "https://www.ebi.ac.uk/europepmc/webservices/rest/search", params,
                    timeout=10.0)
    except Exception as exc:
        ctx.fail("europepmc", exc)
        return []

    out: list[Candidate] = []
    for item in (data.get("resultList") or {}).get("result", []):
        doi = item.get("doi")
        pdf = None
        for url in ((item.get("fullTextUrlList") or {}).get("fullTextUrl") or []):
            if url.get("documentStyle") == "pdf" and url.get("availability") == "Open access":
                pdf = url.get("url")
                break
        out.append(Candidate(
            title=_clean(item.get("title")),
            source="europepmc",
            authors=[a.get("fullName", "") for a in
                     ((item.get("authorList") or {}).get("author") or [])][:12],
            year=_as_int(item.get("pubYear")),
            venue=item.get("journalInfo", {}).get("journal", {}).get("title", "") or "",
            doi=doi,
            url=f"https://doi.org/{doi}" if doi else item.get("id"),
            abstract=_clean(item.get("abstractText")),
            cited_by=_as_int(item.get("citedByCount")) or 0,
            oa_pdf=pdf,
        ))
    return out


ADAPTERS: dict[str, Callable[[str, int, RetrievalContext], list[Candidate]]] = {
    "openalex": openalex,
    "crossref": crossref,
    "scielo": scielo,
    "europepmc": europepmc,
}


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------


def search(
    queries: list[tuple[str, str]],
    sources: list[str],
    ctx: RetrievalContext,
    *,
    limit_per_query: int = 12,
    per_source: bool = True,
) -> list[Candidate]:
    """Run every query against every source, dedupe, filter and score.

    Requests run in a small thread pool: three queries against three APIs
    sequentially took about a minute, which is unusable as a UI button. Each task
    gets its own light context sharing the HTTP client, and results are merged
    under a lock so counters stay correct.

    Returns candidates sorted by score (best first). Never raises: adapter errors
    become warnings and per-source reports.
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor

    names = [name for name in sources if name in ADAPTERS]
    for unknown in [n for n in sources if n not in ADAPTERS]:
        ctx.note(f"unknown source: {unknown}")

    tasks = [(theme, query, name) for theme, query in queries for name in names]
    if not tasks:
        ctx.filtered_out = 0
        return []

    def run_task(task: tuple[str, str, str]):
        theme, query, name = task
        local = RetrievalContext(
            mailto=ctx.mailto, openalex_key=ctx.openalex_key,
            year_from=ctx.year_from, year_to=ctx.year_to,
            languages=list(ctx.languages), exclude_terms=list(ctx.exclude_terms),
            include_peer_reviewed=ctx.include_peer_reviewed,
            include_grey=ctx.include_grey, attempts=ctx.attempts, client=ctx.client,
        )
        adapter = ADAPTERS[name]
        started = time.monotonic()
        try:
            hits = adapter(query, limit_per_query, local)
        except Exception as exc:  # defensive: adapters already catch
            local.note(f"{name} crashed: {type(exc).__name__}")
            hits = []
        elapsed = time.monotonic() - started
        report = local.report(name)
        report.calls += 1
        report.hits += len(hits)
        report.seconds += elapsed
        return theme, query, name, hits, local

    results = []
    workers = max(1, min(6, len(tasks)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for result in pool.map(run_task, tasks):
            results.append(result)

    lock = threading.Lock()
    seen: dict[str, Candidate] = {}
    for theme, query, name, hits, local in results:
        with lock:
            global_report = ctx.report(name)
            local_report = local.report(name)
            global_report.calls += local_report.calls
            global_report.hits += local_report.hits
            global_report.seconds += local_report.seconds
            if local_report.last_status:
                global_report.last_status = local_report.last_status
            global_report.errors.extend(local_report.errors)
            ctx.warnings.extend(w for w in local.warnings if w not in ctx.warnings)
        for cand in hits:
            cand.theme = theme
            setattr(cand, "_query", query)
            key = cand.dedupe_key()
            existing = seen.get(key)
            if existing is not None:
                # keep the richer record (abstract + OA pdf win)
                if len(cand.abstract) > len(existing.abstract):
                    existing.abstract = cand.abstract
                existing.oa_pdf = existing.oa_pdf or cand.oa_pdf
                existing.cited_by = max(existing.cited_by, cand.cited_by)
                continue
            seen[key] = cand

    keywords: list[str] = []
    for theme, query in queries:
        keywords += [w for w in re.split(r"\W+", f"{theme} {query}") if len(w) > 3]
    if ctx.exclude_terms:
        keywords = keywords  # exclude terms are filters, not scoring input

    out = [c for c in seen.values() if _passes_filters(c, ctx)]
    ctx.filtered_out = len(seen) - len(out)
    for cand in out:
        cand.score = score_candidate(cand, keywords)
    out.sort(key=lambda c: c.score, reverse=True)
    return out


def describe_filters(ctx: RetrievalContext) -> str:
    parts = []
    if ctx.year_from or ctx.year_to:
        parts.append(f"years {ctx.year_from or 'any'}–{ctx.year_to or 'present'}")
    if ctx.languages:
        parts.append(f"languages {', '.join(ctx.languages)}")
    if ctx.exclude_terms:
        parts.append(f"excluding {', '.join(ctx.exclude_terms)}")
    if ctx.include_peer_reviewed and not ctx.include_grey:
        parts.append("peer-reviewed only")
    return "; ".join(parts) or "no filters"


def failure_report(queries: list[tuple[str, str]], sources: list[str],
                   ctx: RetrievalContext) -> str:
    """Human explanation for a search that produced nothing.

    'No sources found' alone is useless: the user cannot tell a rate limit from a
    typo in the year range.
    """
    lines = [f"No sources found after {len(queries)} query(ies) on "
             f"{', '.join(sources) or 'no sources'}."]
    for name in sources:
        rep = ctx.report(name)
        state = f"{rep.calls} call(s), {rep.hits} hit(s)"
        if rep.errors:
            state += f", errors: {', '.join(rep.errors[-2:])}"
        lines.append(f"  - {name}: {state}")
    lines.append(f"Filters: {describe_filters(ctx)}.")
    if ctx.filtered_out:
        lines.append(f"{ctx.filtered_out} result(s) were discarded by those filters.")
    if any(rep.last_status in (403, 429) for rep in ctx.reports.values()):
        lines.append("A 403/429 means the source is rate-limiting this IP. "
                     "OpenAlex without a key shares a tiny daily budget — add a "
                     "free key in Settings, or try again later.")
    hints: list[str] = []
    if ctx.exclude_terms:
        hints.append(f"remove the excluded terms ({', '.join(ctx.exclude_terms)})")
    if ctx.year_from or ctx.year_to:
        hints.append("widen the year range")
    if ctx.include_peer_reviewed and not ctx.include_grey:
        hints.append("allow grey literature")
    if len(ctx.languages) == 1:
        hints.append(f"add another literature language (now {ctx.languages[0]})")
    hints.append("enable another source")
    lines.append("Try: " + "; ".join(hints) + ".")
    return "\n".join(lines)


def diagnose(queries: list[tuple[str, str]], sources: list[str],
             ctx: RetrievalContext, limit_per_query: int = 3,
             limit_queries: int = 2) -> dict:
    """Cheap probe used by the UI's 'test sources' button. No ingest, no LLM."""
    queries = queries[:limit_queries]
    # A diagnostics button must answer in seconds, so it gets a short timeout and
    # no retries: a slow host is reported as slow instead of holding the UI.
    probe = RetrievalContext(
        mailto=ctx.mailto, openalex_key=ctx.openalex_key,
        year_from=ctx.year_from, year_to=ctx.year_to,
        languages=list(ctx.languages), exclude_terms=list(ctx.exclude_terms),
        include_peer_reviewed=ctx.include_peer_reviewed,
        include_grey=ctx.include_grey, attempts=1,
        client=httpx.Client(timeout=httpx.Timeout(12.0, connect=5.0),
                            headers={"User-Agent": USER_AGENT}, follow_redirects=True),
    )
    cands = search(queries, sources, probe, limit_per_query=limit_per_query)
    probe.client.close()
    ctx.reports.update(probe.reports)
    ctx.warnings.extend(w for w in probe.warnings if w not in ctx.warnings)
    ctx.filtered_out = probe.filtered_out
    return {
        "queries": [{"theme": t, "query": q} for t, q in queries],
        "sources": ctx.summary(),
        "hits": len(cands),
        "filtered_out": ctx.filtered_out,
        "filters": describe_filters(ctx),
        "warnings": ctx.warnings,
        "explanation": "" if cands else failure_report(queries, sources, ctx),
        "examples": [{"title": c.title[:90], "year": c.year, "venue": c.venue,
                      "doi": c.doi, "source": c.source} for c in cands[:10]],
    }


def validate_doi(doi: str, ctx: RetrievalContext) -> tuple[str, str]:
    """Resolve a DOI and compare its Crossref title. Returns (status, note).

    status: 'yes' | 'mismatch' | 'no'. Keyless (DOI handle API + Crossref).
    """
    doi = (doi or "").strip()
    if not doi:
        return "no", "no DOI on record"
    try:
        resp = ctx.client.get(f"https://doi.org/api/handles/{doi}",
                              headers={"Accept": "application/json"})
        if resp.status_code != 200:
            return "no", f"DOI does not resolve (HTTP {resp.status_code})"
    except Exception as exc:
        return "no", f"DOI resolution failed: {type(exc).__name__}"
    try:
        resp = ctx.client.get(f"https://api.crossref.org/works/{doi}")
        if resp.status_code == 200:
            title = ((resp.json().get("message", {}).get("title") or [""])[0])
            return "yes", f"resolves; Crossref title: {title[:90]}"
    except Exception:
        pass
    return "yes", "DOI resolves (no Crossref metadata)"


def dump_candidates(cands: list[Candidate]) -> str:
    return json.dumps([c.model_dump() for c in cands], indent=2, ensure_ascii=False)
