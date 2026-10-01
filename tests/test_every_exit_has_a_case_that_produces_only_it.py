"""Each exit code is produced by a case that produces only that exit.

## The rule, and it is narrower than "test every branch"

**A probe that trips two branches at once proves neither in isolation.** A
neighbouring lane split a gate's failure verdict into two labels and proved both
fire with one probe carrying one of each - and that proof is what hid the bug.
The success test read `bad.length === 0` and never looked at the second list, so
a case that populated only the second left the first empty and the gate printed
*all resolve* and exited 0. **The class built to stop those being mislabelled
made them invisible**, which is worse: a wrong label gets argued with and a
silent pass does not.

## What that found here, and it is the one with money on it

`rent_an_hour.py` carried exits {0, 2, 3}. Run with the row file absent:

| case | exit was | says |
|---|---|---|
| `--plan`, rows missing | **0** | UNKNOWN |
| `--ceiling 5.00`, rows missing | **3** | UNKNOWN |

0 is the code for *a plan that counted*, and 3 for *a ceiling accepted*. So a run
that **could not count the workload at all** returned the same codes as a fully
priced one, and `unmeasurable renders unknown` lived in the PROSE and not in the
EXIT CODE - which is the thing a caller acts on.

The second row is the money case: **it accepted a ceiling against a workload it
could not count**, and mentioned that only in a paragraph. A ceiling is named
against a number; with no number there is nothing to name it against, and that
has to be a refusal rather than a caveat. `CANNOT_COUNT` is now its own exit, and
a distinct one - folding it into `CEILING_TOO_LOW` would leave a caller unable to
tell "your budget is short" from "I do not know what it costs".

`the_vendored_copy.py` was checked the same way and was already clean: all three
of its exits have an isolating case, including the unreachable-upstream branch.
"""

from __future__ import annotations

import io
import tempfile
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import support

rental = support.import_file(
    "rent_an_hour", support.REPO_ROOT / "scripts" / "rent_an_hour.py"
)
vendored = support.import_file(
    "the_vendored_copy", support.REPO_ROOT / "scripts" / "the_vendored_copy.py"
)

#: Captured BEFORE anything is patched. A stub that calls the name it is
#: replacing recurses until the interpreter stops it - which is what the first
#: version of this harness did.
THE_REAL_OURS = vendored.ours
THE_REAL_RECORD = vendored.the_record

A_PATH_THAT_IS_NOT_THERE = Path("no-such-row-file-anywhere.jsonl")


def run(module, argv, **patch):
    """Call `main` with named attributes replaced, and give back (exit, output)."""
    saved = {name: getattr(module, name) for name in patch}
    for name, value in patch.items():
        setattr(module, name, value)
    out, err = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = module.main(argv)
    finally:
        for name, value in saved.items():
            setattr(module, name, value)
    return code, out.getvalue() + err.getvalue()


class TheRentalCannotPriceWhatItCannotCountTest(unittest.TestCase):
    """THE CASE, and it is the one a ceiling gets named against."""

    def test_a_missing_row_file_refuses_rather_than_planning(self):
        code, said = run(rental, ["--plan"], THE_ROWS=A_PATH_THAT_IS_NOT_THERE)
        self.assertEqual(code, rental.CANNOT_COUNT)
        self.assertIn("cannot be counted", said)

    def test_a_missing_row_file_refuses_rather_than_ACCEPTING_A_CEILING(self):
        """THE MONEY CASE. This returned 3 - *ceiling accepted* - about a
        workload it could not count."""
        code, said = run(rental, ["--ceiling", "5.00"], THE_ROWS=A_PATH_THAT_IS_NOT_THERE)
        self.assertEqual(code, rental.CANNOT_COUNT)
        self.assertNotEqual(code, rental.CEILING_ACCEPTED)
        self.assertIn("cannot be priced", said)

    def test_it_refuses_before_it_judges_the_ceiling(self):
        """Cannot-count beats ceiling-too-low, because "your budget is short"
        is a claim about a price nobody has."""
        code, _ = run(rental, ["--ceiling", "0.10"], THE_ROWS=A_PATH_THAT_IS_NOT_THERE)
        self.assertEqual(code, rental.CANNOT_COUNT)

    def test_the_code_is_distinct_from_every_other(self):
        codes = {rental.PLAN_ONLY, rental.CEILING_TOO_LOW,
                 rental.CEILING_ACCEPTED, rental.CANNOT_COUNT}
        self.assertEqual(len(codes), 4, "two of the rental's exits share a number")


