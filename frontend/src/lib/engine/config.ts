/**
 * Where the engine is, and the bearer token to talk to it.
 *
 * The engine writes `engine.json` at startup (app/security.py
 * `write_portfile`), user-only, at the repository root:
 *
 *     { "host", "port", "base_url", "token", "pid" }
 *
 * A browser cannot read a file off disk, so the dev server reads it and serves
 * it back on a loopback-only route. See vite.config.ts `enginePortfilePlugin`.
 *
 * TWO REAL CONSTRAINTS, both found by running the engine rather than by
 * reading about it:
 *
 * 1. `app/security.py allowed_origins()` permits exactly two origins —
 *    `http://127.0.0.1:<engine port>` and `http://localhost:<engine port>`.
 *    A Vite dev server on :5173 is NOT one of them, and a direct browser fetch
 *    to the engine is answered `403 cross-site request refused`. Verified.
 *    So every request goes through the dev server's own origin at `/engine/*`
 *    and is proxied; the proxy strips `Origin`, which `origin_is_allowed()`
 *    explicitly treats as "the caller is not a browser" — a curl, the
 *    launcher, a test. The bearer token still does the authenticating.
 *
 * 2. ~~`EventSource` cannot set an `Authorization` header~~ **SOLVED, and this
 *    note was stale.** It said "under Tauri it will need either a token query
 *    parameter or a fetch-stream reader"; `events.ts` IS a fetch-stream reader
 *    and has been for some time — it sets the header itself and reads
 *    `response.body.getReader()`. So streaming needs nothing from the shell
 *    beyond a session. The note is kept rather than deleted because it made the
 *    remaining Tauri risk look larger than it is, and the correction is the
 *    useful half. What IS still unmeasured is the `Origin` a WebView2-hosted
 *    page sends — `scripts/origin_spike.py` is that measurement.
 *
 * 3. **THE TOKEN ROTATES ON EVERY ENGINE START.** `app/security.py` mints a
 *    fresh one at startup and publishes it. A page that resolved its session
 *    once and cached it forever is holding a secret the engine has never heard
 *    of the moment the engine restarts — and the symptom is the worst kind:
 *    everything already loaded keeps working and everything new returns 401.
 *    That has happened to Max once already. So the session is cached but
 *    RE-RESOLVABLE (`refreshEngineSession`), and the 401 path in `client.ts`
 *    and `events.ts` uses it before giving up.
 */

import { readIdentity, type Checkout, type EngineIdentity } from './identity';
import { hasNativeShell, nativeEngineStatus, nativeStartEngine } from './shell';

/** What the dev server hands back from `engine.json`. */
export interface EngineSession {
  /** Prefix every request with this. In dev it is the proxy mount, not the
   *  engine's own origin — see constraint 1 above. */
  baseUrl: string;
  /** The engine's real base_url, for display only. */
  engineBaseUrl: string | null;
  token: string | null;
  /** False when `engine.json` is absent — the engine is not running. */
  available: boolean;
  /** Why it is unavailable, in words, for the UI to print. */
  reason: string | null;
  /**
   * Who the engine says it is, minus anything secret — see `identity.ts`.
   *
   * `null` when the dev server published nothing identifying, which is a state
   * the interface has to be able to say out loud rather than paper over.
   */
  identity: EngineIdentity | null;
  /** The revision this page was served from, for comparison against the above.
   *  `null` when the dev server could not read `.git`. */
  checkout: Checkout | null;
  /** When this session was resolved, so "we last checked at…" is a fact and
   *  not a guess. */
  resolvedAt: number;
}

const DEV_PROXY_PREFIX = '/engine';
const PORTFILE_ROUTE = '/__engine/session';

let cached: Promise<EngineSession> | null = null;
/** One refresh in flight at a time. Twelve requests can 401 in the same tick
 *  when a token rotates mid-page; they must not become twelve refreshes and
 *  twelve different opinions about which engine is answering. */
