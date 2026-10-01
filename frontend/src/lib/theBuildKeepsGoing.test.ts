import { describe, expect, it } from 'vitest';

import {
  anApprovalIsWaiting,
  askedOnlyWhetherToGoOn,
  MOST_TURNS_WITHOUT_A_PERSON,
  shouldRunAnotherTurn,
  stepsIn,
  theLastThingItSaid,
  type WorkingDown,
} from './theBuildKeepsGoing';

/** A thread that is building a plan and has just finished a turn that acted. */
function working(over: Partial<WorkingDown> = {}): WorkingDown {
  return {
    mode: 'build',
    plan: '## Phase 1 - carve an eval set\n- [ ] Carve the eval set',
    items: [{ kind: 'user' }, { kind: 'assistant' }, { kind: 'tool' }],
    running: false,
    awaitingApproval: false,
    failed: false,
    taken: 0,
    stopped: false,
    ...over,
  };
}

describe('what ends a turn decides whether there is another', () => {
  it('open steps point at Run the plan rather than auto-chaining', () => {
    /* Max, 2026-09-14: the browser loop no longer invents autonomy. The
       durable path is longrun via "Run the plan". */
    const verdict = shouldRunAnotherTurn(working());
    expect(verdict.go).toBe(false);
    expect(verdict.why).toContain('press Run the plan');
  });

  it('a turn that only spoke still does not auto-chain', () => {
    const talked = working({ items: [{ kind: 'user' }, { kind: 'assistant' }] });
    expect(shouldRunAnotherTurn(talked).go).toBe(false);
    expect(shouldRunAnotherTurn(talked).why).toContain('press Run the plan');
  });

  it('reads only as far back as the last thing the person said', () => {
    /* Text from before the person spoke is not this turn talking. */
    const items = [{ kind: 'user' }, { kind: 'assistant', text: 'Which column?' }];
    expect(theLastThingItSaid(items)).toBe('Which column?');
    expect(theLastThingItSaid([{ kind: 'assistant', text: 'old' }, { kind: 'user' }])).toBe('');
  });

  it('an empty transcript said nothing', () => {
    expect(theLastThingItSaid([])).toBe('');
  });
});

describe('the to-do list is the goal function', () => {
  /* 2026-09-12. Max: "it starts working and then it kind of builds a part of
     it and stops... until every single part of that's fixed it doesn't
     exit." A plan with `- [ ]` steps keeps going through narration; only a
     question to the person, or the last tick, ends it. */
  const stepped = '## Phase 1\n- [x] Profile the rows\n- [ ] Carve the eval set\n- [ ] Measure the baseline';

  it('a turn that only narrated still waits for Run while a step is open', () => {
    const narrated = working({
      plan: stepped,
      items: [{ kind: 'user' }, { kind: 'assistant', text: 'Profiled. Moving on to the carve.' } as never],
    });
    const verdict = shouldRunAnotherTurn(narrated);
    expect(verdict.go).toBe(false);
    expect(verdict.why).toContain('2 open');
    expect(verdict.why).toContain('press Run the plan');
  });

  it('a question to the person stops it even with steps open', () => {
    const asked = working({
      plan: stepped,
      items: [{ kind: 'user' }, { kind: 'assistant', text: 'Which column holds the label?' } as never],
    });
    expect(shouldRunAnotherTurn(asked)).toEqual({ go: false, why: 'it asked you something' });
  });

  it('asking whether to proceed is not asking the person anything', () => {
    /* MEASURED 2026-09-12: three steps done, then "Would you like me to
       proceed with that, or is there something else you'd like to address?" -
       the person pressed Build; that was the answer. */
    const proceed = working({
      plan: stepped,
      items: [
        { kind: 'user' },
        {
          kind: 'assistant',
          text: 'Two steps done. The remaining step is to read the recipes. Would you like me to proceed with that, or is there something else you would like to address?',
        } as never,
      ],
    });
    expect(shouldRunAnotherTurn(proceed).go).toBe(false);
    expect(shouldRunAnotherTurn(proceed).why).toContain('press Run the plan');
    expect(askedOnlyWhetherToGoOn('Shall I continue?')).toBe(true);
    expect(askedOnlyWhetherToGoOn('Which column holds the label?')).toBe(false);
    expect(askedOnlyWhetherToGoOn('Should I proceed and delete the old sandbox?')).toBe(false);
  });

  it('the last tick ends it', () => {
    const all = working({ plan: stepped.replace(/- \[ \]/g, '- [x]') });
    expect(shouldRunAnotherTurn(all)).toEqual({ go: false, why: 'every step is ticked (3)' });
  });

  it('counts steps the way the engine does', () => {
    expect(stepsIn(stepped)).toEqual({ open: 2, done: 1, parked: 0 });
    expect(stepsIn('## Phase 1 - carve an eval set')).toEqual({ open: 0, done: 0, parked: 0 });
    expect(stepsIn(null)).toEqual({ open: 0, done: 0, parked: 0 });
    expect(stepsIn('- [!] blocked — parked: no eval set')).toEqual({ open: 0, done: 0, parked: 1 });
  });

  it('a plan with no step lines is not a goal function and does not loop', () => {
    /* 2026-09-13. Max, photographing the bar: "it keeps parking things and
       saying it's working but in reality it's working 0 items, which just
       sucks and is unoperational." This used to loop on any plan at all as
       long as the last turn had called a tool - phases with no `- [ ]` lines
       under them gave it nothing to finish and nothing to count, so it ran
       to the ceiling saying "working" the whole way. */
    for (const plan of ['## Phase 1 - carve an eval set', '# A plan\n\nSome prose.']) {
      expect(shouldRunAnotherTurn(working({ plan }))).toEqual({
        go: false,
        why: 'the plan has no steps to work down',
      });
    }
  });

  it('parking its way to zero is not every step ticked', () => {
    const parked = working({
      plan: '## Phase 1\n- [x] Profile the rows\n- [!] Carve the eval set — parked: no labels',
    });
    expect(shouldRunAnotherTurn(parked)).toEqual({
      go: false,
      why: 'nothing left to work · 1 done, 1 parked',
    });
  });
});

