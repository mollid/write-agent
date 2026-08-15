from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import ValidationError

from novel.config import ModelConfig
from novel.providers import ModelProvider

I = TypeVar("I")
O = TypeVar("O")


def feedback_message(agent_name: str, feedback: list[str]) -> dict:
    return {
        "role": "user",
        "agent": agent_name,
        "content": "[USER FEEDBACK — apply ALL of these to your output]\n"
        + "\n".join(f"- {f}" for f in feedback),
    }


class Agent(Generic[I, O]):
    name: str = "agent"
    output_schema: type
    max_retries: int = 2

    def __init__(self, provider: ModelProvider, cfg: ModelConfig) -> None:
        self.provider = provider
        self.cfg = cfg

    def build_messages(self, inputs: I) -> list[dict]:
        raise NotImplementedError

    def run(self, inputs: I, *, feedback: list[str] | None = None) -> O:
        messages = self.build_messages(inputs)
        if feedback:
            messages = messages + [feedback_message(self.name, feedback)]
        last_err: Exception | None = None
        for _attempt in range(self.max_retries + 1):
            try:
                result = self.provider.complete_structured(messages, self.output_schema, self.cfg)
                return result  # type: ignore[return-value]
            except ValidationError as e:
                last_err = e
                messages = messages + [
                    {"role": "assistant", "content": "<invalid output>"},
                    {
                        "role": "user",
                        "agent": self.name,
                        "content": f"Your output failed validation: {e}. Fix it and return valid JSON only.",
                    },
                ]
        assert last_err is not None
        raise last_err
