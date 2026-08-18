"""Background job management: run the synchronous pipeline in threads, bridge
human gates to the GUI, and broadcast progress events per project."""
from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, Queue

from pydantic import BaseModel

from novel.models import Character, Concept, Foreshadow, Outline, World
from novel.render import artifact_text
from novel.store.bible import StoryBible


class JobCancelled(Exception):
    """Raised inside a job thread when cancellation was requested."""


@dataclass
class Gate:
    id: str
    label: str
    artifact: str
    done: threading.Event = field(default_factory=threading.Event)
    approved: bool = False
    feedback: str | None = None


class Job:
    """One background run (premise or chapter pipeline) for a project."""

    def __init__(self, project: str, kind: str, fn: Callable[[Job], object]) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.project = project
        self.kind = kind  # "premise" | "write-chapter" | custom label
        self.status = "running"  # running | done | error | cancelled
        self.error: str | None = None
        self.cancel = threading.Event()
        self.gates: dict[str, Gate] = {}
        self._bus: EventBus | None = None
        self._fn = fn
        self.thread = threading.Thread(target=self._run, daemon=True)

    # -- used by the job function ------------------------------------
    def emit(self, event: dict[str, object]) -> None:
        """Publish a progress event; raises JobCancelled if the job was cancelled."""
        if self.cancel.is_set():
            raise JobCancelled
        if self._bus is not None:
            self._bus.publish(self.project, {"job_id": self.id, **event})

    def gate(self, label: str, artifact: object) -> bool:
        """Block until the GUI resolves this approval request (or the job is cancelled)."""
        return self.gate_with_feedback(label, artifact)[0]

    def gate_with_feedback(self, label: str, artifact: object) -> tuple[bool, str | None]:
        """Block until resolved; returns (approved, feedback_text). feedback is set only
        when the resolver supplied one (guided-setup regeneration requests)."""
        g = Gate(id=uuid.uuid4().hex[:12], label=label, artifact=artifact_text(artifact))
        self.gates[g.id] = g
        if self._bus is not None:
            self._bus.publish(self.project, {
                "type": "gate", "job_id": self.id, "gate_id": g.id,
                "label": label, "artifact": g.artifact,
            })
        while not g.done.wait(timeout=0.25):
            if self.cancel.is_set():
                return False, None
        return g.approved, g.feedback

    # -- lifecycle ----------------------------------------------------
    def start(self, bus: EventBus) -> None:
        self._bus = bus
        self.thread.start()

    def _run(self) -> None:
        try:
            self._fn(self)
            self.status = "cancelled" if self.cancel.is_set() else "done"
        except JobCancelled:
            self.status = "cancelled"
        except Exception as e:  # noqa: BLE001 - surfaced to the UI
            self.error = f"{type(e).__name__}: {e}"
            self.status = "error"
        finally:
            if self._bus is not None:
                self._bus.publish(self.project, {
                    "type": "job_end", "job_id": self.id, "status": self.status,
                    "error": self.error, "kind": self.kind,
                })


