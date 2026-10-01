/**
 * The native shell, if there is one. Today there is not, and that is the point.
 *
 * `docs/THE_PLAN.md` Phase B lists "seven frontend files swapped" as the work
 * the Tauri shell needs, and V.5 restates the acceptance as *no changes outside
 * `lib/engine/{config,client,events,liveness}.ts` and
 * `components/{Composer,PaneStack,QuestionCard,JourneyActions}.tsx`*.
 *
 * **This module makes that number one.** Everything the app wants from a native
 * host is asked for here, in one place, behind functions that answer honestly
 * when there is no host. The Rust side lands by implementing the two commands
 * below; nothing else in the app changes, and nothing in the app has to know
 * whether it is running in a browser or in a window.
 *
 * ── WHY IT IS SAFE TO ADD BEFORE THE SHELL EXISTS ────────────────────────────
 *
 * Every function here returns "no shell" today, on a check that cannot be true
 * in a browser. So the behaviour of this build is byte-identical to the build
 * before it, which is what makes this preparation rather than speculation - and
 * it is why `npm test` and `npm run build` are the whole of its verification.
 *
 * A seam that changes nothing until the other half arrives is the opposite of
 * a feature flag nobody turns on: it exists so the arrival is a small diff in a
 * reviewable place, rather than seven simultaneous ones in files that also do
 * other things.
 *
 * ── THE TWO COMMANDS, AND THE ONE THAT WAS DROPPED ───────────────────────────
 *
 * `docs/ARCHITECTURE.md` §4.1 named three Rust commands. THE_PLAN V.2 drops
 * `secret_get`/`secret_set` and gives three reasons: the key never returns to
 * the frontend today (`/api/providers` answers `has_key`, a boolean), the
 * consumer is the ENGINE, which cannot call the shell that spawned it, and both
 * paths land in the same DPAPI store anyway. So there are two:
 *
 *   `engine_status()` -> the same `{base_url, token, engine, checkout}` shape
 *      `vite.config.ts`'s `enginePortfilePlugin` already serves. THE_PLAN V.1:
 *      "A direct swap, not a new mechanism." The shell reads `engine.json` off
 *      disk exactly as `scripts/launch.py` does, which is now
 *      `app.launcher.read_portfile` and travels in the wheel.
 *
 *   `pick_path(kind)` -> a real path on this machine, or null if cancelled.
 *      The one thing a browser genuinely cannot do, and the reason
 *      `Composer.tsx` says "typed or pasted" today.
 *
 * ── WHAT IS NO LONGER A PROBLEM, corrected here because it was written down ──
 *
 * `config.ts` used to warn that `EventSource` cannot set an `Authorization`
 * header and that "under Tauri it will need either a token query parameter or a
 * fetch-stream reader". **`events.ts` IS a fetch-stream reader and has been for
 * some time** - it sets the header itself and reads `response.body.getReader()`.
 * So streaming needs nothing from the shell beyond a session, and the note that
 * said otherwise made the remaining Tauri risk look larger than it is.
 *
 * What DOES remain unmeasured is the `Origin` a WebView2-hosted page sends;
 * `scripts/origin_spike.py` is the measurement and `docs/THE_PLAN.md` A7 is the
 * step. Nothing here guesses at it.
 */

/** The kinds of thing `pick_path` can be asked for. Closed, because the shell
 *  side is a match statement and a free string would be a silent no-op. */
export type PickKind = 'file' | 'directory';

/** What `engine_status()` answers with — deliberately the shape the dev
 *  server's `/__engine/session` route already returns, so `config.ts` reads one
 *  payload and not two. */
export interface NativeEngineStatus {
  base_url?: string;
  token?: string;
  error?: string;
  engine?: unknown;
  checkout?: { revision?: unknown; source?: unknown } | null;
}

