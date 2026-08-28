from typer.testing import CliRunner

from novel.cli import app

runner = CliRunner()

def test_init_creates_project(tmp_path):
    result = runner.invoke(app, ["init", "demo", "--genre", "fantasy", "--root", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "demo" / "bible" / "_canonical.json").exists()

def test_premise_runs_in_demo_mode(tmp_path):
    runner.invoke(app, ["init", "demo", "--genre", "fantasy", "--root", str(tmp_path)])
    result = runner.invoke(app, ["--project", str(tmp_path / "demo"), "premise", "a thief steals time"])
    assert result.exit_code == 0, result.output
    # concept should now be persisted
    import json
    canon = json.loads((tmp_path / "demo" / "bible" / "_canonical.json").read_text())
    assert "concept" in canon

def _demo_project(tmp_path):
    runner.invoke(app, ["init", "demo", "--genre", "fantasy", "--root", str(tmp_path)])
    result = runner.invoke(app, ["--project", str(tmp_path / "demo"), "premise", "a thief steals time"])
    assert result.exit_code == 0, result.output
    return tmp_path / "demo"

def test_write_chapter_demo_e2e(tmp_path):
    proj = _demo_project(tmp_path)
    result = runner.invoke(app, ["--project", str(proj), "write-chapter", "3"])
    assert result.exit_code == 0, result.output
    chapters = sorted((proj / "chapters").glob("[0-9][0-9][0-9].md"))
    assert len(chapters) == 3

def test_write_chapter_continues(tmp_path):
    proj = _demo_project(tmp_path)
    r1 = runner.invoke(app, ["--project", str(proj), "write-chapter", "3"])
    assert r1.exit_code == 0, r1.output
    r2 = runner.invoke(app, ["--project", str(proj), "write-chapter", "2"])
    assert r2.exit_code == 0, r2.output
    chapters = sorted((proj / "chapters").glob("[0-9][0-9][0-9].md"))
    assert len(chapters) == 5

def test_write_chapter_resumes_message(tmp_path):
    proj = _demo_project(tmp_path)
    r1 = runner.invoke(app, ["--project", str(proj), "write-chapter", "2"])
    assert r1.exit_code == 0, r1.output
    r2 = runner.invoke(app, ["--project", str(proj), "write-chapter", "1"])
    assert r2.exit_code == 0, r2.output
    assert "Resuming from chapter 3" in r2.output
    chapters = sorted((proj / "chapters").glob("[0-9][0-9][0-9].md"))
    assert len(chapters) == 3


def test_setup_command_demo_e2e(tmp_path):
    runner.invoke(app, ["init", "demo", "--genre", "fantasy", "--root", str(tmp_path)])
    proj = tmp_path / "demo"
    # premise passed via --premise; four stages approved with "a"
    result = runner.invoke(app, ["--project", str(proj), "setup", "--premise", "a thief steals time"],
                           input="a\na\na\na\n")
    assert result.exit_code == 0, result.output
    assert "演示模式" in result.output  # demo notice printed
    import json
    canon = json.loads((proj / "bible" / "_canonical.json").read_text())
    assert "concept" in canon and "outline" in canon


def test_setup_command_feedback_loop_and_quit(tmp_path):
    runner.invoke(app, ["init", "demo", "--genre", "fantasy", "--root", str(tmp_path)])
    proj = tmp_path / "demo"
    # concept: feedback once then approve; world: approve; characters: approve; outline: quit
    result = runner.invoke(app, ["--project", str(proj), "setup", "--premise", "a thief"],
                           input="f\n主角改成女性\na\na\na\nq\n")
    assert result.exit_code == 0, result.output
    import json
    canon = json.loads((proj / "bible" / "_canonical.json").read_text())
    assert "concept" in canon and "world" in canon  # approved stages persisted
    assert "outline" not in canon  # quit before outline
    # re-run skips approved stages and finishes the rest
    result2 = runner.invoke(app, ["--project", str(proj), "setup"], input="a\n")
    assert result2.exit_code == 0, result2.output
    assert "跳过" in result2.output  # approved stages skipped on re-entry
    canon2 = json.loads((proj / "bible" / "_canonical.json").read_text())
    assert "outline" in canon2


def test_setup_command_invalid_choice_does_not_regenerate(tmp_path):
    runner.invoke(app, ["init", "demo", "--genre", "fantasy", "--root", str(tmp_path)])
    proj = tmp_path / "demo"
    # first stage gets one invalid "x" before approving; remaining stages approve directly
    result = runner.invoke(app, ["--project", str(proj), "setup", "--premise", "a thief"],
                           input="x\na\na\na\na\n")
    assert result.exit_code == 0, result.output
    assert result.output.count("第 1 次生成") == 4  # one generation per stage
    assert "第 2 次生成" not in result.output  # invalid input must not re-run the agent
    assert "设定完成" in result.output


def test_setup_passes_longform_params(tmp_path, monkeypatch):
    """Guided setup wires cfg.generation.target_chapters into the outline stage."""
    from novel import setup_flow
    from novel.project import NovelProject

    proj = NovelProject.scaffold("n", "fantasy", root=tmp_path)
    raw = proj.config_path.read_text(encoding="utf-8")
    proj.config_path.write_text(raw + "generation:\n  target_chapters: 240\n", encoding="utf-8")
    captured: list[dict] = []
    real = setup_flow.generate_stage

    def spy(stage, **kw):
        captured.append(kw)
        return real(stage, **kw)

    monkeypatch.setattr(setup_flow, "generate_stage", spy)
    result = runner.invoke(app, ["--project", str(proj.root), "setup", "--premise", "a thief"],
                           input="a\na\na\na\n")
    assert result.exit_code == 0, result.output
    assert captured and captured[-1].get("target_chapters") == 240


def test_write_chapter_rewrites_empty_chapter(tmp_path):
    proj = _demo_project(tmp_path)
    runner.invoke(app, ["--project", str(proj), "write-chapter", "2"])
    ch2 = proj / "chapters" / "002.md"
    good = ch2.read_text()
    (proj / "chapters" / "001.md").write_text("")  # simulate a crashed write
    result = runner.invoke(app, ["--project", str(proj), "write-chapter", "1"])
    assert result.exit_code == 0, result.output
    assert len((proj / "chapters" / "001.md").read_text()) > 50  # rewritten
    assert ch2.read_text() == good  # complete chapter untouched
    assert len(sorted((proj / "chapters").glob("[0-9][0-9][0-9].md"))) == 2


_FakeState = type("S", (), {"error": None, "written": []})()


def test_write_chapter_passes_longform_params(tmp_path, monkeypatch):
    """write-chapter wires cfg.generation longform fields into run_full_pipeline."""
    from novel import cli, graph
    from novel.project import NovelProject

    proj = NovelProject.scaffold("n", "fantasy", root=tmp_path)
    cfg_path = proj.config_path
    raw = cfg_path.read_text(encoding="utf-8")
    cfg_path.write_text(raw + "generation:\n  target_chapters: 240\n  arc_detail_lookahead: 8\n",
                        encoding="utf-8")
    captured: dict[str, object] = {}
    monkeypatch.setattr(graph, "run_full_pipeline",
                        lambda **kw: captured.update(kw) or _FakeState)
    cli.write_chapter(1, proj.root)  # typer function called directly
    assert captured["planned_total"] == 240
    assert captured["arc_lookahead"] == 8
    assert captured["gate_every_n"] == 1


def test_skill_commands_install_list_toggle(tmp_path):
    """skill install → list shows it → disable → list reflects it."""
    import json
    src = tmp_path / "pkg" / "my-style"
    (src).mkdir(parents=True)
    (src / "skill.json").write_text(json.dumps(
        {"name": "my-style", "description": "测试技能", "targets": ["writer"]},
        ensure_ascii=False), encoding="utf-8")
    (src / "writer.md").write_text("多用短句。", encoding="utf-8")

    proj = tmp_path / "sk"
    runner.invoke(app, ["init", "sk", "--root", str(tmp_path)])
    r = runner.invoke(app, ["--project", str(proj), "skill", "install", str(src)])
    assert r.exit_code == 0, r.output
    assert (proj / "skills" / "my-style" / "skill.json").is_file()

    r = runner.invoke(app, ["--project", str(proj), "skill", "list"])
    assert r.exit_code == 0, r.output
    assert "my-style" in r.output and "writer" in r.output

    r = runner.invoke(app, ["--project", str(proj), "skill", "disable", "my-style"])
    assert r.exit_code == 0, r.output
    manifest = json.loads((proj / "skills" / "my-style" / "skill.json").read_text())
    assert manifest["enabled"] is False


def test_skill_install_rejects_unknown_target(tmp_path):
    import json
    src = tmp_path / "pkg2" / "bad"
    (src).mkdir(parents=True)
    (src / "skill.json").write_text(json.dumps(
        {"name": "bad", "targets": ["dragon"]}), encoding="utf-8")
    (src / "dragon.md").write_text("x", encoding="utf-8")
    proj = tmp_path / "sk2"
    runner.invoke(app, ["init", "sk2", "--root", str(tmp_path)])
    r = runner.invoke(app, ["--project", str(proj), "skill", "install", str(src)])
    assert r.exit_code != 0 or "未知 target" in r.output


def test_skill_install_claude_md_one_step(tmp_path):
    """A Claude Agent Skills package installs without any rewriting."""
    pkg = tmp_path / "hw" / "human-writing"
    pkg.mkdir(parents=True)
    (pkg / "SKILL.md").write_text(
        "---\nname: human-writing\ndescription: less AI-sounding prose\n---\n"
        "Prefer concrete verbs over adverb stacks.", encoding="utf-8")
    proj = tmp_path / "cz"
    runner.invoke(app, ["init", "cz", "--root", str(tmp_path)])
    r = runner.invoke(app, ["--project", str(proj), "skill", "install", str(pkg),
                            "--target", "writer,editor"])
    assert r.exit_code == 0, r.output
    import json
    manifest = json.loads((proj / "skills" / "human-writing" / "skill.json").read_text())
    assert manifest["targets"] == ["writer", "editor"]
    assert (proj / "skills" / "human-writing" / "writer.md").is_file()
