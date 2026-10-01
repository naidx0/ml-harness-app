/**
 * What a thread's transcript says about its diagnosis and its eval runs.
 *
 * Two folds over the durable event log, shared by the shell (`App.tsx`) and
 * the pane window (`components/PaneWindow.tsx`), which follows the same
 * thread from its own window and must draw the same verdict and the same
 * runs. One reader, two windows, no disagreement.
 */

import { readEvalReport, type EvalReport } from './engine/evals';
import { readDiagnosis, type DiagnosisPayload } from './engine/facts';
import type { TranscriptItem } from './transcript';

/**
 * The newest diagnosis the thread has reached, or null before one has run.
 *
 * A fold over the durable event log rather than a piece of React state, for
 * the same reason the transcript itself is one: the thread survives a restart,
 * a closed laptop and a crashed engine, and a verdict held in memory would not.
 * Reading backwards means the newest answer wins without sorting.
 *
 * A `run_diagnosis` that FAILED is skipped rather than shown as a diagnosis
 * with holes in it — `readDiagnosis` refuses a payload without an outcome and a
 * gate ledger, and a ledger with a missing row is a promise with a missing
 * piece.
 */
export function latestDiagnosis(items: TranscriptItem[]): DiagnosisPayload | null {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    const item = items[index];
    if (item.kind !== 'tool' || item.state !== 'ok') continue;
    const parsed = readDiagnosis(item.result);
    if (parsed) return parsed;
  }
  return null;
}

/**
 * Every eval run this thread has read back, newest first.
 *
 * The same fold over the durable event log as `latestDiagnosis`, and for the
 * same reason: the transcript is the artifact, so an eval read before a restart
 * is an eval the pane can still draw, and one held in a React ref would not be.
 *
 * DE-DUPLICATED BY RUN ID, NEWEST WINS. One run reaches this list from more
 * than one place — `run_eval` returns the report when the run finishes, and
 * every later `read_eval_results` returns it again, with a different `failures`
 * cut. Without the de-duplication the picker shows run 4 five times. Reading
 * backwards means the first sighting of an id is the freshest reading of it,
 * which is the one to keep.
 */
export function evalReportsIn(items: TranscriptItem[]): EvalReport[] {
  const seen = new Set<number>();
  const out: EvalReport[] = [];
  for (let index = items.length - 1; index >= 0; index -= 1) {
    const item = items[index];
    if (item.kind !== 'tool' || item.state !== 'ok') continue;
    const parsed = readEvalReport(item.result);
    if (!parsed || seen.has(parsed.runId)) continue;
    seen.add(parsed.runId);
    out.push(parsed);
  }
  return out;
}
