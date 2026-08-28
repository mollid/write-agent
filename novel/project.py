from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_CONFIG = """\
models:
  strategist: { provider: zhipu, model: glm-4-plus }
  writer: { provider: zhipu, model: glm-4-plus }
  scorer: { provider: deepseek, model: deepseek-chat }
thresholds:
  score_min: 80
  max_retries: 3
generation:
  human_gate_every_n_chapters: 1
  context_token_budget: 24000
language: en
# 接口需要代理/VPN 才能访问时取消注释（仅真实模式生效，模型调用与 TTS 都会走它）
# network:
#   proxy: http://127.0.0.1:7890
#   no_proxy: localhost,127.0.0.1
"""


def _config_text(target_chapters: int | None) -> str:
    """Default project.config.yaml; longform projects carry their whole-book plan."""
    if target_chapters is None:
        return _DEFAULT_CONFIG
    return _DEFAULT_CONFIG.replace(
        "  context_token_budget: 24000\n",
        f"  context_token_budget: 24000\n  target_chapters: {target_chapters}\n")


@dataclass
class NovelProject:
    root: Path

    @property
    def canonical_path(self) -> Path:
        return self.root / "bible" / "_canonical.json"

    @property
    def config_path(self) -> Path:
        return self.root / "project.config.yaml"

    @classmethod
    def scaffold(cls, name: str, genre: str, root: Path | None = None,
                 target_chapters: int | None = None) -> NovelProject:
        base = root or Path.cwd()
        proj_root = base / name
        (proj_root / "bible").mkdir(parents=True, exist_ok=True)
        (proj_root / "chapters" / "_summaries").mkdir(parents=True, exist_ok=True)
        (proj_root / "memory" / "chroma").mkdir(parents=True, exist_ok=True)
        (proj_root / "runs").mkdir(parents=True, exist_ok=True)
        (proj_root / ".meta" / "reviews").mkdir(parents=True, exist_ok=True)
        (proj_root / "project.config.yaml").write_text(_config_text(target_chapters),
                                                       encoding="utf-8")
        (proj_root / ".gitignore").write_text("*\n", encoding="utf-8")
        (proj_root / "bible" / "foreshadowing.json").write_text("[]", encoding="utf-8")
        (proj_root / "bible" / "events.jsonl").write_text("", encoding="utf-8")
        cls(proj_root).save_canonical({"genre": genre})
        return cls(proj_root)

    def load_canonical(self) -> dict:
        data: dict = json.loads(self.canonical_path.read_text(encoding="utf-8"))
        return data

    def save_canonical(self, data: dict) -> None:
        tmp = self.canonical_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.canonical_path)