class EventBus:
    """Fan-out of per-project events to SSE subscriber queues."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subs: dict[str, set[Queue[dict[str, object]]]] = {}

    def subscribe(self, project: str) -> Queue[dict[str, object]]:
        q: Queue[dict[str, object]] = Queue()
        with self._lock:
            self._subs.setdefault(project, set()).add(q)
        return q

    def unsubscribe(self, project: str, q: Queue[dict[str, object]]) -> None:
        with self._lock:
            self._subs.get(project, set()).discard(q)

    def publish(self, project: str, event: dict[str, object]) -> None:
        with self._lock:
            subs = list(self._subs.get(project, ()))
        for q in subs:
            q.put(event)


class JobManager:
    def __init__(self) -> None:
        self.bus = EventBus()
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._active_by_project: dict[str, str] = {}

    def start(self, project: str, kind: str, fn: Callable[[Job], object]) -> Job:
        """Start fn(job) in a background thread; one active job per project."""
        with self._lock:
            active = self._active_by_project.get(project)
            if active and active in self._jobs \
                    and self._jobs[active].thread.is_alive():
                raise RuntimeError("该项目已有任务在运行")
            job = Job(project, kind, fn)
            self._jobs[job.id] = job
            self._active_by_project[project] = job.id
        job.start(self.bus)
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def active_job(self, project: str) -> Job | None:
        with self._lock:
            jid = self._active_by_project.get(project)
            job = self._jobs.get(jid) if jid else None
            if job and job.thread.is_alive():
                return job
            return None

    def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None or not job.thread.is_alive():
            return False
        job.cancel.set()
        # unblock any pending gate; it returns "not approved"
        for g in job.gates.values():
            g.done.set()
        return True

    def resolve_gate(self, gate_id: str, approved: bool,
                     feedback: str | None = None) -> bool:
        for job in self._jobs.values():
            g = job.gates.get(gate_id)
            if g is not None:
                if g.done.is_set():
                    return False  # already resolved or cancelled
                g.approved = approved
                g.feedback = feedback
                g.done.set()
                return True
        return False


def run_premise_job(proj_root: Path, text: str) -> Callable[[Job], object]:
    def fn(job: Job) -> object:
        from novel.agents.strategist import StrategistAgent
        from novel.config import load_config
        from novel.project import NovelProject
        from novel.runtime import make_provider
        from novel.store.bible import StoryBible

        proj = NovelProject(root=proj_root)
        job.emit({"type": "stage", "stage": "strategist"})
        cfg = load_config(proj.config_path)
        provider = make_provider(cfg)
        concept = StrategistAgent(provider, cfg.model_for("strategist")).run(text)
        StoryBible(proj).set_concept(concept)
        job.emit({"type": "premise_done", "genre": concept.genre})
        return concept
    return fn


def run_setup_job(proj_root: Path, premise: str) -> Callable[[Job], object]:
    """Guided setup: per stage, block on a gate that carries approve-or-feedback."""
    def fn(job: Job) -> object:
        from novel.config import load_config
        from novel.project import NovelProject
        from novel.runtime import AGENT_NAMES, make_provider
        from novel.setup_flow import SETUP_STAGES, approve_stage, generate_stage, stage_done
        from novel.store.bible import StoryBible
        from novel.store.notes import WritingNotes

        proj = NovelProject(root=proj_root)
        cfg = load_config(proj.config_path)
        provider = make_provider(cfg)
        bible = StoryBible(proj)
        notes = WritingNotes(proj)
        cfg_map = {name: cfg.model_for(name) for name in AGENT_NAMES}
        for stage in SETUP_STAGES:
            if stage_done(stage, bible):
                job.emit({"type": "setup_stage", "stage": stage, "attempt": 0, "skipped": True})
                continue
            feedback: list[str] = []
            while True:
                artifact = generate_stage(stage, provider=provider, cfg_map=cfg_map,
                                          bible=bible, premise=premise, feedback=feedback)
                job.emit({"type": "setup_stage", "stage": stage, "attempt": len(feedback) + 1,
                          "artifact": artifact_text(artifact)})
                approved, fb = job.gate_with_feedback(f"setup:{stage}", artifact)
                if fb:
                    # writing memory: approval directives keep shaping every
                    # later chapter instead of being spent on one regeneration
                    notes.add_feedback(f"setup:{stage}", fb)
                if approved:
                    approve_stage(stage, artifact, bible)
                    break
                if not fb:
                    job.emit({"type": "setup_stage", "stage": stage, "attempt": 0,
                              "skipped": True, "reason": "aborted"})
                    return None  # rejected without feedback: stop cleanly, keep approved stages
                feedback.append(fb)
        return None
    return fn


def run_chapters_job(proj_root: Path, n: int) -> Callable[[Job], object]:
    def fn(job: Job) -> object:
        from novel.config import load_config
        from novel.graph import run_full_pipeline
        from novel.project import NovelProject
        from novel.resume import next_start_chapter
        from novel.runtime import AGENT_NAMES, is_live_mode, make_provider
        from novel.store.bible import StoryBible
        from novel.store.reviews import ReviewStore
        from novel.store.vector import VectorMemory, hash_embed

        proj = NovelProject(root=proj_root)
        cfg = load_config(proj.config_path)
        provider = make_provider(cfg)
        bible = StoryBible(proj)
        vector = VectorMemory(proj, embed=hash_embed)
        cfg_map = {name: cfg.model_for(name) for name in AGENT_NAMES}
        min_chars = cfg.generation.min_chapter_chars
        start_chapter = next_start_chapter(proj, ReviewStore(proj), min_chars)
        concept = bible.get_concept()
        logline = concept.logline if concept is not None else ""
        return run_full_pipeline(
            provider=provider, cfg_map=cfg_map, bible=bible, vector=vector,
            proj=proj, premise=logline,
            target_chapters=start_chapter - 1 + n, start_chapter=start_chapter,
            score_min=cfg.thresholds.score_min, max_retries=cfg.thresholds.max_retries,
            token_budget=cfg.generation.context_token_budget,
            min_chapter_chars=min_chars,
            on_gate=job.gate if is_live_mode() else None,
            on_event=job.emit,
        )
    return fn


def apply_chapter_text(proj_root: Path, chapter_no: int, draft: str) -> str:
    """Shared apply step for chapter rewrites and manual edits: back up the
    current prose under .meta/chapter_versions/, replace the chapter file
    atomically, and upsert vector memory with the new prose. Returns the
    backup file's name."""
    from datetime import UTC, datetime

    from novel.project import NovelProject
    from novel.store.vector import VectorMemory, hash_embed

    chapter_file = proj_root / "chapters" / f"{chapter_no:03d}.md"
    original = chapter_file.read_text(encoding="utf-8")
    backup_dir = proj_root / ".meta" / "chapter_versions"
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    backup = backup_dir / f"{chapter_no:03d}-{ts}.md"
    backup.write_text(original, encoding="utf-8")
    VectorMemory(NovelProject(root=proj_root), embed=hash_embed).add_chapter(chapter_no, draft)
    tmp = chapter_file.with_name(f".{chapter_no:03d}.md.tmp")
    tmp.write_text(draft, encoding="utf-8")
    tmp.replace(chapter_file)
    return backup.name


