"""Paper registry: traceability + existence validation.

Every paper the Retriever touches becomes a record in ``registry/papers.jsonl``
with a **stable id** derived from its normalized DOI (preferred) or URL. This
gives us:

  * a single source of truth for "what did we look at",
  * stable ids so evidence references never drift,
  * a repeatable existence check (``validate``) that does not involve any LLM.

Run validation with::

    python -m core.registry validate registry/papers.jsonl

The validator performs an HTTP(S) reachability check (HEAD, then GET) for the
DOI/URL and updates ``validated_at`` / ``status``. It is dependency-free (uses
``urllib``) and polite (short timeout, no retries that hammer servers).
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    d = doi.strip().lower()
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)
    d = re.sub(r"^doi:\s*", "", d)
    return d or None


def make_paper_id(doi: str | None, url: str | None) -> str:
    """Stable id: hash of normalized DOI (preferred) or URL."""
    from core.cache import Cache  # local import to keep module import light

    basis = normalize_doi(doi) or (url or "").strip()
    if not basis:
        raise ValueError("need a doi or url to mint a paper id")
    return "p_" + Cache.hash_str(basis)[:16]


@dataclass
class Paper:
    id: str
    title: str = ""
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str = ""
    doi: str | None = None
    url: str | None = None
    source: str = ""
    content_hash: str | None = None
    fetched_at: str = ""
    validated_at: str = ""
    status: str = "ok"            # ok | unreachable | no_doi | unvalidated
    retrieved_by: str = "retriever"
    queries: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class Registry:
    def __init__(self, path: str | Path = "registry/papers.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._index: dict[str, Paper] = {p.id: p for p in self._load()}

    # -- persistence --------------------------------------------------------

    def _load(self) -> list[Paper]:
        if not self.path.exists():
            return []
        out: list[Paper] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(Paper(**json.loads(line)))
        return out

    def _rewrite(self) -> None:
        with self.path.open("w", encoding="utf-8") as fh:
            for p in self._index.values():
                fh.write(json.dumps(p.to_dict(), ensure_ascii=False) + "\n")

    # -- api ----------------------------------------------------------------

    def exists(self, paper_id: str) -> bool:
        return paper_id in self._index

    def get(self, paper_id: str) -> Paper | None:
        return self._index.get(paper_id)

    def upsert(self, paper: Paper) -> Paper:
        """Insert or merge a paper; existing fields win unless empty."""
        cur = self._index.get(paper.id)
        if cur is None:
            self._index[paper.id] = paper
        else:
            # Merge: fill gaps, union queries, prefer richer metadata.
            for f in ("title", "venue", "doi", "url", "source", "content_hash",
                      "fetched_at", "validated_at"):
                new = getattr(paper, f)
                if new and not getattr(cur, f):
                    setattr(cur, f, new)
            if paper.year and not cur.year:
                cur.year = paper.year
            if paper.authors and not cur.authors:
                cur.authors = paper.authors
            for q in paper.queries:
                if q not in cur.queries:
                    cur.queries.append(q)
            if paper.notes and paper.notes not in cur.notes:
                cur.notes = (cur.notes + " | " + paper.notes).strip(" |")
        self._rewrite()
        return self._index[paper.id]

    def all(self) -> list[Paper]:
        return list(self._index.values())

    # -- validation ---------------------------------------------------------

    def validate(self, timeout: float = 10.0) -> dict[str, int]:
        """Re-check that every paper's source resolves. Returns counts."""
        counts = {"ok": 0, "unreachable": 0, "no_doi": 0}
        for p in self._index.values():
            target = _resolve_target(p)
            if not target:
                p.status = "no_doi"
                counts["no_doi"] += 1
            elif _reachable(target, timeout):
                p.status = "ok"
                counts["ok"] += 1
            else:
                p.status = "unreachable"
                counts["unreachable"] += 1
            p.validated_at = _now()
        self._rewrite()
        return counts


# ---------------------------------------------------------------------------
# validation helpers
# ---------------------------------------------------------------------------

def _resolve_target(p: Paper) -> str | None:
    doi = normalize_doi(p.doi)
    if doi:
        return "https://doi.org/" + doi
    return p.url or None


def _reachable(url: str, timeout: float) -> bool:
    headers = {"User-Agent": "bibliometric-research-validator/1.0"}
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if 200 <= resp.status < 400:
                    return True
        except urllib.error.HTTPError as e:
            # 401/403/405 = reachable-but-restricted; the server responded.
            if e.code in (401, 403, 405):
                return True
        except (urllib.error.URLError, TimeoutError, ValueError):
            continue
    return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] != "validate":
        print("usage: python -m core.registry validate <registry.jsonl>")
        return 2
    reg = Registry(argv[1])
    print(f"Validating {len(reg.all())} papers from {argv[1]} ...")
    counts = reg.validate()
    print(f"  ok:          {counts['ok']}")
    print(f"  unreachable: {counts['unreachable']}")
    print(f"  no_doi:      {counts['no_doi']}")
    if counts["unreachable"]:
        print("\nUnreachable sources:")
        for p in reg.all():
            if p.status == "unreachable":
                print(f"  - {p.id}  {p.doi or p.url}  ({p.title[:60]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
