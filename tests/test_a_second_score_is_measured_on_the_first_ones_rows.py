"""Somebody improving on a score is not sent to build a second eval set.

FOUND ON THE IMPROVE WALK. The ask was "My adapter scored 0.62 on my eval set
and I want the next one to score higher. I still have the eval set and the
baseline run." It maps to `make_an_eval`, whose FIRST step is `carve_eval_set`.

The waste is not the point. A newly carved eval set is not the one 0.62 was
measured on, so the next number would not be higher or lower than 0.62 - it
would be about a different question, and nothing downstream could tell the two
apart. `score_the_adapter` is airtight about this at the moment of scoring: it
reuses the baseline run's graded rows, eval file, columns and metric unchanged,
"that is what makes the comparison a comparison". The route was walking the
person past that guarantee before they reached it.

So the answer now says the carving step is not where this starts, and says why
in the product's own rule rather than a new opinion.
"""

from __future__ import annotations

import unittest

from app.tools import REGISTRY, knowledge

MAP = REGISTRY.get("map_the_ask").handler


class ASecondScoreTest(unittest.TestCase):
    ASK = (
        "My adapter scored 0.62 on my eval set and I want the next one to score "
        "higher. I still have the eval set and the baseline run."
    )

    def test_it_says_the_carving_step_is_not_where_this_starts(self):
        answer = MAP(ask=self.ASK)
        self.assertIn("do_not_carve_a_second_eval_set", answer)
        self.assertIn("not where this starts", answer["do_not_carve_a_second_eval_set"])

    def test_it_quotes_the_words_they_used(self):
        self.assertEqual(MAP(ask=self.ASK)["you_said_you_have_the_eval_set"], "still have the eval")

    def test_it_says_why_a_second_eval_set_destroys_the_comparison(self):
        """The reason is the danger. Two numbers on different rows are not a
        comparison, and the second one looks exactly like a result."""
        said = MAP(ask=self.ASK)["the_number_to_beat_is_tied_to_its_eval_set"]
        self.assertIn("same rows", said)
        self.assertIn("cannot be compared", said)

    def test_it_names_the_guarantee_the_product_already_makes(self):
        """Not a new opinion: `score_the_adapter`'s own contract. If that
        contract is ever reworded, this sentence should be reread with it."""
        said = MAP(ask=self.ASK)["the_number_to_beat_is_tied_to_its_eval_set"]
        self.assertIn("score_the_adapter", said)
        for promised in ("graded rows", "eval file", "columns", "metric"):
            with self.subTest(promised):
                self.assertIn(promised, said)

    def test_the_guarantee_it_quotes_is_the_one_the_tool_declares(self):
        """The sentence claims score_the_adapter reuses the baseline's rows
        unchanged. That claim is checked against the tool's own schema rather
        than trusted, so a reworded contract fails here instead of leaving the
        map quoting a promise the product no longer makes."""
        described = REGISTRY.get("score_the_adapter").schema["properties"]["baseline_run_id"][
            "description"
        ]
        self.assertIn("graded rows", described)
        self.assertIn("reused unchanged", described)

    def test_an_ask_with_no_eval_set_in_hand_is_untouched(self):
        answer = MAP(ask="I have a folder of support tickets and I want the model to answer like our team does.")
        self.assertNotIn("do_not_carve_a_second_eval_set", answer)

    def test_a_route_that_does_not_carve_gets_no_such_note(self):
        """Telling somebody not to carve on a route with no carving step would
        be its own confusion."""
        answer = MAP(ask="I still have the eval set. How do I serve this model locally with ollama?")
        carves = any(s.get("tool") == "carve_eval_set" for s in answer.get("steps", []))
        self.assertEqual("do_not_carve_a_second_eval_set" in answer, carves)

    def test_the_phrases_are_a_closed_list(self):
        self.assertIsInstance(knowledge.ALREADY_HAVE_THE_EVAL, tuple)
        for phrase in knowledge.ALREADY_HAVE_THE_EVAL:
            with self.subTest(phrase):
                self.assertEqual(phrase, phrase.lower())
                self.assertNotIn("'", phrase)

    def test_the_three_clauses_do_not_silence_each_other(self):
        """"I trained one, I still have the eval set, and I have no new data"
        is a real sentence. Each note answers a different question."""
        answer = MAP(
            ask="I trained an adapter and I still have the eval set, but I have no data for a second run."
        )
        self.assertIn("you_said_it_is_already_trained", answer)
        self.assertIn("you_said_you_have_the_eval_set", answer)
        self.assertIn("you_said_you_have_no_material", answer)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
