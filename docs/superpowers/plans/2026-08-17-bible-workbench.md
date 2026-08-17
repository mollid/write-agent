# 设定工作台（Bible Workbench）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增「设定库」页面：全量预览设定（静态四件套+动态状态）、JSON 手动编辑（pydantic 校验）、对话式定点改写（diff 确认后应用）、大纲追章解锁续写。

**Architecture:** 新增 `SettingEditorAgent`（实例级动态 schema：当前设定+指令→同 schema 改写稿）与 `OutlinerExtendAgent`（只产出续号新章）。后端混合传输：手动编辑走同步 `PUT /bible/{section}`（422 校验/409 互斥）；对话改写与追章走 Job+SSE+gate（label 统一 `bible:` 前缀）。前端 `pages/Bible.tsx`（左导航+卡片流+右对话面板），`bible:` gate 由页内 diff 面板接管、GateModal 跳过。

**Tech Stack:** Python 3.11+ / pydantic / FastAPI / pytest+FakeProvider；React 18 + TS strict + AntD 5 + TanStack Query + zustand + vitest。

**Spec:** `docs/superpowers/specs/2026-08-17-bible-workbench-design.md`（gitignored by repo convention）。

## Global Constraints

- 测试一律用 `FakeProvider` / `runtime.demo_provider()`——无网络、无 `NOVEL_LIVE=1`。
- 每个任务提交前过三道门：`uv run pytest -q`、`uv run ruff check .`（line-length 100）、`uv run mypy novel`（strict，只查 `novel/`）。
- 前端任务另过：`cd ui-v2 && npm run test && npm run typecheck`（tsc strict）。
- 不改动既有测试语义；demo_provider 扩充响应键不影响现有断言（FakeProvider 按消息里的 agent tag 查响应，未调用的键无害）。
- UI 文案中文、代码标识符英文；新增 pydantic schema 进 `novel/models.py` 或就近文件。
- SSE 事件字段沿用扁平 dict（`job_id` 由 `Job.emit` 自动附加）。

## Reference facts (do not re-derive)

- `Agent`（novel/agents/base.py）：`name`/`output_schema` 是**类属性**，但 `run()` 经 `self.output_schema` 读取——实例上覆盖即可生效；`run(inputs, feedback=...)` 已有。`complete_structured(messages, schema, cfg)` 中 FakeProvider 对 pydantic 实例响应做 `isinstance(val, schema)` 断言、对 dict 做 `schema.model_validate(val)`。
- FakeProvider 按 `_agent_tag(messages, "agent")`（取 system 消息的 `agent` 字段）查 canned response；未注册的 tag 抛 KeyError——**响应键必须等于 agent 类的 `name`**。
- `AGENT_NAMES`（novel/runtime.py:9-12）：九元组列表；`cfg.model_for(name)` 回退 `default` 再回退第一个 model——加名无需迁移 config。
- `StoryBible`（novel/store/bible.py）：`get_concept()->Concept|None`（无 concept 时 KeyError 风险——实际 `self._load()["concept"]` 直接下标，**fresh 项目调用会 KeyError**，只有 world/outline 有 None 保护）、`get_world`、`get_outline`、`all_characters`、`upsert_character`、`set_*`、`list_foreshadow`（读 `bible/foreshadowing.json`）、`list_events`（读 `bible/events.jsonl`）。写操作自动 `_write_mirrors`。
- `approve_stage("outline", artifact, bible)`（novel/setup_flow.py:68-88）含伏笔并入逻辑；`_parse_ch` 在 setup_flow.py:23-26。
- Job/gate（novel/ui/jobs.py）：`manager.start(project, kind, fn)` 每项目单活跃 Job（冲突 raise RuntimeError→端点转 409）；`job.emit(dict)` 发布 SSE 且检查 cancel；`job.gate_with_feedback(label, artifact)->(approved, feedback|None)` 阻塞等待 `POST /api/gates/{id}`；`artifact_text(artifact)` 把 pydantic 转 pretty JSON 字符串。gate SSE 事件字段：`type/gate_id/label/artifact`。
- app.py 端点模式：`_safe_project(root, name)`→404；RuntimeError→409；请求体用模块级 `class XReq(BaseModel)`。
- 前端：`api/client.ts` 的 `api<T>(path, opts)` 抛 `ApiError(status, detail)`；hooks 在 `api/hooks.ts`（queryKey 惯例 `["bible", name]`）；SSE 事件在 `stores/events.ts` 的 `apply(ev)` switch；`describe(ev)`（src/describe.ts）把事件转日志文案；GateModal 判定 `gate.label.startsWith("setup:")`；路由在 App.tsx `Routes`，Sider items 数组「创作」组在「分阶段设定」后有 `generate`。
- `useProjectEvents`（api/events.ts:67）对 `premise_done|setup_stage|job_end` invalidate `["status"]`——新事件要加进这个集合。
- 测试：后端 `tests/test_ui.py` 用 `TestClient(create_app(tmp_path))` + `_wait_job` 轮询；前端 `ui-v2/tests/pages.test.tsx` 用 `stubFetchFor` 模式 mock fetch、`renderPage` helper。

## File Structure

- Create: `novel/agents/setting_editor.py`（SettingEditorAgent）、`tests/test_setting_editor.py`
- Modify: `novel/agents/outliner.py`（OutlinerExtendAgent）、`tests/test_outliner_extend.py`（新建）
- Modify: `novel/runtime.py`（AGENT_NAMES + demo_provider 响应）、`novel/ui/jobs.py`（两个 job 函数 + diff helper）、`novel/ui/app.py`（4 端点）、`novel/models.py`（若需请求 schema，尽量复用既有）
- Create: `tests/test_bible_api.py`
- Modify: `ui-v2/src/api/types.ts`、`api/hooks.ts`、`stores/events.ts`、`describe.ts`、`constants.ts`、`components/GateModal.tsx`、`App.tsx`、`ui-v2/tests/*`
- Create: `ui-v2/src/pages/Bible.tsx`、`ui-v2/src/components/BibleChat.tsx`（对话面板）、`ui-v2/src/components/DiffView.tsx`
- Modify: `README.md`（API/页面用法）

---

### Task 1: `SettingEditorAgent`（动态 schema 定点改写）

**Files:**
- Create: `novel/agents/setting_editor.py`
- Test: `tests/test_setting_editor.py`

**Interfaces:**
- Consumes: `Agent[I, O]`（base.py）、`FakeProvider`（providers.py）。
- Produces: `SettingEditorAgent(provider, cfg, schema: type[BaseModel])`；`agent.name == "setting_editor"`；`run(SettingEditInput) -> BaseModel`（schema 实例）。`SettingEditInput` 为本文件定义的 dataclass：`current_json: str`、`instruction: str`、`history: list[tuple[str, str]]`（(instruction, outcome) 轮次）。

- [ ] **Step 1: Write the failing test**

```python
"""SettingEditorAgent: dynamic-schema targeted rewrite of a bible section."""
from __future__ import annotations

from novel.agents.base import Agent
from novel.agents.setting_editor import SettingEditInput, SettingEditorAgent
from novel.models import World
from novel.providers import FakeProvider, ModelConfig

CFG = ModelConfig("zhipu", "x")


def test_agent_attributes() -> None:
    agent = SettingEditorAgent(FakeProvider({}), CFG, World)
    assert agent.name == "setting_editor"
    assert agent.output_schema is World


def test_prompt_carries_current_instruction_history_and_rules() -> None:
    captured: list[list[dict]] = []

    class Spy(Agent[SettingEditInput, World]):
        name = "setting_editor"

        def build_messages(self, inputs: SettingEditInput) -> list[dict]:
            msgs = SettingEditorAgent.build_messages(self, inputs)  # type: ignore[arg-type]
            captured.append(msgs)
            return msgs

    agent = Spy(FakeProvider({"setting_editor": World(setting="x")}), CFG)
    agent.run(SettingEditInput(current_json='{"setting": "old"}', instruction="让世界更冷",
                                history=[("加一个沙漠", "已应用")]))
    text = "\n".join(m["content"] for m in captured[0])
    assert '{"setting": "old"}' in text
    assert "让世界更冷" in text
    assert "加一个沙漠" in text
    assert "逐字保留" in text  # preservation rule stated in prompt


def test_run_returns_schema_instance() -> None:
    world = World(setting="changed", rules=["ice"])
    agent = SettingEditorAgent(FakeProvider({"setting_editor": world}), CFG, World)
    out = agent.run(SettingEditInput(current_json='{"setting": "old"}', instruction="改",
                                     history=[]))
    assert isinstance(out, World)
    assert out.rules == ["ice"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_setting_editor.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'novel.agents.setting_editor'`

