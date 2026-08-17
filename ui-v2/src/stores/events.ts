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
  /** F2: bumped each time the Generate 409 CTA「查看运行中任务」is clicked;
   * JobStrip watches it to briefly flash a highlight (the CTA already sits on
   * the Generate page, so navigating would be a no-op). */
  stripPulse: number;
  /** True while the user dismissed the gate modal without deciding; a NEW gate
   * event or「打开审批」flips it back. The job keeps waiting server-side. */
  gateDismissed: boolean;
  bibleProposal: { section: string; diff: string; gateId: string; draft: unknown } | null;
  outlineProposal: { added: number; diff: string; gateId: string } | null;
  /** Task 9: last bible_chat_done outcome (seq re-triggers repeated payloads);
   * BibleChat panels watch it to flip their pending history entry. */
  bibleChatDone: { section: string; applied: boolean; seq: number } | null;
  pushLine: (text: string) => void;
  setConnected: (v: boolean) => void;
  pushFeedback: (text: string) => void;
  pulseStrip: () => void;
  dismissGate: () => void;
  reopenGate: () => void;
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
  stripPulse: 0,
  gateDismissed: false,
  bibleProposal: null,
  outlineProposal: null,
  bibleChatDone: null,
  pushLine: (text) =>
    set((s) => ({ lines: [...s.lines, { time: fmt(), text }].slice(-MAX_LINES) })),
  setConnected: (v) => set({ connected: v }),
  pushFeedback: (text) => set((s) => ({ feedbackHistory: [...s.feedbackHistory, text] })),
  pulseStrip: () => set((s) => ({ stripPulse: s.stripPulse + 1 })),
  dismissGate: () => set({ gateDismissed: true }),
  reopenGate: () => set({ gateDismissed: false }),
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
          if (String(ev.label).startsWith("bible:")) {
            // bible gates render in the Bible page's diff panel, not the global modal
            if (String(ev.label) === "bible:outline_extend" && s.outlineProposal) {
              patch.outlineProposal = { ...s.outlineProposal, gateId: String(ev.gate_id ?? "") };
            } else if (s.bibleProposal) {
              patch.bibleProposal = { ...s.bibleProposal, gateId: String(ev.gate_id ?? "") };
            }
            break;
          }
          patch.gateDismissed = false;
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
          patch.bibleProposal = null;
          patch.outlineProposal = null;
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
        case "bible_proposal":
          patch.bibleProposal = {
            section: String(ev.section), diff: String(ev.diff ?? ""),
            gateId: String(ev.gate_id ?? ""), draft: (ev as { draft?: unknown }).draft,
          };
          break;
        case "bible_chat_done":
          patch.bibleProposal = null;
          patch.bibleChatDone = {
            section: String(ev.section ?? ""),
            applied: Boolean(ev.applied),
            seq: (s.bibleChatDone?.seq ?? 0) + 1,
          };
          break;
        case "outline_extend_proposal":
          patch.outlineProposal = {
            added: Number(ev.added ?? 0), diff: String(ev.diff ?? ""),
            gateId: String(ev.gate_id ?? ""),
          };
          break;
        case "outline_extended":
          patch.outlineProposal = null;
          break;
      }
      return patch;
    }),
  resetTransient: () =>
    set({
      gate: null, job: null, progress: null, setupArtifact: null, gateDismissed: false,
      bibleProposal: null, outlineProposal: null, bibleChatDone: null,
    }),
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
      stripPulse: 0,
      gateDismissed: false,
      bibleProposal: null,
      outlineProposal: null,
      bibleChatDone: null,
    }),
}));
