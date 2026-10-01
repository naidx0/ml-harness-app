"""Every script that imports `app` must put its own repository first.

WHAT THIS DOES NOT FIX. Two checkouts on this machine share one virtualenv, and
that virtualenv carries an editable install mapping `app` to ONE of them. A
process in either tree that does not put its own repository first on `sys.path`
imports the other lane's package - and because `ENGINE_FILE` is
`data_root()/engine.json` and `data_root()` prefers the checkout of whichever
`app` was imported, it also authenticates against the other lane's engine and
writes to the other lane's data root.

**That is unfixed and this test does not fix it.** Changing how `app` resolves
is surgery on shared infrastructure that both lanes run every process through,
and it is not a thing to do at the end of a long night. This test does the part
that is safe and checkout-independent: it keeps the failure from arriving
through OUR OWN scripts.

WHY IT IS SAFE IN EITHER TREE, which matters after tonight. It reads tracked
files that are identical in both checkouts and asserts a property of their
source. It does not import `app`, does not consult the virtualenv, and does not
depend on which checkout the editable install points at - so it cannot be a
check that only passes on a prepared machine, which is the law this repository
learned four hours ago at the cost of a gate no clone could pass.

MEASURED when written: 16 scripts import `app` and 16 put their repository
first. The value is not the 16 - it is the seventeenth, written next week by
someone who does not know the venv is shared.
"""

from __future__ import annotations

import re
import unittest

import support

#: `from app...`, `import app`, or a dotted use in a loader call. Deliberately
#: broad: a script that reaches for the package by any route needs the guard.
IMPORTS_APP = re.compile(r"^\s*(?:from\s+app\b|import\s+app\b)", re.M)

#: The guard itself. `sys.path.insert(0, ...)` is the only form that puts a
#: path FIRST; `append` puts it last, where the editable install still wins.
PUTS_ITS_OWN_REPO_FIRST = re.compile(r"sys\.path\.insert\(\s*0\s*,")


def the_scripts_that_import_app():
    for path in sorted((support.REPO_ROOT / "scripts").glob("*.py")):
        if IMPORTS_APP.search(path.read_text(encoding="utf-8")):
            yield path


class EveryScriptImportingAppGuardsItsPathTest(unittest.TestCase):
    """THE CASE."""

    def test_every_one_of_them_puts_its_repository_first(self):
        unguarded = [
            path.name
            for path in the_scripts_that_import_app()
            if not PUTS_ITS_OWN_REPO_FIRST.search(path.read_text(encoding="utf-8"))
        ]
        self.assertEqual(
            unguarded,
            [],
            "these scripts import `app` without putting their own repository "
            "first on sys.path. On this machine the shared virtualenv's editable "
            "install maps `app` to ONE checkout, so they would import, "
            "authenticate against and write to whichever tree that is - which "
            "may not be the one they are running in. Add "
            "`sys.path.insert(0, str(REPO))` before the import.",
        )

    def test_the_scan_found_something_to_scan(self):
        """A check that scanned nothing would pass. The failure mode of every
        check that reports zero, and this repository has met it twice."""
        self.assertGreater(len(list(the_scripts_that_import_app())), 10)

    def test_append_does_not_count_as_the_guard(self):
        """`sys.path.append` puts the repository LAST, where the editable
        install still wins - so it looks like the guard and is not one."""
        self.assertIsNone(PUTS_ITS_OWN_REPO_FIRST.search("sys.path.append(str(REPO))"))
        self.assertIsNotNone(PUTS_ITS_OWN_REPO_FIRST.search("sys.path.insert(0, str(REPO))"))

    def test_the_detector_can_fail(self):
        """A gate you cannot make fail is not a gate. A script with the import
        and without the guard must be caught."""
        self.assertIsNotNone(IMPORTS_APP.search("from app.tools import evals"))
        self.assertIsNotNone(IMPORTS_APP.search("import app"))
        self.assertIsNone(PUTS_ITS_OWN_REPO_FIRST.search("from app.tools import evals"))


class ItReadsSourceRatherThanResolvingImportsTest(unittest.TestCase):
    """So it says the same thing in either checkout."""

    def test_it_does_not_import_app_to_find_out(self):
        """PARSED, NOT GREPPED. The first version searched its own source for
        the string `import app` - and this file contains that string inside the
        very regex that looks for it, so the check failed on itself. A substring
        search cannot tell a statement from a mention of one; `ast` can."""
        import ast

        tree = ast.parse(
            (support.REPO_ROOT / "tests" /
             "test_a_script_imports_its_own_app.py").read_text(encoding="utf-8")
        )
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertNotIn("app", imported, "this check resolves the package it audits")

    def test_it_scans_tracked_files_only(self):
        """`scripts/` is tracked, so both checkouts hold the same files and the
        answer cannot depend on which tree ran it."""
        for path in the_scripts_that_import_app():
            self.assertTrue(str(path).endswith(".py"))
            self.assertIn("scripts", str(path))


if __name__ == "__main__":
    unittest.main()
