"""Fetch + extract documents to clean text, with caching at every step.

Pipeline for one URL::

    bytes  = fetch_bytes(url)      # cached blob
    text   = extract_text(bytes, kind)  # cached text
    chunks = chunk_text(text)

Extraction uses optional dependencies when available and falls back gracefully:
  * PDF  -> pypdf
  * DOCX -> python-docx
  * HTML -> BeautifulSoup (or a regex stripper)
  * plain text -> as-is

Nothing here calls an LLM. This module is pure ingestion.
"""

from __future__ import annotations

import re
import urllib.request
from pathlib import Path

from core.cache import Cache

_DEFAULT_HEADERS = {"User-Agent": "bibliometric-research/1.0 (+blueprint)"}


# ---------------------------------------------------------------------------
# fetching
# ---------------------------------------------------------------------------

def fetch_bytes(url: str, cache: Cache, timeout: float = 20.0) -> bytes:
    """Download ``url`` (or return cached bytes). Keyed by URL."""
    key = Cache.key_for_url(url)
    cached = cache.get_blob(key)
    if cached is not None:
        return cached
    req = urllib.request.Request(url, headers=_DEFAULT_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    cache.put_blob(key, data)
    return data


# ---------------------------------------------------------------------------
# extraction
# ---------------------------------------------------------------------------

def _kind(url: str, data: bytes) -> str:
    low = url.lower()
    if low.endswith(".pdf") or data[:4] == b"%PDF":
        return "pdf"
    if low.endswith(".docx"):
        return "docx"
    if low.endswith((".html", ".htm")) or b"<html" in data[:512].lower():
        return "html"
    return "text"


def extract_text(data: bytes, kind: str) -> str:
    if kind == "pdf":
        return _extract_pdf(data)
    if kind == "docx":
        return _extract_docx(data)
    if kind == "html":
        return _extract_html(data)
    return data.decode("utf-8", errors="replace")


def _extract_pdf(data: bytes) -> str:
    try:
        import io
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        return "[pdf: install pypdf to extract text]"
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _extract_docx(data: bytes) -> str:
    try:
        import io
        import docx  # type: ignore
    except ImportError:
        return "[docx: install python-docx to extract text]"
    document = docx.Document(io.BytesIO(data))
    return "\n".join(p.text for p in document.paragraphs)


def _extract_html(data: bytes) -> str:
    html = data.decode("utf-8", errors="replace")
    try:
        from bs4 import BeautifulSoup  # type: ignore
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
    except ImportError:
        text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return re.sub(r"[ \t]+", " ", text).strip()


# ---------------------------------------------------------------------------
# convenience: URL -> clean text (fully cached) + chunking
# ---------------------------------------------------------------------------

def url_to_text(url: str, cache: Cache, timeout: float = 20.0) -> str:
    """Return clean text for ``url``; both bytes and text are cached."""
    key = Cache.key_for_url(url)
    cached = cache.get_text(key)
    if cached is not None:
        return cached
    data = fetch_bytes(url, cache, timeout=timeout)
    text = extract_text(data, _kind(url, data))
    cache.put_text(key, text)
    return text


def file_to_text(path: str | Path, cache: Cache) -> str:
    """Return clean text for a local PDF/DOCX/HTML/txt file."""
    p = Path(path)
    data = p.read_bytes()
    key = Cache.hash_bytes(data)
    cached = cache.get_text(key)
    if cached is not None:
        return cached
    kind = _kind(str(p), data)
    text = extract_text(data, kind)
    cache.put_text(key, text)
    return text


def chunk_text(text: str, chunk_words: int = 350) -> list[str]:
    """Split text into ~``chunk_words`` word chunks, respecting paragraphs."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for para in paragraphs:
        words = para.split()
        if buf_len + len(words) > chunk_words and buf:
            chunks.append(" ".join(buf))
            buf, buf_len = [], 0
        buf.append(para)
        buf_len += len(words)
    if buf:
        chunks.append(" ".join(buf))
    return chunks or ([text] if text.strip() else [])
