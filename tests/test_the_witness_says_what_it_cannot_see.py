"""The witness is a cheap check, and this is how cheap - with the number.

`app/build.py` has always said a file "rewritten with the same size and
modification time" defeats the witness, and named a coarse mtime resolution as
one way that happens. That was written as a hypothetical about some other
filesystem.

MEASURED 2026-09-05 ON THIS MACHINE: two different files of the same length,
written back to back, produced an IDENTICAL witness in 157 of 200 trials. The
gap is not exotic and it is not somebody else's disk; it is the common case for
a fast rewrite here.

WHY PIN IT. The limit is documented, and a documented limit that nobody
measures drifts into folklore in both directions: a reader who thinks the
witness is an identity will trust it too far, and a reader who thinks it is
worthless will replace it with a hash the module deliberately refuses to afford
(costing a step on a 50 GB dataset must not read 50 GB).

WHAT WOULD MAKE THIS FILE FAIL, AND WHAT TO DO THEN. If the witness gains a
content hash or a change counter, `test_a_same_length_rewrite_can_be_invisible`
stops finding collisions and goes red. That is not a regression: it means the
witness got stronger, and the clause in `app/build.py` should be rewritten and
this file retired with it. A test that fails when the product IMPROVES has to
say so out loud, which is what this paragraph is for.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app import build

#: Two payloads of equal length and different content. Equal length is the
#: point: the size half of the witness cannot move, so the mtime half is on its
#: own, which is the case being measured.
ONE = '{"q": "a", "a": "1"}'
TWO = '{"q": "b", "a": "2"}'
TRIALS = 200


class TheWitnessSaysWhatItCannotSeeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name) / "rows.jsonl"

    def test_the_two_payloads_really_are_the_same_length(self):
        """The instrument before the measurement: if these ever differ in
        length, this file measures the size check and not the clock."""
        self.assertEqual(len(ONE), len(TWO))
        self.assertNotEqual(ONE, TWO)

    def test_a_witness_is_size_and_modification_time_and_nothing_else(self):
        self.file.write_text(ONE, encoding="utf-8")
        witness = build.witness_of(self.file)
        self.assertIn(f"{len(ONE)} bytes", witness)
        self.assertIn("modified", witness)

    def test_a_same_length_rewrite_can_be_invisible(self):
        """THE MEASUREMENT. Not a rate assertion - the rate moves with the
        machine's load - but the existence of the blind spot, which does not."""
        blind = 0
        for trial in range(TRIALS):
            self.file.write_text(ONE if trial % 2 else TWO, encoding="utf-8")
            before = build.witness_of(self.file)
            self.file.write_text(TWO if trial % 2 else ONE, encoding="utf-8")
            if build.witness_of(self.file) == before:
                blind += 1
        self.assertGreater(
            blind,
            0,
            f"0 of {TRIALS} same-length rewrites were invisible to the witness. "
            "Either this machine's clock got finer or the witness got stronger - "
            "if the witness now reads content, rewrite the clause in app/build.py "
            "and retire this file with it.",
        )

    def test_a_changed_length_is_always_seen(self):
        """The half that does work, so the file is not read as an argument
        against the witness."""
        self.file.write_text(ONE, encoding="utf-8")
        before = build.witness_of(self.file)
        self.file.write_text(ONE + "!", encoding="utf-8")
        self.assertNotEqual(build.witness_of(self.file), before)

    def test_the_module_says_this_out_loud(self):
        """The number lives in the docstring a reader actually meets. If the
        two disagree, the documentation is the thing that is wrong."""
        self.assertIn("157 of 200", build.__doc__ or "")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
