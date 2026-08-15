"""Background job management: run the synchronous pipeline in threads, bridge
human gates to the GUI, and broadcast progress events per project."""
from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, Queue

from novel.render import artifact_text


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

        proj = NovelProject(root=proj_root)
        cfg = load_config(proj.config_path)
        provider = make_provider(cfg)
        bible = StoryBible(proj)
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


def drain(q: Queue[dict[str, object]], timeout: float = 0.05) -> list[dict[str, object]]:
    """Non-blocking drain of a subscriber queue (helper for SSE endpoints/tests)."""
    out: list[dict[str, object]] = []
    while True:
        try:
            out.append(q.get(timeout=timeout))
        except Empty:
            return out
