"""There is a journey for "make the next one better", and it was measured in.

MEASURED 2026-09-05, after recording the gap twice without deciding it. Four
ways a person would say the same thing:

    My adapter scored 0.62 and I want the next one to score higher.
    How do I make the next adapter better than the last one?
    The model we trained is not good enough. Make the next one better.
    I want to beat my last score.

**Three of the four matched no journey at all**, and the fourth matched
`train_on_my_files` — the route that builds one from scratch. The one apparent
match found on the improve walk was an accident: that person happened to write
"eval set", and `make_an_eval` won on the single keyword `eval` with no runner
up. Remove the word and nothing matched.

The journey's steps are the tail of `train_on_my_files` — baseline, run, sandbox,
train, score — because that is what beating a score actually is, and because
inventing new steps for it would have been a second way to do the same thing.

WHAT THIS DID NOT FIX, measured and stated rather than tuned away. The sentence
from the improve walk now scores a TIE: `make_an_eval` on `eval`, and
`improve_the_last_run` on `score higher`, one hit each, broken by declaration
order. Adding keywords until the preferred route wins is how a scorer stops
being falsifiable, so the tie stands and is asserted below. The person is not
left unwarned — the closed-list note still tells them not to carve a second
eval set — but the route is decided by list order and that is fragile.
"""

from __future__ import annotations

import unittest

from app.tools import REGISTRY, knowledge

MAP = REGISTRY.get("map_the_ask").handler

#: The four phrasings, all of which matched nothing useful before.
BEATING_A_SCORE = [
    "My adapter scored 0.62 and I want the next one to score higher.",
    "How do I make the next adapter better than the last one?",
    "The model we trained is not good enough. Make the next one better.",
    "I want to beat my last score.",
]

#: Routes that must not move because a sixth journey exists.
UNMOVED = {
    "I have a folder of support tickets and I want the model to answer like our team does.":
        "route_or_classify",
    "I have a folder of my own front-end code and I want a small model that writes UI in my style.":
        "train_on_my_files",
    "Build me an eval set for a summariser.": "make_an_eval",
    "How do I serve a model locally with ollama?": "run_locally",
}


class ThereIsARouteForBeatingAScoreTest(unittest.TestCase):
    def test_every_phrasing_reaches_it(self):
        for ask in BEATING_A_SCORE:
            with self.subTest(ask):
                self.assertEqual(MAP(ask=ask)["matched"], "improve_the_last_run")

    def test_no_other_route_moved(self):
        """A sixth journey that stole traffic would be a worse defect than the
        gap it closed."""
        for ask, expected in UNMOVED.items():
            with self.subTest(ask[:40]):
                self.assertEqual(MAP(ask=ask)["matched"], expected)

    def test_it_says_what_better_means(self):
        """Not "train again" — higher on the rows that produced the number, or
        it is a different question. The improve walk's whole finding."""
        answer = MAP(ask=BEATING_A_SCORE[0])
        self.assertIn("same rows", answer["says"])

    def test_its_steps_are_the_tail_of_the_training_route_not_new_ones(self):
        """Beating a score is measuring, training and scoring again. Inventing
        steps for it would be a second way to do the same thing."""
        tools = [s["tool"] for s in MAP(ask=BEATING_A_SCORE[0])["steps"]]
        self.assertEqual(
            tools,
            ["measure_baseline", "run_eval", "make_sandbox", "run_in_sandbox", "score_the_adapter"],
        )

    def test_the_tie_this_created_is_recorded_rather_than_tuned_away(self):
        """The improve walk's own sentence scores one hit for each of two
        journeys and is decided by declaration order. Asserted so the fragility
        is visible; adding keywords until the preferred route wins is how a
        scorer stops being falsifiable."""
        ask = (
            "My adapter scored 0.62 on my eval set and I want the next one to score "
            "higher. I still have the eval set and the baseline run."
        )
        scored = knowledge._score_journeys(knowledge.load("playbook.json"), ask)
        by_name = {journey["name"]: hits for _, hits, journey in scored}
        self.assertEqual(by_name["make_an_eval"], ["eval"])
        self.assertEqual(by_name["improve_the_last_run"], ["score higher"])
        # And the person is still warned, whichever route wins the tie.
        self.assertIn("do_not_carve_a_second_eval_set", MAP(ask=ask))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
