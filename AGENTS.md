# AGENTS.md

Multi-agent novel generation CLI (Python 3.11+, uv, typer, langgraph, litellm, chromadb). Nine agents (strategist, worldbuilder, character, outliner, writer, continuity, scorer, editor, extractor) run a fixed pipeline: premise → world/characters/outline → per-chapter writing with continuity checks and score-gated rewrites. Work chat mode runs an eleventh agent (`orchestrator`) whose only job is routing: each turn it reads a deterministic plan from `novel/workflow.py` (`build_plan`, spec'd single `next_action`) and dispatches to existing jobs via `novel/ui/chat.py` (append-only sessions under `.meta/chat/`). Longform (rolling outline) mode additionally runs a per-volume cast planner (message tag `cast_planner`, model slot `character`) before each volume is detailed. State lives in per-project story bible, vector memory, and chapter files.

## Commands

```bash
uv sync                    # install deps (use uv, not pip)
uv run pytest -q           # all tests (uses FakeProvider — no network, no API cost)
uv run ruff check .        # lint (line-length 100, target py311)
uv run mypy novel          # typecheck (strict mode, ignore_missing_imports)
uv run novel --help        # CLI entry point

cd ui-v2 && npm run test        # frontend unit tests (vitest + Testing Library, jsdom)
cd ui-v2 && npm run typecheck   # frontend typecheck (tsc --noEmit, strict)
cd ui-v2 && npm run build       # production build to ui-v2/dist (tsc --noEmit && vite build)
```

Run a single test file: `uv run pytest tests/test_graph.py -q`. Python commands run from the repo root; npm commands run from `ui-v2/`.

## Architecture / layer rules

- `novel/cli.py` — typer entry point (`uv run novel`). Provider selection lives in `novel/runtime.py` (`make_provider`: `NOVEL_LIVE=1` → litellm, else demo `FakeProvider`); both CLI and GUI use it.
- `novel/ui/` — Web GUI backend (`uv run novel-ui`, FastAPI). The console SPA lives in `ui-v2/` (React 18 + Vite + TypeScript strict + Ant Design 5, TanStack Query, react-router-dom, zustand; pages under `ui-v2/src/pages/`, shared components under `ui-v2/src/components/`). `app.py` serves the built SPA from `ui-v2/dist` at `/` (with an SPA deep-link fallback for routes like `/p/x/overview`) and keeps the legacy vanilla-JS UI in `novel/ui/static/` at `/legacy` until parity acceptance is finished; if `ui-v2/dist` is absent, `/` falls back to the legacy UI. Development is two processes: `uv run novel-ui` (API on 8765) plus `cd ui-v2 && npm run dev` (Vite dev server on 5173 proxying `/api`); run `cd ui-v2 && npm run build` before shipping so `novel-ui` serves the fresh SPA. `jobs.py` runs the synchronous pipeline in background threads (one active job per project), bridges human gates (`Job.gate` blocks on a `threading.Event` until the browser approves via `POST /api/gates/{id}`), and fans progress events out over SSE (`EventBus`). `app.py` is the API/routes layer.
- `novel/workflow.py` — deterministic workflow planner (pure `build_plan`): steps + single `next_action` + `available_actions`; sole authority for "what comes next" in Work mode.
- `novel/ui/chat.py` — Work-mode chat sessions (append-only `.meta/chat/*.jsonl`), one orchestrator decision per turn, action dispatch to existing JobManager jobs; double guard against concurrent jobs.
- `novel/providers.py` — `ModelProvider` protocol (`complete` / `complete_structured`). All model calls go through this; agents never call litellm directly.
- `novel/skills.py` — installable third-party skills (directive packages, NO code execution): `skills/<name>/skill.json` + per-target `.md`; `SkillProvider` wraps a ModelProvider and injects directives by agent tag; CLI `novel skill install/list/enable/disable`; every entrypoint passes `skills=load_skills(proj.root)` into `runtime.make_provider`.
- novel/tts.py — edge-tts 封装（预设音色表、参数校验、重试合成；demo 模式写静音占位 MP3）．
- `novel/agents/` — one file per role. All inherit `Agent[I, O]` in `base.py`: implement `build_messages()` and set `output_schema` (a pydantic model); `run()` handles validation-error retries.
- `novel/graph.py` — pipeline orchestration (`PipelineState`, chapter loop, scoring gates). `novel/scorer_rubrics.py` — score thresholds and rewrite/escalation decisions. `run_full_pipeline` emits progress events via optional `on_event` callback (event dicts with `type` in `stage`/`chapter_start`/`review`/`chapter_done`/`chapter_skipped`/`done`; the GUI's `Job.emit` reuses these as the SSE wire format) — keep CLI behavior unchanged by leaving it `None` there.
- `novel/memory/` — `assembler.py` (context assembly within token budget), `extractor.py` (post-chapter state extraction back into bible/memory).
- `novel/store/` — `bible.py` (story bible: `_canonical.json`, foreshadowing, events; every section overwrite snapshots the old version to `.meta/bible_versions/`), `vector.py` (chromadb vector memory), `reviews.py` (append-only scoring history at `.meta/reviews/reviews.jsonl`; every scorer attempt on a chapter is persisted by `run_full_pipeline`), `summaries.py` (章/卷/全书三级摘要 + 手改哈希检测：`chapters/_summaries/`、`.meta/summaries.json`、`.meta/threads_resolved.jsonl`).
- `novel/models.py` — shared pydantic schemas. `novel/config.py` — `ProjectConfig` / `ModelConfig` (per-agent provider, model, `api_base`, `api_key`, `timeout`; falls back to `default`, then first model).

New model outputs must be pydantic schemas; agents are typed generic `Agent[I, O]` and mypy strict must stay clean.

## Gotchas

- **Demo mode is the default.** Without `NOVEL_LIVE=1` no network calls happen; tests must keep using `FakeProvider`. This applies to both the CLI and `novel-ui` (GUI tests use FastAPI `TestClient`, see `tests/test_ui.py`).
- **`novel-ui` gates only fire in live mode** (same as CLI); demo-mode GUI runs have no approval prompts. Cancellation takes effect at the next `on_event` emit (chapter/stage boundary).
- **`project.config.yaml` is gitignored and contains plaintext API keys** — never commit, copy, or paste it anywhere. `demo-novel/`, `*-novel/`, and `docs/superpowers/specs/` are also gitignored by design, as are `ui-v2/node_modules/` and `ui-v2/dist/` — `tests/test_ui.py::test_ui_v2_dist_served` is `skipif`-guarded on dist existing, so CI without Node stays green.
- Chapters are `chapters/001.md`-style three-digit files; continuation logic only recognizes that format — don't rename. `runs/` is scaffolded but still unused; review history lives in `.meta/reviews/reviews.jsonl` (not `runs/`).
- `chapters/_summaries/NNN.json` 与 `.meta/` 下的摘要/伏笔归档文件存在即用、缺失即降级，不影响 resume 判定.
- `language: zh|en` in project config controls output language of all agents in live mode; prompts and code identifiers are otherwise English.
- OpenAI-compatible endpoints (ollama, vLLM, etc.) always use `provider: openai` + `api_base`; local models need a non-empty placeholder `api_key` and often a larger `timeout`.
- Human gates in live mode only accept `a`/Enter; anything else aborts that stage.

## Docs to read before sensitive changes

- `README.md` — full config field reference and troubleshooting (keep it in sync when config/CLI behavior changes).
- `docs/superpowers/runbooks/live-run.md` — live-LLM end-to-end procedure (not run in CI).
- `docs/superpowers/plans/` — design history for the pipeline and prompts.
