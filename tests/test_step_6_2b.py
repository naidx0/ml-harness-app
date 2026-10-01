import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app import db
from app.main import app
from app import client
from app import dataquality  # Add this import statement
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
        p = Path(self.temp.name) / "d.csv"
        p.write_text("a,b\n1,x\n2,\n1,x\n", encoding="utf-8")
        r = dataquality.data_quality_report(str(p))
        self.assertEqual(r["rows"], 3)
        self.assertEqual(r["duplicates"], 1)
        self.assertAlmostEqual(r["null_rate"]["b"], 0.33, delta=0.01)

