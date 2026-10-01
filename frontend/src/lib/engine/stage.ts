/**
 * The Stage's one read: `GET /api/threads/{id}/stage` — `app/stage.py::build`.
 *
 * The Stage is a second READER of what a thread measured, never a second
 * writer. Everything its five panels draw arrives in this one payload, joined
 * by the engine off the same tables the tools wrote through, so nothing here is
 * computed twice and nothing is filed into the transcript by reading it.
 *
 * Field names are the engine's own (snake_case), kept verbatim rather than
 * camel-cased at the boundary: every number on the Stage is quoted with its
 * run id and its provenance, and a renamed field is one more place for the
 * two to drift apart.
 */

import { engineJson } from './client';

export interface StageRow {
  row_index: number;
  correct: boolean;
  failure_mode: string | null;
  bucketed_by: string | null;
}

export interface StageRun {
  run_id: number;
  complete: boolean;
  reused: boolean;
  eval_path: string;
  eval_fingerprint: string | null;
  metric: string;
  prompt: string;
  prompt_is_default: boolean;
  provider: string | null;
  model: string | null;
  locality: string | null;
  judge_model: string | null;
  planned: number;
  graded: number;
  correct: number;
  score: number | null;
  partial_score: number | null;
  scores: Record<string, number>;
  trivial_baseline_score: number | null;
  resolution: {
    n: number;
    ci_95: [number, number];
    half_width_points: number;
    resolves_a_difference_of_at_least_points: number;
    rows_for_a_10_point_difference: number;
    says: string;
  } | null;
  failure_histogram: Record<string, number>;
  self_graded: { judge: string } | Record<string, unknown> | null;
  summary: string | null;
  rows: StageRow[];
}

export interface StageComparison {
  run_id: number;
  against: number;
  paired_rows: number;
  same_rows: boolean;
  score: number;
  score_against: number;
  delta: number;
  correct: number;
  correct_against: number;
  improved: number;
  regressed: number;
  changed: number;
  p_value: number;
  test: string;
  resolved: boolean;
  verdict: 'different' | 'no_evidence' | string;
  rows_that_would_resolve_this_delta: number | null;
  improved_rows: number[];
  regressed_rows: number[];
  measured_on: string;
}

export interface StageSandboxRun {
  name: string;
  kind: string | null;
  recipe: string | null;
  base_model: string | null;
  max_steps: number | null;
  steps: number | null;
  elapsed_seconds: number | null;
  peak_vram_gb: number | null;
  final_loss: number | null;
  adapter_dir: string | null;
  curve: Array<{ step: number; loss: number }>;
  events: number;
  has_adapter: boolean;
  has_predictions: boolean;
}

export interface StageSandbox {
  ok?: boolean;
  name: string;
  purpose?: string;
  path?: string;
  runs_dir?: string;
  created_at?: string;
  snapshotted?: Array<{ path: string; bytes: number; digest: string; copied_to?: string }>;
  snapshot_bytes?: number;
  pinned?: { recipe?: string; interpreter?: string; pinned?: boolean; on_disk_gb?: number; installs?: string[] };
  reach?: { egress: boolean; egress_reason?: string; enforced?: string[] };
  runs: StageSandboxRun[];
  [key: string]: unknown;
}

export interface StageGpu {
  occupancy: {
    used_gb: number;
    total_gb: number;
    resident: Array<{ name: string; size_gb: number }>;
    source: string;
  } | null;
  guard: string | null;
  crowded_above_gb: number;
}

export interface StagePayload {
  thread_id: number;
  project_id: number | null;
  baseline_run_id: number | null;
  runs: StageRun[];
  comparisons: Record<string, StageComparison>;
  sandboxes: StageSandbox[];
  gpu: StageGpu;
  /** `journey_report.build` — verdict, gate ledger, facts with origins. Null
   *  when the thread has no diagnosis yet. */
  diagnosis: Record<string, unknown> | null;
  reads: Record<string, string>;
}

/** `GET /api/threads/{id}/stage`. Bearer, JSON, writes nothing. */
export function getStage(threadId: number): Promise<StagePayload> {
  return engineJson<StagePayload>(`/api/threads/${threadId}/stage`);
}

/** A run's one-word label for a column head: what changed, not the prompt. */
export function runLabel(run: StageRun, baselineId: number | null): string {
  if (run.run_id === baselineId) return 'baseline';
  const model = run.model ?? '';
  if (/adapter/i.test(model)) return 'adapter';
  if (/adapter disabled|\(base\)|bare/i.test(model)) return 'bare base';
  if (run.prompt_is_default) return 'default prompt';
  return 'prompt';
}
