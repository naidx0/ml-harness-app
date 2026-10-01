"""`GET /health` used to be `return {"status": "ok"}`.

It proved that a FastAPI app was listening. That was never the question, and on
the evening this work comes from it answered `ok` three times in a row from a
STALE engine holding port 8078 while the engine somebody believed they had
restarted was dead. "Restarted and confirmed" was reported to the user on that
evidence, and the interface then told him he had no graphics card on a machine
with an idle RTX 2060 SUPER, because the engine answering was old code.

The design rule these tests hold the route to:

    A CHECK WRITTEN AGAINST THIS ROUTE MUST NOT BE ABLE TO PASS WHILE THE
    THING IT IS CHECKING IS WRONG.

There are two halves and neither alone gets there.

*The engine says whether IT is consistent* - the `checks` list, and a 503 when
any of them fails, so `curl -f` cannot read a broken engine as a working one.

*The CALLER says what it expects and is told when it is wrong* - the `expect_*`
parameters, answered with 409. This is the half that catches a stale engine,
and it cannot be had without the caller's participation: an engine running last
week's code is entirely consistent with itself and has no way to know it is not
what you meant.
"""

from __future__ import annotations

import json
import unittest

import support

from app import db, identity
from app.main import app


class HealthReportsWhatItActuallyChecked(unittest.TestCase):
    def setUp(self):
        support.sandbox(self)
        self.client = support.api_client(app)

    def test_it_is_ok_and_says_why(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["service"], "ml-harness-engine")
        names = [check["name"] for check in body["checks"]]
        self.assertEqual(
            names, ["database_opens", "schema_agrees", "answers_a_real_query"]
        )
        self.assertTrue(all(check["ok"] for check in body["checks"]))

    def test_it_carries_the_same_identity_the_portfile_does(self):
        """One source of truth. A portfile that described a slightly different
        build from the socket would put the ambiguity straight back.
        """
        body = self.client.get("/health").json()
        expected = identity.identity()
        self.assertEqual(body["engine"]["engine_id"], expected["engine"]["engine_id"])
        self.assertEqual(
            body["build"]["code_fingerprint"], expected["build"]["code_fingerprint"]
        )
        self.assertEqual(body["portfile_version"], expected["portfile_version"])

    def test_it_names_the_database_it_opened_and_proves_it_read_from_it(self):
        """`SELECT 1` would prove the connection and nothing else. `runs` is
        migration 1's table and `harness_instance` carries the identity every
        artifact path is keyed on; reading both proves the schema is there.
        """
        db.create_run("a-real-row", "{}")
        body = self.client.get("/health").json()
        self.assertEqual(body["database"]["path"], str(db.DB_PATH))
        self.assertEqual(body["database"]["runs"], 1)
        self.assertEqual(
            body["database"]["instance_id"], db.get_instance()["instance_id"]
        )

    def test_it_reports_both_schema_numbers(self):
        body = self.client.get("/health").json()
        self.assertEqual(body["schema"]["build_knows"], identity.known_schema_version())
        self.assertEqual(body["schema"]["database_at"], identity.known_schema_version())
        self.assertTrue(body["schema"]["agrees"])

    def test_polling_it_does_not_write_to_the_database(self):
        """A launcher hits this in a loop. `db.get_instance()` was the natural
        call for the instance id and it does an `INSERT OR IGNORE`, which opens
        a write transaction on every poll.
        """
        before = support.database_fingerprint(db.DB_PATH)
        for _ in range(5):
            self.client.get("/health")
        self.assertEqual(before, support.database_fingerprint(db.DB_PATH))

    def test_it_never_carries_the_token(self):
        """It is unauthenticated on purpose - a client that has not read
        `engine.json` yet still has to be able to ask whether this is the right
        engine - so anything in the body is public to every local process.
        """
        from app import security

        raw = self.client.get("/health").text
        self.assertNotIn(security.current_token(), raw)
        self.assertNotIn("token", raw.lower())

    def test_it_needs_no_bearer_token(self):
        from app import security

        self.assertFalse(security.requires_token("GET", "/health"))
        bare = support.api_client(app)
        bare.headers.pop("Authorization", None)
        self.assertEqual(bare.get("/health").status_code, 200)


