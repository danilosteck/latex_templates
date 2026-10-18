"""Evidence items and the ``ev://`` reference scheme.

Agents never paste whole documents into prompts. They exchange short evidence
IDs of the form::

    ev://<paper_id>#c<chunk_index>

An *evidence item* carries a short neutral summary and a bounded verbatim
excerpt, which is what actually gets sent to the Builder/Critic. Full text stays
in the cache and is only pulled when a task truly needs it.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass
class EvidenceItem:
    ev_id: str            # ev://p_xxxx#c3
    paper_id: str         # p_xxxx
    chunk: int
    summary: str          # 1–3 neutral sentences
    excerpt: str          # <= max_excerpt_words verbatim
    relevance: float = 0.0

    @staticmethod
    def make_id(paper_id: str, chunk: int) -> str:
        return f"ev://{paper_id}#c{chunk}"

    def to_dict(self) -> dict:
        return asdict(self)


def parse_ev_id(ev_id: str) -> tuple[str, int]:
    """Split ``ev://p_abc#c3`` -> (``p_abc``, 3)."""
    if not ev_id.startswith("ev://"):
        raise ValueError(f"not an evidence id: {ev_id!r}")
    body = ev_id[len("ev://"):]
    paper_id, _, chunk = body.partition("#c")
    return paper_id, int(chunk) if chunk else 0


def excerpt(text: str, max_words: int, center_word: int | None = None) -> str:
    """Return a <= max_words window of ``text``.

    If ``center_word`` is given, the window is centred there (used when we know
    roughly which part of a chunk matched); otherwise it takes the head.
    """
    words = text.split()
    if len(words) <= max_words:
        return " ".join(words)
    if center_word is None:
        return " ".join(words[:max_words])
    half = max_words // 2
    start = max(0, center_word - half)
    end = min(len(words), start + max_words)
    return " ".join(words[start:end])


def save_evidence(path: str | Path, items: Iterable[EvidenceItem]) -> None:
    """Append evidence items to a JSONL file (dedup by ev_id on load)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    existing = {e.ev_id for e in load_evidence(p)}
    with p.open("a", encoding="utf-8") as fh:
        for item in items:
            if item.ev_id in existing:
                continue
            fh.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")
            existing.add(item.ev_id)


def load_evidence(path: str | Path) -> list[EvidenceItem]:
    p = Path(path)
    if not p.exists():
        return []
    items: list[EvidenceItem] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            items.append(EvidenceItem(**json.loads(line)))
    return items
