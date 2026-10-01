/**
 * What the journey overview may claim.
 *
 * The engine keeps two questions apart — did this step's tool run here, and is
 * this step's purpose met by facts another tool stamped — and the whole value
 * of that distinction is lost if the surface collapses it back into a tick on
 * the way to the screen. These are the assertions that hold it open.
 *
 * The other class of defect, the one `Studios.test.tsx` names, is still
 * invisible from here: a seam, a clipped row, a rail drawn through a mark.
 * Those need a screenshot, and this step took one.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

import { Journey } from './Journey';
import type { JourneyPayload, JourneyStep } from '../lib/engine/journey';

afterEach(cleanup);

function step(over: Partial<JourneyStep>): JourneyStep {
  return {
    ordinal: 1,
    tool: 'attach_context',
    why: 'record where the material lives',
    args_hint: "path = the person's folder",
    needs_approval: false,
    state: 'ahead',
    unnecessary_because: null,
    attempted: null,
    evidence: null,
    ran_at: null,
    driven_by: null,
    produced: null,
    satisfied_by: null,
    prefill: {},
    readiness: { mode: 'needs' as const, missing: [] },
    ...over,
  };
}

/** Point `next_runnable` at a step, the way the engine does when that step
 *  can be pressed. The run control follows THIS, not the ordinal `next` -
 *  see the "route whose next step cannot run" case below. */
function runnableAt(s: JourneyStep) {
  return {
    ordinal: s.ordinal,
    tool: s.tool,
    why: s.why,
    args_hint: s.args_hint,
    needs_approval: s.needs_approval,
    readiness: s.readiness,
  };
}

function payload(over: Partial<JourneyPayload> = {}): JourneyPayload {
  return {
    thread_id: 33,
    journey: 'train_on_my_files',
    journey_origin: 'recorded',
    matched_on: [],
    says: "Train a small local model that knows the person's own material.",
    steps: [step({})],
    total: 17,
    done_n: 0,
    next: null,
    next_runnable: null,
    outcome: null,
    verdict: null,
    journeys_available: ['train_on_my_files', 'make_an_eval'],
    say: 'Step 1 of 17: record where the material lives.',
    ...over,
  };
}

describe('a route with no journey on it', () => {
  it('names the routes that exist rather than picking one', () => {
    render(
      <Journey
        payload={payload({
          journey: null,
          steps: [],
          say: 'This conversation has no goal on it yet, so there is no route to show.',
        })}
      />,
    );
    expect(screen.getByText(/no goal on it yet/)).toBeTruthy();
    expect(screen.getByText('Train on my files')).toBeTruthy();
    expect(screen.getByText('Make an eval')).toBeTruthy();
  });
});

describe('what a step is allowed to claim', () => {
  it('a step met by another tool says which one, and is not drawn as run', () => {
    render(
      <Journey
        payload={payload({
          steps: [
            step({
              ordinal: 13,
              tool: 'measure_baseline',
              state: 'done_elsewhere',
              evidence: 'ledger',
              satisfied_by: {
                tool: 'run_eval',
                facts: ['baseline_measured', 'baseline_score'],
              },
            }),
          ],
        })}
      />,
    );
    expect(screen.getByText('run_eval')).toBeTruthy();
    expect(screen.getByText(/met by/)).toBeTruthy();
    expect(screen.getByText(/baseline_measured, baseline_score/)).toBeTruthy();
    /* And it does not say a person or a model ran it, because nobody did. */
    expect(screen.queryByText(/run by/)).toBeNull();
  });

  it('a step that ran carries the tool own summary and who drove it', () => {
    render(
      <Journey
        payload={payload({
          steps: [
            step({
              state: 'done',
              evidence: 'event',
              ran_at: '2026-09-01 18:23:03',
              driven_by: 'user',
              produced: 'Carved 30 rows out of 135',
            }),
          ],
          done_n: 1,
        })}
      />,
    );
    expect(screen.getByText('Carved 30 rows out of 135')).toBeTruthy();
    expect(screen.getByText(/run by you/)).toBeTruthy();
  });

  it('exactly one step is marked as where you are', () => {
    /* Rewritten when the "you are here" chip was removed as a third accent
       element, not loosened: the property is unchanged - one step, and only
       one, is the one you are on - and it is now asserted through the row's
       accessible name, which is where those words went. */
    render(
      <Journey
        payload={payload({
          steps: [
            step({ ordinal: 1, state: 'done' }),
            step({ ordinal: 2, tool: 'carve_rows', state: 'next' }),
            step({ ordinal: 3, tool: 'drop_duplicates', state: 'ahead' }),
          ],
        })}
      />,
    );
    expect(screen.getAllByRole('listitem', { name: /you are here/i })).toHaveLength(1);
  });

  it('says a step asks first when the tool needs approval', () => {
    render(
      <Journey
        payload={payload({
          steps: [step({ tool: 'carve_rows', needs_approval: true, state: 'next' })],
        })}
      />,
    );
    expect(screen.getByText('asks first')).toBeTruthy();
  });

  it('marks an inferred journey as inferred', () => {
    render(<Journey payload={payload({ journey_origin: 'matched', matched_on: ['train'] })} />);
    expect(screen.getByText('inferred')).toBeTruthy();
  });

  it('does not mark a recorded journey as inferred', () => {
    render(<Journey payload={payload({ journey_origin: 'recorded' })} />);
    expect(screen.queryByText('inferred')).toBeNull();
  });
});

