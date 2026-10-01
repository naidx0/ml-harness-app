"""`thread_id` stays optional on the control route, and the route says what that means.

Two of the three bad rows in the owner's real database came through
`POST /api/tools/{name}`, written by a reviewer verifying a different fix. That
is the shape of the defect: the argument was optional, nothing said what omitting
it did, and omitting it filed a measurement of one project's file where every
conversation on the machine could read it.

The field stays optional, because optional is RIGHT for one tool: `inspect_hardware`
declares four facts and all four are the machine's own, a person reading their own
hardware page has no conversation open, and demanding one would be ceremony. What
changed is that the ROUTE decides which case a call is, per tool, off the tool's
own `measures=` and the scope declared on each fact - so the answer is derived
rather than listed, and a tool added next year is covered on the day it registers.

TWO REFUSALS, TWO STATUS CODES, AND THE DIFFERENCE IS DELIBERATE:

  400  the pre-check here. The request is incomplete. It runs before the tool
       does, so it can promise nothing ran and say what to send instead.
  400  `evidence.ScopeError` escaping the tool, mapped ahead of the
       `MeasurementError` clause it is a subclass of. Same event, later.
  500  a `MeasurementError` proper, which is a tool trying to launder something
       and is a defect in the harness rather than in the request.

EVERY REFUSAL HERE HAS A CONTROL. A route that answered 400 to everything would
pass every negative test in this file, so each one is paired with the same call
that must still work: with a thread, or against the tool that genuinely needs
none.
"""

from __future__ import annotations

import json
import unittest
from unittest import mock

from app import db
from app.tools import evidence

import support


THREAD = 11
ROWS = 120


def eval_file(root):
    path = root / "eval.jsonl"
    path.write_text(
        "".join(
            json.dumps({"input": f"q{i}", "output": f"a{i}"}) + "\n"
            for i in range(ROWS)
        ),
        encoding="utf-8",
    )
    return path


def ledger_rows() -> list[dict]:
    with db.session() as connection:
        return [dict(r) for r in connection.execute("SELECT * FROM fact_evidence")]


