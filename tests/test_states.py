import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import db
from app.main import app

import support


class StatesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.temp.name) / "states.db"
        db.init_db()
        self.client = support.api_client(app)

    def tearDown(self):
        self.client.close()
        try:
            self.temp.cleanup()
        except (PermissionError, OSError):
            pass

    def plan_response(self):
        session_id = "states-plan"
        db.create_intake(
            session_id,
            {
                "goal": "Fine-tune a classifier",
                "dataset_size": "Small",
                "data_kind": "Text",
            },
        )
        return self.client.get(f"/ui/plan/{session_id}")

    def test_empty_dashboard_names_state_and_seed_command(self):
        response = self.client.get("/")

        self.assertIn("No runs recorded yet.", response.text)
        self.assertIn("scripts/demo_train.py", response.text)

    def test_empty_dashboard_returns_200(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)

    def test_metric_missing_state_template_remains_verbatim(self):
        response = self.client.get("/")

        self.assertIn("No ${metric} data for ${runA.name}.", response.text)

    def test_plan_basis_names_what_it_could_not_measure(self):
        """Updated: the basis used to advertise the defect as a feature.

        It read "This plan assumes the documented 8.00 GB VRAM default. The
        recommendation is keyed on the goal text only and does not consider the
        data kind." Both halves are now false by construction - the VRAM figure
        comes from the saved hardware profile and the recommendation routes on
        the data kind - so the assertion on "8.00 GB" is gone with the literal
        that produced it. What the basis must still do is name its inputs and
        their provenance, and with no hardware profile recorded that means
        saying so rather than substituting a number.
        """
        response = self.plan_response()

        self.assertIn("data kind", response.text)
        self.assertIn("UNKNOWN", response.text)
        self.assertIn("not measured this machine", response.text)
        self.assertNotIn("8.00 GB", response.text)

    def test_a_saved_hardware_profile_reaches_the_plan_page(self):
        """The defect that made the product a demo: the plan ignored the profile."""
        db.create_hardware_profile(
            gpu_name="RTX 4090", vram_gb=24.0, ram_gb=64.0,
            os="Windows 11", disk_free_gb=500.0,
        )

        response = self.plan_response()

        self.assertIn("24.00 GB", response.text)
        self.assertNotIn("8.00 GB", response.text)

    def test_two_hardware_profiles_produce_two_different_verdicts(self):
        """ROADMAP M0 acceptance evidence, as a test.

        Every plan for every user for every goal used to return SPILLS.
        """
        db.create_hardware_profile(
            gpu_name="tiny", vram_gb=1.0, ram_gb=8.0,
            os="Windows 11", disk_free_gb=100.0,
        )
        tiny = self.plan_response().text

        db.create_hardware_profile(
            gpu_name="RTX 4090", vram_gb=24.0, ram_gb=64.0,
            os="Windows 11", disk_free_gb=500.0,
        )
        large = self.plan_response().text

        def pill(body: str) -> str:
            start = body.index('class="vpill')
            return body[start:body.index("</span>", start)]

        self.assertIn("WONT_FIT", pill(tiny))
        self.assertNotIn("WONT_FIT", pill(large))

    def test_plan_basis_is_between_budget_and_training_plan(self):
        body = self.plan_response().text

        self.assertLess(body.index('<div class="budget"'), body.index('class="dim basis"'))
        self.assertLess(body.index('class="dim basis"'), body.index("<h1>Training plan</h1>"))


if __name__ == "__main__":
    unittest.main()
