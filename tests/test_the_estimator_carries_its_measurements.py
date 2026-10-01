"""The three measured changes to the estimator, each pinned to what measured it.

## Why these are tests and not a commit message

Every constant here replaced one that was arrived at by reading a source file
and reasoning. `BYTES_PER_LOGIT = 6` was `transformers/loss/loss_utils.py:55`
read CORRECTLY and counted incompletely - the fp16 original and the fp32 upcast
are two of the tensors the loss holds across a step, not all of them. A number
that survives because it has a plausible derivation is the failure mode; a
number that carries the sweep that produced it can be checked.

## What each one pins

  * **the logits width** - read from a named constant carrying its two sweeps,
    and both sweeps round into the declared range
  * **the attention term** - the modelled slope is CONSTANT in sequence length,
    which is the discriminator a materialised `T x T` matrix fails
  * **the workspace** - scales with hidden size and not with parameter count,
    and is zero when nothing is quantised
  * **the embedding** - priced unquantised, because `bitsandbytes` quantises
    `nn.Linear` and never `nn.Embedding`

## And one that is not about a measurement at all

`test_the_shown_arithmetic_explains_the_total` exists because adding a row to
`terms` and to the returned dict was NOT enough. There is a third accounting -
the `certain` list that decides the yes/no - and a fourth, the `arithmetic`
rows a person reads. Measured 2026-09-10 while applying this patch: with the
workspace in `terms` alone the 7B reported `needed 10.64` against a `total`
computed as 12.07, and the shown rows summed to neither. `_fit_at`'s own
docstring already says why that is fatal - *"the answer must be computed from
the same total the answer displays"* - and it was written about the logits
buffer doing exactly this. A term added to one list and not the others is that
defect returning.
"""

from __future__ import annotations

import unittest

import support

from app import feasibility as F


def geometry(hidden: int, layers: int, heads: int, vocab: int,
             tie: bool | None = None) -> F.ModelGeometry:
    return F.ModelGeometry(
        tie_word_embeddings=tie,
        num_hidden_layers=layers,
        num_key_value_heads=heads,
        head_dim=hidden // heads,
        hidden_size=hidden,
        num_attention_heads=heads,
        vocab_size=vocab,
        provenance="measured",
    )


#: `SmolLM2-1.7B`, the model the sweeps were run on. HIDDEN IS 2,048: the
#: workspace coefficient was divided by 1,948 for an hour, which is where the
#: 0.093-against-0.089 disagreement came from when it was re-derived.
THE_SWEPT_MODEL = geometry(hidden=2048, layers=24, heads=32, vocab=49152)


class TheLogitsWidthCarriesItsSweepsTest(unittest.TestCase):
    def test_the_width_is_named_and_not_a_literal(self):
        self.assertTrue(hasattr(F, "BYTES_PER_LOGIT"))
        self.assertTrue(hasattr(F, "BYTES_PER_LOGIT_SWEEPS"))
        self.assertTrue(hasattr(F, "BYTES_PER_LOGIT_RANGE"))

    def test_both_sweeps_round_into_the_declared_range(self):
        """THE POINT OF CARRYING A RANGE. 12.6 fitted to eight points should
        not read as firm as a definition, and a reader who needs to know how
        firm it is can see both ends."""
        low, high = F.BYTES_PER_LOGIT_RANGE
        for measured in F.BYTES_PER_LOGIT_SWEEPS:
            with self.subTest(sweep=measured):
                self.assertTrue(
                    low <= round(measured, 1) <= high,
                    f"{measured} is outside the declared {low}-{high}",
                )

    def test_the_point_estimate_is_inside_its_own_range(self):
        low, high = F.BYTES_PER_LOGIT_RANGE
        self.assertTrue(low <= F.BYTES_PER_LOGIT <= high)

    def test_it_is_no_longer_the_source_read_figure(self):
        """RED IF SOMEBODY PUTS 6 BACK because a source file says 2 + 4. The
        source was read correctly; it names two tensors, not the peak."""
        self.assertNotEqual(6, F.BYTES_PER_LOGIT)

    def test_the_shown_source_states_the_width_it_used(self):
        """The displayed provenance said `s*b*vocab*4` while the constant was
        6, so it described neither. A breakdown that misstates its own
        arithmetic is worse than one that omits it."""
        estimate = F.estimate_training_vram(
            1.7, "qlora", 2048, 1, geometry=THE_SWEPT_MODEL
        )
        self.assertIsNotNone(estimate["logits_gb"])
        expected = round(
            2048 * 1 * 49152 * F.BYTES_PER_LOGIT / F.GIB, 2
        )
        self.assertEqual(expected, estimate["logits_gb"])