/**
 * What a Tauri v2 window exposes. Typed rather than `any` so a wrong call shape
 * is a compile error on the day the shell lands rather than a runtime one.
 *
 * `__TAURI_INTERNALS__.invoke` is v2's; `__TAURI__.core.invoke` is what the
 * `withGlobalTauri` build option exposes. Both are checked because which one is
 * present depends on a setting in `tauri.conf.json` that has not been written
 * yet, and a detector that guessed one would be a coin toss decided later.
 */
interface TauriWindow {
  __TAURI_INTERNALS__?: { invoke?: (cmd: string, args?: unknown) => Promise<unknown> };
  __TAURI__?: { core?: { invoke?: (cmd: string, args?: unknown) => Promise<unknown> } };
}

function invoker(): ((cmd: string, args?: unknown) => Promise<unknown>) | null {
  if (typeof window === 'undefined') return null;
  const host = window as unknown as TauriWindow;
  return (
    host.__TAURI_INTERNALS__?.invoke ?? host.__TAURI__?.core?.invoke ?? null
  );
}

/**
 * Is this page running inside the native shell?
 *
 * A CAPABILITY CHECK RATHER THAN A USER-AGENT ONE, and the difference matters:
 * the WebView reports itself as Edge, so a UA test would be wrong in both
 * directions - false for a future shell on another engine, true for anybody
 * browsing to the dev server in Edge.
 */
export function hasNativeShell(): boolean {
  return invoker() !== null;
}

/**
 * Ask the shell where the engine is. `null` when there is no shell.
 *
 * `null` and a status with an `error` are different answers and both callers
 * have to keep them apart: `null` means "not running in the shell, use the
 * other route", and an `error` means "the shell looked and there is no engine",
 * which is a thing to show somebody.
 */
export async function nativeEngineStatus(): Promise<NativeEngineStatus | null> {
  const invoke = invoker();
  if (!invoke) return null;
  try {
    const answer = await invoke('engine_status');
    return (answer ?? {}) as NativeEngineStatus;
  } catch (error) {
    // A SHELL THAT IS THERE AND FAILED IS NOT A SHELL THAT IS ABSENT. Returning
    // `null` here would send the caller down the dev-server path inside a
    // packaged app, where there is no dev server, and the person would be told
    // to run `npm run dev`.
    return { error: `the shell could not report the engine: ${String(error)}` };
  }
}

/**
 * Ask the shell for a real path. `null` when there is no shell OR the person
 * cancelled — and those are deliberately the same answer here.
 *
 * The caller's behaviour is identical for both: leave the field as it was and
 * let them type. Distinguishing them would only let a caller say "you
 * cancelled" to somebody who never saw a dialog.
 */
export async function nativePickPath(kind: PickKind): Promise<string | null> {
  const invoke = invoker();
  if (!invoke) return null;
  try {
    const answer = await invoke('pick_path', { kind });
    return typeof answer === 'string' && answer.length > 0 ? answer : null;
  } catch {
    return null;
  }
}

/** What `start_engine` answers with — `engine::Bootstrap`, verbatim. */
export interface NativeBootstrap {
  started: boolean;
  already_running: boolean;
  interpreter: string | null;
  detail: string;
}

/**
 * Ask the shell to start the engine. `null` when there is no shell.
 *
 * ── WHY THIS EXISTS, AND WHY IT IS SEPARATE FROM `engine_status` ─────────────
 *
 * `engine_status()` READS `engine.json` and deliberately starts nothing —
 * `lib.rs` argues that at length, and the argument is right: starting processes
 * belongs to code with tests behind it, not to a status call somebody might
 * make twice. But a status call that never starts anything, in an app where
 * nothing else calls a starter, is a packaged build that opens a window,
 * reports "no engine", and waits forever for a person who has no terminal to
 * open one. **That is what a first run on a clean machine would have been.**
 *
 * So the shell has two commands and this is the second: an explicit start,
 * asked for once, whose answer is a SENTENCE about what it tried. On a machine
 * with no Python at all this is the call that makes uv build an interpreter, so
 * it can take minutes on a first run and seconds on every run after.
 *
 * It never throws. A shell that is present and whose start failed still has to
 * tell somebody why, and an exception here would be caught by a caller that
 * would then say "no shell" — the one thing that is definitely false.
 */