#: Fixture directories to remove when the module is done. They live INSIDE the
#: repository because `rent_an_hour` reports the row file relative to the repo,
#: and a path outside it raises rather than printing - which is how the first
#: version of this fixture turned four failures into four errors.
_SCRATCH: list[Path] = []


def a_row_file(rows: int = 88) -> Path:
    """A rows file that EXISTS, for the four exits that need one.

    THESE FOUR TESTS DEPENDED ON AN ARTEFACT THAT DOES NOT TRAVEL. `THE_ROWS`
    is `runs/judge-sentinel-n/results.jsonl`, `runs/` is gitignored, and a
    gitignored file lives in a working TREE - so the checkout that ran the
    judge pass has it and every other checkout does not. All four asserted
    PLAN_ONLY or a ceiling exit while the module correctly returned
    CANNOT_COUNT, and they were green in one tree and red in another with no
    difference in the code. Measured 2026-09-09.

    The sibling case above already passes `THE_ROWS=` to force the absent
    file; this is the same mechanism pointed the other way, so an isolating
    case isolates the exit rather than the machine it runs on.
    """
    where = Path(tempfile.mkdtemp(dir=support.REPO_ROOT, prefix="mlh-rental-rows-"))
    _SCRATCH.append(where)
    rows_file = where / "results.jsonl"
    with rows_file.open("w", encoding="utf-8", newline=chr(10)) as handle:
        for n in range(rows):
            handle.write(json.dumps({"row_index": n, "answer": "x"}) + chr(10))
    return rows_file


def tearDownModule():
    import shutil
    for where in _SCRATCH:
        shutil.rmtree(where, ignore_errors=True)
    _SCRATCH.clear()

class EveryRentalExitHasAnIsolatingCaseTest(unittest.TestCase):
    """One case per exit, each producing that exit and no other."""

    def test_plan_only(self):
        self.assertEqual(run(rental, ["--plan"], THE_ROWS=a_row_file())[0],
                         rental.PLAN_ONLY)

    def test_plan_only_without_the_flag(self):
        self.assertEqual(run(rental, [], THE_ROWS=a_row_file())[0], rental.PLAN_ONLY)

    def test_ceiling_too_low(self):
        code, said = run(rental, ["--ceiling", "0.10"], THE_ROWS=a_row_file())
        self.assertEqual(code, rental.CEILING_TOO_LOW)
        self.assertIn("REFUSED", said)

    def test_ceiling_accepted(self):
        code, said = run(rental, ["--ceiling", "5.00"], THE_ROWS=a_row_file())
        self.assertEqual(code, rental.CEILING_ACCEPTED)
        self.assertIn("not written yet", said)

    def test_cannot_count(self):
        self.assertEqual(
            run(rental, ["--plan"], THE_ROWS=A_PATH_THAT_IS_NOT_THERE)[0],
            rental.CANNOT_COUNT,
        )

    def test_the_four_cases_produce_four_different_exits(self):
        """THE POINT OF THE WHOLE FILE. Four cases, four codes - if any two
        collapse, one exit has no case that produces only it."""
        #: THE THREE COUNTABLE CASES NEED A ROWS FILE THAT EXISTS, for the same
        #: reason the isolating cases above do: without one the module returns
        #: CANNOT_COUNT for all three and the set collapses to a single 4, which
        #: reads as "three exits share a number" when it means "this checkout has
        #: not run the judge pass".
        rows = a_row_file()
        got = {
            run(rental, ["--plan"], THE_ROWS=rows)[0],
            run(rental, ["--ceiling", "0.10"], THE_ROWS=rows)[0],
            run(rental, ["--ceiling", "5.00"], THE_ROWS=rows)[0],
            run(rental, ["--plan"], THE_ROWS=A_PATH_THAT_IS_NOT_THERE)[0],
        }
        self.assertEqual(len(got), 4, f"exits collapsed: {sorted(got)}")


