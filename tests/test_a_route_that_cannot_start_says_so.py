"""Somebody who says they have no material is told the route cannot start.

FOUND ON THE NO-DATA WALK. The ask was "I want to fine-tune a model so it
writes product copy in our brand voice. I don't have a dataset yet." It mapped
to `train_on_my_files`, whose first step is "record where your material lives",
and nothing anywhere said that could not happen. The keywords that matched were
`fine-tune` and `model`; the clause saying there was nothing to point at was
not weighed at all.

WHAT THIS DOES NOT DO, and the restraint is the point. It does not choose a
different goal for them - the route they asked for is still the route they
asked for. It does not invent a dataset, synthesise a stand-in, or offer a
proxy measurement. It says the route cannot start yet, quotes the words they
used to say so, and names what would make it passable: the eval set, which is
both the material the route needs and the definition of "good" that G0 asks
for.

The instruction it gives is the one `BLOCKED__DEFINE_SUCCESS_FIRST` already
gives. Two different first instructions for one situation would be the product
disagreeing with itself, so the sentence is shared deliberately.
"""

from __future__ import annotations

import unittest

from app.tools import REGISTRY, knowledge

MAP = REGISTRY.get("map_the_ask").handler


class ARouteWithNothingToStandOnTest(unittest.TestCase):
    #: The exact sentence from the walk.
    ASK = (
        "I want to fine-tune a model so it writes product copy in our brand "
        "voice. I don't have a dataset yet."
    )

    def test_it_says_the_route_cannot_start(self):
        answer = MAP(ask=self.ASK)
        self.assertIn("route_cannot_start_yet", answer)
        self.assertIn("cannot start yet", answer["route_cannot_start_yet"])

    def test_it_quotes_the_words_they_used(self):
        """Quoting them back is not the same as asserting something about
        them. The phrase is returned rather than a boolean for that reason."""
        answer = MAP(ask=self.ASK)
        self.assertEqual(answer["you_said_you_have_no_material"], "dont have a dataset")

    def test_it_names_what_would_make_the_route_passable(self):
        answer = MAP(ask=self.ASK)
        passable = answer["what_makes_it_passable"]
        self.assertIn("20 to 30 examples", passable)
        self.assertIn("G0_EVAL_SET", passable)
        self.assertIn("make_an_eval", passable)

    def test_it_does_not_choose_a_different_goal_for_them(self):
        """The route they asked for is still the route. Silently switching a
        person's goal because their inputs are missing is a different product
        than one that tells them what is missing."""
        self.assertEqual(MAP(ask=self.ASK)["matched"], "train_on_my_files")
        self.assertTrue(MAP(ask=self.ASK)["steps"])

    def test_it_offers_no_dataset_and_no_proxy(self):
        """Nothing in the answer suggests generating, simulating or standing in
        for the material. This is the sentence a person is most likely to be
        talked out of by a helpful-sounding model."""
        answer = MAP(ask=self.ASK)
        # Scoped to the sentences this fix adds. The route LISTING legitimately
        # names synthesize_rows, which is a real step of that journey; what
        # must offer no proxy is what the product says to this person now.
        said = " ".join(
            str(answer.get(k, ""))
            for k in ("route_cannot_start_yet", "what_makes_it_passable", "summary")
        ).lower()
        for forbidden in ("generate a dataset", "sample dataset", "public dataset",
                          "stand-in", "proxy", "synthesize your"):
            with self.subTest(forbidden):
                self.assertNotIn(forbidden, said)
        self.assertIn("stand in for material you do not have", said)

    def test_it_closes_the_door_the_route_itself_leaves_open(self):
        """The route contains `synthesize_rows`, described as "data generation:
        amplify the training half". It resamples rows that already exist and
        copies their answers verbatim, so with nothing to sample it produces
        nothing - but a person who has just said they have no data can read
        that step as the harness offering to make the first examples. The one
        moment not to leave that open is this one."""
        answer = MAP(ask=self.ASK)
        said = answer["synthesis_is_not_a_first_dataset"]
        self.assertIn("produces nothing", said)
        self.assertIn("have to be real", said)

    def test_that_door_is_only_closed_when_the_route_has_that_step(self):
        """Naming a step a route does not contain would be its own confusion."""
        answer = MAP(ask="I don't have a dataset. Help me build an eval set.")
        has_step = any(s.get("tool") == "synthesize_rows" for s in answer.get("steps", []))
        self.assertEqual("synthesis_is_not_a_first_dataset" in answer, has_step)

    def test_the_summary_leads_with_the_blocker(self):
        """A summary that led with the match would bury the one thing that
        changes what they do next."""
        summary = MAP(ask=self.ASK)["summary"]
        self.assertIn("cannot start yet", summary)

    def test_an_ask_that_has_material_is_untouched(self):
        answer = MAP(ask="I have a folder of support tickets and I want the model to answer like our team does.")
        self.assertNotIn("route_cannot_start_yet", answer)
        self.assertNotIn("you_said_you_have_no_material", answer)

    def test_the_phrases_are_a_closed_list_matched_literally(self):
        """Not a model's judgement about whether somebody has data. A wrong
        guess here sends a person down a route whose first step asks for a
        folder that does not exist."""
        self.assertIsInstance(knowledge.NO_MATERIAL_YET, tuple)
        for phrase in knowledge.NO_MATERIAL_YET:
            with self.subTest(phrase):
                self.assertEqual(phrase, phrase.lower())
                self.assertNotIn("'", phrase, "apostrophes are stripped before matching")

    def test_curly_and_straight_apostrophes_read_the_same(self):
        straight = MAP(ask="Fine-tune a model on my voice. I don't have data.")
        curly = MAP(ask="Fine-tune a model on my voice. I don’t have data.")
        self.assertIn("route_cannot_start_yet", straight)
        self.assertIn("route_cannot_start_yet", curly)

    def test_a_sentence_about_something_else_being_absent_is_not_caught(self):
        """The list is specific so ordinary sentences do not trip it."""
        answer = MAP(ask="I have data and no budget for a bigger GPU. Train a small model on my files.")
        self.assertNotIn("route_cannot_start_yet", answer)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
