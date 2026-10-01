/**
 * IS THE ENGINE I LOADED AGAINST STILL THE ENGINE ANSWERING ME.
 *
 * ══ THE TWO FAILURES THIS FILE REMOVES ═════════════════════════════════════
 *
 * **1. The token rotates on every engine start.** `app/security.py` mints a
 * fresh bearer token at startup. A tab left open across a restart is holding a
 * secret the engine has never heard of, and the symptom is the worst possible
 * one: everything already rendered keeps working, everything NEW returns 401,
 * and the page has no story for it. Max has hit this once already. A 401 is now
 * not a dead end — `client.ts` and `events.ts` both call
 * `recoverFromUnauthorized`, which re-reads `/__engine/session` ONCE and hands
 * back either a fresher token to retry with or a sentence saying why retrying
 * will not help.
 *
 * **2. Nothing noticed a stale engine.** An engine three commits old answered
 * `GET /health` with `{"status":"ok"}`, served `gpu_name: null` for an installed
 * RTX 2060 SUPER, and every check that was run passed. This file runs the checks
 * that were missing, on a timer and on focus, and publishes the answer as a
 * state the interface can render.
 *
 * ══ WHAT IT WILL NOT DO ════════════════════════════════════════════════════
 *
 * It will not report "current" for a question it did not ask. `identity.ts`
 * returns `unverifiable` wherever the engine publishes nothing to compare, and
 * this file keeps that word rather than rounding it to "fine". The whole reason
 * the incident lasted an hour is that a check with nothing to check said ok.
 *
 * It is also QUIET. `docs/DESIGN_DIRECTIVES.md` §6: colour appears for state and
 * for data, never for ornament. `current` and `checking` render nothing at all,
 * and `unverifiable` on its own renders nothing — it is only worth a person's
 * attention at the moment they have already been told the engine changed, which
 * is when "and I cannot tell you whether the code changed with it" is the
 * sentence they need.
 */

import {
  nativeEngineFetch,
  nativeRestartEngine,
  nativeStartEngine,
  hasNativeShell,
} from './shell';
import {
  checkAgainstCheckout,
  compareEngines,
  comparePublishedToAnswering,
  readIdentity,
  type EngineIdentity,
} from './identity';
import {
  engineSession,
  refreshEngineSession,
  type EngineSession,
} from './config';

/* ── What the interface renders ──────────────────────────────────────────── */

/** How loudly this deserves to be said. Mapped to exactly one token in
 *  `styles/engine.css`; there is no fourth level and no hue outside these. */
export type EngineSeverity = 'notice' | 'warn' | 'stop';

export interface EngineLiveness {
  readonly kind:
    /** Nothing asked yet. Renders nothing. */
    | 'checking'
    /** Asked, and the answer was "the same engine". Renders nothing. */
    | 'current'
    /** A new process is answering. The session was recovered. */
    | 'restarted'
    /** A field naming the engine's code moved under a live page. */
    | 'rebuilt'
    /** The engine's code is not this checkout's code. */
    | 'stale'
    /** engine.json exists and nothing is answering, or the engine is not
     *  running at all. */
    | 'gone'
    /** The page cannot fix itself from here. */
    | 'reload';
  readonly severity: EngineSeverity;
  /** One line. Says what happened, not what it might mean. */
  readonly headline: string;
  /** The evidence, for the title attribute and the second line: which fields
   *  moved, which revisions, which port. */
  readonly detail: string;
  /** What the person should do, when there is something to do. */
  readonly action: string | null;
  /** When this was established. */
  readonly at: number;
}

const QUIET: EngineLiveness = {
  kind: 'checking',
  severity: 'notice',
  headline: '',
  detail: '',
  action: null,
  at: 0,
};

/* ── The store ───────────────────────────────────────────────────────────── */

let state: EngineLiveness = QUIET;
let dismissed = '';
const listeners = new Set<() => void>();

/** The snapshot is a module-level object replaced only when something actually
 *  changed, so `useSyncExternalStore` is not handed a new object every render. */
export function engineLiveness(): EngineLiveness {
  return state;
}

