from __future__ import annotations

import json

from pydantic import ValidationError

from novel.agents.base import Agent
from novel.models import Character, Concept, World
from novel.providers import _extract_json


class _CharacterList(Character):
    pass


class CharacterAgent(Agent[tuple[Concept, World], list[Character]]):
    name = "character"
    output_schema = list  # placeholder; see note below

    def build_messages(self, inputs: tuple[Concept, World]) -> list[dict]:
        concept, world = inputs
        schema = Character.model_json_schema()
        return [
            {"role": "system", "agent": self.name,
             "content": (
                 "Design a cast of Characters (protagonist, antagonist, supports). "
                 "Return ONLY a JSON array; every element MUST conform to this JSON schema "
                 "(id, slug, name, role, backstory, motivation, arc are REQUIRED):\n"
                 f"{json.dumps(schema, ensure_ascii=False)}")},
            {"role": "user", "agent": self.name,
             "content": f"concept:\n{concept.model_dump_json()}\n\nworld:\n{world.model_dump_json()}"},
        ]

    def run(self, inputs: tuple[Concept, World]) -> list[Character]:
        # list-typed structured output isn't a single BaseModel; call provider then parse array
        msgs = self.build_messages(inputs)
        last_err: Exception | None = None
        for _attempt in range(self.max_retries + 1):
            try:
                text = self.provider.complete(msgs, self.cfg)
                data = json.loads(_extract_json(text))
                return [Character.model_validate(c) for c in data]
            except (ValidationError, ValueError) as e:
                last_err = e
                msgs = msgs + [
                    {"role": "assistant", "content": "<invalid output>"},
                    {"role": "user", "agent": self.name,
                     "content": (
                         f"Your output was invalid: {e}. Return ONLY a JSON array in which "
                         "EVERY element has all required fields (id, slug, name, role, "
                         "backstory, motivation, arc).")},
                ]
        assert last_err is not None
        raise last_err
