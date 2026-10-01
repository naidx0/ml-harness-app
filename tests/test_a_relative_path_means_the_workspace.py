"""A relative path in a workspace thread resolves against the workspace.

Watched before it was written, three runs in one afternoon (2026-08-31), on a
thread whose project sat on a real folder holding the person's 48-row dataset:

  run 1 — the model, never told the workspace existed, probed `.` and a
          leftover file in the ENGINE'S OWN working directory, then reported
          that stranger's three rows as "your data";
  run 2 — told the workspace in the system prompt, the model tried to copy
          the 130-character absolute path by hand and garbled it;
  run 3 — told to pass bare relative names and with the door resolving them,
          it sent `path: ui-vocab.jsonl` and everything downstream was right.

So the guarantee lives where guarantees live in this product: the registry
door. `_rehome_workspace_paths` resolves relative path arguments against the
thread's project folder, reports the rewrite on the result, and touches
nothing else — absolute paths, threads without a project, projects without a
folder all pass through exactly as sent.
"""

import os
import unittest

from app import db, events
from app.tools import registry
import support


class RelativePathsMeanTheWorkspaceTest(unittest.TestCase):
    def setUp(self):
        sandbox = support.sandbox(self)
        self.root = sandbox / "workspace"
        self.root.mkdir()
        (self.root / "data.jsonl").write_text("{}\n", encoding="utf-8")
        project = db.create_project("rehome-test", str(self.root))
        self.thread_id = events.create_thread("rehome", project_id=project["id"])["id"]
        bare = db.create_project("rehome-bare")
        self.bare_thread_id = events.create_thread("bare", project_id=bare["id"])["id"]

    def test_a_relative_path_is_resolved_against_the_project_folder(self):
        accepted = {"path": "data.jsonl"}
        moved = registry._rehome_workspace_paths(accepted, self.thread_id)
        self.assertEqual(
            accepted["path"], os.path.normpath(str(self.root / "data.jsonl"))
        )
        self.assertEqual(moved["path"]["from"], "data.jsonl")

    def test_dot_is_the_workspace_itself(self):
        accepted = {"path": "."}
        registry._rehome_workspace_paths(accepted, self.thread_id)
        self.assertEqual(accepted["path"], os.path.normpath(str(self.root)))

    def test_an_absolute_path_passes_untouched(self):
        somewhere = os.path.abspath(os.sep + "somewhere" + os.sep + "else.jsonl")
        accepted = {"path": somewhere}
        moved = registry._rehome_workspace_paths(accepted, self.thread_id)
        self.assertEqual(accepted["path"], somewhere)
        self.assertEqual(moved, {})

    def test_a_project_without_a_folder_is_untouched(self):
        accepted = {"path": "data.jsonl"}
        moved = registry._rehome_workspace_paths(accepted, self.bare_thread_id)
        self.assertEqual(accepted["path"], "data.jsonl")
        self.assertEqual(moved, {})

    def test_no_thread_means_no_rewrite(self):
        accepted = {"path": "data.jsonl"}
        moved = registry._rehome_workspace_paths(accepted, None)
        self.assertEqual(accepted["path"], "data.jsonl")
        self.assertEqual(moved, {})

    def test_a_name_that_ends_in_path_is_a_path_too(self):
        """The workspace note promises relative paths resolve against the
        folder; a fixed list of ten names did not keep it for `corpus_path`."""
        accepted = {"corpus_path": "data.jsonl", "output_dir": "out"}
        moved = registry._rehome_workspace_paths(accepted, self.thread_id)
        self.assertEqual(set(moved), {"corpus_path", "output_dir"})
        self.assertTrue(accepted["corpus_path"].startswith(str(self.root)))

    def test_a_path_that_climbs_out_of_the_workspace_says_so(self):
        """'..' resolves against the workspace and leaves it. Allowed - the
        folder next door is a real place - but the report must say the
        result is outside, not read as 'inside your project'."""
        accepted = {"path": "../elsewhere.jsonl"}
        moved = registry._rehome_workspace_paths(accepted, self.thread_id)
        self.assertTrue(moved["path"].get("outside_workspace"))
        inside = registry._rehome_workspace_paths({"path": "data.jsonl"}, self.thread_id)
        self.assertNotIn("outside_workspace", inside["path"])

    @unittest.skipUnless(
        os.name == "nt",
        "a drive-relative path is a Windows construct: on posix `C:data.jsonl` "
        "is an ordinary filename and rehoming it against the workspace is the "
        "correct answer, so there is nothing to assert here",
    )
    def test_a_drive_relative_path_passes_untouched_and_unreported(self):
        accepted = {"path": "C:data.jsonl"}
        moved = registry._rehome_workspace_paths(accepted, self.thread_id)
        self.assertEqual(accepted["path"], "C:data.jsonl")
        self.assertEqual(moved, {})

    def test_only_declared_path_arguments_are_considered(self):
        """A rewrite that guessed which arguments are paths would one day
        rewrite a model name. The set is explicit and `repo_id` is not in it."""
        accepted = {"repo_id": "org/model-name"}
        moved = registry._rehome_workspace_paths(accepted, self.thread_id)
        self.assertEqual(accepted["repo_id"], "org/model-name")
        self.assertEqual(moved, {})


if __name__ == "__main__":
    unittest.main()
