# 设定工作台（标准模式）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a guided "standard mode" (`novel setup` / GUI 设定流程) where the four setup stages (concept / world / characters / outline) are generated one at a time, shown to the user, and refined via accumulated natural-language feedback until approved — coexisting with the existing one-shot auto mode.

**Architecture:** UI-agnostic core in a new `novel/setup_flow.py` (`stage_done` / `generate_stage` / `approve_stage`); `Agent.run` gains an optional `feedback: list[str]` that appends one user message to the prompt. `run_full_pipeline`'s SETUP block is rewritten to call `setup_flow` and to skip setup entirely when the bible already has an outline (that IS the mode switch — no config flag). GUI reuses the Gate bridge, extended with a `feedback` text field, plus a `setup_stage` SSE event.

**Tech Stack:** Python 3.11+, typer, rich, FastAPI, vanilla JS (no build step), pytest with FakeProvider (no network).

**Spec:** `docs/superpowers/specs/2026-08-15-setup-workbench-design.md` (gitignored by repo convention).

## Global Constraints

- All tests use `FakeProvider` / `demo_provider()` — no network, no `NOVEL_LIVE=1`.
- `uv run pytest -q`, `uv run ruff check .` (line-length 100), `uv run mypy novel` (strict) must pass before each commit. Only `novel/` is typechecked.
- Existing behavior of the auto mode must stay identical (existing tests unmodified).
- `novel.runtime.demo_provider()` already returns a FakeProvider with canned responses for all four setup stages (`strategist`/`worldbuilder`/`character`/`outliner`) — reuse it in setup tests.

## Reference facts (do not re-derive)

- Agents: `StrategistAgent(Agent[str, Concept])`, `WorldbuilderAgent(Agent[Concept, World])`, `CharacterAgent(Agent[tuple[Concept, World], list[Character]])`, `OutlinerAgent(Agent[tuple[Concept, World, list[Character]], Outline])`. `Agent.run(inputs)` → `build_messages` → `complete_structured` with validation retries (novel/agents/base.py:26-44).
- Bible (novel/store/bible.py): `set_concept`/`get_concept`, `set_world`/`get_world`, `set_outline`/`get_outline`, `upsert_character`, `all_characters`, `add_foreshadow`, `list_foreshadow`.
- `Outline.foreshadow_ledger: list[ForeshadowLedgerEntry]` with `.id`, `.description`, `.planted_in`; `_parse_ch(ref)` in novel/graph.py:38-41 extracts an int chapter number (only used there; no test references).
- `novel/graph.py` SETUP block is the `if start_chapter <= 1:` branch (lines ~69-91); the else branch asserts outline and sets `chapter_no = start_chapter - 1`.
- GUI: `Gate` dataclass + `Job.gate()` in novel/ui/jobs.py (blocks on `threading.Event`, resolved via `JobManager.resolve_gate(gate_id, approved)`); `POST /api/gates/{id}` takes `GateReq(approve: bool)`; `GET /api/jobs/{id}` returns id/kind/status/error/project. Frontend: `showGate`/`resolveGate` in novel/ui/static/app.js, `gate-card` markup in index.html.
- FakeProvider `_lookup` raises KeyError for an agent tag with no canned response — absence of a response proves an agent was NOT called.

## File Structure

- Modify: `novel/agents/base.py` (feedback param), `novel/graph.py` (SETUP via setup_flow + skip rule), `novel/cli.py` (setup command), `novel/ui/jobs.py` (Gate.feedback, gate_with_feedback, run_setup_job), `novel/ui/app.py` (GateReq.feedback, /setup endpoint, job gates), `novel/ui/static/{index.html,app.js,style.css}` (setup UI), `README.md`.
- Create: `novel/setup_flow.py`, `tests/test_setup_flow.py`.

---

### Task 1: `Agent.run` feedback parameter

**Files:**
- Modify: `novel/agents/base.py:26-27`
- Test: `tests/test_agents_base.py` (append)

- [ ] **Step 1: Write the failing test**

```python
def test_run_appends_feedback_message():
    from pydantic import BaseModel

    from novel.agents.base import Agent
    from novel.config import ModelConfig

    class Out(BaseModel):
        text: str = "ok"

    class Dummy(Agent[str, Out]):
        name = "dummy"
        output_schema = Out

        def build_messages(self, inputs: str) -> list[dict]:
            return [{"role": "user", "agent": "dummy", "content": inputs}]

    seen: list[list[dict]] = []

    class Recording:
        def complete(self, messages, cfg, *, seed=None):  # pragma: no cover - unused path
            raise NotImplementedError

        def complete_structured(self, messages, schema, cfg, *, seed=None):
            seen.append(messages)
            return schema(text="ok")

    Dummy(Recording(), ModelConfig("x", "y")).run("hello", feedback=["第一版不行", "主角改成女性"])
    assert len(seen) == 1
    last = seen[0][-1]
    assert last["role"] == "user"
    assert "USER FEEDBACK" in last["content"]
    assert "第一版不行" in last["content"] and "主角改成女性" in last["content"]
    # no feedback -> identical messages as before
    Dummy(Recording(), ModelConfig("x", "y")).run("hello")
    assert len(seen) == 2 and seen[1] == seen[0][:1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_agents_base.py::test_run_appends_feedback_message -q`
