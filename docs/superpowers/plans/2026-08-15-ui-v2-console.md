# UI v2 控制台（React + AntD）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the novel GUI as a console-style SPA (`ui-v2/`, React 18 + Vite + TypeScript + Ant Design 5) with full feature parity plus the critique revisions R1-R6, served by the existing FastAPI app, replacing the vanilla-JS UI after acceptance.

**Architecture:** Independent npm package `ui-v2/` talking only to existing `/api/*` + SSE (one new read-only endpoint). Dev = two processes (FastAPI 8765 + Vite 5173 with proxy); prod = `novel-ui` mounts `ui-v2/dist` at `/`, legacy static at `/legacy` until parity acceptance. Global SSE event store (zustand) feeds a persistent JobStrip (R2) and a global GateModal (R4) with focus trap + live-region (R6).

**Tech Stack:** React 18, Vite, TypeScript (strict), AntD 5, @tanstack/react-query, react-router-dom, zustand; vitest + Testing Library (jsdom). Python side: FastAPI, pytest (TestClient).

**Spec:** `docs/superpowers/specs/2026-08-15-ui-v2-console-design.md` (incl. 设计修订 R1-R6 section — it OVERRIDES conflicting earlier text; read it first).

## Global Constraints

- Python gates unchanged: `uv run pytest -q`, `uv run ruff check .`, `uv run mypy novel` must stay green after every task (backend tasks) or be demonstrably unaffected (frontend-only tasks — still run the Python gate before commits that touch `novel/`).
- Frontend gates: `npm run typecheck` (tsc --noEmit) and `npm run test` (vitest run) must pass before every `ui-v2` commit; `npm run build` must succeed before tasks that mount dist (T10).
- Node >= 20, npm (no pnpm in this env). If `npm install` cannot reach the registry, report BLOCKED — do not vendor tarballs.
- Do NOT delete `novel/ui/static/` in this plan (removal is a post-acceptance follow-up; legacy stays at `/legacy`).
- AntD component API is the design system — no custom CSS beyond `src/index.css` tokens; no extra runtime deps beyond: react, react-dom, antd, @tanstack/react-query, react-router-dom, zustand.
- Every page/component file stays focused; shared display helpers live in `src/components/`.

## Reference facts (do not re-derive)

- Existing API (novel/ui/app.py): `GET /api/mode`; `GET/POST /api/projects`; `GET /api/projects/{n}/status` (returns name/has_concept/has_world/has_outline/chapters/open_threads/score_min/job{id,kind,status,error}); `POST /api/projects/{n}/premise` `{text}`→202 {job_id}; `POST /api/projects/{n}/setup` `{premise}`→202 (422 if no premise & no concept; 409 if a job runs); `POST /api/projects/{n}/write-chapter` `{n}`→202; `GET /api/projects/{n}/chapters/{num}`→{chapter,content}; `GET .../threads`→[{id,description,status}]; `GET .../reviews`→[{chapter,attempt,artifact_type,overall,summary,passed,timestamp,scores:{name:{score,critique}}}]; `POST .../export`→{path}; `GET .../events` (SSE: `data: {json}\n\n`); `POST /api/gates/{id}` `{approve,feedback?}`; `POST /api/jobs/{id}/cancel`; `GET /api/jobs/{id}`→{id,kind,status,error,project,gates:[{id,label}]} (pending only).
- SSE event types: `stage{stage,chapter?}`, `chapter_start{chapter,title}`, `review{chapter,attempt,passed,overall}`, `chapter_done{chapter}`, `chapter_skipped{chapter,reason}`, `premise_done{genre}`, `setup_stage{stage,attempt,artifact?,skipped?,reason?}`, `gate{gate_id,label,artifact}`, `job_end{status,error,kind}`; every event also carries `job_id`.
- Gate labels: `outline`, `chapter`, `chapter_review_failed`, `setup:concept|world|characters|outline`.
- Legacy copy assets to preserve (novel/ui/static/app.js STAGE_NAMES/GATE_LABELS) migrate to `src/constants.ts`.
- `demo_provider` writer prose ≈62 chars; demo chapters are valid resume-wise (min_chapter_chars=50).
- FastAPI app factory `create_app(root)` mounts static at `/` (app.py:220).

## File Structure

```
ui-v2/
├── package.json  vite.config.ts  tsconfig.json  index.html  src/index.css
├── src/
│   ├── main.tsx  App.tsx
│   ├── constants.ts                # STAGE_NAMES / GATE_LABELS / SETUP_STAGE_NAMES (migrated copy)
│   ├── api/client.ts  api/types.ts
│   ├── api/hooks.ts                # TanStack Query hooks
│   ├── api/events.ts               # useProjectEvents SSE hook (reconnect + reconcile R3)
│   ├── stores/events.ts            # zustand: log lines, current gate, job state, connection
│   ├── components/JobStrip.tsx  components/GateModal.tsx  components/ArtifactView.tsx
│   │   └── components/Trend.tsx    # inline-SVG score trend (no chart dep)
│   └── pages/Projects.tsx Overview.tsx Setup.tsx Generate.tsx Reader.tsx
│       Reviews.tsx Threads.tsx Export.tsx
└── tests/{setup.ts, App.test.tsx, events.test.ts, GateModal.test.tsx, pages.test.tsx}
```

---

### Task 1: Scaffold `ui-v2/` + tooling

