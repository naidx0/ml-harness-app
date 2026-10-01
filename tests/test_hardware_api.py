import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import db
from app.main import app

import support


class HardwareApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.temp.name) / "test.db"
        db.init_db()
        self.client = support.api_client(app)

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def test_post_then_get_latest_hardware(self):
        body = {
            "gpu_name": "RTX 2060 Super",
            "vram_gb": 8.0,
            "ram_gb": 16.0,
            "os": "Windows 11",
            "disk_free_gb": 720.6,
        }
        created = self.client.post("/hardware", json=body)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["gpu_name"], "RTX 2060 Super")

        latest = self.client.get("/hardware")
        self.assertEqual(latest.status_code, 200)
        self.assertEqual(latest.json()["gpu_name"], "RTX 2060 Super")
        self.assertAlmostEqual(latest.json()["vram_gb"], 8.0)

    def test_get_latest_returns_404_when_empty(self):
        self.assertEqual(self.client.get("/hardware").status_code, 404)

    def test_latest_reflects_most_recent_insert(self):
        for name in ("first", "second"):
            self.client.post("/hardware", json={
                "gpu_name": name, "vram_gb": 8.0, "ram_gb": 16.0,
                "os": "Windows 11", "disk_free_gb": 100.0,
            })
        self.assertEqual(self.client.get("/hardware").json()["gpu_name"], "second")
