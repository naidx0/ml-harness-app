/**
 * The to-do is something you can use, and un-parking is the person's call.
 *
 * Max, 2026-09-14: *"have the to-do also interactable so that I can actually
 * interact and ask the agent about the to-do, and instruct him to do things,
 * and make sure the agent can see and interact with the list and goal as
 * well."*
 *
 * The agent's half already existed and is tested elsewhere: the open steps are
 * on every build prompt (`conductor._plan_note`), `mark_step_done` ticks one and
 * `planning.park_step` parks one. This file is the PERSON'S half, and the thing
 * worth pinning about it is that neither button invents a message. Work sends
 * the person's own words; Ask puts words in the box for them to finish. A
 * transcript that showed a sentence nobody typed would be a transcript that
 * lies about who asked for the next nine minutes of work - the same rule
 * `theBuildKeepsGoing.ts` gives for never fabricating a "continue".
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { GoalBar, stepRows, unpark } from './GoalBar';

afterEach(cleanup);

const PLAN = [
  '# Train the router',
  '',
  '## Phase 1 - Data',
  '- [x] Carve the eval set',
  '- [!] Measure the baseline — parked: no model is connected',
  '- [ ] Compare the adapter',
].join('\n');

function draw(over: Partial<Record<string, unknown>> = {}) {
  const props: Record<string, unknown> = {
    threadId: 1,
    mode: 'build',
    plan: PLAN,
    planPath: null,
    items: [],
    running: false,
    failed: false,
    lastEventId: 0,
    onContinue: async () => {},
    onOpenPlan: () => {},
    onOpenThread: () => {},
    onSay: vi.fn(),
    onDraft: vi.fn(),
    onPlan: vi.fn(),
    ...over,
  };
  const Card = GoalBar as unknown as (p: Record<string, unknown>) => React.ReactElement;
  render(<Card {...props} />);
  return props as {
    onSay: ReturnType<typeof vi.fn>;
    onDraft: ReturnType<typeof vi.fn>;
    onPlan: ReturnType<typeof vi.fn>;
  };
}

describe('un-parking is the person deciding to try again', () => {
  it('puts the one named step back on the list and drops its reason', () => {
    const back = unpark(PLAN, 'Measure the baseline');
    expect(stepRows(back).map((row) => row.state)).toEqual(['done', 'open', 'open']);
    expect(back).not.toContain('parked:');
    expect(back).toContain('- [ ] Measure the baseline');
    /* The ticked step is untouched - un-parking is not a reset. */
    expect(back).toContain('- [x] Carve the eval set');
  });

  it('matches the whole step, so a substring is not the one that changes', () => {
    const two = [
      '- [!] Measure — parked: a',
      '- [!] Measure the baseline — parked: b',
    ].join('\n');
    const back = unpark(two, 'Measure');
    expect(back).toContain('- [ ] Measure');
    expect(back).toContain('- [!] Measure the baseline — parked: b');
  });

  it('leaves a plan alone when nothing matches', () => {
    expect(unpark(PLAN, 'A step that is not there')).toBe(PLAN);
    expect(unpark(null, 'anything')).toBe('');
  });
});

describe('what the buttons on a step do', () => {
  it('Work sends the person words, and never invents a continue', () => {
    /* The disclosure is named by the plan's own title - that IS its label. */
    const props = draw();
    fireEvent.click(screen.getByRole('button', { name: /Train the router/ }));
    const work = screen.getAllByTitle(/Ask the agent to do this step now/)[0];
    fireEvent.click(work);
    expect(props.onSay).toHaveBeenCalledWith('Work this step now: Measure the baseline');
    /* It did not also quietly save a plan or start a run. */
    expect(props.onPlan).not.toHaveBeenCalled();
  });

  it('Ask fills the chat box rather than sending, because a question needs a second half', () => {
    const props = draw();
    fireEvent.click(screen.getByRole('button', { name: /Train the router/ }));
    fireEvent.click(screen.getAllByTitle(/Ask the agent about this step/)[0]);
    expect(props.onDraft).toHaveBeenCalledWith('About the step "Carve the eval set": ');
    expect(props.onSay).not.toHaveBeenCalled();
  });

  it('Unpark saves the plan with that step open', () => {
    const props = draw();
    fireEvent.click(screen.getByRole('button', { name: /Train the router/ }));
    fireEvent.click(screen.getByTitle(/Put this step back on the list/));
    expect(props.onPlan).toHaveBeenCalledTimes(1);
    const saved = props.onPlan.mock.calls[0][0] as string;
    expect(saved).toContain('- [ ] Measure the baseline');
    expect(saved).not.toContain('parked:');
  });

  it('a ticked step is not offered Work - there is nothing to do', () => {
    draw();
    fireEvent.click(screen.getByRole('button', { name: /Train the router/ }));
    const works = screen.getAllByTitle(/Ask the agent to do this step now/);
    expect(works.map((one) => one.getAttribute('title'))).toEqual([
      'Ask the agent to do this step now: Measure the baseline',
      'Ask the agent to do this step now: Compare the adapter',
    ]);
    /* Unpark is offered on the parked one only. */
    expect(screen.getAllByTitle(/Put this step back on the list/).length).toBe(1);
  });
});

describe('CS12 — X hides the bar and keeps the plan', () => {
  it('Hide goal removes the bar without calling onPlan', async () => {
    const { hideGoalBar, isGoalBarHidden, showGoalBar } = await import(
      '../lib/goalBarVisibility'
    );
    showGoalBar();
    const props = draw();
    fireEvent.click(screen.getByRole('button', { name: 'Hide goal' }));
    expect(isGoalBarHidden()).toBe(true);
    expect(props.onPlan).not.toHaveBeenCalled();
    expect(screen.queryByText('Train the router')).toBeNull();
    hideGoalBar(); /* already hidden */
    showGoalBar();
  });
});
