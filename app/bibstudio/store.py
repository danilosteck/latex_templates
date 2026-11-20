"""Workspace + project storage.

Everything is plain files. The app can be deleted without losing a project, and a
project folder can be zipped, emailed, opened in an editor, or pasted into any
chat tool.

Layout::

    <root>/
      settings.json            non-secret app settings
      .secrets.json            API keys (0600) — only if no OS keychain is available
      blobs/<sha256>           content-addressed store, shared by all projects
      projects/<slug>/
        project.json
        inputs/brief.json  inputs/brief.md  inputs/workplan.md
        agents/*.md  agents/revisions/
        papers.json  papers/P-0001.md
        evidence.json  evidence/P-0001.md
        runs/<run_id>/...
        references/library.bib bibliography.md validation.md
        exports/
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .models import (
    Brief,
    Evidence,
    Paper,
    ProjectMeta,
    RunState,
    slugify,
    utcnow,
)

DEFAULT_ROOT = Path.home() / "BibliometricStudio"
SECRET_ENV = "BIBSTUDIO_HOME"


def atomic_write(path: Path, text: str) -> None:
    """Write via a temp file + rename.

    The UI polls state files while the worker writes them; a half-written
    state.json must never be observable.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, "utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# settings + secrets
# ---------------------------------------------------------------------------


DEFAULT_SETTINGS: dict[str, Any] = {
    "provider": "mock",
    "model": "mock-1",
    "base_url": "",
    "temperature": 0.2,
    "max_output_tokens": 2000,
    "timeout_seconds": 180,
    "ui_language": "pt-BR",
    "workspace": "",
    "openalex_api_key": "",
    "contact_email": "",
    "default_cost_cap_usd": 2.0,
}


class Secrets:
    """OS keychain first, 0600 file as a documented fallback."""

    def __init__(self, root: Path) -> None:
        self.path = root / ".secrets.json"
        self._keyring = None
        try:  # optional dependency; absence is fine
            import keyring  # type: ignore

            self._keyring = keyring
        except Exception:
            self._keyring = None

    @property
    def backend(self) -> str:
        return "keychain" if self._keyring else "file (0600)"

    def get(self, name: str) -> str | None:
        env = os.environ.get(f"BIBSTUDIO_{name.upper()}")
        if env:
            return env
        if self._keyring:
            try:
                val = self._keyring.get_password("bibstudio", name)
                if val:
                    return val
            except Exception:
                pass
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text("utf-8"))
                return data.get(name)
            except (json.JSONDecodeError, OSError):
                return None
        return None

    def set(self, name: str, value: str | None) -> None:
        if self._keyring:
            try:
                if value:
                    self._keyring.set_password("bibstudio", name, value)
                else:
                    try:
                        self._keyring.delete_password("bibstudio", name)
                    except Exception:
                        pass
                return
            except Exception:
                pass
        data: dict[str, str] = {}
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text("utf-8"))
            except (json.JSONDecodeError, OSError):
                data = {}
        if value:
            data[name] = value
        else:
            data.pop(name, None)
        self.path.write_text(json.dumps(data, indent=2), "utf-8")
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# workspace
# ---------------------------------------------------------------------------