Expected: FAIL — `run() got an unexpected keyword argument 'feedback'`.

- [ ] **Step 3: Implement**

In `novel/agents/base.py`, replace the first two lines of `run`:

```python
    def run(self, inputs: I, *, feedback: list[str] | None = None) -> O:
        messages = self.build_messages(inputs)
        if feedback:
            messages = messages + [
                {
                    "role": "user",
                    "agent": self.name,
                    "content": "[USER FEEDBACK — apply ALL of these to your output]\n"
                               + "\n".join(f"- {f}" for f in feedback),
                }
            ]
```

(rest of `run` unchanged).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_agents_base.py -q && uv run mypy novel`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add novel/agents/base.py tests/test_agents_base.py
git commit -m "feat(setup): Agent.run accepts accumulated user feedback"
```

---

### Task 2: `novel/setup_flow.py` — core stage functions

**Files:**
- Create: `novel/setup_flow.py`
- Test: `tests/test_setup_flow.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_setup_flow.py`:

```python
"""Guided setup flow: stage generation, feedback threading, persistence, re-entry skip."""
from __future__ import annotations

from novel.config import ModelConfig
from novel.project import NovelProject
from novel.providers import FakeProvider
from novel.runtime import AGENT_NAMES, demo_provider
from novel.setup_flow import SETUP_STAGES, approve_stage, generate_stage, stage_done
from novel.store.bible import StoryBible


def _proj_bible(tmp_path):
    proj = NovelProject.scaffold("n", genre="fantasy", root=tmp_path)
    return proj, StoryBible(proj)


def _cfg_map() -> dict[str, ModelConfig]:
    return {name: ModelConfig("zhipu", "x") for name in AGENT_NAMES}


class _RecordingProvider:
    """FakeProvider wrapper that records the messages sent for each agent."""

    def __init__(self) -> None:
        self._inner: FakeProvider = demo_provider()
        self.messages: list[tuple[str, list[dict]]] = []

    def complete(self, messages, cfg, *, seed=None):  # pragma: no cover - setup uses structured
        self.messages.append(("raw", messages))
        return self._inner.complete(messages, cfg, seed=seed)

    def complete_structured(self, messages, schema, cfg, *, seed=None):
        agent = str(messages[0].get("agent", "?"))
        self.messages.append((agent, messages))
        return self._inner.complete_structured(messages, schema, cfg, seed=seed)


def test_stage_done_progression(tmp_path):
    _proj, bible = _proj_bible(tmp_path)
    assert [stage_done(s, bible) for s in SETUP_STAGES] == [False, False, False, False]
    concept = generate_stage("concept", provider=demo_provider(), cfg_map=_cfg_map(),
                             bible=bible, premise="a thief")
    approve_stage("concept", concept, bible)
    assert stage_done("concept", bible) and not stage_done("world", bible)
    world = generate_stage("world", provider=demo_provider(), cfg_map=_cfg_map(), bible=bible)
    approve_stage("world", world, bible)
    chars = generate_stage("characters", provider=demo_provider(), cfg_map=_cfg_map(), bible=bible)
    approve_stage("characters", chars, bible)
    assert stage_done("characters", bible)
    outline = generate_stage("outline", provider=demo_provider(), cfg_map=_cfg_map(), bible=bible)
    approve_stage("outline", outline, bible)
    assert all(stage_done(s, bible) for s in SETUP_STAGES)
    assert bible.get_outline() is not None and bible.get_concept() is not None
    assert bible.get_world() is not None and bible.all_characters()


def test_feedback_threaded_into_agent_messages(tmp_path):
    _proj, bible = _proj_bible(tmp_path)
    provider = _RecordingProvider()
    generate_stage("concept", provider=provider, cfg_map=_cfg_map(), bible=bible,
                   premise="a thief", feedback=["主角改成女性", "基调更黑暗"])
    (agent, messages), = provider.messages
    assert agent == "strategist"
    assert "主角改成女性" in messages[-1]["content"]
    assert "基调更黑暗" in messages[-1]["content"]


def test_unknown_stage_raises(tmp_path):
    import pytest
    _proj, bible = _proj_bible(tmp_path)
    with pytest.raises(ValueError):
        stage_done("nope", bible)
    with pytest.raises(ValueError):
        generate_stage("nope", provider=demo_provider(), cfg_map=_cfg_map(), bible=bible)
```