/**
 * The page's wire to the engine, carried by the Rust shell.
 *
 * Exists because the WebView's own networking kept refusing loopback in new
 * ways (CORS, private-network preflights) and because `send()` was, it turned
 * out, never even given the absolute-URL half it needed. The shell has no
 * browser rules: it is a local process talking to a local port. When this
 * returns null there is no shell, and the caller uses fetch as before.
 */
export async function nativeEngineFetch(
  url: string,
  init: { method?: string; body?: string | null; token?: string | null } = {},
): Promise<Response | null> {
  const invoke = invoker();
  if (!invoke) return null;
  const answer = (await invoke('engine_fetch', {
    url,
    method: init.method ?? 'GET',
    token: init.token ?? null,
    body: init.body ?? null,
  })) as { status: number; body: string };
  return new Response(answer.body, {
    status: answer.status === 0 ? 502 : answer.status,
  });
}

/** Window controls for the frameless shell. No-ops in a browser. */
export function nativeWindow(verb: 'minimize' | 'toggle_maximize' | 'close'): void {
  const invoke = invoker();
  if (invoke) void invoke(`window_${verb}`);
}

/**
 * The detached instrument window — size C of the Stage (docs/PHASES.md).
 *
 * Under the shell it is a second Tauri window labelled `stage`, opened by
 * Rust at `index.html?stage=<threadId>` and bound to that thread; opening it
 * again for another thread re-points the same window rather than stacking
 * a second. Returns false when there is no shell, and the caller falls back
 * to a browser popup at the same URL — one page, two hosts.
 */
/** Open one pane in its own window, bound to this thread.
 *
 * Returns false OUTSIDE THE SHELL rather than throwing, and the caller uses
 * that to fall back to `window.open` - a browser has no Tauri command but it
 * does have popups, and the same `?pane=` route serves both.
 */
export async function nativeOpenPane(pane: string, threadId: number): Promise<boolean> {
  const invoke = invoker();
  if (!invoke) return false;
  try {
    await invoke('open_pane', { pane, threadId });
    return true;
  } catch {
    return false;
  }
}

export async function nativeOpenStage(threadId: number): Promise<boolean> {
  const invoke = invoker();
  if (!invoke) return false;
  try {
    await invoke('open_stage', { threadId });
    return true;
  } catch {
    return false;
  }
}

/** Close the instrument window if the shell has one open. No-op elsewhere. */
export function nativeCloseStage(): void {
  const invoke = invoker();
  if (invoke) void invoke('close_stage');
}

/** `restart_engine` — replace the engine that is answering, whoever started it.
 *
 *  `start_engine` refuses while one is up, which leaves the case the window
 *  can actually see: an engine on older code than this page. The shell asks
 *  that engine to exit using the token it published, then starts a new one.
 *  Nothing kills a process. See `src-tauri/src/engine.rs::restart`. */
export async function nativeRestartEngine(): Promise<NativeBootstrap | null> {
  const invoke = invoker();
  if (!invoke) return null;
  try {
    const answer = await invoke('restart_engine');
    return (answer ?? {
      started: false,
      already_running: false,
      interpreter: null,
      detail: 'the shell answered nothing',
    }) as NativeBootstrap;
  } catch (error) {
    return {
      started: false,
      already_running: false,
      interpreter: null,
      detail: `the shell could not restart the engine: ${String(error)}`,
    };
  }
}

export async function nativeStartEngine(): Promise<NativeBootstrap | null> {
  const invoke = invoker();
  if (!invoke) return null;
  try {
    const answer = await invoke('start_engine');
    return (answer ?? {
      started: false,
      already_running: false,
      interpreter: null,
      detail: 'the shell answered nothing',
    }) as NativeBootstrap;
  } catch (error) {
    return {
      started: false,
      already_running: false,
      interpreter: null,
      detail: `the shell could not start the engine: ${String(error)}`,
    };
  }
}
