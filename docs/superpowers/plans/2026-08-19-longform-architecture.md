# 长篇架构加固（Long-form Architecture）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把现有管线原地加固到 50–100 万字 / 200–400 章规模：分层摘要记忆、两段式滚动大纲、记忆库治理、中文 token 估算、运行工程（gate-every-N / 进度 / 手改警告）。

**Architecture:** 不动「单线程顺序管线 + 磁盘状态 + 断点续跑」骨架。新增 SummaryStore（章/卷/全书三级摘要，`chapters/_summaries/` + `.meta/summaries.json`）、ArcPlanner/ArcDetailer 两段式出纲（骨架 + 按卷明细）、bible 批量写盘与压缩治理；组装器改为 10 级优先阶梯 + 截断；graph 循环加自动续纲、卷边界摘要、懒回填、哈希手改检测。

**Tech Stack:** Python 3.11+ / uv / pydantic v2 / typer / chromadb；前端 React 18 + Vite + TS strict + AntD 5 + zustand + vitest。

**Spec:** `docs/superpowers/specs/2026-08-19-longform-architecture-design.md`（v2，用户已认可）。计划与 spec 冲突时以 spec 为准。

## Global Constraints

- 测试一律用 `FakeProvider`（`novel/providers.py`），零网络零 API 成本；demo 是默认模式。
- 每步之后 `uv run pytest -q`、`uv run ruff check .`（line-length 100）、`uv run mypy novel`（strict）必须保持绿。
- 所有新模型输出必须是 pydantic schema；agents 是 `Agent[I, O]` 泛型。
- 章节文件是 `chapters/NNN.md` 三位数字格式，不得改动该约定；resume 判定仍只看章节文件 + reviews。
- `project.config.yaml` 含明文密钥且 gitignored——测试里绝不读写真实项目目录，只用 `tmp_path` scaffold。
- 新配置字段必须同步 README.md 的字段表（Task 16 统一做，但字段名从 Task 1 起固定）：`target_chapters: int | None = None`、`chapter_target_length: int = 2500`、`arc_detail_lookahead: int = 5`。
- 代码常量（不进 config）：`RECENT_SUMMARY_K = 5`、`OPEN_THREADS_M = 10`（assembler.py）；`VOICE_SAMPLE_K = 10`（最早 1 + 最近 9）、`MANNERISMS_CAP = 8`（bible.py）。
- 提交信息用仓库既有风格：`feat(longform): ...` / `test(longform): ...` / `docs: ...`。
- FakeProvider 按 message 里的 `agent` tag 路由 canned 响应。新 LLM 调用点的 tag：`arc_planner`、`arc_detailer`（模型槽位都是 `outliner`）、`summarizer`（章/卷摘要）、`digestor`（全书梗概）（模型槽位都是 `extractor`）。
- 设计文档 §4.2 阶梯里没有 events 块；实现保留 events 作为旧项目降级 fallback，放在 weak_spots 与 recency 之间（比 spec 多一项，向后兼容，低优先级最先被截断）。

---

### Task 1: models + config 长篇字段

**Files:**
- Modify: `novel/models.py`（`Outline` / `Character` 之后追加新模型）
- Modify: `novel/config.py:24-28`（`Generation`）、`novel/config.py:60-70`（`load_config`）
- Test: `tests/test_models.py`、`tests/test_config.py`

**Interfaces:**
- Produces（后续所有任务依赖的类型与字段名，逐字使用）:
  - `ChapterSummary(chapter_no: int, arc_name: str = "", summary: str, characters_involved: list[str] = [], threads_advanced: list[str] = [], prose_sha256: str = "")`
  - `ArcSummary(arc_name: str, chapter_start: int, chapter_end: int, summary: str, major_developments: list[str] = [])`
  - `BookDigest(chapter_count: int, current_arc: str = "", summary: str = "")`
  - `ArcSkeleton(arc_name: str, chapter_start: int, chapter_end: int, premise: str = "")`
  - `ArcPlan(arcs: list[ArcSkeleton] = [], planned_total_chapters: int = 0)`
  - `Outline.arc_plan: list[ArcSkeleton] = []`（**语义：待明细的骨架队列**，已明细的卷从队列移除）
  - `Character.last_updated_chapter: int = 0`
  - `Generation.target_chapters: int | None = None` / `chapter_target_length: int = 2500` / `arc_detail_lookahead: int = 5`

- [ ] **Step 1: Write the failing tests**

`tests/test_models.py` 追加：

```python
def test_longform_models_defaults_and_outline_arc_plan():
    from novel.models import ArcPlan, ArcSkeleton, BookDigest, ChapterSummary, Outline, ArcSummary
    cs = ChapterSummary(chapter_no=3, summary="主角抵达钟城")
    assert cs.arc_name == "" and cs.prose_sha256 == ""
    o = Outline()
    assert o.arc_plan == []          # 旧 bible JSON 缺该字段也能加载
    plan = ArcPlan(arcs=[ArcSkeleton(arc_name="卷一", chapter_start=1, chapter_end=30,
                                     premise="偷取时间")], planned_total_chapters=120)
    assert plan.arcs[0].premise == "偷取时间"
    d = BookDigest(chapter_count=30, summary="第一卷完结")
    assert d.current_arc == ""
    a = ArcSummary(arc_name="卷一", chapter_start=1, chapter_end=30, summary="…")
    assert a.major_developments == []


def test_character_last_updated_chapter_default():
    from novel.models import Character
    c = Character(id="c1", slug="a", name="A", role="p", backstory="b", motivation="m", arc="a")
    assert c.last_updated_chapter == 0
```

`tests/test_config.py` 追加：

```python
def test_generation_longform_fields_parse(tmp_path):
    from novel.config import load_config
    cfg_file = tmp_path / "project.config.yaml"
    cfg_file.write_text(
        "models: { default: { provider: zhipu, model: glm-4-plus } }\n"
        "generation:\n"
        "  target_chapters: 240\n"
        "  chapter_target_length: 3000\n"
        "  arc_detail_lookahead: 10\n",
        encoding="utf-8",
    )
    cfg = load_config(cfg_file)
    assert cfg.generation.target_chapters == 240
    assert cfg.generation.chapter_target_length == 3000
    assert cfg.generation.arc_detail_lookahead == 10


def test_generation_longform_fields_default_off():
    from novel.config import Generation, load_config
    import yaml
    g = Generation()
    assert g.target_chapters is None and g.chapter_target_length == 2500 and g.arc_detail_lookahead == 5
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_models.py tests/test_config.py -q`
Expected: FAIL — `ImportError: cannot import name 'ChapterSummary'` / `AttributeError: 'Generation' object has no attribute 'target_chapters'`

- [ ] **Step 3: Implement**

`novel/models.py` 在 `Outline` 类之前插入五个新模型，`Outline` 与 `Character` 加字段：

```python
class ChapterSummary(BaseModel):
    chapter_no: int
    arc_name: str = ""
    summary: str
    characters_involved: list[str] = Field(default_factory=list)
    threads_advanced: list[str] = Field(default_factory=list)
    prose_sha256: str = ""    # set by the pipeline at write time (manual-edit detection)


class ArcSummary(BaseModel):
    arc_name: str
    chapter_start: int
    chapter_end: int
    summary: str
    major_developments: list[str] = Field(default_factory=list)


class BookDigest(BaseModel):
    chapter_count: int
    current_arc: str = ""
    summary: str = ""


class ArcSkeleton(BaseModel):
    """卷骨架：章数为软目标，编号以运行时 next_chapter_no 为准（spec §4.3）。"""
    arc_name: str
    chapter_start: int
    chapter_end: int
    premise: str = ""


class ArcPlan(BaseModel):
    arcs: list[ArcSkeleton] = Field(default_factory=list)
    planned_total_chapters: int = 0
```

`Outline` 改为：

```python
class Outline(BaseModel):
    arcs: list[Arc] = Field(default_factory=list)
    foreshadow_ledger: list[ForeshadowLedgerEntry] = Field(default_factory=list)
    arc_plan: list[ArcSkeleton] = Field(default_factory=list)
```

`Character` 增加一行字段：

```python
    last_updated_chapter: int = 0
```

`novel/config.py` 的 `Generation`：

```python
@dataclass
class Generation:
    human_gate_every_n_chapters: int = 1
    context_token_budget: int = 24000
    min_chapter_chars: int = 50    # resume check: shorter chapter files count as incomplete
    target_chapters: int | None = None    # planned whole-book total; None = legacy one-shot outline
    chapter_target_length: int = 2500     # per-chapter target: zh=字, en=words
    arc_detail_lookahead: int = 5         # auto arc-detail trigger runway (chapters)
```

`load_config` 中 `generation=Generation(...)` 补三个参数：

```python
        generation=Generation(
            human_gate_every_n_chapters=gen.get("human_gate_every_n_chapters", 1),
            context_token_budget=gen.get("context_token_budget", 24000),
            min_chapter_chars=gen.get("min_chapter_chars", 50),
            target_chapters=gen.get("target_chapters"),
            chapter_target_length=gen.get("chapter_target_length", 2500),
            arc_detail_lookahead=gen.get("arc_detail_lookahead", 5),
        ),
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_models.py tests/test_config.py -q && uv run mypy novel && uv run ruff check .`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add novel/models.py novel/config.py tests/test_models.py tests/test_config.py
git commit -m "feat(longform): longform schema — ChapterSummary/ArcSummary/BookDigest/ArcSkeleton/ArcPlan + config fields"
```

---

### Task 2: CJK 感知 token 估算

**Files:**
- Modify: `novel/memory/assembler.py:14-15`（`estimate_tokens`）
- Test: `tests/test_assembler.py`

**Interfaces:**
- Produces: `estimate_tokens(text: str) -> int`（签名不变，行为变化：ASCII ≈ 4 字符/token，CJK ≈ 1.5 token/字符，保守高估）
- 注意：`tests/test_assembler.py:45` 现有断言 `estimate_tokens("x" * 300) == 100` 必须同步改为 `== 75`。

- [ ] **Step 1: Write the failing tests**

`tests/test_assembler.py` 追加：

```python
def test_estimate_tokens_cjk_aware():
    # pure ASCII: 4 chars per token
    assert estimate_tokens("x" * 300) == 75
    # pure CJK: 1.5 tokens per char (conservative)
    assert estimate_tokens("钟" * 100) == 150
    # mixed: ascii part + cjk part computed independently, min 1
    assert estimate_tokens("abcd" + "钟" * 10) == 1 + 15
    assert estimate_tokens("") == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_assembler.py -q`
Expected: FAIL（旧实现 `len//3`：300//3=100 ≠ 75）

- [ ] **Step 3: Implement**

`novel/memory/assembler.py` 顶部加 `import math`、`import re`，替换 `estimate_tokens`：

```python
_CJK_RE = re.compile(
    r"[\u3040-\u30ff\u31f0-\u31ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
    r"\u3000-\u303f\uff00-\uffef]"
)


def estimate_tokens(text: str) -> int:
    """CJK-aware and deliberately conservative: CJK chars count as 1.5 tokens,
    everything else as 4 chars per token. Over-estimating truncates earlier,
    which is safe; the old len//3 heuristic under-counted Chinese ~3x."""
    cjk = len(_CJK_RE.findall(text))
    other = len(text) - cjk
    return max(1, math.ceil(other / 4) + math.ceil(cjk * 1.5))
```

同时把 `tests/test_assembler.py:45` 的 `assert estimate_tokens("x" * 300) == 100` 改为 `== 75`。

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_assembler.py tests/test_graph.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add novel/memory/assembler.py tests/test_assembler.py
git commit -m "feat(longform): CJK-aware conservative token estimation (regex class, no per-char unicodedata)"
```

---

### Task 3: SummaryStore（章/卷/全书摘要 + 手改哈希检测）

**Files:**
- Create: `novel/store/summaries.py`
- Test: `tests/test_summaries.py`

**Interfaces:**
- Produces:
  - `SummaryStore(proj: NovelProject)`，方法：`put_chapter_summary(cs: ChapterSummary) -> None`、`get_chapter_summary(n: int) -> ChapterSummary | None`、`recent_chapter_summaries(upto: int, k: int) -> list[ChapterSummary]`、`put_arc_summary(a: ArcSummary) -> None`、`get_arc_summary(arc_name: str) -> ArcSummary | None`、`all_arc_summaries() -> list[ArcSummary]`、`put_book_digest(d: BookDigest) -> None`、`get_book_digest() -> BookDigest | None`
  - `sha256_text(text: str) -> str`
  - `detect_edited_chapters(proj: NovelProject, store: SummaryStore) -> list[int]`
  - 存储：章摘要 `chapters/_summaries/NNN.json`；卷摘要+全书梗概 `.meta/summaries.json`（`{"arcs": [...], "book": {...}}`，按 chapter_start 排序，整文件重写）

- [ ] **Step 1: Write the failing tests**

`tests/test_summaries.py`：

```python
from novel.models import ArcSummary, BookDigest, ChapterSummary
from novel.project import NovelProject
from novel.store.summaries import SummaryStore, detect_edited_chapters, sha256_text


def _proj(tmp_path):
    return NovelProject.scaffold("n", genre="g", root=tmp_path)


def test_chapter_summary_roundtrip_and_recent(tmp_path):
    store = SummaryStore(_proj(tmp_path))
    for n in range(1, 6):
        store.put_chapter_summary(ChapterSummary(chapter_no=n, arc_name="卷一",
                                                 summary=f"s{n}", prose_sha256=sha256_text(f"p{n}")))
    assert store.get_chapter_summary(3).summary == "s3"
    assert store.get_chapter_summary(99) is None
    recent = store.recent_chapter_summaries(upto=5, k=3)
    assert [cs.chapter_no for cs in recent] == [3, 4, 5]
    assert store.recent_chapter_summaries(upto=2, k=5) == [store.get_chapter_summary(1),
                                                           store.get_chapter_summary(2)]


def test_arc_and_book_digest_storage(tmp_path):
    store = SummaryStore(_proj(tmp_path))
    store.put_arc_summary(ArcSummary(arc_name="卷一", chapter_start=1, chapter_end=30, summary="a1"))
    store.put_arc_summary(ArcSummary(arc_name="卷二", chapter_start=31, chapter_end=60, summary="a2"))
    assert [a.arc_name for a in store.all_arc_summaries()] == ["卷一", "卷二"]
    assert store.get_arc_summary("卷二").summary == "a2"
    store.put_book_digest(BookDigest(chapter_count=60, current_arc="卷二", summary="d"))
    assert store.get_book_digest().summary == "d"
    assert store.get_arc_summary("卷三") is None


def test_detect_edited_chapters(tmp_path):
    proj = _proj(tmp_path)
    store = SummaryStore(proj)
    prose = "正文" * 30
    (proj.root / "chapters" / "001.md").write_text(prose, encoding="utf-8")
    store.put_chapter_summary(ChapterSummary(chapter_no=1, summary="s", prose_sha256=sha256_text(prose)))
    assert detect_edited_chapters(proj, store) == []
    (proj.root / "chapters" / "001.md").write_text(prose + "手改", encoding="utf-8")
    assert detect_edited_chapters(proj, store) == [1]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_summaries.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'novel.store.summaries'`

- [ ] **Step 3: Implement**

`novel/store/summaries.py`：

```python
"""Three-tier story summaries: per-chapter files under chapters/_summaries/,
arc summaries + whole-book digest in .meta/summaries.json (spec §4.1)."""
from __future__ import annotations

