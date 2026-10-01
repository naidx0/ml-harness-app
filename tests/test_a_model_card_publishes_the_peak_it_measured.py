"""A card must not publish one measurement under another one's name.

Two defects, both found by Research reading `scripts/publish_the_adapter.py`
against the card criterion it registered BEFORE the adapter exists
(`10-Signals/specs/what-the-card-must-carry.md`) - which is the point of
registering a criterion first: no field gets chosen after seeing the number it
would report.

## Defect one: three peaks, one name

The recipe reports three memory figures and they are three quantities:

    peak_load_vram_gb    the transient during the 4-bit load - the fp16 weights
                         that exist briefly before they are quantised away
    peak_train_vram_gb   training, measured after `reset_peak_memory_stats`
    peak_vram_gb         the PROCESS high-water mark, the larger of the two

Every outcome band this lab registers is against the **training** peak. The card
read `peak_vram_gb` and printed it as *"measured peak VRAM"*, which publishes the
load-inclusive number under the training peak's name. That is a number measured
under one definition being read under another - this project's recurring fault
wearing a new label, and the same shape as the reversed-share denominators and
the `du` shared inodes.

It was not wrong when it was written: `peak_vram_gb` was the only key that
existed. It went wrong when the recipe learned to separate the two and the card
was not re-read.

## Defect two: a load the card's own machine cannot run

The usage snippet was `AutoModelForCausalLM.from_pretrained(base)` - no dtype,
no quantisation config. By this project's own measurement that loads **fp32**,
which is neither what the adapter was trained under nor something that fits
beside a 1.5B adapter on the 8 GiB card that produced it. **A card that ships a
load its own machine cannot run has published an untested instruction**, and
an adapter trained on a 4-bit base behaves differently on a base loaded any
other way.

## And a cap is not a length

`max_seq_len` is the ceiling a run was allowed. The realised length is
`num_tokens / steps / batch`, and on this lab's corpus that is 206 against a cap
of 2048. A card printing only the cap invites its reader to price a sequence ten
times the one that was measured.
"""

import unittest
from pathlib import Path

import support  # noqa: F401 - installs the suite's sandbox fences

from scripts import publish_the_adapter as publish


ADAPTER = {
    "base_model": "HuggingFaceTB/SmolLM2-1.7B",
    "r": 16,
    "lora_alpha": 32,
    "target_modules": ["q_proj", "v_proj"],
    "bytes": 4_600_000,
}

#: What `read_run_record` produces for a real 4-bit run of this lane's.
RECORD = {
    "max_seq_len": 2048,
    "batch_size": 1,
    "grad_accum": 1,
    "max_steps": 100,
    "load_in_4bit": True,
    "base_dtype": "torch.float16",
    "dataset_path": "evals/architecture-json/train.jsonl",
    "num_tokens": 20622.0,
    "train_runtime": 39.3755,
    "peak_vram_gb": 1.6,
    "peak_train_vram_gb": 1.6,
    "peak_load_vram_gb": 1.59,
}


class ThreePeaksKeepTheirOwnNamesTest(unittest.TestCase):
    def card(self, record: dict | None = None) -> str:
        return publish.model_card(ADAPTER, RECORD if record is None else record,
                                  "someone/an-adapter")

    def test_the_card_names_all_three_peaks(self):
        card = self.card()
        for label in ("peak VRAM, training",
                      "peak VRAM, model load",
                      "peak VRAM, whole process"):
            with self.subTest(label=label):
                self.assertIn(label, card)

    def test_no_row_says_only_measured_peak_vram(self):
        """THE DEFECT. A single unqualified label is what let the process figure
        be read as the training one."""
        self.assertNotIn("| measured peak VRAM |", self.card())

    def test_a_missing_training_peak_is_reported_as_missing(self):
        """Not omitted, and not filled in from the process figure - the two are
        the same number only when the load transient is the smaller of the two,
        which is a fact about a run rather than a rule."""
        without = {k: v for k, v in RECORD.items() if k != "peak_train_vram_gb"}
        card = self.card(without)
        self.assertIn("peak VRAM, training", card)
        self.assertIn("**not recorded**", card)

    def test_the_process_figure_is_not_silently_relabelled(self):
        """A run whose process high-water exceeds its training peak must show
        both, differing. This is the case where publishing one for the other
        actually changes the number a reader takes away."""
        record = dict(RECORD, peak_vram_gb=2.31, peak_train_vram_gb=1.60,
                      peak_load_vram_gb=2.31)
        card = self.card(record)
        self.assertIn("| peak VRAM, training | 1.6 GiB |", card)
        self.assertIn("| peak VRAM, whole process | 2.31 GiB |", card)


