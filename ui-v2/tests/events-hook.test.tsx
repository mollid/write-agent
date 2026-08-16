import type { ReactNode } from "react";
import { renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "@testing-library/react";
import { test, vi } from "vitest";
import { useProjectEvents } from "../src/api/events";
import { useEvents } from "../src/stores/events";

const instances: FakeES[] = [];

class FakeES {
  onopen: (() => void) | null = null;
  onmessage: ((m: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(_url: string | URL) {
    instances.push(this);
  }
  close(): void {}
}

function stubFetch(statusBody: object, jobBody: object | null) {
  const mock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/status")) return new Response(JSON.stringify(statusBody), { status: 200 });
    if (/\/api\/jobs\/.+/.test(url)) return new Response(JSON.stringify(jobBody ?? {}), { status: 200 });
    return new Response("{}", { status: 200 });
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

const qc = new QueryClient();
const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={qc}>{children}</QueryClientProvider>
);

test("reconnects after error and reconciles on every open", async () => {
  vi.useFakeTimers();
  instances.length = 0;
  const fetchMock = stubFetch({ job: null }, null);
  vi.stubGlobal("EventSource", FakeES as unknown as typeof EventSource);

  const { unmount } = renderHook(() => useProjectEvents("x"), { wrapper });
  expect(instances.length).toBe(1);

  await act(async () => {
    instances[0].onopen?.();
  });
  expect(fetchMock.mock.calls.some((c) => String(c[0]).endsWith("/api/projects/x/status"))).toBe(
    true,
  );

  act(() => {
    instances[0].onerror?.();
  });
  act(() => {
    vi.advanceTimersByTime(2000);
  });
  expect(instances.length).toBe(2); // reconnected

  await act(async () => {
    instances[1].onopen?.();
  });
  const statusCalls = fetchMock.mock.calls.filter((c) =>
    String(c[0]).endsWith("/api/projects/x/status"),
  );
  expect(statusCalls.length).toBeGreaterThanOrEqual(2); // reconciled again

  unmount();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

test("reconcile clears a stale gate when the job has no pending gates", async () => {
  instances.length = 0;
  stubFetch(
    { job: { id: "j1", kind: "setup", status: "running", error: null } },
    { id: "j1", kind: "setup", status: "running", error: null, project: "x", gates: [] },
  );
  vi.stubGlobal("EventSource", FakeES as unknown as typeof EventSource);

  const { unmount } = renderHook(() => useProjectEvents("x"), { wrapper });
  // a gate was held locally when the connection dropped
  act(() => {
    useEvents.getState().apply({
      type: "gate",
      gate_id: "stale",
      label: "setup:world",
      artifact: "{}",
      job_id: "j1",
    });
  });
  expect(useEvents.getState().gate?.id).toBe("stale");

  await act(async () => {
    instances[0].onopen?.(); // reconnect → reconcile
  });
  expect(useEvents.getState().gate).toBeNull(); // cleared, nothing re-applied

  unmount();
  vi.unstubAllGlobals();
});
