import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import db
from app.main import app

import support


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.temp.name) / "test.db"
        db.init_db()
        self.client = support.api_client(app)

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def test_run_metric_complete_flow(self):
        created = self.client.post("/api/runs", json={"name": "unit", "params": {"lr": 0.1}})
        self.assertEqual(created.status_code, 201)
        run_id = created.json()["id"]
        metric = self.client.post(
            f"/api/runs/{run_id}/metrics", json={"step": 0, "name": "loss", "value": 1.25}
        )
        self.assertEqual(metric.status_code, 201)
        self.assertEqual(self.client.get(f"/api/runs/{run_id}/metrics").json()[0]["value"], 1.25)
        completed = self.client.post(f"/api/runs/{run_id}/complete")
        self.assertEqual(completed.json()["status"], "completed")

    def test_missing_run_rejected(self):
        response = self.client.post(
            "/api/runs/999/metrics", json={"step": 0, "name": "loss", "value": 1.0}
        )
        self.assertEqual(response.status_code, 404)

    def test_metrics_can_be_filtered_by_name_and_are_step_ordered(self):
        run_id = self.client.post("/api/runs", json={"name": "compare"}).json()["id"]
        for step, name, value in [(10, "loss", 0.4), (1, "accuracy", 0.7), (2, "loss", 0.8)]:
            response = self.client.post(
                f"/api/runs/{run_id}/metrics",
                json={"step": step, "name": name, "value": value},
            )
            self.assertEqual(response.status_code, 201)

        filtered = self.client.get(f"/api/runs/{run_id}/metrics", params={"name": "loss"})
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual([metric["step"] for metric in filtered.json()], [2, 10])
        self.assertTrue(all(metric["name"] == "loss" for metric in filtered.json()))

        unfiltered = self.client.get(f"/api/runs/{run_id}/metrics")
        self.assertEqual(len(unfiltered.json()), 3)

    def test_dashboard_contains_comparison_controls_and_missing_data_feedback(self):
        html = self.client.get("/").text
        self.assertIn('id="run-a"', html)
        self.assertIn('id="run-b"', html)
        self.assertIn('id="metric-name"', html)
        self.assertIn("No ${metric} data for ${runA.name}.", html)
        self.assertIn("setInterval(loadRuns,2000)", html)


if __name__ == "__main__":
    unittest.main()
