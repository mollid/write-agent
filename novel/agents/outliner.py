from __future__ import annotations

from dataclasses import dataclass

from novel.agents.base import Agent
from novel.models import Character, Concept, Event, Foreshadow, Outline, World

OUTLINER_SYSTEM = """\
You are a story architect who thinks in three-act structure, Save-the-Cat beats, and scene/sequel rhythm. You are obsessive about foreshadowing integrity.

## Task
Produce a hierarchical **Outline**: arcs → chapters → beats.

## Output Schema (strict JSON)
{
  "arcs": [
    {
      "arc_name": "Act I – ...",
      "chapters": [
        {
          "chapter_no": 1,
          "chapter_title": "",
          "beats": [
            {
              "beat_id": "c01-b01",
              "pov": "<character_id>",
              "setting": "<location from World>",
              "event": "What happens, 1–2 sentences",
              "emotional_turn": "Emotional shift: X → Y",
              "characters": ["<character_id>", "..."],
              "plants": ["foreshadow_id"],
              "payoffs": ["foreshadow_id"]
            }
          ]
        }
      ]
    }
  ],
  "foreshadow_ledger": [
    {"id": "fs-01", "planted_in": "c01-b03", "paid_off_in": "c14-b02", "description": ""}
  ]
}

## Critical Rules
1. **ID discipline**: `pov` and every entry in `characters` MUST be a character id from the roster below. NEVER use a character's name, role label, or any figure not in the roster.
2. **Foreshadowing integrity**: Every id in any beat's `plants` MUST appear in `foreshadow_ledger` AND have a corresponding `payoffs` entry in a later beat. No orphan plants. No payoffs without a plant.
3. **POV distribution**: Protagonist gets ≥ 60 % of beats. No character appears in a beat they have no narrative reason to attend.
4. **Pacing**: Alternate high-intensity beats with reflective beats; no more than 3 consecutive action beats.
5. **Escalation**: Each act's climax must raise stakes beyond the previous act's climax.

## Roster (authoritative character ids)
{roster_block}

## Output
Return ONLY the JSON object."""

OUTLINER_USER = """\
<concept>
{concept_json}
</concept>

<world>
{world_json}
</world>

<characters>
{roster_block}
</characters>"""


class OutlinerAgent(Agent[tuple[Concept, World, list[Character]], Outline]):
    name = "outliner"
    output_schema = Outline

    def build_messages(self, inputs: tuple[Concept, World, list[Character]]) -> list[dict]:
        concept, world, chars = inputs
        roster_block = "\n".join(f"- {c.id} ({c.name}): {c.role}" for c in chars)
        return [
            # OUTLINER_SYSTEM carries literal JSON-schema braces, so inject via str.replace.
            {"role": "system", "agent": self.name,
             "content": OUTLINER_SYSTEM.replace("{roster_block}", roster_block)},
            {"role": "user", "agent": self.name,
             "content": OUTLINER_USER.format(
                 concept_json=concept.model_dump_json(),
                 world_json=world.model_dump_json(),
                 roster_block=roster_block,
             )},
        ]


OUTLINER_EXTEND_SYSTEM_EXTRA = """\

## Continuation Mode
You are EXTENDING an existing outline, not rewriting it.
- Number new chapters starting at {next_chapter_no} consecutively ({n_chapters} chapters total).
- Continue existing arcs or open a new one — but NEVER restate or renumber existing chapters.
- Pay off or advance the open foreshadows listed below when natural.
- Every `plants` id must appear in `foreshadow_ledger`; ids continue after existing ledger ids.
"""

OUTLINER_EXTEND_USER = """\
<concept>
{concept_json}
</concept>

<world>
{world_json}
</world>

<characters>
{roster_block}
</characters>

<existing_outline_tail>
{tail_block}
</existing_outline_tail>

<recent_events>
{events_block}
</recent_events>

<open_foreshadows>
{foreshadows_block}
</open_foreshadows>

Extend the outline by {n_chapters} new chapter(s), numbered from {next_chapter_no}."""


@dataclass
class OutlineExtendInput:
    concept: Concept
    world: World
    characters: list[Character]
    current: Outline
    recent_events: list[Event]
    open_foreshadows: list[Foreshadow]
    n_chapters: int


class OutlinerExtendAgent(Agent[OutlineExtendInput, Outline]):
    name = "outliner"
    output_schema = Outline

    def build_messages(self, inputs: OutlineExtendInput) -> list[dict]:
        roster_block = "\n".join(f"- {c.id} ({c.name}): {c.role}" for c in inputs.characters)
        tail = [c for a in inputs.current.arcs for c in a.chapters][-5:]
        tail_block = "\n".join(
            f"- ch{c.chapter_no}「{c.chapter_title}」: "
            + "; ".join(b.event for b in c.beats) for c in tail)
        events_block = "\n".join(f"- ch{e.chapter}: {e.summary}" for e in inputs.recent_events[-10:]) \
            or "(none)"
        foreshadows_block = "\n".join(f"- {f.id}: {f.description}" for f in inputs.open_foreshadows) \
            or "(none)"
        existing_max = max((c.chapter_no for a in inputs.current.arcs for c in a.chapters),
                           default=0)
        next_no = existing_max + 1
        system = (OUTLINER_SYSTEM + OUTLINER_EXTEND_SYSTEM_EXTRA
                  .replace("{next_chapter_no}", str(next_no))
                  .replace("{n_chapters}", str(inputs.n_chapters))) \
            .replace("{roster_block}", roster_block)
        user = OUTLINER_EXTEND_USER.format(
            concept_json=inputs.concept.model_dump_json(),
            world_json=inputs.world.model_dump_json(),
            roster_block=roster_block,
            tail_block=tail_block or "(none)",
            events_block=events_block,
            foreshadows_block=foreshadows_block,
            n_chapters=inputs.n_chapters,
            next_chapter_no=next_no,
        )
        return [
            {"role": "system", "agent": self.name, "content": system},
            {"role": "user", "agent": self.name, "content": user},
        ]
