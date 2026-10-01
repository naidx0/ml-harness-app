"""Every take and every release leaves one line in an append-only ledger.

THE AMENDMENT, 2026-09-06 00:30. The lock line is the record only while the
lock file exists, and one night's line survived only inside a commit body. So
every writer appends: the full lock line on take, and
`released lane=<name> at=<UTC Z> held=<seconds>` on release. One line each,
append-only, never rewritten - a log that can be edited is a log a reader has
to trust rather than read.

`held=` IS WRITTEN BY THE WRITER BECAUSE THE WRITER KNOWS IT. A reader can only
infer a span from two whole-second stamps; the process that held the card knows
how long it held it. The protocol has the reader recompute and report any
disagreement past a second rather than correct either number, so this writes
the span it measured rather than one derived to match.

WHAT IS NOT WRITTEN HERE. A `host=` field. The page lists it as a QUEUED
amendment rather than a ruled one, and the reader is documented as tolerating it
wherever it lands - so adding it early would be this writer inventing a protocol
change on the strength of a paragraph about a different one.

AND WHAT COULD NOT BE CHECKED. The reader this is meant to feed,
`card_owner/the_lock_log.py`, is not in this repository or on origin: the page
describes it as built and green with eighteen cases, and `git ls-tree` finds
neither it nor its tests. So this writer is checked against the FORMAT the page
states, and the pair has never been run end to end. That is a gap in the
evidence, not a claim that the two agree.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "take_the_card_ledger", REPO / "scripts" / "take_the_card.py"
)
card = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules[_spec.name] = card
_spec.loader.exec_module(card)

TAKE = re.compile(r"^lane=\S+ since=\S+ pid=\d+ born=\S+ what=.+$")
RELEASE = re.compile(r"^released lane=\S+ at=\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z held=\d+$")


class TheCardLockWritesALedgerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.lock = Path(self.tmp.name) / "gpu.lock"
        self.log = Path(self.tmp.name) / "gpu.lock.log"

    def quietly(self, argv: list[str]) -> int:
        import contextlib
        import io

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return card.main(argv)

    def lines(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines()

    def test_a_take_and_a_release_leave_one_line_each_in_that_order(self):
        self.assertEqual(self.quietly(["--what", "a run", "--lock", str(self.lock)]), 0)
        self.assertEqual(self.lines(), [self.lock.read_text(encoding="utf-8").strip()])
        self.assertEqual(self.quietly(["--release", "--lock", str(self.lock)]), 0)
        written = self.lines()
        self.assertEqual(len(written), 2)
        self.assertRegex(written[0], TAKE)
        self.assertRegex(written[1], RELEASE)
        self.assertFalse(self.lock.exists(), "the release left the lock behind")

    def test_it_appends_rather_than_rewrites(self):
        """A ledger that can be replaced is one a reader has to trust."""
        for n in range(3):
            self.quietly(["--what", f"run {n}", "--lock", str(self.lock)])
            self.quietly(["--release", "--lock", str(self.lock)])
        self.assertEqual(len(self.lines()), 6)
        self.assertEqual(sum(1 for line in self.lines() if line.startswith("released")), 3)

    def test_the_release_carries_a_span_the_writer_measured(self):
        line = "lane=practical since=2026-09-06T00:00:00Z pid=1 born=x what=a run"
        import datetime

        later = datetime.datetime(2026, 9, 6, 0, 1, 30, tzinfo=datetime.timezone.utc)
        self.assertEqual(card.held_seconds(line, now=later), 90)

    def test_a_line_with_no_readable_since_gives_no_span_rather_than_zero(self):
        """A false zero is a silent subtraction from somebody's total."""
        self.assertIsNone(card.held_seconds("lane=practical what=a run"))
        self.assertIsNone(card.held_seconds("lane=practical since=never what=a run"))

    def test_releasing_nothing_is_refused_rather_than_logged(self):
        self.assertEqual(self.quietly(["--release", "--lock", str(self.lock)]), 2)
        self.assertFalse(self.log.exists(), "it logged a release that never happened")

    def test_a_release_does_not_need_a_purpose(self):
        """Requiring --what to give the card back would make somebody invent
        one, and an invented line is worse than a missing field."""
        self.quietly(["--what", "a run", "--lock", str(self.lock)])
        self.assertEqual(self.quietly(["--release", "--lock", str(self.lock)]), 0)

    def test_an_unwritable_ledger_does_not_stop_the_card_being_taken(self):
        """Loud, and not fatal. A lane refused the card because a log file could
        not be opened is a worse outcome than a missing line - and the warning
        is what stops a quietly unwritten ledger."""
        unwritable = Path(self.tmp.name) / "no-such-dir" / "gpu.lock.log"
        self.assertFalse(card.append(unwritable, "a line"))

    def test_the_ledger_sits_beside_the_lock_it_records(self):
        self.assertEqual(card.the_log_beside(self.lock), self.log)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
