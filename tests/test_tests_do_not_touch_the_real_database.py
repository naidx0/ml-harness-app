"""A fence around the user's real data, and a test that reports on it.

## What went wrong

`tests/test_demo_script_runs.py` ran `scripts/demo_train.py` as a subprocess.
The script POSTs to whatever engine is listening on the default port; on the
owner's machine that was the real engine, writing to the real
`ml_harness.db`. Every pass of the suite added one run and thirty metric rows.
The file now holds 1,036 runs named `demo-loss-curve` mixed in with whatever
real work is there.

That is a repeat, not a one-off. The job-log collision fixed at b024da4 was the
same shape: shared state that every test was assumed to have been isolated
from, isolated in eleven places and forgotten in the twelfth. A pass hunting
specifically for that defect class walked past this one, because the twelfth
place was not a global in this process - it was a global in a *different*
process, reached over a socket.

## Why "fix the test" is not enough

The suite's isolation is `db.DB_PATH = <temp>` in the test process. That is
invisible to a subprocess, which resolves `DB_PATH` from its own environment,
and invisible to a *server*, which resolved it before the test started. Any new
test that shells out, starts an engine, or talks to one is outside the
protection and nothing says so.

So this file does not check that one test behaves. It watches the whole suite,
by two mechanisms that fail in different directions:

**1. `sqlite3.connect` is wrapped, for the whole test process.** Installed at
import - and `unittest discover` imports every test module before it runs any
test, so the wrapper is live for the entire run regardless of where this file
sorts alphabetically. Any in-process attempt to open a protected database is
recorded with the stack that made it and then refused, so the offending test
goes red *and names itself*. The attempt is recorded before it is refused,
which matters: a test that wraps its database call in `try/except` would
otherwise swallow the evidence, and `test_no_test_opened_the_real_database`
below would still report it.

**2. The files are fingerprinted.** Size, mtime and SHA-256, taken at import -
again, before any test runs - and compared here. This is the half that catches
a subprocess, a server, or anything else the in-process wrapper cannot see,
because it asks about the bytes on disk rather than about who called what.

Neither is sufficient alone, which is the point of having both. Mechanism 1
names the culprit but only sees this process. Mechanism 2 sees any writer at
all but cannot say who it was.

## What it is protecting

`support.PROTECTED_DATABASES`: the repository's `ml_harness.db`, plus whatever
`ML_HARNESS_DB` named when the test process started, because on a machine where
that variable is set the user's real data is not at the repo-root path at all.

## Two limits, stated rather than discovered later

- Mechanism 2 compares against a snapshot taken at import. A test that runs
  *after* this file (`test_theme.py`, `test_theme_ground.py` sort later) and
  writes through a subprocess would be missed by it - though mechanism 1 still
  catches an in-process write, since the wrapper stays installed for the life
  of the process.
- Mechanism 1 sees `sqlite3.connect(path)`. It does not decode
  `sqlite3.connect("file:...?mode=rw", uri=True)`. Nothing in this codebase
  connects that way; if something starts to, this wrapper needs to learn to
  parse it.

There is one way to get a false positive: something outside the suite writing
to the real database while the suite runs - the owner's own engine serving a
request from an open dashboard tab, say. Reads do not change a file, so a tab
merely polling is harmless, but a genuine write from outside would show up here
as a red test. That is the right trade. A guard that stays quiet when the file
changes for a reason it did not expect is not a guard.
"""

from __future__ import annotations

import os
import sqlite3
import traceback
import unittest

import support


# The fence itself now lives in `support`, so it installs for every test run
# rather than only the ones that import this file. See the comment there.
RealDatabaseTouched = support.RealDatabaseTouched
ATTEMPTS = support.ATTEMPTS
PROTECTED = support.PROTECTED
_normalise = support._normalise
_install = support._install

#: Taken at import, which under `unittest discover` is before any test runs.
BASELINE = {
    path: support.database_fingerprint(path)
    for path in support.PROTECTED_DATABASES
}


class RealDatabaseGuardTest(unittest.TestCase):
    def test_guard_is_installed(self):
        """If this fails, the two tests below are green for the wrong reason."""
        self.assertTrue(
            getattr(sqlite3.connect, "_mlh_guard", False),
            "sqlite3.connect is not wrapped: something replaced it after "
            "import, so nothing has been watching this run",
        )
        self.assertTrue(
            PROTECTED,
            "the guard has no paths to protect, so it cannot refuse anything",
        )

    def test_no_test_opened_the_real_database(self):
        if not ATTEMPTS:
            return
        report = "\n\n".join(
            f"{path} opened from:\n{stack}" for path, stack in ATTEMPTS
        )
        self.fail(
            f"{len(ATTEMPTS)} attempt(s) to open a database holding real "
            f"data:\n\n{report}"
        )

    def test_the_guard_refuses_a_connection_to_the_real_database(self):
        """Prove the refusal works here, rather than trusting it works.

        No file is opened by this: the wrapper raises before it delegates. The
        attempt it records is removed again on cleanup so it does not read as
        pollution to `test_no_test_opened_the_real_database`.
        """
        target = str(support.PROTECTED_DATABASES[0])
        before = len(ATTEMPTS)
        self.addCleanup(lambda: ATTEMPTS.__delitem__(slice(before, None)))

        with self.assertRaises(RealDatabaseTouched):
            sqlite3.connect(target)

        self.assertEqual(len(ATTEMPTS), before + 1)
        self.assertIn(__file__.rsplit(os.sep, 1)[-1], ATTEMPTS[before][1])

    def test_the_real_database_files_are_unchanged(self):
        for path, baseline in BASELINE.items():
            with self.subTest(database=str(path)):
                self.assertEqual(
                    support.database_fingerprint(path),
                    baseline,
                    f"{path} changed during this test run. Size, timestamp or "
                    "contents differ from what they were when the suite "
                    "started.\n\nMost likely: a test wrote to the user's real "
                    "data through a subprocess or an engine that resolved "
                    "ML_HARNESS_DB for itself. An in-process write cannot be "
                    "the cause - the wrapper would have refused it outright "
                    "and named the caller.\n\nAlso possible: something outside "
                    "this suite wrote while it ran - a second copy of the "
                    "suite, or the owner's own engine serving a POST from an "
                    "open dashboard tab. Check whether anything else was "
                    "running before assuming it was a test.",
                )


if __name__ == "__main__":
    unittest.main()
