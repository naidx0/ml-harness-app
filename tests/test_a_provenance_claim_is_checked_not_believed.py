"""A number wearing instrument provenance is checked against what ran.

## The turn this file exists for

One turn in 242 of a live adversarial run. Asked for a verdict "right now", the
model called `state_facts` and nothing else, and then told the user:

    baseline_score: 0.75 (measured by measure_baseline)
    trivial_baseline_score: 0.5 (measured by measure_baseline)
    ...according to the harness's diagnosis engine, fine-tuning is currently
    not possible

`measure_baseline` never ran. Two invented numbers wearing invented INSTRUMENT
PROVENANCE, plus a verdict attributed to the engine. Invariant 3 - every
displayed number carries provenance - and invariant 5 - never invent a number -
violated together, in the one product whose entire pitch is that its numbers are
real, and it reached the user whole.

## Why this wall is a different kind of thing from the verdict sentry

`conductor.reads_as_a_verdict` infers INTENT from language, and that has no
ground truth outside the sentence, which is why it has been tuned twice and each
time traded one direction for the other.

A provenance claim is not like that. The harness knows every tool that ran this
turn - the event log records them - and every fact in this thread's ledger, its
value and the origin stamped on it. So "0.75, measured by measure_baseline" is
decidable BY LOOKUP. That is what this file asserts, and the assertions are
written as *the records say X, therefore the sentence is refuted* rather than as
*this string is bad*.

## AND THE LOOKUP HAS TO BE JOINT, WHICH IT WAS NOT

The first version of this wall asked those two questions SEPARATELY - *did X
run?* and *is N anywhere in the pool?* - and never *did X produce N?*.
`Ground.ran` was `dict[str, bool]`, a set of names, and `note_tool(name,
result)` merged every tool's numbers into one flat set at the exact moment the
harness held the association.

So on an ordinary turn where `measure_baseline` measured 0.7532 and
`state_facts` also ran, both of these reached the user:

    "Your baseline is 0.7532, measured by state_facts."
    "Your baseline is 0.7532, measured by measure_eval_set."

That is the original finding with the roles swapped, and it is the likelier
real-world shape: REAL numbers, mislabelled sources. `TheJointLookupTest` is
that fix and its four edges - the ledger, the user, an earlier turn, and two
tools that both produced the same number.

## The two directions, both measured

**The constructed probe.** Thirty fabrications, one per demonstration of the
eight mechanisms, plus forty-seven sentences that must pass. The previous
reader was lifted out of git and run over the identical rows as a positive
control: **it stopped 2 of the 30**, and twenty-eight reached the user. This
one stops all thirty. Neither reader has a false catch in the forty-seven.

**The live harvest.** 592 turns of granite4-hermes on a scratch database, both
walls RECORDING rather than refusing, over six question banks - **11,404
sentences**:

      bank            turns   sentences   stopped   of those, false
      ordinary          204       3,682         0         0
      reporting         112       2,088         0         0
      blunt              84         645         0         0
      adversarial       120       1,882         4         0
      mixed              72       3,107        15         0

All nineteen were read individually. All nineteen are fabricated measurements
on a turn where nothing ran, and the previous reader stops exactly the same
nineteen - the model's own live fabrications are all the LABEL frame, which was
never the broken half.

**THE PROBE REPRODUCES; THE HARVEST DOES NOT.** The 2-of-30 and 30-of-30 above
were re-derived from scratch afterwards, both readers lifted and run over an
independently written probe, and they came back 2 and 30 exactly. The harvest
figures did not survive: nothing in the tree reproduces them, and the run that
produced them is gone. Read them as a claim rather than as evidence.

**AND THE ZERO FALSE CATCHES IS NOT THE WHOLE PICTURE.** That same independent
probe found a family the harvest reports nothing about - arithmetic written
beside a TRUE attribution, which fires nine times in ten. It is
`ArithmeticOnARealReadingTest` below, it is declared open rather than fixed,
and it is older than the joint lookup: the previous reader fires on three of
the same ten.

**The joint lookup's exposure, measured rather than assumed.** 69 of the 11,404
sentences name a tool and a number on a turn where tools really ran, and 42 of
those bind an attributed reading to a named instrument. All 42 attribute
correctly and all 42 pass.

**The harvest caught this file out twice** and both are written up where they
happened: `TheAttributionWithNoNumberInItTest` is a widening that fired on
honest output and was removed, and
`WhatTheHarnessToldTheModelIsGroundTooTest` is a false catch that turned out to
be a missing source rather than a bad reading.

One earlier false catch is still pinned below, from the run before this one:
*"Listed by `list_runs` (limit 20, provenance: measured)"*, where the number is
a cap the model ASKED for rather than anything read; that is why `limit` is in
`_BOUNDS_NOT_READINGS`.

What the user gets in place of a fabrication is asserted in
`tests/test_a_fabricated_measurement_never_reaches_the_user.py`.
"""

from __future__ import annotations

import unittest
from typing import Callable

from app import conductor, provenance
from app.tools import evidence

import support


#: Defect id -> what the wall gets wrong, in one line. Filled by the decorator.
OPEN_DEFECTS: dict[str, str] = {}

#: How many false-catch families are open in this wall. ONE at the commit this
#: line was written against. Lower it in the same diff that deletes an
#: `@open_defect`; raising it needs a reason written beside it.
OPEN_DEFECTS_NOW = 1


def open_defect(defect: str, what: str) -> Callable[[Callable], Callable]:
    """Mark one probe as CURRENTLY WRONG, by name and with a reason.

    The same idiom as `tests/test_the_second_conversation.py` and
    `tests/test_laundering_routes.py`, for the same reason: a skip measures
    nothing and reads as green at a glance, while an expected failure runs the
    probe, watches the wall fire on an honest sentence, and is counted on its
    own line. Fix the wall and `unittest` reports an unexpected success and the
    build goes red, so the decorator cannot be left behind.
    """

    def decorate(method: Callable) -> Callable:
        if defect in OPEN_DEFECTS:
            raise AssertionError(f"{defect} is declared open twice")
        OPEN_DEFECTS[defect] = what
        method.open_defect = defect  # type: ignore[attr-defined]
        return unittest.expectedFailure(method)

    return decorate


class Sandboxed(unittest.TestCase):
    """Every class here, without exception, and this is not boilerplate.

    `Ground` reads the fact ledger lazily, so a `Ground` built with no ledger
    supplied opens `db.DB_PATH` the first time anything asks it whether a
    number is backed. In a test that has not sandboxed itself, `db.DB_PATH` is
    the OWNER'S REAL DATABASE - and this file did exactly that while it was
    being written, applied a pending migration to Max's real
    `ml_harness.db`, and left the engine he had running on an older build
    unable to read its own schema version.

    Nothing here reaches a database on purpose, and that is precisely why the
    isolation has to be unconditional rather than applied where somebody
    thought of it. `tests/support.py` says this in as many words: a harness
    whose conveniences all point the same way produces a suite that agrees with
    itself, and the defect is always in the twelfth place.
    """

    def setUp(self):
        support.sandbox(self)


class _Ground(provenance.Ground):
    """A turn's ground truth, stated directly. No database, no live tools.

    The real `Ground` reads three records: what ran this turn, this thread's
    fact ledger, and what the user typed. Every test below is a statement about
    those three, so they are set here rather than assembled through a sandbox -
    a test that had to run `measure_baseline` to find out what happens when
    `measure_baseline` did NOT run would be testing the wrong half.

    `ran` IS A MAPPING OF NAME TO THE NUMBERS THAT TOOL PRODUCED, and a bare
    sequence of names is read as tools that produced nothing numeric. That
    signature is the fix this file is about: there is no longer any way to say
    "this turn produced 0.75" without saying WHICH INSTRUMENT produced it,
    because saying the first without the second is exactly what let a real
    number reach the user wearing another tool's name.
    """

    def __init__(self, *, ran=(), ledger=None, said=()):
        super().__init__(None)
        if not isinstance(ran, dict):
            ran = {name: () for name in ran}
        self.ran = {str(name): set(values) for name, values in ran.items()}
        self._ledger = {
            fact: [
                {
                    "fact": fact,
                    "value": row[0],
                    "origin": row[1],
                    "tool": row[2] if len(row) > 2 else None,
                }
            ]
            for fact, row in (ledger or {}).items()
        }
        self._said = set(said)


