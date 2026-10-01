import tempfile
import unittest
from pathlib import Path

from app import db


class IntakeStorageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.temp.name) / "test.db"
        db.init_db()

    def tearDown(self):
        try:
            self.temp.cleanup()
        except (PermissionError, OSError):
            pass

    def test_answers_round_trip(self):
        answers = {"goal": "fine-tune", "dataset_rows": 5000, "kind": "text"}
        created = db.create_intake("s1", answers)
        self.assertEqual(created["session_id"], "s1")
        self.assertEqual(created["answers"], answers)

        fetched = db.get_intake("s1")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["answers"], answers)
        self.assertEqual(fetched["answers"]["dataset_rows"], 5000)

    def test_missing_session_returns_none(self):
        self.assertIsNone(db.get_intake("nope"))

    def test_latest_answers_win(self):
        db.create_intake("s2", {"goal": "first"})
        db.create_intake("s2", {"goal": "second"})
        self.assertEqual(db.get_intake("s2")["answers"]["goal"], "second")
