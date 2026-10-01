"""31 unconditional reads of the first ledger, counted so the number can only fall.

## What this is holding, and what it deliberately is not

`docs/PHASES.md` has carried this since capability blocks shipped:

> **Nine files still call `default_spec()` unconditionally.** Per-thread ledger
> landed in migration `v011` and most tools take `ledger` through injection, but
> an AST sweep on 2026-08-26 still found **9 files** in `app/tools/` with bare
> `default_spec()` calls. Each is a place where an AI-thread tool could read the
> wrong ledger if called outside the conductor path.

**A debt with a number that nobody recomputes is a debt that grows.** The 2026-08-26
sweep looked at `app/tools/` only; over the whole package the figure is 31 calls
in 13 files, and one of them was live on an HTTP route - see
`tests/test_a_card_is_not_offered_in_the_wrong_domain.py`.

This file does not assert that the calls are wrong. **Most of them are not.**
The shape almost everywhere is

    def eval_set_floor(spec: diagnosis.Spec | None = None) -> ...:
        current = spec or diagnosis.default_spec()

which is a helper that TAKES a ledger and falls back when handed none. That is
the right signature; the risk is in the callers, and the risk is real only where
a caller had a ledger and dropped it.

So what is pinned here is the CENSUS, per file, as a ceiling. Removing a call is
free. Adding one turns this file red and asks for a sentence about which ledger
the new site reads and why that is the right one - which is the whole of what
this debt needs while it is open.

## The three files whose calls are argued rather than owed

Named here, and their counts are pinned exactly like the rest, so a fourth call
appearing in one of them is as loud as a call appearing anywhere else:

* **`app/tools/evidence.py`** (3). `spec()` documents its own default as the
  debt in its docstring - *"the parameter is the whole point and the default is
  the debt"* - and names its two honest callers: registration, which happens at
  import before any conversation exists, and the standing walk over nothing,
  which has no thread. `ledger_for_thread` falls back for a thread id that names
  nothing, which is a different question with the same answer.
* **`app/tools/propose.py`** (12). `the_ledger_these_tables_are_keyed_to`
  states it outright: `PROPOSERS`, `COVERAGE` and `NOT_COVERED` are keyed by the
  first ledger's outcome ids, that is a fact about the module rather than about
  a thread, and the honest way to hold it is a function that says so. It goes
  away with `contract.builds`.
* **`app/asking.py`** (1). `_spec` is the module's single door and its docstring
  now records the measurement rather than the old claim - the sentence *"the
  product has one ledger"* stopped being true at `v011`, and
  `app/main.py::next_step_ep` refuses at the boundary rather than serving a card
  from the wrong tree.

## Why a ceiling per file and not one total

A total lets a call move from a file where it is argued to one where it is not,
and stay green. The per-file map is what makes the interesting event - *this
module started reading the default ledger* - the thing that fails.
"""

from __future__ import annotations

import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Per file, the number of `default_spec()` calls taking no argument, MEASURED
#: on 2026-08-27 by the sweep in this file. A CEILING: fewer is a pass, more is
#: a failure that asks for a sentence.
THE_CENSUS: dict[str, int] = {
    "app/asking.py": 1,
    "app/build.py": 1,
    "app/diagnosis.py": 1,
    "app/main.py": 1,
    "app/tools/agents.py": 1,
    "app/tools/classical.py": 4,
    "app/tools/context.py": 1,
    "app/tools/data.py": 1,
    "app/tools/datawork.py": 1,
    "app/tools/evals.py": 1,
    "app/tools/evidence.py": 3,
    "app/tools/next_moves.py": 3,
    "app/tools/propose.py": 12,
}

#: The three whose calls carry a written argument. Read by the test that
#: requires each of them to still carry one, so deleting the argument and
#: keeping the call is caught.
ARGUED = {
    "app/tools/evidence.py": "THE DEFAULT IS THE DEBT",
    "app/tools/propose.py": "the_ledger_these_tables_are_keyed_to",
    "app/asking.py": "IT STOPPED BEING TRUE AT MIGRATION v011",
}


def _calls_in(path: pathlib.Path) -> list[int]:
    """Line numbers of every `default_spec()` call that passes no argument."""
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        name = (
            function.attr
            if isinstance(function, ast.Attribute)
            else getattr(function, "id", None)
        )
        if name == "default_spec" and not node.args and not node.keywords:
            found.append(node.lineno)
    return found


def _sweep() -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for path in sorted((ROOT / "app").rglob("*.py")):
        lines = _calls_in(path)
        if lines:
            # `.as_posix()` and not `str()`: THE_CENSUS above is keyed with
            # forward slashes, and on Windows `str()` yields a path separated
            # by \ , so every key missed and this test reported all 13
            # files as "found 0" and as newly-offending at the same time.
            found[path.relative_to(ROOT).as_posix()] = lines
    return found


