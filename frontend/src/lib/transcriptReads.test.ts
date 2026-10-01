/**
 * Reading results back out of the transcript, for surfaces that draw them.
 *
 * The Stage's Retrieval panel draws a recall report and a carve, and neither
 * is in the Stage's own payload: no table stores a recall score — the number
 * lives in the tool's reply, which lives in the event log, which the
 * transcript already folds. So the panel reads the transcript, the same way
 * `App.tsx` reads eval reports and diagnoses out of it.
 *
 * These two helpers were private to `App.tsx`, which is why the DETACHED
 * window shipped with `recall={null}`: it never mounts `App`, so its Retrieval
 * panel said "no retriever scored in this thread yet" about a thread that
 * scored three. Same surface, same thread, two different answers depending on
 * which size you were looking at.
 */

import { describe, expect, it } from 'vitest';

import type { TranscriptItem } from './transcript';
import { allReadsOf, latestReadOf } from './transcriptReads';

interface Marked {
  mark: string;
}

/** A reader in this codebase's own idiom: it keys on a field no other tool
 *  returns, and answers `null` for everything else. */
function readMarked(value: unknown): Marked | null {
  if (typeof value !== 'object' || value === null) return null;
  const mark = (value as { mark?: unknown }).mark;
  return typeof mark === 'string' ? { mark } : null;
}

function tool(key: string, result: unknown): TranscriptItem {
  return { kind: 'tool', key, id: 1, name: 't', args: {}, state: 'ok', result } as unknown as TranscriptItem;
}

function user(key: string): TranscriptItem {
  return { kind: 'user', key, id: 2, content: 'hello' } as unknown as TranscriptItem;
}

const THREAD: TranscriptItem[] = [
  tool('a', { mark: 'first' }),
  user('u1'),
  tool('b', { somethingElse: true }),
  tool('c', { mark: 'second' }),
  user('u2'),
  tool('d', { mark: 'third' }),
];

describe('every result a reader accepts', () => {
  it('comes back newest first, so a picker can default to the last one', () => {
    expect(allReadsOf(THREAD, readMarked)).toEqual([
      { mark: 'third' },
      { mark: 'second' },
      { mark: 'first' },
    ]);
  });

  it('skips rows that are not tools and results the reader refuses', () => {
    expect(allReadsOf([user('u1'), tool('b', { somethingElse: true })], readMarked)).toEqual([]);
  });

  it('is empty for an empty transcript rather than throwing', () => {
    expect(allReadsOf([], readMarked)).toEqual([]);
  });
});

describe('the newest result a reader accepts', () => {
  it('is the last one in the thread, not the first', () => {
    expect(latestReadOf(THREAD, readMarked)).toEqual({ mark: 'third' });
  });

  it('is null when nothing in the thread is one', () => {
    expect(latestReadOf([user('u1')], readMarked)).toBeNull();
  });

  it('agrees with the head of the full list, always', () => {
    /* The two helpers must not be able to disagree about which is newest -
       one surface uses each, and a picker whose default differs from the
       single-value reader is two answers to one question. */
    expect(latestReadOf(THREAD, readMarked)).toEqual(allReadsOf(THREAD, readMarked)[0]);
  });
});
