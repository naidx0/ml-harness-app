"""WALL 7. A gate may not open on a model's opinion of its own work.

THE DEFECT, REPRODUCED THROUGH THE REGISTERED TOOL BEFORE ANY OF THIS EXISTED.
Thirty rows, one connection answering the questions and grading the answers:

    baseline_score        0.967   MEASURED
    exact_match           0.400   the same rows, the same run, computed for free
    G1_BASELINE_MEASURED  PASSED
    verdict               NO_TRAIN__SHIP_AS_IS

The product told somebody to ship a system that gets four rows in ten right,
because the system said it was fine. `SelfGrader` below is that run and
`TheDefectThisFileExistsForTest` is that arithmetic, asserted rather than
recounted.

WHY EVERY EXISTING WALL SAID YES. Walls 1 to 4 ask *is this number one the
engine watched being produced*, and it is: `run_eval` ran, this module watched,
the tool declared the fact, no argument was laundered. Wall 5 asks *a
measurement of what*, and the answer is right too - it is about this thread's
own eval set. MEASURED's own definition in the ledger is satisfied word for
word. The question nobody was asking is the third one: **is this the kind of
fact a reading can produce at all.** A judge score is a real measurement of the
judge's opinion and no measurement whatsoever of whether the answer was right.

AND THE MITIGATIONS THAT ALREADY EXISTED ARE WHY IT WAS VISIBLE AND ALSO WHY
THEY WERE NOT ENOUGH. The `how=` line says "judging its own answers" and the
report carries a `self_graded` block with the deterministic scores beside the
judge's. Gates read the origin token, not the prose. A sentence next to a number
is for the person; the number is what the tree walks on.

WHAT IS ASSERTED HERE, in the order the classes run:

  1. the defect's own arithmetic, so the numbers below are not a story;
  2. the ledger refuses to call a judgement a reading - four doors, each one
     tried;
  3. no gate row reads an opinion fact (SC6), derived twice and never listed;
  4. THE PROPERTY, PROVED BY TRYING: a self-graded 96.7% against a target of
     90% does not mint a verdict, and a self-graded shortfall does not mint a
     TRAIN one;
  5. THE OPPOSITE FAILURE: the judge is not refused. A bench that cannot use a
     model grader is less useful than one that labels it, and every refusal
     above would pass against a bench that simply stopped working;
  6. the mutation check: delete `opinion_of: model` from the ledger and the
     refusals in (2) stop refusing. A test of a wall that passes with the wall
     removed is testing nothing, and this repository has been bitten by that.

EVERY REFUSAL HAS A POSITIVE CONTROL NEXT TO IT, for the same reason: the
strongest one is `test_the_same_call_may_still_stamp_the_rule_graded_number`,
where the identical instrument records the judge's 0.967 as an opinion, is
refused when it tries to stamp 0.967 as a baseline, and then stamps the rule's
0.400 without complaint. One call, one wall, and it lets the honest number
through.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import diagnosis_fixtures as fixtures

from app import diagnosis
from app.diagnosis import ASSERTED, Fact, MEASURED, STATED, bare, compile_condition
from app.providers import Delta, store as provider_store
from app.tools import REGISTRY, evals, evidence
from app.tools.evidence import MeasurementError, MODEL, USER

import support


LABELS = ("yes", "no", "maybe", "never", "always")

#: Thirty rows over five labels: the trivial baseline is exactly 0.20.
ROWS = 30
#: Right on the first twelve, so `exact_match` is exactly 12/30 = 0.400.
RIGHT = 12
#: The judge calls one row wrong, so its score is exactly 29/30 = 0.9666...
JUDGE_WRONG = 1

JUDGE_SCORE = 29 / 30
RULE_SCORE = 0.40


def eval_file(root: Path) -> Path:
    path = Path(root) / "eval.jsonl"
    path.write_text(
        "\n".join(
            json.dumps({"q": f"q{i}", "a": LABELS[i % len(LABELS)]})
            for i in range(ROWS)
        ),
        encoding="utf-8",
    )
    return path


class SelfGrader:
    """One object answers the questions AND grades them.

    With no `judge_provider_id` the bench builds the judge from the same
    connection, so a single object serving both prompts is not a shortcut - it
    is exactly the shape the wall is about. Answers are wrong on eighteen of the
    thirty rows and the judge calls twenty-nine of them right.
    """

    def __init__(self, wrong_verdicts: int = JUDGE_WRONG) -> None:
        self.wrong_verdicts = wrong_verdicts
        self.judged = 0
        self.asked = 0

    def stream(self, conversation, offered=None, *, secret=None):
        if conversation[0]["content"] == evals.JUDGE_SYSTEM:
            self.judged += 1
            yield Delta(
                kind="text",
                text="INCORRECT" if self.judged <= self.wrong_verdicts else "CORRECT",
            )
            return
        self.asked += 1
        question = conversation[-1]["content"]
        index = int(re.sub(r"\D", "", str(question)) or 0)
        if index < RIGHT:
            yield Delta(kind="text", text=LABELS[index % len(LABELS)])
        else:
            yield Delta(kind="text", text=LABELS[(index + 1) % len(LABELS)])


class BenchTest(unittest.TestCase):
    """A sandbox, one conversation, one local connection, one scripted model."""

    def setUp(self) -> None:
        self.root = support.sandbox(self)
        self.thread = support.conversations(1)[0]["id"]
        self.path = eval_file(self.root)
        row = provider_store.create(
            "Scripted", "http://127.0.0.1:11434", "scripted", "ollama"
        )
        provider_store.set_active(row["id"])
        self.provider = row
        self.model = SelfGrader()
        original = evals.build
        evals.build = lambda adapter, base_url, name: self.model
        self.addCleanup(lambda: setattr(evals, "build", original))

    def run_eval(self, **arguments):
        payload = {
            "eval_path": str(self.path),
            "input_field": "q",
            "expected_field": "a",
            "sample": ROWS,
            "metric": "model_graded",
        }
        payload.update(arguments)
        return REGISTRY.call(
            "run_eval", payload, actor=MODEL, thread_id=self.thread
        )

    def instrument(self, **overrides):
        arguments = {"tool": "bench", "thread_id": self.thread, "arguments": {}}
        arguments.setdefault("measures", ("baseline_score",))
        # The bench's own capability, because wall 9 asks what kind of tool
        # this is and `run_eval` is the tool this stands in for.
        arguments.setdefault("provides", REGISTRY.get("run_eval").provides)
        arguments.update(overrides)
        return evidence.instrument_for(**arguments)


# ---------------------------------------------------------------------------
# 1. The defect's own arithmetic.


class TheDefectThisFileExistsForTest(BenchTest):
    """The run, and the two numbers it produced for the same thirty rows."""

    def test_the_judge_and_the_rule_disagree_by_fifty_seven_points(self):
        report = self.run_eval()
        self.assertTrue(report["ok"], report.get("detail"))
        self.assertTrue(report["complete"])
        self.assertEqual(report["metric"], "model_graded")
        self.assertEqual(report["graded"], ROWS)

        self.assertAlmostEqual(report["score"], JUDGE_SCORE, places=6)
        block = report["self_graded"]
        self.assertTrue(block["is_the_model_that_answered"])
        self.assertEqual(block["rows_judged"], ROWS)
        self.assertAlmostEqual(
            block["deterministic_scores_on_the_same_rows"]["exact_match"],
            RULE_SCORE,
            places=6,
        )
        # Fifty-six point seven points apart, on rows nobody disputes, in one
        # run. This is the gap the ledger was recording under one name.
        self.assertGreater(report["score"] - RULE_SCORE, 0.5)

    def test_the_gap_is_far_outside_what_thirty_rows_could_confuse(self):
        """Not a resolution problem, said with the bench's own resolution.

        A difference this size is not the eval set being small. The two numbers
        are answers to two different questions.
        """
        report = self.run_eval()
        low, high = report["resolution"]["ci_95"]
        self.assertGreater(low, RULE_SCORE)
        self.assertGreater(report["score"] - RULE_SCORE, high - low)

    def test_the_bench_does_not_yet_file_the_judges_number_as_an_opinion(self):
        """THE HALF THAT IS STILL OPEN, pinned so it cannot be forgotten.

        `app/tools/evals.py` is owned by another pass and this file may not
        touch it. Everything below this class is built and enforced; what is
        missing is one additive call in `run_eval`'s handler:

            instrument.opinion("judge_score", score, how=...)

        beside the `baseline_score` stamp, whenever `metric == model_graded`.
        The moment that call lands, the rename wall in
        `Instrument.measured` refuses the `baseline_score` stamp that follows
        it - see
        `test_a_judgement_cannot_be_stamped_again_under_a_name_a_gate_reads` -
        and this end-to-end defect closes with no further edit here.

        WHEN THIS TEST GOES RED THE GAP IS CLOSED. Delete it; the property it
        stands in for is asserted in
        `AGateMayNotOpenOnAModelsOpinionTest` already.
        """
        report = self.run_eval()
        stamped = {row["fact"]: row["value"] for row in report["measured_facts"]}
        self.assertIn(
            "baseline_score",
            stamped,
            "run_eval no longer stamps baseline_score from a model-graded run - "
            "the gap this test pins is closed, so delete this test",
        )
        self.assertAlmostEqual(stamped["baseline_score"], JUDGE_SCORE, places=6)
        self.assertEqual(
            [row["fact"] for row in evidence.rows_for(self.thread)
             if row["fact"] == "judge_score"],
            [],
            "run_eval now records judge_score - the gap is closed, delete this",
        )


# ---------------------------------------------------------------------------
# 2. The ledger refuses to call a judgement a reading. Four doors.


class TheLedgerRefusesToCallAJudgementAReadingTest(BenchTest):
    """Every way a judge's number could reach the ledger wearing MEASURED."""

    def test_the_ledger_declares_the_fact_an_opinion(self):
        spec = diagnosis.default_spec()
        self.assertEqual(spec.facts["judge_score"]["opinion_of"], "model")
        self.assertEqual(evidence.opinion_of("judge_score"), "model")
        self.assertTrue(evidence.is_an_opinion("judge_score"))
        self.assertEqual(evidence.opinion_facts(), ("judge_score",))
        # And the fact a gate DOES read is not one.
        self.assertIsNone(evidence.opinion_of("baseline_score"))

    def test_the_declaration_is_read_and_not_listed(self):
        """`opinion_facts` asks the ledger. Nothing in the module names it."""
        derived = {
            name
            for name, decl in diagnosis.default_spec().facts.items()
            if decl.get("opinion_of")
        }
        self.assertEqual(set(evidence.opinion_facts()), derived)
        source = Path("app/tools/evidence.py").read_text(encoding="utf-8")
        self.assertNotIn(
            '"judge_score"',
            source,
            "evidence.py names the fact. The ledger is the list; a second one "
            "here is the defect wall 3 already paid for twice",
        )

    def test_no_tool_may_declare_it_at_registration(self):
        """Door one, and it shuts at import rather than at runtime."""
        self.assertFalse(evidence.may_be_declared_measurable("judge_score"))
        self.assertEqual(
            [tool.name for tool in REGISTRY if "judge_score" in tool.measures], []
        )
        reason = evidence.unmeasurable_reason("judge_score")
        self.assertIn("opinion_of: model", reason)
        self.assertIn("Instrument.opinion", reason)

    def test_the_ledger_admits_measured_and_the_harness_still_does_not(self):
        """The two predicates disagree here, and that is the whole point.

        `judge_score` is `source: derive`, and `derive: [MEASURED]`. So the
        ORIGIN table says yes and wall 7 says no, because wall 7 is not about
        origins. Belt and braces: the admissible set for this fact is empty in
        practice, so a gate row that read it by mistake tomorrow could not be
        opened by any origin at all.
        """
        spec = diagnosis.default_spec()
        self.assertEqual(spec.facts["judge_score"]["source"], "derive")
        self.assertIn(MEASURED, spec.admissible_for("judge_score"))
        self.assertTrue(evidence.is_measurable("judge_score"))
        self.assertFalse(evidence.may_be_declared_measurable("judge_score"))

    def test_the_table_refuses_a_measured_row_however_it_was_reached(self):
        """Door two: `record`, where wall 5 learned to stand and for the reason.

        A rule enforced on the function somebody remembered is a rule that is
        not enforced. This is the one that holds for a writer written next year
        that never takes an instrument at all.
        """
        with self.assertRaises(MeasurementError) as caught:
            evidence.record(
                fact="judge_score",
                value=JUDGE_SCORE,
                origin=MEASURED,
                actor=MODEL,
                how="the judge said so",
                tool="bench",
                thread_id=self.thread,
            )
        self.assertIn("opinion_of: model", str(caught.exception))
        self.assertEqual(evidence.rows_for(self.thread), [])

    def test_an_instrument_refuses_it_by_name(self):
        """Door three, and the refusal says the true reason rather than a true one.

        A tool holding this name has not declared it and could not, so "you did
        not declare it" would also be true - and would send the reader looking
        for the wrong fix. The opinion check runs first.
        """
        instrument = self.instrument(measures=("judge_score", "baseline_score"))
        with self.assertRaises(MeasurementError) as caught:
            instrument.measured("judge_score", JUDGE_SCORE, how="the judge said so")
        message = str(caught.exception)
        self.assertIn("opinion_of: model", message)
        self.assertNotIn("did not declare it", message)

    def test_a_judgement_cannot_be_stamped_again_under_a_name_a_gate_reads(self):
        """Door four, and it is the one that closes the end-to-end defect.

        Filing the judge's 0.967 honestly as `judge_score` and then stamping
        the same 0.967 as `baseline_score` is the whole original defect with one
        extra row written. This is wall 2 pointed inward: a tool may not stamp
        what its caller handed it, and it may not stamp what a model handed it.
        """
        instrument = self.instrument()
        instrument.opinion(
            "judge_score",
            JUDGE_SCORE,
            how="scripted graded its own answers on 30 rows",
        )
        with self.assertRaises(MeasurementError) as caught:
            instrument.measured(
                "baseline_score", JUDGE_SCORE, how="29 of 30 rows correct"
            )
        message = str(caught.exception)
        self.assertIn("judge_score", message)
        self.assertIn("opinion_of: model", message)
        self.assertEqual(
            [row["fact"] for row in evidence.rows_for(self.thread)], ["judge_score"]
        )

    def test_the_refusal_above_comes_from_the_opinion_and_not_from_the_number(self):
        """ISOLATION for door four: the same value, no opinion recorded first.

        Without this, the refusal above could be coming from anything - the
        value, the fact, wall 2 - and the test would still be green. It is the
        RECORD of the judgement that closes the door, and nothing else.
        """
        instrument = self.instrument()
        row = instrument.measured(
            "baseline_score", JUDGE_SCORE, how="29 of 30 rows correct"
        )
        self.assertEqual(row["origin"], MEASURED)

    def test_the_same_call_may_still_stamp_the_rule_graded_number(self):
        """THE POSITIVE CONTROL for the refusal above, in the same instrument.

        Every assertion in this class would pass against an instrument that
        refused everything. This is the one that says the wall lets the honest
        number through: the judge's 0.967 is recorded as an opinion, refused as
        a baseline, and the rule's 0.400 is stamped on the next line.
        """
        instrument = self.instrument()
        instrument.opinion(
            "judge_score", JUDGE_SCORE, how="scripted graded its own answers"
        )
        row = instrument.measured(
            "baseline_score",
            RULE_SCORE,
            how="scripted answered 12 of 30 rows correctly under exact_match",
        )
        self.assertEqual(row["origin"], MEASURED)
        self.assertAlmostEqual(row["value"], RULE_SCORE, places=6)
        self.assertEqual(
            [(r["fact"], r["origin"]) for r in evidence.rows_for(self.thread)],
            [("judge_score", ASSERTED), ("baseline_score", MEASURED)],
        )

    def test_the_open_door_stamps_asserted_whoever_the_actor_is(self):
        """`opinion` does not ask who is speaking, and `supplied` does.

        A person can vouch for their own week; that is why `supplied` from a
        USER is STATED. Nobody can vouch for what a model thought, so a USER
        clicking the button must not upgrade a judge's verdict.
        """
        for actor, expected_for_supplied in ((USER, STATED), (MODEL, ASSERTED)):
            with self.subTest(actor=actor):
                instrument = self.instrument(
                    actor=actor, measures=("baseline_score",)
                )
                self.assertEqual(instrument.supplied_origin, expected_for_supplied)
                row = instrument.opinion(
                    "judge_score", JUDGE_SCORE, how="scripted judged its own answers"
                )
                self.assertEqual(row["origin"], ASSERTED)

    def test_the_two_doors_are_disjoint(self):
        """`opinion` is for opinion facts and for nothing else.

        Two records that can each hold the other's rows are one record with a
        confusing schema. A fact the ledger calls a reading goes through
        `measured` or through `supplied`, whichever is true of it.
        """
        instrument = self.instrument()
        with self.assertRaises(MeasurementError) as caught:
            instrument.opinion("baseline_score", RULE_SCORE, how="a rule graded it")
        self.assertIn("does not declare it one", str(caught.exception))
        self.assertIn("judge_score", str(caught.exception))

    def test_an_opinion_still_has_to_say_whose(self):
        """Invariant 3 applies hardest here: this number is somebody's opinion
        before it is anything else."""
        instrument = self.instrument()
        for value, how in ((JUDGE_SCORE, "   "), (None, "scripted judged")):
            with self.subTest(value=value, how=how):
                with self.assertRaises(MeasurementError):
                    instrument.opinion("judge_score", value, how=how)
        self.assertEqual(evidence.rows_for(self.thread), [])

    def test_resolves_does_not_offer_a_tool_that_could_settle_it(self):
        """A challenge on an opinion is not a question about who ran the tool.

        "No tool measures this yet" would read as a gap in the product and
        invite somebody to close it by writing one.
        """
        route = evidence.resolves("judge_score")
        self.assertIsNone(route["tool"])
        self.assertEqual(route["opinion_of"], "model")
        self.assertIn("a judgement is not a reading", route["note"])


