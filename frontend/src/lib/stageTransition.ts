/**
 * When the Stage opens itself, and when it folds away.
 *
 * Max's ruling of 2026-09-02 (docs/PHASES.md, "The Stage"): **C, the detached
 * window, while a run launches and works; D, the inline row, when it is done —
 * still expandable back into C; A, the split, as the minimised in-between.**
 * The invariant that comes with it is the one this file exists to keep: when a
 * run finishes, the window's content folds into the transcript row where the
 * result landed and the window goes, so there are never two records of one
 * thing.
 *
 * Lifted out of `App.tsx`, where it was three closures nothing could test. It
 * is a pure function of the transcript because the transcript IS the record: a
 * run's state is the engine's own count of its own events (`lib/transcript.ts`
 * folds them), so asking the rows is asking the engine. A timer here would be
 * this interface guessing about work it can already see.
 */

import type { TranscriptItem } from './transcript';

/** A `train.*` kind that means the job is over. Matched rather than listed
 *  because the recipes emit their own terminal names; a kind this misses
 *  leaves a run counted as spending, which shows a window nobody needed —
 *  the harmless direction of the two. */
const TERMINAL = /finished|failed|done|complete|cancel|interrupt/i;

export interface StageMoveInput {
  items: TranscriptItem[];
  /** Run rows that have already opened the window once in this thread. A run
   *  is only a reason to open it the first time it is seen spending. */
  seen: ReadonlySet<string>;
  windowOpen: boolean;
}

export type StageMove =
  | { kind: 'none' }
  | { kind: 'open-window'; started: string[] }
  | { kind: 'fold-into-row'; anchor: string };

/**
 * The keys of every run row still spending — a `train` row whose latest event
 * is not terminal, an `eval` row still `running`.
 *
 * `reused` is not spending and that is the whole point of the state: the eval
 * bench answers an identical run out of its own tables and nothing is paid
 * for, so a window announcing work would be announcing none.
 */
export function spendingRows(items: TranscriptItem[]): string[] {
  const keys: string[] = [];
  for (const item of items) {
    if (item.kind === 'eval' && item.state === 'running') keys.push(item.key);
    if (item.kind === 'train' && !TERMINAL.test(item.latest?.kind ?? '')) keys.push(item.key);
  }
  return keys;
}

/**
 * The last row a person would look at for the result: the newest finished run
 * row, or a completed tool row below it — `score_the_adapter`'s reply lands
 * after the run row it describes, and that reply is what the Stage draws.
 */
export function foldAnchor(items: TranscriptItem[]): string | null {
  for (let i = items.length - 1; i >= 0; i -= 1) {
    const item = items[i];
    if (item.kind === 'tool' && item.state !== 'running') return item.key;
    if (item.kind === 'eval' && item.state !== 'running') return item.key;
    if (item.kind === 'train' && TERMINAL.test(item.latest?.kind ?? '')) return item.key;
  }
  return null;
}

/**
 * What the Stage should do about this transcript, once.
 *
 * ORDER MATTERS AND IT IS THE ONE JUDGEMENT HERE. A run finishing in the same
 * frame as another starting is common — a training run ends and its scoring
 * run begins — and folding first would close a window the very next evaluation
 * of this function has to reopen, which reads on screen as a flicker and in
 * the log as two windows. So a fresh spending run wins over a fold.
 *
 * A window with nothing in `seen` was opened by the person. It is never folded
 * away: taking back a view somebody asked for is not this rule's business.
 */
export function nextStageMove({ items, seen, windowOpen }: StageMoveInput): StageMove {
  const spending = spendingRows(items);
  const started = spending.filter((key) => !seen.has(key));
  if (started.length > 0) return { kind: 'open-window', started };
  if (spending.length > 0) return { kind: 'none' };
  if (!windowOpen || seen.size === 0) return { kind: 'none' };
  const anchor = foldAnchor(items);
  return anchor === null ? { kind: 'none' } : { kind: 'fold-into-row', anchor };
}