**Files:** Create everything under `ui-v2/` (gitignore `ui-v2/node_modules`, `ui-v2/dist` in root `.gitignore`).

- [ ] **Step 1: Create package + configs** (do NOT use `npm create vite` scaffolding — write files directly, then install):

`ui-v2/package.json`:
```json
{
  "name": "novel-ui-v2",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "test": "vitest run",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "@tanstack/react-query": "^5.0.0",
    "antd": "^5.0.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "react-router-dom": "^6.26.0",
    "zustand": "^5.0.0"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.0.0",
    "@testing-library/react": "^16.0.0",
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.0.0",
    "jsdom": "^25.0.0",
    "typescript": "^5.5.0",
    "vite": "^5.4.0",
    "vitest": "^2.0.0"
  }
}
```

`ui-v2/vite.config.ts`:
```ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8765", changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
  },
});
```

`ui-v2/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "skipLibCheck": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src", "tests"]
}
```

`ui-v2/index.html`:
```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>小说生成控制台</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`ui-v2/src/index.css`:
```css
html, body, #root { height: 100%; margin: 0; }
body { font-family: -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; }
```

`ui-v2/src/main.tsx`:
```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

`ui-v2/src/App.tsx` (temporary shell; T4 replaces):
```tsx
export default function App() {
  return <div data-testid="app-shell">novel console</div>;
}
```

`ui-v2/tests/setup.ts`:
```ts
import "@testing-library/jest-dom/vitest";
```

`ui-v2/tests/App.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import App from "../src/App";

test("app shell renders", () => {
  render(<App />);
  expect(screen.getByTestId("app-shell")).toBeInTheDocument();
});
```

- [ ] **Step 2: Install and verify**

```bash
cd ui-v2 && npm install && npm run typecheck && npm run test
```
Expected: install succeeds; typecheck clean; 1 test passes. (If the registry is unreachable → report BLOCKED.)

- [ ] **Step 3: Root .gitignore additions**

Append to `/home/gdmax/write-agent/.gitignore`:
```
ui-v2/node_modules/
ui-v2/dist/
```

- [ ] **Step 4: Commit**

```bash
git add ui-v2 .gitignore
git commit -m "feat(ui-v2): Vite+React+TS+AntD scaffold with vitest tooling"
```

---

### Task 2: API layer, types, SSE hook + event store

**Files:** Create `ui-v2/src/api/types.ts`, `api/client.ts`, `api/hooks.ts`, `api/events.ts`, `src/stores/events.ts`, `src/constants.ts`; tests `tests/events.test.ts`.

- [ ] **Step 1: types** — `src/api/types.ts`:
```ts
export interface ProjectStatus {
  name: string;
  has_concept: boolean;
  has_world: boolean;
  has_outline: boolean;
  chapters: number[];
  open_threads: number;
  score_min: number;
  job: { id: string; kind: string; status: string; error: string | null } | null;
}
export interface ReviewRecord {
  chapter: number;
  attempt: number;
  artifact_type: string;
  overall: number;
  summary: string;
  passed: boolean;
  timestamp: string;
  scores: Record<string, { score: number; critique: string }>;
}
export interface Thread { id: string; description: string; status: string; }
export interface JobInfo {
  id: string; kind: string; status: string;
  error: string | null; project: string;
  gates: { id: string; label: string }[];
}
export interface OutlineInfo {
  arcs: { arc_name: string; chapters: { chapter_no: number; chapter_title: string }[] }[];
}
export type SseEvent = Record<string, unknown> & { type: string; job_id?: string };
```

- [ ] **Step 2: client + constants** — `src/api/client.ts`:
```ts
export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}
export async function api<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers ?? {}) },
    ...opts,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* ignore */ }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}
```
`src/constants.ts` (copy the Chinese copy from novel/ui/static/app.js STAGE_NAMES/GATE_LABELS/SETUP_STAGE_NAMES, plus `API` path builders `p = (n: string) => \`/api/projects/${n}\``).

- [ ] **Step 3: event store** — `src/stores/events.ts` (zustand):
```ts
import { create } from "zustand";
import type { SseEvent } from "../api/types";

export interface LogLine { time: string; text: string }
interface EventState {
  connected: boolean;
  lines: LogLine[];
  gate: { id: string; label: string; artifact: string } | null;
  job: { id: string; kind: string } | null;
  progress: { done: number; total: number } | null;
  pushLine: (text: string) => void;
  setConnected: (v: boolean) => void;
  apply: (ev: SseEvent) => void;
  reset: () => void;
}
const MAX_LINES = 500;
const fmt = () => new Date().toLocaleTimeString("zh-CN", { hour12: false });

export const useEvents = create<EventState>((set) => ({
  connected: false,
  lines: [],
  gate: null,
  job: null,
  progress: null,
  pushLine: (text) =>
    set((s) => ({ lines: [...s.lines, { time: fmt(), text }].slice(-MAX_LINES) })),
  setConnected: (v) => set({ connected: v }),
  apply: (ev) =>
    set((s) => {
      const patch: Partial<EventState> = {};
      if (ev.job_id && typeof ev.job_id === "string") patch.job = { id: ev.job_id, kind: String((ev as { kind?: string }).kind ?? s.job?.kind ?? "") };
      switch (ev.type) {
        case "gate":
          patch.gate = {
            id: String(ev.gate_id), label: String(ev.label),
            artifact: String(ev.artifact ?? ""),
          };
          break;
        case "job_end":
          patch.job = null; patch.gate = null; patch.progress = null;
          break;
        case "chapter_done":
          patch.progress = s.progress
            ? { ...s.progress, done: s.progress.done + 1 } : s.progress;
          break;
      }
      return patch;
    }),
  reset: () => set({ connected: false, lines: [], gate: null, job: null, progress: null }),
}));
```