import hashlib
import json

from novel.models import ArcSummary, BookDigest, ChapterSummary
from novel.project import NovelProject


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class SummaryStore:
    def __init__(self, proj: NovelProject) -> None:
        self.proj = proj
        self._chapter_dir = proj.root / "chapters" / "_summaries"
        self._chapter_dir.mkdir(parents=True, exist_ok=True)
        self._meta_path = proj.root / ".meta" / "summaries.json"

    # ---- chapter summaries: one JSON file per chapter ----
    def _chapter_path(self, n: int) -> object:
        return self._chapter_dir / f"{n:03d}.json"

    def put_chapter_summary(self, cs: ChapterSummary) -> None:
        path = self._chapter_path(cs.chapter_no)
        path.write_text(cs.model_dump_json(), encoding="utf-8")

    def get_chapter_summary(self, n: int) -> ChapterSummary | None:
        path = self._chapter_path(n)
        if not path.is_file():
            return None
        return ChapterSummary.model_validate_json(path.read_text(encoding="utf-8"))

    def recent_chapter_summaries(self, upto: int, k: int) -> list[ChapterSummary]:
        """Last k existing summaries for chapters <= upto (oldest → newest)."""
        out: list[ChapterSummary] = []
        n = upto
        while n >= 1 and len(out) < k:
            cs = self.get_chapter_summary(n)
            if cs is not None:
                out.append(cs)
            n -= 1
        return list(reversed(out))

    # ---- arc summaries + book digest: one small meta file ----
    def _load_meta(self) -> dict:
        if not self._meta_path.is_file():
            return {"arcs": [], "book": None}
        return json.loads(self._meta_path.read_text(encoding="utf-8"))

    def _save_meta(self, data: dict) -> None:
        self._meta_path.parent.mkdir(parents=True, exist_ok=True)
        data["arcs"] = sorted(data.get("arcs", []), key=lambda a: a["chapter_start"])
        self._meta_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def put_arc_summary(self, a: ArcSummary) -> None:
        data = self._load_meta()
        data["arcs"] = [x for x in data.get("arcs", []) if x["arc_name"] != a.arc_name] \
            + [a.model_dump()]
        self._save_meta(data)

    def get_arc_summary(self, arc_name: str) -> ArcSummary | None:
        for raw in self._load_meta().get("arcs", []):
            if raw["arc_name"] == arc_name:
                return ArcSummary.model_validate(raw)
        return None

    def all_arc_summaries(self) -> list[ArcSummary]:
        return [ArcSummary.model_validate(raw) for raw in self._load_meta().get("arcs", [])]

    def put_book_digest(self, d: BookDigest) -> None:
        data = self._load_meta()
        data["book"] = d.model_dump()
        self._save_meta(data)

    def get_book_digest(self) -> BookDigest | None:
        raw = self._load_meta().get("book")
        return BookDigest.model_validate(raw) if raw else None


def detect_edited_chapters(proj: NovelProject, store: SummaryStore) -> list[int]:
    """Chapters whose prose file hash no longer matches the recorded
    prose_sha256 — i.e. manually edited outside the pipeline (spec §4.5/§5)."""
    edited: list[int] = []
    for path in sorted((proj.root / "chapters" / "_summaries").glob("[0-9][0-9][0-9].json")):
        cs = ChapterSummary.model_validate_json(path.read_text(encoding="utf-8"))
        chapter_file = proj.root / "chapters" / f"{cs.chapter_no:03d}.md"
        if not chapter_file.is_file() or not cs.prose_sha256:
            continue
        if sha256_text(chapter_file.read_text(encoding="utf-8")) != cs.prose_sha256:
            edited.append(cs.chapter_no)
    return edited
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_summaries.py -q && uv run mypy novel && uv run ruff check .`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add novel/store/summaries.py tests/test_summaries.py
git commit -m "feat(longform): SummaryStore — chapter/arc/book summaries + manual-edit hash detection"
```

---

### Task 4: extractor 章摘要 + 完整状态 prompt

**Files:**
- Modify: `novel/memory/extractor.py`（`EXTRACTOR_SYSTEM`、`_UpdatePayload`、`ChapterUpdates`、`extract_updates` 的 roster_block）
- Test: `tests/test_extractor.py`

**Interfaces:**
- Produces: `ChapterUpdates.chapter_summary: str = ""`（约 150–250 字本章摘要）；extractor 的 roster 携带每角色上一状态，prompt 要求输出完整新状态。
- Consumes: 无新依赖。

- [ ] **Step 1: Write the failing tests**

`tests/test_extractor.py` 追加（文件顶部已有 `FakeProvider`/`ModelConfig` import 的跟随现状；若无则补 `from novel.providers import FakeProvider, ModelConfig`）：

```python
def test_extraction_carries_chapter_summary_and_previous_state():
    from novel.memory.extractor import extract_updates
    from novel.models import Character, CharacterState

    captured: list[list[dict[str, object]]] = []

    class _Recording(FakeProvider):
        def complete_structured(self, messages, schema, cfg, *, seed=None):
            captured.append(messages)
            return super().complete_structured(messages, schema, cfg, seed=seed)

    chars = [Character(id="c1", slug="ara", name="Ara", role="protagonist", backstory="b",
                       motivation="m", arc="a",
                       state=CharacterState(emotional_state="doubt", location_end="tavern"))]
    provider = _Recording({
        "extractor": {
            "character_states": {"c1": {"emotional_state": "resolve", "physical_state": "",
                                         "knowledge_gained": [], "relationships_shifted": {},
                                         "location_end": "tower"}},
            "voice_samples": {}, "mannerisms_used": {}, "key_events": [],
            "threads_advanced": [], "new_information_revealed": [],
            "chapter_summary": "阿娜离开酒馆潜入钟塔。",
        }})
    upd = extract_updates(1, "正文。", chars, provider, ModelConfig("zhipu", "x"))
    assert upd.chapter_summary == "阿娜离开酒馆潜入钟塔。"
    # roster block carries the character's previous state for complete-state output
    system = str(captured[0][0]["content"])
    assert "previous_state" in system and '"emotional_state":"doubt"' in system.replace(" ", "")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_extractor.py -q`
Expected: FAIL — `AttributeError: 'ChapterUpdates' object has no attribute 'chapter_summary'`

- [ ] **Step 3: Implement**

`novel/memory/extractor.py`：

1. `EXTRACTOR_SYSTEM` 的 schema JSON 里 `"key_events"` 之前加一行：

```
  "chapter_summary": "150–250 unit plot summary of THIS chapter: what happened, who was involved, what changed",
```

2. `EXTRACTOR_SYSTEM` 的 `## Critical Rules` 追加两条（编号顺延）：

```
5. **Complete states, not deltas**: each `character_states` value must be the character's
   FULL state at the chapter's end — carry forward any `previous_state` fields still true.
6. **Summary discipline**: `chapter_summary` covers plot progression, involved characters
   and state changes; never a teaser or a list of foreshadows.
```

3. roster_block 携带上一状态（`extract_updates` 内）：

```python
    roster_block = "\n".join(
        f"- {c.id} ({c.name})\n  previous_state: {c.state.model_dump_json()}" for c in characters)
```

4. `_UpdatePayload` 与 `ChapterUpdates` 都加字段 `chapter_summary: str = ""`；`extract_updates` 构造 `ChapterUpdates(..., chapter_summary=payload.chapter_summary)`。

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_extractor.py tests/test_graph.py -q`
Expected: PASS（旧 dict fixture 缺 `chapter_summary` → 默认 `""`，向后兼容）

- [ ] **Step 5: Commit**

```bash
git add novel/memory/extractor.py tests/test_extractor.py
git commit -m "feat(longform): extractor emits chapter_summary and complete character states"
```

---

### Task 5: bible 治理 — 批量应用 / 压缩 / 已回收伏笔 / 尾读

**Files:**
- Modify: `novel/store/bible.py`
- Test: `tests/test_bible.py`

**Interfaces:**
- Produces:
  - `StoryBible.apply_chapter_updates(chapter_no: int, upd: ChapterUpdates, beats: list[ChapterBeat]) -> None`——每章**一次** canonical load-modify-save；events 追加；plants 注册 / payoffs 归档。
  - `StoryBible.list_events(last: int | None = None) -> list[Event]`（`last=N` 只读尾部 N 行）
  - 模块常量 `VOICE_SAMPLE_K = 10`（保留最早 1 条 + 最近 9 条）、`MANNERISMS_CAP = 8`（按 used_count 淘汰）
  - 已回收伏笔 append 到 `.meta/threads_resolved.jsonl`（`Foreshadow` JSON，status=PAID_OFF、payoff_ch=回收章号），并从 `bible/foreshadowing.json` 移除
- Consumes: `ChapterUpdates`（`novel.memory.extractor`）、`ChapterBeat`/`Mannerism`/`Character`（`novel.models`）。`store.bible → memory.extractor` 无环（extractor 不 import store）。

- [ ] **Step 1: Write the failing tests**

`tests/test_bible.py` 追加：

```python
def test_apply_chapter_updates_batches_canonical_writes(tmp_path):
    from novel.memory.extractor import ChapterUpdates
    from novel.models import ChapterBeat, CharacterState, KeyEvent
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    bible = StoryBible(proj)
    bible.upsert_character(Character(id="c1", slug="ara", name="Ara", role="protagonist",
                                     backstory="b", motivation="m", arc="a"))
    writes = {"n": 0}
    real_save = proj.save_canonical

    def counting_save(data):
        writes["n"] += 1
        real_save(data)

    proj.save_canonical = counting_save  # type: ignore[method-assign]
    beat = ChapterBeat(pov="Ara", setting="t", event="e", emotional_turn="d",
                       characters=["c1"], plants=["the bell"], payoffs=[])
    upd = ChapterUpdates(
        character_states={"c1": CharacterState(emotional_state="resolve", location_end="tower")},
        voice_samples={"c1": "drawl"}, mannerisms_used={"c1": ["taps table"]},
        key_events=[KeyEvent(event="bell rings", significance="pivot", affected_characters=["c1"])])
    bible.apply_chapter_updates(1, upd, [beat])
    c1 = bible.get_character("c1")
    assert c1.state.emotional_state == "resolve" and c1.last_updated_chapter == 1
    assert c1.voice_fingerprint["sample_1"] == "drawl"
    assert writes["n"] == 1            # ONE canonical write for the whole chapter
    assert any(e.id == "evt_1_1" for e in bible.list_events())
    assert any(f.description == "the bell" for f in bible.list_foreshadow())


def test_voice_compaction_keeps_earliest_and_recent_nine(tmp_path):
    from novel.memory.extractor import ChapterUpdates
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    bible = StoryBible(proj)
    bible.upsert_character(Character(id="c1", slug="a", name="A", role="p",
                                     backstory="b", motivation="m", arc="a"))
    for n in range(1, 16):   # 15 chapters of samples
        bible.apply_chapter_updates(n, ChapterUpdates(voice_samples={"c1": f"v{n}"}), [])
    vf = bible.get_character("c1").voice_fingerprint
    assert len(vf) == 10
    assert vf["sample_1"] == "v1"            # 定调样本保留
    assert vf["sample_15"] == "v15"          # 最近样本保留
    assert "sample_2" not in vf


def test_payoff_archives_to_resolved_jsonl(tmp_path):
    from novel.memory.extractor import ChapterUpdates
    from novel.models import ChapterBeat, ForeshadowStatus
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    bible = StoryBible(proj)
    bible.add_foreshadow(Foreshadow(id="fs-1", description="the bell", planted_ch=1))
    beat = ChapterBeat(pov="Ara", setting="t", event="e", emotional_turn="d",
                       characters=["c1"], payoffs=["the bell"])
    bible.apply_chapter_updates(9, ChapterUpdates(), [beat])
    assert bible.list_foreshadow() == []     # paid-off: gone from the open ledger
    resolved = (proj.root / ".meta" / "threads_resolved.jsonl").read_text(encoding="utf-8")
    assert '"status":"paid_off"' in resolved.replace(" ", "") and '"payoff_ch":9' in resolved


def test_list_events_tail_only(tmp_path):
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    bible = StoryBible(proj)
    for i in range(1, 11):
        bible.append_event(Event(id=f"e{i}", chapter=i, summary=f"s{i}"))
    tail = bible.list_events(last=3)
    assert [e.id for e in tail] == ["e8", "e9", "e10"]
    assert len(bible.list_events()) == 10
```

（若 `tests/test_bible.py` 尚未 import `NovelProject`/`StoryBible`/`Character`/`Event`，按需补 import。）

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_bible.py -q`
Expected: FAIL — `AttributeError: 'StoryBible' object has no attribute 'apply_chapter_updates'`

- [ ] **Step 3: Implement**

`novel/store/bible.py` 顶部 import 区追加：

```python
from novel.memory.extractor import ChapterUpdates
from novel.models import ChapterBeat, Mannerism
```

模块常量与压缩函数（`StoryBible` 类之前）：

```python
VOICE_SAMPLE_K = 10   # earliest 1 (定调) + most recent 9 per character
MANNERISMS_CAP = 8    # keep highest used_count


def _compact_voice(vf: dict[str, str]) -> dict[str, str]:
    if len(vf) <= VOICE_SAMPLE_K:
        return vf

    def ch_no(key: str) -> int:
        suffix = key.rsplit("_", 1)[-1]
        return int(suffix) if suffix.isdigit() else -1

    keys = sorted(vf, key=ch_no)
    keep = {keys[0]} | set(keys[-(VOICE_SAMPLE_K - 1):])
    return {k: vf[k] for k in sorted(keep, key=ch_no)}
```

`StoryBible` 内新增方法（放在 `# ---- events` 段之前）：

