"""Counting a 120-row eval file with `max_rows=120` is a measurement, not a fraud.

WHAT WAS BROKEN, AND WHY IT IS THE WORST KIND OF BROKEN.

`evidence.Instrument.measured` refuses a value the caller handed the tool. That
is wall 2, it is right to exist, and its test was wrong: it compared the stamped
value against every scalar in the arguments, so `profile_dataset` reading 120
rows off a 120-row file was refused as laundering the moment the caller had
written `max_rows=120`.

    POST /api/tools/profile_dataset {"path": eval.jsonl, "split": "eval",
                                     "max_rows": 120}            -> HTTP 500

    'profile_dataset' tried to stamp 'eval_size_n' MEASURED with 120, which is
    a value it was handed in this call's arguments.

`max_rows=121` on the same file returned 200. Reproduced at rows=50/cap=50 and
rows=120/cap=120. Capping a scan at the size of the file is the most ordinary
thing anybody does with this tool, it is the first of the five gates, and it
could never open that way.

WHAT DISTINGUISHES THE TWO, WHICH IS THE WHOLE SUBJECT OF THIS FILE.

Not the value, and no comparison of the value can ever answer it. "I counted and
got 120" and "you handed me 120 and I handed it back" produce the same integer;
with a cap of 120 on a 120-row file, equality is what a CORRECT reading looks
like. What differs is where the number came from, and that is a question about
the value's history rather than about its size.

`app/tools/evidence.py` answers it by history now: a value that arrives in a
tool call's arguments is marked, the mark survives being added to, parsed and
reformatted, and `measured()` refuses a marked value rather than an equal one. A
number read off a disk carries no mark and is stamped whatever it happens to
equal. That module is where the fix lives; THIS FILE IS THE PRODUCT-LEVEL
ACCEPTANCE TEST FOR IT - the reproduction the user reported, at both row counts,
through the registry and through the door they were actually clicking, plus the
gate it was blocking.

WHY THE CAP CANNOT CARRY AN ANSWER EITHER WAY, which is the property that makes
the honest reading honest and is asserted twice at the bottom of this file:

  * when the cap BITES, the scan did not reach the end of the file, `rows` comes
    back `inferred` rather than `measured`, and nothing is stamped at all;
  * when it does not bite, the number stamped is the number of rows in the file.
    A 50-row file counted with `max_rows=120` records 50.

So there is no cap a caller can choose that makes the harness agree to a number
the file does not contain, which is the reason equality at the boundary was
never evidence of anything.
"""

from __future__ import annotations

import json
import unittest

from app import build
from pathlib import Path

from app.tools import REGISTRY, evidence
from app.tools.evidence import MEASURED, MODEL, USER

import support


THREAD = 1


def eval_file(root: Path, rows: int) -> Path:
    """An eval set with a known row count. The count is the whole subject."""
    path = root / f"eval_{rows}.jsonl"
    path.write_text(
        "\n".join(json.dumps({"q": f"q{i}", "a": f"label{i % 5}"}) for i in range(rows)),
        encoding="utf-8",
    )
    return path


