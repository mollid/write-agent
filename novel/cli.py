from __future__ import annotations

import os
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from novel.config import load_config
from novel.project import NovelProject
from novel.providers import ModelProvider
from novel.store.bible import StoryBible
from novel.store.vector import VectorMemory, hash_embed

app = typer.Typer(add_completion=False)
console = Console()


def _load_project(project: Path | None) -> NovelProject:
    root = project or _global_project or Path.cwd()
    return NovelProject(root=root)


def _make_provider(cfg: object) -> ModelProvider:
    from novel.providers import LiteLLMProvider
    if os.environ.get("NOVEL_LIVE") == "1":
        lang = getattr(cfg, "language", "en")
        return LiteLLMProvider(language=lang)
    return _demo_provider()


def _demo_provider() -> ModelProvider:
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
    from novel.providers import FakeProvider
    concept = Concept(logline="A thief steals time.", genre="fantasy", tone="grim", themes=["loss"],
                      target_length_words=9000, audience="adult")
    beat = ChapterBeat(pov="Ara", setting="tavern", event="meet informant", emotional_turn="doubt",
                       characters=["c1"])
    outline = Outline(arcs=[Arc(arc_name="A", chapters=[
        ChapterOutline(chapter_no=i, chapter_title=f"T{i}", beats=[beat]) for i in range(1, 4)])],
        foreshadow_ledger=[])
    chars = [Character(id="c1", slug="ara", name="Ara", role="protagonist",
                       backstory="orphan", motivation="revenge", arc="a")]
    passing = ReviewScore(artifact_type="chapter", overall=90,
                          scores={"beat_adherence": DimensionScore(score=90, critique="ok")})
    return FakeProvider(responses={
        "strategist": concept, "worldbuilder": World(setting="city of bells"),
        "character": chars, "outliner": outline,
        "writer": "Ara stepped into the tavern. The thief's work was about to begin.",
        "continuity": "[]", "editor": "Ara stepped into the tavern.",
        "scorer": passing,
        "extractor": {"character_states": {}, "voice_samples": {}, "mannerisms_used": {},
              "key_events": [], "threads_advanced": [], "new_information_revealed": []},
    }, tag_key="agent")


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
    provider = _make_provider(cfg)
    from novel.agents.strategist import StrategistAgent
    concept = StrategistAgent(provider, cfg.model_for("strategist")).run(text)
    StoryBible(proj).set_concept(concept)
    console.print(f"[green]Concept saved.[/green] genre={concept.genre}")


@app.command(name="write-chapter")
def write_chapter(n: int = typer.Argument(1, help="number of chapters to write"),
                  project: Path | None = _project_opt) -> None:
    """Write the next N chapters end-to-end (demo or live)."""
    proj = _load_project(project)
    cfg = load_config(proj.config_path)
    provider = _make_provider(cfg)
    bible = StoryBible(proj)
    vector = VectorMemory(proj, embed=hash_embed)
    from novel.graph import run_full_pipeline
    cfg_map = {name: cfg.model_for(name) for name in
               ["strategist", "worldbuilder", "character", "outliner", "writer",
                "continuity", "editor", "scorer", "extractor"]}
    existing = sorted((proj.root / "chapters").glob("[0-9][0-9][0-9].md"))
    start_chapter = int(existing[-1].stem) + 1 if existing else 1
    run_full_pipeline(provider=provider, cfg_map=cfg_map, bible=bible, vector=vector,
                      proj=proj, premise=bible.get_concept().logline,
                      target_chapters=start_chapter - 1 + n, start_chapter=start_chapter,
                      score_min=cfg.thresholds.score_min, max_retries=cfg.thresholds.max_retries,
                      token_budget=cfg.generation.context_token_budget,
                      on_gate=_gate if os.environ.get("NOVEL_LIVE") == "1" else None)
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