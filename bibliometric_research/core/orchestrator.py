"""Orchestrator — routes work between the three agents.

Flow
----
1. Load config + study files (brief, workplan, viewpoints).
2. CHECKPOINT: confirm brief & sources with the human.
3. Retriever: produce evidence (cached, academic-first).
4. CHECKPOINT: review evidence & registry.
5. Builder: draft from evidence only.
6. CHECKPOINT: review draft.
7. Critic: structured findings.
8. CHECKPOINT: decide to iterate. If yes, feed findings back and loop (5–7),
   within ``max_rounds`` and ``token_budget``.
9. Write outputs: document, review, viewpoint map, transcript.

The orchestrator is intentionally thin: it owns sequencing, budgets and
checkpoints; all domain logic lives in the agents.

Usage
-----
    python -m core.orchestrator --study study/
    python -m core.orchestrator --study study/ --config config.yaml
    python -m core.orchestrator --study study/ --no-checkpoints   # unattended
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from agents.builder.agent import BuilderAgent
from agents.critic.agent import CriticAgent
from agents.retriever.agent import RetrieverAgent
from core.cache import Cache
from core.evidence import load_evidence, save_evidence

from core.llm import LLMError, build_llm, load_env_file
from core.registry import Registry


# ---------------------------------------------------------------------------
# config loading (YAML if available, else a tiny fallback parser)
# ---------------------------------------------------------------------------

def load_config(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        default = Path("config.example.yaml")
        if default.exists():
            print(f"! {p} not found; falling back to {default}")
            p = default
        else:
            return _minimal_config()
    text = p.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text) or _minimal_config()
    except ImportError:
        return _parse_simple_yaml(text)


def _minimal_config() -> dict:
    return {
        "provider": "mock",
        "models": {"mock": "mock-1"},
        "max_output_tokens": 1500,
        "retrieval": {
            "sources": ["scielo", "scopus", "web_of_science", "sciencedirect",
                        "google_scholar", "crossref", "openalex", "web"],
            "max_fetches": 40, "results_per_query": 10,
            "max_excerpt_words": 80, "chunk_words": 350,
        },
        "orchestration": {
            "max_rounds": 3, "token_budget": 200000,
            "checkpoints": {"enabled": False},
        },
        "cache": {"dir": "cache", "ttl_days": 0},
    }


def _parse_simple_yaml(text: str) -> dict:
    """Very small YAML subset parser (maps + block lists of scalars).

    Good enough for the shipped config shape. If you need more, install PyYAML.
    Handles nested maps by indentation, `key:` followed by `- item` lists, and
    inline `[a, b]` lists. Trailing `# comment` on a value is stripped.
    """
    root: dict[str, Any] = {}
    # stack entries: (indent, container, parent, parent_key). parent/parent_key
    # let us promote an empty-dict placeholder to a list on the first `- item`.
    stack: list[tuple[int, Any, Any, str | None]] = [(-1, root, None, None)]
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        line = raw.rstrip()
        indent = len(line) - len(line.lstrip())
        while stack and indent <= stack[-1][0]:
            stack.pop()
        _, parent, _, _ = stack[-1]
        stripped = line.strip()
        if stripped.startswith("- "):
            item = _scalar(stripped[2:])
            if isinstance(parent, list):
                parent.append(item)
            elif isinstance(parent, dict):
                _, _, gp, gp_key = stack[-1]
                if gp_key is not None and isinstance(gp, dict) and gp.get(gp_key) == {}:
                    gp[gp_key] = [item]
                    stack[-1] = (stack[-1][0], gp[gp_key], gp, gp_key)
            continue
        if ":" in stripped:
            key, _, val = stripped.partition(":")
            key, val = key.strip(), val.strip()
            if "#" in val:
                val = val.split("#", 1)[0].strip()
            if val == "":
                child: dict[str, Any] = {}
                parent[key] = child
                stack.append((indent, child, parent, key))
            else:
                parent[key] = _scalar(val)
    return root


def _scalar(v: str) -> Any:
    v = v.strip()
    if "#" in v and not (v.startswith('"') or v.startswith("'")):
        v = v.split("#", 1)[0].strip()
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    if v.startswith("[") and v.endswith("]"):
        return [_strip_quotes(x.strip()) for x in v[1:-1].split(",") if x.strip()]
    try:
        return int(v)
    except ValueError:
        return _strip_quotes(v)


def _strip_quotes(v: str) -> str:
    return v.strip().strip('"').strip("'")


# ---------------------------------------------------------------------------
# checkpoint helper
# ---------------------------------------------------------------------------

class Checkpoint:
    def __init__(self, enabled: bool, output_dir: Path) -> None:
        self.enabled = enabled
        self.output_dir = output_dir

    def ask(self, key: str, summary: str, artifact: dict | None = None) -> bool:
        """Pause for the human. Returns True to continue, False to stop.

        Also writes the checkpoint state to ``output/checkpoint_<key>.json`` so
        it can be inspected/edited. In non-interactive environments it defaults
        to 'continue' to avoid hanging.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / f"checkpoint_{key}.json").write_text(
            json.dumps({"summary": summary, "artifact": artifact or {}},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        print("\n" + "=" * 70)
        print(f"CHECKPOINT: {key}")
        print(summary)
        print(f"(state saved to output/checkpoint_{key}.json)")
        print("=" * 70)
        if not self.enabled:
            print("-> checkpoints disabled; continuing.")
            return True
        if not sys.stdin.isatty():
            print("-> non-interactive; continuing.")
            return True
        try:
            ans = input("Continue? [Y/n] ").strip().lower()
        except EOFError:
            return True
        return ans in ("", "y", "yes")


# ---------------------------------------------------------------------------
# main orchestration
# ---------------------------------------------------------------------------

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _load_viewpoints(path: Path) -> list[dict]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(text) or {}
        return data.get("viewpoints", []) if isinstance(data, dict) else []
    except ImportError:
        # minimal: 'label:' lines
        out = []
        label = None
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("- label:"):
                label = s.split(":", 1)[1].strip().strip('"')
                out.append({"label": label, "description": ""})
        return out


def run(study_dir: Path, config: dict, no_checkpoints: bool) -> int:
    output = Path("output")
    output.mkdir(exist_ok=True)

    # -- study inputs -------------------------------------------------------
    brief = _read(study_dir / "brief.md")
    workplan = _read(study_dir / "workplan.md")
    viewpoints = _load_viewpoints(study_dir / "viewpoints.yaml")
    if not brief.strip():
        print("! study/brief.md is empty — fill it in first."); return 2
    if not workplan.strip():
        print("! study/workplan.md is empty — fill it in first."); return 2

    # -- engine -------------------------------------------------------------
    cache = Cache(config.get("cache", {}).get("dir", "cache"),
                  int(config.get("cache", {}).get("ttl_days", 0)))
    registry = Registry("registry/papers.jsonl")
    llm = build_llm(config)

    rcfg = config.get("retrieval", {})
    ocfg = config.get("orchestration", {})
    ckcfg = ocfg.get("checkpoints", {})
    checkpoints = Checkpoint(
        enabled=(ckcfg.get("enabled", True) and not no_checkpoints), output_dir=output)

    retriever = RetrieverAgent(
        llm, cache, registry,
        source_priority=rcfg.get("sources", _minimal_config()["retrieval"]["sources"]),
        max_fetches=int(rcfg.get("max_fetches", 40)),
        results_per_query=int(rcfg.get("results_per_query", 10)),
        max_excerpt_words=int(rcfg.get("max_excerpt_words", 80)),
        chunk_words=int(rcfg.get("chunk_words", 350)),
    )
    builder = BuilderAgent(llm, max_excerpt_words=int(rcfg.get("max_excerpt_words", 80)))
    critic = CriticAgent(llm)

    max_rounds = int(ocfg.get("max_rounds", 3))
    token_budget = int(ocfg.get("token_budget", 200000))

    transcript: list[dict] = []

    # -- 1. brief checkpoint ------------------------------------------------
    if not checkpoints.ask("brief", f"Study: {brief.strip()[:200]}\n"
                                    f"Sources: {rcfg.get('sources')}"):
        print("Stopped at brief checkpoint."); return 0

    # -- 2. retrieval -------------------------------------------------------
    print("\n[Retriever] searching academic sources ...")
    ret = retriever.run(brief)
    evidence = ret.evidence
    save_evidence(Path("registry/evidence.jsonl"), evidence)
    # Reload full evidence from disk so re-runs accumulate.
    all_evidence = load_evidence(Path("registry/evidence.jsonl"))
    print(f"[Retriever] {len(evidence)} new evidence items, "
          f"{ret.papers_added} papers, {ret.fetches} fetches.")
    for w in ret.warnings:
        print(f"  ! {w}")
    transcript.append({"stage": "retrieval", "evidence_new": len(evidence),
                       "papers": ret.papers_added, "fetches": ret.fetches,
                       "warnings": ret.warnings})

    if not checkpoints.ask("evidence",
                           f"{len(all_evidence)} evidence items, "
                           f"{len(registry.all())} papers registered.\n"
                           f"Registry: registry/papers.jsonl (review/edit before continuing)",
                           {"evidence_count": len(all_evidence)}):
        print("Stopped at evidence checkpoint."); return 0

    # -- 3. build/critic loop ----------------------------------------------
    draft: str | None = None
    findings: list[dict] | None = None
    final_review: dict = {}
    for round_no in range(1, max_rounds + 1):
        if llm.tokens_used > token_budget:
            print(f"[budget] ~{llm.tokens_used} tokens > budget {token_budget}; stopping.")
            break

        print(f"\n[Builder] round {round_no} ...")
        bres = builder.run(brief, workplan, viewpoints, all_evidence,
                           previous_draft=draft, critic_findings=findings)

        # Handle evidence requests: route to retriever, then re-invoke once.
        if bres.evidence_requests:
            print(f"[Builder] requested {len(bres.evidence_requests)} more sources.")
            req_queries = [r.get("query", "") for r in bres.evidence_requests if r.get("query")]
            if req_queries:
                ret2 = retriever.run(brief, queries=req_queries)
                if ret2.evidence:
                    save_evidence(Path("registry/evidence.jsonl"), ret2.evidence)
                    all_evidence = load_evidence(Path("registry/evidence.jsonl"))
                    # re-run builder with the new evidence
                    bres = builder.run(brief, workplan, viewpoints, all_evidence,
                                       previous_draft=None, critic_findings=None)

        draft = bres.document
        doc_path = output / f"document_v{round_no}.md"
        doc_path.write_text(draft, encoding="utf-8")
        (output / f"document_v{round_no}.json").write_text(
            json.dumps({"document": draft, "cited_ids": bres.cited_ids},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[Builder] wrote {doc_path} ({len(draft.split())} words, "
              f"{len(bres.cited_ids)} citations).")

        # Verify citations locally (never trust the model for this).
        cites = builder.resolve_citations(draft, all_evidence)
        if cites["missing"]:
            print(f"[Builder] WARNING: {len(cites['missing'])} cited ids not in evidence.")

        if not checkpoints.ask(f"draft_{round_no}",
                               f"Draft v{round_no}: {len(draft.split())} words, "
                               f"{len(bres.cited_ids)} citations, "
                               f"{len(cites['missing'])} missing.",
                               {"missing": cites["missing"]}):
            print("Stopped at draft checkpoint."); break

        print(f"\n[Critic] reviewing round {round_no} ...")
        cres = critic.run(brief, workplan, viewpoints, all_evidence, draft)
        findings = cres.findings
        final_review = {"round": round_no, "overall": cres.overall,
                        "findings": findings, "local": cres.local_checks}
        (output / f"review_v{round_no}.json").write_text(
            json.dumps(final_review, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[Critic] overall={cres.overall}, {len(findings)} findings.")
        transcript.append({"stage": f"round_{round_no}", "overall": cres.overall,
                           "findings": len(findings),
                           "tokens_used": llm.tokens_used})

        if cres.overall == "minor" and not checkpoints.enabled:
            print("[loop] minor findings -> stopping.")
            break
        if not checkpoints.ask(f"critic_{round_no}",
                               f"Critic overall={cres.overall}. "
                               f"See output/review_v{round_no}.json.",
                               final_review):
            print("Stopped at critic checkpoint."); break

    # -- 4. final outputs ---------------------------------------------------
    if draft:
        _export_viewpoint_map(draft, all_evidence, output / "viewpoint_map.md")
        (output / "document_final.md").write_text(draft, encoding="utf-8")
        (output / "review_final.json").write_text(
            json.dumps(final_review, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "transcript.json").write_text(
        json.dumps({"provider": llm.provider, "calls": llm.calls,
                    "tokens_used": llm.tokens_used, "steps": transcript},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    print("\nDone.")
    print(f"  provider={llm.provider}  calls={llm.calls}  ~tokens={llm.tokens_used}")
    print(f"  papers in registry: {len(registry.all())}")
    print(f"  cache: {cache.stats()}")
    print("  outputs: output/document_final.md, output/review_final.json, output/viewpoint_map.md")
    print("\nNext: validate sources ->  python -m core.registry validate registry/papers.jsonl")
    return 0


def _export_viewpoint_map(document: str, evidence, path: Path) -> None:
    """Write a compact map of viewpoint → cited evidence ids from the document.

    Heuristic: take the 'Map of viewpoints' section and list cited ids per
    sub-heading. This is a convenience export, not authoritative.
    """
    import re
    lines = document.splitlines()
    out: list[str] = ["# Viewpoint Map (auto-exported)\n"]
    in_map = False
    current = "General"
    buckets: dict[str, list[str]] = {}
    for line in lines:
        if re.match(r"^#{1,3}\s+.*viewpoint", line, re.IGNORECASE):
            in_map = True
            continue
        if in_map and re.match(r"^#{1,2}\s+", line):
            # a top-level heading after the map section ends it
            if not re.match(r"^#{3,}", line):
                in_map = False
                continue
        if in_map:
            m = re.match(r"^#{3,}\s+(.+)$", line)
            if m:
                current = m.group(1).strip()
                buckets.setdefault(current, [])
            for ev in re.findall(r"ev://[A-Za-z0-9_\-]+#c\d+", line):
                buckets.setdefault(current, []).append(ev)
    if not buckets:
        ev_ids = sorted(set(re.findall(r"ev://[A-Za-z0-9_\-]+#c\d+", document)))
        buckets["All cited evidence"] = ev_ids
    known = {e.ev_id: e for e in evidence}
    for vp, ids in buckets.items():
        out.append(f"\n## {vp}")
        for ev in sorted(set(ids)):
            summary = known[ev].summary if ev in known else "(not in evidence!)"
            out.append(f"- {ev} — {summary}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Multi-agent bibliometric research orchestrator")
    ap.add_argument("--study", default="study/", help="path to the study folder")
    ap.add_argument("--config", default="config.yaml", help="path to config.yaml")
    ap.add_argument("--no-checkpoints", action="store_true", help="run unattended")
    args = ap.parse_args(argv)

    # Load API keys from a local .env file (if present) before reading config.
    n = load_env_file(".env")
    if n:
        print(f"[setup] loaded {n} value(s) from .env")

    config = load_config(args.config)
    try:
        return run(Path(args.study), config, args.no_checkpoints)
    except LLMError as e:
        _print_provider_help(str(e), config.get("provider", "mock"))
        return 3


def _print_provider_help(message: str, provider: str) -> None:
    """Print a friendly, non-technical explanation for provider/setup errors."""
    print("\n" + "=" * 70)
    print("SETUP PROBLEM — the program could not reach the AI provider.")
    print("=" * 70)
    print(f"Details: {message}\n")
    print(f"Current provider in config.yaml: {provider!r}\n")
    print("Common fixes:")
    print("  1. Missing API key  -> open your .env file and add the key, e.g.")
    print(f"       {provider.upper()}_API_KEY=your-key-here")
    print("     (copy env.example to .env first if you haven't:  cp env.example .env)")
    print("  2. Missing library  -> install the provider package, e.g.")
    print(f"       pip install -r requirements.txt")
    print("  3. Just exploring?  -> set 'provider: mock' in config.yaml to run")
    print("     the free offline demo (no key needed).")
    print("=" * 70)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
