"""Phase V's Phase A, driven: where this installation writes, and what it can run.

## The finding that ordered this milestone

`docs/THE_PLAN.md` V.0, measured off `ml_harness.egg-info/SOURCES.txt`:

    diagnosis_engine.yaml   0 hits
    ledgers                 0 hits
    model_configs           0 hits
    recipes                 0 hits

`pip install .` produced an engine that could not load its diagnosis spec, could
not compute a VRAM figure, and could not resolve a recipe. The README's `-e .`
hid all of it, because an editable install points site-packages back at the
checkout. Two of the four are closed - `app/model_configs` is declared package
data (A1a) and the ledgers are bundled by `setup.py` (A1b, decided as option b)
- and this file is about the next two steps.

## A2: the data root, and the half that matters most

`db.DB_PATH`, `security.ENGINE_FILE` and `jobspec.RUNS_ROOT` all resolved
`parents[1]` of the package, which in a wheel is **site-packages**. An installed
engine would have written its database into somebody's Python installation.

**Moving them unconditionally would have been worse than the bug.** Every person
who already has an `ml_harness.db` in their checkout would have found a fresh
empty one, with every conversation, every measured fact and every stored run
still on disk and unreachable, and nothing saying why. So `app/paths.py` takes
the shape `diagnosis._ledger_root` already established: **the checkout wins when
there is one**, and both halves are asserted below.

## A3: `sys.executable` is a lie under a freezer

`jobspec.interpreter` builds `[interpreter, entrypoint.py, --kind, ...]`. Under
PyInstaller `sys.executable` is the frozen application, so that argv relaunches
this product instead of running somebody's training script - silently, with a
plausible process appearing and no error anywhere. `paths.python_executable`
REFUSES rather than guessing, which is why `docs/THE_PLAN.md` V.4 recommends
shipping `uv` instead of freezing.

## What this file cannot assert

That a real wheel installs and runs on a machine that has never seen this
repository. That is the packaging step's own acceptance and it is named in
THE_PLAN as a clean-machine test; a suite running in the checkout cannot fake
it. What it can do is drive every branch of the decision the checkout hides.
"""

import json
import os
import unittest
from pathlib import Path
from unittest import mock

from app import cli, db, jobspec, paths, security


REPO = Path(__file__).resolve().parents[1]


class TheCheckoutKeepsItsOwnFilesTest(unittest.TestCase):
    """THE HALF THAT PROTECTS EVERY DATABASE THAT ALREADY EXISTS."""

    def test_a_checkout_writes_where_it_always_did(self):
        """THE DEFAULT, not the live binding, and the difference is `sandbox()`.

        `db.DB_PATH`, `security.ENGINE_FILE` and `jobspec.RUNS_ROOT` are
        module-level and REBINDABLE on purpose - that is how every test in this
        suite keeps out of the user's checkout - so asserting their current
        value asserts which test ran last. This asserts what the modules
        compute when nothing has moved them, which is the thing that would have
        orphaned somebody's database.
        """
        self.assertEqual(paths.data_root(), REPO)
        self.assertEqual(paths.in_data_root("ml_harness.db"), REPO / "ml_harness.db")
        self.assertEqual(paths.in_data_root("engine.json"), REPO / "engine.json")
        self.assertEqual(paths.in_data_root("runs"), REPO / "runs")

    def test_each_module_takes_its_default_from_that_one_place(self):
        """Read off the source, because the bindings move. Three modules used
        to compute `parents[1]` for themselves - which in a wheel is
        site-packages - and three copies of a rule are three chances to fix two
        of them."""
        for module, name in (
            (db, "ml_harness.db"),
            (security, "engine.json"),
            (jobspec, "runs"),
        ):
            with self.subTest(module=module.__name__):
                source = (REPO / "app" / f"{module.__name__.split('.')[-1]}.py").read_text(
                    encoding="utf-8"
                )
                self.assertIn(f'paths.in_data_root("{name}")', source)

    def test_the_marker_is_the_one_the_ledger_loader_uses(self):
        """Two functions deciding 'am I in a repository' by two different tests
        are two answers waiting to disagree on the machine where it matters."""
        from app import diagnosis

        self.assertTrue((paths.data_root() / paths.CHECKOUT_MARKER).is_file())
        self.assertEqual(diagnosis.LEDGER_ROOT, paths.data_root())


