/**
 * WHICH ENGINE IS THIS, AND IS IT THE ONE I MEANT.
 *
 * ══ THE INCIDENT THIS FILE EXISTS FOR ══════════════════════════════════════
 *
 * On 2026-08-20 an engine was "restarted and confirmed" three times and was
 * never restarted once. Every step failed in a way that looked like success:
 *
 *   1. `engine.json` published `pid: 24636`. The process actually LISTENING on
 *      8078 was `23220`. Killing the published pid killed something else.
 *   2. The replacement engine died on `[Errno 10048] only one usage of each
 *      socket address` — into a log nobody reads.
 *   3. `GET /health` answered `{"status":"ok"}` — from the STALE engine. The
 *      check passed and told nobody anything.
 *   4. Because the stale engine was old code, `GET /local_specs` returned
 *      `gpu_name: null`, and the app would have said "I couldn't find a
 *      graphics card" with an RTX 2060 SUPER installed and idle.
 *
 * Every one of those is the same gap: `engine.json` carries `base_url`, `host`,
 * `pid`, `port`, `token` and NOTHING THAT SAYS WHAT CODE THIS IS. Neither a
 * person nor a program can check that the engine they are talking to is the
 * engine they meant.
 *
 * ══ WHAT THE ENGINE NOW PUBLISHES, READ RATHER THAN GUESSED ════════════════
 *
 * `app/identity.py identity()` is the one function both `engine.json` and
 * `GET /health` are built from, so the two cannot drift. It carries:
 *
 *   service          "ml-harness-engine"
 *   portfile_version 2
 *   engine           { engine_id, pid, launch_nonce, started_at, uptime_seconds }
 *   build            { sha, sha_source, sha_read_at, dirty, dirty_source, code_fingerprint,
 *                      code_files, python, executable }
 *   schema           { build_knows }
 *
 * This file was written before that landed, against an `engine.json` that
 * carried `host`, `port`, `base_url`, `token`, `pid` and nothing else. It was
 * written STRUCTURALLY for that reason, and it stays structural now that the
 * names are known, because the structure is what survives the next addition:
 *
 *   SECRET    — dropped before it ever reaches this file (see `stripSecrets`).
 *   LOCATION  — `host`, `port`, `base_url`. Where to knock. Stable across a
 *               restart, so a change here means the engine MOVED.
 *   PROCESS   — `pid`, and the whole `engine` block, which is `app/identity.py`
 *               `engine()` and holds nothing but facts about the process.
 *               Changes on every restart by definition.
 *   CODE      — **everything else**, whatever it is called.
 *
 * That last line is the trick, and it already paid: `service`,
 * `portfile_version`, `build` and `schema` all arrived without this file being
 * edited, and a change in any of them reads as "the engine is running different
 * code" rather than as "the engine restarted".
 *
 * On top of the structure sit NAMED readers — `revision`, `codeFingerprint`,
 * `engineId`, `dirty` — because a message that says "build.sha moved" is worse
 * than one that says which revision to which, and those names are now known
 * rather than assumed. Each returns `null` when its field is absent, and every
 * caller has to handle that, because an engine old enough to be the problem is
 * exactly the engine that does not publish them.
 *
 * `tests/test_the_page_can_tell_which_engine_it_is_talking_to.py` pins the two
 * halves together: it publishes a real portfile with `app/security.py
 * write_portfile` and runs this file over it, so the day a key changes role is
 * the day a test says so.
 *
 * ══ NOTHING HERE TOUCHES THE NETWORK OR THE DOM ════════════════════════════
 *
 * Pure functions over plain objects, so the reasoning can be read without a
 * browser. `liveness.ts` does the talking.
 */

/* ── The three roles ─────────────────────────────────────────────────────── */

/** Where to knock. Stable across a restart of the same engine. */
export const LOCATION_FIELDS = ['host', 'port', 'base_url'] as const;

/**
 * Which process is answering. Changes on every restart, always.
 *
 * `engine` is `app/identity.py engine()` — `{engine_id, pid, launch_nonce,
 * started_at, uptime_seconds}`. It belongs here rather than in CODE, and the
 * distinction is not cosmetic: `engine_id` and `started_at` move on every
 * ordinary restart, so leaving them in CODE would make every restart of the
 * SAME build announce itself as "the engine is running different code". A
 * detector that cries wolf on the ordinary case is a detector people turn off.
 */
export const PROCESS_FIELDS = ['pid', 'engine'] as const;

