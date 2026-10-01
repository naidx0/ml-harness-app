"""A measuring tool refreshes the ambient walk before the reply is checked.

## The defect, measured on the owner's own transcript (2026-09-14)

`measure_baseline` returned ok and stamped `baseline_measured`. The model then
said the baseline was measured. The sentry still held the turn-start walk with
`G1_BASELINE_MEASURED` at `NOT_REACHED`, because `_Standing.note` only listened
for `decided_by: app/diagnosis.py`, and withheld the truthful sentence.

The fix is mechanical: any tool that declares `measures=` re-walks the thread
ledger into `_Standing`, so the reply is checked against facts that just landed.
"""

from __future__ import annotations

import unittest
from unittest import mock

from app import conductor


class AMeasuringToolRefreshesStandingTest(unittest.TestCase):
    def test_a_diagnosis_stamp_still_replaces_the_payload(self):
        standing = conductor._Standing({"verdict": "old", "gate_ledger": {}})
        standing.note(
            {
                "ok": True,
                "decided_by": "app/diagnosis.py",
                "verdict": "NO_TRAIN",
                "gate_ledger": {"G1_BASELINE_MEASURED": {"status": "PASSED"}},
            }
        )
        self.assertEqual(standing.verdict, "NO_TRAIN")
        self.assertEqual(
            standing.payload["gate_ledger"]["G1_BASELINE_MEASURED"]["status"],
            "PASSED",
        )

    def test_a_measuring_tool_re_walks_the_thread(self):
        standing = conductor._Standing(
            {
                "verdict": "BLOCKED",
                "gate_ledger": {
                    "G1_BASELINE_MEASURED": {"status": "NOT_REACHED"},
                },
                "fact_origins": {"baseline_measured": "DEFAULTED"},
            },
            thread_id=70,
        )
        fresh = {
            "ok": True,
            "decided_by": "app/diagnosis.py",
            "verdict": "BLOCKED",
            "gate_ledger": {
                "G1_BASELINE_MEASURED": {"status": "NOT_REACHED"},
            },
            "fact_origins": {
                "baseline_measured": "MEASURED",
                "baseline_score": "MEASURED",
                "trivial_baseline_score": "MEASURED",
            },
        }
        with mock.patch.object(
            conductor, "_standing_diagnosis", return_value=fresh
        ) as walk:
            with mock.patch.object(
                conductor.REGISTRY,
                "get",
                return_value=mock.Mock(measures=("baseline_measured",)),
            ):
                standing.note({"ok": True, "baseline_score": 0.4}, tool_name="measure_baseline")
        walk.assert_called_once_with(70)
        self.assertEqual(
            standing.payload["fact_origins"]["baseline_measured"], "MEASURED"
        )

    def test_a_lookup_tool_does_not_re_walk(self):
        original = {"verdict": "BLOCKED", "gate_ledger": {}}
        standing = conductor._Standing(original, thread_id=70)
        with mock.patch.object(conductor, "_standing_diagnosis") as walk:
            with mock.patch.object(
                conductor.REGISTRY,
                "get",
                return_value=mock.Mock(measures=()),
            ):
                standing.note({"ok": True, "rows": []}, tool_name="list_runs")
        walk.assert_not_called()
        self.assertIs(standing.payload, original)

    def test_sentry_allows_soft_narration_once_facts_are_earned(self):
        standing = conductor._Standing(
            {
                "verdict": "BLOCKED",
                "gate_ledger": {
                    "G0_EVAL_SET": {"status": "NOT_REACHED"},
                    "G1_BASELINE_MEASURED": {"status": "NOT_REACHED"},
                },
                "fact_origins": {
                    "baseline_measured": "MEASURED",
                    "baseline_score": "MEASURED",
                    "trivial_baseline_score": "MEASURED",
                },
            }
        )
        sentry = conductor._Sentry(standing, None, planning=False)
        sentry.feed("A baseline score was measured on your eval set.")
        self.assertIsNone(sentry.conflict)

    def test_sentry_still_stops_an_unearned_gate_name(self):
        standing = conductor._Standing(
            {
                "verdict": "BLOCKED",
                "gate_ledger": {
                    "G1_BASELINE_MEASURED": {"status": "NOT_REACHED"},
                },
                "fact_origins": {
                    "baseline_measured": "MEASURED",
                    "baseline_score": "MEASURED",
                    "trivial_baseline_score": "MEASURED",
                },
            }
        )
        sentry = conductor._Sentry(standing, None, planning=False)
        sentry.feed("G1_BASELINE_MEASURED is satisfied.")
        sentry.close()
        self.assertIsNotNone(sentry.conflict)
        self.assertEqual(sentry.conflict["kind"], conductor.INVENTED_GATE)


if __name__ == "__main__":
    unittest.main()
