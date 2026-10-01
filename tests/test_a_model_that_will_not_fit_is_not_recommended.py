"""The verdict is computed from every term the estimate computed.

`app/tools/models.py fit_of` summed the base weights, the gradients and the
optimizer state into the certain term it handed `feasibility.verdict`, and left
out the logits buffer - which the very same `estimate_training_vram` call had
already computed and already included in `total_gb`. So the function compared a
cost against the card that it had itself just said was lower than the real one.

Measured on the owner's machine, with the real `config.json` for Qwen/Qwen3-8B
and the 8.0 GB his `nvidia-smi` reports:

    base weights  3.84      \\
    gradients     0.15       |  what the verdict compared:  5.84
    optimizer     0.60       |  + activations 1.45       =  7.29   -> SPILLS
    overhead      1.25      /                                         +0.71 GB
    activations   1.45
    logits        1.16   <- absent
    ------------------
    total_gb      8.45   against an 8.00 GB card         -> WONT_FIT, -0.45 GB

That is the product promising a run that OOMs will work, which is the same
shape as the hardcoded 8.0 VRAM and the RAM field that read free disk space:
a confident number with a missing origin.

It also RANKED. `headroom_fraction` was computed from the floor and feeds
`score()` through `_headroom_score`, so a model needing 8.45 GB scored as
though it had 27% of the card to spare, and outranked models that genuinely
fit. This is why Qwen3-8B was recommended for that card in the first place.

`feasibility.can_this_machine_train` already put the logits buffer in its
certain terms. These two now agree, which is the actual fix: one arithmetic,
not two.
"""

import unittest
from dataclasses import replace

from app import feasibility
from app.tools import models

import support  # noqa: F401  - installs the suite's sandbox fences


#: The owner's card, as `hwdetect.local_specs` measures it.
CARD = feasibility.Field(value=8.0, provenance="measured", source="nvidia-smi")

#: The length at which the defect is visible. Shorter examples fit either way,
#: which is why this went unnoticed - the arithmetic only diverges past the card.
SEQ_LEN = 2048


def candidate(params_b: float) -> dict:
    """Everything `score()` reads, so a ranking assertion is not a KeyError."""
    return {
        "params_b": params_b,
        "downloads": 10_000,
        "licence_bucket": "permissive",
        "task": None,
        "gated": False,
        "has_safetensors": True,
        "is_gguf": False,
        "quantized_from": None,
    }


