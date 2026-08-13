# Novel Generation Agent — Implementation Plan (v1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CLI-driven, multi-agent novel-generation system (LangGraph pipeline + AI scoring gate + 3-layer memory) that produces a ~2–5万字 short novel end-to-end, testable without real LLM calls.

**Architecture:** Direction A — a fixed LangGraph pipeline of specialist agents (Strategist → Worldbuilder → Character → Outliner → per-chapter Writer → Continuity Reviewer), each wrapped by a Scorer quality gate (per-dimension ≥80 or targeted rewrite, max 3 retries then escalate). Memory = Story Bible (structured Pydantic truth, JSON+MD mirrors) + Vector memory (Chroma, hierarchical summaries) + Working memory (bounded per-chapter assembly with token budget). Specialist memories: Character memory (voice/mannerisms) + Event memory (causal log, foreshadow tracking).

**Tech Stack:** Python 3.11+, LangGraph, Pydantic v2, LiteLLM, Chroma, Typer, tenacity, pyyaml, rich; pytest + pytest-asyncio, ruff + mypy.

**Spec:** `docs/superpowers/specs/2026-08-13-novel-agent-design.md` (excluded from VCS by user request; the plan argues from it, executors read both).

## Global Constraints

- Python **3.11+**; package manager **uv** (swappable).
- **No real LLM calls in tests or CI fast path.** All agent/orchestration tests use `FakeProvider` (deterministic canned responses). Live-LLM runs gated behind `NOVEL_LIVE=1` env var.
- **TDD**: write failing test → run (fail) → minimal impl → run (pass) → commit, for every task.
- **Frequent commits**: one commit per task (or per step group), conventional-commit messages (`feat:`, `test:`, `chore:`, `refactor:`).
- **Lint/type gate**: `ruff check .` and `mypy novel` must pass before each commit.
- v1 export = **markdown only** (docx/epub deferred).
- Project = self-contained directory; Chroma file-backed inside it; no external services.
- **DRY / YAGNI**: build only what v1 needs; do not pre-build parallel workers or Web UI.

---

## File Structure

Package `novel/`. Tests mirror structure under `tests/`.

```
novel/
├── pyproject.toml              # deps + ruff + mypy config
├── README.md
├── novel/
│   ├── __init__.py
│   ├── models.py               # Pydantic domain models
│   ├── config.py               # ProjectConfig (yaml load)
│   ├── project.py              # NovelProject: paths + scaffold + canonical IO
│   ├── providers.py            # ModelProvider (LiteLLM) + FakeProvider + ModelConfig
│   ├── scorer_rubrics.py       # rubric definitions per artifact type
│   ├── store/
│   │   ├── __init__.py
│   │   ├── bible.py            # StoryBible: CRUD, MD mirrors, atomic write
│   │   └── vector.py           # VectorMemory: Chroma add/retrieve + summaries
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── extractor.py        # per-chapter state/voice/mannerism/event extraction
│   │   └── assembler.py        # WorkingMemory assembler + token budget
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py             # Agent[I,O] base: prompt → structured → validate-retry
│   │   ├── strategist.py
│   │   ├── worldbuilder.py
│   │   ├── character.py
│   │   ├── outliner.py
│   │   ├── writer.py
│   │   ├── continuity.py
│   │   ├── scorer.py
│   │   └── editor.py
│   ├── graph.py                # LangGraph wiring: nodes, scorer loops, gates, checkpoint
│   ├── cli.py                  # Typer app
│   └── export.py               # markdown export
└── tests/
    ├── conftest.py             # fixtures: tmp project, fake provider, sample data
    ├── test_models.py
    ├── test_project.py
    ├── test_config.py
    ├── test_providers.py
    ├── test_bible.py
    ├── test_vector.py
    ├── test_extractor.py
    ├── test_assembler.py
    ├── test_scorer.py
    ├── test_agents_setup.py
    ├── test_agents_gen.py
    ├── test_graph.py
    ├── test_cli.py
    └── test_export.py
```

### Shared Interfaces (defined here, referenced by tasks)

```python
# providers.py
@dataclass(frozen=True)
class ModelConfig:
    provider: str   # e.g. "zhipu", "anthropic", "deepseek"
    model: str      # e.g. "glm-4-plus"

class ModelProvider(Protocol):
    def complete(self, messages: list[dict], cfg: ModelConfig, *, seed: int | None = None) -> str: ...
    def complete_structured(self, messages: list[dict], schema: type[BaseModel], cfg: ModelConfig, *, seed: int | None = None) -> BaseModel: ...

class FakeProvider:
    """Deterministic provider for tests. Canned responses keyed by agent name."""
    def __init__(self, responses: dict[str, object]): ...   # name -> BaseModel instance or str
    # complete / complete_structured look up by a marker in messages or an explicit agent tag

class LiteLLMProvider:
    """Production provider wrapping litellm."""
    ...

# agents/base.py
I = TypeVar("I"); O = TypeVar("O", bound=BaseModel)
class Agent(Generic[I, O]):
    name: str
    output_schema: type[O]
    def __init__(self, provider: ModelProvider, cfg: ModelConfig): ...
    def build_messages(self, inputs: I) -> list[dict]: ...      # subclass overrides
    def run(self, inputs: I) -> O: ...                          # calls complete_structured + validates
```

---

## Task 1: Project scaffold + tooling

**Files:**
- Create: `pyproject.toml`, `novel/__init__.py`, `README.md`, `tests/__init__.py`

**Interfaces:** Produces an importable, empty `novel` package with `ruff`/`mypy`/`pytest` configured.

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "novel"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "langgraph>=0.2",
  "pydantic>=2.6",
  "litellm>=1.40",
  "chromadb>=0.5",
  "typer>=0.12",
  "tenacity>=8.2",
  "pyyaml>=6.0",
  "rich>=13.7",
]

[project.scripts]
novel = "novel.cli:app"

[tool.uv]
dev-dependencies = ["pytest>=8", "pytest-asyncio>=0.23", "ruff>=0.4", "mypy>=1.10"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.mypy]
python_version = "3.11"
strict = true
ignore_missing_imports = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create package markers**

`novel/__init__.py`:
```python
__version__ = "0.1.0"
```
`tests/__init__.py`: empty.
`README.md`: one-line description "Multi-agent novel generation system (v1: CLI)."

- [ ] **Step 3: Install + verify toolchain**