let refreshing: Promise<EngineSession> | null = null;

/**
 * Resolve the engine session once per page load.
 *
 * TWO SOURCES, ASKED IN THE ORDER THAT CANNOT BE WRONG. The native shell first
 * when there is one — `engine_status()`, which answers the same shape the dev
 * server's route does, so this function reads one payload and not two. The dev
 * server otherwise. And when there is neither, it reports unavailable with the
 * reason rather than inventing a base URL.
 *
 * The shell is asked FIRST rather than only in production builds, and that is
 * deliberate: `import.meta.env.DEV` describes how the bundle was built, not
 * where it is running, and a `devUrl` shell loads a DEV bundle inside the
 * window. Branching on the build flag would send that window to a dev server
 * route the window can reach — and it would work, and it would be the wrong
 * source, and nothing would say so.
 */
export function engineSession(): Promise<EngineSession> {
  if (cached) return cached;
  cached = resolve();
  return cached;
}

/**
 * Ask the dev server again and replace the cache with the answer.
 *
 * This is the whole answer to a rotated token, and it is deliberately not
 * automatic-on-401 *inside this file*: the caller that got the 401 is the one
 * that knows whether retrying its request is safe (`client.ts` retries once,
 * `events.ts` reconnects), and a refresh that silently re-issued requests from
 * here would retry a POST nobody asked it to retry.
 *
 * Concurrent callers share one in-flight fetch and all get the same session.
 */
export function refreshEngineSession(): Promise<EngineSession> {
  if (refreshing) return refreshing;
  refreshing = resolve().then((session) => {
    cached = Promise.resolve(session);
    refreshing = null;
    return session;
  });
  return refreshing;
}

/** The shape `vite.config.ts enginePortfilePlugin` answers with. */
interface SessionPayload {
  base_url?: string;
  token?: string;
  error?: string;
  /** The portfile minus anything secret, forwarded whole. */
  engine?: unknown;
  checkout?: { revision?: unknown; source?: unknown } | null;
}

/**
 * Has this page already asked the shell to start an engine?
 *
 * ONCE PER PAGE, and the reason is that `refreshEngineSession` exists and is
 * called on every 401 — see constraint 3 above. Without this flag, a page whose
 * token went stale would ask a shell to bootstrap an interpreter on every
 * failed request, and on a first run that is a uv download per 401.
 *
 * Not a cache of the ANSWER, only of the asking. If the start failed, the
 * reason is shown; if a person then starts an engine some other way, the next
 * resolve reads it off disk like any other.
 */
let askedTheShellToStart = false;

async function resolve(): Promise<EngineSession> {
  const native = await nativeEngineStatus();
  if (native) {
    const found = fromPayload(native, 'the shell');
    if (found.available || askedTheShellToStart) return found;

    // THE FIRST RUN. There is a shell, it looked, and there is no engine — so
    // ask it to start one rather than telling somebody with no terminal to go
    // and do it. On a machine with no Python this is where uv builds an
    // interpreter, which is slow once and never again.
    askedTheShellToStart = true;
    const bootstrap = await nativeStartEngine();
    if (!bootstrap) return found;

    if (bootstrap.started || bootstrap.already_running) {
      const again = await nativeEngineStatus();
      if (again) {
        const after = fromPayload(again, 'the shell');
        // A START THAT SUCCEEDED AND A SESSION THAT IS STILL MISSING is a real
        // state - the engine answered /health and had not yet written its
        // portfile - and saying so beats printing "no engine" over a running
        // one.
        if (after.available) return after;
        return unavailable(
          `${bootstrap.detail} The engine is running, but it has not published ` +
            'an engine.json this page can read yet. Give it a moment and reload.',
        );
      }
    }

    return unavailable(bootstrap.detail);
  }

  if (!import.meta.env.DEV) {
    return {
      ...unavailable(
        'This is a packaged build and there is no native shell answering ' +
          'engine_status(), so there is nowhere to ask where the engine is. ' +
          'Run `npm run dev` for the dev server, or start the shell.',
      ),
    };
  }

  try {
    const response = await fetch(PORTFILE_ROUTE, { cache: 'no-store' });
    if (!response.ok) {
      return unavailable(
        `The dev server could not read engine.json (HTTP ${response.status}).`,
      );
    }
    return fromPayload((await response.json()) as SessionPayload, 'the dev server');
  } catch {
    // One human sentence, not a parse trace. The owner's screen once filled
    // with "Unexpected token '<'" nine times over for a single fact; whatever
    // the low-level reason, the person's situation is the same one.
    return unavailable(
      'No engine answered. Start the engine, then reload this page.',
    );
  }
}

