import pytest
from pydantic import BaseModel

from novel.models import Concept
from novel.providers import FakeProvider, ModelConfig


class _Msg(BaseModel):
    text: str

def test_fake_provider_returns_canned_structured():
    canned = Concept(logline="x", genre="g", tone="t", themes=[], target_length_words=100, audience="a")
    p = FakeProvider(responses={"strategist": canned}, tag_key="agent")
    out = p.complete_structured(messages=[{"role": "user", "agent": "strategist", "content": "..."}],
                                schema=Concept, cfg=ModelConfig("zhipu", "glm-4-plus"))
    assert out == canned

def test_fake_provider_complete_returns_string():
    p = FakeProvider(responses={"writer": "chapter prose text"}, tag_key="agent")
    out = p.complete(messages=[{"role": "user", "agent": "writer", "content": "..."}],
                     cfg=ModelConfig("zhipu", "glm-4-plus"))
    assert out == "chapter prose text"

def test_fake_provider_missing_raises():
    p = FakeProvider(responses={}, tag_key="agent")
    with pytest.raises(KeyError):
        p.complete_structured(messages=[{"role": "user", "agent": "x", "content": ""}],
                              schema=Concept, cfg=ModelConfig("zhipu", "x"))