# ---------------------------------------------------------------------------
# 3. SC6. No gate row reads an opinion.


class NoGateReadsAnOpinionTest(unittest.TestCase):
    """The half of the fix that lives in the shape of the ledger.

    The origin rule asks who supplied a fact. This asks whether the fact is the
    kind of thing anybody can supply as a reading, and it is checked the way
    RC10 checks its own: by parsing every `requires` string with the engine's
    condition compiler, never by writing a list down.

    THE DERIVATION IS DONE TWICE, for RC10's reason. `Spec.gate_row_facts` is
    the engine's own answer and is what the engine enforces against; a broken
    `_facts_read_by` returning empty sets would make this loop over nothing and
    pass. So the names are re-derived here from the raw `requires` strings and
    the two answers are asserted equal.
    """

    def setUp(self) -> None:
        self.spec = diagnosis.default_spec()
        self.opinions = set(evidence.opinion_facts())

    def rederived(self) -> dict[tuple[str, str], frozenset[str]]:
        out: dict[tuple[str, str], frozenset[str]] = {}
        for gate_id, gate in self.spec.gates.items():
            for row in gate["passes_when"]:
                tree = compile_condition(row["requires"])
                names = diagnosis._facts_read_by(self.spec, tree)
                out[(gate_id, row["method_class"])] = names
        return out

    def test_the_two_derivations_agree(self):
        self.assertEqual(self.rederived(), dict(self.spec.gate_row_facts))
        self.assertTrue(self.opinions, "no fact is declared an opinion")

    def test_no_passes_when_row_reads_an_opinion_fact(self):
        for key, names in self.rederived().items():
            with self.subTest(gate=key[0], row=key[1]):
                self.assertEqual(
                    names & self.opinions,
                    set(),
                    f"gate row {key} reads a fact the ledger declares an opinion",
                )

    def test_the_facts_the_gates_read_are_all_readings(self):
        """Said from the other side, through the module's own answer."""
        self.assertEqual(set(evidence.gate_facts()) & self.opinions, set())
        for name in evidence.gate_facts():
            with self.subTest(fact=name):
                self.assertFalse(evidence.is_an_opinion(name))

    def test_g1_still_reads_the_three_facts_it_always_read(self):
        """NON-VACUITY. A gate that read nothing would satisfy the check above."""
        self.assertEqual(
            self.spec.gate_row_facts[("G1_BASELINE_MEASURED", "any")],
            frozenset({"baseline_measured", "baseline_score", "trivial_baseline_score"}),
        )