class EveryVendorExitHasAnIsolatingCaseTest(unittest.TestCase):
    """Checked the same way, and it was already clean."""

    def test_matches_its_record(self):
        self.assertEqual(run(vendored, [])[0], 0)

    def test_a_changed_file_is_a_failure(self):
        changed = {**THE_REAL_OURS(), "README.md": "0" * 64}
        code, _ = run(vendored, [], ours=lambda: changed)
        self.assertEqual(code, 1)

    def test_a_missing_record_is_a_failure(self):
        self.assertEqual(run(vendored, [], the_record=dict)[0], 1)

    def test_an_unreachable_upstream_is_its_own_code(self):
        """UNREACHABLE IS NOT UNCHANGED, and it is not drift either - so it is
        neither 0 nor 1."""
        code, said = run(vendored, ["--upstream"], upstream_now=lambda url: None)
        self.assertEqual(code, 2)
        self.assertIn("UNKNOWN", said)

    def test_the_three_cases_produce_three_different_exits(self):
        got = {
            run(vendored, [])[0],
            run(vendored, [], the_record=dict)[0],
            run(vendored, ["--upstream"], upstream_now=lambda url: None)[0],
        }
        self.assertEqual(len(got), 3, f"exits collapsed: {sorted(got)}")


class TheSurveyIsRecordedRatherThanImpliedTest(unittest.TestCase):
    """Six scripts carry three or more distinct exits.

    ## THE FIRST VERSION OF THIS NOTE WAS WRONG ABOUT TWO OF ITS FOUR

    It listed `gate.py`, `push_if_green.py` and the two fresh-machine scripts as
    unproved. **I never checked whether coverage already existed elsewhere.**

    * **`push_if_green.py` was already proved** - `tests/test_a_push_reads_the_gates_exit_code.py`
      carries isolating cases for 0, 1, 2, 97 and 128. The note told a reader to
      do work that was done.
    * **`gate.py` is partly proved**: exit 2 has isolating cases in
      `test_a_green_run_says_what_it_could_not_check.py` (a moved tree) and
      `test_the_gate_counts_what_it_ran.py` (a refusing lock). Its exits 0 and 1
      are exercised through a stubbed `_run_the_suite`, which proves the
      passthrough and not the condition, so it stays listed.
    * **The two fresh-machine scripts really were unproved**, and now are:
      `tests/test_the_fresh_machine_scripts_exit_for_one_reason_each.py`.

    UNDERSTATING COVERAGE IS THE SAME FAULT AS OVERSTATING IT, pointed the other
    way: both are a description that does not match what is there, and both send
    a reader somewhere the tree does not support. The first draft of this file
    was careful to avoid implying coverage it lacked and careless about implying
    an absence it had not checked.
    """

    THE_UNPROVED = (
        "gate.py",
    )

    def test_those_scripts_still_exist_to_be_proved(self):
        for name in self.THE_UNPROVED:
            with self.subTest(name=name):
                self.assertTrue((support.REPO_ROOT / "scripts" / name).is_file())

    def test_they_really_do_carry_several_exits(self):
        """If one of them collapsed to a single exit, this note would be stale
        and should go rather than sit here describing a risk that is gone."""
        import re

        for name in self.THE_UNPROVED:
            with self.subTest(name=name):
                source = (support.REPO_ROOT / "scripts" / name).read_text(encoding="utf-8")
                codes = set(re.findall(r"return\s+(\d)\b", source))
                self.assertGreaterEqual(
                    len(codes), 2,
                    f"{name} no longer has several literal exits; update this note",
                )


if __name__ == "__main__":
    unittest.main()