describe('when the engine did not answer', () => {
  it('says so rather than drawing an empty route', () => {
    render(<Journey payload={null} error="connection refused" />);
    expect(screen.getByText(/could not be read/)).toBeTruthy();
  });

  it('keeps the last route on screen when a refresh fails', () => {
    /* `useJourney` deliberately does not clear the payload on a failed
       re-read: a route read a moment ago is truer than none. The component
       must therefore prefer the payload it has over the error beside it. */
    render(<Journey payload={payload()} error="connection refused" />);
    expect(screen.getByText('Train on my files')).toBeTruthy();
    expect(screen.queryByText(/could not be read/)).toBeNull();
  });
});

describe('the one action on the step you are on', () => {
  it('offers it on the next step and names the tool it opens', () => {
    /* Rewritten when the run control moved from the ordinal `next` to the
       first step that CAN run: the property - one control, and it hands over
       the step's own tool and prefill - is unchanged. */
    const asked = vi.fn();
    const target = step({ ordinal: 2, tool: 'carve_rows', state: 'next',
                          readiness: { mode: 'needs', missing: [] } });
    render(
      <Journey
        payload={payload({
          steps: [step({ ordinal: 1, state: 'done' }), target,
                  step({ ordinal: 3, tool: 'drop_duplicates', state: 'ahead' })],
          next_runnable: runnableAt(target),
        })}
        onDoStep={asked}
      />,
    );
    const buttons = screen.getAllByRole('button', { name: /do this step/i });
    expect(buttons).toHaveLength(1);
    fireEvent.click(buttons[0]);
    expect(asked).toHaveBeenCalledWith('carve_rows', {});
  });

  it('offers nothing when the route is finished', () => {
    render(
      <Journey
        payload={payload({ steps: [step({ state: 'done' })], next: null })}
        onDoStep={() => {}}
      />,
    );
    expect(screen.queryByRole('button', { name: /do this step/i })).toBeNull();
  });

  it('draws no control at all when the surface was given no way to act', () => {
    /* The detached and read-only cases: a button that did nothing would be a
       promise the surface cannot keep. */
    render(<Journey payload={payload({ steps: [step({ state: 'next' })] })} />);
    expect(screen.queryByRole('button', { name: /do this step/i })).toBeNull();
  });
});

