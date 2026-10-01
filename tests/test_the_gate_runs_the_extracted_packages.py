"""A library this repository ships must be inside the number the gate prints.

MEASURED 2026-09-07. `packages/four_asserts` held **38 tests**. All 38 passed.
**None had ever run in this gate.** The only discovery root was `tests/`, so
every green line this repository has ever printed - `4,483 of 4,483 discovered`
on the run immediately before this - was true of `tests/` and silent about a
shipped library sitting beside it.

The count was not wrong. Its denominator was not the one a reader assumes, which
is the same failure as `kept: 164`: **a count without its denominator is a
ceiling**, a law this lane wrote about somebody else's number two days ago.

THEY WERE ALSO AWKWARD TO RUN AT ALL FROM HERE. `packages/four_asserts/tests`
has no `__init__.py`, so `unittest discover` refuses it as a start directory
unless it is also the top level, and the package is not importable from the
repository root. The obvious invocation fails with `ImportError: Start directory
is not importable` and the next plausible one with `ModuleNotFoundError: No
module named 'four_asserts'`.

## WHAT THIS FILE DOES NOT CLAIM, AND THE FIRST DRAFT CLAIMED IT

It said *"the tests exist had been doing the work of the tests pass"*. **That is
a claim about the world and this can only see one gate.** `pyproject.toml` names
`Source = https://github.com/naidx0/four-asserts`: the package is published from
a DIFFERENT repository, and if that repository gates these tests then they were
running all along and only THIS gate was blind to them. Nothing in this checkout
can tell the difference, so the claim is withdrawn and the scoped one kept:
**this repository's gate did not run them, and now does.**

## AND THE THING THAT SURFACED WHILE CHECKING THAT

`packages/four_asserts` is a COPY, not the package. No submodule, no subtree, no
nested `.git` - plain vendored files with a `Source` URL pointing elsewhere. So
an edit here changes what this repository vendors and reaches nobody who runs
`pip install four-asserts`; the two can already differ, and nothing here would
notice if they did. That is not this file's to fix - it is a decision about how
the package is published - but a test that brought the copy into the gate while
leaving a reader believing the gate now covers the published package would be
worse than the gap it closed.
"""

from __future__ import annotations

import unittest

import support

gate = support.import_file("gate", support.REPO_ROOT / "scripts" / "gate.py")

PACKAGES = support.REPO_ROOT / "packages"


def the_packages_with_tests():
    if not PACKAGES.is_dir():
        return []
    return [p for p in sorted(PACKAGES.iterdir()) if (p / "tests").is_dir()]


class EveryShippedPackageIsInTheGateTest(unittest.TestCase):
    """THE CASE."""

    def test_the_gate_discovers_each_of_them(self):
        import unittest as ut

        packages = the_packages_with_tests()
        if not packages:
            self.skipTest("no packages/*/tests in this checkout")
        suites = gate.the_extracted_suites(ut.defaultTestLoader)
        self.assertEqual(
            len(suites),
            len(packages),
            f"{len(packages)} package(s) ship tests and the gate found {len(suites)}",
        )

    def test_it_finds_a_real_number_of_tests_and_not_zero(self):
        """A discovery that silently found nothing would pass a test that only
        counted suites. Zero is the answer this whole file exists to refuse."""
        import unittest as ut

        if not the_packages_with_tests():
            self.skipTest("no packages/*/tests in this checkout")
        found = sum(
            gate.how_many_tests_are_in(s)
            for s in gate.the_extracted_suites(ut.defaultTestLoader)
        )
        self.assertGreater(found, 10, "the extracted suites discovered almost nothing")

    def test_the_package_is_importable_by_its_own_name(self):
        """These are STANDALONE libraries. `four_asserts` must import the way a
        consumer would import it, because importing it any other way would test
        a thing nobody ships."""
        import unittest as ut

        if not the_packages_with_tests():
            self.skipTest("no packages/*/tests in this checkout")
        gate.the_extracted_suites(ut.defaultTestLoader)  # puts the roots on sys.path
        import four_asserts

        self.assertTrue(hasattr(four_asserts, "void_unless"))

    def test_a_package_without_tests_is_skipped_rather_than_erroring(self):
        """Not every directory under `packages/` need ship a suite, and a gate
        that crashed on one would be a gate nobody could add a package to."""
        import tempfile
        import unittest as ut
        from pathlib import Path

        real = gate.THE_EXTRACTED
        try:
            with tempfile.TemporaryDirectory() as tmp:
                (Path(tmp) / "no_tests_here").mkdir()
                gate.THE_EXTRACTED = Path(tmp)
                self.assertEqual(gate.the_extracted_suites(ut.defaultTestLoader), [])
        finally:
            gate.THE_EXTRACTED = real

    def test_a_missing_packages_directory_is_not_an_error(self):
        """A checkout without `packages/` must still be able to gate."""
        import unittest as ut
        from pathlib import Path

        real = gate.THE_EXTRACTED
        try:
            gate.THE_EXTRACTED = Path("no-such-directory-anywhere")
            self.assertEqual(gate.the_extracted_suites(ut.defaultTestLoader), [])
        finally:
            gate.THE_EXTRACTED = real