def run_chapter_rewrite_job(proj_root: Path, chapter_no: int, mode: str,
                            instruction: str) -> Callable[[Job], object]:
    """Chapter rewrite (polish / rearrange), bible-chat style: draft → text-diff
    proposal → gate (approve / feedback rounds / abandon). On apply the old
    prose is backed up under .meta/chapter_versions/, the chapter file is
    replaced atomically, and vector memory is upserted with the new prose."""
    from novel.agents.rewriter import ChapterRewriteAgent, RewriteInput
    from novel.config import load_config
    from novel.memory.assembler import (
        prev_ending_block,
        style_directives_block,
        weak_spots_block,
    )
    from novel.project import NovelProject
    from novel.render import text_diff
    from novel.runtime import is_live_mode, make_provider
    from novel.store.bible import StoryBible
    from novel.store.notes import WritingNotes

    def fn(job: Job) -> object:
        assert mode in ("polish", "rearrange"), f"unknown rewrite mode: {mode}"
        proj = NovelProject(root=proj_root)
        cfg = load_config(proj.config_path)
        bible = StoryBible(proj)
        notes = WritingNotes(proj)
        chapter_file = proj.root / "chapters" / f"{chapter_no:03d}.md"
        original = chapter_file.read_text(encoding="utf-8")

        # beat + title for continuity constraints; rewrite works without them too
        beat_json, title = "", f"第 {chapter_no} 章"
        outline = bible.get_outline()
        if outline is not None:
            for arc in outline.arcs:
                for c in arc.chapters:
                    if c.chapter_no == chapter_no:
                        title = c.chapter_title or title
                        if c.beats:
                            beat_json = c.beats[0].model_dump_json()
                        break

        cur_instruction = instruction
        history: list[tuple[str, str]] = []
        for _round in range(3):
            # announce before the (potentially minute-long) generation call:
            # until the first event the UI has no signal the job is alive
            job.emit({"type": "stage", "stage": "rewriting", "chapter": chapter_no})
            if is_live_mode():
                provider = make_provider(cfg)
                draft = ChapterRewriteAgent(provider, cfg.model_for("rewriter")).run(
                    RewriteInput(chapter_no=chapter_no, title=title, mode=mode,
                                 instruction=cur_instruction, original=original,
                                 beat_json=beat_json,
                                 style_block=style_directives_block(notes),
                                 weak_block=weak_spots_block(notes),
                                 prev_ending=prev_ending_block(proj, chapter_no),
                                 history=history)).prose
            else:
                draft = original + "\n\n（演示模式改写稿）"
            job.emit({"type": "chapter_proposal", "chapter": chapter_no, "mode": mode,
                      "diff": text_diff(original, draft), "draft": draft})
            approved, fb = job.gate_with_feedback(f"rewrite:{chapter_no}", draft)
            if approved:
                backup = apply_chapter_text(proj_root, chapter_no, draft)
                job.emit({"type": "rewrite_applied", "chapter": chapter_no,
                          "backup": backup})
                job.emit({"type": "rewrite_done", "chapter": chapter_no, "applied": True})
                return None
            if not fb:
                job.emit({"type": "rewrite_done", "chapter": chapter_no, "applied": False})
                return None
            history.append((cur_instruction, "rejected"))
            cur_instruction = fb
        job.emit({"type": "rewrite_done", "chapter": chapter_no, "applied": False})
        return None
    return fn