describe('what the step already knows', () => {
  it('says which fields the control will arrive holding, and hands them over', () => {
    const asked = vi.fn();
    const prefill = {
      sandbox: { value: 'practical-ml', from: 'the sandbox you made' },
      baseline_run_id: { value: 42, from: 'the baseline in this conversation' },
    };
    const target = step({ tool: 'score_the_adapter', state: 'next', prefill,
                          readiness: { mode: 'needs', missing: [] } });
    render(
      <Journey
        payload={payload({ steps: [target], next_runnable: runnableAt(target) })}
        onDoStep={asked}
      />,
    );
    expect(screen.getByText(/opens knowing/)).toBeTruthy();
    expect(screen.getByText('sandbox')).toBeTruthy();
    expect(screen.getByText('baseline_run_id')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /do this step/i }));
    expect(asked).toHaveBeenCalledWith('score_the_adapter', prefill);
  });

  it('says nothing about what it knows when it knows nothing', () => {
    render(
      <Journey
        payload={payload({ steps: [step({ state: 'next', prefill: {} })] })}
        onDoStep={() => {}}
      />,
    );
    expect(screen.queryByText(/opens knowing/)).toBeNull();
  });
});

describe('the training config', () => {
  it('is named among what the step opens knowing, like any other field', () => {
    render(
      <Journey
        payload={payload({
          steps: [
            step({
              tool: 'run_in_sandbox',
              state: 'next',
              prefill: {
                name: { value: 'practical-ml', from: 'the sandbox you made' },
                config: {
                  value: { base_model: 'HuggingFaceTB/SmolLM2-1.7B', dataset_path: 'C:/sb/train.jsonl' },
                  from: 'the model you sized and the training half, as the sandbox copied it',
                },
              },
            }),
          ],
        })}
        onDoStep={() => {}}
      />,
    );
    expect(screen.getByText('config')).toBeTruthy();
    expect(screen.getByText('name')).toBeTruthy();
  });
});

describe('what came out the other end', () => {
  const outcome = {
    adapter_run_id: 50,
    baseline_run_id: 42,
    score: 0.0667,
    baseline_score: 0.1333,
    delta: -0.0667,
    improved: 2,
    regressed: 4,
    paired_rows: 30,
    p_value: 0.6875,
    verdict: 'no_evidence',
    resolved: false,
    rows_that_would_resolve_this_delta: 433,
    // The engine's own sentence, copied from what it served for runs 50/42
    // rather than paraphrased - a shortened stand-in here is how a screen
    // can pass its tests while reading wrong in the product.
    says:
      "NO EVIDENCE. The scores differ by -6.7% on the 30 rows both runs graded, but only " +
      "6 of them changed (2 improved, 4 regressed) and McNemar's exact test gives p=0.688. " +
      'This eval set cannot tell these two apart. Grade 403 more rows and ask again.',
  };

  it('says NO EVIDENCE in those words, with both runs behind it', () => {
    render(<Journey payload={payload({ outcome })} />);
    expect(screen.getByText('NO EVIDENCE')).toBeTruthy();
    expect(screen.getByText(/run 50 against 42/)).toBeTruthy();
    // 7% (the adapter) beside 13% (the baseline), both the engine's own numbers.
    expect(screen.getByText(/13%/)).toBeTruthy();
  });

  it('calls a resolved improvement better, and a resolved loss worse', () => {
    render(<Journey payload={payload({ outcome: { ...outcome, resolved: true, delta: 0.2 } })} />);
    expect(screen.getByText('BETTER')).toBeTruthy();
    cleanup();
    render(<Journey payload={payload({ outcome: { ...outcome, resolved: true, delta: -0.2 } })} />);
    expect(screen.getByText('WORSE')).toBeTruthy();
  });

  it('carries the denominator on the same line as the scores', () => {
    /* 7% against 13% is a different claim on 30 rows than on 300, and the
       engine measured the 30. A card that shows the percentages and drops the
       n is asking the reader to trust a comparison they cannot weigh. */
    render(<Journey payload={payload({ outcome })} />);
    expect(screen.getByText(/on 30 paired rows/)).toBeTruthy();
  });

  it('turns NO EVIDENCE into an amount of work when nothing else says it', () => {
    /* NO EVIDENCE otherwise leaves a reader with no next move, and the engine
       already knows how many rows would settle a delta this size. */
    render(<Journey payload={payload({ outcome: { ...outcome, says: '' } })} />);
    expect(screen.getByText(/433/)).toBeTruthy();
    cleanup();
    render(<Journey payload={payload({ outcome: { ...outcome, says: '', resolved: true } })} />);
    expect(screen.queryByText(/would need about/)).toBeNull();
  });

  it('does not state the same next move twice in two different units', () => {
    /* The engine's `says` states it as rows still to grade (403); this line
       states the total (433). Both on screen is one fact wearing two numbers,
       and the reader has to work out that they agree. A screenshot caught
       this - every test above passed while it was on screen. */
    render(<Journey payload={payload({ outcome })} />);
    expect(screen.getByText(/Grade 403 more rows/)).toBeTruthy();
    expect(screen.queryByText(/would need about/)).toBeNull();
  });

  it('draws nothing at all before an adapter has been scored', () => {
    render(<Journey payload={payload({ outcome: null })} />);
    expect(screen.queryByText('NO EVIDENCE')).toBeNull();
  });
});