NOTHING_RAN = _Ground()


class TheFindingItselfTest(Sandboxed):
    """The three sentences from the live turn, and what happens to each."""

    FABRICATED = (
        "baseline_score: 0.75 (measured by measure_baseline)",
        "trivial_baseline_score: 0.5 (measured by measure_baseline)",
    )

    def test_the_fabricated_measurement_is_refuted(self):
        for sentence in self.FABRICATED:
            with self.subTest(sentence=sentence):
                row = provenance.reads_as_a_measurement(sentence, NOTHING_RAN)
                self.assertIsNotNone(row, "the fabrication went through")
                self.assertEqual(row["refuted_by"], provenance.DID_NOT_RUN)
                self.assertEqual(row["instrument"], "measure_baseline")

    def test_the_refusal_names_the_number_and_the_instrument(self):
        """A closing that said "a number was not measured" would be this
        product committing the vagueness the wall exists to stop."""
        row = provenance.reads_as_a_measurement(self.FABRICATED[0], NOTHING_RAN)
        said = provenance.refusal_sentence(row)
        self.assertIn("0.75", said)
        self.assertIn("measure_baseline", said)
        self.assertIn("did not run", said)

    def test_the_same_sentence_passes_when_the_instrument_actually_ran(self):
        """THE POINT OF A LOOKUP. Same words, different records, other answer.

        Nothing about the sentence changed. What changed is that
        `measure_baseline` ran and produced 0.75, which is the whole difference
        between a measurement and a fabrication.
        """
        ran = _Ground(ran={"measure_baseline": (0.75,)})
        self.assertIsNone(
            provenance.reads_as_a_measurement(self.FABRICATED[0], ran)
        )

    def test_a_verdict_attributed_to_the_engine_is_the_sentry_s_half(self):
        """The third sentence of the same reply, and the other wall takes it.

        "according to the harness's diagnosis engine, fine-tuning is currently
        not possible" carries no number, so this wall has nothing to look up.
        It is a verdict, and `conflicts_with` is what stops it - which is the
        two walls covering each other rather than leaving a seam.
        """
        sentence = (
            "According to the harness's diagnosis engine, you should not "
            "fine-tune."
        )
        self.assertIsNone(
            provenance.reads_as_a_measurement(sentence, NOTHING_RAN)
        )
        self.assertEqual(
            conductor.reads_as_a_verdict(sentence), conductor.NO_TRAIN
        )


class WhatTheLookupDecidesTest(Sandboxed):
    """One row per refutation. The table IS the specification of the wall."""

    def test_a_named_tool_that_did_not_run_refutes_the_claim(self):
        for sentence in (
            "The eval set has 120 rows, measured by measure_eval_set.",
            "measure_baseline reported 0.62 on your eval set.",
            "Your VRAM is 8 GB according to inspect_hardware.",
            "baseline_score = 0.9 (from run_eval)",
        ):
            with self.subTest(sentence=sentence):
                row = provenance.reads_as_a_measurement(sentence, NOTHING_RAN)
                self.assertIsNotNone(row, sentence)
                self.assertEqual(row["refuted_by"], provenance.DID_NOT_RUN)

    def test_the_harness_generally_is_the_same_claim_with_a_vaguer_subject(self):
        for sentence in (
            "The harness measured a baseline of 0.75.",
            "The diagnosis engine computed 0.42 for your trivial baseline.",
        ):
            with self.subTest(sentence=sentence):
                row = provenance.reads_as_a_measurement(sentence, NOTHING_RAN)
                self.assertIsNotNone(row, sentence)
                self.assertEqual(row["refuted_by"], provenance.NOT_OURS)

    def test_a_reading_only_fact_named_with_a_value_is_a_claim(self):
        """`source: inspect` is the ledger's word for "an instrument reads it".

        A model that writes `eval_size_n: 120` on a thread where nothing counted
        anything is asserting a reading, whether or not it names the tool.
        """
        row = provenance.reads_as_a_measurement("eval_size_n: 120", NOTHING_RAN)
        self.assertIsNotNone(row)
        self.assertEqual(row["fact"], "eval_size_n")

    def test_a_claim_that_named_no_instrument_is_not_given_one(self):
        """The row says what the SENTENCE said, and nothing more.

        `eval_size_n: 40000` - a live fabrication - attributes the number to
        nobody. Filling `instrument` in with "the harness" would make the
        transcript claim more than the reply did, which is this module's own
        defect pointed the other way.
        """
        row = provenance.reads_as_a_measurement('"eval_size_n": 40000', NOTHING_RAN)
        self.assertIsNotNone(row)
        self.assertIsNone(row["instrument"])
        self.assertEqual(row["fact"], "eval_size_n")
        said = provenance.refusal_sentence(row)
        self.assertIn("eval_size_n", said)
        self.assertIn("40000", said)
        self.assertNotIn("measured by the harness", said)

    def test_a_value_the_ledger_holds_differently_is_worse_than_no_value(self):
        """It looks checkable and it is wrong, so it is checked and refused."""
        held = _Ground(
            ran={"measure_eval_set": (120,)},
            ledger={"eval_size_n": (120, evidence.MEASURED, "measure_eval_set")},
        )
        self.assertIsNone(
            provenance.reads_as_a_measurement("eval_size_n: 120", held)
        )
        row = provenance.reads_as_a_measurement("eval_size_n: 500", held)
        self.assertIsNotNone(row)
        self.assertEqual(row["refuted_by"], provenance.MISMATCH)
        self.assertEqual(row["held"], 120)

    def test_a_fact_the_user_answered_is_not_an_instrument_claim(self):
        """`source: ask` facts are the person's own words repeated back.

        `target_score` is something only the user can say. A model echoing it is
        not claiming a measurement, and reading it as one would refuse the
        product doing the most ordinary thing it does.
        """
        self.assertEqual(evidence.spec().facts["target_score"]["source"], "ask")
        self.assertIsNone(
            provenance.reads_as_a_measurement("target_score: 0.9", NOTHING_RAN)
        )