class AnEngineThatIsNotReadySaysSoWithAStatusCode(unittest.TestCase):
    """503, so `curl -f` fails and a shell check cannot read it as success."""

    def setUp(self):
        support.sandbox(self)
        self.client = support.api_client(app)

    def test_a_database_from_the_future_is_not_ready(self):
        """The real incident: a build that knew schema 8 met a database at 9
        and answered every request with a 500. `/health` said `ok` throughout,
        because nothing it looked at had anything to do with the database.
        """
        with db.session() as connection:
            connection.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (identity.known_schema_version() + 40,),
            )
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body["status"], "not_ready")
        failing = {check["name"]: check for check in body["checks"] if not check["ok"]}
        self.assertIn("schema_agrees", failing)
        self.assertIn("ahead of", failing["schema_agrees"]["detail"])
        self.assertFalse(body["schema"]["agrees"])

    def test_a_database_it_cannot_read_is_not_ready_and_does_not_500(self):
        """A health route that crashes tells you less than one that reports.

        The engine still has to be able to say WHICH thing is broken while the
        broken thing is the database, so every check is guarded individually.
        """
        previous = db.DB_PATH
        db.DB_PATH = db.DB_PATH.parent / "no-such-directory" / "missing.db"
        try:
            response = self.client.get("/health")
        finally:
            db.DB_PATH = previous
        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body["status"], "not_ready")
        self.assertFalse(body["checks"][0]["ok"])
        # And it still knows what BUILD it is, which is the half that does not
        # depend on the database and is exactly what a launcher needs in order
        # to decide whether replacing this engine would even help.
        self.assertEqual(
            body["build"]["code_fingerprint"],
            identity.code_fingerprint()[0],
        )


