"""The three closed lists, measured against sentences a person would type.

MEASURED 2026-09-05 on twenty sentences — ten that should raise a note, ten
that should not. The first run scored **2 misses of 10, 0 false fires of 10**,
and the two misses had different causes:

  * "We fine-tuned a model already …" — the list held `already fine-tuned` and
    the person wrote it in the other word order. A literal list grows by what
    people are observed to write.
  * "My adapter is done. What now?" — the phrase MATCHED and no journey did, so
    `map_the_ask` returned early on the no-match branch and the note never
    attached. The answer was "No journey in the playbook matches those words",
    throwing away the one fact the person had given. Somebody who says they
    have a trained adapter and is told nothing was understood does not say it
    again.

The second is the defect. The first is maintenance, and this file is where the
sentences accumulate.
"""

from __future__ import annotations

import unittest

from app.tools import REGISTRY

MAP = REGISTRY.get("map_the_ask").handler

NO_MATERIAL = "you_said_you_have_no_material"
ALREADY_TRAINED = "you_said_it_is_already_trained"
HAVE_EVAL = "you_said_you_have_the_eval_set"

#: Ten sentences that must raise a note, and which one.
SHOULD_HEAR = [
    ("I want to fine-tune a model but I have no dataset yet.", NO_MATERIAL),
    ("Train a model on my writing. I haven't collected anything yet.", NO_MATERIAL),
    ("I'd like a small model for this, though we don't have data for it.", NO_MATERIAL),
    ("I trained an adapter last week, is it any good?", ALREADY_TRAINED),
    ("We fine-tuned a model already and want to know if it helped.", ALREADY_TRAINED),
    ("My adapter is done. What now?", ALREADY_TRAINED),
    ("My adapter scored 0.62 and I still have the eval set.", HAVE_EVAL),
    ("I have an eval set already, train something better on my files.", HAVE_EVAL),
    ("Use the same eval set as last time and train a new adapter.", HAVE_EVAL),
    ("Train on my files. I still have the baseline run from before.", HAVE_EVAL),
]

#: Ten that must raise none. A false fire is worse than a miss: it tells a
#: person something about themselves that they did not say.
SHOULD_NOT = [
    "I have a folder of support tickets and want the model to answer like our team.",
    "Train a small model on my design system files.",
    "How do I serve a model locally with ollama?",
    "My prompt is too slow and costs too much.",
    "I want to classify incoming emails into four buckets.",
    "Can this machine train a 7B model?",
    "Build me an eval set for a summariser.",
    "I have data and no budget for a bigger GPU.",
    "What does the diagnosis actually check?",
    "Show me which model fits this card.",
]


class TheListsHearWhatWasTypedTest(unittest.TestCase):
    def test_every_sentence_that_should_be_heard_is(self):
        missed = [
            (want, ask) for ask, want in SHOULD_HEAR if want not in MAP(ask=ask)
        ]
        self.assertEqual(missed, [], f"{len(missed)} of {len(SHOULD_HEAR)} missed")

    def test_no_sentence_raises_a_note_nobody_earned(self):
        """A false fire tells a person something about themselves they did not
        say, which is worse than staying quiet."""
        fired = []
        for ask in SHOULD_NOT:
            answer = MAP(ask=ask)
            hit = [k for k in (NO_MATERIAL, ALREADY_TRAINED, HAVE_EVAL) if k in answer]
            if hit:
                fired.append((hit, ask))
        self.assertEqual(fired, [], f"{len(fired)} of {len(SHOULD_NOT)} fired wrongly")

    def test_what_was_heard_survives_a_route_that_did_not_match(self):
        """The defect this file found. The phrase matched, no journey did, and
        the early return threw the fact away."""
        answer = MAP(ask="My adapter is done. What now?")
        self.assertIsNone(answer["matched"])
        self.assertEqual(answer[ALREADY_TRAINED], "my adapter")
        self.assertIn("No route matched, but this much was", answer["what_was_understood"])

    def test_the_no_match_answer_still_lists_the_journeys_that_exist(self):
        """The note is added to that answer, not substituted for it."""
        answer = MAP(ask="My adapter is done. What now?")
        self.assertTrue(answer["journeys_available"])

    def test_a_no_match_with_nothing_heard_says_only_that(self):
        answer = MAP(ask="What is the weather in Toronto?")
        self.assertIsNone(answer["matched"])
        self.assertNotIn("what_was_understood", answer)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
