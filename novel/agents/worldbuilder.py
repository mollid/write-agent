from __future__ import annotations

from novel.agents.base import Agent
from novel.models import Concept, World


class WorldbuilderAgent(Agent[Concept, World]):
    name = "worldbuilder"
    output_schema = World

    def build_messages(self, inputs: Concept) -> list[dict]:
        return [
            {"role": "system", "agent": self.name,
             "content": "Build a World (setting, era, rules, power_system, factions, locations, constraints) consistent with the Concept."},
            {"role": "user", "agent": self.name, "content": inputs.model_dump_json()},
        ]
