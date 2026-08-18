import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { JobInfo, ProjectStatus, SseEvent } from "./types";
import { useEvents } from "../stores/events";
import { describe } from "../describe";

export function useProjectEvents(project: string | undefined): void {
  const apply = useEvents((s) => s.apply);
  const setConnected = useEvents((s) => s.setConnected);
  const pushLine = useEvents((s) => s.pushLine);
  const qc = useQueryClient();

  useEffect(() => {
    if (!project) return;
    const store = useEvents.getState();
    store.reset();
    let es: EventSource | null = null;
    let stopped = false;
    let retry: ReturnType<typeof setTimeout> | null = null;

    async function reconcile() {
      // R3: after a reconnect, distrust local state; re-read facts first
      try {
        const status = await api<ProjectStatus>(`/api/projects/${project}/status`);
        if (status.job) {
          const job = await api<JobInfo>(`/api/jobs/${status.job.id}`);
          // Drop any locally-held gate first: it may have been resolved while
          // disconnected (another tab) — re-resolving it would 404. Pending
          // gates from the server are re-applied right after.
          useEvents.setState({ gate: null });
          for (const g of job.gates) {
            useEvents.getState().apply({
              type: "gate",
              gate_id: g.id,
              label: g.label,
              // full artifact so the re-opened GateModal shows the content to approve
              artifact: g.artifact ?? "",
              job_id: job.id,
            } as SseEvent);
          }
        } else {
          // Job died while disconnected (e.g. server restart): drop stale
          // transient state — a pending gate would otherwise keep the
          // GateModal stuck open, and resolving it would 404. Keep log lines.
          useEvents.getState().resetTransient();
        }
      } catch {
        /* next reconnect will retry */
      }
    }

    function connect() {
      if (stopped) return;
      es = new EventSource(`/api/projects/${project}/events`);
      es.onopen = () => {
        setConnected(true);
        void reconcile();
      };
      es.onmessage = (m) => {
        try {
          const ev = JSON.parse(m.data) as SseEvent;
          apply(ev);
          const text = describe(ev);
          if (text) pushLine(text);
          // Facts changed server-side — let /status queries refetch so pages
          // deriving state from the booleans (e.g. Setup's Steps) update live.
          if (ev.type === "premise_done" || ev.type === "setup_stage" || ev.type === "job_end") {
            void qc.invalidateQueries({ queryKey: ["status"] });
          }
          if (ev.type === "bible_applied" || ev.type === "outline_extended" ||
              ev.type === "rewrite_applied" || ev.type === "rewrite_done" ||
              ev.type === "job_end") {
            void qc.invalidateQueries({ queryKey: ["bible"] });
          }
          if (ev.type === "outline_extended" || ev.type === "rewrite_applied" ||
              ev.type === "rewrite_done" || ev.type === "job_end") {
            void qc.invalidateQueries({ queryKey: ["outline"] });
            void qc.invalidateQueries({ queryKey: ["chapters"] });
            void qc.invalidateQueries({ queryKey: ["status"] });
          }
          if (ev.type === "tts_done") {
            void qc.invalidateQueries({ queryKey: ["audio"] });
          }
        } catch {
          /* ignore */
        }
      };
      es.onerror = () => {
        setConnected(false);
        es?.close();
        if (!stopped) retry = setTimeout(connect, 2000);
      };
    }
    connect();
    return () => {
      stopped = true;
      if (retry) clearTimeout(retry);
      es?.close();
      setConnected(false);
    };
  }, [project, apply, setConnected, pushLine, qc]);
}
