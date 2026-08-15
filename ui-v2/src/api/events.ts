import { useEffect } from "react";
import { api } from "./client";
import type { JobInfo, ProjectStatus, SseEvent } from "./types";
import { useEvents } from "../stores/events";

export function useProjectEvents(project: string | undefined): void {
  const apply = useEvents((s) => s.apply);
  const setConnected = useEvents((s) => s.setConnected);

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
          for (const g of job.gates) {
            useEvents.getState().apply({
              type: "gate",
              gate_id: g.id,
              label: g.label,
              artifact: "",
              job_id: job.id,
            } as SseEvent);
          }
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
          apply(JSON.parse(m.data) as SseEvent);
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
  }, [project, apply, setConnected]);
}