/**
 * One payload, one reading, whichever door it came through.
 *
 * The shell and the dev server answer the same shape on purpose - THE_PLAN V.1
 * calls it "a direct swap, not a new mechanism" - so this is written once. Two
 * copies of it would be two opinions about what a session is, and the one that
 * drifted would drift in the packaged build, which is the one nobody runs
 * while developing.
 *
 * `baseUrl` stays the dev proxy prefix in BOTH cases and that is not an
 * oversight. In the shell there is no proxy, so requests go to the engine's own
 * origin - but which prefix to use is `client.ts`'s question, and it reads
 * `engineBaseUrl` for exactly that. Changing this field here would move a
 * decision out of the file that makes it.
 */
function fromPayload(body: SessionPayload, source: string): EngineSession {
  const checkout = readCheckout(body.checkout);
  if (body.error) return { ...unavailable(body.error), checkout };
  if (!body.base_url && !body.token) {
    return {
      ...unavailable(`${source} answered with no engine in it.`),
      checkout,
    };
  }
  return {
    baseUrl: DEV_PROXY_PREFIX,
    engineBaseUrl: body.base_url ?? null,
    token: body.token ?? null,
    available: true,
    reason: null,
    /* Read again on arrival even though the dev server already stripped
       secrets. Two filters, one rule; see identity.ts. */
    identity: readIdentity(body.engine),
    checkout,
    resolvedAt: Date.now(),
  };
}

/** Is there a native host? Re-exported so callers that want to say so on the
 *  page do not each reach into `shell.ts` and each decide differently. */
export { hasNativeShell };

/** A checkout only counts when it names a revision. A `{source}` with no
 *  revision would compare equal to nothing and read as a failed comparison
 *  rather than as an absent one. */
function readCheckout(raw: SessionPayload['checkout']): Checkout | null {
  if (!raw || typeof raw.revision !== 'string' || raw.revision.length === 0) {
    /* NO CHECKOUT BESIDE AN INSTALLED APP, and that used to be the end of the
       question. `engine_status` finds a checkout only when the exe is sitting
       in one, so every installed window answered `unverifiable` and drew
       nothing - which is how Max spent 2026-09-19/20 on an engine two commits
       behind, with no way to know. The bundle knows which commit it was built
       from (`__UI_REVISION__`, see the vite config), and comparing THAT to the
       engine's `build.sha` is the same question with an answer. */
    const built = typeof __UI_REVISION__ === 'string' ? __UI_REVISION__ : null;
    if (built && built.length > 0) {
      return { revision: built, source: 'the commit this window was built from' };
    }
    return null;
  }
  return {
    revision: raw.revision,
    source: typeof raw.source === 'string' ? raw.source : 'unstated',
  };
}

function unavailable(reason: string): EngineSession {
  return {
    baseUrl: DEV_PROXY_PREFIX,
    engineBaseUrl: null,
    token: null,
    available: false,
    reason,
    identity: null,
    checkout: null,
    resolvedAt: Date.now(),
  };
}

/** Drop the cached session. Used when the user asks to reconnect. */
export function forgetEngineSession(): void {
  cached = null;
}
