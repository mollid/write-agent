from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from novel.config import load_config
from novel.project import NovelProject
from novel.runtime import is_live_mode, make_provider
from novel.store.bible import StoryBible
from novel.store.vector import VectorMemory, hash_embed

app = typer.Typer(add_completion=False)
console = Console()


def _load_project(project: Path | None) -> NovelProject:
    root = project or _global_project or Path.cwd()
    return NovelProject(root=root)


def _gate(label: str, artifact: object) -> bool:
    console.print(f"[bold cyan]Stage:[/bold cyan] {label}")
    console.print(str(artifact)[:1000])
    choice = typer.prompt("Approve? [a]pprove/[e]dit/[r]egen/[s]how", default="a")
    return choice in ("a", "")


_project_opt = typer.Option(None, "--project", "-p", help="project directory")

_global_project: Path | None = None


@app.callback()
def _project_callback(ctx: typer.Context, project: Path | None = _project_opt) -> None:
    global _global_project
    _global_project = project


@app.command()
def init(name: str, genre: str = "fantasy", root: Path | None = None) -> None:
    """Scaffold a new novel project."""
    proj = NovelProject.scaffold(name, genre=genre, root=root or Path.cwd())
    console.print(f"[green]Created[/green] {proj.root}")


@app.command()
def premise(text: str, project: Path | None = _project_opt) -> None:
    """Run Strategist on a premise (demo mode uses canned data)."""
    proj = _load_project(project)
    cfg = load_config(proj.config_path)
    provider = make_provider(cfg)
    from novel.agents.strategist import StrategistAgent
    concept = StrategistAgent(provider, cfg.model_for("strategist")).run(text)
    StoryBible(proj).set_concept(concept)
    console.print(f"[green]Concept saved.[/green] genre={concept.genre}")


@app.command()
def setup(premise_text: str = typer.Option("", "--premise", "-m",
                                           help="one-line premise (prompted if omitted)"),
          project: Path | None = _project_opt) -> None:
    """Guided setup (标准模式): approve or refine each stage with natural-language feedback."""
    proj = _load_project(project)
    cfg = load_config(proj.config_path)
    provider = make_provider(cfg)
    bible = StoryBible(proj)
    from novel.render import artifact_text
    from novel.runtime import AGENT_NAMES
    from novel.setup_flow import SETUP_STAGES, approve_stage, generate_stage, stage_done
    cfg_map = {name: cfg.model_for(name) for name in AGENT_NAMES}
    if not premise_text:
        saved = bible.get_concept()
        premise_text = saved.logline if saved else typer.prompt("Premise")
    if not is_live_mode():
        console.print("[yellow]演示模式：反馈不会改变生成内容。[/yellow]")
    for stage in SETUP_STAGES:
        if stage_done(stage, bible):
            console.print(f"[green]✓ {stage} 已通过，跳过[/green]")
            continue
        feedback: list[str] = []
        regenerate = True
        while True:
            if regenerate:  # invalid input / empty feedback never re-runs the agent
                console.rule(f"[bold cyan]{stage}[/bold cyan]（第 {len(feedback) + 1} 次生成）")
                artifact = generate_stage(stage, provider=provider, cfg_map=cfg_map,
                                          bible=bible, premise=premise_text, feedback=feedback)
                console.print(artifact_text(artifact)[:2000])
                regenerate = False
            choice = typer.prompt("通过(a) / 反馈(f) / 退出(q)", default="a")
            if choice in ("a", ""):
                approve_stage(stage, artifact, bible)
                console.print(f"[green]✓ {stage} 已通过并存入故事圣经[/green]")
                break
            if choice == "q":
                console.print("[yellow]Setup 已停止；已通过的阶段已保存，重跑 setup 可继续。[/yellow]")
                return
            if choice == "f":
                fb = typer.prompt("反馈意见")
                if fb.strip():
                    feedback.append(fb.strip())
                    regenerate = True  # regenerate with the new feedback
                else:
                    console.print("[yellow]反馈为空，请重新选择[/yellow]")
                continue
            console.print("[red]无效选择，请输入 a / f / q[/red]")
    console.print("[green]设定完成。运行 write-chapter 开始写作（会自动跳过设定阶段）。[/green]")


@app.command(name="write-chapter")
def write_chapter(n: int = typer.Argument(1, help="number of chapters to write"),
                  project: Path | None = _project_opt) -> None:
    """Write the next N chapters end-to-end (demo or live)."""
    proj = _load_project(project)
    cfg = load_config(proj.config_path)
    provider = make_provider(cfg)
    bible = StoryBible(proj)
    vector = VectorMemory(proj, embed=hash_embed)
    from novel.graph import run_full_pipeline
    from novel.runtime import AGENT_NAMES
    cfg_map = {name: cfg.model_for(name) for name in AGENT_NAMES}
    from novel.resume import next_start_chapter
    from novel.store.reviews import ReviewStore
    min_chars = cfg.generation.min_chapter_chars
    start_chapter = next_start_chapter(proj, ReviewStore(proj), min_chars)
    if start_chapter > 1:
        console.print(f"[cyan]Resuming from chapter {start_chapter}"
                      f" ({start_chapter - 1} chapter(s) already complete)[/cyan]")
    run_full_pipeline(provider=provider, cfg_map=cfg_map, bible=bible, vector=vector,
                      proj=proj, premise=(c.logline if (c := bible.get_concept()) else ""),
                      target_chapters=start_chapter - 1 + n, start_chapter=start_chapter,
                      score_min=cfg.thresholds.score_min, max_retries=cfg.thresholds.max_retries,
                      token_budget=cfg.generation.context_token_budget,
                      min_chapter_chars=min_chars,
                      on_gate=_gate if is_live_mode() else None)
    console.print(f"[green]Wrote {n} chapter(s).[/green]")


@app.command()
def threads(project: Path | None = _project_opt) -> None:
    """List open foreshadowing/threads."""
    bible = StoryBible(_load_project(project))
    t = Table("id", "description", "status")
    for f in bible.list_foreshadow():
        t.add_row(f.id, f.description, f.status.value)
    console.print(t)


@app.command()
def export(fmt: str = "md", project: Path | None = _project_opt) -> None:
    """Export the novel."""
    from novel.export import export_markdown
    proj = _load_project(project)
    out = export_markdown(proj)
    console.print(f"[green]Exported[/green] {out}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()