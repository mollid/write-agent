import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, expect, test, vi } from "vitest";
import { App as AntApp } from "antd";
import BibleChat from "../src/components/BibleChat";
import DiffView from "../src/components/DiffView";
import { useEvents } from "../src/stores/events";
import type { BibleData } from "../src/api/types";

// ---------- helpers ----------

const BIBLE: BibleData = {
  concept: null,
  world: null,
  characters: [
    {
      id: "c1",
      slug: "ara",
      name: "阿岚",
      role: "主角",
      backstory: "",
      motivation: "",
      arc: "",
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
  outline: null,
  foreshadows: [],
  events: [],
};

/** Stub fetch for the endpoints BibleChat touches (bible query + chat/gate POSTs). */
function stubFetch(over: { bible?: BibleData } = {}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/projects/x/bible")
      return new Response(JSON.stringify(over.bible ?? BIBLE), { status: 200 });
    if (url === "/api/projects/x/status")
      return new Response(JSON.stringify({ name: "x", chapters: [] }), { status: 200 });
    if (init?.method === "POST" && url === "/api/projects/x/bible/chat")
      return new Response(JSON.stringify({ job_id: "j1" }), { status: 202 });
    if (init?.method === "POST" && url.startsWith("/api/gates/"))
      return new Response(JSON.stringify({ resolved: true }), { status: 200 });
    return new Response("{}", { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderPanel(el: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AntApp>{el}</AntApp>
    </QueryClientProvider>,
  );
}

function lastBodyOf(fetchMock: ReturnType<typeof stubFetch>, url: string): Record<string, unknown> {
  const call = fetchMock.mock.calls.find((c) => String(c[0]) === url);
  expect(call).toBeTruthy();
  return JSON.parse(String((call![1] as RequestInit).body));
}

function inputArea(): HTMLTextAreaElement {
  const el = screen.getByTestId("chat-input");
  return (
    el.tagName === "TEXTAREA" ? el : el.querySelector("textarea")!
  ) as HTMLTextAreaElement;
}

/** jsdom may normalize hex to rgb(...) — accept either form. */
const AS_RGB = (hex: string): string => {
  const n = hex.slice(1);
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(n.slice(i, i + 2), 16));
  return `rgb(${r}, ${g}, ${b})`;
};

afterEach(() => {
  vi.unstubAllGlobals();
  useEvents.getState().reset();
});

// ---------- DiffView ----------

test("DiffView: signs each line (+/-/@/ctx) with contract colors; empty diff is empty", () => {
  const { rerender } = render(
    <DiffView diff={'- "a": 1\n+ "a": 2\n@@ -1 +1 @@\n  context'} />,
  );
  const el = screen.getByTestId("diff-view");
  const lines = Array.from(el.children);
  expect(lines.map((l) => l.getAttribute("data-sign"))).toEqual(["-", "+", "@", "ctx"]);

  const bg = (l: Element) => (l as HTMLElement).style.backgroundColor.toLowerCase();
  expect([ "#fdecea", AS_RGB("#fdecea") ]).toContain(bg(lines[0]));
  expect([ "#e6f4ea", AS_RGB("#e6f4ea") ]).toContain(bg(lines[1]));
  // hunk header gray text; context line unstyled
  const fg = (l: Element) => (l as HTMLElement).style.color.toLowerCase();
  expect([ "#8c8c8c", AS_RGB("#8c8c8c") ]).toContain(fg(lines[2]));
  expect(bg(lines[3])).toBe("");

  rerender(<DiffView diff="" />);
  expect(screen.getByTestId("diff-view").children.length).toBe(0);
  rerender(<DiffView diff={undefined} />);
  expect(screen.getByTestId("diff-view").children.length).toBe(0);
});

// ---------- BibleChat: read-only sections ----------

test("BibleChat: outline/events sections render a read-only note instead of the composer", async () => {
  stubFetch();
  const { rerender } = renderPanel(<BibleChat name="x" section="outline" />);
  expect(screen.getByTestId("chat-readonly-note")).toHaveTextContent(/追章/);
  expect(screen.queryByTestId("chat-input")).not.toBeInTheDocument();
  expect(screen.queryByTestId("chat-send")).not.toBeInTheDocument();

  rerender(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <AntApp>
        <BibleChat name="x" section="events" />
      </AntApp>
    </QueryClientProvider>,
  );
  expect(screen.getByTestId("chat-readonly-note")).toHaveTextContent(/自动记录/);
  expect(screen.queryByTestId("chat-input")).not.toBeInTheDocument();
});

test("BibleChat: foreshadows section renders a read-only note (edit JSON instead)", async () => {
  stubFetch();
  renderPanel(<BibleChat name="x" section="foreshadows" />);
  expect(screen.getByTestId("chat-readonly-note")).toHaveTextContent(
    "伏笔暂不支持对话改写，请使用编辑 JSON",
  );
  expect(screen.queryByTestId("chat-input")).not.toBeInTheDocument();
  expect(screen.queryByTestId("chat-send")).not.toBeInTheDocument();
});

// ---------- BibleChat: send flow ----------

test("BibleChat: send posts {section, instruction} and records a pending history entry", async () => {
  const fetchMock = stubFetch();
  renderPanel(<BibleChat name="x" section="world" />);

  expect(screen.getByTestId("chat-send")).toBeDisabled(); // empty text
  fireEvent.change(inputArea(), { target: { value: "让世界更冷" } });
  expect(screen.getByTestId("chat-send")).toBeEnabled();
  fireEvent.click(screen.getByTestId("chat-send"));

  await waitFor(() =>
    expect(lastBodyOf(fetchMock, "/api/projects/x/bible/chat")).toEqual({
      section: "world",
      instruction: "让世界更冷",
    }),
  );
  // pending entry: instruction + 生成中 status tag; composer cleared
  expect(await screen.findByText("让世界更冷")).toBeInTheDocument();
  expect(screen.getByText("生成中")).toBeInTheDocument();
  expect(inputArea().value).toBe("");
});

test("BibleChat: characters section renders the character select and sends character_id", async () => {
  const fetchMock = stubFetch();
  renderPanel(<BibleChat name="x" section="characters" />);

  const select = screen.getByTestId("chat-character-select");
  fireEvent.mouseDown(select.querySelector(".ant-select-selector")!);
  fireEvent.click(await screen.findByText("阿岚"));
  fireEvent.change(inputArea(), { target: { value: "给她加一条伤疤" } });
  fireEvent.click(screen.getByTestId("chat-send"));

  await waitFor(() =>
    expect(lastBodyOf(fetchMock, "/api/projects/x/bible/chat")).toEqual({
      section: "characters",
      instruction: "给她加一条伤疤",
      character_id: "c1",
    }),
  );
});

test("BibleChat: characters section keeps send disabled until a character is selected", async () => {
  stubFetch();
  renderPanel(<BibleChat name="x" section="characters" />);

  fireEvent.change(inputArea(), { target: { value: "给她加一条伤疤" } });
  expect(screen.getByTestId("chat-send")).toBeDisabled(); // no character yet

  const select = screen.getByTestId("chat-character-select");
  fireEvent.mouseDown(select.querySelector(".ant-select-selector")!);
  fireEvent.click(await screen.findByText("阿岚"));
  expect(screen.getByTestId("chat-send")).toBeEnabled();
});

// ---------- BibleChat: pending sweep on job end ----------

test("BibleChat: a pending entry flips to 已放弃 when the job ends without done", async () => {
  stubFetch();
  renderPanel(<BibleChat name="x" section="world" />);

  fireEvent.change(inputArea(), { target: { value: "让世界更冷" } });
  fireEvent.click(screen.getByTestId("chat-send"));
  expect(await screen.findByText("生成中")).toBeInTheDocument();

  // job dies before any gate resolution — job_end must sweep the pending entry
  act(() => {
    useEvents.getState().apply({ type: "job_end", status: "error", error: "boom" });
  });
  await waitFor(() => expect(screen.getByText("已放弃")).toBeInTheDocument());
  expect(screen.queryByText("生成中")).not.toBeInTheDocument();
});

// ---------- BibleChat: proposal → apply ----------

test("BibleChat: matching proposal renders diff + apply/discard; apply resolves the gate; done flips history", async () => {
  const fetchMock = stubFetch();
  renderPanel(<BibleChat name="x" section="world" />);

  // a proposal for ANOTHER section must not render here
  act(() => {
    useEvents.getState().apply({
      type: "bible_proposal", section: "characters", diff: "+x", draft: {}, gate_id: "g1",
    });
  });
  expect(screen.queryByTestId("diff-view")).not.toBeInTheDocument();

  fireEvent.change(inputArea(), { target: { value: "让世界更冷" } });
  fireEvent.click(screen.getByTestId("chat-send"));
  expect(await screen.findByText("生成中")).toBeInTheDocument();

  act(() => {
    useEvents.getState().apply({
      type: "bible_proposal",
      section: "world",
      diff: '- "cold": false\n+ "cold": true',
      draft: {},
      gate_id: "g9",
    });
  });
  expect(screen.getByTestId("diff-view")).toBeInTheDocument();
  expect(screen.getByTestId("diff-view").children[0].getAttribute("data-sign")).toBe("-");
  // hint: discard then re-instruct instead of a feedback box
  expect(screen.getByText(/放弃/)).toBeInTheDocument();
  // composer locked while a proposal is pending
  expect(screen.getByTestId("chat-send")).toBeDisabled();

  fireEvent.click(screen.getByTestId("chat-apply"));
  await waitFor(() => expect(lastBodyOf(fetchMock, "/api/gates/g9")).toEqual({
    approve: true,
    feedback: "",
  }));

  // backend confirms via SSE; the store also clears the proposal
  act(() => {
    useEvents.getState().apply({ type: "bible_chat_done", section: "world", applied: true });
  });
  expect(useEvents.getState().bibleChatDone).toMatchObject({ section: "world", applied: true, seq: 1 });
  await waitFor(() => expect(screen.getByText("已应用")).toBeInTheDocument());
  expect(screen.queryByTestId("diff-view")).not.toBeInTheDocument();
  expect(screen.getByTestId("chat-send")).toBeDisabled(); // text empty again

  useEvents.getState().reset();
  expect(useEvents.getState().bibleChatDone).toBeNull();
});

test("BibleChat: discard resolves approve=false and done marks 已放弃", async () => {
  const fetchMock = stubFetch();
  renderPanel(<BibleChat name="x" section="world" />);

  fireEvent.change(inputArea(), { target: { value: "让世界更冷" } });
  fireEvent.click(screen.getByTestId("chat-send"));
  expect(await screen.findByText("生成中")).toBeInTheDocument();
  act(() => {
    useEvents.getState().apply({
      type: "bible_proposal", section: "world", diff: "+x", draft: {}, gate_id: "g2",
    });
  });

  fireEvent.click(screen.getByTestId("chat-discard"));
  await waitFor(() => expect(lastBodyOf(fetchMock, "/api/gates/g2")).toEqual({
    approve: false,
    feedback: "",
  }));
  act(() => {
    useEvents.getState().apply({ type: "bible_chat_done", section: "world", applied: false });
  });
  await waitFor(() => expect(screen.getByText("已放弃")).toBeInTheDocument());
});
