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

    def test_the_questions_are_served_for_whatever_renders_them(self):
        """WAS A TEST OF THE FORM THAT RENDERED THEM. `docs/THE_PLAN.md` V.3 A9
        retired `/ui/intake`, so what is left to assert is the thing that
        survived it: the questions are still published, and they are still the
        prompts a caller would put in front of somebody. The renderer is the
        React app now, and it reads this endpoint."""
        questions = self.client.get("/intake/questions").json()
        self.assertTrue(questions)
        for question in questions:
            with self.subTest(question=question.get("prompt")):
                self.assertTrue(str(question["prompt"]).strip())

    def test_the_form_that_used_to_render_them_is_gone(self):
        """Asserted rather than left implicit, because a route coming back is
        exactly when somebody should be asked whether its CSRF exemption is
        coming back with it."""
        self.assertEqual(self.client.get("/ui/intake").status_code, 404)