- [ ] **Step 4: SSE hook with reconnect+reconcile (R3)** — `src/api/events.ts`:
```ts
import { useEffect } from "react";
import { api } from "./client";
import type { JobInfo, ProjectStatus, SseEvent } from "./types";
import { useEvents } from "../stores/events";

export function useProjectEvents(project: string | undefined): void {
  const apply = useEvents((s) => s.apply);
  const setConnected = useEvents((s) => s.setConnected);
  const pushLine = useEvents((s) => s.pushLine);

  useEffect(() => {
    if (!project) return;
    const store = useEvents.getState();
    store.reset();
    let es: EventSource | null = null;
    let stopped = false;
    let retry: ReturnType<typeof setTimeout> | null = null;

    async function reconcile() {
      // R3: after a reconnect, distrust local state; re-read facts first
      try {
        const status = await api<ProjectStatus>(`/api/projects/${project}/status`);
        if (status.job) {
          const job = await api<JobInfo>(`/api/jobs/${status.job.id}`);
          for (const g of job.gates) {
            useEvents.getState().apply({
              type: "gate", gate_id: g.id, label: g.label, artifact: "",
              job_id: job.id,
            } as SseEvent);
          }
        }
      } catch { /* next reconnect will retry */ }
    }

    function connect() {
      if (stopped) return;
      es = new EventSource(`/api/projects/${project}/events`);
      es.onopen = () => { setConnected(true); void reconcile(); };
      es.onmessage = (m) => {
        try { apply(JSON.parse(m.data) as SseEvent); } catch { /* ignore */ }
      };
      es.onerror = () => {
        setConnected(false);
        es?.close();
        if (!stopped) retry = setTimeout(connect, 2000);
      };
    }
    connect();
    return () => {
      stopped = true;
      if (retry) clearTimeout(retry);
      es?.close();
      setConnected(false);
    };
  }, [project, apply, setConnected, pushLine]);
}
```
(The hook stores raw events; human-readable log lines are derived by pages/components so the store stays presentational-data only — pushLine is used by consumers. Remove `pushLine` from the dependency array if unused in this file.)

- [ ] **Step 5: query hooks** — `src/api/hooks.ts`: TanStack Query v5 hooks, each one `useQuery`/`useMutation` with explicit types: `useProjects`, `useStatus(name)`, `useChapter(name, n)`, `useReviews(name)`, `useThreads(name)`, `useMode`, `useOutline(name)` (endpoint arrives in T3 — write the hook now, tests mock fetch), plus mutations `useCreateProject`, `usePremise`, `useSetup`, `useWriteChapters`, `useExport`, `useResolveGate`, `useCancelJob` (`useMutation` + `queryClient.invalidateQueries`). Complete code follows the standard TanStack pattern; invalidate `["status", name]` and `["projects"]` on success. API error rethrow so pages can surface 409/422.

- [ ] **Step 6: tests** — `tests/events.test.ts`:
```ts
import { useEvents } from "../src/stores/events";

describe("event store", () => {
  beforeEach(() => useEvents.getState().reset());

  test("gate event sets current gate; job_end clears it", () => {
    useEvents.getState().apply({ type: "gate", gate_id: "g1", label: "setup:concept", artifact: "{}", job_id: "j1" });
    expect(useEvents.getState().gate?.id).toBe("g1");
    useEvents.getState().apply({ type: "job_end", job_id: "j1" });
    expect(useEvents.getState().gate).toBeNull();
    expect(useEvents.getState().job).toBeNull();
  });

  test("chapter_done increments progress", () => {
    useEvents.getState().apply({ type: "chapter_start", job_id: "j1" });
    // progress initialized by Generate page; simulate:
    useEvents.setState({ progress: { done: 0, total: 3 } });
    useEvents.getState().apply({ type: "chapter_done", chapter: 1, job_id: "j1" });
    expect(useEvents.getState().progress).toEqual({ done: 1, total: 3 });
  });

  test("log lines capped at 500", () => {
    for (let i = 0; i < 520; i++) useEvents.getState().pushLine(`l${i}`);
    expect(useEvents.getState().lines.length).toBe(500);
    expect(useEvents.getState().lines[0].text).toBe("l20");
  });
});
```

- [ ] **Step 7: gates**

`cd ui-v2 && npm run typecheck && npm run test` → clean. From repo root `uv run pytest -q` → 111 passed (untouched).

- [ ] **Step 8: Commit**

```bash
git add ui-v2
git commit -m "feat(ui-v2): API client/types, query hooks, SSE store with reconnect+reconcile"
```

---

### Task 3: Backend read-only outline endpoint

**Files:** Modify `novel/ui/app.py`; test: append to `tests/test_ui.py`.

- [ ] **Step 1: failing test**

