/**
 * Reading tool results back out of a folded transcript.
 *
 * Some of what a surface draws is not in any table. A recall score is the
 * clearest case: `measure_retriever_recall` computes it, the reply carries it,
 * and nothing stores it — so the only durable record is the event log, which
 * `foldEvents` turns back into rows. Reading it here is not a shortcut around
 * the engine; it IS the record, the same one the transcript renders.
 *
 * Both helpers take a READER — one of the `readX(value): X | null` functions in
 * `lib/engine/*`, each keyed on fields no other tool returns — so nothing here
 * has to know which tool produced a row. That is the same contract the
 * transcript itself uses to decide which card to draw.
 *
 * They live in their own module rather than inside `App.tsx` because a second
 * surface needs them and could not reach them: the Stage's detached window
 * never mounts `App`, and so it shipped drawing "no retriever scored in this
 * thread yet" about a thread that had scored three.
 */

import type { TranscriptItem } from './transcript';

/**
 * Every result in the thread the reader accepts, **newest first**.
 *
 * Newest first because the surfaces that take a list offer a picker, and the
 * one it defaults to should be the last thing that happened.
 */
export function allReadsOf<T>(
  items: readonly TranscriptItem[],
  read: (value: unknown) => T | null,
): T[] {
  const out: T[] = [];
  for (let i = items.length - 1; i >= 0; i -= 1) {
    const item = items[i];
    if (item.kind !== 'tool') continue;
    const found = read(item.result);
    if (found !== null) out.push(found);
  }
  return out;
}

/** The newest result the reader accepts, or null. Always `allReadsOf(...)[0]` —
 *  two surfaces use one each, and a picker whose default disagreed with the
 *  single-value reader would be two answers to one question. */
export function latestReadOf<T>(
  items: readonly TranscriptItem[],
  read: (value: unknown) => T | null,
): T | null {
  for (let i = items.length - 1; i >= 0; i -= 1) {
    const item = items[i];
    if (item.kind !== 'tool') continue;
    const found = read(item.result);
    if (found !== null) return found;
  }
  return null;
}
