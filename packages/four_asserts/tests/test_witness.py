"""The witness: identity that outlives the bytes, and a denominator on a read."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from four_asserts import counted, read_lines, witness


class WitnessTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def a_file(self, name: str, text: str) -> Path:
        p = self.dir / name
        p.write_text(text, encoding="utf-8")
        return p

    def test_it_says_what_the_artifact_was(self):
        p = self.a_file("rows.jsonl", "one\ntwo\nthree\n")
        w = witness(p)
        self.assertEqual(w.size, p.stat().st_size)
        self.assertEqual(len(w.sha256), 64)
        self.assertTrue(w.whole)
        self.assertIn("all", w.how)

    def test_two_different_files_of_the_same_length_are_told_apart(self):
        """THE CASE A SIZE-AND-TIME STAMP CANNOT SEE. Measured on an ordinary
        filesystem, two different files of the same length written back to back
        produced an identical size-and-mtime stamp in 157 of 200 trials."""
        one = self.a_file("a.jsonl", '{"q": "a", "a": "1"}')
        two = self.a_file("b.jsonl", '{"q": "b", "a": "2"}')
        self.assertEqual(one.stat().st_size, two.stat().st_size)
        self.assertNotEqual(witness(one).sha256, witness(two).sha256)
        self.assertFalse(witness(one).same_as(witness(two)))

    def test_the_witness_outlives_the_file(self):
        """The point of keeping it: a record can still say what it was about
        after the bytes are gone."""
        p = self.a_file("gone.jsonl", "some rows\n")
        kept = witness(p)
        p.unlink()
        self.assertFalse(p.exists())
        self.assertEqual(len(kept.sha256), 64)
        self.assertIn("gone.jsonl", kept.how)

    def test_the_same_bytes_witness_the_same(self):
        one = self.a_file("a.txt", "identical")
        two = self.a_file("b.txt", "identical")
        self.assertTrue(witness(one).same_as(witness(two)))

    def test_a_partial_witness_says_so_and_refuses_to_be_an_identity(self):
        """A prefix hash is evidence about a prefix. Two agreeing prefixes are
        not the same artifact, and this refuses to say they are."""
        p = self.a_file("big.txt", "x" * 5000)
        part = witness(p, limit_bytes=100)
        self.assertFalse(part.whole)
        self.assertEqual(part.read_bytes, 100)
        self.assertEqual(part.size, 5000)
        self.assertIn("first 100 of 5000", part.how)
        self.assertFalse(part.same_as(witness(p)))
        self.assertFalse(part.same_as(part))

    def test_a_read_carries_its_denominator(self):
        """'The log shows no errors' means one thing over 200 lines of 200 and
        another over 200 of 60,000."""
        p = self.a_file("log.txt", "\n".join(str(n) for n in range(500)))
        some = read_lines(p, limit=10)
        self.assertEqual(len(some.lines), 10)
        self.assertEqual(some.total, 500)
        self.assertEqual(some.n_of_m, "10 of 500")
        self.assertFalse(some.whole)

    def test_a_whole_read_says_it_is_whole(self):
        p = self.a_file("small.txt", "a\nb\nc")
        all_of_it = read_lines(p)
        self.assertEqual(all_of_it.n_of_m, "3 of 3")
        self.assertTrue(all_of_it.whole)

    def test_a_read_carries_the_witness_of_what_it_read(self):
        p = self.a_file("rows.txt", "a\nb\n")
        self.assertEqual(read_lines(p).witness.sha256, witness(p).sha256)

    def test_a_counted_measurement_names_its_subject(self):
        p = self.a_file("rows.jsonl", "a\nb\nc\n")
        said = counted(3, witness(p), what="rows")
        self.assertIn("counted 3 rows", said)
        self.assertIn("sha256", said)
        self.assertIn("rows.jsonl", said)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
