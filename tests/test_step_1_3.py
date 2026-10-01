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
        resp = self.client.get("/intake/questions")
        self.assertEqual(resp.status_code, 200)
        items = resp.json()
        self.assertGreater(len(items), 0)
        for item in items:
            self.assertIn("id", item)
            self.assertIn("prompt", item)
            self.assertIn("type", item)
            self.assertIn("options", item)
