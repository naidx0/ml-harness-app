"""The plan page, reached the way it is now reachable.

## What this file used to be

Four tests of `GET /ui/intake` and `POST /ui/intake` - the server-rendered form
that took a goal and redirected to a plan. `docs/THE_PLAN.md` V.3 A9 retired
that form: it was the last server-rendered thing that CHANGED state, and the
only reason `security.BROWSER_FORM_ROUTES` had a member.

## What survived, and why it is worth keeping

`/ui/plan/{session_id}` is still there and is NOT orphaned. An intake is created
by `POST /api/intake`, the JSON surface the React app and any script already
use, and the page renders whatever session id it is handed. So the assertions
that were about the PAGE - that it shows the goal back, that it carries a
verdict pill - are still real assertions about shipped behaviour, and they are
kept here driven through the door that remains.

What is gone with the form is the assertions that were about the FORM: that it
had exactly one input, that it used the composer style, that submitting it
redirected. Those described markup that no longer exists, and a test that keeps
describing deleted markup is how a suite comes to be read as decoration.
"""

import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from app import db
from app.main import app

import support


class ThePlanPageRendersWhatItWasGivenTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.temp.name) / "test.db"
        db.init_db()
        self.client = support.api_client(app)
        self.headers = support.auth_headers()

    def tearDown(self):
        self.client.close()
        try:
            self.temp.cleanup()
        except (PermissionError, OSError):
            pass

    def _an_intake(self, goal: str) -> str:
        """One intake, through the JSON door - the one that is left.

        `POST /intake`, which is the surface the React app and any script use.
        It takes a token like every other state-changing route, which is the
        whole of what A9 bought: there is no longer a path that does not.
        """
        session_id = uuid4().hex
        response = self.client.post(
            "/intake",
            json={"session_id": session_id, "answers": {"goal": goal}},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 201, response.text)
        return session_id

    def test_the_plan_page_shows_the_goal_back(self):
        goal = "Fine-tune a tiny text classifier"
        response = self.client.get(f"/ui/plan/{self._an_intake(goal)}")

        self.assertEqual(response.status_code, 200)
        self.assertIn(goal, response.text)

    def test_the_plan_page_carries_a_verdict(self):
        """The pill is the whole point of the page: a plan that did not say what
        it had concluded would be a document about a decision nobody made."""
        response = self.client.get(f"/ui/plan/{self._an_intake('Route tickets')}")

        self.assertEqual(response.status_code, 200)
        self.assertIn('class="vpill', response.text)

    def test_a_session_that_does_not_exist_is_a_404(self):
        self.assertEqual(self.client.get(f"/ui/plan/{uuid4().hex}").status_code, 404)

    def test_the_form_that_used_to_reach_it_is_gone(self):
        """Asserted rather than left implicit. A route coming back is exactly
        when somebody should be asked whether the CSRF exemption it needed is
        coming back with it - see `tests/test_security_boundary.py`."""
        self.assertEqual(self.client.get("/ui/intake").status_code, 404)
        self.assertEqual(
            self.client.post("/ui/intake", data={"goal": "x"}).status_code, 404
        )


if __name__ == "__main__":
    unittest.main()
