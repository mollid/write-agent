"""SettingEditorAgent: dynamic-schema targeted rewrite of a bible section."""
from __future__ import annotations

from novel.agents.base import Agent
from novel.agents.setting_editor import SettingEditInput, SettingEditorAgent
from novel.models import World
from novel.providers import FakeProvider, ModelConfig

CFG = ModelConfig("zhipu", "x")


def test_agent_attributes() -> None:
    agent = SettingEditorAgent(FakeProvider({}), CFG, World)
    assert agent.name == "setting_editor"
    assert agent.output_schema is World


def test_prompt_carries_current_instruction_history_and_rules() -> None:
    captured: list[list[dict]] = []

    class Spy(Agent[SettingEditInput, World]):
        name = "setting_editor"
        output_schema = World

        def build_messages(self, inputs: SettingEditInput) -> list[dict]:
            msgs = SettingEditorAgent.build_messages(self, inputs)  # type: ignore[arg-type]
            captured.append(msgs)
            return msgs

    agent = Spy(FakeProvider({"setting_editor": World(setting="x")}), CFG)
    agent.run(SettingEditInput(current_json='{"setting": "old"}', instruction="让世界更冷",
                                history=[("加一个沙漠", "已应用")]))
    text = "\n".join(m["content"] for m in captured[0])
    assert '{"setting": "old"}' in text
    assert "让世界更冷" in text
    assert "加一个沙漠" in text
    assert "逐字保留" in text  # preservation rule stated in prompt


def test_run_returns_schema_instance() -> None:
    world = World(setting="changed", rules=["ice"])
    agent = SettingEditorAgent(FakeProvider({"setting_editor": world}), CFG, World)
    out = agent.run(SettingEditInput(current_json='{"setting": "old"}', instruction="改",
                                     history=[]))
    assert isinstance(out, World)
    assert out.rules == ["ice"]
