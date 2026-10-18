"""Agent 2 — Builder.

Writes the analysis document required by the Workplan. It **does not browse**.

Contract
--------
* Input: the Study Brief, the Workplan, and a set of evidence items (short
  summaries + bounded excerpts, each with an ``ev://`` id).
* Output: ``{"document": "<markdown>", "evidence_requests": [ {...}, ... ]}``.
* If the Builder needs information it does not have, it emits **evidence
  requests** instead of inventing. The orchestrator routes those to the
  Retriever and re-invokes the Builder.
* Every substantive claim must cite an ``ev://`` id present in the provided
  evidence. Unresolved ids are detected by the orchestrator/Critic.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from core.evidence import EvidenceItem
from core.llm import LLM


@dataclass
class BuildResult:
    document: str = ""
    evidence_requests: list[dict] = field(default_factory=list)
    cited_ids: list[str] = field(default_factory=list)


class BuilderAgent:
    def __init__(self, llm: LLM, max_excerpt_words: int = 80) -> None:
        self.llm = llm
        self.max_excerpt_words = max_excerpt_words

    def run(
        self,
        brief: str,
        workplan: str,
        viewpoints: list[dict],
        evidence: list[EvidenceItem],
        *,
        previous_draft: str | None = None,
        critic_findings: list[dict] | None = None,
        max_evidence_in_prompt: int = 60,
    ) -> BuildResult:
        # Robust against providers that return empty or truncated JSON (e.g.
        # when a large prompt hits the output-token cap). Try the full evidence
        # set, then retry once with a smaller set + stricter instruction, and
        # finally return a labelled placeholder instead of crashing.
        attempts = [
            (evidence[:max_evidence_in_prompt], previous_draft, critic_findings, False),
            (evidence[: max(8, max_evidence_in_prompt // 3)], None, None, True),
        ]
        last_err: Exception | None = None
        for ev, prev, findings, compact in attempts:
            user = _render_user(
                brief=brief,
                workplan=workplan,
                viewpoints=viewpoints,
                evidence=ev,
                previous_draft=prev,
                critic_findings=findings,
                retry_compact=compact,
            )
            try:
                data = self.llm.complete_json(_SYSTEM, user)
            except Exception as e:  # empty / truncated / non-JSON
                last_err = e
                continue
            doc, reqs = _coerce(data)
            if doc.strip():
                cited = sorted(set(re.findall(r"ev://[A-Za-z0-9_\-]+#c\d+", doc)))
                return BuildResult(document=doc, evidence_requests=reqs, cited_ids=cited)
            last_err = ValueError("model returned an empty document")

        note = (
            "# Draft unavailable\n\n"
            "The AI provider returned an empty or unparseable response this round.\n\n"
            f"Reason: {last_err}\n\n"
            "Tip: if the draft was cut off, raise `max_output_tokens` in "
            "config.yaml; if the prompt was too big, lower `results_per_query` "
            "or `max_fetches`.\n"
        )
        return BuildResult(document=note, evidence_requests=[], cited_ids=[])

    @staticmethod
    def resolve_citations(document: str, evidence: list[EvidenceItem]) -> dict:
        """Return which cited ids exist/miss and map cited→paper for refs."""
        known = {e.ev_id for e in evidence}
        cited = set(re.findall(r"ev://[A-Za-z0-9_\-]+#c\d+", document))
        return {
            "cited": sorted(cited),
            "resolved": sorted(cited & known),
            "missing": sorted(cited - known),
        }


# ---------------------------------------------------------------------------
# prompt rendering
# ---------------------------------------------------------------------------

def _coerce(data) -> tuple[str, list[dict]]:
    """Normalise the model reply into (markdown_document, evidence_requests)."""
    if isinstance(data, dict):
        doc = data.get("document") or data.get("markdown") or ""
        reqs = data.get("evidence_requests") or []
        return str(doc), list(reqs)
    if isinstance(data, str):
        return data, []
    return str(data), []


def _render_evidence(evidence: list[EvidenceItem]) -> str:
    lines = []
    for e in evidence:
        lines.append(f"- {e.ev_id} | {e.summary} | EXCERPT: {e.excerpt}")
    return "\n".join(lines) if lines else "(no evidence available)"


def _render_viewpoints(viewpoints: list[dict]) -> str:
    if not viewpoints:
        return "(none provided)"
    return "\n".join(
        f"- {v.get('label','')}: {v.get('description','')}" for v in viewpoints
    )


def _render_user(
    *, brief: str, workplan: str, viewpoints: list[dict], evidence: list[EvidenceItem],
    previous_draft: str | None, critic_findings: list[dict] | None,
    retry_compact: bool = False,
) -> str:
    parts = [
        "## STUDY BRIEF\n" + brief.strip(),
        "\n## WORKPLAN (required document structure)\n" + workplan.strip(),
        "\n## EXPECTED VIEWPOINTS (hints, not exhaustive)\n" + _render_viewpoints(viewpoints),
        "\n## EVIDENCE (cite these by their ev:// id)\n" + _render_evidence(evidence),
    ]
    if previous_draft:
        parts.append("\n## PREVIOUS DRAFT (revise it)\n" + previous_draft.strip())
    if critic_findings:
        parts.append("\n## CRITIC FINDINGS (address these)\n" +
                     json.dumps(critic_findings, ensure_ascii=False, indent=2))
    parts.append(
        "\n## TASK\n"
        "Write the document exactly per the WORKPLAN. Cite evidence with ev:// ids. "
        "If you need information not present in EVIDENCE, do NOT invent it: add it to "
        "evidence_requests as {\"query\": \"...\", \"why\": \"...\"}. "
        "Respond ONLY with a single JSON object (no prose, no code fences) of the form "
        "{\"document\": \"<markdown>\", \"evidence_requests\": [...]}."
    )
    if retry_compact:
        parts.append(
            "\n## IMPORTANT\nYour previous reply was empty or not valid JSON. "
            "Keep the document CONCISE (under ~800 words), still valid JSON, and "
            "make sure the JSON is complete and properly closed."
        )
    return "\n".join(parts)


_SYSTEM = """You are the Builder agent in a bibliometric research system.

HARD RULES:
1. You do NOT browse the web and you have NO external knowledge you may use for
   facts. Use ONLY the EVIDENCE provided.
2. Every substantive claim MUST cite at least one ev:// id from the EVIDENCE.
3. If evidence is missing for something the WORKPLAN requires, emit an
   evidence_request instead of guessing.
4. Represent genuinely distinct academic viewpoints; attribute positions to
   sources; do not collapse them into a single narrative.
5. Output ONLY JSON: {"document": "<markdown>", "evidence_requests": [{"query","why"}]}
"""
