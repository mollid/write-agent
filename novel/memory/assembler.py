from __future__ import annotations

from dataclasses import dataclass, field

from novel.models import ChapterBeat
from novel.project import NovelProject
from novel.store.bible import StoryBible
from novel.store.vector import VectorMemory


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


def assemble_context(
    beat: ChapterBeat, bible: StoryBible, vector: VectorMemory, proj: NovelProject, token_budget: int,
) -> AssembledContext:
    beat_block = f"[Beat] pov={beat.pov}; setting={beat.setting}; event={beat.event}; " \
                 f"turn={beat.emotional_turn}; plants={beat.plants}; payoffs={beat.payoffs}"
    char_block = _character_block(beat, bible)
    world = bible.get_world()
    world_block = f"[World] {world.model_dump_json() if world else ''}"
    recency_block = "\n".join(vector.retrieve(beat.event, k=2)) if beat.event else ""

    # priority order: beats > bible(world+character) > recency > retrieved(extra)
    candidates = [
        ("beat", beat_block),
        ("world", world_block),
        ("characters", char_block),
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
