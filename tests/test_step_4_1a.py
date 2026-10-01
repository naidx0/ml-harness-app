import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app import db
from app.main import app
from app import client
from app import diagram
from app import feasibility
from app import hwdetect
from app import plan

import support



class GeneratedStepTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.temp.name) / "test.db"
        db.init_db()
        self.client = support.api_client(app)

    def tearDown(self):
        self.client.close()
        # Windows refuses to unlink a sqlite file while any connection is still
        # open, and a lingering connection in product code should not fail an
        # otherwise-passing test. Leaking a temp dir is the lesser evil.
        try:
            self.temp.cleanup()
        except (PermissionError, OSError):
            pass

    def test_generated_step(self):
        # Rewritten, not loosened: a job is a structured spec now, so there is
        # no `cmd` column left to assert on. What this step was really about -
        # a row is created queued, and get_job round-trips it - is unchanged.
        db.create_job("s1", support.spec("demo-metrics", steps=3))
        job = db.create_job("s1", support.spec("demo-metrics", steps=3))
        self.assertEqual(job["status"], "queued")
        self.assertEqual(job["recipe"], "demo-metrics")
        self.assertEqual(job["kind"], "train")
        fetched = db.get_job(job["id"])
        self.assertEqual(fetched["config_json"], job["config_json"])
        self.assertNotIn("cmd", job)
        self.assertIsNone(db.get_job(99999))