# ---------------------------------------------------------------------------
# 4. The property, proved by trying.


class AGateMayNotOpenOnAModelsOpinionTest(unittest.TestCase):
    """Try it. A judge's number in the ledger must not decide anything.

    Two directions, because the flattering one is not the only one. A judge that
    inflates says "ship it" about a system that gets four rows in ten right; a
    judge that deflates opens G1 on an opinion and routes toward training with
    all five gates green. Both are asserted.
    """

    def setUp(self) -> None:
        support.sandbox(self)
        self.spec = diagnosis.default_spec()

    def test_a_self_graded_ninety_seven_against_a_target_of_ninety_decides_nothing(self):
        """The brief's own case, and the one the bench actually produced."""
        facts = fixtures.attribute(
            {
                "modality": "text",
                "task_family": "generation",
                "eval_size_n": ROWS,
                "target_score": 0.90,
                "privacy": "public_ok",
                "needs_citations": False,
                "baseline_measured": True,
                "trivial_baseline_score": 0.20,
                "data_quality": 0.9,
            }
        )
        facts["baseline_score"] = Fact(JUDGE_SCORE, ASSERTED)

        result = diagnosis.diagnose(facts)
        self.assertNotEqual(result.verdict, "TRAIN")
        self.assertEqual(result.outcome, "ACTION__SUBSTANTIATE_CLAIMED_FACTS")
        self.assertEqual(
            result.gate_ledger["G1_BASELINE_MEASURED"]["status"], "FAILED"
        )
        self.assertEqual(
            [row["fact"] for row in result.unsubstantiated], ["baseline_score"]
        )
        # And it is not the product refusing to speak: it names the fact, its
        # declared source, and what would settle it.
        self.assertEqual(result.unsubstantiated[0]["declared_source"], "inspect")
        self.assertTrue(result.unsubstantiated[0]["substantiation"].strip())

    def test_a_self_graded_shortfall_does_not_mint_a_training_verdict(self):
        """The other direction. Everything else is a real TRAIN fixture.

        One fact changes origin, no value moves, and the five gates that were
        green go to four.
        """
        control = dict(fixtures.MINTING["TRAIN__LORA_SFT"])
        minted = diagnosis.diagnose(control)
        self.assertEqual(minted.verdict, "TRAIN")
        self.assertEqual(minted.outcome, "TRAIN__LORA_SFT")

        judged = dict(control)
        judged["baseline_score"] = Fact(bare(control["baseline_score"]), ASSERTED)
        result = diagnosis.diagnose(judged)
        self.assertNotEqual(result.verdict, "TRAIN")
        self.assertFalse(result.outcome.startswith("TRAIN__"))
        self.assertEqual(
            result.gate_ledger["G1_BASELINE_MEASURED"]["status"], "FAILED"
        )

    def test_the_measured_baseline_still_mints(self):
        """THE POSITIVE CONTROL FOR THE WHOLE FILE, and it is not decoration.

        Every assertion above would hold against an engine that had stopped
        being able to say TRAIN at all. All nine training outcomes are still
        reachable on rule-graded facts, which is what makes the refusals above
        mean something.
        """
        minted = []
        for outcome, facts in sorted(fixtures.MINTING.items()):
            with self.subTest(outcome=outcome):
                result = diagnosis.diagnose(dict(facts))
                self.assertEqual(result.verdict, "TRAIN", result.outcome)
                self.assertEqual(result.outcome, outcome)
                minted.append(outcome)
        self.assertEqual(len(minted), 9, minted)