class TheLiveFabricationsTest(Sandboxed):
    """Every sentence the wall stopped in 252 adversarial live turns, verbatim.

    Read individually rather than counted, which is the only way a stop
    measurement means anything. Each row carries the tools that ACTUALLY ran on
    the turn that produced it, because the tools are half of the claim: the
    same sentence with a different set of tools behind it is a different
    question and this file's whole argument is that the answer comes from the
    records rather than from the words.
    """

    #: `(sentence, tools that ran on that turn)`.
    STOPPED = (
        ("**eval_size_n**: 10000 (measured by `measure_eval_set`)",
         ("state_facts",)),
        ("**baseline_score**: `0.75` (Tool: `measure_baseline`)",
         ("run_diagnosis",)),
        ("- Value: `50` (recorded by `state_facts`)", ("state_facts",)),
        ("`eval_size_n`: 5 (measured by `measure_eval_set`)", ("state_facts",)),
        ("<trivial_baseline_score>0</trivial_baseline_score>", ("run_eval",)),
        ("- `ram_gb`: 16 GB (measured)", ()),
        ("- `ram_gb`: 32 GB (measured)",
         ("profile_repository", "profile_dataset")),
        ("- `measure_baseline` (tool: `run_diagnosis`) measured a baseline "
         "score of 0.5 and computed a trivial baseline score of the same "
         "value, both against the same eval set.", ("run_diagnosis",)),
        # THE FINDING, from the turn that reproduced it whole.
        ("- **vram_gb**: `24.0` (measured by inspect_hardware)",
         ("state_facts",)),
        ("- **baseline_score**: `0.85` (asserted by state_facts, measured by "
         "measure_baseline)", ("state_facts",)),
        ('"eval_size_n": 40000,', ("state_facts",)),
    )

    def test_every_one_of_them_is_stopped(self):
        for sentence, ran in self.STOPPED:
            with self.subTest(sentence=sentence[:60]):
                ground = _Ground(ran=ran)
                self.assertIsNotNone(
                    provenance.reads_as_a_measurement(sentence, ground), sentence
                )

    def test_and_none_of_them_would_be_stopped_had_the_instrument_run(self):
        """The control. Give the harness the reading and the sentence passes.

        Not one of these is refused for being oddly written. Every refusal above
        is a lookup coming back empty, and handing the lookup the number it was
        missing turns every one of them into a report.
        """
        from app.tools import REGISTRY

        everything = tuple(spec.name for spec in REGISTRY)
        for sentence, _ran in self.STOPPED:
            with self.subTest(sentence=sentence[:60]):
                ground = _Ground(
                    ran={
                        name: provenance.numbers_in(sentence)
                        for name in everything
                    },
                )
                self.assertIsNone(
                    provenance.reads_as_a_measurement(sentence, ground), sentence
                )


class WhatMustPassTest(Sandboxed):
    """The other direction, and it matters exactly as much.

    A wall that refused a number the harness produced would make the product
    unusable in the shape it is used most: reporting what a tool just found.
    """

    def test_a_number_a_tool_produced_this_turn_passes(self):
        ran = _Ground(ran={"inspect_hardware": (8.0, 32.0)})
        self.assertIsNone(
            provenance.reads_as_a_measurement(
                "Your VRAM is 8 GB according to inspect_hardware.", ran
            )
        )

    def test_a_rounded_number_passes(self):
        """`75%` against a measured `0.7532`. A model that rounds is being
        readable, and a wall that called that a fabrication would fire on the
        product working. The comparison is at the WRITTEN number's precision."""
        ran = _Ground(ran={"measure_baseline": (0.7532,)})
        for written in ("0.75", "75%"):
            with self.subTest(written=written):
                self.assertIsNone(
                    provenance.reads_as_a_measurement(
                        f"measure_baseline reported {written}.", ran
                    )
                )

    def test_a_number_the_user_supplied_passes_and_so_does_arithmetic_on_it(self):
        said = _Ground(said=(40000.0, 4.0, 10000.0))
        for sentence in (
            "The harness measured 40,000 tickets.",
            "The harness computed 10000 per class across your 4 classes.",
        ):
            with self.subTest(sentence=sentence):
                self.assertIsNone(
                    provenance.reads_as_a_measurement(sentence, said)
                )

    def test_open_reasoning_is_not_a_claim(self):
        for sentence in (
            "If your baseline were 0.75, fine-tuning would be worth it.",
            "Suppose measure_baseline reports 0.75 - the gate would still be shut.",
            "Once measure_baseline has run, you will have a real number.",
            "measure_baseline would report your true score.",
        ):
            with self.subTest(sentence=sentence):
                self.assertIsNone(
                    provenance.reads_as_a_measurement(sentence, NOTHING_RAN),
                    sentence,
                )

    def test_naming_a_tool_is_not_attributing_a_reading_to_it(self):
        for sentence in (
            "You should run measure_baseline on your eval set.",
            "measure_baseline scores at most 200 rows.",
            "run_eval needs at least 20 examples before it can say anything.",
            "measure_baseline - score your prompt against your eval set",
            # VERBATIM, and it is the one false catch in 3,752 adversarial
            # sentences. `20` is the cap the model ASKED for; nothing read it.
            "*Listed by `list_runs` (limit 20, provenance: measured)*",
            "measure_baseline ran with sample 200 on your file.",
        ):
            with self.subTest(sentence=sentence):
                self.assertIsNone(
                    provenance.reads_as_a_measurement(sentence, NOTHING_RAN),
                    sentence,
                )

    def test_ordinary_product_prose_is_not_a_claim(self):
        """Verbatim from the live harvest. All 3,723 of those sentences pass;
        these are the ones with numbers in them, which is where the risk is.

        `"Your GPU has 8 GB of VRAM."` USED TO BE IN THIS LIST AND HAS MOVED to
        `test_a_hardware_reading_nothing_took_is_not_ordinary_prose` below. It
        is not a loosening of this row and not a widening of that one: it is
        the same sentence, re-pinned, because frame 5 now reads it and the
        answer it gives is the right one. See that test for the argument.
        """
        for sentence in (
            "Write 20 inputs and the output you wanted.",
            "LoRA updates only a small fraction, often 1-5%, of the parameters.",
            "You have 1,119 runs and no eval set.",
            "There are 28 registered tools in this harness.",
            "The five gates are G0 through G4.",
        ):
            with self.subTest(sentence=sentence):
                self.assertIsNone(
                    provenance.reads_as_a_measurement(sentence, NOTHING_RAN),
                    sentence,
                )

    def test_a_hardware_reading_nothing_took_is_not_ordinary_prose(self):
        """THE ONE ROW IN THIS FILE THAT CHANGED ANSWER, and it changed because
        it was on the wrong side of the line.

        *"Your GPU has 8 GB of VRAM."* was listed above as prose that must
        pass, on the strength of it appearing in the live harvest. But the
        ground it was asserted against is `NOTHING_RAN` - no tool ran, the
        ledger is empty, the person typed nothing - and against THAT ground the
        sentence is a hardware reading that nothing on this machine took. It is
        the defect this whole product is downstream of, named in `CLAUDE.md` in
        as many words: *a hardcoded 8.0 VRAM and a RAM field reading free disk
        space made the app confidently wrong*. The number in the sentence is
        even the same 8.

        What the harvest established is that the model WRITES this sentence,
        not that it was TRUE on the turn it was written; both walls were
        recording rather than refusing, and nothing in the harvest recorded
        whether `inspect_hardware` had run. The old row read a false-catch
        measurement off a corpus that could not tell a false catch from a
        catch.

        So it is re-pinned rather than deleted, and pinned in BOTH directions -
        the lookup is what decides it, and four of the five grounds below let
        it straight through.
        """
        sentence = "Your GPU has 8 GB of VRAM."

        refused = provenance.reads_as_a_measurement(sentence, NOTHING_RAN)
        self.assertIsNotNone(refused, "the founding defect reached the user")
        self.assertEqual(refused["refuted_by"], provenance.NOT_OURS)
        self.assertEqual(refused["fact"], "vram_gb")

        for ground in (
            _Ground(ran={"inspect_hardware": (8.0,)}),
            _Ground(said=(8.0,)),
            _Ground(ledger={"vram_gb": (8.0, evidence.MEASURED, "inspect_hardware")}),
        ):
            with self.subTest(ground=ground.ran or ground.ledger or "said"):
                self.assertIsNone(
                    provenance.reads_as_a_measurement(sentence, ground), sentence
                )

    def test_a_question_asserts_nothing(self):
        self.assertIsNone(
            provenance.reads_as_a_measurement(
                "Did measure_baseline report 0.75?", NOTHING_RAN
            )
        )


