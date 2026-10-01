/**
 * The strip says who is working, and never says more than it knows.
 *
 * Two things are worth pinning here and neither is styling. FIRST, a finished
 * sub-agent must not read as a success when it parked its way to the end -
 * the same defect Max photographed in the run's own ending on 2026-09-13, one
 * surface over. SECOND, the strip must never carry a child's words: that is
 * the whole economy of delegation (`app/subagents.py`), and a component that
 * quietly started rendering a transcript would undo it silently.
 */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { endingInWords, SubAgentStrip } from './SubAgentStrip';
import { ContextRing, dialPath } from './Spinner';
import type { SubAgent, SubAgentRead } from '../lib/engine/subagents';

afterEach(cleanup);

function one(over: Partial<SubAgent> = {}): SubAgent {
  return {
    id: 1,
    thread_id: 42,
    phase: 'Phase 1 - Data',
    state: 'running',
    reason: '',
    detail: '',
    harvested: false,
    turns: 3,
    seconds: 74,
    steps: 4,
    done: 1,
    open: 3,
    parked: [],
    started_at: '2026-09-13 10:00:00',
    updated_at: '2026-09-13 10:01:14',
    ...over,
  };
}

function read(over: Partial<SubAgentRead> = {}): SubAgentRead {
  return {
    thread_id: 7,
    subagents: [one()],
    running: 1,
    running_anywhere: 1,
    at_most: 2,
    ...over,
  };
}

