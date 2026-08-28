"""Orchestrator agent: structured decision over an authoritative plan (spec §4.2)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from novel.agents.orchestrator import (
    ChatAction,
    OrchestratorAgent,
    OrchestratorDecision,
    OrchestratorInput,
)
from novel.config import ModelConfig
from novel.providers import FakeProvider
from novel.runtime import AGENT_NAMES, demo_provider

CFG = ModelConfig("demo", "fake")


def _input() -> OrchestratorInput:
    return OrchestratorInput(history_tail=[{"role": "user", "text": "hi"}],
                             plan_json='{"steps": [], "next_action": {"type": "none"}, "available_actions": []}',
                             user_message="继续")


class _Recording(FakeProvider):
    """Capture the message dicts the agent builds."""

    def __init__(self) -> None:
        super().__init__({"orchestrator": OrchestratorDecision(reply="ok", action=None)})
        self.seen: list[list[dict]] = []

    def complete_structured(self, messages, schema, cfg, *, seed=None):
        self.seen.append(messages)
        return super().complete_structured(messages, schema, cfg, seed=seed)


def test_decision_passthrough() -> None:
    decision = OrchestratorDecision(reply="好的。", action=ChatAction(type="write_chapters", args={"n": 3}))
    agent = OrchestratorAgent(FakeProvider({"orchestrator": decision}), CFG)
    out = agent.run(_input())
    assert out == decision


def test_messages_carry_agent_tag_and_plan() -> None:
    provider = _Recording()
    OrchestratorAgent(provider, CFG).run(_input())
    assert len(provider.seen) >= 1
    msgs = provider.seen[0]
    assert all(m.get("agent") == "orchestrator" for m in msgs)
    assert any('"next_action"' in str(m.get("content", "")) for m in msgs)  # plan embedded
    assert msgs[-1]["role"] == "user" and msgs[-1]["content"] == "继续"


def test_system_prompt_renders_json_template_single_braces() -> None:
    """占位符替换是 .replace(),模板必须用单花括号,否则 {{...}} 原样泄漏给模型。"""
    provider = _Recording()
    OrchestratorAgent(provider, CFG).run(_input())
    system = str(provider.seen[0][0]["content"])
    assert "{{" not in system
    assert '{"reply"' in system


def test_invalid_action_shape_exhausts_retries() -> None:
    canned = {"reply": "ok", "action": {"type": "write_chapters", "args": 123}}  # args must be dict
    agent = OrchestratorAgent(FakeProvider({"orchestrator": canned}), CFG)
    with pytest.raises(ValidationError):
        agent.run(_input())


def test_agent_names_and_demo_canned() -> None:
    assert "orchestrator" in AGENT_NAMES
    provider = demo_provider()
    out = provider.complete_structured(
        [{"role": "user", "agent": "orchestrator", "content": "x"}],
        OrchestratorDecision, CFG)
    assert isinstance(out, OrchestratorDecision)
