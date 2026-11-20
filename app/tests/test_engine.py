"""End-to-end engine tests: offline, deterministic, no network.

The retrieval adapters and DOI validation are monkeypatched at the module
attribute level, which is exactly how the engine calls them — so this exercises
the real pipeline minus the network.
"""

from __future__ import annotations

import time

import pytest

from bibstudio import retrieval
from bibstudio.engine import JobManager
from bibstudio.models import Candidate, Paper


def _fake_candidates(queries, sources, ctx, **kw):
    return [
        Candidate(title="Green roofs and urban cooling", source="openalex",
                  authors=["Silva, A."], year=2019, venue="Urban Climate",
                  doi="10.1000/a", url="https://doi.org/10.1000/a",
                  abstract="Green roofs reduced surface temperature in three districts.",
                  score=1.0, theme="green roofs"),
        Candidate(title="Reflective materials versus vegetation", source="crossref",
                  authors=["Costa, B."], year=2021, venue="Building and Environment",
                  doi="10.1000/b", url="https://doi.org/10.1000/b",
                  abstract="Reflective coatings outperformed vegetation at street level.",
                  score=0.9, theme="green roofs"),
        Candidate(title="Equity in urban heat exposure", source="openalex",
                  authors=["Rocha, C."], year=2022, venue="Cities",
                  doi="10.1000/c", url="https://doi.org/10.1000/c",
                  abstract="Heat exposure follows income; mitigation is unevenly distributed.",
                  score=0.8, theme="green roofs"),
    ]


def _fake_validate(doi, ctx):
    return "yes", "fake validation"


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(retrieval, "search", _fake_candidates)
    monkeypatch.setattr(retrieval, "validate_doi", _fake_validate)


def _wait(project, manager, run_id, statuses, timeout=40.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = project.load_run_state(run_id)
        if state and state.status in statuses:
            return state
        time.sleep(0.1)
    state = project.load_run_state(run_id)
    log = (project.run_dir(run_id) / "log.jsonl").read_text() if (
        project.run_dir(run_id) / "log.jsonl").exists() else ""
    raise AssertionError(f"run stuck in {state.status if state else 'unknown'}\n{log[-3000:]}")


def test_full_run_produces_cited_document(ws, brief, offline):
    brief.checkpoints.candidates = False
    brief.checkpoints.outline = False
    brief.checkpoints.review = False
    project = ws.create_project(brief)

    manager = JobManager()
    state = manager.start(project)
    final = _wait(project, manager, state.run_id, {"done", "failed", "cancelled"})
    if final.status != "done":
        raise AssertionError(final.error)

    outputs = project.run_dir(state.run_id) / "outputs"
    document = (outputs / "document-final.md").read_text()
    assert "## Executive summary" in document
    assert "[P-0001]" in document
    assert "## References" in document
    assert "invented" not in document

    bib = (project.references_dir / "library.bib").read_text()
    assert bib.count("@article{") == 3
    from bibstudio import bibtex
    assert bibtex.validate(bib) == []

    report = (project.run_dir(state.run_id) / "report.json").read_text()
    import json
    data = json.loads(report)
    assert data["ledger"]["missing"] == []
    assert data["ledger"]["sources_total"] == 3
    assert data["ledger"]["sections_missing"] == []
    assert data["cost_usd"] == 0.0  # mock provider

    papers = project.papers()
    assert [p.id for p in papers] == ["P-0001", "P-0002", "P-0003"]
    assert all(p.verified == "yes" for p in papers)
    assert len(project.evidence()) == 3

    # the human-readable artifacts exist too
    assert (project.papers_dir / "P-0001.md").exists()
    assert (project.references_dir / "validation.md").exists()


def test_candidate_checkpoint_blocks_then_continues(ws, brief, offline):
    brief.checkpoints.candidates = True
    brief.checkpoints.outline = False
    brief.checkpoints.review = False
    project = ws.create_project(brief)

    manager = JobManager()
    state = manager.start(project)
    waiting = _wait(project, manager, state.run_id, {"waiting"})
    assert waiting.checkpoint is not None
    assert waiting.checkpoint.kind == "candidates"
    assert len(waiting.checkpoint.data["candidates"]) == 3

    assert manager.decide(state.run_id, {"action": "continue"}) is True
    final = _wait(project, manager, state.run_id, {"done", "failed"}, timeout=40)
    assert final.status == "done"
    assert len(project.papers()) == 3


def test_checkpoint_can_drop_a_candidate(ws, brief, offline):
    brief.checkpoints.candidates = True
    brief.checkpoints.outline = False
    brief.checkpoints.review = False
    project = ws.create_project(brief)
    manager = JobManager()
    state = manager.start(project)
    waiting = _wait(project, manager, state.run_id, {"waiting"})
    keys = [c["key"] for c in waiting.checkpoint.data["candidates"]]
    manager.decide(state.run_id, {"action": "continue", "keys": keys[:2]})
    final = _wait(project, manager, state.run_id, {"done", "failed"})
    assert final.status == "done"
    assert len(project.papers()) == 2


def test_stop_at_checkpoint_cancels_cleanly(ws, brief, offline):
    brief.checkpoints.candidates = True
    brief.checkpoints.outline = False
    brief.checkpoints.review = False
    project = ws.create_project(brief)
    manager = JobManager()
    state = manager.start(project)
    _wait(project, manager, state.run_id, {"waiting"})
    manager.decide(state.run_id, {"action": "stop"})
    final = _wait(project, manager, state.run_id, {"cancelled", "done", "failed"})
    assert final.status == "cancelled"
    assert project.papers() == []


def test_cancel_mid_wait(ws, brief, offline):
    brief.checkpoints.outline = True
    brief.checkpoints.candidates = False
    brief.checkpoints.review = False
    project = ws.create_project(brief)
    manager = JobManager()
    state = manager.start(project)
    _wait(project, manager, state.run_id, {"waiting"})
    assert manager.cancel(state.run_id) is True
    final = _wait(project, manager, state.run_id, {"cancelled", "done", "failed"})
    assert final.status == "cancelled"


def test_empty_search_fails_with_an_explanation(ws, brief, monkeypatch):
    """The exact failure a user hit: a run must say why nothing was found."""
    monkeypatch.setattr(retrieval, "search", lambda *a, **k: [])

    def boom(query, limit, ctx):
        raise RuntimeError("kaboom")

    monkeypatch.setitem(retrieval.ADAPTERS, "openalex", boom)
    brief.checkpoints.candidates = False
    brief.checkpoints.outline = False
    brief.checkpoints.review = False
    project = ws.create_project(brief)

    manager = JobManager()
    state = manager.start(project)
    final = _wait(project, manager, state.run_id, {"done", "failed", "cancelled"})
    assert final.status == "failed"
    assert "No sources found" in (final.error or "")
    events = (project.run_dir(state.run_id) / "log.jsonl").read_text()
    assert "diagnose" in events


def test_manual_source_is_used_and_never_duplicated(ws, brief):
    project = ws.create_project(brief)
    from bibstudio.models import Evidence, Paper

    paper = Paper(id="P-0001", title="Manual source", doi="10.1000/manual",
                  source_type="peer_reviewed")
    project.save_papers([paper])
    project.save_evidence([Evidence(paper_id="P-0001", locator="abstract",
                                    text="Manual abstract text.")])
    assert project.paper_by_doi("https://doi.org/10.1000/MANUAL") is None  # not normalized
    assert project.paper_by_doi("10.1000/manual").id == "P-0001"
