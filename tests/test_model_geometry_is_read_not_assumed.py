"""The headline question stops answering UNKNOWN to everybody.

`app/feasibility.py` used to hand `recommend()` a hardcoded `"geometry": None`,
so the KV-cache term was never computed, so `verdict()` returned UNKNOWN at
4 GB, at 6 GB, at 8 GB and at 24 GB alike. A verdict that is the same word
whatever card you own is not a verdict, and a user cannot tell it apart from
the product not working.

The fix is not a table of model shapes typed into the source - that is the
single-architecture bug again with more rows. It is to read the model's own
`config.json`, keep the bytes, and record which revision they came from.

So there are two things to prove and they pull in opposite directions:

1. **It answers now.** Real geometry for a real repo produces real, *different*
   verdicts across card sizes.
2. **It still says UNKNOWN when it should.** A model whose config has never
   been read, and a config that turns out not to describe an autoregressive
   decoder at all, both keep the fourth verdict. `docs/ARCHITECTURE.md` 4.8:
   UNKNOWN exists so a guess cannot pass as a measurement, and making it rarer
   must not make it dishonest.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app import feasibility


REPO_ROOT = Path(__file__).resolve().parents[1]

#: Qwen3-4B's real shape, taken from the config this repository ships in
#: `app/model_configs/`. Not typed in from memory: the test reads the file.
QWEN3_4B = "Qwen/Qwen3-4B"
QWEN3_8B = "Qwen/Qwen3-8B"
VIT = "google/vit-base-patch16-224"


class ShippedConfigsTest(unittest.TestCase):
    """The configs this repository keeps are real, dated and verbatim."""

    def test_every_stored_config_names_the_revision_it_came_from(self):
        root = feasibility.MODEL_CONFIG_ROOT
        self.assertTrue(root.is_dir(), f"no stored configs at {root}")
        stored = sorted(root.glob("*.json"))
        self.assertTrue(stored, "the harness ships no model configs at all")

        for path in stored:
            with self.subTest(config=path.name):
                envelope = json.loads(path.read_text(encoding="utf-8"))
                self.assertIn("repo_id", envelope)
                self.assertIsInstance(envelope.get("config"), dict)
                # A copy of somebody's config with no note of which commit it
                # is from cannot be re-checked, and an unre-checkable number is
                # the thing invariant 5 is about.
                self.assertTrue(
                    envelope.get("revision"),
                    f"{path.name} does not say which revision it is",
                )
                self.assertTrue(envelope.get("url"))
                self.assertTrue(envelope.get("fetched_at"))

    def test_the_parameter_count_is_the_index_and_not_the_name(self):
        """`Qwen3-8B` holds 8,190,735,360 parameters. The name says 8B."""
        params_b, source = feasibility.parameters_b_for(QWEN3_8B)

        self.assertIsNotNone(params_b)
        self.assertNotEqual(params_b, 8.0)
        self.assertAlmostEqual(params_b, 8.191, delta=0.001)
        self.assertIn("safetensors", source)


class GeometryParsingTest(unittest.TestCase):
    def geometry(self, config, **kwargs):
        return feasibility.geometry_from_config(config, **kwargs)

    def test_a_real_config_produces_the_real_shape(self):
        geometry = feasibility.geometry_for(QWEN3_4B)
        self.assertIsNotNone(geometry, "the shipped Qwen3-4B config did not parse")

        raw = json.loads(
            feasibility.config_path(QWEN3_4B).read_text(encoding="utf-8")
        )["config"]
        self.assertEqual(geometry.num_hidden_layers, raw["num_hidden_layers"])
        self.assertEqual(geometry.num_attention_heads, raw["num_attention_heads"])
        self.assertEqual(geometry.num_key_value_heads, raw["num_key_value_heads"])
        self.assertEqual(geometry.vocab_size, raw["vocab_size"])
        self.assertEqual(geometry.provenance, "measured")
        self.assertIn(QWEN3_4B, geometry.source)

    def test_grouped_query_attention_is_not_flattened_to_multi_head(self):
        """The KV cache is per *kv* head. Reading the wrong field overstates it."""
        geometry = self.geometry(
            {
                "num_hidden_layers": 36,
                "hidden_size": 2560,
                "num_attention_heads": 32,
                "num_key_value_heads": 8,
                "head_dim": 128,
                "vocab_size": 151936,
            }
        )

        self.assertEqual(geometry.num_key_value_heads, 8)
        self.assertNotEqual(geometry.num_key_value_heads, geometry.num_attention_heads)

    def test_a_pre_gqa_config_falls_back_to_the_attention_heads(self):
        """No `num_key_value_heads` is multi-head attention, by definition."""
        geometry = self.geometry(
            {
                "num_hidden_layers": 32,
                "hidden_size": 4096,
                "num_attention_heads": 32,
                "vocab_size": 32000,
            }
        )

        self.assertEqual(geometry.num_key_value_heads, 32)
        self.assertEqual(geometry.head_dim, 128)

    def test_a_decoder_hidden_under_text_config_is_found(self):
        """A vision-language config keeps the decoder one level down."""
        geometry = self.geometry(
            {
                "model_type": "multimodal",
                "num_hidden_layers": 2,          # the projector, not the model
                "vocab_size": 32000,
                "text_config": {
                    "num_hidden_layers": 32,
                    "hidden_size": 4096,
                    "num_attention_heads": 32,
                    "num_key_value_heads": 8,
                },
            }
        )

        self.assertEqual(geometry.num_hidden_layers, 32)
        self.assertEqual(geometry.num_key_value_heads, 8)

    def test_a_vision_encoder_is_refused_rather_than_given_a_kv_cache(self):
        """`google/vit-base` has layers and heads and no KV cache at all."""
        self.assertIsNone(feasibility.geometry_for(VIT))

    def test_a_config_that_cannot_be_divided_is_refused_not_rounded(self):
        self.assertIsNone(
            self.geometry(
                {
                    "num_hidden_layers": 12,
                    "hidden_size": 100,
                    "num_attention_heads": 7,
                    "vocab_size": 1000,
                }
            )
        )

    def test_a_missing_field_is_none_and_never_a_default(self):
        for missing in ("num_hidden_layers", "hidden_size", "num_attention_heads",
                        "vocab_size"):
            with self.subTest(missing=missing):
                config = {
                    "num_hidden_layers": 32,
                    "hidden_size": 4096,
                    "num_attention_heads": 32,
                    "vocab_size": 32000,
                }
                config.pop(missing)
                self.assertIsNone(self.geometry(config))

    def test_a_boolean_is_not_an_integer_here(self):
        """`True` is an `int` in Python and is not a layer count."""
        self.assertIsNone(
            self.geometry(
                {
                    "num_hidden_layers": True,
                    "hidden_size": 4096,
                    "num_attention_heads": 32,
                    "vocab_size": 32000,
                }
            )
        )


class StoringConfigsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_a_repo_id_cannot_spell_a_path(self):
        for hostile in ("../../etc/passwd", "a/../../b", "C:\\windows\\system32"):
            with self.subTest(repo_id=hostile):
                path = feasibility.config_path(hostile, self.root)
                self.assertEqual(path.parent.resolve(), self.root.resolve())

    def test_a_stored_config_round_trips_with_its_provenance(self):
        config = {
            "num_hidden_layers": 4,
            "hidden_size": 64,
            "num_attention_heads": 4,
            "vocab_size": 100,
        }
        feasibility.store_model_config(
            "acme/tiny",
            config,
            revision="deadbeef",
            url="https://example.invalid/config.json",
            parameters_total=1234567,
            parameters_source="test",
            root=self.root,
        )

        envelope = feasibility.load_model_config("acme/tiny", self.root)
        self.assertEqual(envelope["config"], config)
        self.assertEqual(envelope["revision"], "deadbeef")

        geometry = feasibility.geometry_from_config(
            envelope["config"], source="test"
        )
        self.assertEqual(geometry.num_hidden_layers, 4)

    def test_an_unreadable_store_is_none_and_never_an_exception(self):
        self.assertIsNone(feasibility.load_model_config("nobody/nothing", self.root))
        self.assertEqual(
            feasibility.parameters_b_for("nobody/nothing", self.root), (None, None)
        )

    def test_a_corrupt_stored_file_is_ignored_rather_than_crashing(self):
        path = feasibility.config_path("acme/broken", self.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")

        self.assertIsNone(feasibility.load_model_config("acme/broken", self.root))


class TheHeadlineQuestionTest(unittest.TestCase):
    """4, 6, 8 and 24 GB must not all get the same word."""

    def plan(self, gb):
        vram = feasibility.Field(float(gb), "declared", "test")
        rec = feasibility.recommend("fine-tune a chat model on my own data", vram)
        estimate = feasibility.estimate_vram(
            rec["params_b"],
            rec["quant"] if rec["quant"] in feasibility.BITS_PER_WEIGHT else "FP16",
            4096,
            "q8_0",
            geometry=rec["geometry"],
        )
        return rec, feasibility.verdict(
            vram,
            estimate["weights_gb"],
            estimate["kv_gb"],
            overhead_gb=estimate["overhead_gb"],
            geometry_provenance=estimate["geometry_provenance"],
        )

    def test_a_text_goal_now_gets_a_computed_verdict_not_unknown(self):
        for gb in (4, 6, 8, 24):
            with self.subTest(vram_gb=gb):
                _rec, decided = self.plan(gb)
                self.assertNotEqual(
                    decided["verdict"],
                    "UNKNOWN",
                    "the geometry was read, so this must be answerable",
                )
                self.assertEqual(decided["geometry_provenance"], "measured")

    def test_the_answer_actually_depends_on_the_card(self):
        headroom = {gb: self.plan(gb)[1]["headroom_gb"] for gb in (4, 6, 8, 24)}

        self.assertEqual(len(set(headroom.values())), 4, headroom)
        self.assertLess(headroom[4], headroom[24])

    def test_the_recommendation_carries_the_repo_it_actually_means(self):
        rec, _ = self.plan(8)

        self.assertTrue(rec["repo_id"], "a model with no repo cannot be looked up")
        self.assertIsNotNone(rec["geometry"])
        self.assertIn(rec["repo_id"], rec["geometry_source"])

    def test_an_image_goal_stays_unknown_because_it_honestly_is(self):
        vram = feasibility.Field(8.0, "declared", "test")
        rec = feasibility.recommend("classify images of parts", vram)

        self.assertIsNone(rec["geometry"])
        estimate = feasibility.estimate_vram(
            rec["params_b"], "FP16", 4096, "q8_0", geometry=rec["geometry"]
        )
        decided = feasibility.verdict(
            vram,
            estimate["weights_gb"],
            estimate["kv_gb"],
            overhead_gb=estimate["overhead_gb"],
            geometry_provenance=estimate["geometry_provenance"],
        )
        self.assertEqual(decided["verdict"], "UNKNOWN")

    def test_a_defaulted_card_is_still_unknown_however_good_the_geometry(self):
        """Invariant: a verdict computed from a defaulted input is UNKNOWN."""
        rec = feasibility.recommend("fine-tune", feasibility.Field(None, "defaulted"))
        estimate = feasibility.estimate_vram(
            rec["params_b"], "Q4", 4096, "q8_0", geometry=rec["geometry"]
        )
        decided = feasibility.verdict(
            feasibility.Field(None, "defaulted"),
            estimate["weights_gb"],
            estimate["kv_gb"],
            overhead_gb=estimate["overhead_gb"],
            geometry_provenance=estimate["geometry_provenance"],
        )

        self.assertEqual(decided["verdict"], "UNKNOWN")

    def test_a_model_nobody_has_read_the_config_for_is_still_unknown(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        previous = feasibility.MODEL_CONFIG_ROOT
        feasibility.MODEL_CONFIG_ROOT = Path(temp.name)
        self.addCleanup(setattr, feasibility, "MODEL_CONFIG_ROOT", previous)

        rec, decided = self.plan(8)

        self.assertIsNone(rec["geometry"])
        self.assertEqual(decided["verdict"], "UNKNOWN")
        # `model_size`, not `geometry`, and that is right rather than a near
        # miss: one unread file carries both the parameter count and the shape,
        # so the first thing the verdict cannot compute is the weight term.
        # What matters is that it names something real and does not guess.
        self.assertEqual(decided["missing"], "model_size")
        self.assertIn("parameters", decided["reason"])


if __name__ == "__main__":
    unittest.main()
