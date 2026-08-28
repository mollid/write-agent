"""Guided setup (标准模式): stage-by-stage generation with accumulated user feedback.

UI-agnostic core shared by the CLI `setup` command, the GUI setup job, and the
pipeline's one-shot SETUP block. Stages read their inputs from the bible, so the
flow is re-entrant: already-approved stages are skipped by callers via stage_done().
"""
from __future__ import annotations

import re

from novel.agents.cast_planner import CastPlanInput, CastPlannerAgent
from novel.agents.character import CharacterAgent
from novel.agents.outliner import ArcDetailerAgent, ArcDetailInput, ArcPlannerAgent, OutlinerAgent
from novel.agents.strategist import StrategistAgent
from novel.agents.worldbuilder import WorldbuilderAgent
from novel.config import ModelConfig
from novel.models import (
    Arc,
    ArcSkeleton,
    ArcSummary,
    ChapterSummary,
    Character,
    Concept,
    Foreshadow,
    ForeshadowStatus,
    Outline,
    World,
)
from novel.providers import ModelProvider
from novel.store.bible import StoryBible

SETUP_STAGES = ["concept", "world", "characters", "outline"]


def _parse_ch(ref: str) -> int | None:
    """Best-effort: 'c03-b01' / 'ch3' -> 3."""
    m = re.search(r"(\d+)", ref)
    return int(m.group(1)) if m else None


def stage_done(stage: str, bible: StoryBible) -> bool:
    if stage == "concept":
        return bible.get_concept() is not None
    if stage == "world":
        return bible.get_world() is not None
    if stage == "characters":
        return bool(bible.all_characters())
    if stage == "outline":
        return bible.get_outline() is not None
    raise ValueError(f"unknown setup stage: {stage}")


def validate_outline(outline: Outline, *, start_chapter: int = 1) -> None:
    """Whole-book invariants every persisted outline must hold:
    1. chapter numbering is consecutive from start_chapter — the write loop maps
       chapter k on disk to the k-th outline entry, so gaps or milestone jumps
       (e.g. ch5 → ch120) silently misalign prose with beats;
    2. arc_plan queues only NOT-yet-detailed volumes — a duplicated volume name
       makes the rolling detailer re-detail an already-written volume.
    The message names the offending numbers so it can be fed back to the model."""
    want = start_chapter
    for arc in outline.arcs:
        for ch in arc.chapters:
            if ch.chapter_no != want:
                raise ValueError(
                    f"invalid outline (章节编号必须连续): after chapter {want - 1} came "
                    f"chapter {ch.chapter_no}, expected {want}")
            want += 1
    duplicated = [s.arc_name for s in outline.arc_plan
                  if s.arc_name in {a.arc_name for a in outline.arcs}]
    if duplicated:
        raise ValueError(
            f"invalid outline (arc_plan 只能排队未细化的卷): {duplicated} already in arcs")


def generate_stage(stage: str, *, provider: ModelProvider, cfg_map: dict[str, ModelConfig],
                   bible: StoryBible, premise: str = "",
                   feedback: list[str] | None = None,
                   target_chapters: int | None = None) -> object:
    """Run the stage's agent WITHOUT persisting anything. Inputs come from the bible."""
    fb = list(feedback or [])
    if stage == "concept":
        concept = bible.get_concept()
        text = premise or (concept.logline if concept is not None else "")
        return StrategistAgent(provider, cfg_map["strategist"]).run(text, feedback=fb)
    if stage == "world":
        concept = bible.get_concept()
        assert concept is not None, "concept must be approved before world"
        return WorldbuilderAgent(provider, cfg_map["worldbuilder"]).run(concept, feedback=fb)
    if stage == "characters":
        concept = bible.get_concept()
        world = bible.get_world()
        assert concept is not None and world is not None, "concept+world required"
        return CharacterAgent(provider, cfg_map["character"]).run((concept, world), feedback=fb)
    if stage == "outline":
        concept = bible.get_concept()
        world = bible.get_world()
        assert concept is not None and world is not None, "concept+world required"
        if target_chapters:
            return generate_two_phase_outline(provider=provider, cfg_map=cfg_map,
                                               bible=bible, target_chapters=target_chapters,
                                               feedback=fb)
        agent_feedback = list(fb)
        outline: Outline | None = None
        for _attempt in range(2):
            outline = OutlinerAgent(provider, cfg_map["outliner"]).run(
                (concept, world, list(bible.all_characters())), feedback=agent_feedback)
            # the one-shot outliner never legitimately queues volume skeletons; a
            # hallucinated arc_plan would make the write loop re-detail volumes
            outline.arc_plan = []
            try:
                validate_outline(outline)
                break
            except ValueError as e:
                # one auto-retry carrying the validation error — sparse numbering
                # (milestone jumps) is the classic long-book hallucination
                agent_feedback.append(str(e))
        assert outline is not None
        return outline
    raise ValueError(f"unknown setup stage: {stage}")


