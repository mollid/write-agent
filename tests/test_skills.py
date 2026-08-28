"""Installable third-party skills: directive packages injected into targeted
agent calls (writer / scorer / setup agents ...) at the provider layer."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from novel.models import (
    Arc,
    ChapterBeat,
    ChapterOutline,
    Character,
    Concept,
    DimensionScore,
    Outline,
    ReviewScore,
    World,
)
from novel.project import NovelProject
from novel.providers import FakeProvider, ModelConfig
from novel.skills import (
    Skill,
    install_skill,
    load_skills,
    set_skill_enabled,
    skill_messages,
)
from novel.store.bible import StoryBible


def _make_src(root: Path, name: str = "wuxia-style", targets: list[str] | None = None,
              files: dict[str, str] | None = None) -> Path:
    src = root / "src" / name
    src.mkdir(parents=True)
    manifest = {
        "name": name,
        "description": "demo skill",
        "targets": targets or ["writer", "scorer"],
    }
    (src / "skill.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    for fname, text in (files or {
        "writer.md": "战斗描写侧重招式力度与身法节奏。",
        "scorer.md": "对「beat_adherence」维度的及格线从严把握。",
    }).items():
        (src / fname).write_text(text, encoding="utf-8")
    return src


def test_install_skill_copies_package_and_loads(tmp_path):
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    src = _make_src(tmp_path)
    installed = install_skill(src, proj.root)
    assert installed.is_dir()
    skills = load_skills(proj.root)
    assert len(skills) == 1
    s = skills[0]
    assert s.name == "wuxia-style"
    assert s.targets == {"writer", "scorer"}
    assert "招式力度" in s.directives["writer"]
    assert "及格线" in s.directives["scorer"]


def test_install_rejects_invalid_packages(tmp_path):
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    # unknown target tag
    bad_target = _make_src(tmp_path / "a", name="bad-target", targets=["dragon"])
    with pytest.raises(ValueError, match="target"):
        install_skill(bad_target, proj.root)
    # manifest targets a file that does not exist
    bad_files = _make_src(tmp_path / "b", name="bad-files", targets=["writer", "editor"])
    with pytest.raises(ValueError, match="editor"):
        install_skill(bad_files, proj.root)
    # name conflict with an installed skill
    install_skill(_make_src(tmp_path / "c"), proj.root)
    with pytest.raises(ValueError, match="已安装"):
        install_skill(_make_src(tmp_path / "d"), proj.root)


def test_load_skills_ignores_disabled_and_missing_dir(tmp_path):
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    assert load_skills(proj.root) == []  # no skills dir yet
    install_skill(_make_src(tmp_path), proj.root)
    set_skill_enabled(proj.root, "wuxia-style", False)
    skills = load_skills(proj.root)
    assert len(skills) == 1 and skills[0].enabled is False
    msgs = skill_messages(skills, "writer")
    assert msgs == []  # disabled skill never injects


def test_skill_messages_inject_only_targeted_agents(tmp_path):
    skills = [Skill(name="s1", description="d", targets={"writer", "scorer"},
                    directives={"writer": "W1", "scorer": "S1"}, enabled=True)]
    w = skill_messages(skills, "writer")
    assert len(w) == 1
    assert w[0]["role"] == "system" and w[0]["agent"] == "writer"
    assert "[INSTALLED SKILL — s1]" in w[0]["content"]
    assert "W1" in w[0]["content"]
    assert skill_messages(skills, "strategist") == []


def test_skill_provider_wraps_both_call_paths():
    from novel.skills import SkillProvider

    captured: list[tuple[str, list[dict]]] = []

    class _Rec:
        def complete(self, messages, cfg, *, seed=None):
            captured.append(("complete", messages))
            return "ok"

        def complete_structured(self, messages, schema, cfg, *, seed=None):
            captured.append(("structured", messages))
            return schema.model_validate({})

    skills = [Skill(name="s1", description="d", targets={"writer"},
                    directives={"writer": "注入文本"})]
    provider = SkillProvider(_Rec(), skills)  # type: ignore[arg-type]
    base = [{"role": "system", "agent": "writer", "content": "sys"},
            {"role": "user", "agent": "writer", "content": "u"}]
    cfg = ModelConfig("zhipu", "x")
    assert provider.complete(base, cfg) == "ok"
    assert captured[0][1][-1]["content"].endswith("注入文本")  # appended, not replacing
    assert captured[0][1][:2] == base
    provider.complete_structured([{"role": "user", "agent": "writer", "content": "u"}],
                                 Outline, cfg)
    assert "[INSTALLED SKILL" in captured[1][1][-1]["content"]
    # untargeted agent passes through untouched
    provider.complete([{"role": "user", "agent": "scorer", "content": "u"}], cfg)
    assert captured[2][1] == [{"role": "user", "agent": "scorer", "content": "u"}]


def test_make_provider_wraps_skills_when_given():
    from novel.config import ProjectConfig
    from novel.runtime import make_provider
    from novel.skills import SkillProvider

    cfg = ProjectConfig()
    skills = [Skill(name="s", description="d", targets={"writer"},
                    directives={"writer": "x"})]
    assert isinstance(make_provider(cfg, skills=skills), SkillProvider)
    assert not isinstance(make_provider(cfg), SkillProvider)


def test_pipeline_injects_skills_into_targeted_agents(tmp_path):
    """End to end: an installed writer+scorer skill reaches exactly those two
    agents' message streams during chapter generation."""
    from novel.graph import run_full_pipeline
    from novel.runtime import AGENT_NAMES
    from novel.skills import SkillProvider
    from novel.store.vector import VectorMemory, hash_embed

    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    bible = StoryBible(proj)
    install_skill(_make_src(tmp_path), proj.root)
    bible.set_concept(Concept(logline="L", genre="g", tone="t",
                              target_length_words=9000, audience="a"))
    bible.set_world(World(setting="city"))
    beat = ChapterBeat(pov="c1", setting="tavern", event="meet", emotional_turn="d",
                       characters=["c1"])
    bible.upsert_character(Character(id="c1", slug="ara", name="Ara", role="protagonist",
                                     backstory="b", motivation="m", arc="a"))
    bible.set_outline(Outline(arcs=[Arc(arc_name="A", chapters=[
        ChapterOutline(chapter_no=1, chapter_title="T1", beats=[beat])])]))

    inner = FakeProvider({
        "strategist": Concept(logline="L", genre="g", tone="t",
                              target_length_words=9000, audience="a"),
        "worldbuilder": World(setting="city"), "outliner": Outline(arcs=[]),
        "writer": "Chapter prose that is definitely long enough.",
        "continuity": "[]", "editor": "x",
        "scorer": ReviewScore(artifact_type="chapter", overall=90,
                              scores={"beat_adherence": DimensionScore(score=90, critique="ok")}),
        "extractor": {"character_states": {}, "voice_samples": {}, "mannerisms_used": {},
                      "key_events": [], "threads_advanced": [], "new_information_revealed": [],
                      "chapter_summary": "摘要。"},
    }, tag_key="agent")

    seen: dict[str, str] = {}

    class _Spy:
        def _note(self, messages):
            from novel.providers import _agent_tag
            tag = _agent_tag(messages, "agent")
            seen[tag] = "\n".join(str(m.get("content", "")) for m in messages)

        def complete(self, messages, cfg, *, seed=None):
            self._note(messages)
            return inner.complete(messages, cfg, seed=seed)

        def complete_structured(self, messages, schema, cfg, *, seed=None):
            self._note(messages)
            return inner.complete_structured(messages, schema, cfg, seed=seed)

    provider = SkillProvider(_Spy(), load_skills(proj.root))  # type: ignore[arg-type]
    cfg_map = {name: ModelConfig("zhipu", "x") for name in AGENT_NAMES}
    state = run_full_pipeline(provider=provider, cfg_map=cfg_map, bible=bible,
                              vector=VectorMemory(proj, embed=hash_embed),
                              proj=proj, premise="L", target_chapters=1, start_chapter=1)
    assert state.error is None
    assert "招式力度" in seen["writer"]        # writer got the skill directive
    assert "及格线" in seen["scorer"]          # scorer got the skill directive
    assert "INSTALLED SKILL" not in seen["extractor"]  # untargeted agent untouched


