/**
 * The card drew "The engine sends no alternatives with a verdict" on every
 * blocked verdict, and the engine had been sending them the whole time.
 *
 * `app/tools/next_moves.py` builds `alternatives` and `revisit_if` out of the
 * ledger's own words and the registry's `measures=` declarations, and
 * `run_diagnosis` attaches both. `readDiagnosis` builds a fresh allowlisted
 * object field by field, and neither name was on the list — so they were
 * dropped at the door, and two renderers hardcoded to `return null` filled the
 * gap with a sentence about the absence. Max read that sentence for weeks.
 *
 * These lock the door open: the reader copies both, and it copies them the way
 * every other field here is copied — shape-checked, never trusted.
 */
import { describe, expect, it } from 'vitest';

import { readDiagnosis } from './facts';

/** The shape `run_diagnosis` puts on the wire, trimmed to what this is about. */
function payload(extra: Record<string, unknown> = {}) {
  return {
    ok: true,
    outcome: 'BLOCKED__DEFINE_SUCCESS_FIRST',
    verdict: 'BLOCKED',
    say: "Nothing downstream is decidable until 'good' is defined.",
    proposed_method: 'UNSET',
    gate_ledger: {},
    path: [],
    constraints: [],
    struck_methods: [],
    cost_provenance: 'UNKNOWN',
    fact_origins: {},
    facts_used: {},
    your_facts_were_recorded_as: 'ASSERTED',
    unsubstantiated: [],
    ...extra,
  };
}

describe('the moves the engine named survive the reader', () => {
  it('copies alternatives, with the tool and who runs it', () => {
    const result = readDiagnosis(
      payload({
        alternatives: [
          {
            move: 'exhaust_the_cheaper_thing',
            text: 'Write 20 inputs and the output you wanted.',
            from: 'S0_NO_DEFINITION_OF_SUCCESS.say',
            fact: 'target_score',
            tool: 'state_facts',
            verb: 'say this yourself',
            run_as: 'user',
            arguments: {},
            starts_now: true,
            why: 'BLOCKED__DEFINE_SUCCESS_FIRST',
          },
        ],
      }),
    );
    expect(result).not.toBeNull();
    expect(result?.alternatives).toHaveLength(1);
    expect(result?.alternatives[0].tool).toBe('state_facts');
    expect(result?.alternatives[0].run_as).toBe('user');
    expect(result?.alternatives[0].starts_now).toBe(true);
  });

  it('copies revisit_if', () => {
    const result = readDiagnosis(
      payload({ revisit_if: ['target_score changes from null'] }),
    );
    expect(result?.revisit_if).toEqual(['target_score changes from null']);
  });

  it('is empty rather than broken when the engine sends neither', () => {
    const result = readDiagnosis(payload());
    expect(result?.alternatives).toEqual([]);
    expect(result?.revisit_if).toEqual([]);
  });

  it('drops a move with no text, and never invents one', () => {
    const result = readDiagnosis(
      payload({
        alternatives: [
          { move: 'a', text: '   ', tool: 'x' },
          null,
          'not an object',
          { move: 'b', text: 'a real move' },
        ],
      }),
    );
    expect(result?.alternatives.map((one) => one.text)).toEqual(['a real move']);
    expect(result?.alternatives[0].tool).toBeNull();
  });

  it('ignores an alternatives field that is not a list', () => {
    const result = readDiagnosis(payload({ alternatives: { move: 'nope' } }));
    expect(result?.alternatives).toEqual([]);
  });
});
