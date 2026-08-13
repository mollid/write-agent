from __future__ import annotations

from novel.agents.base import Agent


class EditorAgent(Agent[str, str]):
    name = "editor"
    output_schema = str

    def build_messages(self, inputs: str) -> list[dict]:
        return [
            {"role": "system", "agent": self.name,
             "content": "Lightly polish prose for flow and clarity without changing events. Output prose only."},
            {"role": "user", "agent": self.name, "content": inputs},
        ]

    def run(self, inputs: str) -> str:
        return self.provider.complete(self.build_messages(inputs), self.cfg)
