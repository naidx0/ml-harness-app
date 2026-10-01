"""A skip that says its absence matters must not be summarised as a pass.

MEASURED 2026-09-06, on this lane, in this gate.
`test_no_shipped_file_names_a_person` skipped with:

    no identifier list on this machine, so the personal-identifier rules did not
    run; 4 shape rules did, and they are asserted separately. This is NOT a
    clean bill.

and printed that warning four times. The summary line said `OK (skipped=1)`. I
read the summary, the gate printed GATE IS GREEN, I pushed, and the commit went
red in another checkout on a rule that had never run here.

The check said exactly what it had not done. The summary said OK. **The distance
between a law you wrote and a law you have internalised is one summary line** -
this repository already carried "nothing failed is not nothing was checked, and
the two need different words", authored by this lane about somebody else's
suite.
"""

from __future__ import annotations

import unittest

import support

gate = support.import_file("gate", support.REPO_ROOT / "scripts" / "gate.py")


class AResult:
    """Only what `the_skips_that_matter` reads."""

    def __init__(self, skipped):
        self.skipped = skipped


class AMaterialSkipIsNotAPassTest(unittest.TestCase):
    """THE CASE."""

    THE_REAL_ONE = (
        "no identifier list on this machine, so the personal-identifier rules "
        "did not run; 4 shape rules did, and they are asserted separately. "
        "This is NOT a clean bill."
    )

    def test_the_skip_that_actually_happened_is_caught(self):
        found = gate.the_skips_that_matter(AResult([("a_test", self.THE_REAL_ONE)]))
        self.assertEqual(len(found), 1)

    def test_an_ordinary_skip_is_not_caught(self):
        """A gate that refused every skip would be turned off in a day, and
        platform skips are legitimate."""
        for reason in (
            "not applicable on Windows",
            "no GPU on this machine",
            "the pinned environment is not built",
            "runs/ is gitignored so this checks the real artefact when it exists",
        ):
            with self.subTest(reason=reason):
                self.assertEqual(
                    gate.the_skips_that_matter(AResult([("t", reason)])), []
                )

    def test_the_marker_is_matched_whatever_the_case(self):
        for reason in ("This is NOT a clean bill.", "not a clean bill",
                       "NOT A CLEAN BILL"):
            with self.subTest(reason=reason):
                self.assertEqual(
                    len(gate.the_skips_that_matter(AResult([("t", reason)]))), 1
                )

    def test_several_are_all_reported(self):
        found = gate.the_skips_that_matter(
            AResult([("a", self.THE_REAL_ONE), ("b", "fine"), ("c", "not a clean bill")])
        )
        self.assertEqual(len(found), 2)

    def test_a_result_with_no_skips_attribute_does_not_crash_the_gate(self):
        """Bookkeeping must never decide a verdict, and must never raise into
        one either - the lesson from the line that crashed AFTER printing GATE
        IS GREEN."""
        class Bare:
            pass

        self.assertEqual(gate.the_skips_that_matter(Bare()), [])


class TheSentenceSaysWhatWentWrongTest(unittest.TestCase):
    def test_it_does_not_say_green(self):
        said = gate.why_a_material_skip_is_not_green([("t", "not a clean bill")])
        self.assertNotIn("GATE IS GREEN", said)
        self.assertIn("GATE IS NOT GREEN", said)

    def test_it_names_the_test_and_the_reason(self):
        said = gate.why_a_material_skip_is_not_green(
            [("test_no_shipped_file_names_a_person", "This is NOT a clean bill.")]
        )
        self.assertIn("test_no_shipped_file_names_a_person", said)
        self.assertIn("NOT a clean bill", said)

    def test_it_says_why_a_partial_result_is_not_a_pass(self):
        said = gate.why_a_material_skip_is_not_green([("t", "not a clean bill")])
        self.assertIn("partial result", said)
        self.assertIn("does not speak for it", said)

    def test_it_counts_them(self):
        said = gate.why_a_material_skip_is_not_green(
            [("a", "not a clean bill"), ("b", "not a clean bill")]
        )
        self.assertIn("2 check(s) skipped", said)


class AFreshCloneMustStillBeAbleToPassTest(unittest.TestCase):
    """THE REGRESSION THIS CHECK SHIPPED WITH, for about an hour.

    The first version exited 2 on a material skip. A peer measured what that
    did: a fresh clone has no `identifiers.json` - it is gitignored, and a
    visitor can never legitimately hold a file of somebody's personal
    identifiers - so the skip fires forever and the gate can never be green.
    The suite became structurally un-passable for everyone except this machine,
    and the only two checkouts that could have noticed had both acquired the
    file within the hour.

    The distinction that settles it: "the identifier rules did not run" means
    THIS RUN CANNOT CERTIFY A RELEASE. It does not mean the tests said nothing
    about the tree, and the second is the claim a gate makes.
    """

    def gate_source(self):
        return (support.REPO_ROOT / "scripts" / "gate.py").read_text(encoding="utf-8")

    def test_a_material_skip_does_not_make_the_gate_exit_non_zero(self):
        """A clone must be able to learn that its tests pass."""
        source = self.gate_source()
        after = source[source.index("material = the_skips_that_matter(result)"):]
        branch = after[: after.index("if not result.wasSuccessful():")]
        self.assertNotIn("return 2", branch, "a clone could never be green")

    def test_but_the_verdict_line_is_not_a_bare_pass(self):
        """The qualification goes IN the verdict, not four thousand dots above
        it, which is how `OK (skipped=1)` was read past in the first place."""
        source = self.gate_source()
        self.assertIn("GATE IS GREEN FOR THIS TREE, NOT FOR RELEASE", source)

    def test_the_unqualified_green_still_exists_for_a_complete_run(self):
        """A gate that qualified every run would be as unreadable as one that
        qualified none."""
        self.assertIn('f"GATE IS GREEN: {ran} of {discovered}"', self.gate_source())

    def test_the_refusal_moved_to_the_release_path(self):
        push = (support.REPO_ROOT / "scripts" / "push_if_green.py").read_text(encoding="utf-8")
        self.assertIn("why_this_checkout_cannot_certify_a_release", push)

    def test_the_release_path_refuses_before_spending_a_gate(self):
        """Eight minutes on a suite whose result cannot authorise a push is
        time nobody gets back."""
        push = (support.REPO_ROOT / "scripts" / "push_if_green.py").read_text(encoding="utf-8")
        self.assertLess(
            push.index("uncertifiable = why_this_checkout_cannot_certify_a_release()"),
            push.index("code = the_gate_exit_code(gate_args, run=run)"),
        )

    def test_the_refusal_says_the_gate_is_right_to_be_green(self):
        """So nobody reads it as the tests having failed."""
        push_mod = support.import_file(
            "push_if_green", support.REPO_ROOT / "scripts" / "push_if_green.py"
        )
        said = push_mod.why_this_checkout_cannot_certify_a_release.__doc__
        self.assertIn("not in this working tree", said)


if __name__ == "__main__":
    unittest.main()
