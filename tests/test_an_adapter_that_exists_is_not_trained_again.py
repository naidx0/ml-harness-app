"""Somebody holding a finished adapter is not handed the recipe for making one.

FOUND ON THE ADAPTER WALK. The ask was "I trained an adapter last week and I
want to know if it is any good. It is in runs/.../run_4/adapter". It mapped to
`train_on_my_files` - seventeen steps that begin by carving rows and end by
training an adapter. The words `trained` and `model` were weighed; "I trained
... last week", meaning it is already done, was not. A person holding the
finished thing was handed the instructions for making another one.

This is the same shape as the no-data walk and it is fixed in the same place
and with the same restraint: the route is still their goal, because "is it any
good" IS a question about a trained model. What changes is that the answer says
the early steps are not where this starts, and names what is actually missing -
the eval set and the baseline, without which "any good" has no answer.

THE THRESHOLD IS READ FROM THE LEDGER, NOT TYPED. `G0_EVAL_SET`'s rule is
`eval_size_n >= 30` today and the number is the ledger's to change. A sentence
that hardcoded 30 would go quietly wrong the day it moved - the mistake the
no-verdict card nearly shipped with "0 of 5 gates reached", where five is true
of one ledger and false of another.
"""

from __future__ import annotations

import unittest

from app import diagnosis
from app.tools import REGISTRY, knowledge

MAP = REGISTRY.get("map_the_ask").handler


class AFinishedAdapterTest(unittest.TestCase):
    ASK = (
        "I trained an adapter last week and I want to know if it is any good. "
        "It is in runs/d3b225bb983a42389ac896d894f19017/sandboxes/practical-ml/"
        "runs/run_4/adapter"
    )

    def test_it_says_the_early_steps_are_not_where_this_starts(self):
        answer = MAP(ask=self.ASK)
        self.assertIn("you_may_not_need_the_early_steps", answer)
        self.assertIn("already exists", answer["you_may_not_need_the_early_steps"])

    def test_it_quotes_the_words_they_used(self):
        self.assertEqual(MAP(ask=self.ASK)["you_said_it_is_already_trained"], "i trained")

    def test_it_does_not_choose_a_different_goal_for_them(self):
        """The route is still the route. "Is it any good" is a question about a
        trained model, and the steps that answer it are the ones near the end."""
        answer = MAP(ask=self.ASK)
        self.assertEqual(answer["matched"], "train_on_my_files")
        self.assertTrue(answer["steps"])

    def test_it_names_the_eval_set_the_baseline_and_the_path_that_scores(self):
        needs = MAP(ask=self.ASK)["what_scoring_needs"]
        self.assertIn("eval set", needs)
        self.assertIn("G0_EVAL_SET", needs)
        self.assertIn("baseline", needs)
        self.assertIn("make_an_eval", needs)
        # The path the scoring actually goes through, named so they can find it.
        self.assertIn("score_the_adapter", needs)
        self.assertIn("adapter_dir", needs)

    def test_the_threshold_comes_from_the_ledger_rather_than_this_file(self):
        """If the ledger's rule changes, this sentence changes with it. A test
        that asserted the literal "30" would pass while the product told people
        a number the engine no longer applies."""
        rule = diagnosis.load_spec().gate_row("G0_EVAL_SET", "any")["requires"]
        self.assertIn(rule, MAP(ask=self.ASK)["what_scoring_needs"])

    def test_it_says_the_denominator_is_what_later_numbers_are_quoted_over(self):
        self.assertIn("denominator", MAP(ask=self.ASK)["what_scoring_needs"])

    def test_an_ask_with_no_finished_adapter_is_untouched(self):
        answer = MAP(ask="I have a folder of support tickets and I want the model to answer like our team does.")
        self.assertNotIn("you_said_it_is_already_trained", answer)
        self.assertNotIn("what_scoring_needs", answer)

    def test_a_route_that_does_not_train_gets_no_such_note(self):
        """Telling somebody the training steps are unnecessary on a route that
        has none would be its own confusion."""
        answer = MAP(ask="I trained a model already. How do I serve it locally with ollama?")
        trains = any(
            step.get("tool") in {"run_in_sandbox", "synthesize_rows"}
            for step in answer.get("steps", [])
        )
        self.assertEqual("you_may_not_need_the_early_steps" in answer, trains)

    def test_the_phrases_are_a_closed_list(self):
        self.assertIsInstance(knowledge.ALREADY_TRAINED, tuple)
        for phrase in knowledge.ALREADY_TRAINED:
            with self.subTest(phrase):
                self.assertEqual(phrase, phrase.lower())
                self.assertNotIn("'", phrase)

    def test_both_clauses_can_be_true_at_once(self):
        """"I trained one but I have no data to test it on" is a real sentence,
        and neither note should silence the other."""
        answer = MAP(ask="I trained an adapter but I have no dataset to test it on.")
        self.assertIn("you_said_it_is_already_trained", answer)
        self.assertIn("route_cannot_start_yet", answer)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
