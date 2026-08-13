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
from novel.models import Foreshadow, ForeshadowStatus, Mannerism, ReviewScore
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
    start_chapter: int = 1,
    on_gate: Callable[[str, object], bool] | None = None,
) -> PipelineState:
    state = PipelineState(premise=premise)

    def agent(name: str) -> ModelConfig:
        return cfg_map[name]

    if start_chapter <= 1:
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
        chapter_no = 0
    else:
        # --- RESUME: skip SETUP, load persisted bible state ---
        _outline = bible.get_outline()
        assert _outline is not None, "no outline to resume from"
        outline = _outline
        concept = bible.get_concept()
        premise = premise or concept.logline
        chapter_no = start_chapter - 1

    scorer = ScorerAgent(provider, agent("scorer"))

    # --- GENERATION ---
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
            final_ok = False
            while True:
                ok, rs = _scored(prose, "chapter",
                                 json.dumps({"prose": prose, "beat": beat.model_dump()}, ensure_ascii=False),
                                 scorer, score_min, max_retries, attempt)
                state.last_review = rs
                if ok:
                    final_ok = True
                    break
                if attempt >= max_retries:
                    break
                feedback = apply_review(rs, prose)
                prose = writer.run(type(ctx)(blocks=ctx.blocks + [f"[REWRITE NOTES] {feedback}"]))
                attempt += 1
            if not final_ok:
                approved = on_gate("chapter_review_failed", rs) if on_gate else False
                if not approved:
                    state.error = f"chapter {chapter_no} rejected after {max_retries} attempts"
                    continue
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
            for cid, sample in upd.voice_samples.items():
                ch_obj = bible.get_character(cid)
                if ch_obj:
                    ch_obj.voice_fingerprint[f"sample_{chapter_no}"] = sample
                    bible.upsert_character(ch_obj)
            for cid, mannerism_text in upd.mannerisms_used.items():
                ch_obj = bible.get_character(cid)
                if ch_obj:
                    existing = next((m for m in ch_obj.mannerisms if m.text == mannerism_text), None)
                    if existing:
                        existing.used_count += 1
                    else:
                        ch_obj.mannerisms.append(Mannerism(text=mannerism_text, used_count=1))
                    bible.upsert_character(ch_obj)
            for e in upd.events:
                bible.append_event(e)
            # register foreshadowing from the beat
            for plant in beat.plants:
                fid = f"plant-{plant}"
                if not any(f.id == fid for f in bible.list_foreshadow()):
                    bible.add_foreshadow(Foreshadow(id=fid, description=plant, planted_ch=chapter_no))
            for payoff in beat.payoffs:
                open_fs = [f for f in bible.list_foreshadow()
                           if f.status == ForeshadowStatus.OPEN
                           and (payoff in f.description or f.description in payoff)]
                if open_fs:
                    target = open_fs[0]
                    bible.add_foreshadow(Foreshadow(
                        id=target.id, description=target.description,
                        planted_ch=target.planted_ch, payoff_ch=chapter_no,
                        status=ForeshadowStatus.PAID_OFF))
            vector.add_summary("chapter", f"ch{chapter_no}", prose[:300])
            if on_gate:
                on_gate("chapter", chapter_no)
    return state
