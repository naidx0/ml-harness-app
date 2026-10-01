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
from app import runner

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
        self.client.post("/intake", json={"session_id": "u1", "answers": {"goal": "fine-tune"}})
        resp = self.client.get("/ui/plan/u1")
        self.assertEqual(resp.status_code, 200)
        # The page renders the markdown now instead of dumping it, so the
        # heading arrives as an element. Asserting the literal "# Training plan"
        # here was asserting the defect.
        self.assertIn("<h1>Training plan</h1>", resp.text)
        self.assertIn("flowchart", resp.text)
        self.assertEqual(self.client.get("/ui/plan/nope").status_code, 404)
