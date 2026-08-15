from pydantic import BaseModel

from novel.agents.base import Agent
from novel.providers import FakeProvider, ModelConfig


class Out(BaseModel):
    summary: str

class EchoAgent(Agent[str, Out]):
    name = "echo"
    output_schema = Out
    def build_messages(self, inputs: str) -> list[dict]:
        return [{"role": "user", "agent": self.name, "content": inputs}]

def test_agent_runs_with_fake_provider():
    p = FakeProvider(responses={"echo": Out(summary="hi")}, tag_key="agent")
    a = EchoAgent(provider=p, cfg=ModelConfig("zhipu", "x"))
    assert a.run("hello").summary == "hi"

def test_agent_retries_on_bad_structured_then_succeeds():
    # first call returns invalid dict (missing 'summary'), second returns valid
    class SeqProvider(FakeProvider):
        def __init__(self): super().__init__({}, tag_key="agent"); self.calls = 0
        def complete_structured(self, messages, schema, cfg, *, seed=None):
            self.calls += 1
            if self.calls == 1:
                return schema.model_validate({})  # invalid (missing field) -> will fail validation downstream
            return Out(summary="ok")
    p = SeqProvider()
    a = EchoAgent(provider=p, cfg=ModelConfig("zhipu", "x"))
    out = a.run("x")
    assert out.summary == "ok" and p.calls == 2

def test_run_appends_feedback_message():
    from pydantic import BaseModel

    from novel.agents.base import Agent
    from novel.config import ModelConfig

    class Out(BaseModel):
        text: str = "ok"

    class Dummy(Agent[str, Out]):
        name = "dummy"
        output_schema = Out

        def build_messages(self, inputs: str) -> list[dict]:
            return [{"role": "user", "agent": "dummy", "content": inputs}]

    seen: list[list[dict]] = []

    class Recording:
        def complete(self, messages, cfg, *, seed=None):  # pragma: no cover - unused path
            raise NotImplementedError

        def complete_structured(self, messages, schema, cfg, *, seed=None):
            seen.append(messages)
            return schema(text="ok")

    Dummy(Recording(), ModelConfig("x", "y")).run("hello", feedback=["第一版不行", "主角改成女性"])
    assert len(seen) == 1
    last = seen[0][-1]
    assert last["role"] == "user"
    assert "USER FEEDBACK" in last["content"]
    assert "第一版不行" in last["content"] and "主角改成女性" in last["content"]
    # no feedback -> identical messages as before
    Dummy(Recording(), ModelConfig("x", "y")).run("hello")
    assert len(seen) == 2 and seen[1] == seen[0][:1]
