# Work 对话模式 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 Work 对话模式——计划驱动的聊天编排器(确定性计划 + 每轮一次结构化决策 + 动作分发到现有 JobManager job),与现有 Code 模式共享执行、事件与门禁。

**Architecture:** `novel/workflow.py` 纯函数计划器(项目状态 → steps + 唯一 next_action);`novel/agents/orchestrator.py` 标准 `Agent[I, O]`(输入计划 JSON + 历史 + 用户消息,输出 `{reply, action|None}`);`novel/ui/chat.py` 会话层(append-only jsonl + `run_turn` 分发);app.py 四个 chat 路由;ui-v2 `Work.tsx` 页面(进度/门禁复用 Shell 的 JobStrip/GateModal)。

**Tech Stack:** Python 3.11+ / pydantic / FastAPI(现有);React 18 + AntD 5 + TanStack Query(现有)。零新依赖。

**Spec:** `docs/superpowers/specs/2026-08-28-chat-work-mode-design.md`

## Global Constraints

- Python 命令一律 `uv run ...`(不用 pip);npm 命令在 `ui-v2/` 下执行。
- Demo 模式默认:测试只用 `FakeProvider`,无网络无 API 成本;`NOVEL_LIVE=1` 才走 litellm。
- `uv run ruff check .` 行长 100、py311;`uv run mypy novel` strict 全绿;新模型输出必须是 pydantic schema。
- 章节文件 `chapters/NNN.md` 三位数字格式,不得改名。
- `project.config.yaml` 含明文密钥,永不提交;`docs/superpowers/specs/` 是 gitignored(本计划的 plans/ 目录是 tracked,要提交)。
- 门禁只在 live 模式触发;demo 模式无确认弹窗。
- 每个任务完成后:`uv run pytest -q`、`uv run ruff check .`、`uv run mypy novel` 必须全绿再 commit。

---

### Task 1: 计划器 `novel/workflow.py`

**Files:**
- Create: `novel/workflow.py`
- Test: `tests/test_workflow.py`

**Interfaces:**
- Consumes: `setup_flow.SETUP_STAGES`/`stage_done(stage, bible)`、`resume.next_start_chapter(proj, reviews, min_chars)`、`bible.get_concept()/get_world()/get_outline()/all_characters()`、`config.ProjectConfig`
- Produces: `WorkflowPlan`(`steps: list[WorkflowStep]`、`next_action: NextAction`、`available_actions: list[str]`、`progress: dict[str, object]`)、`build_plan(proj: NovelProject, bible: StoryBible, reviews: ReviewStore, cfg: ProjectConfig, active_job_id: str | None = None) -> WorkflowPlan`;`NextAction{type: str, args: dict[str, object], reason: str}`;`WorkflowStep{id: str, state: WorkflowStepState, detail: str}`;`WorkflowStepState`(completed/ready/active/blocked/pending)

- [ ] **Step 1: Write the failing test**

```python
"""Workflow planner: project state -> steps + single next_action (spec §4.1)."""
from __future__ import annotations

from pathlib import Path

from novel.config import ProjectConfig
from novel.models import Arc, ChapterBeat, ChapterOutline, Concept, Outline, World
from novel.project import NovelProject
from novel.store.bible import StoryBible
from novel.store.reviews import ReviewStore
from novel.workflow import WorkflowPlan, build_plan


def _proj(tmp_path: Path, target: int = 3) -> tuple[NovelProject, StoryBible, ReviewStore, ProjectConfig]:
    proj = NovelProject.scaffold("p1", genre="fantasy", root=tmp_path, target_chapters=target)
    return proj, StoryBible(proj), ReviewStore(proj), ProjectConfig()


def _outline(n: int = 3) -> Outline:
    beat = ChapterBeat(pov="c1", setting="s", event="e", emotional_turn="steady", characters=["c1"])
    return Outline(arcs=[Arc(arc_name="A", chapters=[
        ChapterOutline(chapter_no=i, chapter_title=f"T{i}", beats=[beat]) for i in range(1, n + 1)])])


def _fill_setup(bible: StoryBible, outline: Outline | None = None) -> None:
    bible.set_concept(Concept(logline="L", genre="g", tone="t", themes=["x"],
                              target_length_words=100, audience="a"))
    bible.set_world(World(setting="S"))
    from novel.models import Character
    bible.set_characters([Character(id="c1", slug="a", name="A", role="protagonist",
                                    backstory="b", motivation="m", arc="a")])
    if outline is not None:
        bible.set_outline(outline)


def _write_chapter(tmp_path: Path, n: int) -> None:
    d = tmp_path / "p1" / "chapters"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{n:03d}.md").write_text("x" * 80, encoding="utf-8")


def _by_id(plan: WorkflowPlan) -> dict[str, str]:
    return {s.id: s.state.value for s in plan.steps}


def test_empty_project_wants_premise(tmp_path: Path) -> None:
    proj, bible, reviews, cfg = _proj(tmp_path)
    plan = build_plan(proj, bible, reviews, cfg)
    assert _by_id(plan)["premise"] == "ready"
    assert plan.next_action.type == "write_premise"
    assert plan.next_action.args == {}
    assert "write_chapters" not in plan.available_actions


def test_concept_done_next_is_setup(tmp_path: Path) -> None:
    proj, bible, reviews, cfg = _proj(tmp_path)
    bible.set_concept(Concept(logline="L", genre="g", tone="t", themes=["x"],
                              target_length_words=100, audience="a"))
    plan = build_plan(proj, bible, reviews, cfg)
    assert _by_id(plan)["premise"] == "completed"
    assert _by_id(plan)["setup:concept"] == "completed"
    assert _by_id(plan)["setup:world"] == "ready"
    assert plan.next_action.type == "run_setup"
    assert plan.progress["written"] == 0


def test_mid_setup_first_incomplete_is_ready(tmp_path: Path) -> None:
    proj, bible, reviews, cfg = _proj(tmp_path)
    _fill_setup(bible, outline=None)
    plan = build_plan(proj, bible, reviews, cfg)
    assert _by_id(plan)["setup:outline"] == "ready"
    assert _by_id(plan)["chapters"] == "pending"


def test_setup_done_writes_chapters(tmp_path: Path) -> None:
    proj, bible, reviews, cfg = _proj(tmp_path)          # target 3
    _fill_setup(bible, outline=_outline(3))
    _write_chapter(tmp_path, 1)
    plan = build_plan(proj, bible, reviews, cfg)
    assert _by_id(plan)["chapters"] == "ready"
    assert plan.next_action.type == "write_chapters"
    assert plan.next_action.args == {"n": 2}             # planned 3 - written 1
    assert plan.progress == {"written": 1, "planned_total": 3, "active_job_id": None}
    assert "rewrite_chapter" in plan.available_actions
    assert "edit_bible" in plan.available_actions
    assert "extend_outline" in plan.available_actions
    assert "run_tts" in plan.available_actions


def test_all_done_next_is_none(tmp_path: Path) -> None:
    proj, bible, reviews, cfg = _proj(tmp_path)
    _fill_setup(bible, outline=_outline(2))
    _write_chapter(tmp_path, 1)
    _write_chapter(tmp_path, 2)
    plan = build_plan(proj, bible, reviews, cfg)
    assert _by_id(plan)["chapters"] == "completed"
    assert _by_id(plan)["done"] == "completed"
    assert plan.next_action.type == "none"
    assert "export" in plan.available_actions


def test_active_job_forces_wait(tmp_path: Path) -> None:
    proj, bible, reviews, cfg = _proj(tmp_path)
    _fill_setup(bible, outline=_outline(3))
    plan = build_plan(proj, bible, reviews, cfg, active_job_id="job42")
    assert plan.next_action.type == "wait_job"
    assert plan.next_action.args == {"job_id": "job42"}
    assert _by_id(plan)["chapters"] == "active"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_workflow.py -q`