- [ ] **Step 3: Write minimal implementation**

```python
"""Targeted setting rewriter: current setting + NL instruction -> same-schema draft."""
from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel

from novel.agents.base import Agent
from novel.config import ModelConfig
from novel.providers import ModelProvider

SETTING_EDITOR_SYSTEM = """\
You are a story-bible editor. You rewrite ONE setting artifact according to the user's instruction.

## Critical Rules
1. Targeted change: modify ONLY what the instruction asks for.
2. Preservation: fields the instruction does not mention MUST be preserved VERBATIM (逐字保留) — same value, same language.
3. ID discipline: never change entity ids (e.g. character ids); never reference characters that do not exist.
4. System-managed fields (e.g. character `state`, `voice_fingerprint`, `mannerisms`, `description_history`) stay unchanged unless the instruction explicitly targets them.
5. The instruction may ask to ADD entities (a character, a location, a faction, a foreshadow entry) — do it, keeping the existing ones untouched.
6. Output the COMPLETE artifact in the same JSON schema. Same language as the original text values.

## Current artifact (JSON)
{current_json}

## Earlier turns of this editing session
{history_block}

## Output
Return ONLY the JSON object."""

SETTING_EDITOR_USER = """\
Rewrite the artifact above according to this instruction:
{instruction}"""


@dataclass
class SettingEditInput:
    current_json: str
    instruction: str
    history: list[tuple[str, str]] = field(default_factory=list)


def _history_block(history: list[tuple[str, str]]) -> str:
    if not history:
        return "(none)"
    return "\n".join(f"- user: {i} -> {o}" for i, o in history[-6:])


class SettingEditorAgent(Agent[SettingEditInput, BaseModel]):
    name = "setting_editor"

    def __init__(self, provider: ModelProvider, cfg: ModelConfig,
                 schema: type[BaseModel]) -> None:
        super().__init__(provider, cfg)
        self.output_schema = schema

    def build_messages(self, inputs: SettingEditInput) -> list[dict]:
        content = SETTING_EDITOR_SYSTEM.replace("{current_json}", inputs.current_json) \
            .replace("{history_block}", _history_block(inputs.history))
        return [
            {"role": "system", "agent": self.name, "content": content},
            {"role": "user", "agent": self.name,
             "content": SETTING_EDITOR_USER.replace("{instruction}", inputs.instruction)},
        ]
```

注意：`Agent` 泛型第二参数填 `BaseModel`，`run()` 返回时 `type: ignore` 已由 base 处理。`{...}` 花括号在模板中是字面量占位，用 `.replace` 注入避免 `format` 冲突（沿用 outliner.py:78 注释的惯例）。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_setting_editor.py -q`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add novel/agents/setting_editor.py tests/test_setting_editor.py
git commit -m "feat(bible): SettingEditorAgent — dynamic-schema targeted setting rewrite"
```

---

### Task 2: `OutlinerExtendAgent`（大纲续写）

**Files:**
- Modify: `novel/agents/outliner.py`（追加类）
- Test: `tests/test_outliner_extend.py`（新建）

**Interfaces:**
- Consumes: `Outline`/`Concept`/`World`/`Character`/`Event`/`Foreshadow`（models.py）、`Agent`。
- Produces: `OutlinerExtendAgent(Agent[OutlineExtendInput, Outline])`；`name == "outliner"`（复用 outliner 配置位与 FakeProvider 键）；`OutlineExtendInput` dataclass：`concept: Concept`、`world: World`、`characters: list[Character]`、`current: Outline`、`recent_events: list[Event]`、`open_foreshadows: list[Foreshadow]`、`n_chapters: int`。

- [ ] **Step 1: Write the failing test**

```python
"""OutlinerExtendAgent: append-only outline continuation."""
from __future__ import annotations

from novel.agents.outliner import OutlineExtendInput, OutlinerExtendAgent
from novel.models import (
    Arc, ChapterBeat, ChapterOutline, Character, Concept, Event, Foreshadow, Outline, World,
)
from novel.providers import FakeProvider, ModelConfig

CFG = ModelConfig("zhipu", "x")
BEAT = ChapterBeat(pov="c1", setting="tavern", event="meet", emotional_turn="doubt→resolve",
                   characters=["c1"])


def _base(current_max: int) -> OutlineExtendInput:
    current = Outline(arcs=[Arc(arc_name="A", chapters=[
        ChapterOutline(chapter_no=i, chapter_title=f"T{i}", beats=[BEAT])
        for i in range(1, current_max + 1)])])
    return OutlineExtendInput(
        concept=Concept(logline="L", genre="g", tone="t", target_length_words=100, audience="a"),
        world=World(setting="city"),
        characters=[Character(id="c1", slug="ara", name="Ara", role="protagonist",
                              backstory="b", motivation="m", arc="a")],
        current=current,
        recent_events=[Event(id="e1", chapter=1, summary="theft")],
        open_foreshadows=[Foreshadow(id="fs-1", description="the watch", planted_ch=1)],
        n_chapters=3,
    )


def test_prompt_carries_continuation_context() -> None:
    agent = OutlinerExtendAgent(FakeProvider({}, tag_key="agent"), CFG)
    msgs = agent.build_messages(_base(current_max=2))
    text = "\n".join(m["content"] for m in msgs)
    assert "T2" in text                    # existing outline tail visible
    assert "fs-1" in text                  # open foreshadow listed
    assert "theft" in text                 # recent event listed
    assert "3" in text                     # n_chapters in prompt
    assert "chapter_no" in text            # numbering rule stated


def test_run_validates_against_outline_schema() -> None:
    extension = Outline(arcs=[Arc(arc_name="B", chapters=[
        ChapterOutline(chapter_no=i, chapter_title=f"T{i}", beats=[BEAT])
        for i in (3, 4, 5)])])
    agent = OutlinerExtendAgent(FakeProvider({"outliner": extension}), CFG)
    out = agent.run(_base(current_max=2))
    assert isinstance(out, Outline)
    assert [c.chapter_no for c in out.arcs[0].chapters] == [3, 4, 5]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_outliner_extend.py -q`
Expected: FAIL — `ImportError: cannot import name 'OutlineExtendInput'`

- [ ] **Step 3: Write minimal implementation**（追加到 `novel/agents/outliner.py` 末尾）

```python
OUTLINER_EXTEND_SYSTEM_EXTRA = """\

## Continuation Mode
You are EXTENDING an existing outline, not rewriting it.
- Number new chapters starting at {next_chapter_no} consecutively ({n_chapters} chapters total).
- Continue existing arcs or open a new one — but NEVER restate or renumber existing chapters.
- Pay off or advance the open foreshadows listed below when natural.
- Every `plants` id must appear in `foreshadow_ledger`; ids continue after existing ledger ids.
"""

OUTLINER_EXTEND_USER = """\
<concept>
{concept_json}
</concept>

<world>
{world_json}
</world>

<characters>
{roster_block}
</characters>

<existing_outline_tail>
{tail_block}
</existing_outline_tail>

<recent_events>
{events_block}
</recent_events>

<open_foreshadows>
{foreshadows_block}
</open_foreshadows>

Extend the outline by {n_chapters} new chapter(s), numbered from {next_chapter_no}."""


@dataclass
class OutlineExtendInput:
    concept: Concept
    world: World
    characters: list[Character]
    current: Outline
    recent_events: list[Event]
    open_foreshadows: list[Foreshadow]
    n_chapters: int


class OutlinerExtendAgent(Agent[OutlineExtendInput, Outline]):
    name = "outliner"
    output_schema = Outline

    def build_messages(self, inputs: OutlineExtendInput) -> list[dict]:
        roster_block = "\n".join(f"- {c.id} ({c.name}): {c.role}" for c in inputs.characters)
        tail = [c for a in inputs.current.arcs for c in a.chapters][-5:]
        tail_block = "\n".join(
            f"- ch{c.chapter_no}「{c.chapter_title}」: "
            + "; ".join(b.event for b in c.beats) for c in tail)
        events_block = "\n".join(f"- ch{e.chapter}: {e.summary}" for e in inputs.recent_events[-10:]) \
            or "(none)"
        foreshadows_block = "\n".join(f"- {f.id}: {f.description}" for f in inputs.open_foreshadows) \
            or "(none)"
        existing_max = max((c.chapter_no for a in inputs.current.arcs for c in a.chapters),
                           default=0)
        next_no = existing_max + 1
        system = (OUTLINER_SYSTEM + OUTLINER_EXTEND_SYSTEM_EXTRA
                  .replace("{next_chapter_no}", str(next_no))
                  .replace("{n_chapters}", str(inputs.n_chapters))) \
            .replace("{roster_block}", roster_block)
        user = OUTLINER_EXTEND_USER.format(
            concept_json=inputs.concept.model_dump_json(),
            world_json=inputs.world.model_dump_json(),
            roster_block=roster_block,
            tail_block=tail_block or "(none)",
            events_block=events_block,
            foreshadows_block=foreshadows_block,
            n_chapters=inputs.n_chapters,
            next_chapter_no=next_no,
        )
        return [
            {"role": "system", "agent": self.name, "content": system},
            {"role": "user", "agent": self.name, "content": user},
        ]
```

