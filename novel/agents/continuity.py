from __future__ import annotations

import json

from novel.agents.base import Agent


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
        text = self.provider.complete(self.build_messages(inputs), self.cfg)
        data = json.loads(text)
        return [str(x) for x in data]