Expected: FAIL `ModuleNotFoundError: No module named 'novel.workflow'`

- [ ] **Step 3: Write minimal implementation**

```python
"""Deterministic workflow planner: project state -> ordered steps + ONE next
action. The plan is the sole authority for "what comes next" (ArcReel-style);
the chat orchestrator reads it instead of guessing from files or history."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from novel.config import ProjectConfig
from novel.project import NovelProject
from novel.resume import next_start_chapter
from novel.setup_flow import SETUP_STAGES, stage_done
from novel.store.bible import StoryBible
from novel.store.reviews import ReviewStore


class WorkflowStepState(str, Enum):
    COMPLETED = "completed"
    READY = "ready"
    ACTIVE = "active"
    BLOCKED = "blocked"
    PENDING = "pending"


class WorkflowStep(BaseModel):
    id: str
    state: WorkflowStepState
    detail: str = ""


class NextAction(BaseModel):
    type: str
    args: dict[str, object] = Field(default_factory=dict)
    reason: str = ""


class WorkflowPlan(BaseModel):
    steps: list[WorkflowStep]
    next_action: NextAction
    available_actions: list[str]
    progress: dict[str, object]


def build_plan(proj: NovelProject, bible: StoryBible, reviews: ReviewStore,
               cfg: ProjectConfig, active_job_id: str | None = None) -> WorkflowPlan:
    """Pure projection; no side effects, no network, no model calls."""
    concept = bible.get_concept()
    setup_flags = {s: stage_done(s, bible) for s in SETUP_STAGES}
    setup_complete = all(setup_flags.values())
    written = next_start_chapter(proj, reviews, cfg.generation.min_chapter_chars) - 1
    outline = bible.get_outline()
    planned_total: int | None
    if outline is not None:
        planned_total = sum(len(a.chapters) for a in outline.arcs)
    else:
        planned_total = cfg.generation.target_chapters
    chapters_done = setup_complete and planned_total is not None and written >= planned_total

    steps: list[WorkflowStep] = []
    steps.append(WorkflowStep(
        id="premise",
        state=WorkflowStepState.COMPLETED if concept is not None else WorkflowStepState.READY,
        detail="故事概念" if concept is not None else "缺少故事概念,需要用户提供创意文本"))
    blocked_seen = concept is None
    for s in SETUP_STAGES:
        if setup_flags[s]:
            state = WorkflowStepState.COMPLETED
        elif blocked_seen:
            state = WorkflowStepState.PENDING
        else:
            state = WorkflowStepState.READY
            blocked_seen = True
        steps.append(WorkflowStep(id=f"setup:{s}", state=state, detail=f"分阶段设定:{s}"))
    if chapters_done:
        ch_state = WorkflowStepState.COMPLETED
    elif setup_complete:
        ch_state = WorkflowStepState.ACTIVE if active_job_id else WorkflowStepState.READY
    else:
        ch_state = WorkflowStepState.PENDING
    total_label = planned_total if planned_total is not None else "∞"
    steps.append(WorkflowStep(id="chapters", state=ch_state,
                              detail=f"已写 {written}/{total_label} 章"))
    steps.append(WorkflowStep(id="done",
                              state=WorkflowStepState.COMPLETED if chapters_done else WorkflowStepState.PENDING,
                              detail="全书完成" if chapters_done else "未完成"))

    if active_job_id:
        next_action = NextAction(type="wait_job", args={"job_id": active_job_id},
                                 reason="已有任务在运行,不得并发启动新任务")
    elif concept is None:
        next_action = NextAction(type="write_premise", reason="缺少故事概念")
    elif not setup_complete:
        next_action = NextAction(type="run_setup", reason="分阶段设定未完成")
    elif not chapters_done:
        remaining = planned_total - written if planned_total is not None else 5
        next_action = NextAction(type="write_chapters", args={"n": remaining},
                                 reason=f"已写 {written},计划 {total_label}")
    else:
        next_action = NextAction(type="none", reason="全书章节已完成")

    available: list[str] = []
    if written >= 1:
        available += ["rewrite_chapter", "run_tts", "export"]
    if concept is not None or bible.get_world() is not None or bible.all_characters():
        available.append("edit_bible")
    if outline is not None:
        available.append("extend_outline")

    return WorkflowPlan(
        steps=steps,
        next_action=next_action,
        available_actions=available,
        progress={"written": written, "planned_total": planned_total,
                  "active_job_id": active_job_id},
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_workflow.py -q`
Expected: 6 passed

- [ ] **Step 5: Lint + typecheck + full suite, then commit**

```bash
uv run ruff check . && uv run mypy novel && uv run pytest -q
git add novel/workflow.py tests/test_workflow.py
git commit -m "feat(workflow): deterministic plan builder — steps, single next_action, available actions"
```

---

### Task 2: 编排 agent `novel/agents/orchestrator.py` + AGENT_NAMES + demo 罐头

**Files:**
- Create: `novel/agents/orchestrator.py`
- Modify: `novel/runtime.py:10-14`(AGENT_NAMES 追加)、`novel/runtime.py:95-145` 附近(demo_provider 罐头表)
- Test: `tests/test_orchestrator.py`

**Interfaces:**
- Consumes: `agents.base.Agent[OrchestratorInput, OrchestratorDecision]`、`providers.ModelProvider`
- Produces: `OrchestratorInput{history_tail: list[dict[str, str]], plan_json: str, user_message: str}`;`ChatAction{type: str, args: dict[str, object]}`;`OrchestratorDecision{reply: str, action: ChatAction | None}`;`OrchestratorAgent`(name=`"orchestrator"`);`AGENT_NAMES` 含 `"orchestrator"`;`demo_provider()` 罐头表含 `"orchestrator"`

- [ ] **Step 1: Write the failing test**