class TheSnippetLoadsWhatTheRunLoadedTest(unittest.TestCase):
    def test_a_four_bit_run_publishes_a_four_bit_load(self):
        card = publish.model_card(ADAPTER, RECORD, "someone/an-adapter")
        self.assertIn("BitsAndBytesConfig", card)
        self.assertIn("load_in_4bit=True", card)
        self.assertIn('bnb_4bit_quant_type="nf4"', card)

    def test_every_snippet_names_a_dtype(self):
        """THE DEFECT. `from_pretrained(base)` with nothing else loads fp32 -
        four bytes a parameter - which is not what any run here trained under
        and will not fit on the card that made the adapter."""
        for record in (RECORD, dict(RECORD, load_in_4bit=False)):
            with self.subTest(four_bit=record["load_in_4bit"]):
                card = publish.model_card(ADAPTER, record, "someone/an-adapter")
                self.assertIn("dtype=torch.float16", card)

    def test_an_fp16_run_does_not_publish_a_quantised_load(self):
        """The snippet follows the record; it does not always say 4-bit."""
        card = publish.model_card(ADAPTER, dict(RECORD, load_in_4bit=False),
                                  "someone/an-adapter")
        self.assertNotIn("BitsAndBytesConfig", card)


class ThePreviewIsTheUploadTest(unittest.TestCase):
    """Found by driving the refusal on a real adapter, not by reading the code.

    `files : ...` listed `UPLOADABLE` while the upload sent
    `[*files, "README.md"]`, so the list a person inspects before approving a
    publish omitted **the model card** - the file a reader of the repository
    actually reads, and the one carrying every measured figure. The behaviour
    was right and the report was wrong, which is the worse way round for a step
    whose entire purpose is inspection before upload.
    """

    def test_the_preview_and_the_upload_are_built_from_one_expression(self):
        source = Path(publish.__file__).read_text(encoding="utf-8")
        self.assertIn("would_send = [*files, \"README.md\"]", source)
        self.assertIn("for name in would_send:", source,
                      "the upload no longer iterates the list that is previewed")
        self.assertNotIn('for name in [*files, "README.md"]:', source)

    def test_the_summary_names_three_peaks_not_one(self):
        """The card was fixed and this line one below it was not: it printed the
        process high-water mark under the unqualified label `peak`."""
        source = Path(publish.__file__).read_text(encoding="utf-8")
        self.assertNotIn('"peak    : "', source)
        self.assertNotIn("peak    :", source)
        for key in ("peak_train_vram_gb", "peak_load_vram_gb", "peak_vram_gb"):
            self.assertIn(key, source)


class ACapIsNotALengthTest(unittest.TestCase):
    def test_the_realised_length_is_printed_beside_the_cap(self):
        card = publish.model_card(ADAPTER, RECORD, "someone/an-adapter")
        # 20622 / 100 steps / batch 1 = 206
        self.assertIn("cap 2048 / realised 206", card)

    def test_the_realised_length_says_whose_tokens_they_are(self):
        """The fourth silent input to a realised length, after the cap, the
        concatenated columns and the file itself.

        Measured 2026-09-10: the same 400 rows realise 236.4 tokens under
        SmolLM2's 49,152-entry vocabulary and 217.84 under Qwen's 151,936-entry
        one - 9% from the tokeniser alone, on identical text. The flagship run
        was compared against a band computed in another model's tokens before
        anybody noticed, so a bare number here invites exactly that.
        """
        card = publish.model_card(ADAPTER, RECORD, "someone/an-adapter")
        self.assertIn("tokeniser", card.lower())

    def test_a_cap_without_a_realised_length_says_so(self):
        """Print both or neither: a bare cap is the number a reader prices a
        sequence from, and it is up to ten times the one measured."""
        card = publish.model_card(ADAPTER,
                                  {k: v for k, v in RECORD.items()
                                   if k != "num_tokens"},
                                  "someone/an-adapter")
        self.assertIn("realised length not recorded", card)

    def test_the_columns_that_were_concatenated_are_named(self):
        """The second silent input to the realised length. Naming `text_field`
        alone trains on 95.1 tokens where the default trains on 206.3 of the
        same rows, and nothing in any output labels which happened."""
        card = publish.model_card(ADAPTER, dict(RECORD, text_field="prompt"),
                                  "someone/an-adapter")
        self.assertIn("`text` = `prompt`", card)

    def test_naming_no_column_is_reported_as_the_default_not_as_missing(self):
        """A run that names no field is correct and common - the recipe
        concatenates a prompt/completion pair - so `not recorded` would be a
        lie about a configuration that was made deliberately."""
        card = publish.model_card(ADAPTER, RECORD, "someone/an-adapter")
        self.assertIn("concatenating default", card)


if __name__ == "__main__":
    unittest.main()