describe('the strip says who is working', () => {
  it('draws nothing when nothing has been handed out', () => {
    const { container } = render(
      <SubAgentStrip read={read({ subagents: [], running: 0 })} onOpen={() => {}} onStop={() => {}} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('names the phase, the progress and how long', () => {
    render(<SubAgentStrip read={read()} onOpen={() => {}} onStop={() => {}} />);
    expect(screen.getByText('Phase 1 - Data')).toBeTruthy();
    expect(screen.getByText('1 of 4')).toBeTruthy();
    expect(screen.getByText('1m 14s')).toBeTruthy();
    expect(screen.getByText('1 sub-agent working')).toBeTruthy();
  });

  it('shows one pip per slot the machine has, lit for what is in use', () => {
    const { container } = render(
      <SubAgentStrip read={read()} onOpen={() => {}} onStop={() => {}} />,
    );
    const pips = container.querySelectorAll('.subagents__pip');
    expect(pips.length).toBe(2);
    expect(pips[0].getAttribute('data-lit')).toBe('yes');
    expect(pips[1].getAttribute('data-lit')).toBeNull();
  });

  it('says when the other slot is spent in a different conversation', () => {
    /* The cap is on the machine. A person looking at one chat and seeing one
       sub-agent would otherwise wonder why a second will not start. */
    render(
      <SubAgentStrip read={read({ running_anywhere: 2 })} onOpen={() => {}} onStop={() => {}} />,
    );
    expect(screen.getByText(/1 more in another chat/)).toBeTruthy();
  });

  it('opens the child conversation rather than showing its transcript', () => {
    const onOpen = vi.fn();
    render(<SubAgentStrip read={read()} onOpen={onOpen} onStop={() => {}} />);
    screen.getByTitle(/open this sub-agent/).click();
    expect(onOpen).toHaveBeenCalledWith(42);
  });

  it('a clipped phase name is on the hover, in full and first', () => {
    /* Max, 2026-09-13: "if the text isn't fitting it should show the dot dot
       dot, and when you hover you can see the whole extent." */
    const long = 'Phase 4 - ' + 'reconcile the retriever against the baseline '.repeat(6);
    render(
      <SubAgentStrip read={read({ subagents: [one({ phase: long })] })} onOpen={() => {}} onStop={() => {}} />,
    );
    const row = screen.getByRole('button', { name: /reconcile the retriever/ });
    expect(row.getAttribute('title')?.startsWith(long)).toBe(true);
  });

  it('offers stop only while it is working', () => {
    const onStop = vi.fn();
    const { rerender } = render(
      <SubAgentStrip read={read()} onOpen={() => {}} onStop={onStop} />,
    );
    screen.getByTitle(/Stop this sub-agent/).click();
    expect(onStop).toHaveBeenCalledWith(1);

    rerender(
      <SubAgentStrip
        read={read({ subagents: [one({ state: 'done' })], running: 0, running_anywhere: 0 })}
        onOpen={() => {}}
        onStop={onStop}
      />,
    );
    expect(screen.queryByTitle(/Stop this sub-agent/)).toBeNull();
  });
});

describe('a finished sub-agent says how it finished', () => {
  it('parking its way to the end is not "all done"', () => {
    expect(endingInWords(one({ state: 'done', done: 4, steps: 4, parked: [] }))).toBe('all 4 done');
    expect(
      endingInWords(
        one({ state: 'done', done: 2, steps: 4, parked: [{ step: 'a', why: 'no rows' }, { step: 'b', why: 'no rows' }] }),
      ),
    ).toBe('2 done, 2 parked');
    expect(
      endingInWords(one({ state: 'done', done: 0, steps: 2, parked: [{ step: 'a', why: 'no rows' }] })),
    ).toBe('nothing could be done');
  });

  it('a failure and a stop are told apart', () => {
    expect(endingInWords(one({ state: 'failed' }))).toBe('it failed');
    expect(endingInWords(one({ state: 'stopped' }))).toBe('stopped');
  });

  it('a working one says nothing about how it ended', () => {
    expect(endingInWords(one())).toBe('');
  });
});

describe('the context wheel is a drawing, and the spinner is not', () => {
  /* Max, 2026-09-13: "the blue context wheel... looks very low res" - it was
     a conic gradient, whose hard colour stop is an unantialiased staircase at
     eleven pixels. It is a stroked path now.

     THE SPINNER IS NOT HERE ON PURPOSE. It was drawn too, for one day, and
     Max, 2026-09-14: "for loading and working keep our thinking and reasoning
     spinner in ascii as well." The braille orbit is the product's word for
     working; the rail spins the same glyph the transcript does. */
  it('the ring IS the application mark, to the master’s own numbers', () => {
    /* THE TIE, AND IT IS A NUMBER RATHER THAN A RESEMBLANCE.
       `src-tauri/icons/icon.svg` fills its dial to 0.757 and its blue arc
       ends, on the 24 grid, at (16.66, 8.47) - which is exactly the endpoint
       `Icon.tsx`'s `mark` glyph draws. If this component ever stops being
       that drawing, this is the assertion that says so. */
    const ends = (share: number) =>
      dialPath(share).split(' 1 ')[1].split(' ').map(Number);
    const [x, y] = ends(0.757);
    /* Within a fiftieth of a unit on a 24 grid - the master's endpoint is
       16.6547, 8.4727 and `Icon.tsx` rounded it to 16.66, 8.47. */
    expect(Math.abs(x - 16.6547)).toBeLessThan(0.02);
    expect(Math.abs(y - 8.4727)).toBeLessThan(0.02);
    /* And the empty and full ends are the dial's own, 200 and 340 degrees. */
    expect(dialPath(0)).toContain('M4.56 12.17');
    expect(dialPath(1)).toContain('19.44 12.17');
  });

  it('the dial fills from the left, and out of range is clamped not wrapped', () => {
    const endOf = (share: number) => dialPath(share).split('1 ')[1];
    expect(endOf(1.4)).toBe(endOf(1));
    expect(endOf(-1)).toBe(endOf(0));
    expect(endOf(Number.NaN)).toBe(endOf(0));
    /* Half the sweep is 70 degrees on, which is the top of the dial. */
    expect(endOf(0.5)).toBe('12.00 6.96');
  });

  it('an empty dial draws its track and no reading', () => {
    const { container } = render(<ContextRing share={0} size={15} />);
    expect(container.querySelector('.ctxring__track')).toBeTruthy();
    expect(container.querySelector('.ctxring__arc')).toBeNull();
  });
});