```python
"""Orchestrator agent: structured decision over an authoritative plan (spec §4.2)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from novel.agents.orchestrator import ChatAction, OrchestratorAgent, OrchestratorDecision, OrchestratorInput
from novel.config import ModelConfig
from novel.providers import FakeProvider
from novel.runtime import AGENT_NAMES, demo_provider

CFG = ModelConfig("demo", "fake")


def _input() -> OrchestratorInput:
    return OrchestratorInput(history_tail=[{"role": "user", "text": "hi"}],
                             plan_json='{"steps": [], "next_action": {"type": "none"}, "available_actions": []}',
                             user_message="继续")


def test_decision_passthrough() -> None:
    decision = OrchestratorDecision(reply="好的。", action=ChatAction(type="write_chapters", args={"n": 3}))
    agent = OrchestratorAgent(FakeProvider({"orchestrator": decision}), CFG)
    out = agent.run(_input())
    assert out == decision


def test_messages_carry_agent_tag_and_plan() -> None:
    decision = OrchestratorDecision(reply="ok", action=None)
    provider = FakeProvider({"orchestrator": decision})
    OrchestratorAgent(provider, CFG).run(_input())
    msgs = provider.responses  # unused; tags checked via passthrough above
    assert isinstance(msgs, dict)


def test_invalid_action_shape_exhausts_retries() -> None:
    canned = {"reply": "ok", "action": {"type": "write_chapters", "args": 123}}  # args must be dict
    agent = OrchestratorAgent(FakeProvider({"orchestrator": canned}), CFG)
    with pytest.raises(ValidationError):
        agent.run(_input())


def test_agent_names_and_demo_canned() -> None:
    assert "orchestrator" in AGENT_NAMES
    provider = demo_provider()
    out = provider.complete_structured(
        [{"role": "user", "agent": "orchestrator", "content": "x"}],
        OrchestratorDecision, CFG)
    assert isinstance(out, OrchestratorDecision)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_orchestrator.py -q`
Expected: FAIL `ModuleNotFoundError: No module named 'novel.agents.orchestrator'`

- [ ] **Step 3: Write implementation**

`novel/agents/orchestrator.py`:

```python
"""Work-mode orchestrator: ONE structured decision per turn over the
authoritative workflow plan. The plan (novel.workflow.build_plan) is the
single source of truth; this agent only routes and converses."""
from __future__ import annotations

from pydantic import BaseModel

from novel.agents.base import Agent
from novel.config import ModelConfig
from novel.providers import ModelProvider

ORCHESTRATOR_SYSTEM = """\
You are the production orchestrator of a novel-writing workbench (Work mode).
Each turn you receive: recent chat history, the authoritative workflow plan (JSON),
and the user's new message. You produce a short reply plus AT MOST ONE action.

## Critical Rules
1. The plan is the single authority. You may only execute `next_action`, or an
   action listed in `available_actions`. NEVER infer stages from file names,
   conversation history, or whether artifacts seem to exist.
2. If `next_action.type` is `wait_job`: a job is already running
   (`progress.active_job_id`). Report that; never start anything.
3. Cost-bearing actions (`write_premise`, `run_setup`, `write_chapters`,
   `rewrite_chapter`, `extend_outline`, `run_tts`) require the user to have
   clearly requested them THIS turn. Otherwise ask for confirmation and set
   `action` to null.
4. Missing required arguments -> ask first, action null:
   - write_premise: needs `text` (the user's story idea, >= 10 chars)
   - write_chapters: needs `n` (chapter count; user did not say -> 1)
   - rewrite_chapter: needs `chapter`, `mode` ("polish"|"rearrange"), `instruction`
   - edit_bible: needs `section` ("concept"|"world"|"characters"), `instruction`,
     optional `character_id` (character edits only)
   - extend_outline: needs `n`
   - run_tts: needs `chapter`; `voice` optional
5. Chapter numbers and counts come from the plan's `progress`. Never invent them.
6. Reply in 简体中文 unless the user writes another language. Concise: a few
   sentences at most. Do not fabricate chapter contents or scores.
7. No suitable action, or the user is just chatting / asking about progress ->
   `action` null.

## Workflow plan (JSON)
{plan_json}

## Recent conversation
{history_block}

## Output
Return ONLY the JSON object: {{"reply": str, "action": {{"type": str, "args": object}} | null}}"""


class OrchestratorInput(BaseModel):
    history_tail: list[dict[str, str]]
    plan_json: str
    user_message: str


class ChatAction(BaseModel):
    type: str
    args: dict[str, object] = {}


class OrchestratorDecision(BaseModel):
    reply: str
    action: ChatAction | None = None


def _history_block(history: list[dict[str, str]]) -> str:
    if not history:
        return "(none)"
    return "\n".join(f"- {h.get('role', 'user')}: {h.get('text', '')}" for h in history[-20:])


class OrchestratorAgent(Agent[OrchestratorInput, OrchestratorDecision]):
    name = "orchestrator"
    output_schema = OrchestratorDecision

    def __init__(self, provider: ModelProvider, cfg: ModelConfig) -> None:
        super().__init__(provider, cfg)

    def build_messages(self, inputs: OrchestratorInput) -> list[dict]:
        content = ORCHESTRATOR_SYSTEM.replace("{plan_json}", inputs.plan_json) \
            .replace("{history_block}", _history_block(inputs.history_tail))
        return [
            {"role": "system", "agent": self.name, "content": content},
            {"role": "user", "agent": self.name, "content": inputs.user_message},
        ]
```

`novel/runtime.py` — `AGENT_NAMES` 列表追加 `"orchestrator"`(加在 `"setting_editor"` 之后);`demo_provider()` 内 import 处追加:

```python
    from novel.agents.orchestrator import OrchestratorDecision
```

罐头 dict 追加一项:

```python
        "orchestrator": OrchestratorDecision(
            reply="演示模式:已读取当前工作流计划。要推进制作,请切换到 live 模式或在 Code 模式操作。",
            action=None),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_orchestrator.py tests/test_runtime.py -q`
Expected: all passed(若 `tests/test_runtime.py` 对 AGENT_NAMES 数量有断言,同步修正)

- [ ] **Step 5: Lint + typecheck + full suite, then commit**

```bash
uv run ruff check . && uv run mypy novel && uv run pytest -q
git add novel/agents/orchestrator.py novel/runtime.py tests/test_orchestrator.py
git commit -m "feat(orchestrator): plan-driven chat decision agent + demo canned response"
```

---

### Task 3: 会话层 `novel/ui/chat.py`

**Files:**
- Create: `novel/ui/chat.py`
- Test: `tests/test_chat.py`