describe('the other answer', () => {
  const verdict = {
    outcome: 'NO_TRAIN__RAG',
    trains: false,
    say: 'Under roughly 100M domain tokens, continued pretraining buys less than a good retriever.',
    gates_passed: 3,
    gates_total: 5,
    blocked_by: null,
  };

  it('names the ledger answer and the gates behind it', () => {
    render(<Journey payload={payload({ verdict })} />);
    expect(screen.getByText('NO_TRAIN__RAG')).toBeTruthy();
    expect(screen.getByText('3 of 5 gates passed')).toBeTruthy();
    expect(screen.getByText(/retriever/)).toBeTruthy();
  });

  it('draws a do-not-train answer as plainly as a train one', () => {
    /* Neither is coloured as good: a do-not-train verdict is this product's
       most valuable output, and a TRAIN verdict is not a prize. */
    const { container } = render(<Journey payload={payload({ verdict })} />);
    const card = container.querySelector('.jrn__verdict');
    expect(card?.getAttribute('data-trains')).toBeNull();
    cleanup();
    const trained = render(
      <Journey payload={payload({ verdict: { ...verdict, outcome: 'TRAIN__LORA_SFT', trains: true } })} />,
    );
    expect(trained.container.querySelector('.jrn__verdict')?.getAttribute('data-trains')).toBe('true');
  });

  it('draws nothing before anything has been diagnosed', () => {
    render(<Journey payload={payload({ verdict: null })} />);
    expect(screen.queryByText(/gates passed/)).toBeNull();
  });
});

describe('the hue budget, and who can hear the route', () => {
  const threeSteps = () => {
    const target = step({ ordinal: 2, tool: 'carve_rows', state: 'next',
                          readiness: { mode: 'needs', missing: [] } });
    return payload({
      steps: [step({ ordinal: 1, state: 'done' }), target,
              step({ ordinal: 3, tool: 'drop_duplicates', state: 'ahead' })],
      next_runnable: runnableAt(target),
    });
  };

  it('spends the accent on the action and nowhere else', () => {
    /* DESIGN_SYSTEM §3.4: "At most one accent element is lit per screen... A
       second accent element in the chrome means the accent has stopped
       meaning the product needs you." Measured in the browser this surface
       had three, and all three said the same thing - the mark, a chip and the
       button all meant "this is the step you are on". The button keeps it,
       because that is where the product actually needs a person. */
    const { container } = render(<Journey payload={threeSteps()} onDoStep={() => {}} />);
    expect(container.querySelectorAll('.jrn__do')).toHaveLength(1);
    expect(container.querySelectorAll('.jrn__now')).toHaveLength(0);
  });

  it('says which step you are on in words, not only in a shape', () => {
    /* The mark is aria-hidden, so before this the state reached a screen
       reader not at all: every row announced its tool and nothing about
       whether it was done, next or untouched. */
    render(<Journey payload={threeSteps()} />);
    expect(screen.getByRole('listitem', { name: /step 2 of 17.*you are here/i })).toBeTruthy();
    expect(screen.getByRole('listitem', { name: /step 1 of 17.*done/i })).toBeTruthy();
    expect(screen.getByRole('listitem', { name: /step 3 of 17.*not started/i })).toBeTruthy();
  });

  it('announces a step met by another tool as met, not as done', () => {
    render(
      <Journey
        payload={payload({
          steps: [
            step({
              ordinal: 13,
              tool: 'measure_baseline',
              state: 'done_elsewhere',
              satisfied_by: { tool: 'run_eval', facts: ['baseline_score'] },
            }),
          ],
        })}
      />,
    );
    expect(screen.getByRole('listitem', { name: /met by run_eval/i })).toBeTruthy();
  });
});

