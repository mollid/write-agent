"""Installable third-party skills: directive packages injected into targeted
agent calls at the provider layer.

A skill is a directory (no code, no execution — instructions only):

    skills/<name>/skill.json   # {"name", "description", "targets": [...], "enabled": true}
    skills/<name>/writer.md    # one directive file per targeted agent tag
    skills/<name>/scorer.md

`SkillProvider` wraps a ModelProvider and appends each active skill's directive
as a system message — same layer the language directive uses — so every call
path (CLI, GUI jobs, pipeline) picks skills up by wrapping once in
`runtime.make_provider(cfg, skills=load_skills(proj.root))`.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import BaseModel

from novel.config import ModelConfig
from novel.providers import ModelProvider

# every agent message tag a skill may target (model slots may differ from tags)
SKILL_TARGETS = frozenset({
    "strategist", "worldbuilder", "character", "outliner",
    "arc_planner", "arc_detailer", "cast_planner",
    "writer", "scorer", "continuity", "editor", "extractor",
    "summarizer", "digestor", "rewriter", "setting_editor",
})


@dataclass
class Skill:
    name: str
    description: str
    targets: frozenset[str]
    directives: dict[str, str] = field(default_factory=dict)
    enabled: bool = True


def _parse_skill(pkg: Path) -> Skill:
    manifest = json.loads((pkg / "skill.json").read_text(encoding="utf-8"))
    name = str(manifest.get("name", "")).strip()
    if not name:
        raise ValueError(f"{pkg / 'skill.json'}: manifest 缺少 name")
    targets_raw = manifest.get("targets") or []
    unknown = [t for t in targets_raw if t not in SKILL_TARGETS]
    if unknown:
        raise ValueError(f"技能 {name}: 未知 target {unknown}，可用: {sorted(SKILL_TARGETS)}")
    missing = [t for t in targets_raw if not (pkg / f"{t}.md").is_file()]
    if missing:
        raise ValueError(f"技能 {name}: targets 声明了 {missing} 但缺少对应 .md 指令文件")
    directives = {t: (pkg / f"{t}.md").read_text(encoding="utf-8").strip()
                  for t in targets_raw}
    return Skill(name=name, description=str(manifest.get("description", "")),
                 targets=frozenset(targets_raw), directives=directives,
                 enabled=bool(manifest.get("enabled", True)))


def skills_dir(proj_root: Path) -> Path:
    return proj_root / "skills"


def load_skills(proj_root: Path) -> list[Skill]:
    """Load all installed skills; malformed packages are skipped (an authoring
    mistake must never take down a writing run)."""
    root = skills_dir(proj_root)
    if not root.is_dir():
        return []
    out: list[Skill] = []
    for pkg in sorted(root.iterdir()):
        if not (pkg / "skill.json").is_file():
            continue
        try:
            out.append(_parse_skill(pkg))
        except (ValueError, json.JSONDecodeError):
            continue
    return out


def install_skill(src: Path, proj_root: Path, targets: list[str] | None = None,
                  force: bool = False) -> Path:
    """Install a skill package in one step.

    Accepted sources: a native package dir (skill.json), a Claude Agent Skills
    package (SKILL.md, converted — SKILL.md has no targets concept, so `targets`
    or the DEFAULT_CLAUDE_TARGETS apply), a bare SKILL.md file, or a .zip
    archive as shipped by the marketplaces (package root located automatically).
    """
    src = Path(src)
    if src.suffix.lower() == ".zip":
        with tempfile.TemporaryDirectory() as td:
            extracted = Path(td)
            _extract_zip(src, extracted)
            return _install_dir(_locate_pkg_root(extracted), proj_root, targets, force)
    if src.is_file() and src.name == "SKILL.md":
        src = src.parent
    return _install_dir(src, proj_root, targets, force)


DEFAULT_CLAUDE_TARGETS = ("writer", "editor")


def _install_dir(pkg_src: Path, proj_root: Path, targets: list[str] | None,
                 force: bool) -> Path:
    if (pkg_src / "skill.json").is_file():
        skill = _parse_skill(pkg_src)  # native: the manifest is authoritative
        dest = skills_dir(proj_root) / skill.name
        _prepare_dest(dest, force)
        shutil.copytree(pkg_src, dest, dirs_exist_ok=True)
        return dest
    if (pkg_src / "SKILL.md").is_file():
        return _install_claude(pkg_src, proj_root, targets, force)
    raise ValueError(f"{pkg_src} 不是技能包（缺少 skill.json 或 SKILL.md）")


def _install_claude(pkg_src: Path, proj_root: Path, targets: list[str] | None,
                    force: bool) -> Path:
    meta, body = _parse_frontmatter((pkg_src / "SKILL.md").read_text(encoding="utf-8"))
    name = str(meta.get("name", "")).strip()
    if not name:
        raise ValueError("SKILL.md frontmatter 缺少 name")
    raw_targets = meta.get("targets")
    from_manifest = [str(t) for t in raw_targets] if isinstance(raw_targets, list) else []
    chosen = list(targets or []) or from_manifest or list(DEFAULT_CLAUDE_TARGETS)
    unknown = [t for t in chosen if t not in SKILL_TARGETS]
    if unknown:
        raise ValueError(f"技能 {name}: 未知 target {unknown}，可用: {sorted(SKILL_TARGETS)}")
    dest = skills_dir(proj_root) / name
    _prepare_dest(dest, force)
    manifest = {"name": name, "description": str(meta.get("description", "")),
                "targets": chosen, "enabled": True}
    (dest / "skill.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
    for t in chosen:
        (dest / f"{t}.md").write_text(body, encoding="utf-8")
    shutil.copy2(pkg_src / "SKILL.md", dest / "SKILL.md")  # 原文保留，便于溯源
    return dest


def _prepare_dest(dest: Path, force: bool) -> None:
    if dest.exists():
        if not force:
            raise ValueError(f"技能 {dest.name} 已安装（{dest}）；覆盖安装请加 --force")
        shutil.rmtree(dest)
    dest.mkdir(parents=True)


def _parse_frontmatter(text: str) -> tuple[dict[str, object], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("SKILL.md 缺少 YAML frontmatter（首行应为 ---）")
    end = next((i for i, l in enumerate(lines[1:], start=1) if l.strip() == "---"), None)
    if end is None:
        raise ValueError("SKILL.md frontmatter 未闭合（缺少结束 ---）")
    meta = yaml.safe_load("\n".join(lines[1:end])) or {}
    if not isinstance(meta, dict):
        raise TypeError("SKILL.md frontmatter 必须是键值对")
    return meta, "\n".join(lines[end + 1:]).strip()


def _extract_zip(zpath: Path, dest: Path) -> None:
    with zipfile.ZipFile(zpath) as z:
        root = dest.resolve()
        for info in z.infolist():
            target = (dest / info.filename).resolve()
            if not target.is_relative_to(root):
                raise ValueError(f"压缩包含非法路径（疑似 zip-slip）: {info.filename}")
            z.extract(info, dest)


def _locate_pkg_root(extracted: Path) -> Path:
    markers = list(extracted.rglob("SKILL.md")) + list(extracted.rglob("skill.json"))
    if not markers:
        raise ValueError("压缩包内未找到 SKILL.md 或 skill.json")
    return min((m.parent for m in markers), key=lambda p: len(p.parts))


def set_skill_enabled(proj_root: Path, name: str, enabled: bool) -> None:
    pkg = skills_dir(proj_root) / name
    manifest_path = pkg / "skill.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["enabled"] = enabled
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                             encoding="utf-8")


def skill_messages(skills: list[Skill], agent_tag: str) -> list[dict[str, object]]:
    """System messages carrying every active skill's directive for one agent."""
    return [
        {"role": "system", "agent": agent_tag,
         "content": f"[INSTALLED SKILL — {s.name}]\n{s.directives[agent_tag]}"}
        for s in skills
        if s.enabled and agent_tag in s.directives
    ]


class SkillProvider:
    """ModelProvider wrapper injecting skill directives per agent tag."""

    def __init__(self, inner: ModelProvider, skills: list[Skill]) -> None:
        self._inner = inner
        self._skills = skills

    def _with_skills(self, messages: list[dict[str, object]]) -> list[dict[str, object]]:
        from novel.providers import _agent_tag
        try:
            tag = _agent_tag(messages, "agent")
        except KeyError:
            return messages
        extra = skill_messages(self._skills, tag)
        return messages + extra if extra else messages

    def complete(self, messages: list[dict[str, object]], cfg: ModelConfig,
                 *, seed: int | None = None) -> str:
        return self._inner.complete(self._with_skills(messages), cfg, seed=seed)

    def complete_structured(self, messages: list[dict[str, object]],
                            schema: type[BaseModel], cfg: ModelConfig,
                            *, seed: int | None = None) -> BaseModel:
        return self._inner.complete_structured(self._with_skills(messages), schema, cfg,
                                               seed=seed)