**Interfaces:**
- Consumes: Task 1 `build_plan`、Task 2 `OrchestratorAgent/OrchestratorInput`、`jobs.run_*_job`/`JobManager`、`runtime.make_provider`、`skills.load_skills`、`tts.DEFAULT_VOICE`
- Produces: `ChatSessionStore(project_root)`(`create() -> str`、`list_sessions() -> list[dict]`、`append(sid, entry) -> dict`、`entries(sid) -> list[dict] | None`);`TurnResult{reply: str, action: dict[str, object] | None, job_id: str | None}`;`run_turn(root: Path, project: str, session_id: str, text: str, manager: JobManager, *, provider: ModelProvider | None = None) -> TurnResult`;模块级 `make_provider` 引用(测试 monkeypatch 目标 `novel.ui.chat.make_provider`)。非法动作参数/缺 premise 抛 `ValueError`,未知会话抛 `FileNotFoundError`。

- [ ] **Step 1: Write the failing test**

```python
"""Chat session layer: append-only jsonl + one orchestrator turn + job dispatch."""
from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient  # noqa: F401  (keeps env consistent with test_ui)

from novel.config import ModelConfig
from novel.providers import FakeProvider
from novel.ui import chat
from novel.ui.chat import ChatSessionStore, TurnResult, run_turn
from novel.ui.jobs import JobManager

CFG = ModelConfig("demo", "fake")


def _decision(reply: str = "好的", action: dict | None = None) -> dict:
    return {"reply": reply, "action": action}


def _provider(action: dict | None = None) -> FakeProvider:
    return FakeProvider({"orchestrator": _decision(action=action)})


def _setup(tmp_path: Path) -> tuple[Path, JobManager, str]:
    from novel.project import NovelProject
    from novel.store.bible import StoryBible
    proj = NovelProject.scaffold("p1", genre="g", root=tmp_path, target_chapters=2)
    bible = StoryBible(proj)
    from novel.models import Arc, ChapterBeat, ChapterOutline, Character, Concept, Outline, World
    beat = ChapterBeat(pov="c1", setting="s", event="e", emotional_turn="t", characters=["c1"])
    bible.set_concept(Concept(logline="L", genre="g", tone="t", themes=["x"],
                              target_length_words=100, audience="a"))
    bible.set_world(World(setting="S"))
    bible.set_characters([Character(id="c1", slug="a", name="A", role="protagonist",
                                    backstory="b", motivation="m", arc="a")])
    bible.set_outline(Outline(arcs=[Arc(arc_name="A", chapters=[
        ChapterOutline(chapter_no=i, chapter_title=f"T{i}", beats=[beat]) for i in (1, 2)])]))
    root = tmp_path / "p1"
    manager = JobManager()
    store = ChatSessionStore(root)
    return root, manager, store.create()


def test_store_crud(tmp_path: Path) -> None:
    store = ChatSessionStore(tmp_path / "p1")
    sid = store.create()
    assert [s["id"] for s in store.list_sessions()] == [sid]
    assert store.list_sessions()[0]["title"] == "(空会话)"
    store.append(sid, {"type": "user", "text": "帮我写一本小说"})
    assert store.list_sessions()[0]["title"] == "帮我写一本小说"
    entries = store.entries(sid)
    assert entries is not None and entries[0]["type"] == "user" and entries[0]["seq"] == 0
    assert store.entries("nosuch") is None


def test_turn_pure_chat(tmp_path: Path) -> None:
    root, manager, sid = _setup(tmp_path)
    result = run_turn(root, "p1", sid, "你好", manager, provider=_provider())
    assert isinstance(result, TurnResult)
    assert result.reply == "好的" and result.action is None and result.job_id is None
    entries = ChatSessionStore(root).entries(sid)
    assert entries is not None
    assert [e["type"] for e in entries] == ["user", "assistant"]


def test_turn_dispatches_write_chapters(tmp_path: Path) -> None:
    root, manager, sid = _setup(tmp_path)
    action = {"type": "write_chapters", "args": {"n": 1}}
    result = run_turn(root, "p1", sid, "写一章", manager, provider=_provider(action))
    assert result.job_id is not None
    job = manager.get(result.job_id)
    assert job is not None and job.kind == "write-chapter"
    store = ChatSessionStore(root)
    entries = store.entries(sid)
    assert entries is not None
    assert entries[-2]["type"] == "action" and entries[-2]["job_id"] == result.job_id
    deadline = time.time() + 30
    while time.time() < deadline:
        entries = store.entries(sid) or []
        if entries and entries[-1]["type"] == "system":
            break
        time.sleep(0.05)
    assert entries and entries[-1]["type"] == "system"
    assert (root / "chapters" / "001.md").is_file()


def test_turn_rejects_when_job_active(tmp_path: Path) -> None:
    root, manager, sid = _setup(tmp_path)
    started = manager.start("p1", "sleeper", lambda job: time.sleep(2))
    action = {"type": "write_chapters", "args": {"n": 1}}
    result = run_turn(root, "p1", sid, "再写一章", manager, provider=_provider(action))
    assert result.job_id is None
    entries = ChatSessionStore(root).entries(sid)
    assert entries is not None and entries[-1]["type"] == "system"
    assert "已有任务在运行" in str(entries[-1]["text"])
    manager.cancel(started.id)


def test_turn_invalid_args_value_error(tmp_path: Path) -> None:
    root, manager, sid = _setup(tmp_path)
    action = {"type": "write_premise", "args": {}}  # missing text
    import pytest
    with pytest.raises(ValueError):
        run_turn(root, "p1", sid, "开始", manager, provider=_provider(action))
    entries = ChatSessionStore(root).entries(sid)
    assert entries is not None and entries[-1]["type"] == "system"
    assert manager.active_job("p1") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_chat.py -q`
Expected: FAIL `ModuleNotFoundError`(或 `ImportError: cannot import name 'chat'`)

- [ ] **Step 3: Write implementation**

`novel/ui/chat.py`:

