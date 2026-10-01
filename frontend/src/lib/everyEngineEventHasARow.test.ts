import { describe, expect, it } from 'vitest';

import { foldEvents } from './transcript';
import type { EngineEvent } from './engine/types';

/**
 * A ROW, OR A REASON. The transcript's fallback prints "The engine sent a
 * <kind> event, which this surface has no row for yet" - deliberately, so that
 * silencing a kind is a decision somebody argued rather than a frame that
 * vanished. Two kinds were living in that fallback and neither had been
 * argued.
 *
 * Max, 2026-09-20, reading his own run: "this is also very confusing i dont
 * quite understand what this is runing for and whats happening?" - over a
 * transcript whose first line was the placeholder for `thread.permission` and
 * which carried eleven more for `observation.packed`, in between the rows that
 * were about his data.
 *
 * They go different ways, and the difference is the point. Setting the
 * autonomy ladder is a thing the PERSON did and it changes what runs without
 * asking, so it draws. How a large result is CARRIED is a fact about the
 * context window - `turn.context`'s argument exactly - so it does not.
 */

let next = 1;
const event = (kind: string, payload: Record<string, unknown> = {}): EngineEvent =>
  ({ id: next++, kind, payload }) as unknown as EngineEvent;

describe('the two kinds that were living in the fallback', () => {
  it('draws the autonomy ladder as the person s own choice', () => {
    const [row] = foldEvents([event('thread.permission', { id: 7, permission: 'full' })]);
    expect(row.kind).toBe('notice');
    expect(row.kind === 'notice' && row.text).toBe('Approvals set to Full.');
    expect(row.kind === 'notice' && row.reason).toContain('without asking');
  });

  it('names each rung, and never leaves one unnamed', () => {
    const said = ['ask', 'measure', 'write', 'full'].map((rung) => {
      const [row] = foldEvents([event('thread.permission', { permission: rung })]);
      return row.kind === 'notice' ? row.text : '';
    });
    expect(said).toEqual([
      'Approvals set to Ask.',
      'Approvals set to Measure.',
      'Approvals set to Write.',
      'Approvals set to Full.',
    ]);
  });

  it('draws nothing at all for how a result is carried', () => {
    const items = foldEvents([
      event('observation.packed', { handle: 'obs:18692', name: 'what_is_missing', chars: 34081 }),
    ]);
    expect(items).toEqual([]);
  });

  it('still falls back loudly for a kind nobody has considered', () => {
    /* The fallback is the feature. If this ever goes quiet, the argument
       above stopped being a decision and became a default. */
    const [row] = foldEvents([event('something.nobody.wrote.yet')]);
    expect(row.kind).toBe('unknown');
  });
});
