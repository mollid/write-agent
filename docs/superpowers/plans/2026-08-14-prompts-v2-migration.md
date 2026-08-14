# Prompts v2 Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate all 9 agents to the professional v2 prompts AND align the pydantic models + pipeline consumers + tests to the v2 output schemas (full migration, not a prompt-only swap).

**Architecture:** Five vertical tasks, each self-contained and leaving the suite green. Models migrate incrementally alongside the agent + consumers + tests that depend on them. The integration point (`graph.py`) is edited across Tasks 2–4 for outline / scorer / extractor respectively. `assembler.py` needs no v2 changes (it treats state/world as opaque JSON). Prompt text is taken verbatim from the spec (§ references below); this plan provides the model + consumer code the spec does not specify.

**Tech Stack:** Python 3.11, pydantic 2, uv, pytest, ruff, mypy strict (`disallow_any_generics = false`).

**Spec:** `docs/superpowers/specs/2026-08-14-prompts-v2.md` (gitignored; on disk — read it; agent prompt bodies are copied verbatim from its §1–§9).

## Global Constraints

- `uv run pytest -q`, `uv run ruff check .`, `uv run mypy novel` must all be green before each commit.
- No real LLM in unit tests (FakeProvider, `tag_key="agent"`). Live re-validation is the final task.
- v2 prompt bodies: copy verbatim from the spec §N into each agent's `build_messages`. The `{placeholder}` tokens in the spec are injected via f-string.
- Conventional commits; one commit per task.
- `disallow_any_generics = false` (R4 from v1 still applies; canonical JSON IO is `dict[str, object]`).
- Keep `Event` model rich (it backs `events.jsonl` event memory); map v2 `key_events` → `Event` in the graph.

---

## File Structure (what changes per file)

- `novel/models.py` — `World` (factions/locations → objects), `Outline`/`Arc`/`ChapterOutline`/`ChapterBeat` (rename + `beat_id`), add `ForeshadowLedgerEntry`, restructure `ReviewScore` (+ `DimensionScore`), restructure `CharacterState`, add `KeyEvent`. `Concept`/`Character`/`Mannerism`/`Event`/`Foreshadow` unchanged.
- `novel/agents/*.py` — each `build_messages` rewritten from spec §N; character/continuity retry text updated.
- `novel/memory/extractor.py` — `_UpdatePayload` + `ChapterUpdates` to v2 shape; v2 prompt (spec §9).
- `novel/scorer_rubrics.py` — `decide`/`apply_review` read `ReviewScore.scores` (dict).
- `novel/graph.py` — register `foreshadow_ledger`; consume `mannerisms_used` (list) and `key_events` → `Event`.
- `novel/cli.py` — `_demo_provider` canned values updated to v2 shapes (incrementally across tasks).
- `novel/memory/assembler.py` — **no change** (state/world are opaque JSON to it).
- `tests/*` — fixtures updated to v2 model shapes.

---

### Task 1: Strategist + Worldbuilder + Character (prompts + World model)

**Files:**
- Modify: `novel/models.py` (add `Faction`, `Location`; `World.factions`/`locations` → object lists)
- Modify: `novel/agents/strategist.py`, `novel/agents/worldbuilder.py`, `novel/agents/character.py`
- Test: `tests/test_models.py`, `tests/test_agents_setup.py`

**Interfaces:**
- Produces: `World.factions: list[Faction]`, `World.locations: list[Location]`. Consumers that only call `world.model_dump_json()` (assembler, graph continuity) are unaffected.

- [ ] **Step 1: Add Faction/Location, change World**

In `novel/models.py`, add (before `World`) and update `World`:
```python
class Faction(BaseModel):
    name: str
    ideology: str = ""
    resources: str = ""
    conflict_with: str = ""


class Location(BaseModel):
    name: str
    description: str = ""
    narrative_function: str = ""


class World(BaseModel):
    setting: str
    era: str = ""
    rules: list[str] = Field(default_factory=list)
    power_system: str = ""
    factions: list[Faction] = Field(default_factory=list)
    locations: list[Location] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
```

- [ ] **Step 2: Rewrite the three agents' build_messages from spec §1, §2, §3**

