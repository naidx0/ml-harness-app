/**
 * A GATE NOBODY HAS LOOKED AT IS NOT A GATE YOU FAILED.
 *
 * Max, reading the diagnosis on a thread where he had measured nothing: *"it
 * fails really loud on this check and goes all in on it."* Every gate on a
 * fresh thread is BLOCKED, and blocked drew `--wont` red with an alert icon -
 * a column of red telling somebody who has not started that something is
 * wrong.
 *
 * The argument for the fix was already in `DiagnosisCard.tsx`, written for the
 * other end of the ledger: page 23.8 rule 3 keeps not-reached grey "because red
 * would claim the harness tested it and found it wanting".
 *
 * What these hold is the LINE between the two, because the easy version of this
 * change - grey whenever nothing in the thread was measured - would also grey
 * out a gate that really is blocked on a reading that exists and disagrees, and
 * that reading is the most important red in the product.
 */

import { describe, expect, it } from 'vitest';

import { LOOK, rowState } from './DiagnosisCard';
import type { GateLedgerEntry } from '../lib/engine/facts';

function gate(over: Partial<GateLedgerEntry> = {}): GateLedgerEntry {
  return {
    node: 'S0_NO_EVAL_SET',
    status: 'FAILED',
    clause: 'eval_size_n >= 20',
    unsubstantiated: [],
    ...over,
  } as GateLedgerEntry;
}

const NOTHING: Record<string, string> = {};
const MEASURED = { eval_size_n: 'MEASURED' };
const ASSERTED = { eval_size_n: 'ASSERTED' };

describe('the untouched gate', () => {
  it('reads as a step not taken when no fact it names is known', () => {
    expect(rowState(gate(), NOTHING)).toBe('not-started');
  });

  it('is grey, and says so in a word a person has not failed', () => {
    expect(LOOK['not-started'].token).toBe('unknown');
    expect(LOOK['not-started'].word).toBe('not started');
    expect(LOOK['not-started'].icon).not.toBe('alert');
  });
});

describe('the line this must not cross', () => {
  it('a gate blocked on a MEASURED fact stays red', () => {
    /* THE MOST IMPORTANT RED IN THE PRODUCT: the harness read your machine or
       your file and the number does not clear the bar. */
    expect(rowState(gate(), MEASURED)).toBe('blocked');
    expect(LOOK.blocked.token).toBe('wont');
  });

  it('a gate blocked on a fact somebody merely claimed is still red', () => {
    /* An origin is an origin. The claim was made, the predicate was evaluated
       against it, and it did not hold - that is a block, not a blank. */
    expect(rowState(gate(), ASSERTED)).toBe('blocked');
  });

  it('is decided per gate, not per thread', () => {
    /* One gate measured and failing, another untouched, in the same payload. */
    const origins = { eval_size_n: 'MEASURED' };
    const measuredGate = gate({ clause: 'eval_size_n >= 20' });
    const untouchedGate = gate({ node: 'S1_NO_BASELINE', clause: 'baseline_measured' });
    expect(rowState(measuredGate, origins)).toBe('blocked');
    expect(rowState(untouchedGate, origins)).toBe('not-started');
  });
});

describe('the states it must not have swallowed', () => {
  it('passed is untouched', () => {
    expect(rowState(gate({ status: 'PASSED' }), NOTHING)).toBe('passed');
  });

  it('not-reached is untouched, and is a different thing', () => {
    /* Not reached: the walk stopped before here. Not started: the walk asked,
       and nothing had been read. Both grey, both true, not the same sentence. */
    expect(rowState(gate({ status: 'NOT_REACHED' }), NOTHING)).toBe('not-reached');
    expect(rowState(undefined, NOTHING)).toBe('not-reached');
  });

  it('unsubstantiated still wins over not-started', () => {
    /* A gate whose predicate HELD on facts that were only claimed is the row a
       person can close. That is a live invitation and must not be softened
       into "nothing happened here". */
    const claimed = gate({ unsubstantiated: [{ fact: 'eval_size_n' }] as never });
    expect(rowState(claimed, NOTHING)).toBe('unsubstantiated');
  });

  it('a gate with no clause at all is not called not-started', () => {
    /* An empty fact list then means "there was no condition to read", which is
       a different absence and not one this state should claim. */
    expect(rowState(gate({ clause: null }), NOTHING)).toBe('blocked');
  });
});

describe('every state is still drawable', () => {
  it('has a look with a token, an icon and a word', () => {
    for (const state of ['passed', 'blocked', 'not-started', 'unsubstantiated', 'not-reached'] as const) {
      expect(LOOK[state].token.length).toBeGreaterThan(0);
      expect(LOOK[state].icon.length).toBeGreaterThan(0);
      expect(LOOK[state].word.length).toBeGreaterThan(0);
    }
  });

  it('only a real block is red', () => {
    const red = Object.entries(LOOK).filter(([, look]) => look.token === 'wont');
    expect(red.map(([state]) => state)).toEqual(['blocked']);
  });
});
