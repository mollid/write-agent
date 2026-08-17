import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { ReactNode } from "react";
import { afterEach, expect, test, vi } from "vitest";
import { ApiError } from "../src/api/client";
import { useBible, useBibleChat, useMode, useOutlineExtend, useProjects, useSaveBibleSection } from "../src/api/hooks";

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

test("useBible fetches and useSaveBibleSection PUTs with invalidation", async () => {
  const bibleFixture = {
    concept: null,
    world: null,
    characters: [],
    outline: null,
    foreshadows: [],
    events: [],
  };
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/projects/po/bible") {
      return new Response(JSON.stringify(bibleFixture), { status: 200 });
    }
    if (url === "/api/projects/po/bible/world" && init?.method === "PUT") {
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    }
    return new Response("{}", { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  const { result } = renderHook(
    () => ({ bible: useBible("po"), save: useSaveBibleSection("po") }),
    { wrapper },
  );
  await waitFor(() => expect(result.current.bible.data).toEqual(bibleFixture));
  expect(fetchMock).toHaveBeenCalledWith("/api/projects/po/bible", expect.anything());
  const getsBefore = fetchMock.mock.calls.filter(([u]) => String(u) === "/api/projects/po/bible").length;
  const out = await act(async () =>
    result.current.save.mutateAsync({ section: "world", data: { setting: "沙漠" } }),
  );
  expect(out).toEqual({ ok: true });
  const put = fetchMock.mock.calls.find(
    ([u, i]) => String(u) === "/api/projects/po/bible/world" && i?.method === "PUT",
  );
  expect(put?.[1]?.body).toBe(JSON.stringify({ setting: "沙漠" }));
  await waitFor(() => {
    const getsAfter = fetchMock.mock.calls.filter(([u]) => String(u) === "/api/projects/po/bible").length;
    expect(getsAfter).toBeGreaterThan(getsBefore);
  });
});

test("useBibleChat POSTs section/instruction/character_id", async () => {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify({ job_id: "j1" }), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  const { result } = renderHook(() => useBibleChat("po"), { wrapper });
  const vars = { section: "characters", instruction: "丰富配角动机", character_id: "c1" };
  const out = await act(async () => result.current.mutateAsync(vars));
  expect(out).toEqual({ job_id: "j1" });
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/projects/po/bible/chat",
    expect.objectContaining({ method: "POST", body: JSON.stringify(vars) }),
  );
});

test("useOutlineExtend POSTs n", async () => {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify({ job_id: "j2" }), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  const { result } = renderHook(() => useOutlineExtend("po"), { wrapper });
  const out = await act(async () => result.current.mutateAsync({ n: 3 }));
  expect(out).toEqual({ job_id: "j2" });
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/projects/po/outline/extend",
    expect.objectContaining({ method: "POST", body: JSON.stringify({ n: 3 }) }),
  );
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