`strategist.py` — system = `STRATEGIST_SYSTEM` (spec §1), user = `STRATEGIST_USER` with `{premise}` = `inputs`:
```python
def build_messages(self, inputs: str) -> list[dict]:
    return [
        {"role": "system", "agent": self.name, "content": STRATEGIST_SYSTEM},
        {"role": "user", "agent": self.name, "content": STRATEGIST_USER.format(premise=inputs)},
    ]
```
Define `STRATEGIST_SYSTEM` / `STRATEGIST_USER` as module constants copied verbatim from spec §1.

`worldbuilder.py` — system = `WORLDBUILDER_SYSTEM`, user uses `{concept_json}` = `inputs.model_dump_json()` (spec §2).

`character.py` — system = `CHARACTER_SYSTEM` with `{character_schema}` = `Character.model_json_schema()`; user uses `{concept_json}` / `{world_json}` (spec §3). Keep the overridden `run()` retry loop; change the retry message to `CHARACTER_RETRY.format(error=e)` (spec §3). Roster note: character agent takes `(concept, world)` — no roster needed (it designs the cast).

- [ ] **Step 3: Update tests**

`tests/test_models.py`: any `World(factions=[...])`/`locations=[...]` string fixtures → use `Faction(name=...)` / `Location(name=...)` or rely on defaults. Add a test that `World` parses a v2 dict with object factions/locations and rejects a `factions: [str]` (coercion: pydantic will error on str→Faction).
`tests/test_agents_setup.py`: the strategist/worldbuilder/character canned outputs already use `Concept`/`World(setting=...)`/`[Character]` — `World(setting="city")` still valid (defaults). If any test asserts on `world.factions` as strings, update to objects.

- [ ] **Step 4: Run gates + commit**

`uv run pytest -q && uv run ruff check . && uv run mypy novel` → green.
Commit: `feat(prompts-v2): strategist/worldbuilder/character prompts + object-typed World`

---

### Task 2: Outliner + Outline model restructure + foreshadow_ledger

**Files:**
- Modify: `novel/models.py` (`Arc`, `ChapterOutline`, `ChapterBeat`, `Outline`, add `ForeshadowLedgerEntry`)
- Modify: `novel/agents/outliner.py` (spec §4)
- Modify: `novel/graph.py` (register ledger after outline)
- Modify: `novel/cli.py` (`_demo_provider` canned `Outline` → v2 shape)
- Test: `tests/test_models.py`, `tests/test_agents_setup.py`, `tests/test_graph.py` (outline fixture), `tests/test_cli.py`

**Interfaces:**
- Produces: `Outline.arcs: list[Arc(arc_name, chapters)]`, `Arc.chapters: list[ChapterOutline(chapter_no, chapter_title, beats)]`, `ChapterBeat` gains `beat_id: str = ""`, `Outline.foreshadow_ledger: list[ForeshadowLedgerEntry]`.
- `graph.py` iterates `outline.arcs` → `.chapters` → `.beats` (unchanged loop shape; uses its own `chapter_no` counter, does not read `Arc.arc_name`/`ChapterOutline.chapter_no`).

- [ ] **Step 1: Restructure outline models**

In `novel/models.py`:
```python
class ChapterBeat(BaseModel):
    beat_id: str = ""
    pov: str
    setting: str
    event: str
    emotional_turn: str
    characters: list[str] = Field(default_factory=list)
    plants: list[str] = Field(default_factory=list)
    payoffs: list[str] = Field(default_factory=list)


class ChapterOutline(BaseModel):
    chapter_no: int
    chapter_title: str = ""
    beats: list[ChapterBeat] = Field(default_factory=list)


class Arc(BaseModel):
    arc_name: str
    chapters: list[ChapterOutline] = Field(default_factory=list)


class ForeshadowLedgerEntry(BaseModel):
    id: str
    planted_in: str = ""
    paid_off_in: str = ""
    description: str = ""


class Outline(BaseModel):
    arcs: list[Arc] = Field(default_factory=list)
    foreshadow_ledger: list[ForeshadowLedgerEntry] = Field(default_factory=list)
```

- [ ] **Step 2: Rewrite outliner build_messages (spec §4)**

`roster_block = "\n".join(f"- {c.id} ({c.name}): {c.role}" for c in chars)`. system = `OUTLINER_SYSTEM` with `{roster_block}` injected; user = `OUTLINER_USER` with concept/world/roster. (Both `OUTLINER_SYSTEM` and `OUTLINER_USER` carry `{roster_block}`; build the system string with `.format(roster_block=roster_block)` and user with `.format(...)`.)

