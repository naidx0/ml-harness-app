"""A whole feature was unreachable, and nothing said so.

## The measurement

Across the entire repository on 2026-08-28: `db.create_project` was the **only**
code anywhere that ever wrote `projects.root_path`. `db.default_project()` - the
project every thread lands in unless somebody says otherwise - inserts a name
and nothing else. And the frontend never sent one either:
`frontend/src/lib/useThreads.ts` calls `createProject(name)` and drops the
options argument the client offers.

So on every fresh install, for every person, `root_path` was NULL. All three
standing-constraints tools refused with `no_root_path`, correctly, carrying a
`what_would_fix_it` that named a thing **no route and no tool could do**.

`docs/PRODUCT_SPEC.md` 4.3 describes a file at the project root that every run
inherits and that the harness maintains and scaffolds. None of it could happen.

## What closed it

One writer - `db.set_project_root` - and two doors onto it: `POST
/api/projects/{id}/root` for a folder picker, and the `set_the_project_root`
tool for the sentence somebody actually says, which is where it comes up.
`app/instructions/03_look_before_you_ask.md`'s whole argument is that the
harness acts on what it was told rather than asking again on a form.

## The three refusals that are as load-bearing as the write

**A path that is not a directory** is refused HERE, once, with the path in it -
rather than by every tool that later looks under it.

**Nothing is created.** A root is a place work already is. A tool that made the
directory would turn a typo into a new empty folder and report success.

**Re-pointing is allowed and is reported.** Drives change and work moves; a
first answer made permanent is a settings screen with no edit button. What was
replaced is in the reply so the change is visible.

## What this file does NOT assert

That a person can set a root from the UI. `Rail.tsx` is still the only project
surface and it has no picker - `renameProject`, `archiveProject` and
`moveThread` are wrapped in the client with zero callers, and the root is now a
fourth. The route exists and is driven here; wiring it to a control is Tauri's
`pick_path`, which is Phase V and is not this.
"""

import os
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import db, main
from app.tools import REGISTRY
import support

#: An absolute path on the platform this test is running on, and NOT a fixed
#: Windows one. `D:/work/tickets` is absolute on Windows and relative on
#: Linux - there it names a directory called `D:` - so the route's own
#: refusal of relative roots correctly rejected it, and this test failed on
#: every Ubuntu CI run while passing on the machine it was written on. The
#: route is right; the fixture was platform-blind. The path need not exist:
#: `set_project_root`'s docstring says the existence check belongs where the
#: path is USED, not where it is stored.
A_ROOT = "D:/work/tickets" if os.name == "nt" else "/work/tickets"


class TheWriterThatWasMissingTest(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)

    def test_a_project_starts_with_no_root_and_that_was_the_defect(self):
        """Pinned, because it is the state every install begins in and the
        reason the rest of this file exists."""
        self.assertIsNone(db.create_project("tickets")["root_path"])
        self.assertIsNone(db.default_project()["root_path"])

    def test_a_root_can_be_set_after_the_project_exists(self):
        project = db.create_project("tickets")
        updated = db.set_project_root(project["id"], A_ROOT)
        self.assertEqual(updated["root_path"], A_ROOT)
        self.assertEqual(db.get_project(project["id"])["root_path"], A_ROOT)

    def test_it_stores_the_path_verbatim_exactly_as_its_sibling_does(self):
        """`create_project` stores what it is given - no resolve, no normalise,
        no existence check - and `tests/test_projects.py` pins `/tmp/x` round
        tripping through it. A writer that normalised where its sibling does not
        would mean one project has two different roots depending on which
        function last touched it."""
        project = db.create_project("tickets", "/tmp/x")
        self.assertEqual(project["root_path"], "/tmp/x")
        self.assertEqual(
            db.set_project_root(project["id"], "/tmp/y")["root_path"], "/tmp/y"
        )

    def test_a_project_that_is_not_there_is_None_and_not_an_exception(self):
        """`rename_project`'s contract, and `add_metric`'s before it."""
        self.assertIsNone(db.set_project_root(9999, "D:/anywhere"))


class TheRouteIsOneOfTwoDoorsTest(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)
        self.client = TestClient(main.app)
        self.headers = support.auth_headers()

    def test_it_sets_the_root_and_says_so_on_the_event_spine(self):
        project = db.create_project("tickets")
        response = self.client.post(
            f"/api/projects/{project['id']}/root",
            json={"root_path": A_ROOT},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["root_path"], A_ROOT)
        with db.session() as connection:
            kinds = [
                row["kind"]
                for row in connection.execute(
                    "SELECT kind FROM events WHERE project_id = ?", (project["id"],)
                ).fetchall()
            ]
        self.assertIn("project.root_set", kinds)

    def test_a_project_that_is_not_there_is_a_404(self):
        response = self.client.post(
            "/api/projects/9999/root",
            json={"root_path": "D:/anywhere"},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 404)

    def test_an_empty_root_is_refused_by_the_model_rather_than_stored(self):
        project = db.create_project("tickets")
        response = self.client.post(
            f"/api/projects/{project['id']}/root",
            json={"root_path": ""},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 422)

    def test_it_needs_a_token_like_every_other_mutation(self):
        project = db.create_project("tickets")
        response = self.client.post(
            f"/api/projects/{project['id']}/root", json={"root_path": "D:/x"}
        )
        self.assertEqual(response.status_code, 401)


