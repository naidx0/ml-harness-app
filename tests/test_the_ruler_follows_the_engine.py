"""The detector that scores the recital must not be a list of words.

## Why this file exists, which is that the last ruler was wrong and nobody knew

`scripts/did_it_answer_the_question.py` is the bank and the driver for Max's
oldest complaint: he asks the product a question and gets the engine's gate
material back. The fix before this one was measured with `GATE_WORDS` - a
hand-written list of strings: `G0_EVAL_SET`, `NOT_REACHED`, `gates 0 of`,
`define success`.

**That list was written against the wording the fix had just removed.** So it
went on reporting a shape that had already changed clothes. Re-measured on 125
live non-training turns at 3966702:

    a reader, going through every reply        15 of 125   (12%)
    the lookup that replaced it                13 of 125, 13 of them right
    `GATE_WORDS`                                7 of 125,  6 of them right

A detector written against the shape you just fixed will always say you fixed
it. That is not a bug in the list; it is what a vocabulary IS.

## The property under test, and it is one sentence

**The detector's vocabulary comes from the engine at run time, so a change to
the engine's wording changes what it looks for, with nothing in the script to
edit.** That is checkable rather than argued: hand it a sentence the engine has
never said, and it must find a recital of THAT sentence. `GATE_WORDS` cannot,
by construction, and the second test says so with the same input, so the
contrast is a fact in the suite rather than a paragraph in a docstring.

Nothing here asserts a live number. Live numbers are in the driver's own
docstring and in `conductor.constant_record`; what is asserted here is the
mechanism that makes a re-measurement mean anything.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

import support  # noqa: F401 - imported for the fence it installs on import

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "did_it_answer_the_question.py"

_spec = importlib.util.spec_from_file_location("did_it_answer", SCRIPT)
ruler = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ruler)


#: A verdict sentence this engine has never produced and never will. Every word
#: in it is absent from `GATE_WORDS`, and that is the whole point of the
#: fixture: it stands in for the engine's wording AFTER the next fix moves it.
INVENTED = (
    "STALLED - STALLED__NO_TARGET_METRIC. There is no number to aim at, so "
    "every later comparison is a matter of opinion. Name the metric."
)


class ItIsALookupNotAVocabularyTest(unittest.TestCase):
    """Hand it a sentence nobody wrote down, and it still finds the recital."""

    def test_it_catches_a_recital_of_a_sentence_it_has_never_seen(self):
        reply = (
            "I cannot get anywhere with this yet. There is no number to aim "
            "at, so every later comparison is going to be a matter of "
            "opinion. Please name the metric you want me to optimise."
        )
        found = ruler.recites_the_engine(reply, [INVENTED])
        self.assertIsNotNone(found, "the lookup missed a near-verbatim recital")
        self.assertEqual(found["sentence"], INVENTED)

    def test_the_list_it_replaced_cannot(self):
        """THE CONTRAST, ASSERTED RATHER THAN DESCRIBED. Same reply, same
        defect, and the old detector is silent - because nothing in it names a
        word this engine had not already said when somebody typed it out."""
        reply = (
            "I cannot get anywhere with this yet. There is no number to aim "
            "at, so every later comparison is going to be a matter of "
            "opinion. Please name the metric you want me to optimise."
        )
        self.assertFalse(
            any(word in reply.lower() for word in ruler.GATE_WORDS),
            "the fixture must be invisible to the old list, or it proves nothing",
        )

    def test_it_is_silent_on_an_answer_that_owes_the_engine_nothing(self):
        reply = (
            "LoRA is Low-Rank Adaptation. The base weights are frozen and two "
            "small low-rank matrices are trained per layer, so the adapter is "
            "a few megabytes instead of a few gigabytes."
        )
        self.assertIsNone(ruler.recites_the_engine(reply, [INVENTED]))

    def test_an_empty_reply_recites_nothing(self):
        self.assertIsNone(ruler.recites_the_engine("", [INVENTED]))
        self.assertIsNone(ruler.recites_the_engine("   ", [INVENTED]))

    def test_a_needle_too_short_to_be_evidence_is_not_used(self):
        """Two keys out of three is a coincidence. The coverage arm needs a
        sentence with something in it; the order arm still applies."""
        self.assertIsNone(ruler.recites_the_engine("the good part", ["good part"]))


class WhereTheSentencesComeFromTest(unittest.TestCase):
    """Off the engine's own payload, through `conductor.verdict_sentence`."""

    def test_it_takes_the_sentence_the_id_and_the_say(self):
        from app import conductor

        payload = {
            "verdict": "STALLED",
            "outcome": "STALLED__NO_TARGET_METRIC",
            "say": "Name the metric.",
        }
        said = ruler._said(payload, conductor)
        self.assertIn(conductor.verdict_sentence(payload), said)
        self.assertIn("STALLED__NO_TARGET_METRIC", said)
        self.assertIn("Name the metric.", said)

    def test_a_walk_with_no_say_contributes_what_it_has(self):
        from app import conductor

        said = ruler._said({"verdict": "BLOCKED", "outcome": "X__Y"}, conductor)
        self.assertIn("X__Y", said)
        self.assertTrue(all(item for item in said), "a blank string is not a needle")


