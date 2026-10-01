/**
 * The Stage reads. It has no way to write, in any size, on any payload.
 *
 * `app/stage.py` is one GET and `tests/test_the_stage_reads_what_the_thread_
 * measured.py` proves the ENGINE files no row while answering it. That is
 * half the claim. The other half is this side: a surface that draws a
 * thread's whole measurement history is exactly the surface where an
 * innocent-looking "rename this run" box would one day appear, and the first
 * person to add one would not think of themselves as changing the product's
 * contract. This file is what makes that a failing test rather than a
 * conversation.
 *
 * Three claims, each on both payloads (thread 33, and a thread that has
 * measured nothing):
 *
 *   1. no writable control is rendered - no input, textarea, contenteditable,
 *      form or submit, in any of the three sizes;
 *   2. the Stage issues NO request at all while drawing a payload it was
 *      handed - and if that ever changes, every request must be a GET;
 *   3. an empty payload draws no invented figure - no "0" standing in for a
 *      score nobody measured.
 *
 * The empty payload here is built from the shape `app/stage.py build()`
 * returns for a thread with nothing in it, which the engine-side test in this
 * commit measures and locks: empty containers, a skeleton diagnosis whose
 * every field is an absence, and the `reads` block intact.
 */

import { useReducer } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

import payloadJson from '../fixtures/stage/thread-33.json';
import type { StagePayload } from '../lib/engine/stage';
import { initialStage, stageReducer, type StageSize, type StageState } from '../lib/stageState';
import { Stage } from './Stage';

const measured = payloadJson as unknown as StagePayload;

/** A thread that exists and has measured nothing. The shape is the engine's;
 *  see `AnEmptyThreadIsEmptyAndNotZeroTest` in the Python suite, which locks
 *  it on the other side of the wire. */
const empty: StagePayload = {
  ...measured,
  thread_id: 999,
  baseline_run_id: null,
  runs: [],
  comparisons: {},
  sandboxes: [],
  diagnosis: {
    thread_id: 999,
    thread_name: null,
    ledger: 'docs/diagnosis_engine.yaml',
    generated_at: '2026-09-02T00:00:00+00:00',
    verdict: { outcome: null, say: null, gates: {}, fact_origins: {} },
    facts: [],
    storms: [],
  },
};

const SIZES: StageSize[] = ['row', 'split', 'window'];

function Harness({
  payload,
  size,
  start,
}: {
  payload: StagePayload;
  size: StageSize;
  start?: Partial<StageState>;
}) {
  const [state, dispatch] = useReducer(stageReducer, undefined, () => ({
    ...initialStage(),
    ...start,
  }));
  return (
    <Stage
      payload={payload}
      state={state}
      dispatch={dispatch}
      size={size}
      recall={null}
      carve={null}
    />
  );
}

afterEach(() => cleanup());

describe('the Stage renders no way to write', () => {
  for (const [name, payload] of [
    ['thread 33', measured],
    ['a thread that measured nothing', empty],
  ] as const) {
    for (const size of SIZES) {
      it(`offers no writable control for ${name} at size ${size}`, () => {
        const { container } = render(<Harness payload={payload} size={size} />);

        expect(container.querySelectorAll('input')).toHaveLength(0);
        expect(container.querySelectorAll('textarea')).toHaveLength(0);
        expect(container.querySelectorAll('form')).toHaveLength(0);
        expect(container.querySelectorAll('[contenteditable="true"]')).toHaveLength(0);
        expect(container.querySelectorAll('button[type="submit"]')).toHaveLength(0);
      });
    }
  }

  it('draws every panel without a writable control', () => {
    for (const panel of ['bench', 'sandbox', 'progression', 'gates', 'retrieval'] as const) {
      cleanup();
      const { container } = render(
        <Harness payload={measured} size="window" start={{ panel }} />,
      );
      expect(
        container.querySelectorAll('input, textarea, form, [contenteditable="true"]'),
      ).toHaveLength(0);
    }
  });
});

