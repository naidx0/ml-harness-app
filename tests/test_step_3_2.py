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
        out = diagram.render_diagram(feasibility.recommend("fine-tune", 8.0), feasibility.verdict(feasibility.measured(8.0, 'nvidia-smi'), 4.19, 3.5))
        self.assertTrue(out.startswith(chr(96) * 3 + "mermaid"))
        self.assertIn("flowchart LR", out)
        self.assertIn("Qwen3-4B", out)
        self.assertIn("SPILLS", out)
        self.assertGreaterEqual(out.count("-->"), 4)
        self.assertTrue(out.rstrip().endswith(chr(96) * 3))
        self.assertEqual(out.count(chr(96) * 3), 2)
