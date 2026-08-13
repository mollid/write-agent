from __future__ import annotations

from novel.agents.base import Agent
from novel.models import Concept


class StrategistAgent(Agent[str, Concept]):
    name = "strategist"
    output_schema = Concept

    def build_messages(self, inputs: str) -> list[dict]:
        return [
            {"role": "system", "agent": self.name,
             "content": "Turn the user premise into a Concept (logline, genre, tone, themes, target_length_words, audience)."},
            {"role": "user", "agent": self.name, "content": inputs},
        ]
