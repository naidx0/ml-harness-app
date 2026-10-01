"""Every journey is reachable by describing the problem, not by naming the method.

## The stall this exists for

`docs/readiness-rehearsal-2026-09-11.md`, turn 1. A stranger typed a real,
specific description of what they wanted to build, with an example of their own
data in it, and the product's routing tool answered:

    No journey in the playbook matches those words. The journeys that exist:
    train_on_my_files, route_or_classify, make_an_eval, ...

Two turns later the same tool MATCHED on "Should I fine-tune the whole model or
use LoRA?" - on the words `model` and `fine-tune`.

**The playbook matched ML vocabulary rather than what the person wanted to
build.** That is backwards for a product whose whole premise is that a person
should not need the words: somebody who already knows them gets in, and
somebody describing their problem is told to go away and say it differently.

## What this test does, and why it is shaped this way

The subjects are DERIVED FROM THE PLAYBOOK, not listed here by hand. Every
journey the playbook carries must have a plain-English ask in `PLAIN_ENGLISH`
and every ask must route somewhere. A journey added next year with no ask fails
`test_every_journey_has_a_plain_english_ask` rather than quietly having no
front door - which is exactly how this defect survived: nothing required a
route to be reachable in the language people actually use.

**No ask may contain its own journey's name, or `model`, `fine-tune`, `finetune`
or `LoRA`.** Those are the words that made the matcher look like it worked. An
ask containing them would test the keyword list against itself.
"""

from __future__ import annotations

import unittest

import support

from app.tools import knowledge


#: One plain-English ask per journey, written the way somebody who has the
#: problem and not the vocabulary would type it. The first is the sentence
#: from the rehearsal, near enough verbatim.
PLAIN_ENGLISH: dict[str, str] = {
    "train_on_my_files": (
        "I want something that draws system-design JSON graphs from a "
        "description. Here is one example of the output I need."
    ),
    "route_or_classify": (
        "A few hundred support emails come in every day and I want each one put "
        "in the right bucket automatically."
    ),
    "make_an_eval": (
        "How do I tell whether the thing I built is any good, in numbers rather "
        "than by reading answers myself?"
    ),
    "improve_without_training": (
        "The answers are fine but each one takes ten seconds and costs a "
        "fortune. Can I get the same thing cheaper?"
    ),
    "run_locally": (
        "I want this to work on my own laptop, with nothing leaving the "
        "machine."
    ),
    "improve_the_last_run": (
        "The last attempt was not good enough. How do I make the next one "
        "better?"
    ),
}

#: The words that made the matcher look like it worked.
THE_VOCABULARY_A_PERSON_SHOULD_NOT_NEED = ("model", "fine-tune", "finetune", "lora")


class EveryJourneyHasAPlainEnglishDoorTest(unittest.TestCase):
    def setUp(self):
        support.sandbox(self)

    def test_every_journey_has_a_plain_english_ask(self):
        """DERIVED, NOT LISTED. A journey added with no ask has no front door,
        and nothing but this would say so."""
        self.assertEqual(
            set(knowledge.journey_names()),
            set(PLAIN_ENGLISH),
            "a journey exists with no plain-English ask, or an ask names a "
            "journey the playbook no longer has",
        )

    def test_no_ask_leans_on_the_vocabulary_the_product_exists_to_replace(self):
        """An ask containing `fine-tune` tests the keyword list against
        itself."""
        for journey, ask in PLAIN_ENGLISH.items():
            lowered = ask.lower()
            with self.subTest(journey=journey):
                self.assertNotIn(journey.replace("_", " "), lowered)
                self.assertNotIn(journey, lowered)
                for word in THE_VOCABULARY_A_PERSON_SHOULD_NOT_NEED:
                    self.assertNotIn(word, lowered, f"the ask leans on {word!r}")

    def test_every_plain_english_ask_reaches_a_journey(self):
        """THE CASE. Not 'reaches the right one' - reaches ANY one. A person
        who is routed imperfectly can be corrected by the next card; a person
        told nothing matched has nowhere to go."""
        landed_nowhere = [
            journey
            for journey, ask in PLAIN_ENGLISH.items()
            if knowledge.match_journey(ask) is None
        ]
        self.assertEqual(
            [], landed_nowhere,
            "these journeys cannot be reached by describing the problem: "
            + ", ".join(landed_nowhere),
        )

    def test_the_rehearsal_sentence_itself_routes(self):
        """The exact shape from `docs/readiness-rehearsal-2026-09-11.md`, kept
        as its own case so the sentence that found this cannot regress
        quietly."""
        self.assertIsNotNone(
            knowledge.match_journey(
                "What should I do to draw system-design JSON graphs from a "
                "description?"
            )
        )

    def test_a_sentence_about_nothing_this_product_does_still_matches_nothing(self):
        """THE CONTROL, and it is what stops the fix being "match everything".
        A matcher that routed this would have no refusal left, and the refusal
        is what keeps the product from inventing a journey for somebody."""
        self.assertIsNone(
            knowledge.match_journey(
                "What time does the post office close on a Saturday?"
            )
        )


if __name__ == "__main__":
    unittest.main()