class ACallerThatSaysWhatItMeantIsToldWhenItIsWrong(unittest.TestCase):
    """The half that catches a stale engine. 409, not 200, not 503.

    409 rather than 503 because the engine is FINE - it is simply not the one
    you meant, and a launcher acts differently on those two: it replaces a
    stale engine and it reports a broken one.
    """

    def setUp(self):
        support.sandbox(self)
        self.client = support.api_client(app)
        self.fingerprint = identity.code_fingerprint()[0]

    def _health(self, **params):
        return self.client.get("/health", params=params)

    def test_the_right_build_passes(self):
        self.assertEqual(self._health(expect_build=self.fingerprint).status_code, 200)

    def test_a_prefix_of_the_right_build_passes(self):
        """So a person can paste twelve characters into a curl by hand without
        it being a trap. A prefix of a sha256 is still enormous evidence, and
        "the full 64 characters or nothing" is the ergonomics that gets a check
        quietly dropped from a script.
        """
        self.assertEqual(
            self._health(expect_build=self.fingerprint[:12]).status_code, 200
        )

    def test_the_wrong_build_is_refused(self):
        """THE STALE ENGINE CASE. This is the assertion that would have caught
        the RTX 2060 SUPER reported as absent.
        """
        response = self._health(expect_build="0" * 64)
        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertEqual(body["status"], "not_the_engine_you_meant")
        self.assertEqual(
            body["mismatch"],
            [{"field": "build", "expected": "0" * 64, "actual": self.fingerprint}],
        )

    def test_the_wrong_launch_nonce_is_refused(self):
        """A launcher asks "are you the child I started". The nonce answers it;
        the pid cannot, because `Popen(...).pid` is not the pid that ends up
        running the code when an interpreter re-execs - measured on this
        machine as 12468 against a server logging `Started server process
        [25392]`.
        """
        response = self._health(expect_launch="a-nonce-this-engine-never-saw")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["mismatch"][0]["field"], "launch_nonce")

    def test_the_right_launch_nonce_passes(self):
        previous = identity.LAUNCH_NONCE
        identity.LAUNCH_NONCE = "the-value-the-launcher-chose"
        self.addCleanup(setattr, identity, "LAUNCH_NONCE", previous)
        self.assertEqual(
            self._health(expect_launch="the-value-the-launcher-chose").status_code, 200
        )

    def test_the_wrong_pid_is_refused_and_the_right_one_passes(self):
        import os

        self.assertEqual(self._health(expect_pid=1).status_code, 409)
        self.assertEqual(self._health(expect_pid=os.getpid()).status_code, 200)

    def test_the_wrong_engine_id_is_refused(self):
        self.assertEqual(self._health(expect_engine="f" * 32).status_code, 409)
        self.assertEqual(
            self._health(expect_engine=identity.ENGINE_ID).status_code, 200
        )

    def test_the_wrong_schema_is_refused(self):
        self.assertEqual(self._health(expect_schema=1).status_code, 409)
        self.assertEqual(
            self._health(expect_schema=identity.known_schema_version()).status_code,
            200,
        )

    def test_every_disagreement_is_reported_not_just_the_first(self):
        """A caller that asked four questions and got one answer has to ask
        again to learn whether the rest were fine.
        """
        response = self._health(
            expect_build="0" * 64,
            expect_schema=1,
            expect_pid=1,
            expect_engine="f" * 32,
            expect_launch="nope",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            {item["field"] for item in response.json()["mismatch"]},
            {"build", "schema", "pid", "engine_id", "launch_nonce"},
        )

    def test_no_stated_expectation_can_be_answered_with_success_when_wrong(self):
        """The property, asserted directly rather than case by case.

        Every field a caller can state, given a value this engine does not
        have, must produce a non-2xx. A new `expect_*` parameter added without
        wiring it into the mismatch list fails here.
        """
        wrong = {
            "expect_build": "0" * 64,
            "expect_schema": 999,
            "expect_pid": 1,
            "expect_engine": "f" * 32,
            "expect_launch": "not-this-one",
        }
        for name, value in wrong.items():
            with self.subTest(parameter=name):
                response = self._health(**{name: value})
                self.assertGreaterEqual(
                    response.status_code,
                    400,
                    f"{name}={value} was answered with success",
                )

    def test_the_documented_expect_parameters_are_all_checked(self):
        """Derived from the signature, so a parameter cannot be added to the
        route and left out of the comparison. That combination is the one that
        matters: a caller who states an expectation and is silently ignored is
        worse off than one who states nothing, because they believe they
        checked.
        """
        import inspect

        from app.main import health

        stated = {
            name: parameter
            for name, parameter in inspect.signature(health).parameters.items()
            if name.startswith("expect_")
        }
        self.assertTrue(stated, "the route states no expectations at all")
        for name, parameter in stated.items():
            with self.subTest(parameter=name):
                # A wrong value OF THE RIGHT TYPE. Handing an int parameter a
                # string would get a 422 from FastAPI's validation, which is a
                # refusal for the wrong reason and would let an unchecked
                # parameter pass this test.
                wrong = 987654321 if "int" in str(parameter.annotation) else "not-this"
                response = self._health(**{name: wrong})
                self.assertEqual(response.status_code, 409, f"{name} is not checked")
                self.assertIn(
                    name.removeprefix("expect_").replace("engine", "engine_id"),
                    json.dumps(response.json()["mismatch"]),
                )


class TheOldContractIsGoneAndThatIsThePoint(unittest.TestCase):
    """A body that could only say `ok` was the whole defect."""

    def setUp(self):
        support.sandbox(self)
        self.client = support.api_client(app)

    def test_ok_is_no_longer_the_entire_answer(self):
        body = self.client.get("/health").json()
        self.assertNotEqual(body, {"status": "ok"})
        for field in ("service", "engine", "build", "schema", "database", "checks"):
            self.assertIn(field, body)

    def test_status_ok_still_reads_the_same_for_anything_that_only_wanted_that(self):
        """`frontend/src/lib/engine/client.ts getHealth()` is typed
        `Promise<{status: string}>`. Additive, so it keeps working.
        """
        body = self.client.get("/health").json()
        self.assertEqual(body["status"], "ok")
        self.assertIsInstance(json.dumps(body), str)


if __name__ == "__main__":
    unittest.main()