class TheAttentionTermIsNotMaterialisedTest(unittest.TestCase):
    """The discriminator is the SHAPE of the slope, not the size of a residual."""

    def modelled_gb(self, seq: int) -> float:
        estimate = F.estimate_training_vram(
            1.7, "qlora", seq, 1, geometry=THE_SWEPT_MODEL, grad_checkpointing=True
        )
        return estimate["activations_gb"]

    def test_doubling_the_length_doubles_the_activations(self):
        """FLAT SLOPE, STATED SO ROUNDING CANNOT FAKE EITHER ANSWER.

        MEASURED: adjacent slopes 0.625, 0.742, 0.742 per 1,000 realised
        tokens - flat from 512 up. A materialised `T x T` matrix makes them
        RISE (0.271 / 0.385 / 0.614), which is what this catches.

        THE FIRST VERSION OF THIS COMPARED `gb / seq` ACROSS 512, 1024 AND
        2048 AND WENT RED ON THE CORRECT MODEL. `activations_gb` is rounded to
        two decimals, and at 512 tokens the figure is 0.076 GiB - so 0.08/512
        against 0.15/1024 differs by 6.7%, all of it rounding. The test was
        measuring the rounding and would have reported a linear model as
        superlinear.

        Doubling is the same claim without that: linear in `s` means each
        doubling doubles the term, and the tolerance is the rounding step
        rather than a number chosen to make it pass.
        """
        for shorter in (1024, 2048, 4096):
            with self.subTest(seq=shorter):
                self.assertAlmostEqual(
                    2 * self.modelled_gb(shorter),
                    self.modelled_gb(2 * shorter),
                    delta=0.02,
                    msg="the modelled activations grow faster than linearly, "
                        "which is the signature of a materialised attention "
                        "matrix",
                )

    def test_the_flag_exists_and_is_off(self):
        """Kept rather than deleted: a path that DOES materialise it is a real
        path this estimator may be asked about."""
        self.assertFalse(F.ATTENTION_MATRIX_IS_MATERIALISED)

    def test_turning_the_flag_on_makes_the_slope_rise(self):
        """THE CONTROL, and it is what makes the test above mean something. If
        the flag changed nothing, a flat slope would prove nothing about
        whether the term is modelled."""
        F.ATTENTION_MATRIX_IS_MATERIALISED = True
        self.addCleanup(setattr, F, "ATTENTION_MATRIX_IS_MATERIALISED", False)
        self.assertGreater(
            self.modelled_gb(4096), 2 * self.modelled_gb(2048) + 0.02,
            "turning the term on changed nothing, so the test above proves "
            "nothing about whether it is modelled",
        )


class TheWorkspaceScalesWithHiddenSizeTest(unittest.TestCase):
    def workspace(self, hidden: int, params_b: float, quant: str = "qlora") -> float:
        return F.estimate_training_vram(
            params_b, quant, 2048, 1,
            geometry=geometry(hidden, 24, 32, 49152),
        )["workspace_gb"]

    def test_doubling_hidden_size_doubles_it(self):
        self.assertAlmostEqual(
            2 * self.workspace(1024, 1.7), self.workspace(2048, 1.7), places=2
        )

    def test_changing_the_parameter_count_does_not_move_it(self):
        """PROVED BY THE TWO-MODEL SPLIT: 0.182 and 0.202 MiB per hidden unit
        across models differing 3.56x in size. A per-parameter term could not
        have produced that."""
        self.assertEqual(self.workspace(1948, 0.135), self.workspace(1948, 1.7))

    def test_it_is_zero_and_not_none_when_nothing_is_quantised(self):
        """ZERO IS A MEASURED ABSENCE. `None` would make `total_gb` None, which
        is the answer for "could not compute" and would be a lie here."""
        self.assertEqual(0.0, self.workspace(1948, 1.7, quant="lora"))

    def test_it_matches_the_measured_rate(self):
        expected = round(1948 * F.DEQUANT_WORKSPACE_MIB_PER_HIDDEN_UNIT * (1024 ** 2) / F.GIB, 2)
        self.assertEqual(expected, self.workspace(1948, 1.7))

    def test_the_coefficient_is_the_one_derived_after_the_upcast(self):
        """RED IF THE PRE-CALL RESIDENT COMES BACK. 0.192 was solved for with
        resident = 0.962, the figure BEFORE
        `prepare_model_for_kbit_training`; training happens after it, at 1.149,
        so the old coefficient carried 0.187 GiB of embedding inside it and was
        twice too large. The two rows are degenerate against the sweep - both
        models share a vocabulary, so a per-hidden workspace and a per-hidden
        embedding correction are the same function of the data - which is why
        this is pinned by the constant rather than by a fit."""
        self.assertLess(F.DEQUANT_WORKSPACE_MIB_PER_HIDDEN_UNIT, 0.15)
        self.assertAlmostEqual(0.098, F.DEQUANT_WORKSPACE_MIB_PER_HIDDEN_UNIT, places=3)

    def test_the_measured_pair_brackets_the_constant(self):
        low, high = F.DEQUANT_WORKSPACE_MIB_RANGE
        self.assertTrue(low <= F.DEQUANT_WORKSPACE_MIB_PER_HIDDEN_UNIT <= high)


