from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from novel.models import ChapterBeat, ForeshadowStatus
from novel.project import NovelProject
from novel.store.bible import StoryBible
from novel.store.notes import WritingNotes
from novel.store.vector import VectorMemory

PREV_ENDING_CHARS = 600  # tail of chapter N-1 injected as a continuity reference

RECENT_SUMMARY_K = 5    # recent chapter summaries injected into writer context
OPEN_THREADS_M = 10     # max open foreshadow lines in context
_TRUNCATION_MARKER = "\n(truncated)"

_CJK_RE = re.compile(
    r"[\u3040-\u30ff\u31f0-\u31ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
    r"\u3000-\u303f\uff00-\uffef]"
)


def estimate_tokens(text: str) -> int:
    """CJK-aware and deliberately conservative: CJK chars count as 1.5 tokens,
    everything else as 4 chars per token. Over-estimating truncates earlier,
    which is safe; the old len//3 heuristic under-counted Chinese ~3x."""
    cjk = len(_CJK_RE.findall(text))
    other = len(text) - cjk
    return max(1, math.ceil(other / 4) + math.ceil(cjk * 1.5))


@dataclass
class AssembledContext:
    blocks: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    truncated: list[str] = field(default_factory=list)
    tokens: int = 0

    @property
    def text(self) -> str:
        return "\n\n".join(self.blocks)


def _character_block(beats: list[ChapterBeat], bible: StoryBible) -> str:
    """Compact character cards (spec §4.2): only characters the beats actually
    use, state + the single most recent voice sample + the 3 least-used
    mannerisms (keep suggesting low-frequency ones)."""
    seen: list[str] = []
    for beat in beats:
        for cid in beat.characters:
            if cid not in seen:
                seen.append(cid)
    lines = []
    for cid in seen:
        ch = bible.get_character(cid)
        if not ch:
            continue
        last_voice = ""
        if ch.voice_fingerprint:
            def _no(key: str) -> int:
                s = key.rsplit("_", 1)[-1]
                return int(s) if s.isdigit() else -1
            last_key = max(ch.voice_fingerprint, key=_no)
            last_voice = ch.voice_fingerprint[last_key]
        mans = sorted(ch.mannerisms, key=lambda m: m.used_count)[:3]  # suggest low-frequency
        lines.append(
            f"[Character {ch.name}] role={ch.role}; state={ch.state.model_dump_json()}; "
            f"voice={last_voice}; suggested_mannerisms="
            f"{[m.text for m in mans]}; last_updated_chapter={ch.last_updated_chapter}"
        )
    return "\n".join(lines)


def prev_ending_block(proj: NovelProject, chapter_no: int | None) -> str:
    """Tail of the previous chapter, read straight from disk — the vector
    recency hook cannot be trusted to return it (hash embeddings carry no
    semantics), yet the ending is the strongest continuity/style anchor."""
    if not chapter_no or chapter_no < 2:
        return ""
    f = proj.root / "chapters" / f"{chapter_no - 1:03d}.md"
    if not f.is_file():
        return ""
    tail = f.read_text(encoding="utf-8").strip()[-PREV_ENDING_CHARS:]
    if not tail:
        return ""
    return f"[Previous chapter ending — continue style, POV and plot naturally]\n{tail}"


def style_directives_block(notes: WritingNotes) -> str:
    lines = [f"- ({n.source}) {n.text}" for n in notes.recent_feedback()]
    if not lines:
        return ""
    return "[Style directives — accumulated human approvals; obey throughout]\n" + "\n".join(lines)


def weak_spots_block(notes: WritingNotes) -> str:
    chapters: dict[str, list[int]] = {}
    latest: dict[str, str] = {}
    for ch, dims in sorted(notes.weak_by_chapter().items()):
        for dim, wd in dims.items():
            chapters.setdefault(dim, []).append(ch)
            latest[dim] = wd.critique or "—"
    if not chapters:
        return ""
    lines = [f"- {dim}: failed in ch {', '.join(map(str, chs))}; latest critique: {latest[dim]}"
             for dim, chs in chapters.items()]
    return "[Known weak spots — recent review failures; avoid repeating]\n" + "\n".join(lines)