# ---------- Claude Agent Skills (SKILL.md) one-step install ----------

def _make_claude_src(root: Path, name: str = "human-writing") -> Path:
    """A Claude Agent Skills package: SKILL.md with YAML frontmatter."""
    pkg = root / "claude" / name
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: strip AI-sounding prose\nlicense: MIT\n---\n"
        "# Human writing\n\nPrefer concrete verbs. Avoid em-dash pileups and\n"
        "\"delve\"-style vocabulary.\n", encoding="utf-8")
    return pkg


def test_install_claude_skill_converts_to_native(tmp_path):
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    dest = install_skill(_make_claude_src(tmp_path), proj.root)  # default writer,editor
    assert (dest / "skill.json").is_file()
    skills = load_skills(proj.root)
    assert len(skills) == 1
    s = skills[0]
    assert s.name == "human-writing"
    assert s.description == "strip AI-sounding prose"
    assert s.targets == {"writer", "editor"}
    assert "concrete verbs" in s.directives["writer"]
    assert "concrete verbs" in s.directives["editor"]
    assert (dest / "SKILL.md").is_file()  # original kept for reference


def test_install_claude_skill_custom_targets(tmp_path):
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    install_skill(_make_claude_src(tmp_path), proj.root, targets=["scorer"])
    s = load_skills(proj.root)[0]
    assert s.targets == {"scorer"}
    assert "concrete verbs" in s.directives["scorer"]


def test_install_zip_skill_one_step(tmp_path):
    """Marketplaces ship ZIPs: install directly from the archive (nested root
    dir is located automatically; path-traversal entries are rejected)."""
    import zipfile
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    src = _make_claude_src(tmp_path)
    zpath = tmp_path / "human-writing.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("human-writing/SKILL.md", (src / "SKILL.md").read_text(encoding="utf-8"))
    install_skill(zpath, proj.root, targets=["writer"])
    s = load_skills(proj.root)[0]
    assert s.name == "human-writing" and s.targets == {"writer"}

    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("../../evil.md", "boom")
    with pytest.raises(ValueError, match="路径"):
        install_skill(evil, proj.root)


def test_install_force_replaces_existing(tmp_path):
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    install_skill(_make_claude_src(tmp_path), proj.root, targets=["writer"])
    with pytest.raises(ValueError, match="已安装"):
        install_skill(_make_claude_src(tmp_path), proj.root, targets=["scorer"])
    install_skill(_make_claude_src(tmp_path), proj.root, targets=["scorer"], force=True)
    assert load_skills(proj.root)[0].targets == {"scorer"}


def test_install_rejects_skill_md_without_name(tmp_path):
    pkg = tmp_path / "anon"
    pkg.mkdir()
    (pkg / "SKILL.md").write_text("---\ndescription: no name\n---\nbody", encoding="utf-8")
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    with pytest.raises(ValueError, match="name"):
        install_skill(pkg, proj.root)