describe('what happened when you tried', () => {
  const refused = {
    at: '2026-09-02 23:45:00',
    error: 'approval_required',
    detail: 'split graded data into eval and train files needs an approval before it can run.',
  };

  it('carries the tool own sentence, and does not dress it as an alarm', () => {
    /* Bare right/wrong feedback measures d = 0.05 and discouraging feedback is
       negative at -0.14; saying why and what next measures 0.49. So: no red,
       no cross, no "failed" - the remedy the tool already wrote. */
    const { container } = render(
      <Journey payload={payload({ steps: [step({ state: 'next', attempted: refused })] })} />,
    );
    expect(screen.getByText(/needs an approval before it can run/)).toBeTruthy();
    expect(screen.queryByText(/failed/i)).toBeNull();
    expect(container.querySelectorAll('.jrn__tried')).toHaveLength(1);
  });

  it('says nothing about an attempt on a step nobody tried', () => {
    render(<Journey payload={payload({ steps: [step({ state: 'next', attempted: null })] })} />);
    expect(screen.queryByText('tried')).toBeNull();
  });
});

describe('picking a route', () => {
  const noRoute = () =>
    payload({ journey: null, steps: [], say: 'This conversation has no goal on it yet.' });

  it('offers each route as a button and names the one picked', () => {
    const picked = vi.fn();
    render(<Journey payload={noRoute()} onChooseJourney={picked} />);
    fireEvent.click(screen.getByRole('button', { name: 'Train on my files' }));
    expect(picked).toHaveBeenCalledWith('train_on_my_files');
  });

  it('lists them as plain text where the surface cannot act', () => {
    /* A button that did nothing would be a promise this surface cannot keep -
       the same rule the step control follows. */
    render(<Journey payload={noRoute()} />);
    expect(screen.queryByRole('button', { name: 'Train on my files' })).toBeNull();
    expect(screen.getByText('Train on my files')).toBeTruthy();
  });
});

describe('the step control has three honest answers', () => {
  const ready = (over: Record<string, unknown> = {}) => {
    const only = step({
      tool: 'read_model_shortlist',
      state: 'next',
      readiness: { mode: 'click', missing: [] },
      ...over,
    });
    return payload({
      steps: [only],
      next_runnable: {
        ordinal: only.ordinal,
        tool: only.tool,
        why: only.why,
        args_hint: only.args_hint,
        needs_approval: only.needs_approval,
        readiness: only.readiness,
      },
    });
  };

  it('runs a ready step from the button, with no form', () => {
    const ran = vi.fn().mockResolvedValue({ ok: true });
    render(<Journey payload={ready()} onRunStep={ran} />);
    fireEvent.click(screen.getByRole('button', { name: /run this step/i }));
    expect(ran).toHaveBeenCalledWith('read_model_shortlist', {}, false);
  });

  it('asks once before a step that needs a person to say yes', async () => {
    const ran = vi.fn().mockResolvedValue({ ok: true });
    render(
      <Journey
        payload={ready({ tool: 'run_in_sandbox', readiness: { mode: 'approve', missing: [] } })}
        onRunStep={ran}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /review and run/i }));
    expect(ran).not.toHaveBeenCalled();
    expect(screen.getByText(/this one asks first/i)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /yes, run it/i }));
    await waitFor(() => expect(ran).toHaveBeenCalledWith('run_in_sandbox', {}, true));
  });

  it('names what it still wants instead of opening a form blind', () => {
    const opened = vi.fn();
    render(
      <Journey
        payload={ready({ tool: 'state_facts', readiness: { mode: 'needs', missing: ['facts'] } })}
        onDoStep={opened}
      />,
    );
    expect(screen.getByRole('button', { name: /fill in facts/i })).toBeTruthy();
  });

  it('shows a refusal in the flow, in the tool own words', async () => {
    const ran = vi.fn().mockResolvedValue({ ok: false, detail: 'There is nothing at that path. Check it and run it again.' });
    render(<Journey payload={ready()} onRunStep={ran} />);
    fireEvent.click(screen.getByRole('button', { name: /run this step/i }));
    await waitFor(() => expect(screen.getByText(/check it and run it again/i)).toBeTruthy());
    /* And the step is still there to try again - a refusal is not an end. */
    expect(screen.getByRole('button', { name: /run this step/i })).toBeTruthy();
  });
});

