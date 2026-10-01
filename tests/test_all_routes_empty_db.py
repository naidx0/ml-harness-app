"""No GET route may return a 500 against an empty database.

The same discovery idea as `test_empty_state_all_helpers`, one layer up.

`GET /jobs/{id}/log` returned 500 for a queued job because `Path(None)` raised
TypeError. It was found by starting a real server and clicking around, not by
the suite, because every generated test creates the row it is about to read.

So this enumerates the app's own routes instead of listing them. A route added
later is covered the moment it exists. 404 and 422 are fine - those are the
app answering correctly about something that is not there, or a bad parameter.
500 means it fell over.
"""
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from app import db

import support

warnings.filterwarnings("ignore")

# Plausible values for path parameters. The point is that nothing exists, so
# these should all miss cleanly rather than crash.
PARAM_VALUES = {
    "session_id": "nobody",
    "job_id": "1",
    "run_id": "1",
    "id": "1",
    # Without these the Conductor's routes are silently SKIPPED by the
    # discovery below - a path whose parameters have no value never gets
    # requested, and nobody would notice the two most important routes of the
    # milestone going uncovered.
    "thread_id": "1",
    "provider_id": "1",
    "project_id": "1",
    "name": "inspect_hardware",
}


class AllRoutesEmptyDbTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.temp.name) / "empty.db"
        db.init_db()
        from app.main import app
        self.app = app
        self.client = support.api_client(app)
        # ONE ROUTE HERE NEVER ENDS ON PURPOSE. `GET /oc/api/event` is
        # OpenCode's event stream, which stays open until the client leaves
        # (`app/facade/stream.py`), and this client reads a whole body before
        # it returns - so the enumeration below would wait for ever on it. The
        # stream's test-only bound makes it finish; the route is still
        # requested and still held to "no 500" like every other.
        from app.facade import stream

        bound = mock.patch.object(stream, "MAX_SECONDS", 0.2)
        bound.start()
        self.addCleanup(bound.stop)

    def tearDown(self):
        self.client.close()
        try:
            self.temp.cleanup()
        except (PermissionError, OSError):
            pass

    def _get_routes(self):
        found = []
        for route in self.app.routes:
            methods = getattr(route, "methods", set()) or set()
            path = getattr(route, "path", "")
            if "GET" not in methods or not path.startswith("/"):
                continue
            concrete = path
            for name, value in PARAM_VALUES.items():
                concrete = concrete.replace("{" + name + "}", value)
            if "{" in concrete:            # a parameter we have no value for
                continue
            found.append((path, concrete))
        return found

    def test_no_get_route_500s_on_an_empty_database(self):
        routes = self._get_routes()
        self.assertGreater(len(routes), 6,
                           "route discovery found almost nothing")
        for path, concrete in routes:
            with self.subTest(route=path):
                resp = self.client.get(concrete)
                self.assertLess(
                    resp.status_code, 500,
                    f"GET {concrete} returned {resp.status_code} against an "
                    f"empty database")

    def test_no_get_route_500s_on_half_finished_data(self):
        """The state that actually caught job_log, which "empty" does not.

        On an empty database `get_job(1)` returns None and the endpoint 404s
        before it can touch `log_path`. The 500 needs a row that EXISTS but is
        incomplete - a job created and never run, an intake with no plan yet.
        Writing this as an empty-database test looked right and proved
        nothing; the mutation check is what exposed that.
        """
        db.create_job("s1", support.spec("demo-metrics"))  # queued, log_path NULL
        db.create_intake("nobody", {})                     # intake with no goal
        db.create_run("r", "{}")                           # run with no metrics
        for path, concrete in self._get_routes():
            with self.subTest(route=path):
                resp = self.client.get(concrete)
                self.assertLess(
                    resp.status_code, 500,
                    f"GET {concrete} returned {resp.status_code} with a row "
                    f"present but unfinished")

    def test_index_and_health_are_always_fine(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/").status_code, 200)


if __name__ == "__main__":
    unittest.main()