```python
def test_outline_endpoint(client: TestClient) -> None:
    client.post("/api/projects", json={"name": "po"})
    job_id = client.post("/api/projects/po/premise", json={"text": "x"}).json()["job_id"]
    assert _wait_job(client, job_id)["status"] == "done"
    r = client.post("/api/projects/po/write-chapter", json={"n": 1})
    assert _wait_job(client, r.json()["job_id"])["status"] == "done"
    outline = client.get("/api/projects/po/outline").json()
    titles = [c["chapter_title"] for arc in outline["arcs"] for c in arc["chapters"]]
    assert titles == ["T1", "T2", "T3"][: len(titles)] and len(titles) == 3
    assert set(outline["arcs"][0]["chapters"][0]) == {"chapter_no", "chapter_title"}
    assert client.get("/api/projects/nope/outline").status_code == 404
```
(demo outline has chapters T1..T3.)

- [ ] **Step 2: run** → 404 FAIL.

- [ ] **Step 3: implement** in `novel/ui/app.py` after `get_threads`:
```python
    @app.get("/api/projects/{name}/outline")
    def get_outline(name: str) -> dict[str, object]:
        p = _safe_project(root, name)
        from novel.models import Outline
        from novel.project import NovelProject
        from novel.store.bible import StoryBible
        outline: Outline | None = StoryBible(NovelProject(root=p)).get_outline()
        if outline is None:
            return {"arcs": []}
        return {"arcs": [
            {"arc_name": a.arc_name,
             "chapters": [{"chapter_no": c.chapter_no, "chapter_title": c.chapter_title}
                          for c in a.chapters]}
            for a in outline.arcs]}
```

- [ ] **Step 4:** `uv run pytest tests/test_ui.py -q && uv run ruff check . && uv run mypy novel` → green.

- [ ] **Step 5: Commit**

```bash
git add novel/ui/app.py tests/test_ui.py
git commit -m "feat(ui-v2): read-only GET /api/projects/{name}/outline for chapter titles"
```

---

### Task 4: App shell — Layout, Sider groups, Header, JobStrip, routing

**Files:** Replace `ui-v2/src/App.tsx`; create `src/components/JobStrip.tsx`, 8 stub pages under `src/pages/`; test `tests/App.test.tsx` (replace).

- [ ] **Step 1: stub pages** — each of `src/pages/{Projects,Overview,Setup,Generate,Reader,Reviews,Threads,Export}.tsx`:
```tsx
import { useParams } from "react-router-dom";
export default function Overview() {
  const { name = "" } = useParams();
  return <div data-testid="page-overview">{name}</div>;
}
```
(unique `data-testid` per page; only Projects/Overview needed for routing now — create all 8 stubs so routes are stable.)

- [ ] **Step 2: JobStrip (R2)** — `src/components/JobStrip.tsx`:
```tsx
import { Alert, Button, Space, Tag, Typography } from "antd";
import { useNavigate } from "react-router-dom";
import { useEvents } from "../stores/events";
import { STAGE_NAMES } from "../constants";
import { useCancelJob } from "../api/hooks";

export default function JobStrip({ project }: { project: string }) {
  const { job, progress, gate, connected } = useEvents();
  const navigate = useNavigate();
  const cancel = useCancelJob();
  if (!job) return null;
  const stage = ""; // current stage text is appended to log lines by Generate; strip shows coarse state
  return (
    <Alert
      data-testid="job-strip"
      type={gate ? "warning" : "info"}
      showIcon
      message={
        <Space wrap>
          <Typography.Text strong>
            {gate ? "等待审批" : "任务进行中"}
          </Typography.Text>
          {gate ? <Tag color="orange">{gate.label}</Tag> : null}
          {progress && progress.total
            ? <Tag>章节 {Math.min(progress.done, progress.total)}/{progress.total}</Tag>
            : null}
          {!connected && <Tag color="red">连接断开，重连中…</Tag>}
          <Button size="small" onClick={() => navigate(`/p/${project}/generate`)}>
            查看进度
          </Button>
          <Button size="small" danger onClick={() => job && cancel.mutate(job.id)}>
            取消任务
          </Button>
          <span style={{ display: "none" }} aria-live="polite">{stage}</span>
        </Space>
      }
    />
  );
}
```
(Wire a live-region announcement of stage changes from the store in this task — add `lastStage` to the store, set in `apply` for `stage` events, render it in the hidden live region instead of the empty string.)

