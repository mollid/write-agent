from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field

from novel.agents.character import CharacterAgent
from novel.agents.continuity import ContinuityAgent
from novel.agents.editor import EditorAgent
from novel.agents.outliner import OutlinerAgent
from novel.agents.scorer import ScorerAgent
from novel.agents.strategist import StrategistAgent
from novel.agents.worldbuilder import WorldbuilderAgent
from novel.agents.writer import WriterAgent
from novel.config import ModelConfig
from novel.memory.assembler import assemble_context
from novel.memory.extractor import extract_updates
from novel.models import ReviewScore
from novel.project import NovelProject
from novel.providers import ModelProvider
from novel.scorer_rubrics import apply_review, decide
from novel.store.bible import StoryBible
from novel.store.vector import VectorMemory


@dataclass
class PipelineState:
    premise: str = ""
    attempts: dict[str, int] = field(default_factory=dict)
    last_review: ReviewScore | None = None
    human_overrides: dict[str, object] = field(default_factory=dict)
    error: str | None = None


def _scored(producer_out: str, artifact_type: str, artifact_json: str, scorer: ScorerAgent,
            score_min: int, max_retries: int, attempt: int) -> tuple[bool, ReviewScore]:
    rs = scorer.run((artifact_type, artifact_json))
    rs.attempt = attempt
    ok = decide(rs, score_min)
    return ok, rs


def run_full_pipeline(
    *, provider: ModelProvider, cfg_map: dict[str, ModelConfig], bible: StoryBible,
    vector: VectorMemory, proj: NovelProject, premise: str, target_chapters: int,
    score_min: int = 80, max_retries: int = 3, token_budget: int = 24000,
    on_gate: Callable[[str, object], None] | None = None,
) -> PipelineState:
    state = PipelineState(premise=premise)

    def agent(name: str) -> ModelConfig:
        return cfg_map[name]

    # --- SETUP ---
    concept = StrategistAgent(provider, agent("strategist")).run(premise)
    bible.set_concept(concept)
    world = WorldbuilderAgent(provider, agent("worldbuilder")).run(concept)
    bible.set_world(world)
    chars = CharacterAgent(provider, agent("character")).run((concept, world))
    for ch in chars:
        bible.upsert_character(ch)
    outline = OutlinerAgent(provider, agent("outliner")).run((concept, world, chars))
    bible.set_outline(outline)
    if on_gate:
        on_gate("outline", outline)

    scorer = ScorerAgent(provider, agent("scorer"))

    # --- GENERATION ---
    chapter_no = 0
    for arc in outline.arcs:
        for ch_out in arc.chapters:
            chapter_no += 1
            if chapter_no > target_chapters:
                break
            beat = ch_out.beats[0] if ch_out.beats else None
            assert beat is not None, f"chapter {chapter_no} has no beat"
            ctx = assemble_context(beat=beat, bible=bible, vector=vector,
                                   proj=proj, token_budget=token_budget)
            writer = WriterAgent(provider, agent("writer"))
            prose = writer.run(ctx)
            # scorer loop on chapter
            attempt = 1
            while True:
                ok, rs = _scored(prose, "chapter",
                                 json.dumps({"prose": prose, "beat": beat.model_dump()}, ensure_ascii=False),
                                 scorer, score_min, max_retries, attempt)
                state.last_review = rs
                if ok or attempt >= max_retries:
                    break
                feedback = apply_review(rs, prose)
                prose = writer.run(type(ctx)(blocks=ctx.blocks + [f"[REWRITE NOTES] {feedback}"]))
                attempt += 1
            # continuity
            issues = ContinuityAgent(provider, agent("continuity")).run(
                (prose, json.dumps(proj.load_canonical(), ensure_ascii=False)))
            if issues:
                prose = EditorAgent(provider, agent("editor")).run(prose)
            # persist
            (proj.root / "chapters" / f"{chapter_no:03d}.md").write_text(prose, encoding="utf-8")
            vector.add_chapter(chapter_no, prose)
            # extract updates -> apply to bible
            raw_chars = [bible.get_character(c) for c in beat.characters] if beat else []
            involved = [c for c in raw_chars if c is not None]
            upd = extract_updates(chapter_no, prose, involved, provider, agent("extractor"))
            for cid, st in upd.character_states.items():
                ch_obj = bible.get_character(cid)
                if ch_obj:
                    ch_obj.state = st
                    bible.upsert_character(ch_obj)
            for e in upd.events:
                bible.append_event(e)
            vector.add_summary("chapter", f"ch{chapter_no}", prose[:300])
            if on_gate and chapter_no % 1 == 0:
                on_gate("chapter", chapter_no)
    return state
