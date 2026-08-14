from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

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
from novel.models import Event, Foreshadow, ForeshadowStatus, Mannerism, ReviewRecord, ReviewScore
from novel.project import NovelProject
from novel.providers import ModelProvider
from novel.scorer_rubrics import apply_review, decide
from novel.store.bible import StoryBible
from novel.store.reviews import ReviewStore
from novel.store.vector import VectorMemory


@dataclass
class PipelineState:
    premise: str = ""
    attempts: dict[str, int] = field(default_factory=dict)
    last_review: ReviewScore | None = None
    human_overrides: dict[str, object] = field(default_factory=dict)
    error: str | None = None


def _parse_ch(ref: str) -> int | None:
    """Best-effort: 'c03-b01' / 'ch3' -> 3."""
    m = re.search(r"(\d+)", ref)
    return int(m.group(1)) if m else None


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
    on_event: Callable[[dict[str, object]], None] | None = None,
) -> PipelineState:
    state = PipelineState(premise=premise)

    def emit(event: dict[str, object]) -> None:
        if on_event is not None:
            on_event(event)

    def agent(name: str) -> ModelConfig:
        return cfg_map[name]

    if start_chapter <= 1:
        # --- SETUP ---
        emit({"type": "stage", "stage": "strategist"})
        concept = StrategistAgent(provider, agent("strategist")).run(premise)
        bible.set_concept(concept)
        emit({"type": "stage", "stage": "worldbuilder"})
        world = WorldbuilderAgent(provider, agent("worldbuilder")).run(concept)
        bible.set_world(world)
        emit({"type": "stage", "stage": "character"})
        chars = CharacterAgent(provider, agent("character")).run((concept, world))
        for ch in chars:
            bible.upsert_character(ch)
        emit({"type": "stage", "stage": "outliner"})
        outline = OutlinerAgent(provider, agent("outliner")).run((concept, world, chars))
        bible.set_outline(outline)
        for entry in outline.foreshadow_ledger:
            if not any(f.id == entry.id for f in bible.list_foreshadow()):
                bible.add_foreshadow(Foreshadow(
                    id=entry.id, description=entry.description,
                    planted_ch=_parse_ch(entry.planted_in), status=ForeshadowStatus.OPEN))
        if on_gate:
            on_gate("outline", outline)
        chapter_no = 0
    else:
        # --- RESUME: skip SETUP, load persisted bible state ---
        _outline = bible.get_outline()
        assert _outline is not None, "no outline to resume from"
        outline = _outline
        saved_concept = bible.get_concept()
        premise = premise or (saved_concept.logline if saved_concept else "")
        chapter_no = start_chapter - 1
        emit({"type": "stage", "stage": "resume", "chapter": start_chapter})

    scorer = ScorerAgent(provider, agent("scorer"))
    reviews = ReviewStore(proj)

    # --- GENERATION ---
    for arc in outline.arcs:
        for ch_out in arc.chapters:
            chapter_no += 1
            if chapter_no > target_chapters:
                break
            beat = ch_out.beats[0] if ch_out.beats else None
            assert beat is not None, f"chapter {chapter_no} has no beat"
            emit({"type": "chapter_start", "chapter": chapter_no, "title": ch_out.chapter_title})
            ctx = assemble_context(beat=beat, bible=bible, vector=vector,
                                   proj=proj, token_budget=token_budget)
            writer = WriterAgent(provider, agent("writer"))
            prose = writer.run(ctx)
            # scorer loop on chapter
            attempt = 1
            final_ok = False
            while True:
                emit({"type": "stage", "stage": "scorer", "chapter": chapter_no, "attempt": attempt})
                ok, rs = _scored(prose, "chapter",
                                 json.dumps({"prose": prose, "beat": beat.model_dump()}, ensure_ascii=False),
                                 scorer, score_min, max_retries, attempt)
                state.last_review = rs
                reviews.append(ReviewRecord(
                    chapter=chapter_no, attempt=attempt, artifact_type=rs.artifact_type,
                    overall=rs.overall, summary=rs.summary, scores=rs.scores, passed=ok,
                    timestamp=datetime.now(UTC).isoformat()))
                emit({"type": "review", "chapter": chapter_no, "attempt": attempt,
                      "passed": ok, "overall": rs.overall})
                if ok:
                    final_ok = True
                    break
                if attempt >= max_retries:
                    break
                feedback = apply_review(rs, prose)
                emit({"type": "stage", "stage": "writer_rewrite", "chapter": chapter_no, "attempt": attempt})
                prose = writer.run(type(ctx)(blocks=ctx.blocks + [f"[REWRITE NOTES] {feedback}"]))
                attempt += 1
            if not final_ok:
                approved = on_gate("chapter_review_failed", rs) if on_gate else False
                if not approved:
                    state.error = f"chapter {chapter_no} rejected after {max_retries} attempts"
                    emit({"type": "chapter_skipped", "chapter": chapter_no, "reason": state.error})
                    continue
            # continuity
            emit({"type": "stage", "stage": "continuity", "chapter": chapter_no})
            issues = ContinuityAgent(provider, agent("continuity")).run(
                (prose, json.dumps(proj.load_canonical(), ensure_ascii=False)))
            if issues:
                emit({"type": "stage", "stage": "editor", "chapter": chapter_no})
                prose = EditorAgent(provider, agent("editor")).run(prose)
            # persist
            (proj.root / "chapters" / f"{chapter_no:03d}.md").write_text(prose, encoding="utf-8")
            vector.add_chapter(chapter_no, prose)
            emit({"type": "stage", "stage": "extractor", "chapter": chapter_no})
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
            for cid, man_list in upd.mannerisms_used.items():
                ch_obj = bible.get_character(cid)
                if not ch_obj:
                    continue
                for man in man_list:
                    existing = next((m for m in ch_obj.mannerisms if m.text == man), None)
                    if existing:
                        existing.used_count += 1
                    else:
                        ch_obj.mannerisms.append(Mannerism(text=man, used_count=1))
                bible.upsert_character(ch_obj)
            for i, ke in enumerate(upd.key_events):
                bible.append_event(Event(
                    id=f"evt_{chapter_no}_{i + 1}", chapter=chapter_no, summary=ke.event,
                    characters=list(ke.affected_characters)))
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
            emit({"type": "chapter_done", "chapter": chapter_no})
            if on_gate:
                on_gate("chapter", chapter_no)
    emit({"type": "done"})
    return state