```python
    # ---- per-chapter batch application (spec §4.4) ----
    def apply_chapter_updates(self, chapter_no: int, upd: ChapterUpdates,
                              beats: list[ChapterBeat]) -> None:
        """All per-chapter state changes in ONE canonical load-modify-save
        (the old per-field path rewrote the whole file 3+ times per chapter)."""
        d = self._load()
        chars = {c["id"]: c for c in d.setdefault("characters", [])}
        for cid, st in upd.character_states.items():
            if cid in chars:
                obj = Character.model_validate(chars[cid])
                obj.state = st
                obj.last_updated_chapter = chapter_no
                chars[cid] = obj.model_dump()
        for cid, sample in upd.voice_samples.items():
            if cid in chars:
                obj = Character.model_validate(chars[cid])
                obj.voice_fingerprint[f"sample_{chapter_no}"] = sample
                obj.voice_fingerprint = _compact_voice(obj.voice_fingerprint)
                chars[cid] = obj.model_dump()
        for cid, man_list in upd.mannerisms_used.items():
            if cid not in chars:
                continue
            obj = Character.model_validate(chars[cid])
            for man in man_list:
                existing = next((m for m in obj.mannerisms if m.text == man), None)
                if existing:
                    existing.used_count += 1
                else:
                    obj.mannerisms.append(Mannerism(text=man, used_count=1))
            if len(obj.mannerisms) > MANNERISMS_CAP:
                obj.mannerisms = sorted(obj.mannerisms, key=lambda m: -m.used_count)[:MANNERISMS_CAP]
            chars[cid] = obj.model_dump()
        d["characters"] = list(chars.values())
        self._save(d)
        for i, ke in enumerate(upd.key_events):
            self.append_event(Event(
                id=f"evt_{chapter_no}_{i + 1}", chapter=chapter_no, summary=ke.event,
                characters=list(ke.affected_characters)))
        self._apply_plants_and_payoffs(chapter_no, beats)

    def _apply_plants_and_payoffs(self, chapter_no: int, beats: list[ChapterBeat]) -> None:
        path = self._mirror_dir / "foreshadowing.json"
        items = json.loads(path.read_text(encoding="utf-8") or "[]")
        resolved_path = self.proj.root / ".meta" / "threads_resolved.jsonl"
        resolved: list[str] = []
        for beat in beats:
            for plant in beat.plants:
                fid = f"plant-{plant}"
                if not any(i["id"] == fid for i in items):
                    items.append(Foreshadow(id=fid, description=plant,
                                            planted_ch=chapter_no).model_dump())
            for payoff in beat.payoffs:
                open_fs = [Foreshadow.model_validate(i) for i in items
                           if i.get("status", ForeshadowStatus.OPEN.value) != ForeshadowStatus.PAID_OFF.value
                           and (payoff in i.get("description", "") or i.get("description", "") in payoff)]
                if open_fs:
                    target = open_fs[0]
                    items = [i for i in items if i["id"] != target.id]
                    target.payoff_ch = chapter_no
                    target.status = ForeshadowStatus.PAID_OFF
                    resolved.append(target.model_dump_json())
        path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        if resolved:
            resolved_path.parent.mkdir(parents=True, exist_ok=True)
            with resolved_path.open("a", encoding="utf-8") as fh:
                for line in resolved:
                    fh.write(line + "\n")
```

import 区补 `ForeshadowStatus`（models import 列表加入）。`list_events` 替换为：

```python
    def list_events(self, last: int | None = None) -> list[Event]:
        path = self._mirror_dir / "events.jsonl"
        if not path.exists():
            return []
        if last is None:
            lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        else:
            from collections import deque
            with path.open(encoding="utf-8") as fh:
                lines = [ln for ln in deque(fh, maxlen=last) if ln.strip()]
        return [Event.model_validate_json(ln) for ln in lines]
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_bible.py tests/test_graph.py -q && uv run mypy novel`
Expected: PASS（旧 graph 路径未删，`test_voice_mannerisms_and_events_persist` 仍走旧逻辑通过）

- [ ] **Step 5: Commit**

```bash
git add novel/store/bible.py tests/test_bible.py
git commit -m "feat(longform): bible governance — batch chapter application, voice/mannerism caps, resolved-thread archive, tail event reads"
```

---

### Task 6: ArcPlanner / ArcDetailer agents

**Files:**
- Modify: `novel/agents/outliner.py`（文件末尾追加）
- Test: `tests/test_outliner_arc.py`

**Interfaces:**
- Produces:
  - `ArcPlannerAgent(Agent[tuple[Concept, World, list[Character], int], ArcPlan])`，`name = "arc_planner"`（模型槽位 `outliner`）
  - `ArcDetailInput` dataclass：`skeleton: ArcSkeleton`、`concept: Concept`、`world: World`、`characters: list[Character]`、`prev_arc: ArcSummary | None`、`open_foreshadows: list[Foreshadow]`、`recent_summaries: list[ChapterSummary]`、`next_chapter_no: int`
  - `ArcDetailerAgent(Agent[ArcDetailInput, Arc])`，`name = "arc_detailer"`（模型槽位 `outliner`）
- Consumes: Task 1 的 `ArcSkeleton` / `ArcPlan` / `ArcSummary` / `ChapterSummary`。

- [ ] **Step 1: Write the failing tests**

`tests/test_outliner_arc.py`：

```python
from novel.agents.outliner import ArcDetailInput, ArcDetailerAgent, ArcPlannerAgent
from novel.models import ArcSkeleton, Character, ChapterSummary, Concept, Foreshadow, World
from novel.providers import FakeProvider, ModelConfig

_C = Concept(logline="L", genre="g", tone="t", target_length_words=100000, audience="a")
_W = World(setting="city")
_R = [Character(id="c1", slug="ara", name="Ara", role="protagonist", backstory="b",
                motivation="m", arc="a")]
_CFG = ModelConfig("zhipu", "x")


def test_arc_planner_builds_messages_with_target_chapters():
    provider = FakeProvider({"arc_planner": {
        "arcs": [{"arc_name": "卷一", "chapter_start": 1, "chapter_end": 40, "premise": "p"}],
        "planned_total_chapters": 120}})
    plan = ArcPlannerAgent(provider, _CFG).run((_C, _W, _R, 120))
    assert plan.planned_total_chapters == 120
    assert plan.arcs[0].arc_name == "卷一"


def test_arc_detailer_input_contains_next_chapter_no_and_summaries():
    provider = FakeProvider({"arc_detailer": {
        "arc_name": "卷二", "chapters": [
            {"chapter_no": 41, "chapter_title": "T41",
             "beats": [{"pov": "c1", "setting": "s", "event": "e",
                        "emotional_turn": "d", "characters": ["c1"]}]}]}})
    arc = ArcDetailerAgent(provider, _CFG).run(ArcDetailInput(
        skeleton=ArcSkeleton(arc_name="卷二", chapter_start=41, chapter_end=80, premise="p2"),
        concept=_C, world=_W, characters=_R, prev_arc=None,
        open_foreshadows=[Foreshadow(id="fs-1", description="the bell", planted_ch=3)],
        recent_summaries=[ChapterSummary(chapter_no=40, summary="卷一收尾")],
        next_chapter_no=41))
    assert arc.arc_name == "卷二" and arc.chapters[0].chapter_no == 41
    # the agent's user message must carry the runtime numbering anchor (spec §4.3)
    msgs = ArcDetailerAgent(FakeProvider({}), _CFG).build_messages(ArcDetailInput(
        skeleton=ArcSkeleton(arc_name="卷二", chapter_start=41, chapter_end=80, premise="p2"),
        concept=_C, world=_W, characters=_R, prev_arc=None,
        open_foreshadows=[], recent_summaries=[], next_chapter_no=55))
    user = str(msgs[-1]["content"])
    assert "55" in user and "卷一收尾" not in user   # next_chapter_no present; summaries injected via input build
```

（最后一条断言只校验 next_chapter_no 出现；recent_summaries 的注入在实现里由空列表给出，非空场景由 `test_arc_detailer_includes_recent_summaries` 覆盖：）

```python
def test_arc_detailer_includes_recent_summaries():
    detailer = ArcDetailerAgent(FakeProvider({}), _CFG)
    msgs = detailer.build_messages(ArcDetailInput(
        skeleton=ArcSkeleton(arc_name="卷二", chapter_start=41, chapter_end=80, premise="p2"),
        concept=_C, world=_W, characters=_R, prev_arc=None,
        open_foreshadows=[Foreshadow(id="fs-1", description="the bell", planted_ch=3)],
        recent_summaries=[ChapterSummary(chapter_no=40, summary="卷一收尾")],
        next_chapter_no=41))
    user = str(msgs[-1]["content"])
    assert "卷一收尾" in user and "the bell" in user
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_outliner_arc.py -q`
Expected: FAIL — `ImportError: cannot import name 'ArcPlannerAgent'`

- [ ] **Step 3: Implement**

`novel/agents/outliner.py` 末尾追加（import 区补 `Arc, ArcPlan, ArcSkeleton, ArcSummary, ChapterSummary`——`Arc`/`Outline` 已有则不重复）：

```python
ARC_PLANNER_SYSTEM = """\
You are a story architect planning a LONG novel (hundreds of chapters) volume by volume.

## Task
Produce a volume skeleton plan (卷级骨架): a list of arcs covering the WHOLE book.

## Output Schema (strict JSON)
{
  "arcs": [
    {"arc_name": "卷一 – ...", "chapter_start": 1, "chapter_end": 40, "premise": "one-sentence arc promise"}
  ],
  "planned_total_chapters": 120
}

## Critical Rules
1. The arcs are CONSECUTIVE and their ranges sum to exactly the target chapter count.
2. 3–8 arcs for a long novel; each arc 20–60 chapters.
3. Each premise must escalate stakes beyond the previous arc.
4. chapter_start/chapter_end are PLANNING references only — runtime numbering is recomputed.

## Roster (authoritative character ids)
{roster_block}

## Output
Return ONLY the JSON object."""

ARC_PLANNER_USER = """\
<concept>
{concept_json}
</concept>

<world>
{world_json}
</world>

<characters>
{roster_block}
</characters>

<target_chapters>
{target_chapters}
</target_chapters>"""


class ArcPlannerAgent(Agent[tuple[Concept, World, list[Character], int], ArcPlan]):
    name = "arc_planner"   # message tag; model slot stays "outliner"
    output_schema = ArcPlan

    def build_messages(self, inputs: tuple[Concept, World, list[Character], int]) -> list[dict]:
        concept, world, chars, target = inputs
        roster_block = "\n".join(f"- {c.id} ({c.name}): {c.role}" for c in chars)
        return [
            {"role": "system", "agent": self.name,
             "content": ARC_PLANNER_SYSTEM.replace("{roster_block}", roster_block)},
            {"role": "user", "agent": self.name,
             "content": ARC_PLANNER_USER.format(
                 concept_json=concept.model_dump_json(),
                 world_json=world.model_dump_json(),
                 roster_block=roster_block,
                 target_chapters=target)},
        ]


ARC_DETAILER_SYSTEM = """\
You are a story architect detailing ONE volume (卷) of an existing long novel.

## Task
Given the volume skeleton, produce this volume's chapters and beats.

## Output Schema (strict JSON)
{
  "arc_name": "…",
  "chapters": [
    {
      "chapter_no": 41,
      "chapter_title": "",
      "beats": [
        {"beat_id": "", "pov": "<character_id>", "setting": "<location>", "event": "1–2 sentences",
         "emotional_turn": "X → Y", "characters": ["<character_id>"], "plants": [], "payoffs": []}
      ]
    }
  ]
}

## Critical Rules
1. **Numbering is HARD**: number chapters consecutively from {next_chapter_no}. Ignore the
   skeleton's chapter_start/chapter_end as absolute positions; its length is a SOFT target
   (you may deviate by a few chapters).
2. **ID discipline**: pov and characters entries MUST be roster character ids.
3. **Continuity**: honour the previous-arc summary and recent chapter summaries; pay off or
   advance the open foreshadows when natural; never restate events already summarised.
4. Each chapter has 1–4 beats; protagonist POV ≥ 60 % of beats.

## Roster (authoritative character ids)
{roster_block}

## Output
Return ONLY the JSON object."""

ARC_DETAILER_USER = """\
<volume_skeleton arc_name="{arc_name}" soft_chapters="{soft_n}">
{premise}
</volume_skeleton>

<concept>
{concept_json}
</concept>

<world>
{world_json}
</world>

<characters>
{roster_block}
</characters>

<previous_arc_summary>
{prev_arc_block}
</previous_arc_summary>

<recent_chapter_summaries>
{summaries_block}
</recent_chapter_summaries>

<open_foreshadows>
{foreshadows_block}
</open_foreshadows>

<next_chapter_no>
{next_chapter_no}
</next_chapter_no>

Detail this volume's chapters, numbered from {next_chapter_no}."""


@dataclass
class ArcDetailInput:
    skeleton: ArcSkeleton
    concept: Concept
    world: World
    characters: list[Character]
    prev_arc: ArcSummary | None
    open_foreshadows: list[Foreshadow]
    recent_summaries: list[ChapterSummary]
    next_chapter_no: int


class ArcDetailerAgent(Agent[ArcDetailInput, Arc]):
    name = "arc_detailer"   # message tag; model slot stays "outliner"
    output_schema = Arc

    def build_messages(self, inputs: ArcDetailInput) -> list[dict]:
        s = inputs.skeleton
        roster_block = "\n".join(f"- {c.id} ({c.name}): {c.role}" for c in inputs.characters)
        prev_arc_block = inputs.prev_arc.summary if inputs.prev_arc else "(none — first volume)"
        summaries_block = "\n".join(f"- ch{cs.chapter_no}: {cs.summary}"
                                    for cs in inputs.recent_summaries) or "(none)"
        foreshadows_block = "\n".join(f"- {f.id}: {f.description}"
                                      for f in inputs.open_foreshadows) or "(none)"
        soft_n = max(1, s.chapter_end - s.chapter_start + 1)
        system = (ARC_DETAILER_SYSTEM
                  .replace("{next_chapter_no}", str(inputs.next_chapter_no))
                  .replace("{roster_block}", roster_block))
        user = ARC_DETAILER_USER.format(
            arc_name=s.arc_name, soft_n=soft_n, premise=s.premise or "(no premise)",
            concept_json=inputs.concept.model_dump_json(),
            world_json=inputs.world.model_dump_json(),
            roster_block=roster_block,
            prev_arc_block=prev_arc_block,
            summaries_block=summaries_block,
            foreshadows_block=foreshadows_block,
            next_chapter_no=inputs.next_chapter_no)
        return [
            {"role": "system", "agent": self.name, "content": system},
            {"role": "user", "agent": self.name, "content": user},
        ]
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_outliner_arc.py tests/test_outliner_extend.py -q && uv run mypy novel`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add novel/agents/outliner.py tests/test_outliner_arc.py
git commit -m "feat(longform): ArcPlannerAgent + ArcDetailerAgent (two-phase rolling outline)"
```

---

### Task 7: summarizer（章补生成 / 卷摘要 / 全书梗概）

**Files:**
- Create: `novel/memory/summarizer.py`
- Test: `tests/test_summarizer.py`

**Interfaces:**
- Produces（全部带 ValidationError 重试，与 `extract_updates` 同款契约；模型槽位 `extractor`）:
  - `summarize_chapter(chapter_no: int, prose: str, arc_name: str, provider: ModelProvider, cfg: ModelConfig) -> ChapterSummary`（tag `summarizer`；懒回填专用，主路径摘要由 extractor 顺手产出）
  - `summarize_arc(arc_name: str, chapter_start: int, chapter_end: int, chapter_summaries: list[ChapterSummary], prev: ArcSummary | None, provider, cfg) -> ArcSummary`（tag `summarizer`）
  - `digest_book(arc_summaries: list[ArcSummary], chapter_count: int, current_arc: str, provider, cfg) -> BookDigest`（tag `digestor`）

- [ ] **Step 1: Write the failing tests**

`tests/test_summarizer.py`：

```python
from novel.memory.summarizer import digest_book, summarize_arc, summarize_chapter
from novel.models import ArcSummary, ChapterSummary
from novel.providers import FakeProvider, ModelConfig

_CFG = ModelConfig("zhipu", "x")


def test_summarize_chapter_returns_schema_with_no_sha():
    provider = FakeProvider({"summarizer": {
        "chapter_no": 7, "arc_name": "卷一", "summary": "主角潜入钟塔。",
        "characters_involved": ["c1"], "threads_advanced": [], "prose_sha256": ""}})
    cs = summarize_chapter(7, "正文。", "卷一", provider, _CFG)
    assert cs.summary == "主角潜入钟塔。" and cs.prose_sha256 == ""


