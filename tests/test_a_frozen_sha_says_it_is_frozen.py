"""The published sha is read once, and the identity says when.

FOUND BY MISREADING IT. On 2026-09-05 a full gate reported one failure:
`identity.git_head()` answered `1cec60f` while `git rev-parse HEAD` answered
`1d29f22`. The test was right both times. A commit had landed while the suite
was running, and the suite's subject is the repository it runs in.

THE VALUE WAS NOT WRONG, WHICH IS WHY THIS FILE IS NOT A BUG FIX. A process
executes the modules it imported at startup. When HEAD moves afterwards the
code in memory does not move with it, so the sha describing this engine is the
one that was HEAD when it started - and re-reading would make a long-lived
engine report a commit whose code it is not running, which is the failure
`app/identity.py` exists to prevent.

WHAT WAS MISSING WAS THE DISCLOSURE. `sha_source` says `git-ref`: how the
answer was obtained, never when. Nothing in the published identity let a reader
tell a frozen reading from a fresh one, so the honest interpretation and the
alarming one looked identical - and the reader who could not tell was the
person who wrote the surrounding checks. `build()` now carries `sha_read_at`.

THE PLANTED CASE IS BELOW: HEAD moves under a live reader, and the frozen
answer must NOT follow it, while an explicit root must.
"""

from __future__ import annotations

import subprocess
import tempfile
from datetime import datetime, timezone
import unittest
from pathlib import Path

from app import identity


def a_repository_with_two_commits(where: Path) -> tuple[str, str]:
    """Build a throwaway repository and return both shas, in order."""
    def git(*args: str) -> str:
        done = subprocess.run(
            ["git", *args], cwd=where, capture_output=True, text=True
        )
        return done.stdout.strip()

    git("init", "-q")
    git("config", "user.email", "gate@example.invalid")
    git("config", "user.name", "gate")
    (where / "a.txt").write_text("one", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "first")
    first = git("rev-parse", "HEAD")
    (where / "a.txt").write_text("two", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "second")
    return first, git("rev-parse", "HEAD")


class AFrozenShaSaysItIsFrozenTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)

    def test_an_explicit_root_reads_live(self):
        """THE INSTRUMENT FIRST. If this fails, the fixture is not a
        repository and the freeze test below proves nothing."""
        first, second = a_repository_with_two_commits(self.repo)
        self.assertNotEqual(first, second)
        sha, source = identity.git_head(self.repo)
        self.assertEqual(sha, second)
        self.assertEqual(source, "git-ref")

    def test_the_process_reading_does_not_follow_a_later_commit(self):
        """THE PLANTED CASE. A commit lands under a live reader; the frozen
        answer must stay put, because the code in memory did too.

        Against a throwaway repository with `REPO_ROOT` pointed at it, never
        against this one. The first draft committed to the real repository and
        undid it with `git reset --hard HEAD~1`, which discards uncommitted
        work in the tree - a suite that runs thousands of times a night must
        not carry a destructive git command that only has to escape once.
        """
        first, second = a_repository_with_two_commits(self.repo)
        real = identity.REPO_ROOT
        identity.REPO_ROOT = self.repo
        self.addCleanup(setattr, identity, "REPO_ROOT", real)
        self.addCleanup(identity.reset_caches_for_tests)

        identity.reset_caches_for_tests()
        frozen, _ = identity.git_head()
        self.assertEqual(frozen, second, "the reader did not see the fixture at all")

        subprocess.run(
            ["git", "commit", "-q", "--allow-empty", "-m", "under a live reader"],
            cwd=self.repo,
            capture_output=True,
            text=True,
        )
        moved = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.repo, capture_output=True, text=True
        ).stdout.strip()
        self.assertNotEqual(moved, frozen, "the plant did not land, so nothing was tested")

        after, _ = identity.git_head()
        self.assertEqual(
            after, frozen, "the published sha followed a commit this process did not load"
        )
        self.assertNotEqual(after, moved)

    def test_the_identity_says_when_it_read(self):
        identity.reset_caches_for_tests()
        built = identity.build()
        self.assertIn("sha_read_at", built)
        self.assertTrue(
            built["sha_read_at"],
            "the sha is published with no reading time, which is the state that "
            "made a correct disagreement look like a caching defect",
        )
        # PARSED, NOT SNIFFED. This asserted `"T" in value`, and "Tuesday"
        # contains a T - a check that would pass on any string with the right
        # letter in it, on a field whose whole job is to be a time a reader can
        # compare against a commit date.
        when = datetime.fromisoformat(built["sha_read_at"])
        self.assertIsNotNone(when.tzinfo, "a reading time with no zone cannot be compared")
        self.assertLess(
            abs((datetime.now(timezone.utc) - when).total_seconds()),
            3600,
            "the reading time is not near now, so it is not this process's reading",
        )

    def test_the_reading_time_does_not_move_either(self):
        """A timestamp that refreshed on every call would say the sha was read
        now, which is the opposite of what it is for."""
        identity.reset_caches_for_tests()
        first = identity.build()["sha_read_at"]
        self.assertEqual(identity.build()["sha_read_at"], first)

    def test_resetting_for_tests_clears_both(self):
        identity.reset_caches_for_tests()
        identity.build()
        identity.reset_caches_for_tests()
        self.assertEqual(identity._GIT_HEAD, None)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
