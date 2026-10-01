/**
 * What a person is told about a turn that stopped when the engine did.
 *
 * FOUND ON THE RETURNING-USER WALK: ran yesterday, closed everything, came
 * back. The thread opened at "6 of 17" with its facts intact and their origins
 * and denominators unchanged, and the tab left open across the restart
 * recovered silently from the new bearer token. What was missing was the other
 * half: five threads in this database end on the person's own message with no
 * reply, one of them with seventeen thousand characters of tool output after
 * the ask, and nothing anywhere said the turn had died.
 *
 * The product already writes that sentence when it can see the failure — "the
 * connection to the model failed part way through this turn ... nothing was
 * lost". Nobody writes it when the ENGINE is what stopped, because the process
 * that would have written it is the one that went away.
 */

import { afterEach, describe, expect, it } from 'vitest';
import { cleanup } from '@testing-library/react';

import { NO_ANSWER_WAS_WRITTEN, endsOnAnUnansweredAsk } from './Transcript';
import type { TranscriptItem } from '../lib/transcript';

afterEach(cleanup);

const user = { kind: 'user', text: 'do the thing' } as unknown as TranscriptItem;
const assistant = { kind: 'assistant', text: 'done' } as unknown as TranscriptItem;
const tool = { kind: 'tool', name: 'measure_eval_set' } as unknown as TranscriptItem;

describe('what the marker may claim', () => {
  it('names both possibilities rather than asserting the engine stopped', () => {
    /* Found on the second walk of this route. `turn` is local state set when
       THIS page sends, and the only event that moves it is `stream.end` — so a
       turn started in another window (this product ships a detached Stage
       window) leaves this one with `streaming` false and no assistant message
       yet, for as long as the model takes to write a first token. Measured at
       5m 37s on the slowest turn walked. The old wording told those people
       their running turn had died. */
    const said = NO_ANSWER_WAS_WRITTEN;
    expect(said).toMatch(/still being written somewhere else/);
    expect(said).toMatch(/those look the same/);
    expect(said).not.toMatch(/the engine stopped/);
  });

  it('still says the work above is intact', () => {
    expect(NO_ANSWER_WAS_WRITTEN).toMatch(/still on the record/);
  });
});

describe('a turn that never finished', () => {
  it('is recognised when the person spoke and nothing answered', () => {
    expect(endsOnAnUnansweredAsk([user])).toBe(true);
  });

  it('is still recognised when tools ran before it died', () => {
    /* The case actually found: a turn can call tools and stop before writing a
       word, so looking at the very last item would have missed it entirely. */
    expect(endsOnAnUnansweredAsk([user, tool, tool])).toBe(true);
  });

  it('is not claimed when the turn was answered', () => {
    expect(endsOnAnUnansweredAsk([user, assistant])).toBe(false);
    expect(endsOnAnUnansweredAsk([user, tool, assistant, tool])).toBe(false);
  });

  it('is not claimed for an empty thread', () => {
    expect(endsOnAnUnansweredAsk([])).toBe(false);
  });

  it('is not claimed for an earlier unanswered ask that was later answered', () => {
    expect(endsOnAnUnansweredAsk([user, assistant, user, assistant])).toBe(false);
  });
});
