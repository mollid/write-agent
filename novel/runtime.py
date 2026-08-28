"""Shared runtime helpers for CLI and GUI: provider selection (demo vs live)."""
from __future__ import annotations

import os

from novel.config import ProjectConfig
from novel.models import Arc
from novel.providers import FakeProvider, ModelProvider

AGENT_NAMES = [
    "strategist", "worldbuilder", "character", "outliner", "writer",
    "continuity", "editor", "scorer", "extractor", "setting_editor", "orchestrator",
]


def is_live_mode() -> bool:
    return os.environ.get("NOVEL_LIVE") == "1"


_PROXY_ENV_VARS = ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy",
                   "ALL_PROXY", "all_proxy")
_NO_PROXY_ENV_VARS = ("NO_PROXY", "no_proxy")

# Pre-tool values of the proxy env vars we have written, so switching to a
# project without `network:` config restores the user's own environment instead
# of leaking the previous project's proxy into later runs.
_proxy_env_backup: dict[str, str | None] = {}
_applied_proxy_vars: set[str] = set()


def _apply_network_proxy(cfg: ProjectConfig) -> None:
    """Export the project's proxy settings before the first httpx client exists.

    litellm's OpenAI-compatible path rides on httpx with ``trust_env=True``,
    which reads HTTP(S)_PROXY / ALL_PROXY / NO_PROXY when the client is built.
    `make_provider` runs before any completion call, so setting them here routes
    every live-mode model call through the configured proxy. Vars this config
    does not name are restored to their pre-tool values (a project without
    `network:` leaves the user's shell environment untouched).

    Caveat: the environment is process-global — concurrent live jobs on projects
    with *different* proxy configs can race (last `make_provider` wins).
    """
    global _applied_proxy_vars
    targets: dict[str, str] = {}
    if cfg.network.proxy:
        for var in _PROXY_ENV_VARS:
            targets[var] = cfg.network.proxy
    if cfg.network.no_proxy:
        for var in _NO_PROXY_ENV_VARS:
            targets[var] = cfg.network.no_proxy
    for var in _applied_proxy_vars | targets.keys():
        if var not in _proxy_env_backup:
            _proxy_env_backup[var] = os.environ.get(var)
    for var in _applied_proxy_vars - targets.keys():
        original = _proxy_env_backup[var]
        if original is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = original
    for var, value in targets.items():
        os.environ[var] = value
    _applied_proxy_vars = set(targets)


class _DemoSeqProvider(FakeProvider):
    """FakeProvider serving queued arc_detailer responses so each volume in
    demo mode gets its own correctly-sized detail (spec §4.3)."""

    def __init__(self, responses: dict[str, object], arcs: list[Arc], tag_key: str = "agent") -> None:
        super().__init__(responses, tag_key=tag_key)
        self._arcs = list(arcs)

    def _lookup(self, messages: list[dict[str, object]]) -> object:
        from novel.providers import _agent_tag
        if _agent_tag(messages, self.tag_key) == "arc_detailer":
            return self._arcs.pop(0)
        return super()._lookup(messages)


def make_provider(cfg: ProjectConfig, skills: list | None = None) -> ModelProvider:
    """Build the run's provider; with skills installed the provider injects each
    active skill's directives into its targeted agents' calls."""
    if is_live_mode():
        _apply_network_proxy(cfg)
        from novel.providers import LiteLLMProvider
        provider: ModelProvider = LiteLLMProvider(language=cfg.language)
    else:
        provider = demo_provider()
    if skills:
        from novel.skills import SkillProvider
        return SkillProvider(provider, skills)
    return provider


def demo_provider() -> ModelProvider:
    from novel.agents.orchestrator import OrchestratorDecision
    from novel.models import (
        ArcPlan,
        ArcSkeleton,
        BookDigest,
        ChapterBeat,
        ChapterOutline,
        Character,
        Concept,
        DimensionScore,
        Outline,
        ReviewScore,
        World,
    )
    concept = Concept(logline="A thief steals time.", genre="fantasy", tone="grim", themes=["loss"],
                      target_length_words=9000, audience="adult")
    beat = ChapterBeat(pov="Ara", setting="tavern", event="meet informant", emotional_turn="doubt",
                       characters=["c1"])
    outline = Outline(arcs=[Arc(arc_name="A", chapters=[
        ChapterOutline(chapter_no=i, chapter_title=f"T{i}", beats=[beat]) for i in range(1, 7)])],
        foreshadow_ledger=[])
    chars = [Character(id="c1", slug="ara", name="Ara", role="protagonist",
                       backstory="orphan", motivation="revenge", arc="a")]
    passing = ReviewScore(artifact_type="chapter", overall=90,
                          scores={"beat_adherence": DimensionScore(score=90, critique="ok")})
    arc_queue = [
        Arc(arc_name="第一卷", chapters=[
            ChapterOutline(chapter_no=i, chapter_title=f"T{i}", beats=[beat]) for i in range(1, 7)]),
        Arc(arc_name="第二卷", chapters=[
            ChapterOutline(chapter_no=900 + i, chapter_title=f"X{i}", beats=[beat])
            for i in range(1, 7)]),
    ]
    return _DemoSeqProvider({
        "strategist": concept, "worldbuilder": World(setting="city of bells"),
        "character": chars, "outliner": outline,
        "cast_planner": [],   # demo volumes reuse the initial cast
        "arc_planner": ArcPlan(arcs=[ArcSkeleton(arc_name="第一卷", chapter_start=1,
                                                  chapter_end=6, premise="demo"),
                                     ArcSkeleton(arc_name="第二卷", chapter_start=7,
                                                 chapter_end=12, premise="demo2")],
                               planned_total_chapters=12),
        "summarizer": {"chapter_no": 1, "arc_name": "第一卷", "summary": "演示摘要。",
                       "chapter_start": 1, "chapter_end": 6, "major_developments": []},
        "digestor": BookDigest(chapter_count=6, current_arc="第一卷", summary="演示梗概。"),
        "writer": "Ara stepped into the tavern. The thief's work was about to begin.",
        "continuity": "[]", "editor": "Ara stepped into the tavern.",
        "scorer": passing,
        "extractor": {"character_states": {}, "voice_samples": {}, "mannerisms_used": {},
              "key_events": [], "threads_advanced": [], "new_information_revealed": []},
        "orchestrator": OrchestratorDecision(
            reply="演示模式:已读取当前工作流计划。要推进制作,请切换到 live 模式或在 Code 模式操作。",
            action=None),
    }, arcs=arc_queue, tag_key="agent")