describe('a route whose next step cannot run', () => {
  it('puts the run control on the step that can, and says what the blocked one wants', () => {
    /* The walk found this: a workspace that arrived with graded rows makes
       step 2 ask for a folder of markdown it does not have, and anchoring the
       only action there left the route pointing at something that could not
       happen while later steps sat ready. */
    const blocked = step({
      ordinal: 2,
      tool: 'carve_rows',
      state: 'next',
      readiness: { mode: 'needs', missing: ['root', 'into'] },
    });
    const able = step({
      ordinal: 6,
      tool: 'check_split_leakage',
      state: 'ahead',
      readiness: { mode: 'click', missing: [] },
    });
    const ran = vi.fn().mockResolvedValue({ ok: true });
    render(
      <Journey
        payload={payload({
          steps: [blocked, able],
          next_runnable: {
            ordinal: 6,
            tool: 'check_split_leakage',
            why: '',
            args_hint: '',
            needs_approval: false,
            readiness: { mode: 'click', missing: [] },
          },
        })}
        onRunStep={ran}
        onDoStep={() => {}}
      />,
    );
    expect(screen.getAllByRole('button', { name: /run this step/i })).toHaveLength(1);
    expect(screen.getByRole('button', { name: /fill in root, into/i })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /run this step/i }));
    expect(ran).toHaveBeenCalledWith('check_split_leakage', {}, false);
  });
});

describe('a refusal is printed once', () => {
  it('does not repeat what the step is already reporting', async () => {
    /* Caught by a screenshot and invisible to every assertion before it: the
       button's own refusal and the engine's `attempted` record are the same
       sentence, and both were drawn. */
    const detail = 'The GPU is already holding 5.72 GB of 8.0 GB.';
    const only = step({
      tool: 'run_in_sandbox',
      state: 'next',
      readiness: { mode: 'click', missing: [] },
      attempted: { at: '2026-09-04 20:06', error: 'sandbox_rejected', detail },
    });
    const ran = vi.fn().mockResolvedValue({ ok: false, detail });
    render(
      <Journey
        payload={payload({ steps: [only], next_runnable: runnableAt(only) })}
        onRunStep={ran}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /run this step/i }));
    await waitFor(() => expect(screen.getAllByText(new RegExp(detail.slice(0, 30)))).toHaveLength(1));
  });

  it('still shows a refusal the engine never recorded', async () => {
    /* The 428 case: an approval refusal raises before the event pair is
       written, so this is the only surface that can carry it. */
    const only = step({
      tool: 'carve_eval_set',
      state: 'next',
      readiness: { mode: 'click', missing: [] },
      attempted: null,
    });
    const ran = vi.fn().mockResolvedValue({ ok: false, detail: 'needs an approval before it can run.' });
    render(
      <Journey payload={payload({ steps: [only], next_runnable: runnableAt(only) })} onRunStep={ran} />,
    );
    fireEvent.click(screen.getByRole('button', { name: /run this step/i }));
    await waitFor(() => expect(screen.getByText(/needs an approval/)).toBeTruthy());
  });
});

