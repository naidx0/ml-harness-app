"""Each thing that stops a restart stops it alone, and says which thing it was.

A long-lived engine serves the build it started with. Measured 2026-09-10: the
engine on 8078 reported `build.sha da203bb` with `dirty: true` while main had
moved many commits past it, so a walk recorded through it described a tree that
had not existed for hours.

Restarting is easy; restarting safely is three questions, each owned by a
different lane - is the card busy, is anybody mid-conversation, is the tree the
new engine would launch from clean. This file is the one rule that makes those
answerable: **a probe that trips two guards proves neither in isolation**, so
each refusal gets a case that produces only it, and a fourth case shows the four
exits are four numbers.

The verification is tested the same way. A restart that does not read back the
sha it produced is the health-check fault in a new costume - a process that
started is not a build that is serving - so an unchanged sha is its own exit.
"""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

import support

restart = support.import_file(
    "restart_engine_when_idle",
    support.REPO_ROOT / "scripts" / "restart_engine_when_idle.py",
)


def run(argv, **patch):
    """Call `main` with named attributes replaced, and give back (exit, said)."""
    saved = {name: getattr(restart, name) for name in patch}
    for name, value in patch.items():
        setattr(restart, name, value)
    out, err = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = restart.main(argv)
    finally:
        for name, value in saved.items():
            setattr(restart, name, value)
    return code, out.getvalue() + err.getvalue()


class AHeldCardRefusesAloneTest(unittest.TestCase):
    """Guard one. The lane holding it may be mid-measurement."""

    def setUp(self):
        self.root = Path(support.sandbox(self))
        self.lock = self.root / "gpu.lock"
        self.lock.write_text(
            "lane=sequence since=2026-09-10T05:34:47Z pid=2400 "
            "what=sequence teach: 4 runs, granite42-hermes" + chr(10),
            encoding="utf-8",
        )

    def test_it_refuses_and_names_the_holder(self):
        code, said = run(
            ["--dry-run", "--lock", str(self.lock), "--database", str(self.root / "none.db")],
            what_is_dirty=lambda *a, **k: [],
        )
        self.assertEqual(code, restart.THE_CARD_IS_BUSY)
        #: THE LINE, not the word "busy". A lane that has to find out who is
        #: holding it has been told nothing.
        self.assertIn("lane=sequence", said)
        self.assertIn("granite42-hermes", said)

    def test_a_free_card_does_not_trip_this_guard(self):
        """The isolating half: same call, empty lock file."""
        self.lock.write_text("", encoding="utf-8")
        code, _ = run(
            ["--dry-run", "--lock", str(self.lock), "--database", str(self.root / "none.db")],
            what_is_dirty=lambda *a, **k: [],
            health=lambda *a, **k: {"build": {"sha": "abc123"}},
        )
        self.assertNotEqual(code, restart.THE_CARD_IS_BUSY)


class ALiveThreadRefusesAloneTest(unittest.TestCase):
    """Guard two. Read from the database, not assumed."""

    def setUp(self):
        self.root = Path(support.sandbox(self))
        self.lock = self.root / "gpu.lock"
        self.lock.write_text("", encoding="utf-8")
        self.db = self.root / "ml_harness.db"

    def a_database_with(self, when: datetime, thread_id: int = 77):
        import sqlite3

        connection = sqlite3.connect(self.db)
        connection.execute(
            "CREATE TABLE messages (id INTEGER PRIMARY KEY, thread_id INTEGER, "
            "created_at TEXT)"
        )
        connection.execute(
            "INSERT INTO messages (thread_id, created_at) VALUES (?, ?)",
            (thread_id, when.strftime("%Y-%m-%d %H:%M:%S")),
        )
        connection.commit()
        connection.close()

    def test_a_thread_touched_a_minute_ago_refuses_and_names_it(self):
        self.a_database_with(datetime.now(timezone.utc) - timedelta(minutes=1))
        code, said = run(
            ["--dry-run", "--lock", str(self.lock), "--database", str(self.db)],
            what_is_dirty=lambda *a, **k: [],
        )
        self.assertEqual(code, restart.A_THREAD_IS_LIVE)
        self.assertIn("77", said)

    def test_a_thread_touched_an_hour_ago_does_not(self):
        """THE ISOLATING HALF, and the one that stops this guard being 'never
        restart'. Every database has old rows."""
        self.a_database_with(datetime.now(timezone.utc) - timedelta(hours=1))
        code, _ = run(
            ["--dry-run", "--lock", str(self.lock), "--database", str(self.db)],
            what_is_dirty=lambda *a, **k: [],
            health=lambda *a, **k: {"build": {"sha": "abc123"}},
        )
        self.assertNotEqual(code, restart.A_THREAD_IS_LIVE)

    def test_a_database_that_is_not_there_is_not_a_live_thread(self):
        self.assertIsNone(restart.a_live_thread(self.root / "absent.db"))


