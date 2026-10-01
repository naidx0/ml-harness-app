/**
 * Max's ruling of 2026-09-02, as a test: C while it launches and works, D when
 * it is done — and never two records of one thing.
 *
 * The rule was wired into `App.tsx` when the Stage landed and nothing checked
 * it, which is the half of a decision that decays. These are the four moments
 * it has to get right, each one a state of the transcript rather than a clock:
 *
 *   nothing spending, nothing seen   → do nothing
 *   a run starts spending            → open the window, once
 *   it is still spending             → do nothing (never a second window)
 *   the last spending run finishes   → close the window, unfold the row where
 *                                      the result landed
 *
 * The transcript is the input because the transcript is the record: a run's
 * state is the engine's own count of its events, and a timer would be this
 * interface guessing at work it can see.
 */

import { describe, expect, it } from 'vitest';

import type { TranscriptItem } from './transcript';
import { nextStageMove, spendingRows } from './stageTransition';

function evalRow(key: string, state: 'running' | 'finished' | 'reused' | 'interrupted'): TranscriptItem {
  return {
    kind: 'eval', key, id: Number(key.replace(/\D/g, '')) || 1, runId: 42,
    evalPath: 'eval.jsonl', model: 'granite', metric: 'model_graded', promptIsDefault: true,
    graded: state === 'running' ? 12 : 30, planned: 30, seconds: 4, state, score: state === 'finished' ? 0.13 : null,
    why: null,
  } as TranscriptItem;
}

function trainRow(key: string, latest: string | null): TranscriptItem {
  return {
    kind: 'train', key, id: 9, jobId: 'j1', logLines: 20,
    latest: latest === null ? null : { kind: latest, payload: {} },
  } as TranscriptItem;
}

function toolRow(key: string): TranscriptItem {
  return {
    kind: 'tool', key, id: 7, name: 'score_the_adapter', args: {}, state: 'ok', result: { ok: true },
    drivenBy: 'user',
  } as unknown as TranscriptItem;
}

describe('what counts as spending', () => {
  it('is a run the engine has not reported finished, and nothing else', () => {
    const items = [
      evalRow('eval-1', 'running'),
      evalRow('eval-2', 'finished'),
      trainRow('train-1', 'train.progress'),
      trainRow('train-2', 'train.finished'),
      toolRow('tool-1'),
    ];
    expect(spendingRows(items)).toEqual(['eval-1', 'train-1']);
  });

  it('a reused eval spent nothing, so it is not spending', () => {
    expect(spendingRows([evalRow('eval-1', 'reused')])).toEqual([]);
  });

  it('a training row with no event yet is spending: it was started', () => {
    expect(spendingRows([trainRow('train-1', null)])).toEqual(['train-1']);
  });
});

describe('C while it works, D when it is done', () => {
  it('does nothing on a thread where nothing has ever spent', () => {
    const move = nextStageMove({ items: [toolRow('tool-1')], seen: new Set(), windowOpen: false });
    expect(move.kind).toBe('none');
  });

  it('opens the window when a run starts spending, and remembers it', () => {
    const items = [trainRow('train-1', 'train.progress')];
    const move = nextStageMove({ items, seen: new Set(), windowOpen: false });
    expect(move).toEqual({ kind: 'open-window', started: ['train-1'] });
  });

  it('does not open a second window while the same run is still spending', () => {
    const items = [trainRow('train-1', 'train.progress')];
    const move = nextStageMove({ items, seen: new Set(['train-1']), windowOpen: true });
    expect(move.kind).toBe('none');
  });

  it('folds into the row where the result landed when the last run finishes', () => {
    const items = [trainRow('train-1', 'train.finished'), toolRow('tool-9')];
    const move = nextStageMove({ items, seen: new Set(['train-1']), windowOpen: true });
    expect(move).toEqual({ kind: 'fold-into-row', anchor: 'tool-9' });
  });

  it('folds under the run row itself when no result row followed it', () => {
    const items = [toolRow('tool-1'), evalRow('eval-1', 'finished')];
    const move = nextStageMove({ items, seen: new Set(['eval-1']), windowOpen: true });
    expect(move).toEqual({ kind: 'fold-into-row', anchor: 'eval-1' });
  });

  it('does not fold a window the person opened themselves', () => {
    /* `seen` empty means no run ever opened this window - it is the person's,
       and closing it because a thread has nothing running would take away a
       view they asked for. */
    const items = [toolRow('tool-1')];
    expect(nextStageMove({ items, seen: new Set(), windowOpen: true }).kind).toBe('none');
  });

  it('reopens for a second run after the first has folded away', () => {
    const items = [trainRow('train-1', 'train.finished'), trainRow('train-2', 'train.progress')];
    const move = nextStageMove({ items, seen: new Set(['train-1']), windowOpen: false });
    expect(move).toEqual({ kind: 'open-window', started: ['train-2'] });
  });

  it('opens for the new run rather than folding, when one finishes as another starts', () => {
    /* The window belongs to whatever is spending NOW. Folding first would
       close a window the next line of the same effect has to reopen. */
    const items = [trainRow('train-1', 'train.finished'), evalRow('eval-2', 'running')];
    const move = nextStageMove({ items, seen: new Set(['train-1']), windowOpen: true });
    expect(move).toEqual({ kind: 'open-window', started: ['eval-2'] });
  });
});
