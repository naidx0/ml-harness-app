/**
 * The first run, from the page's side: a window that finds no engine ASKS.
 *
 * ── THE BUG THIS FILE EXISTS BECAUSE OF ──────────────────────────────────────
 *
 * `lib.rs` implemented `start_engine` and **nothing in the frontend ever called
 * it.** Measured 2026-08-28 by grepping for it: `liveness.ts` has a
 * `startEngineWatch`, which is a different thing entirely, and that was the
 * only match. So a packaged build on a clean machine would have opened a
 * window, read no `engine.json`, printed "no engine", and waited forever for
 * somebody with no terminal to start one — with a 47 MB uv sidecar sitting
 * beside the binary whose whole purpose was that moment.
 *
 * Every test below is about the seam between "there is no engine" and "so ask
 * the shell for one", because that seam is where the sidecar either earns its
 * place in the installer or does nothing at all.
 *
 * `vi.resetModules()` runs before each, because `askedTheShellToStart` is
 * module state on purpose — see `config.ts` — and a test that inherited it from
 * the test above would be asserting about the previous test's shell.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

type Invoke = (cmd: string, args?: unknown) => Promise<unknown>;

const A_LIVE_ENGINE = {
  base_url: 'http://127.0.0.1:8078',
  token: 'a-token-that-is-not-real',
  engine: { engine_id: 'abc', pid: 1 },
  checkout: null,
};

function withShell(invoke: Invoke) {
  (globalThis as unknown as Record<string, unknown>).__TAURI_INTERNALS__ = { invoke };
}

async function freshConfig() {
  vi.resetModules();
  return import('./config');
}

beforeEach(() => {
  vi.resetModules();
});

afterEach(() => {
  delete (globalThis as unknown as Record<string, unknown>).__TAURI_INTERNALS__;
});

describe('when the shell already has an engine', () => {
  it('does not ask it to start one', async () => {
    const invoke = vi.fn(async (cmd: string) => {
      if (cmd === 'engine_status') return A_LIVE_ENGINE;
      throw new Error(`start_engine must not be called: ${cmd}`);
    });
    withShell(invoke);

    const { engineSession } = await freshConfig();
    const session = await engineSession();

    expect(session.available).toBe(true);
    expect(invoke).toHaveBeenCalledTimes(1);
    expect(invoke).toHaveBeenCalledWith('engine_status');
  });
});

describe('when the shell has no engine, which is every first run', () => {
  it('asks it to start one and reads the engine that appears', async () => {
    let engineExists = false;
    const invoke = vi.fn(async (cmd: string) => {
      if (cmd === 'engine_status') {
        return engineExists
          ? A_LIVE_ENGINE
          : { error: 'no engine.json in any of ...' };
      }
      // THE SIDECAR'S WHOLE REASON: uv builds an interpreter and the engine
      // comes up, so the second status call finds what the first could not.
      engineExists = true;
      return {
        started: true,
        already_running: false,
        interpreter: 'C:/…/ml-harness/python/Scripts/python.exe',
        detail: 'no interpreter on this machine could run the engine, so uv made one.',
      };
    });
    withShell(invoke);

    const { engineSession } = await freshConfig();
    const session = await engineSession();

    expect(invoke.mock.calls.map((call) => call[0])).toEqual([
      'engine_status',
      'start_engine',
      'engine_status',
    ]);
    expect(session.available).toBe(true);
    expect(session.token).toBe(A_LIVE_ENGINE.token);
  });

  it('shows what the shell tried when it could not start one', async () => {
    withShell(async (cmd: string) => {
      if (cmd === 'engine_status') return { error: 'no engine.json anywhere' };
      return {
        started: false,
        already_running: false,
        interpreter: null,
        detail: 'no uv sidecar beside this binary. A packaged build ships one.',
      };
    });

    const { engineSession } = await freshConfig();
    const session = await engineSession();

    expect(session.available).toBe(false);
    // THE DETAIL AND NOT A SHRUG. "no engine" tells somebody nothing they can
    // act on; the sentence the shell wrote names what it looked for.
    expect(session.reason).toContain('no uv sidecar');
  });

  it('asks ONCE, however many times the session is re-resolved', async () => {
    // `refreshEngineSession` runs on every 401, and the token rotates on every
    // engine start. Without the guard, a stale token would mean a uv bootstrap
    // per failed request.
    const invoke = vi.fn(async (cmd: string) => {
      if (cmd === 'engine_status') return { error: 'still no engine' };
      return {
        started: false,
        already_running: false,
        interpreter: null,
        detail: 'nothing could start it',
      };
    });
    withShell(invoke);

    const { engineSession, refreshEngineSession } = await freshConfig();
    await engineSession();
    await refreshEngineSession();
    await refreshEngineSession();

    const starts = invoke.mock.calls.filter((call) => call[0] === 'start_engine');
    expect(starts).toHaveLength(1);
  });
});

describe('when there is no shell at all', () => {
  it('never reaches for start_engine, because a browser cannot spawn anything', async () => {
    const fetching = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response('{}', { status: 500 }));

    const { engineSession } = await freshConfig();
    const session = await engineSession();

    expect(session.available).toBe(false);
    fetching.mockRestore();
  });
});
