/**
 * The first test this frontend has ever had.
 *
 * `docs/PHASES.md` step 9 asked for a runner and one smoke test. This is the
 * smoke test, and it is deliberately about a REAL question rather than
 * `expect(1 + 1).toBe(2)`: does the studios card draw what the engine sent,
 * and does it draw nothing at all when the engine did not answer.
 *
 * WHAT A TEST LIKE THIS IS FOR, AND WHAT IT IS NOT FOR. `AGENTS.md`: "A UI
 * change is not done until someone has looked at it. Three real defects here —
 * a run-on Goal/Method/Quantization line, a hard vertical seam where the
 * background stopped at the text column, and a live reflected XSS — passed
 * every DOM assertion and were caught only by a screenshot." All three are
 * still invisible from here. What is visible from here is the other class: a
 * card that renders the wrong count, a component that invents a list when the
 * request failed, a label that stops matching the data behind it. Those are
 * cheap to catch and expensive to catch in a browser, which is the whole
 * division of labour.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';

import { StudiosCard } from './Studios';
import { forgetStudios } from '../lib/useStudios';
import * as client from '../lib/engine/client';

const PACKS = {
  packs: {
    ledger: "the engine's own doors, and the evidence door",
    agent: 'somebody else’s agent, read rather than run',
  },
  core: ['ledger'],
  capabilities: { 'agent.traces.read': 'read an agent’s traces' },
  pack_index: {
    ledger: ['run_diagnosis', 'propose_build'],
    agent: ['read_agent_traces', 'read_tool_definitions'],
  },
};

afterEach(() => {
  cleanup();
  /* The hook caches for the page's lifetime on purpose — see its docstring —
     so each test starts by forgetting, not by hoping. */
  forgetStudios();
  vi.restoreAllMocks();
});

describe('the studios card', () => {
  it('draws the packs the engine sent, and counts them', async () => {
    vi.spyOn(client, 'listStudios').mockResolvedValue(PACKS);

    render(<StudiosCard />);

    expect(await screen.findByText('agent')).toBeTruthy();
    expect(screen.getByText('ledger')).toBeTruthy();
    /* Two packs, four tools — arithmetic over what arrived, never a constant. */
    expect(screen.getByText('2 packs · 4 tools')).toBeTruthy();
  });

  it('marks the core packs and only those', async () => {
    vi.spyOn(client, 'listStudios').mockResolvedValue(PACKS);

    render(<StudiosCard />);
    await screen.findByText('agent');

    expect(screen.getAllByText('core')).toHaveLength(1);
  });

  it('lists a pack’s tools only once its row is opened', async () => {
    const user = { click: (el: Element) => el.dispatchEvent(new MouseEvent('click', { bubbles: true })) };
    vi.spyOn(client, 'listStudios').mockResolvedValue(PACKS);

    render(<StudiosCard />);
    const row = await screen.findByText('agent');

    expect(screen.queryByText('read_agent_traces')).toBeNull();
    user.click(row);
    await waitFor(() => expect(screen.getByText('read_agent_traces')).toBeTruthy());
  });

  it('lists nothing when the engine did not answer', async () => {
    /* The one that matters most. A studios card that renders a plausible set of
       packs when the request failed is the interface making a claim about a
       registry it has not read. */
    vi.spyOn(client, 'listStudios').mockRejectedValue(new Error('engine is not running'));

    render(<StudiosCard />);

    expect(await screen.findByText(/engine is not running/)).toBeTruthy();
    expect(screen.queryByText('ledger')).toBeNull();
    expect(screen.queryByText(/packs ·/)).toBeNull();
  });
});
