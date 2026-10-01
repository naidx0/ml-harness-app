"""Autonomous mode covers what somebody named, and nothing else.

Max asked for the switch and set its limits in the same sentence: *"it is
opt-in per thread and never the default; every auto-approved call is still
recorded and visible in the transcript exactly as a manual one would be; and
it never covers a tool that spends money or writes outside the sandbox."*

Each of those is a test here. The load-bearing one is the first:

**A gated tool nobody has classified is not covered.** `app/autonomy.py` is a
whitelist, so the dangerous default - a tool shipping tomorrow with
`approval="always"` and being silently pre-approved - is unreachable by
construction. `test_every_gated_tool_is_classified_with_a_reason` then makes
the *safe* default loud too: a new gated tool fails this suite until somebody
says which side of the line it is on and why, so nobody has to remember.

Why a list at all, rather than a derivation off the specs: `carve_rows` and
`delete_sandbox` both declare `writes=("filesystem",)`. One writes a new file
beside your data and the other removes a sandbox that took an hour to build.
Nothing on the spec separates making from destroying, so a derivation would
be a guess wearing an algorithm's clothes. Measured, not assumed - the test
below prints both declarations if that ever stops being true.
"""

from __future__ import annotations

import unittest

from app import autonomy, conductor, events, main
from app.tools import REGISTRY
import support


def _gated() -> set[str]:
    """Every tool the registry says needs an approval, read from the specs."""
    return {
        name for name in REGISTRY.names() if REGISTRY._tools[name].approval == "always"
    }


class TheClassificationIsExhaustiveTest(unittest.TestCase):
    def test_every_gated_tool_is_classified_with_a_reason(self):
        named = set(autonomy.UNATTENDED) | set(autonomy.NEVER_UNATTENDED)
        missing = sorted(_gated() - named)
        self.assertEqual(
            missing, [],
            "These tools need an approval and nobody has said whether "
            "autonomous mode may run them: "
            f"{missing}. Add each to UNATTENDED or NEVER_UNATTENDED in "
            "app/autonomy.py with the reason. Until then they are NOT "
            "auto-approved - this test is the reminder, not the wall.",
        )

    def test_nothing_is_classified_that_is_not_gated(self):
        """A name in either list that no longer needs an approval is a stale
        entry, and a stale entry is how a list stops describing the product."""
        named = set(autonomy.UNATTENDED) | set(autonomy.NEVER_UNATTENDED)
        self.assertEqual(sorted(named - _gated()), [])

    def test_no_tool_is_on_both_sides(self):
        self.assertEqual(
            sorted(set(autonomy.UNATTENDED) & set(autonomy.NEVER_UNATTENDED)), []
        )

    def test_every_reason_is_a_sentence_somebody_wrote(self):
        for name, reason in {**autonomy.UNATTENDED, **autonomy.NEVER_UNATTENDED}.items():
            with self.subTest(tool=name):
                self.assertGreater(
                    len(reason.split()), 6,
                    f"{name}'s reason is too short to be a reason: {reason!r}",
                )

    def test_the_destructive_and_the_expensive_are_never_covered(self):
        """delete_sandbox never auto; training may under full (AU1 bypass).

        LAW SUBSTITUTED 2026-09-18. "delete_sandbox never auto" is now "never
        auto EXCEPT a box this thread made with nothing measured or trained in
        it, under full" - Max's rule, and it is narrow enough that every
        assertion below is unchanged: they ask without `own_sandbox`, which is
        the default and the old answer. The exception has its own file,
        `tests/test_full_may_throw_away_its_own_sandbox.py`, because a law with
        two halves read off disk is not a line in a table test.
        """
        self.assertIn("delete_sandbox", autonomy.NEVER_UNATTENDED)
        self.assertFalse(autonomy.may_run_unattended("delete_sandbox"))
        self.assertFalse(autonomy.may_run("full", "delete_sandbox"))
        self.assertFalse(autonomy.may_run("write", "delete_sandbox"))
        self.assertFalse(autonomy.may_run("write", "start_training"))
        self.assertFalse(autonomy.may_run("write", "set_the_project_root"))

    def test_measure_mode_only_covers_scoring_tools(self):
        self.assertTrue(autonomy.may_run("measure", "score_the_adapter"))
        self.assertFalse(autonomy.may_run("measure", "carve_rows"))
        self.assertFalse(autonomy.may_run("ask", "score_the_adapter"))

    def test_full_covers_generate_rows_and_training(self):
        """AU1: full is zero-ask — training and project root auto; wipe does not.

        LAW SUBSTITUTED 2026-09-18: a wipe of a box this thread made, holding
        nothing measured, does. The last line still reads as it did because the
        question here is asked WITHOUT that fact, and without it the answer has
        not changed - which is the whole design of the parameter.
        """
        self.assertTrue(autonomy.may_run("full", "generate_rows"))
        self.assertTrue(autonomy.may_run("full", "start_training"))
        self.assertTrue(autonomy.may_run("full", "set_the_project_root"))
        self.assertFalse(autonomy.may_run("full", "delete_sandbox"))
        self.assertTrue(
            autonomy.may_run("full", "delete_sandbox", own_sandbox=True)
        )

    def test_an_unknown_name_is_not_covered(self):
        self.assertFalse(autonomy.may_run_unattended("a_tool_that_ships_tomorrow"))
        self.assertIsNone(autonomy.why("a_tool_that_ships_tomorrow"))


