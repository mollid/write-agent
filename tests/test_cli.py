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
