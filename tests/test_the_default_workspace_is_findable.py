"""A folder-less project's workspace is somewhere a person can find it.

Before this rule every folder-less project worked in `<db dir>/workspaces/
project-N` - for the installed app, under AppData, where nobody looks for the
files a conversation made. Now (`app/facade/sessions.py::workspace_root`):

1. `MLH_WORKSPACE_ROOT` wins;
2. the default per-user database means `~/Documents/ML Harness/<project>`;
3. anything else - a test sandbox, a custom database - stays beside the
   database.

Rule 3 is what keeps this suite out of the real home directory, so it is
tested first and on its own. Rule 2 is tested WITHOUT touching the default
database: `workspace_root` reads the path and never opens it, and `Path.home`
is pointed at the sandbox.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from app import db, paths
from app.facade import sessions

import support


class TheWorkspaceRuleTest(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("MLH_WORKSPACE_ROOT", None)

    def test_under_the_test_harness_the_workspace_is_in_the_sandbox(self):
        project = db.default_project()
        folder = Path(sessions.directory_of(project))
        self.assertIn(self.root, folder.parents)
        self.assertEqual(folder, self.root / "workspaces" / f"project-{project['id']}")
        self.assertIsNone(sessions.workspace_root())
        self.assertNotIn(Path.home() / "Documents", [folder, *folder.parents])

    def test_the_environment_names_the_root(self):
        chosen = self.root / "chosen"
        os.environ["MLH_WORKSPACE_ROOT"] = str(chosen)
        project = db.create_project("Ticket triage", None)
        self.assertEqual(sessions.workspace_for(int(project["id"])), chosen / "Ticket triage")

    def test_the_default_database_means_documents_and_nothing_is_opened_or_made(self):
        home = self.root / "home"
        os.environ.pop("ML_HARNESS_DB", None)
        with mock.patch.object(db, "DB_PATH", paths.in_data_root("ml_harness.db")), mock.patch.object(
            Path, "home", return_value=home
        ):
            self.assertEqual(sessions.workspace_root(), home / "Documents" / "ML Harness")
            # A database named in the environment is not the default one,
            # even at the default path.
            os.environ["ML_HARNESS_DB"] = str(paths.in_data_root("ml_harness.db"))
            self.assertIsNone(sessions.workspace_root())
        self.assertFalse(home.exists(), "deciding the root must create nothing")

    def test_folder_names_are_safe_and_unique(self):
        os.environ["MLH_WORKSPACE_ROOT"] = str(self.root / "chosen")
        first = db.create_project("Default", None)
        second = db.create_project("default", None)
        odd = db.create_project('a/b:c*?"<>|  ', None)
        reserved = db.create_project("CON", None)
        empty = db.create_project("...", None)
        names = {int(p["id"]): sessions.workspace_for(int(p["id"])).name for p in (first, second, odd, reserved, empty)}
        self.assertEqual(names[int(first["id"])], "Default")
        self.assertEqual(names[int(second["id"])], f"default ({second['id']})")
        self.assertEqual(names[int(odd["id"])], "a-b-c------")
        self.assertEqual(names[int(reserved["id"])], f"CON ({reserved['id']})")
        self.assertEqual(names[int(empty["id"])], f"project-{empty['id']}")

    def test_an_old_workspace_with_files_stays_and_is_still_found(self):
        project = db.create_project("Keeps its files", None)
        pid = int(project["id"])
        old = sessions.legacy_workspace(pid)
        old.mkdir(parents=True)
        (old / "made-by-a-turn.csv").write_bytes(b"a,b\n")
        os.environ["MLH_WORKSPACE_ROOT"] = str(self.root / "chosen")
        self.assertEqual(sessions.workspace_for(pid), old)
        self.assertEqual(sessions.find_project(str(old))["id"], pid)
        # An empty old folder gives way to the findable one, and the old path
        # still names the project rather than becoming a new one.
        (old / "made-by-a-turn.csv").unlink()
        self.assertEqual(sessions.workspace_for(pid), self.root / "chosen" / "Keeps its files")
        self.assertEqual(sessions.find_project(str(old))["id"], pid)


if __name__ == "__main__":
    unittest.main()