class AnInstalledCopyGetsAPerUserRootTest(unittest.TestCase):
    """The branch the checkout hides, driven by hiding the checkout."""

    def test_with_no_repository_it_falls_to_the_platform_directory(self):
        with mock.patch.object(paths, "_checkout", return_value=None):
            with mock.patch.dict(os.environ, {"MLH_DATA_ROOT": ""}, clear=False):
                os.environ.pop("MLH_DATA_ROOT", None)
                root = paths.data_root()
        self.assertEqual(root.name, paths.APPLICATION)
        self.assertNotEqual(root, REPO)

    def test_on_windows_it_is_LOCAL_appdata_and_not_roaming(self):
        """A real choice rather than a coin toss. `%APPDATA%` follows a user
        between machines on a domain, and what this directory holds is a SQLite
        database, a token file and run artifacts sized in gigabytes - none of
        which should be copied across a network at login."""
        if os.name != "nt":  # pragma: no cover - the suite's home is Windows
            self.skipTest("the roaming distinction is a Windows one")
        local = os.environ.get("LOCALAPPDATA")
        self.assertTrue(local, "this machine has no LOCALAPPDATA to check against")
        with mock.patch.object(paths, "_checkout", return_value=None):
            os.environ.pop("MLH_DATA_ROOT", None)
            self.assertEqual(paths.data_root(), Path(local) / paths.APPLICATION)

    def test_nothing_is_created_by_asking_where_something_would_be(self):
        """A function that made a directory as a side effect of being asked
        where one would be would create a folder in somebody's home the first
        time a test imported this module."""
        with mock.patch.object(paths, "_checkout", return_value=None):
            os.environ.pop("MLH_DATA_ROOT", None)
            where = paths.in_data_root("a-folder-nothing-should-make")
        self.assertFalse(where.exists())


class TheOverridesKeepWinningTest(unittest.TestCase):
    """A person or a test that named a path said something more specific."""

    def test_the_root_can_be_moved_without_naming_each_file(self):
        with mock.patch.dict(os.environ, {"MLH_DATA_ROOT": str(Path("D:/elsewhere"))}):
            self.assertEqual(paths.data_root(), Path("D:/elsewhere"))
            self.assertEqual(
                paths.in_data_root("ml_harness.db"), Path("D:/elsewhere/ml_harness.db")
            )

    def test_the_per_file_overrides_are_the_ones_the_modules_read(self):
        """`ML_HARNESS_DB` and `MLH_ENGINE_FILE` are read at import, which is
        what `support.sandbox` rebinds around - so this asserts the SOURCE says
        they win rather than re-importing the world to prove it."""
        source = (REPO / "app" / "db.py").read_text(encoding="utf-8")
        self.assertIn('os.environ.get("ML_HARNESS_DB")', source)
        self.assertIn("paths.in_data_root", source)
        engine = (REPO / "app" / "security.py").read_text(encoding="utf-8")
        self.assertIn('os.environ.get("MLH_ENGINE_FILE")', engine)


class TheInterpreterIsNotAlwaysSysExecutableTest(unittest.TestCase):
    def test_in_an_ordinary_process_it_is(self):
        import sys

        os.environ.pop("MLH_PYTHON", None)
        self.assertEqual(paths.python_executable(), sys.executable)
        # `interpreter` is on `Recipe` rather than on `JobSpec` - the property
        # belongs to the thing that gets run, not to the request to run it - and
        # this asserts the seam is wired where the runner actually reads it.
        self.assertEqual(jobspec.load_recipe("demo-metrics").interpreter, sys.executable)

    def test_a_frozen_build_is_refused_rather_than_relaunched(self):
        """THE DEFECT THIS EXISTS TO PREVENT, driven. Under a freezer
        `sys.executable` is the application, so the runner's argv would
        relaunch this product instead of running the training script - and it
        would look like it worked."""
        import sys

        os.environ.pop("MLH_PYTHON", None)
        with mock.patch.object(sys, "frozen", True, create=True):
            with self.assertRaises(RuntimeError) as refused:
                paths.python_executable()
        self.assertIn("relaunch this product", str(refused.exception))
        self.assertIn("MLH_PYTHON", str(refused.exception))

    def test_a_build_that_ships_an_interpreter_says_so_and_is_believed(self):
        import sys

        with mock.patch.dict(os.environ, {"MLH_PYTHON": "C:/uv/python.exe"}):
            with mock.patch.object(sys, "frozen", True, create=True):
                self.assertEqual(paths.python_executable(), "C:/uv/python.exe")


