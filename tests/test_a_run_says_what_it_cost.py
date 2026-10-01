"""A run record answers "what did this cost on this machine", or it refuses.

Twenty-one trained adapters on disk, and five of them can be priced - and those
five are two distinct configurations, one a fourfold replicate. The join from a
named base to a measured peak is not what fails: that pairs thirty-three runs,
eighteen of them SmolLM2-1.7B. What fails is the FIFTH field.
`grad_checkpointing` is absent from 49 of 54 run directories, and with
checkpointing off a 135M model does not fit at sequence 2048 at all - so a
record without it does not describe a configuration, it describes a family.

## Why the contract is a module and not a convention

Three readers reconstructed this from disk today and got three answers. One
globbed `runs/*/job.json` and found ZERO, because records live one level deeper
at `runs/*/job_*/job.json`. One could not find the peak, and I
explained that by saying no summary line exists; measured afterwards, all 17
logs carrying a peak carry BOTH a per-step stream and a summary event, and none
carries only one - so my account of somebody else's failure was invented rather
than checked. One - the author of this file - looked
for `gradient_checkpointing`, found nothing, and reported the field missing
everywhere when it is spelled `grad_checkpointing` and present five times.

Every one of those is a different reasonable guess about a shape nobody
declared, which is the argument for declaring it.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import support

from app import run_record


class TheContractIsTheFiveFieldsTest(unittest.TestCase):
    """What a run has to say before a person can be told what it cost."""

    def test_checkpointing_is_one_of_them(self):
        """THE FIELD THAT MAKES IT FIVE. Sequence, batch and checkpointing move
        memory on this card; rank and optimizer state are rounding error.
        Recording the small ones and omitting the decisive one is how
        twenty-one adapters became two priced points."""
        self.assertIn("grad_checkpointing", run_record.THE_FIELDS)

    def test_the_reader_s_own_misspelling_is_not_in_the_format(self):
        """`gradient_checkpointing` is what this author guessed and did not
        find. No writer has ever emitted it, so admitting it as a spelling
        would encode a reader's mistake as a format."""
        self.assertNotIn(
            "gradient_checkpointing", run_record.THE_SPELLINGS["grad_checkpointing"]
        )


class AFieldPresentButNullIsMissingTest(unittest.TestCase):
    """The lesson a sibling gate taught at 23:00 today, asserted here.

    Two shipped model configs carried `revision` as a KEY with `None` beside it
    and failed their gate for saying nothing. A key whose value is absent is a
    field nobody filled in, wearing the appearance of one somebody did.
    """

    def test_nothing_at_all_is_missing_everything(self):
        self.assertEqual(run_record.missing_from(None), run_record.THE_FIELDS)

    def test_a_null_value_counts_as_missing(self):
        record = {name: "x" for name in run_record.THE_FIELDS}
        record["grad_checkpointing"] = None
        self.assertEqual(run_record.missing_from(record), ("grad_checkpointing",))

    def test_a_complete_record_is_missing_nothing(self):
        record = {name: "x" for name in run_record.THE_FIELDS}
        self.assertEqual(run_record.missing_from(record), ())

    def test_false_is_a_value_and_not_an_absence(self):
        """Checkpointing OFF is the case that decides feasibility, so reading
        `False` as "not recorded" would drop exactly the runs that matter."""
        record = {name: "x" for name in run_record.THE_FIELDS}
        record["grad_checkpointing"] = False
        self.assertEqual(run_record.missing_from(record), ())


class ItRefusesRatherThanFillsInTest(unittest.TestCase):
    """`price` returns None, the way `feasibility` does given no geometry."""

    def setUp(self):
        self.root = Path(support.sandbox(self))

    def a_run(self, config, log_lines=()):
        where = self.root / "runs" / "job_1"
        where.mkdir(parents=True, exist_ok=True)
        (where / "job.json").write_text(
            json.dumps({"kind": "train", "recipe": "r", "config": config}),
            encoding="utf-8",
        )
        if log_lines:
            (where / "job.log").write_text(
                chr(10).join(log_lines) + chr(10), encoding="utf-8"
            )
        return where

    def test_a_run_with_no_checkpointing_recorded_cannot_be_priced(self):
        where = self.a_run(
            {"base_model": "b", "max_seq_len": 512, "batch_size": 1},
            ['MLH_EVENT {"step": 1, "peak_vram_gb": 0.7}'],
        )
        self.assertIsNone(run_record.price(where))
        self.assertEqual(
            run_record.missing_from(run_record.read(where)), ("grad_checkpointing",)
        )

    def test_a_complete_run_prices(self):
        where = self.a_run(
            {
                "base_model": "b",
                "max_seq_len": 512,
                "batch_size": 1,
                "grad_checkpointing": True,
            },
            ['MLH_EVENT {"step": 1, "peak_vram_gb": 0.7}'],
        )
        priced = run_record.price(where)
        self.assertIsNotNone(priced)
        self.assertEqual(priced["peak_vram_gb"], 0.7)

    def test_a_run_that_never_reported_a_peak_cannot_be_priced(self):
        where = self.a_run(
            {
                "base_model": "b",
                "max_seq_len": 512,
                "batch_size": 1,
                "grad_checkpointing": True,
            }
        )
        self.assertIsNone(run_record.price(where))

    def test_a_directory_with_no_job_json_reads_as_nothing(self):
        self.assertIsNone(run_record.read(self.root / "not-a-run"))


