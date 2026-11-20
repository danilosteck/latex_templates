from __future__ import annotations

from bibstudio import bibtex, ledger
from bibstudio.models import Brief, Evidence, Paper


def _paper(pid="P-0001", **kw):
    base = dict(id=pid, title="Green roofs and urban heat", authors=["Silva, A.", "Costa, B."],
                year=2020, venue="Urban Climate", doi=f"10.1000/{pid.lower()}",
                source_type="peer_reviewed", verified="yes")
    base.update(kw)
    return Paper(**base)


def test_citation_parsing():
    found = ledger.citations("Claim one [P-0001]. Quote [P-0002 p.4] and again [P-0001].")
    assert found == [("P-0001", None), ("P-0002", 4), ("P-0001", None)]
    assert ledger.cited_ids("a [P-0002] b [P-0002]") == ["P-0002"]


def test_unresolved_and_missing_sections(brief):
    doc = (
        "## Executive summary\n\n"
        "This paragraph is long enough to count as a substantive claim about cooling "
        "effects and it carries a citation [P-0009].\n\n"
        "## Extra\n\nAnother long paragraph that states a result without any citation "
        "and should be reported by the ledger.\n"
    )
    led = ledger.check(doc, [_paper()], [], brief)
    assert led.missing == ["P-0009"]
    assert "Viewpoint map" in led.sections_missing
    assert led.paragraphs_without_citation
    assert led.verdict == "fail"


def test_quote_must_exist_in_evidence(brief):
    evidence = [Evidence(paper_id="P-0001", locator="p.2", page=2,
                         text="Green roofs reduced peak surface temperature by 2.1 degrees.")]
    good = ('"Green roofs reduced peak surface temperature by 2.1 degrees" [P-0001 p.2]')
    bad = ('"Green roofs reduced peak surface temperature by 9.9 degrees" [P-0001 p.2]')
    doc_good = f"## Executive summary\n\n{good}\n\n## Viewpoint map\n\n{good}\n"
    doc_bad = f"## Executive summary\n\n{bad}\n\n## Viewpoint map\n\n{bad}\n"
    assert ledger.check(doc_good, [_paper()], evidence, brief).quote_mismatches == []
    mism = ledger.check(doc_bad, [_paper()], evidence, brief).quote_mismatches
    assert len(mism) == 2


def test_references_come_from_records_not_the_model():
    doc = "## Executive summary\n\nA claim [P-0001].\n\n## References\n\n- invented [P-9999]\n"
    out = ledger.ensure_references(doc, [_paper()])
    assert "P-9999" not in out
    assert "[P-0001]" in out
    assert "Urban Climate" in out


def test_bibtex_is_valid_and_escaped():
    papers = [_paper("P-0001", title="Cost & benefit_analysis of #heat", venue="A & B"),
              _paper("P-0002")]
    text = bibtex.build(papers)
    assert bibtex.validate(text) == []
    assert "@article{P-0001," in text
    assert r"\&" in text and r"\_" in text
    assert text.index("P-0001") < text.index("P-0002")


def test_bibtex_escapes_unbalanced_braces():
    papers = [_paper(title="A {weird} title")]
    text = bibtex.build(papers)
    assert bibtex.validate(text) == []


def test_page_locator_must_exist_in_the_source(brief):
    evidence = [Evidence(paper_id="P-0001", locator="p.2", page=2,
                         text="Green roofs reduced peak surface temperature.")]
    doc = (
        "## Executive summary\n\nA cited claim about cooling [P-0001 p.2].\n\n"
        "## Viewpoint map\n\nAnother claim pointing at a page that was never extracted "
        "[P-0001 p.9].\n"
    )
    led = ledger.check(doc, [_paper()], evidence, brief)
    assert len(led.page_mismatches) == 1
    assert "p.9" in led.page_mismatches[0]
    assert led.verdict == "fail"


def test_abstract_citation_has_no_page_requirement(brief):
    evidence = [Evidence(paper_id="P-0001", locator="abstract",
                         text="Green roofs cool cities.")]
    doc = (
        "## Executive summary\n\nA cited claim [P-0001].\n\n"
        "## Viewpoint map\n\nAnother cited claim [P-0001].\n\n## References\n\n- [P-0001]\n"
    )
    led = ledger.check(doc, [_paper()], evidence, brief)
    assert led.page_mismatches == []
    assert led.verdict == "pass"


def test_verdict_pass_when_everything_resolves(brief):
    evidence = [Evidence(paper_id="P-0001", locator="abstract",
                         text="Green roofs cool cities.")]
    doc = (
        "## Executive summary\n\nGreen roofs cool cities according to the reviewed "
        "evidence [P-0001].\n\n"
        "## Viewpoint map\n\nThe green infrastructure viewpoint argues for vegetation "
        "first [P-0001].\n\n"
        "## References\n\n- [P-0001] Silva (2020)\n"
    )
    led = ledger.check(doc, [_paper()], evidence, brief)
    assert led.verdict == "pass", led.model_dump()
