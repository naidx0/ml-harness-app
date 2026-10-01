"""Every db helper must work against a database that has nothing in it.

`list_jobs` shipped without its `ensure_jobs_table()` call. Its generated
acceptance test created two jobs first, so the table already existed by the
time it was listed and the omission was invisible - until the jobs page tried
to render an empty queue and got "no such table: jobs".

The pattern is the one worth guarding: a test that sets up its own data can
hide a missing table-creation call. These tests deliberately set up nothing.
"""
import tempfile
import unittest
from pathlib import Path

from app import db


class EmptyDatabaseTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.temp.name) / "empty.db"
        db.init_db()

    def tearDown(self):
        try:
            self.temp.cleanup()
        except (PermissionError, OSError):
            pass

    def test_list_jobs_on_a_fresh_database(self):
        self.assertEqual(db.list_jobs(), [])

    def test_next_queued_job_on_a_fresh_database(self):
        self.assertIsNone(db.next_queued_job())

    def test_get_job_on_a_fresh_database(self):
        self.assertIsNone(db.get_job(1))

    def test_get_intake_on_a_fresh_database(self):
        self.assertIsNone(db.get_intake("nobody"))


if __name__ == "__main__":
    unittest.main()