- [ ] **Step 3: App.tsx** — AntD Layout + router:
```tsx
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes, useParams } from "react-router-dom";
import { Layout, Menu, Select, Tag } from "antd";
import { useLocation, useNavigate } from "react-router-dom";
import { useMode, useProjects } from "./api/hooks";
import { useProjectEvents } from "./api/events";
import JobStrip from "./components/JobStrip";
import Projects from "./pages/Projects";
import Overview from "./pages/Overview";
import Setup from "./pages/Setup";
import Generate from "./pages/Generate";
import Reader from "./pages/Reader";
import Reviews from "./pages/Reviews";
import Threads from "./pages/Threads";
import Export from "./pages/Export";

const qc = new QueryClient();

function Shell() {
  const { name = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const { data: mode } = useMode();
  const { data: projects = [] } = useProjects();
  useProjectEvents(name || undefined);
  const items = [
    { type: "group" as const, label: "创作", children: [
      { key: "overview", label: "概览" },
      { key: "setup", label: "分阶段设定" },
      { key: "generate", label: "生成章节" },
      { key: "reader", label: "章节阅读" },
    ]},
    { type: "group" as const, label: "审阅与输出", children: [
      { key: "reviews", label: "评分历史" },
      { key: "threads", label: "伏笔台账" },
      { key: "export", label: "导出" },
    ]},
  ];
  const selected = location.pathname.split("/")[3] ?? "overview";
  return (
    <Layout style={{ height: "100%" }}>
      <Layout.Sider width={200} theme="light" breakpoint="lg" collapsible>
        <div style={{ padding: 16, fontWeight: 600 }}>小说控制台</div>
        <Menu mode="inline" selectedKeys={[selected]} items={items}
          onSelect={({ key }) => navigate(`/p/${name}/${key}`)} />
      </Layout.Sider>
      <Layout>
        <Layout.Header style={{ background: "#fff", paddingInline: 16, display: "flex",
                                 alignItems: "center", gap: 12 }}>
          <Select style={{ minWidth: 180 }} placeholder="选择项目…" value={name || undefined}
            options={projects.map((p) => ({ value: p.name, label: p.name }))}
            onChange={(v) => navigate(`/p/${v}/overview`)} />
          <Tag color={mode?.live ? "green" : "default"}>
            {mode?.live ? "真实模型模式" : "演示模式"}
          </Tag>
        </Layout.Header>
        <div style={{ padding: "0 16px" }}>
          {name ? <JobStrip project={name} /> : null}
        </div>
        <Layout.Content style={{ padding: 16, overflow: "auto" }}>
          <Routes>
            <Route index element={<Projects />} />
            <Route path="p/:name/overview" element={<Overview />} />
            <Route path="p/:name/setup" element={<Setup />} />
            <Route path="p/:name/generate" element={<Generate />} />
            <Route path="p/:name/reader" element={<Reader />} />
            <Route path="p/:name/reviews" element={<Reviews />} />
            <Route path="p/:name/threads" element={<Threads />} />
            <Route path="p/:name/export" element={<Export />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Layout.Content>
      </Layout>
    </Layout>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <ConfigProvider locale={zhCN}>
        <BrowserRouter>
          <Routes>
            <Route path="/*" element={<Shell />} />
          </Routes>
        </BrowserRouter>
      </ConfigProvider>
    </QueryClientProvider>
  );
}
```

- [ ] **Step 4: tests** — replace `tests/App.test.tsx`: render `<App />` inside `MemoryRouter` with a fetch mock returning `{ live: false }` for `/api/mode` and `[]` for `/api/projects`; assert: 项目选择器 renders, Sider has both groups (创作 / 审阅与输出) with 7 items total, mode badge shows 演示模式. Render a `/p/x/overview` route and assert `page-overview` + JobStrip absence when no job.

- [ ] **Step 5: gates + commit**

`cd ui-v2 && npm run typecheck && npm run test` → clean; `uv run pytest -q` → 112 passed.
```bash
git add ui-v2
git commit -m "feat(ui-v2): console shell — grouped Sider, project selector, mode badge, JobStrip"
```

---

### Task 5: GateModal (global, R4 + a11y R6)

**Files:** Create `ui-v2/src/components/GateModal.tsx`; wire into Shell (render once under JobStrip); test `tests/GateModal.test.tsx`.

- [ ] **Step 1: component**
```tsx
import { App as AntApp } from "antd";
import { useEffect, useRef, useState } from "react";
import { Modal, Input, Button, Space, Typography, Alert } from "antd";
import { Link } from "react-router-dom";
import { useEvents } from "../stores/events";
import { useResolveGate } from "../api/hooks";
import { GATE_LABELS, SETUP_STAGE_NAMES } from "../constants";

export default function GateModal({ project }: { project: string }) {
  const { gate } = useEvents();
  const resolve = useResolveGate();
  const [feedback, setFeedback] = useState("");
  const [confirmForce, setConfirmForce] = useState(false);
  const openerRef = useRef<HTMLElement | null>(null);
  const { message } = AntApp.useApp();

  useEffect(() => {
    if (gate) {
      openerRef.current = document.activeElement as HTMLElement | null;
      setFeedback(""); setConfirmForce(false);
    } else if (openerRef.current) {
      openerRef.current.focus(); openerRef.current = null;
    }
  }, [gate]);

  if (!gate) return null;
  const isSetup = gate.label.startsWith("setup:");
  const isForce = gate.label === "chapter_review_failed";
  const title = isSetup
    ? `设定阶段：${SETUP_STAGE_NAMES[gate.label.slice(6)] ?? gate.label.slice(6)} — 通过还是修改？`
    : (GATE_LABELS[gate.label] ?? gate.label);

  async function submit(approve: boolean, fb = "") {
    if (!approve && isSetup && !fb.trim()) {
      message.warning("请填写修改意见，或点击「通过」");
      return;
    }
    if (approve && isForce && !confirmForce) {
      setConfirmForce(true);
      return;
    }
    try {
      await resolve.mutateAsync({ id: gate!.id, approve, feedback: fb });
    } catch (e) {
      message.error(String(e));
    }
  }

  return (
    <Modal
      open title={title} closable={false} footer={null}
      width={720} data-testid="gate-modal"
      aria-live="polite"
    >
      <pre style={{ whiteSpace: "pre-wrap", maxHeight: 320, overflow: "auto" }}>
        {gate.artifact.slice(0, 4000)}
      </pre>
      {gate.label === "chapter" && (
        <Typography.Paragraph>
          <Link to={`/p/${project}/reader`}>查看本章</Link>
        </Typography.Paragraph>
      )}
      {isSetup && (
        <Input.TextArea data-testid="gate-feedback" rows={3} value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          placeholder="修改意见（自然语言），系统会带着意见重新生成该阶段…" />
      )}
      {isForce && confirmForce && (
        <Alert type="warning" showIcon style={{ marginTop: 8 }}
          message="强行放行不可撤销：该章将以未达标状态保存。确认放行？" />
      )}
      <Space style={{ marginTop: 12 }}>
        <Button type="primary" onClick={() => submit(true)}>
          {isForce && confirmForce ? "确认强行放行" : "通过"}
        </Button>
        <Button danger={isForce && confirmForce} onClick={() => submit(false, feedback)}>
          {isSetup ? "带反馈重生成" : isForce ? "放行前再想想（取消）" : "拒绝"}
        </Button>
      </Space>
    </Modal>
  );
}
```
(Focus trap: AntD Modal traps focus by default; verify in test that focus returns to the opener on close by simulating `gate → null`. The feedback history strip (R4): render prior feedback lines — add `feedbackHistory: string[]` to the store, appended when a `setup_stage` event with `attempt > 1` arrives after a rejection; display above the textarea. Implement in this task.)

