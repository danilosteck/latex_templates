"""HTTP API and static UI serving.

Local-first: bind 127.0.0.1, reject non-local Host headers (DNS-rebinding defence),
no CORS. The UI is a static bundle served from the package.
"""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from pydantic import ValidationError

from . import __version__, bibtex
from .agents import AGENT_IDS, AgentFile, estimate_tokens, render_variables, variables_from_brief
from .engine import JOBS
from .models import Brief, ProjectMeta, slugify
from .retrieval import diagnose as retrieval_diagnose
from .store import Project, Workspace

WEB_DIR = Path(__file__).parent / "web"


def create_app(workspace: Workspace | None = None) -> FastAPI:
    ws = workspace or Workspace()
    app = FastAPI(title="Bibliometric Studio", version=__version__, docs_url="/api/docs")

    # -- guards -------------------------------------------------------------

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        host = (request.headers.get("host") or "").split(":")[0]
        if host not in {"127.0.0.1", "localhost", "::1", "[::1]", "testserver"}:
            return JSONResponse({"detail": "forbidden host"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    # -- helpers ------------------------------------------------------------

    def get_project(slug: str) -> Project:
        try:
            return ws.project(slug)
        except KeyError:
            raise HTTPException(404, f"project not found: {slug}")

    # -- health / settings --------------------------------------------------

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "version": __version__,
            "workspace": str(ws.root),
            "secret_backend": ws.secrets.backend,
            "provider": ws.settings().get("provider"),
        }

    @app.get("/api/settings")
    def get_settings() -> dict[str, Any]:
        from .llm import MODEL_PRICES, PROVIDER_PRESETS

        return {
            "settings": ws.public_settings(),
            "providers": PROVIDER_PRESETS,
            "prices": MODEL_PRICES,
        }

    @app.put("/api/settings")
    def put_settings(patch: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return ws.save_settings(patch)

    @app.post("/api/settings/test")
    def test_settings() -> dict[str, Any]:
        from .llm import LLMError, client_from_settings

        settings = ws.settings()
        provider = settings.get("provider", "mock")
        if provider == "mock":
            return {"ok": True, "detail": "Offline demo mode: no key needed."}
        llm = client_from_settings(settings, ws.api_key())
        try:
            res = llm.complete("You are a connection test.", "Reply with the single word: ok",
                               max_tokens=8)
            return {"ok": True, "detail": f"{provider}/{llm.model} replied: {res.text.strip()[:40]}"}
        except LLMError as exc:
            return {"ok": False, "detail": str(exc)}

    @app.get("/api/providers/{provider}/models")
    def provider_models(provider: str) -> dict[str, Any]:
        """List models the provider actually offers.

        For Ollama this is the difference between 'it works' and guessing which
        model name the user has pulled locally.
        """
        import httpx

        from .llm import PROVIDER_PRESETS

        provider = provider.lower()
        preset = PROVIDER_PRESETS.get(provider)
        if preset is None:
            raise HTTPException(404, f"unknown provider: {provider}")
        settings = ws.settings()
        base = (settings.get("base_url") or preset["base_url"]).rstrip("/")
        if not base:
            return {"ok": False, "detail": "no base URL configured", "models": []}

        if provider == "ollama":
            # native endpoint is /api/tags; the OpenAI shim is mounted under /v1
            root = base.removesuffix("/v1")
            try:
                with httpx.Client(timeout=8) as client:
                    resp = client.get(f"{root}/api/tags")
                if resp.status_code != 200:
                    return {"ok": False, "models": [],
                            "detail": f"Ollama respondeu HTTP {resp.status_code} em {root}"}
                models = [m.get("name", "") for m in resp.json().get("models", [])]
                return {"ok": True, "models": models,
                        "detail": f"{len(models)} modelo(s) local(is)" if models
                        else "Ollama está rodando, mas nenhum modelo foi baixado "
                             "(ex.: `ollama pull llama3.1`)"}
            except Exception as exc:
                return {"ok": False, "models": [],
                        "detail": f"Ollama não respondeu em {root} ({type(exc).__name__}). "
                                  f"Inicie com `ollama serve` ou ajuste a URL base."}

        key = ws.api_key()
        if not key:
            return {"ok": False, "models": [], "detail": "no API key to list models"}
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get(f"{base}/models",
                                  headers={"Authorization": f"Bearer {key}"})
            if resp.status_code != 200:
                return {"ok": False, "models": [],
                        "detail": f"HTTP {resp.status_code}: {resp.text[:120]}"}
            models = [m.get("id", "") for m in resp.json().get("data", [])]
            return {"ok": True, "models": sorted(models)[:80],
                    "detail": f"{len(models)} models available"}
        except Exception as exc:
            return {"ok": False, "models": [],
                    "detail": f"could not reach {base}: {type(exc).__name__}"}

    # -- projects -----------------------------------------------------------

    @app.get("/api/projects")
    def list_projects() -> list[dict[str, Any]]:
        out = []
        for meta in ws.list_projects():
            try:
                project = ws.project(meta.slug)
                papers = len(project.papers())
                runs = project.runs()
                last = runs[0] if runs else None
            except Exception:
                papers, last = 0, None
            out.append({
                **meta.model_dump(),
                "sources": papers,
                "last_run": last.model_dump() if last else None,
            })
        return out

    @app.post("/api/projects")
    def create_project(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            brief = Brief.model_validate(payload.get("brief", payload))
        except ValidationError as exc:
            raise HTTPException(422, exc.errors())
        project = ws.create_project(brief)
        return {"slug": project.meta.slug, "project": project.meta.model_dump()}

    @app.get("/api/projects/{slug}")
    def project_detail(slug: str) -> dict[str, Any]:
        project = get_project(slug)
        brief = project.brief()
        papers = project.papers()
        return {
            "meta": project.meta.model_dump(),
            "brief": brief.model_dump(),
            "brief_md": (project.inputs / "brief.md").read_text("utf-8"),
            "workplan_md": (project.inputs / "workplan.md").read_text("utf-8"),
            "papers": [p.model_dump() for p in papers],
            "evidence_count": len(project.evidence()),
            "runs": [r.model_dump() for r in project.runs()[:10]],
        }

    @app.put("/api/projects/{slug}/brief")
    def update_brief(slug: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        project = get_project(slug)
        try:
            brief = Brief.model_validate(payload)
        except ValidationError as exc:
            raise HTTPException(422, exc.errors())
        project.save_brief(brief)
        return {"meta": project.meta.model_dump(), "brief": brief.model_dump()}

    @app.delete("/api/projects/{slug}")
    def delete_project(slug: str) -> dict[str, Any]:
        get_project(slug)
        ws.delete_project(slug)
        return {"deleted": slug}

    @app.post("/api/projects/{slug}/duplicate")
    def duplicate_project(slug: str, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        get_project(slug)
        new = ws.duplicate_project(slug, payload.get("title"))
        return {"slug": new.meta.slug}

    @app.get("/api/projects/{slug}/export.zip")
    def export_zip(slug: str) -> Response:
        get_project(slug)
        data = ws.export_zip(slug)
        return Response(content=data, media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{slug}.zip"'})

    @app.post("/api/projects/import")
    async def import_zip(file: UploadFile = File(...)) -> dict[str, Any]:
        data = await file.read()
        try:
            project = ws.import_zip(data)
        except Exception as exc:
            raise HTTPException(400, f"import failed: {exc}")
        return {"slug": project.meta.slug}

    # -- sources ------------------------------------------------------------

    @app.get("/api/projects/{slug}/papers")
    def list_papers(slug: str) -> list[dict[str, Any]]:
        project = get_project(slug)
        evidence = project.evidence()
        counts: dict[str, int] = {}
        for ev in evidence:
            counts[ev.paper_id] = counts.get(ev.paper_id, 0) + 1
        return [{**p.model_dump(), "evidence_count": counts.get(p.id, 0)}
                for p in project.papers()]

    @app.get("/api/projects/{slug}/papers/{paper_id}")
    def paper_detail(slug: str, paper_id: str) -> dict[str, Any]:
        project = get_project(slug)
        for paper in project.papers():
            if paper.id == paper_id:
                evs = [e.model_dump() for e in project.evidence() if e.paper_id == paper_id]
                return {"paper": paper.model_dump(), "evidence": evs}
        raise HTTPException(404, "paper not found")

    @app.post("/api/projects/{slug}/add-source")
    def add_source(slug: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        """Manually register a DOI/URL the user already knows about."""
        from . import retrieval
        from .models import Paper

        project = get_project(slug)
        doi = str(payload.get("doi") or "").strip().removeprefix("https://doi.org/").strip()
        title = str(payload.get("title") or "").strip()
        if not doi and not title:
            raise HTTPException(422, "provide a DOI or a title")
        existing = project.paper_by_doi(doi) if doi else None
        if existing:
            return {"id": existing.id, "existing": True}
        paper = Paper(
            id=project.next_paper_id(),
            title=title or doi,
            doi=doi or None,
            url=f"https://doi.org/{doi}" if doi else payload.get("url"),
            source="manual",
            source_type="peer_reviewed" if doi else "web",
            full_text="abstract_only",
            abstract=str(payload.get("abstract") or ""),
        )
        papers = project.papers()
        papers.append(paper)
        project.save_papers(papers)
        project.write_paper_record(paper)
        if paper.abstract:
            from .models import Evidence
            from .extract import summarize

            ev = Evidence(paper_id=paper.id, locator="abstract", text=paper.abstract,
                          summary=summarize(paper.abstract))
            evidence = project.evidence() + [ev]
            project.save_evidence(evidence)
            project.write_evidence_record(paper, [ev])
        return {"id": paper.id, "existing": False}

    # -- agents -------------------------------------------------------------

    @app.get("/api/agents/defaults")
    def agent_defaults() -> dict[str, Any]:
        from .store import DEFAULT_AGENTS

        return {aid: AgentFile.parse(aid, text).as_payload()
                for aid, text in DEFAULT_AGENTS.items()}

    @app.get("/api/projects/{slug}/agents/{agent_id}")
    def get_agent(slug: str, agent_id: str) -> dict[str, Any]:
        if agent_id not in AGENT_IDS:
            raise HTTPException(404, "unknown agent")
        project = get_project(slug)
        parsed = AgentFile.parse(agent_id, project.agent_text(agent_id))
        payload = parsed.as_payload()
        payload["revisions"] = sorted(
            p.name for p in (project.agents_dir / "revisions").glob(f"{agent_id}-*.md"))
        return payload

    @app.put("/api/projects/{slug}/agents/{agent_id}")
    def save_agent(slug: str, agent_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        if agent_id not in AGENT_IDS:
            raise HTTPException(404, "unknown agent")
        project = get_project(slug)
        if "raw" in payload and payload.get("mode") == "raw":
            text = str(payload["raw"])
        else:
            text = AgentFile.from_payload(agent_id, payload).to_text()
        project.save_agent(agent_id, text)
        return AgentFile.parse(agent_id, text).as_payload()

    @app.post("/api/projects/{slug}/agents/{agent_id}/reset")
    def reset_agent(slug: str, agent_id: str) -> dict[str, Any]:
        if agent_id not in AGENT_IDS:
            raise HTTPException(404, "unknown agent")
        project = get_project(slug)
        text = project.reset_agent(agent_id)
        return AgentFile.parse(agent_id, text).as_payload()

    @app.get("/api/projects/{slug}/agents/{agent_id}/preview")
    def preview_agent(slug: str, agent_id: str) -> dict[str, Any]:
        """The compiled system prompt plus a representative user block and sizes."""
        if agent_id not in AGENT_IDS:
            raise HTTPException(404, "unknown agent")
        project = get_project(slug)
        brief = project.brief()
        agent = AgentFile.parse(agent_id, project.agent_text(agent_id))
        system = render_variables(agent.system_prompt(), variables_from_brief(brief))
        papers = project.papers()
        evidence = project.evidence()[:6]
        from .engine import _evidence_block

        block, _ = _evidence_block(evidence, None) if agent_id == "author" else ("(not used)", [])
        sample_user = {
            "author": (
                f"STUDY: {brief.title}\nOBJECT: {brief.topic}\n"
                f"OUTPUT LANGUAGE: {brief.output_language}\n"
                f"SECTION: {brief.deliverable.sections[0] if brief.deliverable.sections else 'Section'}\n"
                f"WORD BUDGET: ~{max(120, brief.deliverable.length_words // max(1, len(brief.deliverable.sections)))} words\n\n"
                f"EVIDENCE (cite these IDs exactly as written):\n{block}"
            ),
            "critic": (
                f"WORKPLAN SECTIONS: {', '.join(brief.deliverable.sections)}\n"
                f"DRAFT:\n(assembled document)\n\nMECHANICAL CHECKS: citations 12/12 resolved"
            ),
            "researcher": (
                f"Study object: {brief.topic}\nQuestions: "
                f"{'; '.join(rq.question for rq in brief.rqs)}"
            ),
        }[agent_id]
        return {
            "system": system,
            "user_sample": sample_user,
            "system_tokens": estimate_tokens(system),
            "user_tokens": estimate_tokens(sample_user),
            "papers_available": len(papers),
        }

    # -- runs ---------------------------------------------------------------

    @app.get("/api/projects/{slug}/runs")
    def list_runs(slug: str) -> list[dict[str, Any]]:
        return [r.model_dump() for r in get_project(slug).runs()]

    @app.post("/api/projects/{slug}/runs")
    def start_run(slug: str) -> dict[str, Any]:
        project = get_project(slug)
        if not project.papers() and not project.brief().themes:
            raise HTTPException(422, "add at least one search theme before running")
        state = JOBS.start(project)
        return state.model_dump()

    @app.post("/api/projects/{slug}/diagnose")
    def diagnose_sources(slug: str) -> dict[str, Any]:
        """Probe every enabled source with the project's real queries and filters.

        Runs before (or instead of) a full run so 'no sources found' can be
        explained in the UI instead of after an LLM round.
        """
        from .engine import build_retrieval_context

        project = get_project(slug)
        brief = project.brief()
        ctx = build_retrieval_context(brief, ws)
        queries = brief.queries()
        sources = brief.sources_enabled or ["openalex", "crossref"]
        return retrieval_diagnose(queries, sources, ctx)

    @app.get("/api/projects/{slug}/runs/{run_id}/state")
    def run_state(slug: str, run_id: str) -> dict[str, Any]:
        project = get_project(slug)
        state = project.load_run_state(run_id)
        if state is None:
            raise HTTPException(404, "run not found")
        return state.model_dump()

    @app.get("/api/projects/{slug}/runs/{run_id}/events")
    def run_events(slug: str, run_id: str, offset: int = 0) -> dict[str, Any]:
        project = get_project(slug)
        path = project.run_dir(run_id) / "log.jsonl"
        events: list[dict[str, Any]] = []
        next_offset = offset
        if path.exists():
            with path.open("rb") as fh:
                fh.seek(offset)
                for raw in fh:
                    next_offset += len(raw)
                    if not raw.strip():
                        continue
                    try:
                        events.append(json.loads(raw))
                    except json.JSONDecodeError:
                        continue
        state = project.load_run_state(run_id)
        return {"events": events[-400:], "offset": next_offset,
                "state": state.model_dump() if state else None}

    @app.post("/api/projects/{slug}/runs/{run_id}/decide")
    def run_decide(slug: str, run_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        get_project(slug)
        ok = JOBS.decide(run_id, payload)
        if not ok:
            raise HTTPException(409, "run is not waiting at a checkpoint")
        return {"ok": True}

    @app.post("/api/projects/{slug}/runs/{run_id}/cancel")
    def run_cancel(slug: str, run_id: str) -> dict[str, Any]:
        get_project(slug)
        return {"ok": JOBS.cancel(run_id)}

    # -- artifacts ----------------------------------------------------------

    @app.get("/api/projects/{slug}/runs/{run_id}/report")
    def run_report(slug: str, run_id: str) -> dict[str, Any]:
        project = get_project(slug)
        path = project.run_dir(run_id) / "report.json"
        if not path.exists():
            raise HTTPException(404, "no report for this run")
        return json.loads(path.read_text("utf-8"))

    @app.get("/api/projects/{slug}/runs/{run_id}/artifact")
    def run_artifact(slug: str, run_id: str, name: str) -> PlainTextResponse:
        project = get_project(slug)
        path = project.artifact(run_id, name)
        if path is None:
            raise HTTPException(404, f"artifact not found: {name}")
        return PlainTextResponse(path.read_text("utf-8"))

    @app.get("/api/projects/{slug}/file")
    def project_file(slug: str, name: str) -> PlainTextResponse:
        project = get_project(slug)
        allowed = {"brief.md", "workplan.md", "papers.json", "evidence.json",
                   "references/library.bib", "references/bibliography.md",
                   "references/validation.md"}
        if name not in allowed:
            raise HTTPException(404, "file not exposed")
        path = (project.path / name).resolve()
        if project.path not in path.parents or not path.exists():
            raise HTTPException(404, "file not found")
        return PlainTextResponse(path.read_text("utf-8"))

    @app.get("/api/projects/{slug}/bibliography.bib")
    def bibliography(slug: str) -> Response:
        project = get_project(slug)
        text = bibtex.build(project.papers())
        return Response(text, media_type="text/plain; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{slug}.bib"'})

    # -- static UI ----------------------------------------------------------

    @app.get("/")
    def index() -> Response:
        path = WEB_DIR / "index.html"
        if not path.exists():
            return PlainTextResponse(
                "UI not built yet. Run `npm --prefix web-src run build` "
                "or use the API at /api/docs.", status_code=200)
        return FileResponse(path)

    @app.get("/{full_path:path}")
    def static_files(full_path: str) -> Response:
        if full_path.startswith("api/"):
            raise HTTPException(404, "not found")
        target = (WEB_DIR / full_path).resolve()
        if WEB_DIR.resolve() in target.parents and target.is_file():
            media, _ = mimetypes.guess_type(str(target))
            return FileResponse(target, media_type=media or "application/octet-stream")
        if (WEB_DIR / "index.html").exists():
            return FileResponse(WEB_DIR / "index.html")  # SPA fallback
        raise HTTPException(404, "not found")

    return app


app = create_app()
