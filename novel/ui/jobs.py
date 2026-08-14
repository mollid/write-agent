"""Background job management: run the synchronous pipeline in threads, bridge
human gates to the GUI, and broadcast progress events per project."""
from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, Queue

from pydantic import BaseModel


class JobCancelled(Exception):
    """Raised inside a job thread when cancellation was requested."""


def artifact_text(obj: object) -> str:
    """Render a gate artifact (pydantic model / int / str) to displayable text."""
    if isinstance(obj, BaseModel):
        try:
            import json
            return json.dumps(json.loads(obj.model_dump_json()), ensure_ascii=False, indent=2)
        except Exception:  # noqa: BLE001 - display only
            return str(obj)
    return str(obj)


@dataclass
class Gate:
    id: str
    label: str
    artifact: str
    done: threading.Event = field(default_factory=threading.Event)
    approved: bool = False


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
        g = Gate(id=uuid.uuid4().hex[:12], label=label, artifact=artifact_text(artifact))
        self.gates[g.id] = g
        if self._bus is not None:
            self._bus.publish(self.project, {
                "type": "gate", "job_id": self.id, "gate_id": g.id,
                "label": label, "artifact": g.artifact,
            })
        while not g.done.wait(timeout=0.25):
            if self.cancel.is_set():
                return False
        return g.approved

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

    def resolve_gate(self, gate_id: str, approved: bool) -> bool:
        for job in self._jobs.values():
            g = job.gates.get(gate_id)
            if g is not None:
                if g.done.is_set():
                    return False  # already resolved or cancelled
                g.approved = approved
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


def run_chapters_job(proj_root: Path, n: int) -> Callable[[Job], object]:
    def fn(job: Job) -> object:
        from novel.config import load_config
        from novel.graph import run_full_pipeline
        from novel.project import NovelProject
        from novel.runtime import AGENT_NAMES, is_live_mode, make_provider
        from novel.store.bible import StoryBible
        from novel.store.vector import VectorMemory, hash_embed

        proj = NovelProject(root=proj_root)
        cfg = load_config(proj.config_path)
        provider = make_provider(cfg)
        bible = StoryBible(proj)
        vector = VectorMemory(proj, embed=hash_embed)
        cfg_map = {name: cfg.model_for(name) for name in AGENT_NAMES}
        existing = sorted((proj.root / "chapters").glob("[0-9][0-9][0-9].md"))
        start_chapter = int(existing[-1].stem) + 1 if existing else 1
        concept = bible.get_concept()
        logline = concept.logline if concept is not None else ""
        return run_full_pipeline(
            provider=provider, cfg_map=cfg_map, bible=bible, vector=vector,
            proj=proj, premise=logline,
            target_chapters=start_chapter - 1 + n, start_chapter=start_chapter,
            score_min=cfg.thresholds.score_min, max_retries=cfg.thresholds.max_retries,
            token_budget=cfg.generation.context_token_budget,
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