class TheConsoleScriptIsTheInstallMetricTest(unittest.TestCase):
    def test_the_entry_point_is_declared(self):
        import tomllib

        config = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(config["project"]["scripts"]["mlh"], "app.cli:main")

    def test_doctor_reports_every_thing_phase_v_measured_missing(self):
        """The four rows of V.0's table, asked of this installation."""
        rows = {row["check"]: row for row in cli._findings()}
        for name in ("ledgers", "model_configs", "recipes"):
            with self.subTest(check=name):
                self.assertIn(name, rows)
                self.assertTrue(rows[name]["ok"], rows[name])
        self.assertGreater(len(rows["recipes"]["detail"]), 0)

    def test_it_exits_zero_when_everything_reads_and_writes_nothing(self):
        before = sorted(p.name for p in REPO.iterdir())
        code, said = self.doctor_says(("doctor", "--json"))
        self.assertEqual(code, 0)
        self.assertEqual(before, sorted(p.name for p in REPO.iterdir()))
        # Captured for the reason in `doctor_says`, and asserted on rather than
        # discarded: a run that printed nothing would pass this test too.
        self.assertEqual(json.loads(said)["broken"], [])

    def test_a_known_open_question_is_not_a_broken_install(self):
        """THE DEFECT A REAL WHEEL FOUND, and only a real wheel could have.

        Built non-editable, installed into a throwaway environment, run from a
        directory that is not the checkout - the only arrangement in which any
        of this is visible. It reported:

            RED recipes   none under site-packages
            exit=1

        The exit code was 1 for every healthy installation, which is an exit
        code nothing can be built on: CI cannot gate on it, a person cannot
        script it, and the one time it means something nobody is watching. A
        check is one of three things - fine, known-open, or broken - and only
        the third exits non-zero.

        **`recipes` WAS that known-open row and is not any more.** THE_PLAN V.3
        A1b was decided on 2026-08-28: a recipe's definition is package data and
        its virtualenv is not, so an installed copy has all three recipes and an
        install without them is genuinely broken. Nothing sets `open` today.

        So this drives the machinery DIRECTLY rather than borrowing a row that
        no longer means what it needed. The alternative - deleting the test with
        the question it was about - would take the distinction between "this
        installation is broken" and "this product has not decided that yet" out
        of the product on the day it happened to have no open questions, and the
        next honest unknown would have nowhere to be reported.
        """
        undecided = {
            "check": "a question nobody has answered",
            "ok": False,
            "open": True,
            "detail": "nothing here yet",
            "why": "the placeholder for the next real unknown",
        }
        with mock.patch("app.cli._findings", return_value=[undecided]):
            self.assertEqual(self.doctor_says()[0], 0)

        # AND THE ROW THAT USED TO BE OPEN IS NOW AN ORDINARY CHECK. An install
        # with no recipe definitions is a build that failed to bundle them.
        with mock.patch("app.jobspec.available_recipes", return_value=[]):
            rows = {row["check"]: row for row in cli._findings()}
            self.assertFalse(rows["recipes"]["ok"])
            self.assertNotIn("open", rows["recipes"])
            code, said = self.doctor_says()
            self.assertEqual(code, 1)
            self.assertIn("BROKEN: recipes", said)

    def doctor_says(self, args=("doctor",)):
        """Run the doctor, returning `(exit code, what it printed)`.

        CAPTURED, BECAUSE THE FAILURE PATH IS LOUD AND THE SUITE IS READ BY
        PEOPLE. These tests prove the doctor goes red correctly, so they make
        it print `RED ledgers  OSError: no ledgers` and `1 check(s) are BROKEN`
        - into the middle of a run that is passing. A reader scanning the gate
        log sees a broken install reported beside exit code 0 and reasonably
        concludes the gate is lying. That happened on 2026-09-04: a second
        session read exactly these two lines as a live fault and filed it as
        the top-priority defect in the stack.

        The output was never wrong; it was unlabelled. Capturing it keeps the
        suite log honest about what is actually failing, and returning it lets
        each test ASSERT on the sentence rather than merely on the number -
        which is strictly more than these tests checked before.
        """
        import io
        from contextlib import redirect_stdout

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = cli.main(list(args))
        return code, buffer.getvalue()

    def test_something_actually_broken_still_exits_nonzero(self):
        """The control. Without it the case above passes for a doctor that can
        never fail, which is the same uselessness in the other direction."""
        with mock.patch(
            "app.diagnosis.known_ledgers", side_effect=OSError("no ledgers")
        ):
            rows = {row["check"]: row for row in cli._findings()}
            self.assertFalse(rows["ledgers"]["ok"])
            self.assertFalse(rows["ledgers"].get("open", False))
            code, said = self.doctor_says()
            self.assertEqual(code, 1)
            self.assertIn("BROKEN: ledgers", said)
            self.assertIn("no ledgers", said)
            # AND THE SENTENCE THAT SAYS WHAT THE CHECK IS FOR. A red row whose
            # `why` is not printed tells a person a name and a stack message
            # and leaves them to guess what the engine has lost. Nothing
            # asserted this until a mutation run showed the line could be
            # deleted with the suite still green.
            self.assertIn(rows["ledgers"]["why"], said)

    def test_the_json_names_which_is_which(self):
        """A machine reading this needs the two lists separately, for the same
        reason the exit code does."""
        import io
        from contextlib import redirect_stdout

        # An install with no recipes is BROKEN now, not open - see the test
        # above and V.3 A1b.
        with mock.patch("app.jobspec.available_recipes", return_value=[]):
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                cli.main(["doctor", "--json"])
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["broken"], ["recipes"])
        # `recipes` IS IN NEITHER OTHER LIST, which is the claim. This line used
        # to read `assertEqual(payload["open_questions"], [])` and went red on
        # 2026-09-10 when `mlh doctor` gained its `model` row - the first check
        # ever to set `open`, which `app/cli.py` had reserved in writing for
        # "the next honest unknown". Nothing about recipes changed.
        #
        # An emptiness assertion made in a file that is about ONE row is a
        # tripwire on every other row, and it fires as a failure in the file
        # that did not change. What this test is for is that the two lists are
        # separate and a row lands in the right one, so that is what it asks.
        self.assertNotIn("recipes", payload["open_questions"])

        # And the two lists stay SEPARATE keys even when one is empty, because a
        # machine reading this should not have to infer a missing key.
        undecided = {
            "check": "a question nobody has answered",
            "ok": False,
            "open": True,
            "detail": "nothing here yet",
            "why": "the placeholder for the next real unknown",
        }
        with mock.patch("app.cli._findings", return_value=[undecided]):
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                cli.main(["doctor", "--json"])
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["broken"], [])
        self.assertEqual(payload["open_questions"], ["a question nobody has answered"])

    def test_a_broken_install_is_a_finding_and_not_a_stack_trace(self):
        """`mlh doctor` is the command a stranger runs when something is wrong,
        so an import error inside it has to arrive as a red row rather than as
        a traceback that tells them nothing they can act on."""
        with mock.patch("app.jobspec.available_recipes", side_effect=OSError("gone")):
            rows = {row["check"]: row for row in cli._findings()}
        self.assertFalse(rows["recipes"]["ok"])
        self.assertIn("gone", rows["recipes"]["detail"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
