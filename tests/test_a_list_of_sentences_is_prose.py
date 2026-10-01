"""A list of sentences is prose. A list of terms is tags.

MEASURED 2026-09-21 on Max's ML-principles eval set. `grade_fields` decided
which lists to grade by the LENGTH of their entries, at 48 characters, and that
cut ran straight through the middle of two fields: `pitfalls` was graded as
verbatim-match tags on 30 of 40 rows and ignored as prose on the other 10,
purely because of how long each sentence happened to be. 40% of every list
entry the metric demanded verbatim was a whole sentence - 'Optimizing train
loss alone can hide overfitting' - which no model reproduces except by having
been trained on that exact phrasing.

With the output contract stated in the prompt, the same 40 answers scored 1/40
under the length rule and 7/40 under this one. The 16 points were never the
model's to earn.
"""
from __future__ import annotations

import json
import unittest

import support  # noqa: F401  - puts the repo root on the path

from app.tools import measure


class ASentenceIsNotATagTest(unittest.TestCase):
    def test_a_list_of_terms_is_graded(self):
        self.assertTrue(measure._is_tag_list(["loss", "cross-entropy", "mse"]))

    def test_a_multi_word_term_is_still_a_term(self):
        """Length was the old rule and it got these wrong in both directions."""
        for term in ("mixture of experts", "learning rate schedule",
                     "scaled dot-product attention", "held-out validation"):
            with self.subTest(term=term):
                self.assertTrue(measure._is_tag_list([term]))

    def test_a_list_of_sentences_is_not_graded(self):
        for sentence in ("Optimizing train loss alone can hide overfitting",
                         "Apply mask if needed, then softmax.",
                         "Use MSE or MAE for continuous regression targets."):
            with self.subTest(sentence=sentence):
                self.assertFalse(measure._is_tag_list([sentence]))

    def test_one_sentence_makes_the_whole_list_prose(self):
        """The list is one field. It gets one ruler, not a ruler per entry."""
        self.assertFalse(measure._is_tag_list(["loss", "Always track validation loss."]))

    def test_prose_lands_in_free_text_rather_than_disagreeing(self):
        """THE POINT. Free text never decides, so a sentence list that does not
        match can no longer fail the row - it abstains."""
        expected = json.dumps({
            "task_type": "concept",
            "principles": ["loss", "cross-entropy"],
            "pitfalls": ["Optimizing train loss alone can hide overfitting"],
        })
        answer = json.dumps({
            "task_type": "concept",
            "principles": ["loss", "cross-entropy"],
            "pitfalls": ["Watching only the training curve hides overfitting"],
        })
        graded = measure.grade_fields(expected, answer)
        self.assertIn("pitfalls", graded["free_text"])
        self.assertNotIn("pitfalls", graded["disagreed"])
        self.assertTrue(graded["correct"])

    def test_a_term_list_that_disagrees_still_fails(self):
        """The fix must not turn the metric into a rubber stamp."""
        expected = json.dumps({"principles": ["loss", "cross-entropy", "mse", "adam"]})
        answer = json.dumps({"principles": ["dropout", "batch norm", "relu", "sgd"]})
        graded = measure.grade_fields(expected, answer)
        self.assertIn("principles", graded["disagreed"])
        self.assertFalse(graded["correct"])


if __name__ == "__main__":
    unittest.main()
