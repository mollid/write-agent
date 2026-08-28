import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { App as AntApp } from "antd";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import Work from "../src/pages/Work";

interface ChatEntryLike {
  seq: number;
  ts: string;
  type: "user" | "assistant" | "action" | "system";
  text?: string;
  action?: { type: string; args: Record<string, unknown> };
  job_id?: string;
}

const ENTRIES_S1: ChatEntryLike[] = [
  { seq: 0, ts: "2026-08-28T00:00:00Z", type: "user", text: "写一章" },
  { seq: 1, ts: "2026-08-28T00:00:01Z", type: "assistant", text: "好的,开始写第 1 章。" },
  { seq: 2, ts: "2026-08-28T00:00:02Z", type: "action", action: { type: "write_chapters", args: { n: 1 } }, job_id: "j1" },
  { seq: 3, ts: "2026-08-28T00:00:40Z", type: "system", text: "任务结束:write-chapter -> done" },
];

/** Stub the Work chat endpoints; defaults reproduce the original fixture (one
 * session s1 with the four entry kinds and a replying POST). */
function stubChatFetch(over: {
  sessions?: { id: string; title: string; created: string; entries: number }[];
  sessionEntries?: Record<string, ChatEntryLike[]>;
  messageResponse?: () => Response;
} = {}) {
  const sessions = over.sessions ?? [{ id: "s1", title: "写一本小说", created: "t", entries: 4 }];
  const sessionEntries = over.sessionEntries ?? { s1: ENTRIES_S1 };
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/projects/x/chat/sessions" && init?.method === "POST") {
      return new Response(JSON.stringify({ session_id: "s1" }), { status: 201 });
    }
    if (url === "/api/projects/x/chat/sessions")
      return new Response(JSON.stringify(sessions), { status: 200 });
    const mm = url.match(/^\/api\/projects\/x\/chat\/sessions\/([^/]+)\/messages$/);
    if (mm && init?.method === "POST") {
      if (over.messageResponse) return over.messageResponse();
      return new Response(JSON.stringify({ reply: "已完成", action: null, job_id: null }), { status: 200 });
    }
    const m = url.match(/^\/api\/projects\/x\/chat\/sessions\/([^/]+)$/);
    if (m)
      return new Response(
        JSON.stringify({ session_id: m[1], entries: sessionEntries[m[1]] ?? [] }),
        { status: 200 },
      );
    return new Response(JSON.stringify({}), { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock as unknown as typeof fetch);
  return fetchMock;
}

function renderWork(): void {
  const qc = new QueryClient();
  qc.setDefaultOptions({ queries: { retry: false } });
  render(
    <QueryClientProvider client={qc}>
      <AntApp>
        <MemoryRouter initialEntries={["/p/x/work"]}>
          <Routes>
            <Route path="/p/:name/work" element={<Work />} />
          </Routes>
        </MemoryRouter>
      </AntApp>
    </QueryClientProvider>,
  );
}

test("renders session list and all four entry kinds", async () => {
  stubChatFetch();
  renderWork();
  expect(await screen.findByTestId("page-work")).toBeTruthy();
  expect(await screen.findByText("写一本小说")).toBeTruthy();
  expect(await screen.findByText("好的,开始写第 1 章。")).toBeTruthy();
  expect(await screen.findByText(/撰写章节/)).toBeTruthy();
  expect(await screen.findByText(/任务结束/)).toBeTruthy();
});

test("sending a message posts and shows the reply", async () => {
  stubChatFetch();
  renderWork();
  const input = await screen.findByTestId("chat-input");
  fireEvent.change(input, { target: { value: "继续" } });
  fireEvent.click(await screen.findByTestId("chat-send"));
  await waitFor(() =>
    expect(screen.getAllByText("已完成").length).toBeGreaterThan(0));
});

test("sending renders the optimistic user bubble alongside the reply", async () => {
  // 默认 stub 的 GET 条目在 POST 后不变(服务端记录尚未刷新进来):
  // 用户气泡与回复都必须靠乐观渲染可见(spec §4.5)
  stubChatFetch();
  renderWork();
  fireEvent.change(await screen.findByTestId("chat-input"), { target: { value: "继续" } });
  fireEvent.click(await screen.findByTestId("chat-send"));
  await waitFor(() =>
    expect(screen.getAllByText("已完成").length).toBeGreaterThan(0));
  expect(screen.getAllByText("继续").length).toBeGreaterThan(0);
});

test("switching sessions does not leak the previous session's reply", async () => {
  stubChatFetch({
    sessions: [
      { id: "s1", title: "写一本小说", created: "t", entries: 4 },
      { id: "s2", title: "第二本", created: "t", entries: 1 },
    ],
    sessionEntries: {
      s1: ENTRIES_S1,
      s2: [{ seq: 0, ts: "2026-08-28T00:01:00Z", type: "user", text: "换个思路" }],
    },
  });
  renderWork();

  // 在 s1 中发送一条,回复先于服务端记录到达而立即渲染
  fireEvent.change(await screen.findByTestId("chat-input"), { target: { value: "继续" } });
  fireEvent.click(await screen.findByTestId("chat-send"));
  await waitFor(() =>
    expect(screen.getAllByText("已完成").length).toBeGreaterThan(0));

  // 切到 s2:s2 自己的条目出现,但 s1 的回复不得出现在 s2 的视图里
  fireEvent.click(await screen.findByText("第二本"));
  expect(await screen.findByText("换个思路")).toBeInTheDocument();
  expect(screen.queryByText("已完成")).toBeNull();
});

test("send failure restores the input text and surfaces the server error", async () => {
  stubChatFetch({
    messageResponse: () => new Response(JSON.stringify({ detail: "文本过长" }), { status: 422 }),
  });
  renderWork();

  const input = (await screen.findByTestId("chat-input")) as HTMLTextAreaElement;
  fireEvent.change(input, { target: { value: "写一万章" } });
  fireEvent.click(await screen.findByTestId("chat-send"));
  await waitFor(() => expect(screen.getByText(/文本过长/)).toBeInTheDocument());
  expect((screen.getByTestId("chat-input") as HTMLTextAreaElement).value).toBe("写一万章");
});