class FishersExactIsExactTest(unittest.TestCase):
    """The p values this project publishes are computed here, with `math.comb`
    and no dependency. These three are the ones already in the tree, so a
    change to the implementation has to reproduce the numbers the last agent
    reported or be caught doing something else."""

    def test_it_reproduces_the_committed_numbers(self):
        self.assertAlmostEqual(ruler.fisher(15, 125, 6, 134), 0.0673, places=4)
        self.assertAlmostEqual(ruler.fisher(121, 19, 126, 14), 0.4589, places=4)
        self.assertAlmostEqual(ruler.fisher(17, 11, 85, 7), 0.000195, places=6)

    def test_a_table_with_no_difference_is_p_one(self):
        self.assertAlmostEqual(ruler.fisher(10, 10, 10, 10), 1.0, places=9)


class TheBankKeepsItsRegressionRowsTest(unittest.TestCase):
    """MAX'S FOUR PHRASINGS, VERBATIM, GRADED ON THE ENGINE BEING REACHED.

    They have been traded away twice by fixes to their neighbours. A bank that
    quietly loses them, or grades them on a keyword like every other row, stops
    being able to see it happen.
    """

    def test_the_four_training_rows_are_there_and_carry_no_keywords(self):
        training = [row for row in ruler.BANK if row.kind == "training"]
        self.assertEqual(len(training), 4)
        for row in training:
            self.assertEqual(row.needs, (), f"{row.name} is graded on words")

    def test_a_training_row_is_answered_when_the_engine_was_reached(self):
        graded = ruler.grade(
            {
                "conversation": "would_training_help",
                "kind": "training",
                "prose": "Some words that match no keyword in the bank.",
                "tools": ["run_diagnosis"],
                "verdicts": [],
                "engine_said": [],
            }
        )
        self.assertTrue(graded["answered"])
        self.assertFalse(graded["empty"])

    def test_a_two_part_row_needs_both_halves(self):
        """The training half crowding out the other one is the whole kind."""
        only_training = ruler.grade(
            {
                "conversation": "train_and_lora",
                "kind": "two_part",
                "prose": "Let me run the diagnosis before we decide anything.",
                "tools": ["run_diagnosis"],
                "verdicts": [],
                "engine_said": [],
            }
        )
        self.assertFalse(only_training["answered"], "it never said what LoRA is")

        both = ruler.grade(
            {
                "conversation": "train_and_lora",
                "kind": "two_part",
                "prose": "LoRA is a low-rank adapter. And on training: ",
                "tools": ["run_diagnosis"],
                "verdicts": [],
                "engine_said": [],
            }
        )
        self.assertTrue(both["answered"])


if __name__ == "__main__":
    unittest.main()
