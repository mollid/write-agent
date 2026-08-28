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
/** Secret-free subset of project.config.yaml (models/api_key never included). */
export interface ProjectConfig {
  target_chapters: number | null;
  arc_detail_lookahead: number;
  chapter_target_length: number;
  context_token_budget: number;
  human_gate_every_n_chapters: number;
  score_min: number;
  max_retries: number;
  language: string;
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
  gates: { id: string; label: string; artifact: string }[];
}
export interface OutlineInfo {
  arcs: { arc_name: string; chapters: { chapter_no: number; chapter_title: string }[] }[];
}
export interface ConceptData {
  logline: string; genre: string; tone: string; themes: string[];
  target_length_words: number; audience: string;
}
export interface WorldData {
  setting: string; era: string; rules: string[]; power_system: string;
  factions: { name: string; ideology: string; resources: string; conflict_with: string }[];
  locations: { name: string; description: string; narrative_function: string }[];
  constraints: string[];
}
export interface CharacterStateData {
  emotional_state: string; physical_state: string; knowledge_gained: string[];
  relationships_shifted: Record<string, string>; location_end: string;
}
export interface CharacterData {
  id: string; slug: string; name: string; role: string; backstory: string;
  motivation: string; arc: string; voice_fingerprint: Record<string, string>;
  mannerisms: { text: string; used_count: number }[]; description_history: string[];
  relationships: Record<string, string>; state: CharacterStateData;
}
export interface BeatData {
  beat_id: string; pov: string; setting: string; event: string; emotional_turn: string;
  characters: string[]; plants: string[]; payoffs: string[];
}
export interface OutlineChapterData {
  chapter_no: number; chapter_title: string; beats: BeatData[];
}
export interface OutlineFullData {
  arcs: { arc_name: string; chapters: OutlineChapterData[] }[];
  foreshadow_ledger: { id: string; planted_in: string; paid_off_in: string; description: string }[];
}
export interface ForeshadowData {
  id: string; description: string; planted_ch: number | null;
  payoff_ch: number | null; status: string;
}
export interface EventData { id: string; chapter: number; characters: string[]; summary: string }
export interface AudioInfo {
  chapter: number;
  size: number;
}
export interface BibleData {
  concept: ConceptData | null; world: WorldData | null; characters: CharacterData[];
  outline: OutlineFullData | null; foreshadows: ForeshadowData[];
  events: EventData[];
}
export type SseEvent = Record<string, unknown> & { type: string; job_id?: string };
