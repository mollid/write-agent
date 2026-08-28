import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import Work from "../src/pages/Work";

function renderWork(): void {
  const qc = new QueryClient();
  qc.setDefaultOptions({ queries: { retry: false } });
  const entries = [
    { seq: 0, ts: "2026-08-28T00:00:00Z", type: "user", text: "写一章" },
    { seq: 1, ts: "2026-08-28T00:00:01Z", type: "assistant", text: "好的,开始写第 1 章。" },
    { seq: 2, ts: "2026-08-28T00:00:02Z", type: "action", action: { type: "write_chapters", args: { n: 1 } }, job_id: "j1" },
    { seq: 3, ts: "2026-08-28T00:00:40Z", type: "system", text: "任务结束:write-chapter -> done" },
  ];
  const posts: string[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/projects/x/chat/sessions" && init?.method === "POST") {
      posts.push("create");
      return new Response(JSON.stringify({ session_id: "s1" }), { status: 201 });
    }
    if (url === "/api/projects/x/chat/sessions")
      return new Response(JSON.stringify([{ id: "s1", title: "写一本小说", created: "t", entries: 4 }]), { status: 200 });
    if (url === "/api/projects/x/chat/sessions/s1")
      return new Response(JSON.stringify({ session_id: "s1", entries }), { status: 200 });
    if (url === "/api/projects/x/chat/sessions/s1/messages" && init?.method === "POST") {
      posts.push(String(init.body));
      return new Response(JSON.stringify({ reply: "已完成", action: null, job_id: null }), { status: 200 });
    }
    return new Response(JSON.stringify({}), { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock as unknown as typeof fetch);
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/p/x/work"]}>
        <Routes>
          <Route path="/p/:name/work" element={<Work />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test("renders session list and all four entry kinds", async () => {
  renderWork();
  expect(await screen.findByTestId("page-work")).toBeTruthy();
  expect(await screen.findByText("写一本小说")).toBeTruthy();
  expect(await screen.findByText("好的,开始写第 1 章。")).toBeTruthy();
  expect(await screen.findByText(/撰写章节/)).toBeTruthy();
  expect(await screen.findByText(/任务结束/)).toBeTruthy();
});

test("sending a message posts and shows the reply", async () => {
  renderWork();
  const input = await screen.findByTestId("chat-input");
  fireEvent.change(input, { target: { value: "继续" } });
  fireEvent.click(await screen.findByTestId("chat-send"));
  await waitFor(() =>
    expect(screen.getAllByText("已完成").length).toBeGreaterThan(0));
});