class TheVerdictUsesEveryTermTest(unittest.TestCase):
    def setUp(self) -> None:
        self.geometry = feasibility.geometry_for("Qwen/Qwen3-8B")
        if self.geometry is None:
            self.skipTest("no stored config.json for Qwen/Qwen3-8B in this checkout")

    def test_the_logits_buffer_is_in_the_verdict_not_only_in_the_total(self):
        """The defect itself, stated as the arithmetic it broke."""
        estimate = feasibility.estimate_training_vram(
            8.0, "qlora", SEQ_LEN, geometry=self.geometry, grad_checkpointing=True
        )
        # The estimate knows the logits buffer is real and how big it is.
        self.assertIsNotNone(estimate["logits_gb"])
        self.assertGreater(estimate["logits_gb"], 0.0)
        self.assertGreater(estimate["total_gb"], CARD.value)

        fit = models.fit_of(
            candidate(8.0),
            vram=CARD,
            method="qlora",
            seq_len=SEQ_LEN,
            geometry=self.geometry,
        )
        # A total over the card cannot come back as anything but WONT_FIT.
        # SPILLS means "tight but it runs" and would be a promise this
        # arithmetic does not support.
        self.assertEqual(fit["verdict"], "WONT_FIT")
        self.assertEqual(fit["total_gb"], estimate["total_gb"])

    def test_headroom_is_measured_against_the_total_not_the_floor(self):
        """The half that ranked, not the half that reported.

        A negative headroom on a model that exceeds the card is the whole
        point: `_headroom_score` must not be able to reward it.
        """
        fit = models.fit_of(
            candidate(8.0),
            vram=CARD,
            method="qlora",
            seq_len=SEQ_LEN,
            geometry=self.geometry,
        )
        self.assertEqual(fit["headroom_basis"], "total")
        self.assertLess(fit["headroom_fraction"], 0.0)
        # And the floor is still reported, still a floor - it is just no longer
        # what "how much room is left" is computed from.
        self.assertLess(fit["floor_gb"], fit["total_gb"])

    def test_a_model_that_fits_outranks_one_that_does_not(self):
        """The consequence a person actually met: the wrong recommendation."""
        smaller = feasibility.geometry_for("Qwen/Qwen3-4B")
        if smaller is None:
            self.skipTest("no stored config.json for Qwen/Qwen3-4B")

        #: AT 1,024 RATHER THAN AT `SEQ_LEN`, and for the reason the positive
        #: control above gives: under the measured envelope both models are
        #: WONT_FIT at 2,048, and a case comparing a no with a no cannot show
        #: that a fit outranks a non-fit. 1,024 is where the two still differ.
        big = models.fit_of(
            candidate(8.0), vram=CARD, method="qlora", seq_len=1024,
            geometry=self.geometry,
        )
        small = models.fit_of(
            candidate(4.0), vram=CARD, method="qlora", seq_len=1024,
            geometry=smaller,
        )
        self.assertEqual(big["verdict"], "WONT_FIT")
        self.assertEqual(small["verdict"], "FITS")

        scored_big = models.score(
            candidate(8.0), big, task=None, intent="train",
            method="qlora", max_downloads=10_000,
        )
        scored_small = models.score(
            candidate(4.0), small, task=None, intent="train",
            method="qlora", max_downloads=10_000,
        )
        self.assertGreater(scored_small["score"], scored_big["score"])

    def test_a_geometry_with_no_vocabulary_refuses_the_verdict(self):
        """Ruling 6, on the edge the fix opened.

        `logits_gb` needs `vocab_size`; `activations_gb` does not. A config
        carrying one and not the other would otherwise be sized with a term
        this module knows is large treated as zero - which is exactly the
        defect, arrived at by a different road.
        """
        without_vocab = replace(self.geometry, vocab_size=None)
        fit = models.fit_of(
            candidate(8.0), vram=CARD, method="qlora", seq_len=SEQ_LEN,
            geometry=without_vocab,
        )
        self.assertEqual(fit["verdict"], "UNKNOWN")


