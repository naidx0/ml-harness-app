"""Where to train is a question about this machine, this job and one constraint.

## What `rent_advice` was

    def rent_advice(needed_gb: float) -> Dict[str, Any]:
        if needed_gb <= 24:  ... "RTX 4090", 0.60
        elif needed_gb <= 48: ... "A6000",   0.90
        else:                 ... "A100 80GB", 1.80

Three branches over a number the caller passed in. It never looked at the
machine, it never looked at the job, and it named a card and a price - which is
the shape of a recommendation. Three things were missing and each one changes
the answer rather than decorating it:

* **The machine and the job.** `needed_gb` came from wherever the caller got it.
  Now it comes from the model's own `config.json` and the method, through the
  same arithmetic that answers `can_this_machine_train`, so the two answers
  cannot disagree about how much memory the job wants.
* **The date on the price.** "Static table (prices are indicative, RunPod, Aug
  2026)" was inside a sentence, which meant nothing could compute how stale it
  was. It is a date now, and every answer carries the age in days.
* **The constraint.** Max cannot send his data to a hosted model - insurance,
  compliance. That is not a footnote on a rental table, it deletes the rental
  option, and a product that quotes him $0.90 an hour for a card he may not use
  has answered a question he did not ask. `privacy` is a declared fact of
  `docs/diagnosis_engine.yaml`; this file proves the placement answer reads it.

## And the number that stays UNKNOWN

Cost is hours times price. The price is indicative and dated. The hours are
UNKNOWN, because nothing in this harness has ever recorded how long a training
step took - `tests/test_the_proposal_is_executable.py` asserts that same gap
for build steps and it is the same gap. So no total is computed. Multiplying an
indicative price by an invented duration would produce the most convincing
number on the page and the least true one, which is `AGENTS.md` invariant 5 in
its most tempting form.
"""

from __future__ import annotations

import unittest

from app import feasibility
from app.tools import REGISTRY

import support


MAX_VRAM_GB = 8.0
BIG = "Qwen/Qwen3-8B"
SMALL = "Qwen/Qwen3-4B"


class ThePriceIsIndicativeAndSaysSo(unittest.TestCase):
    def test_the_three_rows_still_price_the_same_way(self):
        """The rows did not change and are not supposed to.

        Adding a row means typing a price nobody here measured. The fix was
        never a bigger table, and `tests/test_step_2_4.py` still asserts the
        A6000 figure at 30 GB.
        """
        self.assertAlmostEqual(feasibility.rent_advice(30.0)["usd_per_hour"], 0.90)
        self.assertEqual(feasibility.rent_advice(12.0)["gpu"], "RTX 4090")
        self.assertEqual(feasibility.rent_advice(60.0)["gpu"], "A100 80GB")

    def test_it_picks_the_smallest_card_that_actually_holds_the_job(self):
        for needed, expected in ((8.0, 24), (24.0, 24), (24.1, 48), (48.0, 48), (49.0, 80)):
            with self.subTest(needed=needed):
                self.assertEqual(feasibility.rent_advice(needed)["vram_gb"], expected)

    def test_every_price_carries_its_provenance_and_its_age(self):
        advice = feasibility.rent_advice(30.0)
        self.assertEqual("indicative", advice["price_provenance"])
        self.assertEqual(feasibility.RENT_TABLE_AS_OF, advice["priced_as_of"])
        self.assertIsInstance(advice["price_age_days"], int)
        self.assertGreaterEqual(advice["price_age_days"], 0)
        self.assertIn("Indicative and dated", advice["note"])

    def test_a_job_bigger_than_the_biggest_row_is_told_so(self):
        advice = feasibility.rent_advice(200.0)
        self.assertIn("note_on_size", advice)
        self.assertIn("multi-GPU", advice["note_on_size"])

    def test_no_total_is_ever_computed(self):
        advice = feasibility.rent_advice(30.0)
        self.assertIsNone(advice["total_usd"])
        self.assertEqual("UNKNOWN", advice["hours"]["provenance"])
        self.assertIsNone(advice["hours"]["value"])
        self.assertTrue(advice["hours"]["find_out_by"].strip())


class TheAnswerComesFromTheMachineAndTheJob(unittest.TestCase):
    def setUp(self) -> None:
        support.sandbox(self)

    def test_two_different_models_want_two_different_amounts(self):
        """The proof that this is not a constant any more.

        A table keyed on nothing gives the same answer to every question. Two
        models of different sizes, on the same card with the same method, must
        produce two different memory figures - and they do, because both are
        computed from the models' own `config.json`.
        """
        big = REGISTRY.call(
            "where_to_train", {"repo_id": BIG, "method": "qlora", "seq_len": 2048, "vram_gb": MAX_VRAM_GB},
            actor="model",
        )
        small = REGISTRY.call(
            "where_to_train",
            {"repo_id": SMALL, "method": "qlora", "seq_len": 2048, "vram_gb": MAX_VRAM_GB},
            actor="model",
        )
        self.assertNotEqual(big["needed_gb"], small["needed_gb"])
        self.assertGreater(big["needed_gb"], small["needed_gb"])

    def test_the_method_changes_the_answer(self):
        qlora = REGISTRY.call(
            "where_to_train",
            {"repo_id": SMALL, "method": "qlora", "seq_len": 1024, "vram_gb": MAX_VRAM_GB},
            actor="model",
        )
        full = REGISTRY.call(
            "where_to_train",
            {"repo_id": SMALL, "method": "full", "seq_len": 1024, "vram_gb": MAX_VRAM_GB},
            actor="model",
        )
        self.assertGreater(full["needed_gb"], qlora["needed_gb"])

    def test_the_placement_and_the_yes_no_never_disagree(self):
        """One arithmetic, two answers. Not two arithmetics."""
        for repo, method, length in (
            (BIG, "qlora", 2048),
            (SMALL, "qlora", 2048),
            (SMALL, "lora", 512),
        ):
            with self.subTest(repo=repo, method=method):
                here = REGISTRY.call(
                    "can_this_machine_train",
                    {
                        "repo_id": repo,
                        "method": method,
                        "seq_len": length,
                        "vram_gb": MAX_VRAM_GB,
                    },
                    actor="model",
                )
                placed = REGISTRY.call(
                    "where_to_train",
                    {
                        "repo_id": repo,
                        "method": method,
                        "seq_len": length,
                        "vram_gb": MAX_VRAM_GB,
                    },
                    actor="model",
                )
                self.assertEqual(here["needed_gb"], placed["needed_gb"])
                self.assertEqual(here["answer"], placed["fits_on_this_machine"])
                if here["answer"] == "YES":
                    self.assertEqual("LOCAL", placed["answer"])


