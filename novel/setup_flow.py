"""Guided setup (标准模式): stage-by-stage generation with accumulated user feedback.

UI-agnostic core shared by the CLI `setup` command, the GUI setup job, and the
pipeline's one-shot SETUP block. Stages read their inputs from the bible, so the
flow is re-entrant: already-approved stages are skipped by callers via stage_done().
"""
from __future__ import annotations

import re

from novel.agents.character import CharacterAgent
from novel.agents.outliner import OutlinerAgent
from novel.agents.strategist import StrategistAgent
from novel.agents.worldbuilder import WorldbuilderAgent
from novel.config import ModelConfig
from novel.models import Character, Concept, Foreshadow, ForeshadowStatus, Outline, World
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


def generate_stage(stage: str, *, provider: ModelProvider, cfg_map: dict[str, ModelConfig],
                   bible: StoryBible, premise: str = "",
                   feedback: list[str] | None = None) -> object:
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
        return OutlinerAgent(provider, cfg_map["outliner"]).run(
            (concept, world, list(bible.all_characters())), feedback=fb)
    raise ValueError(f"unknown setup stage: {stage}")


def merge_foreshadow_ledger(outline: Outline, bible: StoryBible) -> None:
    """Merge an outline's ledger entries into the bible's foreshadow list (idempotent)."""
    for entry in outline.foreshadow_ledger:
        if not any(f.id == entry.id for f in bible.list_foreshadow()):
            bible.add_foreshadow(Foreshadow(
                id=entry.id, description=entry.description,
                planted_ch=_parse_ch(entry.planted_in), status=ForeshadowStatus.OPEN))


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
        bible.set_outline(artifact)
        merge_foreshadow_ledger(artifact, bible)
    else:
        raise ValueError(f"unknown setup stage: {stage}")
