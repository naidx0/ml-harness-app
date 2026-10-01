/**
 * THE STRIP ITSELF: what it draws, and what clicking it does.
 *
 * WHAT THIS COVERS AND WHAT IT DOES NOT, stated because the gap matters. The
 * decision of which rows fold is `lib/foldTheToolRows.ts` and has its own
 * tests. This is the component. The WIRING between them - the three lines in
 * `Transcript.tsx` that return a strip beside an opened row - is typechecked
 * and not rendered by any test: `Transcript` takes eighteen props including a
 * live `runTool`, and a harness that fabricated all of them would be a fixture
 * asserting against itself. I would rather name that gap than imply it is
 * closed.
 */

import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ToolStrip } from './ToolStrip';
import type { ToolItem } from '../lib/transcript';
import type { ToolControl } from '../lib/engine/types';

afterEach(cleanup);

const call = (name: string, state = 'ok'): ToolItem =>
  ({ kind: 'tool', key: `k-${name}`, id: 1, callId: name, name, args: {}, drivenBy: null, state, result: {} }) as ToolItem;

const roster = new Map<string, ToolControl>([
  ['inspect_hardware', { group: 'Look' } as ToolControl],
]);

describe('what the strip says', () => {
  it('draws one button per call, named for the tool', () => {
    render(
      <ToolStrip
        run={[call('inspect_hardware'), call('list_runs')]}
        tools={roster}
        working={false}
        opened={new Set()}
        onToggle={() => {}}
      />,
    );
    expect(screen.getByLabelText('Show the inspect_hardware call')).toBeTruthy();
    expect(screen.getByLabelText('Show the list_runs call')).toBeTruthy();
  });

  it('counts the steps when the turn is over', () => {
    render(
      <ToolStrip
        run={[call('a'), call('b'), call('c')]}
        tools={roster}
        working={false}
        opened={new Set()}
        onToggle={() => {}}
      />,
    );
    expect(screen.getByText('3 steps')).toBeTruthy();
  });

  it('names the failures rather than hiding them in a count', () => {
    /* A folded run must not make a failed call quieter than it was. */
    render(
      <ToolStrip
        run={[call('a'), call('b', 'error')]}
        tools={roster}
        working={false}
        opened={new Set()}
        onToggle={() => {}}
      />,
    );
    expect(screen.getByText('2 steps, 1 failed')).toBeTruthy();
  });

  it('says what is running, not a count, while the turn is going', () => {
    /* Max asked for "an animated loading or ASCII spinner working while the
       model thinks". A count that is still climbing is not that. */
    const { container } = render(
      <ToolStrip
        run={[call('a'), call('read_gpu_prices')]}
        tools={roster}
        working
        opened={new Set()}
        onToggle={() => {}}
      />,
    );
    expect(screen.getByText('read_gpu_prices')).toBeTruthy();
    expect(container.querySelector('.toolstrip__pulse')).not.toBeNull();
  });

  it('shows no spinner when nothing is running', () => {
    const { container } = render(
      <ToolStrip
        run={[call('a'), call('b')]}
        tools={roster}
        working={false}
        opened={new Set()}
        onToggle={() => {}}
      />,
    );
    expect(container.querySelector('.toolstrip__pulse')).toBeNull();
  });
});

describe('clicking an icon', () => {
  it('asks for that call by key, and opens nothing itself', () => {
    /* THE STRIP DRAWS NO TOOL ROW. The row expands where it always was, so a
       second approval button cannot exist to disagree with the first. */
    const onToggle = vi.fn();
    render(
      <ToolStrip
        run={[call('inspect_hardware')]}
        tools={roster}
        working={false}
        opened={new Set()}
        onToggle={onToggle}
      />,
    );
    fireEvent.click(screen.getByLabelText('Show the inspect_hardware call'));
    expect(onToggle).toHaveBeenCalledWith('k-inspect_hardware');
  });

  it('marks an opened call as pressed', () => {
    render(
      <ToolStrip
        run={[call('inspect_hardware')]}
        tools={roster}
        working={false}
        opened={new Set(['k-inspect_hardware'])}
        onToggle={() => {}}
      />,
    );
    expect(
      screen.getByLabelText('Show the inspect_hardware call').getAttribute('aria-pressed'),
    ).toBe('true');
  });
});

describe('a tool the roster has not loaded yet', () => {
  it('still gets an icon', () => {
    /* The transcript renders before `/api/tools` answers on a cold start, and
       an icon-less strip is worse than a generic one. */
    const { container } = render(
      <ToolStrip
        run={[call('something_new'), call('other')]}
        tools={new Map()}
        working={false}
        opened={new Set()}
        onToggle={() => {}}
      />,
    );
    expect(container.querySelectorAll('.toolstrip__icon svg').length).toBe(2);
  });
});

describe('the fold says how long the turn took', () => {
  /* Max, 2026-09-14, via the ai-agent-response vetting: that component's
     collapsed phase reads "Worked for 19 seconds" where ours read "6 steps",
     and our measured duration lived one line further down on the metarow. One
     turn's identity was split across two lines and the fold - the line people
     actually read - was the half without the number. */
  it('prints the measured seconds beside the count, rounded, exact on the hover', () => {
    render(
      <ToolStrip
        run={[call('inspect_hardware'), call('list_runs')]}
        tools={new Map()}
        working={false}
        seconds={19.4}
        opened={new Set()}
        onToggle={() => {}}
      />,
    );
    const said = screen.getByText(/2 steps/);
    expect(said.textContent).toBe('2 steps · 19s');
    expect(said.getAttribute('title')).toBe('2 steps in 19.4s');
  });

  it('says nothing at all when the turn has not ended', () => {
    /* `null` is not zero. A turn whose duration has not landed has no
       duration, and `0s` would be a measurement nobody took. */
    render(
      <ToolStrip
        run={[call('inspect_hardware')]}
        tools={new Map()}
        working={false}
        seconds={null}
        opened={new Set()}
        onToggle={() => {}}
      />,
    );
    const said = screen.getByText(/1 steps/);
    expect(said.textContent).toBe('1 steps');
    expect(said.getAttribute('title')).toBeNull();
  });
});
