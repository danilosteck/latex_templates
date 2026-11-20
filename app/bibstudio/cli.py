"""Command line entry point.

    bibstudio serve [--workspace PATH] [--port 8765] [--no-browser]
    bibstudio run --project SLUG [--workspace PATH] [--no-checkpoints]
    bibstudio doctor
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

from . import __version__


def _free_port(preferred: int = 8765) -> int:
    for port in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return sock.getsockname()[1]
            except OSError:
                continue
    return preferred


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .api import create_app
    from .store import Workspace

    workspace = Workspace(args.workspace)
    port = args.port or _free_port()
    url = f"http://127.0.0.1:{port}/"
    print(f"Bibliometric Studio {__version__}")
    print(f"  workspace: {workspace.root}")
    print(f"  secrets:   {workspace.secrets.backend}")
    print(f"  serving:   {url}")
    print("  press Ctrl+C to stop")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    if args.reload:
        # the reloader needs an import string; the workspace comes from the env
        os.environ["BIBSTUDIO_HOME"] = str(workspace.root)
        uvicorn.run("bibstudio.api:app", host="127.0.0.1", port=port,
                    log_level=args.log_level, reload=True)
    else:
        app = create_app(workspace)
        uvicorn.run(app, host="127.0.0.1", port=port, log_level=args.log_level)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    import httpx

    from .store import Workspace

    workspace = Workspace(args.workspace)
    settings = workspace.settings()
    checks: list[tuple[str, bool, str]] = []

    checks.append(("workspace writable", _writable(workspace.root), str(workspace.root)))
    checks.append(("secrets backend", True, workspace.secrets.backend))
    provider = settings.get("provider", "mock")
    checks.append(("provider", provider == "mock" or bool(workspace.api_key()),
                   f"{provider}"
                   + ("" if provider == "mock" or workspace.api_key() else " (no key set)")))
    try:
        import pypdf  # noqa: F401
        checks.append(("pdf extraction", True, "pypdf installed"))
    except ImportError:
        checks.append(("pdf extraction", False, "pypdf missing — PDFs will be abstract-only"))
    for name, url in (("network: crossref", "https://api.crossref.org/works?rows=1"),
                      ("network: openalex", "https://api.openalex.org/works?per-page=1")):
        try:
            with httpx.Client(timeout=15, headers={"User-Agent": "bibstudio-doctor/0.1"}) as c:
                resp = c.get(url)
            checks.append((name, resp.status_code == 200, f"HTTP {resp.status_code}"))
        except Exception as exc:
            checks.append((name, False, type(exc).__name__))
    ui = Path(__file__).parent / "web" / "index.html"
    checks.append(("UI bundle", ui.exists(), "present" if ui.exists() else "missing (API only)"))

    width = max(len(c[0]) for c in checks)
    for name, ok, detail in checks:
        print(f"  {'OK ' if ok else '!! '} {name.ljust(width)}  {detail}")
    return 0 if all(c[1] for c in checks) else 1


def _writable(path: Path) -> bool:
    try:
        probe = path / ".write-test"
        probe.write_text("ok")
        probe.unlink()
        return True
    except OSError:
        return False


def cmd_run(args: argparse.Namespace) -> int:
    from .engine import JobManager
    from .store import Workspace

    workspace = Workspace(args.workspace)
    project = workspace.project(args.project)
    brief = project.brief()
    if args.no_checkpoints:
        brief.checkpoints.candidates = False
        brief.checkpoints.outline = False
        brief.checkpoints.review = False
        project.save_brief(brief)

    manager = JobManager()
    state = manager.start(project)
    print(f"run {state.run_id} started; tail: {project.run_dir(state.run_id) / 'log.jsonl'}")
    events_path = project.run_dir(state.run_id) / "log.jsonl"
    offset = 0
    while True:
        time.sleep(0.5)
        if events_path.exists():
            with events_path.open("rb") as fh:
                fh.seek(offset)
                for raw in fh:
                    offset += len(raw)
                    try:
                        ev = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    print(f"[{ev['phase']:>10}] {ev['kind']:<18} {ev['message'][:110]}")
        current = project.load_run_state(state.run_id)
        if current and current.status in {"done", "failed", "cancelled"}:
            print(f"\nstatus={current.status} cost=${current.cost_usd:.4f} "
                  f"tokens={current.tokens_in}+{current.tokens_out}")
            if current.error:
                print(f"error: {current.error}")
            return 0 if current.status == "done" else 1
        if current and current.checkpoint:
            print(f"\nCHECKPOINT {current.checkpoint.kind}: {current.checkpoint.summary}")
            try:
                answer = input("approve? [Y/n] ").strip().lower()
            except EOFError:
                answer = "y"
            manager.decide(state.run_id, {"action": "stop" if answer == "n" else "continue"})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bibstudio",
                                     description="Bibliometric Studio")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="start the local app")
    serve.add_argument("--workspace", default=None)
    serve.add_argument("--port", type=int, default=0)
    serve.add_argument("--no-browser", action="store_true")
    serve.add_argument("--reload", action="store_true", help="restart on code changes (dev)")
    serve.add_argument("--log-level", default="warning")
    serve.set_defaults(func=cmd_serve)

    run = sub.add_parser("run", help="run a project from the terminal")
    run.add_argument("--project", required=True)
    run.add_argument("--workspace", default=None)
    run.add_argument("--no-checkpoints", action="store_true")
    run.set_defaults(func=cmd_run)

    doctor = sub.add_parser("doctor", help="self-test the installation")
    doctor.add_argument("--workspace", default=None)
    doctor.set_defaults(func=cmd_doctor)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
