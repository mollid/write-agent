"""Workflow planner: project state -> steps + single next_action (spec §4.1)."""
from __future__ import annotations

from pathlib import Path

from novel.config import ProjectConfig
from novel.models import Arc, ChapterBeat, ChapterOutline, Concept, Outline, World
from novel.project import NovelProject
from novel.store.bible import StoryBible
from novel.store.reviews import ReviewStore
from novel.workflow import WorkflowPlan, build_plan


def _proj(tmp_path: Path, target: int = 3) -> tuple[NovelProject, StoryBible, ReviewStore, ProjectConfig]:
    proj = NovelProject.scaffold("p1", genre="fantasy", root=tmp_path, target_chapters=target)
    return proj, StoryBible(proj), ReviewStore(proj), ProjectConfig()


def _outline(n: int = 3) -> Outline:
    beat = ChapterBeat(pov="c1", setting="s", event="e", emotional_turn="steady", characters=["c1"])
    return Outline(arcs=[Arc(arc_name="A", chapters=[
        ChapterOutline(chapter_no=i, chapter_title=f"T{i}", beats=[beat]) for i in range(1, n + 1)])])


def _fill_setup(bible: StoryBible, outline: Outline | None = None) -> None:
    bible.set_concept(Concept(logline="L", genre="g", tone="t", themes=["x"],
                              target_length_words=100, audience="a"))
    bible.set_world(World(setting="S"))
    from novel.models import Character
    bible.set_characters([Character(id="c1", slug="a", name="A", role="protagonist",
                                    backstory="b", motivation="m", arc="a")])
    if outline is not None:
        bible.set_outline(outline)


def _write_chapter(tmp_path: Path, n: int) -> None:
    d = tmp_path / "p1" / "chapters"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{n:03d}.md").write_text("x" * 80, encoding="utf-8")


def _by_id(plan: WorkflowPlan) -> dict[str, str]:
    return {s.id: s.state.value for s in plan.steps}


def test_empty_project_wants_premise(tmp_path: Path) -> None:
    proj, bible, reviews, cfg = _proj(tmp_path)
    plan = build_plan(proj, bible, reviews, cfg)
    assert _by_id(plan)["premise"] == "ready"
    assert plan.next_action.type == "write_premise"
    assert plan.next_action.args == {}
    assert "write_chapters" not in plan.available_actions


def test_concept_done_next_is_setup(tmp_path: Path) -> None:
    proj, bible, reviews, cfg = _proj(tmp_path)
    bible.set_concept(Concept(logline="L", genre="g", tone="t", themes=["x"],
                              target_length_words=100, audience="a"))
    plan = build_plan(proj, bible, reviews, cfg)
    assert _by_id(plan)["premise"] == "completed"
    assert _by_id(plan)["setup:concept"] == "completed"
    assert _by_id(plan)["setup:world"] == "ready"
    assert plan.next_action.type == "run_setup"
    assert plan.progress["written"] == 0


def test_mid_setup_first_incomplete_is_ready(tmp_path: Path) -> None:
    proj, bible, reviews, cfg = _proj(tmp_path)
    _fill_setup(bible, outline=None)
    plan = build_plan(proj, bible, reviews, cfg)
    assert _by_id(plan)["setup:outline"] == "ready"
    assert _by_id(plan)["chapters"] == "pending"


def test_setup_done_writes_chapters(tmp_path: Path) -> None:
    proj, bible, reviews, cfg = _proj(tmp_path)          # target 3
    _fill_setup(bible, outline=_outline(3))
    _write_chapter(tmp_path, 1)
    plan = build_plan(proj, bible, reviews, cfg)
    assert _by_id(plan)["chapters"] == "ready"
    assert plan.next_action.type == "write_chapters"
    assert plan.next_action.args == {"n": 2}             # planned 3 - written 1
    assert plan.progress == {"written": 1, "planned_total": 3, "active_job_id": None}
    assert "rewrite_chapter" in plan.available_actions
    assert "edit_bible" in plan.available_actions
    assert "extend_outline" in plan.available_actions
    assert "run_tts" in plan.available_actions


def test_all_done_next_is_none(tmp_path: Path) -> None:
    proj, bible, reviews, cfg = _proj(tmp_path)
    _fill_setup(bible, outline=_outline(2))
    _write_chapter(tmp_path, 1)
    _write_chapter(tmp_path, 2)
    plan = build_plan(proj, bible, reviews, cfg)
    assert _by_id(plan)["chapters"] == "completed"
    assert _by_id(plan)["done"] == "completed"
    assert plan.next_action.type == "none"
    assert "export" in plan.available_actions


def test_active_job_forces_wait(tmp_path: Path) -> None:
    proj, bible, reviews, cfg = _proj(tmp_path)
    _fill_setup(bible, outline=_outline(3))
    plan = build_plan(proj, bible, reviews, cfg, active_job_id="job42")
    assert plan.next_action.type == "wait_job"
    assert plan.next_action.args == {"job_id": "job42"}
    assert _by_id(plan)["chapters"] == "active"
