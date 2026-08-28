"""FastAPI application exposing the novel engine to a browser UI."""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from novel.ui import jobs

STATIC_DIR = Path(__file__).parent / "static"
DIST_DIR = Path(__file__).resolve().parents[2] / "ui-v2" / "dist"


class CreateProjectReq(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    genre: str = "fantasy"
    target_chapters: int | None = Field(default=None, ge=1, le=5000)


class PremiseReq(BaseModel):
    text: str = Field(min_length=1)


class WriteReq(BaseModel):
    n: int = Field(default=1, ge=1, le=2000)


class GateReq(BaseModel):
    approve: bool
    feedback: str = ""


class SetupReq(BaseModel):
    premise: str = ""


class BibleChatReq(BaseModel):
    section: str
    instruction: str = Field(min_length=1)
    character_id: str | None = None


class ExtendReq(BaseModel):
    n: int = Field(default=3, ge=1, le=50)


class ChapterRewriteReq(BaseModel):
    chapter: int = Field(ge=1)
    mode: str = "polish"
    instruction: str = Field(min_length=1)


class TtsReq(BaseModel):
    chapter: int = Field(ge=1)
    voice: str
    rate: str = "+0%"
    volume: str = "+0%"
    pitch: str = "+0Hz"


class ChapterSaveReq(BaseModel):
    content: str = Field(min_length=1)


class ChatSendReq(BaseModel):
    text: str = Field(min_length=1)


class ProjectConfigUpdateReq(BaseModel):
    """Exposed generation settings. null target_chapters clears the key
    (back to the one-shot outline); model credentials are never editable here."""
    target_chapters: int | None = Field(default=None, ge=1, le=5000)


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
        proj = NovelProject.scaffold(req.name, genre=req.genre, root=root,
                                     target_chapters=req.target_chapters)
        return {"name": req.name, "root": str(proj.root)}

    @app.get("/api/projects/{name}/config")
    def get_project_config(name: str) -> dict[str, object]:
        """Secret-free subset of project.config.yaml (models/api_key never leave)."""
        p = _safe_project(root, name)
        from novel.config import load_config
        from novel.project import NovelProject
        cfg = load_config(NovelProject(root=p).config_path)
        return {
            "target_chapters": cfg.generation.target_chapters,
            "arc_detail_lookahead": cfg.generation.arc_detail_lookahead,
            "chapter_target_length": cfg.generation.chapter_target_length,
            "context_token_budget": cfg.generation.context_token_budget,
            "human_gate_every_n_chapters": cfg.generation.human_gate_every_n_chapters,
            "score_min": cfg.thresholds.score_min,
            "max_retries": cfg.thresholds.max_retries,
            "language": cfg.language,
        }

    @app.put("/api/projects/{name}/config")
    def update_project_config(name: str, req: ProjectConfigUpdateReq) -> dict[str, object]:
        """Surgical update of the exposed settings in project.config.yaml; the
        models section (including api keys) round-trips untouched."""
        p = _safe_project(root, name)
        import yaml

        from novel.project import NovelProject
        cfg_path = NovelProject(root=p).config_path
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        gen = raw.setdefault("generation", {})
        if req.target_chapters is None:
            gen.pop("target_chapters", None)
        else:
            gen["target_chapters"] = req.target_chapters
        cfg_path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
                            encoding="utf-8")
        return {"ok": True, "target_chapters": req.target_chapters}

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

    @app.post("/api/projects/{name}/setup", status_code=202)
    def start_setup(name: str, req: SetupReq) -> dict[str, str]:
        p = _safe_project(root, name)
        if not req.premise:
            from novel.project import NovelProject
            from novel.store.bible import StoryBible
            if StoryBible(NovelProject(root=p)).get_concept() is None:
                raise HTTPException(status_code=422, detail="缺少创意：请提供 premise 或先运行 premise/setup")
        try:
            job = manager.start(name, "setup", jobs.run_setup_job(p, req.premise))
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

    @app.put("/api/projects/{name}/chapters/{num}")
    def save_chapter(name: str, num: int, req: ChapterSaveReq) -> dict[str, object]:
        """Manual chapter edit: same apply semantics as an approved rewrite —
        old prose backed up, file replaced atomically, vector memory upserted."""
        p = _safe_project(root, name)
        if not (p / "chapters" / f"{num:03d}.md").is_file():
            raise HTTPException(status_code=404, detail=f"章节不存在: {num}")
        if manager.active_job(name) is not None:
            raise HTTPException(status_code=409, detail="该项目有任务运行中，稍后再试")
        from novel.config import load_config
        from novel.project import NovelProject
        proj = NovelProject(root=p)
        cfg = load_config(proj.config_path) if proj.config_path.is_file() else None
        min_chars = cfg.generation.min_chapter_chars if cfg else 50
        if len(req.content.strip()) < min_chars:
            raise HTTPException(
                status_code=422,
                detail=f"正文过短：去空白后至少 {min_chars} 字（防止误存空稿破坏续跑判定）")
        backup = jobs.apply_chapter_text(p, num, req.content)
        return {"ok": True, "backup": backup}

    @app.get("/api/projects/{name}/threads")
    def get_threads(name: str) -> list[dict[str, str]]:
        p = _safe_project(root, name)
        from novel.project import NovelProject
        from novel.store.bible import StoryBible
        bible = StoryBible(NovelProject(root=p))
        return [{"id": f.id, "description": f.description, "status": f.status.value}
                for f in bible.list_foreshadow()]

    @app.get("/api/projects/{name}/outline")
    def get_outline(name: str) -> dict[str, object]:
        p = _safe_project(root, name)
        from novel.models import Outline
        from novel.project import NovelProject
        from novel.store.bible import StoryBible
        outline: Outline | None = StoryBible(NovelProject(root=p)).get_outline()
        if outline is None:
            return {"arcs": []}
        return {"arcs": [
            {"arc_name": a.arc_name,
             "chapters": [{"chapter_no": c.chapter_no, "chapter_title": c.chapter_title}
                          for c in a.chapters]}
            for a in outline.arcs]}

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

    @app.get("/api/projects/{name}/bible")
    def get_bible(name: str) -> dict[str, object]:
        p = _safe_project(root, name)
        from novel.project import NovelProject
        from novel.store.bible import StoryBible
        from novel.ui.jobs import read_bible_section

        def dump(sec: str) -> object:
            art = read_bible_section(StoryBible(NovelProject(root=p)), sec)
            if art is None:
                return None
            if isinstance(art, list):
                return [o.model_dump() for o in art]
            assert isinstance(art, BaseModel)
            return art.model_dump()

        return {sec: dump(sec) for sec in
                ("concept", "world", "characters", "outline", "foreshadows", "events")}

    @app.put("/api/projects/{name}/bible/{section}")
    def put_bible_section(name: str, section: str, body: object = Body(None)) -> dict[str, bool]:
        p = _safe_project(root, name)
        from novel.project import NovelProject
        from novel.store.bible import StoryBible
        from novel.ui.jobs import save_bible_section, validate_bible_section
        if section not in ("concept", "world", "characters", "outline", "foreshadows"):
            raise HTTPException(status_code=400, detail=f"未知设定段: {section}")
        if manager.active_job(name) is not None:
            raise HTTPException(status_code=409, detail="该项目有任务运行中，稍后再试")
        try:
            artifact = validate_bible_section(section, body)
        except AssertionError as e:
            raise HTTPException(status_code=422, detail=f"结构错误: {e}") from e
        except Exception as e:  # pydantic ValidationError
            raise HTTPException(status_code=422, detail=str(e)) from e
        save_bible_section(StoryBible(NovelProject(root=p)), section, artifact)
        return {"ok": True}

    @app.post("/api/projects/{name}/bible/chat", status_code=202)
    def start_bible_chat(name: str, req: BibleChatReq) -> dict[str, str]:
        p = _safe_project(root, name)
        if req.section == "foreshadows":
            raise HTTPException(status_code=422, detail="伏笔暂不支持对话改写，请使用编辑 JSON")
        if req.section not in ("concept", "world", "characters"):
            raise HTTPException(status_code=422, detail=f"该设定段不支持对话改写: {req.section}")
        instruction = req.instruction.strip()
        if not instruction:
            raise HTTPException(status_code=422, detail="指令不能为空")
        from novel.project import NovelProject
        from novel.store.bible import StoryBible
        bible = StoryBible(NovelProject(root=p))
        if req.section == "characters":
            cid = (req.character_id or "").strip()
            if not cid:
                raise HTTPException(status_code=422, detail="请先选择人物")
            if bible.get_character(cid) is None:
                raise HTTPException(status_code=422, detail=f"人物不存在: {cid}")
        else:
            try:
                art = bible.get_concept() if req.section == "concept" else bible.get_world()
            except KeyError:
                art = None
            if art is None:
                raise HTTPException(status_code=422, detail="该设定尚未生成，无法对话改写")
        try:
            job = manager.start(name, "bible-chat",
                                jobs.run_bible_chat_job(p, req.section, instruction,
                                                        req.character_id))
        except RuntimeError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        return {"job_id": job.id}

    @app.post("/api/projects/{name}/outline/extend", status_code=202)
    def start_outline_extend(name: str, req: ExtendReq) -> dict[str, str]:
        p = _safe_project(root, name)
        from novel.project import NovelProject
        from novel.store.bible import StoryBible
        if StoryBible(NovelProject(root=p)).get_outline() is None:
            raise HTTPException(status_code=422, detail="尚无大纲，无法追章")
        try:
            job = manager.start(name, "bible-extend", jobs.run_outline_extend_job(p, req.n))
        except RuntimeError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        return {"job_id": job.id}

    @app.post("/api/projects/{name}/chapter-rewrite", status_code=202)
    def start_chapter_rewrite(name: str, req: ChapterRewriteReq) -> dict[str, str]:
        p = _safe_project(root, name)
        if req.mode not in ("polish", "rearrange"):
            raise HTTPException(status_code=422, detail=f"未知改写模式: {req.mode}")
        if not (p / "chapters" / f"{req.chapter:03d}.md").is_file():
            raise HTTPException(status_code=404, detail=f"章节不存在: {req.chapter}")
        try:
            job = manager.start(name, "chapter-rewrite",
                                jobs.run_chapter_rewrite_job(p, req.chapter, req.mode,
                                                             req.instruction))
        except RuntimeError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        return {"job_id": job.id}

    @app.post("/api/projects/{name}/tts", status_code=202)
    def start_tts(name: str, req: TtsReq) -> dict[str, str]:
        p = _safe_project(root, name)
        from novel.tts import validate_tts_params
        try:
            validate_tts_params(req.voice, req.rate, req.volume, req.pitch)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        if not (p / "chapters" / f"{req.chapter:03d}.md").is_file():
            raise HTTPException(status_code=404, detail=f"章节不存在: {req.chapter}")
        try:
            job = manager.start(name, "tts", jobs.run_tts_job(
                p, req.chapter, req.voice, req.rate, req.volume, req.pitch))
        except RuntimeError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        return {"job_id": job.id}

    @app.get("/api/projects/{name}/audio")
    def list_audio(name: str) -> list[dict[str, int]]:
        p = _safe_project(root, name)
        audio_dir = p / "audio"
        if not audio_dir.is_dir():
            return []
        out = []
        for f in sorted(audio_dir.glob("*.mp3")):
            if f.stem.isdigit():
                out.append({"chapter": int(f.stem), "size": f.stat().st_size})
        return out

    @app.get("/api/projects/{name}/audio/{num}")
    def get_audio(name: str, num: int) -> FileResponse:
        p = _safe_project(root, name)
        f = p / "audio" / f"{num:03d}.mp3"
        if not f.is_file():
            raise HTTPException(status_code=404, detail=f"音频不存在: {num}")
        return FileResponse(f, media_type="audio/mpeg", filename=f.name)

    @app.post("/api/projects/{name}/export")
    def do_export(name: str) -> dict[str, str]:
        p = _safe_project(root, name)
        from novel.export import export_markdown
        from novel.project import NovelProject
        out = export_markdown(NovelProject(root=p))
        return {"path": str(out)}

    @app.post("/api/projects/{name}/chat/sessions", status_code=201)
    def create_chat_session(name: str) -> dict[str, str]:
        p = _safe_project(root, name)
        from novel.ui.chat import ChatSessionStore
        return {"session_id": ChatSessionStore(p).create()}

    @app.get("/api/projects/{name}/chat/sessions")
    def list_chat_sessions(name: str) -> list[dict[str, object]]:
        p = _safe_project(root, name)
        from novel.ui.chat import ChatSessionStore
        return ChatSessionStore(p).list_sessions()

    @app.get("/api/projects/{name}/chat/sessions/{sid}")
    def get_chat_session(name: str, sid: str) -> dict[str, object]:
        p = _safe_project(root, name)
        from novel.ui.chat import ChatSessionStore
        try:
            entries = ChatSessionStore(p).entries(sid)
        except ValueError as e:  # malformed sid ("..", etc.) -> 422, not 500
            raise HTTPException(status_code=422, detail=str(e)) from e
        if entries is None:
            raise HTTPException(status_code=404, detail=f"会话不存在: {sid}")
        return {"session_id": sid, "entries": entries}

    @app.post("/api/projects/{name}/chat/sessions/{sid}/messages")
    def send_chat_message(name: str, sid: str, req: ChatSendReq) -> dict[str, object]:
        p = _safe_project(root, name)
        from novel.ui import chat
        try:
            return chat.run_turn(p, name, sid, req.text, manager).model_dump()
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        except RuntimeError as e:  # orchestrator decision failed
            raise HTTPException(status_code=502, detail=str(e)) from e

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
        ok = manager.resolve_gate(gate_id, req.approve, (req.feedback or "").strip() or None)
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
                "error": job.error, "project": job.project,
                "gates": [{"id": g.id, "label": g.label, "artifact": g.artifact}
                          for g in job.gates.values() if not g.done.is_set()]}

    app.mount("/legacy", StaticFiles(directory=STATIC_DIR, html=True), name="legacy")
    if DIST_DIR.is_dir():
        app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="ui-v2")

        @app.exception_handler(StarletteHTTPException)
        async def spa_fallback(request: Request, exc: StarletteHTTPException) -> Response:
            """Serve the SPA shell for deep links like /p/x/overview.

            StaticFiles(html=True) 404s on unknown paths because no such file
            exists; the SPA router handles those client-side instead.
            """
            path = request.url.path
            if (
                exc.status_code == 404
                and not path.startswith("/api")
                and not path.startswith("/legacy")
            ):
                return FileResponse(DIST_DIR / "index.html")
            return JSONResponse(
                {"detail": exc.detail},
                status_code=exc.status_code,
                headers=getattr(exc, "headers", None),
            )

    else:
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static-fallback")
    return app
