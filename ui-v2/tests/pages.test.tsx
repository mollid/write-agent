import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, expect, test, vi } from "vitest";
import { App as AntApp } from "antd";
import { MemoryRouter, Route, Routes, useSearchParams } from "react-router-dom";
import Setup from "../src/pages/Setup";
import Generate from "../src/pages/Generate";
import Reader from "../src/pages/Reader";
import Relationships from "../src/pages/Relationships";
import Reviews from "../src/pages/Reviews";
import Threads from "../src/pages/Threads";
import Export from "../src/pages/Export";
import Projects from "../src/pages/Projects";
import Overview from "../src/pages/Overview";
import Bible from "../src/pages/Bible";
import JobStrip from "../src/components/JobStrip";
import { ArtifactView } from "../src/components/ArtifactView";
import { Trend, trendPoints } from "../src/components/Trend";
import { useEvents } from "../src/stores/events";
import { buildGraph } from "../src/components/RelationGraph";
import type {
  BibleData,
  CharacterData,
  ConceptData,
  OutlineFullData,
  ProjectStatus,
  ReviewRecord,
  WorldData,
} from "../src/api/types";

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

const BIBLE_EMPTY: BibleData = {
  concept: null,
  world: null,
  characters: [],
  outline: null,
  foreshadows: [],
  events: [],
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
  bible?: Partial<BibleData>;
  putBibleStatus?: number;
  putBibleDetail?: string;
  audio?: { chapter: number; size: number }[];
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
    if (url === "/api/projects/x/bible")
      return new Response(JSON.stringify({ ...BIBLE_EMPTY, ...over.bible }), { status: 200 });
    const bibleSec = url.match(/^\/api\/projects\/x\/bible\/([a-z]+)$/);
    if (bibleSec && init?.method === "PUT") {
      if (over.putBibleStatus && over.putBibleStatus >= 400)
        return new Response(
          JSON.stringify({ detail: over.putBibleDetail ?? "validation error" }),
          { status: over.putBibleStatus },
        );
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    }
    if (url === "/api/projects/x/audio")
      return new Response(JSON.stringify(over.audio ?? []), { status: 200 });
    if (/^\/api\/projects\/x\/audio\/\d+$/.test(url))
      return new Response(new Blob(["mp3"]), { status: 200,
        headers: { "content-type": "audio/mpeg" } });
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
    if (init?.method === "POST" && url === "/api/projects/x/bible/chat")
      return new Response(JSON.stringify({ job_id: "jc" }), { status: 202 });
    if (init?.method === "POST" && url === "/api/projects/x/outline/extend")
      return new Response(JSON.stringify({ job_id: "je" }), { status: 202 });
    if (init?.method === "POST" && url.startsWith("/api/gates/"))
      return new Response(JSON.stringify({ resolved: true }), { status: 200 });
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
  window.localStorage.clear();
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

test("Generate: whole-book progress shown when plannedTotal is present", async () => {
  stubFetchFor({ status: { has_outline: true, chapters: [1] }, outline: OUTLINE_RESP });
  renderGenerate();

  act(() => {
    const st = useEvents.getState();
    st.apply({ type: "stage", stage: "writer", chapter: 37, job_id: "j9" });
    st.apply({ type: "chapter_start", chapter: 37, title: "T", planned_total: 240, job_id: "j9" });
  });
  expect(await screen.findByTestId("book-progress")).toHaveTextContent("第 37 / 共 240 章");
});

test("Generate: whole-book progress hidden when plannedTotal is absent", async () => {
  stubFetchFor({ status: { has_outline: true, chapters: [1] }, outline: OUTLINE_RESP });
  renderGenerate();

  act(() => {
    const st = useEvents.getState();
    st.apply({ type: "stage", stage: "writer", chapter: 37, job_id: "j9" });
    st.apply({ type: "chapter_start", chapter: 37, title: "T", job_id: "j9" });
  });
  expect(await screen.findByTestId("page-generate")).toBeInTheDocument();
  expect(screen.queryByTestId("book-progress")).not.toBeInTheDocument();
});

test("Generate: a lastEnd from before the visit is not re-toasted; a new job_end still is", async () => {
  stubFetchFor({ status: { has_outline: true, chapters: [1] }, outline: OUTLINE_RESP });
  act(() => {
    useEvents.getState().apply({ type: "job_end", status: "done", job_id: "j0" });
  });
  renderGenerate();

  expect(await screen.findByTestId("page-generate")).toBeInTheDocument();
  expect(screen.queryByText("任务完成")).not.toBeInTheDocument();

  act(() => {
    useEvents.getState().apply({ type: "job_end", status: "cancelled", job_id: "j9" });
  });
  await waitFor(() => expect(screen.getByText("任务已取消")).toBeInTheDocument());
});

// ---------- Reader page (T8 + F1) ----------

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

test("Reader: rewrite card — mode + instruction POST /chapter-rewrite; later-chapter warning", async () => {
  const fetchMock = stubFetchFor({ status: { has_outline: true, chapters: [1, 2] } });
  renderPage(<Reader />, "/p/:name/reader");
  await screen.findByTestId("rewrite-card");

  // chapter 1 selected but chapter 2 exists → continuity warning
  expect(screen.getByText(/重写本章可能与后续内容衔接不畅/)).toBeInTheDocument();

  fireEvent.click(screen.getByTestId("rewrite-start"));
  // empty instruction is blocked client-side
  expect(
    fetchMock.mock.calls.some((c) => String(c[0]).endsWith("/chapter-rewrite")),
  ).toBe(false);

  fireEvent.change(screen.getByTestId("rewrite-instruction"), { target: { value: "结尾更克制" } });
  fireEvent.click(screen.getByTitle("创意重编排")); // Segmented option
  fireEvent.click(screen.getByTestId("rewrite-start"));
  await waitFor(() => {
    const call = fetchMock.mock.calls.find((c) => String(c[0]).endsWith("/chapter-rewrite"));
    expect(call).toBeDefined();
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({
      chapter: 1, mode: "rearrange", instruction: "结尾更克制",
    });
  });
  // pending indicator shows while the draft generates, clears when the
  // proposal for THIS chapter lands (regression: frozen-looking page)
  expect(await screen.findByTestId("rewrite-pending")).toBeInTheDocument();
  act(() => {
    useEvents.getState().apply({
      type: "chapter_proposal", chapter: 1, mode: "rearrange",
      diff: "d", draft: "全文", job_id: "j",
    });
  });
  await waitFor(() =>
    expect(screen.queryByTestId("rewrite-pending")).not.toBeInTheDocument());
  // a proposal for ANOTHER chapter must not clear our pending state
  act(() => {
    useEvents.getState().apply({ type: "job_end", status: "done", job_id: "j" });
  });
  fireEvent.click(screen.getByTestId("rewrite-start"));
  expect(await screen.findByTestId("rewrite-pending")).toBeInTheDocument();
  act(() => {
    useEvents.getState().apply({
      type: "chapter_proposal", chapter: 9, mode: "polish",
      diff: "d", draft: "全文", job_id: "j",
    });
  });
  expect(screen.getByTestId("rewrite-pending")).toBeInTheDocument();
  // job_end (error/cancel) also clears it
  act(() => {
    useEvents.getState().apply({ type: "job_end", status: "error", error: "x", job_id: "j" });
  });
  await waitFor(() =>
    expect(screen.queryByTestId("rewrite-pending")).not.toBeInTheDocument());
});

test("Reader: proposal panel shows diff; approve resolves the rewrite gate", async () => {
  const fetchMock = stubFetchFor({ status: { has_outline: true, chapters: [1] } });
  renderPage(<Reader />, "/p/:name/reader");
  await screen.findByTestId("rewrite-card");
  expect(screen.queryByTestId("rewrite-proposal")).not.toBeInTheDocument();

  act(() => {
    useEvents.getState().apply({
      type: "chapter_proposal", chapter: 1, mode: "polish",
      diff: "--- 当前章稿\n+++ 改写稿\n@@\n+新结尾", draft: "全文", job_id: "j",
    });
    useEvents.getState().apply({
      type: "gate", gate_id: "gr1", label: "rewrite:1", artifact: "全文", job_id: "j",
    });
  });

  expect(await screen.findByTestId("rewrite-proposal")).toBeInTheDocument();
  expect(screen.getByTestId("rewrite-diff")).toHaveTextContent("新结尾");
  expect(screen.getByText(/第 1 章改写提案 · 微调/)).toBeInTheDocument();

  fireEvent.click(screen.getByTestId("rewrite-approve"));
  await waitFor(() => {
    const call = fetchMock.mock.calls.find((c) =>
      String(c[0]) === "/api/gates/gr1" && c[1]?.method === "POST");
    expect(call).toBeDefined();
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ approve: true, feedback: "" });
  });
});