class TheEmbeddingIsNotQuantisedTest(unittest.TestCase):
    """`bitsandbytes` quantises `nn.Linear` and never `nn.Embedding`."""

    def test_a_quantised_base_prices_the_embedding_at_full_width(self):
        g = geometry(1536, 28, 12, 151936)
        estimate = F.estimate_training_vram(1.5437, "qlora", 2048, 1, geometry=g)
        emb = 151936 * 1536
        expected = round(
            ((1.5437e9 - emb) * F.bytes_per_param("NF4")
             + emb * F.EMBEDDING_BYTES_PER_PARAM) / F.GIB, 2
        )
        self.assertEqual(expected, estimate["base_weights_gb"])

    def test_an_unquantised_base_is_unchanged(self):
        """THE CONTROL. Nothing is quantised, so there is no embedding to
        exempt and the old arithmetic must still hold exactly."""
        g = geometry(1536, 28, 12, 151936)
        estimate = F.estimate_training_vram(1.5437, "lora", 2048, 1, geometry=g)
        self.assertEqual(
            round(1.5437e9 * F.bytes_per_param("FP16") / F.GIB, 2),
            estimate["base_weights_gb"],
        )

    def test_the_fork_is_closed_and_the_measurement_is_named(self):
        """THIS ASSERTED "unmeasured" FOR ABOUT AN HOUR. The fp16-or-fp32
        question was open when the row was written and `mlbuild fa5f09a` closed
        it, taking the reading on both sides of
        `prepare_model_for_kbit_training`: fp16 0.188 before, fp32 0.375 after,
        the same 1.594 load peak either side. Every training peak is read after
        that call, so fp32 is the configuration the peaks describe.

        The assumption now names what measured it, because an estimate that
        says "4 bytes" without saying who found that out is the kind of number
        this whole file exists to stop shipping.
        """
        g = geometry(1536, 28, 12, 151936)
        said = " ".join(
            F.estimate_training_vram(1.5437, "qlora", 2048, 1, geometry=g)["assumptions"]
        )
        self.assertIn("fp32", said)
        self.assertIn("fa5f09a", said)
        self.assertNotIn("unmeasured", said)
        self.assertEqual(4.0, F.EMBEDDING_BYTES_PER_PARAM)

    def test_an_untied_model_carries_two_unquantised_tensors(self):
        """THE DISCREPANCY THAT FOUND THIS. Counting one tensor agreed with the
        sweep exactly on the tied 1.5B and was low by almost exactly one
        embedding on the untied 7B - on BOTH the fp16 and the fp32 fork. An
        error that survives a change of dtype is structural.

        `lm_head` is a second `vocab x hidden` matrix when the model does not
        tie it, and `get_keys_to_not_convert` leaves it unquantised for the
        same reason `embed_tokens` is left.
        """
        tied = geometry(1536, 28, 12, 151936, tie=True)
        untied = geometry(1536, 28, 12, 151936, tie=False)
        one = F.estimate_training_vram(1.5437, "qlora", 2048, 1, geometry=tied)
        two = F.estimate_training_vram(1.5437, "qlora", 2048, 1, geometry=untied)
        per_copy = 151936 * 1536 * (F.EMBEDDING_BYTES_PER_PARAM - F.bytes_per_param("NF4"))
        self.assertAlmostEqual(
            two["base_weights_gb"] - one["base_weights_gb"],
            round(per_copy / F.GIB, 2), delta=0.02,
        )

    def test_absent_is_read_as_tied_because_that_is_the_framework_default(self):
        """Reading absence as untied would charge for a tensor
        `PretrainedConfig` says is not there."""
        unsaid = geometry(1536, 28, 12, 151936)
        tied = geometry(1536, 28, 12, 151936, tie=True)
        self.assertIsNone(unsaid.tie_word_embeddings)
        self.assertEqual(
            F.estimate_training_vram(1.5437, "qlora", 2048, 1, geometry=unsaid)["base_weights_gb"],
            F.estimate_training_vram(1.5437, "qlora", 2048, 1, geometry=tied)["base_weights_gb"],
        )