class ComplianceIsAFactAndItDeletesAnOption(unittest.TestCase):
    """Max cannot use hosted models. That changes the answer, it does not annotate it."""

    def setUp(self) -> None:
        support.sandbox(self)
        self.threads = support.conversations(1)
        self.thread_id = self.threads[0]["id"]

    def test_privacy_is_a_declared_fact_of_the_ledger(self):
        """Derived from the spec, so this cannot pass on a fact that was deleted."""
        from app import diagnosis

        spec = diagnosis.default_spec()
        self.assertIn("privacy", spec.facts)
        members = set(spec.facts["privacy"]["enum"])
        self.assertTrue(
            set(feasibility.CLOUD_IS_RULED_OUT_BY) <= members,
            "the values this module treats as ruling out cloud must all be real "
            "members of the ledger's own privacy enum, or it is deciding on a "
            "word the engine has never heard of",
        )

    def test_a_regulated_business_is_not_offered_a_rented_card(self):
        answer = REGISTRY.call(
            "where_to_train",
            {"repo_id": BIG, "method": "qlora", "seq_len": 2048, "privacy": "regulated", "vram_gb": MAX_VRAM_GB},
            actor="user",
            thread_id=self.thread_id,
        )
        self.assertEqual("OWN_HARDWARE", answer["answer"])
        self.assertFalse(answer["cloud_available"])
        self.assertIsNone(answer["rent"])
        self.assertIsNone(answer["cost"]["usd_per_hour"])
        self.assertTrue(answer["cloud_ruled_out_because"])

    def test_the_same_job_without_the_constraint_is_offered_one(self):
        answer = REGISTRY.call(
            "where_to_train",
            {"repo_id": BIG, "method": "qlora", "seq_len": 2048, "privacy": "public_ok", "vram_gb": MAX_VRAM_GB},
            actor="user",
            thread_id=self.thread_id,
        )
        self.assertEqual("RENTED_VM", answer["answer"])
        self.assertTrue(answer["cloud_available"])
        self.assertIsNotNone(answer["rent"])
        self.assertEqual("indicative", answer["rent"]["price_provenance"])

    def test_a_constraint_stated_three_turns_ago_still_decides_this_turn(self):
        """The point of the constraint being a FACT rather than an argument.

        The user says it once, through `state_facts`, in their own person. The
        placement question is asked later with no mention of privacy at all, and
        the answer is still the one their compliance regime requires.
        """
        REGISTRY.call(
            "state_facts",
            {"facts": {"privacy": "on_prem_only"}},
            actor="user",
            thread_id=self.thread_id,
        )
        answer = REGISTRY.call(
            "where_to_train",
            {"repo_id": BIG, "method": "qlora", "seq_len": 2048, "vram_gb": MAX_VRAM_GB},
            actor="model",
            thread_id=self.thread_id,
        )
        self.assertFalse(answer["cloud_available"])
        self.assertEqual("STATED", answer["constraint_origins"]["privacy"])

    def test_when_nobody_has_said_the_answer_says_it_is_assuming(self):
        answer = REGISTRY.call(
            "where_to_train",
            {"repo_id": BIG, "method": "qlora", "seq_len": 2048, "vram_gb": MAX_VRAM_GB},
            actor="model",
            thread_id=self.thread_id,
        )
        self.assertIn("what_would_sharpen_this", answer)
        self.assertEqual("privacy", answer["what_would_sharpen_this"]["fact"])
        self.assertEqual("state_facts", answer["what_would_sharpen_this"]["tool"])
        self.assertEqual("user", answer["what_would_sharpen_this"]["run_as"])

    def test_a_no_without_a_cloud_option_still_names_a_smaller_job_that_fits(self):
        """A refusal with no route back is a refusal. This one has three."""
        answer = REGISTRY.call(
            "where_to_train",
            {"repo_id": BIG, "method": "lora", "seq_len": 2048, "privacy": "regulated", "vram_gb": MAX_VRAM_GB},
            actor="user",
            thread_id=self.thread_id,
        )
        self.assertEqual("OWN_HARDWARE", answer["answer"])
        self.assertTrue(answer["a_smaller_job_that_would_fit"])
        joined = " ".join(answer["a_smaller_job_that_would_fit"])
        self.assertIn("QLoRA", joined)
        self.assertIn("find_models", joined)


if __name__ == "__main__":
    unittest.main()
