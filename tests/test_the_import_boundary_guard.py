"""The guard convicts a crossed import and stays silent on every other case.

Registered at `docs/judge_runs/2026-09-07-the-import-guard-prereg.md` before the
guard existed, and built on the measurement at `32319aa`: the blast radius of
the current code is empty - 16 of 16 entry points guarded here, 16 of 16 in
stage, 2 of 2 in the third worktree. Nothing is broken today. This closes the
hazard before somebody writes the 35th entry point from a subdirectory.

THE CASE THAT MATTERS IS THE RED ONE, and it is built for real rather than
mocked: a second checkout on disk, with the marker `paths.CHECKOUT_MARKER`
names, holding a script that does a bare `import app` from its own `scripts/`
directory - run with `app` resolving to THIS tree, which is what the shared
virtualenv's editable install does. That is the one configuration in the whole
measured matrix that reproduces the hazard.

**A guard that is green everywhere cannot be told from a guard that does
nothing**, and this repository has shipped one of those before: a check whose
detector could not fail, and a summary line that read `OK (skipped=1)` over a
warning saying NOT a clean bill.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import support

from app import import_boundary, paths


def a_second_checkout(root: Path, *, with_its_own_app: bool = False) -> Path:
    """A real tree on disk, marked the way `paths` decides a checkout.

    Written with the marker read from `paths.CHECKOUT_MARKER` rather than
    spelled out here. Restating a rule instead of calling it is how a lock key
    lost its `.lower()` last night, and a test that marked its fixture by a
    hand-copied path would keep passing after somebody changed the real one.
    """
    tree = root / "treeB"
    marker = tree / paths.CHECKOUT_MARKER
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("# a synthetic second checkout\n", encoding="utf-8")
    (tree / "scripts").mkdir(parents=True, exist_ok=True)
    if with_its_own_app:
        (tree / "app").mkdir(parents=True, exist_ok=True)
        (tree / "app" / "__init__.py").write_text('"""treeB\'s own app."""\n', encoding="utf-8")
    return tree