- [ ] **Step 3: Register foreshadow_ledger in graph**

In `novel/graph.py`, after `bible.set_outline(outline)` (setup block) and before the scorer line, add:
```python
for entry in outline.foreshadow_ledger:
    if not any(f.id == entry.id for f in bible.list_foreshadow()):
        bible.add_foreshadow(Foreshadow(
            id=entry.id, description=entry.description,
            planted_ch=_parse_ch(entry.planted_in), status=ForeshadowStatus.OPEN))
```
Add helper near top of graph.py:
```python
def _parse_ch(ref: str) -> int | None:
    """Best-effort: 'c03-b01' / 'ch3' -> 3."""
    import re
    m = re.search(r"(\d+)", ref)
    return int(m.group(1)) if m else None
```
(Import `Foreshadow`, `ForeshadowStatus` from `novel.models`.) Keep the existing per-chapter plant/payoff status-update logic.

- [ ] **Step 4: Update _demo_provider + tests**

`novel/cli.py _demo_provider`: change the canned `outline` to v2 shape, e.g.:
```python
outline = Outline(arcs=[Arc(arc_name="A", chapters=[
    ChapterOutline(chapter_no=i, chapter_title=f"T{i}", beats=[beat]) for i in range(1, 4)])],
    foreshadow_ledger=[])
```
`tests/test_graph.py`: update the smoke `outline` fixture to `Arc(arc_name=...)` / `ChapterOutline(chapter_no=...)`. `tests/test_models.py` + `tests/test_agents_setup.py`: update any `Arc(id=,title=)`/`ChapterOutline(id=,title=)` constructions.

- [ ] **Step 5: Run gates + commit**

Green. Commit: `feat(prompts-v2): outliner prompt + restructured Outline + foreshadow ledger wiring`

---

### Task 3: Scorer + ReviewScore model + rubrics

**Files:**
- Modify: `novel/models.py` (`ReviewScore` → v2; add `DimensionScore`; remove/replace `ReviewDimension`)
- Modify: `novel/agents/scorer.py` (spec §6)
- Modify: `novel/scorer_rubrics.py` (`decide`, `apply_review`)
- Modify: `novel/cli.py` (`_demo_provider` canned `ReviewScore` → v2)
- Test: `tests/test_models.py`, `tests/test_scorer.py`, `tests/test_graph.py` (passing fixture), `tests/test_cli.py`

**Interfaces:**
- Produces: `ReviewScore(artifact_type, scores: dict[str, DimensionScore], overall, summary, attempt, passed)`. `attempt`/`passed` are pipeline-managed (defaults); the model emits `{artifact_type, scores, overall, summary}`.
- `decide(score, score_min)` sets `score.passed = all(ds.score >= score_min for ds in score.scores.values())`.
- `apply_review(score, _existing)` joins `name(score): critique` over `score.scores`.
- `graph._scored` is UNCHANGED (still `rs.attempt = attempt; ok = decide(rs, score_min)`).

- [ ] **Step 1: Restructure ReviewScore**

In `novel/models.py` replace `ReviewDimension` usage:
```python
class DimensionScore(BaseModel):
    score: int
    critique: str = ""


class ReviewScore(BaseModel):
    artifact_type: str = ""
    scores: dict[str, DimensionScore] = Field(default_factory=dict)
    overall: int = 0
    summary: str = ""
    attempt: int = 1          # pipeline-managed
    passed: bool = False      # set by decide()
```
(Remove the old `ReviewDimension` class if nothing else uses it; grep first.)

- [ ] **Step 2: Rewrite scorer_rubrics**

```python
def decide(score: ReviewScore, score_min: int) -> bool:
    score.passed = all(ds.score >= score_min for ds in score.scores.values()) if score.scores else False
    return score.passed


def apply_review(score: ReviewScore, _existing: str) -> str:
    return "; ".join(f"{name}({ds.score}): {ds.critique}" for name, ds in score.scores.items() if ds.critique)
```
`RUBRICS` dict unchanged (still maps artifact_type → dimension names).

- [ ] **Step 3: Rewrite scorer build_messages (spec §6)**

`rubric_dimensions = "\n".join(f"- {d}" for d in RUBRICS.get(artifact_type, ["quality"]))`. system = `SCORER_SYSTEM` with `{artifact_type}` and `{rubric_dimensions}` injected; user = `SCORER_USER` with `{artifact_type}`/`{artifact_json}`.