describe('a step the route did not need', () => {
  it('is neither ticked nor failed, and says which step covered it', () => {
    /* Somebody arriving with graded rows cannot run `carve_rows` - there is no
       folder of documents to cut. Marking it done would claim work nobody did;
       leaving it not-started would demand work nobody needs. */
    render(
      <Journey
        payload={payload({
          steps: [
            step({
              ordinal: 2,
              tool: 'carve_rows',
              state: 'not_needed',
              unnecessary_because: 'carve_eval_set',
            }),
          ],
        })}
      />,
    );
    expect(screen.getByText(/not needed here/)).toBeTruthy();
    expect(screen.getByText('carve_eval_set')).toBeTruthy();
  });

  it('announces itself that way too, rather than as done', () => {
    render(
      <Journey
        payload={payload({
          steps: [
            step({ ordinal: 2, tool: 'carve_rows', state: 'not_needed',
                   unnecessary_because: 'carve_eval_set' }),
          ],
        })}
      />,
    );
    expect(
      screen.getByRole('listitem', { name: /not needed here, carve_eval_set covered it/i }),
    ).toBeTruthy();
  });
});

describe('the route with no verdict yet', () => {
  it('says there is no verdict rather than drawing nothing', () => {
    /* Found on the design-model walk. A fresh route drew all seventeen steps
       and then stopped. The same route on a thread where one tool had run
       showed "0 of 5 gates passed" and named the rule that comes first. A
       reader cannot tell a harness with no opinion from one that is not showing
       the opinion it has, and those call for different next moves. */
    render(<Journey payload={payload({ verdict: null })} />);
    expect(screen.getByText('NO VERDICT YET')).toBeTruthy();
    expect(screen.getByText(/A verdict appears as soon as a step records a fact/)).toBeTruthy();
  });

  it('does not advise an action the person has already taken', () => {
    /* Second walk. The first draft ended "Run a step above - or tell the
       harness where your material is". Somebody who had just attached their
       folder saw the counter read 1 of 17 and, under it, advice to do what they
       had done. A gate opens on a measured fact, and a folder is a location. */
    render(<Journey payload={payload({ verdict: null })} />);
    const said = screen.getByText(/A verdict appears/).textContent ?? '';
    expect(said).not.toMatch(/tell the harness where your material is/);
    expect(said).toMatch(/records a fact/);
  });

  it('states no denominator it cannot read', () => {
    /* The first draft said "0 of 5 gates reached". Five is true of the
       machine-learning ledger and false of the harness-design one, which
       declares six - and with no verdict there is no `gates_total` to read.
       Inventing a total in the card that exists because a denominator was
       missing would be the exact failure this surface prevents. */
    render(<Journey payload={payload({ verdict: null })} />);
    const said = screen.getByText(/no gate reached/).textContent ?? '';
    expect(said).not.toMatch(/\bof \d+\b/);
  });

  it('gives way to the real verdict as soon as there is one', () => {
    render(
      <Journey
        payload={payload({
          verdict: {
            outcome: 'BLOCKED__DEFINE_SUCCESS_FIRST',
            trains: false,
            say: '',
            gates_passed: 0,
            gates_total: 5,
            blocked_by: null,
          },
        })}
      />,
    );
    expect(screen.queryByText('NO VERDICT YET')).toBeNull();
    expect(screen.getByText('0 of 5 gates passed')).toBeTruthy();
  });
});

describe('the pane with nothing in it', () => {
  it('names the way out, not just the gap', () => {
    /* Found on a stranger walk, by opening all eight inspector panes side by
       side with no thread. Seven said what was missing AND what would fill it -
       Files offers "Open a thread, or pick a project in the rail". This one
       said "No conversation open." and stopped, which hands the reader the gap
       and no way to close it. An empty pane is the one that most needs to say
       what would put something in it. */
    render(<Journey payload={null} />);
    const said = screen.getByText(/No conversation open/).textContent ?? '';
    expect(said).toMatch(/Start a thread|pick one in the sidebar/);
    expect(said.length).toBeGreaterThan(60);
  });

  it('says it is reading before it says there is nothing', () => {
    /* "No conversation open" while a fetch is in flight is a wrong answer, not
       a slow one. */
    render(<Journey payload={null} loading />);
    expect(screen.getByText(/Reading the route/)).toBeTruthy();
    expect(screen.queryByText(/No conversation open/)).toBeNull();
  });
});