def run_from(where: Path, script: Path, **extra_env) -> subprocess.CompletedProcess:
    """Run `script` with `where` as the working directory and `app` on the path.

    `PYTHONPATH` pointing at this repository is what stands in for the editable
    install: it is the mechanism by which another tree's process gets this
    tree's package, and it reproduces the measured behaviour exactly.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(support.REPO_ROOT)
    env.pop("MLH_ALLOW_FOREIGN_APP", None)
    env.update({k: str(v) for k, v in extra_env.items()})
    return subprocess.run(
        [sys.executable, str(script)], cwd=str(where), env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )


A_BARE_IMPORT = (
    "# The 35th entry point: written from a subdirectory by somebody who does\n"
    "# not know the virtualenv is shared. No sys.path.insert.\n"
    "import app\n"
    "print('NO GUARD FIRED', app.__file__)\n"
)


class ItConvictsTheOneCaseThatReproducesTheHazardTest(unittest.TestCase):
    """RED FIRST. Nothing below is believed until this passes."""

    def test_a_bare_import_from_another_trees_subdirectory_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = a_second_checkout(Path(tmp))
            script = tree / "scripts" / "probe.py"
            script.write_text(A_BARE_IMPORT, encoding="utf-8")
            done = run_from(tree / "scripts", script)
        self.assertNotEqual(done.returncode, 0, f"the guard did not fire:\n{done.stdout}")
        self.assertIn("WRONG CHECKOUT", done.stderr)
        self.assertNotIn("NO GUARD FIRED", done.stdout)

    def test_the_message_names_both_trees_and_the_data_root_at_risk(self):
        """A conviction that does not say what it convicted is unactionable."""
        with tempfile.TemporaryDirectory() as tmp:
            tree = a_second_checkout(Path(tmp))
            script = tree / "scripts" / "probe.py"
            script.write_text(A_BARE_IMPORT, encoding="utf-8")
            said = run_from(tree / "scripts", script).stderr
        self.assertIn(str(tree), said, "it does not name the caller's tree")
        self.assertIn(str(support.REPO_ROOT), said, "it does not name the tree app came from")
        self.assertIn("data_root", said, "it does not say the data root is at risk")

    def test_it_prescribes_a_remedy_that_actually_works(self):
        """MEASURED, not asserted. The message tells the reader to put their own
        checkout first; this runs that exact remedy and confirms the import then
        resolves to the caller's own tree. A guard whose advice does not work is
        a guard that sends people in circles."""
        with tempfile.TemporaryDirectory() as tmp:
            tree = a_second_checkout(Path(tmp), with_its_own_app=True)
            script = tree / "scripts" / "fixed.py"
            script.write_text(
                "import sys\n"
                "from pathlib import Path\n"
                "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
                "import app\n"
                "print('RESOLVED', app.__file__)\n",
                encoding="utf-8",
            )
            done = run_from(tree / "scripts", script)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(str(tree), done.stdout, "the remedy did not resolve to the caller's tree")


class ItIsSilentOnEveryLegitimateCaseTest(unittest.TestCase):
    """A guard that complains where the answer is right teaches people to
    ignore it, which is worse than having none."""

    def test_this_very_process_is_not_convicted(self):
        """The suite itself imports `app` 4,444 times over. If the guard were
        wrong in the firing direction, nothing here would run at all."""
        self.assertIsNone(import_boundary.why_this_app_is_not_the_callers_app())

    def test_a_caller_in_this_tree_is_silent_wherever_it_sits(self):
        for where in (
            support.REPO_ROOT / "scripts" / "gate.py",
            support.REPO_ROOT / "tests" / "test_the_import_boundary_guard.py",
            support.REPO_ROOT / "app" / "paths.py",
        ):
            with self.subTest(where=where.name):
                self.assertIsNone(import_boundary.why_this_app_is_not_the_callers_app(where))

    def test_a_caller_that_is_not_in_any_checkout_is_not_convicted(self):
        """A notebook, a home-directory script, anything outside a tree. The
        guard cannot name the tree the caller belongs to, and A CHECK THAT
        CANNOT IDENTIFY ITS SUBJECT MUST NOT CONVICT IT."""
        with tempfile.TemporaryDirectory() as tmp:
            stray = Path(tmp) / "somebodys_notebook.py"
            stray.write_text("# not in a checkout\n", encoding="utf-8")
            self.assertIsNone(import_boundary.why_this_app_is_not_the_callers_app(stray))

    def test_an_unidentifiable_caller_is_not_convicted(self):
        """`python -c`, the REPL and a frozen entry point give no real file."""
        self.assertIsNone(import_boundary.why_this_app_is_not_the_callers_app(None) or None)
        with tempfile.TemporaryDirectory() as tmp:
            done = subprocess.run(
                [sys.executable, "-c", "import app; print('OK')"],
                cwd=tmp, env={**os.environ, "PYTHONPATH": str(support.REPO_ROOT)},
                capture_output=True, text=True, encoding="utf-8", timeout=120,
            )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("OK", done.stdout)

    def test_a_library_in_a_venv_nested_in_a_checkout_is_not_the_caller(self):
        """FOUND BY IT REFUSING TO START AN ENGINE, 2026-09-09. The one
        virtualenv on this machine lives INSIDE one of the two checkouts, so
        the tree holding `uvicorn/importer.py` is that checkout - and a
        `python -m uvicorn app.main:app` launched correctly from the OTHER
        tree, cwd set to it, `app` resolving to it, was convicted of a
        crossing it had not made.

        A library was installed into an environment. The directory it happens
        to sit in names nobody, and this file's own rule is that a check which
        cannot identify its subject must not convict it."""
        with tempfile.TemporaryDirectory() as tmp:
            tree = a_second_checkout(Path(tmp))
            library = tree / '.venv' / 'Lib' / 'site-packages' / 'uvicorn' / 'importer.py'
            library.parent.mkdir(parents=True, exist_ok=True)
            library.write_text('# a third-party library', encoding='utf-8')
            # The tree really does hold it - that is the whole trap.
            self.assertEqual(import_boundary.the_tree_holding(library), tree)
            self.assertIsNone(
                import_boundary.why_this_app_is_not_the_callers_app(library),
                'a library in a nested venv was convicted of a crossed import')

    def test_a_real_crossing_is_still_convicted_after_that(self):
        """The acquittal above must not have widened into an amnesty: the one
        case that reproduces the hazard still has to be caught."""
        with tempfile.TemporaryDirectory() as tmp:
            tree = a_second_checkout(Path(tmp))
            caller = tree / 'scripts' / 'theirs.py'
            caller.parent.mkdir(parents=True, exist_ok=True)
            caller.write_text('import app', encoding='utf-8')
            said = import_boundary.why_this_app_is_not_the_callers_app(caller)
            self.assertIsNotNone(said, 'the guard stopped convicting the real case')
            self.assertIn(str(tree), said)

    def test_a_venv_directory_name_alone_does_not_excuse_a_caller(self):
        """Only an installed-packages directory is a library. A script that
        merely lives under a folder called .venv is still somebody's code."""
        with tempfile.TemporaryDirectory() as tmp:
            tree = a_second_checkout(Path(tmp))
            caller = tree / '.venv' / 'a_script_someone_put_here.py'
            caller.parent.mkdir(parents=True, exist_ok=True)
            caller.write_text('import app', encoding='utf-8')
            self.assertIsNotNone(
                import_boundary.why_this_app_is_not_the_callers_app(caller),
                'the acquittal keyed on the wrong part of the path')

    def test_an_installed_package_is_not_a_crossed_import(self):
        """When `app` is a wheel in site-packages, `_checkout()` is None. That
        is a legitimate resolution, not another lane's tree, and the guard must
        say nothing about it."""
        real = paths._checkout
        try:
            paths._checkout = lambda: None
            with tempfile.TemporaryDirectory() as tmp:
                tree = a_second_checkout(Path(tmp))
                caller = tree / "scripts" / "x.py"
                caller.write_text("", encoding="utf-8")
                self.assertIsNone(import_boundary.why_this_app_is_not_the_callers_app(caller))
        finally:
            paths._checkout = real

    def test_the_thirty_four_entry_points_would_all_stay_silent(self):
        """Registered prediction 2, checked against the tree rather than
        recalled. Every entry point that imports `app` lives in this checkout,
        so every one of them resolves to it."""
        checked = 0
        for path in sorted((support.REPO_ROOT / "scripts").rglob("*.py")):
            if path.name == "__init__.py":
                continue
            checked += 1
            self.assertIsNone(
                import_boundary.why_this_app_is_not_the_callers_app(path),
                f"{path.name} would be convicted, and it is a legitimate entry point",
            )
        self.assertGreater(checked, 10, "the scan found nothing to scan")


