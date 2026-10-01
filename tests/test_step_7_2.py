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
from app import dataquality
from app import diagram
from app import export
from app import feasibility
from app import hwdetect
from app import plan
from app import runner
from app import teach

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
        run = db.create_run("t", "{}")
        db.add_metric(run["id"], 1, "loss", 0.9)
        db.add_metric(run["id"], 2, "loss", 0.4)
        out = teach.explain_loss(run["id"])
        self.assertEqual(out["points"], 2)
        self.assertTrue(out["heuristic"].startswith("Heuristic: "))
        self.assertIn("0.9", out["observed"])
