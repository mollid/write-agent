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
  /** Latest setup-stage artifact (N3): set on `setup_stage` events that carry
   * an `artifact`; per-STAGE, replaced as each stage generates. Cleared on job
   * death too (resetTransient) so a stale artifact never outlives its job. */
  setupArtifact: { stage: string; attempt: number; artifact: string } | null;
  /** Last observed job_end (seq makes repeated identical payloads re-trigger
   * consumers, e.g. the Generate page's final toast). */
  lastEnd: { status: string; error: string | null; seq: number } | null;
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
  setupArtifact: null,
  lastEnd: null,
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
          if (typeof ev.artifact === "string" && ev.artifact) {
            patch.setupArtifact = {
              stage: String(ev.stage),
              attempt: Number(ev.attempt ?? 1),
              artifact: ev.artifact,
            };
          }
          break;
        case "job_end":
          patch.job = null;
          patch.gate = null;
          patch.progress = null;
          patch.lastEnd = {
            status: String(ev.status ?? "unknown"),
            error: typeof ev.error === "string" ? ev.error : null,
            seq: (s.lastEnd?.seq ?? 0) + 1,
          };
          break;
        case "chapter_done":
        case "chapter_skipped":
          // N4: a skipped chapter is final too — count it toward progress so
          // the bar completes even when the backend auto-skips done chapters.
          patch.progress = s.progress
            ? { ...s.progress, done: s.progress.done + 1 }
            : s.progress;
          break;
      }
      return patch;
    }),
  resetTransient: () =>
    set({ gate: null, job: null, progress: null, setupArtifact: null }),
  reset: () =>
    set({
      connected: false,
      lines: [],
      gate: null,
      job: null,
      progress: null,
      lastStage: null,
      feedbackHistory: [],
      setupArtifact: null,
      lastEnd: null,
    }),
}));