class TheHonestPathsStillWorkTest(unittest.TestCase):
    """Positive controls. A fix that turns every answer into WONT_FIT or
    UNKNOWN would pass the tests above and destroy the product."""

    def test_no_geometry_is_still_unknown_and_still_says_why(self):
        fit = models.fit_of(
            candidate(8.0), vram=CARD, method="qlora", seq_len=SEQ_LEN, geometry=None
        )
        self.assertEqual(fit["verdict"], "UNKNOWN")
        self.assertEqual(fit["headroom_basis"], "floor")
        self.assertIn("config.json", fit["reason"])

    def test_a_model_that_really_fits_still_says_fits(self):
        """THE LENGTH MOVED, THE CONTROL DID NOT.

        This ran at `SEQ_LEN` (2,048) until 2026-09-10, when three measured
        terms replaced three reasoned ones and the 4B at 2,048 became 8.73 GiB
        - a WONT_FIT. Loosening the assertion to accept that would have
        destroyed the control, whose whole job is to fail if a change turns
        every answer into WONT_FIT. So the case keeps asserting FITS and moves
        to a length where the model genuinely fits: 1,024, at 6.65 GiB.

        The boundary is now between 1,024 and 2,048 for this model on this
        card, and `test_the_boundary_for_the_four_b_is_recorded` pins it so a
        drift in either direction is visible rather than absorbed.
        """
        geometry = feasibility.geometry_for("Qwen/Qwen3-4B")
        if geometry is None:
            self.skipTest("no stored config.json for Qwen/Qwen3-4B")
        fit = models.fit_of(
            candidate(4.0), vram=CARD, method="qlora", seq_len=1024,
            geometry=geometry,
        )
        self.assertEqual(fit["verdict"], "FITS")
        self.assertGreater(fit["headroom_fraction"], 0.0)
        self.assertLess(fit["total_gb"], CARD.value)

    def test_a_shorter_example_turns_the_no_into_a_yes(self):
        """The NO is not a dead end. Same model, same card, fewer tokens."""
        geometry = feasibility.geometry_for("Qwen/Qwen3-8B")
        if geometry is None:
            self.skipTest("no stored config.json for Qwen/Qwen3-8B")
        at_2048 = models.fit_of(
            candidate(8.0), vram=CARD, method="qlora", seq_len=2048, geometry=geometry
        )
        at_1024 = models.fit_of(
            candidate(8.0), vram=CARD, method="qlora", seq_len=1024, geometry=geometry
        )
        at_512 = models.fit_of(
            candidate(8.0), vram=CARD, method="qlora", seq_len=512, geometry=geometry
        )
        at_192 = models.fit_of(
            candidate(8.0), vram=CARD, method="qlora", seq_len=192, geometry=geometry
        )
        self.assertEqual(at_2048["verdict"], "WONT_FIT")
        #: 1024 USED TO BE THE YES AND IS NOW A SPILL. The logits term was
        #: priced at four bytes per position and the loss path holds six -
        #: `transformers/loss/loss_utils.py` upcasts with `logits.float()` while
        #: the caller still holds the fp16 tensor - so every length got more
        #: expensive and this one crossed back over the line. The property this
        #: case exists for is unchanged: a NO is not a dead end. It turns at 768
        #: now rather than 1024, and recording the middle verdict is better than
        #: moving the number and saying nothing.
        #: AND IT MOVED AGAIN ON 2026-09-10, further and for three reasons at
        #: once: the logits width went 6 -> 12.6 (measured over two sweeps
        #: rather than read off a source file), a dequantisation workspace of
        #: 0.192 MiB per hidden unit joined the sum, and the embedding stopped
        #: being priced at NF4 because `bitsandbytes` never quantises it. The
        #: attention term came out at the same time, which pushes the other
        #: way, and at these lengths it does not win.
        #:
        #: AND ON 2026-09-10 THIS MODEL BECAME A DEAD END AT EVERY LENGTH.
        #: With the embedding measured at fp32 (`mlbuild fa5f09a`) and counted
        #: TWICE on an untied model, `Qwen3-8B`'s BASE WEIGHTS ALONE exceed an
        #: 8 GB card. No sequence length turns this no into a yes: 192 is a
        #: WONT_FIT like 2,048. That is not the property failing - it is this
        #: model leaving the set the property is about.
        self.assertEqual(at_1024["verdict"], "WONT_FIT")
        self.assertEqual(at_512["verdict"], "WONT_FIT")
        self.assertEqual(at_192["verdict"], "WONT_FIT")

        #: THE PROPERTY ITSELF, ON A MODEL THAT STILL HAS A BOUNDARY. A NO is
        #: not a dead end when the weights fit and the sequence is what does
        #: not - which is the case a person can actually act on.
        smaller = feasibility.geometry_for("Qwen/Qwen3-4B")
        if smaller is None:
            self.skipTest("no stored config.json for Qwen/Qwen3-4B")
        at_4b = lambda s: models.fit_of(
            candidate(4.0), vram=CARD, method="qlora", seq_len=s, geometry=smaller
        )["verdict"]
        self.assertEqual(at_4b(2048), "WONT_FIT")
        self.assertEqual(at_4b(1024), "FITS")

    def test_the_boundary_for_the_four_b_is_recorded(self):
        """A control that moved should say where it moved TO, or the next
        person moves it again without noticing it is drifting."""
        geometry = feasibility.geometry_for("Qwen/Qwen3-4B")
        if geometry is None:
            self.skipTest("no stored config.json for Qwen/Qwen3-4B")
        at = lambda s: models.fit_of(
            candidate(4.0), vram=CARD, method="qlora", seq_len=s, geometry=geometry
        )["verdict"]
        self.assertEqual(at(1024), "FITS")
        self.assertEqual(at(2048), "WONT_FIT")

    def test_the_inference_path_is_untouched(self):
        geometry = feasibility.geometry_for("Qwen/Qwen3-8B")
        if geometry is None:
            self.skipTest("no stored config.json for Qwen/Qwen3-8B")
        fit = models.fit_of(
            candidate(8.0), vram=CARD, method="inference", seq_len=SEQ_LEN,
            geometry=geometry,
        )
        # Inference has no logits buffer to forget: the guard is keyed on
        # `method != "inference"` and must not have changed this answer.
        self.assertEqual(fit["verdict"], "FITS")


if __name__ == "__main__":
    unittest.main()
