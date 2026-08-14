from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ModelConfig:
    provider: str
    model: str


@dataclass
class Thresholds:
    score_min: int = 80
    max_retries: int = 3


@dataclass
class Generation:
    human_gate_every_n_chapters: int = 1
    context_token_budget: int = 24000


@dataclass
class ProjectConfig:
    models: dict[str, ModelConfig] = field(default_factory=dict)
    thresholds: Thresholds = field(default_factory=Thresholds)
    generation: Generation = field(default_factory=Generation)
    language: str = "en"

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
        name: ModelConfig(provider=m.get("provider", ""), model=m.get("model", ""))
        for name, m in (raw.get("models") or {}).items()
    }
    th = raw.get("thresholds") or {}
    gen = raw.get("generation") or {}
    return ProjectConfig(
        models=models,
        thresholds=Thresholds(score_min=th.get("score_min", 80), max_retries=th.get("max_retries", 3)),
        generation=Generation(
            human_gate_every_n_chapters=gen.get("human_gate_every_n_chapters", 1),
            context_token_budget=gen.get("context_token_budget", 24000),
        ),
        language=str(raw.get("language", "en")).strip().lower() or "en",
    )
