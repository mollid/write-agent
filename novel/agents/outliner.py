from __future__ import annotations

from novel.agents.base import Agent
from novel.models import Character, Concept, Outline, World

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
