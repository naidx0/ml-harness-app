"""The page and the engine have to agree about which engine this is.

WHAT THIS IS ABOUT. On 2026-08-20 an engine was reported to Max as "restarted
and confirmed" three times and was never restarted once. `engine.json` published
`pid: 24636`; the process listening on 8078 was `23220`, so the taskkill killed
something else. The replacement died on `[Errno 10048] only one usage of each
socket address` into a log nobody reads. `GET /health` answered `{"status":"ok"}`
- from the *stale* engine - so the check passed and told nobody anything. And
because that engine was old code, `GET /local_specs` returned `gpu_name: null`
for an installed, idle RTX 2060 SUPER.

Every one of those is the same gap: `engine.json` says where the engine is and
how to talk to it, and nothing that says WHAT IT IS. This file holds the two
halves of closing it against each other:

  * what `app/security.py write_portfile` actually publishes, obtained by
    calling it rather than by reading its source, and
  * how `frontend/src/lib/engine/identity.ts` classifies what it finds there,
    obtained by RUNNING it rather than by grepping it.

The second half matters more than it looks. A test that asserted on the text of
a TypeScript file would pass whether or not that file works, which is precisely
the defect - a check that passes without checking - that cost the hour. Node 24
strips TypeScript types itself, so `tests/identity_probe.ts` runs with no
toolchain and no new dependency; when `node` is absent the probe tests skip and
say why instead of quietly reducing to nothing.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

from app import security

import support

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tests" / "identity_probe.ts"
IDENTITY_TS = ROOT / "frontend" / "src" / "lib" / "engine" / "identity.ts"
CONFIG_TS = ROOT / "frontend" / "src" / "lib" / "engine" / "config.ts"
CLIENT_TS = ROOT / "frontend" / "src" / "lib" / "engine" / "client.ts"
EVENTS_TS = ROOT / "frontend" / "src" / "lib" / "engine" / "events.ts"
VITE_CONFIG = ROOT / "frontend" / "vite.config.ts"

NODE = shutil.which("node")


def _portfile_keys(test) -> dict:
    """What the engine publishes, by publishing it.

    `support.sandbox` binds `security.ENGINE_FILE` into the test's own temp
    directory, so this writes a portfile without touching the checkout's real
    `engine.json` - the file the launcher, the CLI client and every local tool
    read the running engine's bearer token from.
    """
    support.sandbox(test)
    path = security.write_portfile(port=8078)
    return json.loads(path.read_text(encoding="utf-8"))


class WhatTheEnginePublishes(unittest.TestCase):
    def test_the_portfile_still_carries_what_the_client_navigates_by(self):
        """A rename here silently blinds the page. Name the keys out loud."""
        published = _portfile_keys(self)

        for key in ("host", "port", "base_url", "token", "pid"):
            self.assertIn(
                key,
                published,
                f"engine.json no longer publishes {key!r}. "
                "frontend/src/lib/engine/identity.ts classifies the portfile by "
                "role and this key had one; give it a role there before "
                "removing it here.",
            )

    def test_only_the_token_looks_like_a_secret(self):
        """The dev server forwards the portfile WHOLE so a new field reaches the
        page without an edit. That convenience is only safe while exactly one
        published field is secret and its name is caught by the filter."""
        published = _portfile_keys(self)
        import re

        pattern = re.compile(
            r"token|secret|password|credential|\bkeys?\b", re.IGNORECASE
        )
        secret = {key for key in published if pattern.search(key)}

        self.assertEqual(
            secret,
            {"token"},
            "A published field's name is no longer classified the way "
            "frontend/src/lib/engine/identity.ts SECRET_FIELD_PATTERN and "
            "frontend/vite.config.ts SECRET_FIELD classify it. Either the new "
            "field is a secret that would now be forwarded to the browser, or "
            "a real secret stopped being recognised as one.",
        )

    def test_the_token_rotates_on_every_start(self):
        """The premise of the whole 401-recovery path, asserted rather than
        assumed. `current_token` mints 256 bits per process; a tab left open
        across a restart is holding a secret the engine never heard of."""
        os.environ.pop("MLH_TOKEN", None)
        security.reset_token_for_tests()
        self.addCleanup(security.reset_token_for_tests)
        first = security.current_token()
        security.reset_token_for_tests()
        second = security.current_token()

        self.assertNotEqual(first, second)
        self.assertFalse(
            security.token_matches(f"Bearer {first}"),
            "The token a tab was holding before the restart is still accepted, "
            "which would mean the 401 this whole recovery path exists for "
            "cannot happen. It can.",
        )
        self.assertTrue(security.token_matches(f"Bearer {second}"))


@unittest.skipIf(
    NODE is None,
    "node is not on PATH, so frontend/src/lib/engine/identity.ts cannot be RUN. "
    "Skipped rather than replaced with an assertion about its source text: a "
    "check that passes without checking is the defect this file is about.",
)
class HowThePageClassifiesIt(unittest.TestCase):
    """Run the real module over a real portfile and read its answers.

    The portfile is written here by `app/security.py write_portfile`, into this
    test's sandbox, so nothing below describes the engine's payload from memory.
    """

    def setUp(self):
        self.published = _portfile_keys(self)
        result = subprocess.run(
            [NODE, str(PROBE), json.dumps(self.published)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
        )
        if result.returncode != 0:
            raise AssertionError(
                "tests/identity_probe.ts did not run:\n" + result.stderr
            )
        self.answers = json.loads(result.stdout)

    def test_the_token_never_becomes_part_of_an_identity(self):
        self.assertNotIn("token", self.answers["stripped_keys"])
        self.assertNotIn(
            self.published["token"],
            self.answers["identity_json"],
            "The bearer token reached the object the page keeps, compares, and "
            "puts in a title attribute.",
        )

    def test_every_published_field_lands_in_exactly_one_role(self):
        """`app/identity.py identity()` is what both halves are built from, and
        the roles are what stop a restart reading as a rebuild."""
        roles = self.answers["roles"]
        self.assertEqual(roles["location"], ["base_url", "host", "port"])
        self.assertEqual(
            roles["process"],
            ["engine", "pid"],
            "`engine` holds engine_id, pid and started_at, all of which move on "
            "an ordinary restart. In the code role it would make every restart "
            "of the same build announce itself as different code.",
        )
        self.assertIn("build", roles["code"])
        self.assertIn("schema", roles["code"])
        for key in roles["location"] + roles["process"] + roles["code"]:
            self.assertIn(key, self.published)

    def test_the_named_readers_read_what_the_engine_actually_wrote(self):
        named = self.answers["named"]
        self.assertEqual(named["revision"], self.published["build"]["sha"])
        self.assertEqual(
            named["code_fingerprint"],
            self.published["build"]["code_fingerprint"],
        )
        self.assertEqual(named["engine_id"], self.published["engine"]["engine_id"])
        self.assertEqual(named["dirty"], self.published["build"]["dirty"])

    def test_a_restart_is_told_apart_from_a_rebuild(self):
        self.assertEqual(self.answers["same"], {"kind": "same"})
        self.assertEqual(
            self.answers["restart"],
            {"kind": "restarted", "changed": ["engine", "pid"]},
        )
        self.assertEqual(
            self.answers["rebuild"], {"kind": "rebuilt", "changed": ["build"]}
        )

    def test_a_moved_code_fingerprint_is_not_read_as_the_same_engine(self):
        """The defect this assertion was written for, and it was real.

        `fingerprintOf` was `JSON.stringify(payload, Object.keys(payload).sort())`.
        That second argument is an ALLOWLIST applied at every depth, not a key
        order, so every nested field was silently deleted from the fingerprint
        and `build` fingerprinted as `{}`. An engine whose code fingerprint had
        changed therefore compared EQUAL to the one before it, and a page
        watching for a rebuilt engine answered `same` - a check that passed while
        the thing it checked was wrong, which is the whole subject of this file.
        Invisible to reading; obvious on the first real payload.
        """
        self.assertEqual(self.answers["rebuild"]["kind"], "rebuilt")

    def test_a_field_the_engine_does_not_publish_yet_reads_as_its_code(self):
        """The property the design rests on.

        This module was written before `app/identity.py` existed, against a
        portfile of five flat keys, and picked up `service`, `portfile_version`,
        `build` and `schema` without an edit. It has to keep doing that.
        """
        self.assertEqual(
            self.answers["unknown_field_is_code"],
            {"kind": "rebuilt", "changed": ["whatever_they_call_it_next"]},
        )

    def test_a_revision_is_read_from_where_it_is_written(self):
        """By NAME, and from 2026-09-21 by name only.

        The loose fallback scanned every value for anything revision-shaped,
        kept for "a later field that carries the revision under a name nobody
        has thought of". What it found in the packaged build - where the shell
        forwarded only the nested `engine` block and `build` never arrived -
        was `engine.engine_id`: 32 hex characters from `secrets.token_hex(16)`,
        new on every start. The page compared a random per-process id to a git
        commit, called the engine stale, and every restart minted a different
        id. Max pressed the button ten times and watched c467f06b become
        ba572ca while the sentence stayed.

        `revisionIn`'s own docstring already held the rule: a false revision is
        worse than no revision, because it turns "I cannot tell" into a
        confident accusation. A name nobody has thought of gets added to
        REVISION_FIELDS by whoever thinks of it.
        """
        self.assertEqual(
            self.answers["revision_from_build_sha"],
            "39667021e0be82b98a2f47f90c068489e9511de1",
        )
        self.assertIsNone(self.answers["revision_fallback"])

    def test_nothing_revision_shaped_is_mistaken_for_a_revision(self):
        """Every one of these is a real value in today's payload."""
        for case, what in (
            ("revision_not_a_fingerprint", "a 64-character sha256"),
            ("revision_not_a_path", "a filesystem path holding a uuid"),
            ("revision_not_a_timestamp", "a unix timestamp"),
            ("revision_absent", "nothing at all"),
        ):
            with self.subTest(case=case):
                self.assertIsNone(
                    self.answers[case],
                    f"{what} was read as the engine's revision. A false "
                    "revision turns 'I cannot tell' into a confident wrong "
                    "accusation that the engine is stale.",
                )

    def test_a_stale_engine_is_caught_and_a_current_one_is_not_accused(self):
        self.assertEqual(self.answers["checkout_matches"]["kind"], "matches")
        self.assertEqual(
            self.answers["checkout_matches_short"]["kind"],
            "matches",
            "Git's short form is seven characters and its long form is forty. "
            "The same commit must not read as two.",
        )
        self.assertEqual(self.answers["checkout_differs"]["kind"], "differs")

    def test_an_unanswerable_question_is_never_answered_ok(self):
        """The whole incident in one assertion.

        `GET /health` said `ok` while nothing had been checked. Here the cases
        where nothing CAN be checked come back `unverifiable` with the reason,
        and none of them comes back `matches`.
        """
        for case in (
            "checkout_unverifiable_no_engine_revision",
            "checkout_unverifiable_no_checkout",
        ):
            with self.subTest(case=case):
                verdict = self.answers[case]
                self.assertEqual(verdict["kind"], "unverifiable")
                self.assertTrue(verdict["why"].strip())

    def test_the_portfile_can_be_caught_describing_a_different_engine(self):
        """Defect 1 of the incident: engine.json named a process that was not
        the one on the socket. The health route cannot lie about that, so when
        both name what they are, disagreeing is a finding."""
        self.assertEqual(self.answers["published_agrees"], {"kind": "agree"})
        self.assertEqual(
            self.answers["published_disagrees"],
            {"kind": "disagree", "changed": ["build.code_fingerprint"]},
        )
        self.assertEqual(
            self.answers["published_disagrees_on_engine_id"],
            {"kind": "disagree", "changed": ["engine.engine_id"]},
        )

    def test_a_healthy_engine_is_never_accused_of_being_the_wrong_one(self):
        """The false accusation, which was real and was shipped for an hour.

        `GET /health` does not echo `identity()` verbatim: `app/main.py` merges
        `database_at` and `agrees` into `schema` and replaces `database` - a
        path string in the portfile - with an object. The portfile for its part
        carries `host`, `port`, `base_url` and a top-level `pid` the health
        payload has no reason to repeat.

        The first version of this comparison checked shared top-level keys for
        equality and, on the first run against a real engine, put a red strip
        across a perfectly healthy page saying the process on that port was not
        the one that wrote engine.json, with an instruction to go and kill
        things. A false accusation is worse than silence here: the entire value
        of this notice is that it appears only when it is true.
        """
        self.assertEqual(
            self.answers["published_agrees_when_health_enriches"],
            {"kind": "agree"},
        )

    def test_an_engine_too_old_to_say_what_it_is_is_itself_the_finding(self):
        """The live case, and the one `/health?expect_*` cannot catch.

        An engine old enough to be the problem ignores query parameters it has
        never heard of and answers 200 with the old `{"status":"ok"}`. Both
        halves of the new payload are built from `app/identity.py identity()`,
        so a portfile that names a build belongs to a process whose /health
        names one too - and when the socket says nothing, the socket is not that
        process.

        Reproduced by accident while verifying this change: an engine wrote its
        portfile during the lifespan, failed to bind with `[Errno 10048]`, and
        died, leaving a stale engine answering the old route under a portfile
        that described the dead one.
        """
        self.assertEqual(
            self.answers["answering_is_older"], {"kind": "answering-is-older"}
        )

    def test_nothing_published_is_not_an_identity(self):
        """An empty identity would compare equal to the next empty one and
        report 'same engine' - a claim nobody earned."""
        self.assertTrue(self.answers["empty_is_null"])
        self.assertTrue(self.answers["nonsense_is_null"])
        self.assertEqual(self.answers["changed_fields"], ["a", "b", "c"])


