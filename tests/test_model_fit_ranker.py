"""Finding a model is a fit question, and popularity is worth five points.

`app/tools/models.py` exists because a search box answers "what is popular",
which is a different question from "what will run on this machine, for this
job, under this licence" - and the gap between the two is where the person this
product is for loses a weekend.

Nothing here touches the network. Every Hub record below is a fixture in the
shape the live API actually returns, checked against it once by hand:
`expand[]` on the *list* endpoint gives `safetensors.parameters`, `tags`,
`gated`, `library_name`, `pipeline_tag`, `sha` and a `config` that carries
`architectures` and `model_type` **and no geometry at all**. That last one is
why `fetch_config` exists, and a test that assumed otherwise would be testing a
Hub that does not exist.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app import feasibility
from app.tools import models


def record(
    repo_id,
    *,
    params=None,
    tags=(),
    task="text-generation",
    downloads=0,
    gated=False,
    library="transformers",
):
    body = {
        "id": repo_id,
        "sha": "0" * 40,
        "pipeline_tag": task,
        "library_name": library,
        "downloads": downloads,
        "gated": gated,
        "tags": list(tags),
        "config": {"architectures": ["LlamaForCausalLM"], "model_type": "llama"},
    }
    if params is not None:
        body["safetensors"] = {"parameters": {"BF16": params}, "total": params}
    return body


MEASURED_8GB = feasibility.Field(8.0, "measured", "nvidia-smi")


class RateLimitHeaderTest(unittest.TestCase):
    """Read the budget the server states, rather than guessing a sleep."""

    def test_the_live_header_shape_is_parsed(self):
        headers = {
            "RateLimit": '"api";r=499;t=264',
            "RateLimit-Policy": '"fixed window";"api";q=500;w=300',
        }

        parsed = models.parse_rate_limit(headers)

        self.assertEqual(parsed["remaining"], 499)
        self.assertEqual(parsed["resets_in_seconds"], 264)
        self.assertEqual(parsed["quota"], 500)
        self.assertEqual(parsed["window_seconds"], 300)

    def test_no_header_is_none_rather_than_an_invented_budget(self):
        self.assertIsNone(models.parse_rate_limit({}))
        self.assertIsNone(models.parse_rate_limit(None))


class LicenceTest(unittest.TestCase):
    def bucket(self, tag):
        return models.licence_of([tag])[1]

    def test_the_four_buckets(self):
        self.assertEqual(self.bucket("license:apache-2.0"), "CLEAR_COMMERCIAL")
        self.assertEqual(self.bucket("license:llama3.1"), "CONDITIONAL")
        self.assertEqual(self.bucket("license:cc-by-nc-4.0"), "NOT_COMMERCIAL")
        self.assertEqual(self.bucket("license:other"), "UNKNOWN")

    def test_unknown_is_never_quietly_permissive(self):
        """`license:other` is one of the commonest tags and says nothing."""
        self.assertNotEqual(self.bucket("license:other"), "CLEAR_COMMERCIAL")
        self.assertEqual(models.licence_of([])[1], "UNKNOWN")

    def test_any_non_commercial_creative_commons_variant_is_caught(self):
        self.assertEqual(self.bucket("license:cc-by-nc-sa-2.5"), "NOT_COMMERCIAL")


class ParameterCountTest(unittest.TestCase):
    def test_the_count_comes_from_the_index_and_never_from_the_name(self):
        """Two repos both called 8B differ by hundreds of millions."""
        summary = models.summarize(record("acme/totally-an-8B", params=4_000_000_000))

        self.assertEqual(summary["params_b"], 4.0)
        self.assertIn("measured", summary["params_source"])

    def test_a_repo_with_no_index_has_no_count_rather_than_a_guess(self):
        summary = models.summarize(record("acme/mystery"))

        self.assertIsNone(summary["params_b"])
        self.assertIn("unknown", summary["params_source"])


class HeadroomCurveTest(unittest.TestCase):
    def test_it_peaks_in_the_sweet_spot_and_penalises_both_ends(self):
        low, high = models.HEADROOM_SWEET_SPOT

        self.assertEqual(models._headroom_score((low + high) / 2), 1.0)
        self.assertLess(models._headroom_score(0.02), 1.0)
        self.assertLess(models._headroom_score(0.95), 1.0)
        self.assertEqual(models._headroom_score(-0.1), 0.0)
        self.assertEqual(models._headroom_score(None), 0.0)


class RankingTest(unittest.TestCase):
    def rank(self, records, **kwargs):
        options = {
            "vram": MEASURED_8GB,
            "task": "text-generation",
            "intent": "commercial",
            "method": "qlora",
            "seq_len": 2048,
        }
        options.update(kwargs)
        return models.rank(records, **options)

    def test_downloads_cannot_outweigh_fitting_the_machine(self):
        """The whole point. A wildly popular model that does not fit loses."""
        result = self.rank(
            [
                record(
                    "famous/enormous",
                    params=70_000_000_000,
                    downloads=50_000_000,
                    tags=["license:apache-2.0", "safetensors"],
                ),
                record(
                    "obscure/small",
                    params=3_000_000_000,
                    downloads=11,
                    tags=["license:apache-2.0", "safetensors"],
                ),
            ]
        )

        self.assertEqual([e["repo_id"] for e in result["ranked"]], ["obscure/small"])
        self.assertEqual(result["eliminated"][0]["repo_id"], "famous/enormous")

    def test_downloads_is_worth_five_points_out_of_a_hundred(self):
        self.assertEqual(models.WEIGHTS["DOWNLOADS"], 5)
        self.assertEqual(models.WEIGHTS["FIT"], 35)
        self.assertGreater(models.WEIGHTS["FIT"], models.WEIGHTS["DOWNLOADS"] * 5)

    def test_a_non_commercial_licence_is_a_hard_gate_when_the_use_is_commercial(self):
        records = [
            record("acme/nc", params=3_000_000_000, tags=["license:cc-by-nc-4.0",
                                                          "safetensors"])
        ]

        commercial = self.rank(records, intent="commercial")
        personal = self.rank(records, intent="non-commercial")

        self.assertEqual(commercial["ranked"], [])
        self.assertIn("forbids commercial use", commercial["eliminated"][0]["reason"])
        self.assertEqual(len(personal["ranked"]), 1)

    def test_a_wrong_task_is_refused_with_a_reason_not_silently_dropped(self):
        result = self.rank(
            [
                record(
                    "acme/classifier",
                    params=1_000_000_000,
                    task="image-classification",
                    tags=["license:mit", "safetensors"],
                )
            ]
        )

        self.assertEqual(result["ranked"], [])
        self.assertIn("image-classification", result["eliminated"][0]["reason"])

    def test_gated_is_a_demotion_and_not_an_elimination(self):
        result = self.rank(
            [
                record(
                    "meta/gated",
                    params=3_000_000_000,
                    gated=True,
                    tags=["license:llama3.1", "safetensors"],
                )
            ]
        )

        self.assertEqual(len(result["ranked"]), 1)
        entry = result["ranked"][0]
        self.assertTrue(any("gated" in d for d in entry["demotions"]))
        self.assertLess(entry["score_parts"]["gated_demotion"], 0)
        self.assertTrue(
            any("nobody here accepts a licence" in d.lower() or
                "on your behalf" in d for d in entry["demotions"])
        )

    def test_a_wont_fit_reason_never_argues_with_itself(self):
        """The defect: "needs 5.95 GB, you have 8.0 GB, so it will not fit".

        Two different WONT_FITs - weights alone over the card, and a computed
        total over the card - were being reported with the first one's
        sentence. The result was a refusal whose own numbers said it should
        have fitted, which reads as the product being broken.
        """
        geometry = feasibility.geometry_from_config(
            {
                "num_hidden_layers": 36,
                "hidden_size": 4096,
                "num_attention_heads": 32,
                "num_key_value_heads": 8,
                "vocab_size": 151936,
            },
            source="test",
        )
        candidate = models.summarize(
            record("acme/eight", params=8_000_000_000,
                   tags=["license:apache-2.0", "safetensors"])
        )
        fit = models.fit_of(
            candidate,
            vram=MEASURED_8GB,
            method="qlora",
            seq_len=8192,
            geometry=geometry,
            grad_checkpointing=False,
        )
        self.assertEqual(fit["verdict"], "WONT_FIT")

        reason = models.eliminate(candidate, fit, task=None, intent="unspecified")

        self.assertIsNotNone(reason)
        self.assertIn(str(fit["total_gb"]), reason)
        self.assertNotIn("weights alone", reason)
        # And the sentence must be arithmetically true.
        self.assertGreater(fit["total_gb"], fit["vram_gb"])

    def test_a_floor_says_it_is_a_floor(self):
        candidate = models.summarize(
            record("acme/four", params=4_000_000_000,
                   tags=["license:apache-2.0", "safetensors"])
        )

        without = models.fit_of(
            candidate, vram=MEASURED_8GB, method="qlora", seq_len=2048
        )

        self.assertTrue(without["floor_is_a_floor"])
        self.assertIsNone(without["total_gb"])
        self.assertEqual(without["verdict"], "UNKNOWN")

    def test_adapter_training_is_costed_with_checkpointing_on(self):
        """Costing LoRA without it makes every model on the Hub 'not fit'."""
        candidate = models.summarize(
            record("acme/eight", params=8_000_000_000,
                   tags=["license:apache-2.0", "safetensors"])
        )
        geometry = feasibility.geometry_from_config(
            {
                "num_hidden_layers": 32,
                "hidden_size": 4096,
                "num_attention_heads": 32,
                "num_key_value_heads": 8,
                "vocab_size": 128256,
            },
            source="test",
        )

        default = models.fit_of(
            candidate, vram=MEASURED_8GB, method="qlora", seq_len=2048,
            geometry=geometry,
        )
        naive = models.fit_of(
            candidate, vram=MEASURED_8GB, method="qlora", seq_len=2048,
            geometry=geometry, grad_checkpointing=False,
        )

        self.assertTrue(default["grad_checkpointing"])
        self.assertLess(default["total_gb"], naive["total_gb"])

    def test_a_repo_with_no_readable_size_is_refused_with_the_reason(self):
        result = self.rank([record("acme/mystery", tags=["license:mit"])])

        self.assertEqual(result["ranked"], [])
        self.assertIn("safetensors", result["eliminated"][0]["reason"])


class OfflineTest(unittest.TestCase):
    """The Hub being down is a state to report, not an empty shortlist."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.previous = models.HUB_CACHE_ROOT
        models.HUB_CACHE_ROOT = Path(self.temp.name)
        self.addCleanup(setattr, models, "HUB_CACHE_ROOT", self.previous)

    def test_no_network_and_no_cache_is_not_the_same_as_no_results(self):
        got = models.fetch_json(
            "https://this-host-does-not-exist.invalid/api/models", timeout=2
        )

        self.assertFalse(got["ok"])
        self.assertEqual(got["source"], "unavailable")
        self.assertIn("not the same as", got["help"])

    def test_a_cached_answer_is_served_with_its_age_when_the_network_fails(self):
        url = "https://this-host-does-not-exist.invalid/api/models"
        models._cache_write(url, [{"id": "acme/cached"}])

        # `max_age=-1`, not 0. A cache written microseconds ago can have an age
        # of exactly 0.0, which `age <= max_age` counts as fresh - so this test
        # passed or failed depending on the clock, which is worse than either.
        got = models.fetch_json(url, timeout=2, max_age=-1)

        self.assertTrue(got["ok"])
        self.assertEqual(got["source"], "cache")
        self.assertTrue(got["stale"])
        self.assertIsNotNone(got["age_seconds"])
        self.assertEqual(got["payload"], [{"id": "acme/cached"}])

    def test_a_fresh_cache_is_used_without_touching_the_network_at_all(self):
        url = "https://this-host-does-not-exist.invalid/api/models"
        models._cache_write(url, [{"id": "acme/cached"}])

        got = models.fetch_json(url, timeout=2)

        self.assertEqual(got["source"], "cache")
        self.assertNotIn("stale", got)

    def test_find_models_reports_the_outage_rather_than_an_empty_list(self):
        previous = models.HUB_API
        models.HUB_API = "https://this-host-does-not-exist.invalid/api"
        self.addCleanup(setattr, models, "HUB_API", previous)

        result = models.find_models(task="text-generation", limit=5, detail=0)

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "hub_unavailable")
        self.assertNotIn("ranked", result)


