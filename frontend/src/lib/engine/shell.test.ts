/**
 * The native-shell seam, in both worlds — and today's world is the important one.
 *
 * `docs/THE_PLAN.md` Phase B lists "seven frontend files swapped" as the work
 * the Tauri shell needs. `shell.ts` makes that number one: everything the app
 * wants from a native host is asked for in that module, and the Rust side lands
 * by implementing two commands.
 *
 * **The half of this file that matters most asserts that nothing changed.** A
 * seam added before the other half exists is only safe if the build without it
 * behaves exactly as it did, and "exactly" is a claim a test makes rather than
 * a comment. So every function is driven with no shell present, and the answers
 * are the ones that keep the browser path intact.
 *
 * The other half drives a FAKE shell — an object shaped like Tauri's `invoke` —
 * because the real one cannot exist here: `cargo`, `rustc` and `rustup` are all
 * absent from this machine, measured, which is why Phase B is not built. A fake
 * cannot prove the Rust side is right. It CAN prove this side calls the command
 * names it says it calls, with the argument shape it says it uses, and handles
 * a rejection rather than propagating it — which is every mistake this file
 * could make on its own.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  hasNativeShell,
  nativeEngineStatus,
  nativePickPath,
  nativeStartEngine,
} from './shell';

type Invoke = (cmd: string, args?: unknown) => Promise<unknown>;

/** Pretend a Tauri v2 window is here, in whichever of the two shapes. */
function withShell(invoke: Invoke, flavour: 'internals' | 'global' = 'internals') {
  const host = globalThis as unknown as Record<string, unknown>;
  if (flavour === 'internals') host.__TAURI_INTERNALS__ = { invoke };
  else host.__TAURI__ = { core: { invoke } };
}

afterEach(() => {
  const host = globalThis as unknown as Record<string, unknown>;
  delete host.__TAURI_INTERNALS__;
  delete host.__TAURI__;
});

describe('with no shell, which is every build that exists today', () => {
  it('says there is no shell', () => {
    expect(hasNativeShell()).toBe(false);
  });

  it('answers null for the engine, so config.ts falls through to the dev server', () => {
    return expect(nativeEngineStatus()).resolves.toBeNull();
  });

  it('answers null for a path, so the composer leaves the field alone', () => {
    return expect(nativePickPath('directory')).resolves.toBeNull();
  });

  it('answers null for a start, so a browser never thinks it can spawn one', () => {
    return expect(nativeStartEngine()).resolves.toBeNull();
  });
});

describe('starting the engine, which is the whole of a first run', () => {
  it('calls start_engine and hands the bootstrap back verbatim', async () => {
    const invoke = vi.fn(async (cmd: string) => {
      expect(cmd).toBe('start_engine');
      return {
        started: true,
        already_running: false,
        interpreter: 'C:/Users/x/AppData/Local/ml-harness/python/Scripts/python.exe',
        detail: 'uv made one and the engine answered.',
      };
    });
    withShell(invoke);

    const answer = await nativeStartEngine();

    expect(invoke).toHaveBeenCalledOnce();
    expect(answer?.started).toBe(true);
    expect(answer?.interpreter).toContain('ml-harness');
  });

  it('turns a rejection into a detail rather than throwing', async () => {
    // A SHELL THAT IS THERE AND FAILED IS NOT A SHELL THAT IS ABSENT. If this
    // threw, `config.ts` would fall through to the dev-server path inside a
    // packaged app and tell somebody to run `npm run dev`.
    withShell(async () => {
      throw new Error('no uv sidecar beside this binary');
    });

    const answer = await nativeStartEngine();

    expect(answer).not.toBeNull();
    expect(answer?.started).toBe(false);
    expect(answer?.detail).toContain('no uv sidecar');
  });

  it('does not mistake an empty answer for a started engine', async () => {
    withShell(async () => null);

    const answer = await nativeStartEngine();

    expect(answer?.started).toBe(false);
    expect(answer?.already_running).toBe(false);
  });
});

describe('detection is a capability check and not a user-agent one', () => {
  it('finds the v2 internals shape', () => {
    withShell(async () => ({}), 'internals');
    expect(hasNativeShell()).toBe(true);
  });

  it('finds the withGlobalTauri shape too', () => {
    withShell(async () => ({}), 'global');
    expect(hasNativeShell()).toBe(true);
  });

  it('is not fooled by a window that merely looks like one', () => {
    const host = globalThis as unknown as Record<string, unknown>;
    host.__TAURI_INTERNALS__ = { notInvoke: true };
    expect(hasNativeShell()).toBe(false);
  });
});

describe('the two commands, by the names and shapes the Rust side will implement', () => {
  it('asks for engine_status with no arguments', async () => {
    const invoke = vi.fn<Invoke>(async () => ({ base_url: 'http://127.0.0.1:8078' }));
    withShell(invoke);

    await expect(nativeEngineStatus()).resolves.toEqual({
      base_url: 'http://127.0.0.1:8078',
    });
    expect(invoke).toHaveBeenCalledWith('engine_status');
  });

  it('asks for pick_path with the kind, because the shell side is a match', async () => {
    const invoke = vi.fn<Invoke>(async () => 'D:\\work\\tickets');
    withShell(invoke);

    await expect(nativePickPath('directory')).resolves.toBe('D:\\work\\tickets');
    expect(invoke).toHaveBeenCalledWith('pick_path', { kind: 'directory' });
  });
});

describe('a shell that is there and failing is not a shell that is absent', () => {
  it('reports the failure rather than returning null', async () => {
    withShell(async () => {
      throw new Error('no engine.json');
    });

    const answer = await nativeEngineStatus();
    // NOT null. Null would send `config.ts` down the dev-server path inside a
    // packaged app, where there is no dev server, and the person would be told
    // to run `npm run dev` by a window that has no terminal.
    expect(answer).not.toBeNull();
    expect(answer?.error).toContain('no engine.json');
  });

  it('treats a cancelled picker and a broken picker the same, on purpose', async () => {
    withShell(async () => {
      throw new Error('user closed the dialog');
    });
    // The caller's behaviour is identical for both - leave the field, let them
    // type - and distinguishing them would only let something say "you
    // cancelled" to a person who never saw a dialog.
    await expect(nativePickPath('file')).resolves.toBeNull();
  });

  it('treats an empty path as no path', async () => {
    withShell(async () => '');
    await expect(nativePickPath('file')).resolves.toBeNull();
  });

  it('treats a non-string answer as no path', async () => {
    withShell(async () => 42);
    await expect(nativePickPath('file')).resolves.toBeNull();
  });
});
