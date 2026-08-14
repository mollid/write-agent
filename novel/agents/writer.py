from __future__ import annotations

from novel.agents.base import Agent
from novel.memory.assembler import AssembledContext


class WriterAgent(Agent[AssembledContext, str]):
    name = "writer"
    output_schema = str  # not used via complete_structured

    def build_messages(self, inputs: AssembledContext) -> list[dict]:
        return [
            {"role": "system", "agent": self.name,
             "content": "Write the chapter prose for the given beat/context. Stay in-character, honor the beat and foreshadowing. Output prose only."},
            {"role": "user", "agent": self.name, "content": inputs.text},
        ]

    def run(self, inputs: AssembledContext) -> str:
        return self.provider.complete(self.build_messages(inputs), self.cfg)
