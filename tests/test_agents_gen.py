from novel.agents.continuity import ContinuityAgent
from novel.agents.editor import EditorAgent
from novel.agents.writer import WriterAgent
from novel.memory.assembler import AssembledContext
from novel.providers import FakeProvider, ModelConfig


def test_writer_returns_prose():
    ctx = AssembledContext(blocks=["[Beat] event=meet", "[Character] Ara"])
    p = FakeProvider(responses={"writer": "Ara walked into the tavern."}, tag_key="agent")
    out = WriterAgent(p, ModelConfig("zhipu", "x")).run(ctx)
    assert "Ara" in out

def test_continuity_returns_issues():
    p = FakeProvider(responses={"continuity": '["Ara was in docks but beat says tavern"]'}, tag_key="agent")
    out = ContinuityAgent(p, ModelConfig("deepseek", "x")).run(("some prose", "{}"))
    assert isinstance(out, list) and out

def test_editor_polishes():
    p = FakeProvider(responses={"editor": "polished prose"}, tag_key="agent")
    assert EditorAgent(p, ModelConfig("zhipu", "x")).run("rough") == "polished prose"