class SearchUrlTest(unittest.TestCase):
    def test_one_request_carries_every_field_the_ranking_needs(self):
        url = models.search_url(task="text-generation", query=None, limit=200)

        for field in ("safetensors", "tags", "downloads", "gated", "sha"):
            with self.subTest(field=field):
                self.assertIn(f"expand%5B%5D={field}", url)
        self.assertIn("pipeline_tag=text-generation", url)
        self.assertIn("limit=200", url)

    def test_the_expand_list_only_names_fields_the_api_accepts(self):
        """Checked against the live API's own error message, once, by hand.

        `childrenModelCount` is not in it, however much the roadmap wanted it.
        """
        accepted = {
            "author", "baseModels", "cardData", "config", "createdAt", "disabled",
            "downloads", "downloadsAllTime", "evalResults", "gated", "inference",
            "inferenceProviderMapping", "lastModified", "library_name", "likes",
            "mask_token", "model-index", "pipeline_tag", "private", "safetensors",
            "sha", "siblings", "spaces", "tags", "transformersInfo", "trendingScore",
            "widgetData", "gguf", "resourceGroup", "xetEnabled",
        }

        self.assertTrue(set(models.LIST_EXPAND) <= accepted,
                        set(models.LIST_EXPAND) - accepted)


class LocalModelGeometryTest(unittest.TestCase):
    """A model already on this disk is a measurement, not a claim."""

    #: The shape `POST /api/show` really returns, taken from the local daemon.
    ORNITH = {
        "general.architecture": "qwen35",
        "general.parameter_count": 8953803264,
        "qwen35.attention.head_count": 16,
        "qwen35.attention.head_count_kv": 4,
        "qwen35.attention.key_length": 256,
        "qwen35.block_count": 32,
        "qwen35.embedding_length": 4096,
    }

    #: The same call for a model whose GGUF carries no kv head count at all.
    GRANITE = {
        "general.architecture": "granitehybrid",
        "granitehybrid.attention.head_count": 12,
        "granitehybrid.attention.head_count_kv": None,
        "granitehybrid.block_count": 40,
        "granitehybrid.embedding_length": 1536,
        "granitehybrid.vocab_size": 100352,
    }

    def test_real_gguf_metadata_becomes_real_geometry(self):
        geometry = models.geometry_from_gguf(self.ORNITH)

        self.assertEqual(geometry.num_hidden_layers, 32)
        self.assertEqual(geometry.num_key_value_heads, 4)
        self.assertEqual(geometry.head_dim, 256)
        self.assertEqual(geometry.provenance, "measured")

    def test_a_null_kv_head_count_falls_back_to_the_head_count(self):
        geometry = models.geometry_from_gguf(self.GRANITE)

        self.assertEqual(geometry.num_key_value_heads, 12)
        self.assertEqual(geometry.vocab_size, 100352)

    def test_a_missing_vocabulary_is_allowed_here_and_not_on_the_config_path(self):
        """Different evidence, so a different requirement, deliberately.

        `general.architecture` already establishes that a GGUF is a decoder,
        which is the thing `vocab_size` stands in for when reading a
        `config.json`. Several real GGUFs on this machine carry no vocab field
        at all; refusing them would throw away a measurement for a formality.
        """
        geometry = models.geometry_from_gguf(self.ORNITH)

        self.assertIsNone(geometry.vocab_size)
        self.assertIsNotNone(geometry.num_hidden_layers)

    def test_nothing_at_all_is_none(self):
        self.assertIsNone(models.geometry_from_gguf({}))
        self.assertIsNone(models.geometry_from_gguf({"general.architecture": "x"}))


class ToolSurfaceTest(unittest.TestCase):
    def test_the_ranking_tools_are_registered_and_declare_no_gate(self):
        from app.tools import REGISTRY
        from app.tools.registry import RESERVED_ARGUMENTS, RESERVED_WRITES

        for name in ("find_models", "read_model_config", "list_local_models"):
            with self.subTest(tool=name):
                spec = REGISTRY.get(name)
                self.assertIsNotNone(spec)
                self.assertEqual(
                    {w.lower() for w in spec.writes} & RESERVED_WRITES, set()
                )
                properties = spec.schema.get("properties") or {}
                self.assertEqual(
                    {k for k in properties if k.lower() in RESERVED_ARGUMENTS}, set()
                )

    def test_find_models_refuses_a_task_the_hub_does_not_have(self):
        result = models.find_models(task="make-me-a-sandwich")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "unknown_task")
        self.assertIn("text-generation", result["known_tasks"])


if __name__ == "__main__":
    unittest.main()