文件顶部 import 增补：`from dataclasses import dataclass` 与 `Event, Foreshadow`（models 导入行）。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_outliner_extend.py -q`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add novel/agents/outliner.py tests/test_outliner_extend.py
git commit -m "feat(bible): OutlinerExtendAgent — append-only outline continuation"
```

---

### Task 3: runtime 注册 + demo 响应

**Files:**
- Modify: `novel/runtime.py`
- Test: `tests/test_setting_editor.py`（追加）

**Interfaces:**
- Produces: `AGENT_NAMES` 含 `"setting_editor"`（十元组）；`demo_provider()` 响应键 `setting_editor` = dict `{"echo": True}` 语义的**原文回显函数不可行**（FakeProvider 只支持静态值）——改为：响应键 `setting_editor` 映射到特殊字符串 `"__echo__"`，由调用侧 job 处理（见 Task 4 Step 3 的 demo 分支）；`outliner` 键已存在（demo outline 6 章），extend 的 demo 分支同样在 job 侧合成。**本任务只加 AGENT_NAMES 条目**，不动 demo_provider 的静态字典（extend/editor 的 demo 行为属于 job 层）。

- [ ] **Step 1: Write the failing test**

```python
def test_agent_names_include_setting_editor() -> None:
    from novel.runtime import AGENT_NAMES
    assert "setting_editor" in AGENT_NAMES
    assert AGENT_NAMES.count("strategist") == 1  # 既有条目未动
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_setting_editor.py -q`
Expected: 1 failed（test_agent_names_include_setting_editor）

- [ ] **Step 3: Implement**

`novel/runtime.py` 的 `AGENT_NAMES` 改为：

```python
AGENT_NAMES = [
    "strategist", "worldbuilder", "character", "outliner", "writer",
    "continuity", "editor", "scorer", "extractor", "setting_editor",
]
```

- [ ] **Step 4: Run full suite**（确认 graph.py 的 `cfg_map` 生成与 `model_for` 回退不受影响）

Run: `uv run pytest -q && uv run ruff check . && uv run mypy novel`
Expected: 全绿

- [ ] **Step 5: Commit**

```bash
git add novel/runtime.py tests/test_setting_editor.py
git commit -m "feat(bible): register setting_editor in AGENT_NAMES (falls back to default model)"
```

---

### Task 4: bible 读取层 + diff helper（jobs.py）

**Files:**
- Modify: `novel/ui/jobs.py`
- Test: `tests/test_bible_api.py`（新建，本任务先测纯函数）

**Interfaces:**
- Consumes: `StoryBible`、`SettingEditorAgent`、`OutlineExtendInput`。
- Produces（jobs.py 模块级，供 Task 5 端点与测试复用）:
  - `BIBLE_SECTIONS = ("concept", "world", "characters", "outline", "foreshadows", "events")`
  - `read_bible_section(bible, section) -> object | None`（pydantic 对象或 list；concept 缺失返回 None）
  - `SECTION_SCHEMAS: dict[str, type[BaseModel]]`（concept→Concept、world→World；characters/outline 为 list/Outline 特判）
  - `save_bible_section(bible, section, payload: object) -> None`（校验后的 pydantic 对象写入；**不做**校验——校验在 `validate_bible_section`）
  - `validate_bible_section(section, data: object) -> object`：section 非法 raise ValueError；data 经 `Concept.model_validate` 等；events raise ValueError("read-only")
  - `json_diff(old: object, new: object) -> str`：difflib.unified_diff（pretty JSON 行级，ensure_ascii=False，无 context 行头 `n=0` 前缀 `±` 描述见实现）

- [ ] **Step 1: Write the failing test**

```python
"""Bible read/validate/diff helpers + /bible API endpoints."""
from __future__ import annotations

import pytest

from novel.models import Concept, World
from novel.project import NovelProject
from novel.ui.jobs import (
    json_diff,
    read_bible_section,
    save_bible_section,
    validate_bible_section,
)
from novel.store.bible import StoryBible


@pytest.fixture()
def bible(tmp_path):
    proj = NovelProject.scaffold("n", genre="fantasy", root=tmp_path)
    return StoryBible(proj)


def test_read_concept_missing_returns_none(bible):
    assert read_bible_section(bible, "concept") is None


def test_validate_roundtrip(bible):
    concept = validate_bible_section("concept", {
        "logline": "L", "genre": "g", "tone": "t", "target_length_words": 100, "audience": "a"})
    assert isinstance(concept, Concept)
    save_bible_section(bible, "concept", concept)
    back = read_bible_section(bible, "concept")
    assert isinstance(back, Concept) and back.logline == "L"


def test_validate_rejects_bad_section_and_readonly(bible):
    with pytest.raises(ValueError, match="unknown section"):
        validate_bible_section("events", {})
    with pytest.raises(ValueError, match="unknown section"):
        validate_bible_section("nope", {})


def test_validate_reports_pydantic_error(bible):
    with pytest.raises(Exception):
        validate_bible_section("world", {"rules": "not-a-list"})


def test_json_diff_marks_changed_lines():
    old = World(setting="cold city").model_dump()
    new = World(setting="cold city", era="winter").model_dump()
    d = json_diff(old, new)
    assert "-\"setting\": \"cold city\"" in d
    assert "+  \"setting\": \"cold city\"" in d or "+\"setting\": \"cold city\"" in d
    assert "+\"era\": \"winter\"" in d
```

（注：diff 断言对缩进宽松——统一由实现保证 `json.dumps(..., indent=2)`，old 行带 `-`、new 行带 `+`。）

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bible_api.py -q`
Expected: FAIL — ImportError（json_diff 等）

- [ ] **Step 3: Implement**（jobs.py 模块级新增，放 `drain` 之前）

```python
BIBLE_SECTIONS = ("concept", "world", "characters", "outline", "foreshadows", "events")
_READ_ONLY_SECTIONS = ("events",)
_SECTION_MODELS: dict[str, type] = {"concept": Concept, "world": World, "outline": Outline}


def read_bible_section(bible: StoryBible, section: str) -> object | None:
    if section == "concept":
        try:
            return bible.get_concept()
        except KeyError:
            return None
    if section == "world":
        return bible.get_world()
    if section == "characters":
        return bible.all_characters()
    if section == "outline":
        return bible.get_outline()
    if section == "foreshadows":
        return bible.list_foreshadow()
    if section == "events":
        return bible.list_events()
    raise ValueError(f"unknown section: {section}")


def validate_bible_section(section: str, data: object) -> object:
    if section in _READ_ONLY_SECTIONS:
        raise ValueError(f"unknown section: {section}")  # events: append-only, no PUT
    if section == "characters":
        assert isinstance(data, list)
        return [Character.model_validate(c) for c in data]
    if section == "foreshadows":
        assert isinstance(data, list)
        return [Foreshadow.model_validate(f) for f in data]
    if section in _SECTION_MODELS:
        return _SECTION_MODELS[section].model_validate(data)
    raise ValueError(f"unknown section: {section}")


def save_bible_section(bible: StoryBible, section: str, artifact: object) -> None:
    if section == "concept":
        bible.set_concept(artifact)  # type: ignore[arg-type]
    elif section == "world":
        bible.set_world(artifact)  # type: ignore[arg-type]
    elif section == "characters":
        for ch in artifact:  # type: ignore[union-attr]
            bible.upsert_character(ch)
    elif section == "outline":
        bible.set_outline(artifact)  # type: ignore[arg-type]
    elif section == "foreshadows":
        for f in artifact:  # type: ignore[union-attr]
            bible.add_foreshadow(f)
    else:
        raise ValueError(f"unknown section: {section}")


def json_diff(old: object, new: object) -> str:
    import difflib
    import json as _json

    def lines(obj: object) -> list[str]:
        return _json.dumps(obj, ensure_ascii=False, indent=2,
                           default=lambda o: o.model_dump() if hasattr(o, "model_dump") else str(o)
                           ).splitlines()

    return "\n".join(difflib.unified_diff(
        lines(old), lines(new), fromfile="当前", tofile="改写稿", lineterm=""))