class TheCensusIsPinnedTest(unittest.TestCase):
    def setUp(self):
        self.found = _sweep()

    def test_the_sweep_finds_something(self):
        """A sweep that found nothing would pass this file forever. It is also
        the day this debt is paid, and on that day this file is deleted rather
        than left standing green."""
        self.assertGreater(len(self.found), 0)
        self.assertGreaterEqual(sum(len(v) for v in self.found.values()), 20)

    def test_no_file_reads_the_default_ledger_more_often_than_it_did(self):
        grown = {
            path: f"{len(lines)} calls, was {THE_CENSUS.get(path, 0)}, at {lines}"
            for path, lines in self.found.items()
            if len(lines) > THE_CENSUS.get(path, 0)
        }
        self.assertEqual(
            {},
            grown,
            "these files read the first ledger unconditionally more often than "
            "they did when this was last measured. `default_spec()` with no "
            "argument is the ML ledger whatever conversation is running - see "
            "docs/PHASES.md, and app/tools/evidence.py::spec for the shape a "
            "helper should have instead. If the new call is right, say which "
            "ledger it reads and why, and raise the number here in the same "
            "change.",
        )

    def test_no_new_file_starts_reading_it(self):
        """The event this file most wants to catch. A module that never touched
        the default ledger and now does is a new coupling, and it is invisible
        in a total."""
        fresh = sorted(set(self.found) - set(THE_CENSUS))
        self.assertEqual(
            [],
            fresh,
            "these modules did not read the first ledger unconditionally and "
            "now do",
        )

    def test_the_pinned_numbers_are_not_stale_upwards(self):
        """The other direction, which keeps the ceiling honest. A file whose
        count FELL should have its number lowered in the same change, or the
        ceiling quietly stops binding."""
        slack = {
            path: f"pinned {pinned}, found {len(self.found.get(path, []))}"
            for path, pinned in THE_CENSUS.items()
            if len(self.found.get(path, [])) < pinned
        }
        self.assertEqual(
            {},
            slack,
            "these files now read the default ledger FEWER times than this "
            "census records, which is good work with a stale ceiling behind "
            "it. Lower the number so it still binds.",
        )


class TheArguedOnesStillCarryTheirArgumentTest(unittest.TestCase):
    """Three files are allowed to read the default ledger and each says why.

    A count on its own cannot tell "argued" from "nobody has looked", so the
    sentence is asserted too - deleting the paragraph and keeping the call is
    exactly how an argued exception becomes an unexamined one.
    """

    def test_each_argued_file_still_states_its_reason(self):
        for path, phrase in ARGUED.items():
            with self.subTest(path=path):
                source = (ROOT / path).read_text(encoding="utf-8")
                self.assertIn(
                    phrase,
                    source,
                    f"{path} reads the default ledger and no longer carries the "
                    "written reason it is allowed to. Either restore the "
                    "argument or thread a ledger through.",
                )

    def test_every_argued_file_is_in_the_census(self):
        for path in ARGUED:
            self.assertIn(path, THE_CENSUS)


class TheHelperShapeIsTheOneToCopyTest(unittest.TestCase):
    """What a call site should look like, asserted against the ones that do.

    Almost every site in the census is inside a helper that TAKES a ledger and
    falls back - `spec or diagnosis.default_spec()` - which is the right
    signature. This checks that the shape is real and widespread rather than
    something this file's docstring asserts about code nobody looked at.
    """

    #: Files where every call is inside a function that offers a ledger
    #: parameter. Measured, not chosen.
    def _fallbacks(self, path: str) -> tuple[int, int]:
        source = (ROOT / path).read_text(encoding="utf-8")
        tree = ast.parse(source, path)
        offering = total = 0
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            calls = _calls_in_node(node)
            if not calls:
                continue
            total += len(calls)
            names = {a.arg for a in node.args.args + node.args.kwonlyargs}
            if names & {"spec", "ledger"}:
                offering += len(calls)
        return offering, total

    def test_most_call_sites_already_take_a_ledger_and_merely_fall_back(self):
        offering = total = 0
        for path in THE_CENSUS:
            mine, all_of_them = self._fallbacks(path)
            offering += mine
            total += all_of_them
        self.assertGreater(total, 0)
        self.assertGreaterEqual(
            offering / total,
            0.5,
            f"only {offering} of {total} calls are inside a function that takes "
            "a ledger. The debt is supposed to be about CALLERS not passing "
            "one, and if most helpers no longer offer the parameter at all, "
            "this file is measuring the wrong thing.",
        )


def _calls_in_node(node: ast.AST) -> list[int]:
    found = []
    for inner in ast.walk(node):
        if not isinstance(inner, ast.Call):
            continue
        function = inner.func
        name = (
            function.attr
            if isinstance(function, ast.Attribute)
            else getattr(function, "id", None)
        )
        if name == "default_spec" and not inner.args and not inner.keywords:
            found.append(inner.lineno)
    return found


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
