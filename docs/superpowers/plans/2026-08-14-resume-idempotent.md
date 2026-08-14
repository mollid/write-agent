# 断点续跑与恢复（磁盘即真相）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `write-chapter` idempotent for CLI and GUI — rerunning the same command after an interruption skips complete chapters, rewrites incomplete ones, and never again treats an empty/stub chapter file as finished.

**Architecture:** Disk is the single source of truth. A new pure module `novel/resume.py` decides "is chapter N complete" (file exists, ≥ `min_chapter_chars`, and a `passed` review record exists — with a file-only fallback for legacy projects predating review history). `run_full_pipeline` gains an in-loop idempotent skip, atomically writes each chapter file last (extraction → bible → vector → atomic rename, so the file's appearance is the commit point), and cleans stale `.tmp` files on start. CLI and GUI both replace their inline `glob` logic with `next_start_chapter`.

**Tech Stack:** Python 3.11+, pytest (FakeProvider only — no network), typer, FastAPI TestClient for the GUI path.

**Spec:** `docs/superpowers/specs/2026-08-14-resume-design.md` (gitignored by repo convention).

## Global Constraints

- All tests use `FakeProvider` (demo responses); never require `NOVEL_LIVE=1` or network.
- Default `min_chapter_chars = 50` **must stay below** the demo writer's canned prose (62 chars) — otherwise demo-mode projects never count as complete and resume loops. Live projects can raise it to thousands.
- `mypy novel` (strict) and `ruff check .` (line-length 100) must pass before each commit.
- Do not commit `project.config.yaml`, `demo-novel/`, `*-novel/`, or `docs/superpowers/specs/` (all gitignored).

## File Structure

- Create: `novel/resume.py` — pure chapter-completion rules (`is_chapter_complete`, `next_start_chapter`).
- Modify: `novel/config.py` — new `Generation.min_chapter_chars` field.
- Modify: `novel/graph.py` — atomic chapter write, persist-order reorder, stale `.tmp` cleanup, in-loop skip, new `min_chapter_chars` param.
- Modify: `novel/cli.py` — `write_chapter` uses `next_start_chapter`, prints resume notice, passes `min_chapter_chars`.
- Modify: `novel/ui/jobs.py` — `run_chapters_job` uses `next_start_chapter`, passes `min_chapter_chars`.
- Modify: `README.md` — config table row + 「中断后续跑」section.
- Create: `tests/test_resume.py`; modify `tests/test_config.py`, `tests/test_cli.py`, `tests/test_ui.py`.

Reference facts (do not re-derive):
- `ReviewStore` (novel/store/reviews.py): `append(rec)`, `list_for_chapter(n)`, `path() -> Path` (`.meta/reviews/reviews.jsonl`). Its constructor mkdirs `.meta/reviews/` but does **not** create the jsonl — legacy detection uses `reviews.path().is_file()`.
- `ReviewRecord.passed: bool` (novel/models.py:169).
- `VectorMemory._add` uses chroma `upsert` keyed by `ch{n}` — idempotent, safe on reruns.
- Demo writer prose (`novel/runtime.py`): `"Ara stepped into the tavern. The thief's work was about to begin."` (62 chars).
- `run_full_pipeline` signature today: `(*, provider, cfg_map, bible, vector, proj, premise, target_chapters, score_min=80, max_retries=3, token_budget=24000, start_chapter=1, on_gate=None, on_event=None)` (novel/graph.py:52-59).
- Loop iteration: `chapter_no` starts at `start_chapter - 1` and increments per outline chapter; chapters before `start_chapter` are never iterated (so the in-loop skip only fires for chapters ≥ start).
- Chapters glob `[0-9][0-9][0-9].md` in cli.py:73, jobs.py:209, export.py:10 — a dot-prefixed `.001.md.tmp` matches none of them.

---

### Task 1: Config field `generation.min_chapter_chars`

**Files:**
- Modify: `novel/config.py:24-27` (Generation dataclass) and `novel/config.py:59-67` (load_config)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config.py`:

```python
def test_min_chapter_chars_default_and_override(tmp_path):
    from novel.project import NovelProject
    proj = NovelProject.scaffold("n", genre="fantasy", root=tmp_path)
    cfg = load_config(proj.config_path)
    assert cfg.generation.min_chapter_chars == 50  # default, and below demo prose (62 chars)

    text = proj.config_path.read_text(encoding="utf-8")
    proj.config_path.write_text(
        text.replace("generation:", "generation:\n  min_chapter_chars: 2000"),
        encoding="utf-8",
    )
    cfg2 = load_config(proj.config_path)
    assert cfg2.generation.min_chapter_chars == 2000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py::test_min_chapter_chars_default_and_override -q`
Expected: FAIL with `AttributeError: 'Generation' object has no attribute 'min_chapter_chars'`

- [ ] **Step 3: Implement**

In `novel/config.py`, extend the dataclass:

```python
@dataclass
class Generation:
    human_gate_every_n_chapters: int = 1
    context_token_budget: int = 24000
    min_chapter_chars: int = 50    # resume check: shorter chapter files count as incomplete
```

In `load_config`, extend the `Generation(...)` construction:

```python
        generation=Generation(
            human_gate_every_n_chapters=gen.get("human_gate_every_n_chapters", 1),
            context_token_budget=gen.get("context_token_budget", 24000),
            min_chapter_chars=gen.get("min_chapter_chars", 50),
        ),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -q`
Expected: PASS (all tests in file)

- [ ] **Step 5: Commit**

```bash
git add novel/config.py tests/test_config.py
git commit -m "feat(resume): generation.min_chapter_chars config field"
```

---

### Task 2: `novel/resume.py` — `is_chapter_complete`

**Files:**
- Create: `novel/resume.py`
- Test: `tests/test_resume.py` (new file)

- [ ] **Step 1: Write the failing test**

Create `tests/test_resume.py`:

```python
"""Resume rules: disk is the source of truth for chapter completeness."""
from __future__ import annotations

from novel.models import DimensionScore, ReviewRecord
from novel.project import NovelProject
from novel.resume import is_chapter_complete
from novel.store.reviews import ReviewStore

LONG = "Ara stepped into the tavern and the long night began. " * 2  # > 50 chars


def _proj(tmp_path):
    return NovelProject.scaffold("n", genre="fantasy", root=tmp_path)


def _pass_review(chapter: int) -> ReviewRecord:
    return ReviewRecord(chapter=chapter, attempt=1, artifact_type="chapter", overall=90,
                        summary="ok", passed=True, timestamp="2026-08-14T00:00:00+00:00",
                        scores={"beat_adherence": DimensionScore(score=90, critique="ok")})


def _write_chapter(proj, n: int, text: str) -> None:
    (proj.root / "chapters" / f"{n:03d}.md").write_text(text, encoding="utf-8")


def test_complete_needs_file_length_and_pass(tmp_path):
    proj = _proj(tmp_path)
    reviews = ReviewStore(proj)
    # missing file -> incomplete
    assert is_chapter_complete(proj, reviews, 1) is False
    # too short -> incomplete
    _write_chapter(proj, 1, "tiny")
    assert is_chapter_complete(proj, reviews, 1) is False
    # long enough but no passed review -> incomplete
    _write_chapter(proj, 1, LONG)
    assert is_chapter_complete(proj, reviews, 1) is False
    failed = _pass_review(1)
    failed.passed = False
    reviews.append(failed)
    assert is_chapter_complete(proj, reviews, 1) is False
    # long enough + passed record -> complete
    reviews.append(_pass_review(1))
    assert is_chapter_complete(proj, reviews, 1) is True


def test_legacy_project_without_reviews_jsonl(tmp_path):
    """Projects predating review history: file rule only, no rewrite-everything."""
    proj = _proj(tmp_path)
    reviews = ReviewStore(proj)
    reviews.path().unlink(missing_ok=True)
    _write_chapter(proj, 1, LONG)
    assert is_chapter_complete(proj, reviews, 1) is True
    _write_chapter(proj, 1, "")
    assert is_chapter_complete(proj, reviews, 1) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_resume.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'novel.resume'`

- [ ] **Step 3: Implement**

Create `novel/resume.py`:

```python
"""Resume rules: the filesystem is the single source of truth for chapter
completeness. A chapter counts as complete only when its file is long enough
AND (post-reviews-era) it has a passed scoring record on disk."""
from __future__ import annotations

from novel.project import NovelProject
from novel.store.reviews import ReviewStore


def is_chapter_complete(proj: NovelProject, reviews: ReviewStore,
                        n: int, min_chars: int = 50) -> bool:
    path = proj.root / "chapters" / f"{n:03d}.md"
    if not path.is_file() or len(path.read_text(encoding="utf-8").strip()) < min_chars:
        return False
    if not reviews.path().is_file():
        return True  # legacy project predating review history: file rule only
    return any(r.passed for r in reviews.list_for_chapter(n))


def next_start_chapter(proj: NovelProject, reviews: ReviewStore,
                       min_chars: int = 50) -> int:
    """Smallest chapter number that is missing or incomplete."""
    n = 1
    for existing in sorted(int(p.stem) for p in
                           (proj.root / "chapters").glob("[0-9][0-9][0-9].md")):
        if existing == n and is_chapter_complete(proj, reviews, n, min_chars):
            n += 1
        else:
            break
    return n
```

Note: `next_start_chapter` is fully implemented here (it is 8 lines and tested in Task 3); do not split it further.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_resume.py -q`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add novel/resume.py tests/test_resume.py
git commit -m "feat(resume): is_chapter_complete disk-based completion rule"
```

---

### Task 3: `next_start_chapter` behavior

**Files:**
- Test: `tests/test_resume.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_resume.py` (add `next_start_chapter` to the import line):

```python
def test_next_start_chapter_positions(tmp_path):
    from novel.resume import next_start_chapter
    proj = _proj(tmp_path)
    reviews = ReviewStore(proj)
    # empty project -> 1
    assert next_start_chapter(proj, reviews) == 1
    # chapters 1-2 complete -> 3
    for n in (1, 2):
        _write_chapter(proj, n, LONG)
        reviews.append(_pass_review(n))
    assert next_start_chapter(proj, reviews) == 3
    # hole: 003 exists but empty -> resume at 3 even though it is the last file
    _write_chapter(proj, 3, "")
    assert next_start_chapter(proj, reviews) == 3
    # middle hole: 004 complete, 003 empty -> resume at 3
    _write_chapter(proj, 4, LONG)
    reviews.append(_pass_review(4))
    assert next_start_chapter(proj, reviews) == 3
    # min_chars override: 62-char demo prose vs threshold 100
    reviews.path().unlink()
    _write_chapter(proj, 1, "x" * 62)
    assert next_start_chapter(proj, reviews, min_chars=100) == 1
    assert next_start_chapter(proj, reviews, min_chars=50) == 2
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_resume.py -q`
Expected: PASS — `next_start_chapter` already exists from Task 2; this test pins its positional behavior. If it fails, fix `next_start_chapter` (not the test).

- [ ] **Step 3: Commit**

```bash
git add tests/test_resume.py
git commit -m "test(resume): pin next_start_chapter positions (holes, legacy, min_chars)"
```

---

### Task 4: Pipeline — atomic write, persist reorder, stale `.tmp` cleanup

**Files:**
- Modify: `novel/graph.py:155-157` (persist block) and `novel/graph.py:103` (after ReviewStore construction)
- Test: `tests/test_resume.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_resume.py`:

```python
def _run_pipeline(tmp_path, prose: str, target: int, start: int = 1,
                  proj: NovelProject | None = None):
    """Demo-mode pipeline run with FakeProvider; pass `proj` back in to rerun."""
    from novel.graph import run_full_pipeline
    from novel.models import Arc, ChapterBeat, ChapterOutline, Character, Concept, \
        DimensionScore, Outline, ReviewScore, World
    from novel.providers import FakeProvider, ModelConfig
    from novel.store.bible import StoryBible
    from novel.store.vector import VectorMemory, hash_embed

    if proj is None:
        proj = NovelProject.scaffold("n", genre="fantasy", root=tmp_path)
    bible = StoryBible(proj)
    vector = VectorMemory(proj, embed=hash_embed)
    concept = Concept(logline="L", genre="fantasy", tone="grim", themes=["x"],
                      target_length_words=9000, audience="a")
    beat = ChapterBeat(pov="Ara", setting="tavern", event="meet informant",
                       emotional_turn="doubt", characters=["c1"])
    outline = Outline(arcs=[Arc(arc_name="A", chapters=[
        ChapterOutline(chapter_no=i, chapter_title=f"T{i}", beats=[beat])
        for i in range(1, target + 1)])])
    chars = [Character(id="c1", slug="ara", name="Ara", role="protagonist",
                       backstory="b", motivation="m", arc="a")]
    passing = ReviewScore(artifact_type="chapter", overall=90,
                          scores={"beat_adherence": DimensionScore(score=90, critique="ok")})
    provider = FakeProvider(responses={
        "strategist": concept, "worldbuilder": World(setting="city"),
        "character": chars, "outliner": outline,
        "writer": prose, "continuity": "[]", "editor": prose, "scorer": passing,
        "extractor": {"character_states": {}, "voice_samples": {}, "mannerisms_used": {},
                      "key_events": [], "threads_advanced": [], "new_information_revealed": []},
    }, tag_key="agent")
    cfg_map = {name: ModelConfig("zhipu", "x") for name in
               ["strategist", "worldbuilder", "character", "outliner", "writer",
                "continuity", "editor", "scorer", "extractor"]}
    state = run_full_pipeline(provider=provider, cfg_map=cfg_map, bible=bible, vector=vector,
                              proj=proj, premise="a thief", target_chapters=target,
                              start_chapter=start)
    return proj, state


def test_atomic_write_no_tmp_residue(tmp_path):
    proj, state = _run_pipeline(tmp_path, LONG, target=1)
    assert state.error is None
    assert (proj.root / "chapters" / "001.md").read_text(encoding="utf-8") == LONG
    assert list((proj.root / "chapters").glob("*.tmp")) == []


def test_stale_tmp_cleaned_on_rerun(tmp_path):
    proj, state = _run_pipeline(tmp_path, LONG, target=1)
    assert state.error is None
    # a crashed run left a partial tmp behind; the next pipeline start must remove it
    (proj.root / "chapters" / ".002.md.tmp").write_text("partial", encoding="utf-8")
    proj, state2 = _run_pipeline(tmp_path, LONG, target=2, start=2, proj=proj)
    assert state2.error is None
    assert (proj.root / "chapters" / "002.md").read_text(encoding="utf-8") == LONG
    assert list((proj.root / "chapters").glob("*.tmp")) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_resume.py -q`
Expected: `test_stale_tmp_cleaned_on_rerun` FAILs — the current code never deletes
`.002.md.tmp`, so the final `glob("*.tmp")` finds it. `test_atomic_write_no_tmp_residue`
may already pass (a direct write also produces correct content and no tmp); it pins the
contract. Proceed once the stale test fails for that reason.

- [ ] **Step 3: Implement**

In `novel/graph.py`:

3a. After `reviews = ReviewStore(proj)` (currently line 103), add:

```python
    # stale tmp files from a crashed run must never be mistaken for chapters
    for stale in (proj.root / "chapters").glob(".*.md.tmp"):
        stale.unlink()
```

3b. Replace the persist block. **Delete** these lines (currently 155-157):

```python
            # persist
            (proj.root / "chapters" / f"{chapter_no:03d}.md").write_text(prose, encoding="utf-8")
            vector.add_chapter(chapter_no, prose)
```

**Keep** the extractor stage emit and everything through the foreshadow `payoffs` block
unchanged, then **replace** the final two lines of the loop body (currently 203-204):

```python
            vector.add_summary("chapter", f"ch{chapter_no}", prose[:300])
            emit({"type": "chapter_done", "chapter": chapter_no})
```

with:

```python
            vector.add_chapter(chapter_no, prose)
            vector.add_summary("chapter", f"ch{chapter_no}", prose[:300])
            # atomic write last: the file's appearance is the chapter's commit point
            # (score gate, extraction, bible and memory updates are all on disk already)
            chapters_dir = proj.root / "chapters"
            tmp = chapters_dir / f".{chapter_no:03d}.md.tmp"
            tmp.write_text(prose, encoding="utf-8")
            tmp.replace(chapters_dir / f"{chapter_no:03d}.md")
            emit({"type": "chapter_done", "chapter": chapter_no})
```

Resulting order inside the loop after the score gate and continuity/editor: extractor →
bible updates (character states / voice / mannerisms / events / plants / payoffs) →
`vector.add_chapter` → `vector.add_summary` → atomic file write → `chapter_done`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_resume.py tests/test_reviews.py tests/test_graph.py -q`
Expected: PASS (reordering must not break existing persistence tests — vector upsert is idempotent, ReviewRecord writes are unchanged).

- [ ] **Step 5: Commit**

```bash
git add novel/graph.py tests/test_resume.py
git commit -m "feat(resume): atomic chapter write; extraction/memory before commit point; stale .tmp cleanup"
```

---

### Task 5: Pipeline — in-loop idempotent skip + `min_chapter_chars` param

**Files:**
- Modify: `novel/graph.py:52-59` (signature), `novel/graph.py:106-112` (loop head)
- Test: `tests/test_resume.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_resume.py` (needs a counting provider — writer invocations prove skipping):

```python
class _CountingProvider:
    """Wraps FakeProvider, counting calls per agent tag (protocol-compatible)."""

    def __init__(self, responses: dict[str, object]) -> None:
        from collections import Counter
        from novel.providers import FakeProvider, _agent_tag
        self._inner = FakeProvider(responses, tag_key="agent")
        self._agent_tag = _agent_tag
        self.counts: Counter[str] = Counter()

    def complete(self, messages, cfg, *, seed=None):
        self.counts[self._agent_tag(messages, "agent")] += 1
        return self._inner.complete(messages, cfg, seed=seed)

    def complete_structured(self, messages, schema, cfg, *, seed=None):
        self.counts[self._agent_tag(messages, "agent")] += 1
        return self._inner.complete_structured(messages, schema, cfg, seed=seed)


def _run_counting(tmp_path, target: int, start: int = 1):
    """Like _run_pipeline but with a counting provider; returns (proj, state, provider)."""
    import novel.graph as graph
    from novel.models import Arc, ChapterBeat, ChapterOutline, Character, Concept, \
        DimensionScore, Outline, ReviewScore, World
    from novel.providers import ModelConfig
    from novel.store.bible import StoryBible
    from novel.store.vector import VectorMemory, hash_embed

    proj = NovelProject.scaffold("n", genre="fantasy", root=tmp_path)
    bible = StoryBible(proj)
    vector = VectorMemory(proj, embed=hash_embed)
    concept = Concept(logline="L", genre="fantasy", tone="grim", themes=["x"],
                      target_length_words=9000, audience="a")
    beat = ChapterBeat(pov="Ara", setting="tavern", event="meet informant",
                       emotional_turn="doubt", characters=["c1"])
    outline = Outline(arcs=[Arc(arc_name="A", chapters=[
        ChapterOutline(chapter_no=i, chapter_title=f"T{i}", beats=[beat])
        for i in range(1, target + 1)])])
    chars = [Character(id="c1", slug="ara", name="Ara", role="protagonist",
                       backstory="b", motivation="m", arc="a")]
    passing = ReviewScore(artifact_type="chapter", overall=90,
                          scores={"beat_adherence": DimensionScore(score=90, critique="ok")})
    provider = _CountingProvider({
        "strategist": concept, "worldbuilder": World(setting="city"),
        "character": chars, "outliner": outline,
        "writer": LONG, "continuity": "[]", "editor": LONG, "scorer": passing,
        "extractor": {"character_states": {}, "voice_samples": {}, "mannerisms_used": {},
                      "key_events": [], "threads_advanced": [], "new_information_revealed": []},
    })
    cfg_map = {name: ModelConfig("zhipu", "x") for name in
               ["strategist", "worldbuilder", "character", "outliner", "writer",
                "continuity", "editor", "scorer", "extractor"]}
    state = graph.run_full_pipeline(
        provider=provider, cfg_map=cfg_map, bible=bible, vector=vector,
        proj=proj, premise="a thief", target_chapters=target, start_chapter=start)
    return proj, state, provider


def test_complete_chapters_skipped_on_rerun(tmp_path):
    proj, state, provider = _run_counting(tmp_path, target=3)
    assert state.error is None
    assert provider.counts["writer"] == 3
    events: list[dict] = []

    import novel.graph as graph
    from novel.store.bible import StoryBible
    from novel.store.vector import VectorMemory, hash_embed
    from novel.providers import ModelConfig
    bible = StoryBible(proj)
    cfg_map = {name: ModelConfig("zhipu", "x") for name in
               ["strategist", "worldbuilder", "character", "outliner", "writer",
                "continuity", "editor", "scorer", "extractor"]}
    # rerun from chapter 1 on the same project: nothing should be regenerated
    state2 = graph.run_full_pipeline(
        provider=provider, cfg_map=cfg_map, bible=bible,
        vector=VectorMemory(proj, embed=hash_embed),
        proj=proj, premise="a thief", target_chapters=3, start_chapter=1,
        on_event=events.append)
    assert state2.error is None
    assert provider.counts["writer"] == 3  # no extra writer calls
    skips = [e for e in events if e["type"] == "chapter_skipped"]
    assert [e["chapter"] for e in skips] == [1, 2, 3]
    assert all(e["reason"] == "already complete" for e in skips)


def test_pipeline_rewrites_invalid_hole(tmp_path):
    proj, state, provider = _run_counting(tmp_path, target=3)
    assert provider.counts["writer"] == 3
    # chapter 2 got truncated by a crash: rerun must rewrite ONLY chapter 2
    (proj.root / "chapters" / "002.md").write_text("", encoding="utf-8")

    import novel.graph as graph
    from novel.store.bible import StoryBible
    from novel.store.vector import VectorMemory, hash_embed
    from novel.providers import ModelConfig
    bible = StoryBible(proj)
    cfg_map = {name: ModelConfig("zhipu", "x") for name in
               ["strategist", "worldbuilder", "character", "outliner", "writer",
                "continuity", "editor", "scorer", "extractor"]}
    events: list[dict] = []
    state2 = graph.run_full_pipeline(
        provider=provider, cfg_map=cfg_map, bible=bible,
        vector=VectorMemory(proj, embed=hash_embed),
        proj=proj, premise="a thief", target_chapters=3, start_chapter=2,
        on_event=events.append)
    assert state2.error is None
    assert provider.counts["writer"] == 4  # exactly one rewrite (chapter 2)
    assert (proj.root / "chapters" / "002.md").read_text(encoding="utf-8") == LONG
    skips = [e for e in events if e["type"] == "chapter_skipped"]
    assert [e["chapter"] for e in skips] == [3]  # chapter 3 untouched
    assert list((proj.root / "chapters").glob("*.tmp")) == []


def test_min_chapter_chars_param_gates_completeness(tmp_path):
    proj, state, provider = _run_counting(tmp_path, target=1)
    assert provider.counts["writer"] == 1

    import novel.graph as graph
    from novel.store.bible import StoryBible
    from novel.store.vector import VectorMemory, hash_embed
    from novel.providers import ModelConfig
    bible = StoryBible(proj)
    cfg_map = {name: ModelConfig("zhipu", "x") for name in
               ["strategist", "worldbuilder", "character", "outliner", "writer",
                "continuity", "editor", "scorer", "extractor"]}
    # LONG (~116 chars) is complete at min_chars=50 but not at 500
    state2 = graph.run_full_pipeline(
        provider=provider, cfg_map=cfg_map, bible=bible,
        vector=VectorMemory(proj, embed=hash_embed),
        proj=proj, premise="a thief", target_chapters=1, start_chapter=1,
        min_chapter_chars=500)
    assert provider.counts["writer"] == 2  # rewritten under the stricter threshold
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_resume.py -q`
Expected: the three new tests FAIL (`run_full_pipeline() got an unexpected keyword argument 'min_chapter_chars'`, and reruns regenerate chapters — writer counts grow past expected).

- [ ] **Step 3: Implement**

In `novel/graph.py`:

3a. Add the import near the other `novel.*` imports:

```python
from novel.resume import is_chapter_complete
```

3b. Extend the signature (novel/graph.py:52-59) — add after `start_chapter: int = 1,`:

```python
    min_chapter_chars: int = 50,
```

3c. In the generation loop, right after the target check (`if chapter_no > target_chapters: break`, currently line 110) and **before** the `beat = ...` line, insert:

```python
            if is_chapter_complete(proj, reviews, chapter_no, min_chapter_chars):
                emit({"type": "chapter_skipped", "chapter": chapter_no,
                      "reason": "already complete"})
                continue
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy novel`
Expected: full suite PASS (existing demo e2e tests must still pass — demo prose is 62 chars ≥ 50, and `tests/test_cli.py::test_write_chapter_continues` specifically proves resume still advances), lint and types clean.

- [ ] **Step 5: Commit**

```bash
git add novel/graph.py tests/test_resume.py
git commit -m "feat(resume): idempotent in-loop chapter skip + min_chapter_chars param"
```

---

### Task 6: CLI wiring

**Files:**
- Modify: `novel/cli.py:61-81` (`write_chapter`)
- Test: `tests/test_cli.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_write_chapter_resumes_message(tmp_path):
    proj = _demo_project(tmp_path)
    r1 = runner.invoke(app, ["--project", str(proj), "write-chapter", "2"])
    assert r1.exit_code == 0, r1.output
    r2 = runner.invoke(app, ["--project", str(proj), "write-chapter", "1"])
    assert r2.exit_code == 0, r2.output
    assert "Resuming from chapter 3" in r2.output
    chapters = sorted((proj / "chapters").glob("[0-9][0-9][0-9].md"))
    assert len(chapters) == 3


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -q`
Expected: `test_write_chapter_rewrites_empty_chapter` FAILs — the current glob-based start
(`int(existing[-1].stem) + 1`) sees `002.md` and starts at 3, leaving the empty `001.md`
in place. (`test_write_chapter_resumes_message` fails on the missing message.)

- [ ] **Step 3: Implement**

In `novel/cli.py` `write_chapter`, replace the two glob lines (currently 73-74):

```python
    existing = sorted((proj.root / "chapters").glob("[0-9][0-9][0-9].md"))
    start_chapter = int(existing[-1].stem) + 1 if existing else 1
```

with:

```python
    from novel.resume import next_start_chapter
    from novel.store.reviews import ReviewStore
    min_chars = cfg.generation.min_chapter_chars
    start_chapter = next_start_chapter(proj, ReviewStore(proj), min_chars)
    if start_chapter > 1:
        console.print(f"[cyan]Resuming from chapter {start_chapter}"
                      f" ({start_chapter - 1} chapter(s) already complete)[/cyan]")
```

and pass the threshold into the pipeline call (add after `token_budget=...`):

```python
                      min_chapter_chars=min_chars,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py tests/test_resume.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add novel/cli.py tests/test_cli.py
git commit -m "feat(resume): CLI write-chapter idempotent via next_start_chapter"
```

---

### Task 7: GUI wiring

**Files:**
- Modify: `novel/ui/jobs.py:194-222` (`run_chapters_job`)
- Test: `tests/test_ui.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ui.py` (reuses the file's `client` fixture — which is built from
`create_app(tmp_path)` — and its `_wait_job` helper):

```python
def test_write_chapter_rewrites_empty_chapter(client: TestClient, tmp_path: Path) -> None:
    client.post("/api/projects", json={"name": "px"})
    job_id = client.post("/api/projects/px/premise", json={"text": "x"}).json()["job_id"]
    assert _wait_job(client, job_id)["status"] == "done"
    r = client.post("/api/projects/px/write-chapter", json={"n": 2})
    assert _wait_job(client, r.json()["job_id"])["status"] == "done"

    root = tmp_path / "px"
    ch1 = root / "chapters" / "001.md"
    ch2 = root / "chapters" / "002.md"
    good2 = ch2.read_text(encoding="utf-8")
    ch1.write_text("", encoding="utf-8")  # simulate a crashed write

    r2 = client.post("/api/projects/px/write-chapter", json={"n": 1})
    job = _wait_job(client, r2.json()["job_id"])
    assert job["status"] == "done", job["error"]

    assert len(ch1.read_text(encoding="utf-8")) > 50  # rewritten
    assert ch2.read_text(encoding="utf-8") == good2  # complete chapter untouched
    status = client.get("/api/projects/px/status").json()
    assert status["chapters"] == [1, 2]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ui.py::test_write_chapter_rewrites_empty_chapter -q`
Expected: FAIL — empty `001.md` is not rewritten (glob-based start sees `002.md` and begins at chapter 3).

- [ ] **Step 3: Implement**

In `novel/ui/jobs.py` `run_chapters_job`, replace the glob lines (currently 209-210):

```python
        existing = sorted((proj.root / "chapters").glob("[0-9][0-9][0-9].md"))
        start_chapter = int(existing[-1].stem) + 1 if existing else 1
```

with:

```python
        from novel.resume import next_start_chapter
        from novel.store.reviews import ReviewStore
        min_chars = cfg.generation.min_chapter_chars
        start_chapter = next_start_chapter(proj, ReviewStore(proj), min_chars)
```

and pass the threshold into `run_full_pipeline` (add after `token_budget=...`):

```python
            min_chapter_chars=min_chars,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ui.py -q`
Expected: PASS (all GUI tests, including the existing demo e2e which must keep producing chapters 1-2)

- [ ] **Step 5: Commit**

```bash
git add novel/ui/jobs.py tests/test_ui.py
git commit -m "feat(resume): GUI write-chapter shares next_start_chapter with CLI"
```

---

### Task 8: README sync + full gate

**Files:**
- Modify: `README.md` (config table at line ~257; new subsection after「### 3. 生成章节」which ends before「### 4. 查看故事线索」at line ~163;「排错」section at line ~421「章节没有从预期位置继续」entry likely needs updating)

- [ ] **Step 1: Update the config table**

In the 配置字段说明 table (after the `generation.context_token_budget` row at line 257), add:

```markdown
| `generation.min_chapter_chars` | 断点续跑时判定章节「已完成」的最小字符数，默认 `50`（必须低于演示模式章节长度）。真实模型项目建议设为实际章节长度的下限（如 `2000`），过大会导致同一章每次续跑都被重写。 |
```

- [ ] **Step 2: Add 「中断后续跑」 note**

At the end of `### 3. 生成章节` (before `### 4. 查看故事线索`), append:

```markdown
**中断后续跑**：`write-chapter` 是幂等的——章节文件完整（长度达到 `generation.min_chapter_chars`）且评分留档中有通过记录的章节会被自动跳过，空文件或过短的半成品章节会被重写。生成中断后（崩溃、取消、断网）直接重跑同一条命令即可从断点继续，CLI 会打印 `Resuming from chapter N`。评分留档功能之前的旧项目没有 `reviews.jsonl`，此时只按文件长度判定。

章节采用原子写入（先写临时文件再改名），中断不会留下半截的 `001.md`；极少数情况下磁盘上可能残留 `.001.md.tmp` 之类的临时文件，下次运行时会自动清理，不影响导出。
```

- [ ] **Step 3: Check the 排错 entry**

Read the `### 章节没有从预期位置继续` entry (README.md:421). If it describes the old glob-based behavior ("以已存在的章节文件数为起点"), rewrite it to describe the completeness rule (文件长度 + 评分记录；空文件/过短会被重写；调大/调小 `min_chapter_chars` 的效果).

- [ ] **Step 4: Full gate**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy novel`
Expected: all PASS / clean.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: README — min_chapter_chars config + 中断后续跑 (idempotent write-chapter)"
```

---

## Self-Review

**1. Spec coverage:** completion rule (Task 2: file+length+passed, legacy fallback), `min_chapter_chars` config default 50 (Task 1), atomic write + reorder + tmp cleanup (Task 4), in-loop skip incl. hole scenario (Task 5), CLI + GUI shared logic + resume message (Tasks 6-7), tests 1-7 from the spec's test plan map to Tasks 2/3/5/6/7, README sync (Task 8). Spec's「错误处理」边界 (rewrite adds append-only review records, hand-deleted file, reason distinction) are covered by Task 5 tests + unchanged existing behavior. ✅

**2. Placeholder scan:** Every step contains complete, runnable code or exact commands; no TBD/TODO/"similar to Task N" (the Task 5 fixture intentionally repeats Task 4's setup per the repeat-don't-reference rule). ✅

**3. Type consistency:** `is_chapter_complete(proj, reviews, n, min_chars)` and `next_start_chapter(proj, reviews, min_chars)` signatures identical across resume.py, graph.py call site, cli.py, jobs.py. `min_chapter_chars` keyword name matches in `run_full_pipeline` signature and both call sites. `chapter_skipped` event uses existing keys (`chapter`, `reason`). ✅
