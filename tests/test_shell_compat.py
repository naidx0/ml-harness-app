"""H-shell: the project shell and the commands a small model actually writes.

Desktop-shortcut check, 2026-09-30 (lab/log.md "H-shell"): the iris task never
finished because MiniCPM5 wrote bash - a heredoc for every script, `which`,
`2>/dev/null`, `| head`, `| tail`, `ls -la`, `||` - and every command went to
PowerShell 5.1. 0 of 6 runs wrote the script file.

The replay guard reads the 26 distinct commands those runs sent, frozen in
tests/fixtures/shell/replay_2026-09-30.jsonl, and fails if any of them would
again reach a shell that cannot parse it under the shipped default.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402
from app import conductor, db, events  # noqa: E402
from app.tools import workspace_shell as ws  # noqa: E402

REPLAY = REPO / "tests" / "fixtures" / "shell" / "replay_2026-09-30.jsonl"

#: What PowerShell 5.1 said to the replayed commands when they failed on syntax.
POWERSHELL_SYNTAX_ERRORS = (
    "is not recognized as the name",
    "dev\\null",
    "A parameter cannot be found",
    "is not a valid statement separator",
    "Missing file specification",
)


def _replay() -> list[dict]:
    return [json.loads(line) for line in REPLAY.read_text(encoding="utf-8").splitlines() if line.strip()]


def _bashisms(command: str) -> list[str]:
    """Bash syntax PowerShell cannot run, found by the same patterns preflight uses."""
    found = [f for pattern, f, _ in ws._BASHISMS if pattern.search(command)]
    found += [n for pattern, _, n in ws._TRANSLATIONS if pattern.search(command)]
    return found


class ReplayGuardTest(unittest.TestCase):
    """The shipped default must not send the replayed commands to a shell that cannot parse them."""

    def test_the_fixture_is_the_frozen_one(self) -> None:
        rows = _replay()
        self.assertEqual(len(rows), 26)
        self.assertEqual(len({r["command"] for r in rows}), 26)

    def test_the_detector_finds_the_planted_failures(self) -> None:
        """Negative control: every command PowerShell rejected on syntax is one the scan flags."""
        rows = _replay()
        syntax_failures = [
            r for r in rows
            if r["observed_in_powershell"] == "failed"
            and any(s in r["stderr_head"] for s in POWERSHELL_SYNTAX_ERRORS)
        ]
        self.assertGreaterEqual(len(syntax_failures), 8)
        for row in syntax_failures:
            self.assertTrue(_bashisms(row["command"]), row["command"])
        # ...and a plain PowerShell-valid command is not flagged.
        self.assertEqual(_bashisms('python -c "import sklearn; print(sklearn.__version__)"'), [])

    @unittest.skipUnless(sys.platform == "win32", "the mismatch is Windows-only")
    def test_no_replayed_command_reaches_a_shell_that_cannot_parse_it(self) -> None:
        shell = ws.project_shell()
        preflight = ws.preflight_on()
        for row in _replay():
            command = row["command"]
            if shell == "bash":
                done = subprocess.run(
                    [ws._git_bash(), "--noprofile", "--norc", "-n", "-c", command],
                    capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(done.returncode, 0, (command, done.stderr))
                continue
            if not _bashisms(command):
                continue
            self.assertTrue(
                preflight,
                "PowerShell is the default and preflight is off, so this replayed "
                f"command goes to PowerShell as bash: {command[:80]!r}",
            )
            with tempfile.TemporaryDirectory() as tmp:
                checked = ws.preflight_powershell(command, Path(tmp))
            if checked.get("refused"):
                continue
            self.assertEqual(_bashisms(checked["command"]), [], checked)

    @unittest.skipUnless(sys.platform == "win32", "the no-Git fallback is Windows-only")
    def test_without_git_the_replay_is_caught_too(self) -> None:
        """A machine with no Git for Windows: PowerShell with the preflight (A6)."""
        clean = {k: v for k, v in os.environ.items() if k not in (ws.SHELL_ENV, ws.PREFLIGHT_ENV)}
        with mock.patch.dict(os.environ, clean, clear=True), mock.patch.object(ws, "_git_bash", return_value=None):
            self.assertEqual(ws.project_shell(), "powershell")
            self.assertTrue(ws.preflight_on())
            for row in _replay():
                with tempfile.TemporaryDirectory() as tmp:
                    checked = ws.preflight_powershell(row["command"], Path(tmp))
                if not checked.get("refused"):
                    self.assertEqual(_bashisms(checked["command"]), [], row["command"])

    @unittest.skipUnless(sys.platform == "win32" and ws._git_bash(), "needs Git for Windows")
    def test_git_bash_has_what_the_replay_calls(self) -> None:
        tools = "which head tail ls find cat python"
        done = subprocess.run(
            [ws._git_bash(), "--noprofile", "--norc", "-c", f"for t in {tools}; do type -P $t >/dev/null || echo MISSING $t; done"],
            capture_output=True, text=True, timeout=30,
        )
        self.assertNotIn("MISSING", done.stdout, done.stdout)


class ShellChoiceTest(unittest.TestCase):
    def test_git_bash_is_never_wsl(self) -> None:
        with mock.patch.dict(os.environ, {"MLH_GIT_BASH": "C:/Windows/System32/bash.exe"}):
            found = ws._git_bash()
        self.assertTrue(found is None or "system32" not in found.lower(), found)

    @unittest.skipUnless(sys.platform == "win32", "PowerShell is the Windows fallback")
    def test_the_flag_picks_the_shell(self) -> None:
        with mock.patch.dict(os.environ, {ws.SHELL_ENV: "powershell"}):
            self.assertEqual(ws.project_shell(), "powershell")
            self.assertEqual(ws._shell_argv("echo x")[0], "powershell")
        with mock.patch.dict(os.environ, {ws.SHELL_ENV: "bash"}), mock.patch.object(ws, "_git_bash", return_value="C:/Git/bin/bash.exe"):
            self.assertEqual(ws.project_shell(), "bash")
            self.assertEqual(ws._shell_argv("echo x"), ["C:/Git/bin/bash.exe", "--noprofile", "--norc", "-c", "echo x"])
        with mock.patch.dict(os.environ, {ws.SHELL_ENV: "bash"}), mock.patch.object(ws, "_git_bash", return_value=None):
            self.assertEqual(ws.project_shell(), "powershell")


class PreflightTest(unittest.TestCase):
    def test_a_heredoc_becomes_the_file_and_the_rest_runs(self) -> None:
        command = "cat > train.py << 'EOF'\nprint('acc', 1.0)\nEOF\npython train.py 2>/dev/null | head -5"
        with tempfile.TemporaryDirectory() as tmp:
            checked = ws.preflight_powershell(command, Path(tmp))
            self.assertEqual((Path(tmp) / "train.py").read_bytes(), b"print('acc', 1.0)\n")
        self.assertEqual(checked["command"], "python train.py 2>$null | Select-Object -First 5")
        self.assertIn("heredoc -> file written by the harness", checked["translated"])

    def test_which_head_tail_are_translated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            checked = ws.preflight_powershell("which python; pip list | tail -3", Path(tmp))
        self.assertEqual(checked["command"], "(Get-Command python).Source; pip list | Select-Object -Last 3")

    def test_what_cannot_be_translated_is_refused_with_its_form(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            checked = ws.preflight_powershell('ls -la x || echo "no"', Path(tmp))
        found = {r["found"]: r["use_instead"] for r in checked["refused"]}
        self.assertEqual(found["ls -la"], "Get-ChildItem -Force")
        self.assertIn("||", found)

    def test_clean_powershell_passes_unchanged(self) -> None:
        command = "python train.py; Get-ChildItem | Select-Object -First 3"
        with tempfile.TemporaryDirectory() as tmp:
            checked = ws.preflight_powershell(command, Path(tmp))
        self.assertEqual(checked, {"command": command, "wrote": [], "translated": []})


class ProjectVenvEnvTest(unittest.TestCase):
    def test_the_venv_is_first_and_pip_stays_inside(self) -> None:
        env = ws._with_venv({"Path": "C:/Python314", "PYTHONHOME": "x"}, "C:/p/.venv")
        first = env["Path"].split(os.pathsep)[0]
        self.assertTrue(first.replace("\\", "/").startswith("C:/p/.venv/"), first)
        self.assertEqual(env["VIRTUAL_ENV"], "C:/p/.venv")
        self.assertEqual(env["PIP_REQUIRE_VIRTUALENV"], "true")
        self.assertNotIn("PYTHONHOME", env)


class SmallTaskBriefTest(unittest.TestCase):
    def test_off_says_nothing(self) -> None:
        with mock.patch.dict(os.environ, {conductor.SHELL_BRIEF_ENV: "0"}):
            self.assertEqual(conductor._small_task_lines(), "")

    @unittest.skipUnless(sys.platform == "win32", "PowerShell is the Windows fallback")
    def test_it_follows_the_shell_by_default(self) -> None:
        """A5 (Git Bash + brief + venv) and A6 (PowerShell + preflight + brief + venv) both won."""
        clean = {k: v for k, v in os.environ.items() if k not in (conductor.SHELL_BRIEF_ENV, ws.VENV_ENV, ws.SHELL_ENV, ws.PREFLIGHT_ENV)}
        with mock.patch.dict(os.environ, clean, clear=True), mock.patch.object(ws, "_git_bash", return_value="C:/Git/bin/bash.exe"):
            self.assertEqual(ws.project_shell(), "bash")
            self.assertTrue(ws.brief_on() and ws.venv_on())
        with mock.patch.dict(os.environ, clean, clear=True), mock.patch.object(ws, "_git_bash", return_value=None):
            self.assertEqual(ws.project_shell(), "powershell")
            self.assertTrue(ws.brief_on() and ws.venv_on() and ws.preflight_on())
            self.assertIn("PowerShell", conductor._small_task_lines())
        with mock.patch.dict(os.environ, dict(clean, **{ws.PREFLIGHT_ENV: "0", ws.VENV_ENV: "0", conductor.SHELL_BRIEF_ENV: "0"}), clear=True):
            self.assertFalse(ws.brief_on() or ws.venv_on() or ws.preflight_on())

    def test_on_names_the_shell_and_the_three_steps(self) -> None:
        with mock.patch.dict(os.environ, {conductor.SHELL_BRIEF_ENV: "1"}):
            text = conductor._small_task_lines()
        self.assertIn(ws.shell_facts()["name"], text)
        self.assertIn("**Done when:**", text)
        self.assertEqual(text.count("- [ ] "), 3)
        self.assertIn("run_project_command: write train.py", text)


@unittest.skipUnless(sys.platform == "win32", "the Windows smoke")
class SmallTaskSmokeTest(unittest.TestCase):
    """The template's three steps, through the real tool, in the shipped shell.

    No model: this proves the path a small ML task takes - write a script with
    the shell's own file form, run it, read the metric - works on Windows. A
    model that follows the template cannot then fail on the shell.
    """

    def setUp(self) -> None:
        support.sandbox(self)

    def test_write_run_read(self) -> None:
        """With the project venv on, as shipped: pandas and sklearn import from it."""
        os.environ[ws.VENV_ENV] = "1"
        self.addCleanup(os.environ.pop, ws.VENV_ENV, None)
        facts = ws.shell_facts()
        script = "import sys, pandas, sklearn\nprint(sys.prefix)\nprint('test_accuracy', round(2 / 2, 3))"
        write = facts["write_file"].replace("<the script>", script)
        with tempfile.TemporaryDirectory() as tmp:
            project = db.create_project("smoke-small-task")
            db.set_project_root(int(project["id"]), tmp)
            tid = events.create_thread("smoke", project_id=int(project["id"]))["id"]
            wrote = ws.run_project_command(write, thread_id=tid, timeout_seconds=60)
            self.assertTrue(wrote.get("ok"), wrote)
            ran = ws.run_project_command(facts["run"], thread_id=tid, timeout_seconds=60)
            self.assertTrue(ran.get("ok"), ran)
            self.assertIn("test_accuracy 1.0", ran.get("stdout") or "")
            self.assertIn(".venv", ran.get("stdout") or "")


if __name__ == "__main__":
    unittest.main()