def test_summarize_arc_passes_prev_and_chapter_summaries():
    captured: list[list[dict[str, object]]] = []

    class _Recording(FakeProvider):
        def complete_structured(self, messages, schema, cfg, *, seed=None):
            captured.append(messages)
            return super().complete_structured(messages, schema, cfg, seed=seed)

    provider = _Recording({"summarizer": {
        "arc_name": "卷一", "chapter_start": 1, "chapter_end": 30,
        "summary": "第一卷：立约与背叛。", "major_developments": ["a", "b"]}})
    prev = ArcSummary(arc_name="卷零", chapter_start=1, chapter_end=0, summary="序")
    a = summarize_arc("卷一", 1, 30,
                      [ChapterSummary(chapter_no=n, summary=f"s{n}") for n in (1, 30)],
                      prev, provider, _CFG)
    assert a.summary == "第一卷：立约与背叛。"
    user = str(captured[0][-1]["content"])
    assert "s1" in user and "s30" in user and "卷零" in user


def test_digest_book_separate_tag():
    provider = FakeProvider({"digestor": {
        "chapter_count": 60, "current_arc": "卷二", "summary": "全书梗概。"}})
    d = digest_book([ArcSummary(arc_name="卷一", chapter_start=1, chapter_end=30, summary="a")],
                    60, "卷二", provider, _CFG)
    assert d.summary == "全书梗概。" and d.chapter_count == 60
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_summarizer.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'novel.memory.summarizer'`

- [ ] **Step 3: Implement**

`novel/memory/summarizer.py`：

```python
"""Summary-tier LLM calls (spec §4.1): chapter backfill (lazy retry), arc
summaries, whole-book digest. Cheap by construction — inputs are already
bounded summaries, and arc/digest calls happen once per ~20-40 chapters."""
from __future__ import annotations

from pydantic import ValidationError

from novel.config import ModelConfig
from novel.models import ArcSummary, BookDigest, ChapterSummary
from novel.providers import ModelProvider

MAX_RETRIES = 2

_CHAPTER_SYSTEM = """\
You are a story archivist. Summarise the given chapter in 150–250 units (Chinese characters \
or English words): what happened, who was involved, what changed. No teaser language, no \
foreshadow lists. Return ONLY a JSON object matching the ChapterSummary schema \
(chapter_no, arc_name, summary, characters_involved, threads_advanced)."""

_ARC_SYSTEM = """\
You are a story archivist. Given one volume's chapter summaries and the previous volume's \
summary, write a 200–300 unit arc summary: the volume's throughline, major developments \
(3–6 bullets), and the state it leaves the story in. Return ONLY a JSON object matching \
the ArcSummary schema (arc_name, chapter_start, chapter_end, summary, major_developments)."""

_DIGEST_SYSTEM = """\
You are a story archivist. Given ALL volume summaries of a long novel so far, write a \
150–250 unit whole-book digest: premise, where the story stands now, the central tension. \
Return ONLY a JSON object matching the BookDigest schema (chapter_count, current_arc, summary)."""


def _run_structured(system: str, user: str, schema: type, tag: str,
                    provider: ModelProvider, cfg: ModelConfig):
    messages: list[dict[str, object]] = [
        {"role": "system", "agent": tag, "content": system},
        {"role": "user", "agent": tag, "content": user},
    ]
    last_err: ValidationError | None = None
    for _attempt in range(MAX_RETRIES + 1):
        try:
            return provider.complete_structured(messages, schema, cfg)
        except ValidationError as e:
            last_err = e
            messages = messages + [
                {"role": "assistant", "agent": tag, "content": "<invalid output>"},
                {"role": "user", "agent": tag,
                 "content": f"Your output failed validation: {e}. Fix the JSON and return "
                            "ONLY the valid JSON object."},
            ]
    assert last_err is not None
    raise last_err


def summarize_chapter(chapter_no: int, prose: str, arc_name: str,
                      provider: ModelProvider, cfg: ModelConfig) -> ChapterSummary:
    cs = _run_structured(
        _CHAPTER_SYSTEM,
        f"<arc_name>{arc_name}</arc_name>\n<chapter_no>{chapter_no}</chapter_no>\n"
        f"<prose>\n{prose}\n</prose>",
        ChapterSummary, "summarizer", provider, cfg)
    assert isinstance(cs, ChapterSummary)
    cs.chapter_no = chapter_no
    cs.arc_name = arc_name
    return cs


def summarize_arc(arc_name: str, chapter_start: int, chapter_end: int,
                  chapter_summaries: list[ChapterSummary], prev: ArcSummary | None,
                  provider: ModelProvider, cfg: ModelConfig) -> ArcSummary:
    summaries_block = "\n".join(f"- ch{cs.chapter_no}: {cs.summary}" for cs in chapter_summaries)
    prev_block = f"{prev.arc_name}: {prev.summary}" if prev else "(none)"
    a = _run_structured(
        _ARC_SYSTEM,
        f"<arc_name>{arc_name}</arc_name>\n<range>{chapter_start}-{chapter_end}</range>\n"
        f"<previous_volume>\n{prev_block}\n</previous_volume>\n"
        f"<chapter_summaries>\n{summaries_block}\n</chapter_summaries>",
        ArcSummary, "summarizer", provider, cfg)
    assert isinstance(a, ArcSummary)
    a.arc_name = arc_name
    a.chapter_start = chapter_start
    a.chapter_end = chapter_end
    return a


def digest_book(arc_summaries: list[ArcSummary], chapter_count: int, current_arc: str,
                provider: ModelProvider, cfg: ModelConfig) -> BookDigest:
    arcs_block = "\n".join(f"- {a.arc_name} (ch{a.chapter_start}-{a.chapter_end}): {a.summary}"
                           for a in arc_summaries)
    d = _run_structured(
        _DIGEST_SYSTEM,
        f"<volume_summaries>\n{arcs_block}\n</volume_summaries>\n"
        f"<chapter_count>{chapter_count}</chapter_count>\n<current_arc>{current_arc}</current_arc>",
        BookDigest, "digestor", provider, cfg)
    assert isinstance(d, BookDigest)
    d.chapter_count = chapter_count
    d.current_arc = current_arc
    return d
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_summarizer.py -q && uv run mypy novel && uv run ruff check .`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add novel/memory/summarizer.py tests/test_summarizer.py
git commit -m "feat(longform): summarizer — chapter backfill, arc summary, book digest"
```

---

### Task 8: 组装器新阶梯与截断

**Files:**
- Modify: `novel/memory/assembler.py`（重写 `assemble_context` 及块构建）
- Test: `tests/test_assembler.py`（既有测试改新签名 + 新测试）

**Interfaces:**
- Produces:
  - `assemble_context(beats: list[ChapterBeat], bible, vector, proj, token_budget: int, chapter_no: int | None = None, *, arc_summary: str = "", recent_summaries: list[str] | None = None, book_digest: str = "", target_note: str = "") -> AssembledContext`
  - 阶梯（高→低，spec §4.2）：`target_note`(核心) → `beat`(核心) → `prev_ending`(核心) → `arc_summary` → `recent_summaries` → `book_digest` → `characters` → `threads` → `world` → `style_notes` → `weak_spots` → `events`(降级 fallback) → `recency`
  - 非核心块超预算**截断**（尾部加 `"\n(truncated)"`），`AssembledContext.truncated: list[str]` 记录；核心块永不截断
  - `continuity_compact_view(beats, bible, arc_summary: str, recent_summaries: list[str], book_digest: str) -> str`——continuity 紧凑视图（Task 10 使用）
  - 常量 `RECENT_SUMMARY_K = 5`、`OPEN_THREADS_M = 10`（定义在 assembler.py，供 graph 引用）
  - `_character_block` 精简：state + 最近 1 条 voice 样本 + **used_count 最低的 3 条 mannerisms**（沿用现状「建议低频」语义，既有测试依赖）
- Consumes: `bible.list_events(last=3)`（Task 5）。
- 破坏性变更：`beat: ChapterBeat` → `beats: list[ChapterBeat]`；`tests/test_assembler.py` 全部调用点 `beat=beat` → `beats=[beat]`。

- [ ] **Step 1: Write the failing tests**

`tests/test_assembler.py`：先把 `_seed` 返回值用法统一改为 `beats=[beat]`（6 个既有测试函数的全部调用点），再追加：

```python
def test_hierarchy_blocks_rank_above_world_and_characters(tmp_path):
    proj, b, vm, beat = _seed(tmp_path)
    from novel.store.summaries import SummaryStore
    from novel.models import ChapterSummary
    SummaryStore(proj).put_chapter_summary(ChapterSummary(chapter_no=1, summary="上一章摘要"))
    ctx = assemble_context(beats=[beat], bible=b, vector=vm, proj=proj, token_budget=20000,
                           chapter_no=2, arc_summary="本卷至今主线",
                           recent_summaries=["ch1: 上一章摘要"],
                           book_digest="全书梗概", target_note="[Target length] 目标约 2500 字")
    assert "本卷至今主线" in ctx.text and "全书梗概" in ctx.text and "上一章摘要" in ctx.text
    assert "Target length" in ctx.text
    # hierarchy blocks rank ABOVE world/characters: they appear earlier in the text
    assert ctx.text.index("本卷至今主线") < ctx.text.index("[World]")


def test_overflow_truncates_instead_of_dropping(tmp_path):
    proj, b, vm, beat = _seed(tmp_path)
    ctx = assemble_context(beats=[beat], bible=b, vector=vm, proj=proj, token_budget=1200,
                           chapter_no=1, arc_summary="卷摘" * 400, book_digest="梗概" * 400)
    # beat (core) still intact; some low block got truncated, not silently dropped
    assert "meet" in ctx.text
    assert ctx.truncated  # at least one block was cut with a marker
    assert "(truncated)" in ctx.text


def test_threads_capped_at_ten_with_beat_mention_priority(tmp_path):
    proj, b, vm, beat = _seed(tmp_path)
    for i in range(15):
        b.add_foreshadow(Foreshadow(id=f"fs-{i}", description=f"伏笔{i}", planted_ch=i + 1))
    b.add_foreshadow(Foreshadow(id="fs-KEY", description="meet", planted_ch=99))
    ctx = assemble_context(beats=[beat], bible=b, vector=vm, proj=proj, token_budget=20000)
    threads_section = ctx.text.split("[Threads]")[1]
    assert "伏笔14" not in threads_section            # capped at 10
    assert "meet (planted ch99)" in threads_section   # beat-mentioned first
    assert "more open threads omitted" in threads_section


def test_continuity_compact_view_contains_hierarchy_not_world(tmp_path):
    from novel.memory.assembler import continuity_compact_view
    proj, b, vm, beat = _seed(tmp_path)
    view = continuity_compact_view(beats=[beat], bible=b, arc_summary="本卷至今主线",
                                   recent_summaries=["ch1: 上一章摘要"], book_digest="全书梗概")
    assert "本卷至今主线" in view and "Ara" in view and "[World]" not in view
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_assembler.py -q`
Expected: FAIL — `TypeError: assemble_context() got an unexpected keyword argument 'beats'`

- [ ] **Step 3: Implement**

`novel/memory/assembler.py` 重写核心部分（保留 `PREV_ENDING_CHARS`、`prev_ending_block`、`style_directives_block`、`weak_spots_block`、Task 2 的 `estimate_tokens`）：

```python
RECENT_SUMMARY_K = 5    # recent chapter summaries injected into writer context
OPEN_THREADS_M = 10     # max open foreshadow lines in context
_TRUNCATION_MARKER = "\n(truncated)"
```

`AssembledContext` 增加字段 `truncated: list[str] = field(default_factory=list)`。

`_character_block` 改为 beats 签名 + 精简角色卡：

```python
def _character_block(beats: list[ChapterBeat], bible: StoryBible) -> str:
    seen: list[str] = []
    for beat in beats:
        for cid in beat.characters:
            if cid not in seen:
                seen.append(cid)
    lines = []
    for cid in seen:
        ch = bible.get_character(cid)
        if not ch:
            continue
        last_voice = ""
        if ch.voice_fingerprint:
            def _no(key: str) -> int:
                s = key.rsplit("_", 1)[-1]
                return int(s) if s.isdigit() else -1
            last_key = max(ch.voice_fingerprint, key=_no)
            last_voice = ch.voice_fingerprint[last_key]
        mans = sorted(ch.mannerisms, key=lambda m: m.used_count)[:3]  # suggest low-frequency
        lines.append(
            f"[Character {ch.name}] role={ch.role}; state={ch.state.model_dump_json()}; "
            f"voice={last_voice}; suggested_mannerisms="
            f"{[m.text for m in mans]}; last_updated_chapter={ch.last_updated_chapter}"
        )
    return "\n".join(lines)
```

新增 threads 块：

```python
def threads_block(beats: list[ChapterBeat], bible: StoryBible, cap: int = OPEN_THREADS_M) -> str:
    open_fs = [f for f in bible.list_foreshadow()
               if f.status != ForeshadowStatus.PAID_OFF]
    if not open_fs:
        return ""
    beat_text = " ".join([*(b.event for b in beats), *(p for b in beats for p in b.plants),
                          *(p for b in beats for p in b.payoffs), *(b.characters for b in beats)])
    open_fs.sort(key=lambda f: (0 if (f.description and f.description in beat_text) else 1,
                                f.planted_ch if f.planted_ch is not None else 0))
    selected = open_fs[:cap]
    lines = [f"- {f.description} (planted ch{f.planted_ch})" for f in selected]
    if len(open_fs) > cap:
        lines.append(f"- (+{len(open_fs) - cap} more open threads omitted)")
    return "[Threads — open foreshadowing]\n" + "\n".join(lines)
```

`assemble_context` 重写：

