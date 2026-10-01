"""World knowledge is served with its age, or refused with a sentence.

The gap this layer closed: the ledgers know the USER'S situation, but nothing
in the product could answer "which model today" or "what does a rented GPU
cost" except from somebody's memory - and memory is the one source this
product refuses everywhere else. The rule under test: every answer carries
`fetched_at`, `age_days` and a staleness sentence; a snapshot past its budget
is still served but SAYS SO; a missing or garbled file is a refusal that names
the refresh command, never an invented table.
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from app.tools import REGISTRY, blocks, knowledge


def stamped(days_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(
        timespec="seconds"
    )


class TheSnapshotsShipAndAnswerTest(unittest.TestCase):
    def test_both_snapshots_exist_and_carry_provenance(self):
        for name in ("model_shortlist.json", "gpu_prices.json"):
            path = knowledge.KNOWLEDGE_ROOT / name
            self.assertTrue(path.is_file(), f"{name} is not committed")
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("fetched_at", data)
            self.assertIn("source", data, f"{name} does not say where it came from")

    def test_the_shortlist_facts_are_fetched_not_typed(self):
        # Every model row must carry the API's fields; a row with a role but
        # no parameters would be the editorial half posing as the fetched half.
        answer = knowledge.read_model_shortlist()
        self.assertTrue(answer["ok"], answer)
        for row in answer["models"]:
            for field in ("parameters_total", "license", "last_modified", "url"):
                self.assertIn(field, row, f"{row.get('repo_id')} lacks {field}")

    def test_every_answer_says_how_old_it_is(self):
        for call in (knowledge.read_model_shortlist, knowledge.read_gpu_prices):
            answer = call()
            self.assertTrue(answer["ok"], answer)
            self.assertIn("age_days", answer)
            self.assertIn("staleness", answer)
            self.assertIn("fetched", answer["summary"])


class StalenessIsSaidNotGuessedAroundTest(unittest.TestCase):
    def test_a_stale_snapshot_is_served_and_says_so(self):
        with mock.patch.object(
            knowledge, "age_days", return_value=999.0
        ):
            answer = knowledge.read_gpu_prices()
        self.assertTrue(answer["ok"])
        self.assertTrue(answer["stale"])
        self.assertIn("STALE", answer["staleness"])
        self.assertIn(knowledge.REFRESH_COMMAND, answer["staleness"])

    def test_an_undated_snapshot_is_stale_by_definition(self):
        self.assertIsNone(knowledge.age_days("not a timestamp"))
        with mock.patch.object(knowledge, "age_days", return_value=None):
            answer = knowledge.read_model_shortlist()
        self.assertTrue(answer["stale"])
        self.assertIn("UNDATED", answer["staleness"])

    def test_a_missing_file_is_a_refusal_that_names_the_fix(self):
        with mock.patch.object(
            knowledge, "KNOWLEDGE_ROOT", Path("Z:/nowhere-at-all")
        ):
            answer = knowledge.read_gpu_prices()
        self.assertFalse(answer.get("ok"))
        self.assertEqual(answer["error"], "missing_knowledge")
        self.assertIn(knowledge.REFRESH_COMMAND, answer["detail"])

    def test_prices_go_stale_faster_than_models(self):
        # The budgets encode a fact about the world: marketplace asks drift
        # daily, the model ladder moves monthly. Flattening them to one number
        # would make one of the two files lie about its reliability.
        self.assertLess(
            knowledge.STALE_AFTER_DAYS["gpu_prices.json"],
            knowledge.STALE_AFTER_DAYS["model_shortlist.json"],
        )


class TheDoctorRowHasThreeStatesTest(unittest.TestCase):
    def test_fresh_is_fine(self):
        row = knowledge.doctor_row()
        self.assertEqual(row["check"], "knowledge")
        # On this checkout the snapshots were just fetched; if this fails
        # because time passed, that is the row doing its job - refresh them.
        self.assertTrue(row["ok"], row)

    def test_stale_is_open_not_broken(self):
        with mock.patch.object(knowledge, "age_days", return_value=999.0):
            row = knowledge.doctor_row()
        self.assertFalse(row["ok"])
        self.assertTrue(row.get("open"), "stale knowledge must be a known-open "
                        "question, not a broken install")
        self.assertIn(knowledge.REFRESH_COMMAND, row["why"])

    def test_missing_is_broken(self):
        with mock.patch.object(
            knowledge, "KNOWLEDGE_ROOT", Path("Z:/nowhere-at-all")
        ):
            row = knowledge.doctor_row()
        self.assertFalse(row["ok"])
        self.assertFalse(row.get("open", False))


class TheToolsAreRealToolsTest(unittest.TestCase):
    def test_registered_with_declared_capabilities(self):
        names = set(REGISTRY.names())
        self.assertIn("read_model_shortlist", names)
        self.assertIn("read_gpu_prices", names)
        for cap in ("knowledge.models.shortlist", "knowledge.gpu.prices"):
            self.assertIn(cap, blocks.CAPABILITIES)

    def test_they_measure_nothing(self):
        # A world-fact is nobody's evidence: these tools must not be able to
        # stamp a ledger row, today or by drift.
        for control in REGISTRY.controls():
            if control["name"] in ("read_model_shortlist", "read_gpu_prices"):
                self.assertFalse(control.get("measures"),
                                 f"{control['name']} declares measures")


if __name__ == "__main__":
    unittest.main()
