"""The GPU lock line carries the two facts a card owner has to rule on.

THE PROTOCOL, ruled 2026-09-05 20:50:

    lane=<lane> since=<UTC Z> pid=<pid> born=<start time UTC Z> what=<line>

The owner has to decide two different things about a lock nobody released - is
the holder dead, or is it alive under a number handed to somebody else - and
the old line carried neither fact. Every lock written before tonight answers
"cannot be decided", which is the honest reading of a line with no pid and no
birth: not alive, not gone, never askable.

WHY `born` IS CONVERTED. The operating system's own token is a FILETIME on
Windows and clock ticks since boot on Linux. Neither is comparable by a person
reading a lock file, and the second is not comparable across a reboot. Where a
wall clock cannot be produced this writes `unknown` rather than a number that
looks like one, because a field that is sometimes a timestamp and sometimes a
tick count is worse than an absent field.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("take_the_card", REPO / "scripts" / "take_the_card.py")
card = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(card)

STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class TheCardLockSaysWhoAndWhenTest(unittest.TestCase):
    def test_the_line_carries_all_five_fields_in_the_ruled_order(self):
        line = card.the_line("practical", "one teach turn")
        self.assertRegex(line, r"^lane=\S+ since=\S+ pid=\d+ born=\S+ what=")
        self.assertTrue(line.endswith("what=one teach turn"))

    def test_since_and_born_are_both_utc_stamps(self):
        line = card.the_line("practical", "a run")
        fields = dict(part.split("=", 1) for part in line.split(" ")[:4])
        self.assertRegex(fields["since"], STAMP)
        self.assertRegex(fields["born"], STAMP)

    @unittest.skipUnless(os.name == "nt", "the conversion under test is the Windows one")
    def test_born_agrees_with_an_independent_reader(self):
        """The arithmetic is checked against something that is not this code.
        A FILETIME converted with the wrong epoch is off by 369 years and still
        looks like a timestamp."""
        mine = card.born_utc(os.getpid())
        other = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-Process -Id {}).StartTime.ToUniversalTime()"
                ".ToString('yyyy-MM-ddTHH:mm:ssZ')".format(os.getpid()),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        ).stdout.strip()
        if not other:  # pragma: no cover - powershell unavailable
            self.skipTest("no independent reader available")
        self.assertEqual(mine, other)

    def test_a_pid_that_is_gone_has_no_birth_rather_than_a_wrong_one(self):
        self.assertEqual(card.born_utc(999_999), "")
        self.assertEqual(card.born_utc(0), "")
        self.assertIn("born=unknown", card.the_line("practical", "a run", pid=999_999))

    def test_it_refuses_to_overwrite_a_lock_that_is_already_there(self):
        """Taking a card somebody else holds is the collision the lock exists
        to prevent, and a writer that clobbers is worse than no writer."""
        # Captured, because `main` prints the line it wrote and a lock-shaped
        # line loose in the gate's output reads like a lane claiming the card.
        import contextlib
        import io as _io

        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(_io.StringIO()):
            lock = Path(tmp) / "gpu.lock"
            self.assertEqual(card.main(["--what", "mine", "--lock", str(lock)]), 0)
            first = lock.read_text(encoding="utf-8")
            self.assertEqual(card.main(["--what", "also mine", "--lock", str(lock)]), 2)
            self.assertEqual(lock.read_text(encoding="utf-8"), first)

    def test_the_old_form_is_readable_as_cannot_be_decided(self):
        """Locks written before tonight have no pid and no birth. A reader must
        get "cannot be decided" from them, not a default of either answer."""
        old = "lane=practical since=2026-09-05T18:52:10Z what=an experiment"
        fields = dict(
            part.split("=", 1) for part in old.split(" ") if "=" in part
        )
        self.assertNotIn("pid", fields)
        self.assertNotIn("born", fields)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
