"""A run record that carries a peak and not its configuration is uncomparable.

## What went wrong

`load_in_4bit` appeared in **0 of 43** existing training records and
`grad_checkpointing` was left to its default by **38 of 43**, so two runs at four
times the memory of each other read identically. Meanwhile `max_seq_len` is a
CAP: two runs under one 512 cap realised **36 and 339 tokens per step**, a 9.4x
spread that three lanes explained three different ways - run-to-run noise, a
checkpointing treatment, a dataset difference - before anybody read `num_tokens`,
which was being emitted the whole time.

## And the field that was worst, because it was a claim rather than an omission

`fp16=True` was set in the trainer args, a comment beside it explained that this
card has no native bf16, and another said *"every adapter on this disk was
trained fp16"*. **Measured 2026-09-10: all of that was false.** The recipe handed
TRL a model NAME, TRL called `from_pretrained` with no dtype, and transformers
defaults to **fp32** - it does not honour the checkpoint's own `torch_dtype`
unless asked:

    from_pretrained("HuggingFaceTB/SmolLM2-135M")                 -> torch.float32
    from_pretrained("HuggingFaceTB/SmolLM2-135M", dtype=float16)  -> torch.float16
    that checkpoint's config says                                 -> bfloat16

So every fp16 memory estimate this project made priced the base at half what it
cost, which is most of an evening's worth of "the estimator is optimistic". The
recipe now passes the dtype it claims, and this file pins both the passing and
the recording.
"""

import unittest
from pathlib import Path

import support  # noqa: F401  - installs the suite's sandbox fences

REPO_ROOT = Path(__file__).resolve().parent.parent
ENTRYPOINT = REPO_ROOT / "recipes" / "hf-peft-lora" / "entrypoint.py"

#: Every key a run record must carry for its peak to be placeable against
#: another run's. Each was absent before 2026-09-10.
REQUIRED = (
    "peak_train_vram_gb",
    "peak_load_vram_gb",
    "load_in_4bit",
    "base_dtype",
    "revision",
    "optimizer",
    "target_modules",
    "batch_size",
    "grad_accum",
    "max_seq_len",
    "num_tokens",
)


class TheRecipePassesTheDtypeItClaimsTest(unittest.TestCase):
    def setUp(self):
        self.source = ENTRYPOINT.read_text(encoding="utf-8")

    def test_the_fp16_path_loads_the_model_itself(self):
        """Handing TRL a STRING is what caused this: TRL then loads it with no
        dtype and transformers picks fp32."""
        self.assertIn(
            "AutoModelForCausalLM.from_pretrained(\n            base_model, dtype=base_dtype\n        )",
            self.source,
            "the non-quantised path no longer loads the model with an explicit "
            "dtype, so it is back to whatever transformers defaults to - which "
            "is fp32, not the fp16 the trainer args claim.",
        )

    def test_it_does_not_reach_for_auto(self):
        """`auto` would take the bfloat16 in the checkpoint config, and this
        card is sm_75 with no native bf16 - the same reason `fp16=True` is set
        rather than `bf16=True`."""
        self.assertNotIn('base_dtype", "auto"', self.source)
        self.assertIn('config.get("base_dtype", "float16")', self.source)

    def test_an_unknown_dtype_is_refused_rather_than_guessed(self):
        self.assertIn("unknown base_dtype", self.source)
        self.assertIn("train at a precision", self.source)

    def test_the_false_claim_is_gone(self):
        """The comment said every adapter here was trained fp16. It was not, and
        a comment that is measured false is worse than no comment."""
        self.assertNotIn(
            "every adapter on this disk was trained fp16; flipping the",
            self.source,
            "the fp16 claim is back in the source and it was measured false.",
        )


class TheRecordSaysWhatItTrainedTest(unittest.TestCase):
    def setUp(self):
        self.source = ENTRYPOINT.read_text(encoding="utf-8")
        # THE WHOLE emit CALL, not a fixed-width window. The first version took
        # `[start:start + 2000]`, and adding two fields pushed the last one past
        # the window - so a test guarding "the record carries these keys" went
        # red because the record grew. That is the second brittle assertion in
        # this file: the first pinned a literal source line and broke when the
        # line was corrected. Both measured the shape of the code rather than
        # the property being asserted.
        start = self.source.index('"finished",')
        end = self.source.index("\n    )", start)
        self.finished = self.source[start:end]

    def test_every_placing_field_is_in_the_finished_event(self):
        for key in REQUIRED:
            with self.subTest(key=key):
                self.assertIn(
                    f"{key}=", self.finished,
                    f"a run record without {key} cannot be compared with "
                    "another run: two runs differing only in this field would "
                    "read identically.",
                )

    def test_the_target_modules_are_resolved_and_not_the_absence(self):
        """LoraConfig leaves `target_modules` to peft's default, so the CONFIG
        says None while the run trained q_proj/v_proj. Recording None would
        write down a question."""
        self.assertIn("peft_config", self.finished)
        self.assertIn("target_modules", self.finished)

    def test_num_tokens_comes_from_the_per_step_logs(self):
        """It is NOT in `result.metrics`, and the first version of this read it
        from there - so the field added to make a peak interpretable recorded
        `null`. Only running it found that.

        Asserted as *the per-step capture is consulted* rather than as a literal
        expression: the first version of this test pinned the exact source line
        and went red the moment the code it guarded was corrected, which is a
        test measuring the spelling of a fix instead of the fix.
        """
        self.assertIn("num_tokens=", self.finished)
        self.assertIn('seen["num_tokens"]', self.finished)
        self.assertIn('logs.get("num_tokens")', self.source,
                      "nothing captures num_tokens from the per-step logs, so "
                      "the finished record will carry null again.")


