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
        m = db.create_model("qwen3-4b-q4", "Qwen3-4B", "Q4", "QLoRA", "/models/q4", "fits 8GB")
        self.assertEqual(m["name"], "qwen3-4b-q4")
        self.assertEqual(m["quant"], "Q4")
        models = db.list_models()
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0]["method"], "QLoRA")
