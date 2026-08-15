import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, expect, test, vi } from "vitest";
import { App as AntApp } from "antd";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import Setup from "../src/pages/Setup";
import Generate from "../src/pages/Generate";
import { ArtifactView } from "../src/components/ArtifactView";
import { useEvents } from "../src/stores/events";
import type { ProjectStatus } from "../src/api/types";

// ---------- helpers ----------

const baseStatus: ProjectStatus = {
  name: "x",
  has_concept: false,
  has_world: false,
  has_outline: false,
  chapters: [],
  open_threads: 0,
  score_min: 0,
  job: null,
};

/** Stub fetch for the project page endpoints; `over.status` merges into /status. */
function stubFetchFor(over: {
  status?: Partial<ProjectStatus>;
  live?: boolean;
  postStatus?: number;
  postDetail?: string;
  outline?: object | null;
  projects?: { name: string }[];
  reviews?: object[];
  threads?: object[];
  chapterContent?: (n: number) => string;
  exportPath?: string;
} = {}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/mode")
      return new Response(JSON.stringify({ live: over.live ?? false }), { status: 200 });
    if (url === "/api/projects" && init?.method !== "POST")
      return new Response(JSON.stringify(over.projects ?? []), { status: 200 });
    if (url === "/api/projects/x/status")
      return new Response(JSON.stringify({ ...baseStatus, ...over.status }), { status: 200 });
    if (url === "/api/projects/x/outline")
      return new Response(JSON.stringify(over.outline ?? { arcs: [] }), { status: 200 });
    if (url === "/api/projects/x/reviews")
      return new Response(JSON.stringify(over.reviews ?? []), { status: 200 });
    if (url === "/api/projects/x/threads")
      return new Response(JSON.stringify(over.threads ?? []), { status: 200 });
    const chMatch = url.match(/^\/api\/projects\/x\/chapters\/(\d+)$/);
    if (chMatch) {
      const n = Number(chMatch[1]);
      return new Response(
        JSON.stringify({
          chapter: n,
          content: over.chapterContent ? over.chapterContent(n) : `第 ${n} 章的演示正文。`,
        }),
        { status: 200 },
      );
    }
    if (init?.method === "POST" && url.endsWith("/export"))
      return new Response(
        JSON.stringify({ path: over.exportPath ?? "/tmp/novels/x/export/x.md" }),
        { status: 200 },
      );
    if (init?.method === "POST") {
      if (over.postStatus && over.postStatus >= 400)
        return new Response(
          JSON.stringify({ detail: over.postDetail ?? "已有任务在运行" }),
          { status: over.postStatus },
        );
      return new Response(JSON.stringify({ job_id: "j9" }), { status: 202 });
    }
    return new Response("{}", { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderPage(el: ReactElement, routePath = "/p/:name/setup", initialEntry?: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AntApp>
        <MemoryRouter initialEntries={[initialEntry ?? routePath.replace(":name", "x")]}>
          <Routes>
            <Route path={routePath} element={el} />
          </Routes>
        </MemoryRouter>
      </AntApp>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  useEvents.getState().reset();
});

// ---------- Setup page ----------

test("Setup: step 0 premise input, demo notice and guiding copy", async () => {
  stubFetchFor();
  renderPage(<Setup />);

  expect(await screen.findByTestId("premise-input")).toBeInTheDocument();
  await waitFor(() =>
    expect(screen.getByText("演示模式：反馈不会改变生成内容")).toBeInTheDocument(),
  );
  expect(screen.getByText("从一句创意开始，逐步确认概念、世界观、人物与大纲")).toBeInTheDocument();
  expect(screen.queryByTestId("start-setup")).toBeDisabled();
});

test("Setup: has_concept → steps 0-1 finished, start-setup posts {premise:\"\"}", async () => {
  const fetchMock = stubFetchFor({ status: { has_concept: true } });
  renderPage(<Setup />);

  await waitFor(() =>
    expect(document.querySelectorAll(".ant-steps-item-finish").length).toBe(2),
  );
  expect(screen.queryByTestId("premise-input")).not.toBeInTheDocument();
  fireEvent.click(screen.getByTestId("start-setup"));
  await waitFor(() => {
    const call = fetchMock.mock.calls.find((c) => String(c[0]).endsWith("/setup"));
    expect(call).toBeTruthy();
    expect((call![1] as RequestInit).method).toBe("POST");
    expect(JSON.parse(String((call![1] as RequestInit).body))).toEqual({ premise: "" });
  });
});

test("Setup: latest setup_stage artifact renders via ArtifactView", async () => {
  stubFetchFor();
  renderPage(<Setup />);
  act(() => {
    useEvents.getState().apply({
      type: "setup_stage",
      stage: "world",
      attempt: 1,
      artifact: JSON.stringify({ setting: "city of bells" }),
      job_id: "j1",
    });
  });
  expect(screen.getByText(/最新产物 · 世界观/)).toBeInTheDocument();
  expect(screen.getByText("city of bells")).toBeInTheDocument();
});

// ---------- ArtifactView (real demo artifact shapes from novel/runtime.py) ----------

const CONCEPT = JSON.stringify(
  {
    logline: "A thief steals time.",
    genre: "fantasy",
    tone: "grim",
    themes: ["loss"],
    target_length_words: 9000,
    audience: "adult",
  },
  null,
  2,
);
const WORLD = JSON.stringify(
  {
    setting: "city of bells",
    era: "",
    rules: [],
    power_system: "",
    factions: [],
    locations: [],
    constraints: [],
  },
  null,
  2,
);
const CHARACTERS = JSON.stringify(
  [
    {
      id: "c1",
      slug: "ara",
      name: "Ara",
      role: "protagonist",
      backstory: "orphan",
      motivation: "revenge",
      arc: "a",
      voice_fingerprint: {},
      mannerisms: [],
      description_history: [],
      relationships: {},
      state: {
        emotional_state: "",
        physical_state: "",
        knowledge_gained: [],
        relationships_shifted: {},
        location_end: "",
      },
    },
  ],
  null,
  2,
);
const OUTLINE = JSON.stringify(
  {
    arcs: [
      {
        arc_name: "A",
        chapters: [
          {
            chapter_no: 1,
            chapter_title: "T1",
            beats: [
              {
                beat_id: "",
                pov: "Ara",
                setting: "tavern",
                event: "meet informant",
                emotional_turn: "doubt",
                characters: ["c1"],
                plants: [],
                payoffs: [],
              },
            ],
          },
          { chapter_no: 2, chapter_title: "T2", beats: [] },
          { chapter_no: 3, chapter_title: "T3", beats: [] },
        ],
      },
    ],
    foreshadow_ledger: [],
  },
  null,
  2,
);

test("ArtifactView: demo concept with labeled fields and theme tags", () => {
  render(<ArtifactView raw={CONCEPT} title="最新产物 · 故事概念" />);
  expect(screen.getByText("一句话概念")).toBeInTheDocument();
  expect(screen.getByText("A thief steals time.")).toBeInTheDocument();
  expect(screen.getByText("目标字数")).toBeInTheDocument();
  expect(screen.getByText("9000")).toBeInTheDocument();
  expect(screen.getByText("loss")).toBeInTheDocument();
});

test("ArtifactView: demo world shows setting, filters empty default fields", () => {
  render(<ArtifactView raw={WORLD} />);
  expect(screen.getByText("舞台设定")).toBeInTheDocument();
  expect(screen.getByText("city of bells")).toBeInTheDocument();
  expect(screen.queryByText("时代")).not.toBeInTheDocument();
  expect(screen.queryByText("世界规则")).not.toBeInTheDocument();
});

test("ArtifactView: demo character list — one block per character, noise fields hidden", () => {
  render(<ArtifactView raw={CHARACTERS} />);
  expect(screen.getByText("人物：Ara")).toBeInTheDocument();
  expect(screen.getByText("orphan")).toBeInTheDocument();
  expect(screen.getByText("revenge")).toBeInTheDocument();
  // hidden: state / voice_fingerprint / mannerisms / beats
  expect(screen.queryByText(/emotional_state/)).not.toBeInTheDocument();
  expect(screen.queryByText(/voice_fingerprint/)).not.toBeInTheDocument();
});

test("ArtifactView: demo outline — arc heading + chapter rows", () => {
  render(<ArtifactView raw={OUTLINE} />);
  expect(screen.getByText("A", { selector: "h5" })).toBeInTheDocument();
  expect(screen.getByText("章号")).toBeInTheDocument();
  expect(screen.getByText("章标题")).toBeInTheDocument();
  for (const t of ["T1", "T2", "T3"]) expect(screen.getByText(t)).toBeInTheDocument();
  // hidden beats
  expect(screen.queryByText(/meet informant/)).not.toBeInTheDocument();
});

test("ArtifactView: non-JSON text falls back to <pre>; empty shows Empty", () => {
  const { rerender } = render(<ArtifactView raw="plain prose artifact" />);
  expect(screen.getByText("plain prose artifact")).toBeInTheDocument();
  rerender(<ArtifactView raw="   " />);
  expect(document.querySelector(".ant-empty")).toBeInTheDocument();
});

// ---------- Generate page ----------

const OUTLINE_RESP = {
  arcs: [
    {
      arc_name: "A",
      chapters: [
        { chapter_no: 1, chapter_title: "T1" },
        { chapter_no: 2, chapter_title: "T2" },
        { chapter_no: 3, chapter_title: "T3" },
      ],
    },
  ],
};

function renderGenerate() {
  return renderPage(<Generate />, "/p/:name/generate");
}

test("Generate: resume text from existing chapters; titled chips navigate to reader", async () => {
  stubFetchFor({ status: { has_outline: true, chapters: [1, 2, 3] }, outline: OUTLINE_RESP });
  renderGenerate();

  expect(await screen.findByText(/已有 3 章/)).toBeInTheDocument();
  expect(screen.getByText(/本次将生成 1 章/)).toBeInTheDocument();
  expect(await screen.findByTestId("chapter-chip-1")).toHaveTextContent("001 · T1");
  expect(screen.getByTestId("chapter-chip-3")).toHaveTextContent("003 · T3");
});

test("Generate: start posts {n}; progress counts chapter_done AND chapter_skipped (N4)", async () => {
  const fetchMock = stubFetchFor({
    status: { has_outline: true, chapters: [1, 2, 3] },
    outline: OUTLINE_RESP,
  });
  renderGenerate();

  fireEvent.change(await screen.findByRole("spinbutton"), { target: { value: "3" } });
  fireEvent.click(screen.getByTestId("start-generate"));
  await waitFor(() => {
    const call = fetchMock.mock.calls.find((c) => String(c[0]).endsWith("/write-chapter"));
    expect(call).toBeTruthy();
    expect((call![1] as RequestInit).method).toBe("POST");
    expect(JSON.parse(String((call![1] as RequestInit).body))).toEqual({ n: 3 });
  });
  // drive the store as the SSE hook would
  act(() => {
    const st = useEvents.getState();
    st.apply({ type: "stage", stage: "writer", chapter: 4, job_id: "j9" });
    st.apply({ type: "chapter_done", chapter: 4, job_id: "j9" });
    st.apply({ type: "chapter_skipped", chapter: 5, reason: "already exists", job_id: "j9" });
  });
  expect(useEvents.getState().progress).toEqual({ done: 2, total: 3 });
  await waitFor(() => expect(screen.getByText("2/3")).toBeInTheDocument());
  expect(screen.getByText(/当前阶段：正文写作中/)).toBeInTheDocument();
});

test("Generate: 409 shows an error message with 查看运行中任务 CTA", async () => {
  stubFetchFor({ postStatus: 409, postDetail: "任务已在运行" });
  renderGenerate();

  fireEvent.click(await screen.findByTestId("start-generate"));
  await waitFor(() => expect(screen.getByText("任务已在运行")).toBeInTheDocument());
  expect(screen.getByText("查看运行中任务")).toBeInTheDocument();
});

test("Generate: log lines render; job_end toasts and invalidates", async () => {
  stubFetchFor({ status: { has_outline: true, chapters: [1] }, outline: OUTLINE_RESP });
  renderGenerate();

  act(() => {
    useEvents.getState().pushLine("✔ 第 4 章完成并已保存");
  });
  expect(await screen.findByText(/第 4 章完成并已保存/)).toBeInTheDocument();

  act(() => {
    useEvents.getState().apply({ type: "job_end", status: "done", job_id: "j9" });
  });
  await waitFor(() => expect(screen.getByText("任务完成")).toBeInTheDocument());
  expect(useEvents.getState().progress).toBeNull();
});

// ---------- Reader page (T8 + F1) ----------

import Reader from "../src/pages/Reader";
import { useSearchParams } from "react-router-dom";

function SearchProbe() {
  const [sp] = useSearchParams();
  return <div data-testid="search-probe">{sp.toString()}</div>;
}

test("Reader: titled chapter list from outline; untitled fallback", async () => {
  stubFetchFor({
    status: { has_outline: true, chapters: [1, 2] },
    outline: { arcs: [{ arc_name: "A", chapters: [{ chapter_no: 2, chapter_title: "钟之城" }] }] },
  });
  renderPage(<Reader />, "/p/:name/reader");

  expect(await screen.findByText("001 · （无标题）")).toBeInTheDocument();
  expect(screen.getByText("002 · 钟之城")).toBeInTheDocument();
  // first chapter auto-selected → prose fetched
  expect(await screen.findByTestId("reader-prose")).toHaveTextContent("第 1 章的演示正文。");
});

test("Reader: ?chapter=2 deep link preselects chapter 2 and clears the param (F1)", async () => {
  const fetchMock = stubFetchFor({
    status: { has_outline: true, chapters: [1, 2, 3] },
    outline: OUTLINE_RESP,
  });
  renderPage(
    <>
      <Reader />
      <SearchProbe />
    </>,
    "/p/:name/reader",
    "/p/x/reader?chapter=2",
  );

  expect(await screen.findByTestId("reader-prose")).toHaveTextContent("第 2 章的演示正文。");
  expect(fetchMock.mock.calls.some((c) => String(c[0]) === "/api/projects/x/chapters/2")).toBe(true);
  // menu item 2 selected; param cleared so back-button stays sane
  await waitFor(() => {
    const item = screen.getByText("002 · T2").closest(".ant-menu-item");
    expect(item?.className).toContain("ant-menu-item-selected");
  });
  await waitFor(() => expect(screen.getByTestId("search-probe")).toHaveTextContent(""));
});

test("Reader: empty state links to the generate page", async () => {
  stubFetchFor();
  renderPage(<Reader />, "/p/:name/reader");

  expect(await screen.findByText("尚无章节")).toBeInTheDocument();
  expect(screen.getByText("去生成")).toHaveAttribute("href", "/p/x/generate");
});

// ---------- Reviews page + Trend (T8) ----------

import Reviews from "../src/pages/Reviews";
import { Trend, trendPoints } from "../src/components/Trend";
import type { ReviewRecord } from "../src/api/types";

const REVIEWS: ReviewRecord[] = [
  {
    chapter: 1,
    attempt: 1,
    artifact_type: "chapter",
    overall: 60,
    summary: "首次未达标",
    passed: false,
    timestamp: "2026-08-15T10:00:00",
    scores: { pacing: { score: 55, critique: "节奏偏快" }, prose: { score: 65, critique: "" } },
  },
  {
    chapter: 1,
    attempt: 2,
    artifact_type: "chapter",
    overall: 85,
    summary: "重写后达标",
    passed: true,
    timestamp: "2026-08-15T10:05:00",
    scores: { pacing: { score: 84, critique: "" }, prose: { score: 86, critique: "" } },
  },
  {
    chapter: 2,
    attempt: 1,
    artifact_type: "chapter",
    overall: 90,
    summary: "一次通过",
    passed: true,
    timestamp: "2026-08-15T11:00:00",
    scores: { pacing: { score: 91, critique: "" } },
  },
];

test("Reviews: groups by chapter, final badge + attempts with text scores (not color-only)", async () => {
  stubFetchFor({ reviews: REVIEWS });
  renderPage(<Reviews />, "/p/:name/reviews");

  // chapter headers with summary badges
  expect(await screen.findByText("第 1 章")).toBeInTheDocument();
  expect(screen.getByText("最终 85 分 ✅")).toBeInTheDocument();
  expect(screen.getByText("2 次评分")).toBeInTheDocument();
  expect(screen.getByText("最终 90 分 ✅")).toBeInTheDocument();
  // attempts in order, pass/fail as words + icon
  const a1 = await screen.findByTestId("review-attempt-1-1");
  expect(a1).toHaveTextContent("未通过 ❌");
  expect(a1).toHaveTextContent("总分 60 分");
  expect(await screen.findByTestId("review-attempt-1-2")).toHaveTextContent("通过 ✅");
  // dimension scores as text
  expect(screen.getByText("pacing：55 分")).toBeInTheDocument();
  expect(screen.getByText("prose：86 分")).toBeInTheDocument();
});

test("Reviews: trend svg renders for ≥2 chapters with role=img + aria-label", async () => {
  stubFetchFor({ reviews: REVIEWS });
  renderPage(<Reviews />, "/p/:name/reviews");

  const svg = await screen.findByTestId("score-trend");
  expect(svg).toHaveAttribute("role", "img");
  expect(svg).toHaveAttribute("aria-label", "各章总分趋势");
  expect(svg.querySelector("polyline")).toBeInTheDocument();
});

test("Reviews: empty state when no records; Trend needs ≥2 points; last attempt wins", async () => {
  stubFetchFor({ reviews: [] });
  renderPage(<Reviews />, "/p/:name/reviews");
  expect(await screen.findByText("暂无评分记录，生成章节后自动留档")).toBeInTheDocument();

  // unit-level: trendPoints picks the LAST attempt per chapter, ascending order
  expect(trendPoints(REVIEWS)).toEqual([
    { x: 1, y: 85 },
    { x: 2, y: 90 },
  ]);
  // <2 points → renders nothing
  const { container } = render(<Trend points={[{ x: 1, y: 80 }]} />);
  expect(container.querySelector("svg")).toBeNull();
});

// ---------- Threads page (T8) ----------

import Threads from "../src/pages/Threads";

test("Threads: table with status tags (color + text) and teaching empty state", async () => {
  stubFetchFor({
    threads: [
      { id: "fs-1", description: "钟楼的第七口钟", status: "planted" },
      { id: "fs-2", description: "偷走的时间去了哪里", status: "open" },
      { id: "fs-3", description: "告密者的身份", status: "paid_off" },
    ],
  });
  renderPage(<Threads />, "/p/:name/threads");

  expect(await screen.findByText("钟楼的第七口钟")).toBeInTheDocument();
  expect(screen.getByText("已埋设（planted）")).toBeInTheDocument();
  expect(screen.getByText("待埋设（open）")).toBeInTheDocument();
  expect(screen.getByText("已回收（paid_off）")).toBeInTheDocument();

  stubFetchFor({ threads: [] });
  renderPage(<Threads />, "/p/:name/threads");
  expect(await screen.findByText(/暂无伏笔记录/)).toBeInTheDocument();
});

// ---------- Export page (T8) ----------

import Export from "../src/pages/Export";

test("Export: button POSTs, path shown copyable with note", async () => {
  const fetchMock = stubFetchFor({ exportPath: "/tmp/novels/x/export/x.md" });
  renderPage(<Export />, "/p/:name/export");

  expect(screen.getByText("导出文件位于项目目录")).toBeInTheDocument();
  fireEvent.click(screen.getByTestId("export-button"));
  expect(await screen.findByTestId("export-path")).toHaveTextContent("/tmp/novels/x/export/x.md");
  expect(screen.getByText("导出完成")).toBeInTheDocument();
  const call = fetchMock.mock.calls.find((c) => String(c[0]).endsWith("/export"));
  expect(call).toBeTruthy();
  expect((call![1] as RequestInit).method).toBe("POST");
});

// ---------- Projects page (T9) ----------

import Projects from "../src/pages/Projects";

test("Projects: cards with enter button; empty name blocked by validation", async () => {
  const fetchMock = stubFetchFor({ projects: [{ name: "alpha" }] });
  renderPage(<Projects />, "/");

  expect(await screen.findByText("alpha")).toBeInTheDocument();
  fireEvent.click(screen.getByText("新建项目"));
  fireEvent.click(await screen.findByTestId("create-submit"));
  await waitFor(() => expect(screen.getByText("请输入项目名")).toBeInTheDocument());
  expect(
    fetchMock.mock.calls.find(
      (c) => String(c[0]) === "/api/projects" && (c[1] as RequestInit).method === "POST",
    ),
  ).toBeUndefined();
});

test("Projects: create submits {name, genre} payload; 409 conflict surfaced", async () => {
  const fetchMock = stubFetchFor({ projects: [] });
  renderPage(<Projects />, "/");

  fireEvent.click(screen.getByText("新建项目"));
  fireEvent.change(await screen.findByTestId("project-name-input"), {
    target: { value: "beta" },
  });
  fireEvent.click(screen.getByTestId("create-submit"));
  await waitFor(() => {
    const call = fetchMock.mock.calls.find(
      (c) => String(c[0]) === "/api/projects" && (c[1] as RequestInit).method === "POST",
    );
    expect(call).toBeTruthy();
    expect(JSON.parse(String((call![1] as RequestInit).body))).toEqual({
      name: "beta",
      genre: "fantasy",
    });
  });
  await waitFor(() => expect(screen.getByText("项目 beta 已创建")).toBeInTheDocument());
});

test("Projects: 409 conflict surfaces as an error message", async () => {
  stubFetchFor({ postStatus: 409, postDetail: "项目已存在" });
  renderPage(<Projects />, "/");

  fireEvent.click(screen.getByText("新建项目"));
  fireEvent.change(await screen.findByTestId("project-name-input"), {
    target: { value: "beta" },
  });
  fireEvent.click(screen.getByTestId("create-submit"));
  await waitFor(() =>
    expect(screen.getByText(/创建失败（冲突）：项目已存在/)).toBeInTheDocument(),
  );
});

// ---------- Overview page (T9) ----------

import Overview from "../src/pages/Overview";

test("Overview: !has_concept → hero CTA to setup; empty-chapters state links", async () => {
  stubFetchFor({ status: { has_concept: false, chapters: [], open_threads: 0 } });
  renderPage(<Overview />, "/p/:name/overview");

  const cta = await screen.findByTestId("overview-cta");
  expect(cta).toBeInTheDocument();
  expect(screen.getByTestId("overview-cta-button")).toHaveTextContent("从一句创意开始 →");
  expect(screen.getByTestId("overview-cta-button").closest("a")).toHaveAttribute(
    "href",
    "/p/x/setup",
  );
  expect(await screen.findByText(/还没有章节/)).toBeInTheDocument();
  expect(screen.getByText("概念未生成")).toBeInTheDocument();
});

test("Overview: stats state when concept exists — tags, latest chapter link, threads, job", async () => {
  stubFetchFor({
    status: {
      has_concept: true,
      has_world: true,
      has_outline: true,
      chapters: [1, 3],
      open_threads: 2,
      job: { id: "j5", kind: "write-chapter", status: "running", error: null },
    },
  });
  renderPage(<Overview />, "/p/:name/overview");

  expect(await screen.findByTestId("overview-stats")).toBeInTheDocument();
  expect(screen.queryByTestId("overview-cta")).not.toBeInTheDocument();
  expect(screen.getByText("✓ 概念已生成")).toBeInTheDocument();
  expect(screen.getByText("✓ 世界观已构建")).toBeInTheDocument();
  expect(screen.getByText("✓ 大纲已编排")).toBeInTheDocument();
  expect(screen.getByText("共 2 章")).toBeInTheDocument();
  expect(screen.getByText("最新章节：第 3 章")).toHaveAttribute("href", "/p/x/reader?chapter=3");
  expect(screen.getByText("2 条未闭合")).toBeInTheDocument();
  expect(screen.getByText("章节生成")).toBeInTheDocument(); // job kind 中文文案
});

// ---------- F2: Generate 409 CTA pulses the JobStrip; F3 demo notice ----------

import JobStrip from "../src/components/JobStrip";

test("Generate: 409 CTA pulses JobStrip instead of no-op navigate (F2); demo notice (F3)", async () => {
  stubFetchFor({ postStatus: 409, postDetail: "任务已在运行" });
  act(() => {
    useEvents.setState({ job: { id: "j1", kind: "setup" } });
  });
  renderPage(
    <>
      <JobStrip project="x" />
      <Generate />
    </>,
    "/p/:name/generate",
  );

  // F3: persistent demo-mode alert, same copy as Setup
  expect(await screen.findByTestId("demo-notice")).toBeInTheDocument();
  expect(screen.getByText("演示模式：反馈不会改变生成内容")).toBeInTheDocument();

  expect(screen.getByTestId("job-strip")).toBeInTheDocument();
  expect(document.querySelector(".job-strip-pulse")).toBeNull();
  fireEvent.click(await screen.findByTestId("start-generate"));
  await waitFor(() => expect(screen.getByText("任务已在运行")).toBeInTheDocument());
  fireEvent.click(screen.getByText("查看运行中任务"));
  expect(useEvents.getState().stripPulse).toBe(1);
  await waitFor(() => expect(document.querySelector(".job-strip-pulse")).not.toBeNull());
});