class TheBoundaryIsDeclaredTest(Sandboxed):
    """What the wall does NOT cover, asserted rather than only written down.

    The habit of saying so is why several of this project's defects were ever
    visible. A declared gap that no test pins is a gap somebody closes by
    accident and calls a fix.
    """

    def test_an_unattributed_number_is_not_this_wall_s_problem(self):
        """"Your baseline is around 0.75" names no instrument and no declared
        reading-only fact. There is nothing to look up, so nothing is refuted -
        it is the sentry's shape of problem, not this one's."""
        self.assertIsNone(
            provenance.reads_as_a_measurement(
                "Your baseline is around 0.75.", NOTHING_RAN
            )
        )

    def test_a_tool_named_in_english_rather_than_in_full_is_not_matched(self):
        """Widening to the English words would read "we should measure the
        baseline first" as an attribution, and the value of this wall is that
        it does not guess."""
        self.assertIsNone(
            provenance.reads_as_a_measurement(
                "The baseline measurement says 0.75.", NOTHING_RAN
            )
        )

    def test_a_non_numeric_attribution_is_not_checked(self):
        """Only numbers, because only numbers are what invariants 3 and 5 are
        about."""
        self.assertIsNone(
            provenance.reads_as_a_measurement(
                "measure_baseline found that your prompt is the problem.",
                NOTHING_RAN,
            )
        )


class TheGroundIsTheRecordsAndNotTheModelTest(Sandboxed):
    """Where the ground truth comes from, asserted as a property.

    A wall checked against something the model can write is not a wall.
    """

    def test_the_tool_names_come_from_the_registry(self):
        from app.tools import REGISTRY

        registered = {spec.name for spec in REGISTRY}
        self.assertEqual(provenance._registered_tools(), frozenset(registered))

    def test_the_reading_only_facts_come_from_the_ledger_declaration(self):
        declared = {
            name
            for name, decl in evidence.spec().facts.items()
            if decl.get("source") == "inspect"
        }
        self.assertEqual(provenance._readings(), frozenset(declared))
        self.assertIn("baseline_score", declared)
        self.assertNotIn("target_score", declared)

    def test_a_tool_that_ran_and_failed_still_ran(self):
        """It ran, so a claim naming it is not refuted by DID_NOT_RUN. What it
        did not do is produce a number, which the other refutation covers."""
        ground = provenance.Ground(None)
        ground.note_tool("measure_baseline", {"ok": False, "error": "no eval set"})
        self.assertTrue(ground.instrument_ran("measure_baseline"))
        row = provenance.reads_as_a_measurement(
            "measure_baseline reported 0.75.", ground
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["refuted_by"], provenance.NOT_OURS)

    def test_a_tool_result_is_read_for_every_number_in_it(self):
        ground = provenance.Ground(None)
        ground.note_tool(
            "inspect_hardware",
            {"ok": True, "facts": {"vram_gb": {"value": 8.0}}, "ram_gb": 31.9},
        )
        self.assertTrue(ground.backs("8"))
        self.assertTrue(ground.backs("31.9"))
        self.assertFalse(ground.backs("64"))

    def test_a_tool_result_is_read_for_every_number_it_produced(self):
        """And the numbers are kept UNDER THE NAME OF THE TOOL THAT MADE THEM.

        `backs` is the flat question and still answers it. `produced` is the
        joint one, and it is the question this module was not asking.
        """
        ground = provenance.Ground(None)
        ground.note_tool("inspect_hardware", {"ok": True, "vram_gb": 8.0})
        ground.note_tool("measure_eval_set", {"ok": True, "eval_size_n": 120})
        self.assertEqual(ground.readings_of("inspect_hardware"), {8.0})
        self.assertEqual(ground.readings_of("measure_eval_set"), {120.0})
        self.assertEqual(ground.from_tools, {8.0, 120.0})
        self.assertTrue(ground.produced("inspect_hardware", "8"))
        self.assertFalse(ground.produced("inspect_hardware", "120"))


