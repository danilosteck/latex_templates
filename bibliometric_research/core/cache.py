"""Content-addressed local cache.

Everything the system fetches (URLs, PDFs, DOCX, search results) is stored on
disk once and reused forever. This is the backbone of token/network savings:

  * re-fetching the same URL is free,
  * re-extracting text from a cached blob is free,
  * repeated searches return cached result lists.

Layout::

    cache/
      blobs/<sha256>            raw bytes (html/pdf/docx/...)
      text/<sha256>.txt         extracted clean text
      json/<sha256>.json        cached JSON (search results, metadata)

Keys are hashes of the canonical input (URL, file bytes, or normalized query),
so identical content always maps to the same entry.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any


class Cache:
    def __init__(self, root: str | Path = "cache", ttl_days: int = 0) -> None:
        self.root = Path(root)
        self.ttl_seconds = ttl_days * 86400 if ttl_days else 0
        for sub in ("blobs", "text", "json"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

    # -- keys ---------------------------------------------------------------

    @staticmethod
    def hash_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def hash_str(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @classmethod
    def key_for_url(cls, url: str) -> str:
        return cls.hash_str("url:" + url.strip())

    @classmethod
    def key_for_query(cls, query: str, source: str = "") -> str:
        norm = " ".join(query.lower().split())
        return cls.hash_str(f"query:{source}:{norm}")

    # -- generic helpers ----------------------------------------------------

    def _fresh(self, path: Path) -> bool:
        if not path.exists():
            return False
        if self.ttl_seconds:
            return (time.time() - path.stat().st_mtime) < self.ttl_seconds
        return True

    # -- blobs (raw bytes) --------------------------------------------------

    def get_blob(self, key: str) -> bytes | None:
        p = self.root / "blobs" / key
        return p.read_bytes() if self._fresh(p) else None

    def put_blob(self, key: str, data: bytes) -> str:
        (self.root / "blobs" / key).write_bytes(data)
        return key

    # -- extracted text -----------------------------------------------------

    def get_text(self, key: str) -> str | None:
        p = self.root / "text" / f"{key}.txt"
        return p.read_text(encoding="utf-8") if self._fresh(p) else None

    def put_text(self, key: str, text: str) -> str:
        (self.root / "text" / f"{key}.txt").write_text(text, encoding="utf-8")
        return key

    # -- json (search results, metadata) ------------------------------------

    def get_json(self, key: str) -> Any | None:
        p = self.root / "json" / f"{key}.json"
        if not self._fresh(p):
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def put_json(self, key: str, obj: Any) -> str:
        (self.root / "json" / f"{key}.json").write_text(
            json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return key

    # -- introspection ------------------------------------------------------

    def stats(self) -> dict[str, int]:
        def count(sub: str) -> int:
            return sum(1 for _ in (self.root / sub).glob("*"))
        return {"blobs": count("blobs"), "text": count("text"), "json": count("json")}