```python
def assemble_context(
    beats: list[ChapterBeat], bible: StoryBible, vector: VectorMemory, proj: NovelProject,
    token_budget: int, chapter_no: int | None = None, *,
    arc_summary: str = "", recent_summaries: list[str] | None = None,
    book_digest: str = "", target_note: str = "",
) -> AssembledContext:
    beat_block = "[Beats — cover in order]\n" + "\n".join(
        f"{i + 1}. pov={b.pov}; setting={b.setting}; event={b.event}; "
        f"turn={b.emotional_turn}; plants={b.plants}; payoffs={b.payoffs}"
        for i, b in enumerate(beats))
    char_block = _character_block(beats, bible)
    world = bible.get_world()
    world_block = f"[World] {world.model_dump_json() if world else ''}"
    recency_block = "\n".join(vector.retrieve(beats[0].event, k=2)) if beats[0].event else ""
    events_block = "\n".join(e.model_dump_json() for e in bible.list_events(last=3))
    threads = threads_block(beats, bible)
    notes = WritingNotes(proj)
    prev_block = prev_ending_block(proj, chapter_no)
    style_block = style_directives_block(notes)
    weak_block = weak_spots_block(notes)
    arc_block = f"[Arc summary — current volume so far]\n{arc_summary}" if arc_summary else ""
    recent_block = ("[Recent chapter summaries — what happened lately]\n"
                    + "\n".join(f"- {line}" for line in (recent_summaries or []))
                    ) if recent_summaries else ""
    digest_block = f"[Book digest — whole story so far]\n{book_digest}" if book_digest else ""

    # priority ladder (spec §4.2): core never truncated; lower blocks truncated, not dropped
    candidates: list[tuple[str, str, bool]] = [
        ("target_note", target_note, True),
        ("beat", beat_block, True),
        ("prev_ending", prev_block, True),
        ("arc_summary", arc_block, False),
        ("recent_summaries", recent_block, False),
        ("book_digest", digest_block, False),
        ("characters", char_block, False),
        ("threads", threads, False),
        ("world", world_block, False),
        ("style_notes", style_block, False),
        ("weak_spots", weak_block, False),
        ("events", events_block, False),
        ("recency", recency_block, False),
    ]
    ctx = AssembledContext()
    for name, block, core in candidates:
        if not block:
            continue
        cost = estimate_tokens(block)
        if ctx.tokens + cost <= token_budget:
            ctx.blocks.append(block)
            ctx.tokens += cost
            continue
        if core:
            ctx.blocks.append(block)   # core always ships, even over budget
            ctx.tokens += cost
            continue
        remaining = token_budget - ctx.tokens
        if remaining <= 1:
            ctx.dropped.append(name)
            continue
        # worst case is all-CJK at 1.5 tokens/char → chars = remaining/1.5 (marker margin: -10)
        max_chars = max(0, int(remaining / 1.5) - 10)
        cut = block[:max_chars] + _TRUNCATION_MARKER
        cut_cost = estimate_tokens(cut)
        if cut_cost <= remaining:
            ctx.blocks.append(cut)
            ctx.tokens += cut_cost
            ctx.truncated.append(name)
        else:
            ctx.dropped.append(name)
    return ctx
```

文件末尾追加：

```python
def continuity_compact_view(beats: list[ChapterBeat], bible: StoryBible, arc_summary: str,
                            recent_summaries: list[str], book_digest: str) -> str:
    """Compact continuity reference (spec §4.5): replaces the whole canonical
    JSON the continuity agent used to receive — the single largest token waste
    at 100+ chapter scale."""
    parts = [p for p in [
        _character_block(beats, bible),
        threads_block(beats, bible),
        f"[Arc summary]\n{arc_summary}" if arc_summary else "",
        "[Recent chapter summaries]\n" + "\n".join(f"- {l}" for l in recent_summaries)
        if recent_summaries else "",
        f"[Book digest]\n{book_digest}" if book_digest else "",
    ] if p]
    return "\n\n".join(parts)
```

同步更新 `tests/test_assembler.py` 既有 6 个测试的调用签名（`beat=beat` → `beats=[beat]`；断言不变）。

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_assembler.py -q && uv run mypy novel && uv run ruff check .`
Expected: PASS（`test_graph.py` 此刻仍传旧签名会失败——`assemble_context` 调用在 graph，Task 10 修复；本步只跑 assembler 测试。注意：**不要**在本任务跑全量 pytest）

- [ ] **Step 5: Commit**

```bash
git add novel/memory/assembler.py tests/test_assembler.py
git commit -m "feat(longform): assembler priority ladder with truncation, thread cap, compact character cards, continuity compact view"
```

---

### Task 9: writer 提示词 — 全 beats + 目标长度参数化

**Files:**
- Modify: `novel/agents/writer.py`（`WRITER_SYSTEM`）
- Test: `tests/test_agents_gen.py`

**Interfaces:**
- Produces: `WRITER_SYSTEM` 引用 `[Beats]` / `[Arc summary]` / `[Recent chapter summaries]` / `[Book digest]` / `[Target length]` 块；不再含硬编码 "1,800–3,200 words"。
- 目标长度由 graph 组装的 `[Target length]` 核心块传入（Task 10）。

- [ ] **Step 1: Write the failing test**

`tests/test_agents_gen.py` 追加：

```python
def test_writer_prompt_references_ladder_blocks_and_no_hardcoded_length():
    from novel.agents.writer import WRITER_SYSTEM
    assert "1,800" not in WRITER_SYSTEM
    for marker in ("[Beats]", "[Arc summary]", "[Recent chapter summaries]",
                   "[Book digest]", "[Target length]"):
        assert marker in WRITER_SYSTEM
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_agents_gen.py -q`
Expected: FAIL — `AssertionError`（旧提示词含 "1,800–3,200"）

- [ ] **Step 3: Implement**

`WRITER_SYSTEM` 中 `## Context Blocks` 段替换为：

```
## Context Blocks (provided in user message)
[Target length] → the chapter's target length; hit it within ±20 %
[Beats] → the beat(s) to dramatise, in order — cover every one
[Previous chapter ending] → continue style, POV and plot seamlessly
[Arc summary] → where the current volume stands; stay on its throughline
[Recent chapter summaries] → what happened lately; do not contradict
[Book digest] → the whole story so far; do not contradict
[Characters] → relevant character sheets
[World] → setting rules & constraints to honour
[Threads] → open foreshadowing threads
[Events] → recent events (fallback when summaries are missing)
[REWRITE NOTES] → (if present) specific criticisms to address in this revision
```

`## Constraints` 中的长度行 `- Target length: 1,800–3,200 words unless the beat demands otherwise.` 替换为：

```
- Target length: follow the [Target length] block (roughly 1,800–3,200 words when absent).
```

`## Craft Directives` 的 Beat fidelity 行改为覆盖全部 beats：`Every beat's \`event\` in [Beats] must occur, in order.`

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_agents_gen.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add novel/agents/writer.py tests/test_agents_gen.py
git commit -m "feat(longform): writer prompt — all beats in order + parameterized target length"
```

---

### Task 10: graph 核心整合 — 摘要写入 / 批量应用 / continuity 紧凑 / 懒回填 / 全 beats

**Files:**
- Modify: `novel/graph.py`（generation 循环重写）
- Test: `tests/test_graph.py`

**Interfaces:**
- Produces: `run_full_pipeline` 新增关键字参数（全部有默认值，既有调用零改动可跑）：
  `planned_total: int | None = None`、`gate_every_n: int = 1`、`language: str = "en"`、`chapter_target_length: int = 2500`、`arc_lookahead: int = 5`
- Consumes: Task 3 `SummaryStore`/`sha256_text`/`detect_edited_chapters`、Task 4 `ChapterUpdates.chapter_summary`、Task 5 `apply_chapter_updates`、Task 7 `summarize_chapter`、Task 8 `assemble_context(beats=...)`/`continuity_compact_view`。
- 本任务**不含**自动续纲与卷摘要（Task 12）、gate-every-N 接线与 planned_total 事件与哈希警告（Task 11）——循环结构一次到位，后续任务只做增量插入。

- [ ] **Step 1: Write the failing tests**

`tests/test_graph.py` 追加（复用文件内已有的 `_cfg_map`、`_one_chapter_setup`、`_RecordingWriterProvider`）：

```python
def _two_chapter_arc_setup(tmp_path):
    proj, bible, vector, concept, beat, _outline, chars = _one_chapter_setup(tmp_path)
    outline = Outline(arcs=[Arc(arc_name="卷一", chapters=[
        ChapterOutline(chapter_no=i, chapter_title=f"T{i}", beats=[ChapterBeat(
            pov="Ara", setting="t", event=f"event-{i}", emotional_turn="d",
            characters=["c1"])]) for i in (1, 2)])])
    passing = ReviewScore(artifact_type="chapter", overall=90,
                          scores={"beat_adherence": DimensionScore(score=90, critique="ok")})
    provider = _RecordingWriterProvider(responses={
        "strategist": concept, "worldbuilder": World(setting="city"), "character": chars,
        "outliner": outline, "writer": "Chapter prose text.", "continuity": "[]",
        "editor": "Chapter prose text.", "scorer": passing,
        "extractor": {"character_states": {}, "voice_samples": {}, "mannerisms_used": {},
                      "key_events": [], "threads_advanced": [], "new_information_revealed": [],
                      "chapter_summary": "第二章摘要。"}})
    return proj, bible, vector, provider


def test_chapter_summaries_written_with_sha(tmp_path):
    from novel.store.summaries import SummaryStore
    proj, bible, vector, provider = _two_chapter_arc_setup(tmp_path)
    state = run_full_pipeline(provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
                              proj=proj, premise="a thief", target_chapters=2)
    assert state.error is None
    store = SummaryStore(proj)
    cs2 = store.get_chapter_summary(2)
    assert cs2.summary == "第二章摘要。" and cs2.arc_name == "卷一"
    assert cs2.prose_sha256 == __import__("hashlib").sha256(
        "Chapter prose text.".encode()).hexdigest()


def test_writer_receives_all_beats_and_target_note(tmp_path):
    proj, bible, vector, provider = _two_chapter_arc_setup(tmp_path)
    # give chapter 1 three beats; all must reach the writer context
    outline = bible.get_outline()  # not yet persisted; rebuild provider outline instead
    run_full_pipeline(provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
                      proj=proj, premise="a thief", target_chapters=1,
                      language="zh", chapter_target_length=3000)
    ctx0 = provider.writer_contexts[0]
    assert "[Beats" in ctx0 and "[Target length] 本章目标约 3000 字" in ctx0
    assert "[Arc summary]" not in ctx0   # no arc summary yet (Task 12 adds them)


def test_summary_lazy_backfill(tmp_path):
    from novel.store.summaries import SummaryStore
    proj, bible, vector, provider = _two_chapter_arc_setup(tmp_path)
    state1 = run_full_pipeline(provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
                               proj=proj, premise="a thief", target_chapters=1)
    assert state1.error is None
    SummaryStore(proj)._chapter_path(1).unlink()      # simulate a lost summary
    provider.responses["summarizer"] = {
        "chapter_no": 1, "arc_name": "卷一", "summary": "补生成的第一章摘要。",
        "characters_involved": [], "threads_advanced": []}
    state2 = run_full_pipeline(provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
                               proj=proj, premise="", target_chapters=2, start_chapter=2)
    assert state2.error is None
    assert SummaryStore(proj).get_chapter_summary(1).summary == "补生成的第一章摘要。"


def test_continuity_receives_compact_view_not_canonical(tmp_path):
    captured: list[dict[str, object]] = []

    class _RecordingContinuity(_RecordingWriterProvider):
        def complete(self, messages, cfg, *, seed=None):
            if any(m.get("agent") == "continuity" for m in messages):
                captured.append(messages[-1])
            return super().complete(messages, cfg, seed=seed)

    proj, bible, vector, concept, beat, _o, chars = _one_chapter_setup(tmp_path)
    passing = ReviewScore(artifact_type="chapter", overall=90,
                          scores={"beat_adherence": DimensionScore(score=90, critique="ok")})
    provider = _RecordingContinuity({
        "strategist": concept, "worldbuilder": World(setting="city"), "character": chars,
        "outliner": Outline(arcs=[Arc(arc_name="卷一", chapters=[
            ChapterOutline(chapter_no=1, chapter_title="T1", beats=[beat])])]),
        "writer": "Chapter prose text.", "continuity": "[]", "editor": "x",
        "scorer": passing,
        "extractor": {"character_states": {}, "voice_samples": {}, "mannerisms_used": {},
                      "key_events": [], "threads_advanced": [], "new_information_revealed": []}})
    run_full_pipeline(provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
                      proj=proj, premise="a thief", target_chapters=1)
    user = str(captured[0]["content"])
    assert "setting" in user            # compact view carries world setting via characters/threads
    assert "_canonical" not in user and '"logline"' not in user   # NOT the raw canonical JSON
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_graph.py -q`
Expected: FAIL — `TypeError: assemble_context() got an unexpected keyword argument 'beat'`（graph 仍旧签名）等

- [ ] **Step 3: Implement**

`novel/graph.py`：

1. import 区追加：

```python
from novel.agents.outliner import ArcDetailInput, ArcDetailerAgent
from novel.memory.assembler import RECENT_SUMMARY_K, assemble_context, continuity_compact_view
from novel.memory.summarizer import digest_book, summarize_arc, summarize_chapter
from novel.models import ChapterOutline, ChapterSummary
from novel.store.summaries import SummaryStore, detect_edited_chapters, sha256_text
```

（`ArcDetailInput`/`ArcDetailerAgent`/`summarize_arc`/`digest_book` 在 Task 12 才使用——先 import 会因未用触发 ruff F401；**本任务只 import Task 10 用到的**：`RECENT_SUMMARY_K, assemble_context, continuity_compact_view, summarize_chapter, ChapterSummary, SummaryStore, sha256_text`。`detect_edited_chapters`、`ArcDetailerAgent` 等留到 Task 11/12 再加。）

2. `run_full_pipeline` 签名在 `min_chapter_chars: int = 50,` 之后追加：

```python
    planned_total: int | None = None,
    gate_every_n: int = 1,
    language: str = "en",
    chapter_target_length: int = 2500,
    arc_lookahead: int = 5,
```

3. **generation 循环整体替换**（从 `# --- GENERATION ---` 注释起到 `emit({"type": "done"})` 之前的循环体）：

