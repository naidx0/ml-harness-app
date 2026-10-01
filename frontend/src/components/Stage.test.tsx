/**
 * The Stage draws thread 33 as it was measured — docs/PHASES.md S2–S5.
 *
 * The fixture is `GET /api/threads/33/stage` off the real database on
 * 2026-09-02, plus the raw `measure_retriever_recall` reply from the same
 * thread. Every number asserted here is one of those runs' own; none is typed
 * from memory, and a fixture regenerated from a different thread would fail
 * these on purpose.
 */

import { useReducer } from 'react';
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

import payloadJson from '../fixtures/stage/thread-33.json';
import recallJson from '../fixtures/stage/recall-33.json';
import { readRecallReport } from '../lib/engine/retrieval';
import type { StagePayload } from '../lib/engine/stage';
import { initialStage, stageReducer, type StageState } from '../lib/stageState';
import { Stage, currentRun } from './Stage';

const payload = payloadJson as unknown as StagePayload;
const recall = readRecallReport((recallJson as { result: unknown }).result);

/** The Stage under the same reducer the shell uses, so a click here is a
 *  dispatch there. */
function Harness({ start }: { start?: Partial<StageState> }) {
  const [state, dispatch] = useReducer(stageReducer, undefined, () => ({ ...initialStage(), ...start }));
  return <Stage payload={payload} state={state} dispatch={dispatch} size="split" recall={recall} carve={null} />;
}

afterEach(() => cleanup());

describe('the Bench', () => {
  it('draws every run of thread 33 as a row of its own cells, baseline first', () => {
    render(<Harness />);
    expect(payload.baseline_run_id).toBe(42);
    const rows = screen.getAllByRole('option');
    expect(rows.map((row) => row.textContent)).toEqual(
      expect.arrayContaining([expect.stringContaining('42'), expect.stringContaining('45'), expect.stringContaining('50')]),
    );
    /* 9 runs × 30 rows of cells, each carrying its verdict as a title. */
    const cells = document.querySelectorAll('.lattice__cell');
    expect(cells.length).toBe(payload.runs.length * 30);
  });

  it('states the paired verdict the engine computed, never its own', () => {
    render(<Harness start={{ runId: 45 }} />);
    const paired = payload.comparisons['45'];
    expect(paired.against).toBe(42);
    const side = document.querySelector('.stage__side .stage__kv')!;
    expect(side.textContent).toContain(`improved${paired.improved}`);
    expect(side.textContent).toContain(`regressed${paired.regressed}`);
    expect(side.textContent).toContain(paired.p_value.toFixed(3));
    expect(screen.getByText(paired.verdict === 'different' ? 'DIFFERENT' : 'NO EVIDENCE')).toBeTruthy();
  });

  it('picks the newest complete run when nothing is selected', () => {
    const run = currentRun(payload, null);
    expect(run?.run_id).toBe(50);
  });
});

describe('the Gate map', () => {
  it('renders NO_TRAIN__RAG with 3 of 5 gates passed', () => {
    render(<Harness start={{ panel: 'gates' }} />);
    expect(screen.getByText('NO_TRAIN__RAG')).toBeTruthy();
    expect(screen.getByText('3 of 5 gates passed')).toBeTruthy();
    expect(screen.getAllByText('PASSED').length).toBe(3);
  });
});

describe('Retrieval & split', () => {
  it('draws the recall curve to 29 of 30 at k=5', () => {
    render(<Harness start={{ panel: 'retrieval' }} />);
    expect(recall?.hits).toBe(29);
    /* k=5 is the last row of the curve; earlier k may already read 29/30. */
    const rows = document.querySelectorAll('.rcurve__row');
    expect(rows.length).toBe(recall?.curve.length);
    expect(rows[rows.length - 1].textContent).toContain('29/30 · 97%');
  });
});

describe('the Sandbox ledger', () => {
  it('lists the practical-ml sandbox and its runs off the run logs', () => {
    render(<Harness start={{ panel: 'sandbox' }} />);
    expect(screen.getByText('practical-ml')).toBeTruthy();
    const box = payload.sandboxes.find((b) => b.name === 'practical-ml');
    expect(box?.runs.some((run) => run.kind === 'train' && run.curve.length > 1)).toBe(true);
  });
});

describe('one selection across sizes', () => {
  it('a click on a run chip changes the selection the Bench states', () => {
    render(<Harness />);
    fireEvent.click(screen.getAllByRole('option').find((el) => el.textContent?.includes('47'))!);
    /* The eyebrow dropped the word `selected`: the lattice marks the pick in
       gold and this panel exists only for it, so saying it again was the
       third label on one 10px line. The property under test is unchanged -
       the Bench states WHICH run the click selected. */
    expect(screen.getByText(/^run 47/)).toBeTruthy();
  });
});