class TheTwoPeaksAreSeparatedTest(unittest.TestCase):
    """`max_memory_allocated` is a high-water mark from PROCESS START, and this
    recipe never reset it - so every peak it ever reported also contained
    whatever the load transiently allocated, which for a 4-bit run is the fp16
    weights that exist briefly before being quantised away.

    Resetting before `train()` separates them. **Both are kept and the old name
    keeps its old meaning**: renaming `peak_vram_gb` would have silently changed
    what every already-published number referred to.

    Measured 2026-09-10, SmolLM2-1.7B 4-bit batch 4, twice: process high-water
    **2.12**, train-only **2.12**, load **1.59**. The load transient is BELOW the
    training peak, so the gap between the allocator sum and the reported peak is
    not a load artefact - it is a training term the estimate does not contain.
    """

    def setUp(self):
        self.source = ENTRYPOINT.read_text(encoding="utf-8")

    def test_the_peak_is_reset_before_training(self):
        self.assertIn("reset_peak_memory_stats", self.source,
                      "without the reset, a training peak cannot be told apart "
                      "from a load transient and every band is built on the sum "
                      "of both.")

    def test_the_reset_happens_before_train_and_not_after(self):
        source = self.source
        self.assertLess(
            source.index("reset_peak_memory_stats"),
            source.index("result = trainer.train()"),
            "resetting after training would zero the very measurement it is "
            "meant to isolate.",
        )

    def test_the_old_field_keeps_the_old_meaning(self):
        """A field that quietly narrows its definition invalidates every number
        already recorded against it, with nothing saying so."""
        self.assertIn("max(x for x in (load_peak_gb, train_peak_gb)", self.source)


class TheNextStepSentenceIsTrueOfBothStatesTest(unittest.TestCase):
    """It used to be true of a running job and false of a queued one.

    The reply said *"The run has its own process group, so closing this app does
    not stop it."* A job is created `queued`; `start_supervisor` starts a DAEMON
    thread; only when that thread reaches `runner.run_next_job` does a child
    process exist with its own group. Until then the job depends on the calling
    process staying alive, and a daemon thread dies with it silently - leaving a
    row indistinguishable from a job about to start.

    Measured 2026-09-10: a `start_training` call from a short-lived script left
    job 5 `queued`, no error anywhere. Through the engine that window is a
    moment; for a direct caller it is permanent, and the sentence told that
    caller the opposite of the truth.
    """

    def setUp(self):
        self.source = (REPO_ROOT / "app" / "tools" / "training.py").read_text(
            encoding="utf-8"
        )

    def test_it_says_the_job_starts_queued(self):
        self.assertIn("It is QUEUED", self.source,
                      "the reply no longer tells the caller the job is queued "
                      "before it runs, which is the half that was missing.")

    def test_it_says_the_supervisor_lives_in_the_calling_process(self):
        self.assertIn("thread in", self.source)
        self.assertIn("exits straight", self.source)

    def test_it_still_says_what_was_true_about_a_started_run(self):
        """The old sentence was not wrong, only unqualified. Dropping it would
        trade one incomplete claim for another."""
        self.assertIn("own process group", self.source)

    def test_the_unqualified_claim_is_gone(self):
        self.assertNotIn(
            "The run has its own process group, so closing this app does not "
            "stop it.",
            self.source,
            "the unqualified sentence is back, and it is false of a queued job.",
        )


class ThePredictionCarriesTheCallersRowIdTest(unittest.TestCase):
    """`row_index` is positional; a scorer keying on the eval file's own ids
    reads it as if it were one, and the two collide in silence.

    Measured 2026-09-10: `evals/architecture-json/edge_direction.py` keys every
    `held-out*.jsonl` by `row_id` and looks up `ref[row_index]`. The extra
    held-out set starts its ids at **100** — chosen so an extra could never be
    mistaken for an original — so a predictions file straight from this recipe
    scored answer 0 against the ORIGINAL set's row 0, all the way down, and
    produced a table that looked entirely reasonable.

    Carrying the caller's own id changes neither convention. Driven the same
    day: rows given `row_index` 0-2 and `row_id` 100-102 came back carrying
    both.
    """

    def setUp(self):
        self.source = ENTRYPOINT.read_text(encoding="utf-8")

    def test_a_supplied_row_id_survives_into_the_plan(self):
        self.assertIn('if row.get("row_id") is not None:', self.source)

    def test_it_reaches_the_prediction_record(self):
        self.assertIn('{"row_id": row["row_id"]}', self.source,
                      "the id is kept on the plan but never written to "
                      "predictions.jsonl, which is the file a scorer reads.")

    def test_row_index_is_still_required_and_still_positional(self):
        """The fix must not turn `row_index` into something optional: every
        paired comparison in this product depends on it meaning a position."""
        self.assertIn("has no 'row_index'", self.source)
        self.assertIn("appears twice in config.rows", self.source)

    def test_only_the_id_is_passed_through(self):
        """A pass-through of arbitrary keys is a way to smuggle a field nobody
        chose into a file this recipe is responsible for."""
        self.assertNotIn("**row", self.source)


if __name__ == "__main__":
    unittest.main()