```python
    # --- GENERATION ---
    # Flatten outline chapters by position (1..N). Position == global chapter number:
    # chapter k on disk must be written from the k-th outline chapter. On resume,
    # skip positions < start_chapter instead of restarting the outline from the top.
    summaries = SummaryStore(proj)

    def flat_chapters() -> list[tuple[str, ChapterOutline]]:
        return [(a.arc_name, c) for a in outline.arcs for c in a.chapters]

    total_outline = len(flat_chapters())
    if start_chapter > total_outline:
        state.error = (f"outline exhausted: {total_outline} chapters in outline, "
                       f"nothing to write from chapter {start_chapter}")
        return state

    def _target_note() -> str:
        if language == "zh":
            return f"[Target length] 本章目标约 {chapter_target_length} 字"
        return f"[Target length] Target ~{chapter_target_length} words for this chapter"

    def _backfill_prev_summary(chapter_no: int) -> None:
        """Lazy retry (spec §4.1): regenerate at most the immediate predecessor's
        missing summary — one bounded call per chapter cycle, no history chase."""
        if chapter_no < 2:
            return
        prev = chapter_no - 1
        if summaries.get_chapter_summary(prev) is None and \
                is_chapter_complete(proj, reviews, prev, min_chapter_chars):
            prev_prose = (proj.root / "chapters" / f"{prev:03d}.md").read_text(encoding="utf-8")
            prev_arc = flat[prev - 1][0] if prev - 1 < len(flat) else ""
            cs = summarize_chapter(prev, prev_prose, prev_arc, provider, agent("extractor"))
            cs.prose_sha256 = sha256_text(prev_prose)
            summaries.put_chapter_summary(cs)
            emit({"type": "stage", "stage": "summary_backfill", "chapter": prev})

    idx = start_chapter - 1
    while True:
        flat = flat_chapters()
        if idx >= len(flat) or idx + 1 > target_chapters:
            break
        arc_name, ch_out = flat[idx]
        chapter_no = idx + 1
        _backfill_prev_summary(chapter_no)
        if is_chapter_complete(proj, reviews, chapter_no, min_chapter_chars):
            emit({"type": "chapter_skipped", "chapter": chapter_no,
                  "reason": "already complete"})
            idx += 1
            continue
        beats = ch_out.beats
        assert beats, f"chapter {chapter_no} has no beat"
        emit({"type": "chapter_start", "chapter": chapter_no, "title": ch_out.chapter_title})
        arc_sum = summaries.get_arc_summary(arc_name)
        recent = summaries.recent_chapter_summaries(upto=chapter_no - 1, k=RECENT_SUMMARY_K)
        digest = summaries.get_book_digest()
        ctx = assemble_context(
            beats=beats, bible=bible, vector=vector, proj=proj, token_budget=token_budget,
            chapter_no=chapter_no,
            arc_summary=arc_sum.summary if arc_sum else "",
            recent_summaries=[f"ch{cs.chapter_no}: {cs.summary}" for cs in recent],
            book_digest=digest.summary if digest else "",
            target_note=_target_note())
        writer = WriterAgent(provider, agent("writer"))
        prose = writer.run(ctx)
        # scorer loop on chapter
        attempt = 1
        final_ok = False
        while True:
            emit({"type": "stage", "stage": "scorer", "chapter": chapter_no, "attempt": attempt})
            ok, rs = _scored(prose, "chapter",
                             json.dumps({"prose": prose,
                                         "beats": [b.model_dump() for b in beats]},
                                        ensure_ascii=False),
                             scorer, score_min, max_retries, attempt)
            state.last_review = rs
            reviews.append(ReviewRecord(
                chapter=chapter_no, attempt=attempt, artifact_type=rs.artifact_type,
                overall=rs.overall, summary=rs.summary, scores=rs.scores, passed=ok,
                timestamp=datetime.now(UTC).isoformat()))
            if not ok:
                notes.add_weak(chapter_no, {
                    name: (ds.score, ds.critique)
                    for name, ds in rs.scores.items() if ds.score < score_min})
            emit({"type": "review", "chapter": chapter_no, "attempt": attempt,
                  "passed": ok, "overall": rs.overall,
                  "scores": {name: ds.score for name, ds in rs.scores.items()},
                  "score_min": score_min})
            if ok:
                final_ok = True
                break
            if attempt >= max_retries:
                break
            feedback = apply_review(rs, prose)
            emit({"type": "stage", "stage": "writer_rewrite", "chapter": chapter_no, "attempt": attempt})
            prose = writer.run(type(ctx)(blocks=ctx.blocks + [f"[REWRITE NOTES] {feedback}"]))
            attempt += 1
        if not final_ok:
            approved = on_gate("chapter_review_failed", rs) if on_gate else False
            if not approved:
                state.error = f"chapter {chapter_no} rejected after {max_retries} attempts"
                emit({"type": "chapter_skipped", "chapter": chapter_no, "reason": state.error})
                idx += 1
                continue
            reviews.append(ReviewRecord(
                chapter=chapter_no, attempt=attempt, artifact_type=rs.artifact_type,
                overall=rs.overall, summary=f"human override: {rs.summary}",
                scores=rs.scores, passed=True,
                timestamp=datetime.now(UTC).isoformat()))
        # continuity — compact view replaces the whole canonical JSON (spec §4.5)
        emit({"type": "stage", "stage": "continuity", "chapter": chapter_no})
        compact = continuity_compact_view(
            beats=beats, bible=bible,
            arc_summary=arc_sum.summary if arc_sum else "",
            recent_summaries=[f"ch{cs.chapter_no}: {cs.summary}" for cs in recent],
            book_digest=digest.summary if digest else "")
        issues = ContinuityAgent(provider, agent("continuity")).run((prose, compact))
        if issues:
            emit({"type": "stage", "stage": "editor", "chapter": chapter_no})
            prose = EditorAgent(provider, agent("editor")).run(prose)
        # extract + apply in ONE batched bible write (spec §4.4)
        emit({"type": "stage", "stage": "extractor", "chapter": chapter_no})
        involved_ids: list[str] = []
        for b in beats:
            for cid in b.characters:
                if cid not in involved_ids:
                    involved_ids.append(cid)
        involved = [c for c in (bible.get_character(i) for i in involved_ids) if c is not None]
        upd = extract_updates(chapter_no, prose, involved, provider, agent("extractor"))
        bible.apply_chapter_updates(chapter_no, upd, beats)
        summaries.put_chapter_summary(ChapterSummary(
            chapter_no=chapter_no, arc_name=arc_name,
            summary=(upd.chapter_summary or prose[:300]).strip(),
            characters_involved=list(upd.character_states.keys()),
            threads_advanced=upd.threads_advanced,
            prose_sha256=sha256_text(prose)))
        vector.add_chapter(chapter_no, prose)
        vector.add_summary("chapter", f"ch{chapter_no}", upd.chapter_summary or prose[:300])
        # atomic write last: the file's appearance is the chapter's commit point
        chapters_dir = proj.root / "chapters"
        tmp = chapters_dir / f".{chapter_no:03d}.md.tmp"
        tmp.write_text(prose, encoding="utf-8")
        tmp.replace(chapters_dir / f"{chapter_no:03d}.md")
        emit({"type": "chapter_done", "chapter": chapter_no})
        state.written.append(chapter_no)
        if on_gate:
            on_gate("chapter", chapter_no)
        idx += 1
    total_outline = len(flat_chapters())
    if not state.error and target_chapters > total_outline:
        state.error = (f"outline exhausted: outline has {total_outline} chapters, "
                       f"requested through chapter {target_chapters} "
                       f"(wrote {len(state.written)} this run)")
```

（原 `for arc in outline.arcs: for ch_out in arc.chapters:` 双层循环及其 `outline_pos` 计数全部删除；`beat = ch_out.beats[0]`、旧的手工 extractor 应用段、`vector.add_summary(..., prose[:300])` 原行均被上文取代。`flat` 在 `_backfill_prev_summary` 里通过闭包引用最近一次循环头重建的 `flat` 变量——实现时把 `_backfill_prev_summary(chapter_no)` 移到 `flat = flat_chapters()` 之后调用即可，函数体直接读外层 `flat`。）

4. 既有测试影响：`_resume_setup` 等用单 beat 每章——行为不变；`test_resume_beyond_outline_reports_exhaustion` 语义由新循环保留（`idx >= len(flat)` 即 exhausted）。

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_graph.py tests/test_resume.py tests/test_assembler.py -q && uv run mypy novel`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add novel/graph.py tests/test_graph.py
git commit -m "feat(longform): graph loop — chapter summaries, batched bible application, continuity compact view, lazy summary backfill, all-beats writing"
```

---

### Task 11: gate-every-N + planned_total 事件 + 手改哈希警告

**Files:**
- Modify: `novel/graph.py`
- Test: `tests/test_graph.py`

**Interfaces:**
- Produces:
  - live 人工门按 `chapter_no % gate_every_n == 0` 触发（默认 1 = 现状）
  - `chapter_start` / `chapter_done` 事件携带 `planned_total`（`planned_total=None` 时也带字段、值为 null，additive）
  - 运行启动时对每个手改章发 `{"type": "warning", "warning": "chapter_edited", "chapter": n}`

- [ ] **Step 1: Write the failing tests**

`tests/test_graph.py` 追加：

```python
def test_gate_every_n_skips_intermediate_chapters(tmp_path):
    proj, bible, vector, provider = _two_chapter_arc_setup(tmp_path)
    gates: list[tuple[str, object]] = []
    state = run_full_pipeline(provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
                              proj=proj, premise="a thief", target_chapters=2,
                              gate_every_n=2, on_gate=lambda label, art: gates.append((label, art)) or True)
    assert state.error is None and state.written == [1, 2]
    assert [g[0] for g in gates] == ["chapter"]      # only ch2 (2 % 2 == 0); default N=1 fires every chapter


def test_chapter_events_carry_planned_total(tmp_path):
    proj, bible, vector, provider = _two_chapter_arc_setup(tmp_path)
    events: list[dict[str, object]] = []
    run_full_pipeline(provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
                      proj=proj, premise="a thief", target_chapters=1, planned_total=240,
                      on_event=events.append)
    start = next(e for e in events if e["type"] == "chapter_start")
    done = next(e for e in events if e["type"] == "chapter_done")
    assert start["planned_total"] == 240 and done["planned_total"] == 240


def test_edited_chapter_hash_warning(tmp_path):
    proj, bible, vector, provider = _two_chapter_arc_setup(tmp_path)
    state1 = run_full_pipeline(provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
                               proj=proj, premise="a thief", target_chapters=1)
    assert state1.error is None
    (proj.root / "chapters" / "001.md").write_text("手改后的正文。", encoding="utf-8")
    events: list[dict[str, object]] = []
    state2 = run_full_pipeline(provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
                               proj=proj, premise="", target_chapters=2, start_chapter=2,
                               on_event=events.append)
    assert state2.error is None
    warn = [e for e in events if e["type"] == "warning" and e["warning"] == "chapter_edited"]
    assert warn and warn[0]["chapter"] == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_graph.py -q`
Expected: FAIL — 事件无 `planned_total` / warning、门每章触发

- [ ] **Step 3: Implement**

`novel/graph.py`：

1. import 追加 `detect_edited_chapters`（来自 `novel.store.summaries`）。
2. `stale tmp` 清理循环之后、`total_outline = len(flat_chapters())` 之前插入：

```python
    # user contract (spec §5): manual prose edits that bypassed the pipeline are
    # detected (hash mismatch) and reported — state is NOT auto-rebuilt
    for n in detect_edited_chapters(proj, summaries):
        emit({"type": "warning", "warning": "chapter_edited", "chapter": n})
```

（`summaries = SummaryStore(proj)` 需上移到该处之前——Task 10 已把它放在 GENERATION 注释后首个语句，满足。）
3. `chapter_start` 事件改为：

```python
        emit({"type": "chapter_start", "chapter": chapter_no, "title": ch_out.chapter_title,
              "planned_total": planned_total})
```

4. `chapter_done` 事件改为：

```python
        emit({"type": "chapter_done", "chapter": chapter_no, "planned_total": planned_total})
```

5. 结尾人工门改为：

```python
        if on_gate and gate_every_n > 0 and chapter_no % gate_every_n == 0:
            on_gate("chapter", chapter_no)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_graph.py -q && uv run mypy novel && uv run ruff check .`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add novel/graph.py tests/test_graph.py
git commit -m "feat(longform): gate-every-N wiring, planned_total progress events, manual-edit hash warnings"
```

---

### Task 12: 两段式出纲 — setup 接线 + 自动续纲 + 卷边界摘要

**Files:**
- Modify: `novel/setup_flow.py`（`generate_stage` 增 `target_chapters` 分支 + `generate_two_phase_outline`）
- Modify: `novel/graph.py`（setup 调用传参；循环内自动续纲 + 卷边界摘要）
- Test: `tests/test_setup_flow.py`、`tests/test_graph.py`

**Interfaces:**
- Produces:
  - `generate_stage(stage, *, provider, cfg_map, bible, premise="", feedback=None, target_chapters: int | None = None)`——`stage == "outline"` 且 `target_chapters` 非空时走两段式
  - `generate_two_phase_outline(provider, cfg_map, bible, target_chapters) -> Outline`（骨架一次 + 第一卷明细；`Outline.arc_plan` = 其余骨架队列）
  - graph：`detail_next_arc()`（含 live 门 `arc_detail`、防御性重编号、持久化）+ 卷完结摘要钩子（ArcSummary + BookDigest，失败发 warning 不致命）
- Consumes: Task 6 agents、Task 7 `summarize_arc`/`digest_book`、Task 1 `Outline.arc_plan`。

- [ ] **Step 1: Write the failing tests**

`tests/test_setup_flow.py` 追加：

```python
def test_generate_outline_two_phase_when_target_chapters_set(tmp_path):
    from novel.config import ModelConfig
    from novel.memory.extractor import ChapterUpdates  # noqa: F401  (fixture symmetry)
    from novel.models import Concept, World
    from novel.project import NovelProject
    from novel.providers import FakeProvider
    from novel.setup_flow import generate_stage
    from novel.store.bible import StoryBible

    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    bible = StoryBible(proj)
    bible.set_concept(Concept(logline="L", genre="g", tone="t", target_length_words=9000, audience="a"))
    bible.set_world(World(setting="city"))
    bible.upsert_character(Character(id="c1", slug="ara", name="Ara", role="protagonist",
                                     backstory="b", motivation="m", arc="a"))
    cfg_map = {n: ModelConfig("zhipu", "x") for n in
               ("strategist", "worldbuilder", "character", "outliner", "writer",
                "continuity", "editor", "scorer", "extractor")}
    provider = FakeProvider({
        "arc_planner": {"arcs": [
            {"arc_name": "卷一", "chapter_start": 1, "chapter_end": 2, "premise": "p1"},
            {"arc_name": "卷二", "chapter_start": 3, "chapter_end": 4, "premise": "p2"}],
            "planned_total_chapters": 4},
        "arc_detailer": {"arc_name": "卷一", "chapters": [
            {"chapter_no": 1, "chapter_title": "T1",
             "beats": [{"pov": "c1", "setting": "s", "event": "e1",
                        "emotional_turn": "d", "characters": ["c1"]}]},
            {"chapter_no": 2, "chapter_title": "T2",
             "beats": [{"pov": "c1", "setting": "s", "event": "e2",
                        "emotional_turn": "d", "characters": ["c1"]}]}]}})
    outline = generate_stage("outline", provider=provider, cfg_map=cfg_map, bible=bible,
                             target_chapters=4)
    assert [a.arc_name for a in outline.arcs] == ["卷一"]
    assert [s.arc_name for s in outline.arc_plan] == ["卷二"]   # 待明细骨架队列
```

`tests/test_graph.py` 追加：

```python
class _ArcSequenceProvider(_RecordingWriterProvider):
    """FakeProvider serving queued arc_detailer responses in call order."""

    def __init__(self, responses, arcs):
        super().__init__(responses)
        self._arcs = list(arcs)

    def _lookup(self, messages):
        from novel.providers import _agent_tag
        if _agent_tag(messages, self.tag_key) == "arc_detailer":
            return self._arcs.pop(0)
        return super()._lookup(messages)


