from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from novel.agents.continuity import ContinuityAgent
from novel.agents.editor import EditorAgent
from novel.agents.scorer import ScorerAgent
from novel.agents.writer import WriterAgent
from novel.config import ModelConfig
from novel.memory.assembler import RECENT_SUMMARY_K, assemble_context, continuity_compact_view
from novel.memory.extractor import extract_updates
from novel.memory.summarizer import digest_book, summarize_arc, summarize_chapter
from novel.models import Arc, ChapterOutline, ChapterSummary, Character, ReviewRecord, ReviewScore
from novel.project import NovelProject
from novel.providers import ModelProvider
from novel.resume import is_chapter_complete
from novel.scorer_rubrics import apply_review, decide
from novel.setup_flow import _detail_arc, _plan_arc_cast, approve_stage, generate_stage, stage_done
from novel.store.bible import StoryBible
from novel.store.notes import WritingNotes
from novel.store.reviews import ReviewStore
from novel.store.summaries import SummaryStore, detect_edited_chapters, sha256_text
from novel.store.vector import VectorMemory


def _gate_result(r: bool | tuple[bool, str | None]) -> tuple[bool, str | None]:
    """Gate callbacks may return a plain bool (CLI) or (approved, feedback)
    (GUI gate_with_feedback); normalize before any truthiness test — a
    (False, ...) tuple is itself truthy and would read as approval."""
    return r if isinstance(r, tuple) else (bool(r), None)