- [ ] **Step 4: Update _demo_provider + tests**

`_demo_provider` canned `passing`:
```python
passing = ReviewScore(artifact_type="chapter", overall=90,
                      scores={"beat_adherence": DimensionScore(score=90, critique="ok")})
```
`tests/test_graph.py`: `passing` fixture → v2 `ReviewScore(scores={...})`. `tests/test_scorer.py`: rewrite assertions to use `rs.scores` / `rs.overall` / `rs.passed`. `tests/test_models.py`: update ReviewScore construction.

- [ ] **Step 5: Run gates + commit**

Green. Commit: `feat(prompts-v2): scorer prompt + restructured ReviewScore + calibrated rubrics`

---

### Task 4: Extractor + CharacterState + key_events mapping

**Files:**
- Modify: `novel/models.py` (`CharacterState` → v2 fields; add `KeyEvent`)
- Modify: `novel/memory/extractor.py` (`_UpdatePayload`, `ChapterUpdates`, prompt spec §9)
- Modify: `novel/graph.py` (consume `mannerisms_used` list; map `key_events` → `Event`)
- Modify: `novel/cli.py` (`_demo_provider` canned extractor → v2)
- Test: `tests/test_models.py`, `tests/test_extractor.py`, `tests/test_graph.py` (extractor fixture), `tests/test_cli.py`

**Interfaces:**
- `CharacterState(emotional_state, physical_state, knowledge_gained: list[str], relationships_shifted: dict[str,str], location_end)`.
- `_UpdatePayload(character_states: dict[str,CharacterState], voice_samples: dict[str,str], mannerisms_used: dict[str,list[str]], key_events: list[KeyEvent], threads_advanced: list[str], new_information_revealed: list[str])`.
- `KeyEvent(event, significance, affected_characters: list[str])`.
- graph maps each `KeyEvent` → `Event(id=f"evt_{chapter_no}_{i+1}", chapter=chapter_no, summary=ke.event, characters=ke.affected_characters, ...)`.

- [ ] **Step 1: Restructure CharacterState + add KeyEvent**

In `novel/models.py`:
```python
class CharacterState(BaseModel):
    emotional_state: str = ""
    physical_state: str = ""
    knowledge_gained: list[str] = Field(default_factory=list)
    relationships_shifted: dict[str, str] = Field(default_factory=dict)
    location_end: str = ""


class KeyEvent(BaseModel):
    event: str
    significance: str = ""
    affected_characters: list[str] = Field(default_factory=list)
```
(`Event` stays as-is for `events.jsonl`.)

- [ ] **Step 2: Update _UpdatePayload + ChapterUpdates + prompt (spec §9)**

In `novel/memory/extractor.py`:
```python
class _UpdatePayload(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    character_states: dict[str, CharacterState] = Field(default_factory=dict)
    voice_samples: dict[str, str] = Field(default_factory=dict)
    mannerisms_used: dict[str, list[str]] = Field(default_factory=dict)
    key_events: list[KeyEvent] = Field(default_factory=list)
    threads_advanced: list[str] = Field(default_factory=list)
    new_information_revealed: list[str] = Field(default_factory=list)
```
Mirror the same fields in the `ChapterUpdates` dataclass. Rewrite the system/user messages from spec §9 (`EXTRACTOR_SYSTEM` with `{roster_block}`, `EXTRACTOR_USER` with `{chapter_no}`/`{roster_block}`/`{prose}`); `roster_block = "\n".join(f"- {c.id} ({c.name})" for c in characters)`.

- [ ] **Step 3: Update graph extractor consumption**

In `novel/graph.py`, replace the mannerism + events apply block:
```python
for cid, man_list in upd.mannerisms_used.items():
    ch_obj = bible.get_character(cid)
    if not ch_obj:
        continue
    for man in man_list:
        existing = next((m for m in ch_obj.mannerisms if m.text == man), None)
        if existing:
            existing.used_count += 1
        else:
            ch_obj.mannerisms.append(Mannerism(text=man, used_count=1))
    bible.upsert_character(ch_obj)
for i, ke in enumerate(upd.key_events):
    bible.append_event(Event(
        id=f"evt_{chapter_no}_{i + 1}", chapter=chapter_no, summary=ke.event,
        characters=list(ke.affected_characters)))
```
(voice_samples + character_states apply blocks unchanged in shape; import `Mannerism`, `Event` from `novel.models`.) `threads_advanced`/`new_information_revealed` are accepted by the payload but not wired further (note in report; deep ledger wiring is v1.1).