Note: `_RecordingProvider.complete_structured` identifies the agent by `messages[0]["agent"]` — every agent's first message carries the `agent` tag key (see existing prompts; FakeProvider's `_agent_tag` relies on the same convention). If the first message lacks it, fall back to scanning all messages for an `agent` key.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_setup_flow.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'novel.setup_flow'`.

- [ ] **Step 3: Implement**

Create `novel/setup_flow.py`:

```python
"""Guided setup (标准模式): stage-by-stage generation with accumulated user feedback.

UI-agnostic core shared by the CLI `setup` command, the GUI setup job, and the
pipeline's one-shot SETUP block. Stages read their inputs from the bible, so the
flow is re-entrant: already-approved stages are skipped by callers via stage_done().
"""
from __future__ import annotations

import re

from novel.agents.character import CharacterAgent
from novel.agents.outliner import OutlinerAgent
from novel.agents.strategist import StrategistAgent
from novel.agents.worldbuilder import WorldbuilderAgent
from novel.config import ModelConfig
from novel.models import Character, Concept, Foreshadow, ForeshadowStatus, Outline, World
from novel.providers import ModelProvider
from novel.store.bible import StoryBible

SETUP_STAGES = ["concept", "world", "characters", "outline"]


def _parse_ch(ref: str) -> int | None:
    """Best-effort: 'c03-b01' / 'ch3' -> 3."""
    m = re.search(r"(\d+)", ref)
    return int(m.group(1)) if m else None


def stage_done(stage: str, bible: StoryBible) -> bool:
    if stage == "concept":
        return bible.get_concept() is not None
    if stage == "world":
        return bible.get_world() is not None
    if stage == "characters":
        return bool(bible.all_characters())
    if stage == "outline":
        return bible.get_outline() is not None
    raise ValueError(f"unknown setup stage: {stage}")


def generate_stage(stage: str, *, provider: ModelProvider, cfg_map: dict[str, ModelConfig],
                   bible: StoryBible, premise: str = "",
                   feedback: list[str] | None = None) -> object:
    """Run the stage's agent WITHOUT persisting anything. Inputs come from the bible."""
    fb = list(feedback or [])
    if stage == "concept":
        text = premise or (bible.get_concept().logline if bible.get_concept() else "")
        return StrategistAgent(provider, cfg_map["strategist"]).run(text, feedback=fb)
    if stage == "world":
        concept = bible.get_concept()
        assert concept is not None, "concept must be approved before world"
        return WorldbuilderAgent(provider, cfg_map["worldbuilder"]).run(concept, feedback=fb)
    if stage == "characters":
        concept = bible.get_concept()
        world = bible.get_world()
        assert concept is not None and world is not None, "concept+world required"
        return CharacterAgent(provider, cfg_map["character"]).run((concept, world), feedback=fb)
    if stage == "outline":
        concept = bible.get_concept()
        world = bible.get_world()
        assert concept is not None and world is not None, "concept+world required"
        return OutlinerAgent(provider, cfg_map["outliner"]).run(
            (concept, world, list(bible.all_characters())), feedback=fb)
    raise ValueError(f"unknown setup stage: {stage}")


def approve_stage(stage: str, artifact: object, bible: StoryBible) -> None:
    """Persist an approved artifact into the story bible."""
    if stage == "concept":
        assert isinstance(artifact, Concept)
        bible.set_concept(artifact)
    elif stage == "world":
        assert isinstance(artifact, World)
        bible.set_world(artifact)
    elif stage == "characters":
        assert isinstance(artifact, list)
        for ch in artifact:
            assert isinstance(ch, Character)
            bible.upsert_character(ch)
    elif stage == "outline":
        assert isinstance(artifact, Outline)
        bible.set_outline(artifact)
        for entry in artifact.foreshadow_ledger:
            if not any(f.id == entry.id for f in bible.list_foreshadow()):
                bible.add_foreshadow(Foreshadow(
                    id=entry.id, description=entry.description,
                    planted_ch=_parse_ch(entry.planted_in), status=ForeshadowStatus.OPEN))
    else:
        raise ValueError(f"unknown setup stage: {stage}")
```

Do NOT touch `novel/graph.py` in this task — its local `_parse_ch` stays for now (Task 3 removes it when graph switches to `setup_flow`; the brief duplication between Tasks 2 and 3 lives only on this feature branch).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_setup_flow.py -q && uv run ruff check . && uv run mypy novel`
Expected: PASS (3 tests), lint/types clean.

- [ ] **Step 5: Commit**

