"""An arm that does not name its model cannot be paired against another one.

## Why this file exists

Kill 13 paired `run 1`'s LoRA adapter against a naming-rule baseline and
returned NOT PUBLISHABLE on coverage. Reading it afterwards, the research lane
filed a refusal - **the two arms must share a base model, or the comparison
moves two things at once** - and then could not enforce it. The adapter arm was
`Qwen2.5-Coder-1.5B-Instruct`; the baseline arm was `minicpm5-hermes`; and the
only place that second fact was ever written was the prose of a commit message.

**Neither artefact carried a `model` field.** So the one fact the refusal turned
on could be checked against nothing. That is the citation-that-resolves fault
one level down: the hash was fine, the artefacts were fine, and the claim beside
them had never been in a file.

## What is asserted, and why it is asserted against the source

Both writers are I/O over a live connection or a loaded model, and neither can
be exercised here without one. So this reads the source and asserts the field is
written - the same shape as
`test_training_refuses_data_that_leaks_into_the_eval_set`'s assertions about
`"leakage": leakage`. It is a weaker check than running the writer and it is the
check available; what it does catch is the field being dropped, which is the way
this fails in practice.

**The cost of not having this is asymmetric.** It is one key in a dict now, and
after the same-base arm runs it is a re-run of the only comparison that answers
whether fine-tuning helped - because that arm's entire meaning is *which model
produced it*.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


class TheBaselineArtefactNamesItsModelTest(unittest.TestCase):
    """`measure_baseline` writes the rows every later pairing reads."""

    def setUp(self) -> None:
        self.source = (REPO / "app" / "tools" / "measure.py").read_text(encoding="utf-8")

    def test_the_row_carries_the_model(self):
        self.assertIn(
            '"model": str(row["model"])', self.source,
            "a baseline artefact no longer records which model answered, so "
            "anything paired against it later rests on a sentence somewhere "
            "outside the file.")

    def test_the_row_carries_the_eval_file_s_own_id(self):
        """`row_index` IS POSITIONAL, AND A SCORER READS IT AS AN ID.

        It counts eligible rows from zero. An eval set numbered from 100 and
        a predictions file numbered from 0 have matching COUNTS, so a
        positional join succeeds and produces a table that looks entirely
        reasonable about the wrong questions - measured on a real run.

        Carrying the source row's own id changes neither convention and makes
        that impossible to do by accident.
        """
        self.assertIn('"row_id": row_id', self.source,
                      "a baseline artefact no longer records the eval file's "
                      "own id, so anything scoring it must infer which "
                      "question each answer was for.")

    def test_an_id_is_never_invented(self):
        """Only when the source row HAD one.

        Writing `row_id = index` for a file that has no ids would make the
        positional and declared conventions indistinguishable - which is the
        fault this field exists to end, not to hide.
        """
        self.assertIn('if row_id is not None else {}', self.source,
                      "an id is written unconditionally, so a positional "
                      "index can now masquerade as a declared id.")

    def test_it_is_written_beside_the_answer_and_not_only_in_a_summary(self):
        """A run-level summary is not enough: files get split and concatenated.

        The naming-rule baseline was TWO files scored against two references,
        and they were nearly welded into one table. A per-row field survives
        that; a header does not.
        """
        #: THE WHOLE RECORD, FOUND BY MATCHING ITS BRACES. This used to take
        #: a fixed 1,400 characters from the start of the row, and the first
        #: comment added above `"model"` pushed it out of the window - so the
        #: test failed on a field that had not moved. A fixed-width window is
        #: a check that depends on how much prose sits inside what it reads.
        row_start = self.source.find('"row_index": index,')
        self.assertNotEqual(row_start, -1, "the per-row record moved")
        opened = self.source.rfind("{", 0, row_start)
        depth = 0
        end = len(self.source)
        for i in range(opened, len(self.source)):
            if self.source[i] == "{":
                depth += 1
            elif self.source[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        record = self.source[opened:end]
        self.assertIn('"model"', record,
                      "the model is recorded somewhere other than the row, so "
                      "splitting or concatenating these files loses it.")


class ThePredictionsArtefactNamesItsModelTest(unittest.TestCase):
    """The recipe's eval kind, which writes both arms of a paired run."""

    def setUp(self) -> None:
        self.source = (REPO / "recipes" / "hf-peft-lora" / "entrypoint.py").read_text(
            encoding="utf-8")

    def test_each_predictions_row_carries_the_model(self):
        self.assertIn(
            '"model": base_model,', self.source,
            "predictions rows no longer name the model, so the base and "
            "adapter arms of a paired run cannot be shown to share one.")

    def test_the_adapter_arm_also_names_the_adapter(self):
        """`arm` says base or adapter. It does not say WHICH adapter."""
        self.assertIn('"adapter": str(adapter_dir)', self.source,
                      "the adapter arm does not record which adapter produced "
                      "it, so two adapters on one base are indistinguishable "
                      "in the artefact.")

    def test_the_base_arm_does_not_claim_an_adapter(self):
        """The control arm runs under `disable_adapter()` and must say so.

        Writing `adapter` on both arms would label the control with the very
        thing it is the control for.
        """
        self.assertIn('if arm != "base" and adapter_dir is not None', self.source,
                      "the base arm would carry an adapter field, which labels "
                      "the control with the thing it controls for.")


if __name__ == "__main__":
    unittest.main()
