export interface ProjectStatus {
  name: string;
  has_concept: boolean;
  has_world: boolean;
  has_outline: boolean;
  chapters: number[];
  open_threads: number;
  score_min: number;
  job: { id: string; kind: string; status: string; error: string | null } | null;
}
export interface ReviewRecord {
  chapter: number;
  attempt: number;
  artifact_type: string;
  overall: number;
  summary: string;
  passed: boolean;
  timestamp: string;
  scores: Record<string, { score: number; critique: string }>;
}
export interface Thread {
  id: string;
  description: string;
  status: string;
}
export interface JobInfo {
  id: string;
  kind: string;
  status: string;
  error: string | null;
  project: string;
  gates: { id: string; label: string }[];
}
export interface OutlineInfo {
  arcs: { arc_name: string; chapters: { chapter_no: number; chapter_title: string }[] }[];
}
export type SseEvent = Record<string, unknown> & { type: string; job_id?: string };
