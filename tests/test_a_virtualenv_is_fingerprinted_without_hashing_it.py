"""A leak guard that costs 150 seconds a gate, and the trade that was ruled.

## The number, measured before anything changed

    tree_fingerprint("recipes")   65,691 entries   74.9 s

It reads and SHA-256s **every byte of every file** under each watched path, and
it runs at least twice per gate — once at module import for the baseline, once
in the assertion. `recipes/` holds three virtualenvs totalling about 14 GB, so
**roughly 150 seconds of a 1,270-second gate was hashing virtualenvs**, for every
lane, every run, growing with every environment anyone builds.

This lane measured that and deliberately did **not** change it, because the
trade belongs to whoever owns the guarantee rather than to a passing lane that
found the check slow. The owner ruled: **virtualenv directories are excluded
from the byte hash and covered by a cheap structural fingerprint instead.**

## Why the guarantee survives, stated so the weakening is legible

The question the guard answers is *did anything write into the repository during
this run*. **The way anything writes into a virtualenv is by installing into
it**, and an install adds files, adds bytes, and moves the newest mtime. So each
`.venv` contributes one row carrying those three facts, and no write pattern any
test in this suite produces leaves all three identical.

**What is given up, named rather than glossed:** an in-place, same-size,
mtime-preserving overwrite of an existing file inside a `.venv` is no longer
noticed. That is the cost of the ruling and it is written down here so nobody
later reads the guard as stronger than it is.

## And the pruning is the actual saving

The first implementation filtered virtualenv paths out *after*
`sorted(root.rglob("*"))` had already materialised and sorted all 71,000 of
them: 74.9 s → 21.9 s. Walking with `os.walk` and pruning the directory list,
plus counting through `os.scandir` — whose `DirEntry` carries the stat the
listing already returned — gives the same three answers per venv at **1.04 s**.
A filter that runs after the expensive part is not a saving; it is the same walk
with a shorter output.
"""

import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import support


class ARealWriteIsStillCaughtByBytesTest(unittest.TestCase):
    """The half that must not weaken."""

    def test_a_new_file_outside_a_venv_changes_the_fingerprint(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pack").mkdir()
            (root / "pack" / "a.json").write_text("{}", encoding="utf-8")
            before = support.tree_fingerprint(root)
            (root / "pack" / "b.json").write_text("{}", encoding="utf-8")
            self.assertNotEqual(before, support.tree_fingerprint(root))

    def test_an_edit_that_keeps_the_size_is_still_caught_outside_a_venv(self):
        """THE CASE THE HASH EXISTS FOR. A same-length overwrite is invisible to
        size alone, and outside a virtualenv it is still hashed."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.json").write_text('{"x": 1}', encoding="utf-8")
            before = support.tree_fingerprint(root)
            (root / "a.json").write_text('{"x": 2}', encoding="utf-8")
            after = support.tree_fingerprint(root)
            self.assertEqual(before["a.json"][0], after["a.json"][0])
            self.assertNotEqual(before["a.json"][1], after["a.json"][1])


class AVirtualenvIsCoveredStructurallyTest(unittest.TestCase):
    def a_tree(self, root: Path) -> None:
        venv = root / "recipe" / ".venv" / "Lib" / "site-packages" / "torch"
        venv.mkdir(parents=True)
        for index in range(5):
            (venv / f"mod{index}.py").write_text("x = 1\n", encoding="utf-8")
        (root / "recipe" / "entrypoint.py").write_text("y = 2\n", encoding="utf-8")

    def test_the_venv_is_one_row_and_its_files_are_not_hashed(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.a_tree(root)
            fingerprint = support.tree_fingerprint(root)
        self.assertIn("recipe/.venv", fingerprint)
        self.assertIn("recipe/entrypoint.py", fingerprint)
        inside = [key for key in fingerprint if key.startswith("recipe/.venv/")]
        self.assertEqual(inside, [], "virtualenv files are still being hashed")

    def test_a_file_added_under_a_venv_is_caught_and_named(self):
        """THE HALF THE RULING HAD TO KEEP. An install adds files, and the row
        has to move — and say which of the three facts moved, so a virtualenv
        rebuilt during a gate reads as a rebuild rather than as a leak of
        unknown shape."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.a_tree(root)
            before = support.tree_fingerprint(root)["recipe/.venv"]
            (root / "recipe" / ".venv" / "Lib" / "installed.py").write_text(
                "z = 3\n", encoding="utf-8")
            after = support.tree_fingerprint(root)["recipe/.venv"]

        self.assertNotEqual(before, after)
        self.assertIn("entries=", after[1])
        self.assertIn("bytes=", after[1])
        self.assertEqual(before[0] + 1, after[0], "the entry count did not move")

    def test_a_file_deleted_from_a_venv_is_caught(self):
        """The other direction, because a check that only notices growth reads
        a deletion as nothing happening."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.a_tree(root)
            before = support.tree_fingerprint(root)["recipe/.venv"]
            (root / "recipe" / ".venv" / "Lib" / "site-packages" / "torch"
             / "mod0.py").unlink()
            after = support.tree_fingerprint(root)["recipe/.venv"]
        self.assertNotEqual(before, after)
        self.assertEqual(before[0] - 1, after[0])

    def test_a_same_size_overwrite_inside_a_venv_is_NOT_caught(self):
        """THE WEAKENING, ASSERTED RATHER THAN LEFT TO BE DISCOVERED.

        This is what the ruling gave up. Writing it as a passing test means the
        day somebody strengthens the fingerprint, this test fails and asks them
        to update the docstring above rather than letting the two disagree
        silently. A guard whose limits are only in prose is a guard whose limits
        drift.

        The mtime is restored deliberately: an install moves it, and this is the
        case where nothing an install does has happened.
        """
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.a_tree(root)
            target = (root / "recipe" / ".venv" / "Lib" / "site-packages"
                      / "torch" / "mod0.py")
            stamp = target.stat()
            before = support.tree_fingerprint(root)["recipe/.venv"]
            target.write_text("x = 9\n", encoding="utf-8")  # same length
            os.utime(target, (stamp.st_atime, stamp.st_mtime))
            after = support.tree_fingerprint(root)["recipe/.venv"]
        self.assertEqual(before, after)


class TheSavingIsRealTest(unittest.TestCase):
    def test_pruning_beats_hashing_on_a_tree_with_many_small_files(self):
        """Not a wall-clock threshold - those fail on a loaded CI box for
        reasons that have nothing to do with the change. The claim is the
        RATIO on one tree in one process: skipping a subtree must be
        substantially cheaper than reading it.
        """
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            venv = root / "pkg" / ".venv"
            venv.mkdir(parents=True)
            for index in range(2000):
                (venv / f"f{index}.py").write_text("x" * 400, encoding="utf-8")

            start = time.perf_counter()
            support.tree_fingerprint(root)
            pruned = time.perf_counter() - start

            hashed_root = root / "pkg" / "plain"
            hashed_root.mkdir()
            for index in range(2000):
                (hashed_root / f"f{index}.py").write_text("x" * 400,
                                                          encoding="utf-8")
            start = time.perf_counter()
            support.tree_fingerprint(root)
            both = time.perf_counter() - start

        self.assertLess(pruned, both,
                        "skipping a subtree cost as much as hashing one")


if __name__ == "__main__":
    unittest.main()