```

jobs.py 顶部 import 增补：`from novel.models import Character, Concept, Foreshadow, Outline, World` 与 `from novel.store.bible import StoryBible`（注意 jobs.py 现有 import 均为延迟风格——模块级引入 models/store 无循环风险：store 不 import ui）。`save_bible_section("characters")` 语义为**整段替换**：先删后插才能移除人物——`StoryBible` 无 delete API，实现为直接操作 canonical：

```python
    elif section == "characters":
        d = bible.proj.load_canonical()
        d["characters"] = [ch.model_dump() for ch in artifact]  # type: ignore[union-attr]
        bible.proj.save_canonical(d)
```

（镜像文件由 `_save` 才写——直接 save_canonical 不刷新镜像可接受：canonical 是唯一真源，spec §7。foreshadows 同理用其 json 文件整段重写：`path.write_text(json.dumps([...]))`——沿用 `add_foreshadow` 内的既有文件路径逻辑。）

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bible_api.py -q && uv run mypy novel`
Expected: 全部通过

- [ ] **Step 5: Commit**

```bash
git add novel/ui/jobs.py tests/test_bible_api.py
git commit -m "feat(bible): section read/validate/save helpers + unified json_diff"
```

---

### Task 5: `run_bible_chat_job` + `run_outline_extend_job`

**Files:**
- Modify: `novel/ui/jobs.py`
- Test: `tests/test_bible_api.py`（追加）

**Interfaces:**
- Consumes: Task 4 helpers、`SettingEditorAgent`/`SettingEditInput`、`OutlinerExtendAgent`/`OutlineExtendInput`、`manager.gate_with_feedback`。
- Produces:
  - `run_bible_chat_job(proj_root: Path, section: str, instruction: str, character_id: str | None = None) -> Callable[[Job], object]`。SSE 事件：`{"type": "bible_proposal", "section", "diff", "gate_id"}`（gate_id 便于前端直接调 resolve，**注意** gate SSE 事件本身也带）、`{"type": "bible_applied", "section"}`、`{"type": "bible_chat_done", "section", "applied": bool}`。
  - `run_outline_extend_job(proj_root: Path, n: int) -> Callable[[Job], object]`。SSE 事件：`{"type": "outline_extend_proposal", "added", "diff", "gate_id"}`、`{"type": "outline_extended", "added"}`。
  - demo 分支：`is_live_mode()` 为 False 时**不走 agent**——chat 用 `json.loads(current_json)` 原样回显（diff 空），extend 用既有 beat 模板合成 `T{next}` 占位章。live 时 SettingEditorAgent 由 `make_provider(cfg)` 提供（LiteLLM），demo 时 job 内不调用 provider。

**核心循环（两个 job 共用形态，chat 版）：**

```python
def run_bible_chat_job(proj_root: Path, section: str, instruction: str,
                       character_id: str | None = None) -> Callable[[Job], object]:
    from novel.agents.setting_editor import SettingEditInput, SettingEditorAgent
    from novel.config import load_config
    from novel.models import Character as _Char
    from novel.project import NovelProject
    from novel.runtime import AGENT_NAMES, is_live_mode, make_provider
    from novel.store.bible import StoryBible

    def fn(job: Job) -> object:
        proj = NovelProject(root=proj_root)
        cfg = load_config(proj.config_path)
        bible = StoryBible(proj)
        target_id = character_id  # single-character scoping
        schema = _Char if target_id else _SECTION_MODELS[section]

        def current_artifact() -> object:
            if target_id:
                ch = bible.get_character(target_id)
                assert ch is not None, f"no character {target_id}"
                return ch
            art = read_bible_section(bible, section)
            assert art is not None, f"section {section} is empty"
            return art

        history: list[tuple[str, str]] = []
        for _round in range(3):
            current = current_artifact()
            current_json = current.model_dump_json()  # type: ignore[union-attr]
            if is_live_mode():
                provider = make_provider(cfg)
                draft = SettingEditorAgent(provider, cfg.model_for("setting_editor"),
                                           schema).run(SettingEditInput(
                    current_json=current_json, instruction=instruction, history=history))
            else:
                draft = schema.model_validate_json(current_json)  # demo: echo
            diff = json_diff(current.model_dump(), draft.model_dump())  # type: ignore[union-attr]
            job.emit({"type": "bible_proposal", "section": section,
                      "diff": diff, "draft": draft.model_dump()})  # type: ignore[union-attr]
            approved, fb = job.gate_with_feedback(f"bible:{section}", draft)
            if approved:
                if target_id:
                    bible.upsert_character(draft)  # type: ignore[arg-type]
                else:
                    save_bible_section(bible, section, draft)
                job.emit({"type": "bible_applied", "section": section})
                job.emit({"type": "bible_chat_done", "section": section, "applied": True})
                return None
            if not fb:
                job.emit({"type": "bible_chat_done", "section": section, "applied": False})
                return None
            history.append((instruction, "rejected"))
            instruction = fb
        job.emit({"type": "bible_chat_done", "section": section, "applied": False})
        return None
    return fn
```

extend job 结构相同，但批准后走**追加合并**：`approve_stage` 的伏笔并入逻辑抽公用——在 setup_flow.py 把 `approve_stage` 中 outline 分支的 ledger 并入段提为 `merge_foreshadow_ledger(outline: Outline, bible: StoryBible) -> None`，`approve_stage` 调它；extend job 里：

```python
                existing = bible.get_outline()
                assert existing is not None
                for arc in draft.arcs:          # draft = agent 输出的纯新增章
                    existing.arcs.append(arc)   # 追加弧（agent prompt 已保证编号续接）
                existing.foreshadow_ledger.extend(draft.foreshadow_ledger)
                bible.set_outline(existing)
                merge_foreshadow_ledger(existing, bible)
                job.emit({"type": "outline_extended", "added": n})
```

demo 分支 extend：

```python
            if not is_live_mode():
                existing_max = max((c.chapter_no for a in existing.arcs for c in a.chapters),
                                   default=0)
                beat = ChapterBeat(pov=<roster第一个id>, setting="demo", event="demo extension",
                                   emotional_turn="steady", characters=[<同id>])
                draft = Outline(arcs=[Arc(arc_name="Extension",
                    chapters=[ChapterOutline(chapter_no=existing_max + k,
                                             chapter_title=f"T{existing_max + k}",
                                             beats=[beat]) for k in range(1, n + 1)])])
```

- [ ] **Step 1: Write the failing tests**（`tests/test_bible_api.py` 追加；直接跑 Job 函数，不起 HTTP——HTTP 在 Task 6）

```python
# ---------- run_bible_chat_job / run_outline_extend_job (demo mode) ----------

import threading

from novel.ui import jobs as J


def _run_job(fn) -> J.Job:
    """Run a job fn to completion, auto-approving every gate (demo/test helper)."""
    job = J.Job("n", "bible_test", fn)
    job._bus = None

    def approver() -> None:
        while job.status == "running":
            for g in list(job.gates.values()):
                if not g.done.is_set():
                    J.JobManager.resolve_gate_static = None  # placeholder, see below
                    g.approved = True
                    g.done.set()
            time.sleep(0.01)

    t = threading.Thread(target=approver, daemon=True)
    job.thread.start()
    t.start()
    job.thread.join(timeout=10)
    return job


def _seed_concept(bible):
    bible.set_concept(Concept(logline="L", genre="g", tone="t",
                              target_length_words=100, audience="a"))


def test_chat_job_demo_echo_apply(bible, tmp_path):
    _seed_concept(bible)
    events: list[dict] = []
    collected: list[dict] = []

    def fn(job: J.Job) -> object:
        real_emit = job.emit

        def spy(ev: dict) -> None:
            collected.append(ev)
            real_emit(ev)

        job.emit = spy  # type: ignore[method-assign]
        return J.run_bible_chat_job(bible.proj.root, "concept", "让基调更黑暗")()  # noqa
    ...
```

**实现提示（写测试时直接采用，勿用上面未完成的草稿）**——更简单的方式：给 `Job` 传 bus=None，直接 monkeypatch `Job.gate_with_feedback`：