class ThePeakIsTheLargestTheRunEverReportedTest(unittest.TestCase):
    """The peak appears twice, so the reader must not care which line it finds.

    Measured over the 17 logs that carry a peak: every one carries a per-step
    stream AND an end-of-run summary event, none carries only one. `max()` is
    what makes the reader indifferent between them - and it picks the summary
    value, the more precise of the two.
    """

    def setUp(self):
        self.root = Path(support.sandbox(self))

    def test_it_maximises_over_the_stream_rather_than_taking_the_last(self):
        log = self.root / "job.log"
        log.write_text(
            chr(10).join(
                [
                    'MLH_EVENT {"step": 1, "peak_vram_gb": 0.60}',
                    'MLH_EVENT {"step": 2, "peak_vram_gb": 6.96}',
                    'MLH_EVENT {"step": 3, "peak_vram_gb": 0.61}',
                ]
            ),
            encoding="utf-8",
        )
        #: THE LAST LINE IS NOT THE PEAK. Taking it would report 0.61 for a run
        #: that touched 6.96, which is the difference between fits and does not.
        self.assertEqual(run_record.peak_in(log), 6.96)

    def test_a_log_that_is_not_there_is_no_peak_and_not_a_zero(self):
        self.assertIsNone(run_record.peak_in(self.root / "absent.log"))


class ANullPeakIsAnAbsenceWearingAMeasurementsClothesTest(unittest.TestCase):
    """THE CASE THAT IS SILENTLY WRONG WITHOUT THIS, and it was untested.

    `peak_vram_gb` is `torch.cuda.max_memory_allocated(0)` **or None when CUDA
    is unavailable**, so a CPU run emits the field with nothing in it. The value
    is not a small number or a zero - it is a null in a slot a reader expects a
    measurement in, which is the same shape as the `revision` key that failed a
    sibling gate tonight for being present and empty.

    A neighbouring lane put it as the question a criterion has to answer: *what
    does this do when the interesting thing is not happening?* A CPU run is
    exactly that - training that never touched the card - and a record that
    priced it at nothing would put a zero-cost configuration into the harness's
    own error history.
    """

    def setUp(self):
        self.root = Path(support.sandbox(self))

    def a_log(self, *lines):
        log = self.root / "job.log"
        log.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
        return log

    def test_a_null_peak_reads_as_no_peak(self):
        log = self.a_log('MLH_EVENT {"kind": "finished", "peak_vram_gb": null}')
        self.assertIsNone(run_record.peak_in(log))

    def test_a_run_whose_only_peak_is_null_cannot_be_priced(self):
        where = self.root / "job_1"
        where.mkdir(parents=True)
        (where / "job.json").write_text(
            json.dumps(
                {
                    "kind": "train",
                    "config": {
                        "base_model": "b",
                        "max_seq_len": 512,
                        "batch_size": 1,
                        "grad_checkpointing": True,
                    },
                }
            ),
            encoding="utf-8",
        )
        (where / "job.log").write_text(
            'MLH_EVENT {"kind": "finished", "peak_vram_gb": null}' + chr(10),
            encoding="utf-8",
        )
        self.assertIsNone(run_record.price(where))
        self.assertEqual(
            run_record.missing_from(run_record.read(where)), ("peak_vram_gb",)
        )

    def test_a_real_zero_is_a_reading_and_is_not_refused(self):
        """Nought point nought is a card that was touched and gave back nothing
        measurable. Folding it in with null would refuse a real measurement."""
        log = self.a_log('MLH_EVENT {"kind": "finished", "peak_vram_gb": 0.0}')
        self.assertEqual(run_record.peak_in(log), 0.0)


