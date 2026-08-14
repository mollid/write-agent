from __future__ import annotations

from novel.agents.base import Agent
from novel.models import Character, Concept, Outline, World


class OutlinerAgent(Agent[tuple[Concept, World, list[Character]], Outline]):
    name = "outliner"
    output_schema = Outline

    def build_messages(self, inputs: tuple[Concept, World, list[Character]]) -> list[dict]:
        concept, world, chars = inputs
        roster = "\n".join(f"- {c.id} ({c.name}): {c.role}" for c in chars)
        return [
            {"role": "system", "agent": self.name,
             "content": (
                 "Produce an Outline: arcs -> chapters -> beats. Each beat has pov, setting, "
                 "event, emotional_turn, characters[], plants[], payoffs[]. "
                 "CRITICAL: beat.pov and beat.characters MUST use the character `id` EXACTLY "
                 "as listed in the roster below (never the name, and never a non-roster figure); "
                 "only include roster characters. Ensure foreshadowing plants have matching "
                 "payoffs across chapters."
             )},
            {"role": "user", "agent": self.name,
             "content": f"concept:\n{concept.model_dump_json()}\nworld:\n{world.model_dump_json()}\n"
                        f"characters (id (name): role):\n{roster}"},
        ]
