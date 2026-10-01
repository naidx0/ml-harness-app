import { describe, expect, it, vi, beforeEach } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

/**
 * THE APP IS ONE PACKAGE, AND RESTARTING ITS ENGINE IS A BUTTON.
 *
 * The banner could say "the engine is not running this checkout's code" and
 * then had nothing to offer but two shell commands - `python
 * scripts/launch.py --stop`, then `python scripts/launch.py`. Max, 2026-09-21,
 * with a photo of exactly that: *"we seem to have lost the restart engine on
 * the app button, the whole thing with the app should be one package, and the
 * engine should be easy for people to restart, they shouldn't be running
 * scripts on their own."*
 *
 * Why there was no button: `start_engine` refuses while an engine is
 * answering, and the shell would only stop a child IT had spawned - correct on
 * its own, since a window must not kill a process a terminal owns. Between
 * them they left the one case the window can actually see. The engine now
 * stops ITSELF, for a caller holding the token it published.
 */

const restartEngineNow = vi.fn(async () => null as string | null);
const startEngineNow = vi.fn(async () => {});
let liveness: { kind: string; severity: string; headline: string; detail: string; action: string | null };

vi.mock('../lib/engine/liveness', () => ({
  restartEngineNow: () => restartEngineNow(),
  startEngineNow: () => startEngineNow(),
}));
vi.mock('../lib/engine/shell', () => ({ hasNativeShell: () => true }));
vi.mock('../lib/useEngineLiveness', () => ({
  useEngineLiveness: () => ({ state: liveness, dismissed: false, dismiss: () => {} }),
}));

import { EngineNotice } from './EngineNotice';

const stale = {
  kind: 'stale',
  severity: 'warn',
  headline: 'The engine is not running this checkout’s code.',
  detail: 'engine c467f06b · page d5dd107',
  action: 'Restart it to run this build.',
};

beforeEach(() => {
  /* `globals: false` in the vite config means testing-library never registered
     its automatic afterEach, so without this every render stacks in the same
     document and a second query finds two buttons. */
  cleanup();
  restartEngineNow.mockClear();
  liveness = { ...stale };
});

describe('an engine on the wrong code', () => {
  it('offers a button rather than a command to type', () => {
    render(<EngineNotice />);
    expect(screen.getByRole('button', { name: /restart the engine/i })).toBeTruthy();
  });

  it('never tells the person to run a script', () => {
    const { container } = render(<EngineNotice />);
    const text = container.textContent ?? '';
    expect(text).not.toContain('scripts/launch.py');
    expect(text).not.toContain('python ');
  });

  it('presses through to the shell', async () => {
    render(<EngineNotice />);
    screen.getByRole('button', { name: /restart the engine/i }).click();
    await vi.waitFor(() => expect(restartEngineNow).toHaveBeenCalledTimes(1));
  });

  it('shows why when the restart did not take, and does not reload', async () => {
    restartEngineNow.mockResolvedValueOnce('the engine on 8078 refused to stop');
    render(<EngineNotice />);
    screen.getByRole('button', { name: /restart the engine/i }).click();
    await vi.waitFor(() =>
      expect(screen.getByRole('alert').textContent).toContain('refused to stop'),
    );
  });

  it('offers start, not restart, when there is no engine to replace', () => {
    liveness = { ...stale, kind: 'gone', headline: 'The engine is not running.' };
    render(<EngineNotice />);
    expect(screen.getByRole('button', { name: /start the engine/i })).toBeTruthy();
    expect(screen.queryByRole('button', { name: /restart the engine/i })).toBeNull();
  });
});
