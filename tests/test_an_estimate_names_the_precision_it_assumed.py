"""A number correct about the machine and wrong about the software.

A 1.5B model was priced at 0.74 GiB of base weights and a training run
recommended on it. 0.74 is an **NF4** figure; the same 1,543,569,408 parameters
at fp16 are 2.88 GiB. The recipe that would have run it could not quantise -
`bitsandbytes` was absent from its lock file and `load_in_4bit` from its
entrypoint - so the estimate priced a configuration the product could not
execute, and in fp16 every sequence length on that card is infeasible.

`app/feasibility.py` refuses when it has no geometry. It cannot refuse when it
HAS geometry and the runner cannot reach the precision it assumed, because
nothing in the harness could answer that. `app/recipe_precision.py` answers it,
and the case below is the real one: the module is pointed at the recipe as it
stood at `1550563^`, the tree that produced the mistake, and refuses.

## The asymmetry, asserted rather than hoped

A static read of a lock file and an entrypoint is weaker than running the thing.
`can_reach` returning **False** is trustworthy: without the dependency the path
cannot work. Returning **True** is as good as the recipe's own declarations and
no better. Both directions are tested, and the docstring says which is which,
because a check that is honest in one direction and sold as honest in both is
the same fault one level up.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import support

from app import recipe_precision


class ARecipeThatCannotQuantiseSaysSoTest(unittest.TestCase):
    """THE CASE, and it is the evening it cost."""

    def setUp(self):
        self.root = Path(support.sandbox(self))

    def a_recipe(self, *, lock: str, entrypoint: str) -> Path:
        where = self.root / "hf-peft-lora"
        where.mkdir(parents=True, exist_ok=True)
        (where / "requirements.lock").write_text(lock, encoding="utf-8")
        (where / "entrypoint.py").write_text(entrypoint, encoding="utf-8")
        return where

    def test_neither_the_package_nor_the_path_refuses_and_names_the_package(self):
        where = self.a_recipe(lock="torch==2.4.0\ntrl==0.9.6\n", entrypoint="x = 1\n")
        self.assertFalse(recipe_precision.can_reach(where, "NF4"))
        said = recipe_precision.why_not(where, "NF4")
        self.assertIn("bitsandbytes", said)
        #: THE SENTENCE THAT SENDS SOMEBODY SOMEWHERE USEFUL. "Your card is too
        #: small" and "this recipe cannot quantise" are different actions on the
        #: same arithmetic.
        self.assertIn("fail at import, not at the card", said)

    def test_the_package_without_the_code_path_is_still_a_refusal(self):
        """A recipe can depend on a library it never calls. The lock file alone
        is what a reader checks and is not what runs."""
        where = self.a_recipe(
            lock="torch==2.4.0\nbitsandbytes==0.43.1\n", entrypoint="x = 1\n"
        )
        self.assertFalse(recipe_precision.can_reach(where, "NF4"))
        said = recipe_precision.why_not(where, "NF4")
        self.assertIn("never names", said)
        self.assertIn("load_in_4bit", said)

    def test_both_halves_present_is_reachable(self):
        where = self.a_recipe(
            lock="bitsandbytes==0.43.1\n",
            entrypoint="cfg = dict(load_in_4bit=True)\n",
        )
        self.assertTrue(recipe_precision.can_reach(where, "NF4"))
        self.assertIsNone(recipe_precision.why_not(where, "NF4"))

    def test_fp16_needs_nothing_and_is_never_refused(self):
        """A recipe that trains at all trains in fp16, so there is nothing to
        look for. Refusing it would be inventing a requirement."""
        where = self.a_recipe(lock="torch==2.4.0\n", entrypoint="x = 1\n")
        self.assertTrue(recipe_precision.can_reach(where, "FP16"))

    def test_a_precision_the_harness_does_not_know_is_refused_and_not_allowed(self):
        """Unknown must not read as unconstrained - that is the direction where
        being wrong prices something nobody can run."""
        where = self.a_recipe(lock="", entrypoint="")
        self.assertFalse(recipe_precision.can_reach(where, "FP8"))
        self.assertIn("not a precision", recipe_precision.why_not(where, "FP8"))

    def test_a_recipe_that_is_not_there_reads_as_unable(self):
        self.assertFalse(recipe_precision.can_reach(self.root / "absent", "NF4"))


class ItPricesWhatTheRecipeWillActuallyLoadTest(unittest.TestCase):
    """fp16 claimed, fp32 loaded - the evening's missing constant.

    `hf-peft-lora` hands `SFTTrainer` the base model as a STRING on the
    unquantised path, so nothing calls `from_pretrained` with a dtype and
    transformers loads at its own default: fp32. `fp16=True` in
    `TrainingArguments` is autocast over fp32 master weights, not a
    half-precision load. Every adapter on this disk labelled fp16 was trained at
    four bytes per parameter while the estimator priced two.
    """

    def setUp(self):
        self.root = Path(support.sandbox(self))

    def a_recipe(self, *, declares: str | None) -> Path:
        where = self.root / "hf-peft-lora"
        where.mkdir(parents=True, exist_ok=True)
        lines = ['name = "hf-peft-lora"', 'kinds = ["train"]']
        if declares:
            lines += ["[defaults]", f'dtype = "{declares}"']
        (where / "recipe.toml").write_text(
            chr(10).join(lines) + chr(10), encoding="utf-8"
        )
        (where / "requirements.lock").write_text(
            "torch==2.6.0" + chr(10), encoding="utf-8"
        )
        #: The shape that causes it: the base handed to the trainer as a STRING,
        #: so nothing ever calls `from_pretrained` with a dtype.
        (where / "entrypoint.py").write_text(
            "model_for_trainer = base_model" + chr(10), encoding="utf-8"
        )
        return where

    def test_asking_for_fp16_and_declaring_nothing_prices_at_fp32(self):
        """THE CASE. The estimate must not report the precision it was asked
        for when the recipe will not load it."""
        where = self.a_recipe(declares=None)
        loads, why = recipe_precision.what_it_will_load(where, "FP16")
        self.assertEqual(loads, "FP32")
        self.assertIn("names no dtype", why)
        self.assertIn("autocast", why)

    def test_a_recipe_that_declares_half_precision_is_taken_at_its_word(self):
        where = self.a_recipe(declares="float16")
        loads, why = recipe_precision.what_it_will_load(where, "FP16")
        self.assertEqual(loads, "FP16")
        self.assertIsNone(why)

    def test_a_declaration_that_disagrees_with_the_request_says_so(self):
        where = self.a_recipe(declares="bfloat16")
        loads, why = recipe_precision.what_it_will_load(where, "FP16")
        self.assertEqual(loads, "BF16")
        self.assertIn("declares it loads BF16", why)

    def test_asking_for_fp32_is_not_a_complaint(self):
        """Nobody is surprised by getting what the framework does anyway."""
        where = self.a_recipe(declares=None)
        self.assertEqual(
            recipe_precision.what_it_will_load(where, "FP32"), ("FP32", None)
        )

    def test_the_quantised_path_is_not_downgraded(self):
        """MUST NOT OVER-CLAIM. The 4-bit branch passes `dtype=torch.float16`
        beside its BitsAndBytesConfig, so an NF4 request loads what it asked
        for. Reporting fp32 here would be this check inventing a second bug."""
        where = self.a_recipe(declares=None)
        (where / "requirements.lock").write_text(
            "bitsandbytes==0.50.2" + chr(10), encoding="utf-8"
        )
        (where / "entrypoint.py").write_text(
            "load_in_4bit=True" + chr(10), encoding="utf-8"
        )
        loads, why = recipe_precision.what_it_will_load(where, "NF4")
        self.assertEqual(loads, "NF4")
        self.assertIsNone(why)


class TheRealRecipeIsTheCaseTest(unittest.TestCase):
    """Against the shipped recipe, not a fixture."""

    LORA = support.REPO_ROOT / "recipes" / "hf-peft-lora"

    def test_the_shipped_training_recipe_loads_fp32_when_asked_for_fp16(self):
        if not self.LORA.is_dir():
            self.skipTest("hf-peft-lora is not in this checkout")
        loads, why = recipe_precision.what_it_will_load(self.LORA, "FP16")
        self.assertEqual(loads, "FP32")
        self.assertIsNotNone(why)

    def test_and_its_four_bit_path_still_loads_four_bit(self):
        if not self.LORA.is_dir():
            self.skipTest("hf-peft-lora is not in this checkout")
        self.assertEqual(
            recipe_precision.what_it_will_load(self.LORA, "NF4"), ("NF4", None)
        )


class TheRealRecipesAreCheckedTest(unittest.TestCase):
    """Live facts about the recipes this harness ships."""

    RECIPES = support.REPO_ROOT / "recipes"

    def test_the_dpo_recipe_still_cannot_reach_nf4(self):
        """RECORDED BECAUSE IT IS THE SAME TRAP, STILL OPEN. The LoRA recipe
        gained a 4-bit path; the preference recipe did not, so a QLoRA-priced
        DPO run is the mistake that just cost an evening, waiting to happen
        again on a different recipe."""
        where = self.RECIPES / "hf-peft-dpo"
        if not where.is_dir():
            self.skipTest("hf-peft-dpo is not in this checkout")
        self.assertFalse(recipe_precision.can_reach(where, "NF4"))

    def test_every_recipe_can_reach_fp16(self):
        for where in sorted(p for p in self.RECIPES.iterdir() if p.is_dir()):
            with self.subTest(recipe=where.name):
                self.assertTrue(recipe_precision.can_reach(where, "FP16"))


class WhichDirectionThisCheckIsHonestInTest(unittest.TestCase):
    """False is trustworthy. True is as good as the recipe's declarations."""

    def setUp(self):
        self.root = Path(support.sandbox(self))

    def test_a_declaration_is_not_an_execution(self):
        """A recipe naming both halves reads as reachable even though this
        module has run nothing. Asserted so the limit is in the suite and not
        only in a docstring - a reader who needs certainty has to run the
        recipe, and this says so."""
        where = self.root / "claims-a-lot"
        where.mkdir(parents=True)
        (where / "requirements.lock").write_text("bitsandbytes==0.0.0\n", encoding="utf-8")
        (where / "entrypoint.py").write_text(
            "# load_in_4bit appears in a comment and nothing calls it\n",
            encoding="utf-8",
        )
        self.assertTrue(recipe_precision.can_reach(where, "NF4"))


if __name__ == "__main__":
    unittest.main()
