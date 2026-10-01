"""The log endpoint must work for a job in every state, not just a finished one.

Found by running the server for real and asking for the log of a job that had
been queued but never run. `/jobs/1/log` returned 500: a queued row has the
`log_path` KEY present with a None VALUE, so the endpoint's
`"log_path" not in job` check never fired and `Path(None)` raised TypeError.

Every generated test ran the job first, so the happy path was the only path
anything exercised. This is the third defect this session that only appeared
once something set up nothing.
"""
import unittest
import warnings

from app import db, jobspec, runner

import support

warnings.filterwarnings("ignore")


class JobLogStatesTest(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)
        from app.main import app
        self.client = support.api_client(app)
        self.addCleanup(self.client.close)

    def test_queued_job_log_is_empty_not_an_error(self):
        job = db.create_job("s1", support.spec("printer", message="x"))
        resp = self.client.get(f"/jobs/{job['id']}/log")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.text, "")

    def test_finished_job_log_has_the_output(self):
        db.create_job("s1", support.spec("printer", message="4321"))
        runner.run_next_job()
        resp = self.client.get("/jobs/1/log")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("4321", resp.text)

    def test_the_log_route_serves_the_path_the_runner_actually_wrote(self):
        """The route reads `log_path` off the row, so it needs no convention.

        This is the whole compatibility story for the move out of the flat
        `logs/` folder: a job records where it wrote, and the endpoint reads
        that, so rows written under the old layout keep serving from the old
        layout with nothing to translate. The assertion here is that the two
        agree for a job written under the new one.
        """
        db.create_job("s1", support.spec("printer", message="9876"))
        done = runner.run_next_job()
        self.assertEqual(done["log_path"], str(jobspec.log_path_for(1)))
        resp = self.client.get("/jobs/1/log")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("9876", resp.text)

    def test_missing_job_is_404(self):
        self.assertEqual(self.client.get("/jobs/99999/log").status_code, 404)

    def test_jobs_page_renders_with_no_jobs_at_all(self):
        resp = self.client.get("/ui/jobs")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.text.count("<tr>"), 0)


if __name__ == "__main__":
    unittest.main()
