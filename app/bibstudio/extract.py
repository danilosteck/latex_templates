"""Fetch and extract text, preserving page boundaries.

Page boundaries matter: the citation contract promises `[P-0007 p.3]`, which is
only honest if the extractor knows where page 3 ended. The old engine
concatenated PDF pages, so page-level quotes were impossible.

PDF extraction uses pypdf when installed (optional dependency); without it, PDFs
are skipped with a clear warning rather than producing garbage.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Iterator

# pypdf is chatty about fonts in scanned/publisher PDFs; it is noise for users.
logging.getLogger("pypdf").setLevel(logging.ERROR)

MAX_BYTES = 25 * 1024 * 1024


@dataclass
class Extracted:
    pages: list[str] = field(default_factory=list)  # one entry per page (or one for HTML)
    kind: str = "text"
    page_based: bool = False
    note: str = ""

    @property
    def text(self) -> str:
        return "\n\n".join(p for p in self.pages if p.strip())

    def is_thin(self) -> bool:
        return len(self.text.split()) < 120


def _decode(data: bytes) -> str:
    for enc in ("utf-8", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def extract_pdf(data: bytes) -> Extracted:
    try:
        import io

        from pypdf import PdfReader  # type: ignore
    except ImportError:
        return Extracted(kind="pdf", note="pypdf not installed: PDF text unavailable")
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
    except Exception as exc:
        return Extracted(kind="pdf", note=f"PDF parse failed: {type(exc).__name__}")
    pages = [_normalize(p) for p in pages]
    return Extracted(pages=pages, kind="pdf", page_based=True)


def extract_html(data: bytes) -> Extracted:
    text = _decode(data)
    # drop non-content blocks before stripping tags
    text = re.sub(r"(?is)<(script|style|noscript|nav|header|footer|aside)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?is)<!--.*?-->", " ", text)
    # keep block-level boundaries as newlines
    text = re.sub(r"(?i)</(p|div|section|article|li|h[1-6]|tr|br)>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    import html as htmllib

    text = htmllib.unescape(text)
    text = _normalize(text)
    return Extracted(pages=[text], kind="html", page_based=False)


def extract_text(data: bytes) -> Extracted:
    head = data[:512].lower()
    if data[:4] == b"%PDF" or b"application/pdf" in head:
        return extract_pdf(data)
    if b"<html" in head or b"<!doctype html" in head:
        return extract_html(data)
    return Extracted(pages=[_normalize(_decode(data))], kind="text", page_based=False)


def _normalize(text: str) -> str:
    text = text.replace("\u00ad", "")  # soft hyphen from PDFs
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk(text: str, chunk_words: int = 320, min_words: int = 60) -> Iterator[str]:
    """Split on paragraph boundaries into ~chunk_words blocks."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    buf: list[str] = []
    size = 0
    for para in paragraphs:
        words = para.split()
        if size + len(words) > chunk_words and buf:
            block = " ".join(buf)
            if len(block.split()) >= min_words:
                yield block
            buf, size = [], 0
        buf.append(para)
        size += len(words)
    if buf:
        block = " ".join(buf)
        if len(block.split()) >= 20:
            yield block


def summarize(text: str, sentences: int = 2, max_words: int = 60) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    out = " ".join(parts[:sentences]).strip()
    words = out.split()
    return " ".join(words[:max_words]) + ("…" if len(words) > max_words else "")


def excerpt(text: str, max_words: int = 90) -> str:
    words = text.split()
    return " ".join(words[:max_words]) + ("…" if len(words) > max_words else "")


def normalize_for_match(text: str) -> str:
    """Whitespace/accent-insensitive form for quote verification."""
    import unicodedata

    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[“”\"'‘’]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