/**
 * Anything whose NAME suggests it carries a secret never gets this far.
 *
 * `token` is the only one today. The pattern is deliberately wider than that
 * one name: the dev server copies the portfile through to the page verbatim so
 * that a new field needs no code change, and "no code change" must not mean
 * "a new secret is published to the page the day someone adds one".
 */
export const SECRET_FIELD_PATTERN = /token|secret|password|credential|\bkeys?\b/i;

/**
 * A git revision, as it would appear inside whatever the engine publishes.
 *
 * Seven to forty hex characters, **and at least one letter**. The letter
 * requirement is not decoration: without it this matches a unix timestamp, a
 * port range and a row count, and a false revision is worse than no revision
 * because it turns "I cannot tell" into a confident wrong answer.
 */
const REVISION_PATTERN = /\b(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b/gi;

/* ── The identity itself ─────────────────────────────────────────────────── */

export interface EngineIdentity {
  /** Everything published, minus anything that looked like a secret. */
  readonly all: Readonly<Record<string, unknown>>;
  readonly location: Readonly<Record<string, unknown>>;
  readonly process: Readonly<Record<string, unknown>>;
  /** Every field that is not location, process or secret — see the header. */
  readonly code: Readonly<Record<string, unknown>>;
  /** Stable, order-independent string form. Equal fingerprints mean the engine
   *  published the same thing twice. */
  readonly fingerprint: string;
  /**
   * The revision the engine claims, if it claims one at all — `build.sha`.
   *
   * `null` is a real answer: it means the engine says nothing about what code
   * it is running, which is exactly what an engine old enough to BE the problem
   * says. Every caller has to handle it, which is the point.
   */
  readonly revision: string | null;
  /**
   * `build.code_fingerprint` — a sha256 over the engine's own source files.
   *
   * Stronger than `revision` for the question this page actually asks. The
   * engine's checkout is routinely dirty (`build.dirty` was `true` the day this
   * was written), and two engines at the same commit with different uncommitted
   * edits are different engines. The commit says which branch of history; this
   * says which bytes.
   */
  readonly codeFingerprint: string | null;
  /** `engine.engine_id` — one process, one id. What `/health?expect_engine=`
   *  is answered against. */
  readonly engineId: string | null;
  /** `build.dirty`. `true` means the sha above names the commit the engine
   *  was built ON, not the code it is running. */
  readonly dirty: boolean | null;
}

/** Read one nested value without pretending a missing branch is a value. */
function at(payload: Readonly<Record<string, unknown>>, ...path: string[]): unknown {
  let here: unknown = payload;
  for (const step of path) {
    if (!here || typeof here !== 'object') return undefined;
    here = (here as Record<string, unknown>)[step];
  }
  return here;
}

const stringAt = (
  payload: Readonly<Record<string, unknown>>,
  ...path: string[]
): string | null => {
  const value = at(payload, ...path);
  return typeof value === 'string' && value.length > 0 ? value : null;
};

/** Drop anything whose key looks secret. Applied before a payload is stored,
 *  compared, logged, or put in a `title` attribute. */
export function stripSecrets(
  payload: Readonly<Record<string, unknown>>,
): Record<string, unknown> {
  const kept: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(payload)) {
    if (SECRET_FIELD_PATTERN.test(key)) continue;
    kept[key] = value;
  }
  return kept;
}

/**
 * Read an identity out of whatever the engine published.
 *
 * `null` when there is nothing there — not an empty identity. An empty
 * identity would compare equal to the next empty identity and report "same
 * engine", which is a claim we would not have earned.
 */
export function readIdentity(raw: unknown): EngineIdentity | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const all = stripSecrets(raw as Record<string, unknown>);
  if (Object.keys(all).length === 0) return null;

  const location: Record<string, unknown> = {};
  const process: Record<string, unknown> = {};
  const code: Record<string, unknown> = {};

  for (const [key, value] of Object.entries(all)) {
    if ((LOCATION_FIELDS as readonly string[]).includes(key)) location[key] = value;
    else if ((PROCESS_FIELDS as readonly string[]).includes(key)) process[key] = value;
    else code[key] = value;
  }

  const dirty = at(all, 'build', 'dirty');

  return {
    all,
    location,
    process,
    code,
    fingerprint: fingerprintOf(all),
    revision: revisionIn(code),
    codeFingerprint: stringAt(all, 'build', 'code_fingerprint'),
    engineId: stringAt(all, 'engine', 'engine_id'),
    dirty: typeof dirty === 'boolean' ? dirty : null,
  };
}

