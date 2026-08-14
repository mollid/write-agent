"""FastAPI application exposing the novel engine to a browser UI."""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from novel.ui import jobs

STATIC_DIR = Path(__file__).parent / "static"


class CreateProjectReq(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    genre: str = "fantasy"


class PremiseReq(BaseModel):
    text: str = Field(min_length=1)


class WriteReq(BaseModel):
    n: int = Field(default=1, ge=1, le=50)


class GateReq(BaseModel):
    approve: bool


def _safe_project(root: Path, name: str) -> Path:
    if Path(name).name != name or name in (".", ".."):
        raise HTTPException(status_code=400, detail="非法项目名")
    p = root / name
    if not (p / "bible").is_dir():
        raise HTTPException(status_code=404, detail=f"项目不存在: {name}")
    return p


def create_app(root: Path) -> FastAPI:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="novel GUI", docs_url=None, redoc_url=None)
    manager = jobs.JobManager()

    @app.get("/api/mode")
    def get_mode() -> dict[str, bool]:
        from novel.runtime import is_live_mode
        return {"live": is_live_mode()}

    @app.get("/api/projects")
    def list_projects() -> list[dict[str, str]]:
        out = []
        for p in sorted(root.iterdir()):
            if p.is_dir() and (p / "bible").is_dir():
                out.append({"name": p.name})
        return out

    @app.post("/api/projects", status_code=201)
    def create_project(req: CreateProjectReq) -> dict[str, str]:
        from novel.project import NovelProject
        if Path(req.name).name != req.name or req.name in (".", ".."):
            raise HTTPException(status_code=400, detail="非法项目名")
        if (root / req.name).exists():
            raise HTTPException(status_code=409, detail=f"目录已存在: {req.name}")
        proj = NovelProject.scaffold(req.name, genre=req.genre, root=root)
        return {"name": req.name, "root": str(proj.root)}

    @app.get("/api/projects/{name}/status")
    def project_status(name: str) -> dict[str, object]:
        p = _safe_project(root, name)
        from novel.config import load_config
        from novel.project import NovelProject
        from novel.store.bible import StoryBible
        proj = NovelProject(root=p)
        bible = StoryBible(proj)
        cfg = load_config(proj.config_path) if proj.config_path.is_file() else None
        chapters = sorted(int(f.stem) for f in (p / "chapters").glob("[0-9][0-9][0-9].md"))
        open_threads = sum(1 for f in bible.list_foreshadow()
                           if f.status.value == "open" or f.status.value == "planted")
        job = manager.active_job(name)
        return {
            "name": name,
            "has_concept": bible.get_concept() is not None,
            "has_world": bible.get_world() is not None,
            "has_outline": bible.get_outline() is not None,
            "chapters": chapters,
            "open_threads": open_threads,
            "score_min": cfg.thresholds.score_min if cfg else 80,
            "job": None if job is None else {
                "id": job.id, "kind": job.kind, "status": job.status, "error": job.error,
            },
        }

    @app.post("/api/projects/{name}/premise", status_code=202)
    def start_premise(name: str, req: PremiseReq) -> dict[str, str]:
        p = _safe_project(root, name)
        try:
            job = manager.start(name, "premise", jobs.run_premise_job(p, req.text))
        except RuntimeError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        return {"job_id": job.id}

    @app.post("/api/projects/{name}/write-chapter", status_code=202)
    def start_write(name: str, req: WriteReq) -> dict[str, str]:
        p = _safe_project(root, name)
        try:
            job = manager.start(name, "write-chapter", jobs.run_chapters_job(p, req.n))
        except RuntimeError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        return {"job_id": job.id}

    @app.get("/api/projects/{name}/chapters/{num}")
    def get_chapter(name: str, num: int) -> dict[str, object]:
        p = _safe_project(root, name)
        f = p / "chapters" / f"{num:03d}.md"
        if not f.is_file():
            raise HTTPException(status_code=404, detail=f"章节不存在: {num}")
        return {"chapter": num, "content": f.read_text(encoding="utf-8")}

    @app.get("/api/projects/{name}/threads")
    def get_threads(name: str) -> list[dict[str, str]]:
        p = _safe_project(root, name)
        from novel.project import NovelProject
        from novel.store.bible import StoryBible
        bible = StoryBible(NovelProject(root=p))
        return [{"id": f.id, "description": f.description, "status": f.status.value}
                for f in bible.list_foreshadow()]

    @app.get("/api/projects/{name}/reviews")
    def get_reviews(name: str) -> list[dict[str, object]]:
        p = _safe_project(root, name)
        from novel.project import NovelProject
        from novel.store.reviews import ReviewStore
        recs = ReviewStore(NovelProject(root=p)).list_all()
        return [
            {"chapter": r.chapter, "attempt": r.attempt, "artifact_type": r.artifact_type,
             "overall": r.overall, "summary": r.summary, "passed": r.passed,
             "timestamp": r.timestamp,
             "scores": {k: {"score": v.score, "critique": v.critique}
                        for k, v in r.scores.items()}}
            for r in recs
        ]

    @app.post("/api/projects/{name}/export")
    def do_export(name: str) -> dict[str, str]:
        p = _safe_project(root, name)
        from novel.export import export_markdown
        from novel.project import NovelProject
        out = export_markdown(NovelProject(root=p))
        return {"path": str(out)}

    @app.get("/api/projects/{name}/events")
    async def project_events(name: str, request: Request) -> StreamingResponse:
        _safe_project(root, name)
        q = manager.bus.subscribe(name)

        async def stream() -> AsyncIterator[str]:
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    for ev in jobs.drain(q, timeout=0.2):
                        yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0.1)
            finally:
                manager.bus.unsubscribe(name, q)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    @app.post("/api/gates/{gate_id}")
    def resolve_gate(gate_id: str, req: GateReq) -> dict[str, bool]:
        ok = manager.resolve_gate(gate_id, req.approve)
        if not ok:
            raise HTTPException(status_code=404, detail="审批请求不存在或已处理")
        return {"resolved": True}

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str) -> dict[str, bool]:
        ok = manager.cancel(job_id)
        if not ok:
            raise HTTPException(status_code=404, detail="任务不存在或已结束")
        return {"cancelled": True}

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str) -> dict[str, object]:
        job = manager.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        return {"id": job.id, "kind": job.kind, "status": job.status,
                "error": job.error, "project": job.project}

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app