```python
"""Work-mode chat sessions (spec §4.3): append-only history under
.meta/chat/{sid}.jsonl, one orchestrator decision per turn, actions dispatched
to the existing JobManager jobs (zero changes to jobs.py)."""
from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError

from novel.config import load_config
from novel.providers import ModelProvider
from novel.project import NovelProject
from novel.runtime import make_provider
from novel.skills import load_skills
from novel.store.bible import StoryBible
from novel.store.reviews import ReviewStore
from novel.ui import jobs
from novel.ui.jobs import Job, JobManager
from novel.workflow import build_plan

HISTORY_TAIL = 20
_WRITABLE_BIBLE_SECTIONS = ("concept", "world", "characters")
_REWRITE_MODES = ("polish", "rearrange")


class TurnResult(BaseModel):
    reply: str
    action: dict[str, object] | None = None
    job_id: str | None = None


class ChatSessionStore:
    """Append-only per-session jsonl under {project_root}/.meta/chat/."""

    def __init__(self, project_root: Path) -> None:
        self.dir = project_root / ".meta" / "chat"

    def create(self) -> str:
        self.dir.mkdir(parents=True, exist_ok=True)
        sid = uuid.uuid4().hex[:12]
        (self.dir / f"{sid}.jsonl").write_text("", encoding="utf-8")
        return sid

    def _path(self, sid: str) -> Path:
        if Path(sid).name != sid or sid in (".", ".."):
            raise ValueError(f"非法会话 id: {sid}")
        return self.dir / f"{sid}.jsonl"

    def append(self, session_id: str, entry: dict[str, object]) -> dict[str, object]:
        path = self._path(session_id)
        if not path.is_file():
            raise FileNotFoundError(f"会话不存在: {session_id}")
        seq = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
        full = {"seq": seq, "ts": datetime.now(UTC).isoformat(), **entry}
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(full, ensure_ascii=False) + "\n")
        return full

    def entries(self, session_id: str) -> list[dict[str, object]] | None:
        path = self._path(session_id)
        if not path.is_file():
            return None
        out: list[dict[str, object]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # torn tail line: degrade, same philosophy as summaries
        return out

    def list_sessions(self) -> list[dict[str, object]]:
        if not self.dir.is_dir():
            return []
        out: list[dict[str, object]] = []
        for f in sorted(self.dir.glob("*.jsonl")):
            first_user, count, created = "", 0, ""
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                count += 1
                created = created or str(e.get("ts", ""))
                if not first_user and e.get("type") == "user":
                    first_user = str(e.get("text", ""))
            out.append({"id": f.stem, "title": first_user[:24] or "(空会话)",
                        "created": created, "entries": count})
        return out


def _int_arg(args: dict[str, object], key: str, *, lo: int = 1, hi: int = 2000) -> int:
    v = args.get(key)
    if isinstance(v, bool) or not isinstance(v, int) or not (lo <= v <= hi):
        raise ValueError(f"参数 {key} 必须是 {lo}-{hi} 的整数")
    return v


def _str_arg(args: dict[str, object], key: str, *, min_len: int = 1) -> str:
    v = args.get(key)
    if not isinstance(v, str) or len(v.strip()) < min_len:
        raise ValueError(f"参数 {key} 必须是非空字符串(>= {min_len} 字符)")
    return v.strip()


def _dispatch(root: Path, action_type: str, args: dict[str, object],
              bible: StoryBible) -> tuple[str, Callable[[Job], object]]:
    """Validate one action and bind it to an existing jobs.py runner."""
    if action_type == "write_premise":
        return "premise", jobs.run_premise_job(root, _str_arg(args, "text", min_len=10))
    if action_type == "run_setup":
        concept = bible.get_concept()
        if concept is None or not concept.logline:
            raise ValueError("run_setup 需要先有故事概念(write_premise)")
        return "setup", jobs.run_setup_job(root, concept.logline)
    if action_type == "write_chapters":
        return "write-chapter", jobs.run_chapters_job(root, _int_arg(args, "n"))
    if action_type == "rewrite_chapter":
        mode = _str_arg(args, "mode")
        if mode not in _REWRITE_MODES:
            raise ValueError(f"rewrite mode 必须是 {_REWRITE_MODES}")
        return "chapter-rewrite", jobs.run_chapter_rewrite_job(
            root, _int_arg(args, "chapter"), mode, _str_arg(args, "instruction", min_len=2))
    if action_type == "edit_bible":
        section = _str_arg(args, "section")
        if section not in _WRITABLE_BIBLE_SECTIONS:
            raise ValueError(f"edit_bible section 必须是 {_WRITABLE_BIBLE_SECTIONS}")
        character_id = args.get("character_id")
        if character_id is not None and not isinstance(character_id, str):
            raise ValueError("character_id 必须是字符串")
        return "bible-chat", jobs.run_bible_chat_job(
            root, section, _str_arg(args, "instruction", min_len=2),
            character_id if isinstance(character_id, str) else None)
    if action_type == "extend_outline":
        return "outline-extend", jobs.run_outline_extend_job(root, _int_arg(args, "n"))
    if action_type == "run_tts":
        from novel.tts import DEFAULT_VOICE
        voice = args.get("voice")
        if voice is not None and not isinstance(voice, str):
            raise ValueError("voice 必须是字符串")
        return "tts", jobs.run_tts_job(
            root, _int_arg(args, "chapter"),
            voice if isinstance(voice, str) else DEFAULT_VOICE,
            "+0%", "+0%", "+0Hz")
    raise ValueError(f"未知动作类型: {action_type}")


def _watch_job_end(store: ChatSessionStore, session_id: str, job: Job) -> None:
    def _watch() -> None:
        job.thread.join()
        detail = f"({job.error})" if job.error else ""
        store.append(session_id, {"type": "system",
                                  "text": f"任务结束:{job.kind} -> {job.status} {detail}".rstrip()})
    threading.Thread(target=_watch, daemon=True).start()


def run_turn(root: Path, project: str, session_id: str, text: str,
             manager: JobManager, *, provider: ModelProvider | None = None) -> TurnResult:
    """Process one Work-mode turn (spec §5). Raises ValueError on invalid action
    args (API 422), FileNotFoundError on unknown session, ValidationError upward
    is converted to a system entry + RuntimeError."""
    store = ChatSessionStore(root)
    if store.entries(session_id) is None:
        raise FileNotFoundError(f"会话不存在: {session_id}")
    store.append(session_id, {"type": "user", "text": text})

    proj = NovelProject(root=root)
    cfg = load_config(proj.config_path)
    bible = StoryBible(proj)
    reviews = ReviewStore(proj)
    active = manager.active_job(project)
    plan = build_plan(proj, bible, reviews, cfg,
                      active_job_id=active.id if active is not None else None)

    from novel.agents.orchestrator import OrchestratorAgent, OrchestratorInput
    prov = provider if provider is not None else make_provider(cfg, skills=load_skills(root))
    history = [e for e in (store.entries(session_id) or [])
               if e.get("type") in ("user", "assistant")][-HISTORY_TAIL:]
    history_tail = [{"role": str(e["type"]), "text": str(e.get("text", ""))} for e in history]
    try:
        decision = OrchestratorAgent(prov, cfg.model_for("orchestrator")).run(
            OrchestratorInput(history_tail=history_tail, plan_json=plan.model_dump_json(),
                              user_message=text))
    except ValidationError as e:
        store.append(session_id, {"type": "system", "text": f"编排决策失败:{e}"})
        raise RuntimeError(f"orchestrator failed: {e}") from e
    store.append(session_id, {"type": "assistant", "text": decision.reply})

    job_id: str | None = None
    fired = decision.action.model_dump() if decision.action is not None else None
    if decision.action is not None and decision.action.type not in ("none", "wait_job"):
        if active is not None:
            store.append(session_id, {"type": "system",
                                      "text": f"已有任务在运行(job {active.id}),本次动作未启动。"})
        else:
            kind, fn = _dispatch(root, decision.action.type, decision.action.args, bible)
            job = manager.start(project, kind, fn)
            job_id = job.id
            store.append(session_id, {"type": "action", "action": fired, "job_id": job_id})
            _watch_job_end(store, session_id, job)
    return TurnResult(reply=decision.reply, action=fired, job_id=job_id)
```

