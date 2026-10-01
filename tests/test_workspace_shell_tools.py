"""AU4: free-text sandbox / project shell tools."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402
from app import autonomy, db, events  # noqa: E402
from app.tools import REGISTRY, sandbox as sandbox_tools, workspace_shell  # noqa: E402


class WorkspaceShellToolsTest(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)

    def test_tools_are_registered_and_classified(self) -> None:
        self.assertIn("run_sandbox_command", REGISTRY.names())
        self.assertIn("run_project_command", REGISTRY.names())
        self.assertTrue(autonomy.may_run("write", "run_sandbox_command"))
        self.assertFalse(autonomy.may_run("write", "run_project_command"))
        self.assertTrue(autonomy.may_run("full", "run_project_command"))
        self.assertTrue(autonomy.may_run("full", "run_sandbox_command"))

    def test_sandbox_command_echoes(self) -> None:
        made = sandbox_tools.create(name="shell-box", purpose="au4 test")
        self.assertTrue(made.get("ok"))
        out = workspace_shell.run_sandbox_command(
            "shell-box",
            "echo hello-au4",
            timeout_seconds=30,
        )
        self.assertTrue(out.get("ok"), out)
        self.assertIn("hello-au4", out.get("stdout") or "")

    def test_a_project_with_no_folder_runs_in_its_workspace(self) -> None:
        """New threads get a default project with no root_path. The window
        already shows them a folder for it; the shell runs there rather than
        refusing - a fresh install's first task could run nothing before."""
        from app.facade import sessions

        tid = events.create_thread("shell project")["id"]
        project = db.get_project(int(events.get_thread(tid)["project_id"]))
        self.assertFalse(project.get("root_path"))

        out = workspace_shell.run_project_command(
            "echo in-the-workspace", thread_id=tid, timeout_seconds=30
        )

        self.assertTrue(out.get("ok"), out)
        self.assertIn("in-the-workspace", out.get("stdout") or "")
        self.assertEqual(
            Path(out["cwd"]).resolve(), Path(sessions.directory_of(project)).resolve()
        )

    def test_project_command_runs_in_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = db.create_project("shell-proj")
            db.set_project_root(int(project["id"]), str(root))
            tid = events.create_thread(
                "shell ok", project_id=int(project["id"])
            )["id"]
            out = workspace_shell.run_project_command(
                "echo project-ok",
                thread_id=tid,
                timeout_seconds=30,
            )
            self.assertTrue(out.get("ok"), out)
            self.assertIn("project-ok", out.get("stdout") or "")
            self.assertEqual(Path(out["cwd"]).resolve(), root.resolve())

    def test_the_shell_is_wide(self) -> None:
        """Max, 2026-09-17: "give it as much shell power as it wants to have."
        A baseline of another local model does not fit in two minutes."""
        self.assertGreaterEqual(workspace_shell.DEFAULT_TIMEOUT, 600)
        self.assertGreaterEqual(workspace_shell.MAX_TIMEOUT, 3600)
        self.assertEqual(workspace_shell._bound(None), workspace_shell.DEFAULT_TIMEOUT)
        self.assertEqual(workspace_shell._bound(99999), workspace_shell.MAX_TIMEOUT)

    @unittest.skipUnless(sys.platform == "win32", "PowerShell 5.1 has no &&")
    def test_and_and_means_the_same_thing_on_windows(self) -> None:
        """Thread 75's first shell call died on `cd x && python ...`: exit 1,
        which the run then counted as a refusal. Translated, not refused."""
        # PowerShell named: with Git Bash present the default is bash (H-shell),
        # and this is about what PowerShell does with `&&`.
        import os
        from unittest import mock

        self.enterContext(mock.patch.dict(os.environ, {"MLH_PROJECT_SHELL": "powershell"}))
        argv = workspace_shell._shell_argv("echo one && echo two")
        self.assertNotIn("&&", argv[-1])
        self.assertIn("if ($?)", argv[-1])
        with tempfile.TemporaryDirectory() as tmp:
            project = db.create_project("shell-and")
            db.set_project_root(int(project["id"]), tmp)
            tid = events.create_thread("and", project_id=int(project["id"]))["id"]
            out = workspace_shell.run_project_command("echo one && echo two", thread_id=tid, timeout_seconds=30)
            self.assertTrue(out.get("ok"), out)
            self.assertIn("two", out.get("stdout") or "")

    def test_empty_command_refused(self) -> None:
        out = workspace_shell.run_sandbox_command("x", "  ")
        self.assertEqual(out.get("error"), "empty_command")


if __name__ == "__main__":
    unittest.main()
