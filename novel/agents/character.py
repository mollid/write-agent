from __future__ import annotations

import json

from pydantic import ValidationError

from novel.agents.base import Agent
from novel.models import Character, Concept, World
from novel.providers import _extract_json

CHARACTER_SYSTEM = """\
You are a casting director and character psychologist. You design ensembles where every character is simultaneously a fully realised person AND a narrative function.

## Task
Design the full cast for the story defined by the Concept and World below.

## Output Schema (strict JSON array)
Return a JSON array. Every element MUST contain ALL of the following required fields:
{character_schema}

Field guidelines:
- id:        short kebab-case identifier, e.g. "prot-kira", "ant-voss"
- slug:      URL-safe, identical to id
- name:      Full in-world name
- role:      "protagonist" | "antagonist" | "deuteragonist" | "support" | "mentor" | "catalyst"
- backstory: 3–5 sentences. Include ONE formative wound and ONE secret.
- motivation: 1–2 sentences. Must be a concrete, actionable want (not a vague feeling).
- arc:       "Start state → Midpoint shift → End state" in one sentence.
- voice_note (optional): 1 sentence on speech pattern / verbal tic.
- relationships (optional): dict mapping other character ids to relationship descriptors.

## Process
1. Protagonist's want must directly collide with the World's central constraint.
2. Antagonist's motivation must be sympathetic or at least logically coherent; avoid pure evil.
3. Every support character must either (a) challenge the protagonist's worldview or (b) embody a thematic counter-argument.
4. Ensure at least one relationship will create a "loyalty fracture" by the midpoint.

## Constraints
- Do NOT use placeholder names ("Character A").
- Do NOT output anything outside the JSON array.
- Each character's backstory must be consistent with the World's era, rules, and factions.

## Output
Return ONLY the JSON array."""

CHARACTER_USER = """\
<concept>
{concept_json}
</concept>

<world>
{world_json}
</world>"""

CHARACTER_RETRY = """\
⚠ Your previous output failed validation: {error}

Return ONLY a valid JSON array. Every element MUST include all required fields: id, slug, name, role, backstory, motivation, arc. Do not add commentary."""


class _CharacterList(Character):
    pass


class CharacterAgent(Agent[tuple[Concept, World], list[Character]]):
    name = "character"
    output_schema = list  # placeholder; see note below

    def build_messages(self, inputs: tuple[Concept, World]) -> list[dict]:
        concept, world = inputs
        schema = json.dumps(Character.model_json_schema(), ensure_ascii=False)
        return [
            {"role": "system", "agent": self.name,
             "content": CHARACTER_SYSTEM.format(character_schema=schema)},
            {"role": "user", "agent": self.name,
             "content": CHARACTER_USER.format(
                 concept_json=concept.model_dump_json(),
                 world_json=world.model_dump_json(),
             )},
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
                     "content": CHARACTER_RETRY.format(error=e)},
                ]
        assert last_err is not None
        raise last_err
