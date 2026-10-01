import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import db
from app.main import app

import support


class DashboardChartTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.temp.name) / "dashboard.db"
        db.init_db()
        self.client = support.api_client(app)
        self.response = self.client.get("/")

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def test_dashboard_uses_glass_page_wrapper(self):
        self.assertEqual(self.response.status_code, 200)
        self.assertIn('class="glass"', self.response.text)

    def test_dashboard_drops_old_palette(self):
        for colour in ("#0a0f1c", "#5eead4", "#fb7185"):
            with self.subTest(colour=colour):
                self.assertNotIn(colour, self.response.text)

    def test_chart_container_scrolls_horizontally(self):
        self.assertIn("overflow-x:auto", self.response.text)

    def test_draw_contains_area_fill_and_horizontal_grid_colour(self):
        self.assertIn("rgba(139,124,246,.10)", self.response.text)
        self.assertIn("rgba(255,255,255,.06)", self.response.text)

    def test_dashboard_javascript_contract_is_preserved(self):
        required = (
            'id="run-a"',
            'id="run-b"',
            'id="metric-name"',
            "No ${metric} data for ${runA.name}.",
            "setInterval(loadRuns,2000)",
        )
        for substring in required:
            with self.subTest(substring=substring):
                self.assertIn(substring, self.response.text)


if __name__ == "__main__":
    unittest.main()