class TheSwitchIsOptInPerThreadTest(unittest.TestCase):
    def setUp(self):
        support.sandbox(self)
        self.client = support.api_client(main.app)
        self.thread = events.create_thread("autonomy")

    def test_a_new_thread_is_not_autonomous(self):
        self.assertEqual(
            events.get_thread(self.thread["id"])["autonomous"], 0,
            "autonomous mode must never be the default",
        )

    def test_the_person_turns_it_on_and_off_through_their_own_door(self):
        on = self.client.post(
            f"/api/threads/{self.thread['id']}/autonomous", json={"on": True}
        ).json()
        self.assertEqual(on["autonomous"], 1)
        # The reply hands back what was just pre-approved, with the reasons.
        self.assertEqual(set(on["covers"]), set(autonomy.UNATTENDED))
        self.assertIn("delete_sandbox", on["never_covers"])

        off = self.client.post(
            f"/api/threads/{self.thread['id']}/autonomous", json={"on": False}
        ).json()
        self.assertEqual(off["autonomous"], 0)

    def test_switching_it_is_an_event_on_the_thread(self):
        self.client.post(
            f"/api/threads/{self.thread['id']}/autonomous", json={"on": True}
        )
        kinds = [
            row["kind"]
            for row in events.since(f"thread:{self.thread['id']}", 0)
        ]
        self.assertIn("thread.autonomous", kinds)

    def test_it_is_not_a_tool_the_model_can_reach(self):
        """A model that could switch this on could approve its own next call."""
        self.assertNotIn("set_autonomous", REGISTRY.names())
        for name in REGISTRY.names():
            with self.subTest(tool=name):
                self.assertNotIn("autonom", name.lower())


class WhatTheConductorDoesWithItTest(unittest.TestCase):
    """The seam itself: `_run_tool`'s `unattended`, and the record it writes."""

    def setUp(self):
        support.sandbox(self)
        self.thread = events.create_thread("autonomy-seam")

    def _call(self, name, arguments=None):
        class Call:
            id = "call-1"

        call = Call()
        call.name = name
        call.arguments = arguments or {}
        return call

    def _run(self, name, *, unattended):
        rows = list(
            conductor._run_tool(
                int(self.thread["id"]),
                [],
                self._call(name),
                unattended=unattended,
            )
        )
        return rows

    def test_off_by_default_a_gated_tool_still_asks(self):
        rows = self._run("carve_rows", unattended=False)
        results = [r for r in rows if r["kind"] == "tool.result"]
        self.assertEqual(
            results[-1]["payload"]["result"]["error"], "approval_required"
        )
        calls = [r for r in rows if r["kind"] == "tool.call"]
        self.assertNotIn("auto_approved", calls[-1]["payload"])

    def test_on_a_covered_tool_is_not_refused_for_approval(self):
        rows = self._run("carve_rows", unattended=True)
        results = [r for r in rows if r["kind"] == "tool.result"]
        # It may well fail for a missing argument - that is the tool's own
        # business. What it must NOT do is stop for an approval.
        self.assertNotEqual(
            results[-1]["payload"]["result"].get("error"), "approval_required"
        )

    def test_on_an_uncovered_tool_still_asks(self):
        rows = self._run("delete_sandbox", unattended=True)
        results = [r for r in rows if r["kind"] == "tool.result"]
        self.assertEqual(
            results[-1]["payload"]["result"]["error"], "approval_required",
            "autonomy must never cover a tool NEVER_UNATTENDED names",
        )

    def test_an_auto_approved_call_says_so_on_the_record(self):
        """Visible exactly as a manual one would be, plus the one fact that
        distinguishes them: nobody was asked."""
        rows = self._run("carve_rows", unattended=True)
        calls = [r for r in rows if r["kind"] == "tool.call"]
        self.assertTrue(calls[-1]["payload"]["auto_approved"])
        # and the ordinary fields are all still there
        self.assertEqual(calls[-1]["payload"]["name"], "carve_rows")
        self.assertIn("arguments", calls[-1]["payload"])


if __name__ == "__main__":
    unittest.main()
