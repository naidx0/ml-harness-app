/**
 * The Node half of `tests/test_the_page_can_tell_which_engine_it_is_talking_to.py`.
 *
 * WHY A .ts FILE IN tests/. `frontend/src/lib/engine/identity.ts` is the module
 * that decides whether the page believes it is talking to the engine it meant,
 * and this repository has no JavaScript test runner — adding one is its own
 * step (AGENTS.md: "New dependencies get their own step"). Asserting on the
 * SOURCE TEXT of that module from Python would be the same defect the module
 * exists to remove: a check that passes without checking anything.
 *
 * So the Python test runs this file with `node` (24.x strips the types itself,
 * no toolchain, no dependency) and reads one JSON object off stdout. If `node`
 * is not on the path the Python test skips and says so, rather than pretending.
 *
 * `process.argv[2]` is a REAL portfile, written by `app/security.py
 * write_portfile` into the Python test's sandbox moments earlier. Nothing here
 * describes the engine's payload from memory; the cases below that use a
 * literal are the ones about payloads the engine does NOT produce — an older
 * engine's, a stale one's, a future one's.
 */

import {
  changedFields,
  checkAgainstCheckout,
  compareEngines,
  comparePublishedToAnswering,
  readIdentity,
  revisionIn,
  stripSecrets,
} from '../frontend/src/lib/engine/identity.ts';

const portfile = JSON.parse(process.argv[2] ?? '{}') as Record<string, unknown>;

const answers: Record<string, unknown> = {};

/* ── The token never becomes part of an identity ─────────────────────────── */

answers.stripped_keys = Object.keys(stripSecrets(portfile)).sort();
answers.identity_json = JSON.stringify(readIdentity(portfile));

/* ── Every published key lands in exactly one role ───────────────────────── */

const identity = readIdentity(portfile)!;
answers.roles = {
  location: Object.keys(identity.location).sort(),
  process: Object.keys(identity.process).sort(),
  code: Object.keys(identity.code).sort(),
};

/* ── The named readers, off the real payload ─────────────────────────────── */

answers.named = {
  revision: identity.revision,
  code_fingerprint: identity.codeFingerprint,
  engine_id: identity.engineId,
  dirty: identity.dirty,
};

/* ── A restart is not a rebuild ──────────────────────────────────────────────
   `app/identity.py engine()` moves entirely on a restart — a new engine_id, a
   new pid, a new started_at — while `build` stays put. That has to read as
   "restarted", not as "running different code", or the detector cries wolf on
   the single most ordinary event there is. */

const engineBlock = (portfile.engine ?? {}) as Record<string, unknown>;
const before = readIdentity(portfile)!;
const restarted = readIdentity({
  ...portfile,
  token: 'rotated-on-every-start',
  pid: 24636,
  engine: {
    ...engineBlock,
    engine_id: 'ffffffffffffffffffffffffffffffff',
    pid: 24636,
    started_at: '2026-08-20T20:00:00+00:00',
  },
})!;
answers.restart = compareEngines(before, restarted);
answers.same = compareEngines(before, readIdentity(portfile)!);

/* ── A rebuild IS a rebuild ──────────────────────────────────────────────── */

const buildBlock = (portfile.build ?? {}) as Record<string, unknown>;
const rebuilt = readIdentity({
  ...portfile,
  build: { ...buildBlock, code_fingerprint: 'a'.repeat(64), sha: 'b'.repeat(40) },
})!;
answers.rebuild = compareEngines(before, rebuilt);

/* ── A field NOBODY has invented yet still reads as code identity ─────────
   The property the design rests on: this module was written before
   `app/identity.py` existed, against a portfile of five flat keys, and picked
   up `service`, `portfile_version`, `build` and `schema` without an edit. It
   has to keep doing that for the next one. */

const future = readIdentity({
  ...portfile,
  whatever_they_call_it_next: { commit: 'deadbee' },
})!;
answers.unknown_field_is_code = compareEngines(before, future);

/* ── Revisions are found by name first, and by shape only as a fallback ──── */

answers.revision_from_build_sha = revisionIn({
  build: { sha: '39667021e0be82b98a2f47f90c068489e9511de1' },
});
/* A sha256 code fingerprint is 64 hex characters and is NOT a revision. Before
   the named lookup, a loose search over the payload could return whichever of
   these the key order reached first. */
answers.revision_not_a_fingerprint = revisionIn({
  build: { code_fingerprint: 'a'.repeat(64) },
});
/* The `database` field is a path, and on this machine it contains the hex
   segments of a session uuid. A revision-shaped FRAGMENT inside a longer
   string is not a revision. */
