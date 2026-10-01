/**
 * `GET /api/activity` - which conversations are working right now.
 *
 * Its own module rather than another export of `client.ts` for the reason
 * `journey.ts` and `retrieval.ts` are their own: one route, one shape, one
 * place to read when the shape changes.
 */

import { engineJson } from './client';

export interface ActivityThread {
  thread_id: number;
  /** A turn began and has not ended. Read off the event log, so it is true
   *  for work another window started (`app/activity.py`). */
  working: boolean;
  /** The long run on this thread while it is taking turns, else null. */
  run: { state: string; turns: number; cap: number; stop_reason: string } | null;
  /** What its last prompt cost, and the model's window, when either is known. */
  tokens: number | null;
  window: number | null;
}

export interface ActivityRead {
  threads: ActivityThread[];
  count: number;
}

export function readActivity(): Promise<ActivityRead> {
  return engineJson('/api/activity');
}
