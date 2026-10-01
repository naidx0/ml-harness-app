"""When two journeys score the same, the answer says so.

MEASURED 2026-09-05 over 28 asks drawn from this repository's own corpora:
exactly one produced a tie, and `sort` broke it by declaration order — which is
not a fact about the sentence somebody typed. Adding a sixth journey created a
second tie a few hours earlier, which is how this got looked at.

WHY NOT A TIEBREAK. Longer keyword, earlier journey, more specific family: each
is defensible and none is measured, and a rule invented to make a preferred
route win is how a scorer stops being falsifiable. Picking is fine. Picking
*silently* was the part that was wrong, so the runner-up goes on the record and
the sentence says the order is not about the ask.
"""

from __future__ import annotations

import unittest

from app.tools import REGISTRY, knowledge

MAP = REGISTRY.get("map_the_ask").handler

#: The ask that ties, found by scoring the corpora rather than by construction.
A_TIE = "Use the same eval set as last time and train a new adapter."


class ATieIsNotAChoiceTest(unittest.TestCase):
    def test_the_runner_up_is_named(self):
        answer = MAP(ask=A_TIE)
        self.assertEqual(answer["matched"], "train_on_my_files")
        self.assertEqual(answer["also_matched"], ["make_an_eval"])

    def test_it_says_the_order_is_not_about_the_ask(self):
        said = MAP(ask=A_TIE)["the_match_was_not_clear_cut"]
        self.assertIn("declared first", said)
        self.assertIn("not a fact about what you asked", said)

    def test_a_clear_cut_ask_carries_no_such_note(self):
        """A note on every answer would be noise, and would stop meaning
        anything on the answers where it matters."""
        answer = MAP(ask="I have a folder of support tickets and I want the model to answer like our team does.")
        self.assertNotIn("also_matched", answer)
        self.assertNotIn("the_match_was_not_clear_cut", answer)

    def test_the_route_is_still_taken(self):
        """Naming the tie must not turn into refusing to answer. The steps are
        still there and still the winner's."""
        answer = MAP(ask=A_TIE)
        self.assertTrue(answer["steps"])
        self.assertEqual(answer["steps"][0]["tool"], "attach_context")

    def test_ties_are_rare_enough_that_the_note_stays_meaningful(self):
        """If most asks tied, the note would be wallpaper. Measured over the
        corpora this repository already keeps: one in twenty-eight."""
        import sys
        sys.path.insert(0, "tests")
        from test_the_closed_lists_hear_what_people_type import SHOULD_HEAR, SHOULD_NOT
        from test_a_route_exists_for_beating_a_score import BEATING_A_SCORE, UNMOVED

        asks = [a for a, _ in SHOULD_HEAR] + list(SHOULD_NOT) + list(BEATING_A_SCORE) + list(UNMOVED)
        book = knowledge.load("playbook.json")
        ties = 0
        for ask in asks:
            scored = knowledge._score_journeys(book, ask)
            scored.sort(key=lambda t: -t[0])
            if len(scored) >= 2 and scored[0][0] == scored[1][0]:
                ties += 1
        self.assertLessEqual(ties, 3, f"{ties} of {len(asks)} asks tie; the note is becoming noise")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
