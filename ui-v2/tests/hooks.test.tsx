import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { ReactNode } from "react";
import { afterEach, expect, test, vi } from "vitest";
import { ApiError } from "../src/api/client";
import { useMode, useProjects } from "../src/api/hooks";

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

afterEach(() => vi.unstubAllGlobals());

test("useMode fetches /api/mode", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ live: false }), { status: 200 })),
  );
  const { result } = renderHook(() => useMode(), { wrapper });
  await waitFor(() => expect(result.current.data).toEqual({ live: false }));
});

test("useProjects fetches /api/projects", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    if (String(input) === "/api/projects") {
      return new Response(JSON.stringify([{ name: "po" }]), { status: 200 });
    }
    return new Response("{}", { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  const { result } = renderHook(() => useProjects(), { wrapper });
  await waitFor(() => expect(result.current.data).toEqual([{ name: "po" }]));
  expect(fetchMock).toHaveBeenCalledWith("/api/projects", expect.anything());
});

test("api client surfaces ApiError with status", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(JSON.stringify({ detail: "任务已在运行" }), { status: 409 }),
    ),
  );
  const { api } = await import("../src/api/client");
  await expect(api("/api/projects/po/setup", { method: "POST" })).rejects.toThrow(ApiError);
  await expect(api("/api/projects/po/setup", { method: "POST" })).rejects.toMatchObject({
    status: 409,
    message: "任务已在运行",
  });
});