describe('the four that stop it regardless', () => {
  it('planning never loops', () => {
    expect(shouldRunAnotherTurn(working({ mode: 'plan' })).go).toBe(false);
  });

  it('a thread with no plan has nothing to work down', () => {
    for (const plan of [null, '', '   ']) {
      expect(shouldRunAnotherTurn(working({ plan })).go).toBe(false);
    }
  });

  it('an approval on screen is a person being asked, so it waits', () => {
    /* Autonomy has already removed by name every gate it covers
       (app/autonomy.py). Anything still asking is something it said no to. */
    const asked = working({ awaitingApproval: true });
    expect(shouldRunAnotherTurn(asked)).toEqual({ go: false, why: 'waiting on your approval' });
  });

  it('a failed turn is not retried', () => {
    expect(shouldRunAnotherTurn(working({ failed: true })).go).toBe(false);
  });

  it('never stacks a turn on a running one', () => {
    expect(shouldRunAnotherTurn(working({ running: true })).go).toBe(false);
  });

  it('stops at the ceiling rather than running up a bill', () => {
    const at = working({ taken: MOST_TURNS_WITHOUT_A_PERSON });
    expect(at.taken).toBe(12);
    expect(shouldRunAnotherTurn(at).go).toBe(false);
    expect(shouldRunAnotherTurn(working({ taken: MOST_TURNS_WITHOUT_A_PERSON - 1 })).go).toBe(
      false,
    );
    expect(
      shouldRunAnotherTurn(working({ taken: MOST_TURNS_WITHOUT_A_PERSON - 1 })).why,
    ).toContain('press Run the plan');
  });

  it('stop means stopped, whatever else is true', () => {
    expect(shouldRunAnotherTurn(working({ stopped: true })).go).toBe(false);
  });
});

describe('a refusal says why', () => {
  it('every reason is a sentence a person can read', () => {
    /* The count is beside it in the UI; a loop that will not start must say
       what it is waiting for rather than look broken. */
    const reasons = [
      working({ mode: 'plan' }),
      working({ plan: null }),
      working({ running: true }),
      working({ failed: true }),
      working({ awaitingApproval: true }),
      working({ taken: MOST_TURNS_WITHOUT_A_PERSON }),
      working({ items: [{ kind: 'user' }] }),
      working({ stopped: true }),
      working({ plan: '## Phase 1 with nothing under it' }),
    ].map((state) => shouldRunAnotherTurn(state).why);
    for (const why of reasons) {
      expect(why.trim().length).toBeGreaterThan(0);
    }
    expect(new Set(reasons).size).toBe(reasons.length);
  });
});

describe('an approval on screen is read the way the card reads it', () => {
  const asking = { kind: 'tool', result: { error: 'approval_required' } };

  it('sees the field ApprovalCard keys on', () => {
    expect(anApprovalIsWaiting([{ kind: 'user' }, asking])).toBe(true);
  });

  it('a later tool row means the approval was answered', () => {
    /* Approving re-runs the tool and writes a fresh row. */
    const answered = [{ kind: 'user' }, asking, { kind: 'tool', result: { ok: true } }];
    expect(anApprovalIsWaiting(answered)).toBe(false);
  });

  it('does not reach back past the person', () => {
    expect(anApprovalIsWaiting([asking, { kind: 'user' }])).toBe(false);
  });

  it('a transcript with no tool rows is not waiting on one', () => {
    expect(anApprovalIsWaiting([{ kind: 'user' }, { kind: 'assistant' }])).toBe(false);
    expect(anApprovalIsWaiting([])).toBe(false);
  });

  it('stops the loop when it is fed in', () => {
    const items = [{ kind: 'user' }, asking];
    expect(
      shouldRunAnotherTurn(working({ items, awaitingApproval: anApprovalIsWaiting(items) })),
    ).toEqual({ go: false, why: 'waiting on your approval' });
  });
});
