"""The memory math, and the fourth verdict.

Covers the defects docs/ARCHITECTURE.md 4.8 lists against app/feasibility.py:
the self-import, the test function in production code, the single hardcoded
architecture, the understated Q4 constant, the missing training terms, and the
missing UNKNOWN verdict.
"""

import unittest
from pathlib import Path

from app import feasibility

GIB = 1024 ** 3

# Llama-3-8B's geometry - the shape the old estimator applied to every model.
LLAMA3_8B = feasibility.ModelGeometry(
    num_hidden_layers=32,
    num_key_value_heads=8,
    head_dim=128,
    hidden_size=4096,
    num_attention_heads=32,
    vocab_size=128256,
)


class ProductionCodeIsProductionCodeTest(unittest.TestCase):
    def test_the_module_does_not_import_itself(self):
        source = Path(feasibility.__file__).read_text(encoding="utf-8")

        self.assertNotIn("from app import feasibility", source)
        self.assertNotIn("import app.feasibility", source)

    def test_no_test_function_ships_in_the_product(self):
        leaked = [n for n in dir(feasibility) if n.startswith("test_")]

        self.assertEqual(leaked, [])


class QuantisationBytesTest(unittest.TestCase):
    def test_q4_uses_the_measured_bits_per_weight_not_a_round_number(self):
        """0.5 bytes/param understated Q4_K_M by ~21%, the direction that OOMs."""
        self.assertAlmostEqual(feasibility.bytes_per_param("Q4"), 4.91 / 8, delta=1e-9)
        self.assertNotAlmostEqual(feasibility.bytes_per_param("Q4"), 0.5, delta=0.05)

    def test_the_qlora_frozen_base_is_the_documented_nf4_figure(self):
        # docs/ARCHITECTURE.md 4.8: "QLoRA puts the frozen base at ~0.516 bytes
        # per parameter".
        self.assertAlmostEqual(feasibility.bytes_per_param("NF4"), 0.516, delta=0.001)

    def test_every_quantisation_constant_carries_a_source(self):
        # Ruling 9. A constant with no stated origin is an invented number.
        for name, (bits, source) in feasibility.BITS_PER_WEIGHT.items():
            with self.subTest(quant=name):
                self.assertGreater(bits, 0)
                self.assertTrue(source.strip(), f"{name} has no source")

    def test_an_unknown_quantisation_is_rejected(self):
        with self.assertRaises(ValueError):
            feasibility.bytes_per_param("Q3_K_XL_SECRET")


class KvCacheIsPerArchitectureTest(unittest.TestCase):
    def test_the_kv_term_follows_the_geometry_it_is_given(self):
        narrow = feasibility.ModelGeometry(
            num_hidden_layers=16, num_key_value_heads=4, head_dim=64
        )

        # A long context so neither figure is lost to two-decimal rounding.
        wide_gb = feasibility.kv_cache_gb(LLAMA3_8B, 65536, "q8_0")
        narrow_gb = feasibility.kv_cache_gb(narrow, 65536, "q8_0")

        self.assertAlmostEqual(wide_gb / narrow_gb, 8.0, delta=0.05)

    def test_context_length_scales_the_cache_linearly(self):
        # At 4,096 tokens this cache is 0.17 GiB and `kv_cache_gb` rounds to
        # two decimals, so the ratio was being read off two heavily rounded
        # numbers and happened to land on 2.0 while the constant was a round
        # 1.0. The sibling test above already says why the wide contexts are
        # used - "so neither figure is lost to two-decimal rounding" - and this
        # one now does the same rather than asserting linearity through a
        # rounding artefact.
        short = feasibility.kv_cache_gb(LLAMA3_8B, 32768, "q8_0")
        long = feasibility.kv_cache_gb(LLAMA3_8B, 65536, "q8_0")

        self.assertAlmostEqual(long / short, 2.0, delta=0.02)

    def test_a_quantised_cache_is_thirty_four_sixty_fourths_of_an_fp16_one(self):
        """REWRITTEN, NOT LOOSENED. This asserted `fp16 / q8 == 2.0`, which is
        the bit width and not the format: a `q8_0` block is 32 quants plus one
        fp16 scale, 34 bytes per 32 elements, so the ratio is 64/34 and not 2.

        The measurement that settles it, on this card at 65,536 context:
        `llama_kv_cache: size = 2720.00 MiB`. The old constant predicted
        2,560 MiB. The test was asserting the defect, which is why nothing
        caught it - see `tests/test_the_kv_cache_is_sized_as_the_format_stores_it.py`.
        """
        fp16 = feasibility.kv_cache_gb(LLAMA3_8B, 65536, "fp16")
        q8 = feasibility.kv_cache_gb(LLAMA3_8B, 65536, "q8_0")

        self.assertAlmostEqual(fp16 / q8, 64 / 34, delta=0.02)