- [ ] **Step 4: Update _demo_provider + tests**

`_demo_provider` canned `"extractor"`:
```python
"extractor": {"character_states": {}, "voice_samples": {}, "mannerisms_used": {},
              "key_events": [], "threads_advanced": [], "new_information_revealed": []}
```
`tests/test_extractor.py` + `tests/test_graph.py` extractor canned → v2 payload (`mannerisms_used` lists; `key_events` list; drop `events`). `tests/test_models.py`: CharacterState construction.

- [ ] **Step 5: Run gates + commit**

Green. Commit: `feat(prompts-v2): extractor prompt + restructured CharacterState + key_events`

---

### Task 5: Writer/Continuity/Editor prompts + smoke finalization + live re-validation

**Files:**
- Modify: `novel/agents/writer.py`, `novel/agents/continuity.py`, `novel/agents/editor.py` (spec §5, §7, §8)
- Test: full suite; manual live re-run.

**Interfaces:** Writer/Editor take/return `str` (unchanged). Continuity returns `list[str]` (unchanged). Only prompt bodies change; continuity retry text → `CONTINUITY_RETRY`.

- [ ] **Step 1: Rewrite writer/continuity/editor build_messages**

- `writer.py`: system = `WRITER_SYSTEM` (spec §5); user = `WRITER_USER.format(assembled_context=inputs.text)`. Keep overridden `run()`.
- `continuity.py`: system = `CONTINUITY_SYSTEM`, user = `CONTINUITY_USER` with `{bible_json}`/`{prose}` (spec §7). Keep retry loop; retry msg = `CONTINUITY_RETRY.format(error=e)`.
- `editor.py`: system = `EDITOR_SYSTEM`, user = `EDITOR_USER.format(prose=inputs)` (spec §8). Keep overridden `run()`.

- [ ] **Step 2: Full suite + lint + types**

`uv run pytest -q && uv run ruff check . && uv run mypy novel` → green. Fix any remaining fixture drift across `tests/`.

- [ ] **Step 3: Commit**

Commit: `feat(prompts-v2): writer/continuity/editor prompts; migration complete`

- [ ] **Step 4: Live re-validation (manual, not committed)**

On a FRESH project (avoid the accumulated-characters cruft from prior runs):
```bash
export DEEPSEEK_API_KEY=...
NOVEL_LIVE=1 uv run novel init v2test --genre fantasy
cd v2test
NOVEL_LIVE=1 uv run novel premise "一个能偷走时间的盗贼"
NOVEL_LIVE=1 uv run novel write-chapter 1
```
Confirm: `chapters/001.md` written; `bible/_canonical.json` has `outline.foreshadow_ledger`; a character has `voice_fingerprint["sample_1"]` (proves the outliner-id → extractor → voice chain now closes); `events.jsonl` has events with non-empty `characters`. Record results in the task report (not committed).

---

## Self-Review

**1. Spec coverage:** Strategist §1 (T1), Worldbuilder §2 (T1), Character §3 (T1), Outliner §4 (T2), Writer §5 (T5), Scorer §6 (T3), Continuity §7 (T5), Editor §8 (T5), Extractor §9 (T4). Model conflicts (World, Outline, ReviewScore, CharacterState/Event) each have a task. foreshadow_ledger wired (T2). decide/apply_review updated (T3). assembler intentionally unchanged (noted). ✅
**2. Placeholder scan:** prompt bodies reference spec §N verbatim (spec on disk); model + consumer code is concrete. No TBD. ✅
**3. Type consistency:** `ReviewScore.scores: dict[str, DimensionScore]` used identically by `decide`/`apply_review`/`_scored`. `ChapterOutline.chapter_no`/`Arc.arc_name` consistent in models + fixtures + `_demo_provider`. `mannerisms_used: dict[str, list[str]]` consistent in payload + graph. `key_events`/`KeyEvent` consistent in payload + graph mapping. ✅

## Notes / deferred (v1.1)

- `threads_advanced` / `new_information_revealed` accepted but not wired into the foreshadow ledger status machine.
- `beat_id` parsed for ledger `_parse_ch` best-effort only.
- Live mode still uses `hash_embed` (deferred embedder swap).
