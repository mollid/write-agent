from __future__ import annotations

from dataclasses import dataclass, field

from novel.models import ChapterBeat, ForeshadowStatus
from novel.project import NovelProject
from novel.store.bible import StoryBible
from novel.store.notes import WritingNotes
from novel.store.vector import VectorMemory

PREV_ENDING_CHARS = 600  # tail of chapter N-1 injected as a continuity reference


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 3)


@dataclass
class AssembledContext:
    blocks: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    tokens: int = 0

    @property
    def text(self) -> str:
        return "\n\n".join(self.blocks)


def _character_block(beat: ChapterBeat, bible: StoryBible) -> str:
    lines = []
    for cid in beat.characters:
        ch = bible.get_character(cid)
        if not ch:
            continue
        # pick the lowest-frequency mannerism not yet overused
        man = sorted(ch.mannerisms, key=lambda m: m.used_count)[:1]
        man_txt = man[0].text if man else ""
        lines.append(
            f"[Character {ch.name}] role={ch.role}; state={ch.state.model_dump_json()}; "
            f"voice={ch.voice_fingerprint}; suggested_mannerism={man_txt}"
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


def assemble_context(
    beat: ChapterBeat, bible: StoryBible, vector: VectorMemory, proj: NovelProject, token_budget: int,
    chapter_no: int | None = None,
) -> AssembledContext:
    beat_block = f"[Beat] pov={beat.pov}; setting={beat.setting}; event={beat.event}; " \
                 f"turn={beat.emotional_turn}; plants={beat.plants}; payoffs={beat.payoffs}"
    char_block = _character_block(beat, bible)
    world = bible.get_world()
    world_block = f"[World] {world.model_dump_json() if world else ''}"
    recency_block = "\n".join(vector.retrieve(beat.event, k=2)) if beat.event else ""
    events_block = "\n".join(e.model_dump_json() for e in bible.list_events()[-3:])
    threads_block = "\n".join(
        f"- {f.description} (planted ch{f.planted_ch})"
        for f in bible.list_foreshadow() if f.status != ForeshadowStatus.PAID_OFF
    )
    notes = WritingNotes(proj)
    prev_block = prev_ending_block(proj, chapter_no)
    style_block = style_directives_block(notes)
    weak_block = weak_spots_block(notes)

    # priority order: beats > prev-ending > bible(world+character) > writing
    # memory(style+weak) > bible(events+threads) > recency > retrieved(extra)
    candidates = [
        ("beat", beat_block),
        ("prev_ending", prev_block),
        ("world", world_block),
        ("characters", char_block),
        ("style_notes", style_block),
        ("weak_spots", weak_block),
        ("events", events_block),
        ("threads", threads_block),
        ("recency", recency_block),
    ]
    ctx = AssembledContext()
    for name, block in candidates:
        if not block:
            continue
        cost = estimate_tokens(block)
        if ctx.tokens + cost <= token_budget:
            ctx.blocks.append(block)
            ctx.tokens += cost
        else:
            ctx.dropped.append(name)
    return ctx
