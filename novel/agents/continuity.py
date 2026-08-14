from __future__ import annotations

import json

from novel.agents.base import Agent
from novel.providers import _extract_json


class ContinuityAgent(Agent[tuple[str, str], list[str]]):
    name = "continuity"
    output_schema = str

    def build_messages(self, inputs: tuple[str, str]) -> list[dict]:
        prose, bible_json = inputs
        return [
            {"role": "system", "agent": self.name,
             "content": "Find continuity issues (contradictions, broken foreshadowing, character voice drift) between the chapter and the bible. Return a JSON array of issue strings."},
            {"role": "user", "agent": self.name,
             "content": f"bible:\n{bible_json}\n\nchapter:\n{prose}"},
        ]

    def run(self, inputs: tuple[str, str]) -> list[str]:
        msgs = self.build_messages(inputs)
        last_err: Exception | None = None
        for _attempt in range(self.max_retries + 1):
            try:
                text = self.provider.complete(msgs, self.cfg)
                data = json.loads(_extract_json(text))
                return [str(x) for x in data]
            except ValueError as e:
                last_err = e
                msgs = msgs + [
                    {"role": "assistant", "content": "<invalid output>"},
                    {"role": "user", "agent": self.name,
                     "content": f"Your output was invalid JSON: {e}. Return ONLY a JSON array of issue strings."},
                ]
        assert last_err is not None
        raise last_err