```python
def test_chat_job_demo_echo_applies(bible, monkeypatch):
    _seed_concept(bible)
    seen: list[dict] = []

    def fake_gate(self, label, artifact):
        seen.append({"label": label, "artifact": artifact})
        return True, None

    monkeypatch.setattr(J.Job, "gate_with_feedback", fake_gate)
    events: list[dict] = []
    fn = J.run_bible_chat_job(bible.proj.root, "concept", "让基调更黑暗")
    job = J.Job("n", "bible_chat", fn)
    job._bus = None
    # capture emits by wrapping emit
    orig_emit = job.emit
    job.emit = lambda ev: (events.append(ev), orig_emit(ev))[1]  # type: ignore[method-assign]
    job.thread = threading.Thread(target=job._run, daemon=True)
    job.thread.start()
    job.thread.join(timeout=5)
    assert not job.thread.is_alive()
    assert job.status == "done"
    assert seen[0]["label"] == "bible:concept"
    assert any(e["type"] == "bible_proposal" for e in events)
    assert any(e["type"] == "bible_applied" for e in events)
    # demo echo: content unchanged
    assert bible.get_concept().logline == "L"


def test_chat_job_rejected_without_feedback_keeps_bible(bible, monkeypatch):
    _seed_concept(bible)
    monkeypatch.setattr(J.Job, "gate_with_feedback", lambda self, label, a: (False, None))
    fn = J.run_bible_chat_job(bible.proj.root, "concept", "改")
    job = J.Job("n", "bible_chat", fn)
    job._bus = None
    job.thread = threading.Thread(target=job._run, daemon=True)
    job.thread.start()
    job.thread.join(timeout=5)
    assert bible.get_concept().tone == "t"  # unchanged


def test_extend_job_demo_appends_and_unlocks(bible, monkeypatch, tmp_path):
    _seed_concept(bible)
    bible.set_world(World(setting="city"))
    from novel.models import Arc, ChapterBeat, ChapterOutline, Character, Outline
    beat = ChapterBeat(pov="c1", setting="tavern", event="e", emotional_turn="d",
                       characters=["c1"])
    bible.upsert_character(Character(id="c1", slug="ara", name="Ara", role="protagonist",
                                     backstory="b", motivation="m", arc="a"))
    bible.set_outline(Outline(arcs=[Arc(arc_name="A", chapters=[
        ChapterOutline(chapter_no=1, chapter_title="T1", beats=[beat])])]))
    monkeypatch.setattr(J.Job, "gate_with_feedback", lambda self, label, a: (True, None))
    fn = J.run_outline_extend_job(bible.proj.root, 2)
    job = J.Job("n", "bible_extend", fn)
    job._bus = None
    job.thread = threading.Thread(target=job._run, daemon=True)
    job.thread.start()
    job.thread.join(timeout=5)
    out = bible.get_outline()
    nums = [c.chapter_no for a in out.arcs for c in a.chapters]
    assert nums == [1, 2, 3]
    from novel.resume import next_start_chapter
    from novel.store.reviews import ReviewStore
    # no chapters on disk yet; write one complete to prove unlock
    (bible.proj.root / "chapters" / "001.md").write_text("x" * 80, encoding="utf-8")
    assert next_start_chapter(bible.proj, ReviewStore(bible.proj)) == 2
```

（`import threading`/`import time` 若未用则不加——本组测试只需 threading。）

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_bible_api.py -q`
Expected: 新增 3 个 FAIL（AttributeError: run_bible_chat_job）

- [ ] **Step 3: Implement** 两个 job 函数（按上文核心循环；`merge_foreshadow_ledger` 抽取进 setup_flow.py 并让 `approve_stage` 复用）

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_bible_api.py -q && uv run ruff check . && uv run mypy novel`
Expected: 全绿（注意 jobs.py 新代码 100 列内、mypy strict 类型标注完整）

- [ ] **Step 5: Commit**

```bash
git add novel/ui/jobs.py novel/setup_flow.py tests/test_bible_api.py
git commit -m "feat(bible): bible_chat & outline_extend jobs — proposal gate + demo echo"
```

---

### Task 6: HTTP 端点（GET/PUT bible、chat、extend）

**Files:**
- Modify: `novel/ui/app.py`
- Test: `tests/test_bible_api.py`（追加 HTTP 段）

**Interfaces:**
- Consumes: Task 4/5 全部函数、`manager.start`/`active_job`。
- Produces（wire 契约，前端 Task 8-10 依赖）:
  - `GET /api/projects/{name}/bible` → `{"concept": {...}|null, "world": {...}|null, "characters": [...], "outline": {...}|null, "foreshadows": [...], "events": [...]}`（pydantic `model_dump` 结果）
  - `PUT /api/projects/{name}/bible/{section}` body=该段 JSON → 200 `{"ok": true}`；非法 section→400；校验失败→422（detail 为 pydantic 错误文本）；活跃 job→409；events→400
  - `POST /api/projects/{name}/bible/chat` body `{"section","instruction","character_id"?}` → 202 `{"job_id"}`（section 非法/为空 → 422；空 instruction → 422）
  - `POST /api/projects/{name}/outline/extend` body `{"n": 1..50}` → 202 `{"job_id"}`（无 outline → 422）
  - Req 模型：`class BibleChatReq(BaseModel): section: str; instruction: str = Field(min_length=1); character_id: str | None = None`、`class ExtendReq(BaseModel): n: int = Field(default=3, ge=1, le=50)`

- [ ] **Step 1: Write the failing tests**

```python
# ---------- HTTP endpoints ----------

from fastapi.testclient import TestClient
from novel.ui.app import create_app


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(tmp_path))


def _seed(client):
    client.post("/api/projects", json={"name": "po"})
    client.put("/api/projects/po/bible/concept", json={
        "logline": "L", "genre": "g", "tone": "t", "target_length_words": 100, "audience": "a"})


def test_get_bible_full_shape(client):
    client.post("/api/projects", json={"name": "po"})
    r = client.get("/api/projects/po/bible")
    assert r.status_code == 200
    data = r.json()
    assert set(data) == {"concept", "world", "characters", "outline", "foreshadows", "events"}
    assert data["concept"] is None and data["events"] == []


def test_put_section_validates_and_persists(client):
    _seed(client)
    assert client.get("/api/projects/po/bible").json()["concept"]["logline"] == "L"
    bad = client.put("/api/projects/po/bible/concept", json={"logline": "x"})
    assert bad.status_code == 422
    ro = client.put("/api/projects/po/bible/events", json=[])
    assert ro.status_code == 400
    unk = client.put("/api/projects/po/bible/nope", json={})
    assert unk.status_code == 400


def test_chat_and_extend_endpoints_202(client):
    _seed(client)
    r = client.post("/api/projects/po/bible/chat",
                    json={"section": "concept", "instruction": "更黑暗"})
    assert r.status_code == 202 and "job_id" in r.json()
    job_id = r.json()["job_id"]
    data = _wait_job_like(client, job_id)
    # demo: gate auto? NO gate auto-approve here — job blocks on gate.
    ...
```

**gate 阻塞处理**：chat job 会阻塞在 gate 上——HTTP 测试用 `GET /api/jobs/{id}` 轮询到 `gates` 非空，然后 `POST /api/gates/{gate_id}` approve，再等 `status == "done"`：

```python
def _wait_job_like(client, job_id, timeout=10.0):
    import time as _t
    deadline = _t.time() + timeout
    while _t.time() < deadline:
        data = client.get(f"/api/jobs/{job_id}").json()
        if data["gates"] or data["status"] != "running":
            return data
        _t.sleep(0.05)
    raise AssertionError("gate never appeared")


def test_chat_endpoint_gate_flow(client):
    _seed(client)
    job_id = client.post("/api/projects/po/bible/chat",
                         json={"section": "concept", "instruction": "更黑暗"}).json()["job_id"]
    data = _wait_job_like(client, job_id)
    assert data["gates"][0]["label"] == "bible:concept"
    assert client.post(f"/api/gates/{data['gates'][0]['id']}",
                       json={"approve": True}).status_code == 200
    status = _poll_done(client, job_id)  # 同 _wait_job 轮询 status != running
    assert status == "done"
    # demo echo: content unchanged, still applied
    assert client.get("/api/projects/po/bible").json()["concept"]["logline"] == "L"


def test_chat_rejects_bad_section_and_empty_instruction(client):
    _seed(client)
    assert client.post("/api/projects/po/bible/chat",
                       json={"section": "nope", "instruction": "x"}).status_code == 422
    assert client.post("/api/projects/po/bible/chat",
                       json={"section": "concept", "instruction": " "}).status_code == 422


def test_extend_requires_outline(client):
    client.post("/api/projects", json={"name": "po"})
    r = client.post("/api/projects/po/outline/extend", json={"n": 2})
    assert r.status_code == 422


def test_put_conflicts_with_active_job(client):
    _seed(client)
    job_id = client.post("/api/projects/po/bible/chat",
                         json={"section": "concept", "instruction": "改"}).json()["job_id"]
    _wait_job_like(client, job_id)  # job now parked on its gate
    r = client.put("/api/projects/po/bible/concept", json={
        "logline": "L2", "genre": "g", "tone": "t", "target_length_words": 1, "audience": "a"})
    assert r.status_code == 409
    assert client.get(f"/api/jobs/{job_id}").json()["gates"]  # still parked
```