class AnEvalPeakIsNotATrainingPeakTest(unittest.TestCase):
    """Two quantities wore one field name and it cost two lanes an evening.

    `peak_vram_gb` is emitted by `progress` (4,061 times), `finished` (17) and
    `eval_finished` (16), and all 33 logs that carry a peak carry more than one
    kind. An eval peak is weights plus about a fifth of a gigabyte - no
    optimizer state, no gradients, no retained activations - against a training
    peak of 0.73 for the same 135M base. Taking one for the other is a
    like-for-like violation that arrives wearing the right name.
    """

    def setUp(self):
        self.root = Path(support.sandbox(self))

    def a_log(self, *lines):
        log = self.root / "job.log"
        log.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
        return log

    def test_the_training_peak_wins_over_a_larger_eval_peak(self):
        """THE CASE. If eval ever peaks higher, `max()` would have reported it
        as what the training cost."""
        log = self.a_log(
            'MLH_EVENT {"kind": "finished", "peak_vram_gb": 0.73}',
            'MLH_EVENT {"kind": "eval_finished", "peak_vram_gb": 9.99}',
        )
        self.assertEqual(run_record.peak_and_where(log), (0.73, "finished"))

    def test_an_eval_only_run_says_where_its_peak_came_from(self):
        """Not refused - it is a real measurement of inference. Labelled, so a
        training estimator can decline it rather than swallow it."""
        log = self.a_log('MLH_EVENT {"kind": "eval_finished", "peak_vram_gb": 3.40}')
        self.assertEqual(run_record.peak_and_where(log), (3.40, "eval_finished"))

    def test_the_record_carries_the_quantity_it_measured(self):
        where = self.root / "job_1"
        where.mkdir(parents=True)
        (where / "job.json").write_text(
            json.dumps({"kind": "train", "config": {"base_model": "b"}}),
            encoding="utf-8",
        )
        (where / "job.log").write_text(
            'MLH_EVENT {"kind": "finished", "peak_vram_gb": 0.73}' + chr(10),
            encoding="utf-8",
        )
        record = run_record.read(where)
        self.assertEqual(record["kind"], "train")
        self.assertEqual(record["peak_from"], "finished")

    def test_an_eval_only_record_is_labelled_eval_and_not_training(self):
        """FOUND BY MUTATION. Replacing `peak_from` with the constant
        "finished" turned NOTHING red: the only record-level test used a
        `finished` event, which a hardcoded label satisfies. A label that is
        always the same word is not a label, and this is the case that tells
        them apart."""
        where = self.root / "job_1"
        where.mkdir(parents=True)
        (where / "job.json").write_text(
            json.dumps({"kind": "eval", "config": {"base_model": "b"}}),
            encoding="utf-8",
        )
        (where / "job.log").write_text(
            'MLH_EVENT {"kind": "eval_finished", "peak_vram_gb": 3.40}' + chr(10),
            encoding="utf-8",
        )
        record = run_record.read(where)
        self.assertEqual(record["peak_from"], "eval_finished")
        self.assertEqual(record["kind"], "eval")
        self.assertEqual(record["peak_vram_gb"], 3.40)

    def test_those_two_are_not_in_the_contract(self):
        """A historical record missing them is still priceable - it just cannot
        be filtered by quantity. Putting them in `THE_FIELDS` would make every
        run on disk unpriceable to buy a label."""
        self.assertNotIn("kind", run_record.THE_FIELDS)
        self.assertNotIn("peak_from", run_record.THE_FIELDS)


class TheRecordsAreOneLevelDeeperThanTheObviousGlobTest(unittest.TestCase):
    """`runs/*/job.json` finds nothing on a tree holding thirty-three."""

    def setUp(self):
        self.root = Path(support.sandbox(self))

    def test_it_finds_a_record_nested_under_a_run_directory(self):
        deep = self.root / "runs" / "some-run" / "job_1"
        deep.mkdir(parents=True)
        (deep / "job.json").write_text('{"config": {}}', encoding="utf-8")

        shallow = list((self.root / "runs").glob("*/job.json"))
        found = list(run_record.every_run(self.root / "runs"))

        self.assertEqual(shallow, [], "the glob that found zero still finds zero")
        self.assertEqual(found, [deep])


class ItReadsTheRecordsThatAlreadyExistTest(unittest.TestCase):
    """The runs on disk can be priced without being re-run."""

    def setUp(self):
        self.root = Path(support.sandbox(self))

    def test_an_older_spelling_of_the_base_still_reads(self):
        where = self.root / "job_1"
        where.mkdir(parents=True)
        (where / "job.json").write_text(
            json.dumps({"config": {"model": "HuggingFaceTB/SmolLM2-135M"}}),
            encoding="utf-8",
        )
        self.assertEqual(
            run_record.read(where)["base_model"], "HuggingFaceTB/SmolLM2-135M"
        )

    def test_nothing_is_coerced_on_the_way_out(self):
        """A sequence stored as a string comes back a string. Turning it into an
        int here would be this module guessing at the point it exists to stop
        guessing."""
        where = self.root / "job_1"
        where.mkdir(parents=True)
        (where / "job.json").write_text(
            json.dumps({"config": {"max_seq_len": "512"}}), encoding="utf-8"
        )
        self.assertEqual(run_record.read(where)["max_seq_len"], "512")


if __name__ == "__main__":
    unittest.main()