class TheTwoSidesStayInStep(unittest.TestCase):
    """Assertions about source text, kept to the few things that ARE text.

    Everything checkable by running code is checked by running it above. What is
    left here is the pair of literals that are duplicated on purpose - the dev
    server strips secrets in Node and the client strips them again in the
    browser - and the wiring that has no runtime this suite can reach.
    """

    def test_the_secret_filter_is_the_same_pattern_on_both_sides(self):
        pattern = r"/token|secret|password|credential|\bkeys?\b/i"
        self.assertTrue(
            pattern in IDENTITY_TS.read_text(encoding="utf-8"),
            f"identity.ts no longer contains the literal {pattern} — its "
            "SECRET_FIELD_PATTERN changed.",
        )
        self.assertTrue(
            pattern in VITE_CONFIG.read_text(encoding="utf-8"),
            f"vite.config.ts no longer contains the literal {pattern}. Its "
            "SECRET_FIELD drifted from identity.ts SECRET_FIELD_PATTERN. The "
            "dev server forwards the portfile WHOLE so a new engine field "
            "reaches the page without an edit; these two literals are the only "
            "thing stopping that from publishing the next secret somebody adds.",
        )

    def test_the_dev_server_forwards_the_portfile_and_the_checkout(self):
        source = VITE_CONFIG.read_text(encoding="utf-8")
        self.assertIn("engine: withoutSecrets(portfile)", source)
        self.assertIn("checkout,", source)
        self.assertNotIn(
            "child_process",
            source,
            "The checkout revision is read out of .git with readFileSync. A dev "
            "server that spawns git per page load is a habit this repository "
            "should not acquire.",
        )

    def test_a_401_is_recovered_from_exactly_once_in_both_callers(self):
        """Both things that talk to the engine have to survive a rotated token.

        `client.ts` is every request; `events.ts` is the one loop that runs
        forever and therefore the one that meets a restarted engine first. Before
        this, that loop retried the SAME dead token every eight seconds for as
        long as the tab stayed open.
        """
        for path in (CLIENT_TS, EVENTS_TS):
            with self.subTest(module=path.name):
                source = path.read_text(encoding="utf-8")
                self.assertIn("recoverFromUnauthorized", source)
                self.assertEqual(
                    source.count("recoverFromUnauthorized("),
                    1,
                    "Recovery is attempted once per failed request, not in a "
                    "loop: a second 401 after a fresh token is a different "
                    "fault and deserves reporting rather than hammering.",
                )

    def test_the_session_can_be_re_resolved(self):
        source = CONFIG_TS.read_text(encoding="utf-8")
        self.assertIn("export function refreshEngineSession", source)
        self.assertIn(
            "let refreshing",
            source,
            "Twelve requests can 401 in one tick. They must share one refresh, "
            "not become twelve opinions about which engine is answering.",
        )


if __name__ == "__main__":
    unittest.main()