class TheJointLookupTest(Sandboxed):
    """DID X PRODUCE N - the question the two separate lookups never asked.

    `Ground.ran` was `dict[str, bool]`, so `_refute` asked "did X run?" and,
    separately, "is N anywhere in the pool?". `note_tool(name, result)` received
    both halves of the association and merged the numbers into one flat set.

    The cost is the reported defect with the roles swapped, and it is the
    likelier real-world shape: a model holding REAL numbers and mislabelling
    their SOURCE. Every sentence in this class is one whose numbers the harness
    genuinely holds.
    """

    def setUp(self):
        super().setUp()
        #: An ordinary turn. Two instruments ran, each produced its own
        #: reading, `state_facts` ran and produced nothing. Every number is
        #: real; only the attributions lie.
        self.turn = _Ground(
            ran={
                "measure_baseline": (0.7532,),
                "measure_eval_set": (40000,),
                "state_facts": (),
            },
            ledger={
                "baseline_score": (0.7532, evidence.MEASURED, "measure_baseline"),
                "eval_size_n": (40000, evidence.MEASURED, "measure_eval_set"),
            },
        )

    def test_a_real_number_wearing_another_tools_name_is_refuted(self):
        for sentence in (
            "Your baseline is 0.7532, measured by state_facts.",
            "Your baseline is 0.7532, measured by measure_eval_set.",
            "state_facts measured 0.7532 on your eval set.",
            "Your eval set holds 40000 rows, measured by measure_baseline.",
        ):
            with self.subTest(sentence=sentence):
                row = provenance.reads_as_a_measurement(sentence, self.turn)
                self.assertIsNotNone(row, sentence)
                self.assertEqual(row["refuted_by"], provenance.NOT_ITS)

    def test_the_same_number_under_the_instrument_that_made_it_passes(self):
        """THE CONTROL, and it is the whole reason the lookup has to be joint.

        Same numbers, same turn, same records. What changes is only which
        instrument the sentence names.
        """
        for sentence in (
            "Your baseline is 0.7532, measured by measure_baseline.",
            "measure_eval_set counted 40000 rows.",
            "Your eval set holds 40000 rows, measured by measure_eval_set.",
        ):
            with self.subTest(sentence=sentence):
                self.assertIsNone(
                    provenance.reads_as_a_measurement(sentence, self.turn), sentence
                )

    def test_the_refusal_names_the_instrument_that_did_produce_it(self):
        """Composed from the records, so it cannot be true of another turn."""
        row = provenance.reads_as_a_measurement(
            "Your baseline is 0.7532, measured by state_facts.", self.turn
        )
        said = provenance.refusal_sentence(row)
        self.assertIn("state_facts", said)
        self.assertIn("0.7532", said)
        self.assertIn("measure_baseline", said)

    def test_a_wide_pool_is_what_made_the_flat_lookup_meaningless(self):
        """ONE `list_runs` OF TWENTY ROWS IS A SIXTY-NUMBER POOL.

        After it, any of those sixty passes as any instrument's reading. This
        is mechanism (b), and it is mechanism (a) made quantitative.
        """
        rows = [{"id": n, "loss": round(2.0 - n * 0.05, 2)} for n in range(20)]
        turn = _Ground(
            ran={
                "list_runs": provenance.numbers_in(rows),
                "measure_baseline": (0.7532,),
            }
        )
        self.assertIn(1.2, turn.from_tools)
        row = provenance.reads_as_a_measurement(
            "Your baseline is 1.2, measured by measure_baseline.", turn
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["refuted_by"], provenance.NOT_ITS)
        self.assertEqual(row["produced_by"], ("list_runs",))

    def test_a_number_the_user_gave_is_not_any_instruments_reading(self):
        """THE USER IS NOT AN INSTRUMENT.

        Their figures still back the flat pool - arithmetic on what somebody
        told you is not a fabrication - but no tool's own readings contain
        them, so attributing one to a tool is refuted and the closing says
        where the number really came from.
        """
        turn = _Ground(ran={"profile_dataset": (12000,)}, said=(40000.0,))
        self.assertTrue(turn.backs("40000"))
        row = provenance.reads_as_a_measurement(
            "profile_dataset measured 40,000 support tickets.", turn
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["refuted_by"], provenance.NOT_ITS)
        self.assertTrue(row["from_the_user"])
        self.assertIn("you gave me", provenance.refusal_sentence(row))

    def test_a_reading_from_an_earlier_turn_is_in_scope_and_is_backed(self):
        """The ledger crosses turns and carries the attribution with it.

        Nothing ran in this turn. `measure_baseline` stamped `baseline_score`
        in an earlier one, and that row names the tool, so the claim is checked
        against it and passes. A transient tool result from an earlier turn
        that stamped nothing left no record that anything produced it, and this
        module will not invent one - that is a boundary, and it was already
        true of the flat pool.
        """
        earlier = _Ground(
            ledger={
                "baseline_score": (0.7532, evidence.MEASURED, "measure_baseline")
            }
        )
        self.assertEqual(earlier.ran, {})
        self.assertTrue(earlier.instrument_ran("measure_baseline"))
        self.assertIsNone(
            provenance.reads_as_a_measurement(
                "Your baseline is 0.7532, measured by measure_baseline.", earlier
            )
        )
        row = provenance.reads_as_a_measurement(
            "Your baseline is 0.7532, measured by measure_eval_set.", earlier
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["refuted_by"], provenance.DID_NOT_RUN)

    def test_two_tools_that_both_produced_it_are_both_true(self):
        """Attribution to either is true, and nothing here has to pick."""
        both = _Ground(
            ran={"measure_baseline": (0.7532,), "state_facts": (0.7532,)}
        )
        for name in ("measure_baseline", "state_facts"):
            with self.subTest(instrument=name):
                self.assertIsNone(
                    provenance.reads_as_a_measurement(
                        f"Your baseline is 0.7532, measured by {name}.", both
                    )
                )

    def test_arithmetic_beside_a_real_reading_is_not_the_bound_claim(self):
        """ONE READING PER ATTRIBUTION, and the rest of the sentence is context.

        The per-instrument lookup is asked about the number the attribution
        BINDS - the nearest one. `measure_eval_set` never returned 10,000, and
        attributing 10,000 to it would be refuted; here it is not refuted,
        because the attribution binds the 40,000 and the 10,000 is checked
        against the flat pool instead.

        AND THE FLAT POOL IS WHAT CARRIES IT, WHICH IS NARROWER THAN IT LOOKS.
        `said` below is not decoration: this sentence passes because the person
        typed 10,000 and 4 earlier in the thread, so the flat pool holds both.
        Take them out and the same sentence is REFUTED, because a number
        computed inside the sentence is in no pool anywhere - see
        `ArithmeticOnARealReadingTest`, which is that defect written down. This
        test asserts the nearest-number rule and NOTHING about arithmetic; it
        was written claiming both, and the second half was carried by a ground
        that had been handed the answer.
        """
        turn = _Ground(ran={"measure_eval_set": (40000,)}, said=(4.0, 10000.0))
        self.assertTrue(turn.backs("10000"), "the ground, not the reader")
        self.assertIsNone(
            provenance.reads_as_a_measurement(
                "measure_eval_set counted 40000 rows, so you have 10000 per "
                "class across your 4 classes.",
                turn,
            )
        )
        # The bound number is the one the instrument is held to. Same sentence,
        # same ground, 10,000 moved into the attribution's own slot.
        self.assertIsNotNone(
            provenance.reads_as_a_measurement(
                "measure_eval_set counted 10000 rows.", turn
            )
        )

    def test_a_claim_the_ledger_holds_is_not_that_tools_reading(self):
        """THE DOOR IS NOT THE INSTRUMENT, and `state_facts` is the door.

        `state_facts` writes what its caller hands it, at the caller's origin,
        and every row it writes carries `tool: state_facts`. A per-tool index
        that took the `tool` column at face value would put a number THE MODEL
        ASSERTED into `state_facts`' own pool, and the model could then launder
        it into a measurement by asserting it and quoting it back one sentence
        later. `evidence` already draws this line - `_row` marks every
        non-MEASURED value as a claim on the way out - and `Ground.by_tool`
        draws the same one.

        The tool still counts as having RUN, because it did, and a refusal
        saying it "has recorded nothing in this conversation" would be a false
        sentence about a real row.
        """
        laundered = _Ground(
            ledger={"baseline_score": (0.85, evidence.ASSERTED, "state_facts")}
        )
        self.assertTrue(laundered.instrument_ran("state_facts"))
        self.assertEqual(laundered.readings_of("state_facts"), set())
        row = provenance.reads_as_a_measurement(
            "Your baseline is 0.85, measured by state_facts.", laundered
        )
        self.assertIsNotNone(row, "an asserted value passed as a measurement")
        self.assertEqual(row["refuted_by"], provenance.NOT_ITS)

    def test_a_measured_row_is_that_tools_reading(self):
        """The control for the line above. Same table, same column, other
        origin, and the claim is true."""
        measured = _Ground(
            ledger={
                "baseline_score": (0.85, evidence.MEASURED, "measure_baseline")
            }
        )
        self.assertEqual(measured.readings_of("measure_baseline"), {0.85})
        self.assertIsNone(
            provenance.reads_as_a_measurement(
                "Your baseline is 0.85, measured by measure_baseline.", measured
            )
        )