/**
 * JSON with the keys sorted at EVERY level, so `{a,b}` and `{b,a}` are one
 * string and two readings of the same payload cannot differ by key order.
 *
 * ── A DEFECT THIS FUNCTION HAD, FOUND BY RUNNING IT ─────────────────────────
 *
 * It was one line: `JSON.stringify(payload, Object.keys(payload).sort())`. The
 * second argument of `JSON.stringify` is not a key ORDER, it is a key
 * ALLOWLIST, and it applies at every depth. So every nested field whose name
 * did not also happen to be a top-level key was silently deleted from the
 * fingerprint: `build` fingerprinted as `{}`, and `engine` as `{"pid":…}`
 * because `pid` exists at the top level too.
 *
 * The consequence was the exact failure this module exists to prevent. An
 * engine whose `build.code_fingerprint` had changed compared EQUAL to the one
 * before it, so a page watching for a rebuilt engine reported `same` — a check
 * that passed while the thing it was checking was wrong. It was invisible to
 * reading and obvious the moment the module was run against a real portfile.
 * `tests/identity_probe.ts` case `rebuild` is that case, kept.
 */
export function fingerprintOf(payload: Readonly<Record<string, unknown>>): string {
  return stableStringify(payload);
}

/** Deterministic JSON: objects sorted by key, recursively. */
export function stableStringify(value: unknown): string {
  if (value === null || typeof value !== 'object') {
    return JSON.stringify(value) ?? 'null';
  }
  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).join(',')}]`;
  }
  const entries = Object.entries(value as Record<string, unknown>).sort(
    ([left], [right]) => (left < right ? -1 : left > right ? 1 : 0),
  );
  return `{${entries
    .map(([key, nested]) => `${JSON.stringify(key)}:${stableStringify(nested)}`)
    .join(',')}}`;
}

/**
 * The revision the engine says it is at.
 *
 * `build.sha` first, because that is the field `app/identity.py build()`
 * actually writes and a named lookup cannot be fooled. The near-misses it
 * skips past are all real values in today's payload: `build.code_fingerprint`
 * is a 64-character sha256, `engine.engine_id` is 32 hex characters from
 * `secrets.token_hex(16)`, and `database` is a path that on this machine
 * contains the hex-looking segments of a session uuid. A loose search over the
 * whole payload finds whichever of those the key order happens to reach first.
 *
 * The fallback is kept for the payload after this one — some later field may
 * carry the revision under a name nobody has thought of — and it is deliberately
 * strict: a STRING VALUE that is a revision end to end, never a revision-shaped
 * fragment inside a longer string. A false revision is worse than no revision,
 * because it turns "I cannot tell" into a confident accusation that the engine
 * is stale.
 */
export function revisionIn(code: Readonly<Record<string, unknown>>): string | null {
  for (const path of REVISION_FIELDS) {
    const named = stringAt(code, ...path);
    if (named && isRevision(named)) return named.toLowerCase();
  }
  /* THE LOOSE FALLBACK IS GONE, and the paragraph above predicted why. It
     scanned every value for anything revision-shaped, "kept for the payload
     after this one - some later field may carry the revision under a name
     nobody has thought of". What it actually found, in the packaged build
     where `build` never arrived, was `engine.engine_id`: 32 hex characters
     from `secrets.token_hex(16)`, new on every start. The page compared a
     random per-process id to a git commit, called the engine stale, and a
     restart could only mint a different random id - which is what Max watched
     for ten presses, c467f06b becoming ba572ca while the sentence stayed.

     Its own docstring had the rule: a false revision is worse than no
     revision, because it turns "I cannot tell" into a confident accusation.
     A field nobody has thought of gets added to REVISION_FIELDS by whoever
     thinks of it. */
  return null;
}

/** Where a revision is actually published, most specific first. */
const REVISION_FIELDS: readonly (readonly string[])[] = [
  ['build', 'sha'],
  ['build', 'revision'],
  ['build', 'commit'],
  ['revision'],
  ['commit'],
  ['sha'],
];

function isRevision(value: string): boolean {
  REVISION_PATTERN.lastIndex = 0;
  const match = REVISION_PATTERN.exec(value);
  return match !== null && match[0].length === value.length;
}

/* ── Did the engine change under us ──────────────────────────────────────── */

export type EngineChange =
  /** Byte-for-byte what it published last time. */
  | { readonly kind: 'same' }
  /** A new process, or the same process at a new address. Same code, as far as
   *  the engine is willing to say — which may be not at all. */
  | { readonly kind: 'restarted'; readonly changed: readonly string[] }
  /** A field outside location and process moved. The engine is not running the
   *  code it was running when this page loaded. */
  | { readonly kind: 'rebuilt'; readonly changed: readonly string[] };

/** Which keys differ between two payloads, including keys present in only one. */
export function changedFields(
  before: Readonly<Record<string, unknown>>,
  after: Readonly<Record<string, unknown>>,
): string[] {
  const keys = new Set([...Object.keys(before), ...Object.keys(after)]);
  const moved: string[] = [];
  for (const key of [...keys].sort()) {
    /* `stableStringify`, not `JSON.stringify`: two readings of one nested
       object must not differ because their keys arrived in another order. */
    if (stableStringify(before[key]) !== stableStringify(after[key])) moved.push(key);
  }
  return moved;
}

export function compareEngines(
  before: EngineIdentity,
  after: EngineIdentity,
): EngineChange {
  if (before.fingerprint === after.fingerprint) return { kind: 'same' };
  const codeMoved = changedFields(before.code, after.code);
  const changed = changedFields(before.all, after.all);
  return codeMoved.length > 0
    ? { kind: 'rebuilt', changed }
    : { kind: 'restarted', changed };
}

/* ── Is it the code this page was served from ────────────────────────────── */

/** What the dev server says about the checkout it is serving the page from. */
export interface Checkout {
  readonly revision: string;
  /** The file that was read to get it, so the claim can be checked by hand. */
  readonly source: string;
}

export type CheckoutVerdict =
  /** The engine names a revision and it is this checkout's. */
  | { readonly kind: 'matches'; readonly revision: string }
  /** The engine names a revision and it is a DIFFERENT one. This is the stale
   *  engine, caught. */
  | {
      readonly kind: 'differs';
      readonly engine: string;
      readonly checkout: string;
    }
  /** Nobody is lying; the question cannot be answered. `why` says which half
   *  is missing, in words a person can act on. */
  | { readonly kind: 'unverifiable'; readonly why: string };

/**
 * Compare what the engine says it is running against what this page was served
 * from.
 *
 * **`unverifiable` is the honest answer today and it is not a failure.** The
 * engine publishes no revision, so there is no comparison to make, and saying
 * so is the entire value of this function until that changes. The alternative —
 * returning `matches` when nothing was checked — is the health check that
 * answered `ok` from a stale process, rewritten in TypeScript.
 *
 * Prefix comparison in both directions, because one side is routinely
 * abbreviated: git's short form is 7 characters and the full form is 40, and
 * `3966702` and `3966702f4c…` are the same commit.
 */
export function checkAgainstCheckout(
  identity: EngineIdentity | null,
  checkout: Checkout | null,
): CheckoutVerdict {
  if (!checkout) {
    return {
      kind: 'unverifiable',
      why:
        'the dev server could not read this checkout’s revision from ' +
        '.git, so there is nothing to compare the engine against',
    };
  }
  if (!identity || identity.revision === null) {
    return {
      kind: 'unverifiable',
      why:
        'the engine does not publish which code it is running — engine.json ' +
        'carries where it is and how to talk to it, and nothing that says what ' +
        'it is — so this page cannot tell whether it is current',
    };
  }
  const engine = identity.revision.toLowerCase();
  const here = checkout.revision.toLowerCase();
  const same = engine.startsWith(here) || here.startsWith(engine);
  return same
    ? { kind: 'matches', revision: engine }
    : { kind: 'differs', engine, checkout: here };
}

/* ── Does engine.json describe the engine that is actually answering ─────── */

export type PublishedVerdict =
  | { readonly kind: 'agree' }
  /** `engine.json` describes one engine and another one is answering on that
   *  port. Defect 1 of the incident, caught rather than survived. */
  | { readonly kind: 'disagree'; readonly changed: readonly string[] }
  /**
   * The portfile says what its writer is; the process on the socket says
   * nothing. They cannot be the same process — see the note in the function.
   */
  | { readonly kind: 'answering-is-older' }
  | { readonly kind: 'unverifiable'; readonly why: string };

/**
 * `engine.json` is written by whichever process got there first, and
 * `write_portfile` deliberately refuses to overwrite a portfile whose owning
 * pid is still alive. Both rules are right and both mean the file can describe
 * a process that is not the one on the socket. The health route cannot: it is
 * answered by the process actually listening.
 *
 * So when both name what they are, disagreeing is a finding.
 *
 * ── AND WHEN ONLY ONE OF THEM NAMES ANYTHING ────────────────────────────────
 *
 * `answering-is-older` is not a hedge, it is an inference, and it is the one
 * that catches today's live case. Both halves come from the same function —
 * `app/identity.py identity()` builds the portfile and the health payload — so
 * a process whose portfile carries `build` and `service` is a process whose
 * `/health` carries them too. If the portfile has them and the socket does not,
 * the thing on the socket is not the thing that wrote the file, and the only
 * way it can be answering an older `/health` is by running older code.
 *
 * This was verified by accident and then on purpose: an engine started for this
 * change wrote its portfile in the lifespan, failed to bind with `[Errno 10048]`,
 * and died — leaving a stale engine on the port answering the OLD
 * `{"status":"ok"}` under a portfile that described the dead one. The
 * `expect_*` query parameters on the new `/health` cannot catch that, because
 * an engine old enough to be the problem ignores query parameters it has never
 * heard of and answers 200. This can.
 */
export function comparePublishedToAnswering(
  published: EngineIdentity | null,
  answering: EngineIdentity | null,
): PublishedVerdict {
  const publishedCode = published?.code ?? {};
  const answeringCode = answering?.code ?? {};
  if (
    Object.keys(publishedCode).length > 0 &&
    Object.keys(answeringCode).length === 0
  ) {
    return { kind: 'answering-is-older' };
  }
  if (!published || !answering || Object.keys(answeringCode).length === 0) {
    return {
      kind: 'unverifiable',
      why:
        'engine.json and GET /health have no field in common that names the ' +
        'engine, so there is no way to check that they describe the same one',
    };
  }
  const changed = contradictions(published.all, answering.all);
  return changed.length === 0 ? { kind: 'agree' } : { kind: 'disagree', changed };
}

/**
 * Leaves of `published` that `answering` gives a DIFFERENT value for.
 *
 * A subset check, not an equality check, and the difference matters. The two
 * payloads are the same identity seen from two places, and neither is a
 * complete copy of the other:
 *
 *   - `app/main.py health()` ENRICHES what `identity()` gave it. It merges
 *     `database_at` and `agrees` into `schema`, and it replaces `database`
 *     (a path string in the portfile) with an object. Both are the route adding
 *     what it learned, not the engine contradicting itself.
 *   - `engine.json` carries `host`, `port`, `base_url` and a top-level `pid`
 *     that the health payload has no reason to repeat.
 *
 * An equality check over shared top-level keys called both of those a
 * disagreement. **It was written that way and it was wrong, and the way that
 * showed up is the point: the page accused a perfectly healthy engine of not
 * being the engine engine.json described, in red, with an instruction to go and
 * kill processes.** A false accusation is worse than silence here, because the
 * whole value of this notice is that it only appears when something is true.
 *
 * So: only a leaf present on BOTH sides, scalar on both sides, and different,
 * counts. A missing leaf is not evidence. A leaf that is a string here and an
 * object there is a difference in what the two views are FOR, not in what the
 * engine is.
 */
export function contradictions(
  published: Readonly<Record<string, unknown>>,
  answering: Readonly<Record<string, unknown>>,
): string[] {
  const found: string[] = [];
  walk(published, []);
  return found;

  function walk(node: Readonly<Record<string, unknown>>, path: string[]): void {
    for (const [key, value] of Object.entries(node)) {
      const here = [...path, key];
      if (IGNORED_LEAVES.has(key)) continue;
      if (value && typeof value === 'object' && !Array.isArray(value)) {
        walk(value as Record<string, unknown>, here);
        continue;
      }
      const theirs = at(answering, ...here);
      if (theirs === undefined) continue;
      if (theirs && typeof theirs === 'object') continue;
      if (stableStringify(value) !== stableStringify(theirs)) {
        found.push(here.join('.'));
      }
    }
  }
}

/**
 * Leaves that legitimately differ between one reading and the next.
 *
 * `uptime_seconds` is `0` in the portfile — written during startup — and
 * whatever it is now over the socket. It is a clock, not an identity, and
 * comparing it would make every check after the first second disagree.
 */
const IGNORED_LEAVES = new Set(['uptime_seconds']);