class TheDoorAsksWhichConversationTest(unittest.TestCase):
    def setUp(self):
        from app.main import app

        self.root = support.sandbox(self)

        support.a_conversation(THREAD)
        evidence.ensure_table()
        self.client = support.api_client(app)
        self.path = eval_file(self.root)

    # -- the refusal ------------------------------------------------------

    def test_counting_an_eval_set_with_no_thread_is_a_400(self):
        response = self.client.post(
            "/api/tools/measure_eval_set",
            json={"arguments": {"path": str(self.path)}},
        )
        self.assertEqual(response.status_code, 400, response.text)

    def test_the_refusal_names_the_argument_and_where_it_goes(self):
        response = self.client.post(
            "/api/tools/measure_eval_set",
            json={"arguments": {"path": str(self.path)}},
        )
        detail = response.json()["detail"]
        self.assertEqual(detail["error"], "missing_thread_id")
        self.assertEqual(detail["missing"], "thread_id")
        self.assertIn("thread_id", detail["send"])
        self.assertIn("beside `arguments`", detail["send"]["note"])
        self.assertIn("measure_eval_set", detail["detail"])

    def test_the_refusal_says_what_may_be_recorded_with_no_conversation(self):
        """THE DOOR IN THE WALL. A caller who genuinely has no thread has to be
        able to see the shape of the exception rather than guess at it."""
        response = self.client.post(
            "/api/tools/measure_eval_set",
            json={"arguments": {"path": str(self.path)}},
        )
        detail = response.json()["detail"]
        self.assertEqual(
            detail["the_ledger"]["machine_scoped_facts"],
            list(evidence.facts_at_scope(evidence.MACHINE)),
        )
        self.assertIn("POST /api/threads", detail["if_you_have_no_thread"])

    def test_nothing_ran_and_nothing_was_recorded(self):
        self.client.post(
            "/api/tools/measure_eval_set",
            json={"arguments": {"path": str(self.path)}},
        )
        self.assertEqual(ledger_rows(), [])

    def test_saying_facts_yourself_with_no_thread_is_refused_too(self):
        """`state_facts` declares `writes: facts` and no `measures=`, so it can
        reach `Instrument.supplied` with ANY name in the ledger. `measures=`
        bounds what a tool may STAMP and bounds nothing about what it may say."""
        response = self.client.post(
            "/api/tools/state_facts",
            json={"arguments": {"facts": {"goal_text": "route tickets"}}},
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(ledger_rows(), [])

    def test_profiling_a_dataset_with_no_thread_is_refused(self):
        """The tool that actually wrote two of the three rows in the real file."""
        response = self.client.post(
            "/api/tools/profile_dataset",
            json={"arguments": {"path": str(self.path), "split": "eval"}},
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(ledger_rows(), [])

    # -- the controls -----------------------------------------------------

    def test_the_same_call_with_a_thread_still_counts_the_file(self):
        """POSITIVE CONTROL. A door that refuses everything is not a door."""
        response = self.client.post(
            "/api/tools/measure_eval_set",
            json={"arguments": {"path": str(self.path)}, "thread_id": THREAD},
        )
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()["result"]
        self.assertEqual(result["rows"], ROWS)
        self.assertEqual([row["thread_id"] for row in ledger_rows()], [THREAD])

    def test_reading_the_machine_needs_no_conversation_at_all(self):
        """POSITIVE CONTROL, and the reason `thread_id` is still optional."""
        response = self.client.post("/api/tools/inspect_hardware")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["result"].get("measured_facts"))

    def test_a_tool_that_writes_no_facts_needs_no_conversation(self):
        """`run_diagnosis` and `list_runs` measure nothing and record nothing."""
        for name, arguments in (
            ("run_diagnosis", {"facts": {}}),
            ("list_runs", {}),
        ):
            with self.subTest(tool=name):
                response = self.client.post(
                    f"/api/tools/{name}", json={"arguments": arguments}
                )
                self.assertEqual(response.status_code, 200, response.text)

    def test_an_unknown_tool_is_still_a_404_and_not_a_400(self):
        """The pre-check must not answer for a tool that does not exist - "you
        forgot thread_id" about a tool nobody has is a worse answer than "there
        is no such tool", which names the whole list."""
        response = self.client.post(
            "/api/tools/count_the_eval_set", json={"arguments": {}}
        )
        self.assertEqual(response.status_code, 404, response.text)


class TheLedgersOwnRefusalIsAlsoTheCallersTest(unittest.TestCase):
    """`ScopeError` is caught ahead of `MeasurementError`, which it subclasses.

    The pre-check reads DECLARATIONS. A tool whose declarations say it only
    touches the machine and whose handler writes a thread-scoped fact anyway gets
    past it and is stopped by `record`. That is the wall doing its job, and it
    must not surface as a 500: the request was incomplete, not the harness
    broken. Ordering `except` clauses is exactly the kind of thing that is right
    when written and wrong after the next edit, so it is pinned.
    """

    def setUp(self):
        from app.main import app

        self.root = support.sandbox(self)

        support.a_conversation(THREAD)
        self.client = support.api_client(app)

    def test_a_scope_error_out_of_a_tool_is_a_400_with_its_own_sentence(self):
        message = evidence._scope_refusal(
            "eval_size_n", tool="a_tool_whose_declarations_lie", origin="MEASURED"
        )
        with mock.patch(
            "app.tools.REGISTRY.call", side_effect=evidence.ScopeError(message)
        ):
            response = self.client.post(
                "/api/tools/inspect_hardware", json={"arguments": {}}
            )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("thread_id", response.json()["detail"])

    def test_a_plain_measurement_error_is_still_a_500(self):
        """POSITIVE CONTROL for the ordering above. If `ScopeError` had been
        caught by widening the existing clause, this would have moved too - and
        a tool laundering a number is a defect in the harness, which is what a
        500 says."""
        with mock.patch(
            "app.tools.REGISTRY.call",
            side_effect=evidence.MeasurementError("stamped what it was handed"),
        ):
            response = self.client.post(
                "/api/tools/inspect_hardware", json={"arguments": {}}
            )
        self.assertEqual(response.status_code, 500, response.text)


class WhichToolsNeedAConversationTest(unittest.TestCase):
    """The rule, asserted over the whole registry rather than tool by tool.

    Derived, so a tool added next year is covered by existing. The one tool that
    may run without a conversation is named, because "exactly one" is a much
    stronger statement than "these ones do".
    """

    def test_exactly_the_fact_writers_need_a_thread(self):
        from app.tools.registry import REGISTRY

        needs = {
            candidate.name
            for candidate in REGISTRY
            if evidence.thread_is_required_by(candidate.name)
        }
        writers = {
            candidate.name
            for candidate in REGISTRY
            if candidate.wants_instrument
            and (candidate.measures or "facts" in candidate.writes)
        }
        self.assertEqual(needs, writers - {"inspect_hardware"})
        self.assertIn("measure_eval_set", needs)
        self.assertIn("state_facts", needs)
        self.assertNotIn("inspect_hardware", needs)

    def test_the_answer_comes_off_the_ledger_and_not_off_a_list(self):
        """POSITIVE CONTROL for the derivation, run on the one tool that is
        exempt today. Declare the hardware facts thread scope for a moment and
        `inspect_hardware` starts needing a conversation - which is what "read
        off the ledger" has to mean if it means anything. Without this, a
        `thread_is_required_by` that had `inspect_hardware` written into it by
        name would pass every other test in this class.
        """
        self.assertEqual(evidence.thread_is_required_by("inspect_hardware"), "")
        saved = evidence.scope_of
        evidence.scope_of = lambda fact: evidence.THREAD
        try:
            why = evidence.thread_is_required_by("inspect_hardware")
        finally:
            evidence.scope_of = saved
        self.assertIn("vram_gb", why)
        self.assertEqual(evidence.thread_is_required_by("inspect_hardware"), "")

    def test_the_refusal_names_the_fact_when_the_tool_declared_one(self):
        """The specific answer beats the general one: `measure_eval_set` is told
        which fact, not that tools which write facts need threads."""
        self.assertIn(
            "eval_size_n", evidence.thread_is_required_by("measure_eval_set")
        )
        self.assertIn(
            "writes facts", evidence.thread_is_required_by("state_facts")
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
