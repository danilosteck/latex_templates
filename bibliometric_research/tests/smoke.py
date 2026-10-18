"""Smoke tests — run with:  python -m tests.smoke

These verify the blueprint's plumbing without any network or API key:
  * cache round-trips,
  * evidence id parsing,
  * registry id stability + validation target,
  * LLM mock JSON output for all three roles,
  * config fallback parser reads the example config,
  * a full orchestrator run in mock mode using a temp study.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from core.cache import Cache
from core.evidence import EvidenceItem, excerpt, parse_ev_id
from core.llm import build_llm
from core.registry import Registry, make_paper_id, normalize_doi
from core.orchestrator import _parse_simple_yaml, run, load_config


def test_cache() -> None:
    with tempfile.TemporaryDirectory() as d:
        c = Cache(d)
        key = Cache.key_for_url("https://example.org/a")
        assert c.get_blob(key) is None
        c.put_blob(key, b"hello")
        assert c.get_blob(key) == b"hello"
        c.put_text(key, "clean text")
        assert c.get_text(key) == "clean text"
        c.put_json(key, {"x": 1})
        assert c.get_json(key) == {"x": 1}
        # idempotent keys
        assert Cache.key_for_query("A  b", "crossref") == Cache.key_for_query("a b", "crossref")


def test_evidence() -> None:
    eid = EvidenceItem.make_id("p_abc", 3)
    assert eid == "ev://p_abc#c3"
    assert parse_ev_id(eid) == ("p_abc", 3)
    assert len(excerpt("word " * 200, 80).split()) == 80


def test_registry() -> None:
    assert normalize_doi("https://doi.org/10.1/ABC") == "10.1/abc"
    assert normalize_doi("doi: 10.1/X") == "10.1/x"
    a = make_paper_id("10.1/abc", None)
    b = make_paper_id("https://doi.org/10.1/ABC", None)
    assert a == b and a.startswith("p_") and len(a) == 18
    c = make_paper_id(None, "https://example.org/x")
    assert c.startswith("p_")


def test_mock_llm_roles() -> None:
    llm = build_llm({"provider": "mock", "models": {"mock": "mock-1"}})
    assert "queries" in llm.complete_json("You are the retriever agent", "x")
    assert "document" in llm.complete_json("You are the builder agent", "x")
    assert "findings" in llm.complete_json("You are the critic agent", "x")


def test_fallback_config() -> None:
    cfg = _parse_simple_yaml(Path("config.example.yaml").read_text())
    assert cfg["provider"] == "mock"
    assert cfg["retrieval"]["sources"][0] == "scielo"
    assert isinstance(cfg["retrieval"]["max_fetches"], int)
    assert cfg["orchestration"]["checkpoints"]["enabled"] is True


def test_orchestrator_mock_run() -> None:
    """End-to-end in a temp dir with networking disabled via mock + no fetch hits.

    We point retrieval at 'web' (returns []) so no real network calls are made,
    then assert the pipeline produces the expected output files.
    """
    import os
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as d:
        os.chdir(d)
        try:
            study = Path("study"); study.mkdir()
            (study / "brief.md").write_text("# Brief\nObject: test.\nQuestion: what?\n")
            (study / "workplan.md").write_text(
                "# Workplan\n1. Map of viewpoints\n2. MPAs\n3. References\n")
            (study / "viewpoints.yaml").write_text(
                "viewpoints:\n  - label: A\n    description: a\n")
            cfg = {
                "provider": "mock", "models": {"mock": "mock-1"},
                "max_output_tokens": 500,
                "retrieval": {"sources": ["web"], "max_fetches": 0,
                              "results_per_query": 1, "max_excerpt_words": 40,
                              "chunk_words": 100},
                "orchestration": {"max_rounds": 1, "token_budget": 100000,
                                  "checkpoints": {"enabled": False}},
                "cache": {"dir": "cache", "ttl_days": 0},
            }
            rc = run(study, cfg, no_checkpoints=True)
            assert rc == 0
            assert Path("output/document_final.md").exists()
            assert Path("output/transcript.json").exists()
            t = json.loads(Path("output/transcript.json").read_text())
            assert t["provider"] == "mock"
        finally:
            os.chdir(cwd)


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\nAll {len(tests)} smoke tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
