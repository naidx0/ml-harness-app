"""A green verdict carries what did NOT run, and whether the tree held still.

TWO GAPS FOUND THE SAME EVENING, both by a lane reading a summary line.

A SKIP IS A PARTIAL RESULT WEARING A PASS. The other lane shipped a red commit
because `test_no_shipped_file_names_a_person` skipped its identifier half: the
denylist is gitignored, gitignored files live in a WORKING TREE, and a worktree
does not have one. Verified - the file exists in this checkout and is absent
from theirs, so the same commit was green there and red here with no difference
in the code. The test said the right thing, four times:

    "no identifier list on this machine, so the personal-identifier rules did
     not run; 4 shape rules did ... This is NOT a clean bill."

and the line that got read was `OK (skipped=1)`. This repository already carries
the law that nothing failed is not nothing was checked. The words existed; the
place they were printed was not the place anybody looks. So the reasons come to
the verdict - distinct reasons with counts, because 56 lines is noise and 5 is a
sentence.

AND NOTHING SERIALISES A PERSON EDITING A FILE AGAINST A SUITE READING IT. The
machine lock stops two suites colliding and says nothing about an edit landing
in the middle of one. I saved a docs file while a gate was running on that tree
- the exact interference the lock exists to prevent, by the lane that spent the
day narrowing it - and the other lane has done the same twice, both times
caught by re-gating out of habit rather than by anything stopping them.

WHY IT REFUSES RATHER THAN REPORTS. It was drafted report-only and the other
lane argued it down, which is why it was asked before it had a history. The
case for reporting: a detector that turns a green run red on an unmeasured
signal is one somebody disables. The case that won: the signal is not
unmeasured - both lanes did it today - and a green run whose tree changed
underneath it is not a weaker green, it is a category error. Reporting it
while exiting 0 teaches a reader the line is advisory, which is precisely
how OK (skipped=1) got read past a message saying NOT a clean bill four
times the same evening.

"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("gate_qualifications", REPO / "scripts" / "gate.py")
gate = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules[_spec.name] = gate
_spec.loader.exec_module(gate)


class ASkipIsNotAPassTest(unittest.TestCase):
    def test_reasons_are_counted_not_listed_one_per_test(self):
        said = gate.what_the_skips_were(
            [(None, "no identifier list on this machine, so the rules did not run")] * 40
            + [(None, "needs a GPU")] * 16
        )
        self.assertEqual(len(said), 2, "56 skips should be 2 lines, not 56")
        self.assertIn("40", said[0])
        self.assertIn("identifier list", said[0])

    def test_the_loudest_reason_comes_first(self):
        said = gate.what_the_skips_were(
            [(None, "rare")] + [(None, "common")] * 5
        )
        self.assertIn("common", said[0])

    def test_a_skip_with_no_reason_still_appears(self):
        """A skip that says nothing is the worst kind and must not vanish."""
        said = gate.what_the_skips_were([(None, ""), (None, None)])
        self.assertEqual(len(said), 1)
        self.assertIn("no reason given", said[0])

    def test_a_multi_line_reason_is_reduced_to_its_first_line(self):
        """The real one is a paragraph; the verdict is not the place for it."""
        reason = "the rules did not run" + chr(10) + "and here is a long explanation"
        said = gate.what_the_skips_were([(None, reason)])
        self.assertEqual(len(said), 1)
        self.assertNotIn("long explanation", said[0])

    def test_no_skips_says_nothing_at_all(self):
        self.assertEqual(gate.what_the_skips_were([]), [])


class TheTreeHeldStillTest(unittest.TestCase):
    def test_it_cannot_decide_when_git_cannot_answer(self):
        """None is 'cannot decide', never 'unchanged' - the HEAD check's rule."""

        class Failed:
            returncode = 1
            stdout = ""

        self.assertIsNone(gate.the_tracked_files_now(run=lambda *a, **k: Failed()))

        def explodes(*_a, **_k):
            raise OSError("no git here")

        self.assertIsNone(gate.the_tracked_files_now(run=explodes))

    def test_untracked_files_are_not_asked_about(self):
        """The suite creates scratch files inside the checkout on purpose. A
        detector that fired on those would be switched off within a day."""
        seen = {}

        class Answered:
            returncode = 0
            stdout = ""

        def remember(argv, **_k):
            seen["argv"] = argv
            return Answered()

        gate.the_tracked_files_now(run=remember)
        self.assertIn("--untracked-files=no", seen["argv"])

    def test_the_message_names_what_changed(self):
        said = gate.why_the_tree_moved_under_the_run("", " M docs/how-to-verify.md")
        self.assertIn("docs/how-to-verify.md", said)
        self.assertIn("no longer exists", said)

    def test_a_long_list_is_truncated_rather_than_dumped(self):
        after = chr(10).join(f" M file_{n}.py" for n in range(40))
        said = gate.why_the_tree_moved_under_the_run("", after)
        self.assertIn("...", said)
        self.assertLessEqual(said.count(" M file_"), 10)

    def test_it_does_not_carry_a_typed_escape(self):
        """THIS FUNCTION COST A SYNTAX ERROR TO A TYPED ESCAPE while it was
        being written, which is the tenth time this tree has lost something
        that way. The separator is built from `chr(10)`, and the proof is that
        the output contains real newlines rather than two characters."""
        said = gate.why_the_tree_moved_under_the_run("", " M one.py" + chr(10) + " M two.py")
        self.assertIn(chr(10), said)
        self.assertNotIn(chr(92) + "n", said)


    def test_a_moved_tree_refuses_and_says_so_before_the_verdict(self):
        """The whole point of making it red: a run whose tree changed must not
        print GATE IS GREEN first and qualify itself afterwards. That is the
        green-lie shape, and this repository lost a full suite to it today."""
        import io
        import tempfile as _tempfile
        from contextlib import redirect_stdout, redirect_stderr

        real = gate.the_tracked_files_now
        answers = iter([" M docs/a.md", " M docs/a.md" + chr(10) + " M docs/b.md"])
        gate.the_tracked_files_now = lambda *a, **k: next(answers)
        self.addCleanup(lambda: setattr(gate, 'the_tracked_files_now', real))

        tiny = unittest.TestSuite([_OnePassingTest('test_it_passes')])
        was = unittest.defaultTestLoader.discover
        unittest.defaultTestLoader.discover = lambda *a, **k: tiny
        try:
            with _tempfile.TemporaryFile('w+', encoding='utf-8') as out, \
                 _tempfile.TemporaryFile('w+', encoding='utf-8') as err:
                with redirect_stdout(out), redirect_stderr(err):
                    code = gate._run_the_suite([], 0, None)
                out.seek(0), err.seek(0)
                said, grumbled = out.read(), err.read()
        finally:
            unittest.defaultTestLoader.discover = was

        self.assertEqual(code, 2, 'a moved tree did not refuse')
        self.assertNotIn('GATE IS GREEN', said,
                         'it printed a verdict and then took it back')
        self.assertIn('docs/b.md', grumbled)


class _OnePassingTest(unittest.TestCase):
    """A one-test suite for the case above. Not a check of anything."""

    def test_it_passes(self):
        self.assertTrue(True)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