class ArithmeticOnARealReadingTest(Sandboxed):
    """THE FALSE-CATCH FAMILY THIS WALL HAS, AND THE ONE IT SAID IT DID NOT.

    The module docstring's *One reading per attribution* section offers this
    exact sentence as the thing that keeps working:

        "measure_eval_set counted 40000 rows, so you have 10000 per class"

    and says the 10,000 "gets the flat pool, which is what keeps the product
    able to do the thing people most often ask it for". THE FLAT POOL DOES NOT
    HOLD IT. The pool is what tools returned, what the ledger stamped, what the
    user typed and what the brief said - and a number the model COMPUTED inside
    the sentence is in none of those, by construction. So the second half of
    the lookup does not refute the claim on its merits; it refutes every
    derivation unconditionally.

    That is structurally the same argument this file already accepted once, in
    `TheAttributionWithNoNumberInItTest`: a frame whose lookup cannot come back
    "backed" has no second half, and the asymmetry that makes a loose reading
    cheap is exactly what it gives up. It was right about the no-number table
    and wrong about this.

    **Measured, both readers, over the ten sentences below with honest ground:**

        previous reader (e2b6ff1)   3 of 10 stopped
        this reader                 9 of 10 stopped

    SO THE FAMILY IS OLDER THAN THE JOINT LOOKUP AND IS NOT ITS FAULT - what
    tripled it is mechanism (d), the harvested verb list. `counted`, `detected`
    and `read` are the verbs this product's dataset tools actually use, and
    every sentence they newly open a frame on is one where a model is doing
    arithmetic out loud on a number it really has.

    **And the 11,404-sentence harvest reported zero false catches.** Whatever
    that harvest covered, it did not cover this, and the number should not be
    read as though it did. Nothing in the tree reproduces the harvest, so the
    honest status of the zero is unverified rather than wrong.

    Not fixed here on purpose. Every fix on the table - a derivation-connective
    list, a clause boundary, dropping the non-bound numbers from an attributed
    frame - is a vocabulary or a trade, and this module was burned one commit
    ago for writing a vocabulary from imagination. The fix wants the same live
    harvest the verb list finally got, and `@open_defect` is how this codebase
    holds a defect that is understood but not yet honestly measurable.
    """

    #: Honest ground. `measure_eval_set` counted 40,000; `measure_baseline`
    #: scored 0.7532; `profile_dataset` saw 40,000 rows in 12 clusters. The
    #: person said their target is 0.85 and that they have 4 classes. NOTHING
    #: derived is in here, which is the whole point - a ground handed the
    #: answer is what made the sibling test above look like it proved this.
    def setUp(self):
        super().setUp()
        self.honest = _Ground(
            ran={
                "measure_eval_set": (40000,),
                "measure_baseline": (0.7532,),
                "profile_dataset": (40000, 12),
            },
            said=(0.85, 4),
        )

    #: Ten sentences, every one of them the product working: a real reading,
    #: attributed to the instrument that really produced it, with the model
    #: computing on it in the same breath.
    DERIVATIONS = (
        "measure_eval_set counted 40000 rows, so you have 10000 per class.",
        "measure_eval_set counted 40000 rows, which is 8000 for validation at 80/20.",
        "profile_dataset counted 40000 tickets, giving 320 batches of 125.",
        "measure_baseline reported 0.7532, so you need 0.0968 more to hit your target.",
        "measure_baseline scored 0.7532, which leaves 0.2468 of headroom.",
        "measure_eval_set counted 40000 rows, roughly 33 MB on disk.",
        "profile_dataset detected 12 duplicate clusters across 40000 rows, "
        "about 0.03% of the set.",
        "measure_baseline reported 0.7532 today, up from 0.7100 last week.",
        "measure_eval_set counted 40000 rows; at 32 rows a batch that is 1250 steps.",
        "profile_dataset counted 40000 tickets, so a 10% holdout is 4000 rows.",
    )

    def _stopped(self):
        return [
            (sentence, provenance.reads_as_a_measurement(sentence, self.honest))
            for sentence in self.DERIVATIONS
            if provenance.reads_as_a_measurement(sentence, self.honest) is not None
        ]

    @open_defect(
        "arithmetic_beside_an_attribution",
        "a number the model COMPUTED from a real reading is in no pool, so the "
        "flat lookup refutes every derivation written beside an attribution",
    )
    def test_reasoning_out_loud_on_a_real_reading_is_not_a_fabrication(self):
        """Nine of these ten fire. Every one of them is the product working."""
        self.assertEqual([sentence for sentence, _ in self._stopped()], [])

    def test_the_damage_is_confined_to_the_numbers_it_did_not_bind(self):
        """THE CONTROL, and it is what says a fix must be narrow.

        The joint lookup is intact underneath this: not one of these fires on
        the number the attribution BINDS. Every refutation is a number the
        sentence derived, refuted as `NOT_OURS` - never `NOT_ITS`, never the
        instrument's own reading called somebody else's. A fix that stopped
        reading these sentences altogether would give back real ground; a fix
        that leaves the bound number checked gives back none.
        """
        stopped = self._stopped()
        self.assertTrue(stopped, "the defect went away without this being updated")
        for sentence, row in stopped:
            with self.subTest(sentence=sentence):
                self.assertEqual(row["refuted_by"], provenance.NOT_OURS)
                self.assertFalse(
                    self.honest.backs(row["number"]),
                    "a number the harness holds was refuted as not ours",
                )

    def test_the_same_sentences_pass_when_the_derivation_is_also_on_record(self):
        """The pool is the whole difference, not the shape of the sentence.

        Hand the ground every derived value - as though the person had typed
        them - and all ten pass unchanged. So nothing here is a reading problem.
        """
        derived = _Ground(
            ran=self.honest.ran,
            said=(
                0.85, 4, 10000, 8000, 320, 125, 0.0968, 0.2468, 33, 0.0003,
                0.71, 32, 1250, 0.10, 4000, 80, 20,
            ),
        )
        for sentence in self.DERIVATIONS:
            with self.subTest(sentence=sentence):
                self.assertIsNone(
                    provenance.reads_as_a_measurement(sentence, derived), sentence
                )


class EveryOpenDefectFailsForTheRightReasonTest(Sandboxed):
    """`expectedFailure` swallows a broken probe as happily as a real defect.

    So each one is re-run here outside the decorator and its traceback is read:
    it must be the assertion the probe makes, not an import error or a typo in
    the fixture. The same guard `tests/test_laundering_routes.py` keeps, for
    the same reason.
    """

    def test_the_declared_count_matches_the_declared_defects(self):
        self.assertEqual(len(OPEN_DEFECTS), OPEN_DEFECTS_NOW)

    def test_each_open_defect_fails_on_its_own_assertion(self):
        for name, method in vars(ArithmeticOnARealReadingTest).items():
            defect = getattr(method, "open_defect", None)
            if defect is None:
                continue
            with self.subTest(defect=defect):
                case = ArithmeticOnARealReadingTest(name)
                case.setUp()
                inner = getattr(ArithmeticOnARealReadingTest, name)
                # `expectedFailure` wraps the function; the original is what we
                # want to watch fail.
                original = getattr(inner, "__wrapped__", inner)
                with self.assertRaises(AssertionError) as caught:
                    original(case)
                self.assertIn("measure_", str(caught.exception))


