"""A stranger who starts this product can stop it.

## The lost moment, found by walking it 2026-09-05

A clean clone, `python -m pip install -e .`, then `.\\start.ps1` exactly as the
README says. The engine starts DETACHED and prints its pid — and nothing
anywhere told a person how to stop it. The README's flag list carried
`--status`, `--no-ui`, `--rotate-token`, `--port`, `--ui-port` and
`--foreground`. `mlh` offered only `doctor`. The documented way out of a started
product was to find the pid yourself and kill it.

That is a small defect and a corrosive one: a launcher that starts something it
will not stop is a launcher a person stops trusting about everything else.

## What is asserted here

The three states a stop can meet, each with the sentence it returns, because a
stop that lied about any of them would be worse than no stop:

* nothing on the port — say so, exit 0, terminate nothing;
* something on the port that is not ours — refuse, exit 2, terminate nothing;
* ours — stop that one pid and say which.

The termination itself is `replace_engine`'s, unchanged, and that is the point:
it already carries the two lessons the launcher exists for — terminate ONE pid
and never a name, and prove the PORT closed rather than trusting that a dead pid
means a free socket. A `--stop` that killed by name would be shorter and would
also kill the job runner, the suite and every other lane on the machine.
"""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest import mock

import support

launch = support.import_file(
    "mlh_launch", support.REPO_ROOT / "scripts" / "launch.py"
)


def a_probe(state: str, pid: int | None = 4812):
    return launch.Probe(state, 8095, payload={"engine": {"engine_id": "abc123"}})


class TheThreeStatesAStopCanMeetTest(unittest.TestCase):
    def stop(self, probe):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(launch, "probe_engine", return_value=probe):
            with redirect_stdout(out), redirect_stderr(err):
                code = launch.stop_engine(8095, "fingerprint")
        return code, out.getvalue(), err.getvalue()

    def test_an_empty_port_says_so_and_terminates_nothing(self):
        """`free`, not `closed`. The first version guessed the state name and
        printed 'something is listening on 8099 and it is not this product
        (free)' at an empty port - a sentence contradicting itself inside its
        own parentheses. Caught by running it."""
        with mock.patch.object(launch, "replace_engine") as never:
            code, out, _ = self.stop(a_probe("free"))
        never.assert_not_called()
        self.assertEqual(code, 0)
        self.assertIn("nothing is listening on 8095", out)
        self.assertIn("Nothing to stop", out)

    def test_a_foreign_process_is_refused_and_not_terminated(self):
        """Someone else's server on our port is THEIRS. A launcher that killed
        it would be the name-based kill this file exists to prevent, wearing a
        port number instead of a process name."""
        with mock.patch.object(launch, "replace_engine") as never:
            code, _, err = self.stop(a_probe("foreign"))
        never.assert_not_called()
        self.assertEqual(code, 2)
        self.assertIn("not this product", err)
        self.assertIn("Nothing has been terminated", err)

    def test_our_engine_is_stopped_and_the_sentence_names_it(self):
        with mock.patch.object(
            launch, "replace_engine",
            return_value="stopped the engine on 8095 (pid 4812, engine abc123)",
        ) as stopped:
            code, out, _ = self.stop(a_probe("ours-current"))
        stopped.assert_called_once()
        self.assertEqual(code, 0)
        self.assertIn("pid 4812", out)

    def test_a_stale_engine_of_ours_is_still_ours_to_stop(self):
        """`ours-stale` is our engine running older code. Refusing to stop it
        would leave the one process a person most wants gone."""
        with mock.patch.object(
            launch, "replace_engine", return_value="stopped it"
        ) as stopped:
            code, _, _ = self.stop(a_probe("ours-stale"))
        stopped.assert_called_once()
        self.assertEqual(code, 0)


class TheLauncherAdvertisesTheStopTest(unittest.TestCase):
    def test_the_flag_exists_and_says_what_it_stops(self):
        args = launch.parse_args(["--stop"])
        self.assertTrue(args.stop)

    def test_it_is_off_unless_asked_for(self):
        self.assertFalse(launch.parse_args([]).stop)

    def test_the_readme_tells_a_stranger_how_to_stop(self):
        """THE ACTUAL DEFECT. The code could stop and the person could not find
        out how. A flag nobody is told about is not a remedy."""
        readme = (support.REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("--stop", readme)


if __name__ == "__main__":
    unittest.main()