def test_auto_extend_details_next_arc_and_arc_summary(tmp_path):
    from novel.store.summaries import SummaryStore
    proj, bible, vector, concept, _beat, _o, chars = _one_chapter_setup(tmp_path)
    beat = ChapterBeat(pov="Ara", setting="t", event="e", emotional_turn="d", characters=["c1"])
    skeleton_outline = Outline(
        arcs=[Arc(arc_name="卷一", chapters=[
            ChapterOutline(chapter_no=i, chapter_title=f"T{i}", beats=[beat]) for i in (1, 2)])],
        arc_plan=[ArcSkeleton(arc_name="卷二", chapter_start=3, chapter_end=4, premise="p2")])
    passing = ReviewScore(artifact_type="chapter", overall=90,
                          scores={"beat_adherence": DimensionScore(score=90, critique="ok")})
    arc2 = Arc(arc_name="卷二", chapters=[
        ChapterOutline(chapter_no=99, chapter_title="T3", beats=[beat]),   # wrong numbers on purpose
        ChapterOutline(chapter_no=100, chapter_title="T4", beats=[beat])])
    provider = _ArcSequenceProvider({
        "strategist": concept, "worldbuilder": World(setting="city"), "character": chars,
        "outliner": skeleton_outline, "writer": "Chapter prose text.", "continuity": "[]",
        "editor": "x", "scorer": passing,
        "extractor": {"character_states": {}, "voice_samples": {}, "mannerisms_used": {},
                      "key_events": [], "threads_advanced": [], "new_information_revealed": [],
                      "chapter_summary": "摘要。"},
        "summarizer": {"arc_name": "卷一", "chapter_start": 1, "chapter_end": 2,
                       "summary": "卷一摘要。", "major_developments": []},
        "digestor": {"chapter_count": 2, "current_arc": "卷一", "summary": "全书梗概。"},
    }, arcs=[arc2])
    state = run_full_pipeline(provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
                              proj=proj, premise="a thief", target_chapters=4, arc_lookahead=2)
    assert state.error is None and state.written == [1, 2, 3, 4]
    outline = bible.get_outline()
    assert [a.arc_name for a in outline.arcs] == ["卷一", "卷二"]
    assert outline.arc_plan == []
    # defensive renumbering: canned 99/100 became 3/4
    assert [c.chapter_no for c in outline.arcs[1].chapters] == [3, 4]
    assert (proj.root / "chapters" / "003.md").exists()
    store = SummaryStore(proj)
    assert store.get_arc_summary("卷一").summary == "卷一摘要。"
    assert store.get_book_digest().summary == "全书梗概。"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_setup_flow.py tests/test_graph.py -q`
Expected: FAIL — `TypeError: generate_stage() got an unexpected keyword argument 'target_chapters'`；auto-extend 断言失败

- [ ] **Step 3: Implement**

`novel/setup_flow.py`：

1. import 追加 `from novel.agents.outliner import ArcDetailInput, ArcDetailerAgent, ArcPlannerAgent`；models import 补 `ArcSkeleton, Outline`（Outline 已有则免）。
2. `generate_stage` 签名加 `target_chapters: int | None = None`，`stage == "outline"` 分支改为：

```python
    if stage == "outline":
        concept = bible.get_concept()
        world = bible.get_world()
        assert concept is not None and world is not None, "concept+world required"
        if target_chapters:
            return generate_two_phase_outline(provider=provider, cfg_map=cfg_map,
                                               bible=bible, target_chapters=target_chapters)
        return OutlinerAgent(provider, cfg_map["outliner"]).run(
            (concept, world, list(bible.all_characters())), feedback=fb)
```

3. 新增函数（`merge_foreshadow_ledger` 之前）：

```python
def generate_two_phase_outline(*, provider, cfg_map, bible: StoryBible,
                               target_chapters: int) -> Outline:
    """Volume skeletons first, then only the FIRST volume detailed (spec §4.3).
    Outline.arc_plan keeps the not-yet-detailed skeletons as a queue."""
    concept = bible.get_concept()
    world = bible.get_world()
    assert concept is not None and world is not None, "concept+world required"
    roster = list(bible.all_characters())
    plan = ArcPlannerAgent(provider, cfg_map["outliner"]).run((concept, world, roster, target_chapters))
    assert plan.arcs, "arc planner returned no volumes"
    existing_max = 0
    arc = _detail_arc(provider, cfg_map, bible, plan.arcs[0], prev_arc=None,
                      next_chapter_no=existing_max + 1)
    outline = Outline(arcs=[arc], arc_plan=plan.arcs[1:])
    merge_foreshadow_ledger(outline, bible)
    return outline


def _detail_arc(provider, cfg_map, bible: StoryBible, skeleton: ArcSkeleton,
                prev_arc, next_chapter_no: int):
    from novel.models import ArcSummary, ForeshadowStatus
    arc = ArcDetailerAgent(provider, cfg_map["outliner"]).run(ArcDetailInput(
        skeleton=skeleton, concept=bible.get_concept(), world=bible.get_world(),
        characters=list(bible.all_characters()), prev_arc=prev_arc,
        open_foreshadows=[f for f in bible.list_foreshadow()
                           if f.status == ForeshadowStatus.OPEN],
        recent_summaries=[], next_chapter_no=next_chapter_no))
    # defensive renumbering: model output numbers are advisory only (spec §4.3)
    for i, ch in enumerate(arc.chapters):
        ch.chapter_no = next_chapter_no + i
    return arc
```

（`prev_arc` 参数类型 `ArcSummary | None`——import 放函数内避免顶层与 graph 重复；mypy strict 下顶层 import 更稳，执行时选择顶层 `from novel.models import ArcSummary` 并在签名写全类型。）

`novel/graph.py`：

1. import 追加：`from novel.agents.outliner import ArcDetailInput, ArcDetailerAgent`、`from novel.memory.summarizer import digest_book, summarize_arc`（`summarize_chapter` 已引入）、models 补 `ArcSkeleton`（未直接用则不引）。
2. `generate_stage(...)` 调用点（SETUP 循环内）追加 `target_chapters=planned_total`。
3. GENERATION 段 `summaries = SummaryStore(proj)` 之后加辅助函数：

```python
    def detail_next_arc() -> bool:
        """Rolling outline (spec §4.3): detail the next skeleton. Returns False
        when the live-mode gate denied it (skeleton goes back, run continues)."""
        assert outline is not None and outline.arc_plan
        skeleton = outline.arc_plan.pop(0)
        emit({"type": "stage", "stage": "arc_detail", "arc": skeleton.arc_name})
        if on_gate and not on_gate("arc_detail", skeleton):
            outline.arc_plan.insert(0, skeleton)
            return False
        prev_name = outline.arcs[-1].arc_name if outline.arcs else ""
        prev_arc = summaries.get_arc_summary(prev_name) if prev_name else None
        recent = summaries.recent_chapter_summaries(
            upto=max((c.chapter_no for a in outline.arcs for c in a.chapters), default=0),
            k=RECENT_SUMMARY_K)
        existing_max = max((c.chapter_no for a in outline.arcs for c in a.chapters), default=0)
        from novel.setup_flow import _detail_arc
        arc = _detail_arc(provider, cfg_map, bible, skeleton, prev_arc, existing_max + 1)
        outline.arcs.append(arc)
        bible.set_outline(outline)
        emit({"type": "arc_detailed", "arc": skeleton.arc_name,
              "chapters": len(arc.chapters)})
        return True
```

4. 循环体开头（`flat = flat_chapters()` 之后、`_backfill_prev_summary` 之前）插入自动续纲：

```python
        while outline.arc_plan and len(flat) - (idx + 1) < arc_lookahead:
            if not detail_next_arc():
                break
            flat = flat_chapters()
```

5. 卷边界摘要（`chapter_done` emit 与 `state.written.append` 之间、`if on_gate` 之前插入；对「跳过的已完成章」也要生效——把该逻辑放在 `idx += 1` 前的统一位置，即写完分支与跳过分支汇合处。实现：在 `while` 循环体末尾 `idx += 1` 之前插入）：

```python
        # arc boundary (spec §4.1): next detailed chapter absent or in another volume
        nxt = flat[chapter_no] if chapter_no < len(flat) else None
        if nxt is None or nxt[0] != arc_name:
            try:
                if summaries.get_arc_summary(arc_name) is None:
                    arc_start = next(i + 1 for i, (an, _c) in enumerate(flat) if an == arc_name)
                    chapter_sums = [cs for cs in (
                        summaries.get_chapter_summary(n)
                        for n in range(arc_start, chapter_no + 1)) if cs]
                    if chapter_sums:
                        prev_arcs = [a for a in summaries.all_arc_summaries()
                                     if a.chapter_end < arc_start]
                        arc_sum = summarize_arc(arc_name, arc_start, chapter_no, chapter_sums,
                                                prev_arcs[-1] if prev_arcs else None,
                                                provider, agent("extractor"))
                        summaries.put_arc_summary(arc_sum)
                        digest = digest_book(summaries.all_arc_summaries(), chapter_no, arc_name,
                                             provider, agent("extractor"))
                        summaries.put_book_digest(digest)
                        emit({"type": "arc_summary_done", "arc": arc_name,
                              "chapter_end": chapter_no})
            except Exception:  # noqa: BLE001 - a failed arc summary must not kill a long run
                emit({"type": "warning", "warning": "arc_summary_failed", "arc": arc_name})
```

注意：既有测试的 provider dict 无 `summarizer`/`digestor` 键 → FakeProvider `_lookup` 抛 `KeyError` → 被上面的 `except Exception` 吞掉并发 warning——旧测试保持绿，这是有意设计（长跑韧性优先），新测试提供 canned 断言真路径。

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_setup_flow.py tests/test_graph.py tests/test_ui.py -q && uv run mypy novel && uv run ruff check .`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add novel/setup_flow.py novel/graph.py tests/test_setup_flow.py tests/test_graph.py
git commit -m "feat(longform): two-phase outline setup + in-loop auto arc detailing + arc-boundary summaries"
```

---

### Task 13: CLI / jobs / demo provider 参数贯通

**Files:**
- Modify: `novel/cli.py`（`write_chapter`）
- Modify: `novel/ui/jobs.py`（`run_chapters_job`）
- Modify: `novel/runtime.py`（`demo_provider` canned 增补）
- Test: `tests/test_cli.py`、`tests/test_ui.py`

**Interfaces:**
- Produces: CLI 与 GUI 的写作任务把 `cfg.generation` 的五个长篇参数传入 `run_full_pipeline`（`planned_total`、`gate_every_n`、`language`、`chapter_target_length`、`arc_lookahead`）；demo canned 增 `arc_planner`/`arc_detailer`/`summarizer`/`digestor`。

- [ ] **Step 1: Write the failing tests**

`tests/test_cli.py` 追加（沿用该文件现有的 CLI 测试基建——runner/tmp 项目；若文件里已有 `write-chapter` 的测试函数可参照其 setup）：

```python
def test_write_chapter_passes_longform_params(tmp_path, monkeypatch):
    """write-chapter wires cfg.generation longform fields into run_full_pipeline."""
    import novel.cli as cli
    from novel.config import load_config

    proj = novel_project(tmp_path)          # 该文件现有的项目 scaffold 辅助；若无则用 NovelProject.scaffold
    cfg_path = proj.config_path
    raw = cfg_path.read_text(encoding="utf-8")
    cfg_path.write_text(raw + "generation:\n  target_chapters: 240\n  arc_detail_lookahead: 8\n",
                        encoding="utf-8")
    captured: dict[str, object] = {}
    real = cli.run_full_pipeline if hasattr(cli, "run_full_pipeline") else None

    import novel.graph as graph
    monkeypatch.setattr(graph, "run_full_pipeline",
                        lambda **kw: captured.update(kw) or _FakeState())
    cli.write_chapter("1", proj.root)      # typer 函数直调（该文件既有测试的调用方式）
    assert captured["planned_total"] == 240
    assert captured["arc_lookahead"] == 8
    assert captured["gate_every_n"] == 1
```

（`_FakeState` 为 `type("S", (), {"error": None, "written": []})()` 之类的占位实例；`novel_project` 若不存在，测试内联 `NovelProject.scaffold("n", "fantasy", root=tmp_path)`。实现时按 `tests/test_cli.py` 的既有辅助函数名对齐，断言不变。）

`tests/test_ui.py` 追加（复用该文件现有的 TestClient/项目 fixture 方式）：

```python
def test_write_req_cap_raised_and_params_forwarded(tmp_path):
    """WriteReq.n accepts up to 2000; longform params flow into the job."""
    from novel.ui.app import WriteReq
    req = WriteReq(n=2000)
    assert req.n == 2000
    with pytest.raises(ValueError):
        WriteReq(n=2001)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_cli.py tests/test_ui.py -q`
Expected: FAIL（`planned_total` 未传 / cap 50）

- [ ] **Step 3: Implement**

`novel/cli.py` `write_chapter` 的 `run_full_pipeline(...)` 调用追加参数：

```python
        planned_total=cfg.generation.target_chapters,
        gate_every_n=cfg.generation.human_gate_every_n_chapters,
        language=cfg.language,
        chapter_target_length=cfg.generation.chapter_target_length,
        arc_lookahead=cfg.generation.arc_detail_lookahead,
```

`novel/ui/jobs.py` `run_chapters_job` 的同一调用追加相同五个参数。

`novel/ui/app.py` `WriteReq`：

```python
class WriteReq(BaseModel):
    n: int = Field(default=1, ge=1, le=2000)
```

`novel/runtime.py` `demo_provider` responses 增补（models import 区补 `Arc, ArcPlan, ArcSkeleton, ArcSummary, BookDigest, ChapterOutline, ChapterSummary`）：

```python
        "arc_planner": ArcPlan(arcs=[ArcSkeleton(arc_name="第一卷", chapter_start=1,
                                                  chapter_end=6, premise="demo"),
                                     ArcSkeleton(arc_name="第二卷", chapter_start=7,
                                                 chapter_end=12, premise="demo2")],
                               planned_total_chapters=12),
        "arc_detailer": Arc(arc_name="第一卷", chapters=[
            ChapterOutline(chapter_no=99, chapter_title="D1",
                           beats=[ChapterBeat(pov="Ara", setting="tavern", event="demo arc detail",
                                              emotional_turn="doubt", characters=["c1"])])]),
        "summarizer": ChapterSummary(chapter_no=1, summary="演示摘要。"),
        "digestor": BookDigest(chapter_count=6, current_arc="第一卷", summary="演示梗概。"),
```

（`arc_detailer` canned 的 chapter_no 故意给 99——验证防御性重编号路径在 demo 也可用；`summarizer` 同时充当章/卷摘要：`summarize_chapter`/`summarize_arc` 返回后都会覆写关键字段，canned 只需通过 schema 校验。）

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_cli.py tests/test_ui.py -q && uv run pytest -q && uv run mypy novel && uv run ruff check .`
Expected: PASS（本任务起跑全量 pytest）

- [ ] **Step 5: Commit**

```bash
git add novel/cli.py novel/ui/jobs.py novel/ui/app.py novel/runtime.py tests/test_cli.py tests/test_ui.py
git commit -m "feat(longform): plumb longform params through CLI/GUI write jobs; demo canned arc agents; raise UI chapter cap to 2000"
```

---

### Task 14: UI — 全书进度显示 + 事件文案

**Files:**
- Modify: `ui-v2/src/stores/events.ts`、`ui-v2/src/pages/Generate.tsx`、`ui-v2/src/constants.ts`、`ui-v2/src/describe.ts`
- Test: `ui-v2/tests/events.test.ts`、`ui-v2/tests/pages.test.tsx`

**Interfaces:**
- Produces: events store 新增 `lastChapterStart: { chapter: number; plannedTotal: number | null } | null`（`chapter_start` 事件驱动；`job_end`/`resetTransient`/`reset` 清空）；Generate 页显示「全书进度：第 x / 共 y 章」（`plannedTotal` 非空时）；`describe.ts` 增 `warning` / `arc_detailed` / `arc_summary_done` 文案；`STAGE_NAMES` 增 `arc_detail` / `summary_backfill`；`GATE_LABELS` 增 `arc_detail`。

- [ ] **Step 1: Write the failing tests**

`ui-v2/tests/events.test.ts` 追加（沿用该文件现有的 store 测试写法）：