- [ ] **Step 2: tests** (`tests/GateModal.test.tsx`) with the store driven directly:
  - `gate` null → no modal; set gate `setup:world` → modal renders, feedback textarea present, empty-feedback reject shows warning and does NOT call fetch;
  - approve on `chapter_review_failed` → first click only enters confirm state (warning shown), second click POSTs `{approve: true}`;
  - set gate `chapter` → 「查看本章」link present;
  - opener focus restored after gate clears.
  Mock `api` via `vi.stubGlobal("fetch", ...)`.

- [ ] **Step 3: gates + commit** — `npm run typecheck && npm run test`; `uv run pytest -q` unchanged.
```bash
git add ui-v2
git commit -m "feat(ui-v2): global GateModal — setup feedback, force-pass confirm, focus/live-region"
```

---

### Task 6: Setup page (R1 Step 0 + structured artifacts R5)

**Files:** `ui-v2/src/pages/Setup.tsx`, `src/components/ArtifactView.tsx`; tests in `tests/pages.test.tsx`.

- [ ] **Step 1: ArtifactView** — renders a setup artifact (JSON string from `setup_stage.artifact` / gate artifact) as AntD Descriptions per known schemas; unknown shapes fall back to key/value listing:
```tsx
import { Card, Descriptions, Empty, Tag, Typography } from "antd";

const FIELD_LABELS: Record<string, string> = {
  logline: "一句话概念", genre: "类型", tone: "基调", themes: "主题",
  target_length_words: "目标字数", audience: "读者画像", setting: "舞台设定",
  id: "ID", slug: "别名", name: "姓名", role: "角色", backstory: "背景",
  motivation: "动机", arc: "人物弧", chapter_no: "章号", chapter_title: "章标题",
};

export function ArtifactView({ raw, title }: { raw: string; title?: string }) {
  let data: Record<string, unknown> | unknown[] | null = null;
  try { data = JSON.parse(raw); } catch { data = null; }
  if (data == null) return raw.trim() ? <pre style={{whiteSpace:"pre-wrap"}}>{raw}</pre> : <Empty />;
  const items = Array.isArray(data) ? data : [data];
  return (
    <Card size="small" title={title}>
      {items.map((obj, i) => {
        if (typeof obj !== "object" || obj === null) return <Typography.Paragraph key={i}>{String(obj)}</Typography.Paragraph>;
        return (
          <Descriptions key={i} size="small" bordered column={1}
            items={Object.entries(obj as Record<string, unknown>)
              .filter(([k]) => k !== "state" && k !== "voice_fingerprint" && k !== "mannerisms" && k !== "beats")
              .map(([k, v]) => ({
                key: k, label: FIELD_LABELS[k] ?? k,
                children: Array.isArray(v)
                  ? (v as unknown[]).map((x, j) => <Tag key={j}>{String(typeof x === "object" ? JSON.stringify(x) : x)}</Tag>)
                  : (typeof v === "object" && v !== null ? JSON.stringify(v) : String(v ?? "")),
              }))} />
        );
      })}
    </Card>
  );
}
```
(For character lists, render one Descriptions per character; for outline render arc + chapter rows; long-text fields like backstory get `whiteSpace: pre-wrap` styling. Keep it deterministic and tested on the demo artifacts' real shapes — write the test from actual `setup_stage.artifact` payloads captured via the demo run in Task 10's smoke.)

- [ ] **Step 2: Setup page** — AntD Steps with 5 steps: 创意(0) → 概念(1) → 世界观(2) → 人物(3) → 大纲(4).
  - Step 0: premise `Input.TextArea` + genre input + 「生成概念」button → `usePremise` mutation → on 202 show 「生成中…」(status via SSE `premise_done`); if `status.has_concept`, mark step 0 done and allow 直接进入阶段 1.
  - Steps 1-4: 「开始分阶段设定」→ `useSetup({ premise: "" })`; the page renders the latest `setup_stage` event's artifact via `ArtifactView`, stage completion from `status.has_concept/has_world/has_outline` + characters (needs characters presence — use `status.has_concept` chain; if status lacks a characters flag, derive from outline presence as the terminal proxy and note it).
  - While a setup job runs, the GateModal owns approval; the page shows the Steps state and the feedback history from the store.
  - Empty state when nothing run yet: guiding copy 「从一句创意开始，逐步确认概念、世界观、人物与大纲」.
  - Demo notice (R6): if `mode.live === false`, show one-time `Alert` info 「演示模式：反馈不会改变生成内容」 on first setup start.