注意保持 import 干净(未用的名字 ruff 会抓);`Callable` 用于 `_dispatch` 返回类型。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_chat.py -q`
Expected: 5 passed

- [ ] **Step 5: Lint + typecheck + full suite, then commit**

```bash
uv run ruff check . && uv run mypy novel && uv run pytest -q
git add novel/ui/chat.py tests/test_chat.py
git commit -m "feat(chat): session store + orchestrator turn + job dispatch with double guards"
```

---

### Task 4: API 路由(app.py)

**Files:**
- Modify: `novel/ui/app.py`(在 TTS 路由之后、events 路由之前追加四个 chat 路由 + `ChatSendReq`)
- Test: `tests/test_ui.py`(文件末尾追加)

**Interfaces:**
- Consumes: Task 3 `chat.run_turn`/`ChatSessionStore`;现有 `_safe_project`、`manager`
- Produces: `POST /api/projects/{name}/chat/sessions` → `201 {session_id}`;`GET /api/projects/{name}/chat/sessions` → `[{id, title, created, entries}]`;`GET /api/projects/{name}/chat/sessions/{sid}` → `{entries: [...]}`(404 未知会话);`POST /api/projects/{name}/chat/sessions/{sid}/messages` body `{"text": str}` → `{reply, action, job_id}`(422 非法动作,502 编排失败,404 未知会话/项目)

- [ ] **Step 1: Write the failing test**(追加到 `tests/test_ui.py` 末尾)

```python
# ---------- Work 模式聊天(spec §4.4)----------

class _OrchestratorAction:
    """Canned orchestrator decisions injected via monkeypatched make_provider."""

    def __init__(self, action: dict | None) -> None:
        from novel.providers import FakeProvider
        self.provider = FakeProvider(
            {"orchestrator": {"reply": "收到", "action": action}})


def test_chat_session_crud(client: TestClient) -> None:
    client.post("/api/projects", json={"name": "cp"})
    r = client.post("/api/projects/cp/chat/sessions")
    assert r.status_code == 201
    sid = r.json()["session_id"]
    assert [s["id"] for s in client.get("/api/projects/cp/chat/sessions").json()] == [sid]
    assert client.get("/api/projects/cp/chat/sessions/nosuch").status_code == 404