test("Reader: manual edit — prefilled textarea, cancel reverts, save PUTs content", async () => {
  const fetchMock = stubFetchFor({ status: { has_outline: true, chapters: [1] } });
  renderPage(<Reader />, "/p/:name/reader");
  await screen.findByTestId("reader-prose");

  fireEvent.click(screen.getByTestId("edit-chapter"));
  const area = screen.getByTestId("edit-area") as HTMLTextAreaElement;
  expect(area.value).toContain("第 1 章的演示正文。");

  // cancel returns to read mode with the prose intact
  fireEvent.click(screen.getByTestId("edit-cancel"));
  expect(screen.queryByTestId("edit-area")).not.toBeInTheDocument();
  expect(screen.getByTestId("reader-prose")).toBeInTheDocument();

  // edit again and save → PUT with the new content
  fireEvent.click(screen.getByTestId("edit-chapter"));
  fireEvent.change(screen.getByTestId("edit-area"), {
    target: { value: "手写修订后的正文，长度足够保存。" },
  });
  fireEvent.click(screen.getByTestId("edit-save"));
  await waitFor(() => {
    const call = fetchMock.mock.calls.find(
      (c) => String(c[0]) === "/api/projects/x/chapters/1" && c[1]?.method === "PUT",
    );
    expect(call).toBeDefined();
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({
      content: "手写修订后的正文，长度足够保存。",
    });
  });
});