class TheToolIsTheDoorThatMattersTest(unittest.TestCase):
    """Because this is where it comes up - in the second sentence somebody says."""

    def setUp(self):
        self.root = support.sandbox(self)
        self.thread = int(support.conversations(1)[0]["id"])
        self.work = self.root / "work"
        self.work.mkdir()

    def _set(self, path, **over):
        return REGISTRY.call(
            "set_the_project_root",
            {"path": str(path)},
            actor="user",
            thread_id=over.pop("thread_id", self.thread),
            approved=True,
        )

    def test_it_needs_approval_and_measures_nothing(self):
        """It records WHERE to look, which decides nothing about what is found
        there. A tool that stamped a fact from a path somebody typed would be a
        measurement of the typing."""
        spec = REGISTRY.get("set_the_project_root")
        self.assertEqual(spec.measures, ())
        self.assertEqual(spec.approval, "always")
        self.assertIn("context.project.constraints", spec.provides)

    def test_the_whole_chain_that_could_not_run_before(self):
        """THE POINT OF THE CHANGE, driven end to end.

        Rootless project refuses; the root is set; the reader works; the
        scaffold writes the file PRODUCT_SPEC 4.3 describes. Every rung of this
        was already built and the first one could not be climbed.
        """
        before = REGISTRY.call(
            "read_the_standing_constraints", {}, actor="user", thread_id=self.thread
        )
        self.assertEqual(before["error"], "no_root_path")

        self.assertTrue(self._set(self.work)["ok"])

        after = REGISTRY.call(
            "read_the_standing_constraints", {}, actor="user", thread_id=self.thread
        )
        self.assertTrue(after["ok"])
        self.assertFalse(after["found"], "nothing should have been created")

        scaffolded = REGISTRY.call(
            "scaffold_the_standing_constraints",
            {},
            actor="user",
            thread_id=self.thread,
            approved=True,
        )
        self.assertTrue(scaffolded["ok"], scaffolded)
        from app.tools import context

        self.assertTrue((self.work / context.STANDING_CONSTRAINTS).is_file())

    def test_a_path_that_is_not_a_directory_is_refused_with_the_path_in_it(self):
        refused = self._set(self.root / "not-there")
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["error"], "not_a_directory")
        self.assertIn("not-there", refused["path"])

    def test_it_creates_nothing(self):
        """A typo turned into an empty folder is a success message about
        nothing, which is the shape of every silent failure this refuses."""
        missing = self.root / "not-there"
        self._set(missing)
        self.assertFalse(missing.exists())

    def test_a_file_is_not_a_root(self):
        a_file = self.root / "notes.txt"
        a_file.write_text("hello", encoding="utf-8")
        self.assertEqual(self._set(a_file)["error"], "not_a_directory")

    def test_re_pointing_is_allowed_and_says_what_it_replaced(self):
        """Drives change and work moves. A first answer made permanent is a
        settings screen with no edit button - and a change nobody is told about
        is worse than one they have to confirm."""
        second = self.root / "elsewhere"
        second.mkdir()
        self._set(self.work)
        again = self._set(second)
        self.assertTrue(again["ok"])
        self.assertEqual(again["replaced"], str(self.work))
        self.assertIn("replacing", again["summary"])
        self.assertIn("still on disk", again["summary"])

    def test_the_first_setting_does_not_claim_to_have_replaced_anything(self):
        first = self._set(self.work)
        self.assertIsNone(first["replaced"])
        self.assertNotIn("replacing", first["summary"])

    def test_it_says_what_it_unlocks_and_that_it_created_no_file(self):
        from app.tools import context

        unlocked = self._set(self.work)["what_this_unlocks"]
        self.assertIn(context.STANDING_CONSTRAINTS, unlocked)
        self.assertIn("Nothing was created", unlocked)

    def test_outside_a_conversation_there_is_no_project_to_point(self):
        outside = REGISTRY.call(
            "set_the_project_root",
            {"path": str(self.work)},
            actor="user",
            approved=True,
        )
        self.assertFalse(outside["ok"])
        self.assertEqual(outside["error"], "no_conversation")

    def test_an_empty_path_is_refused_before_anything_is_looked_at(self):
        refused = REGISTRY.call(
            "set_the_project_root",
            {"path": "   "},
            actor="user",
            thread_id=self.thread,
            approved=True,
        )
        self.assertEqual(refused["error"], "no_path")

    def test_nothing_it_returns_is_a_measurement_and_it_says_so(self):
        reply = self._set(self.work)
        self.assertIn("stamps no fact", reply["nothing_here_is_a_measurement"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
