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
