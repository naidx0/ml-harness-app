"""One project's experiments are that project's — without moving a directory.

## What was asked for, and the half of it that is a trap

`docs/THE_PLAN.md` IV.0 asks for "sandboxes keyed to the project rather than the
database". Measured: `sandbox.sandboxes_root()` is the single seam every path in
that module goes through, and `sandbox_path`'s parent-identity guard means
nothing can reach a directory that bypasses it. Putting a project level into
that path is a two-line change.

**And it would orphan every sandbox already on disk.** The parent guard would
refuse them, `destroy` requires a manifest it could no longer find, and what is
left is folders holding somebody's data snapshots and gigabytes of pinned
environment that no tool can list or delete. Moving them instead is a
destructive filesystem operation on exactly that.

So the path does not move. **The manifest learns the project and the listing
filters on it**, which delivers what the scoping was for at no migration risk
and leaves the directory layout free for a decision somebody can take on
purpose later.

## The three cases, and the middle one is the whole design

- No project asked → everything shows. Narrowing on a question nobody asked
  would hide somebody's experiments to answer nothing.
- **The sandbox names no project** → it shows EVERYWHERE. It predates the field,
  it is real data, and a filter it predates must not be the thing that loses it.
- Both name one → they must match.

An unreadable directory is never filtered either: it has no manifest, so it has
no project, and deciding it belongs to somebody else would be inventing the one
fact it is unreadable for.
"""

import json
import unittest

from app.tools import REGISTRY, sandbox
import support


class TheManifestCarriesTheProjectTest(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)
        rows = support.conversations(2)
        self.first, self.first_project = int(rows[0]["id"]), rows[0]["project"]
        self.second, self.second_project = int(rows[1]["id"]), rows[1]["project"]
        self.data = self.root / "data"
        self.data.mkdir()
        (self.data / "rows.jsonl").write_text("{}\n", encoding="utf-8")

    def _make(self, thread, purpose="an experiment"):
        made = REGISTRY.call(
            "make_sandbox",
            {
                "purpose": purpose,
                "data": [str(self.data / "rows.jsonl")],
                "egress": False,
            },
            actor="user",
            thread_id=thread,
            approved=True,
        )
        self.assertTrue(made.get("ok", True), made)
        return made["name"]

    def _listing(self, thread):
        reply = REGISTRY.call("list_sandboxes", {}, actor="user", thread_id=thread)
        self.assertTrue(reply["ok"], reply)
        return reply

    def test_a_sandbox_records_the_project_it_was_made_in(self):
        name = self._make(self.first)
        self.assertEqual(
            sandbox.read_manifest(name)["project_id"], self.first_project["id"]
        )

    def test_one_project_does_not_see_anothers(self):
        mine = self._make(self.first, "mine")
        theirs = self._make(self.second, "theirs")

        self.assertEqual(
            [row["name"] for row in self._listing(self.first)["sandboxes"]], [mine]
        )
        self.assertEqual(
            [row["name"] for row in self._listing(self.second)["sandboxes"]], [theirs]
        )

    def test_the_directory_layout_did_not_move(self):
        """THE COMPATIBILITY THIS WHOLE APPROACH EXISTS FOR, asserted.

        `tests/test_a_sandbox_is_disposable.py` pins a sandbox at exactly two
        levels under `runs_root_for()`. If that ever stops holding, every
        sandbox on somebody's disk is unreachable through `sandbox_path`'s
        parent guard and undeletable through `destroy` - which is why the
        project went into the manifest instead of into the path.
        """
        from pathlib import Path
        from app import jobspec

        name = self._make(self.first)
        where = Path(sandbox.read_manifest(name)["path"])
        self.assertEqual(
            where.parent.parent.resolve(), jobspec.runs_root_for().resolve()
        )

    def test_a_call_from_no_conversation_sees_everything(self):
        """Narrowing on a question nobody asked would hide real work."""
        self._make(self.first)
        self._make(self.second)
        self.assertEqual(len(sandbox.every()), 2)
        reply = REGISTRY.call("list_sandboxes", {}, actor="user")
        self.assertEqual(reply["count"], 2)
        self.assertIn("No conversation asked", reply["scope_note"])


class ASandboxThatPredatesTheFieldIsNotLostTest(unittest.TestCase):
    """The case that makes this safe on a machine that already has sandboxes."""

    def setUp(self):
        self.root = support.sandbox(self)
        rows = support.conversations(2)
        self.first = int(rows[0]["id"])
        self.second = int(rows[1]["id"])
        self.data = self.root / "data"
        self.data.mkdir()
        (self.data / "rows.jsonl").write_text("{}\n", encoding="utf-8")

    def _an_old_sandbox(self) -> str:
        """One made today, then aged by removing the field it predates."""
        made = REGISTRY.call(
            "make_sandbox",
            {
                "purpose": "made before sandboxes recorded a project",
                "data": [str(self.data / "rows.jsonl")],
                "egress": False,
            },
            actor="user",
            thread_id=self.first,
            approved=True,
        )
        name = made["name"]
        path = sandbox.sandbox_path(name) / "sandbox.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest.pop("project_id", None)
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return name

    def test_it_shows_in_every_project(self):
        """It is real data in a real directory. A filter it predates must not be
        the thing that loses it - the person who made it would see an empty
        list, conclude it was gone, and make a second one."""
        old = self._an_old_sandbox()
        for thread in (self.first, self.second):
            with self.subTest(thread=thread):
                reply = REGISTRY.call(
                    "list_sandboxes", {}, actor="user", thread_id=thread
                )
                self.assertIn(old, [row["name"] for row in reply["sandboxes"]])

    def test_the_listing_says_that_is_what_it_is_doing(self):
        """A filtered listing that looked complete is how somebody concludes an
        experiment is gone."""
        self._an_old_sandbox()
        note = REGISTRY.call(
            "list_sandboxes", {}, actor="user", thread_id=self.first
        )["scope_note"]
        self.assertIn("before sandboxes recorded a project", note)
        self.assertIn("still on disk", note)


class TheFilterIsAPropertyRatherThanAQueryTest(unittest.TestCase):
    """`belongs_to` is one rule in one place, so the callers cannot drift."""

    def test_no_project_asked_admits_everything(self):
        self.assertTrue(sandbox.belongs_to({"project_id": 7}, None))
        self.assertTrue(sandbox.belongs_to({}, None))

    def test_a_sandbox_with_no_project_is_admitted_by_every_project(self):
        self.assertTrue(sandbox.belongs_to({"project_id": None}, 1))
        self.assertTrue(sandbox.belongs_to({}, 2))

    def test_two_named_projects_have_to_match(self):
        self.assertTrue(sandbox.belongs_to({"project_id": 3}, 3))
        self.assertFalse(sandbox.belongs_to({"project_id": 3}, 4))

    def test_a_string_id_still_matches_its_number(self):
        """Manifests are JSON somebody may have edited; `1` and `"1"` are the
        same project and a filter that disagreed would hide a directory."""
        self.assertTrue(sandbox.belongs_to({"project_id": "5"}, 5))


class AFailedLookupWidensRatherThanNarrowsTest(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)

    def test_a_thread_that_is_not_there_scopes_to_nothing_and_shows_all(self):
        """The direction matters. A listing that could not work out which
        project it was in must show everything: the alternative is an empty list
        from a failed lookup, which reads exactly like "your work is gone"."""

        class _Ghost:
            thread_id = 999999

        self.assertIsNone(sandbox._project_of(_Ghost()))

    def test_no_instrument_at_all_is_no_project(self):
        self.assertIsNone(sandbox._project_of(None))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