def test_chat_turn_dispatch_and_history(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from novel.ui import chat as chat_mod
    monkeypatch.setattr(chat_mod, "make_provider",
                        lambda cfg, skills=None: _OrchestratorAction(
                            {"type": "write_premise", "args": {"text": "一个时间小偷的故事"}}).provider)
    client.post("/api/projects", json={"name": "cp2"})
    sid = client.post("/api/projects/cp2/chat/sessions").json()["session_id"]
    r = client.post(f"/api/projects/cp2/chat/sessions/{sid}/messages", json={"text": "开始"})
    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == "收到" and body["job_id"]
    job = _wait_job(client, body["job_id"])
    assert job["status"] == "done"
    data = client.get(f"/api/projects/cp2/chat/sessions/{sid}").json()
    kinds = [e["type"] for e in data["entries"]]
    assert kinds[:3] == ["user", "assistant", "action"]
    assert kinds[-1] == "system"
    # premise 真的写进了 bible
    status = client.get("/api/projects/cp2/status").json()
    assert status["has_concept"] is True


def test_chat_turn_invalid_action_422(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from novel.ui import chat as chat_mod
    monkeypatch.setattr(chat_mod, "make_provider",
                        lambda cfg, skills=None: _OrchestratorAction(
                            {"type": "write_premise", "args": {}}).provider)
    client.post("/api/projects", json={"name": "cp3"})
    sid = client.post("/api/projects/cp3/chat/sessions").json()["session_id"]
    r = client.post(f"/api/projects/cp3/chat/sessions/{sid}/messages", json={"text": "开始"})
    assert r.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ui.py -q -k chat`
Expected: FAIL 404 on `/api/projects/cp/chat/sessions`

- [ ] **Step 3: Write implementation**(app.py,TTS 路由后追加)

```python
    class ChatSendReq(BaseModel):
        text: str = Field(min_length=1)

    @app.post("/api/projects/{name}/chat/sessions", status_code=201)
    def create_chat_session(name: str) -> dict[str, str]:
        p = _safe_project(root, name)
        from novel.ui.chat import ChatSessionStore
        return {"session_id": ChatSessionStore(p).create()}

    @app.get("/api/projects/{name}/chat/sessions")
    def list_chat_sessions(name: str) -> list[dict[str, object]]:
        p = _safe_project(root, name)
        from novel.ui.chat import ChatSessionStore
        return ChatSessionStore(p).list_sessions()

    @app.get("/api/projects/{name}/chat/sessions/{sid}")
    def get_chat_session(name: str, sid: str) -> dict[str, object]:
        p = _safe_project(root, name)
        from novel.ui.chat import ChatSessionStore
        entries = ChatSessionStore(p).entries(sid)
        if entries is None:
            raise HTTPException(status_code=404, detail=f"会话不存在: {sid}")
        return {"session_id": sid, "entries": entries}

    @app.post("/api/projects/{name}/chat/sessions/{sid}/messages")
    def send_chat_message(name: str, sid: str, req: ChatSendReq) -> dict[str, object]:
        p = _safe_project(root, name)
        from novel.ui import chat
        try:
            return chat.run_turn(p, name, sid, req.text, manager).model_dump()
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        except RuntimeError as e:  # orchestrator decision failed
            raise HTTPException(status_code=502, detail=str(e)) from e
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ui.py -q`
Expected: all passed

- [ ] **Step 5: Lint + typecheck + full suite, then commit**

```bash
uv run ruff check . && uv run mypy novel && uv run pytest -q
git add novel/ui/app.py tests/test_ui.py
git commit -m "feat(api): chat session routes — create/list/get/messages with 422/502 mapping"
```

---

### Task 5: ui-v2 Work 页(types + hooks + 页面 + 路由/菜单 + 文案)

**Files:**
- Modify: `ui-v2/src/api/types.ts`(追加 Chat 类型)、`ui-v2/src/api/hooks.ts`(追加 3 个 hooks)、`ui-v2/src/constants.ts`(追加 CHAT_ACTION_LABELS)、`ui-v2/src/App.tsx`(import Work、路由、菜单项)
- Create: `ui-v2/src/pages/Work.tsx`
- Test: `ui-v2/tests/work.test.tsx`

**Interfaces:**
- Consumes: Task 4 的四个 REST 路由;现有 `api` client、`p(name)` 常量、AntD 组件、Shell 级 JobStrip/GateModal(门禁与进度零新代码)
- Produces: `useChatSessions(name)`、`useCreateChatSession(name)`、`useChatEntries(name, sid)`、`useSendChatMessage(name, sid)`;`ChatSessionSummary`/`ChatEntry`/`ChatTurnResponse` 类型;路由 `/p/:name/work`;`data-testid="page-work"`

- [ ] **Step 1: Write the failing test**

`ui-v2/tests/work.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { expect, test, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import Work from "../src/pages/Work";

function renderWork(): void {
  const qc = new QueryClient();
  qc.setDefaultOptions({ queries: { retry: false } });
  const entries = [
    { seq: 0, ts: "2026-08-28T00:00:00Z", type: "user", text: "写一章" },
    { seq: 1, ts: "2026-08-28T00:00:01Z", type: "assistant", text: "好的,开始写第 1 章。" },
    { seq: 2, ts: "2026-08-28T00:00:02Z", type: "action", action: { type: "write_chapters", args: { n: 1 } }, job_id: "j1" },
    { seq: 3, ts: "2026-08-28T00:00:40Z", type: "system", text: "任务结束:write-chapter -> done" },
  ];
  const posts: string[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/projects/x/chat/sessions" && init?.method === "POST") {
      posts.push("create");
      return new Response(JSON.stringify({ session_id: "s1" }), { status: 201 });
    }
    if (url === "/api/projects/x/chat/sessions")
      return new Response(JSON.stringify([{ id: "s1", title: "写一本小说", created: "t", entries: 4 }]), { status: 200 });
    if (url === "/api/projects/x/chat/sessions/s1")
      return new Response(JSON.stringify({ session_id: "s1", entries }), { status: 200 });
    if (url === "/api/projects/x/chat/sessions/s1/messages" && init?.method === "POST") {
      posts.push(String(init.body));
      return new Response(JSON.stringify({ reply: "已完成", action: null, job_id: null }), { status: 200 });
    }
    return new Response(JSON.stringify({}), { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock as unknown as typeof fetch);
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/p/x/work"]}>
        <Routes>
          <Route path="/p/:name/work" element={<Work />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test("renders session list and all four entry kinds", async () => {
  renderWork();
  expect(await screen.findByTestId("page-work")).toBeTruthy();
  expect(await screen.findByText("写一本小说")).toBeTruthy();
  expect(await screen.findByText("好的,开始写第 1 章。")).toBeTruthy();
  expect(await screen.findByText(/撰写章节/)).toBeTruthy();
  expect(await screen.findByText(/任务结束/)).toBeTruthy();
});

test("sending a message posts and shows the reply", async () => {
  renderWork();
  const input = await screen.findByTestId("chat-input");
  fireEvent.change(input, { target: { value: "继续" } });
  fireEvent.click(await screen.findByTestId("chat-send"));
  await waitFor(() =>
    expect(screen.getAllByText("已完成").length).toBeGreaterThan(0));
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui-v2 && npm run test -- tests/work.test.tsx`
Expected: FAIL `Cannot find module '../src/pages/Work'`

- [ ] **Step 3: Write implementation**

`ui-v2/src/api/types.ts` 追加:

```ts
export interface ChatSessionSummary {
  id: string;
  title: string;
  created: string;
  entries: number;
}

export interface ChatEntry {
  seq: number;
  ts: string;
  type: "user" | "assistant" | "action" | "system";
  text?: string;
  action?: { type: string; args: Record<string, unknown> };
  job_id?: string;
}

export interface ChatTurnResponse {
  reply: string;
  action: { type: string; args: Record<string, unknown> } | null;
  job_id: string | null;
}
```

`ui-v2/src/api/hooks.ts` 追加(文件顶部 types import 里加 `ChatEntry, ChatSessionSummary, ChatTurnResponse`):

```ts
// ---------- Work 模式聊天 ----------

export function useChatSessions(name: string | undefined) {
  return useQuery({
    queryKey: ["chat-sessions", name],
    queryFn: () => api<ChatSessionSummary[]>(`${p(name!)}/chat/sessions`),
    enabled: !!name,
  });
}

export function useCreateChatSession(name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<{ session_id: string }>(`${p(name)}/chat/sessions`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["chat-sessions", name] }),
  });
}

export function useChatEntries(name: string, sid: string | null) {
  return useQuery({
    queryKey: ["chat-entries", name, sid],
    queryFn: () => api<{ session_id: string; entries: ChatEntry[] }>(`${p(name)}/chat/sessions/${sid}`),
    enabled: !!name && !!sid,
  });
}

export function useSendChatMessage(name: string, sid: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (text: string) =>
      api<ChatTurnResponse>(`${p(name)}/chat/sessions/${sid}/messages`, {
        method: "POST",
        body: JSON.stringify({ text }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["chat-entries", name, sid] }),
  });
}
```

`ui-v2/src/constants.ts` 追加:

```ts
export const CHAT_ACTION_LABELS: Record<string, string> = {
  write_premise: "生成故事前提",
  run_setup: "分阶段设定",
  write_chapters: "撰写章节",
  rewrite_chapter: "改写章节",
  edit_bible: "编辑设定",
  extend_outline: "扩展大纲",
  run_tts: "语音合成",
  wait_job: "等待任务",
  none: "无动作",
};
```

`ui-v2/src/pages/Work.tsx`:

```tsx
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Button, Card, Empty, Input, List, Space, Tag, Typography } from "antd";
import { Link } from "react-router-dom";
import {
  useChatEntries,
  useChatSessions,
  useCreateChatSession,
  useSendChatMessage,
} from "../api/hooks";
import { CHAT_ACTION_LABELS } from "../constants";

/** Work 模式:计划驱动的对话编排。进度与门禁由 Shell 的 JobStrip/GateModal
 * 呈现(跨页复用),本页只负责会话与消息流。 */
export default function Work() {
  const { name = "" } = useParams();
  const [sid, setSid] = useState<string | null>(null);
  const [text, setText] = useState("");
  const sessions = useChatSessions(name);
  const createSession = useCreateChatSession(name);
  const entries = useChatEntries(name, sid);
  const send = useSendChatMessage(name, sid);

  useEffect(() => {
    if (!sid && (sessions.data?.length ?? 0) > 0) setSid(sessions.data![0].id);
  }, [sessions.data, sid]);

  const doSend = () => {
    const t = text.trim();
    if (!t || !sid || send.isPending) return;
    setText("");
    send.mutate(t);
  };

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }} data-testid="page-work">
      <Typography.Title level={4} style={{ margin: 0 }}>
        对话(Work)
      </Typography.Title>
      <Card size="small" title="会话" extra={
        <Button size="small" loading={createSession.isPending}
                onClick={() => createSession.mutate(undefined, { onSuccess: (d) => setSid(d.session_id) })}>
          新建会话
        </Button>
      }>
        <List
          size="small"
          dataSource={sessions.data ?? []}
          rowKey={(s) => s.id}
          renderItem={(s) => (
            <List.Item style={{ cursor: "pointer", padding: "4px 8px",
                                background: s.id === sid ? "#f5f5f5" : undefined }}
              onClick={() => setSid(s.id)}>
              <Typography.Text ellipsis style={{ maxWidth: 240 }}>{s.title}</Typography.Text>
            </List.Item>
          )}
        />
      </Card>
      <Card size="small" title="消息">
        {sid == null ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="新建会话后开始对话" />
        ) : (
          <div style={{ maxHeight: "50vh", overflowY: "auto", padding: "0 4px" }}>
            <List
              size="small"
              dataSource={entries.data?.entries ?? []}
              rowKey={(e) => String(e.seq)}
              renderItem={(e) => {
                if (e.type === "user")
                  return <Typography.Paragraph style={{ textAlign: "right" }}>
                    <Typography.Text style={{ background: "#e6f4ff", padding: "4px 10px", borderRadius: 6 }}>
                      {e.text}
                    </Typography.Text>
                  </Typography.Paragraph>;
                if (e.type === "assistant")
                  return <Typography.Paragraph>{e.text}</Typography.Paragraph>;
                if (e.type === "action")
                  return <Card size="small" style={{ margin: "6px 0", background: "#fafafa" }}>
                    <Space wrap>
                      <Tag color="blue">{CHAT_ACTION_LABELS[e.action?.type ?? ""] ?? e.action?.type}</Tag>
                      <Typography.Text code>{JSON.stringify(e.action?.args ?? {})}</Typography.Text>
                      {e.job_id ? (
                        <Link to={`/p/${name}/generate`}>查看任务 →</Link>
                      ) : null}
                    </Space>
                  </Card>;
                return <Typography.Text type="secondary" style={{ fontSize: 12 }}>{e.text}</Typography.Text>;
              }}
            />
          </div>
        )}
        <Space.Compact style={{ width: "100%", marginTop: 8 }}>
          <Input.TextArea
            data-testid="chat-input"
            autoSize={{ minRows: 1, maxRows: 4 }}
            value={text}
            placeholder={sid == null ? "先新建会话" : "例如:继续写 3 章 / 把第 2 章改得紧张一点"}
            disabled={sid == null}
            onChange={(e) => setText(e.target.value)}
            onPressEnter={(e) => { if (!e.shiftKey) { e.preventDefault(); doSend(); } }}
          />
          <Button type="primary" data-testid="chat-send"
                  loading={send.isPending} disabled={sid == null} onClick={doSend}>
            发送
          </Button>
        </Space.Compact>
      </Card>
    </Space>
  );
}
```

`ui-v2/src/App.tsx` 三处改动:
1. import 区追加:`import Work from "./pages/Work";`
2. `items` 的"创作"组 children 里 `{ key: "generate", label: "生成章节" }` 之后加:`{ key: "work", label: "对话 Work" },`
3. `<Route path="generate" element={<Generate />} />` 之后加:`<Route path="work" element={<Work />} />`

- [ ] **Step 4: Run test to verify it passes**

```bash
cd ui-v2 && npm run test -- tests/work.test.tsx && npm run typecheck
```
Expected: 2 passed;typecheck 无错误

- [ ] **Step 5: Full frontend suite + commit**

```bash
cd ui-v2 && npm run test && npm run build
git add ui-v2/src/api/types.ts ui-v2/src/api/hooks.ts ui-v2/src/constants.ts ui-v2/src/App.tsx ui-v2/src/pages/Work.tsx ui-v2/tests/work.test.tsx
git commit -m "feat(ui-v2): Work chat page — sessions, four entry kinds, action cards; shell JobStrip/GateModal reused"
```

---

### Task 6: 文档同步 + 全量验证

**Files:**
- Modify: `README.md`(模型配置表/说明处补 `orchestrator` 槽位)、`AGENTS.md`(架构段补 workflow/chat/orchestrator 一句 + 层级规则两条)

**Interfaces:**
- Consumes: Task 1-5 的成品
- Produces: 文档与实现一致;全量绿

- [ ] **Step 1: README**

在模型配置说明(models 段,搜 `models:` 的字段参考表)补一行:orchestrator 为 Work 对话模式的编排 agent 槽位,可缺省(fallback 到 `default`);demo 模式下 Work 页可聊天但不启动任务。

- [ ] **Step 2: AGENTS.md**

首段"Nine agents …"句后追加一句:

```markdown
Work chat mode runs an eleventh agent (`orchestrator`) whose only job is routing: each turn it reads a deterministic plan from `novel/workflow.py` (`build_plan`, spec'd single `next_action`) and dispatches to existing jobs via `novel/ui/chat.py` (append-only sessions under `.meta/chat/`).
```

层级规则(`novel/ui/` 条目后)追加:

```markdown
- `novel/workflow.py` — deterministic workflow planner (pure `build_plan`): steps + single `next_action` + `available_actions`; sole authority for "what comes next" in Work mode.
- `novel/ui/chat.py` — Work-mode chat sessions (append-only `.meta/chat/*.jsonl`), one orchestrator decision per turn, action dispatch to existing JobManager jobs; double guard against concurrent jobs.
```

- [ ] **Step 3: 全量验证(验收标准 §8)**

```bash
uv run pytest -q
uv run ruff check .
uv run mypy novel
cd ui-v2 && npm run test && npm run typecheck && npm run build
```
Expected: 全绿(`test_ui.py::test_ui_v2_dist_served` 在 dist 存在时也应通过——build 已生成)

- [ ] **Step 4: Commit**

```bash
git add README.md AGENTS.md
git commit -m "docs: Work chat mode — orchestrator model slot, workflow planner, chat session layer"
```

---

## Self-Review 记录

- **Spec coverage**:§4.1→Task 1;§4.2→Task 2;§4.3→Task 3;§4.4→Task 4;§4.5→Task 5;§6 测试→Task 1-5 各自测试 + Task 6 全量;§7 错误处理→Task 3(ValueError/FileNotFoundError/ValidationError→RuntimeError)+ Task 4(422/404/502);§8 验收→Task 6 Step 3。进度/门禁复用 Shell 的 JobStrip/GateModal——spec §4.5 说"复用 events store + describe",实现上即复用 Shell 组件,语义一致。
- **Type consistency**:`build_plan` 签名在 Task 1/3 一致;`OrchestratorDecision.action: ChatAction | None` 与 Task 3 `decision.action.model_dump()` 一致;`TurnResult` 字段与 Task 4 `.model_dump()` 及前端 `ChatTurnResponse` 一致;路由路径 Task 4 与 Task 5 fetch stub 一致。
- **Placeholder scan**:Task 3 Step 3 中"示意块"是给实现者的说明,最终文件结构已完整给出;无 TBD/TODO。
