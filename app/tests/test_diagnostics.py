"""Diagnostics: a failed search must explain itself, and a 429 must not look like 'no results'."""

from __future__ import annotations

import httpx
import pytest

from bibstudio import retrieval
from bibstudio.retrieval import RetrievalContext, _get, failure_report


class FakeResponse:
    def __init__(self, status: int, payload: dict | None = None) -> None:
        self.status_code = status
        self._payload = payload or {}
        self.request = httpx.Request("GET", "https://example.org")

    def json(self) -> dict:
        return self._payload


class FakeClient:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls = 0

    def get(self, url, params=None, headers=None, timeout=None):  # noqa: ANN001
        self.calls += 1
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr("bibstudio.retrieval.time.sleep", lambda _seconds: None)


def test_query_expansion_yields_combined_and_single_term_queries(brief):
    brief.themes = [type(brief.themes[0])(
        name="green roofs",
        keywords_en=["green roof", "urban heat island"],
        keywords_other=["telhado verde"],
    )]
    queries = brief.queries()
    texts = [q for _, q in queries]
    assert "green roof urban heat island telhado verde" in texts
    assert {"green roof", "urban heat island", "telhado verde"}.issubset(set(texts))
    assert len(queries) <= 8


def test_query_expansion_is_bounded_and_deduped(brief):
    brief.themes = [
        type(brief.themes[0])(name=f"t{i}", keywords_en=[f"term{i}", f"term{i}"],
                              keywords_other=[])
        for i in range(10)
    ]
    queries = brief.queries()
    assert len(queries) <= 8
    assert len({q.lower() for _, q in queries}) == len(queries)


def test_retry_turns_a_429_into_a_result():
    client = FakeClient([FakeResponse(429), FakeResponse(429), FakeResponse(200, {"ok": 1})])
    ctx = RetrievalContext(client=client)
    assert _get(ctx, "x", "https://example.org") == {"ok": 1}
    assert client.calls == 3


def test_404_is_not_retried():
    client = FakeClient([FakeResponse(404)])
    ctx = RetrievalContext(client=client)
    with pytest.raises(httpx.HTTPStatusError):
        _get(ctx, "x", "https://example.org")
    assert client.calls == 1


def test_rate_limited_adapter_reports_status():
    client = FakeClient([FakeResponse(429), FakeResponse(429), FakeResponse(429)])
    ctx = RetrievalContext(client=client)
    assert retrieval.openalex("green roof", 5, ctx) == []
    report = ctx.report("openalex")
    assert report.last_status == 429
    assert report.errors and "429" in report.errors[-1]
    assert any("openalex" in w for w in ctx.warnings)


def test_failure_report_names_the_sources_filters_and_errors():
    ctx = RetrievalContext(year_from=2012, languages=["en"],
                           exclude_terms=["review"])
    ctx.fail("openalex", httpx.HTTPStatusError(
        "HTTP 403", request=httpx.Request("GET", "https://x"),
        response=httpx.Response(403, request=httpx.Request("GET", "https://x"))))
    ctx.report("crossref").calls = 3
    ctx.filtered_out = 4
    text = failure_report([("t", "green roof")], ["openalex", "crossref"], ctx)
    assert "openalex" in text and "HTTP 403" in text
    assert "crossref" in text and "3 call(s)" in text
    assert "years 2012" in text
    assert "4 result(s) were discarded" in text
    assert "403/429" in text


def test_diagnose_returns_structure_and_examples(monkeypatch):
    monkeypatch.setitem(retrieval.ADAPTERS, "fake", lambda q, n, ctx: [
        retrieval.Candidate(title="A paper", source="fake", year=2020, doi="10.1/x",
                            venue="Journal")
    ])
    ctx = RetrievalContext()
    result = retrieval.diagnose([("t", "query")], ["fake"], ctx)
    assert result["hits"] == 1
    assert result["sources"][0]["name"] == "fake"
    assert result["examples"][0]["title"] == "A paper"
    assert result["explanation"] == ""


def test_diagnose_reports_an_adapter_that_raises(monkeypatch):
    def boom(query, limit, ctx):  # noqa: ANN001, ARG001
        raise RuntimeError("kaboom")

    monkeypatch.setitem(retrieval.ADAPTERS, "boom", boom)
    ctx = RetrievalContext()
    result = retrieval.diagnose([("t", "query")], ["boom"], ctx)
    assert result["hits"] == 0
    assert "boom" in result["explanation"]


def test_year_typo_is_repaired(brief):
    """20100 is a typo for 2010; it must not make every API answer 400."""
    fixed = type(brief)(**{**brief.model_dump(), "year_from": 20100})
    assert fixed.year_from == 2010
    assert fixed.queries()


def test_year_out_of_range_becomes_none(brief):
    fixed = type(brief)(**{**brief.model_dump(), "year_from": 99999, "year_to": "any"})
    assert fixed.year_from is None
    assert fixed.year_to is None


def test_api_error_body_is_surfaced():
    ctx = RetrievalContext()
    request = httpx.Request("GET", "https://api.crossref.org/works")
    response = httpx.Response(400, request=request,
                              text='{"message":"from-pub-date: 20100-01-01 is not a valid date"}')
    ctx.fail("crossref", httpx.HTTPStatusError("HTTP 400", request=request, response=response))
    report = ctx.report("crossref")
    assert report.last_status == 400
    assert "not a valid date" in report.errors[0]
    text = failure_report([("t", "q")], ["crossref"], ctx)
    assert "not a valid date" in text
