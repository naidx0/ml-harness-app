"""The training showcase's four planted cases, made runnable before the run.

`docs/journeys/2026-09-06-the-training-showcase-planted-cases.md` states them as
prose and as expectations. Prose does not fail. These run against a fixture and
the product's own functions, so a case that stops being true stops the gate
rather than waiting for someone to reread the page.

    1. the estimator refuses rather than guesses - and the refusal is easy to
       misread, because the geometry is one level down
    2. the card is not free just because no lock file exists
    3. the 164 rows are the run's own output, not a fixture
    4. a refused training run leaves a record

**None of them needs the card**, which is the point of writing them now: every
one is about what the showcase must do BEFORE it allocates anything, and the
first is about a mistake a caller makes while the card sits idle.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import support

# Imported as package modules, not via `support.import_file`: `feasibility`
# defines frozen dataclasses, and a dataclass resolving its own annotations
# looks its module up in `sys.modules`, which `import_file` deliberately does
# not populate. The same failure that made every `card_owner` type a NamedTuple.
from app import feasibility, hwdetect  # noqa: E402

#: A real stored file, in the shape the product actually saves them.
A_STORED_MODEL = (
    support.REPO_ROOT / "app" / "model_configs" / "HuggingFaceTB--SmolLM2-1.7B.json"
)


def the_stored_file() -> dict:
    return json.loads(A_STORED_MODEL.read_text(encoding="utf-8"))


class CaseOneTheEstimatorRefusesRatherThanGuessesTest(unittest.TestCase):
    """The provenance law: unmeasurable renders unknown, never zero."""

    def test_with_no_geometry_the_largest_terms_are_none_not_zero(self):
        said = feasibility.estimate_training_vram(
            params_b=1.7, method="qlora", seq_len=2048
        )
        for term in ("total_gb", "activations_gb", "logits_gb"):
            with self.subTest(term=term):
                self.assertIsNone(
                    said[term],
                    f"{term} is not None without geometry - a zero here reads as "
                    "'costs nothing' when it means 'not computed'",
                )

    def test_it_says_why_rather_than_only_refusing(self):
        said = feasibility.estimate_training_vram(
            params_b=1.7, method="qlora", seq_len=2048
        )
        # The reason is an entry in `assumptions`, not a top-level string: the
        # estimator states what it could not compute beside what it assumed,
        # which is the right place for it and is where a caller has to look.
        why = " ".join(said["assumptions"])
        self.assertIn("hidden_size", why)
        self.assertIn("num_attention_heads", why)
        self.assertIn("not computed", why)

    def test_the_provenance_says_defaulted_when_nothing_was_measured(self):
        said = feasibility.estimate_training_vram(
            params_b=1.7, method="qlora", seq_len=2048
        )
        self.assertEqual(said["geometry_provenance"], "defaulted")


class CaseOneTheTrapIsThatTheGeometryIsOneLevelDownTest(unittest.TestCase):
    """THE CASE'S REAL CONTENT. `geometry_from_config(stored)` answers None
    SILENTLY; `geometry_from_config(stored["config"])` answers a full geometry.
    A caller passing the file as saved reads 'cannot compute' and could take it
    for 'will not fit'."""

    def test_the_file_as_saved_yields_no_geometry(self):
        self.assertIsNone(feasibility.geometry_from_config(the_stored_file()))

    def test_the_inner_config_yields_a_measured_geometry(self):
        geometry = feasibility.geometry_from_config(the_stored_file()["config"])
        self.assertIsNotNone(
            geometry,
            "the inner config no longer parses - either the stored shape moved "
            "or the parser did, and the showcase's number would go unknown",
        )
        self.assertEqual(geometry.provenance, "measured")

    def test_the_two_calls_differ_which_is_the_whole_trap(self):
        stored = the_stored_file()
        self.assertIsNone(feasibility.geometry_from_config(stored))
        self.assertIsNotNone(feasibility.geometry_from_config(stored["config"]))

    def test_passing_the_inner_config_produces_a_number_and_measured_provenance(self):
        """What the showcase must do: a budget with a number on it, and a record
        that says the number was measured rather than assumed."""
        stored = the_stored_file()
        geometry = feasibility.geometry_from_config(stored["config"])
        said = feasibility.estimate_training_vram(
            params_b=1.7, method="qlora", seq_len=2048, geometry=geometry
        )
        self.assertIsNotNone(said["total_gb"])
        self.assertGreater(said["total_gb"], 0)
        self.assertEqual(
            said["geometry_provenance"],
            "measured",
            "a record showing `defaulted` means the number on the screen came "
            "from an assumption",
        )

    def test_the_stored_file_still_carries_what_the_case_assumes(self):
        """The case names `{repo_id, url, parameters_total, config}`. If the
        stored shape changes, this case is about a file that no longer exists."""
        stored = the_stored_file()
        for field in ("repo_id", "url", "parameters_total", "config"):
            self.assertIn(field, stored)


class ThePagesPublishedTableIsCheckableTest(unittest.TestCase):
    """The showcase page prints four totals and says all four fit 8 GB. A
    published number nothing recomputes is a number that goes stale quietly."""

    SMALL = support.REPO_ROOT / "app" / "model_configs" / "HuggingFaceTB--SmolLM2-135M.json"
    BIG = A_STORED_MODEL

    def total_for(self, path, params_b, method, seq_len):
        stored = json.loads(path.read_text(encoding="utf-8"))
        geometry = feasibility.geometry_from_config(stored["config"])
        self.assertIsNotNone(geometry)
        return feasibility.estimate_training_vram(
            params_b=params_b, method=method, seq_len=seq_len, geometry=geometry
        )

    def test_all_four_published_totals_still_reproduce(self):
        """EACH IS 0.05 GiB ABOVE WHAT THE JOURNEY PUBLISHED, AND THE JOURNEY IS
        NOT WRONG.

        `docs/journeys/2026-09-06-the-training-showcase-planted-cases.md` records
        2.02 / 2.21 / 4.05 / 6.40, computed when the logits term was priced at
        four bytes per position. It is six: `transformers/loss/loss_utils.py`
        upcasts with `logits.float()` while the caller still holds the fp16
        tensor, so both are resident across the loss. The constant was corrected
        against that source, and every total in this repo moved.

        A journey is a record of what was computed on the day, not a claim about
        today, so it is left alone. This test is about today, so it moves. The
        rows below carry EVERY number rather than only the newest, because a
        reader who finds the journey and this file should be able to see that
        they disagree BY DESIGN and by how much.

        2026-09-10, AND THIS TIME THE NUMBERS MOVED IN BOTH DIRECTIONS.
        Measurement replaced three reasoned terms at once: the logits width
        went 6 -> 12.6 (two sweeps, 12.79 and 12.40), the attention term came
        OUT because the measured slope is flat in sequence length, and a
        dequantisation workspace of 0.192 MiB per hidden unit was added - a
        term the estimator never had. The quantised rows also stopped pricing
        the embedding at NF4, which `bitsandbytes` never quantises.

        THE QUANTISED ROWS MOVED TWICE MORE IN ONE HOUR, and the two moves are
        halves of ONE error rather than two findings. `mlbuild fa5f09a` closed
        the embedding's dtype on fp32 by measuring both sides
        of `prepare_model_for_kbit_training`; `research 497284a` then
        re-derived the dequantisation workspace against that same fp32
        resident, where it halves - it had been solved for with the BEFORE-call
        figure and so carried 0.187 GiB of embedding inside it. Only the qlora
        rows move for either: the lora rows quantise nothing, so there is
        neither an embedding to exempt nor a workspace to size.

        THE ATTENTION TERM DOMINATED, WHICH IS WHY THE LORA TOTALS WENT DOWN. At
        512 tokens on the 1.7B, `5*a*s/h` is 5*32*512/1948 = 42 against the 34
        that remains, so removing it more than halves the per-layer figure -
        and that outruns the logits width doubling on these short-sequence
        rows. At the estimator's own 2,048 default the balance reverses. A
        patch whose effect changes sign with sequence length is exactly the
        kind that should be pinned at a stated length rather than described.
        """
        for path, params_b, method, published, when_logits_were_six, when_logits_were_four in (
            (self.SMALL, 0.135, "qlora", 2.06, 2.07, 2.02),
            (self.SMALL, 0.135, "lora", 2.09, 2.26, 2.21),
            (self.BIG, 1.7, "qlora", 3.85, 4.10, 4.05),
            (self.BIG, 1.7, "lora", 5.68, 6.45, 6.40),
        ):
            self.assertAlmostEqual(
                when_logits_were_six - when_logits_were_four, 0.05, places=2
            )
            with self.subTest(method=method, params_b=params_b):
                said = self.total_for(path, params_b, method, 512)
                self.assertAlmostEqual(said["total_gb"], published, places=2)
                self.assertEqual(said["geometry_provenance"], "measured")

    def test_all_four_fit_the_measured_card(self):
        card = hwdetect.parse_nvidia_smi("NVIDIA GeForce RTX 2060 SUPER, 8192 MiB")
        self.assertEqual(card["vram_gb"], 8.0)
        for path, params_b, method in (
            (self.SMALL, 0.135, "qlora"),
            (self.SMALL, 0.135, "lora"),
            (self.BIG, 1.7, "qlora"),
            (self.BIG, 1.7, "lora"),
        ):
            with self.subTest(method=method):
                self.assertLessEqual(
                    self.total_for(path, params_b, method, 512)["total_gb"],
                    card["vram_gb"],
                )


class TheFitIsAPropertyOfSeqLenAndTheMarginIsThinTest(unittest.TestCase):
    """`seq_len` is still a decision rather than a detail, and 2026-09-10 moved
    WHERE the decision bites. SmolLM2-1.7B under QLoRA on an 8 GB card:

        seq_len   AS ESTIMATED 2026-09-06   MEASURED 2026-09-10
          512     4.05 GB   fits            3.85 GB   fits
         1024     7.76 GB   fits at 97%     4.93 GB   fits
         2048    20.80 GB   DOES NOT FIT    7.30 GB   fits, 0.70 GB spare
         4096    69.36 GB   does not fit   11.67 GB   does not fit

    THE OLD TABLE WAS QUADRATIC AND THE MEASUREMENT SAYS IT IS LINEAR. The
    `5*a*s/h` attention term grew with the square of the sequence, which is what
    turned 1.73 GB of activations into 66.38; the sweep found the real slope
    FLAT in sequence length (0.625, 0.742, 0.742 per 1k tokens) because
    flash/SDPA attention never materialises the `T x T` matrix. Activations now
    go 0.80 -> 6.38 over the same range: eight times for eight times the tokens.

    SO THE PAGE'S ADVICE SURVIVES AND ITS REASON DOES NOT. Choosing 512 was
    right - the longest row is about 102 tokens, and paying for 2,048 is paying
    for padding. But a caller who leaves the default at 2048 no longer turns a
    run that fits into one that cannot start; they turn a comfortable run into
    one with 0.88 GB of headroom, which is INSIDE the 0.5-1.5 GB desktop
    reserve this estimator declares. The cliff is at 4096 now.

    THE OTHER TRAP IS UNCHANGED: pass the stored file one level too high and
    `activations_gb` reads `None`, so the harness says "not computed" about a
    number that would have said "no" - and at 4096 it still would.
    """

    def totals(self, seq_len):
        stored = json.loads(A_STORED_MODEL.read_text(encoding="utf-8"))
        geometry = feasibility.geometry_from_config(stored["config"])
        return feasibility.estimate_training_vram(
            params_b=1.7, method="qlora", seq_len=seq_len, geometry=geometry
        )

    def test_it_fits_at_the_length_the_page_chose(self):
        self.assertLessEqual(self.totals(512)["total_gb"], 8.0)

    def test_the_common_default_now_fits_and_the_page_needs_rereading(self):
        """THE ASSERTION THIS REPLACES SAID `> 8.0` AND CARRIED THE SENTENCE
        "2048 now fits, so either the estimator changed or the model did - and
        the page's justification for 512 needs rereading either way." The
        estimator changed. This is that rereading, kept as a test so the
        reversal cannot be quietly forgotten."""
        total = self.totals(2048)["total_gb"]
        self.assertLessEqual(total, 8.0, "2048 stopped fitting again")
        self.assertGreater(total, 7.0, "the margin at 2048 stopped being thin")

    def test_the_margin_at_the_common_default_is_inside_the_desktop_reserve(self):
        """FITS IS NOT THE SAME AS SAFE. 0.88 GB of headroom sits inside the
        0.5-1.5 GB the estimator itself budgets for a compositor, so a caller
        who leaves the default at 2048 is relying on the low end of a range
        this file declares is a range."""
        spare = 8.0 - self.totals(2048)["total_gb"]
        low, high = feasibility.DESKTOP_RESERVE_GB_RANGE
        self.assertLess(spare, high)

    def test_the_cliff_is_at_four_thousand_and_ninety_six(self):
        """The old table had it at 2048. A test that only asserted the new
        `fits` would not notice if the cliff vanished entirely."""
        self.assertGreater(self.totals(4096)["total_gb"], 8.0)

    def test_activations_are_what_moves_and_they_move_linearly(self):
        """WAS `* 5` FOR A FOUR-TIMES SEQUENCE, which only passes if the term
        is superlinear - it was pinning the quadratic attention term. Measured,
        the growth is linear, so four times the tokens is four times the
        activations and `* 5` is now the wrong assertion in both directions."""
        small, large = self.totals(512), self.totals(2048)
        self.assertAlmostEqual(
            4 * small["activations_gb"], large["activations_gb"], delta=0.02
        )
        self.assertEqual(small["base_weights_gb"], large["base_weights_gb"])


class CaseTwoTheCardIsNotFreeBecauseNoLockExistsTest(unittest.TestCase):
    """A lock file is a claim about intent. Free VRAM is a fact about the card."""

    def test_a_resident_model_is_visible_with_no_lock_at_all(self):
        """2,244 MiB free of 8,192 means somebody's model is resident whatever
        the lock says."""
        card = hwdetect.parse_nvidia_smi("NVIDIA GeForce RTX 4060, 8192 MiB, 561.09, 8.9")
        self.assertEqual(card["vram_gb"], 8.0)
        free_gb = 2244 / 1024.0
        self.assertLess(
            free_gb,
            card["vram_gb"],
            "free below total is the signal the case is about; equal would mean "
            "an empty card",
        )

    def test_the_absence_of_a_lock_file_is_not_a_reading_of_the_card(self):
        """The two questions are independent, and this is the assertion: a
        missing lock tells you nothing about VRAM."""
        missing = Path("gpu.lock.that.does.not.exist")
        self.assertFalse(missing.exists())
        card = hwdetect.parse_nvidia_smi("NVIDIA GeForce RTX 4060, 8192 MiB")
        self.assertEqual(card["vram_gb"], 8.0)

    def test_no_card_reads_as_no_card_rather_than_an_empty_one(self):
        for text in (None, "", "no devices found"):
            with self.subTest(text=text):
                self.assertEqual(hwdetect.parse_nvidia_smi(text), dict(hwdetect.NO_GPU))

    def test_the_keys_are_the_ones_this_case_reads(self):
        """Written after I filtered a real reading on `name` and
        `memory_total_mib`, got `{}`, and nearly reported my own mistake as a
        product defect. The keys are `gpu_name` and `vram_gb`."""
        card = hwdetect.parse_nvidia_smi("NVIDIA GeForce RTX 4060, 8192 MiB")
        self.assertIn("gpu_name", card)
        self.assertIn("vram_gb", card)
        self.assertNotIn("memory_total_mib", card)


class CaseThreeTheRowsAreTheRunsOwnOutputTest(unittest.TestCase):
    """Not a fixture. The showcase must say which run produced its training
    set, and every row must carry the provenance the pipeline stamped."""

    ROWS = support.REPO_ROOT / "runs" / "two-hundred" / "train.synthetic.jsonl"

    def rows(self):
        if not self.ROWS.exists():
            self.skipTest(
                f"{self.ROWS} is not here - `runs/` is gitignored, so this case "
                "checks the real artefact when it exists and says so when it "
                "does not, rather than passing on a fixture"
            )
        return [
            json.loads(line)
            for line in self.ROWS.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_every_row_carries_the_provenance_the_pipeline_stamped(self):
        rows = self.rows()
        self.assertTrue(rows)
        for index, row in enumerate(rows):
            with self.subTest(row=index):
                self.assertIn("provenance", row)
                self.assertEqual(row["provenance"]["origin"], "ASSERTED")
                self.assertEqual(
                    row["provenance"]["tool"],
                    "scripts/generate_the_preference_pairs.py",
                )

    def test_every_row_names_the_run_that_produced_it(self):
        for row in self.rows():
            self.assertEqual(row["synthetic_seed"], "two-hundred-2026-09-05")
            self.assertTrue(row["synthetic"])

    def test_no_row_is_degenerate(self):
        """A pair whose two sides are equal teaches nothing and would pad the
        count the showcase reports."""
        for row in self.rows():
            self.assertNotEqual(row["chosen"].strip(), row["rejected"].strip())


class CaseFourARefusedRunLeavesARecordTest(unittest.TestCase):
    """`need X, free Y` written down, rather than failing at the first
    allocation - the same shape as a void call."""

    window = support.import_file(
        "card_owner_the_window", support.REPO_ROOT / "card_owner" / "the_window.py"
    )
    record = support.import_file(
        "card_owner_the_record", support.REPO_ROOT / "card_owner" / "the_record.py"
    )

    def test_a_refusal_carries_both_numbers(self):
        verdict = self.window.the_window_verdict(13_213, 4_096)
        self.assertTrue(verdict.void)
        self.assertIn("17,177", verdict.reason)
        self.assertIn("4,096", verdict.reason)

    def test_a_refused_run_is_an_outcome_not_an_absence(self):
        """The refusal is a row. A job that refused everything is COMPLETE."""
        tally = self.record.the_tally(
            1, [{"outcome": self.record.REFUSED}]
        )
        self.assertTrue(tally.complete)
        self.assertIsNone(self.record.why_this_record_is_red(tally))
        self.assertIn("1 refused", self.record.the_calls_line(tally))

    def test_a_run_that_simply_vanished_is_red(self):
        """The failure this case exists against: nothing written, and the record
        quietly one row short."""
        tally = self.record.the_tally(1, [])
        self.assertFalse(tally.complete)
        self.assertIsNotNone(self.record.why_this_record_is_red(tally))


if __name__ == "__main__":
    unittest.main()
