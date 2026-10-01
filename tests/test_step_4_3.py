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
        self.recipes = support.recipe_fixtures(Path(self.temp.name))
        self.recipes.__enter__()
        self.client = support.api_client(app)

    def tearDown(self):
        self.client.close()
        self.recipes.__exit__(None, None, None)
        # Windows refuses to unlink a sqlite file while any connection is still
        # open, and a lingering connection in product code should not fail an
        # otherwise-passing test. Leaking a temp dir is the lesser evil.
        try:
            self.temp.cleanup()
        except (PermissionError, OSError):
            pass

    def test_generated_step(self):
        job = db.create_job("s1", support.spec("printer", message="hello-4-3"))
        runner.run_next_job()
        resp = self.client.get(f"/jobs/{job['id']}/log")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("hello-4-3", resp.text)
        self.assertEqual(self.client.get("/jobs/99999/log").status_code, 404)
