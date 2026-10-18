"""Academic source adapters.

Each adapter exposes ``search(query, limit) -> list[Candidate]`` and returns
**normalized candidate records** (title, authors, year, venue, doi, url, source).
The retriever then registers + fetches them.

Design notes
------------
* **Priority** is defined in config (indexed academic sources first).
* **Graceful degradation**: if an API key is missing (Scopus, WoS), the adapter
  returns ``[]`` and records a warning; the retriever continues with open
  sources (Crossref, OpenAlex, SciELO) and the general web.
* **No scraping of paywalled full text.** Adapters only use *official APIs* or
  open metadata. Google Scholar is treated as a *lead generator*: results are
  not scraped (ToS); instead, queries are redirected to Crossref/OpenAlex, which
  return a stable DOI. This keeps the system legal and the ids stable.
* Results are cached by (source, query) so repeated searches are free.

All network calls go through ``Cache`` to avoid duplicate requests and tokens.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass

from core.cache import Cache


@dataclass
class Candidate:
    title: str
    source: str
    authors: list[str]
    year: int | None = None
    venue: str = ""
    doi: str | None = None
    url: str | None = None
    abstract: str = ""


_HEADERS = {"User-Agent": "bibliometric-research/1.0 (mailto:%s)" % os.environ.get(
    "CROSSREF_MAILTO", "unknown@example.com")}


def _http_json(url: str, cache: Cache, timeout: float = 20.0) -> dict:
    key = Cache.key_for_url(url)
    cached = cache.get_json(key)
    if cached is not None:
        return cached
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    cache.put_json(key, data)
    return data


# ---------------------------------------------------------------------------
# Open metadata: Crossref  (existence validation + stable DOIs)
# ---------------------------------------------------------------------------

def crossref(query: str, limit: int, cache: Cache) -> list[Candidate]:
    mailto = os.environ.get("CROSSREF_MAILTO", "")
    params = {"query": query, "rows": str(limit)}
    if mailto:
        params["mailto"] = mailto
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(params)
    try:
        data = _http_json(url, cache)
    except Exception:
        return []
    out: list[Candidate] = []
    for item in data.get("message", {}).get("items", []):
        year = None
        for k in ("published-print", "published-online", "issued"):
            parts = item.get(k, {}).get("date-parts")
            if parts and parts[0] and parts[0][0]:
                year = parts[0][0]
                break
        authors = [f"{a.get('given','')} {a.get('family','')}".strip()
                   for a in item.get("author", [])]
        out.append(Candidate(
            title=(item.get("title") or [""])[0],
            source="crossref",
            authors=[a for a in authors if a],
            year=year,
            venue=(item.get("container-title") or [""])[0],
            doi=item.get("DOI"),
            url=item.get("URL"),
            abstract=item.get("abstract", "") or "",
        ))
    return out


# ---------------------------------------------------------------------------
# Open metadata: OpenAlex  (broad, free, good for discovery)
# ---------------------------------------------------------------------------

def openalex(query: str, limit: int, cache: Cache) -> list[Candidate]:
    mailto = os.environ.get("OPENALEX_MAILTO", "")
    params = {"search": query, "per-page": str(limit)}
    if mailto:
        params["mailto"] = mailto
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    try:
        data = _http_json(url, cache)
    except Exception:
        return []
    out: list[Candidate] = []
    for item in data.get("results", []):
        doi = item.get("doi")  # full URL
        out.append(Candidate(
            title=item.get("title") or "",
            source="openalex",
            authors=[a.get("author", {}).get("display_name", "")
                     for a in item.get("authorships", [])],
            year=item.get("publication_year"),
            venue=((item.get("primary_location") or {}).get("source") or {}).get("display_name", ""),
            doi=doi,
            url=doi or item.get("id"),
        ))
    return out


# ---------------------------------------------------------------------------
# SciELO  (open; strong Latin America coverage)
# ---------------------------------------------------------------------------

def scielo(query: str, limit: int, cache: Cache) -> list[Candidate]:
    """SciELO via its public articlemeta / search endpoint.

    SciELO has a REST search through the SciELO.org search API. Behaviour varies
    by collection; we use the SciELO search JSON endpoint and normalise results.
    If unavailable, returns [] and the retriever falls back to Crossref.
    """
    url = (
        "https://search.scielo.org/?q="
        + urllib.parse.quote(query)
        + "&output=json&count=" + str(limit)
    )
    try:
        data = _http_json(url, cache) if _looks_json(url, query, cache) else {}
    except Exception:
        return []
    # SciELO's JSON schema is not uniform; treat any hits defensively.
    out: list[Candidate] = []
    for item in data.get("docs", []) if isinstance(data, dict) else []:
        out.append(Candidate(
            title=item.get("title", ""),
            source="scielo",
            authors=[a for a in str(item.get("authors", "")).split(";") if a.strip()],
            year=_as_int(item.get("year")),
            venue=item.get("journal", "") or item.get("source", ""),
            doi=item.get("doi"),
            url=item.get("url") or item.get("link"),
        ))
    return out


# ---------------------------------------------------------------------------
# Scopus  (Elsevier; requires ELSEVIER_API_KEY) — metadata only
# ---------------------------------------------------------------------------

def scopus(query: str, limit: int, cache: Cache) -> list[Candidate]:
    key = os.environ.get("ELSEVIER_API_KEY")
    if not key:
        return []  # graceful degrade: no key -> skip
    params = {"query": f"TITLE-ABS-KEY({query})", "count": str(limit)}
    url = "https://api.elsevier.com/content/search/scopus?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={
            "X-ELS-APIKey": key, "Accept": "application/json"})
        key_ = Cache.key_for_url(url)
        cached = cache.get_json(key_)
        if cached is not None:
            data = cached
        else:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            cache.put_json(key_, data)
    except Exception:
        return []
    out: list[Candidate] = []
    entries = data.get("search-results", {}).get("entry", [])
    for item in entries:
        doi = item.get("prism:doi")
        out.append(Candidate(
            title=item.get("dc:title", ""),
            source="scopus",
            authors=[],  # author parsing needs a separate call; kept light on tokens
            year=_as_int(item.get("prism:coverDate", "")[:4]),
            venue=item.get("prism:publicationName", ""),
            doi=doi,
            url=doi and f"https://doi.org/{doi}",
        ))
    return out


# ---------------------------------------------------------------------------
# Web of Science  (Clarivate; requires WOS_API_KEY) — metadata only
# ---------------------------------------------------------------------------

def web_of_science(query: str, limit: int, cache: Cache) -> list[Candidate]:
    key = os.environ.get("WOS_API_KEY")
    if not key:
        return []
    params = {"q": f"TS=({query})", "db": "WOS", "limit": str(limit), "page": "1"}
    url = "https://api.clarivate.com/apis/wos-starter/v1/documents?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={"X-ApiKey": key})
        key_ = Cache.key_for_url(url)
        cached = cache.get_json(key_)
        if cached is not None:
            data = cached
        else:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            cache.put_json(key_, data)
    except Exception:
        return []
    out: list[Candidate] = []
    for item in data.get("hits", []):
        doi = item.get("identifiers", {}).get("doi")
        out.append(Candidate(
            title=item.get("title", ""),
            source="web_of_science",
            authors=[],  # names returned separately; kept light
            year=_as_int(str(item.get("publishInfo", {}).get("publishYear", ""))),
            venue=item.get("source", {}).get("sourceTitle", ""),
            doi=doi,
            url=item.get("links", {}).get("record"),
        ))
    return out


# ---------------------------------------------------------------------------
# ScienceDirect  (Elsevier full text/abstracts; needs ELSEVIER_API_KEY)
# ---------------------------------------------------------------------------

def sciencedirect(query: str, limit: int, cache: Cache) -> list[Candidate]:
    # ScienceDirect shares the Elsevier API key. Full-text access is
    # subscription-gated; we only request metadata/search.
    key = os.environ.get("ELSEVIER_API_KEY")
    if not key:
        return []
    params = {"query": query, "count": str(limit)}
    url = "https://api.elsevier.com/content/search/sciencedirect?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={
            "X-ELS-APIKey": key, "Accept": "application/json"})
        key_ = Cache.key_for_url(url)
        cached = cache.get_json(key_)
        if cached is not None:
            data = cached
        else:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            cache.put_json(key_, data)
    except Exception:
        return []
    out: list[Candidate] = []
    for item in data.get("search-results", {}).get("entry", []):
        doi = item.get("prism:doi")
        out.append(Candidate(
            title=item.get("dc:title", ""),
            source="sciencedirect",
            authors=[],
            year=_as_int(item.get("prism:coverDate", "")[:4]),
            venue=item.get("prism:publicationName", ""),
            doi=doi,
            url=doi and f"https://doi.org/{doi}",
        ))
    return out


# ---------------------------------------------------------------------------
# Google Scholar  -> redirected to Crossref/OpenAlex (no scraping; ToS-safe)
# ---------------------------------------------------------------------------

def google_scholar(query: str, limit: int, cache: Cache) -> list[Candidate]:
    """Treat Scholar as a *lead generator* without scraping.

    We query Crossref/OpenAlex (which index the same scholarly literature and
    return stable DOIs) and tag results so provenance is visible. This keeps the
    system within Google's terms of service while still surfacing "scholar-like"
    discovery.
    """
    leads = crossref(query, limit, cache) + openalex(query, limit, cache)
    for c in leads:
        c.source = "google_scholar→" + c.source
    return leads[:limit]


# ---------------------------------------------------------------------------
# General web fallback (flagged non-academic)
# ---------------------------------------------------------------------------

def web(query: str, limit: int, cache: Cache) -> list[Candidate]:
    """Return [] by default.

    A general web fallback is intentionally conservative: browsers/APIs differ
    and results are rarely citable. Plug your preferred search API here (e.g.
    Bing, Brave, DuckDuckGo). Results must be flagged ``source='web'`` so the
    Builder treats them as non-academic.
    """
    return []


# ---------------------------------------------------------------------------
# registry of adapters
# ---------------------------------------------------------------------------

ADAPTERS = {
    "scielo": scielo,
    "scopus": scopus,
    "web_of_science": web_of_science,
    "sciencedirect": sciencedirect,
    "google_scholar": google_scholar,
    "crossref": crossref,
    "openalex": openalex,
    "web": web,
}


def search(query: str, sources: list[str], limit: int, cache: Cache) -> list[Candidate]:
    """Query each source in priority order, dedup by DOI/URL, return candidates."""
    seen: set[str] = set()
    out: list[Candidate] = []
    for name in sources:
        fn = ADAPTERS.get(name)
        if fn is None:
            continue
        for cand in fn(query, limit, cache):
            key = (cand.doi or cand.url or cand.title).lower()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(cand)
    return out


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _as_int(v) -> int | None:
    try:
        return int(str(v)[:4])
    except (ValueError, TypeError):
        return None


def _looks_json(url: str, query: str, cache: Cache) -> bool:
    """Optimistic check; SciELO endpoint may return HTML. We just attempt."""
    return True