def run_bible_chat_job(proj_root: Path, section: str, instruction: str,
                       character_id: str | None = None) -> Callable[[Job], object]:
    from novel.agents.setting_editor import SettingEditInput, SettingEditorAgent
    from novel.config import load_config
    from novel.models import Character as _Char
    from novel.project import NovelProject
    from novel.runtime import is_live_mode, make_provider
    from novel.store.bible import StoryBible

    def fn(job: Job) -> object:
        assert section in ("concept", "world", "characters"), f"chat unsupported: {section}"
        proj = NovelProject(root=proj_root)
        cfg = load_config(proj.config_path)
        bible = StoryBible(proj)
        target_id = character_id  # single-character scoping
        schema = _Char if target_id else _SECTION_MODELS[section]

        def current_artifact() -> object:
            if target_id:
                ch = bible.get_character(target_id)
                assert ch is not None, f"no character {target_id}"
                return ch
            art = read_bible_section(bible, section)
            assert art is not None, f"section {section} is empty"
            return art

        cur_instruction = instruction
        history: list[tuple[str, str]] = []
        for _round in range(3):
            current = current_artifact()
            current_json = current.model_dump_json()  # type: ignore[attr-defined]
            if is_live_mode():
                provider = make_provider(cfg)
                draft = SettingEditorAgent(provider, cfg.model_for("setting_editor"),
                                           schema).run(SettingEditInput(
                    current_json=current_json, instruction=cur_instruction, history=history))
            else:
                draft = schema.model_validate_json(current_json)  # demo: echo
            diff = json_diff(current.model_dump(), draft.model_dump())  # type: ignore[attr-defined]
            job.emit({"type": "bible_proposal", "section": section,
                      "diff": diff, "draft": draft.model_dump()})
            approved, fb = job.gate_with_feedback(f"bible:{section}", draft)
            if approved:
                if target_id:
                    bible.upsert_character(draft)  # type: ignore[arg-type]
                else:
                    save_bible_section(bible, section, draft)
                job.emit({"type": "bible_applied", "section": section})
                job.emit({"type": "bible_chat_done", "section": section, "applied": True})
                return None
            if not fb:
                job.emit({"type": "bible_chat_done", "section": section, "applied": False})
                return None
            history.append((cur_instruction, "rejected"))
            cur_instruction = fb
        job.emit({"type": "bible_chat_done", "section": section, "applied": False})
        return None
    return fn