- [ ] **Step 3: tests** — render Setup with mocked query data: step 0 visible with premise textarea; `has_concept: true` → step 0 marked finish, start-setup button calls fetch with `/setup`; demo notice appears when `live: false`.

- [ ] **Step 4: gates + commit** — `npm run typecheck && npm run test`; `uv run pytest -q` unchanged.
```bash
git add ui-v2
git commit -m "feat(ui-v2): Setup page — premise Step 0, stage stepper, structured artifacts"
```

---

### Task 7: Generate page

**Files:** `ui-v2/src/pages/Generate.tsx`; tests appended to `tests/pages.test.tsx`.

- [ ] **Step 1: page**
  - InputNumber `n` (1-50) + 「开始生成」→ `useWriteChapters`; on 409 show message WITH a 「查看运行中任务」action that navigates to this page and highlights JobStrip (R6 CTA — implement via message JSX button).
  - Resume affordance (Alex, R5-adjacent): show `status.chapters` → text 「已有 N 章；本次将生成 n 章，从第 N+1 章开始」(derived client-side; the backend resume makes this literal).
  - Progress: `Progress` bar bound to store `progress` (set `total = n` on start, increment on `chapter_done`), stage text from store `lastStage` + STAGE_NAMES.
  - Event log: `List`/virtual-free capped rendering from `store.lines`, `hover 暂停滚动` (auto-scroll only when not hovered), latest 500 (already capped in store).
  - Chapter list of results: chips from `status.chapters` with titles via `useOutline` (number + title), click → reader.
  - Cancel button (also in JobStrip; here a primary affordance) → `useCancelJob`.
  - job_end handling: success → `message.success("任务完成")` + invalidate status/reviews; error/cancelled → corresponding message with `error` string.

- [ ] **Step 2: tests** — mock store+SSE-free render: shows 「已有 3 章」 when status mock has 3 chapters; start button posts `{n}`; progress bar updates when store receives `chapter_done` events (drive store directly).

- [ ] **Step 3: gates + commit**
```bash
git add ui-v2
git commit -m "feat(ui-v2): Generate page — resume-aware start, progress, paused log, cancel"
```

---

### Task 8: Reader / Reviews / Threads / Export pages

**Files:** `ui-v2/src/pages/{Reader,Reviews,Threads,Export}.tsx`, `src/components/Trend.tsx`; tests appended.

- [ ] **Step 1: Reader** — left `Menu`/List of chapters from `useOutline` + `status.chapters` (`001 · 章标题`), right `Typography` prose with comfortable measure (`maxWidth: 72ch`, `lineHeight: 1.8`, `whiteSpace: pre-wrap`); fetch content on select via `useChapter`; empty state 「尚无章节，去生成」linking to generate.
- [ ] **Step 2: Reviews + Trend** — group `useReviews` by chapter (newest last), `Collapse` per chapter with `Table` of attempts (attempt/overall/passed/summary + dimension scores in expanded rows); page top renders `Trend` — inline SVG polyline of last-attempt overall per chapter (pure function `trendPoints(records) -> {x,y}[]`, no chart dep):
```tsx
export function Trend({ points }: { points: { x: number; y: number }[] }) {
  if (points.length < 2) return null;
  const w = 320, h = 80, pad = 8;
  const maxY = 100, minY = 0;
  const xs = (i: number) => pad + (i * (w - 2 * pad)) / (points.length - 1);
  const ys = (y: number) => pad + (1 - (y - minY) / (maxY - minY)) * (h - 2 * pad);
  return (
    <svg data-testid="score-trend" width={w} height={h} role="img" aria-label="各章总分趋势">
      <polyline fill="none" stroke="#1677ff" strokeWidth="2"
        points={points.map((p, i) => `${xs(i)},${ys(p.y)}`).join(" ")} />
      {points.map((p, i) => <circle key={i} cx={xs(i)} cy={ys(p.y)} r="3" />)}
    </svg>
  );
}
```
  Scores shown as text+color (R6: not color-only — always `92 ✅` style with words).
- [ ] **Step 3: Threads** — `Table` columns id/description/status with `Tag` color by status + text; empty state teaching copy.
- [ ] **Step 4: Export** — 「导出 Markdown」button → `useExport`; result shows path + 「复制路径」(antd Typography copyable); note text 「导出文件位于项目目录」.
- [ ] **Step 5: tests** — Reader renders chapter titles from mocked outline; Reviews groups by chapter and Trend renders svg when ≥2 chapters; Threads/Export happy-path renders. All with `vi.stubGlobal("fetch")` mocks.
- [ ] **Step 6: gates + commit**
```bash
git add ui-v2
git commit -m "feat(ui-v2): Reader/Reviews+Trend/Threads/Export pages"
```

---

### Task 9: Overview + Projects pages, polish (empty states, a11y leftovers)

**Files:** `src/pages/{Projects,Overview}.tsx`; adjustments elsewhere.