answers.revision_not_a_path = revisionIn({
  database: 'C:\\Temp\\claude\\95a6345b-2d3c-44f9-ad75-3c543aa629e6\\verify.db',
});
/* A unix timestamp is hex-legal. Reading one as a revision would turn "I
   cannot tell" into a confident wrong answer about staleness. */
answers.revision_not_a_timestamp = revisionIn({ started_at: 1755648000 });
answers.revision_absent = revisionIn({});
answers.revision_fallback = revisionIn({ some_future_name: 'abc1234' });

/* ── The checkout comparison ─────────────────────────────────────────────── */

const atRevision = (sha: string) =>
  readIdentity({ ...portfile, build: { ...buildBlock, sha } })!;

answers.checkout_matches = checkAgainstCheckout(
  atRevision('39667021e0be82b98a2f47f90c068489e9511de1'),
  { revision: '39667021e0be82b98a2f47f90c068489e9511de1', source: '.git/HEAD' },
);
/* Git's short form is seven characters and its long form is forty. The same
   commit must not read as two. */
answers.checkout_matches_short = checkAgainstCheckout(
  atRevision('39667021e0be82b98a2f47f90c068489e9511de1'),
  { revision: '3966702', source: '.git/HEAD' },
);
answers.checkout_differs = checkAgainstCheckout(
  atRevision('8559485a11b2c3d4e5f60718293a4b5c6d7e8f90'),
  { revision: '39667021e0be82b98a2f47f90c068489e9511de1', source: '.git/HEAD' },
);
/* The two ways the question cannot be answered. Neither may come back
   `matches` — that is the health check that said `ok` from a stale engine,
   rewritten in TypeScript. */
answers.checkout_unverifiable_no_engine_revision = checkAgainstCheckout(
  readIdentity({ host: '127.0.0.1', port: 8078, pid: 1 }),
  { revision: '3966702', source: '.git/HEAD' },
);
answers.checkout_unverifiable_no_checkout = checkAgainstCheckout(
  atRevision('39667021e0be82b98a2f47f90c068489e9511de1'),
  null,
);

/* ── engine.json versus the process actually answering ───────────────────── */

answers.published_agrees = comparePublishedToAnswering(
  identity,
  readIdentity(stripSecrets(portfile)),
);

/* THE FALSE ACCUSATION, kept because it was real and it was shipped.
 *
 * `GET /health` does not echo `identity()` verbatim. `app/main.py` MERGES
 * `database_at` and `agrees` into `schema`, and REPLACES `database` — a path
 * string in the portfile — with an object. `engine.json` for its part carries
 * `host`, `port`, `base_url` and a top-level `pid` that the health payload has
 * no reason to repeat.
 *
 * The first version of `comparePublishedToAnswering` compared shared top-level
 * keys for equality, and on the very first run against a real engine it
 * reported `disagree` on `schema, database` — putting a red strip on a
 * perfectly healthy page telling the user to go and kill processes. This is
 * that exact payload pair. */
answers.published_agrees_when_health_enriches = comparePublishedToAnswering(
  identity,
  readIdentity({
    service: portfile.service,
    portfile_version: portfile.portfile_version,
    engine: { ...engineBlock, uptime_seconds: 412.7 },
    build: buildBlock,
    schema: { ...(portfile.schema as object), database_at: 9, agrees: true },
    database: { path: portfile.database, rows: 0 },
    checks: [{ name: 'database_opens', ok: true, detail: 'opened' }],
  }),
);
/* A real disagreement still has to be caught: the answering engine's build
   fingerprint is not the one the portfile named. */
answers.published_disagrees = comparePublishedToAnswering(
  identity,
  readIdentity({
    ...stripSecrets(portfile),
    build: { ...buildBlock, code_fingerprint: 'c'.repeat(64) },
  }),
);
/* And so does a different process behind the same portfile. */
answers.published_disagrees_on_engine_id = comparePublishedToAnswering(
  identity,
  readIdentity({
    ...stripSecrets(portfile),
    engine: { ...engineBlock, engine_id: 'f'.repeat(32) },
  }),
);
/* THE LIVE CASE, and the one the engine's own `expect_*` parameters cannot
   catch. An engine old enough to be the problem ignores query parameters it
   has never heard of and answers 200 with the old `{"status":"ok"}` — which,
   with `status` dropped, is nothing at all. Both halves of the new payload come
   from one function, so a portfile that names a build belongs to a process
   whose /health names one too. */
answers.answering_is_older = comparePublishedToAnswering(
  identity,
  readIdentity({}),
);

/* ── Empty is not an identity ────────────────────────────────────────────── */

answers.empty_is_null = readIdentity({}) === null;
answers.nonsense_is_null = readIdentity('a string') === null;
answers.changed_fields = changedFields({ a: 1, b: 2 }, { b: 3, c: 4 });

process.stdout.write(JSON.stringify(answers));
