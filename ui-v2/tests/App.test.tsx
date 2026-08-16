import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import App from "../src/App";
import { useEvents } from "../src/stores/events";

/** jsdom has no EventSource — stub a never-opening one. */
class FakeEventSource {
  onopen: (() => void) | null = null;
  onmessage: ((m: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  close(): void {}
  constructor(_url: string | URL) {}
}

function stubFetch() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/mode") return new Response(JSON.stringify({ live: false }), { status: 200 });
    if (url === "/api/projects") return new Response(JSON.stringify([]), { status: 200 });
    return new Response("{}", { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  useEvents.getState().reset();
  window.history.pushState({}, "", "/");
});

test("root renders the standalone Projects page (no console shell)", () => {
  stubFetch();
  vi.stubGlobal("EventSource", FakeEventSource);
  window.history.pushState({}, "", "/");
  render(<App />);

  expect(screen.getByTestId("page-projects")).toBeInTheDocument();
  expect(screen.queryByText("创作")).not.toBeInTheDocument();
});

test("/p/x/overview renders shell: selector, grouped Sider, demo badge, page; no JobStrip", async () => {
  stubFetch();
  vi.stubGlobal("EventSource", FakeEventSource);
  window.history.pushState({}, "", "/p/x/overview");
  render(<App />);

  // project is selected (name=x) — Select shows the value, not the placeholder
  expect(document.querySelector(".ant-select-selection-item")?.textContent).toBe("x");
  expect(screen.getByText("创作")).toBeInTheDocument();
  expect(screen.getByText("审阅与输出")).toBeInTheDocument();
  const creationItems = ["概览", "分阶段设定", "生成章节", "章节阅读"];
  const reviewItems = ["评分历史", "伏笔台账", "导出"];
  for (const label of [...creationItems, ...reviewItems]) {
    expect(screen.getByText(label)).toBeInTheDocument();
  }
  await waitFor(() => expect(screen.getByText("演示模式")).toBeInTheDocument());
  expect(screen.getByTestId("page-overview")).toBeInTheDocument();
  expect(screen.queryByTestId("job-strip")).not.toBeInTheDocument();
});

test("sider title navigates back to the project list", async () => {
  stubFetch();
  vi.stubGlobal("EventSource", FakeEventSource);
  window.history.pushState({}, "", "/p/x/overview");
  render(<App />);
  fireEvent.click(screen.getByTestId("home-link"));
  await waitFor(() => expect(screen.getByTestId("page-projects")).toBeInTheDocument());
});

test("JobStrip appears with visible stage label when a job is running", async () => {
  stubFetch();
  vi.stubGlobal("EventSource", FakeEventSource);
  window.history.pushState({}, "", "/p/x/overview");
  render(<App />);

  useEvents.getState().apply({ type: "stage", stage: "writer", chapter: 1, job_id: "j1" });
  await waitFor(() => expect(screen.getByTestId("job-strip")).toBeInTheDocument());
  expect(screen.getByTestId("job-stage")).toHaveTextContent("正文写作中");
});