export function subscribeToEngine(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** A key that changes when the MEANING changes, so a re-poll that finds the
 *  same thing does not re-notify and does not un-dismiss the strip. */
function keyOf(next: EngineLiveness): string {
  return `${next.kind}|${next.headline}|${next.detail}`;
}

function publish(next: Omit<EngineLiveness, 'at'>): void {
  const full: EngineLiveness = { ...next, at: Date.now() };
  if (keyOf(full) === keyOf(state)) return;
  state = full;
  for (const listener of listeners) listener();
}

/** The user has read it. Stays gone until the situation changes into a
 *  different one — a dismissal is "I know", not "stop telling me things". */
export function dismissEngineNotice(): void {
  dismissed = keyOf(state);
  for (const listener of listeners) listener();
}

export function engineNoticeDismissed(): boolean {
  return dismissed === keyOf(state);
}

/* ── The baseline: the engine this page loaded against ───────────────────── */

let baseline: EngineIdentity | null = null;
let baselineTaken = false;

/**
 * A change already noticed, kept until the page is reloaded.
 *
 * ── WHY THIS EXISTS, AND IT WAS FOUND BY WATCHING IT ────────────────────────
 *
 * Without it the notice appeared and then DELETED ITSELF five seconds later.
 * "The engine restarted" was published the instant a 401 was recovered from,
 * and the next poll — finding the page and the new engine in perfect agreement,
 * which they now were — published `current` over the top of it. Measured at
 * 19:51:56 and gone by 19:52:01.
 *
 * The bug was treating "the engine changed under this page" as a CONDITION.
 * It is not: it is an EVENT, and it stays true for the life of the page. What
 * the reader needs to know is that the answers already on their screen came
 * from a different engine than the one answering now, and that does not stop
 * being true because the new engine is healthy.
 *
 * `gone`, `stale` and `reload` ARE conditions and are not kept here — they
 * outrank this while they hold, and when they clear, this is what the page
 * falls back to rather than to silence.
 */
let sticky: Omit<EngineLiveness, 'at'> | null = null;

/** Test seam and reconnect seam: forget what we thought we were talking to. */
export function forgetEngineBaseline(): void {
  baseline = null;
  baselineTaken = false;
  sticky = null;
  dismissed = '';
  state = QUIET;
}

/** Publish, and remember it for the life of the page. */
function publishChange(next: Omit<EngineLiveness, 'at'>): void {
  sticky = next;
  publish(next);
}

/* ── The checks ──────────────────────────────────────────────────────────── */

/**
 * Ask `GET /health` who is answering, and TELL IT WHO WE EXPECTED.
 *
 * The portfile is written by whichever process got there first and
 * `write_portfile` refuses to overwrite one whose owning pid is still alive —
 * both correct, and together they mean `engine.json` CAN describe a process
 * that is not on the socket. The health route cannot lie about that: it is
 * answered by the process actually listening.
 *
 * `app/main.py health()` makes holding an opinion cost a query parameter, and
 * this page holds one: the `engine_id` and `code_fingerprint` it read from
 * `engine.json`. If the socket disagrees the engine answers `409
 * not_the_engine_you_meant` with a `mismatch` list of
 * `{field, expected, actual}` — its own verdict, in its own words, which beats
 * anything this file could infer. `503 not_ready` is the other answer worth
 * having: running, and honest that it cannot serve.
 *
 * No `Authorization` header. That route is deliberately unauthenticated —
 * "a client that has not yet read engine.json still has to be able to ask
 * whether the engine on this port is the one it wants" — and sending the token
 * would make this check fail for the one reason it must not: a rotated token.
 */
interface HealthReading {
  readonly reached: boolean;
  readonly status: number;
  readonly identity: EngineIdentity | null;
  readonly body: Record<string, unknown>;
}

async function askWhoIsAnswering(
  session: EngineSession,
): Promise<HealthReading> {
  const expectations = new URLSearchParams();
  if (session.identity?.engineId) {
    expectations.set('expect_engine', session.identity.engineId);
  }
  if (session.identity?.codeFingerprint) {
    expectations.set('expect_build', session.identity.codeFingerprint);
  }
  const query = expectations.toString();

  try {
    /* THE DIRECT ADDRESS IS ONLY FOR THE CARRIED WIRE. In a plain browser a
       fetch straight to the engine's own origin is cross-site, the engine's
       allowlist has never contained a dev server, and CORS refuses it — which
       painted "the engine is not answering" over a page whose every proxied
       request was succeeding. Measured 2026-08-31: /health from
       localhost:5199 → "No Access-Control-Allow-Origin". No shell, no direct
       address: the probe rides the page's own base like every other call. */
    const carried = Boolean(session.engineBaseUrl && hasNativeShell());
    const target = carried
      ? `${session.engineBaseUrl}/health${query ? `?${query}` : ''}`
      : `${session.baseUrl}/health${query ? `?${query}` : ''}`;
    const response =
      (carried ? await nativeEngineFetch(target, {}) : null) ??
      (await fetch(target, { cache: 'no-store' }));
    /* THE ONLY THREE ANSWERS THIS ROUTE GIVES: 200 ok, 409
       not_the_engine_you_meant, 503 not_ready. Anything else did not come from
       the engine. In dev the common one is 502 — the Vite proxy's own page,
       served when the thing it proxies to is not there, which is a JSON parse
       away from being mistaken for an engine that answered with nothing. Named
       rather than left to fall through: "the proxy could not reach it" is the
       same fact as "it is not answering", and a 404 from something else on the
       port must not be read as an engine either. */
    if (![200, 409, 503].includes(response.status)) {
      return { reached: false, status: response.status, identity: null, body: {} };
    }
    const body = (await response.json()) as Record<string, unknown>;
    /* `status: "ok"` is not an identity. It is the string that passed three
       times on a stale engine. Everything else the route says is. */
    const { status: _status, ...rest } = body;
    return {
      reached: true,
      status: response.status,
      identity: readIdentity(rest),
      body,
    };
  } catch {
    return { reached: false, status: 0, identity: null, body: {} };
  }
}

/** The engine's own `mismatch` list, rendered as one line. */
function readMismatch(body: Record<string, unknown>): string {
  const rows = body.mismatch;
  if (!Array.isArray(rows) || rows.length === 0) return '';
  return rows
    .map((row) => {
      const entry = row as {
        field?: unknown;
        expected?: unknown;
        actual?: unknown;
      };
      return `${String(entry.field)}: engine.json said ${short(
        entry.expected,
      )}, the engine says ${short(entry.actual)}`;
    })
    .join('; ');
}

/** Every failing readiness check, in the engine's own words. */
function readFailedChecks(body: Record<string, unknown>): string {
  const rows = body.checks;
  if (!Array.isArray(rows)) return '';
  return rows
    .filter((row) => (row as { ok?: unknown }).ok === false)
    .map((row) => {
      const entry = row as { name?: unknown; detail?: unknown };
      return `${String(entry.name)} — ${String(entry.detail)}`;
    })
    .join('; ');
}

function short(value: unknown): string {
  const text = value === null || value === undefined ? 'nothing' : String(value);
  return text.length > 16 ? `${text.slice(0, 12)}…` : text;
}

const shortRev = (revision: string) => revision.slice(0, 7);

const pidOf = (identity: EngineIdentity | null): string => {
  const pid = identity?.process.pid;
  return pid === undefined || pid === null ? 'unstated' : String(pid);
};

/**
 * One full check. Cheap: a local file read at the dev server and one `/health`
 * on loopback.
 */
let triedToStart = false;

/** The banner's button: start the engine through the shell, then re-probe. */
export async function startEngineNow(): Promise<void> {
  const boot = await nativeStartEngine();
  if (boot && (boot.started || boot.already_running)) {
    window.location.reload();
  }
}

/** Replace a running engine, then reload onto it.
 *
 *  THE BUTTON THE BANNER WAS MISSING. A window that can see its engine is on
 *  older code could say so and then had to tell the person to run two shell
 *  commands - which is the app admitting it is two products. Max, 2026-09-21:
 *  *"the engine should be easy for people to restart, they shouldn't be
 *  running scripts on their own."* */
export async function restartEngineNow(): Promise<string | null> {
  const boot = await nativeRestartEngine();
  /* AN ENGINE IS ANSWERING, AND WHO STARTED IT IS NOT THE QUESTION.
     `started` alone was wrong, and Max pressed this ten times because of it.
     The app supervises the engine it spawns: ask that engine to exit and the
     supervisor has a new one on the port before `bootstrap` gets there, so
     bootstrap correctly answers `already_running` - a successful replacement,
     reported by this function as a failure, with no reload. The banner can
     only clear on a reload, so it never cleared.

     `startEngineNow` two functions up has always accepted both flags. This
     was stricter than its sibling for no reason anybody could have stated. */
  if (boot && (boot.started || boot.already_running)) {
    window.location.reload();
    return null;
  }
  /* Nothing is on the port. That is the only real failure, and the detail is
     the whole of what went wrong; reloading onto it would show the same
     banner again. */
  return boot?.detail ?? 'the shell could not restart the engine';
}

export async function probeEngine(): Promise<EngineLiveness> {
  const session = await refreshEngineSession();

  if (!session.available) {
    publish({
      kind: 'gone',
      severity: 'stop',
      headline: 'The engine is not running.',
      detail: session.reason ?? 'engine.json could not be read.',
      action: 'Start it, then reload this page.',
    });
    return state;
  }

  let health = await askWhoIsAnswering(session);
  if (!health.reached && hasNativeShell() && !triedToStart) {
    /* THE OWNER'S QUESTION, TAKEN LITERALLY: "why can't the engine power up
       right away?" It can - the shell has a bootstrap - so a dead engine in
       shell mode is started HERE, once per page, before any banner is shown.
       The button below is the same door for the manual case. */
    triedToStart = true;
    const boot = await nativeStartEngine();
    if (boot && (boot.started || boot.already_running)) {
      const fresh = await refreshEngineSession();
      health = await askWhoIsAnswering(fresh.available ? fresh : session);
    }
  }
  if (!health.reached) {
    publish({
      kind: 'gone',
      severity: 'stop',
      headline: 'The engine is not answering.',
      detail:
        `engine.json still describes an engine at ` +
        `${session.engineBaseUrl ?? 'the configured address'} (pid ` +
        `${pidOf(session.identity)}), and GET /health from that address ` +
        (health.status
          ? `answered HTTP ${health.status}, which the engine never does. `
          : `returned nothing. `) +
        `A portfile is not proof that a process is alive.`,
      action: 'Start the engine, then reload this page.',
    });
    return state;
  }

  /* ── The engine's own verdict, which beats any inference here ──────────
     `/health` was asked with the engine_id and code_fingerprint this page read
     out of engine.json. 409 is it saying, in its own words, that it is not the
     engine those name. */
  if (health.status === 409) {
    publish({
      kind: 'stale',
      severity: 'stop',
      headline: 'This is not the engine engine.json describes.',
      detail:
        readMismatch(health.body) ||
        'GET /health answered 409 not_the_engine_you_meant.',
      action: 'Restart it to put one engine on this build.',
    });
    return state;
  }

  if (health.status === 503) {
    publish({
      kind: 'gone',
      severity: 'stop',
      headline: 'The engine is running but not ready.',
      detail:
        readFailedChecks(health.body) ||
        'GET /health answered 503 not_ready and named no failing check.',
      action: 'Fix what it names, restart it, then reload.',
    });
    return state;
  }

  /* Both halves are alive. Everything below is about WHICH engine it is. */

  if (!baselineTaken) {
    baseline = session.identity;
    baselineTaken = true;
    settleAtRest(session, health.identity);
    return state;
  }

  const change =
    baseline && session.identity
      ? compareEngines(baseline, session.identity)
      : ({ kind: 'same' } as const);

  if (change.kind === 'same') {
    settleAtRest(session, health.identity);
    return state;
  }

  const from = pidOf(baseline);
  const to = pidOf(session.identity);
  const was = baseline;
  baseline = session.identity;

  if (change.kind === 'rebuilt') {
    publishChange({
      kind: 'rebuilt',
      severity: 'warn',
      headline: 'The engine is running different code than when this page loaded.',
      detail:
        `${describeCode(was, session.identity)} Anything this page has already ` +
        `shown you was answered by the previous engine.`,
      action: 'Reload to be sure of what you are looking at.',
    });
    return state;
  }

  publishChange({
    kind: 'restarted',
    severity: 'warn',
    headline: 'The engine restarted.',
    detail: [
      `A different process is answering now (pid ${from} → ${to}). This page ` +
        `picked up the new token, so it is still working.`,
      unverifiableCodeNote(session),
    ]
      .filter(Boolean)
      .join(' '),
    action: 'Reload if the answers stop making sense.',
  });
  return state;
}

/**
 * Which code, in the two forms the engine publishes.
 *
 * `build.code_fingerprint` rather than the commit is what actually answers
 * "different code": the engine's checkout is routinely dirty, and two engines
 * at one commit with different uncommitted edits are two different engines.
 * The commit is named as well because that is the word a person thinks in.
 */
function describeCode(
  before: EngineIdentity | null,
  after: EngineIdentity | null,
): string {
  const wasRev = before?.revision;
  const nowRev = after?.revision;
  if (wasRev && nowRev && wasRev !== nowRev) {
    return `It moved from ${shortRev(wasRev)} to ${shortRev(nowRev)}.`;
  }
  const wasCode = before?.codeFingerprint;
  const nowCode = after?.codeFingerprint;
  if (wasCode && nowCode && wasCode !== nowCode) {
    return (
      `Same commit${nowRev ? ` (${shortRev(nowRev)})` : ''}, different files — ` +
      `its code fingerprint moved from ${shortRev(wasCode)} to ` +
      `${shortRev(nowCode)}.`
    );
  }
  return 'What it publishes about its build changed.';
}

/** The sentence that says what we could NOT check, used only where a person is
 *  already being told the engine moved. */
function unverifiableCodeNote(session: EngineSession): string {
  const verdict = checkAgainstCheckout(session.identity, session.checkout);
  if (verdict.kind !== 'unverifiable') return '';
  return (
    `Whether the code changed with it cannot be checked from here: ` +
    `${verdict.why}.`
  );
}

/**
 * Nothing moved. That is not the same as nothing being wrong: the engine can be
 * steady and be the wrong engine, which is exactly what an hour was lost to.
 */
function settleAtRest(
  session: EngineSession,
  answering: EngineIdentity | null,
): void {
  const published = comparePublishedToAnswering(session.identity, answering);
  if (published.kind === 'disagree') {
    publish({
      kind: 'stale',
      severity: 'stop',
      headline:
        'engine.json describes a different engine than the one answering.',
      detail:
        `${published.changed.join(', ')} differ between engine.json and ` +
        `GET /health. The process on ${session.engineBaseUrl ?? 'that port'} ` +
        `is not the one that wrote the portfile, so the token in it may not be ` +
        `the token that port accepts.`,
      action: 'Restart it to put one engine on this build.',
    });
    return;
  }

  if (published.kind === 'answering-is-older') {
    publish({
      kind: 'stale',
      severity: 'stop',
      headline: 'The engine answering this page is older than engine.json.',
      detail:
        `engine.json says what its writer is — service, build, schema — and ` +
        `GET /health on ${session.engineBaseUrl ?? 'that port'} says only ` +
        `"ok", which the engine that wrote that file would not do. Something ` +
        `older is holding the port, and the token in engine.json is not its ` +
        `token.`,
      action: 'Restart it to put one engine on this build.',
    });
    return;
  }

  const verdict = checkAgainstCheckout(session.identity, session.checkout);
  if (verdict.kind === 'differs') {
    publish({
      kind: 'stale',
      severity: 'warn',
      headline: 'The engine is not running this checkout’s code.',
      detail:
        `The engine reports revision ${shortRev(verdict.engine)}; this window was ` +
        `built from ${shortRev(verdict.checkout)}. Answers here come from the ` +
        `engine, so they are that revision’s answers, not this one’s.`,
      /* NAME THE COMMAND. "Restart the engine from this checkout" is a
         sentence for somebody who already has a terminal open in one. An
         installed window has neither, and Max ran a day and a half on an
         engine from 2026-09-19 01:08 without a way to act on it even once the
         banner could see it. There is no restart button yet - `start_engine`
         refuses while one is answering - so the words have to carry it. */
      /* NO SHELL COMMANDS IN A PRODUCT'S OWN BANNER. This used to name two
         `python scripts/launch.py` invocations, which is the app telling the
         person to go and be its operator. The button beside this sentence does
         it now - see `restartEngineNow`. */
      action: 'Restart it to run this build.',
    });
    return;
  }

  /* Nothing is wrong NOW. That does not undo an engine having changed under
     this page — see `sticky`. Falling through to `current` here is what made
     the notice delete itself five seconds after it appeared. */
  if (sticky) {
    publish(sticky);
    return;
  }

  publish({
    kind: 'current',
    severity: 'notice',
    headline: '',
    /* Kept even though nothing renders it today: when this state IS shown, the
       difference between "checked and matched" and "could not check" is the
       whole point. `dirty` is carried through because a matching commit on a
       dirty tree is a weaker claim than a matching commit on a clean one, and
       rounding the two together is how a check starts meaning less than it
       says. */
    detail:
      verdict.kind === 'matches'
        ? `Engine and page are both at ${shortRev(verdict.revision)}` +
          (session.identity?.dirty
            ? ', and the engine reports uncommitted changes on top of it.'
            : '.')
        : verdict.why,
    action: null,
  });
}

/* ── The 401 path ────────────────────────────────────────────────────────── */

export type Recovery =
  /** A fresher token arrived. Retry the request once with `session`. */
  | { readonly kind: 'retry'; readonly session: EngineSession }
  /** Retrying cannot help, and `why` says so in words. */
  | { readonly kind: 'stuck'; readonly why: string };

/**
 * A 401 came back. Re-read the session once and say whether retrying is worth
 * anything.
 *
 * `tokenUsed` is the token the failed request actually presented, NOT whatever
 * is cached now — twelve requests can 401 in the same tick and the first
 * recovery replaces the cache before the twelfth asks. Comparing against the
 * cache would tell eleven of them that nothing changed.
 */
export async function recoverFromUnauthorized(
  tokenUsed: string | null,
): Promise<Recovery> {
  const session = await refreshEngineSession();

  if (!session.available) {
    const why =
      session.reason ??
      'The engine is not running, so there is no token to pick up.';
    publish({
      kind: 'gone',
      severity: 'stop',
      headline: 'The engine is not running.',
      detail: why,
      action: 'Start it, then reload this page.',
    });
    return { kind: 'stuck', why };
  }

  if (session.token && session.token !== tokenUsed) {
    /* The ordinary case, and the one that had no answer before: the engine
       restarted, minted a new token, published it, and this page was still
       holding the old one. Take the new one and let the caller retry. */
    const before = baseline;
    baseline = session.identity;
    baselineTaken = true;
    const change =
      before && session.identity
        ? compareEngines(before, session.identity)
        : ({ kind: 'restarted', changed: [] } as const);
    publishChange({
      kind: change.kind === 'rebuilt' ? 'rebuilt' : 'restarted',
      severity: 'warn',
      headline:
        change.kind === 'rebuilt'
          ? 'The engine is running different code than when this page loaded.'
          : 'The engine restarted.',
      detail: [
        `Its bearer token rotated, which is why requests started failing ` +
          `(pid ${pidOf(before)} → ${pidOf(session.identity)}). This page ` +
          `picked up the new one and retried.`,
        change.kind === 'rebuilt'
          ? describeCode(before, session.identity)
          : unverifiableCodeNote(session),
      ]
        .filter(Boolean)
        .join(' '),
      action: 'Reload if the answers stop making sense.',
    });
    return { kind: 'retry', session };
  }

  /* engine.json publishes the SAME token the engine just refused. Reloading
     re-reads the same file and gets the same rejected secret, so saying
     "reload" here would be the third wrong instruction in a row. What is
     actually true: the process on that port is not the process that wrote the
     portfile — `write_portfile` refuses to overwrite a portfile whose owner is
     still alive, so a second engine cannot publish and the first one's token is
     the one on disk. */
  const why =
    `The engine refused this page’s token, and engine.json still publishes the ` +
    `same one. The process answering on ${session.engineBaseUrl ?? 'that port'} ` +
    `is not the process that wrote engine.json, so reloading would read the same ` +
    `rejected token again.`;
  publish({
    kind: 'reload',
    severity: 'stop',
    headline: 'The engine refused this page, and reloading will not fix it.',
    detail: why,
    action: 'Restart it to put one engine on this build.',
  });
  return { kind: 'stuck', why };
}

/* ── The watch ───────────────────────────────────────────────────────────── */

/**
 * How often to ask. A local file read plus one loopback `GET /health`, so the
 * cost is not the reason for the number — the number is how long a person
 * should be allowed to keep reading answers from an engine that changed
 * underneath them. Fifteen seconds is under the engine's own 25s stream
 * timeout, so a restart is noticed inside one reconnection cycle.
 */
const PROBE_MS = 15_000;

let watchers = 0;
let timer: ReturnType<typeof setInterval> | null = null;

function wake(): void {
  if (document.visibilityState === 'visible') void probeEngine();
}

/**
 * Start watching; the returned function stops. Reference counted, so several
 * mounted components share one timer.
 *
 * Also probes on focus and on tab-visible, because the case that matters is a
 * tab left open — and a tab left open is exactly the one that has been in the
 * background while the engine was restarted.
 */
export function startEngineWatch(): () => void {
  watchers += 1;
  if (watchers === 1) {
    void engineSession().then(() => probeEngine());
    timer = setInterval(() => void probeEngine(), PROBE_MS);
    window.addEventListener('focus', wake);
    document.addEventListener('visibilitychange', wake);
  }
  return () => {
    watchers -= 1;
    if (watchers === 0) {
      if (timer !== null) clearInterval(timer);
      timer = null;
      window.removeEventListener('focus', wake);
      document.removeEventListener('visibilitychange', wake);
    }
  };
}