class TheDetectorCanFailTest(unittest.TestCase):
    """A gate you cannot make fail is not a gate."""

    def test_two_different_trees_produce_a_sentence(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = a_second_checkout(Path(tmp))
            caller = tree / "scripts" / "x.py"
            caller.write_text("", encoding="utf-8")
            said = import_boundary.why_this_app_is_not_the_callers_app(caller)
        self.assertIsNotNone(said, "the detector cannot convict anything")
        self.assertIn("WRONG CHECKOUT", said)

    def test_the_same_tree_produces_nothing(self):
        here = support.REPO_ROOT / "scripts" / "gate.py"
        self.assertIsNone(import_boundary.why_this_app_is_not_the_callers_app(here))

    def test_refuse_raises_on_what_the_sentence_reports(self):
        """The two must agree. A reporter that finds a problem and a raiser that
        does not is the shape of a check that is on in tests and off in life."""
        with tempfile.TemporaryDirectory() as tmp:
            tree = a_second_checkout(Path(tmp))
            caller = tree / "scripts" / "x.py"
            caller.write_text("", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                import_boundary.refuse_a_foreign_app(caller)

    def test_it_finds_the_tree_by_the_marker_paths_uses(self):
        """A directory that is NOT marked is not a checkout, however much it
        looks like one - so the fixture proves the marker is what decides."""
        with tempfile.TemporaryDirectory() as tmp:
            unmarked = Path(tmp) / "looks_like_a_repo" / "scripts"
            unmarked.mkdir(parents=True)
            (unmarked / "x.py").write_text("", encoding="utf-8")
            self.assertIsNone(import_boundary.the_tree_holding(unmarked / "x.py"))


class TheOverrideIsAnOverrideAndNotADefaultTest(unittest.TestCase):
    """`paths.py` set the precedent: a person who has named something beats
    what the module infers. What it must never be is something a script sets
    for itself."""

    def test_it_silences_the_crossed_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = a_second_checkout(Path(tmp))
            script = tree / "scripts" / "probe.py"
            script.write_text(A_BARE_IMPORT, encoding="utf-8")
            done = run_from(tree / "scripts", script, MLH_ALLOW_FOREIGN_APP="1")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("NO GUARD FIRED", done.stdout)

    def test_no_shipped_file_sets_it_for_the_reader(self):
        """THE FAILURE MODE OF EVERY OVERRIDE. A guard that ships with its own
        escape hatch enabled is a guard that has been switched off in advance,
        and nobody reading the code would see it."""
        setting = []
        for path in sorted(support.REPO_ROOT.rglob("*.py")):
            parts = set(path.parts)
            if {".venv", "build", "dist", "__pycache__", "runs"} & parts:
                continue
            if path.name in {"import_boundary.py", "test_the_import_boundary_guard.py"}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if f'"{import_boundary.THE_OVERRIDE}"' in text or f"'{import_boundary.THE_OVERRIDE}'" in text:
                setting.append(str(path.relative_to(support.REPO_ROOT)))
        self.assertEqual(setting, [], "a shipped file names the guard's escape hatch")

    def test_the_override_is_read_from_the_environment_every_time(self):
        """Not captured at import, for the reason `data_root` gives: a
        module-level constant computed once is a constant a test cannot move."""
        with tempfile.TemporaryDirectory() as tmp:
            tree = a_second_checkout(Path(tmp))
            caller = tree / "scripts" / "x.py"
            caller.write_text("", encoding="utf-8")
            had = os.environ.pop(import_boundary.THE_OVERRIDE, None)
            try:
                self.assertIsNotNone(import_boundary.why_this_app_is_not_the_callers_app(caller))
                os.environ[import_boundary.THE_OVERRIDE] = "1"
                self.assertIsNone(import_boundary.why_this_app_is_not_the_callers_app(caller))
            finally:
                os.environ.pop(import_boundary.THE_OVERRIDE, None)
                if had is not None:
                    os.environ[import_boundary.THE_OVERRIDE] = had


class AGuardThatDidNotRunIsNotAGuardThatPassedTest(unittest.TestCase):
    """`app/__init__.py` lets the conviction propagate and refuses to let a
    defect in the guard take down both checkouts - but the two must not look
    alike. This repository's oldest law, and the one it broke most recently."""

    def source(self):
        return (support.REPO_ROOT / "app" / "__init__.py").read_text(encoding="utf-8")

    def test_a_conviction_propagates(self):
        self.assertIn("except RuntimeError:\n    raise", self.source())

    def test_a_defect_says_it_did_not_run(self):
        said = self.source()
        self.assertIn("DID NOT RUN", said)
        self.assertIn("not a clean bill", said)

    def test_a_defect_is_not_swallowed_silently(self):
        self.assertIn("stderr", self.source())


class ItCostsWhatWasRegisteredTest(unittest.TestCase):
    """Registered budget: under 5 ms, measured with `perf_counter`.

    `time.monotonic()` has a 15.625 ms resolution on this machine and reported
    a real 0.54 ms overhead as "0.0 ms" last week. The clock is part of the
    measurement.
    """

    def test_the_check_is_under_the_registered_budget(self):
        from time import perf_counter

        import_boundary.why_this_app_is_not_the_callers_app()  # warm the caches
        runs = 100
        started = perf_counter()
        for _ in range(runs):
            import_boundary.why_this_app_is_not_the_callers_app()
        each_ms = (perf_counter() - started) / runs * 1000
        self.assertLess(each_ms, 5.0, f"{each_ms:.3f} ms per call, budget was 5 ms")


if __name__ == "__main__":
    unittest.main()
