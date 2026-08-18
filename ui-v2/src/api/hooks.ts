import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import { p } from "../constants";
import type { BibleData, OutlineInfo, ProjectStatus, ReviewRecord, Thread } from "./types";

export interface ProjectSummary {
  name: string;
}
export interface ModeInfo {
  live: boolean;
}
export interface ChapterContent {
  chapter: number;
  content: string;
}

// ---------- queries ----------

export function useProjects() {
  return useQuery({
    queryKey: ["projects"],
    queryFn: () => api<ProjectSummary[]>("/api/projects"),
  });
}

export function useMode() {
  return useQuery({
    queryKey: ["mode"],
    queryFn: () => api<ModeInfo>("/api/mode"),
    staleTime: Infinity,
  });
}

export function useStatus(name: string | undefined) {
  return useQuery({
    queryKey: ["status", name],
    queryFn: () => api<ProjectStatus>(`${p(name!)}/status`),
    enabled: !!name,
  });
}

export function useChapter(name: string, n: number | null) {
  return useQuery({
    queryKey: ["chapters", name, n],
    queryFn: () => api<ChapterContent>(`${p(name)}/chapters/${n}`),
    enabled: n != null,
  });
}

export function useReviews(name: string) {
  return useQuery({
    queryKey: ["reviews", name],
    queryFn: () => api<ReviewRecord[]>(`${p(name)}/reviews`),
  });
}

export function useThreads(name: string) {
  return useQuery({
    queryKey: ["threads", name],
    queryFn: () => api<Thread[]>(`${p(name)}/threads`),
  });
}

export function useOutline(name: string) {
  return useQuery({
    queryKey: ["outline", name],
    queryFn: () => api<OutlineInfo>(`${p(name)}/outline`),
  });
}

export function useBible(name: string) {
  return useQuery({
    queryKey: ["bible", name],
    queryFn: () => api<BibleData>(`${p(name)}/bible`),
    enabled: !!name,
  });
}

// ---------- mutations ----------

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { name: string; genre: string }) =>
      api<{ name: string; root: string }>("/api/projects", {
        method: "POST",
        body: JSON.stringify(vars),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

export function usePremise(name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { text: string }) =>
      api<{ job_id: string }>(`${p(name)}/premise`, {
        method: "POST",
        body: JSON.stringify(vars),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["status", name] });
      void qc.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

export function useSetup(name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { premise: string }) =>
      api<{ job_id: string }>(`${p(name)}/setup`, {
        method: "POST",
        body: JSON.stringify(vars),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["status", name] });
      void qc.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

export function useWriteChapters(name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { n: number }) =>
      api<{ job_id: string }>(`${p(name)}/write-chapter`, {
        method: "POST",
        body: JSON.stringify(vars),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["status", name] });
      void qc.invalidateQueries({ queryKey: ["projects"] });
      void qc.invalidateQueries({ queryKey: ["reviews", name] });
      void qc.invalidateQueries({ queryKey: ["chapters", name] });
      void qc.invalidateQueries({ queryKey: ["outline", name] });
    },
  });
}

export function useExport(name: string) {
  return useMutation({
    mutationFn: () =>
      api<{ path: string }>(`${p(name)}/export`, { method: "POST", body: "{}" }),
  });
}

export function useResolveGate(name?: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: string; approve: boolean; feedback?: string }) =>
      api<{ resolved: boolean }>(`/api/gates/${vars.id}`, {
        method: "POST",
        body: JSON.stringify({ approve: vars.approve, feedback: vars.feedback ?? "" }),
      }),
    onSuccess: () => {
      if (name !== undefined) {
        void qc.invalidateQueries({ queryKey: ["status", name] });
      } else {
        void qc.invalidateQueries({ queryKey: ["status"] });
      }
      void qc.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

export function useCancelJob(name?: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api<{ cancelled: boolean }>(`/api/jobs/${id}/cancel`, { method: "POST", body: "{}" }),
    onSuccess: () => {
      if (name !== undefined) {
        void qc.invalidateQueries({ queryKey: ["status", name] });
      } else {
        void qc.invalidateQueries({ queryKey: ["status"] });
      }
      void qc.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

export function useSaveBibleSection(name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { section: string; data: unknown }) =>
      api<{ ok: boolean }>(`${p(name)}/bible/${vars.section}`, {
        method: "PUT",
        body: JSON.stringify(vars.data),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["bible", name] });
      void qc.invalidateQueries({ queryKey: ["status", name] });
    },
  });
}

export function useBibleChat(name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { section: string; instruction: string; character_id?: string }) =>
      api<{ job_id: string }>(`${p(name)}/bible/chat`, {
        method: "POST",
        body: JSON.stringify(vars),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["status", name] });
    },
  });
}

export function useOutlineExtend(name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { n: number }) =>
      api<{ job_id: string }>(`${p(name)}/outline/extend`, {
        method: "POST",
        body: JSON.stringify(vars),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["outline", name] });
      void qc.invalidateQueries({ queryKey: ["status", name] });
    },
  });
}

export function useChapterRewrite(name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { chapter: number; mode: string; instruction: string }) =>
      api<{ job_id: string }>(`${p(name)}/chapter-rewrite`, {
        method: "POST",
        body: JSON.stringify(vars),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["status", name] });
    },
  });
}

export function useSaveChapter(name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { chapter: number; content: string }) =>
      api<{ ok: boolean; backup: string }>(`${p(name)}/chapters/${vars.chapter}`, {
        method: "PUT",
        body: JSON.stringify({ content: vars.content }),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["chapters", name] });
    },
  });
}
