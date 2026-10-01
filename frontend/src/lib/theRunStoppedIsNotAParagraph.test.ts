import { describe, expect, it } from 'vitest';

import { foldEvents } from './transcript';
import type { EngineEvent } from './engine/types';

/**
 * SEVEN PARKED STEPS ARE A LIST, NOT A SENTENCE.
 *
 * `run.finished` joined every parked step - each one a full instruction with
 * its tool call and arguments - into one parenthesis after the stop reason.
 * Max photographed the result and called it "this infinite kind of text
 * thing": eleven lines of unbroken grey where a count and five bullets would
 * have done.
 *
 * And the stop reason inside it said "Nothing was parked" while the summary
 * beside it said "7 parked". One of the two was wrong and it was the reason:
 * the branch is about THIS STEP, the summary is about the run.
 */

let next = 1;
const event = (kind: string, payload: Record<string, unknown> = {}): EngineEvent =>
  ({ id: next++, kind, payload }) as unknown as EngineEvent;

const seven = Array.from({ length: 7 }, (_, i) => ({
  step: `Step number ${i} with \`some_tool\` - kind = train, config = lora_r=16, lora_alpha=32`,
  why: 'a reason',
}));

describe('the run.finished row', () => {
  it('counts the parked steps in the reason and lists them separately', () => {
    const [row] = foldEvents([
      event('run.finished', { reason: 'r', detail: 'it stopped.', turns: 9, done: 7, parked: seven }),
    ]);
    expect(row.kind).toBe('notice');
    if (row.kind !== 'notice') return;
    expect(row.reason).toContain('7 parked');
    /* The step texts are no longer spliced into the sentence. */
    expect(row.reason).not.toContain('Step number 0');
    expect(row.points).toHaveLength(7);
  });

  it('keeps each line to the step, not its arguments', () => {
    const [row] = foldEvents([event('run.finished', { parked: seven })]);
    if (row.kind !== 'notice') return;
    expect(row.points?.[0]).toBe('Step number 0 with `some_tool`');
    expect(row.points?.[0]).not.toContain('lora_r');
  });

  it('carries no points at all when nothing was parked', () => {
    const [row] = foldEvents([event('run.finished', { turns: 2, done: 2, parked: [] })]);
    if (row.kind !== 'notice') return;
    expect(row.points).toEqual([]);
    expect(row.reason).not.toContain('parked');
  });
});
