import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, expect, test, vi } from "vitest";
import { App as AntApp } from "antd";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import Setup from "../src/pages/Setup";
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
} = {}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/mode")
      return new Response(JSON.stringify({ live: over.live ?? false }), { status: 200 });
    if (url === "/api/projects/x/status")
      return new Response(JSON.stringify({ ...baseStatus, ...over.status }), { status: 200 });
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

function renderPage(el: ReactElement, routePath = "/p/:name/setup") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AntApp>
        <MemoryRouter initialEntries={[routePath.replace(":name", "x")]}>
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
