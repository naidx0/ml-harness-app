import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import db
from app.main import app

import support


class PlanPageRenderTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.temp.name) / "plan-page.db"
        db.init_db()
        self.client = support.api_client(app)

    def tearDown(self):
        self.client.close()
        try:
            self.temp.cleanup()
        except (PermissionError, OSError):
            pass

    def test_goal_html_is_escaped_before_rendering(self):
        session_id = "xss-guard"
        db.create_intake(
            session_id,
            {
                "goal": '<img src=x onerror="document.title=\'pwned\'">',
                "dataset_size": "Small",
                "data_kind": "Image",
            },
        )

        response = self.client.get(f"/ui/plan/{session_id}")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("<img src=x", response.text)
        self.assertIn("&lt;img", response.text)

    def test_markdown_headings_are_rendered_as_html(self):
        session_id = "render-guard"
        db.create_intake(
            session_id,
            {
                "goal": "Classify handwritten constellations",
                "dataset_size": "Small",
                "data_kind": "Image",
            },
        )

        response = self.client.get(f"/ui/plan/{session_id}")

        self.assertEqual(response.status_code, 200)
        self.assertIn("<h1>", response.text)
        self.assertIn("<h2>", response.text)
        self.assertNotIn("# Training plan", response.text)


if __name__ == "__main__":
    unittest.main()