```bash
git add novel/setup_flow.py tests/test_setup_flow.py
git commit -m "feat(setup): setup_flow core — stage_done/generate_stage/approve_stage"
```

---

### Task 3: `graph.py` — SETUP via setup_flow + skip when outline exists

**Files:**
- Modify: `novel/graph.py` (imports; SETUP/resume branch ~lines 38-41, 69-100)
- Test: `tests/test_setup_flow.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_setup_flow.py`:

```python
def test_pipeline_skips_setup_when_outline_exists(tmp_path):
    """One-shot SETUP must not rerun when the bible already has settings (standard mode)."""
    from novel.models import Arc, ChapterBeat, ChapterOutline, DimensionScore, Outline, \
        ReviewScore, World
    from novel.providers import FakeProvider, ModelConfig
    from novel.store.vector import VectorMemory, hash_embed
    from novel.graph import run_full_pipeline

    _proj, bible = _proj_bible(tmp_path)
    concept = generate_stage("concept", provider=demo_provider(), cfg_map=_cfg_map(),
                             bible=bible, premise="a thief")
    approve_stage("concept", concept, bible)
    world = generate_stage("world", provider=demo_provider(), cfg_map=_cfg_map(), bible=bible)
    approve_stage("world", world, bible)
    chars = generate_stage("characters", provider=demo_provider(), cfg_map=_cfg_map(), bible=bible)
    approve_stage("characters", chars, bible)
    outline = generate_stage("outline", provider=demo_provider(), cfg_map=_cfg_map(), bible=bible)
    approve_stage("outline", outline, bible)

    beat = ChapterBeat(pov="Ara", setting="tavern", event="meet informant",
                       emotional_turn="doubt", characters=["c1"])
    rewritten = Outline(arcs=[Arc(arc_name="A", chapters=[
        ChapterOutline(chapter_no=1, chapter_title="T1", beats=[beat])])])
    bible.set_outline(rewritten)  # single-chapter outline for the run
    passing = ReviewScore(artifact_type="chapter", overall=90,
                          scores={"beat_adherence": DimensionScore(score=90, critique="ok")})
    # provider has ONLY chapter-loop agents: any setup agent call raises KeyError
    provider = FakeProvider(responses={
        "writer": "Chapter prose that is long enough to be complete.",
        "continuity": "[]", "editor": "Chapter prose that is long enough to be complete.",
        "scorer": passing,
        "extractor": {"character_states": {}, "voice_samples": {}, "mannerisms_used": {},
                      "key_events": [], "threads_advanced": [], "new_information_revealed": []},
    }, tag_key="agent")
    cfg_map = {name: ModelConfig("zhipu", "x") for name in
               ["strategist", "worldbuilder", "character", "outliner", "writer",
                "continuity", "editor", "scorer", "extractor"]}
    proj = NovelProject(root=_proj.root)
    state = run_full_pipeline(provider=provider, cfg_map=cfg_map, bible=bible,
                              vector=VectorMemory(proj, embed=hash_embed),
                              proj=proj, premise="a thief", target_chapters=1, start_chapter=1)
    assert state.error is None
    assert (proj.root / "chapters" / "001.md").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_setup_flow.py::test_pipeline_skips_setup_when_outline_exists -q`
Expected: FAIL with KeyError `'strategist'` — the current code reruns SETUP when `start_chapter <= 1`.

- [ ] **Step 3: Implement**

In `novel/graph.py`:

3a. Delete the local `_parse_ch` function (lines ~38-41).

3b. Add import: `from novel.setup_flow import approve_stage, generate_stage, stage_done` (with the other novel imports).

3c. Replace the whole `if start_chapter <= 1:` / `else:` setup/resume branch (lines ~69-100) with:

```python
    if start_chapter <= 1 and bible.get_outline() is None:
        # --- SETUP (one-shot auto mode; guided mode = `novel setup` approved these already) ---
        for stage, agent_name in (("concept", "strategist"), ("world", "worldbuilder"),
                                  ("characters", "character"), ("outline", "outliner")):
            emit({"type": "stage", "stage": agent_name})
            if stage_done(stage, bible):
                continue  # half-finished guided setup: only fill the gaps
            artifact = generate_stage(stage, provider=provider, cfg_map=cfg_map,
                                      bible=bible, premise=premise)
            approve_stage(stage, artifact, bible)
        outline = bible.get_outline()
        assert outline is not None
        if on_gate:
            on_gate("outline", outline)
        chapter_no = 0
    else:
        # --- RESUME: skip SETUP, load persisted bible state ---
        outline = bible.get_outline()
        assert outline is not None, "no outline to resume from"
        saved_concept = bible.get_concept()
        premise = premise or (saved_concept.logline if saved_concept else "")
        chapter_no = start_chapter - 1
        emit({"type": "stage", "stage": "resume", "chapter": start_chapter})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy novel`
