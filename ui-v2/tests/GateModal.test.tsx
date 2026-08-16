import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { App as AntApp } from "antd";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import GateModal from "../src/components/GateModal";
import { useEvents } from "../src/stores/events";

const qc = new QueryClient();

function renderModal() {
  return render(
    <QueryClientProvider client={qc}>
      <AntApp>
        <MemoryRouter initialEntries={[`/p/x/reader`]}>
          <GateModal project="x" />
        </MemoryRouter>
      </AntApp>
    </QueryClientProvider>,
  );
}

function stubFetch() {
  const fetchMock = vi.fn(async () => new Response("{}", { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function stubFailingFetch() {
  const fetchMock = vi.fn(
    async () => new Response(JSON.stringify({ detail: "boom" }), { status: 500 }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  act(() => {
    useEvents.getState().reset();
  });
});

test("no gate → no modal; setup gate → textarea present", () => {
  stubFetch();
  renderModal();
  expect(screen.queryByTestId("gate-modal")).not.toBeInTheDocument();

  act(() => {
    useEvents.getState().apply({
      type: "gate", gate_id: "g1", label: "setup:world", artifact: "{}", job_id: "j1",
    });
  });
  expect(screen.getByTestId("gate-modal")).toBeInTheDocument();
  expect(screen.getByTestId("gate-feedback")).toBeInTheDocument();
});

test("setup rejection with empty feedback warns and does not call the API", async () => {
  const fetchMock = stubFetch();
  renderModal();
  act(() => {
    useEvents.getState().apply({
      type: "gate", gate_id: "g1", label: "setup:world", artifact: "{}", job_id: "j1",
    });
  });
  fireEvent.click(screen.getByTestId("gate-reject"));
  await waitFor(() =>
    expect(screen.getByText("请填写修改意见，或点击「通过」")).toBeInTheDocument(),
  );
  expect(fetchMock).not.toHaveBeenCalled();
});

test("setup rejection with feedback POSTs and records history", async () => {
  const fetchMock = stubFetch();
  renderModal();
  act(() => {
    useEvents.getState().apply({
      type: "gate", gate_id: "g1", label: "setup:world", artifact: "{}", job_id: "j1",
    });
  });
  fireEvent.change(screen.getByTestId("gate-feedback"), { target: { value: "基调更黑暗" } });
  fireEvent.click(screen.getByTestId("gate-reject"));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  const [url, opts] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
  expect(url).toBe("/api/gates/g1");
  expect(JSON.parse(String(opts.body))).toEqual({ approve: false, feedback: "基调更黑暗" });
  // N1: history is recorded only after the POST succeeds
  await waitFor(() => expect(useEvents.getState().feedbackHistory).toEqual(["基调更黑暗"]));
});

test("failed feedback POST shows an error and records no phantom history (N1)", async () => {
  stubFailingFetch();
  renderModal();
  act(() => {
    useEvents.getState().apply({
      type: "gate", gate_id: "g1", label: "setup:world", artifact: "{}", job_id: "j1",
    });
  });
  fireEvent.change(screen.getByTestId("gate-feedback"), { target: { value: "基调更黑暗" } });
  fireEvent.click(screen.getByTestId("gate-reject"));
  await waitFor(() => expect(screen.getByText(/boom/)).toBeInTheDocument());
  expect(useEvents.getState().feedbackHistory).toEqual([]);
});

test("force-pass gate requires a second confirming click", async () => {
  const fetchMock = stubFetch();
  renderModal();
  act(() => {
    useEvents.getState().apply({
      type: "gate", gate_id: "g2", label: "chapter_review_failed", artifact: "{}", job_id: "j1",
    });
  });
  fireEvent.click(screen.getByTestId("gate-approve"));
  await waitFor(() =>
    expect(screen.getByText(/强行放行不可撤销/)).toBeInTheDocument(),
  );
  expect(fetchMock).not.toHaveBeenCalled();
  fireEvent.click(screen.getByTestId("gate-approve"));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  const [, opts] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
  expect(JSON.parse(String(opts.body))).toEqual({ approve: true, feedback: "" });
});

test("feedback history renders under the 本阶段已提交的反馈 header", () => {
  stubFetch();
  renderModal();
  act(() => {
    useEvents.setState({ feedbackHistory: ["基调更黑暗", "增加反派戏份"] });
    useEvents.getState().apply({
      type: "gate", gate_id: "g1", label: "setup:world", artifact: "{}", job_id: "j1",
    });
  });
  expect(screen.getByText("本阶段已提交的反馈")).toBeInTheDocument();
  expect(screen.getByText("基调更黑暗")).toBeInTheDocument();
  expect(screen.getByText("增加反派戏份")).toBeInTheDocument();
});

test("chapter gate links to the reader; focus returns to opener when gate clears", async () => {
  stubFetch();
  const opener = document.createElement("button");
  document.body.appendChild(opener);
  opener.focus();
  renderModal();
  act(() => {
    useEvents.getState().apply({
      type: "gate", gate_id: "g3", label: "chapter", artifact: "3", job_id: "j1",
    });
  });
  expect(screen.getByText("查看本章")).toHaveAttribute("href", "/p/x/reader?chapter=3");
  // R4: chapter gates carry the chapter number, never a bare unlabelled artifact
  expect(screen.getByTestId("gate-artifact")).toHaveTextContent("第 3 章");
  act(() => {
    useEvents.getState().apply({ type: "job_end", job_id: "j1" });
  });
  await waitFor(() => expect(screen.queryByTestId("gate-modal")).not.toBeInTheDocument());
  expect(document.activeElement).toBe(opener);
  opener.remove();
});
