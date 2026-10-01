/**
 * `GET /api/threads/{id}/subagents` - the phases this conversation handed out.
 *
 * Its own module for the reason `activity.ts` is: one route, one shape, one
 * place to change. The engine's argument for the whole feature is in
 * `app/subagents.py`; what reaches the page is the counts and the endings, and
 * deliberately never a child's transcript - a person who wants that opens the
 * child, which is a real conversation in the rail.
 */

import { engineJson } from './client';

export interface SubAgent {
  id: number;
  /** The child conversation. Opening it is how a person reads the work. */
  thread_id: number;
  phase: string;
  /** `running`, `done`, `failed` or `stopped`. */
  state: string;
  reason: string;
  detail: string;
  harvested: boolean;
  turns: number;
  seconds: number | null;
  steps: number;
  done: number;
  open: number;
  parked: { step: string; why: string }[];
  /** CS4 — packs this worker's turn loads. */
  packs?: string[];
  /** The plan the phase was handed out with - the child's own instructions. */
  brief?: string;
  /** Read off the child's event log by `subagents.work_of`. */
  tools_run?: number;
  tools_failed?: number;
  tools_distinct?: number;
  tool_names?: { name: string; times: number }[];
  context_peak_tokens?: number;
  /** CS4 — last harvest paragraph, empty while running. */
  last_digest?: string;
  started_at: string;
  updated_at: string;
}

export interface SubAgentRead {
  thread_id: number;
  subagents: SubAgent[];
  /** Working for THIS conversation. */
  running: number;
  /** Working anywhere - the cap is on the machine, not the conversation. */
  running_anywhere: number;
  at_most: number;
}

export const NONE: SubAgentRead = {
  thread_id: 0,
  subagents: [],
  running: 0,
  running_anywhere: 0,
  at_most: 2,
};

export function readSubAgents(threadId: number): Promise<SubAgentRead> {
  return engineJson(`/api/threads/${threadId}/subagents`);
}

export function stopSubAgent(id: number): Promise<unknown> {
  return engineJson(`/api/subagents/${id}/stop`, { method: 'POST' });
}
