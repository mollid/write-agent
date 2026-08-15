"""Guided setup flow: stage generation, feedback threading, persistence."""
from __future__ import annotations

from novel.config import ModelConfig
from novel.project import NovelProject
from novel.providers import FakeProvider
from novel.runtime import AGENT_NAMES, demo_provider
from novel.setup_flow import SETUP_STAGES, approve_stage, generate_stage, stage_done
from novel.store.bible import StoryBible


def _proj_bible(tmp_path):
    proj = NovelProject.scaffold("n", genre="fantasy", root=tmp_path)
    return proj, StoryBible(proj)


def _cfg_map() -> dict[str, ModelConfig]:
    return {name: ModelConfig("zhipu", "x") for name in AGENT_NAMES}


class _RecordingProvider:
    """FakeProvider wrapper that records the messages sent for each agent."""

    def __init__(self) -> None:
        self._inner: FakeProvider = demo_provider()
        self.messages: list[tuple[str, list[dict]]] = []

    def complete(self, messages, cfg, *, seed=None):  # pragma: no cover
        self.messages.append(("raw", messages))
        return self._inner.complete(messages, cfg, seed=seed)

    def complete_structured(self, messages, schema, cfg, *, seed=None):
        agent = str(next(m.get("agent", "?") for m in messages if "agent" in m))
        self.messages.append((agent, messages))
        return self._inner.complete_structured(messages, schema, cfg, seed=seed)


def test_stage_done_progression(tmp_path):
    _proj, bible = _proj_bible(tmp_path)
    assert [stage_done(s, bible) for s in SETUP_STAGES] == [False, False, False, False]
    concept = generate_stage("concept", provider=demo_provider(), cfg_map=_cfg_map(),
                             bible=bible, premise="a thief")
    approve_stage("concept", concept, bible)
    assert stage_done("concept", bible) and not stage_done("world", bible)
    world = generate_stage("world", provider=demo_provider(), cfg_map=_cfg_map(), bible=bible)
    approve_stage("world", world, bible)
    chars = generate_stage("characters", provider=demo_provider(), cfg_map=_cfg_map(), bible=bible)
    approve_stage("characters", chars, bible)
    assert stage_done("characters", bible)
    outline = generate_stage("outline", provider=demo_provider(), cfg_map=_cfg_map(), bible=bible)
    approve_stage("outline", outline, bible)
    assert all(stage_done(s, bible) for s in SETUP_STAGES)
    assert bible.get_outline() is not None and bible.get_concept() is not None
    assert bible.get_world() is not None and bible.all_characters()


def test_feedback_threaded_into_agent_messages(tmp_path):
    _proj, bible = _proj_bible(tmp_path)
    provider = _RecordingProvider()
    generate_stage("concept", provider=provider, cfg_map=_cfg_map(), bible=bible,
                   premise="a thief", feedback=["主角改成女性", "基调更黑暗"])
    (agent, messages), = provider.messages
    assert agent == "strategist"
    assert "主角改成女性" in messages[-1]["content"]
    assert "基调更黑暗" in messages[-1]["content"]


def test_unknown_stage_raises(tmp_path):
    import pytest
    _proj, bible = _proj_bible(tmp_path)
    with pytest.raises(ValueError):
        stage_done("nope", bible)
    with pytest.raises(ValueError):
        generate_stage("nope", provider=demo_provider(), cfg_map=_cfg_map(), bible=bible)