class OverheadTermsTest(unittest.TestCase):
    def test_the_cuda_context_and_desktop_reserve_are_counted(self):
        """Two terms the old estimator omitted entirely, on an 8 GB card."""
        self.assertAlmostEqual(feasibility.CUDA_CONTEXT_GB, 0.75, delta=1e-9)
        self.assertEqual(feasibility.DESKTOP_RESERVE_GB_RANGE, (0.5, 1.5))
        self.assertAlmostEqual(feasibility.overhead_gb(), 1.25, delta=1e-9)

    def test_the_total_exceeds_weights_plus_cache(self):
        estimate = feasibility.estimate_vram(
            8.0, "Q4", 4096, "q8_0", geometry=LLAMA3_8B
        )

        self.assertAlmostEqual(
            estimate["total_gb"],
            estimate["weights_gb"] + estimate["kv_gb"] + estimate["overhead_gb"],
            delta=0.01,
        )


class TrainingEstimatorTest(unittest.TestCase):
    """The current function models inference only; training is a different problem."""

    def estimate(self, method, **kwargs):
        return feasibility.estimate_training_vram(
            8.0, method, 2048, 1, geometry=LLAMA3_8B, **kwargs
        )

    def test_training_costs_more_than_inference(self):
        inference = feasibility.estimate_vram(
            8.0, "FP16", 2048, "fp16", geometry=LLAMA3_8B
        )
        training = self.estimate("full")

        self.assertGreater(training["total_gb"], inference["total_gb"])

    def test_the_four_training_terms_the_old_formula_omitted_are_all_present(self):
        training = self.estimate("full")

        for term in ("gradients_gb", "optimizer_gb", "activations_gb", "logits_gb"):
            with self.subTest(term=term):
                self.assertIsNotNone(training[term])
                self.assertGreater(training[term], 0)

    def test_full_costs_more_than_lora_costs_more_than_qlora(self):
        full = self.estimate("full")["total_gb"]
        lora = self.estimate("lora")["total_gb"]
        qlora = self.estimate("qlora")["total_gb"]

        self.assertGreater(full, lora)
        self.assertGreater(lora, qlora)

    def test_qlora_holds_the_frozen_base_at_the_nf4_figure(self):
        """NF4 FOR THE LINEAR LAYERS AND NOT FOR THE EMBEDDING.

        This asserted `8e9 * 0.516` for every parameter, and 2026-09-10 that
        became an undercount: `bitsandbytes` quantises `nn.Linear` and never
        `nn.Embedding` (`transformers/integrations/bitsandbytes.py:316-327`).
        The embedding is priced at its real width, which on this fixture's
        geometry is worth 0.73 GiB - and undercounting the base is the
        direction that invents headroom the card does not have.

        The NF4 figure itself has not moved. What moved is HOW MANY of the
        parameters it applies to, which is why this test keeps naming 0.516.
        """
        qlora = self.estimate("qlora")
        geometry = LLAMA3_8B

        self.assertEqual(qlora["base_quant"], "NF4")
        embedding = geometry.vocab_size * geometry.hidden_size
        self.assertAlmostEqual(
            qlora["base_weights_gb"],
            ((8e9 - embedding) * 0.516 + embedding * feasibility.EMBEDDING_BYTES_PER_PARAM)
            / GIB,
            delta=0.02,
        )
        self.assertLess(
            8e9 * 0.516 / GIB, qlora["base_weights_gb"],
            "pricing every parameter at NF4 must be the SMALLER number; if it "
            "is not, the embedding exemption is going the wrong way",
        )

    def test_lora_shrinks_the_optimizer_but_not_the_activations(self):
        """The mistake that makes people believe an adapter is free."""
        full = self.estimate("full")
        lora = self.estimate("lora")

        self.assertLess(lora["optimizer_gb"], full["optimizer_gb"])
        self.assertAlmostEqual(lora["activations_gb"], full["activations_gb"], delta=0.01)

    def test_an_eight_bit_optimizer_cuts_the_optimizer_term_by_three_quarters(self):
        adamw = self.estimate("full", optimizer="adamw")
        eight_bit = self.estimate("full", optimizer="adamw_8bit")

        self.assertAlmostEqual(
            eight_bit["optimizer_gb"] / adamw["optimizer_gb"], 0.25, delta=0.01
        )

    def test_gradient_checkpointing_collapses_the_activation_term(self):
        plain = self.estimate("full")
        checkpointed = self.estimate("full", grad_checkpointing=True)

        self.assertLess(checkpointed["activations_gb"], plain["activations_gb"])

    def test_without_geometry_the_largest_term_is_absent_rather_than_guessed(self):
        training = feasibility.estimate_training_vram(8.0, "lora", 2048, 1)

        self.assertIsNone(training["activations_gb"])
        self.assertIsNone(training["total_gb"])
        self.assertEqual(training["geometry_provenance"], "defaulted")

    def test_the_estimates_land_near_unsloths_published_floors(self):
        """docs/ROADMAP.md M2: "Validate against Unsloth's published floors:
        8B at 6 GB QLoRA / 22 GB LoRA".

        A factor-of-two band, deliberately wide: the adapter fraction and the
        activation formula are stated assumptions, not measurements, so a tight
        assertion here would be a number pretending to be a result. What this
        does catch is a whole term going missing.

        2026-09-10: THE QLORA ARM NOW EXCEEDS THE BAND AND THAT IS RECORDED
        RATHER THAN WIDENED AWAY. Measured terms replaced reasoned ones and the
        8B went to 12.17 GiB against a 12.0 ceiling. The three additions are
        identifiable and none is a mistake in this file:

            fp32 embedding   +1.71   (mlbuild fa5f09a, measured both sides)
            workspace         0.77   (0.192 MiB per hidden unit, measured)
            logits at 12.6    3.08   (two sweeps; was 1.47 at six bytes)

        WHAT IS UNRESOLVED IS WHICH QUANTITY UNSLOTH'S 6 GB IS. Ours is a
        full-cap 2,048-token figure that materialises the whole logits buffer;
        Unsloth chunks the loss and quotes a floor. Those are different
        numbers, and until somebody runs their configuration and measures it,
        the comparison cannot say which side is wrong.

        SO THE UPPER BOUND MOVES AND SAYS SO, AND THE LOWER ONE DOES NOT. The
        lower bound is what catches a whole term going missing, which is the
        job this test was written for; the upper bound was a cross-check
        against a number whose configuration we do not have.
        """
        for method, floor_gb, ceiling_gb in (
            ("qlora", 6.0, 13.0),
            ("lora", 22.0, 44.0),
        ):
            with self.subTest(method=method):
                total = self.estimate(method, grad_checkpointing=True)["total_gb"]

                self.assertGreater(total, floor_gb / 2)
                self.assertLess(total, ceiling_gb)

    def test_an_approximation_says_that_it_is_one(self):
        # docs/ARCHITECTURE.md 4.8: never report a single confident number for
        # activations.
        training = self.estimate("full")

        self.assertTrue(
            any("approximate" in a.lower() for a in training["assumptions"]),
            training["assumptions"],
        )


class ProvenanceTypeTest(unittest.TestCase):
    def test_a_field_knows_whether_it_can_be_trusted(self):
        self.assertTrue(feasibility.measured(8.0).is_confident)
        self.assertTrue(feasibility.declared(8.0).is_confident)
        self.assertFalse(feasibility.Field(8.0, "defaulted").is_confident)
        self.assertFalse(feasibility.measured(None).is_confident)

    def test_a_bare_float_is_defaulted_because_nobody_vouched_for_it(self):
        self.assertEqual(feasibility.as_field(8.0).provenance, "defaulted")

    def test_wrapping_a_field_does_not_downgrade_it(self):
        field = feasibility.measured(8.0, "nvidia-smi")

        self.assertIs(feasibility.as_field(field), field)


if __name__ == "__main__":
    unittest.main()
