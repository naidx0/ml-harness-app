/**
 * A+C dock: Build flips without confirm and without starting a run.
 * Autonomy is in the mode (Build = ask, Full = full).
 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const setThreadMode = vi.fn(async (..._args: unknown[]) => ({}));
const setThreadPlan = vi.fn(async (..._args: unknown[]) => ({}));
const setThreadPermission = vi.fn(async (..._args: unknown[]) => ({}));
const startRun = vi.fn(async (..._args: unknown[]) => ({}));

vi.mock('../lib/engine/client', () => ({
  setThreadMode: (threadId: number, mode: string) => setThreadMode(threadId, mode),
  setThreadPlan: (threadId: number, plan: string | null) => setThreadPlan(threadId, plan),
  setThreadPermission: (threadId: number, mode: string) =>
    setThreadPermission(threadId, mode),
  startRun: (threadId: number) => startRun(threadId),
}));

import { ModeSwitch } from './ModeSwitch';

afterEach(() => {
  cleanup();
  setThreadMode.mockClear();
  setThreadPlan.mockClear();
  setThreadPermission.mockClear();
  startRun.mockClear();
});

describe('ModeSwitch Build does not auto-start a run', () => {
  it('switches to build + ask without confirm or startRun', async () => {
    const plan = ['# Goal', '', '- [ ] First open step'].join('\n');
    render(
      <ModeSwitch
        threadId={7}
        mode="plan"
        permission="ask"
        plan={plan}
        planDraft={null}
        onChanged={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Mode' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Build' }));
    await waitFor(() => expect(setThreadMode).toHaveBeenCalledWith(7, 'build'));
    expect(setThreadPermission).toHaveBeenCalledWith(7, 'ask');
    expect(startRun).not.toHaveBeenCalled();
  });

  it('Full sets build mode and permission full', async () => {
    render(
      <ModeSwitch
        threadId={7}
        mode="plan"
        permission="ask"
        plan="# Goal\n\n- [ ] x"
        planDraft={null}
        onChanged={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Mode' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Full' }));
    await waitFor(() => expect(setThreadPermission).toHaveBeenCalledWith(7, 'full'));
    expect(setThreadMode).toHaveBeenCalledWith(7, 'build');
    expect(startRun).not.toHaveBeenCalled();
  });
});