Expected: full suite PASS (existing demo e2e / resume / review tests unchanged; `_parse_ch` deletion is safe — no other references).

- [ ] **Step 5: Commit**

```bash
git add novel/graph.py tests/test_setup_flow.py
git commit -m "feat(setup): pipeline SETUP via setup_flow; skip setup when outline exists"
```

---

### Task 4: CLI `novel setup` command

**Files:**
- Modify: `novel/cli.py` (new `setup` command)
- Test: `tests/test_cli.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py` (note: `premise` command exists; `setup` is new):

```python
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
    # concept: feedback once then approve; world: approve; characters: quit at outline
    result = runner.invoke(app, ["--project", str(proj), "setup", "--premise", "a thief"],
                           input="f\n主角改成女性\na\na\nq\n")
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -q`
Expected: FAIL — `No such command 'setup'`.

- [ ] **Step 3: Implement**

Add to `novel/cli.py` (after the `premise` command; imports follow the file's function-level style):

```python
@app.command()
def setup(premise: str = typer.Option("", "--premise", "-m",
                                      help="one-line premise (prompted if omitted)"),
          project: Path | None = _project_opt) -> None:
    """Guided setup (标准模式): approve or refine each stage with natural-language feedback."""
    proj = _load_project(project)
    cfg = load_config(proj.config_path)
    provider = make_provider(cfg)
    bible = StoryBible(proj)
    from novel.runtime import AGENT_NAMES, is_live_mode
    from novel.setup_flow import SETUP_STAGES, approve_stage, generate_stage, stage_done
    from novel.ui.jobs import artifact_text
    cfg_map = {name: cfg.model_for(name) for name in AGENT_NAMES}
    if not premise:
        saved = bible.get_concept()
        premise = saved.logline if saved else typer.prompt("Premise")
    if not is_live_mode():
        console.print("[yellow]演示模式：反馈不会改变生成内容。[/yellow]")
    for stage in SETUP_STAGES:
        if stage_done(stage, bible):
            console.print(f"[green]✓ {stage} 已通过，跳过[/green]")
            continue
        feedback: list[str] = []
        while True:
            console.rule(f"[bold cyan]{stage}[/bold cyan]（第 {len(feedback) + 1} 次生成）")
            artifact = generate_stage(stage, provider=provider, cfg_map=cfg_map,
                                      bible=bible, premise=premise, feedback=feedback)
            console.print(artifact_text(artifact)[:2000])
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
                continue
            console.print("[red]无效选择，请输入 a / f / q[/red]")
    console.print("[green]设定完成。运行 write-chapter 开始写作（会自动跳过设定阶段）。[/green]")
```

Note on the import `from novel.ui.jobs import artifact_text`: it renders pydantic models to pretty JSON. If importing from `novel.ui` in the CLI is undesirable (it is a small pure helper with no FastAPI dependency — check its imports; `jobs.py` imports fastapi-free modules at top level: threading/uuid/queue/pydantic only), keep it; otherwise move `artifact_text` to a neutral module in this step and update `jobs.py` to import it from there. Prefer the move if `novel.ui` gains heavy top-level deps later; for now the direct import is fine.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -q && uv run ruff check . && uv run mypy novel`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add novel/cli.py tests/test_cli.py
git commit -m "feat(setup): CLI guided setup command with feedback loop"
```

---

### Task 5: GUI backend — Gate.feedback, /setup endpoint, run_setup_job

**Files:**
- Modify: `novel/ui/jobs.py` (Gate.feedback, Job.gate_with_feedback, JobManager.resolve_gate, run_setup_job), `novel/ui/app.py` (GateReq.feedback, SetupReq, /setup route, job gates in GET /api/jobs)
- Test: `tests/test_ui.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ui.py`:

```python
def test_run_setup_job_feedback_then_approve(tmp_path: Path) -> None:
    """Jobs layer: feedback regenerates the stage, approvals persist everything."""
    from novel.project import NovelProject
    from novel.store.bible import StoryBible

    proj = NovelProject.scaffold("sp", genre="fantasy", root=tmp_path)
    m = jobs.JobManager()
    q = m.bus.subscribe("sp")
    job = m.start("sp", "setup", jobs.run_setup_job(proj.root, "a thief"))
    try:
        import time
        deadline = time.time() + 30.0
        sent_feedback = False
        while job.thread.is_alive() and time.time() < deadline:
            gate_id = _next_gate(q, job.id)
            if not sent_feedback:
                m.resolve_gate(gate_id, False, "主角改成女性")  # regenerate once
                sent_feedback = True
            else:
                m.resolve_gate(gate_id, True)  # approve everything else
        assert job.status == "done", job.error
        bible = StoryBible(proj)
        assert bible.get_concept() is not None and bible.get_outline() is not None
        assert bible.get_world() is not None and bible.all_characters()
    finally:
        job.thread.join(timeout=5)
    assert job.status == "done"


def _next_gate(q, job_id: str, timeout: float = 10.0) -> str:
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        for ev in jobs.drain(q, timeout=0.05):
            if ev.get("type") == "gate" and ev.get("job_id") == job_id:
                return str(ev["gate_id"])
        time.sleep(0.02)
    raise AssertionError("no gate event in time")


def test_setup_endpoint_full_flow(client: TestClient) -> None:
    client.post("/api/projects", json={"name": "sx"})
    r = client.post("/api/projects/sx/setup", json={"premise": "a thief"})
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    gate_id = _poll_gate_via_http(client, job_id)
    # feedback -> regenerate (gate for attempt 2 of the same stage)
    assert client.post("/api/gates/" + gate_id,
                       json={"approve": False, "feedback": "基调更黑暗"}).status_code == 200
    gate_id2 = _poll_gate_via_http(client, job_id)
    assert gate_id2 != gate_id
    assert client.post("/api/gates/" + gate_id2, json={"approve": True}).status_code == 200
    # approve the remaining stages (world / characters / outline) until the job ends
    import time
    deadline = time.time() + 30.0
    data = client.get(f"/api/jobs/{job_id}").json()
    while data["status"] == "running" and time.time() < deadline:
        gates = data.get("gates", [])
        if gates:
            client.post(f"/api/gates/{gates[0]['id']}", json={"approve": True})
        time.sleep(0.05)
        data = client.get(f"/api/jobs/{job_id}").json()
    assert data["status"] == "done", data.get("error")
    status = client.get("/api/projects/sx/status").json()
    assert status["has_concept"] is True and status["has_outline"] is True


def _poll_gate_via_http(client: TestClient, job_id: str, timeout: float = 10.0) -> str:
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"/api/jobs/{job_id}").json()
        for g in data.get("gates", []):
            return str(g["id"])
        time.sleep(0.05)
    raise AssertionError("job exposed no pending gate")
```

(These are demo-mode: gates fire for setup regardless of live mode because setup is inherently interactive — feedback simply doesn't change the canned output in demo.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ui.py -q`
Expected: FAIL — `run_setup_job` missing (AttributeError) and `POST /api/projects/sx/setup` → 404.

- [ ] **Step 3: Implement**

3a. `novel/ui/jobs.py`:

- `Gate` dataclass: add field `feedback: str | None = None` (after `approved`).
- Replace `Job.gate` with a delegating pair:

```python
    def gate(self, label: str, artifact: object) -> bool:
        return self.gate_with_feedback(label, artifact)[0]

    def gate_with_feedback(self, label: str, artifact: object) -> tuple[bool, str | None]:
        """Block until resolved; returns (approved, feedback_text). feedback is set only
        when the resolver supplied one (guided-setup regeneration requests)."""
        g = Gate(id=uuid.uuid4().hex[:12], label=label, artifact=artifact_text(artifact))
        self.gates[g.id] = g
        if self._bus is not None:
            self._bus.publish(self.project, {
                "type": "gate", "job_id": self.id, "gate_id": g.id,
                "label": label, "artifact": g.artifact,
            })
        while not g.done.wait(timeout=0.25):
            if self.cancel.is_set():
                return False, None
        return g.approved, g.feedback
```

- `JobManager.resolve_gate` gains a feedback parameter:

```python
    def resolve_gate(self, gate_id: str, approved: bool,
                     feedback: str | None = None) -> bool:
        for job in self._jobs.values():
            g = job.gates.get(gate_id)
            if g is not None:
                if g.done.is_set():
                    return False  # already resolved or cancelled
                g.approved = approved
                g.feedback = feedback
                g.done.set()
                return True
        return False
```

- New job factory (place next to `run_premise_job`):

```python
def run_setup_job(proj_root: Path, premise: str) -> Callable[[Job], object]:
    """Guided setup: per stage, block on a gate that carries approve-or-feedback."""
    def fn(job: Job) -> object:
        from novel.config import load_config
        from novel.project import NovelProject
        from novel.runtime import AGENT_NAMES, make_provider
        from novel.setup_flow import SETUP_STAGES, approve_stage, generate_stage, stage_done
        from novel.store.bible import StoryBible

        proj = NovelProject(root=proj_root)
        cfg = load_config(proj.config_path)
        provider = make_provider(cfg)
        bible = StoryBible(proj)
        cfg_map = {name: cfg.model_for(name) for name in AGENT_NAMES}
        for stage in SETUP_STAGES:
            if stage_done(stage, bible):
                job.emit({"type": "setup_stage", "stage": stage, "attempt": 0, "skipped": True})
                continue
            feedback: list[str] = []
            while True:
                artifact = generate_stage(stage, provider=provider, cfg_map=cfg_map,
                                          bible=bible, premise=premise, feedback=feedback)
                job.emit({"type": "setup_stage", "stage": stage, "attempt": len(feedback) + 1,
                          "artifact": artifact_text(artifact)})
                approved, fb = job.gate_with_feedback(f"setup:{stage}", artifact)
                if approved:
                    approve_stage(stage, artifact, bible)
                    break
                if not fb:
                    job.emit({"type": "setup_stage", "stage": stage, "attempt": 0,
                              "skipped": True})
                    return None  # rejected without feedback: stop cleanly, keep approved stages
                feedback.append(fb)
        return None
    return fn
```

3b. `novel/ui/app.py`:

- `GateReq` gains feedback; new request model + route:

```python
class GateReq(BaseModel):
    approve: bool
    feedback: str = ""


class SetupReq(BaseModel):
    premise: str = ""
```

- In `resolve_gate` route: `ok = manager.resolve_gate(gate_id, req.approve, req.feedback or None)`.
- New route after `start_write`:

```python
    @app.post("/api/projects/{name}/setup", status_code=202)
    def start_setup(name: str, req: SetupReq) -> dict[str, str]:
        p = _safe_project(root, name)
        try:
            job = manager.start(name, "setup", jobs.run_setup_job(p, req.premise))
        except RuntimeError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        return {"job_id": job.id}
```

- `job_status` route: expose pending gates so clients (and tests) can find them:

```python
        return {"id": job.id, "kind": job.kind, "status": job.status,
                "error": job.error, "project": job.project,
                "gates": [{"id": g.id, "label": g.label}
                          for g in job.gates.values() if not g.done.is_set()]}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ui.py -q && uv run pytest -q && uv run ruff check . && uv run mypy novel`
Expected: PASS (existing gate-bridge tests unaffected — `gate()` semantics unchanged).

- [ ] **Step 5: Commit**

```bash
git add novel/ui/jobs.py novel/ui/app.py tests/test_ui.py
git commit -m "feat(setup): GUI backend — gate feedback channel, /setup endpoint, setup job"
```

---

### Task 6: GUI frontend — setup UI

**Files:**
- Modify: `novel/ui/static/index.html`, `novel/ui/static/app.js`, `novel/ui/static/style.css`

No JS test framework exists; this task is verified by the backend tests (Task 5) plus a manual smoke check (Step 4). Frontend changes must stay vanilla JS, no build step.

- [ ] **Step 1: index.html**

In the premise area (next to `btn-premise`), add:

```html
<button id="btn-setup" class="btn secondary" type="button">分阶段设定（标准模式）</button>
```

Inside the `gate-card` element (after `gate-artifact`, before the buttons), add a hidden feedback box:

```html
<textarea id="gate-feedback" rows="3" placeholder="修改意见（自然语言），系统会带着意见重新生成该阶段…"
          hidden></textarea>
```

- [ ] **Step 2: app.js**

2a. Extend `STAGE_NAMES`:

```js
  concept: "生成故事概念",
  world: "构建世界观",
  characters: "设计人物",
  outline: "编排大纲",
```

2b. `showGate(m)` — after the existing lines, add setup-gate handling:

```js
  const isSetup = String(m.label).startsWith("setup:");
  $("gate-feedback").hidden = !isSetup;
  $("gate-feedback").value = "";
  $("btn-reject").textContent = isSetup ? "带反馈重生成" : "拒绝";
```

2c. `resolveGate(approve)` — send feedback on setup rejection:

```js
async function resolveGate(approve) {
  const id = $("gate-card").dataset.gateId;
  if (!id) return;
  let feedback = "";
  if (!approve && !$("gate-feedback").hidden) {
    feedback = $("gate-feedback").value.trim();
    if (!feedback) { alert("请填写修改意见，或点击「通过」"); return; }
  }
  $("btn-approve").disabled = true;
  $("btn-reject").disabled = true;
  await api(`/api/gates/${id}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approve, feedback }),
  });
  log(approve ? "已批准" : "已提交反馈，重新生成中…");
  closeGate();
}
```

(Replace the existing `resolveGate` entirely.)

2d. Add setup gate labels next to `GATE_LABELS`:

```js
const SETUP_STAGE_NAMES = {
  concept: "故事概念", world: "世界观", characters: "人物", outline: "大纲",
};
```

and in `GATE_LABELS` handling inside `showGate`, map `setup:<stage>` labels:

```js
  if (String(m.label).startsWith("setup:")) {
    const st = m.label.slice(6);
    $("gate-label").textContent = `设定阶段：${SETUP_STAGE_NAMES[st] || st} — 通过还是修改？`;
  } else {
    $("gate-label").textContent = GATE_LABELS[m.label] || m.label;
  }