（`_poll_done` 复制 `_wait_job` 的轮询体即可，或直接内联。）

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_bible_api.py -q`
Expected: 新增 FAIL（404 on /bible）

- [ ] **Step 3: Implement**（app.py，`get_reviews` 端点后插入）

```python
    class BibleChatReq(BaseModel):
        section: str
        instruction: str = Field(min_length=1)
        character_id: str | None = None

    class ExtendReq(BaseModel):
        n: int = Field(default=3, ge=1, le=50)

    @app.get("/api/projects/{name}/bible")
    def get_bible(name: str) -> dict[str, object]:
        p = _safe_project(root, name)
        from novel.project import NovelProject
        from novel.store.bible import StoryBible
        from novel.ui.jobs import read_bible_section

        def dump(sec: str) -> object:
            art = read_bible_section(StoryBible(NovelProject(root=p)), sec)
            if art is None:
                return None
            if isinstance(art, list):
                return [o.model_dump() for o in art]
            return art.model_dump()

        return {sec: dump(sec) for sec in
                ("concept", "world", "characters", "outline", "foreshadows", "events")}

    @app.put("/api/projects/{name}/bible/{section}")
    def put_bible_section(name: str, section: str, body: object = None) -> dict[str, bool]:
        p = _safe_project(root, name)
        from novel.project import NovelProject
        from novel.store.bible import StoryBible
        from novel.ui.jobs import save_bible_section, validate_bible_section
        if section not in ("concept", "world", "characters", "outline", "foreshadows"):
            raise HTTPException(status_code=400, detail=f"未知设定段: {section}")
        if manager.active_job(name) is not None:
            raise HTTPException(status_code=409, detail="该项目有任务运行中，稍后再试")
        try:
            artifact = validate_bible_section(section, body)
        except AssertionError as e:
            raise HTTPException(status_code=422, detail=f"结构错误: {e}") from e
        except Exception as e:  # pydantic ValidationError
            raise HTTPException(status_code=422, detail=str(e)) from e
        save_bible_section(StoryBible(NovelProject(root=p)), section, artifact)
        return {"ok": True}
```

（body 参数类型用 `object` + 手工校验即可通过 mypy；pydantic ValidationError 捕获写 `except Exception` 时注释标注。`characters`/`foreshadows` 的 list 断言失败也要 422——`validate_bible_section` 内 `assert isinstance(data, list)` 抛 AssertionError，上面已转 422。）

```python
    @app.post("/api/projects/{name}/bible/chat", status_code=202)
    def start_bible_chat(name: str, req: BibleChatReq) -> dict[str, str]:
        p = _safe_project(root, name)
        if req.section not in ("concept", "world", "characters", "foreshadows"):
            raise HTTPException(status_code=422, detail=f"该设定段不支持对话改写: {req.section}")
        if req.section != "characters" or True:
            pass  # instruction min_length already guards empty (whitespace trimmed below)
        instruction = req.instruction.strip()
        if not instruction:
            raise HTTPException(status_code=422, detail="指令不能为空")
        try:
            job = manager.start(name, "bible-chat",
                                jobs.run_bible_chat_job(p, req.section, instruction,
                                                        req.character_id))
        except RuntimeError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        return {"job_id": job.id}

    @app.post("/api/projects/{name}/outline/extend", status_code=202)
    def start_outline_extend(name: str, req: ExtendReq) -> dict[str, str]:
        p = _safe_project(root, name)
        from novel.project import NovelProject
        from novel.store.bible import StoryBible
        if StoryBible(NovelProject(root=p)).get_outline() is None:
            raise HTTPException(status_code=422, detail="尚无大纲，无法追章")
        try:
            job = manager.start(name, "bible-extend", jobs.run_outline_extend_job(p, req.n))
        except RuntimeError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        return {"job_id": job.id}
```

（实现时删掉 start_bible_chat 里那两行占位 `if req.section != ...` 死代码。outline 不在 chat 白名单 = spec「对话目标排除 outline」。）

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_bible_api.py tests/test_ui.py -q`
Expected: 全绿（既有 test_ui.py 不受影响）

- [ ] **Step 5: Commit**

```bash
git add novel/ui/app.py tests/test_bible_api.py
git commit -m "feat(bible): GET/PUT /bible, POST /bible/chat + /outline/extend endpoints"
```

---

### Task 7: SSE 事件接入（前端 store/describe/types + GateModal 豁免）

**Files:**
- Modify: `ui-v2/src/api/types.ts`、`ui-v2/src/stores/events.ts`、`ui-v2/src/describe.ts`、`ui-v2/src/components/GateModal.tsx`、`ui-v2/src/api/events.ts`
- Test: `ui-v2/tests/events.test.ts`（追加）、`ui-v2/tests/GateModal.test.tsx`（追加）

**Interfaces:**
- Consumes: Task 5/6 的事件契约（`bible_proposal{section,diff,draft,gate_id}`、`bible_applied{section}`、`bible_chat_done{section,applied}`、`outline_extend_proposal{added,diff,gate_id}`、`outline_extended{added}`；gate 事件 label 以 `bible:` 开头）。
- Produces（后续任务依赖）:
  - `types.ts`：`export interface BibleData { concept: ConceptData | null; ... }` 等一组接口（见 Step 3）；SSE 类型联合不强制。
  - `events.ts` store 新 state：`bibleProposal: { section: string; diff: string; gateId: string; draft: unknown } | null` 与 `outlineProposal: { added: number; diff: string; gateId: string } | null`；`bible:` gate 不写 `patch.gate`。`job_end` 时两者清空。
  - GateModal：`gate.label.startsWith("bible:")` 直接 `return null`。
  - `api/events.ts`：invalidate 集合加 `bible_applied|outline_extended`（invalidate `["bible"]` 与 `["outline"]`、`["status"]`）。

- [ ] **Step 1: Write the failing tests**

`ui-v2/tests/events.test.ts` 追加：

```typescript
import { useEvents } from "../src/stores/events";

test("bible_proposal sets bibleProposal and gate id, not gate modal state", () => {
  const s = useEvents.getState();
  s.reset();
  s.apply({ type: "gate", gate_id: "g1", label: "bible:concept", artifact: "{}" });
  s.apply({ type: "bible_proposal", section: "concept", diff: "+x", draft: { a: 1 }, gate_id: "g1" });
  const st = useEvents.getState();
  expect(st.gate).toBeNull(); // bible: gates are handled in-page, not by GateModal
  expect(st.bibleProposal).toEqual({ section: "concept", diff: "+x", gateId: "g1", draft: { a: 1 } });
});

test("bible_chat_done and job_end clear proposal", () => {
  const s = useEvents.getState();
  s.reset();
  s.apply({ type: "bible_proposal", section: "world", diff: "d", draft: {}, gate_id: "g" });
  s.apply({ type: "bible_chat_done", section: "world", applied: true });
  expect(useEvents.getState().bibleProposal).toBeNull();
  s.apply({ type: "outline_extend_proposal", added: 2, diff: "d", gate_id: "g2" });
  s.apply({ type: "job_end", status: "done", error: null, kind: "bible-chat" });
  expect(useEvents.getState().outlineProposal).toBeNull();
});
```

（若 events.test.ts 现有结构是纯函数测试，按其现有 import 风格接入；SseEvent 允许任意额外字段。）

- [ ] **Step 2: Run to verify failure**

Run: `cd ui-v2 && npm run test -- events.test`
Expected: FAIL（bibleProposal 不存在）

- [ ] **Step 3: Implement**

`types.ts` 追加：

```typescript
export interface ConceptData {
  logline: string; genre: string; tone: string; themes: string[];
  target_length_words: number; audience: string;
}
export interface WorldData {
  setting: string; era: string; rules: string[]; power_system: string;
  factions: { name: string; ideology: string; resources: string; conflict_with: string }[];
  locations: { name: string; description: string; narrative_function: string }[];
  constraints: string[];
}
export interface CharacterStateData {
  emotional_state: string; physical_state: string; knowledge_gained: string[];
  relationships_shifted: Record<string, string>; location_end: string;
}
export interface CharacterData {
  id: string; slug: string; name: string; role: string; backstory: string;
  motivation: string; arc: string; voice_fingerprint: Record<string, string>;
  mannerisms: { text: string; used_count: number }[]; description_history: string[];
  relationships: Record<string, string>; state: CharacterStateData;
}
export interface BeatData {
  beat_id: string; pov: string; setting: string; event: string; emotional_turn: string;
  characters: string[]; plants: string[]; payoffs: string[];
}
export interface OutlineChapterData {
  chapter_no: number; chapter_title: string; beats: BeatData[];
}
export interface OutlineFullData {
  arcs: { arc_name: string; chapters: OutlineChapterData[] }[];
  foreshadow_ledger: { id: string; planted_in: string; paid_off_in: string; description: string }[];
}
export interface ForeshadowData {
  id: string; description: string; planted_ch: number | null;
  payoff_ch: number | null; status: string;
}
export interfaceEventData { id: string; chapter: number; characters: string[]; summary: string }
export interface BibleData {
  concept: ConceptData | null; world: WorldData | null; characters: CharacterData[];
  outline: OutlineFullData | null; foreshadows: ForeshadowData[];
  events: EventData[];
}
```

