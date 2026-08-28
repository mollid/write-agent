"""Work-mode chat sessions (spec §4.3): append-only history under
.meta/chat/{sid}.jsonl, one orchestrator decision per turn, actions dispatched
to the existing JobManager jobs (zero changes to jobs.py)."""
from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError

from novel.config import load_config
from novel.project import NovelProject
from novel.providers import ModelProvider
from novel.runtime import make_provider
from novel.skills import load_skills
from novel.store.bible import StoryBible
from novel.store.reviews import ReviewStore
from novel.ui import jobs
from novel.ui.jobs import Job, JobManager
from novel.workflow import build_plan

HISTORY_TAIL = 20
_WRITABLE_BIBLE_SECTIONS = ("concept", "world", "characters")
_REWRITE_MODES = ("polish", "rearrange")


class TurnResult(BaseModel):
    reply: str
    action: dict[str, object] | None = None
    job_id: str | None = None


class ChatSessionStore:
    """Append-only per-session jsonl under {project_root}/.meta/chat/."""

    def __init__(self, project_root: Path) -> None:
        self.dir = project_root / ".meta" / "chat"

    def create(self) -> str:
        self.dir.mkdir(parents=True, exist_ok=True)
        sid = uuid.uuid4().hex[:12]
        (self.dir / f"{sid}.jsonl").write_text("", encoding="utf-8")
        return sid

    def _path(self, sid: str) -> Path:
        if Path(sid).name != sid or sid in (".", ".."):
            raise ValueError(f"非法会话 id: {sid}")
        return self.dir / f"{sid}.jsonl"

    def append(self, session_id: str, entry: dict[str, object]) -> dict[str, object]:
        path = self._path(session_id)
        if not path.is_file():
            raise FileNotFoundError(f"会话不存在: {session_id}")
        seq = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
        full = {"seq": seq, "ts": datetime.now(UTC).isoformat(), **entry}
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(full, ensure_ascii=False) + "\n")
        return full

    def entries(self, session_id: str) -> list[dict[str, object]] | None:
        path = self._path(session_id)
        if not path.is_file():
            return None
        out: list[dict[str, object]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # torn tail line: degrade, same philosophy as summaries
        return out

    def list_sessions(self) -> list[dict[str, object]]:
        if not self.dir.is_dir():
            return []
        out: list[dict[str, object]] = []
        for f in sorted(self.dir.glob("*.jsonl")):
            first_user, count, created = "", 0, ""
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                count += 1
                created = created or str(e.get("ts", ""))
                if not first_user and e.get("type") == "user":
                    first_user = str(e.get("text", ""))
            out.append({"id": f.stem, "title": first_user[:24] or "(空会话)",
                        "created": created, "entries": count})
        return out


def _int_arg(args: dict[str, object], key: str, *, lo: int = 1, hi: int = 2000) -> int:
    v = args.get(key)
    if isinstance(v, bool) or not isinstance(v, int) or not (lo <= v <= hi):
        raise ValueError(f"参数 {key} 必须是 {lo}-{hi} 的整数")
    return v


def _str_arg(args: dict[str, object], key: str, *, min_len: int = 1) -> str:
    v = args.get(key)
    if not isinstance(v, str) or len(v.strip()) < min_len:
        raise ValueError(f"参数 {key} 必须是非空字符串(>= {min_len} 字符)")
    return v.strip()


def _dispatch(root: Path, action_type: str, args: dict[str, object],
              bible: StoryBible) -> tuple[str, Callable[[Job], object]]:
    """Validate one action and bind it to an existing jobs.py runner."""
    if action_type == "write_premise":
        return "premise", jobs.run_premise_job(root, _str_arg(args, "text", min_len=10))
    if action_type == "run_setup":
        concept = bible.get_concept()
        if concept is None or not concept.logline:
            raise ValueError("run_setup 需要先有故事概念(write_premise)")
        return "setup", jobs.run_setup_job(root, concept.logline)
    if action_type == "write_chapters":
        return "write-chapter", jobs.run_chapters_job(root, _int_arg(args, "n"))
    if action_type == "rewrite_chapter":
        mode = _str_arg(args, "mode")
        if mode not in _REWRITE_MODES:
            raise ValueError(f"rewrite mode 必须是 {_REWRITE_MODES}")
        return "chapter-rewrite", jobs.run_chapter_rewrite_job(
            root, _int_arg(args, "chapter"), mode, _str_arg(args, "instruction", min_len=2))
    if action_type == "edit_bible":
        section = _str_arg(args, "section")
        if section not in _WRITABLE_BIBLE_SECTIONS:
            raise ValueError(f"edit_bible section 必须是 {_WRITABLE_BIBLE_SECTIONS}")
        character_id = args.get("character_id")
        if character_id is not None and not isinstance(character_id, str):
            raise ValueError("character_id 必须是字符串")
        return "bible-chat", jobs.run_bible_chat_job(
            root, section, _str_arg(args, "instruction", min_len=2),
            character_id if isinstance(character_id, str) else None)
    if action_type == "extend_outline":
        return "outline-extend", jobs.run_outline_extend_job(root, _int_arg(args, "n"))
    if action_type == "run_tts":
        from novel.tts import DEFAULT_VOICE
        voice = args.get("voice")
        if voice is not None and not isinstance(voice, str):
            raise ValueError("voice 必须是字符串")
        return "tts", jobs.run_tts_job(
            root, _int_arg(args, "chapter"),
            voice if isinstance(voice, str) else DEFAULT_VOICE,
            "+0%", "+0%", "+0Hz")
    raise ValueError(f"未知动作类型: {action_type}")


def _watch_job_end(store: ChatSessionStore, session_id: str, job: Job) -> None:
    def _watch() -> None:
        job.thread.join()
        detail = f"({job.error})" if job.error else ""
        store.append(session_id, {"type": "system",
                                  "text": f"任务结束:{job.kind} -> {job.status} {detail}".rstrip()})
    threading.Thread(target=_watch, daemon=True).start()


def run_turn(root: Path, project: str, session_id: str, text: str,
             manager: JobManager, *, provider: ModelProvider | None = None) -> TurnResult:
    """Process one Work-mode turn (spec §5). Raises ValueError on invalid action
    args (API 422), FileNotFoundError on unknown session, ValidationError upward
    is converted to a system entry + RuntimeError."""
    store = ChatSessionStore(root)
    if store.entries(session_id) is None:
        raise FileNotFoundError(f"会话不存在: {session_id}")
    store.append(session_id, {"type": "user", "text": text})

    proj = NovelProject(root=root)
    cfg = load_config(proj.config_path)
    bible = StoryBible(proj)
    reviews = ReviewStore(proj)
    active = manager.active_job(project)
    plan = build_plan(proj, bible, reviews, cfg,
                      active_job_id=active.id if active is not None else None)

    from novel.agents.orchestrator import OrchestratorAgent, OrchestratorInput
    prov = provider if provider is not None else make_provider(cfg, skills=load_skills(root))
    history = [e for e in (store.entries(session_id) or [])
               if e.get("type") in ("user", "assistant")][-HISTORY_TAIL:]
    history_tail = [{"role": str(e["type"]), "text": str(e.get("text", ""))} for e in history]
    try:
        decision = OrchestratorAgent(prov, cfg.model_for("orchestrator")).run(
            OrchestratorInput(history_tail=history_tail, plan_json=plan.model_dump_json(),
                              user_message=text))
    except ValidationError as e:
        store.append(session_id, {"type": "system", "text": f"编排决策失败:{e}"})
        raise RuntimeError(f"orchestrator failed: {e}") from e
    store.append(session_id, {"type": "assistant", "text": decision.reply})

    job_id: str | None = None
    fired = decision.action.model_dump() if decision.action is not None else None
    if decision.action is not None and decision.action.type not in ("none", "wait_job"):
        if active is not None:
            store.append(session_id, {"type": "system",
                                      "text": f"已有任务在运行(job {active.id}),本次动作未启动。"})
        else:
            try:
                kind, fn = _dispatch(root, decision.action.type, decision.action.args, bible)
            except ValueError as e:
                store.append(session_id, {"type": "system", "text": f"动作未启动:{e}"})
                raise
            job = manager.start(project, kind, fn)
            job_id = job.id
            store.append(session_id, {"type": "action", "action": fired, "job_id": job_id})
            _watch_job_end(store, session_id, job)
    return TurnResult(reply=decision.reply, action=fired, job_id=job_id)
