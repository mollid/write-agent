from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ModelConfig:
    provider: str
    model: str
    api_base: str | None = None      # OpenAI-compatible base URL override (e.g. https://apihub.agnes-ai.com/v1)
    api_key: str | None = None       # secret; will be written into per-project project.config.yaml (which is gitignored)
    timeout: float | None = None     # per-call timeout in seconds; None = litellm default (use for slow local models)


@dataclass(frozen=True)
class NetworkConfig:
    proxy: str | None = None      # e.g. http://127.0.0.1:7890 — routes live-mode model/TTS calls
    no_proxy: str | None = None   # comma-separated hosts/CIDRs that bypass the proxy


@dataclass
class Thresholds:
    score_min: int = 80
    max_retries: int = 3


@dataclass
class Generation:
    human_gate_every_n_chapters: int = 1
    context_token_budget: int = 24000
    min_chapter_chars: int = 50    # resume check: shorter chapter files count as incomplete
    target_chapters: int | None = None    # planned whole-book total; None = legacy one-shot outline
    chapter_target_length: int = 2500     # per-chapter target: zh=字, en=words
    arc_detail_lookahead: int = 5         # auto arc-detail trigger runway (chapters)


@dataclass
class ProjectConfig:
    models: dict[str, ModelConfig] = field(default_factory=dict)
    thresholds: Thresholds = field(default_factory=Thresholds)
    generation: Generation = field(default_factory=Generation)
    language: str = "en"
    network: NetworkConfig = field(default_factory=NetworkConfig)

    def model_for(self, agent_name: str) -> ModelConfig:
        if agent_name in self.models:
            return self.models[agent_name]
        if "default" in self.models:
            return self.models["default"]
        # fall back to first configured model
        return next(iter(self.models.values())) if self.models else ModelConfig("zhipu", "glm-4-plus")


def load_config(path: Path) -> ProjectConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    models = {
        name: ModelConfig(
            provider=m.get("provider", ""),
            model=m.get("model", ""),
            api_base=m.get("api_base") or m.get("base_url"),
            api_key=m.get("api_key"),
            timeout=m.get("timeout"),
        )
        for name, m in (raw.get("models") or {}).items()
    }
    th = raw.get("thresholds") or {}
    gen = raw.get("generation") or {}
    net = raw.get("network") or {}
    return ProjectConfig(
        models=models,
        thresholds=Thresholds(score_min=th.get("score_min", 80), max_retries=th.get("max_retries", 3)),
        generation=Generation(
            human_gate_every_n_chapters=gen.get("human_gate_every_n_chapters", 1),
            context_token_budget=gen.get("context_token_budget", 24000),
            min_chapter_chars=gen.get("min_chapter_chars", 50),
            target_chapters=gen.get("target_chapters"),
            chapter_target_length=gen.get("chapter_target_length", 2500),
            arc_detail_lookahead=gen.get("arc_detail_lookahead", 5),
        ),
        language=str(raw.get("language", "en")).strip().lower() or "en",
        network=NetworkConfig(proxy=net.get("proxy"), no_proxy=net.get("no_proxy")),
    )