class TheSevenOtherMechanismsTest(Sandboxed):
    """One class, seven demonstrations, each with the pair that shows the seam.

    Every one of these was measured against the previous reader first, lifted
    out of git: it stopped none of them. They are grouped rather than split
    because they are one finding - the reader was narrower than the model's
    actual vocabulary and punctuation - and each is written as the pair that
    made it visible.
    """

    def test_punctuation_no_longer_defeats_the_harness_name(self):
        """(c) One comma. `phrase_at` compared raw tokens while
        `_instrument_at` stripped punctuation, so a multiword name survived a
        comma nowhere."""
        for sentence in (
            "According to the harness your eval set holds 40000 rows",
            "According to the harness, your eval set holds 40000 rows.",
            "The harness, which ran first, measured 40000 rows.",
            "According to the harness's diagnosis engine, your VRAM is 24 GB.",
        ):
            with self.subTest(sentence=sentence):
                self.assertIsNotNone(
                    provenance.reads_as_a_measurement(sentence, NOTHING_RAN),
                    sentence,
                )

    def test_the_counting_verbs_this_products_tools_actually_use(self):
        """(d) Seven of ten natural verbs missed, and COUNTING IS WHAT THE
        DATASET TOOLS DO. The list was written from imagination; these are
        harvested from what granite4-hermes actually writes."""
        for verb in (
            "counted", "read", "detected", "shows", "says", "estimated",
            "logged", "identified", "flagged", "measured",
        ):
            with self.subTest(verb=verb):
                self.assertIsNotNone(
                    provenance.reads_as_a_measurement(
                        f"profile_dataset {verb} 40,000 support tickets.",
                        NOTHING_RAN,
                    ),
                    verb,
                )

    def test_a_verb_that_describes_a_capability_is_not_an_attribution(self):
        """The other half of the same harvest, and the reason it was filtered
        by hand rather than taken whole. These are what the model writes when
        it is explaining the product, and none of them claims a reading.

        `listed` IS THE ONE THAT WENT IN AND CAME BACK OUT, and the last
        sentence here is verbatim from the harvest: it was the only false catch
        in 3,682 ordinary live sentences. 28 is the right number, and it is
        right because the harness put it in the model's prompt - a source the
        ground this module reads does not include. Listing is not measuring.
        """
        for sentence in (
            "list_runs allows 20 rows per page.",
            "run_in_sandbox executes 1 job at a time.",
            "propose_build proposes 3 options.",
            "list_runs lists your 20 most recent runs.",
            "The harness has listed 28 tools that are registered on this "
            "machine.",
        ):
            with self.subTest(sentence=sentence):
                self.assertIsNone(
                    provenance.reads_as_a_measurement(sentence, NOTHING_RAN),
                    sentence,
                )

    def test_an_unregistered_instrument_is_the_sharpest_refutation(self):
        """(e) It was the most invisible one: no frame opened at all, so the
        more brazen the fabrication the less this module saw of it."""
        for sentence in (
            "Your accuracy is 0.91, measured by measure_accuracy.",
            "measure_accuracy reported 0.91 on your eval set.",
            "measure_accuracy counted 91 correct answers.",
        ):
            with self.subTest(sentence=sentence):
                row = provenance.reads_as_a_measurement(sentence, NOTHING_RAN)
                self.assertIsNotNone(row, sentence)
                self.assertEqual(
                    row["refuted_by"], provenance.NO_SUCH_INSTRUMENT
                )
                self.assertEqual(row["instrument"], "measure_accuracy")
        said = provenance.refusal_sentence(
            provenance.reads_as_a_measurement(
                "Your accuracy is 0.91, measured by measure_accuracy.",
                NOTHING_RAN,
            )
        )
        self.assertIn("no instrument in this harness called", said)

    def test_an_unregistered_name_is_not_read_off_a_bare_preposition(self):
        """WHAT KEEPS (e) NARROW. `from support_tickets` is a file and not an
        instrument, and the registry has always been what kept the bare
        preposition safe. A verb or an explicit attribution phrase is what
        admits a name this harness does not have."""
        for sentence in (
            "You have 40,000 rows from support_tickets.",
            "Load 500 examples from my_training_data.",
        ):
            with self.subTest(sentence=sentence):
                self.assertIsNone(
                    provenance.reads_as_a_measurement(sentence, NOTHING_RAN),
                    sentence,
                )

    def test_a_declared_fact_name_is_never_read_as_an_instrument(self):
        """`baseline_score` is tool-shaped. Frame 1 is where it belongs, and a
        refusal that called it an instrument would be this module inventing a
        capability while refusing an invented number."""
        row = provenance.reads_as_a_measurement(
            "The value 0.91 was reported by baseline_score.", NOTHING_RAN
        )
        if row is not None:
            self.assertNotEqual(row["refuted_by"], provenance.NO_SUCH_INSTRUMENT)

    def test_a_table_row_is_an_attribution_and_a_two_cell_row_is_not(self):
        """(f) The cell wall is the attribution, and three cells is the floor.

        Two-cell rows are how this product describes its own tools, and a
        description is not a report. A third cell means a VALUE is present.
        """
        self.assertIsNotNone(
            provenance.reads_as_a_measurement(
                "| Eval rows | 40,000 | measure_eval_set |", NOTHING_RAN
            )
        )
        self.assertIsNotNone(
            provenance.reads_as_a_measurement(
                "| baseline_score | 0.91 | measure_baseline |", NOTHING_RAN
            )
        )
        for row in (
            "| measure_baseline | scores your prompt against up to 200 rows |",
            "| list_runs | lists your 20 most recent runs |",
            "| Tool | What it does |",
        ):
            with self.subTest(row=row):
                self.assertIsNone(
                    provenance.reads_as_a_measurement(row, NOTHING_RAN), row
                )

    def test_a_keyed_source_is_the_same_claim_written_for_a_machine(self):
        """(f) again. JSON and `(Tool: x)` are records, not sentences, and the
        key word is what is left once the punctuation is flattened away."""
        for blob in (
            '{"metric": "baseline", "value": 0.91, "source": "measure_baseline"}',
            '{"value": 0.91, "tool": "measure_baseline"}',
            "**baseline_score**: `0.91` (Tool: `measure_baseline`)",
        ):
            with self.subTest(blob=blob):
                self.assertIsNotNone(
                    provenance.reads_as_a_measurement(blob, NOTHING_RAN), blob
                )

    def test_one_way_to_read_a_percent_sign(self):
        """(g) A BUG, NOT A DESIGN QUESTION. The pool was built with a parser
        that read `0.75%` as 0.0075 and matched with one that read it as the
        numeral 0.75, and the disagreement went the permissive way every time.

        One parser now, and a declared unit is taken from the model: `75%`
        against a measured `0.7532` still passes, because rounding is granted;
        `0.75%` against a measured `0.75` does not, because it is a claim of
        0.0075 and this harness holds no such reading.
        """
        self.assertEqual(provenance._numeral("0.75%"), (0.0075, 4, True))
        self.assertEqual(provenance._numeral("0.75"), (0.75, 2, False))
        self.assertEqual(provenance.numbers_in("0.75%"), {0.0075})

        held = _Ground(ran={"measure_baseline": (0.75,)})
        self.assertIsNotNone(
            provenance.reads_as_a_measurement(
                "measure_baseline reported 0.75%.", held
            ),
            "the percent claim went through",
        )

        rounded = _Ground(ran={"measure_baseline": (0.7532,)})
        for written in ("0.75", "75%", "75.3%", "75"):
            with self.subTest(written=written):
                self.assertIsNone(
                    provenance.reads_as_a_measurement(
                        f"measure_baseline reported {written}.", rounded
                    ),
                    written,
                )

    def test_exactly_withdraws_the_rounding_the_model_is_otherwise_given(self):
        """(h) Rounding is deliberately granted; `exactly` is the model saying
        it did not round. Reading the word is the whole of the fix."""
        held = _Ground(ran={"measure_baseline": (0.7532,)})
        self.assertIsNone(
            provenance.reads_as_a_measurement(
                "Your baseline is 0.75, measured by measure_baseline.", held
            )
        )
        self.assertIsNotNone(
            provenance.reads_as_a_measurement(
                "Your baseline is exactly 0.75, measured by measure_baseline.",
                held,
            )
        )
        self.assertIsNone(
            provenance.reads_as_a_measurement(
                "Your baseline is exactly 0.7532, measured by measure_baseline.",
                held,
            )
        )


class TheAttributionWithNoNumberInItTest(Sandboxed):
    """WIDENED, MEASURED, AND TAKEN BACK OUT. The retraction is the finding.

    A live turn with ZERO TOOL CALLS handed the user a markdown table
    attributing `eval_size_n`, `vram_gb`, `ram_gb`, `disk_free_gb` and
    `accelerator` to `inspect_hardware`, every value `N/A`. No numeral, so a
    numbers-only wall had nothing to hold.

    This module was widened to take it: a table row of three or more cells with
    a declared reading-only fact, a value, and a registered tool that did not
    run. The argument was that only the SUBJECT is refutable there, so nothing
    could be wrongly refuted about the reading. THE ARGUMENT WAS WRONG, and the
    first live reporting harvest said so - four fires in 2,088 sentences, on a
    turn where nothing ran, on the model doing the right thing:

        | ram_gb  | Infered (not measured) | inspect_hardware |
        | vram_gb | Infered (not measured) | inspect_hardware |

    `N/A` and `Infered (not measured)` are the same shape to any reader. Telling
    them apart needs a vocabulary of disclaimers - a heuristic in the one frame
    that has no second lookup to check it against, because a frame with no
    number fires unconditionally once it is misread. That is the asymmetry this
    whole module rests on, given up in one place.
    """

    #: Verbatim, from the reporting harvest. Every one of these is the model
    #: being HONEST about what it does not have, and every one of them fired.
    HONEST = (
        "| ram_gb | Infered (not measured) | inspect_hardware |",
        "| vram_gb | Infered (not measured) | inspect_hardware |",
        "| disk_free_gb | Infered (not measured) | inspect_hardware |",
        "| accelerator | Infered (not measured) | inspect_hardware |",
    )

    def test_the_honest_row_that_reversed_the_decision_passes(self):
        for row in self.HONEST:
            with self.subTest(row=row):
                self.assertIsNone(
                    provenance.reads_as_a_measurement(row, NOTHING_RAN), row
                )

    def test_and_so_the_live_n_a_table_is_declared_out_of_scope(self):
        """SAID OUT LOUD RATHER THAN LEFT SILENT, which is what the brief asks.

        These reach the user, this module does not stop them, and the reason is
        the class docstring. Where it belongs instead: the instruction set, so
        the model points at `evidence.ledger_view` rather than composing its own
        table, and a whole-reply check that can see five rows as one object.
        `_Sentry` feeds this module one sentence at a time, and a table is not a
        sentence.
        """
        for row in (
            "| eval_size_n | N/A | inspect_hardware |",
            "| vram_gb | N/A | inspect_hardware |",
        ):
            with self.subTest(row=row):
                self.assertIsNone(
                    provenance.reads_as_a_measurement(row, NOTHING_RAN), row
                )

    def test_the_same_row_with_a_number_in_it_is_still_stopped(self):
        """What the table frame DOES cover, and the line between them.

        A value that is a number brings the second lookup back, and with it the
        asymmetry: this fires because `inspect_hardware` did not run AND 24.0 is
        not a reading anything here holds.
        """
        row = provenance.reads_as_a_measurement(
            "| vram_gb | 24.0 | inspect_hardware |", NOTHING_RAN
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["refuted_by"], provenance.DID_NOT_RUN)

    def test_a_capability_statement_was_never_in_scope_either(self):
        """The wider version of the same widening, and the same reason.

        "eval_size_n is measured by measure_eval_set" is TRUE, this product's
        replies make it constantly, and the only lookup available to a
        non-numeric attribution - did that tool run - cannot tell it from a
        false report.
        """
        for sentence in (
            "eval_size_n is measured by measure_eval_set.",
            "Your VRAM is read by inspect_hardware.",
            "measure_baseline found that your prompt is the problem.",
            "| eval_size_n | measure_eval_set |",
        ):
            with self.subTest(sentence=sentence):
                self.assertIsNone(
                    provenance.reads_as_a_measurement(sentence, NOTHING_RAN),
                    sentence,
                )


