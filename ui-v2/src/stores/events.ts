import { create } from "zustand";
import type { SseEvent } from "../api/types";

export interface LogLine {
  time: string;
  text: string;
}
interface EventState {
  connected: boolean;
  lines: LogLine[];
  gate: { id: string; label: string; artifact: string } | null;
  job: { id: string; kind: string } | null;
  progress: { done: number; total: number } | null;
  lastStage: string | null;
  feedbackHistory: string[];
  pushLine: (text: string) => void;
  setConnected: (v: boolean) => void;
  pushFeedback: (text: string) => void;
  apply: (ev: SseEvent) => void;
  /** Clear transient job state (gate/job/progress) but keep log lines. */
  resetTransient: () => void;
  reset: () => void;
}
const MAX_LINES = 500;
const fmt = () => new Date().toLocaleTimeString("zh-CN", { hour12: false });

export const useEvents = create<EventState>((set) => ({
  connected: false,
  lines: [],
  gate: null,
  job: null,
  progress: null,
  lastStage: null,
  feedbackHistory: [],
  pushLine: (text) =>
    set((s) => ({ lines: [...s.lines, { time: fmt(), text }].slice(-MAX_LINES) })),
  setConnected: (v) => set({ connected: v }),
  pushFeedback: (text) => set((s) => ({ feedbackHistory: [...s.feedbackHistory, text] })),
  apply: (ev) =>
    set((s) => {
      const patch: Partial<EventState> = {};
      if (ev.job_id && typeof ev.job_id === "string")
        patch.job = {
          id: ev.job_id,
          kind: String((ev as { kind?: string }).kind ?? s.job?.kind ?? ""),
        };
      switch (ev.type) {
        case "stage":
          patch.lastStage = String(ev.stage);
          break;
        case "gate":
          patch.gate = {
            id: String(ev.gate_id),
            label: String(ev.label),
            artifact: String(ev.artifact ?? ""),
          };
          break;
        case "setup_stage":
          if (ev.attempt === 1) patch.feedbackHistory = [];
          break;
        case "job_end":
          patch.job = null;
          patch.gate = null;
          patch.progress = null;
          break;
        case "chapter_done":
          patch.progress = s.progress
            ? { ...s.progress, done: s.progress.done + 1 }
            : s.progress;
          break;
      }
      return patch;
    }),
  resetTransient: () => set({ gate: null, job: null, progress: null }),
  reset: () =>
    set({
      connected: false,
      lines: [],
      gate: null,
      job: null,
      progress: null,
      lastStage: null,
      feedbackHistory: [],
    }),
}));