class CappingTheScanAtTheSizeOfTheFileStillCountsItTest(unittest.TestCase):
    """The reproduction, at both row counts it was reported at, then the fix."""

    def setUp(self):
        self.root = support.sandbox(self)
        support.a_conversation(THREAD)
        evidence.ensure_table()

    def recorded(self):
        return [
            (row["fact"], row["value"], row["origin"])
            for row in evidence.rows_for(THREAD)
        ]

    def test_a_cap_equal_to_the_row_count_records_the_count_as_measured(self):
        """rows=120, cap=120. This was HTTP 500 and a laundering accusation."""
        path = eval_file(self.root, 120)
        result = REGISTRY.call(
            "profile_dataset",
            {"path": str(path), "split": "eval", "max_rows": 120},
            actor=USER,
            thread_id=THREAD,
        )
        self.assertEqual(result["rows"], 120)
        self.assertFalse(result["rows_are_truncated"])
        self.assertEqual(
            result["measured_facts"],
            [
                {
                    "fact": "eval_size_n",
                    "value": 120,
                    "origin": MEASURED,
                    # The derivation now carries what the file looked like
                    # when it was counted, so a reader of an export can
                    # tell whether the file in front of them is the file
                    # the number came from. `build.counted_rows_how`.
                    "how": build.counted_rows_how(120, path),
                }
            ],
        )
        self.assertEqual(self.recorded(), [("eval_size_n", 120, MEASURED)])

    def test_the_other_row_count_the_defect_was_reported_at(self):
        """rows=50, cap=50. Two sizes, because one of them could be a fluke."""
        path = eval_file(self.root, 50)
        result = REGISTRY.call(
            "profile_dataset",
            {"path": str(path), "split": "eval", "max_rows": 50},
            actor=MODEL,
            thread_id=THREAD,
        )
        self.assertEqual(result["measured_facts"][0]["value"], 50)
        self.assertEqual(self.recorded(), [("eval_size_n", 50, MEASURED)])

    def test_the_cap_one_higher_still_works_and_records_the_same_number(self):
        """The workaround the adversary found. It must not be the only way."""
        path = eval_file(self.root, 120)
        result = REGISTRY.call(
            "profile_dataset",
            {"path": str(path), "split": "eval", "max_rows": 121},
            actor=USER,
            thread_id=THREAD,
        )
        self.assertEqual(result["measured_facts"][0]["value"], 120)

    def test_the_users_own_door_returns_the_count_rather_than_a_500(self):
        """Through `POST /api/tools/profile_dataset`, which is where it was found.

        The registry test above proves the mechanism. This one proves the
        product, because the defect was reported as an HTTP status code and the
        person who hit it was clicking a control.
        """
        from app.main import app

        path = eval_file(self.root, 120)
        client = support.api_client(app)
        response = client.post(
            "/api/tools/profile_dataset",
            json={
                "arguments": {"path": str(path), "split": "eval", "max_rows": 120},
                "thread_id": THREAD,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()["result"]
        self.assertEqual(result["rows"], 120)
        self.assertEqual(result["measured_facts"][0]["value"], 120)

    def test_the_first_gate_opens_on_a_count_taken_this_way(self):
        """The point of the whole thing: G0 asks, and the count answers it.

        `profile_dataset` does not decide the gate and cannot. This asserts the
        consequence one layer up - that a count taken with the cap set to the
        size of the file is admissible evidence for `G0_EVAL_SET` - which is
        what "the product's own first gate can never open that way" meant.

        The other facts are the person's own, supplied as themselves, and they
        are here only to get the walk as far as stage 0's exit. The gate under
        test reads one fact and it is the counted one.
        """
        path = eval_file(self.root, 120)
        REGISTRY.call(
            "profile_dataset",
            {"path": str(path), "split": "eval", "max_rows": 120},
            actor=USER,
            thread_id=THREAD,
        )
        after = REGISTRY.call(
            "run_diagnosis",
            {
                "facts": {
                    "modality": "text",
                    "task_family": "generation",
                    "target_score": 0.85,
                    "privacy": "public_ok",
                    "needs_citations": False,
                }
            },
            actor=USER,
            thread_id=THREAD,
        )
        self.assertEqual(after["fact_origins"]["eval_size_n"], MEASURED)
        self.assertEqual(after["facts_used"]["eval_size_n"]["value"], 120)
        gate = after["gate_ledger"]["G0_EVAL_SET"]
        self.assertEqual(gate["status"], "PASSED", after["gate_ledger"])
        self.assertEqual(gate["clause"], "eval_size_n >= 30")
        # And the run carries on to the next honest step rather than stopping to
        # ask for the thing that was just measured.
        self.assertEqual(after["outcome"], "ACTION__MEASURE_BASELINE")


class TheCapNeverChoosesTheNumberTest(unittest.TestCase):
    """Why equality at the boundary was never evidence of laundering.

    Both halves of it, because either one alone would leave the argument open. A
    cap that bites records nothing; a cap that does not bite records what is in
    the file. There is no value of `max_rows` that makes the harness agree to a
    row count the file does not have, which is what makes the coincidence at
    `cap == rows` a coincidence rather than a signal.
    """

    def setUp(self):
        self.root = support.sandbox(self)
        support.a_conversation(THREAD)
        evidence.ensure_table()

    def test_a_cap_that_bites_is_a_lower_bound_and_stamps_nothing(self):
        path = eval_file(self.root, 120)
        result = REGISTRY.call(
            "profile_dataset",
            {"path": str(path), "split": "eval", "max_rows": 10},
            actor=MODEL,
            thread_id=THREAD,
        )
        self.assertTrue(result["rows_are_truncated"])
        self.assertNotIn("measured_facts", result)
        self.assertEqual(evidence.rows_for(THREAD), [])

    def test_a_cap_above_the_row_count_records_the_row_count(self):
        """A 50-row file with a cap of 120 records 50, never 120."""
        path = eval_file(self.root, 50)
        result = REGISTRY.call(
            "profile_dataset",
            {"path": str(path), "split": "eval", "max_rows": 120},
            actor=MODEL,
            thread_id=THREAD,
        )
        self.assertEqual(result["measured_facts"][0]["value"], 50)


if __name__ == "__main__":
    unittest.main()