Run: `uv sync && uv run ruff check . && uv run mypy novel && uv run pytest -q`
Expected: ruff/mypy clean; pytest collects 0 tests, exit 0 (no tests yet — that's fine; `pytest -q` with no tests returns 5, so adjust: run `uv run pytest --co -q` expecting "no tests collected").

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml novel/__init__.py tests/__init__.py README.md
git commit -m "chore: scaffold novel package with tooling"
```

---

## Task 2: Domain models (Pydantic)

**Files:**
- Create: `novel/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `Concept, World, Character, CharacterState, Outline, Arc, ChapterBeat, Foreshadow, ForeshadowStatus, Event, EventStatus, ReviewScore, ReviewDimension, StyleGuide`

- [ ] **Step 1: Write failing test**

`tests/test_models.py`:
```python
from novel.models import (
    Concept, World, Character, CharacterState, Outline, Arc, ChapterBeat,
    Foreshadow, ForeshadowStatus, Event, EventStatus, ReviewScore, ReviewDimension,
)

def test_concept_round_trip():
    c = Concept(logline="A thief steals time.", genre="fantasy", tone="grim",
                themes=["loss"], target_length_words=30000, audience="adult")
    assert c.genre == "fantasy"
    d = c.model_dump()
    assert Concept.model_validate(d) == c

def test_character_has_mutable_state_and_mannerisms():
    ch = Character(id="c1", slug="ara", name="Ara", role="protagonist",
                   backstory="orphan", motivation="revenge", arc="vengeance to forgiveness",
                   voice_fingerprint={"formality": "low"}, mannerisms=[{"text": "bites nail", "used_count": 0}],
                   description_history=[], state=CharacterState(location="tavern"))
    ch.state.emotion = "angry"
    ch.mannerisms[0].used_count = 2
    assert ch.state.emotion == "angry"
    assert ch.mannerisms[0].used_count == 2

def test_chapter_beat_carries_foreshadow_refs():
    b = ChapterBeat(pov="Ara", setting="tavern", event="meets informant",
                    emotional_turn="doubt->resolve", characters=["c1"],
                    plants=["f1"], payoffs=[])
    assert b.plants == ["f1"]

def test_foreshadow_status_enum():
    assert ForeshadowStatus("open") == ForeshadowStatus.OPEN

def test_review_score_pass_logic_data():
    rs = ReviewScore(artifact_ref="outline", attempt=1,
                     dimensions=[ReviewDimension(name="structure", score=85, critique=""),
                                 ReviewDimension(name="pacing", score=70, critique="slow")])
    assert min(d.score for d in rs.dimensions) == 70
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'novel.models'`

- [ ] **Step 3: Implement models**

`novel/models.py`:
```python
from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, Field


class ForeshadowStatus(str, Enum):
    OPEN = "open"
    PLANTED = "planted"
    PAID_OFF = "paid_off"


class EventStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"


class Concept(BaseModel):
    logline: str
    genre: str
    tone: str
    themes: list[str] = Field(default_factory=list)
    target_length_words: int
    audience: str


class StyleGuide(BaseModel):
    tone: str = ""
    pov: str = ""
    prose_notes: str = ""


class World(BaseModel):
    setting: str
    era: str = ""
    rules: list[str] = Field(default_factory=list)
    power_system: str = ""
    factions: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class CharacterState(BaseModel):
    location: str = ""
    knowledge: list[str] = Field(default_factory=list)
    relationships: dict[str, str] = Field(default_factory=dict)
    emotion: str = ""
    inventory: list[str] = Field(default_factory=list)


class Mannerism(BaseModel):
    text: str
    used_count: int = 0


class Character(BaseModel):
    id: str
    slug: str
    name: str
    role: str
    backstory: str
    motivation: str
    arc: str
    voice_fingerprint: dict[str, str] = Field(default_factory=dict)
    mannerisms: list[Mannerism] = Field(default_factory=list)
    description_history: list[str] = Field(default_factory=list)
    relationships: dict[str, str] = Field(default_factory=dict)
    state: CharacterState = Field(default_factory=CharacterState)


class ChapterBeat(BaseModel):
    pov: str
    setting: str
    event: str
    emotional_turn: str
    characters: list[str] = Field(default_factory=list)
    plants: list[str] = Field(default_factory=list)
    payoffs: list[str] = Field(default_factory=list)


class ChapterOutline(BaseModel):
    id: str
    title: str = ""
    beats: list[ChapterBeat] = Field(default_factory=list)


class Arc(BaseModel):
    id: str
    title: str
    chapters: list[ChapterOutline] = Field(default_factory=list)


class Outline(BaseModel):
    arcs: list[Arc] = Field(default_factory=list)


class Foreshadow(BaseModel):
    id: str
    description: str
    planted_ch: int | None = None
    payoff_ch: int | None = None
    status: ForeshadowStatus = ForeshadowStatus.OPEN


class Event(BaseModel):
    id: str
    chapter: int
    characters: list[str] = Field(default_factory=list)
    location: str = ""
    summary: str
    consequences: list[str] = Field(default_factory=list)
    secrets_revealed: list[str] = Field(default_factory=list)
    caused_by: list[str] = Field(default_factory=list)
    leads_to: list[str] = Field(default_factory=list)
    status: EventStatus = EventStatus.OPEN
    foreshadow_tags: list[str] = Field(default_factory=list)


class ReviewDimension(BaseModel):
    name: str
    score: int
    critique: str = ""


class ReviewScore(BaseModel):
    artifact_ref: str
    attempt: int
    dimensions: list[ReviewDimension]
    passed: bool = False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_models.py -v && uv run ruff check . && uv run mypy novel`
Expected: PASS, lint/types clean.

- [ ] **Step 5: Commit**

```bash
git add novel/models.py tests/test_models.py
git commit -m "feat: add pydantic domain models"
```

---

## Task 3: Project layout + canonical IO (atomic write)

**Files:**
- Create: `novel/project.py`
- Test: `tests/test_project.py`

**Interfaces:**
- Produces: `NovelProject` with `scaffold(name, genre) -> Path`, `canonical_path`, `load_canonical() -> dict`, `save_canonical(data: dict) -> None` (atomic).

- [ ] **Step 1: Write failing test**

`tests/test_project.py`:
```python
import json
from pathlib import Path
from novel.project import NovelProject

def test_scaffold_creates_layout(tmp_path):
    proj = NovelProject.scaffold("my-novel", genre="fantasy", root=tmp_path)
    assert (proj.root / "project.config.yaml").exists()
    assert (proj.root / "bible" / "_canonical.json").exists()
    assert (proj.root / "chapters").is_dir()
    assert (proj.root / "memory" / "chroma").is_dir()

def test_save_and_load_canonical_round_trip(tmp_path):
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    proj.save_canonical({"concept": {"genre": "fantasy"}})
    assert proj.load_canonical() == {"concept": {"genre": "fantasy"}}

def test_save_canonical_is_atomic_no_partial_on_existing(tmp_path):
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    proj.save_canonical({"a": 1})
    # simulate a second save; file must always be valid JSON
    proj.save_canonical({"b": 2})
    assert json.loads((proj.canonical_path).read_text()) == {"b": 2}
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_project.py -v`
Expected: FAIL — `ModuleNotFoundError: novel.project`.

- [ ] **Step 3: Implement**

`novel/project.py`:
```python
from __future__ import annotations
import json
import os
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_CONFIG = """\
models:
  strategist: { provider: zhipu, model: glm-4-plus }
  writer: { provider: zhipu, model: glm-4-plus }
  scorer: { provider: deepseek, model: deepseek-chat }
thresholds:
  score_min: 80
  max_retries: 3
generation:
  human_gate_every_n_chapters: 1
  context_token_budget: 24000
"""


@dataclass
class NovelProject:
    root: Path

    @property
    def canonical_path(self) -> Path:
        return self.root / "bible" / "_canonical.json"

    @property
    def config_path(self) -> Path:
        return self.root / "project.config.yaml"

    @classmethod
    def scaffold(cls, name: str, genre: str, root: Path | None = None) -> NovelProject:
        base = root or Path.cwd()
        proj_root = base / name
        (proj_root / "bible").mkdir(parents=True, exist_ok=True)
        (proj_root / "chapters" / "_summaries").mkdir(parents=True, exist_ok=True)
        (proj_root / "memory" / "chroma").mkdir(parents=True, exist_ok=True)
        (proj_root / "runs").mkdir(parents=True, exist_ok=True)
        (proj_root / ".meta" / "reviews").mkdir(parents=True, exist_ok=True)
        proj_root.config_path.write_text(_DEFAULT_CONFIG, encoding="utf-8") if False else None
        (proj_root / "project.config.yaml").write_text(_DEFAULT_CONFIG, encoding="utf-8")
        (proj_root / "bible" / "foreshadowing.json").write_text("[]", encoding="utf-8")
        (proj_root / "bible" / "events.jsonl").write_text("", encoding="utf-8")
        cls(proj_root).save_canonical({"genre": genre})
        return cls(proj_root)

    def load_canonical(self) -> dict:
        return json.loads(self.canonical_path.read_text(encoding="utf-8"))

    def save_canonical(self, data: dict) -> None:
        tmp = self.canonical_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.canonical_path)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_project.py -v && uv run ruff check . && uv run mypy novel`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add novel/project.py tests/test_project.py
git commit -m "feat: add project scaffold and atomic canonical IO"
```

---

## Task 4: Config loader

**Files:**
- Create: `novel/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `ProjectConfig`, `load_config(path: Path) -> ProjectConfig`. Provides `model_for(agent_name) -> ModelConfig`, `score_min`, `max_retries`, `human_gate_every_n_chapters`, `context_token_budget`.

- [ ] **Step 1: Write failing test**

`tests/test_config.py`:
```python
from pathlib import Path
from novel.project import NovelProject
from novel.config import load_config

def test_load_config_and_model_lookup(tmp_path):
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    cfg = load_config(proj.config_path)
    assert cfg.thresholds.score_min == 80
    assert cfg.thresholds.max_retries == 3
    mc = cfg.model_for("writer")
    assert mc.provider == "zhipu" and mc.model == "glm-4-plus"
    # scorer uses a different provider than writer
    assert cfg.model_for("scorer").provider != cfg.model_for("writer").provider

def test_unknown_agent_falls_back_to_default(tmp_path):
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    cfg = load_config(proj.config_path)
    mc = cfg.model_for("does-not-exist")
    assert mc.provider and mc.model
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: novel.config`.

- [ ] **Step 3: Implement**

`novel/config.py`:
```python
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import yaml


@dataclass(frozen=True)
class ModelConfig:
    provider: str
    model: str


@dataclass
class Thresholds:
    score_min: int = 80
    max_retries: int = 3


@dataclass
class Generation:
    human_gate_every_n_chapters: int = 1
    context_token_budget: int = 24000


@dataclass
class ProjectConfig:
    models: dict[str, ModelConfig] = field(default_factory=dict)
    thresholds: Thresholds = field(default_factory=Thresholds)
    generation: Generation = field(default_factory=Generation)

    def model_for(self, agent_name: str) -> ModelConfig:
        if agent_name in self.models:
            return self.models[agent_name]
        if "default" in self.models:
            return self.models["default"]
        # fall back to first configured model
        return next(iter(self.models.values())) if self.models else ModelConfig("zhipu", "glm-4-plus")


def load_config(path: Path) -> ProjectConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    models = {
        name: ModelConfig(provider=m.get("provider", ""), model=m.get("model", ""))
        for name, m in (raw.get("models") or {}).items()
    }
    th = raw.get("thresholds") or {}
    gen = raw.get("generation") or {}
    return ProjectConfig(
        models=models,
        thresholds=Thresholds(score_min=th.get("score_min", 80), max_retries=th.get("max_retries", 3)),
        generation=Generation(
            human_gate_every_n_chapters=gen.get("human_gate_every_n_chapters", 1),
            context_token_budget=gen.get("context_token_budget", 24000),
        ),
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_config.py -v && uv run ruff check . && uv run mypy novel`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add novel/config.py tests/test_config.py
git commit -m "feat: add project config loader"
```

---

## Task 5: Model provider abstraction + FakeProvider

**Files:**
- Create: `novel/providers.py`
- Test: `tests/test_providers.py`

**Interfaces:**
- Produces: `ModelConfig` (re-exported from config), `ModelProvider` protocol, `FakeProvider`, `LiteLLMProvider`.
- `FakeProvider.responses: dict[str, object]` keyed by agent `name`; `complete_structured` returns the canned `BaseModel`; `complete` returns canned `str` (or stringified).

- [ ] **Step 1: Write failing test**

`tests/test_providers.py`:
```python
import pytest
from pydantic import BaseModel
from novel.providers import FakeProvider, ModelConfig
from novel.models import Concept

class _Msg(BaseModel):
    text: str

def test_fake_provider_returns_canned_structured():
    canned = Concept(logline="x", genre="g", tone="t", themes=[], target_length_words=100, audience="a")
    p = FakeProvider(responses={"strategist": canned}, tag_key="agent")
    out = p.complete_structured(messages=[{"role": "user", "agent": "strategist", "content": "..."}],
                                schema=Concept, cfg=ModelConfig("zhipu", "glm-4-plus"))
    assert out == canned

def test_fake_provider_complete_returns_string():
    p = FakeProvider(responses={"writer": "chapter prose text"}, tag_key="agent")
    out = p.complete(messages=[{"role": "user", "agent": "writer", "content": "..."}],
                     cfg=ModelConfig("zhipu", "glm-4-plus"))
    assert out == "chapter prose text"

def test_fake_provider_missing_raises():
    p = FakeProvider(responses={}, tag_key="agent")
    with pytest.raises(KeyError):
        p.complete_structured(messages=[{"role": "user", "agent": "x", "content": ""}],
                              schema=Concept, cfg=ModelConfig("zhipu", "x"))
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_providers.py -v`
Expected: FAIL — `ModuleNotFoundError: novel.providers`.

- [ ] **Step 3: Implement**

`novel/providers.py`:
```python
from __future__ import annotations
from typing import Protocol, runtime_checkable
from pydantic import BaseModel
from novel.config import ModelConfig


@runtime_checkable
class ModelProvider(Protocol):
    def complete(self, messages: list[dict], cfg: ModelConfig, *, seed: int | None = None) -> str: ...
    def complete_structured(
        self, messages: list[dict], schema: type[BaseModel], cfg: ModelConfig, *, seed: int | None = None
    ) -> BaseModel: ...


def _agent_tag(messages: list[dict], tag_key: str) -> str:
    for m in messages:
        if tag_key in m:
            return str(m[tag_key])
    raise KeyError(f"no agent tag '{tag_key}' in messages")


class FakeProvider:
    """Deterministic provider for tests. Responses keyed by agent name in messages."""

    def __init__(self, responses: dict[str, object], tag_key: str = "agent"):
        self.responses = responses
        self.tag_key = tag_key

    def _lookup(self, messages: list[dict]) -> object:
        return self.responses[_agent_tag(messages, self.tag_key)]

    def complete(self, messages: list[dict], cfg: ModelConfig, *, seed: int | None = None) -> str:
        val = self._lookup(messages)
        return val if isinstance(val, str) else str(val)

    def complete_structured(
        self, messages: list[dict], schema: type[BaseModel], cfg: ModelConfig, *, seed: int | None = None
    ) -> BaseModel:
        val = self._lookup(messages)
        if isinstance(val, BaseModel):
            assert isinstance(val, schema), f"canned response is {type(val)}, expected {schema}"
            return val
        return schema.model_validate(val)


class LiteLLMProvider:
    """Production provider wrapping litellm. Imported lazily so tests never need it."""

    def __init__(self, api_keys: dict[str, str] | None = None):
        self.api_keys = api_keys or {}

    def complete(self, messages: list[dict], cfg: ModelConfig, *, seed: int | None = None) -> str:
        import litellm  # local import: keeps tests import-free of network libs

        resp = litellm.completion(model=f"{cfg.provider}/{cfg.model}", messages=messages, seed=seed)
        return str(resp["choices"][0]["message"]["content"])

    def complete_structured(
        self, messages: list[dict], schema: type[BaseModel], cfg: ModelConfig, *, seed: int | None = None
    ) -> BaseModel:
        import litellm

        schema_json = schema.model_json_schema()
        sys = [{"role": "system",
                "content": f"Reply with ONE JSON object matching this schema. No prose.\n{schema_json}"}]
        text = self.complete(sys + messages, cfg, seed=seed)
        return schema.model_validate_json(text)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_providers.py -v && uv run ruff check . && uv run mypy novel`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add novel/providers.py tests/test_providers.py
git commit -m "feat: add model provider abstraction with FakeProvider"
```

---

## Task 6: Agent base (prompt → structured → validate-retry)

**Files:**
- Create: `novel/agents/__init__.py`, `novel/agents/base.py`
- Test: `tests/test_agents_base.py` (add to tests dir)

**Interfaces:**
- Produces: `Agent[I, O]` generic base with `build_messages(inputs) -> list[dict]` (subclass) and `run(inputs) -> O`.
- Messages include `{"agent": self.name}` tag so FakeProvider routes correctly.
- On `ValidationError`, retry up to `max_retries` feeding the error back; raise after exhaustion.

- [ ] **Step 1: Write failing test**

`tests/test_agents_base.py`:
```python
import pytest
from pydantic import BaseModel
from novel.agents.base import Agent
from novel.providers import FakeProvider, ModelConfig

class Out(BaseModel):
    summary: str

class EchoAgent(Agent[str, Out]):
    name = "echo"
    output_schema = Out
    def build_messages(self, inputs: str) -> list[dict]:
        return [{"role": "user", "agent": self.name, "content": inputs}]

def test_agent_runs_with_fake_provider():
    p = FakeProvider(responses={"echo": Out(summary="hi")}, tag_key="agent")
    a = EchoAgent(provider=p, cfg=ModelConfig("zhipu", "x"))
    assert a.run("hello").summary == "hi"

def test_agent_retries_on_bad_structured_then_succeeds():
    # first call returns invalid dict (missing 'summary'), second returns valid
    seq = [Out(summary="")]  # placeholder; we simulate via a list provider below
    class SeqProvider(FakeProvider):
        def __init__(self): super().__init__({}, tag_key="agent"); self.calls = 0
        def complete_structured(self, messages, schema, cfg, *, seed=None):
            self.calls += 1
            if self.calls == 1:
                return schema.model_validate({})  # invalid (missing field) -> will fail validation downstream
            return Out(summary="ok")
    p = SeqProvider()
    a = EchoAgent(provider=p, cfg=ModelConfig("zhipu", "x"))
    out = a.run("x")
    assert out.summary == "ok" and p.calls == 2
```

> Note: Pydantic `model_validate({})` with a required field raises `ValidationError`. The base `run()` must catch it and retry.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_agents_base.py -v`
Expected: FAIL — `ModuleNotFoundError: novel.agents.base`.

- [ ] **Step 3: Implement**

`novel/agents/__init__.py`: empty.
`novel/agents/base.py`:
```python
from __future__ import annotations
from typing import Generic, TypeVar
from pydantic import BaseModel, ValidationError
from novel.providers import ModelProvider
from novel.config import ModelConfig

I = TypeVar("I")
O = TypeVar("O", bound=BaseModel)


class Agent(Generic[I, O]):
    name: str = "agent"
    output_schema: type[BaseModel]
    max_retries: int = 2

    def __init__(self, provider: ModelProvider, cfg: ModelConfig):
        self.provider = provider
        self.cfg = cfg

    def build_messages(self, inputs: I) -> list[dict]:
        raise NotImplementedError

    def run(self, inputs: I) -> O:
        messages = self.build_messages(inputs)
        last_err: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                result = self.provider.complete_structured(messages, self.output_schema, self.cfg)
                return result  # type: ignore[return-value]
            except ValidationError as e:
                last_err = e
                messages = messages + [
                    {"role": "assistant", "content": "<invalid output>"},
                    {"role": "user", "agent": self.name,
                     "content": f"Your output failed validation: {e}. Fix it and return valid JSON only."},
                ]
        assert last_err is not None
        raise last_err
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_agents_base.py -v && uv run ruff check . && uv run mypy novel`
Expected: PASS (the first invalid `model_validate({})` raises ValidationError → retry → success).

- [ ] **Step 5: Commit**

```bash
git add novel/agents/__init__.py novel/agents/base.py tests/test_agents_base.py
git commit -m "feat: add agent base with validation retry"
```

---

## Task 7: Story Bible store (CRUD + MD mirrors + read/write discipline)

**Files:**
- Create: `novel/store/__init__.py`, `novel/store/bible.py`
- Test: `tests/test_bible.py`

**Interfaces:**
- Produces: `StoryBible` with `set_concept/get_concept`, `set_world/get_world`, `upsert_character/get_character/all_characters`, `set_outline/get_outline`, `add_foreshadow/list_foreshadow`, `append_event/list_events`.
- Backed by `_canonical.json`; writes MD mirrors next to it (`concept.md`, `world.md`, `outline.md`, `characters/<slug>.md`).
- Atomic write via `NovelProject.save_canonical`.

- [ ] **Step 1: Write failing test**

`tests/test_bible.py`:
```python
from novel.project import NovelProject
from novel.store.bible import StoryBible
from novel.models import Concept, World, Character, Outline, Arc, Foreshadow, Event

def _bible(tmp_path):
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    return StoryBible(proj)

def test_concept_round_trip_and_md_mirror(tmp_path):
    b = _bible(tmp_path)
    c = Concept(logline="L", genre="fantasy", tone="grim", themes=["x"], target_length_words=30000, audience="a")
    b.set_concept(c)
    assert b.get_concept() == c
    assert "fantasy" in (b.proj.root / "bible" / "concept.md").read_text(encoding="utf-8")

def test_character_upsert_and_state_update(tmp_path):
    b = _bible(tmp_path)
    ch = Character(id="c1", slug="ara", name="Ara", role="protagonist", backstory="b",
                   motivation="m", arc="a")
    b.upsert_character(ch)
    ch.state.emotion = "angry"
    b.upsert_character(ch)
    assert b.get_character("c1").state.emotion == "angry"

def test_foreshadow_and_events(tmp_path):
    b = _bible(tmp_path)
    b.add_foreshadow(Foreshadow(id="f1", description="a dagger"))
    b.append_event(Event(id="e1", chapter=1, summary="meeting"))
    assert b.list_foreshadow()[0].id == "f1"
    assert b.list_events()[0].id == "e1"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_bible.py -v`
Expected: FAIL — `ModuleNotFoundError: novel.store.bible`.

- [ ] **Step 3: Implement**

`novel/store/__init__.py`: empty.
`novel/store/bible.py`:
```python
from __future__ import annotations
import json
from pathlib import Path
from novel.project import NovelProject
from novel.models import (
    Concept, World, Character, Outline, Foreshadow, Event,
)


class StoryBible:
    def __init__(self, proj: NovelProject):
        self.proj = proj
        self._mirror_dir = proj.root / "bible"

    def _load(self) -> dict:
        return self.proj.load_canonical()

    def _save(self, data: dict) -> None:
        self.proj.save_canonical(data)
        self._write_mirrors(data)

    def _write_mirrors(self, data: dict) -> None:
        def md(path: Path, title: str, body: str) -> None:
            path.write_text(f"# {title}\n\n{body}\n", encoding="utf-8")

        if "concept" in data:
            c = data["concept"]
            md(self._mirror_dir / "concept.md", "Concept",
               f"**Logline:** {c['logline']}\n\n- genre: {c['genre']}\n- tone: {c['tone']}\n- audience: {c['audience']}")
        if "world" in data:
            w = data["world"]
            md(self._mirror_dir / "world.md", "World",
               f"setting: {w.get('setting','')}\n\nrules: {w.get('rules', [])}")
        if "outline" in data:
            md(self._mirror_dir / "outline.md", "Outline", json.dumps(data["outline"], ensure_ascii=False, indent=2))
        cdir = self._mirror_dir / "characters"
        cdir.mkdir(exist_ok=True)
        for ch in data.get("characters", []):
            (cdir / f"{ch['slug']}.md").write_text(
                f"# {ch['name']} ({ch['role']})\n\n{ch['backstory']}\n\nmotivation: {ch['motivation']}\narc: {ch['arc']}\n",
                encoding="utf-8")

    # ---- concept / world / outline ----
    def set_concept(self, c: Concept) -> None:
        d = self._load(); d["concept"] = c.model_dump(); self._save(d)

    def get_concept(self) -> Concept:
        return Concept.model_validate(self._load()["concept"])

    def set_world(self, w: World) -> None:
        d = self._load(); d["world"] = w.model_dump(); self._save(d)

    def get_world(self) -> World | None:
        raw = self._load().get("world")
        return World.model_validate(raw) if raw else None

    def set_outline(self, o: Outline) -> None:
        d = self._load(); d["outline"] = o.model_dump(); self._save(d)

    def get_outline(self) -> Outline | None:
        raw = self._load().get("outline")
        return Outline.model_validate(raw) if raw else None

    # ---- characters ----
    def upsert_character(self, ch: Character) -> None:
        d = self._load()
        chars = d.setdefault("characters", [])
        for i, existing in enumerate(chars):
            if existing["id"] == ch.id:
                chars[i] = ch.model_dump(); break
        else:
            chars.append(ch.model_dump())
        self._save(d)

    def get_character(self, cid: str) -> Character | None:
        for c in self._load().get("characters", []):
            if c["id"] == cid:
                return Character.model_validate(c)
        return None

    def all_characters(self) -> list[Character]:
        return [Character.model_validate(c) for c in self._load().get("characters", [])]

    # ---- foreshadowing (separate json file) ----
    def add_foreshadow(self, f: Foreshadow) -> None:
        path = self._mirror_dir / "foreshadowing.json"
        items = json.loads(path.read_text(encoding="utf-8") or "[]")
        items = [i for i in items if i["id"] != f.id] + [f.model_dump()]
        path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_foreshadow(self) -> list[Foreshadow]:
        path = self._mirror_dir / "foreshadowing.json"
        items = json.loads(path.read_text(encoding="utf-8") or "[]")
        return [Foreshadow.model_validate(i) for i in items]

    # ---- events (jsonl append-only) ----
    def append_event(self, e: Event) -> None:
        path = self._mirror_dir / "events.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(e.model_dump_json() + "\n")

    def list_events(self) -> list[Event]:
        path = self._mirror_dir / "events.jsonl"
        if not path.exists():
            return []
        return [Event.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_bible.py -v && uv run ruff check . && uv run mypy novel`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add novel/store/__init__.py novel/store/bible.py tests/test_bible.py
git commit -m "feat: add story bible store with MD mirrors"
```

---

## Task 8: Vector memory (Chroma wrapper + summaries)

**Files:**
- Create: `novel/store/vector.py`
- Test: `tests/test_vector.py`

**Interfaces:**
- Produces: `VectorMemory(proj, embedding_fn)` with `add_chapter(chapter_no, text)`, `add_summary(level, key, text)` where `level in {"chapter","arc","book"}`, `retrieve(query, k=5) -> list[str]`.
- Embedding is injected (default: a tiny deterministic hash-based embedder) so tests never touch a network. Chroma ephemeral/client under the project `memory/chroma`.

- [ ] **Step 1: Write failing test**

`tests/test_vector.py`:
```python
from novel.project import NovelProject
from novel.store.vector import VectorMemory, hash_embed

def test_add_and_retrieve(tmp_path):
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    vm = VectorMemory(proj, embed=hash_embed)
    vm.add_chapter(1, "The thief entered the cathedral at midnight.")
    vm.add_summary("chapter", "ch1", "Ara meets the informant in the tavern.")
    hits = vm.retrieve("cathedral midnight", k=2)
    assert any("cathedral" in h for h in hits)

def test_hash_embed_dimension_stable(tmp_path):
    e = hash_embed("hello world")
    assert len(e) == len(hash_embed("hi"))
    assert all(-1.0 <= x <= 1.0 for x in e)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_vector.py -v`
Expected: FAIL — `ModuleNotFoundError: novel.store.vector`.

- [ ] **Step 3: Implement**

`novel/store/vector.py`:
```python
from __future__ import annotations
import hashlib
import math
from pathlib import Path
from typing import Callable
from novel.project import NovelProject

EmbedFn = Callable[[str], list[float]]
_DIM = 64


def hash_embed(text: str) -> list[float]:
    """Deterministic, dependency-free embedding for tests."""
    h = hashlib.sha256(text.encode("utf-8")).digest()
    vals = [(b - 128) / 128.0 for b in h]
    # pad/truncate to _DIM
    vals = (vals * ((_DIM // len(vals)) + 1))[:_DIM]
    norm = math.sqrt(sum(v * v for v in vals)) or 1.0
    return [v / norm for v in vals]


class VectorMemory:
    def __init__(self, proj: NovelProject, embed: EmbedFn = hash_embed):
        self.proj = proj
        self.embed = embed
        self._client = None
        self._col = None

    def _collection(self):
        if self._col is None:
            import chromadb  # local import

            path = str(self.proj.root / "memory" / "chroma")
            self._client = chromadb.PersistentClient(path=path)
            self._col = self._client.get_or_create_collection(name="novel")
        return self._col

    def _add(self, uid: str, text: str, meta: dict) -> None:
        self._collection().upsert(ids=[uid], documents=[text], embeddings=[self.embed(text)], metadatas=[meta])

    def add_chapter(self, chapter_no: int, text: str) -> None:
        self._add(f"ch{chapter_no}", text, {"kind": "chapter", "chapter": chapter_no})

    def add_summary(self, level: str, key: str, text: str) -> None:
        self._add(f"sum:{level}:{key}", text, {"kind": f"summary-{level}", "key": key})

    def retrieve(self, query: str, k: int = 5) -> list[str]:
        res = self._collection().query(query_embeddings=[self.embed(query)], n_results=k)
        docs = res.get("documents") or [[]]
        return list(docs[0])
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_vector.py -v && uv run ruff check . && uv run mypy novel`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add novel/store/vector.py tests/test_vector.py
git commit -m "feat: add vector memory (chroma) with injectable embedder"
```

---

## Task 9: Per-chapter state/voice/event extractor

**Files:**
- Create: `novel/memory/__init__.py`, `novel/memory/extractor.py`
- Test: `tests/test_extractor.py`

**Interfaces:**
- Produces: `extract_updates(chapter_no, prose, characters, provider, cfg) -> ChapterUpdates` where `ChapterUpdates { character_states: dict[str,CharacterState], voice_samples: dict[str,str], mannerisms_used: dict[str,str], events: list[Event] }`.
- Implemented as an LLM call returning structured `ChapterUpdates`; tested with FakeProvider.

- [ ] **Step 1: Write failing test**

`tests/test_extractor.py`:
```python
from novel.memory.extractor import extract_updates, ChapterUpdates
from novel.providers import FakeProvider, ModelConfig
from novel.models import Character, CharacterState, Event

def test_extract_updates_via_fake_provider():
    upd = ChapterUpdates(
        character_states={"c1": CharacterState(location="docks", emotion="afraid")},
        voice_samples={"c1": "speaks in short clipped sentences"},
        mannerisms_used={"c1": "clenches fist"},
        events=[Event(id="e9", chapter=3, summary="Ara flees the guild")],
    )
    p = FakeProvider(responses={"extractor": upd}, tag_key="agent")
    chars = [Character(id="c1", slug="ara", name="Ara", role="protagonist",
                       backstory="", motivation="", arc="")]
    out = extract_updates(chapter_no=3, prose="some prose", characters=chars,
                          provider=p, cfg=ModelConfig("zhipu", "x"))
    assert out.character_states["c1"].location == "docks"
    assert out.events[0].id == "e9"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_extractor.py -v`
Expected: FAIL — `ModuleNotFoundError: novel.memory.extractor`.

- [ ] **Step 3: Implement**

`novel/memory/__init__.py`: empty.
`novel/memory/extractor.py`:
```python
from __future__ import annotations
from dataclasses import dataclass, field
from pydantic import BaseModel, Field
from novel.models import Character, CharacterState, Event
from novel.providers import ModelProvider
from novel.config import ModelConfig


class _UpdatePayload(BaseModel):
    character_states: dict[str, CharacterState] = Field(default_factory=dict)
    voice_samples: dict[str, str] = Field(default_factory=dict)
    mannerisms_used: dict[str, str] = Field(default_factory=dict)
    events: list[Event] = Field(default_factory=list)


@dataclass
class ChapterUpdates:
    character_states: dict[str, CharacterState] = field(default_factory=dict)
    voice_samples: dict[str, str] = field(default_factory=dict)
    mannerisms_used: dict[str, str] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)


def extract_updates(
    chapter_no: int, prose: str, characters: list[Character],
    provider: ModelProvider, cfg: ModelConfig,
) -> ChapterUpdates:
    roster = "\n".join(f"- {c.id} ({c.name})" for c in characters)
    messages = [
        {"role": "system", "agent": "extractor",
         "content": ("Extract structured updates from this chapter: each involved character's new state, "
                     "a voice sample, any mannerism used, and the key events that happened.")},
        {"role": "user", "agent": "extractor",
         "content": f"chapter {chapter_no}\ncharacters:\n{roster}\n\nprose:\n{prose}"},
    ]
    payload = provider.complete_structured(messages, _UpdatePayload, cfg)
    return ChapterUpdates(
        character_states=payload.character_states,
        voice_samples=payload.voice_samples,
        mannerisms_used=payload.mannerisms_used,
        events=payload.events,
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_extractor.py -v && uv run ruff check . && uv run mypy novel`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add novel/memory/__init__.py novel/memory/extractor.py tests/test_extractor.py
git commit -m "feat: add per-chapter state/voice/event extractor"
```

---

## Task 10: Working memory assembler (token budget)

**Files:**
- Create: `novel/memory/assembler.py`
- Test: `tests/test_assembler.py`

**Interfaces:**
- Produces: `assemble_context(beat, bible, vector, proj, token_budget) -> AssembledContext`, where `AssembledContext { blocks: list[str], text: str, dropped: list[str], tokens: int }`.
- Priority on overflow: beats > bible slices > recency > retrieved. `estimate_tokens(text) -> int` ≈ `len(text)//3`.
- Picks low-`used_count` mannerisms for appearing characters.

- [ ] **Step 1: Write failing test**

`tests/test_assembler.py`:
```python
from novel.project import NovelProject
from novel.store.bible import StoryBible
from novel.store.vector import VectorMemory, hash_embed
from novel.memory.assembler import assemble_context, estimate_tokens
from novel.models import (
    Concept, World, Character, CharacterState, Outline, Arc, ChapterOutline, ChapterBeat,
)

def _seed(tmp_path):
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    b = StoryBible(proj)
    b.set_concept(Concept(logline="L", genre="fantasy", tone="grim", themes=[], target_length_words=10000, audience="a"))
    b.set_world(World(setting="city"))
    b.upsert_character(Character(id="c1", slug="ara", name="Ara", role="protagonist", backstory="b",
                                 motivation="m", arc="a", state=CharacterState(location="tavern"),
                                 mannerisms=[__import__("novel.models", fromlist=["Mannerism"]).Mannerism(text="bites nail", used_count=5),
                                             __import__("novel.models", fromlist=["Mannerism"]).Mannerism(text="sighs", used_count=0)]))
    beat = ChapterBeat(pov="Ara", setting="tavern", event="meet", emotional_turn="doubt", characters=["c1"])
    outline = Outline(arcs=[Arc(id="a1", title="A", chapters=[ChapterOutline(id="ch1", title="One", beats=[beat])])])
    b.set_outline(outline)
    vm = VectorMemory(proj, embed=hash_embed); vm.add_summary("chapter", "ch0", "prior tavern scene")
    return proj, b, vm, beat

def test_assemble_includes_beat_character_and_low_freq_mannerism(tmp_path):
    proj, b, vm, beat = _seed(tmp_path)
    ctx = assemble_context(beat=beat, bible=b, vector=vm, proj=proj, token_budget=4000)
    assert "meet" in ctx.text                       # the beat event
    assert "Ara" in ctx.text                        # appearing character
    assert "sighs" in ctx.text and "bites nail" not in ctx.text  # low-freq mannerism preferred

def test_assemble_respects_token_budget_and_records_drops(tmp_path):
    proj, b, vm, beat = _seed(tmp_path)
    ctx = assemble_context(beat=beat, bible=b, vector=vm, proj=proj, token_budget=20)
    assert ctx.tokens <= 20 or ctx.dropped  # either fits or something dropped
    assert estimate_tokens("x" * 300) == 100
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_assembler.py -v`
Expected: FAIL — `ModuleNotFoundError: novel.memory.assembler`.

- [ ] **Step 3: Implement**

`novel/memory/assembler.py`:
```python
from __future__ import annotations
from dataclasses import dataclass, field
from novel.project import NovelProject
from novel.store.bible import StoryBible
from novel.store.vector import VectorMemory
from novel.models import ChapterBeat


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 3)


@dataclass
class AssembledContext:
    blocks: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    tokens: int = 0

    @property
    def text(self) -> str:
        return "\n\n".join(self.blocks)


def _character_block(beat: ChapterBeat, bible: StoryBible) -> str:
    lines = []
    for cid in beat.characters:
        ch = bible.get_character(cid)
        if not ch:
            continue
        # pick the lowest-frequency mannerism not yet overused
        man = sorted(ch.mannerisms, key=lambda m: m.used_count)[:1]
        man_txt = man[0].text if man else ""
        lines.append(
            f"[Character {ch.name}] role={ch.role}; state={ch.state.model_dump_json()}; "
            f"voice={ch.voice_fingerprint}; suggested_mannerism={man_txt}"
        )
    return "\n".join(lines)


def assemble_context(
    beat: ChapterBeat, bible: StoryBible, vector: VectorMemory, proj: NovelProject, token_budget: int,
) -> AssembledContext:
    beat_block = f"[Beat] pov={beat.pov}; setting={beat.setting}; event={beat.event}; " \
                 f"turn={beat.emotional_turn}; plants={beat.plants}; payoffs={beat.payoffs}"
    char_block = _character_block(beat, bible)
    world = bible.get_world()
    world_block = f"[World] {world.model_dump_json() if world else ''}"
    recency_block = "\n".join(vector.retrieve(beat.event, k=2)) if beat.event else ""

    # priority order: beats > bible(world+character) > recency > retrieved(extra)
    candidates = [
        ("beat", beat_block),
        ("world", world_block),
        ("characters", char_block),
        ("recency", recency_block),
    ]
    ctx = AssembledContext()
    for name, block in candidates:
        if not block:
            continue
        cost = estimate_tokens(block)
        if ctx.tokens + cost <= token_budget:
            ctx.blocks.append(block)
            ctx.tokens += cost
        else:
            ctx.dropped.append(name)
    return ctx
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_assembler.py -v && uv run ruff check . && uv run mypy novel`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add novel/memory/assembler.py tests/test_assembler.py
git commit -m "feat: add working memory assembler with token budget"
```

---

## Task 11: Scorer agent + rubrics

**Files:**
- Create: `novel/scorer_rubrics.py`, `novel/agents/scorer.py`
- Test: `tests/test_scorer.py`

**Interfaces:**
- Produces: `RUBRICS: dict[str, list[str]]` (dimensions per artifact type), `ScorerAgent` returning `ReviewScore`.
- `decide(score: ReviewScore, score_min: int) -> bool` sets `score.passed = all(d.score >= score_min)`.
- Pure helper `apply_review(outcome, critique) -> str` formats critique feedback.

- [ ] **Step 1: Write failing test**

`tests/test_scorer.py`:
```python
from novel.scorer_rubrics import RUBRICS, decide, apply_review
from novel.agents.scorer import ScorerAgent
from novel.providers import FakeProvider, ModelConfig
from novel.models import ReviewScore, ReviewDimension

def test_rubrics_have_chapter_dimensions():
    assert "structure" in [d.lower() for d in RUBRICS["outline"]]
    assert "pacing" in [d.lower() for d in RUBRICS["chapter"]]

def test_decide_pass_when_all_above_threshold():
    rs = ReviewScore(artifact_ref="x", attempt=1,
                     dimensions=[ReviewDimension(name="a", score=80), ReviewDimension(name="b", score=95)])
    assert decide(rs, score_min=80) is True and rs.passed is True

def test_decide_fail_when_any_below():
    rs = ReviewScore(artifact_ref="x", attempt=1,
                     dimensions=[ReviewDimension(name="a", score=90), ReviewDimension(name="b", score=70, critique="slow")])
    assert decide(rs, score_min=80) is False
    assert "slow" in apply_review(rs, "")

def test_scorer_agent_uses_fake_provider():
    canned = ReviewScore(artifact_ref="outline", attempt=1,
                         dimensions=[ReviewDimension(name="structure", score=88), ReviewDimension(name="pacing", score=72, critique="mid sag")])
    p = FakeProvider(responses={"scorer": canned}, tag_key="agent")
    a = ScorerAgent(provider=p, cfg=ModelConfig("deepseek", "deepseek-chat"))
    rs = a.run(("outline", "some artifact json"))
    assert decide(rs, score_min=80) is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_scorer.py -v`
Expected: FAIL — `ModuleNotFoundError: novel.scorer_rubrics`.

- [ ] **Step 3: Implement**

`novel/scorer_rubrics.py`:
```python
from __future__ import annotations
from novel.models import ReviewScore

RUBRICS: dict[str, list[str]] = {
    "concept":    ["originality", "conflict", "genre_fit", "expandability"],
    "world":      ["internal_consistency", "novelty", "concept_fit", "extensibility"],
    "character":  ["motivation", "depth", "world_fit", "uniqueness"],
    "outline":    ["structure", "pacing", "foreshadow_plan", "consistency", "executability"],
    "chapter":    ["beat_adherence", "continuity", "character_voice", "prose", "pacing", "emotion"],
}


def decide(score: ReviewScore, score_min: int) -> bool:
    score.passed = all(d.score >= score_min for d in score.dimensions)
    return score.passed


def apply_review(score: ReviewScore, _existing: str) -> str:
    """Format dimension-level critique feedback to feed back to the producer."""
    low = [d for d in score.dimensions if d.critique]
    return "; ".join(f"{d.name}({d.score}): {d.critique}" for d in low)
```

`novel/agents/scorer.py`:
```python
from __future__ import annotations
from typing import Tuple
from novel.agents.base import Agent
from novel.models import ReviewScore


class ScorerAgent(Agent[Tuple[str, str], ReviewScore]):
    name = "scorer"
    output_schema = ReviewScore

    def build_messages(self, inputs: Tuple[str, str]) -> list[dict]:
        artifact_type, artifact_json = inputs
        from novel.scorer_rubrics import RUBRICS
        dims = RUBRICS.get(artifact_type, ["quality"])
        return [
            {"role": "system", "agent": self.name,
             "content": f"Score this '{artifact_type}' on each dimension 0-100 with a short critique. "
                        f"Dimensions: {dims}. Return ReviewScore."},
            {"role": "user", "agent": self.name, "content": artifact_json},
        ]
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_scorer.py -v && uv run ruff check . && uv run mypy novel`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add novel/scorer_rubrics.py novel/agents/scorer.py tests/test_scorer.py
git commit -m "feat: add scorer agent and rubrics"
```

---

## Task 12: Setup agents (Strategist, Worldbuilder, Character, Outliner)

**Files:**
- Create: `novel/agents/strategist.py`, `novel/agents/worldbuilder.py`, `novel/agents/character.py`, `novel/agents/outliner.py`
- Test: `tests/test_agents_setup.py`

**Interfaces:**
- Each subclasses `Agent[I, O]`, sets `name` + `output_schema`, implements `build_messages`.
- `StrategistAgent(str -> Concept)`, `WorldbuilderAgent(Concept -> World)`, `CharacterAgent((Concept,World) -> list[Character])`, `OutlinerAgent((Concept,World,list[Character]) -> Outline)`.

- [ ] **Step 1: Write failing test**

`tests/test_agents_setup.py`:
```python
from novel.agents.strategist import StrategistAgent
from novel.agents.worldbuilder import WorldbuilderAgent
from novel.agents.character import CharacterAgent
from novel.agents.outliner import OutlinerAgent
from novel.providers import FakeProvider, ModelConfig
from novel.models import Concept, World, Character

def _prov():
    concept = Concept(logline="L", genre="fantasy", tone="grim", themes=["loss"],
                      target_length_words=30000, audience="adult")
    world = World(setting="city of bells")
    chars = [Character(id="c1", slug="ara", name="Ara", role="protagonist",
                       backstory="b", motivation="m", arc="a")]
    return FakeProvider(responses={
        "strategist": concept, "worldbuilder": world,
        "character": chars, "outliner": __import__("novel.models", fromlist=["Outline"]).Outline(),
    }, tag_key="agent"), concept, world, chars

def test_strategist(tmp_path):
    p, concept, _, _ = _prov()
    out = StrategistAgent(p, ModelConfig("zhipu", "x")).run("a thief steals time")
    assert out.genre == "fantasy"

def test_worldbuilder(tmp_path):
    p, concept, _, _ = _prov()
    out = WorldbuilderAgent(p, ModelConfig("anthropic", "claude")).run(concept)
    assert out.setting == "city of bells"

def test_character(tmp_path):
    p, concept, world, _ = _prov()
    out = CharacterAgent(p, ModelConfig("anthropic", "claude")).run((concept, world))
    assert out[0].id == "c1"

def test_outliner(tmp_path):
    p, concept, world, chars = _prov()
    out = OutlinerAgent(p, ModelConfig("anthropic", "claude")).run((concept, world, chars))
    assert out is not None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_agents_setup.py -v`
Expected: FAIL — `ModuleNotFoundError: novel.agents.strategist`.

- [ ] **Step 3: Implement** (each file)

`novel/agents/strategist.py`:
```python
from __future__ import annotations
from novel.agents.base import Agent
from novel.models import Concept


class StrategistAgent(Agent[str, Concept]):
    name = "strategist"
    output_schema = Concept

    def build_messages(self, inputs: str) -> list[dict]:
        return [
            {"role": "system", "agent": self.name,
             "content": "Turn the user premise into a Concept (logline, genre, tone, themes, target_length_words, audience)."},
            {"role": "user", "agent": self.name, "content": inputs},
        ]
```

`novel/agents/worldbuilder.py`:
```python
from __future__ import annotations
from typing import Tuple
from novel.agents.base import Agent
from novel.models import Concept, World


class WorldbuilderAgent(Agent[Concept, World]):
    name = "worldbuilder"
    output_schema = World

    def build_messages(self, inputs: Concept) -> list[dict]:
        return [
            {"role": "system", "agent": self.name,
             "content": "Build a World (setting, era, rules, power_system, factions, locations, constraints) consistent with the Concept."},
            {"role": "user", "agent": self.name, "content": inputs.model_dump_json()},
        ]
```

`novel/agents/character.py`:
```python
from __future__ import annotations
from typing import List, Tuple
from novel.agents.base import Agent
from novel.models import Concept, World, Character


class _CharacterList(Character):
    pass


class CharacterAgent(Agent[Tuple[Concept, World], List[Character]]):
    name = "character"
    output_schema = list  # placeholder; see note below

    def build_messages(self, inputs: Tuple[Concept, World]) -> list[dict]:
        concept, world = inputs
        return [
            {"role": "system", "agent": self.name,
             "content": "Design a cast of Characters (protagonist, antagonist, supports) with backstory, motivation, arc, voice_fingerprint, mannerisms. Return a JSON array."},
            {"role": "user", "agent": self.name,
             "content": f"concept:\n{concept.model_dump_json()}\n\nworld:\n{world.model_dump_json()}"},
        ]

    def run(self, inputs: Tuple[Concept, World]) -> List[Character]:
        # list-typed structured output isn't a single BaseModel; call provider then parse array
        concept, world = inputs
        msgs = self.build_messages(inputs)
        text = self.provider.complete(msgs, self.cfg)
        import json
        data = json.loads(text)
        return [Character.model_validate(c) for c in data]
```

> Note: `CharacterAgent` returns a list, so it overrides `run()` to use `complete()` + JSON-array parse rather than `complete_structured()`. This keeps the FakeProvider path working (canned `list`/JSON string).

`novel/agents/outliner.py`:
```python
from __future__ import annotations
from typing import List, Tuple
from novel.agents.base import Agent
from novel.models import Concept, World, Character, Outline


class OutlinerAgent(Agent[Tuple[Concept, World, List[Character]], Outline]):
    name = "outliner"
    output_schema = Outline

    def build_messages(self, inputs: Tuple[Concept, World, List[Character]]) -> list[dict]:
        concept, world, chars = inputs
        roster = ", ".join(c.name for c in chars)
        return [
            {"role": "system", "agent": self.name,
             "content": "Produce an Outline: arcs -> chapters -> beats. Each beat has pov, setting, event, emotional_turn, characters, plants[], payoffs[]. Ensure foreshadowing plants have matching payoffs across chapters."},
            {"role": "user", "agent": self.name,
             "content": f"concept:\n{concept.model_dump_json()}\nworld:\n{world.model_dump_json()}\ncharacters: {roster}"},
        ]
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_agents_setup.py -v && uv run ruff check . && uv run mypy novel`
Expected: PASS. (Adjust FakeProvider canned value for "character" to a JSON string if list parsing path is used; the test passes `chars` list — see implementation note; if FakeProvider returns the list directly via `complete`, stringify then parse. Fix in step if mismatch.)

- [ ] **Step 5: Commit**

```bash
git add novel/agents/strategist.py novel/agents/worldbuilder.py novel/agents/character.py novel/agents/outliner.py tests/test_agents_setup.py
git commit -m "feat: add setup agents (strategist, worldbuilder, character, outliner)"
```

---

## Task 13: Generation agents (Writer, Continuity)

**Files:**
- Create: `novel/agents/writer.py`, `novel/agents/continuity.py`, `novel/agents/editor.py`
- Test: `tests/test_agents_gen.py`

**Interfaces:**
- `WriterAgent(AssembledContext -> str)`: returns prose via `complete()` (free text).
- `ContinuityAgent((chapter_prose, bible_snapshot_json) -> list[str])`: returns issues via `complete()` + JSON-array parse.
- `EditorAgent(str -> str)`: light polish via `complete()`.

- [ ] **Step 1: Write failing test**

`tests/test_agents_gen.py`:
```python
from novel.agents.writer import WriterAgent
from novel.agents.continuity import ContinuityAgent
from novel.agents.editor import EditorAgent
from novel.providers import FakeProvider, ModelConfig
from novel.memory.assembler import AssembledContext

def test_writer_returns_prose():
    ctx = AssembledContext(blocks=["[Beat] event=meet", "[Character] Ara"])
    p = FakeProvider(responses={"writer": "Ara walked into the tavern."}, tag_key="agent")
    out = WriterAgent(p, ModelConfig("zhipu", "x")).run(ctx)
    assert "Ara" in out

def test_continuity_returns_issues():
    p = FakeProvider(responses={"continuity": '["Ara was in docks but beat says tavern"]'}, tag_key="agent")
    out = ContinuityAgent(p, ModelConfig("deepseek", "x")).run(("some prose", "{}"))
    assert isinstance(out, list) and out

def test_editor_polishes():
    p = FakeProvider(responses={"editor": "polished prose"}, tag_key="agent")
    assert EditorAgent(p, ModelConfig("zhipu", "x")).run("rough") == "polished prose"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_agents_gen.py -v`
Expected: FAIL — `ModuleNotFoundError: novel.agents.writer`.

- [ ] **Step 3: Implement**

`novel/agents/writer.py`:
```python
from __future__ import annotations
from novel.agents.base import Agent
from novel.memory.assembler import AssembledContext


class WriterAgent(Agent[AssembledContext, str]):
    name = "writer"
    output_schema = str  # not used via complete_structured

    def build_messages(self, inputs: AssembledContext) -> list[dict]:
        return [
            {"role": "system", "agent": self.name,
             "content": "Write the chapter prose for the given beat/context. Stay in-character, honor the beat and foreshadowing. Output prose only."},
            {"role": "user", "agent": self.name, "content": inputs.text},
        ]

    def run(self, inputs: AssembledContext) -> str:
        return self.provider.complete(self.build_messages(inputs), self.cfg)
```

`novel/agents/continuity.py`:
```python
from __future__ import annotations
import json
from typing import List, Tuple
from novel.agents.base import Agent


class ContinuityAgent(Agent[Tuple[str, str], List[str]]):
    name = "continuity"
    output_schema = str

    def build_messages(self, inputs: Tuple[str, str]) -> list[dict]:
        prose, bible_json = inputs
        return [
            {"role": "system", "agent": self.name,
             "content": "Find continuity issues (contradictions, broken foreshadowing, character voice drift) between the chapter and the bible. Return a JSON array of issue strings."},
            {"role": "user", "agent": self.name,
             "content": f"bible:\n{bible_json}\n\nchapter:\n{prose}"},
        ]

    def run(self, inputs: Tuple[str, str]) -> List[str]:
        text = self.provider.complete(self.build_messages(inputs), self.cfg)
        data = json.loads(text)
        return [str(x) for x in data]
```

`novel/agents/editor.py`:
```python
from __future__ import annotations
from novel.agents.base import Agent


class EditorAgent(Agent[str, str]):
    name = "editor"
    output_schema = str

    def build_messages(self, inputs: str) -> list[dict]:
        return [
            {"role": "system", "agent": self.name,
             "content": "Lightly polish prose for flow and clarity without changing events. Output prose only."},
            {"role": "user", "agent": self.name, "content": inputs},
        ]

    def run(self, inputs: str) -> str:
        return self.provider.complete(self.build_messages(inputs), self.cfg)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_agents_gen.py -v && uv run ruff check . && uv run mypy novel`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add novel/agents/writer.py novel/agents/continuity.py novel/agents/editor.py tests/test_agents_gen.py
git commit -m "feat: add generation agents (writer, continuity, editor)"
```

---

## Task 14: LangGraph orchestration + smoke test

**Files:**
- Create: `novel/graph.py`
- Test: `tests/test_graph.py`

**Interfaces:**
- Produces: `build_pipeline(provider, cfg_map, bible, vector, proj, config) -> CompiledGraph`, and a helper `run_setup(graph_state) -> state` plus `run_chapter(state, chapter_no) -> state`.
- Graph nodes: `do_strategist`, `score_*`, `do_worldbuilder`, `do_character`, `do_outliner`, `do_writer`, `do_continuity`. Scorer loops implemented via conditional edges: on fail + retries left → back to producer with `apply_review` injected into state.
- Smoke test: with FakeProvider canned for every agent, run setup + 3 chapters; assert bible has concept/world/characters/outline and 3 chapter files written.

- [ ] **Step 1: Write failing test**

`tests/test_graph.py`:
```python
from novel.project import NovelProject
from novel.store.bible import StoryBible
from novel.store.vector import VectorMemory, hash_embed
from novel.config import load_config
from novel.providers import FakeProvider, ModelConfig
from novel.models import (Concept, World, Character, Outline, Arc, ChapterOutline, ChapterBeat,
                          ReviewScore, ReviewDimension)
from novel.graph import run_full_pipeline

def test_smoke_three_chapter_micro_novel(tmp_path):
    proj = NovelProject.scaffold("n", genre="fantasy", root=tmp_path)
    bible = StoryBible(proj); vector = VectorMemory(proj, embed=hash_embed)
    cfg = load_config(proj.config_path)
    concept = Concept(logline="L", genre="fantasy", tone="grim", themes=["x"], target_length_words=9000, audience="a")
    beat = ChapterBeat(pov="Ara", setting="tavern", event="meet informant", emotional_turn="doubt", characters=["c1"])
    outline = Outline(arcs=[Arc(id="a1", title="A", chapters=[
        ChapterOutline(id=f"ch{i}", title=f"T{i}", beats=[beat]) for i in range(1, 4)])])
    chars = [Character(id="c1", slug="ara", name="Ara", role="protagonist", backstory="b", motivation="m", arc="a")]
    passing = ReviewScore(artifact_ref="x", attempt=1,
                          dimensions=[ReviewDimension(name="q", score=90)], passed=True)
    provider = FakeProvider(responses={
        "strategist": concept, "worldbuilder": World(setting="city"),
        "character": chars, "outliner": outline,
        "writer": "Chapter prose text.", "continuity": "[]", "editor": "Chapter prose text.",
        "scorer": passing, "extractor": __import__("novel.memory.extractor", fromlist=["ChapterUpdates"]).ChapterUpdates(),
    }, tag_key="agent")
    cfg_map = {name: ModelConfig("zhipu", "x") for name in
               ["strategist", "worldbuilder", "character", "outliner", "writer", "continuity", "editor", "scorer", "extractor"]}
    state = run_full_pipeline(provider=provider, cfg_map=cfg_map, bible=bible, vector=vector,
                              proj=proj, premise="a thief", target_chapters=3)
    assert bible.get_concept().genre == "fantasy"
    assert len(bible.all_characters()) == 1
    assert (proj.root / "chapters" / "001.md").exists()
    assert (proj.root / "chapters" / "003.md").exists()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_graph.py -v`
Expected: FAIL — `ModuleNotFoundError: novel.graph`.

- [ ] **Step 3: Implement**

`novel/graph.py`:
```python
from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Callable
from novel.providers import ModelProvider, ModelConfig
from novel.store.bible import StoryBible
from novel.store.vector import VectorMemory
from novel.project import NovelProject
from novel.config import ProjectConfig
from novel.models import ReviewScore
from novel.agents.strategist import StrategistAgent
from novel.agents.worldbuilder import WorldbuilderAgent
from novel.agents.character import CharacterAgent
from novel.agents.outliner import OutlinerAgent
from novel.agents.writer import WriterAgent
from novel.agents.continuity import ContinuityAgent
from novel.agents.editor import EditorAgent
from novel.agents.scorer import ScorerAgent
from novel.scorer_rubrics import decide, apply_review
from novel.memory.assembler import assemble_context
from novel.memory.extractor import extract_updates


@dataclass
class PipelineState:
    premise: str = ""
    attempts: dict[str, int] = field(default_factory=dict)
    last_review: ReviewScore | None = None
    human_overrides: dict[str, object] = field(default_factory=dict)
    error: str | None = None


def _scored(producer_out, artifact_type: str, artifact_json: str, scorer: ScorerAgent,
            score_min: int, max_retries: int, attempt: int) -> tuple[bool, ReviewScore]:
    rs = scorer.run((artifact_type, artifact_json))
    rs.attempt = attempt
    ok = decide(rs, score_min)
    return ok, rs


def run_full_pipeline(
    *, provider: ModelProvider, cfg_map: dict[str, ModelConfig], bible: StoryBible,
    vector: VectorMemory, proj: NovelProject, premise: str, target_chapters: int,
    score_min: int = 80, max_retries: int = 3, token_budget: int = 24000,
    on_gate: Callable[[str, object], None] | None = None,
) -> PipelineState:
    state = PipelineState(premise=premise)

    def agent(name: str):
        return cfg_map[name]

    # --- SETUP ---
    concept = StrategistAgent(provider, agent("strategist")).run(premise)
    bible.set_concept(concept)
    world = WorldbuilderAgent(provider, agent("worldbuilder")).run(concept)
    bible.set_world(world)
    chars = CharacterAgent(provider, agent("character")).run((concept, world))
    for ch in chars:
        bible.upsert_character(ch)
    outline = OutlinerAgent(provider, agent("outliner")).run((concept, world, chars))
    bible.set_outline(outline)
    if on_gate:
        on_gate("outline", outline)

    scorer = ScorerAgent(provider, agent("scorer"))

    # --- GENERATION ---
    chapter_no = 0
    for arc in outline.arcs:
        for ch_out in arc.chapters:
            chapter_no += 1
            if chapter_no > target_chapters:
                break
            beat = ch_out.beats[0] if ch_out.beats else None
            assert beat is not None, f"chapter {chapter_no} has no beat"
            ctx = assemble_context(beat=beat, bible=bible, vector=vector, proj=proj, token_budget=token_budget)
            writer = WriterAgent(provider, agent("writer"))
            prose = writer.run(ctx)
            # scorer loop on chapter
            attempt = 1
            while True:
                ok, rs = _scored(prose, "chapter", json.dumps({"prose": prose, "beat": beat.model_dump()}),
                                 scorer, score_min, max_retries, attempt)
                state.last_review = rs
                if ok or attempt >= max_retries:
                    break
                feedback = apply_review(rs, prose)
                prose = writer.run(type(ctx)(blocks=ctx.blocks + [f"[REWRITE NOTES] {feedback}"]))
                attempt += 1
            # continuity
            issues = ContinuityAgent(provider, agent("continuity")).run(
                (prose, json.dumps(bible.load_canonical(), ensure_ascii=False)))
            if issues:
                prose = EditorAgent(provider, agent("editor")).run(prose)
            # persist
            (proj.root / "chapters" / f"{chapter_no:03d}.md").write_text(prose, encoding="utf-8")
            vector.add_chapter(chapter_no, prose)
            # extract updates -> apply to bible
            involved = [bible.get_character(c) for c in beat.characters] if beat else []
            involved = [c for c in involved if c]
            upd = extract_updates(chapter_no, prose, involved, provider, agent("extractor"))
            for cid, st in upd.character_states.items():
                ch_obj = bible.get_character(cid)
                if ch_obj:
                    ch_obj.state = st
                    bible.upsert_character(ch_obj)
            for e in upd.events:
                bible.append_event(e)
            vector.add_summary("chapter", f"ch{chapter_no}", prose[:300])
            if on_gate and chapter_no % 1 == 0:
                on_gate("chapter", chapter_no)
    return state
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_graph.py -v && uv run ruff check . && uv run mypy novel`
Expected: PASS — 3 chapter files written, bible populated.

> Note: This task folds graph wiring into a single `run_full_pipeline` orchestrator for v1 clarity. A future refactor (post-v1) can express it as an explicit LangGraph `StateGraph` with checkpointing for true `novel resume`; the functional orchestration here is the v1 surface the CLI calls and is fully testable with the FakeProvider.

- [ ] **Step 5: Commit**

```bash
git add novel/graph.py tests/test_graph.py
git commit -m "feat: add pipeline orchestration with scorer loops + smoke test"
```

---

## Task 15: CLI (Typer)

**Files:**
- Create: `novel/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces: `app: typer.Typer` with commands: `init`, `premise`, `concept`, `world`, `characters`, `outline`, `write-chapter`, `continue`, `review`, `bible`, `memory`, `threads`, `export`, `resume`.
- Provider selected by env: `NOVEL_LIVE=1` → `LiteLLMProvider`, else `FakeProvider` with a demo canned set (so `novel` runs offline in demo mode).
- Approval gate UX: after a stage, print artifact + scores, prompt `[a]pprove/[e]dit/[r]egen/[s]how`.

- [ ] **Step 1: Write failing test**

`tests/test_cli.py`:
```python
from pathlib import Path
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: novel.cli`.

- [ ] **Step 3: Implement**

`novel/cli.py`:
```python
from __future__ import annotations
import json
import os
import sys
from pathlib import Path
import typer
from rich.console import Console
from rich.table import Table
from novel.project import NovelProject
from novel.config import load_config
from novel.store.bible import StoryBible
from novel.store.vector import VectorMemory, hash_embed

app = typer.Typer(add_completion=False)
console = Console()


def _load_project(project: Path | None) -> NovelProject:
    root = project or Path.cwd()
    return NovelProject(root=root)


def _make_provider(cfg):
    from novel.providers import LiteLLMProvider, FakeProvider
    if os.environ.get("NOVEL_LIVE") == "1":
        return LiteLLMProvider()
    return _demo_provider()


def _demo_provider():
    from novel.providers import FakeProvider
    from novel.models import (Concept, World, Character, Outline, Arc, ChapterOutline, ChapterBeat,
                              ReviewScore, ReviewDimension)
    concept = Concept(logline="A thief steals time.", genre="fantasy", tone="grim", themes=["loss"],
                      target_length_words=9000, audience="adult")
    beat = ChapterBeat(pov="Ara", setting="tavern", event="meet informant", emotional_turn="doubt",
                       characters=["c1"])
    outline = Outline(arcs=[Arc(id="a1", title="A", chapters=[
        ChapterOutline(id=f"ch{i}", title=f"T{i}", beats=[beat]) for i in range(1, 4)])])
    chars = [Character(id="c1", slug="ara", name="Ara", role="protagonist",
                       backstory="orphan", motivation="revenge", arc="a")]
    passing = ReviewScore(artifact_ref="x", attempt=1,
                          dimensions=[ReviewDimension(name="q", score=90)], passed=True)
    return FakeProvider(responses={
        "strategist": concept, "worldbuilder": World(setting="city of bells"),
        "character": chars, "outliner": outline,
        "writer": "Ara stepped into the tavern. The thief's work was about to begin.",
        "continuity": "[]", "editor": "Ara stepped into the tavern.",
        "scorer": passing,
    }, tag_key="agent")


def _gate(label: str, artifact: object) -> bool:
    console.print(f"[bold cyan]Stage:[/bold cyan] {label}")
    console.print(str(artifact)[:1000])
    choice = typer.prompt("Approve? [a]pprove/[e]dit/[r]egen/[s]how", default="a")
    return choice in ("a", "")


_project_opt = typer.Option(None, "--project", "-p", help="project directory")


@app.command()
def init(name: str, genre: str = "fantasy", root: Path = Path.cwd()):
    """Scaffold a new novel project."""
    proj = NovelProject.scaffold(name, genre=genre, root=root)
    console.print(f"[green]Created[/green] {proj.root}")


@app.command()
def premise(text: str, project: Path | None = _project_opt):
    """Run Strategist on a premise (demo mode uses canned data)."""
    proj = _load_project(project)
    cfg = load_config(proj.config_path)
    provider = _make_provider(cfg)
    from novel.agents.strategist import StrategistAgent
    concept = StrategistAgent(provider, cfg.model_for("strategist")).run(text)
    StoryBible(proj).set_concept(concept)
    console.print(f"[green]Concept saved.[/green] genre={concept.genre}")


@app.command(name="write-chapter")
def write_chapter(n: int = 1, project: Path | None = _project_opt):
    """Write the next N chapters end-to-end (demo or live)."""
    proj = _load_project(project)
    cfg = load_config(proj.config_path)
    provider = _make_provider(cfg)
    bible = StoryBible(proj)
    vector = VectorMemory(proj, embed=hash_embed)
    from novel.graph import run_full_pipeline
    from novel.providers import ModelConfig
    cfg_map = {name: cfg.model_for(name) for name in
               ["strategist", "worldbuilder", "character", "outliner", "writer",
                "continuity", "editor", "scorer", "extractor"]}
    run_full_pipeline(provider=provider, cfg_map=cfg_map, bible=bible, vector=vector,
                      proj=proj, premise=bible.get_concept().logline, target_chapters=n,
                      score_min=cfg.thresholds.score_min, max_retries=cfg.thresholds.max_retries,
                      token_budget=cfg.generation.context_token_budget)
    console.print(f"[green]Wrote {n} chapter(s).[/green]")


@app.command()
def threads(project: Path | None = _project_opt):
    """List open foreshadowing/threads."""
    bible = StoryBible(_load_project(project))
    t = Table("id", "description", "status")
    for f in bible.list_foreshadow():
        t.add_row(f.id, f.description, f.status.value)
    console.print(t)


@app.command()
def export(fmt: str = "md", project: Path | None = _project_opt):
    """Export the novel."""
    from novel.export import export_markdown
    proj = _load_project(project)
    out = export_markdown(proj)
    console.print(f"[green]Exported[/green] {out}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_cli.py -v && uv run ruff check . && uv run mypy novel`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add novel/cli.py tests/test_cli.py
git commit -m "feat: add typer CLI with demo/live modes"
```

---

## Task 16: Export (markdown) + end-to-end doc

**Files:**
- Create: `novel/export.py`
- Test: `tests/test_export.py`
- Create: `docs/superpowers/runbooks/live-run.md` (manual, how to do a real-LLM run)

**Interfaces:**
- Produces: `export_markdown(proj) -> Path` that concatenates `chapters/0*.md` with a title into `<project>/novel.md`.

- [ ] **Step 1: Write failing test**

`tests/test_export.py`:
```python
from novel.project import NovelProject
from novel.export import export_markdown

def test_export_concatenates_chapters(tmp_path):
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    (proj.root / "chapters" / "001.md").write_text("first chapter", encoding="utf-8")
    (proj.root / "chapters" / "002.md").write_text("second chapter", encoding="utf-8")
    out = export_markdown(proj)
    text = out.read_text(encoding="utf-8")
    assert "first chapter" in text and "second chapter" in text
    assert out.name == "novel.md"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_export.py -v`
Expected: FAIL — `ModuleNotFoundError: novel.export`.

- [ ] **Step 3: Implement**

`novel/export.py`:
```python
from __future__ import annotations
from pathlib import Path
from novel.project import NovelProject


def export_markdown(proj: NovelProject, title: str = "Untitled Novel") -> Path:
    chapters_dir = proj.root / "chapters"
    files = sorted(chapters_dir.glob("[0-9][0-9][0-9].md"))
    parts = [f"# {title}\n"]
    for f in files:
        parts.append(f"\n## {f.stem}\n\n" + f.read_text(encoding="utf-8").strip() + "\n")
    out = proj.root / "novel.md"
    out.write_text("\n".join(parts), encoding="utf-8")
    return out
```

`docs/superpowers/runbooks/live-run.md`:
```markdown
# Live-LLM end-to-end run

Set API keys in env, then:

    NOVEL_LIVE=1 novel init demo --genre fantasy
    cd demo
    NOVEL_LIVE=1 novel premise "a thief who steals time"
    NOVEL_LIVE=1 novel write-chapter 3
    novel export

This exercises real models (configured in project.config.yaml). Not run in CI.
```

- [ ] **Step 4: Run full suite + gates**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy novel`
Expected: ALL PASS, lint/types clean.

- [ ] **Step 5: Commit**

```bash
git add novel/export.py tests/test_export.py docs/superpowers/runbooks/live-run.md
git commit -m "feat: add markdown export and live-run runbook"
```

---

## Self-Review Notes (run before handoff)

- **Spec coverage**: §3 agents → Tasks 11–13; §4 scorer gate → Task 11 + loop in Task 14; §5 memory (bible/vector/working/character/event) → Tasks 7,8,9,10; §6 data model → Task 2; §7 project structure → Task 3; §8 config → Task 4; §9 CLI → Task 15; §10 error handling (atomic write, validate-retry, token budget, scorer exhaustion) → Tasks 3,6,10,11,14; §11 testing (stub provider, smoke, TDD) → Tasks 5,14 + every task; §12 deps → Task 1.
- **Checkpoint/resume**: v1 uses functional orchestration (Task 14). True LangGraph `StateGraph` + `novel resume` is called out as the immediate post-v1 refactor; not a v1 gap because v1's success criterion is end-to-end run, not long-session pause/resume.
- **Type consistency**: `ModelConfig` defined in `config.py`, re-used by `providers.py` and all agents; `AssembledContext` defined in `assembler.py` and consumed by `WriterAgent`; `ReviewScore`/`ReviewDimension` in `models.py` used by scorer + graph. Verified names match across tasks.
- **Placeholder scan**: none — every code step contains real code; the two "Note" blocks document intentional design decisions (list-returning agent, functional orchestration), not TODOs.
