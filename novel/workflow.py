"""Deterministic workflow planner: project state -> ordered steps + ONE next
action. The plan is the sole authority for "what comes next" (ArcReel-style);
the chat orchestrator reads it instead of guessing from files or history."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from novel.config import ProjectConfig
from novel.project import NovelProject
from novel.resume import next_start_chapter
from novel.setup_flow import SETUP_STAGES, stage_done
from novel.store.bible import StoryBible
from novel.store.reviews import ReviewStore


class WorkflowStepState(str, Enum):
    COMPLETED = "completed"
    READY = "ready"
    ACTIVE = "active"
    BLOCKED = "blocked"
    PENDING = "pending"


class WorkflowStep(BaseModel):
    id: str
    state: WorkflowStepState
    detail: str = ""


class NextAction(BaseModel):
    type: str
    args: dict[str, object] = Field(default_factory=dict)
    reason: str = ""


class WorkflowPlan(BaseModel):
    steps: list[WorkflowStep]
    next_action: NextAction
    available_actions: list[str]
    progress: dict[str, object]


def build_plan(proj: NovelProject, bible: StoryBible, reviews: ReviewStore,
               cfg: ProjectConfig, active_job_id: str | None = None) -> WorkflowPlan:
    """Pure projection; no side effects, no network, no model calls."""
    concept = bible.get_concept()
    setup_flags = {s: stage_done(s, bible) for s in SETUP_STAGES}
    setup_complete = all(setup_flags.values())
    written = next_start_chapter(proj, reviews, cfg.generation.min_chapter_chars) - 1
    outline = bible.get_outline()
    planned_total: int | None
    if outline is not None:
        planned_total = sum(len(a.chapters) for a in outline.arcs)
    else:
        planned_total = cfg.generation.target_chapters
    chapters_done = setup_complete and planned_total is not None and written >= planned_total

    steps: list[WorkflowStep] = []
    steps.append(WorkflowStep(
        id="premise",
        state=WorkflowStepState.COMPLETED if concept is not None else WorkflowStepState.READY,
        detail="故事概念" if concept is not None else "缺少故事概念,需要用户提供创意文本"))
    blocked_seen = concept is None
    for s in SETUP_STAGES:
        if setup_flags[s]:
            state = WorkflowStepState.COMPLETED
        elif blocked_seen:
            state = WorkflowStepState.PENDING
        else:
            state = WorkflowStepState.READY
            blocked_seen = True
        steps.append(WorkflowStep(id=f"setup:{s}", state=state, detail=f"分阶段设定:{s}"))
    if chapters_done:
        ch_state = WorkflowStepState.COMPLETED
    elif setup_complete:
        ch_state = WorkflowStepState.ACTIVE if active_job_id else WorkflowStepState.READY
    else:
        ch_state = WorkflowStepState.PENDING
    total_label = planned_total if planned_total is not None else "∞"
    steps.append(WorkflowStep(id="chapters", state=ch_state,
                              detail=f"已写 {written}/{total_label} 章"))
    steps.append(WorkflowStep(id="done",
                              state=WorkflowStepState.COMPLETED if chapters_done else WorkflowStepState.PENDING,
                              detail="全书完成" if chapters_done else "未完成"))

    if active_job_id:
        next_action = NextAction(type="wait_job", args={"job_id": active_job_id},
                                 reason="已有任务在运行,不得并发启动新任务")
    elif concept is None:
        next_action = NextAction(type="write_premise", reason="缺少故事概念")
    elif not setup_complete:
        next_action = NextAction(type="run_setup", reason="分阶段设定未完成")
    elif not chapters_done:
        remaining = planned_total - written if planned_total is not None else 5
        next_action = NextAction(type="write_chapters", args={"n": remaining},
                                 reason=f"已写 {written},计划 {total_label}")
    else:
        next_action = NextAction(type="none", reason="全书章节已完成")

    available: list[str] = []
    if written >= 1:
        available += ["rewrite_chapter", "run_tts", "export"]
    if concept is not None or bible.get_world() is not None or bible.all_characters():
        available.append("edit_bible")
    if outline is not None:
        available.append("extend_outline")

    return WorkflowPlan(
        steps=steps,
        next_action=next_action,
        available_actions=available,
        progress={"written": written, "planned_total": planned_total,
                  "active_job_id": active_job_id},
    )