```typescript
it("tracks chapter_start with plannedTotal and clears on job_end", () => {
  const s = useEvents.getState();
  s.reset();
  useEvents.getState().apply({ type: "chapter_start", chapter: 37, title: "T", planned_total: 240 });
  expect(useEvents.getState().lastChapterStart).toEqual({ chapter: 37, plannedTotal: 240 });
  useEvents.getState().apply({ type: "job_end", status: "done" });
  expect(useEvents.getState().lastChapterStart).toBeNull();
});
```

`ui-v2/tests/pages.test.tsx` 追加（沿用现有 RenderWrapper 方式）：

```typescript
it("Generate shows whole-book progress when plannedTotal is present", async () => {
  useEvents.getState().reset();
  useEvents.getState().apply({ type: "chapter_start", chapter: 37, title: "T", planned_total: 240 });
  render(<Generate />, { wrapper: RenderWrapper, initialEntries: ["/p/demo-novel/generate"] });
  expect(await screen.findByText(/第 37 \/ 共 240 章/)).toBeInTheDocument();
});
```

（`RenderWrapper`/`initialEntries`/mock 按该文件既有测试的实际辅助名对齐——页面已有 `page-generate` testid 测试可参照；若既有测试不传 initialEntries 而是直接渲染 + mock useParams，按现状改写调用方式，断言不变。）

- [ ] **Step 2: Run to verify failure**

Run: `cd ui-v2 && npm run test`
Expected: FAIL

- [ ] **Step 3: Implement**

1. `ui-v2/src/stores/events.ts`：`EventState` 接口与初始 state 加 `lastChapterStart: { chapter: number; plannedTotal: number | null } | null;`（初始 `null`）；`apply` 的 `switch` 加：

```typescript
        case "chapter_start":
          patch.lastChapterStart = {
            chapter: Number(ev.chapter ?? 0),
            plannedTotal: typeof ev.planned_total === "number" ? ev.planned_total : null,
          };
          break;
```

`job_end` 分支加 `patch.lastChapterStart = null;`；`resetTransient` 与 `reset` 的 set 对象里加 `lastChapterStart: null`。

2. `ui-v2/src/pages/Generate.tsx`：`const lastStart = useEvents((s) => s.lastChapterStart);`；进度 Card 里 `lastStage` 行之后加：

```tsx
          {lastStart?.plannedTotal ? (
            <Typography.Text data-testid="book-progress">
              全书进度：第 {lastStart.chapter} / 共 {lastStart.plannedTotal} 章
            </Typography.Text>
          ) : null}
```

`InputNumber` 的 `max={50}` 改 `max={2000}`。

3. `ui-v2/src/constants.ts`：`STAGE_NAMES` 加 `"arc_detail": "生成下一卷明细", "summary_backfill": "补生成上一章摘要",`；`GATE_LABELS` 加 `arc_detail: "下一卷大纲明细已生成，是否批准？",`。

4. `ui-v2/src/describe.ts`：`switch` 加：

```typescript
    case "warning":
      return ev.warning === "chapter_edited"
        ? `⚠ 第 ${ev.chapter} 章正文与摘要记录不一致（手动修改？）——状态未自动重算`
        : `⚠ ${s("warning")}`;
    case "arc_detailed":
      return `📖 卷「${s("arc")}」明细已生成（${s("chapters")} 章）`;
    case "arc_summary_done":
      return `📘 卷「${s("arc")}」摘要与全书梗概已更新`;
```

- [ ] **Step 4: Run tests & typecheck & build**

Run: `cd ui-v2 && npm run test && npm run typecheck && npm run build`
Expected: PASS（build 产出 dist 供 novel-ui 服务）

- [ ] **Step 5: Commit**

```bash
git add ui-v2/src ui-v2/tests
git commit -m "feat(ui-v2): whole-book progress display, longform stage/gate labels, manual-edit warning copy"
```

---

### Task 15: 200 章长跑集成测试

**Files:**
- Create: `tests/test_longrun.py`

**Interfaces:**
- Consumes: 全部前置任务。
- Produces: `test_long_run_two_hundred_chapters`（spec §6 验收 ①）。

- [ ] **Step 1: Write the test**

`tests/test_longrun.py`：

```python
"""Spec §6 acceptance (1): a 200-chapter micro-novel must run end-to-end on
FakeProvider with bounded memory, rolling outline, and working resume."""
from novel.config import ModelConfig
from novel.graph import run_full_pipeline
from novel.models import (
    Arc,
    ArcSkeleton,
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
from novel.providers import FakeProvider
from novel.store.bible import StoryBible
from novel.store.summaries import SummaryStore
from novel.store.vector import VectorMemory, hash_embed

ARC_LEN = 50           # 4 arcs x 50 chapters = 200
TOTAL = 200


class _SeqArcProvider(FakeProvider):
    """Serves queued arc_detailer responses in call order."""

    def __init__(self, responses: dict[str, object], arcs: list[object]) -> None:
        super().__init__(responses, tag_key="agent")
        self._arcs = list(arcs)

    def _lookup(self, messages):
        from novel.providers import _agent_tag
        if _agent_tag(messages, self.tag_key) == "arc_detailer":
            return self._arcs.pop(0)
        return super()._lookup(messages)


def _beat():
    return ChapterBeat(pov="c1", setting="s", event=f"event", emotional_turn="d",
                       characters=["c1"], plants=[], payoffs=[])


def _provider(concept, chars):
    beat = _beat()
    skeleton_outline = Outline(
        arcs=[Arc(arc_name="卷一", chapters=[
            ChapterOutline(chapter_no=i, chapter_title=f"T{i}", beats=[beat])
            for i in range(1, ARC_LEN + 1)])],
        arc_plan=[ArcSkeleton(arc_name=f"卷{k}", chapter_start=(k - 1) * ARC_LEN + 1,
                              chapter_end=k * ARC_LEN, premise=f"p{k}")
                  for k in (2, 3, 4)])
    passing = ReviewScore(artifact_type="chapter", overall=90,
                          scores={"beat_adherence": DimensionScore(score=90, critique="ok")})
    later_arcs = [
        Arc(arc_name=f"卷{k}", chapters=[
            ChapterOutline(chapter_no=900 + i, chapter_title=f"X{i}", beats=[_beat()])
            for i in range(ARC_LEN)])
        for k in (2, 3, 4)
    ]
    return _SeqArcProvider({
        "strategist": concept, "worldbuilder": World(setting="city"), "character": chars,
        "outliner": skeleton_outline, "writer": "Chapter prose text.", "continuity": "[]",
        "editor": "x", "scorer": passing,
        "extractor": {"character_states": {}, "voice_samples": {"c1": "drawl"},
                      "mannerisms_used": {"c1": ["taps table"]}, "key_events": [],
                      "threads_advanced": [], "new_information_revealed": [],
                      "chapter_summary": "本章推进了主线。"},
        "summarizer": {"chapter_no": 1, "arc_name": "卷一", "summary": "卷摘要。",
                       "major_developments": []},
        "digestor": {"chapter_count": 1, "current_arc": "卷一", "summary": "全书梗概。"},
    }, arcs=later_arcs)


def _cfg_map():
    return {name: ModelConfig("zhipu", "x") for name in
            ("strategist", "worldbuilder", "character", "outliner", "writer",
             "continuity", "editor", "scorer", "extractor")}


def test_long_run_two_hundred_chapters(tmp_path):
    proj = NovelProject.scaffold("n", genre="fantasy", root=tmp_path)
    bible = StoryBible(proj)
    vector = VectorMemory(proj, embed=hash_embed)
    concept = Concept(logline="L", genre="fantasy", tone="grim", themes=[],
                      target_length_words=500000, audience="a")
    chars = [Character(id="c1", slug="ara", name="Ara", role="protagonist",
                       backstory="b", motivation="m", arc="a")]
    provider = _provider(concept, chars)
    events: list[dict[str, object]] = []
    state = run_full_pipeline(
        provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
        proj=proj, premise="a thief", target_chapters=TOTAL, min_chapter_chars=10,
        planned_total=TOTAL, arc_lookahead=5, on_event=events.append)
    assert state.error is None
    assert len(state.written) == TOTAL

    store = SummaryStore(proj)
    # every chapter has a summary
    assert all(store.get_chapter_summary(n) for n in range(1, TOTAL + 1))
    # arc summaries + digest generated for the four volumes
    assert [a.arc_name for a in store.all_arc_summaries()] == ["卷一", "卷二", "卷三", "卷四"]
    assert store.get_book_digest() is not None
    # rolling outline actually detailed the three skeleton volumes
    assert [a.arc_name for a in bible.get_outline().arcs] == ["卷一", "卷二", "卷三", "卷四"]
    assert bible.get_outline().arc_plan == []
    # bounded bible: voice capped at 10 (earliest + 9 recent), mannerisms capped at 8
    c1 = bible.get_character("c1")
    assert len(c1.voice_fingerprint) == 10
    assert "sample_1" in c1.voice_fingerprint and f"sample_{TOTAL}" in c1.voice_fingerprint
    assert len(c1.mannerisms) == 1          # single distinct mannerism, merged not duplicated
    # canonical file stays bounded relative to chapter count
    canonical_size = proj.canonical_path.stat().st_size
    assert canonical_size < 60_000          # 200 chapters must not inflate the bible
    # progress events carry planned_total
    assert next(e for e in events if e["type"] == "chapter_start")["planned_total"] == TOTAL
    assert any(e["type"] == "arc_detailed" for e in events)

    # resume: delete the last two chapters and re-run — rewritten, not restarted
    for n in (TOTAL - 1, TOTAL):
        (proj.root / "chapters" / f"{n:03d}.md").unlink()
    state2 = run_full_pipeline(
        provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
        proj=proj, premise="", target_chapters=TOTAL, start_chapter=TOTAL - 1,
        min_chapter_chars=10, planned_total=TOTAL, arc_lookahead=5)
    assert state2.error is None and state2.written == [TOTAL - 1, TOTAL]
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/test_longrun.py -q`
Expected: PASS（FakeProvider 下秒级~分钟级；若超过 3 分钟，检查是否 chroma upsert 卡顿——正常不会）

- [ ] **Step 3: Run the full suite**

Run: `uv run pytest -q && uv run mypy novel && uv run ruff check . && cd ui-v2 && npm run test && npm run typecheck`
Expected: 全绿

- [ ] **Step 4: Commit**

```bash
git add tests/test_longrun.py
git commit -m "test(longform): 200-chapter end-to-end long-run — bounded memory, rolling outline, resume"
```

---

### Task 16: 文档同步 — README / AGENTS.md / live runbook

**Files:**
- Modify: `README.md`（generation 字段表 + 用户契约 + 两段式大纲说明）
- Modify: `AGENTS.md`（store 模块行、gotcha）
- Modify: `docs/superpowers/runbooks/live-run.md`（长篇试跑一卷段落）

**Interfaces:** 无代码；内容变更必须与实现一致（字段名/默认值逐字）。

- [ ] **Step 1: README.md**

1. 字段表（约 `README.md:343-348` 的 generation 段）追加三行：

```markdown
| `generation.target_chapters` | 计划全书总章数；设置后 setup 走两段式大纲（卷骨架 + 按卷明细），留空保持单次全量出纲 | `240` |
| `generation.chapter_target_length` | 每章目标长度（zh=字 / en=词），注入写手提示词 | `2500` |
| `generation.arc_detail_lookahead` | 自动续纲提前量：已明细章节不足该值时自动生成下一卷明细（强剧情可调大） | `5` |
```

2. 「追章」说明（约 `README.md:134` 与 `:521` 附近）补一句：设置了 `target_chapters` 时写作循环会**自动**生成下一卷明细（live 模式过 `arc_detail` 人工门），UI 手动追章仍可用、二者共存。

3. 新增「用户契约：手动修改已完成章节」小节：

```markdown
### 用户契约：手动修改已完成章节

直接编辑 `chapters/NNN.md` **不会**自动同步角色状态、事件与伏笔（extractor 只在管线写作时运行）。
系统在每次写作任务启动时会校验章节文件哈希（记录于 `chapters/_summaries/NNN.json` 的
`prose_sha256`），不一致时在 UI 发出警告，但**不会自动重算状态**。需要状态重建时，
请重写该章（Reader 页改写功能会走完整回写），或等待后续的 backfill 工具。
```

- [ ] **Step 2: AGENTS.md**

`novel/store/` 行补 `summaries.py`（章/卷/全书三级摘要 + 手改哈希检测：`chapters/_summaries/`、`.meta/summaries.json`、`.meta/threads_resolved.jsonl`）；Gotchas 补一条：`chapters/_summaries/NNN.json` 与 `.meta/` 下的摘要/伏笔归档文件存在即用、缺失即降级，不影响 resume 判定。

- [ ] **Step 3: live-run runbook**

`docs/superpowers/runbooks/live-run.md` 追加「长篇试跑一卷」段落：配置 `target_chapters`（如 240）→ setup（两段式大纲）→ `write-chapter 20` → 检查项清单：跨章一致性（前卷事件、角色状态、伏笔回收）、`chapters/_summaries/` 每章摘要质量（150–250 字、情节/角色/状态）、卷完结时 `.meta/summaries.json` 生成、`arc_detail` 门只在该卷明细时出现。

- [ ] **Step 4: Verify & commit**

Run: `uv run pytest -q`（确认无破坏）— 无代码变更，直接提交：

```bash
git add README.md AGENTS.md docs/superpowers/runbooks/live-run.md
git commit -m "docs: longform config fields, user contract for manual chapter edits, live arc-run checklist"
```

---

## Self-Review 记录（写完计划后自查）

1. **Spec 覆盖**：§4.1 分层摘要→Task 3/4/7/10/12；§4.2 组装器→Task 2/8；§4.3 大纲滚动→Task 6/12/13；§4.4 治理→Task 5；§4.5 运行工程→Task 10/11/13/14；§5 契约→Task 11/16；§6 测试→Task 15 + 各任务内；§4.1 懒重试→Task 10；卷边界显式跟踪→Task 12（`flat` 分组 + `nxt[0] != arc_name`，骨架不参与扁平化）。无遗漏。
2. **占位符**：无 TBD/TODO；Task 13/14 的测试辅助名标注了「按既有文件对齐」并给出了对齐方法（这是对既有基建的引用，不是缺失实现）。
3. **类型一致性**：`ChapterUpdates.chapter_summary`（Task 4 定义，Task 5/10 消费）；`apply_chapter_updates(chapter_no, upd, beats)`（Task 5 定义，Task 10 消费）；`assemble_context(beats=..., arc_summary=..., recent_summaries=..., book_digest=..., target_note=...)`（Task 8 定义，Task 10 消费）；`_detail_arc`（Task 12 setup_flow 定义，graph 消费）；`summarize_chapter/summarize_arc/digest_book`（Task 7 定义，Task 10/12 消费）。已核对。
4. **已知偏离 spec 的点（有意为之，均已标注）**：① events 块保留为降级 fallback（spec 阶梯未列）；② `ArcDetailerAgent.name` 为消息 tag 用 `arc_detailer`（模型槽位 `outliner`），FakeProvider 路由需要；③ 卷摘要 LLM 失败吞异常发 warning（长跑韧性，spec 风险表「摘要失败不阻塞」的延伸）。
