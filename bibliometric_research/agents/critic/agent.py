"""Agent 3 — Critic.

Evaluates a Builder draft against the Study Brief, the Workplan and the evidence,
and returns **structured findings** (not a rewrite). It drives the iteration loop
and the human checkpoints.

Checks performed:
  * Section coverage vs Workplan.
  * Viewpoint diversity vs brief + seed viewpoints.
  * Unsupported claims (sentences with no ev:// citation).
  * Citation integrity (ev:// ids that are missing from evidence) — computed
    locally, not trusted to the LLM.
  * Misuse / imbalance (one viewpoint dominating, neglected axes).
  * Clarity and structure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.evidence import EvidenceItem
from core.llm import LLM


@dataclass
class CriticResult:
    findings: list[dict] = field(default_factory=list)
    overall: str = "minor"          # minor | major
    local_checks: dict = field(default_factory=dict)


class CriticAgent:
    def __init__(self, llm: LLM) -> None:
        self.llm = llm

    def run(
        self,
        brief: str,
        workplan: str,
        viewpoints: list[dict],
        evidence: list[EvidenceItem],
        document: str,
    ) -> CriticResult:
        # Deterministic checks first (free, no tokens).
        local = self._local_checks(document, evidence)

        user = _render_user(brief, workplan, viewpoints, evidence, document, local)
        try:
            data = self.llm.complete_json(_SYSTEM, user)
            findings = data.get("findings", []) if isinstance(data, dict) else []
            overall = data.get("overall", "minor") if isinstance(data, dict) else "minor"
        except Exception as e:
            findings = [{
                "severity": "info", "location": "n/a",
                "issue": f"critic model error: {type(e).__name__}",
                "suggestion": "inspect logs",
            }]
            overall = "minor"

        # Elevate to major if local checks found broken citations.
        if local.get("missing_ids"):
            overall = "major"
            findings.insert(0, {
                "severity": "major", "location": "citations",
                "issue": f"{len(local['missing_ids'])} cited ev:// ids are not in evidence.",
                "suggestion": "remove or re-retrieve the missing sources before finalizing.",
            })

        return CriticResult(findings=findings, overall=overall, local_checks=local)

    # -- deterministic checks ----------------------------------------------

    @staticmethod
    def _local_checks(document: str, evidence: list[EvidenceItem]) -> dict:
        known = {e.ev_id for e in evidence}
        cited = set(re.findall(r"ev://[A-Za-z0-9_\-]+#c\d+", document))
        missing = sorted(cited - known)

        # crude "unsupported claim" heuristic: paragraphs with no citation.
        paragraphs = [p for p in re.split(r"\n\s*\n", document) if p.strip()]
        uncited = [
            p[:80] for p in paragraphs
            if len(p.split()) > 25 and not re.search(r"ev://", p)
            and not p.lstrip().startswith("#")
        ]

        # section coverage heuristic: markdown headings vs workplan numbers.
        headings = re.findall(r"^#{1,3}\s+(.+)$", document, re.MULTILINE)

        return {
            "cited_count": len(cited),
            "missing_ids": missing,
            "uncited_paragraphs": uncited,
            "headings": headings,
        }


def _render_user(brief, workplan, viewpoints, evidence, document, local) -> str:
    ev = "\n".join(f"- {e.ev_id} | {e.summary}" for e in evidence[:80])
    vp = "\n".join(f"- {v.get('label','')}: {v.get('description','')}" for v in viewpoints)
    return (
        "## STUDY BRIEF\n" + brief.strip() +
        "\n## WORKPLAN\n" + workplan.strip() +
        "\n## EXPECTED VIEWPOINTS\n" + (vp or "(none)") +
        "\n## EVIDENCE INDEX\n" + (ev or "(none)") +
        "\n## AUTOMATED CHECKS (trust these)\n" +
        f"cited={local['cited_count']} missing={local['missing_ids']} "
        f"uncited_paragraphs={len(local['uncited_paragraphs'])} "
        f"headings={local['headings']}" +
        "\n## DRAFT TO REVIEW\n" + document.strip() +
        "\n\n## TASK\nReturn JSON: {\"findings\":[{\"severity\":\"major|minor|info\","
        "\"location\":\"...\",\"issue\":\"...\",\"suggestion\":\"...\"}],\"overall\":\"major|minor\"}"
    )


_SYSTEM = """You are the Critic agent in a bibliometric research system.
Evaluate the DRAFT against the BRIEF and WORKPLAN. Do not rewrite it; report
findings. Focus on: coverage of required sections, plurality/balance of
viewpoints, unsupported claims, citation misuse, clarity and structure.
Be specific and actionable. Output ONLY JSON:
{"findings": [{"severity":"major|minor|info","location":"...","issue":"...","suggestion":"..."}],
 "overall":"major|minor"}
"""
