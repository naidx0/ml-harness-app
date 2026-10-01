"""The KV cache is sized by the block format, not by the bit width.

FOUND ON THE FIT WALK, against a measurement rather than by reading. The table
said `q8_0` costs 1.0 bytes per element - "8 bits is one byte" - which is the
bit width and not the format. llama.cpp's `q8_0` block holds 32 quants plus one
fp16 scale: 34 bytes for 32 elements, 1.0625 bytes each. `q4_0` is 16 + 2 = 18
bytes per 32 elements, 0.5625.

THE MEASUREMENT THAT SETTLES IT. On this card at 65,536 context the 3.7B dense
granite's cache is `llama_kv_cache: size = 2720.00 MiB (K q8_0 1360.00 MiB, V
q8_0 1360.00 MiB)`. The old constant predicted 2.50 GiB = 2,560 MiB. 1.0625
gives 2,720.00 MiB exactly. The error was 160 MiB at that context and always in
the optimistic direction, which is the wrong direction for an answer to "will
this fit".

The vault's `one-click-local` spec states the same relation from the other end:
q8_0 KV is exactly 34/64 of fp16. Both statements are the same fact, and this
file asserts it as a ratio as well as an absolute, so a change to either
constant alone fails.
"""

from __future__ import annotations

import unittest

from app import feasibility

#: The geometry of `granite42-hermes`, the model the bench measured: 40 layers,
#: 8 KV heads, head_dim 64. Derived from the measurement itself rather than
#: typed from a config, and asserted below against the number it must produce.
MEASURED_MODEL = dict(num_hidden_layers=40, num_key_value_heads=8, head_dim=64)

#: `llama_kv_cache: size = 2720.00 MiB` at num_ctx 65536, this machine,
#: 2026-09-04, with OLLAMA_KV_CACHE_TYPE=q8_0.
MEASURED_MIB_AT_64K = 2720.00


class TheCacheMatchesTheCardTest(unittest.TestCase):
    def geometry(self):
        return feasibility.ModelGeometry(**MEASURED_MODEL)

    def test_q8_matches_the_measured_cache_within_four_mib(self):
        gib = feasibility.kv_cache_gb(self.geometry(), 65536, "q8_0")
        mib = gib * 1024
        self.assertAlmostEqual(mib, MEASURED_MIB_AT_64K, delta=4.0)

    def test_the_old_constant_would_have_been_160_mib_light(self):
        """Stated as its own case so the size of the error is on the record and
        not only in a commit message. A prediction under the truth is the
        dangerous direction here: it turns a no into a yes."""
        gib = feasibility.kv_cache_gb(self.geometry(), 65536, "q8_0")
        old = 2.50 * 1024
        self.assertGreater(gib * 1024 - old, 150.0)

    def test_q8_is_exactly_thirty_four_sixty_fourths_of_fp16(self):
        """The vault's `one-click-local` spec states the relation this way, and
        it holds on CUDA and CPU. Asserting the ratio as well as the absolute
        means changing one constant without the other fails."""
        eight = feasibility.KV_BYTES_PER_ELEMENT["q8_0"][0]
        sixteen = feasibility.KV_BYTES_PER_ELEMENT["fp16"][0]
        self.assertAlmostEqual(eight / sixteen, 34 / 64, places=6)

    def test_q4_carries_its_scale_too(self):
        """16 bytes of quants plus one fp16 scale per 32 elements. The same
        mistake lived here and it is the same size in proportion."""
        four = feasibility.KV_BYTES_PER_ELEMENT["q4_0"][0]
        self.assertAlmostEqual(four, 18 / 32, places=6)

    def test_every_entry_says_where_its_number_comes_from(self):
        for name, (value, source) in feasibility.KV_BYTES_PER_ELEMENT.items():
            with self.subTest(name):
                self.assertGreater(value, 0)
                self.assertTrue(source.strip(), "a constant with no stated source")

    def test_an_unknown_quantisation_is_refused_rather_than_guessed(self):
        """Unchanged behaviour, asserted here because this file is about what
        the cache costs and a silent default would be the same class of bug."""
        with self.assertRaises(ValueError) as caught:
            feasibility.kv_cache_gb(self.geometry(), 4096, "q6_k")
        self.assertIn("q6_k", str(caught.exception))


class FittingIsNotPlacementTest(unittest.TestCase):
    """A card with room is not a runtime that will use it.

    `SPILLS` in this module means "needed lands within a tenth of the card" - a
    margin band computed from memory, not a claim about where layers go, though
    the name reads like one. Measured on this card: a 9B Q4_K_M at 65,536 peaks
    at 7,081 MiB of 8,192, which this arithmetic calls FITS at 86%, and Ollama
    still placed 15% of it on the CPU at a fifth of the speed.
    """

    def answer(self, repo_id: str):
        from app.tools import REGISTRY

        return REGISTRY.get("can_this_machine_train").handler(repo_id=repo_id, method="qlora")

    def test_an_answer_that_fits_says_which_question_it_answered(self):
        answer = self.answer("HuggingFaceTB/SmolLM2-1.7B")
        self.assertEqual(answer["fit"], "FITS")
        self.assertIn("memory arithmetic", answer["because"])
        self.assertIn("placement_is_not_memory", answer)

    def test_it_names_the_measured_case_and_the_lever(self):
        note = self.answer("HuggingFaceTB/SmolLM2-1.7B")["placement_is_not_memory"]
        self.assertIn("7,081", note)
        self.assertIn("num_gpu", note)

    def test_a_model_that_does_not_fit_gets_no_placement_note(self):
        """Nothing is going to be placed anywhere, so the caveat would only
        compete with the answer."""
        answer = self.answer("Qwen/Qwen3-8B")
        self.assertEqual(answer["fit"], "WONT_FIT")
        self.assertNotIn("placement_is_not_memory", answer)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