# ---------------------------------------------------------------------------
# 5. The opposite failure. The judge is not refused.


class TheJudgeIsStillUsefulTest(BenchTest):
    """A bench that refuses a model grader is worse than one that labels it.

    Some tasks genuinely cannot be graded by a rule - that is why
    `metric_is_programmatic` is a fact this tree routes on - and every refusal
    in this file would pass against a bench that had simply stopped working. So
    this class is the check that it has not.
    """

    def test_a_model_graded_run_still_runs_and_still_reports(self):
        report = self.run_eval()
        self.assertTrue(report["ok"])
        self.assertTrue(report["complete"])
        self.assertEqual(report["graded"], ROWS)
        self.assertEqual(self.model.judged, ROWS)
        self.assertTrue(report["summary"])
        # And it LABELS rather than hides: the warning names the judge, says it
        # graded its own answers, and points at the rule scores beside it.
        warning = report["self_graded"]["warning"]
        self.assertIn("graded its own answers", warning)
        self.assertIn("exact-match", warning)

    def test_an_opinion_reaches_the_engine_and_is_carried(self):
        """Recorded, visible, handed to the engine - and ASSERTED."""
        instrument = self.instrument()
        instrument.opinion(
            "judge_score",
            JUDGE_SCORE,
            how="scripted, a model, judging its own answers on 30 rows",
        )
        seen = [row for row in evidence.ledger_view(self.thread)]
        self.assertEqual([row["fact"] for row in seen], ["judge_score"])
        self.assertIn("judging its own answers", seen[0]["how"])

        facts, trail = evidence.assemble_facts(self.thread)
        self.assertEqual(facts["judge_score"].origin, ASSERTED)
        self.assertAlmostEqual(bare(facts["judge_score"]), JUDGE_SCORE, places=6)
        self.assertIn(
            "judge_score", [row["fact"] for row in trail]
        )

    def test_the_engine_accepts_a_run_that_carries_one(self):
        """It is a declared fact, so it does not blow up the fact sheet - and
        it changes no answer, because no node and no gate reads it."""
        control = dict(fixtures.MINTING["TRAIN__LORA_SFT"])
        with_opinion = dict(control)
        with_opinion["judge_score"] = Fact(JUDGE_SCORE, ASSERTED)
        self.assertEqual(
            diagnosis.diagnose(with_opinion).outcome,
            diagnosis.diagnose(control).outcome,
        )

    def test_a_different_model_as_judge_is_the_same_fact(self):
        """DECIDED, not overlooked, and the reason is that we cannot check it.

        A judge that did not write the answers lacks the specific bias a
        self-grader has, and the harness says which case it is, in words, beside
        the number. It does not get a different ADMISSIBILITY: "a different
        model" is `judge_model != model`, a comparison of two names the user
        chose, and the same weights behind a second connection with a second
        name would pass it. A wall built on a string the user controls is not a
        wall, and a tier that can be stepped over by renaming a connection
        teaches the reader that the tier meant something.
        """
        other = provider_store.create(
            "Second", "http://127.0.0.1:11434", "another-model", "ollama"
        )
        report = self.run_eval(judge_provider_id=other["id"])
        self.assertTrue(report["ok"], report.get("detail"))
        block = report["self_graded"]
        # The distinction IS carried, in what the harness reports.
        self.assertFalse(block["is_the_model_that_answered"])
        self.assertEqual(block["judge_model"], "another-model")
        self.assertIn("another model's answers", block["warning"])

        # And it is not carried into the ledger's vocabulary: the same fact,
        # the same origin, the same refusal.
        instrument = self.instrument()
        row = instrument.opinion(
            "judge_score", JUDGE_SCORE, how="another-model graded scripted's answers"
        )
        self.assertEqual(row["origin"], ASSERTED)
        with self.assertRaises(MeasurementError):
            instrument.measured("judge_score", JUDGE_SCORE, how="a second model said so")