@dataclass
class PipelineState:
    premise: str = ""
    attempts: dict[str, int] = field(default_factory=dict)
    last_review: ReviewScore | None = None
    human_overrides: dict[str, object] = field(default_factory=dict)
    error: str | None = None
    written: list[int] = field(default_factory=list)


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
    start_chapter: int = 1, min_chapter_chars: int = 50,
    planned_total: int | None = None,
    gate_every_n: int = 1,
    language: str = "en",
    chapter_target_length: int = 2500,
    arc_lookahead: int = 5,
    on_gate: Callable[[str, object], bool | tuple[bool, str | None]] | None = None,
    on_event: Callable[[dict[str, object]], None] | None = None,
) -> PipelineState:
    state = PipelineState(premise=premise)

    def emit(event: dict[str, object]) -> None:
        if on_event is not None:
            on_event(event)

    def agent(name: str) -> ModelConfig:
        return cfg_map[name]

    if start_chapter <= 1 and bible.get_outline() is None:
        # --- SETUP (one-shot auto mode; guided mode = `novel setup` approved these already) ---
        for stage, agent_name in (("concept", "strategist"), ("world", "worldbuilder"),
                                  ("characters", "character"), ("outline", "outliner")):
            emit({"type": "stage", "stage": agent_name})
            if stage_done(stage, bible):
                continue  # half-finished guided setup: only fill the gaps
            artifact = generate_stage(stage, provider=provider, cfg_map=cfg_map,
                                      bible=bible, premise=premise,
                                      target_chapters=planned_total)
            approve_stage(stage, artifact, bible)
        outline = bible.get_outline()
        assert outline is not None
        if on_gate:
            on_gate("outline", outline)
    else:
        # --- RESUME: skip SETUP, load persisted bible state ---
        outline = bible.get_outline()
        assert outline is not None, "no outline to resume from"
        saved_concept = bible.get_concept()
        premise = premise or (saved_concept.logline if saved_concept else "")
        emit({"type": "stage", "stage": "resume", "chapter": start_chapter})

    scorer = ScorerAgent(provider, agent("scorer"))
    reviews = ReviewStore(proj)
    notes = WritingNotes(proj)

    # stale tmp files from a crashed run must never be mistaken for chapters
    for stale in (proj.root / "chapters").glob(".*.md.tmp"):
        stale.unlink()

    # --- GENERATION ---
    # Flatten outline chapters by position (1..N). Position == global chapter number:
    # chapter k on disk must be written from the k-th outline chapter. On resume,
    # skip positions < start_chapter instead of restarting the outline from the top.
    summaries = SummaryStore(proj)

    def detail_next_arc() -> bool:
        """Rolling outline (spec §4.3): seed then detail the next skeleton.
        First the arc_cast gate reviews proposed NEW characters for the volume
        (feedback regenerates the proposal, bounded to 3 rounds; a plain deny
        adds nobody; an empty proposal skips the gate silently). Approved cast
        members are upserted BEFORE detailing, so the detailer's roster already
        contains them. Then the arc_detail gate reviews the DETAILED volume:
        approve persists it; feedback re-runs the detailer (≤3 rounds); a plain
        deny discards the draft and re-queues the skeleton."""
        assert outline is not None and outline.arc_plan
        skeleton = outline.arc_plan.pop(0)
        prev_name = outline.arcs[-1].arc_name if outline.arcs else ""
        prev_arc = summaries.get_arc_summary(prev_name) if prev_name else None
        existing_max = max((c.chapter_no for a in outline.arcs for c in a.chapters), default=0)
        recent = summaries.recent_chapter_summaries(upto=existing_max, k=RECENT_SUMMARY_K)

        # --- volume cast seeding ---
        emit({"type": "stage", "stage": "arc_cast", "arc": skeleton.arc_name})
        cast_feedback: list[str] = []
        new_chars: list[Character] = []
        for attempt in range(1, 4):
            proposal = _plan_arc_cast(provider, cfg_map, bible, skeleton, recent,
                                      feedback=cast_feedback)
            if not proposal:
                break  # volume works with the existing cast: no interruption
            if on_gate is None:
                new_chars = proposal  # demo/provider-driven: auto-adopt
                break
            approved, fb = _gate_result(on_gate("arc_cast", proposal))
            if approved:
                new_chars = proposal
                break
            if not fb or attempt == 3:
                emit({"type": "arc_cast_denied", "arc": skeleton.arc_name,
                      "count": len(proposal)})
                break
            cast_feedback.append(fb)
            emit({"type": "stage", "stage": "arc_cast_retry",
                  "arc": skeleton.arc_name, "attempt": attempt + 1})
        for ch in new_chars:
            bible.upsert_character(ch)
        if new_chars:
            emit({"type": "arc_cast_done", "arc": skeleton.arc_name,
                  "names": [c.name for c in new_chars]})

        # --- volume detail ---
        emit({"type": "stage", "stage": "arc_detail", "arc": skeleton.arc_name})
        feedback: list[str] = []
        arc: Arc | None = None
        for attempt in range(1, 4):
            arc = _detail_arc(provider, cfg_map, bible, skeleton, prev_arc,
                              existing_max + 1, recent, feedback=feedback)
            if on_gate is None:
                break  # demo mode: no approval flow
            approved, fb = _gate_result(on_gate("arc_detail", arc))
            if approved:
                break
            if not fb or attempt == 3:
                outline.arc_plan.insert(0, skeleton)
                emit({"type": "arc_detail_denied", "arc": skeleton.arc_name})
                return False
            feedback.append(fb)
            emit({"type": "stage", "stage": "arc_detail_retry",
                  "arc": skeleton.arc_name, "attempt": attempt + 1})
        assert arc is not None
        outline.arcs.append(arc)
        bible.set_outline(outline)
        emit({"type": "arc_detailed", "arc": skeleton.arc_name,
              "chapters": len(arc.chapters)})
        return True

    # user contract (spec §5): manual prose edits that bypassed the pipeline are
    # detected (hash mismatch) and reported — state is NOT auto-rebuilt
    for n in detect_edited_chapters(proj, summaries):
        emit({"type": "warning", "warning": "chapter_edited", "chapter": n})

    denied_arcs: set[str] = set()   # volumes the human rejected at the arc_detail gate

    def flat_chapters() -> list[tuple[str, ChapterOutline]]:
        return [(a.arc_name, c) for a in outline.arcs for c in a.chapters]

    total_outline = len(flat_chapters())
    if start_chapter > total_outline:
        state.error = (f"outline exhausted: {total_outline} chapters in outline, "
                       f"nothing to write from chapter {start_chapter}")
        return state

    def _target_note() -> str:
        if language == "zh":
            return f"[Target length] 本章目标约 {chapter_target_length} 字"
        return f"[Target length] Target ~{chapter_target_length} words for this chapter"

    def _backfill_prev_summary(chapter_no: int) -> None:
        """Lazy retry (spec §4.1): regenerate at most the immediate predecessor's
        missing summary — one bounded call per chapter cycle, no history chase."""
        if chapter_no < 2:
            return
        prev = chapter_no - 1
        try:
            if summaries.get_chapter_summary(prev) is None and \
                    is_chapter_complete(proj, reviews, prev, min_chapter_chars):
                prev_prose = (proj.root / "chapters" / f"{prev:03d}.md").read_text(encoding="utf-8")
                prev_arc = flat[prev - 1][0] if prev - 1 < len(flat) else ""
                cs = summarize_chapter(prev, prev_prose, prev_arc, provider, agent("extractor"))
                cs.prose_sha256 = sha256_text(prev_prose)
                summaries.put_chapter_summary(cs)
                emit({"type": "stage", "stage": "summary_backfill", "chapter": prev})
        except Exception:  # noqa: BLE001 - a failed backfill must not kill the run
            emit({"type": "warning", "warning": "summary_backfill_failed", "chapter": prev})

    idx = start_chapter - 1
    while True:
        flat = flat_chapters()
        if idx >= len(flat) or idx + 1 > target_chapters:
            break
        arc_name, ch_out = flat[idx]
        chapter_no = idx + 1
        while outline.arc_plan and len(flat) - (idx + 1) < arc_lookahead:
            if outline.arc_plan[0].arc_name in denied_arcs:
                break  # already rejected this run: no re-prompt, no wasted detail calls
            if not detail_next_arc():
                denied_arcs.add(outline.arc_plan[0].arc_name)
                break
            flat = flat_chapters()
        _backfill_prev_summary(chapter_no)
        if is_chapter_complete(proj, reviews, chapter_no, min_chapter_chars):
            emit({"type": "chapter_skipped", "chapter": chapter_no,
                  "reason": "already complete"})
        else:
            beats = ch_out.beats
            assert beats, f"chapter {chapter_no} has no beat"
            emit({"type": "chapter_start", "chapter": chapter_no, "title": ch_out.chapter_title,
                  "planned_total": planned_total})
            arc_sum = summaries.get_arc_summary(arc_name)
            recent = summaries.recent_chapter_summaries(upto=chapter_no - 1, k=RECENT_SUMMARY_K)
            digest = summaries.get_book_digest()
            ctx = assemble_context(
                beats=beats, bible=bible, vector=vector, proj=proj, token_budget=token_budget,
                chapter_no=chapter_no,
                arc_summary=arc_sum.summary if arc_sum else "",
                recent_summaries=[f"ch{cs.chapter_no}: {cs.summary}" for cs in recent],
                book_digest=digest.summary if digest else "",
                target_note=_target_note())
            writer = WriterAgent(provider, agent("writer"))
            prose = writer.run(ctx)
            # scorer loop on chapter
            attempt = 1
            final_ok = False
            while True:
                emit({"type": "stage", "stage": "scorer", "chapter": chapter_no, "attempt": attempt})
                ok, rs = _scored(prose, "chapter",
                                 json.dumps({"prose": prose,
                                             "beats": [b.model_dump() for b in beats]},
                                            ensure_ascii=False),
                                 scorer, score_min, max_retries, attempt)
                state.last_review = rs
                reviews.append(ReviewRecord(
                    chapter=chapter_no, attempt=attempt, artifact_type=rs.artifact_type,
                    overall=rs.overall, summary=rs.summary, scores=rs.scores, passed=ok,
                    timestamp=datetime.now(UTC).isoformat()))
                if not ok:
                    # persist the below-threshold dimensions so later chapters'
                    # writer context warns against repeating them
                    notes.add_weak(chapter_no, {
                        name: (ds.score, ds.critique)
                        for name, ds in rs.scores.items() if ds.score < score_min})
                emit({"type": "review", "chapter": chapter_no, "attempt": attempt,
                      "passed": ok, "overall": rs.overall,
                      # pass rule is EVERY dimension >= score_min: ship the
                      # per-dimension scores + threshold so the GUI log can
                      # explain why overall 82 may still fail
                      "scores": {name: ds.score for name, ds in rs.scores.items()},
                      "score_min": score_min})
                if ok:
                    final_ok = True
                    break
                if attempt >= max_retries:
                    break
                feedback = apply_review(rs, prose)
                emit({"type": "stage", "stage": "writer_rewrite", "chapter": chapter_no,
                      "attempt": attempt})
                prose = writer.run(type(ctx)(blocks=ctx.blocks + [f"[REWRITE NOTES] {feedback}"]))
                attempt += 1
            if not final_ok:
                approved = _gate_result(on_gate("chapter_review_failed", rs))[0] if on_gate \
                    else False
                if not approved:
                    state.error = f"chapter {chapter_no} rejected after {max_retries} attempts"
                    emit({"type": "chapter_skipped", "chapter": chapter_no,
                          "reason": state.error})
                    idx += 1
                    continue
                # the human shipped this failing chapter: persist a passed record
                # so resume (is_chapter_complete) treats it as complete
                reviews.append(ReviewRecord(
                    chapter=chapter_no, attempt=attempt, artifact_type=rs.artifact_type,
                    overall=rs.overall, summary=f"human override: {rs.summary}",
                    scores=rs.scores, passed=True,
                    timestamp=datetime.now(UTC).isoformat()))
            # continuity — compact view replaces the whole canonical JSON (spec §4.5)
            emit({"type": "stage", "stage": "continuity", "chapter": chapter_no})
            compact = continuity_compact_view(
                beats=beats, bible=bible,
                arc_summary=arc_sum.summary if arc_sum else "",
                recent_summaries=[f"ch{cs.chapter_no}: {cs.summary}" for cs in recent],
                book_digest=digest.summary if digest else "")
            issues = ContinuityAgent(provider, agent("continuity")).run((prose, compact))
            if issues:
                emit({"type": "stage", "stage": "editor", "chapter": chapter_no})
                prose = EditorAgent(provider, agent("editor")).run(prose)
            # extract + apply in ONE batched bible write (spec §4.4)
            emit({"type": "stage", "stage": "extractor", "chapter": chapter_no})
            involved_ids: list[str] = []
            for b in beats:
                for cid in b.characters:
                    if cid not in involved_ids:
                        involved_ids.append(cid)
            involved = [c for c in (bible.get_character(i) for i in involved_ids) if c is not None]
            upd = extract_updates(chapter_no, prose, involved, provider, agent("extractor"))
            bible.apply_chapter_updates(chapter_no, upd, beats)
            try:
                summaries.put_chapter_summary(ChapterSummary(
                    chapter_no=chapter_no, arc_name=arc_name,
                    summary=(upd.chapter_summary or prose[:300]).strip(),
                    characters_involved=list(upd.character_states.keys()),
                    threads_advanced=upd.threads_advanced,
                    prose_sha256=sha256_text(prose)))
            except Exception:  # noqa: BLE001 - a failed summary write must not kill the run
                emit({"type": "warning", "warning": "chapter_summary_write_failed",
                      "chapter": chapter_no})
            vector.add_chapter(chapter_no, prose)
            vector.add_summary("chapter", f"ch{chapter_no}", upd.chapter_summary or prose[:300])
            # atomic write last: the file's appearance is the chapter's commit point
            # (score gate, extraction, bible, summaries and memory updates are all on disk already)
            chapters_dir = proj.root / "chapters"
            tmp = chapters_dir / f".{chapter_no:03d}.md.tmp"
            tmp.write_text(prose, encoding="utf-8")
            tmp.replace(chapters_dir / f"{chapter_no:03d}.md")
            emit({"type": "chapter_done", "chapter": chapter_no, "planned_total": planned_total})
            state.written.append(chapter_no)
            if on_gate and gate_every_n > 0 and chapter_no % gate_every_n == 0:
                on_gate("chapter", chapter_no)
        # arc boundary (spec §4.1): next detailed chapter absent or in another volume
        nxt = flat[chapter_no] if chapter_no < len(flat) else None
        if nxt is None or nxt[0] != arc_name:
            try:
                if summaries.get_arc_summary(arc_name) is None:
                    arc_start = next(i + 1 for i, (an, _c) in enumerate(flat) if an == arc_name)
                    chapter_sums = [cs for cs in (
                        summaries.get_chapter_summary(n)
                        for n in range(arc_start, chapter_no + 1)) if cs]
                    if chapter_sums:
                        prev_arcs = [a for a in summaries.all_arc_summaries()
                                     if a.chapter_end < arc_start]
                        arc_sum = summarize_arc(arc_name, arc_start, chapter_no, chapter_sums,
                                                prev_arcs[-1] if prev_arcs else None,
                                                provider, agent("extractor"))
                        summaries.put_arc_summary(arc_sum)
                        digest = digest_book(summaries.all_arc_summaries(), chapter_no, arc_name,
                                             provider, agent("extractor"))
                        summaries.put_book_digest(digest)
                        emit({"type": "arc_summary_done", "arc": arc_name,
                              "chapter_end": chapter_no})
            except Exception:  # noqa: BLE001 - a failed arc summary must not kill a long run
                emit({"type": "warning", "warning": "arc_summary_failed", "arc": arc_name})
        idx += 1
    total_outline = len(flat_chapters())
    if not state.error and target_chapters > total_outline:
        state.error = (f"outline exhausted: outline has {total_outline} chapters, "
                       f"requested through chapter {target_chapters} "
                       f"(wrote {len(state.written)} this run)")
    emit({"type": "done"})
    return state