def generate_two_phase_outline(*, provider: ModelProvider, cfg_map: dict[str, ModelConfig],
                               bible: StoryBible, target_chapters: int,
                               feedback: list[str] | None = None) -> Outline:
    """Volume skeletons first, then only the FIRST volume detailed (spec §4.3).
    Outline.arc_plan keeps the not-yet-detailed skeletons as a queue. Guided-setup
    feedback shapes the skeleton stage (where whole-book structure belongs)."""
    concept = bible.get_concept()
    world = bible.get_world()
    assert concept is not None and world is not None, "concept+world required"
    roster = list(bible.all_characters())
    plan = ArcPlannerAgent(provider, cfg_map["outliner"]).run(
        (concept, world, roster, target_chapters), feedback=list(feedback or []))
    assert plan.arcs, "arc planner returned no volumes"
    existing_max = 0
    arc = _detail_arc(provider, cfg_map, bible, plan.arcs[0], prev_arc=None,
                      next_chapter_no=existing_max + 1, recent_summaries=[])
    assert arc.chapters, "arc detailer returned no chapters"
    outline = Outline(arcs=[arc], arc_plan=plan.arcs[1:])
    merge_foreshadow_ledger(outline, bible)
    validate_outline(outline)
    return outline


_CAST_CAP_PER_VOLUME = 5


def _plan_arc_cast(provider: ModelProvider, cfg_map: dict[str, ModelConfig],
                   bible: StoryBible, skeleton: ArcSkeleton,
                   recent_summaries: list[ChapterSummary],
                   feedback: list[str] | None = None) -> list[Character]:
    """Volume cast seeding (spec §4.3): propose the upcoming volume's NEW
    characters (0–5). Proposals are filtered defensively before they reach the
    gate — a second protagonist, ids colliding with the existing roster, or
    duplicate ids would overwrite bible entries on upsert."""
    concept = bible.get_concept()
    world = bible.get_world()
    assert concept is not None and world is not None, "concept+world required"
    roster = list(bible.all_characters())
    proposal = CastPlannerAgent(provider, cfg_map["character"]).run(
        CastPlanInput(skeleton=skeleton, concept=concept, world=world,
                      characters=roster, recent_summaries=recent_summaries),
        feedback=feedback)
    existing_ids = {c.id for c in roster}
    seen: set[str] = set()
    out: list[Character] = []
    for ch in proposal:
        if ch.role == "protagonist" or ch.id in existing_ids or ch.id in seen:
            continue
        seen.add(ch.id)
        ch.slug = ch.id   # mirrors stay one file per character id
        out.append(ch)
        if len(out) >= _CAST_CAP_PER_VOLUME:
            break
    return out


def _detail_arc(provider: ModelProvider, cfg_map: dict[str, ModelConfig],
                bible: StoryBible, skeleton: ArcSkeleton, prev_arc: ArcSummary | None,
                next_chapter_no: int, recent_summaries: list[ChapterSummary],
                feedback: list[str] | None = None) -> Arc:
    concept = bible.get_concept()
    world = bible.get_world()
    assert concept is not None and world is not None, "concept+world required"
    arc = ArcDetailerAgent(provider, cfg_map["outliner"]).run(ArcDetailInput(
        skeleton=skeleton, concept=concept, world=world,
        characters=list(bible.all_characters()), prev_arc=prev_arc,
        open_foreshadows=[f for f in bible.list_foreshadow()
                          if f.status == ForeshadowStatus.OPEN],
        recent_summaries=recent_summaries, next_chapter_no=next_chapter_no),
        feedback=feedback)
    # defensive renumbering: model output numbers are advisory only (spec §4.3)
    for i, ch in enumerate(arc.chapters):
        ch.chapter_no = next_chapter_no + i
    # adopt the skeleton's name — model output is advisory only (spec §4.3)
    arc.arc_name = skeleton.arc_name
    return arc


def merge_foreshadow_ledger(outline: Outline, bible: StoryBible) -> None:
    """Merge an outline's ledger entries into the bible's foreshadow list (idempotent)."""
    for entry in outline.foreshadow_ledger:
        if not any(f.id == entry.id for f in bible.list_foreshadow()):
            bible.add_foreshadow(Foreshadow(
                id=entry.id, description=entry.description,
                planted_ch=_parse_ch(entry.planted_in), status=ForeshadowStatus.OPEN))


def merge_outline_extension(existing: Outline, draft: Outline) -> None:
    """Append a 手动追章 draft (agent output = pure additions) in place. Draft
    numbering is advisory only: chapters are renumbered onto the existing tail,
    and a hallucinated draft.arc_plan never enters the rolling queue."""
    existing_max = max((c.chapter_no for a in existing.arcs for c in a.chapters), default=0)
    for arc in draft.arcs:
        for i, ch in enumerate(arc.chapters):
            ch.chapter_no = existing_max + 1 + i
        existing_max += len(arc.chapters)
        existing.arcs.append(arc)
    existing.foreshadow_ledger.extend(draft.foreshadow_ledger)


def approve_stage(stage: str, artifact: object, bible: StoryBible) -> None:
    """Persist an approved artifact into the story bible."""
    if stage == "concept":
        assert isinstance(artifact, Concept)
        bible.set_concept(artifact)
    elif stage == "world":
        assert isinstance(artifact, World)
        bible.set_world(artifact)
    elif stage == "characters":
        assert isinstance(artifact, list)
        for ch in artifact:
            assert isinstance(ch, Character)
            bible.upsert_character(ch)
    elif stage == "outline":
        assert isinstance(artifact, Outline)
        validate_outline(artifact)  # last line of defense before persistence
        bible.set_outline(artifact)
        merge_foreshadow_ledger(artifact, bible)
    else:
        raise ValueError(f"unknown setup stage: {stage}")