- [ ] **Step 1: Projects** — `List` of project cards (name + enter button → `/p/:name/overview`) + 「新建项目」modal (`Form`: name, genre) via `useCreateProject`; validation: name required ≤64; 409 conflict surfaced.
- [ ] **Step 2: Overview** — `Card` grid: 设定状态 (three booleans as Steps-mini or Tags with 中文说明文案), 章节数 + 最近章节链接, 未闭合伏笔 (link to threads), 运行中任务 (from `status.job`). When `!has_concept`: hero CTA card 「从一句创意开始 →」 linking to Setup (R1). Empty-chapters state: 「还没有章节——完成设定后开始生成」+ links.
- [ ] **Step 3: cross-page polish** — connection-lost banner already in JobStrip (verify); ensure every page has an empty state; add `aria-label`s to icon-only controls (Sider collapse trigger, copy button); ensure keyboard reachability of chapter menu (AntD Menu default).
- [ ] **Step 4: tests** — Projects create-form validation + submit; Overview CTA when `has_concept:false`, stats when true.
- [ ] **Step 5: gates + commit**
```bash
git add ui-v2
git commit -m "feat(ui-v2): Projects/Overview pages, empty states, a11y polish"
```

---

### Task 10: Production serving, docs, acceptance

**Files:** Modify `novel/ui/app.py` (+`novel/ui/__init__.py` if needed), `AGENTS.md`, `README.md`.

- [ ] **Step 1: static mounting** in `create_app` — replace the single `app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")` with:
```python
    dist_dir = Path(__file__).resolve().parent.parent.parent / "ui-v2" / "dist"
    app.mount("/legacy", StaticFiles(directory=STATIC_DIR, html=True), name="legacy")
    if dist_dir.is_dir():
        app.mount("/", StaticFiles(directory=dist_dir, html=True), name="ui-v2")
    else:
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static-fallback")
```
  (SPA deep links: StaticFiles(html=True) returns 404 for `/p/x/overview` — add a catch-all GET route `/{full_path:path}` serving `dist/index.html` when the mount misses; register BEFORE the mounts or use a 404 handler. Simplest: `@app.get("/legacy-check", include_in_schema=False)` no — implement via exception handler for HTTPException 404 falling back to `FileResponse(dist/index.html)` when `dist_dir` exists and path doesn't start with `/api` or `/legacy`.)
- [ ] **Step 2: pytest** — append to `tests/test_ui.py`: `test_ui_v2_dist_served` (build ui-v2 first: `cd ui-v2 && npm run build`; then `TestClient(create_app(tmp))` with a fake `ui-v2/dist/index.html` written into the repo path — monkeypatch `dist_dir` constant if simpler — assert GET `/` returns the SPA html, GET `/legacy/` returns old page, GET `/api/mode` still JSON). Mark with `@pytest.mark.skipif(not (repo/"ui-v2"/"dist").exists(), ...)` so CI without node stays green.
- [ ] **Step 3: AGENTS.md** — rewrite the `novel/ui/` bullet: add `ui-v2/` structure, two-process dev (`uv run novel-ui` + `cd ui-v2 && npm run dev`), `npm run build` before shipping, `/legacy` transition note; remove "no build step" phrasing; add npm gates to Commands.
- [ ] **Step 4: README** — GUI section: add 开发模式 two-process instructions + build/发布说明 + note legacy at `/legacy` until parity.
- [ ] **Step 5: full gates** — `cd ui-v2 && npm run build && npm run test && npm run typecheck`; `uv run pytest -q && uv run ruff check . && uv run mypy novel`.
- [ ] **Step 6: manual acceptance run (report results, not committed)** — `uv run novel-ui` + demo mode, walk the spec's 对等验收清单 end-to-end in the browser at the built SPA: 新建项目 → premise(Step 0) → setup（含一次反馈重生成 + 强行放行确认）→ 生成 3 章（JobStrip 跨页可见、断开后端再重连对账、取消）→ 阅读（带标题）→ 评分（趋势图）→ 伏笔 → 导出。Record pass/fail per item in the task report; failures become fix tasks.
- [ ] **Step 7: Commit**

```bash
git add novel/ui/app.py tests/test_ui.py AGENTS.md README.md
git commit -m "feat(ui-v2): serve SPA at / with /legacy fallback; docs; acceptance wiring"
```

---

## Self-Review

**1. Spec coverage:** R1 (T6 Step 0 + T9 CTA), R2 JobStrip (T4), R3 reconcile (T2 events.ts + verified in T10 manual), R4 GateModal variants/history/confirm (T5), R5 Sider groups (T4) + structured artifacts (T6) + outline endpoint & reader titles (T3/T8) + trend (T8) + copy constants (T2), R6 a11y/focus/live-region/log cap/pause (T2/T4/T5/T7) + empty states/demo notice/409 CTA (T6/T7/T9), 8 pages (T4 stubs → T6-T9 full), scaffold (T1), dev/prod serving + legacy + docs (T10), acceptance checklist (T10 Step 6). ✅

**2. Placeholder scan:** T2 Step 5 (hooks) and T8 Step 3 (Threads table) describe intent with patterns rather than full code — they follow the single TanStack/AntD idiom established verbatim elsewhere in this plan; an executor with the file open writes them mechanically. All other steps carry complete code. Acceptable, flagged. ✅

**3. Type consistency:** `SseEvent`, `ProjectStatus`, `JobInfo`, `ReviewRecord`, `Thread`, `OutlineInfo` used consistently; store fields (`gate/job/progress/lines/connected/lastStage/feedbackHistory`) match consumers in T4/T5/T6/T7; `useResolveGate({id, approve, feedback})` matches `POST /api/gates/{id}` body; JobStrip/`GateModal` take `{project: string}`. ✅
