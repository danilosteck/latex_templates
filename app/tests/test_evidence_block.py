from __future__ import annotations

from bibstudio.engine import _evidence_block
from bibstudio.models import Evidence


def test_evidence_block_renders_the_exact_citation_form():
    evidence = [
        Evidence(paper_id="P-0002", locator="p.4", page=4, text="A quote from page four.",
                 summary="summary four"),
        Evidence(paper_id="P-0003", locator="abstract", page=None, text="An abstract.",
                 summary="summary abstract"),
    ]
    block, used = _evidence_block(evidence, None)
    assert "- [P-0002 p.4]" in block
    assert "- [P-0003] (abstract)" in block
    assert used == ["P-0002", "P-0003"]


def test_evidence_block_respects_the_allowed_paper_set():
    evidence = [
        Evidence(paper_id="P-0001", locator="p.1", page=1, text="one", summary="s1"),
        Evidence(paper_id="P-0002", locator="p.1", page=1, text="two", summary="s2"),
    ]
    block, used = _evidence_block(evidence, ["P-0002"])
    assert "P-0001" not in block
    assert used == ["P-0002"]


def test_evidence_block_is_bounded():
    evidence = [
        Evidence(paper_id=f"P-{i:04d}", locator="p.1", page=1, text="text", summary="s")
        for i in range(1, 40)
    ]
    block, _ = _evidence_block(evidence, None)
    assert block.count("\n- ") + 1 <= 10
