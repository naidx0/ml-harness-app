"""A green gate says whether it had the machine to itself.

MEASURED 2026-09-05: two full suites were running concurrently under two
different interpreters while `scripts/one_gate_at_a_time.py` reported that
nobody held the lock. **2 concurrent runners, 0 lock acquisitions.** The lock
only protects lanes that remember to wrap their run in it, and a guard that
depends on being remembered is not one — the same shape as the law it produced.

This does not refuse and does not wait. The count assertion already turns a run
that LOST tests red, which is the failure that matters, and a gate that refused
to run because a neighbour existed would block a lane on another lane's
schedule. What it does is name the neighbours, so a green result carries the
fact that it did not have the machine to itself and a reader weighing a timing
or a flake knows to look.

THE FILTER IS THE PART THAT NEEDED MEASURING. A first version matched any
process whose command line contained the pattern and reported **7 suites where
2 were real**: it caught the shell that launched the query and the PowerShell
running it, because those carry the pattern by carrying the query. The thing
being looked for is a python interpreter with the suite on its own command
line.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

#: One process line ends here. Built rather than typed: a literal
#: backslash in a fixture has changed what a test was testing five times
#: in one night on this branch, twice in this very file.
ENDS = chr(10)

#: A real Windows interpreter path, with the spaces and the quotes
#: Windows actually puts on it, assembled rather than typed.
QUOTE = chr(34)

QUOTED = '33496|' + QUOTE + 'C:/Program Files/Python/python.exe' + QUOTE + '  scripts/gate.py'

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("gate_script", REPO / "scripts" / "gate.py")
gate = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(gate)


class ItNamesOnlyRealSuitesTest(unittest.TestCase):
    def rows(self, out: str) -> list[str]:
        """Run the parser over a captured process list.

        `SimpleNamespace` rather than a class defined here: the first version
        wrote `class Done: stdout = out` inside this method, and a class body
        does not see a method's locals the way a nested function does. The test
        then reported zero rows for a real suite and I went looking in the
        product for it.
        """
        from types import SimpleNamespace
        from unittest import mock

        with mock.patch("subprocess.run", return_value=SimpleNamespace(stdout=out)):
            return gate.other_suites_running_now()

    def test_a_python_running_the_suite_is_named(self):
        # Forward slashes on purpose. Written with backslashes first, where
        # "C:\v..." is a vertical tab and the fixture stopped describing a real
        # command line — the fourth time tonight a literal backslash in file
        # content has changed what a test was testing.
        out = "31992|C:/venv/Scripts/python.exe -m unittest discover -s tests\n"
        self.assertEqual(len(self.rows(out)), 1)

    def test_the_shell_that_launched_the_query_is_not_a_suite(self):
        """The seven-for-two case. A bash or PowerShell carrying the search
        pattern is carrying the query, not running a suite.

        REWRITTEN 2026-09-05. The first version of this fixture typed Windows
        paths with literal backslashes, so `bash.exe` began with a BACKSPACE
        and this test stopped describing any real command line. It went on
        passing, because it asserts an EMPTY result and corrupted input matches
        nothing either - a negative test proving nothing, which is the family
        of defect this whole file exists to catch. Forward slashes throughout,
        and `tests/test_no_literal_backslash_eats_a_fixture.py` now fails on
        the character rather than waiting for someone to notice.
        """
        out = (
            '2857|' + QUOTE + 'C:/Program Files/Git/bin/bash.exe' + QUOTE
            + ' -c "... unittest discover ..."' + ENDS
            + '10408|powershell -NoProfile -Command "... unittest discover ..."' + ENDS
            + '2856|C:/Program Files/Git/bin/bash.exe -c "source ... unittest discover"' + ENDS
        )
        self.assertEqual(self.rows(out), [])

    def test_a_python_doing_something_else_is_not_a_suite(self):
        out = '32624|C:/venv/Scripts/python.exe -c "print(1)"' + ENDS
        self.assertEqual(self.rows(out), [])

    def test_a_gate_launched_with_no_flags_is_seen(self):
        """THE HOLE THE TIGHTENING LEFT, found 2026-09-05 by watching this
        report 0 neighbours while a gate ran three feet away.

        The executable was read as the text before the first FLAG, which finds
        it only when a flag follows. `python -m unittest discover` splits at
        ` -m` and yields `python.exe`; `python scripts/gate.py` has no flag, so
        the whole line was the "head" and it ended in `gate.py`. The invocation
        it could not see was the one this repository had just made standard
        everywhere - a filter tightened against one wrong answer and loosened
        into another.

        Re-measured after the fix, with four gates live on this machine: 0 -> 4.
        """
        out = "34660|C:/venv/Scripts/python.exe scripts/gate.py" + ENDS
        self.assertEqual(len(self.rows(out)), 1)

    def test_an_interpreter_path_with_a_space_is_one_token(self):
        """A quoted path is read to its closing quote. Splitting on the first
        space instead would make the program `"C:/Program`, which ends in
        neither python nor a suite, and a neighbour would vanish for having a
        normal install location."""
        out = QUOTED + ENDS
        self.assertEqual(len(self.rows(out)), 1)

    def test_a_non_python_program_running_a_gate_is_still_not_a_suite(self):
        """The fix must not undo the seven-for-two tightening it sits inside."""
        out = "9001|C:/tools/tail.exe scripts/gate.py" + ENDS
        self.assertEqual(self.rows(out), [])

    def test_one_process_is_one_neighbour_however_many_times_it_is_listed(self):
        """ITEM 71. The count never said distinct.

        The process table should never list a pid twice, so this has never
        fired - and a count that is only right because the input happens to be
        clean teaches nothing about the instrument. Fed the same pid twice, it
        reported two neighbours; the harness lane found the same shape in its
        own night counts on the same day.
        """
        one = "31992|C:/venv/Scripts/python.exe -m unittest discover -s tests" + ENDS
        self.assertEqual(len(self.rows(one)), 1)
        self.assertEqual(len(self.rows(one * 3)), 1, "one process counted three times")

    def test_two_real_pids_are_still_two(self):
        """The other direction: deduping must not collapse genuine neighbours."""
        out = (
            "31992|C:/venv/Scripts/python.exe -m unittest discover -s tests" + ENDS
            + "31993|C:/venv/Scripts/python.exe -m unittest discover -s tests" + ENDS
        )
        self.assertEqual(len(self.rows(out)), 2)

    def test_an_unreadable_process_list_is_not_a_failure(self):
        """A machine whose process list cannot be read gets no claim either
        way, rather than a guess."""
        from unittest import mock

        with mock.patch("subprocess.run", side_effect=OSError("no")):
            self.assertEqual(gate.other_suites_running_now(), [])

    def test_the_run_states_its_own_completion_contract_too(self):
        """The neighbour line sits beside the pending line, and neither may be
        mistaken for the verdict."""
        said = gate.what_a_finished_run_looks_like()
        self.assertFalse(said.startswith("GATE IS"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
