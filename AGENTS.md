# AGENTS.md

Multi-agent novel generation CLI (Python 3.11+, uv, typer, langgraph, litellm, chromadb). Nine agents (strategist, worldbuilder, character, outliner, writer, continuity, scorer, editor, extractor) run a fixed pipeline: premise → world/characters/outline → per-chapter writing with continuity checks and score-gated rewrites. State lives in per-project story bible, vector memory, and chapter files.

## Commands

```bash
uv sync                    # install deps (use uv, not pip)
uv run pytest -q           # all tests (uses FakeProvider — no network, no API cost)
uv run ruff check .        # lint (line-length 100, target py311)
uv run mypy novel          # typecheck (strict mode, ignore_missing_imports)
uv run novel --help        # CLI entry point
```

Run a single test file: `uv run pytest tests/test_graph.py -q`. All commands run from the repo root.

## Architecture / layer rules

- `novel/cli.py` — typer entry point (`uv run novel`). Provider selection lives in `novel/runtime.py` (`make_provider`: `NOVEL_LIVE=1` → litellm, else demo `FakeProvider`); both CLI and GUI use it.
- `novel/ui/` — Web GUI (`uv run novel-ui`, FastAPI + vanilla JS in `ui/static/`, no build step). `jobs.py` runs the synchronous pipeline in background threads (one active job per project), bridges human gates (`Job.gate` blocks on a `threading.Event` until the browser approves via `POST /api/gates/{id}`), and fans progress events out over SSE (`EventBus`). `app.py` is the API/routes layer.
- `novel/providers.py` — `ModelProvider` protocol (`complete` / `complete_structured`). All model calls go through this; agents never call litellm directly.
- `novel/agents/` — one file per role. All inherit `Agent[I, O]` in `base.py`: implement `build_messages()` and set `output_schema` (a pydantic model); `run()` handles validation-error retries.
- `novel/graph.py` — pipeline orchestration (`PipelineState`, chapter loop, scoring gates). `novel/scorer_rubrics.py` — score thresholds and rewrite/escalation decisions. `run_full_pipeline` emits progress events via optional `on_event` callback (event dicts with `type` in `stage`/`chapter_start`/`review`/`chapter_done`/`chapter_skipped`/`done`; the GUI's `Job.emit` reuses these as the SSE wire format) — keep CLI behavior unchanged by leaving it `None` there.
- `novel/memory/` — `assembler.py` (context assembly within token budget), `extractor.py` (post-chapter state extraction back into bible/memory).
- `novel/store/` — `bible.py` (story bible: `_canonical.json`, foreshadowing, events), `vector.py` (chromadb vector memory), `reviews.py` (append-only scoring history at `.meta/reviews/reviews.jsonl`; every scorer attempt on a chapter is persisted by `run_full_pipeline`).
- `novel/models.py` — shared pydantic schemas. `novel/config.py` — `ProjectConfig` / `ModelConfig` (per-agent provider, model, `api_base`, `api_key`, `timeout`; falls back to `default`, then first model).

New model outputs must be pydantic schemas; agents are typed generic `Agent[I, O]` and mypy strict must stay clean.

## Gotchas

- **Demo mode is the default.** Without `NOVEL_LIVE=1` no network calls happen; tests must keep using `FakeProvider`. This applies to both the CLI and `novel-ui` (GUI tests use FastAPI `TestClient`, see `tests/test_ui.py`).
- **`novel-ui` gates only fire in live mode** (same as CLI); demo-mode GUI runs have no approval prompts. Cancellation takes effect at the next `on_event` emit (chapter/stage boundary).
- **`project.config.yaml` is gitignored and contains plaintext API keys** — never commit, copy, or paste it anywhere. `demo-novel/`, `*-novel/`, and `docs/superpowers/specs/` are also gitignored by design.
- Chapters are `chapters/001.md`-style three-digit files; continuation logic only recognizes that format — don't rename. `runs/` is scaffolded but still unused; review history lives in `.meta/reviews/reviews.jsonl` (not `runs/`).
- `language: zh|en` in project config controls output language of all agents in live mode; prompts and code identifiers are otherwise English.
- OpenAI-compatible endpoints (ollama, vLLM, etc.) always use `provider: openai` + `api_base`; local models need a non-empty placeholder `api_key` and often a larger `timeout`.
- Human gates in live mode only accept `a`/Enter; anything else aborts that stage.

## Docs to read before sensitive changes

- `README.md` — full config field reference and troubleshooting (keep it in sync when config/CLI behavior changes).
- `docs/superpowers/runbooks/live-run.md` — live-LLM end-to-end procedure (not run in CI).
- `docs/superpowers/plans/` — design history for the pipeline and prompts.