def run_outline_extend_job(proj_root: Path, n: int) -> Callable[[Job], object]:
    from novel.agents.outliner import OutlineExtendInput, OutlinerExtendAgent
    from novel.config import load_config
    from novel.models import Arc, ChapterBeat, ChapterOutline, ForeshadowStatus
    from novel.project import NovelProject
    from novel.runtime import is_live_mode, make_provider
    from novel.setup_flow import merge_foreshadow_ledger
    from novel.store.bible import StoryBible

    def fn(job: Job) -> object:
        proj = NovelProject(root=proj_root)
        cfg = load_config(proj.config_path)
        bible = StoryBible(proj)
        concept = bible.get_concept()
        world = bible.get_world()
        roster = bible.all_characters()
        existing = bible.get_outline()
        assert concept is not None and world is not None, "concept+world required"
        assert existing is not None, "outline is empty"
        if is_live_mode():
            provider = make_provider(cfg)
            draft = OutlinerExtendAgent(provider, cfg.model_for("outliner")).run(
                OutlineExtendInput(concept=concept, world=world, characters=roster,
                                   current=existing, recent_events=bible.list_events(),
                                   open_foreshadows=[f for f in bible.list_foreshadow()
                                                      if f.status == ForeshadowStatus.OPEN],
                                   n_chapters=n))
        else:
            existing_max = max((c.chapter_no for a in existing.arcs for c in a.chapters),
                               default=0)
            first = roster[0].id if roster else "c1"
            beat = ChapterBeat(pov=first, setting="demo", event="demo extension",
                               emotional_turn="steady", characters=[first])
            draft = Outline(arcs=[Arc(arc_name="Extension",
                chapters=[ChapterOutline(chapter_no=existing_max + k,
                                         chapter_title=f"T{existing_max + k}",
                                         beats=[beat]) for k in range(1, n + 1)])])
        diff = json_diff(existing.model_dump(), draft.model_dump())
        job.emit({"type": "outline_extend_proposal", "added": n, "diff": diff})
        approved, _fb = job.gate_with_feedback("bible:outline_extend", draft)
        if not approved:
            return None
        for arc in draft.arcs:          # draft = agent 输出的纯新增章
            existing.arcs.append(arc)   # 追加弧（agent prompt 已保证编号续接）
        existing.foreshadow_ledger.extend(draft.foreshadow_ledger)
        bible.set_outline(existing)
        merge_foreshadow_ledger(existing, bible)
        job.emit({"type": "outline_extended", "added": n})
        return None
    return fn


BIBLE_SECTIONS = ("concept", "world", "characters", "outline", "foreshadows", "events")
_READ_ONLY_SECTIONS = ("events",)
_SECTION_MODELS: dict[str, type[BaseModel]] = {
    "concept": Concept,
    "world": World,
    "outline": Outline,
}


def read_bible_section(bible: StoryBible, section: str) -> object | None:
    if section == "concept":
        try:
            return bible.get_concept()
        except KeyError:
            return None
    if section == "world":
        return bible.get_world()
    if section == "characters":
        return bible.all_characters()
    if section == "outline":
        return bible.get_outline()
    if section == "foreshadows":
        return bible.list_foreshadow()
    if section == "events":
        return bible.list_events()
    raise ValueError(f"unknown section: {section}")


def validate_bible_section(section: str, data: object) -> object:
    if section in _READ_ONLY_SECTIONS:
        raise ValueError(f"unknown section: {section}")  # events: append-only, no PUT
    if section == "characters":
        assert isinstance(data, list)
        return [Character.model_validate(c) for c in data]
    if section == "foreshadows":
        assert isinstance(data, list)
        return [Foreshadow.model_validate(f) for f in data]
    if section in _SECTION_MODELS:
        return _SECTION_MODELS[section].model_validate(data)
    raise ValueError(f"unknown section: {section}")


def save_bible_section(bible: StoryBible, section: str, artifact: object) -> None:
    if section == "concept":
        bible.set_concept(artifact)  # type: ignore[arg-type]
    elif section == "world":
        bible.set_world(artifact)  # type: ignore[arg-type]
    elif section == "characters":
        d = bible.proj.load_canonical()
        d["characters"] = [ch.model_dump() for ch in artifact]  # type: ignore[attr-defined]
        bible.proj.save_canonical(d)
    elif section == "outline":
        bible.set_outline(artifact)  # type: ignore[arg-type]
    elif section == "foreshadows":
        path = bible.proj.root / "bible" / "foreshadowing.json"
        items = [f.model_dump() for f in artifact]  # type: ignore[attr-defined]
        path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        raise ValueError(f"unknown section: {section}")


def json_diff(old: object, new: object) -> str:
    import difflib
    import json as _json

    def lines(obj: object) -> list[str]:
        return _json.dumps(obj, ensure_ascii=False, indent=2,
                           default=lambda o: o.model_dump() if hasattr(o, "model_dump") else str(o)
                           ).splitlines()

    return "\n".join(difflib.unified_diff(
        lines(old), lines(new), fromfile="当前", tofile="改写稿", lineterm=""))


def drain(q: Queue[dict[str, object]], timeout: float = 0.05) -> list[dict[str, object]]:
    """Non-blocking drain of a subscriber queue (helper for SSE endpoints/tests)."""
    out: list[dict[str, object]] = []
    while True:
        try:
            out.append(q.get(timeout=timeout))
        except Empty:
            return out
