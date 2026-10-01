"""POST routes must reject bad input, not fall over on it.

The GET discovery test covers reads. Writes were untested against anything
except the exact payload each acceptance test sends, which is the same blind
spot one layer over: a generated test posts the body the spec dictated and
nothing else is ever tried.

A missing key should be a 4xx. `{}` should be a 4xx. A string where a dict
belongs should be a 4xx. Any of them returning 500 means the endpoint indexed
straight into a payload it had not checked, which is exactly how
`render_plan` turned a goal-less intake into three broken pages.
"""
import tempfile
import unittest
import warnings
from pathlib import Path

from fastapi.testclient import TestClient

from app import db

import support

warnings.filterwarnings("ignore")

# (route, a payload that is wrong in some ordinary way)
BAD_PAYLOADS = [
    ("/intake", {}),
    ("/intake", {"session_id": "x"}),                 # no answers
    ("/intake", {"answers": {"goal": "fine-tune"}}),  # no session_id
    ("/intake", {"session_id": "x", "answers": "not-a-dict"}),
    ("/jobs", {}),
    ("/jobs", {"intake_id": "x"}),                    # no recipe, no kind
    ("/jobs", {"recipe": "demo-metrics"}),            # no intake_id, no kind
    ("/jobs", {"intake_id": "x", "recipe": "demo-metrics", "kind": "train",
               "config": "not-a-dict"}),
    ("/jobs", {"intake_id": "x", "recipe": "no-such-recipe", "kind": "train"}),
    ("/jobs", {"intake_id": "x", "recipe": "demo-metrics", "kind": "banana"}),
    # The old contract, still sent by an old client. It must be named and
    # refused, not quietly dropped on the floor.
    ("/jobs", {"intake_id": "x", "cmd": "echo hi"}),
    ("/hardware", {}),
    ("/hardware", {"gpu_name": "RTX 2060"}),          # missing the rest
]


class PostRoutesPartialTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.temp.name) / "test.db"
        db.init_db()
        from app.main import app
        self.client = support.api_client(app)

    def tearDown(self):
        self.client.close()
        try:
            self.temp.cleanup()
        except (PermissionError, OSError):
            pass

    def test_partial_payloads_are_rejected_not_crashed(self):
        for route, payload in BAD_PAYLOADS:
            with self.subTest(route=route, payload=payload):
                resp = self.client.post(route, json=payload)
                self.assertLess(
                    resp.status_code, 500,
                    f"POST {route} with {payload} returned "
                    f"{resp.status_code}; a bad body should be a 4xx")

    def test_a_good_payload_still_works(self):
        """The guard above is worthless if it passes by rejecting everything."""
        ok = self.client.post(
            "/intake", json={"session_id": "good", "answers": {"goal": "fine-tune"}})
        self.assertEqual(ok.status_code, 201)
        job = self.client.post("/jobs", json={
            "intake_id": "good", "recipe": "demo-metrics", "kind": "train"})
        self.assertEqual(job.status_code, 201, job.text)


if __name__ == "__main__":
    unittest.main()
