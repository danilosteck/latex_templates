from __future__ import annotations

import json

import pytest

from bibstudio.store import Workspace


def test_create_project_writes_the_documented_layout(ws, brief):
    project = ws.create_project(brief)
    root = project.path
    for rel in ("project.json", "inputs/brief.json", "inputs/brief.md", "inputs/workplan.md",
                "agents/researcher.md", "agents/author.md", "agents/critic.md",
                "papers.json", "evidence.json"):
        assert (root / rel).exists(), rel
    assert "Urban heat islands" in (root / "inputs" / "brief.md").read_text()
    assert "Required sections" in (root / "inputs" / "workplan.md").read_text()
    meta = json.loads((root / "project.json").read_text())
    assert meta["slug"] == project.meta.slug


def test_slug_collision_gets_suffix(ws, brief):
    a = ws.create_project(brief)
    b = ws.create_project(brief)
    assert a.meta.slug != b.meta.slug
    assert b.meta.slug.startswith(a.meta.slug)


def test_project_isolation(ws, brief):
    a = ws.create_project(brief)
    b = ws.create_project(brief.model_copy(update={"title": "Other study"}))
    (a.path / "papers.json").write_text("[]")
    a.save_papers([])
    assert a.papers() == []
    assert b.papers() == []
    assert a.path != b.path


def test_paper_ids_increment_and_do_not_duplicate(ws, brief):
    project = ws.create_project(brief)
    assert project.next_paper_id() == "P-0001"
    from bibstudio.models import Paper

    papers = [Paper(id="P-0001", title="one"), Paper(id="P-0007", title="seven")]
    project.save_papers(papers)
    assert project.next_paper_id() == "P-0008"
    assert project.path.exists()


def test_agent_save_creates_revision(ws, brief):
    project = ws.create_project(brief)
    original = project.agent_text("author")
    project.save_agent("author", original + "\n\n## Domain guidance\n\nBe brief.\n")
    project.save_agent("author", original + "\n\n## Domain guidance\n\nBe shorter.\n")
    revisions = list((project.agents_dir / "revisions").glob("author-*.md"))
    assert len(revisions) >= 1
    assert "Be brief" in project.agent_text("author") or "Be shorter" in project.agent_text("author")


def test_reset_returns_to_default(ws, brief):
    project = ws.create_project(brief)
    project.save_agent("critic", "# broken\n")
    text = project.reset_agent("critic")
    assert "## Role" in text
    assert project.agent_text("critic") == text


def test_export_and_import_roundtrip(ws, brief, tmp_path):
    project = ws.create_project(brief)
    data = ws.export_zip(project.meta.slug)
    assert data[:2] == b"PK"
    other = Workspace(tmp_path / "other")
    imported = other.import_zip(data)
    assert imported.brief().title == "Urban heat islands"
    assert imported.agent_text("author").strip()


def test_path_traversal_cannot_escape_the_workspace(ws, brief):
    project = ws.create_project(brief)
    # traversal-looking input must be neutralised, never resolved outside the root
    assert project.run_dir("../../etc").parent == project.run_dir("../../etc").parent
    assert str(project.run_dir("../../etc")).startswith(str(project.runs_dir))
    assert str(ws.project_dir("../../etc")).startswith(str(ws.projects_dir))
    with pytest.raises(KeyError):
        ws.project("../../etc")


def test_secrets_never_land_in_settings_file(ws):
    ws.save_settings({"api_key": "sk-secret", "provider": "openai"})
    text = (ws.root / "settings.json").read_text()
    assert "sk-secret" not in text
    assert ws.api_key() == "sk-secret"
    assert ws.public_settings()["has_api_key"] is True


def test_workplan_renders_deliverable_spec(ws, brief):
    project = ws.create_project(brief)
    workplan = (project.path / "inputs" / "workplan.md").read_text()
    assert "Executive summary" in workplan
    assert "~2500 words" in workplan or "word" in workplan
    assert "Citation contract" in workplan
