from __future__ import annotations

import json

from novel.agents.base import Agent
from novel.models import Character, Concept, World


class _CharacterList(Character):
    pass


class CharacterAgent(Agent[tuple[Concept, World], list[Character]]):
    name = "character"
    output_schema = list  # placeholder; see note below

    def build_messages(self, inputs: tuple[Concept, World]) -> list[dict]:
        concept, world = inputs
        return [
            {"role": "system", "agent": self.name,
             "content": "Design a cast of Characters (protagonist, antagonist, supports) with backstory, motivation, arc, voice_fingerprint, mannerisms. Return a JSON array."},
            {"role": "user", "agent": self.name,
             "content": f"concept:\n{concept.model_dump_json()}\n\nworld:\n{world.model_dump_json()}"},
        ]

    def run(self, inputs: tuple[Concept, World]) -> list[Character]:
        # list-typed structured output isn't a single BaseModel; call provider then parse array
        msgs = self.build_messages(inputs)
        text = self.provider.complete(msgs, self.cfg)
        data = json.loads(text)
        return [Character.model_validate(c) for c in data]
