"""The defect that made the product a demo rather than a tool.

`available_gb = 8.0`, `weights_gb = 4.19` and `activations_gb = 3.5` appeared
literally at three call sites - `GET /plan/{id}`, `GET /plan/{id}/download` and
`GET /ui/plan/{id}` - so every plan, for every user, on every machine, for every
goal, returned the same verdict. The app could record that you own a 24 GB 4090
and still tell you your plan spilled on 8 GB.

All three routes are covered, because fixing two of three would leave the same
bug reachable through the third.
"""

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import db, feasibility
from app.main import app

import support

PLAN_ROUTES = ("/plan/{sid}", "/plan/{sid}/download", "/ui/plan/{sid}")


class PlanReadsHardwareProfileTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.temp.name) / "plan-hw.db"
        db.init_db()
        self.client = support.api_client(app)
        self.sid = "hw-plan"
        db.create_intake(
            self.sid,
            {"goal": "Fine-tune a classifier", "dataset_size": "1000",
             "data_kind": "Text"},
        )

    def tearDown(self):
        self.client.close()
        try:
            self.temp.cleanup()
        except (PermissionError, OSError):
            pass

    def profile(self, vram_gb: float, name: str = "card"):
        return db.create_hardware_profile(
            gpu_name=name, vram_gb=vram_gb, ram_gb=16.0,
            os="Windows 11", disk_free_gb=100.0,
        )

    def fetch(self, route: str) -> str:
        response = self.client.get(route.format(sid=self.sid))
        self.assertEqual(response.status_code, 200, route)
        return response.text

    def test_no_route_hardcodes_the_literals_any_more(self):
        """Parsed, not grepped, so prose about the defect does not fool it."""
        import ast

        import app.main

        tree = ast.parse(Path(app.main.__file__).read_text(encoding="utf-8"))
        floats = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, float)
        }

        for literal in (8.0, 4.19, 3.5):
            with self.subTest(literal=literal):
                self.assertNotIn(literal, floats)

    def test_every_plan_route_changes_its_answer_with_the_hardware(self):
        self.profile(1.0, "tiny")
        tiny = {route: self.fetch(route) for route in PLAN_ROUTES}

        self.profile(48.0, "A6000")
        large = {route: self.fetch(route) for route in PLAN_ROUTES}

        for route in PLAN_ROUTES:
            with self.subTest(route=route):
                self.assertNotEqual(
                    tiny[route], large[route],
                    f"{route} returned the same page for a 1 GB card and a 48 GB card",
                )

    def test_a_card_too_small_for_the_weights_is_told_so_on_every_route(self):
        self.profile(1.0, "tiny")

        for route in PLAN_ROUTES:
            with self.subTest(route=route):
                self.assertIn("WONT_FIT", self.fetch(route))

    def test_with_no_hardware_profile_the_verdict_is_UNKNOWN_not_SPILLS(self):
        """Ruling 6. The old answer was SPILLS, computed from a made-up 8.0."""
        for route in PLAN_ROUTES:
            with self.subTest(route=route):
                body = self.fetch(route)
                self.assertIn("UNKNOWN", body)
                self.assertNotIn("SPILLS", body)

    def test_the_recommended_model_follows_the_recorded_vram(self):
        self.profile(8.0, "RTX 2060 SUPER")
        small = self.fetch("/plan/{sid}")

        self.profile(24.0, "RTX 4090")
        large = self.fetch("/plan/{sid}")

        self.assertIn("Qwen3-4B", small)
        self.assertIn("Qwen3-8B", large)

    def test_the_plan_page_renders_the_recorded_vram_rather_than_eight(self):
        self.profile(24.0, "RTX 4090")

        body = self.fetch("/ui/plan/{sid}")

        self.assertIn("24.00 GB", body)
        self.assertNotIn("8.00 GB", body)

    def test_the_page_never_prints_a_number_it_does_not_have(self):
        """With nothing recorded, the memory line is em dashes, not 0.00 GB."""
        body = self.fetch("/ui/plan/{sid}")

        self.assertIn("&mdash; needed", body)
        self.assertNotIn("0.00 GB available", body)


class PlanUsesTheDataKindTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.temp.name) / "plan-kind.db"
        db.init_db()
        self.client = support.api_client(app)

    def tearDown(self):
        self.client.close()
        try:
            self.temp.cleanup()
        except (PermissionError, OSError):
            pass

    def plan_for(self, data_kind: str) -> str:
        sid = f"kind-{data_kind}"
        db.create_intake(
            sid,
            {"goal": "Fine-tune a classifier", "dataset_size": "1000",
             "data_kind": data_kind},
        )
        response = self.client.get(f"/plan/{sid}")
        self.assertEqual(response.status_code, 200)
        return response.text

    def test_an_image_goal_is_not_answered_with_a_language_model(self):
        body = self.plan_for("Image")

        self.assertNotIn("Qwen", body)
        self.assertIn("vit", body.lower())

    def test_a_tabular_goal_is_not_answered_with_a_language_model(self):
        body = self.plan_for("Tabular")

        self.assertNotIn("Qwen", body)
        self.assertIn("gradient boosting", body)

    def test_a_text_goal_still_gets_a_language_model(self):
        self.assertIn("Qwen", self.plan_for("Text"))

    def test_the_three_data_kinds_do_not_all_produce_the_same_plan(self):
        plans = {kind: self.plan_for(kind) for kind in ("Text", "Image", "Tabular")}

        self.assertEqual(len(set(plans.values())), 3)


class PlanInputsProvenanceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.temp.name) / "plan-prov.db"
        db.init_db()

    def tearDown(self):
        try:
            self.temp.cleanup()
        except (PermissionError, OSError):
            pass

    def test_a_typed_in_profile_is_declared_not_measured(self):
        from app.main import plan_inputs

        db.create_hardware_profile(
            gpu_name="RTX 4090", vram_gb=24.0, ram_gb=64.0,
            os="Windows 11", disk_free_gb=500.0,
        )

        _rec, _estimate, verdict_info = plan_inputs({"goal": "fine-tune"})

        # POST /hardware is a person typing a number in. That is a declaration,
        # not a measurement, and the two must not be spelled the same way.
        self.assertEqual(verdict_info["vram_provenance"], "declared")

    def test_no_profile_means_defaulted_and_therefore_unknown(self):
        from app.main import plan_inputs

        _rec, _estimate, verdict_info = plan_inputs({"goal": "fine-tune"})

        self.assertEqual(verdict_info["vram_provenance"], "defaulted")
        self.assertEqual(verdict_info["verdict"], "UNKNOWN")
        self.assertIn(verdict_info["verdict"], feasibility.VERDICTS)


if __name__ == "__main__":
    unittest.main()