// ---------- Reviews page + Trend (T8) ----------

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

test("Reviews: groups newest-first — latest chapter group on top, newest attempt first", async () => {
  stubFetchFor({ reviews: REVIEWS });
  renderPage(<Reviews />, "/p/:name/reviews");

  // groups ordered by latest review time: ch2 (11:00) before ch1 (10:05)
  const headers = await screen.findAllByText(/第 \d+ 章/);
  expect(headers[0]).toHaveTextContent("第 2 章");
  expect(headers[1]).toHaveTextContent("第 1 章");
  // within ch1, attempt 2 (10:05) renders before attempt 1 (10:00)
  const a2 = screen.getByTestId("review-attempt-1-2");
  expect(a2.nextElementSibling?.getAttribute("data-testid")).toBe("review-attempt-1-1");
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

// ---------- Relationships graph page ----------

const REL_CHARS: CharacterData[] = [
  {
    id: "c1", slug: "ara", name: "阿岚", role: "主角", backstory: "b",
    motivation: "夺回家传怀表", arc: "从逃避到承担", voice_fingerprint: {},
    mannerisms: [], description_history: [],
    relationships: { c2: "宿敌，夺走了家传怀表" },
    state: { emotional_state: "警觉", physical_state: "健康", knowledge_gained: [],
             relationships_shifted: { c3: "从猜忌转为同盟" }, location_end: "钟楼" },
  },
  {
    id: "c2", slug: "kai", name: "凯恩", role: "反派", backstory: "b",
    motivation: "垄断时间交易", arc: "堕落加深", voice_fingerprint: {},
    mannerisms: [], description_history: [], relationships: {},
    state: { emotional_state: "得意", physical_state: "健康", knowledge_gained: [],
             relationships_shifted: {}, location_end: "钟楼" },
  },
  {
    id: "c3", slug: "mira", name: "米拉", role: "配角·情报贩子", backstory: "b",
    motivation: "还清债务", arc: "摇摆后站队", voice_fingerprint: {},
    mannerisms: [], description_history: [], relationships: {},
    state: { emotional_state: "犹豫", physical_state: "轻伤", knowledge_gained: [],
             relationships_shifted: {}, location_end: "钟楼" },
  },
];

const REL_BIBLE: Partial<BibleData> = {
  characters: REL_CHARS,
  events: [
    { id: "e1", chapter: 1, characters: ["c1", "c2"], summary: "酒馆对峙" },
    { id: "e2", chapter: 2, characters: ["c1", "c2", "c3"], summary: "钟楼伏击" },
  ],
};

test("buildGraph: weights from co-appearance, labels merged (shift overrides), degrees", () => {
  const { nodes, edges } = buildGraph({ ...BIBLE_EMPTY, ...REL_BIBLE } as BibleData);
  const find = (a: string, b: string) =>
    edges.find((e) => (e.a === a && e.b === b) || (e.a === b && e.b === a));
  expect(find("c1", "c2")).toMatchObject({ label: "宿敌，夺走了家传怀表", weight: 2 });
  expect(find("c1", "c3")).toMatchObject({ label: "从猜忌转为同盟", weight: 1 });
  expect(find("c2", "c3")).toMatchObject({ label: "", weight: 1 }); // co-appearance only
  expect(nodes.find((n) => n.id === "c1")?.degree).toBe(2);
  expect(nodes).toHaveLength(3);
});

test("Relationships: graph renders nodes and edge labels; click shows character card", async () => {
  stubFetchFor({ bible: REL_BIBLE });
  renderPage(<Relationships />, "/p/:name/relationships");

  expect(await screen.findByTestId("relation-graph")).toBeInTheDocument();
  expect(screen.getByTestId("graph-node-c1")).toBeInTheDocument();
  expect(screen.getByTestId("graph-node-c2")).toBeInTheDocument();
  expect(screen.getByTestId("graph-node-c3")).toBeInTheDocument();
  expect(screen.getAllByText("阿岚").length).toBeGreaterThan(0);
  expect(screen.getByText("宿敌，夺走了家传怀表")).toBeInTheDocument(); // edge label
  expect(screen.getByText("从猜忌转为同盟")).toBeInTheDocument();

  fireEvent.click(screen.getByTestId("graph-node-c1"));
  expect(await screen.findByTestId("relation-detail")).toHaveTextContent("夺回家传怀表");
  expect(screen.getByText("米拉：从猜忌转为同盟")).toBeInTheDocument();

  // click again to deselect
  fireEvent.click(screen.getByTestId("graph-node-c1"));
  expect(screen.getByTestId("relation-detail")).toHaveTextContent("点击图谱中的人物查看详情");
});

test("Relationships: empty state links to setup", async () => {
  stubFetchFor();
  renderPage(<Relationships />, "/p/:name/relationships");
  expect(await screen.findByText("尚无人物设定")).toBeInTheDocument();
  expect(screen.getByText("去分阶段设定")).toHaveAttribute("href", "/p/x/setup");
});

// ---------- Threads page (T8) ----------

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

// ---------- Bible page (Task 10) ----------

const BIBLE_CONCEPT: ConceptData = {
  logline: "L",
  genre: "奇幻",
  tone: "冷峻",
  themes: ["失去", "时间"],
  target_length_words: 9000,
  audience: "成人读者",
};

const BIBLE_WORLD: WorldData = {
  setting: "钟之城",
  era: "末法之世",
  rules: ["钟声可以兑换记忆"],
  power_system: "钟律",
  factions: [{ name: "守钟会", ideology: "秩序", resources: "钟楼", conflict_with: "偷钟人" }],
  locations: [{ name: "大钟楼", description: "城市中心", narrative_function: "主线舞台" }],
  constraints: ["每章至少一口钟出场"],
};

const BIBLE_OUTLINE: OutlineFullData = {
  arcs: [
    {
      arc_name: "第一卷",
      chapters: [
        {
          chapter_no: 1,
          chapter_title: "钟声",
          beats: [
            {
              beat_id: "b1",
              pov: "阿岚",
              setting: "大钟楼",
              event: "偷走第一口钟",
              emotional_turn: "不安",
              characters: ["c1"],
              plants: ["fs-1"],
              payoffs: [],
            },
          ],
        },
      ],
    },
  ],
  foreshadow_ledger: [],
};

test("Bible: renders concept card and section nav", async () => {
  stubFetchFor({ bible: { concept: BIBLE_CONCEPT } });
  renderPage(<Bible />, "/p/:name/bible");

  expect(screen.getByTestId("page-bible")).toBeInTheDocument();
  expect(await screen.findByText("L")).toBeInTheDocument();
  expect(screen.getByText("世界观")).toBeInTheDocument();
  expect(screen.getByTestId("edit-json")).toBeInTheDocument();
});

test("Bible: edit JSON persists via PUT (已保存) and surfaces 422 detail", async () => {
  const ok = stubFetchFor({ bible: { concept: BIBLE_CONCEPT } });
  const first = renderPage(<Bible />, "/p/:name/bible");

  fireEvent.click(await screen.findByTestId("edit-json"));
  const wrap = screen.getByTestId("edit-json-text");
  const ta = (
    wrap.tagName === "TEXTAREA" ? wrap : wrap.querySelector("textarea")!
  ) as HTMLTextAreaElement;
  fireEvent.change(ta, {
    target: { value: JSON.stringify({ ...BIBLE_CONCEPT, logline: "L2" }, null, 2) },
  });
  // antd inserts a space between the two Chinese chars of a button label (保 存)
  fireEvent.click(screen.getByRole("button", { name: "保 存" }));
  expect(await screen.findByText("已保存")).toBeInTheDocument();
  const put = ok.mock.calls.find(
    ([u, i]) => String(u) === "/api/projects/x/bible/concept" && i?.method === "PUT",
  );
  expect(put).toBeTruthy();
  expect(JSON.parse(String(put![1]!.body))).toEqual({ ...BIBLE_CONCEPT, logline: "L2" });
  first.unmount();

  stubFetchFor({
    bible: { concept: BIBLE_CONCEPT },
    putBibleStatus: 422,
    putBibleDetail: "validation error",
  });
  renderPage(<Bible />, "/p/:name/bible");
  fireEvent.click(await screen.findByTestId("edit-json"));
  fireEvent.click(screen.getByRole("button", { name: "保 存" }));
  expect(await screen.findByText("validation error")).toBeInTheDocument();
});

test("Bible: outline extend posts {n}; proposal renders diff; apply resolves gate", async () => {
  const fetchMock = stubFetchFor({ bible: { outline: BIBLE_OUTLINE } });
  renderPage(<Bible />, "/p/:name/bible");

  fireEvent.click(screen.getByText("大纲"));
  fireEvent.change(await screen.findByRole("spinbutton"), { target: { value: "5" } });
  fireEvent.click(screen.getByTestId("extend-outline"));
  await waitFor(() => {
    const call = fetchMock.mock.calls.find((c) => String(c[0]).endsWith("/outline/extend"));
    expect(call).toBeTruthy();
    expect(JSON.parse(String((call![1] as RequestInit).body))).toEqual({ n: 5 });
  });

  act(() => {
    useEvents.getState().apply({
      type: "outline_extend_proposal",
      added: 2,
      diff: "+ 第4章 · 新的开始",
      gate_id: "g1",
    });
  });
  expect(screen.getByTestId("diff-view")).toBeInTheDocument();
  fireEvent.click(screen.getByTestId("outline-apply"));
  await waitFor(() => {
    const call = fetchMock.mock.calls.find((c) => String(c[0]) === "/api/gates/g1");
    expect(call).toBeTruthy();
    expect(JSON.parse(String((call![1] as RequestInit).body))).toEqual({
      approve: true,
      feedback: "",
    });
  });
});

test("Bible: chat panel in right column for world; outline section is read-only", async () => {
  stubFetchFor({ bible: { world: BIBLE_WORLD } });
  renderPage(<Bible />, "/p/:name/bible");

  fireEvent.click(screen.getByText("世界观"));
  expect(await screen.findByTestId("chat-input")).toBeInTheDocument();
  fireEvent.click(screen.getByText("大纲"));
  expect(screen.getByTestId("chat-readonly-note")).toBeInTheDocument();
});

// ---------- Reader TTS card (edge-tts Task 3) ----------

test("Reader: TTS card — voice select, sliders, reset; POST /tts carries params", async () => {
  const fetchMock = stubFetchFor({ status: { has_outline: true, chapters: [1] } });
  renderPage(<Reader />, "/p/:name/reader");
  await screen.findByTestId("tts-card");

  // defaults visible
  expect(screen.getByTestId("tts-voice")).toHaveTextContent("晓晓");
  expect(screen.getByTestId("tts-rate-label")).toHaveTextContent("语速 +0%");
  expect(screen.getByTestId("tts-pitch-label")).toHaveTextContent("音调 +0Hz");

  // antd 5 Select renders no native <select>: open the dropdown and click the option
  fireEvent.mouseDown(screen.getByTestId("tts-voice").querySelector(".ant-select-selector")!);
  fireEvent.click(await screen.findByText("云希（男 · 阳光）"));
  // antd Slider in jsdom: keyboard on the handle (ArrowRight ×4 = +20 at step 5)
  for (let i = 0; i < 4; i++) {
    const handle = screen.getByTestId("tts-rate").querySelector(".ant-slider-handle")!;
    fireEvent.keyDown(handle, { key: "ArrowRight", keyCode: 39 });
  }
  await waitFor(() =>
    expect(screen.getByTestId("tts-rate-label")).toHaveTextContent("语速 +20%"));

  // reset restores defaults (before generate: reset is disabled while pending)
  fireEvent.click(screen.getByTestId("tts-reset"));
  await waitFor(() => {
    expect(screen.getByTestId("tts-rate-label")).toHaveTextContent("语速 +0%");
    expect(screen.getByTestId("tts-voice")).toHaveTextContent("晓晓");
  });

  // re-select for the POST assertion
  fireEvent.mouseDown(screen.getByTestId("tts-voice").querySelector(".ant-select-selector")!);
  fireEvent.click(await screen.findByText("云希（男 · 阳光）"));
  for (let i = 0; i < 4; i++) {
    const handle = screen.getByTestId("tts-rate").querySelector(".ant-slider-handle")!;
    fireEvent.keyDown(handle, { key: "ArrowRight", keyCode: 39 });
  }
  await waitFor(() =>
    expect(screen.getByTestId("tts-rate-label")).toHaveTextContent("语速 +20%"));

  fireEvent.click(screen.getByTestId("tts-generate"));
  await waitFor(() => {
    const call = fetchMock.mock.calls.find((c) => String(c[0]).endsWith("/tts"));
    expect(call).toBeDefined();
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({
      chapter: 1, voice: "zh-CN-YunxiNeural",
      rate: "+20%", volume: "+0%", pitch: "+0Hz",
    });
  });
});

test("Reader: TTS pending feedback clears on tts_done; player appears from /audio", async () => {
  stubFetchFor({ status: { has_outline: true, chapters: [1] }, audio: [{ chapter: 1, size: 1024 }] });
  renderPage(<Reader />, "/p/:name/reader");
  await screen.findByTestId("tts-card");

  // demo mode (stubFetchFor defaults to live:false) shows the placeholder-audio notice
  expect(await screen.findByTestId("tts-demo-notice")).toBeInTheDocument();

  // existing audio renders a player
  expect(await screen.findByTestId("tts-player")).toBeInTheDocument();

  fireEvent.click(screen.getByTestId("tts-generate"));
  expect(await screen.findByTestId("tts-pending")).toBeInTheDocument();

  act(() => {
    useEvents.getState().apply({ type: "stage", stage: "tts", chapter: 1, job_id: "j" });
    useEvents.getState().apply({ type: "tts_done", chapter: 1, job_id: "j" });
  });
  await waitFor(() =>
    expect(screen.queryByTestId("tts-pending")).not.toBeInTheDocument());
});

test("Reader: TTS params persist to localStorage and refill on remount", async () => {
  stubFetchFor({ status: { has_outline: true, chapters: [1] } });
  renderPage(<Reader />, "/p/:name/reader");
  await screen.findByTestId("tts-card");
  // ArrowRight ×6 = +30 at step 5
  for (let i = 0; i < 6; i++) {
    const handle = screen.getByTestId("tts-rate").querySelector(".ant-slider-handle")!;
    fireEvent.keyDown(handle, { key: "ArrowRight", keyCode: 39 });
  }
  fireEvent.click(screen.getByTestId("tts-generate"));
  await waitFor(() => {
    const raw = window.localStorage.getItem("tts-params:x");
    expect(raw).toBeTruthy();
    expect(JSON.parse(raw!)).toMatchObject({ rate: 30 });
  });
});