class AddingASuiteToItselfAppendsForeverTest(unittest.TestCase):
    """MEASURED, and it cost a full 37-minute gate.

    `TestSuite.addTests` iterates its argument while appending to `self`. Hand
    it the suite it is appending to and it appends forever - the list grows
    until the interpreter raises `MemoryError`.

    It is not a contrived case. The gate's own self-tests stub
    `loader.discover` to return ONE suite object for every call, so the moment
    a second discovery was added, the second call handed back the first suite
    and four tests died on the first full run. The tests were right and the
    change was wrong.
    """

    def test_a_loader_returning_one_suite_for_every_call_terminates(self):
        import unittest as ut

        one = ut.TestSuite([ut.FunctionTestCase(lambda: None)])
        real = ut.defaultTestLoader.discover
        ut.defaultTestLoader.discover = lambda *a, **k: one
        try:
            found = gate.the_extracted_suites(ut.defaultTestLoader)
            for extracted in found:
                if extracted is one:
                    continue
                one.addTests(list(extracted))
            self.assertLess(one.countTestCases(), 1000, "the suite grew without bound")
        finally:
            ut.defaultTestLoader.discover = real

    def test_the_guard_is_in_the_gate_and_not_only_here(self):
        source = (support.REPO_ROOT / "scripts" / "gate.py").read_text(encoding="utf-8")
        self.assertIn("if extracted is suite:", source)
        self.assertIn("suite.addTests(list(extracted))", source)


class TheCountedSuiteIsTheRunSuiteTest(unittest.TestCase):
    """The gate's oldest law, and adding a root must not break it.

    "Discover once, count that suite, run THAT suite, compare." The law is that
    the collection counted is the collection run - not that there may only be
    one root. The packages are folded into the same suite object BEFORE the
    count, and this asserts that ordering rather than trusting it.
    """

    def source(self):
        return (support.REPO_ROOT / "scripts" / "gate.py").read_text(encoding="utf-8")

    def test_the_packages_are_added_before_the_count(self):
        source = self.source()
        added = source.index("suite.addTests(list(extracted))")
        counted = source.index("discovered = how_many_tests_are_in(suite)")
        self.assertLess(
            added,
            counted,
            "the extracted tests are added after the count, so the gate would "
            "run more tests than it counted - which is the exact asymmetry the "
            "counting law exists to make impossible",
        )

    def test_there_is_still_one_suite_object(self):
        self.assertIn("suite.addTests(", self.source())
        self.assertNotIn("how_many_tests_are_in(base)", self.source())


if __name__ == "__main__":
    unittest.main()