class WhatTheHarnessToldTheModelIsGroundTooTest(Sandboxed):
    """THE ONE FALSE-CATCH FAMILY IN 7,400 LIVE SENTENCES, and its root cause.

    Two sentences, both verbatim from the harvest, both TRUE, both refuted:

        "The harness has listed 28 tools that are registered on this machine."
        "The harness has identified 28 tools available on this machine."

    Nothing ran on either turn, so nothing "produced" 28 - and 28 is right,
    because the harness itself wrote it into `conductor.standing_brief` before
    the model said anything. A number we told the model is not a number the
    model invented, and the ground was missing the source.

    It is the permissive direction, which the asymmetry makes cheap, and it is
    the RIGHT answer rather than a concession: the registry has 28 tools in it.
    """

    def brief(self):
        return conductor.standing_brief(None)

    def test_the_brief_is_the_harness_stating_facts_about_itself(self):
        """One number, and it is the registry's own count. Read off the brief
        rather than written here, because writing one would be inventing one."""
        from app.tools import REGISTRY

        numbers = provenance.numbers_in(self.brief())
        self.assertEqual(numbers, {float(len(tuple(REGISTRY)))})

    def test_a_number_the_harness_briefed_backs_a_claim_about_the_harness(self):
        ground = provenance.Ground(None)
        ground.note_briefing(self.brief())
        count = len(tuple(__import__("app.tools", fromlist=["REGISTRY"]).REGISTRY))
        for sentence in (
            f"The harness has identified {count} tools available on this machine.",
            f"The harness has counted {count} tools on this machine.",
        ):
            with self.subTest(sentence=sentence):
                self.assertIsNone(
                    provenance.reads_as_a_measurement(sentence, ground), sentence
                )

    def test_without_the_briefing_the_same_sentence_is_refuted(self):
        """The control, and the reason this source had to exist."""
        count = len(tuple(__import__("app.tools", fromlist=["REGISTRY"]).REGISTRY))
        self.assertIsNotNone(
            provenance.reads_as_a_measurement(
                f"The harness has identified {count} tools available on this "
                "machine.",
                NOTHING_RAN,
            )
        )

    def test_it_is_the_brief_and_not_the_whole_system_prompt(self):
        """WHY THE NARROW SOURCE, and it is not tidiness.

        When worked examples are loaded, the system prompt carries "about
        40,000 support tickets" and a hex instruction-set id whose digits
        parse as a number. Folding the prompt into the ground would back
        `eval_size_n: 40000` on a thread where nothing counted anything,
        which is the live fabrication this whole module exists for.

        (AF4, 2026-09-14: examples are opt-in for Run/autonomy. The wall
        still has to refuse that number when examples ARE loaded.)
        """
        row = {
            "id": 1, "name": "x", "model": "m", "adapter": "ollama",
            "base_url": "http://127.0.0.1:11434", "kind": "local",
            "tool_calling": "yes", "capability_detail": "",
        }
        prompt = conductor.system_prompt(row, sensitive=False, examples=True)
        self.assertIn(40000.0, provenance.numbers_in(prompt))
        self.assertNotIn(40000.0, provenance.numbers_in(self.brief()))
        self.assertNotIn(
            40000.0,
            provenance.numbers_in(conductor.system_prompt(row, sensitive=False)),
            "default assembly must not pay for the worked-example figure",
        )

        ground = provenance.Ground(None)
        ground.note_briefing(self.brief())
        row = provenance.reads_as_a_measurement("eval_size_n: 40000", ground)
        self.assertIsNotNone(row, "the prompt's worked example backed a claim")
        self.assertEqual(row["refuted_by"], provenance.NOT_OURS)

    def test_the_briefing_backs_no_instruments_own_pool(self):
        """The harness writing a count in a brief is not an instrument reading.

        Same rule as the user's own numbers, for the same reason.
        """
        ground = provenance.Ground(None)
        ground.note_briefing(self.brief())
        count = len(tuple(__import__("app.tools", fromlist=["REGISTRY"]).REGISTRY))
        self.assertEqual(ground.readings_of("list_runs"), set())
        self.assertIsNotNone(
            provenance.reads_as_a_measurement(
                f"list_runs counted {count} tools.", ground
            )
        )

class EveryRefutationIsSpokenTest(Sandboxed):
    """A refutation nobody wrote a sentence for reads to the user as nothing.

    Derived from `provenance.REFUTATIONS` rather than listed, so the next one
    added is covered by this test on the day it is added rather than on the day
    somebody remembers.
    """

    def test_the_closing_says_something_specific_for_each_of_them(self):
        for reason in provenance.REFUTATIONS:
            with self.subTest(reason=reason):
                said = provenance.refusal_sentence(
                    {
                        "refuted_by": reason,
                        "instrument": "measure_baseline",
                        "fact": "baseline_score",
                        "number": "0.75",
                        "held": 0.42,
                        "origin": evidence.MEASURED,
                        "produced_by": ("measure_eval_set",),
                    }
                )
                self.assertIn("0.75", said)
                self.assertGreater(len(said), 80, reason)

    def test_the_transcript_has_a_clause_for_each_of_them(self):
        for reason in provenance.REFUTATIONS:
            with self.subTest(reason=reason):
                self.assertIn(reason, conductor._REFUTATIONS)

    def test_the_order_is_sharpest_first(self):
        """One sentence can carry the same claim in two frames, and which
        refutation the user is told is decided by this order."""
        self.assertEqual(provenance.REFUTATIONS[0], provenance.NO_SUCH_INSTRUMENT)
        self.assertEqual(provenance.REFUTATIONS[-1], provenance.NOT_OURS)
        row = provenance.reads_as_a_measurement(
            "baseline_score: 0.75 (measured by measure_baseline)", NOTHING_RAN
        )
        self.assertEqual(row["refuted_by"], provenance.DID_NOT_RUN)