class TheAnswerIsComputedFromTheTotalItShowsTest(unittest.TestCase):
    """A term in one accounting and not the others is the defect this file's
    own `_fit_at` docstring was written about."""

    def test_a_refusal_states_a_margin_that_matches_its_own_needed(self):
        """THE BRANCH THE TEST ABOVE NEVER ENTERS, and mutation found it.

        `test_the_yes_or_no_is_decided_from_the_total_it_displays` uses a model
        that FITS, so it never reaches the WONT_FIT arm - where `needed_gb`
        added the uncertain term and `headroom_gb` did not, three lines apart.
        Reverting that fix left this file green.

        MEASURED on `Coder-7B` at 2,048: needed 14.10 with a reported headroom
        of -5.48, where `8.0 - 14.10` is `-6.10`. The refusal understated its
        own shortfall by the activations term, in the direction that flatters
        the card - and `record_that_this_card_refuses` stamps that number as
        `training_headroom_gb` for the diagnosis to read back to somebody.
        """
        vram = F.Field(value=8.0, provenance="measured", source="a test")
        huge = geometry(4096, 32, 32, 128256, tie=False)
        estimate, fit = F._fit_at(
            8.0, huge, vram,
            method="qlora", seq_len=2048, batch=1,
            optimizer="adamw", grad_checkpointing=True,
        )
        self.assertEqual("WONT_FIT", fit["verdict"], "this fixture is meant not to fit")
        self.assertAlmostEqual(
            fit["vram_gb"] - fit["needed_gb"], fit["headroom_gb"], places=2,
            msg="the refusal's margin is not its own vram minus its own needed",
        )

    def test_the_workspace_reaches_the_returned_dict(self):
        estimate = F.estimate_training_vram(
            1.7, "qlora", 2048, 1, geometry=THE_SWEPT_MODEL
        )
        self.assertIn("workspace_gb", estimate)

    def test_the_yes_or_no_is_decided_from_the_total_it_displays(self):
        """THE INVARIANT `_fit_at`'S OWN DOCSTRING NAMES, and the one my first
        five tests did not cover.

        Found by mutation: deleting `workspace_gb` from the `certain` list in
        `_fit_at` left this file GREEN, because everything above asserts what
        `estimate_training_vram` RETURNS and the yes/no is decided somewhere
        else. That is the defect verbatim - measured while applying this patch,
        the 7B answered `needed 10.64` while its own shown rows summed to
        12.07, a tool disagreeing with itself by 1.43 GiB.

        The docstring says it plainly about the logits buffer doing this
        before: *"the answer must be computed from the same total the answer
        displays."* A term added to `terms` and to the returned dict but not to
        `certain` is that sentence being broken again.
        """
        vram = F.Field(value=8.0, provenance="measured", source="a test")
        estimate, fit = F._fit_at(
            1.7, THE_SWEPT_MODEL, vram,
            method="qlora", seq_len=2048, batch=1,
            optimizer="adamw", grad_checkpointing=True,
        )
        self.assertAlmostEqual(
            estimate["total_gb"], fit["needed_gb"], places=2,
            msg="the number the answer is computed from is not the number it "
                "displays; a term is in one accounting and not the other",
        )
        #: AND THE HEADROOM COMES OFF THE SAME NUMBER. A verdict that agrees
        #: with the total while the headroom is computed from something else
        #: would pass the line above and still mislead the reader.
        self.assertAlmostEqual(
            fit["vram_gb"] - fit["needed_gb"], fit["headroom_gb"], places=2
        )

    def test_the_total_includes_every_term_it_reports(self):
        estimate = F.estimate_training_vram(
            1.7, "qlora", 2048, 1, geometry=THE_SWEPT_MODEL
        )
        rows = (
            "base_weights_gb", "gradients_gb", "optimizer_gb",
            "activations_gb", "logits_gb", "workspace_gb",
        )
        self.assertAlmostEqual(
            round(sum(estimate[r] for r in rows) + estimate["overhead_gb"], 2),
            estimate["total_gb"],
            places=2,
        )


if __name__ == "__main__":
    unittest.main()
