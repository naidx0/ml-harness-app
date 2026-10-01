import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

/**
 * A SUPERVISED RESTART IS A RESTART.
 *
 * The app spawns the engine and supervises it. Ask that engine to exit and the
 * supervisor has a new one on the port before `bootstrap` gets there - so
 * bootstrap answers `already_running: true, started: false`, which is a
 * SUCCESSFUL replacement described accurately.
 *
 * `restartEngineNow` only reloaded on `started`, so it read that as a failure,
 * printed bootstrap's "an ML Harness engine is already answering" into the
 * banner, and never reloaded. The banner can only clear on a reload. Max,
 * 2026-09-21: *"i restarted tghe button like 10 times, we never had this
 * poroiblem what broke"* - and he was right that it was new: I shipped both
 * the banner and the button the night before.
 *
 * `startEngineNow`, two functions away, has always accepted either flag.
 */

const nativeRestartEngine = vi.fn();
vi.mock('./shell', () => ({
  hasNativeShell: () => true,
  nativeEngineFetch: vi.fn(),
  nativeStartEngine: vi.fn(),
  nativeRestartEngine: () => nativeRestartEngine(),
}));

import { restartEngineNow } from './liveness';

const reload = vi.fn();
let original: Location;

beforeEach(() => {
  nativeRestartEngine.mockReset();
  reload.mockReset();
  original = window.location;
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { ...original, reload },
  });
});

afterEach(() => {
  Object.defineProperty(window, 'location', { configurable: true, value: original });
});

const boot = (over: Record<string, unknown>) => ({
  started: false,
  already_running: false,
  interpreter: null,
  detail: '',
  ...over,
});

describe('restarting the engine', () => {
  it('reloads when this window started the new one', async () => {
    nativeRestartEngine.mockResolvedValue(boot({ started: true }));
    expect(await restartEngineNow()).toBeNull();
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('reloads when the supervisor beat us to it', async () => {
    /* The case that cost ten presses. */
    nativeRestartEngine.mockResolvedValue(
      boot({
        already_running: true,
        detail: 'an ML Harness engine is already answering on 8078.',
      }),
    );
    expect(await restartEngineNow()).toBeNull();
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('reports the reason and does NOT reload when nothing is answering', async () => {
    nativeRestartEngine.mockResolvedValue(
      boot({ detail: 'no interpreter could start an engine' }),
    );
    expect(await restartEngineNow()).toContain('no interpreter');
    expect(reload).not.toHaveBeenCalled();
  });

  it('says something rather than nothing when the shell answers nothing', async () => {
    nativeRestartEngine.mockResolvedValue(null);
    expect(await restartEngineNow()).toBeTruthy();
    expect(reload).not.toHaveBeenCalled();
  });
});
