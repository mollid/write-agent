from __future__ import annotations

from novel.agents.base import Agent
from novel.models import Character, Concept, Outline, World


class OutlinerAgent(Agent[tuple[Concept, World, list[Character]], Outline]):
    name = "outliner"
    output_schema = Outline

    def build_messages(self, inputs: tuple[Concept, World, list[Character]]) -> list[dict]:
        concept, world, chars = inputs
        roster = ", ".join(c.name for c in chars)
        return [
            {"role": "system", "agent": self.name,
             "content": "Produce an Outline: arcs -> chapters -> beats. Each beat has pov, setting, event, emotional_turn, characters, plants[], payoffs[]. Ensure foreshadowing plants have matching payoffs across chapters."},
            {"role": "user", "agent": self.name,
             "content": f"concept:\n{concept.model_dump_json()}\nworld:\n{world.model_dump_json()}\ncharacters: {roster}"},
        ]