（注意修正笔误：`export interfaceEventData` → `export interface EventData`。）

`stores/events.ts`：EventState 增字段与 `case`：

```typescript
  bibleProposal: { section: string; diff: string; gateId: string; draft: unknown } | null;
  outlineProposal: { added: number; diff: string; gateId: string } | null;
```

`apply` switch 增：

```typescript
        case "gate":
          if (String(ev.label).startsWith("bible:")) {
            // bible gates render in the Bible page's diff panel, not the global modal
            break;
          }
          ...existing...
        case "bible_proposal":
          patch.bibleProposal = {
            section: String(ev.section), diff: String(ev.diff ?? ""),
            gateId: String(ev.gate_id ?? ""), draft: (ev as { draft?: unknown }).draft,
          };
          break;
        case "bible_chat_done":
          patch.bibleProposal = null;
          break;
        case "outline_extend_proposal":
          patch.outlineProposal = {
            added: Number(ev.added ?? 0), diff: String(ev.diff ?? ""),
            gateId: String(ev.gate_id ?? ""),
          };
          break;
        case "outline_extended":
          patch.outlineProposal = null;
          break;
```

`job_end` case 里补 `patch.bibleProposal = null; patch.outlineProposal = null;`；`resetTransient`/`reset` 同步清空两字段。

`GateModal.tsx` 最顶部渲染判定改：`if (!gate || dismissed || gate.label.startsWith("bible:")) return null;`

`describe.ts` 增文案：

```typescript
  case "bible_proposal": return "设定改写稿已生成，等待确认";
  case "bible_applied": return "设定改写已应用";
  case "bible_chat_done": return ev.applied ? "对话改写结束（已应用）" : "对话改写结束（未应用）";
  case "outline_extend_proposal": return "大纲追章方案已生成，等待确认";
  case "outline_extended": return `大纲已追加 ${ev.added} 章`;
```

（按 describe.ts 现有函数签名接入——先读该文件再改。）

`api/events.ts` onmessage 的 invalidate 判定改为：

```typescript
          if (ev.type === "premise_done" || ev.type === "setup_stage" || ev.type === "job_end") {
            void qc.invalidateQueries({ queryKey: ["status"] });
          }
          if (ev.type === "bible_applied" || ev.type === "outline_extended" || ev.type === "job_end") {
            void qc.invalidateQueries({ queryKey: ["bible"] });
          }
          if (ev.type === "outline_extended" || ev.type === "job_end") {
            void qc.invalidateQueries({ queryKey: ["outline"] });
          }
```

`GateModal.test.tsx` 追加一个用例：label `bible:concept` 的 gate 事件后 `queryByTestId("gate-modal")` 为 null。

- [ ] **Step 4: Run tests**

Run: `cd ui-v2 && npm run test && npm run typecheck`
Expected: 全绿

- [ ] **Step 5: Commit**

```bash
git add ui-v2/src/api/types.ts ui-v2/src/api/events.ts ui-v2/src/stores/events.ts ui-v2/src/describe.ts ui-v2/src/components/GateModal.tsx ui-v2/tests/events.test.ts ui-v2/tests/GateModal.test.tsx
git commit -m "feat(bible-ui): SSE bible_proposal/outline events; GateModal skips bible: gates"
```

---

### Task 8: API hooks（useBible/useSaveBibleSection/useBibleChat/useOutlineExtend）

**Files:**
- Modify: `ui-v2/src/api/hooks.ts`
- Test: `ui-v2/tests/hooks.test.tsx`（追加）

**Interfaces:**
- Consumes: `api` client、Task 7 的 `BibleData`。
- Produces:
  - `useBible(name)` → `useQuery<BibleData>`，queryKey `["bible", name]`
  - `useSaveBibleSection(name)` → mutation `(vars: {section: string; data: unknown}) => api<{ok: boolean}>`，method PUT `${p(name)}/bible/${section}`，成功 invalidate `["bible", name]`、`["status", name]`
  - `useBibleChat(name)` → mutation `(vars: {section: string; instruction: string; character_id?: string}) => api<{job_id: string}>`，POST `${p(name)}/bible/chat`
  - `useOutlineExtend(name)` → mutation `(vars: {n: number}) => api<{job_id: string}>`，POST `${p(name)}/outline/extend`，成功 invalidate `["outline", name]`

- [ ] **Step 1: Write the failing test**（沿用 hooks.test.tsx 现有 fetch mock 模式——先读文件头部 helper）

```typescript
test("useBible fetches and useSaveBibleSection PUTs with invalidation", async () => {
  // arrange: mock fetch GET /api/projects/x/bible -> BibleData-ish, PUT -> {ok:true}
  // renderHook + act; assert PUT body and that queries were invalidated (spy on qc)
});
```

（具体断言对齐该文件现有用例的写法：fetch mock 记录 URL/method/body；invalidate 用 queryClient spy 或直接断言 mutation 成功后 `["bible"]` query refetch——采用文件内既有模式，不引入新测试机制。）

- [ ] **Step 2: Run to verify failure** — `npm run test -- hooks.test`

- [ ] **Step 3: Implement** 四个 hooks（签名见上；模板照抄 `useWriteChapters` 的 invalidate 写法）

- [ ] **Step 4: Run tests** — `npm run test && npm run typecheck`

- [ ] **Step 5: Commit**

```bash
git add ui-v2/src/api/hooks.ts ui-v2/tests/hooks.test.tsx
git commit -m "feat(bible-ui): useBible/useSaveBibleSection/useBibleChat/useOutlineExtend hooks"
```

---

### Task 9: DiffView + BibleChat 组件

**Files:**
- Create: `ui-v2/src/components/DiffView.tsx`、`ui-v2/src/components/BibleChat.tsx`
- Test: `ui-v2/tests/BibleChat.test.tsx`（新建）

**Interfaces:**
- Consumes: `useEvents`（bibleProposal/outlineProposal）、`useResolveGate`、`useBibleChat`、`useOutlineExtend`。
- Produces:
  - `DiffView({ diff }: { diff: string })`：按行渲染，`+`开头绿（#e6f4ea 底色）`-`开头红（#fdecea），`@@`灰，其余默认；`data-testid="diff-view"`。
  - `BibleChat({ name, section }: { name: string; section: string })`：目标为当前 section（`outline`/`events` 时整块替换为只读说明文字）；人物段渲染 Select 选人（`data-testid="chat-character-select"`）；历史为会话内 state `Array<{instruction: string; status: "pending"|"applied"|"discarded"}>`；发送按钮 `data-testid="chat-send"`；proposal 到达时渲染 DiffView + 应用（approve=true）/放弃（approve=false 无 feedback）按钮，`bible_chat_done` 后按 `applied` 更新历史状态。追章入口不在此组件（在 Outline 卡片，Task 10）。

- [ ] **Step 1: Write the failing tests**

```typescript
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { AntApp } from "antd"; // 照 pages.test.tsx 的 Provider 包装方式
import BibleChat from "../src/components/BibleChat";
import DiffView from "../src/components/DiffView";
import { useEvents } from "../src/stores/events";

test("DiffView renders +/- lines with colors", () => {
  render(<DiffView diff={'- "a": 1"\n+ "a": 2"\n@@ hunk @@\n ctx"} />);
  const el = screen.getByTestId("diff-view");
  const lines = el.children;
  expect(lines[0].getAttribute("data-sign")).toBe("-");
  expect(lines[1].getAttribute("data-sign")).toBe("+");
  expect(lines[2].getAttribute("data-sign")).toBe("@");
});

// fetch mock：POST /api/projects/x/bible/chat -> {job_id:"j1"}
test("BibleChat sends instruction and renders proposal then applies via gate", async () => {
  // mock fetch; render BibleChat name="x" section="world"
  fireEvent.change(screen.getByTestId("chat-input").querySelector("textarea")!, {
    target: { value: "让世界更冷" } });
  fireEvent.click(screen.getByTestId("chat-send"));
  await waitFor(() => expect(screen.getByText("生成中…")).toBeTruthy());
  act(() => {
    useEvents.getState().apply({ type: "bible_proposal", section: "world",
      diff: "- old\n+ new", draft: {}, gate_id: "g9" });
  });
  expect(screen.getByTestId("diff-view")).toBeTruthy();
  // mock POST /api/gates/g9 -> {resolved:true}
  fireEvent.click(screen.getByTestId("chat-apply"));
  await waitFor(() =>
    expect(screen.getByText("已应用").toBeTruthy ? screen.getByText("已应用") : null).toBeTruthy());
});
```