def threads_block(beats: list[ChapterBeat], bible: StoryBible, cap: int = OPEN_THREADS_M) -> str:
    """Open-foreshadow lines, capped at `cap`; threads mentioned by the beats
    (event/plants/payoffs/characters text) sort first (spec §4.2)."""
    open_fs = [f for f in bible.list_foreshadow()
               if f.status != ForeshadowStatus.PAID_OFF]
    if not open_fs:
        return ""
    beat_text = " ".join([*(b.event for b in beats), *(p for b in beats for p in b.plants),
                          *(p for b in beats for p in b.payoffs),
                          *(cid for b in beats for cid in b.characters)])
    open_fs.sort(key=lambda f: (0 if (f.description and f.description in beat_text) else 1,
                                f.planted_ch if f.planted_ch is not None else 0))
    selected = open_fs[:cap]
    lines = [f"- {f.description} (planted ch{f.planted_ch})" for f in selected]
    if len(open_fs) > cap:
        lines.append(f"- (+{len(open_fs) - cap} more open threads omitted)")
    return "[Threads] open foreshadowing\n" + "\n".join(lines)


def assemble_context(
    beats: list[ChapterBeat], bible: StoryBible, vector: VectorMemory, proj: NovelProject,
    token_budget: int, chapter_no: int | None = None, *,
    arc_summary: str = "", recent_summaries: list[str] | None = None,
    book_digest: str = "", target_note: str = "",
) -> AssembledContext:
    beat_block = "[Beats — cover in order]\n" + "\n".join(
        f"{i + 1}. pov={b.pov}; setting={b.setting}; event={b.event}; "
        f"turn={b.emotional_turn}; plants={b.plants}; payoffs={b.payoffs}"
        for i, b in enumerate(beats))
    char_block = _character_block(beats, bible)
    world = bible.get_world()
    world_block = f"[World] {world.model_dump_json() if world else ''}"
    recency_block = ("\n".join(vector.retrieve(beats[0].event, k=2))
                     if beats and beats[0].event else "")
    events_block = "\n".join(e.model_dump_json() for e in bible.list_events(last=3))
    threads = threads_block(beats, bible)
    notes = WritingNotes(proj)
    prev_block = prev_ending_block(proj, chapter_no)
    style_block = style_directives_block(notes)
    weak_block = weak_spots_block(notes)
    arc_block = f"[Arc summary — current volume so far]\n{arc_summary}" if arc_summary else ""
    recent_block = ""
    if recent_summaries:
        recent_block = ("[Recent chapter summaries — what happened lately]\n"
                        + "\n".join(f"- {line}" for line in recent_summaries))
    digest_block = f"[Book digest — whole story so far]\n{book_digest}" if book_digest else ""

    # priority ladder (spec §4.2): core never truncated; lower blocks truncated, not dropped
    candidates: list[tuple[str, str, bool]] = [
        ("target_note", target_note, True),
        ("beat", beat_block, True),
        ("prev_ending", prev_block, True),
        ("arc_summary", arc_block, False),
        ("recent_summaries", recent_block, False),
        ("book_digest", digest_block, False),
        ("characters", char_block, False),
        ("threads", threads, False),
        ("world", world_block, False),
        ("style_notes", style_block, False),
        ("weak_spots", weak_block, False),
        ("events", events_block, False),
        ("recency", recency_block, False),
    ]
    ctx = AssembledContext()
    for name, block, core in candidates:
        if not block:
            continue
        cost = estimate_tokens(block)
        if ctx.tokens + cost <= token_budget:
            ctx.blocks.append(block)
            ctx.tokens += cost
            continue
        if core:
            ctx.blocks.append(block)   # core always ships, even over budget
            ctx.tokens += cost
            continue
        remaining = token_budget - ctx.tokens
        if remaining <= 1:
            ctx.dropped.append(name)
            continue
        # worst case is all-CJK at 1.5 tokens/char → chars = remaining/1.5 (marker margin: -10)
        max_chars = max(0, int(remaining / 1.5) - 10)
        cut = block[:max_chars] + _TRUNCATION_MARKER
        cut_cost = estimate_tokens(cut)
        if cut_cost <= remaining:
            ctx.blocks.append(cut)
            ctx.tokens += cut_cost
            ctx.truncated.append(name)
        else:
            ctx.dropped.append(name)
    return ctx


def continuity_compact_view(beats: list[ChapterBeat], bible: StoryBible, arc_summary: str,
                            recent_summaries: list[str], book_digest: str) -> str:
    """Compact continuity reference (spec §4.5): replaces the whole canonical
    JSON the continuity agent used to receive — the single largest token waste
    at 100+ chapter scale."""
    parts = [p for p in [
        _character_block(beats, bible),
        threads_block(beats, bible),
        f"[Arc summary]\n{arc_summary}" if arc_summary else "",
        "[Recent chapter summaries]\n" + "\n".join(f"- {line}" for line in recent_summaries)
        if recent_summaries else "",
        f"[Book digest]\n{book_digest}" if book_digest else "",
    ] if p]
    return "\n\n".join(parts)