```

2e. `handleEvent` — add a case (before `case "gate":`):

```js
    case "setup_stage":
      if (m.skipped) log(`设定阶段 ${m.stage} 已通过，跳过`);
      else log(`设定阶段 ${m.stage}：第 ${m.attempt} 次生成（见审批卡片）`);
      break;
```

2f. New action + wiring (next to `startPremise`):

```js
async function startSetup() {
  const premiseText = $("premise-input").value.trim();
  try {
    const r = await api(`/api/projects/${state.project}/setup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ premise: premiseText }),
    });
    state.jobId = r.job_id;
    $("btn-cancel").hidden = false;
    log(`▶ 开始分阶段设定${premiseText ? `：${premiseText}` : ""}`);
    setStatus("设定流程启动…");
  } catch (e) { alert(e.message); }
}
```

and `$("btn-setup").onclick = startSetup;` in the wiring block at the bottom.

- [ ] **Step 3: style.css**

Style the feedback textarea to match existing inputs:

```css
#gate-feedback {
  width: 100%;
  margin-top: 8px;
  border: 1px solid var(--border, #ccc);
  border-radius: 6px;
  padding: 8px;
  font: inherit;
  resize: vertical;
}
```

(Adapt to the file's actual CSS variables/class names.)

- [ ] **Step 4: Manual smoke check (not committed)**

`uv run novel-ui --root /tmp/setup-smoke --no-browser`, create a project, click 分阶段设定, verify: gate card shows stage artifact, textarea visible, 「带反馈重生成」with empty text prompts, feedback regenerates (same content in demo), 通过 advances stages, job ends done, chapters then generate without rerunning setup. Record observations in the task report.

- [ ] **Step 5: Commit**

```bash
git add novel/ui/static
git commit -m "feat(setup): GUI setup flow — stage cards, feedback box, setup action"
```

---

### Task 7: README sync + full gate

**Files:**
- Modify: `README.md`

- [ ] **Step 1:** In 「完整操作流程」 add a new subsection after 「### 2. 生成故事概念」 titled 「### 2b. 标准模式：分阶段设定（可选）」 describing: `uv run novel setup --premise "..."`（省略 --premise 时会用已保存概念的 logline 或提示输入）; 每阶段 通过(a)/反馈(f)/退出(q); 反馈逐条累积; 中断重跑跳过已通过阶段; 设定完成后 write-chapter 自动跳过设定阶段; 演示模式不响应反馈。Include the 「重做设定警示」：对已有章节的项目重跑 setup 会替换 bible 设定，只影响后续章节，不回写既有章节。
- [ ] **Step 2:** In 「图形界面（Web GUI）」 bullet list add one bullet: 分阶段设定（标准模式）——点击「分阶段设定」逐阶段审批，卡片内可填自然语言修改意见让系统重生成。
- [ ] **Step 3:** In 「可用子命令」 text block add `setup` 一行。
- [ ] **Step 4: Full gate**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy novel`
Expected: all PASS / clean.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: README — 标准模式（分阶段设定）用法与警示"
```

---

## Self-Review

**1. Spec coverage:** feedback threading (T1), setup_flow core + re-entry (T2), pipeline skip rule + half-setup gap filling (T3), CLI guided flow incl. demo notice and quit/re-entry (T4), GUI feedback channel + endpoint + events (T5), GUI UI (T6), README incl. demo/重做警示 (T7). Spec's error-handling section: half-done setup + write-chapter (T3 stage-skip loop), cancel/quit keeping approved stages (T4/T5), validation retries orthogonal (T1 leaves base retry loop untouched). ✅

**2. Placeholder scan:** every code step contains complete code or exact file/anchor instructions; no TBD/TODO/"similar to Task N". Task 6 Step 4 is an explicit manual check with instructions, not a placeholder. ✅

**3. Type consistency:** `generate_stage(stage, *, provider, cfg_map, bible, premise="", feedback=None)` identical at all four call sites (graph T3, CLI T4, jobs T5, tests T2/T3). `gate_with_feedback -> tuple[bool, str | None]` matches both callers. `GateReq(approve, feedback="")` matches the JS body `{approve, feedback}`. `setup_stage` event keys (`stage`, `attempt`, `artifact`, `skipped`) match the JS handler. mypy strict is satisfied by `assert isinstance` narrowing in `approve_stage`. ✅

**Known deferred (recorded, not blocking):** `artifact_text` lives in `novel/ui/jobs.py` but is imported by the CLI (T4) — acceptable because its top-level imports are stdlib+pydantic; move to a neutral module if `novel.ui` ever gains heavy top-level deps.
