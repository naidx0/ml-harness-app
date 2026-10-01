import { describe, expect, it } from 'vitest';

import {
  A_RUN_WORTH_FOLDING,
  howToDrawEachRow,
  toolRunsIn,
  type Row,
} from './foldTheToolRows';

/**
 * THE EXCEPTION IS THE FEATURE.
 *
 * Max asked for tool calls to condense "apart from question asks and diagnosis
 * and so on". Everything here is about that "apart from": a run of plain rows
 * folds, and a row that draws something breaks the run rather than joining it.
 * Folding a diagnosis into an icon would put the most important surface in the
 * product behind a click, which is the opposite of the ask.
 */

const rows = (kinds: string[]): Row[] => kinds.map((kind) => ({ kind }));

/** Everything is plain unless its index is listed. */
const plainExcept = (cards: number[]) => (index: number) => !cards.includes(index);

describe('what folds', () => {
  it('folds a run of plain tool rows', () => {
    const items = rows(['user', 'tool', 'tool', 'tool', 'assistant']);
    expect(toolRunsIn(items, plainExcept([]))).toEqual([[1, 2, 3]]);
  });

  it('leaves a lone tool row alone', () => {
    /* A strip over one line is more to click and less to read. */
    const items = rows(['user', 'tool', 'assistant']);
    expect(toolRunsIn(items, plainExcept([]))).toEqual([]);
  });

  it('folds at exactly two, which is the stated threshold', () => {
    expect(A_RUN_WORTH_FOLDING).toBe(2);
    expect(toolRunsIn(rows(['tool', 'tool']), plainExcept([]))).toEqual([[0, 1]]);
  });

  it('finds every run, not just the first', () => {
    const items = rows(['tool', 'tool', 'assistant', 'tool', 'tool', 'tool']);
    expect(toolRunsIn(items, plainExcept([]))).toEqual([
      [0, 1],
      [3, 4, 5],
    ]);
  });
});

describe('what breaks a run', () => {
  it('a row that draws a card is never folded', () => {
    /* Index 2 is a diagnosis. It must render as itself. */
    const items = rows(['tool', 'tool', 'tool', 'tool', 'tool']);
    expect(toolRunsIn(items, plainExcept([2]))).toEqual([
      [0, 1],
      [3, 4],
    ]);
  });

  it('a card in the middle leaves neither side short enough to fold', () => {
    const items = rows(['tool', 'tool', 'tool']);
    expect(toolRunsIn(items, plainExcept([1]))).toEqual([]);
  });

  it('anything that is not a tool row breaks the run', () => {
    for (const between of ['assistant', 'user', 'verdict', 'error', 'notice']) {
      const items = rows(['tool', 'tool', between, 'tool', 'tool']);
      expect(toolRunsIn(items, plainExcept([])).length).toBe(2);
    }
  });

  it('an empty transcript folds nothing', () => {
    expect(toolRunsIn([], plainExcept([]))).toEqual([]);
  });
});

describe('what each index is told to do', () => {
  it('marks the first of a run as the one that draws the strip', () => {
    const items = rows(['user', 'tool', 'tool', 'tool']);
    const how = howToDrawEachRow(items, plainExcept([]));
    expect(how.get(1)?.leads).toBe(true);
    expect(how.get(2)?.leads).toBe(false);
    expect(how.get(3)?.leads).toBe(false);
  });

  it('says nothing about a row that renders normally', () => {
    /* `undefined` is the signal to draw the row exactly as before, so a
       transcript with no runs behaves identically to one with no strip. */
    const items = rows(['user', 'tool', 'assistant']);
    const how = howToDrawEachRow(items, plainExcept([]));
    expect(how.get(0)).toBeUndefined();
    expect(how.get(1)).toBeUndefined();
    expect(how.get(2)).toBeUndefined();
  });

  it('hands every member of a run the same run, so a count cannot disagree', () => {
    const items = rows(['tool', 'tool', 'tool']);
    const how = howToDrawEachRow(items, plainExcept([]));
    expect(how.get(0)?.run).toEqual([0, 1, 2]);
    expect(how.get(2)?.run).toEqual([0, 1, 2]);
  });
});