class ADirtyTreeRefusesAloneTest(unittest.TestCase):
    """Guard three. Relaunching onto uncommitted work swaps one
    unreproducible build for another."""

    def setUp(self):
        self.root = Path(support.sandbox(self))
        self.lock = self.root / "gpu.lock"
        self.lock.write_text("", encoding="utf-8")

    def test_it_refuses_and_names_the_paths(self):
        code, said = run(
            ["--dry-run", "--lock", str(self.lock), "--database", str(self.root / "none.db")],
            what_is_dirty=lambda *a, **k: ["app/tools/training.py"],
        )
        self.assertEqual(code, restart.THE_TREE_IS_DIRTY)
        self.assertIn("app/tools/training.py", said)

    def test_an_untracked_file_is_not_dirt(self):
        """Every lane leaves scratch files here. Counting them as dirt would
        mean never restarting, which is a guard that has become a wall."""
        said = restart.what_is_dirty(support.REPO_ROOT)
        self.assertNotIn("??", "".join(said))


class ARestartThatDidNotTakeIsNotARestartTest(unittest.TestCase):
    """FOUND BY MUTATION, and it is the fault this script was warned about.

    Loosening the check from "the sha CHANGED" to "a sha came back" turned
    NOTHING red: every case above stops at a guard, so the action path had no
    test at all. A process that started is not a build that is serving, and the
    only evidence of the second is the number coming back different from the one
    written down before.
    """

    class _Clock:
        @staticmethod
        def sleep(_seconds):
            return None

    def setUp(self):
        self.root = Path(support.sandbox(self))
        self.lock = self.root / "gpu.lock"
        self.lock.write_text("", encoding="utf-8")

    def act(self, healths):
        answers = iter(healths)
        last = healths[-1]

        def health(*_a, **_k):
            return next(answers, last)

        return run(
            ["--lock", str(self.lock), "--database", str(self.root / "none.db")],
            what_is_dirty=lambda *a, **k: [],
            health=health,
            _launcher=lambda *a, **k: type("R", (), {"stdout": "ok", "stderr": ""})(),
            security=type("S", (), {"read_portfile": staticmethod(lambda: {"port": 1})}),
            time=self._Clock,
        )

    def test_the_same_sha_afterwards_is_a_restart_that_did_not_happen(self):
        code, said = self.act([{"build": {"sha": "old", "dirty": False}}] * 3)
        self.assertEqual(code, restart.THE_RESTART_DID_NOT_TAKE)
        self.assertIn("still reports", said)
        self.assertIn("did not happen", said)

    def test_a_changed_sha_that_is_still_dirty_is_refused_too(self):
        """A new build nobody can reproduce is not an improvement on an old one
        nobody can reproduce."""
        code, said = self.act(
            [{"build": {"sha": "old", "dirty": True}}, {"build": {"sha": "new", "dirty": True}}]
        )
        self.assertEqual(code, restart.THE_RESTART_DID_NOT_TAKE)
        self.assertIn("dirty", said)

    def test_a_changed_clean_sha_is_the_success(self):
        code, said = self.act(
            [{"build": {"sha": "old", "dirty": False}}, {"build": {"sha": "new", "dirty": False}}]
        )
        self.assertEqual(code, restart.RESTARTED)
        self.assertIn("old -> new", said)


