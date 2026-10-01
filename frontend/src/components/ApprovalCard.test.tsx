/**
 * A tool the model was refused can be approved from the chat.
 *
 * Before this card there was no way to say yes at all: `grep -rn
 * approval_required frontend/src` returned nothing, while fourteen registered
 * tools declare `approval="always"` and six of the seventeen steps in the
 * `train_on_my_files` journey are among them. The refusal rendered as a failed
 * tool row and the journey stopped there.
 *
 * What these tests hold:
 *
 *   - the card appears for `approval_required` and for nothing else, so an
 *     ordinary tool failure never grows an inviting green button;
 *   - the arguments shown are the arguments submitted, unchanged - the whole
 *     risk of an approval surface is approving a sentence while other values
 *     run;
 *   - declining runs nothing;
 *   - the engine's own refusal sentence is printed rather than paraphrased.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

import { ApprovalCard, readApprovalRequest } from './ApprovalCard';

afterEach(() => cleanup());

const REFUSED = {
  ok: false,
  error: 'approval_required',
  detail:
    "carve_rows needs an approval before it runs. Let them start it from the control.",
};

const ARGS = {
  root: 'C:/Users/example/Desktop/practical-ml-workspace',
  into: 'split',
  answer_column: 'a',
  rows: 30,
};

describe('reading the refusal', () => {
  it('keys on the error code the conductor writes', () => {
    expect(readApprovalRequest(REFUSED)).toEqual({ detail: REFUSED.detail });
  });

  it('is null for every other shape, so no other failure grows a button', () => {
    for (const other of [
      null,
      undefined,
      'approval_required',
      { ok: false, error: 'tool_failed', detail: 'TypeError' },
      { ok: false, error: 'no_such_tool' },
      { ok: true },
      {},
    ]) {
      expect(readApprovalRequest(other)).toBeNull();
    }
  });
});

describe('the card', () => {
  it('submits exactly the arguments it displayed', async () => {
    const onApprove = vi.fn().mockResolvedValue({ ok: true, result: { rows: 30 }, error: null });
    render(
      <ApprovalCard
        name="carve_rows"
        args={ARGS}
        control={null}
        detail={REFUSED.detail}
        onApprove={onApprove}
      />,
    );

    // every argument is on screen, by name and by value
    for (const [key, value] of Object.entries(ARGS)) {
      expect(screen.getByText(key)).toBeTruthy();
      expect(screen.getByText(String(value))).toBeTruthy();
    }

    fireEvent.click(screen.getByText('Run it'));

    await waitFor(() => expect(onApprove).toHaveBeenCalledTimes(1));
    // THE SAME OBJECT, not a rebuilt one: approving what was shown.
    expect(onApprove).toHaveBeenCalledWith('carve_rows', ARGS);
  });

  it("prints the engine's sentence rather than a paraphrase", () => {
    render(
      <ApprovalCard
        name="carve_rows"
        args={ARGS}
        control={null}
        detail={REFUSED.detail}
        onApprove={vi.fn()}
      />,
    );
    expect(screen.getByText(REFUSED.detail)).toBeTruthy();
  });

  it('runs nothing when declined', () => {
    const onApprove = vi.fn();
    render(
      <ApprovalCard
        name="carve_rows"
        args={ARGS}
        control={null}
        detail=""
        onApprove={onApprove}
      />,
    );

    fireEvent.click(screen.getByText('Not now'));
    expect(onApprove).not.toHaveBeenCalled();
    expect(screen.queryByText('Run it')).toBeNull();

    // and the way back is a control, not a reload
    fireEvent.click(screen.getByText('Approve it after all'));
    expect(screen.getByText('Run it')).toBeTruthy();
  });

  it('says what happened, including when the tool refused on its own terms', async () => {
    const onApprove = vi
      .fn()
      .mockResolvedValue({ ok: false, result: { ok: false, error: 'leaked' }, error: null });
    render(
      <ApprovalCard
        name="carve_eval_set"
        args={{}}
        control={null}
        detail=""
        onApprove={onApprove}
      />,
    );

    // a tool that takes no arguments says so rather than showing an empty box
    expect(screen.getByText(/proposed no arguments/)).toBeTruthy();

    fireEvent.click(screen.getByText('Run it'));
    await waitFor(() =>
      expect(screen.getByText(/It ran and refused/)).toBeTruthy(),
    );
  });

  it("uses the tool's own verb for the headline when the registry has it", () => {
    render(
      <ApprovalCard
        name="carve_rows"
        args={{}}
        control={
          {
            name: 'carve_rows',
            verb: 'cut raw files into verbatim tagged rows',
            label: 'Carve rows',
            group: 'Data',
            order: 20,
            description: '',
            fields: [],
            measures: [],
            approval: 'always',
          } as never
        }
        detail=""
        onApprove={vi.fn()}
      />,
    );
    expect(
      screen.getByText('Cut raw files into verbatim tagged rows'),
    ).toBeTruthy();
  });
});