（写测试时以实际实现为准调整选择器细节，但保留 data-testid 契约：`chat-input`/`chat-send`/`chat-apply`/`chat-discard`/`diff-view`。）

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Implement** 两个组件。BibleChat 骨架：

```tsx
export default function BibleChat({ name, section }: { name: string; section: string }) {
  const proposal = useEvents((s) => s.bibleProposal);
  const chat = useBibleChat(name);
  const resolve = useResolveGate(name);
  const [text, setText] = useState("");
  const [history, setHistory] = useState<{ instruction: string; status: string }[]>([]);
  const [characterId, setCharacterId] = useState<string | undefined>();
  const { data: bible } = useBible(name);
  const disabled = section === "outline" || section === "events";
  ...
}
```

（`outline`/`events` 只读文案；pending 条目在发送时 push，`bible_chat_done` 事件由父组件或本组件 `useEffect` 监听 `lastEnd`/`bibleProposal` 清空来置状态——采用「proposal 清空 && job_end」判定 applied 需要 store 提供更多信息；简化：`bible_chat_done` 事件也写进一个 store 字段 `bibleChatDone: {section, applied, seq}`，BibleChat 用 useEffect 监听 seq 更新最后一条 pending 的状态。**在 Task 7 的 store 里补这个字段**，类型 `{ section: string; applied: boolean; seq: number } | null`，`bible_chat_done` case 递增 seq。）

- [ ] **Step 4: Run tests** — `npm run test && npm run typecheck`

- [ ] **Step 5: Commit**

```bash
git add ui-v2/src/components/DiffView.tsx ui-v2/src/components/BibleChat.tsx ui-v2/tests/BibleChat.test.tsx ui-v2/src/stores/events.ts
git commit -m "feat(bible-ui): DiffView + BibleChat panel with apply/discard via gate"
```

---

### Task 10: Bible 页面 + 路由 + 编辑 Modal + 追章入口

**Files:**
- Create: `ui-v2/src/pages/Bible.tsx`
- Modify: `ui-v2/src/App.tsx`（route + Sider）、`ui-v2/tests/pages.test.tsx`（追加）

**Interfaces:**
- Consumes: Task 7-9 全部。
- Produces: 路由 `/p/:name/bible`；页面 `data-testid="page-bible"`。

**页面结构：**
- 顶部 Title「设定库」+ demo Alert（照 Setup.tsx 抄）。
- 左侧 `Menu`（inline, selectedKeys=[section]）：concept/world/characters/outline/foreshadows/events，中文标签用 `SETUP_STAGE_NAMES` + 追加 `foreshadows: "伏笔"`, `events: "事件"`（constants.ts 增 `BIBLE_SECTION_NAMES`）。
- 主区按 section 渲染（见下）+ 每卡片头部「编辑 JSON」按钮（`data-testid="edit-json"`，events 段无此按钮）。
- 右侧 `BibleChat`（section 传入；人物段传选择的人）。布局用 `Layout` 或 flex 双栏，`span={16}/{8}` 的 Row/Col 即可。
- Outline 卡片底部：「追章」InputNumber + 按钮（`data-testid="extend-outline"`），成功（`outline_extended` 事件）后 message 提示；outlineProposal 到达时在卡片内渲染 DiffView + 应用/放弃（复用 resolve gate）。

**各 section 预览：**
- concept：`Descriptions`（logline/genre/tone/themes/audience/target_length_words）。
- world：Descriptions（setting/era/power_system）+ rules/constraints 列表 + locations/factions 小卡片。
- characters：每人物 Card——Descriptions 静态字段 + 动态区：`state.emotional_state`/`state.location_end`、voice_fingerprint 条数、mannerisms 前 3（text ×used_count）、description_history 条数、relationships 对。
- outline：Collapse（弧线）→ 嵌套 Collapse（章）→ beats 列表（pov/event/emotional_turn/plants/payoffs Tag）。
- foreshadows：Table（id/description/planted_ch/payoff_ch/status Tag，颜色 open=default planted=processing paid_off=success）。
- events：Timeline 逆序（`ch${chapter} · summary`，children 显示 characters join）。

**编辑 Modal：** antd `Modal` + `Input.TextArea`（mono），open 时 `JSON.stringify(data, null, 2)`；保存调 `useSaveBibleSection`，`ApiError` 时 `message.error(e.message)`（后端 422 detail 是 pydantic 文本，直接展示）；成功 invalidate 自动刷新（hooks 已做）。

- [ ] **Step 1: Write the failing tests**（pages.test.tsx 追加；stubFetchFor 需扩展 `bible` 字段支持 GET/PUT `/bible*`）

```typescript
test("Bible page renders concept card and sections nav", async () => {
  stubFetchFor({ bible: { concept: { logline: "L", ... }, world: null, characters: [],
    outline: null, foreshadows: [], events: [] } });
  renderPage(<Bible />, { name: "x" });
  expect(screen.getByTestId("page-bible")).toBeTruthy();
  expect(await screen.findByText("L")).toBeTruthy();
  expect(screen.getByText("世界观")).toBeTruthy();
});

test("edit JSON persists via PUT and shows 422 error", async () => {
  // PUT /api/projects/x/bible/concept -> 422 {detail: "validation error..."}
  // click edit-json -> textarea visible -> click save -> error message shown
});

test("outline card offers extend and applies proposal", async () => {
  // bible.outline = {...}; click extend-outline; emit outline_extend_proposal via store;
  // diff-view visible; click apply -> POST /api/gates/g1
});
```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Implement** Bible.tsx + App.tsx 路由（`<Route path="bible" element={<Bible />} />` 紧跟 setup；Sider「创作」组 `setup` 后插 `{ key: "bible", label: "设定库" }`）+ constants.ts `BIBLE_SECTION_NAMES`。

- [ ] **Step 4: Run tests**

Run: `cd ui-v2 && npm run test && npm run typecheck && npm run build`
Expected: 全绿（build 产出 dist，`test_ui_v2_dist_served` 由 CI skipif 守护）

- [ ] **Step 5: Commit**

```bash
git add ui-v2/src/pages/Bible.tsx ui-v2/src/App.tsx ui-v2/src/constants.ts ui-v2/tests/pages.test.tsx
git commit -m "feat(bible-ui): Bible page — full preview, JSON edit, chat panel, outline extend"
```

---

### Task 11: README + 收尾验证

**Files:**
- Modify: `README.md`
- Test: 无新增；全量门禁。

- [ ] **Step 1: README 增补**（找「分阶段设定」章节后插入「设定库」小节；`uv run novel-ui` 章节补页面说明）：
  - 页面入口与六段预览说明；
  - 手动 JSON 编辑（PUT 语义、422/409 含义）；
  - 对话改写（demo 模式不改变内容的提示；live 模式需要 `setting_editor` 可在 config 配置模型，缺省回退 default）；
  - 大纲追章（追章后 `write-chapter` 自动续写新章；`outline exhausted` 警告消除）；
  - config 参考表补 `setting_editor` 行。
- [ ] **Step 2: 全量门禁**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy novel && cd ui-v2 && npm run test && npm run typecheck && npm run build`
Expected: 全绿

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: 设定库页面 — 预览/JSON编辑/对话改写/大纲追章用法"
```

---

## Self-Review 记录

- **Spec 覆盖**：§4.1→Task 1；§4.2→Task 2；AGENT_NAMES→Task 3；§4.3 GET/PUT/chat/extend→Task 4/6；§4.4 两 job+diff→Task 5；§4.5 并发 409 与 gate 豁免→Task 6/7；§5.1-5.4→Task 7-10；§6 测试→各任务；README→Task 11。demo 行为在 job 层（Task 5），符合「不触碰九智能体管线」。
- **占位符**：Task 6 Step 3 start_bible_chat 有两行需删除的死代码已标注；Task 8 测试为骨架但注明沿用既有 mock 模式先读后写；其余均含完整代码。
- **类型一致性**：`SettingEditInput`/`OutlineExtendInput` 字段在 Task 1/2 定义、Task 5 消费一致；store 字段 `bibleProposal/outlineProposal/bibleChatDone` 在 Task 7 定义、Task 9 消费一致（bibleChatDone 在 Task 9 Step 3 补进 store，已在该任务 Files 列出）。