class Workspace:
    def __init__(self, root: str | Path | None = None) -> None:
        env_root = os.environ.get(SECRET_ENV)
        self.root = Path(root or env_root or DEFAULT_ROOT).expanduser().resolve()
        self.projects_dir = self.root / "projects"
        self.blobs_dir = self.root / "blobs"
        for d in (self.root, self.projects_dir, self.blobs_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.secrets = Secrets(self.root)
        self._settings = self._load_settings()

    # -- settings -----------------------------------------------------------

    @property
    def settings_path(self) -> Path:
        return self.root / "settings.json"

    def _load_settings(self) -> dict[str, Any]:
        data = dict(DEFAULT_SETTINGS)
        if self.settings_path.exists():
            try:
                data.update(json.loads(self.settings_path.read_text("utf-8")))
            except (json.JSONDecodeError, OSError):
                pass
        data["workspace"] = str(self.root)
        return data

    def settings(self) -> dict[str, Any]:
        return dict(self._settings)

    def public_settings(self) -> dict[str, Any]:
        """Settings safe to send to the UI (no secrets, but says whether one is set)."""
        s = self.settings()
        out = {k: v for k, v in s.items() if k not in {"openalex_api_key"}}
        out["has_api_key"] = bool(self.secrets.get("api_key"))
        out["secret_backend"] = self.secrets.backend
        out["openalex_key_set"] = bool(s.get("openalex_api_key") or self.secrets.get("openalex_api_key"))
        return out

    def save_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        allowed = set(DEFAULT_SETTINGS) - {"workspace"}
        for key, value in patch.items():
            if key in allowed:
                self._settings[key] = value
        if patch.get("api_key") is not None:
            self.secrets.set("api_key", str(patch["api_key"]) or None)
        if patch.get("openalex_api_key") is not None:
            self.secrets.set("openalex_api_key", str(patch["openalex_api_key"]) or None)
            self._settings["openalex_api_key"] = ""  # never keep it in settings.json
        self.settings_path.write_text(json.dumps(self._settings, indent=2), "utf-8")
        return self.public_settings()

    def api_key(self) -> str | None:
        return self.secrets.get("api_key")

    def openalex_key(self) -> str | None:
        return self._settings.get("openalex_api_key") or self.secrets.get("openalex_api_key")

    # -- blobs --------------------------------------------------------------

    def put_blob(self, data: bytes) -> str:
        import hashlib

        key = hashlib.sha256(data).hexdigest()
        path = self.blobs_dir / key
        if not path.exists():
            path.write_bytes(data)
        return key

    def get_blob(self, key: str) -> bytes | None:
        path = self.blobs_dir / key
        return path.read_bytes() if path.exists() else None

    # -- projects -----------------------------------------------------------

    def project_dir(self, slug: str) -> Path:
        safe = slugify(slug)
        path = (self.projects_dir / safe).resolve()
        if self.projects_dir.resolve() not in path.parents:
            raise ValueError("invalid project slug")
        return path

    def project(self, slug: str) -> "Project":
        path = self.project_dir(slug)
        if not (path / "project.json").exists():
            raise KeyError(f"project not found: {slug}")
        return Project(path, self)

    def list_projects(self) -> list[ProjectMeta]:
        out: list[ProjectMeta] = []
        for meta_path in sorted(self.projects_dir.glob("*/project.json")):
            try:
                out.append(ProjectMeta.model_validate_json(meta_path.read_text("utf-8")))
            except Exception:
                continue
        return sorted(out, key=lambda m: m.updated_at, reverse=True)

    def create_project(self, brief: Brief) -> "Project":
        base = slugify(brief.title or brief.topic)
        slug, n = base, 2
        while self.project_dir(slug).exists():
            slug = f"{base}-{n}"
            n += 1
        path = self.project_dir(slug)
        for sub in ("inputs", "agents/revisions", "papers", "evidence", "runs",
                    "references", "exports"):
            (path / sub).mkdir(parents=True, exist_ok=True)
        project = Project(path, self)
        project.meta = ProjectMeta(slug=slug, title=brief.title or brief.topic[:80])
        project.save_meta()
        project.save_brief(brief)
        project.write_default_agents()
        project.save_papers([])
        project.save_evidence([])
        return project

    def delete_project(self, slug: str) -> None:
        path = self.project_dir(slug)
        if path.exists():
            shutil.rmtree(path)

    def duplicate_project(self, slug: str, new_title: str | None = None) -> "Project":
        src = self.project(slug)
        brief = src.brief()
        if new_title:
            brief = brief.model_copy(update={"title": new_title})
        dst = self.create_project(brief)
        # copy the research inputs and the agents, but not runs/evidence (fresh study)
        for name in ("brief.json",):
            shutil.copy2(src.inputs / name, dst.inputs / name)
        for agent in ("researcher", "author", "critic"):
            f = src.agents_dir / f"{agent}.md"
            if f.exists():
                shutil.copy2(f, dst.agents_dir / f.name)
        dst.save_brief(src.brief())
        return dst

    def export_zip(self, slug: str) -> bytes:
        """Zip a project. Never includes secrets (they live outside projects)."""
        project = self.project(slug)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(project.path.rglob("*")):
                if path.is_file() and "exports" not in path.parts:
                    zf.write(path, path.relative_to(project.path.parent))
        return buf.getvalue()

    def import_zip(self, data: bytes) -> "Project":
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = zf.namelist()
                if not any(n.endswith("project.json") for n in names):
                    raise ValueError("not a Bibliometric Studio project archive")
                zf.extractall(tmp)
            # tolerate a single nested directory
            candidates = list(Path(tmp).glob("*/project.json"))
            if not candidates:
                raise ValueError("project.json not found in archive")
            src_dir = candidates[0].parent
            meta = ProjectMeta.model_validate_json((src_dir / "project.json").read_text("utf-8"))
            slug, n = slugify(meta.slug or meta.title), 2
            while self.project_dir(slug).exists():
                slug = f"{slugify(meta.slug or meta.title)}-{n}"
                n += 1
            dst = self.project_dir(slug)
            shutil.copytree(src_dir, dst)
            project = Project(dst, self)
            project.meta = project.meta.model_copy(update={"slug": slug, "updated_at": utcnow()})
            project.save_meta()
            return project


# ---------------------------------------------------------------------------
# project
# ---------------------------------------------------------------------------


class Project:
    def __init__(self, path: Path, workspace: Workspace) -> None:
        self.path = path
        self.workspace = workspace
        self.inputs = path / "inputs"
        self.agents_dir = path / "agents"
        self.papers_dir = path / "papers"
        self.evidence_dir = path / "evidence"
        self.runs_dir = path / "runs"
        self.references_dir = path / "references"
        self.exports_dir = path / "exports"
        for d in (self.inputs, self.agents_dir, self.papers_dir, self.evidence_dir,
                  self.runs_dir, self.references_dir, self.exports_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.meta = self._load_meta()

    # -- meta ---------------------------------------------------------------

    @property
    def meta_path(self) -> Path:
        return self.path / "project.json"

    def _load_meta(self) -> ProjectMeta:
        if self.meta_path.exists():
            return ProjectMeta.model_validate_json(self.meta_path.read_text("utf-8"))
        return ProjectMeta(slug=self.path.name, title=self.path.name)

    def save_meta(self) -> None:
        self.meta.updated_at = utcnow()
        atomic_write(self.meta_path, self.meta.model_dump_json(indent=2))

    # -- brief --------------------------------------------------------------

    @property
    def brief_path(self) -> Path:
        return self.inputs / "brief.json"

    def brief(self) -> Brief:
        if not self.brief_path.exists():
            raise KeyError("project has no brief")
        return Brief.model_validate_json(self.brief_path.read_text("utf-8"))

    def save_brief(self, brief: Brief) -> None:
        atomic_write(self.brief_path, brief.model_dump_json(indent=2))
        atomic_write(self.inputs / "brief.md", render_brief_md(brief))
        atomic_write(self.inputs / "workplan.md", render_workplan_md(brief))
        self.meta.title = brief.title or self.meta.title
        self.save_meta()

    # -- agents -------------------------------------------------------------

    def agent_path(self, agent_id: str) -> Path:
        if agent_id not in ("researcher", "author", "critic"):
            raise ValueError("unknown agent")
        return self.agents_dir / f"{agent_id}.md"

    def agent_text(self, agent_id: str) -> str:
        path = self.agent_path(agent_id)
        if path.exists():
            return path.read_text("utf-8")
        return DEFAULT_AGENTS[agent_id]

    def save_agent(self, agent_id: str, text: str) -> None:
        path = self.agent_path(agent_id)
        if path.exists():
            n = len(list((self.agents_dir / "revisions").glob(f"{agent_id}-*.md"))) + 1
            shutil.copy2(path, self.agents_dir / "revisions" / f"{agent_id}-{n:04d}.md")
        path.write_text(text, "utf-8")

    def reset_agent(self, agent_id: str) -> str:
        path = self.agent_path(agent_id)
        text = DEFAULT_AGENTS[agent_id]
        self.save_agent(agent_id, text)
        return text

    def write_default_agents(self) -> None:
        for agent_id, text in DEFAULT_AGENTS.items():
            path = self.agent_path(agent_id)
            if not path.exists():
                path.write_text(text, "utf-8")

    # -- papers / evidence --------------------------------------------------

    @property
    def papers_path(self) -> Path:
        return self.path / "papers.json"

    @property
    def evidence_path(self) -> Path:
        return self.path / "evidence.json"

    def papers(self) -> list[Paper]:
        if not self.papers_path.exists():
            return []
        raw = json.loads(self.papers_path.read_text("utf-8"))
        return [Paper.model_validate(p) for p in raw]

    def save_papers(self, papers: list[Paper]) -> None:
        atomic_write(self.papers_path, json.dumps(
            [p.model_dump() for p in papers], indent=2, ensure_ascii=False))

    def evidence(self) -> list[Evidence]:
        if not self.evidence_path.exists():
            return []
        raw = json.loads(self.evidence_path.read_text("utf-8"))
        return [Evidence.model_validate(e) for e in raw]

    def save_evidence(self, evidence: list[Evidence]) -> None:
        atomic_write(self.evidence_path, json.dumps(
            [e.model_dump() for e in evidence], indent=2, ensure_ascii=False))

    def next_paper_id(self) -> str:
        nums = [int(m.group(1)) for p in self.papers()
                if (m := re.match(r"P-(\d+)$", p.id))]
        return f"P-{(max(nums) + 1) if nums else 1:04d}"

    def paper_by_doi(self, doi: str | None) -> Paper | None:
        if not doi:
            return None
        doi = doi.lower()
        for p in self.papers():
            if p.doi and p.doi.lower() == doi:
                return p
        return None

    def write_paper_record(self, paper: Paper) -> None:
        """Human-readable record next to the machine-readable papers.json."""
        lines = [
            f"# {paper.id} — {paper.title}",
            "",
            f"- **Authors:** {', '.join(paper.authors) or 'n/a'}",
            f"- **Year:** {paper.year or 'n/a'}",
            f"- **Venue:** {paper.venue or 'n/a'}",
            f"- **DOI:** {paper.doi or 'n/a'}",
            f"- **URL:** {paper.url or 'n/a'}",
            f"- **Found via:** {paper.source}",
            f"- **Type:** {paper.source_type}",
            f"- **Full text:** {paper.full_text}",
            f"- **Verified:** {paper.verified}",
            "",
            "## Abstract",
            "",
            paper.abstract.strip() or "(none cached)",
            "",
        ]
        (self.papers_dir / f"{paper.id}.md").write_text("\n".join(lines), "utf-8")

    def write_evidence_record(self, paper: Paper, items: list[Evidence]) -> None:
        lines = [f"# Evidence — {paper.id}", "", f"Source: {paper.title}", ""]
        for ev in items:
            lines += [f"## {ev.locator}", "", ev.text.strip(), ""]
        (self.evidence_dir / f"{paper.id}.md").write_text("\n".join(lines), "utf-8")

    # -- runs ---------------------------------------------------------------

    def run_dir(self, run_id: str) -> Path:
        safe = re.sub(r"[^0-9A-Za-z_.-]", "", run_id)
        path = (self.runs_dir / safe).resolve()
        if self.runs_dir.resolve() not in path.parents:
            raise ValueError("invalid run id")
        return path

    def new_run_id(self) -> str:
        base = utcnow().replace(":", "").replace("-", "").replace("+0000", "Z")
        run_id, n = base, 2
        while self.run_dir(run_id).exists():
            run_id = f"{base}-{n}"
            n += 1
        return run_id

    def save_run_state(self, state: RunState) -> None:
        d = self.run_dir(state.run_id)
        d.mkdir(parents=True, exist_ok=True)
        atomic_write(d / "state.json", state.model_dump_json(indent=2))

    def load_run_state(self, run_id: str) -> RunState | None:
        path = self.run_dir(run_id) / "state.json"
        if not path.exists():
            return None
        try:
            return RunState.model_validate_json(path.read_text("utf-8"))
        except Exception:
            return None

    def runs(self) -> list[RunState]:
        out: list[RunState] = []
        for path in sorted(self.runs_dir.glob("*/state.json"), reverse=True):
            try:
                out.append(RunState.model_validate_json(path.read_text("utf-8")))
            except Exception:
                continue
        return out

    def artifact(self, run_id: str, name: str) -> Path | None:
        path = (self.run_dir(run_id) / name).resolve()
        if self.run_dir(run_id) not in path.parents:
            return None
        return path if path.exists() else None


# ---------------------------------------------------------------------------
# markdown rendering (the human/no-app view of the canonical JSON)
# ---------------------------------------------------------------------------


def _bullets(values: Iterable[str], empty: str = "(none)") -> str:
    vals = [v for v in values if str(v).strip()]
    return "\n".join(f"- {v}" for v in vals) if vals else empty


def render_brief_md(brief: Brief) -> str:
    langs = ", ".join(brief.lit_languages) or "en"
    lines = [
        f"# Brief — {brief.title}",
        "",
        "> Rendered from `inputs/brief.json`. Edit in the app; edits here can be",
        "> re-imported but the JSON is the source of truth.",
        "",
        "## 1. Study object",
        "",
        f"- **Topic / object of study:** {brief.topic}",
        f"- **Discipline(s):** {', '.join(brief.disciplines) or '(unspecified)'}",
        f"- **Time frame:** {brief.year_from or 'any'}–{brief.year_to or 'present'}",
        f"- **Geographic scope:** {brief.geography or 'global'}",
        f"- **Literature languages:** {langs}",
        f"- **Output language:** {brief.output_language}",
        "",
        "## 2. Research questions",
        "",
    ]
    if brief.rqs:
        for i, rq in enumerate(brief.rqs, 1):
            lines.append(f"{i}. **RQ{i}:** {rq.question}")
            if rq.why:
                lines.append(f"   - Why it matters: {rq.why}")
    else:
        lines.append("(none)")
    lines += ["", "## 3. Search themes & seed keywords", "",
              "| Theme | Core keywords (EN) | Other languages / synonyms | Target sources |",
              "|---|---|---|---|"]
    for t in brief.themes:
        lines.append(
            f"| {t.name} | {', '.join(t.keywords_en) or '—'} | "
            f"{', '.join(t.keywords_other) or '—'} | {', '.join(t.sources) or 'default'} |")
    if not brief.themes:
        lines.append("| (none) | — | — | default |")
    lines += ["", "## 4. Viewpoints to map", ""]
    if brief.viewpoints:
        for v in brief.viewpoints:
            extra = f" — proponents: {', '.join(v.proponents)}" if v.proponents else ""
            lines.append(f"- **{v.label}:** {v.description}{extra}")
    else:
        lines.append("(none — the critic's balance check will be limited)")
    lines += ["", "## 5. Inclusion / exclusion criteria", "",
              f"- Peer-reviewed only: {'yes' if brief.include_peer_reviewed else 'no'}",
              f"- Grey literature: {'yes' if brief.include_grey else 'no'}",
              f"- Year range: {brief.year_from or 'any'}–{brief.year_to or 'present'}",
              f"- Minimum distinct sources: {brief.min_sources}",
              f"- Exclude terms: {', '.join(brief.exclude_terms) or '(none)'}",
              ""]
    return "\n".join(lines)


def render_workplan_md(brief: Brief) -> str:
    d = brief.deliverable
    lines = [
        f"# Workplan — {brief.title}",
        "",
        "> Rendered from `inputs/brief.json`. This is the specification the Author",
        "> agent builds the document around.",
        "",
        "## Required sections",
        "",
    ]
    lines += [f"- [ ] {s}" for s in d.sections] or ["- [ ] (none)"]
    lines += [
        "",
        "## Document specification",
        "",
        f"- **Template:** {d.template}",
        f"- **Length target:** ~{d.length_words} words",
        f"- **Tone / audience:** {d.tone}",
        f"- **Citation style:** {d.citation_style} (`[P-0007]` / `[P-0007 p.3]`)",
        f"- **BibTeX output:** {'yes' if d.bibtex else 'no'}",
        f"- **Max revision rounds:** {d.max_rounds}",
        f"- **Cost cap:** US$ {d.cost_cap_usd:.2f}",
        "",
        "## Citation contract",
        "",
        "Every factual sentence must carry a citation of the form `[P-0001]` or",
        "`[P-0001 p.3]`. A sentence without a citation must be framing, not a claim.",
        "The app verifies citations mechanically and reports unresolved ones.",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# default agents (kept in the package, copied into each project)
# ---------------------------------------------------------------------------


def _load_default_agents() -> dict[str, str]:
    base = Path(__file__).parent / "defaults" / "agents"
    out: dict[str, str] = {}
    for agent_id in ("researcher", "author", "critic"):
        path = base / f"{agent_id}.md"
        out[agent_id] = path.read_text("utf-8") if path.exists() else f"# {agent_id}\n"
    return out


DEFAULT_AGENTS = _load_default_agents()