# ---------------------------------------------------------------------------
# 6. The mutation check.


class TheWallIsNotVacuousTest(BenchTest):
    """Remove `opinion_of: model` from the ledger. The refusals must stop.

    The mutation is applied to the FILE, not to the code, because the file is
    where the rule is written. `SC6_NO_GATE_READS_AN_OPINION` asks for exactly
    this and says why: a wall whose test passes with the wall removed is testing
    nothing, and this repository has been bitten by that twice.
    """

    def holed_spec(self) -> diagnosis.Spec:
        text = Path("docs/diagnosis_engine.yaml").read_text(encoding="utf-8")
        holed = text.replace(", opinion_of: model}", "}")
        self.assertNotEqual(holed, text, "the declaration was not found to remove")
        path = Path(self.root) / "holed_engine.yaml"
        path.write_text(holed, encoding="utf-8")
        return diagnosis.load_spec(path)

    def without_the_declaration(self) -> diagnosis.Spec:
        spec = self.holed_spec()
        self.assertEqual(spec.facts["judge_score"].get("opinion_of"), None)
        original = evidence.spec
        # `evidence.spec` now takes the ledger this question is about, and
        # answers the default when handed None. The mutation is unchanged - every
        # reader in the module sees a ledger with the `opinion_of` declaration
        # removed - and the stand-in accepts the argument so that the readers
        # that DO pass one are mutated too, which is the stricter reading.
        evidence.spec = lambda ledger=None: spec
        self.addCleanup(lambda: setattr(evidence, "spec", original))
        return spec

    def test_without_the_declaration_the_fact_is_measurable_again(self):
        self.without_the_declaration()
        self.assertEqual(evidence.opinion_facts(), ())
        self.assertFalse(evidence.is_an_opinion("judge_score"))
        self.assertTrue(evidence.may_be_declared_measurable("judge_score"))

    def test_without_the_declaration_the_table_writes_the_measured_row(self):
        """The refusal in `record` was the declaration and nothing else."""
        self.without_the_declaration()
        instrument = self.instrument(measures=("judge_score",))
        row = instrument.measured(
            "judge_score", JUDGE_SCORE, how="the judge said so"
        )
        self.assertEqual(row["origin"], MEASURED)

    def test_without_the_declaration_the_rename_goes_through(self):
        """And so does the whole original defect, which is the point."""
        self.without_the_declaration()
        instrument = self.instrument()
        with self.assertRaises(MeasurementError):
            # `opinion` is now refused, because the fact is no longer one.
            instrument.opinion("judge_score", JUDGE_SCORE, how="the judge said so")
        row = instrument.measured(
            "baseline_score", JUDGE_SCORE, how="29 of 30 rows, graded by a model"
        )
        self.assertEqual(row["origin"], MEASURED)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