describe('the rule that stopped the route', () => {
  const blockedVerdict = {
    outcome: 'ACTION__MEASURE_BASELINE',
    trains: false,
    say: '',
    gates_passed: 1,
    gates_total: 5,
    blocked_by: {
      reached: true,
      checked: 2,
      of: 5,
      class_undecided: false,
      gate: 'G1_BASELINE_MEASURED',
      clause: 'baseline_measured and baseline_score is not null',
      reads: [
        { fact: 'baseline_score', value: null, origin: null, how: null, unmeasured: true },
        { fact: 'eval_size_n', value: 30, origin: 'MEASURED', how: 'counted 30 rows', unmeasured: false },
      ],
    },
  };

  it('names the gate, the rule, and every fact the rule reads', () => {
    render(<Journey payload={payload({ verdict: blockedVerdict })} />);
    expect(screen.getByText('G1_BASELINE_MEASURED')).toBeTruthy();
    expect(screen.getByText(/baseline_measured and baseline_score/)).toBeTruthy();
    expect(screen.getByText('eval_size_n')).toBeTruthy();
    expect(screen.getByText('30')).toBeTruthy();
    expect(screen.getByText('MEASURED')).toBeTruthy();
  });

  it('says an unmeasured fact is unanswered, not false', () => {
    /* The commonest refusal on this route: `baseline_score is not null` fails
       because nobody has scored anything, not because a score came back
       empty. Conflating them teaches the wrong thing about what a gate does. */
    render(<Journey payload={payload({ verdict: blockedVerdict })} />);
    expect(screen.getByText(/nothing has measured this yet/)).toBeTruthy();
  });

  it('carries the denominator with the count of gates checked', () => {
    /* "1 passed" is not a number a reader can act on without knowing how many
       were checked. The denominator travels with it. */
    render(<Journey payload={payload({ verdict: blockedVerdict })} />);
    expect(screen.getByText('2 of 5 gates checked')).toBeTruthy();
  });

  it('does not call an unreached gate the one that stopped the route', () => {
    /* Thread 39 is the live case: BLOCKED__DEFINE_SUCCESS_FIRST with all five
       gates NOT_REACHED. Nothing failed, so the screen shows the rule that
       comes first and says so - reporting it as the rule that failed would be
       a claim the reader could act on and it would be wrong. */
    const unreached = {
      ...blockedVerdict,
      outcome: 'BLOCKED__DEFINE_SUCCESS_FIRST',
      blocked_by: {
        ...blockedVerdict.blocked_by,
        gate: 'G0_EVAL_SET',
        reached: false,
        checked: 0,
        clause: 'eval_size_n >= 30',
        reads: [
          { fact: 'eval_size_n', value: 30, origin: 'MEASURED', how: 'counted 30 rows', unmeasured: false },
        ],
      },
    };
    render(<Journey payload={payload({ verdict: unreached })} />);
    expect(screen.getByText('first rule')).toBeTruthy();
    expect(screen.queryByText('stopped at')).toBeNull();
    expect(screen.getByText(/stopped before any gate was evaluated/)).toBeTruthy();
    expect(screen.getByText('0 of 5 gates checked')).toBeTruthy();
  });

  it('says the class is undecided rather than quoting a rule that may not apply', () => {
    /* G2 and G3 carry no `any` row - which rule applies depends on the method
       class. Picking one to fill the line would teach a rule the run is not
       being judged by. */
    const undecided = {
      ...blockedVerdict,
      outcome: 'NO_TRAIN__RAG',
      blocked_by: {
        ...blockedVerdict.blocked_by,
        gate: 'G2_PROMPT_EXHAUSTED',
        reached: false,
        checked: 3,
        class_undecided: true,
        clause: '',
        reads: [],
      },
    };
    render(<Journey payload={payload({ verdict: undecided })} />);
    expect(screen.getByText(/depends on the method class/)).toBeTruthy();
  });

  it('draws no rule block when nothing is blocking', () => {
    render(<Journey payload={payload({ verdict: { ...blockedVerdict, blocked_by: null } })} />);
    expect(screen.queryByText(/G1_BASELINE_MEASURED/)).toBeNull();
  });
});
