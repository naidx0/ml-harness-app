import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import db
from app.main import app

import support


class PlanHierarchyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.temp.name) / "plan-hierarchy.db"
        db.init_db()
        self.client = support.api_client(app)
        self.session_id = "plan-hierarchy"
        # Updated: this fixture asks for an image classifier over image data and
        # used to assert the page recommended Qwen3-4B, a language model. The
        # fixture was right and the answer was wrong - `recommend` never
        # received the data kind. The heading and duplication assertions below
        # are unchanged; only the name of the model they expect has moved.
        self.model_name = "google/vit-base-patch16-224"
        db.create_intake(
            self.session_id,
            {
                "goal": "Fine-tune a small image classifier on my RTX 2060 SUPER",
                "dataset_size": "12000",
                "data_kind": "images",
            },
        )
        self.page_response = self.client.get(f"/ui/plan/{self.session_id}")
        self.body = self.page_response.text.split("<body>", 1)[1].split("</body>", 1)[0]

    def tearDown(self):
        self.client.close()
        try:
            self.temp.cleanup()
        except (PermissionError, OSError):
            pass

    def test_plan_page_body_has_one_h1(self):
        self.assertEqual(self.body.count("<h1"), 1)

    def test_training_plan_is_the_h1(self):
        self.assertIn("<h1>Training plan</h1>", self.body)

    def test_old_plan_h1_is_absent(self):
        self.assertNotIn("<h1>Plan</h1>", self.body)

    def test_the_duplicate_summary_paragraph_is_gone(self):
        """The model+verdict paragraph must not restate the glass panel.

        This test used to assert the model name appeared exactly ONCE in the
        body. That was a count where I meant an intent, and it made the product
        worse to satisfy it: the mermaid diagram had its model name replaced
        with the words "recommended model" purely so the total stayed at one.
        The diagram legitimately names the model. What must not happen is the
        markdown restating the panel directly beneath the heading.
        """
        heading = "<h1>Training plan</h1>"
        after_heading = self.body[self.body.index(heading) + len(heading):]
        first_chunk = after_heading[:200]

        self.assertNotIn(f"<p>{self.model_name}", first_chunk)
        self.assertNotIn("verdict:", first_chunk)

    def test_the_diagram_still_names_the_real_model(self):
        # Losing this is what the old counting assertion cost us.
        self.assertIn(f"Train {self.model_name}", self.body)
        self.assertNotIn("recommended model", self.body)

    def test_an_image_goal_is_not_answered_with_a_language_model(self):
        self.assertNotIn("Qwen", self.body)

    def test_the_verdict_pill_is_not_labelled(self):
        # "verdict: SPILLS" inside a pill is a label restating its own context.
        self.assertNotIn("verdict: SPILLS", self.body)

    def test_plaintext_plan_keeps_full_markdown_header(self):
        response = self.client.get(f"/plan/{self.session_id}")

        self.assertEqual(response.status_code, 200)
        self.assertIn(self.model_name, response.text)
        self.assertIn("verdict:", response.text)
        self.assertIn("# Training plan", response.text)


if __name__ == "__main__":
    unittest.main()