def _release_module(name: str):
    """`scripts/release/` is not a package, so it is loaded by path."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        name, support.REPO_ROOT / "scripts" / "release" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


mirror = _release_module("mirror")


class ThisFileCarriesNobodysFolders(unittest.TestCase):
    """A shipped script must not know where one person keeps their notes.

    THIS FILE WAS THE DEFECT. It built the card lock's path from
    `Path.home()` joined to literal segments naming a personal cloud folder and
    a vault. `tests/test_the_mirror_ships_nothing_private.py` flags private path
    segments against `identifiers.json`, which is GITIGNORED AND PER-CHECKOUT -
    so a tree whose denylist does not happen to name those segments reads green
    while a tree whose denylist does reads red. Main was red for two lanes on
    this file while it was green in the checkout that wrote it.

    That is why this case must not read whichever `identifiers.json` is on disk:
    a test that depends on a gitignored file for its strictness is a test whose
    strictness varies by machine, and that is the fault it is here to catch.

    AND THE FIRST VERSION OF IT SPELLED THE SEGMENTS OUT, which was the same
    defect again one file over. A hand-written denylist naming a vault IS a file
    that names a vault, and `scripts/release/mirror.py` scans every file that
    would ship - including this one. It went red on its own literals.
    `mirror.py:103` had already written the rule down: "a rule that spells out
    its own trigger fails its own check."

    So the strictness comes from the mirror's own SHAPE rules, run directly on
    the script. They live in the tree rather than in a gitignored file, so this
    is machine-independent for the reason the hand-written list was reaching
    for - and it is the canonical set, so a shape added there tightens this
    test for free instead of leaving it a stale copy.
    """

    #: Generic directory words. Not private and not anybody's - a shipped script
    #: has no business hard-coding them either, and none of them names a person.
    NO_HARD_CODED_DIRECTORIES = ("OneDrive", "AppData")

    @property
    def script(self) -> str:
        return (support.REPO_ROOT / "scripts" / "restart_engine_when_idle.py").read_text(
            encoding="utf-8"
        )

    def test_the_script_trips_none_of_the_mirrors_shape_rules(self):
        """THE STRICT HALF, and it names nobody to be strict."""
        self.assertEqual(
            mirror.scan(
                ["scripts/restart_engine_when_idle.py"], include_identifiers=False
            ),
            [],
            "the restart script matches a shape the mirror refuses to publish.",
        )

    def test_the_shape_rules_are_a_real_set(self):
        """A scan of zero rules reports clean, which is the failure mode of
        every check that reports zero."""
        self.assertGreater(len(mirror.SHAPES), 3)

    def test_the_script_hard_codes_no_directory_names(self):
        for segment in self.NO_HARD_CODED_DIRECTORIES:
            with self.subTest(segment=segment):
                self.assertNotIn(segment, self.script)

    def test_it_reads_the_path_from_the_environment(self):
        self.assertEqual(restart.THE_CARD_LOCK_VARIABLE, "MLH_CARD_LOCK")

    def test_unset_refuses_and_names_the_variable(self):
        """A REFUSAL, NOT A GUESS. A guess that happens to be right on one
        machine is how the personal path shipped in the first place."""
        import os

        saved = os.environ.pop(restart.THE_CARD_LOCK_VARIABLE, None)
        try:
            code, said = run(["--dry-run"])
        finally:
            if saved is not None:
                os.environ[restart.THE_CARD_LOCK_VARIABLE] = saved
        self.assertEqual(code, restart.NO_LOCK_CONFIGURED)
        self.assertIn(restart.THE_CARD_LOCK_VARIABLE, said)
        self.assertIn("will not guess", said)

    def test_the_variable_is_used_when_it_is_set(self):
        import os

        root = Path(support.sandbox(self))
        lock = root / "gpu.lock"
        lock.write_text("lane=someone what=mine" + chr(10), encoding="utf-8")
        saved = os.environ.get(restart.THE_CARD_LOCK_VARIABLE)
        os.environ[restart.THE_CARD_LOCK_VARIABLE] = str(lock)
        try:
            code, said = run(["--dry-run"], what_is_dirty=lambda *a, **k: [])
        finally:
            if saved is None:
                os.environ.pop(restart.THE_CARD_LOCK_VARIABLE, None)
            else:
                os.environ[restart.THE_CARD_LOCK_VARIABLE] = saved
        self.assertEqual(code, restart.THE_CARD_IS_BUSY)
        self.assertIn("lane=someone", said)


class TheFourExitsAreFourNumbersTest(unittest.TestCase):
    """If any two collapsed, one refusal would have no case that produces
    only it."""

    def test_they_are_distinct(self):
        codes = {
            restart.RESTARTED,
            restart.THE_CARD_IS_BUSY,
            restart.A_THREAD_IS_LIVE,
            restart.THE_TREE_IS_DIRTY,
            restart.THE_RESTART_DID_NOT_TAKE,
        }
        self.assertEqual(len(codes), 5)

    def test_every_guard_passing_is_exit_zero_and_changes_nothing(self):
        root = Path(support.sandbox(self))
        lock = root / "gpu.lock"
        lock.write_text("", encoding="utf-8")
        code, said = run(
            ["--dry-run", "--lock", str(lock), "--database", str(root / "none.db")],
            what_is_dirty=lambda *a, **k: [],
            health=lambda *a, **k: {"build": {"sha": "abc123"}},
        )
        self.assertEqual(code, restart.RESTARTED)
        self.assertIn("nothing was restarted", said)


if __name__ == "__main__":
    unittest.main()
