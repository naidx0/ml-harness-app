"""The teaching panel must report the direction the loss actually moved.

Hand-written. The generated acceptance test for 7.2 checked the point count,
the `Heuristic: ` prefix, and that "0.9" appeared somewhere in the observed
string. All three passed while the implementation used `min()` for the first
value and `max()` for the last, so `last > first` held for nearly any run and
a falling loss curve was described as "increasing and may indicate too high a
learning rate".

Wrong teaching output is worse than a crash: it is confidently misleading, and
nothing in the suite objected.
"""
import tempfile
import unittest
from pathlib import Path

from app import db, teach


class LossDirectionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.temp.name) / "test.db"
        db.init_db()

    def tearDown(self):
        try:
            self.temp.cleanup()
        except (PermissionError, OSError):
            pass

    def _run_with(self, values):
        run = db.create_run("t", "{}")
        for step, value in enumerate(values, start=1):
            db.add_metric(run["id"], step, "loss", value)
        return teach.explain_loss(run["id"])

    def test_falling_loss_is_reported_as_decreasing(self):
        out = self._run_with([0.9, 0.6, 0.4])
        self.assertIn("decreasing", out["heuristic"])
        self.assertNotIn("increasing", out["heuristic"])

    def test_rising_loss_is_reported_as_increasing(self):
        out = self._run_with([0.2, 0.5, 0.8])
        self.assertIn("increasing", out["heuristic"])

    def test_observed_states_the_endpoints_in_order(self):
        out = self._run_with([0.9, 0.1, 0.4])
        # earliest is 0.9 and latest is 0.4; min/max would say 0.1 and 0.9
        self.assertIn("0.9", out["observed"])
        self.assertIn("0.4", out["observed"])
        self.assertNotIn("0.1", out["observed"])

    def test_observed_contains_no_interpretation(self):
        out = self._run_with([0.9, 0.4])
        for word in ("increasing", "decreasing", "learning rate", "Heuristic"):
            self.assertNotIn(word, out["observed"])


if __name__ == "__main__":
    unittest.main()