describe('the Stage issues nothing but GETs', () => {
  let seen: { url: string; method: string }[];

  beforeEach(() => {
    seen = [];
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        seen.push({
          url: String(input),
          method: (init?.method ?? 'GET').toUpperCase(),
        });
        return Promise.resolve(
          new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }),
        );
      }),
    );
  });

  afterEach(() => vi.unstubAllGlobals());

  it('stays a reader while a person clicks a run, changes size and opens a panel', () => {
    for (const size of SIZES) {
      cleanup();
      function Driven() {
        const [state, dispatch] = useReducer(stageReducer, undefined, initialStage);
        return (
          <>
            <Stage
              payload={measured}
              state={state}
              dispatch={dispatch}
              size={size}
              recall={null}
              carve={null}
            />
            <button type="button" onClick={() => dispatch({ type: 'pick', runId: 45 })}>
              drive:pick
            </button>
            <button type="button" onClick={() => dispatch({ type: 'panel', panel: 'gates' })}>
              drive:panel
            </button>
          </>
        );
      }
      render(<Driven />);

      fireEvent.click(screen.getByText('drive:pick'));
      fireEvent.click(screen.getByText('drive:panel'));
      for (const option of screen.getAllByRole('option').slice(0, 3)) {
        fireEvent.click(option);
      }
    }

    // THE ASSERTION THAT KEEPS THIS TEST HONEST. `Stage` is rendered with a
    // payload already in hand, so on today's code it issues no request at
    // all - and "every request was a GET" over an empty list is a test that
    // cannot fail. So the empty case is asserted as itself: the Stage made
    // no request, and IF it ever makes one, every one must be a GET. The day
    // somebody gives the Stage its own fetch, the first line fails and names
    // this comment.
    expect(
      seen,
      'the Stage issued a request while drawing a payload it was handed',
    ).toEqual([]);
    for (const call of seen) {
      expect(call.method, `${call.method} ${call.url}`).toBe('GET');
    }
  });
});

describe('an empty Stage invents no figure', () => {
  /**
   * MEASURED, not guessed. The first version of this test scanned for cells
   * matching `td, .stage__cell, .stage__num` and asserted none of them read
   * `0` - and matched NOTHING, so it passed by looking at an empty list. The
   * Stage was then rendered and read: on an empty payload it draws its
   * chrome, the lattice, the legend and the glossary, and where a figure
   * would go it writes an em dash. That is the thing worth locking, and it
   * is `docs/DESIGN_DIRECTIVES.md` page 13.5 rule 2 - a value nobody
   * measured is an em dash, never a zero - rendered.
   */
  it('writes an em dash where a figure would go, and no zero anywhere', () => {
    for (const size of SIZES) {
      cleanup();
      const { container } = render(<Harness payload={empty} size={size} />);
      const text = (container.textContent ?? '').replace(/\s+/g, ' ');

      expect(text, `size ${size} drew no em dash`).toContain('—');
      /* 2026-09-19: "no target stated" is gone, and with it "selected · run —".
         Two eyebrows about two absences, stacked, under a panel with nothing
         selected. What an empty Stage says now is the one thing a person can
         act on - and it is still not a zero, which is what this test is for. */
      expect(text).toContain('no run selected');
      expect(text).not.toContain('no target stated');

      // PER ELEMENT, NOT OVER textContent. The first version of this check
      // ran a whitespace-anchored regex over the whole concatenated text, and
      // a deliberate `<span>0%</span>` mutation walked straight through it -
      // `textContent` glues neighbours together, so the zero never had a
      // space on either side. Leaf elements are what a person actually reads
      // as a cell, so they are what is checked.
      const leaves = Array.from(container.querySelectorAll('*')).filter(
        (node) => node.children.length === 0,
      );
      expect(leaves.length, 'nothing was rendered to check').toBeGreaterThan(0);
      for (const leaf of leaves) {
        const own = (leaf.textContent ?? '').trim();
        expect(
          own,
          `a cell read "${own}" on a thread that measured nothing`,
        ).not.toMatch(/^0(\.0+)?%?$/);
      }
    }
  });

  it('names no run when there are no runs', () => {
    render(<Harness payload={empty} size="window" />);
    expect(screen.queryAllByRole('option')).toHaveLength(0);
  });
});
