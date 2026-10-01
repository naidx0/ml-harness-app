"""A continued adapter's manifest names the merged base, not the raw one.

## The silent wrong answer, measured before it was fixed

`runs/dpo-after-sft-2026-09-04` was a real DPO run continuing from a real SFT
adapter, on 2026-09-04. Its saved manifest read:

    "base_model_name_or_path": "HuggingFaceTB/SmolLM2-135M"

which is the RAW BASE, written by `peft`'s `save_pretrained` from the string the
model was loaded from. But that adapter is relative to the SFT-MERGED weights -
`recipes/hf-peft-dpo/entrypoint.py`'s own module docstring says so at length,
and the run wrote a 538 MB `merged_base/` beside it for exactly that reason.

`recipes/hf-peft-lora/entrypoint.py::resolve_base_model` reads that field when
a caller names no `base_model`. So the default route loads raw base + DPO
adapter and scores a model nobody trained. That function's docstring names the
failure itself - *"scoring an adapter against a base it was not trained on
produces a number that looks like a score"* - and offers an override; nothing
makes a caller reach for it, and the recorded value points them away from it.

**A manifest that said nothing would have been safer than one that was
confidently wrong.** That is the whole of this file.

## Why it is tested here and not in the recipe's own suite

`the_base_this_adapter_belongs_to` is pure and takes a dict, so it runs in an
interpreter with no torch, no peft and no GPU - the same argument
`recipes/hf-peft-dpo` makes for splitting out `adapter_keys_in`: the decision
is the part that was wrong, and it is the part a suite with nothing installed
can still exercise.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import support

dpo = support.import_file(
    "hf_peft_dpo_entrypoint",
    support.REPO_ROOT / "recipes" / "hf-peft-dpo" / "entrypoint.py",
)

#: What `peft` actually wrote on the 2026-09-04 run, trimmed to the keys that
#: matter. Copied rather than invented, so the fixture cannot drift into a
#: shape peft never produces.
AS_PEFT_WROTE_IT = {
    "base_model_name_or_path": "HuggingFaceTB/SmolLM2-135M",
    "peft_type": "LORA",
    "r": 16,
    "lora_alpha": 32,
}


class AContinuedRunNamesTheMergedBaseTest(unittest.TestCase):
    def test_the_manifest_points_at_the_weights_the_adapter_is_relative_to(self):
        merged = Path("runs/dpo-after-sft-2026-09-04/merged_base")
        fixed = dpo.the_base_this_adapter_belongs_to(AS_PEFT_WROTE_IT, merged)
        self.assertEqual(fixed["base_model_name_or_path"], str(merged))

    def test_where_the_lineage_started_is_kept_rather_than_overwritten(self):
        """Which model the lineage began from is still true and still useful.
        It is simply not the thing to load this adapter onto."""
        merged = Path("runs/x/merged_base")
        fixed = dpo.the_base_this_adapter_belongs_to(AS_PEFT_WROTE_IT, merged)
        self.assertEqual(fixed["mlh_trained_from_base"], "HuggingFaceTB/SmolLM2-135M")
        self.assertEqual(fixed["mlh_merged_base"], str(merged))

    def test_everything_peft_wrote_survives(self):
        """A rewrite that dropped `r` or `peft_type` would produce a manifest
        that no longer loads, which is a worse failure than the one being
        fixed."""
        fixed = dpo.the_base_this_adapter_belongs_to(
            AS_PEFT_WROTE_IT, Path("runs/x/merged_base")
        )
        for key in ("peft_type", "r", "lora_alpha"):
            with self.subTest(key=key):
                self.assertEqual(fixed[key], AS_PEFT_WROTE_IT[key])

    def test_a_run_from_the_raw_base_is_left_exactly_alone(self):
        """THE OTHER HALF, and without it this is a function that breaks the
        case that was already right. `runs/dpo-synthetic-2026-09-04` started
        from the raw base, so what peft recorded is correct there."""
        self.assertEqual(
            dpo.the_base_this_adapter_belongs_to(AS_PEFT_WROTE_IT, None),
            AS_PEFT_WROTE_IT,
        )

    def test_it_does_not_mutate_what_it_was_handed(self):
        before = dict(AS_PEFT_WROTE_IT)
        dpo.the_base_this_adapter_belongs_to(AS_PEFT_WROTE_IT, Path("runs/x/m"))
        self.assertEqual(AS_PEFT_WROTE_IT, before)


class TheScorerWouldHaveBeenMisledTest(unittest.TestCase):
    """The other end of the same wire, so this file states the whole failure.

    `resolve_base_model` is what reads the field. These assert the behaviour
    this fix depends on, so a change there that made the manifest irrelevant
    would fail here rather than silently making this fix pointless.
    """

    def setUp(self):
        self.lora = support.import_file(
            "hf_peft_lora_entrypoint",
            support.REPO_ROOT / "recipes" / "hf-peft-lora" / "entrypoint.py",
        )

    def test_the_scorer_reads_the_manifest_when_no_base_is_named(self):
        root = support.sandbox(self)
        adapter = root / "adapter"
        adapter.mkdir()
        (adapter / "adapter_config.json").write_text(
            '{"base_model_name_or_path": "some/merged/path"}', encoding="utf-8"
        )
        self.assertEqual(
            self.lora.resolve_base_model({}, adapter), "some/merged/path"
        )

    def test_an_explicit_base_still_wins(self):
        """The override the docstring offers has to keep working, because it is
        the escape hatch for a relocated base."""
        root = support.sandbox(self)
        adapter = root / "adapter"
        adapter.mkdir()
        (adapter / "adapter_config.json").write_text(
            '{"base_model_name_or_path": "wrong/one"}', encoding="utf-8"
        )
        self.assertEqual(
            self.lora.resolve_base_model({"base_model": "right/one"}, adapter),
            "right/one",
        )


if __name__ == "__main__":
    unittest.main()
