"""An eval set is carved out of answers that were already there, or it is refused.

`docs/diagnosis_engine.yaml` states G0's recipe: *"30-50 real inputs sampled from
actual traffic, GRADED BY THE PERSON WHO CARES ABOUT THE ANSWER."*

**SPLITTING IS MECHANICAL. GRADING IS JUDGEMENT.** That sentence is the whole of
this file. A held-out slice of unlabelled rows is a pile of inputs with no right
answers; handing one over as an eval set would open the first of the five gates
on a file this harness wrote itself, which is the worst thing this build could do
and the one thing no amount of prose in a docstring prevents. So the line is
drawn in code and this is where it either holds or the suite goes red.

`app/tools/datawork.py` draws the same line inside the tool. This file is about
the PROPOSER: which of two builds a person gets, decided by reading their file,
and what the refusal says when neither is honest.

What is checked here, and why none of it is a formality:

1. **The line itself, from both sides.** A dataset whose answers are really
   there gets a build. A dataset whose answers are not - no column named, a
   column that is not in the file, a column that is there and empty - gets the
   refusal that was always here, and it is checked that the refusal still says
   grading is the person's. The blank-answer case is the one a reader assumes
   works: `dataquality.is_null` treats absent, empty and whitespace-only alike,
   so a file full of `"   "` answers is ungraded data and must be refused as such.
2. **The half that was true is untouched.** Somebody who HAS an eval file gets
   exactly the build they got before - attach, count, re-check - and somebody
   whose eval file is counted and short, with no graded dataset anywhere, gets
   the same refusal sentence they got before. A fix that quietly changed either
   would be this task's real failure mode.
3. **THE WHOLE PLAN RUNS, against the real tools, on a real file.** Four steps,
   `Step.bind` resolving the reference the carve reported, `ExitCriterion.met`
   deciding each one, ending with `eval_size_n` MEASURED in the ledger. No key
   and no network: every tool in this build reads the filesystem.
4. **A leaking split is a failed step.** This was driven with a file whose rows
   are near-duplicates of each other, and that file no longer leaks: the draw is
   now made in the same units the leak check judges it in, so a carve cannot
   produce this leak by construction. Both halves are asserted - the fixture
   that used to leak comes back clean, AND the `ok: false` path is still driven,
   on the one way the two can still disagree, which is a similarity search that
   was narrowed. A build that counted a leaking eval set and handed it to G0
   would be this whole task's worst outcome reached by accident, so the path
   that catches it does not get deleted along with the defect.
5. **The size comes from the gate, and from one derivation of it.** The plan
   does not pass `rows`: the tool reads G0's threshold itself. What the plan is
   held to is the COUNT, and that is checked by MOVING the threshold rather than
   by comparing 30 to 30.
6. **Nothing lands on top of anything.** The destination is derived from the
   dataset rather than the clock, it must not exist, and proposing writes
   nothing at all.
7. **The cross-lane contract.** `carve_eval_set` belongs to a sibling lane, and
   the name this file first pinned - `split_dataset`, from `docs/ROADMAP.md` -
   was wrong, as was every argument name it guessed. That disagreement surfaced
   as a REFUSAL at proposal time rather than as a step failing after somebody
   approved it, and the tests below drive that path with stand-in schemas so it
   keeps working the next time the two lanes disagree.
"""

from __future__ import annotations

import json
import random
import re
import unittest
from pathlib import Path
from unittest import mock

from app import dataquality, diagnosis
from app.tools import REGISTRY, evidence, propose
from app.tools import registry as registry_module
from app.tools.registry import Control, Registry, ToolSpec

import support


THE_TOOL = propose.THE_CARVE

REPO = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Scaffolding.


def a_registry(*, without: str = "", plus: ToolSpec | None = None) -> Registry:
    """The live registry with one tool removed, or one added, or both.

    `Registry` has no `remove`, on purpose - nothing in the product may
    unregister a tool at runtime - so the mutation is a different registry built
    from the same declarations.
    """
    other = Registry()
    for live in REGISTRY:
        if live.name != without:
            other.add(live)
    if plus is not None:
        other.add(plus)
    return other


def instead(other: Registry):
    """Bind BOTH names the registry is reached under to `other`.

    `app/tools/propose.py` binds `REGISTRY` at import; `app/build.py` imports it
    late, inside `validate`. Patching one and not the other gives a proposer that
    can see a tool and a validator that cannot, which is a state that exists
    nowhere in the product.
    """
    return mock.patch.object(propose, "REGISTRY", other), mock.patch.object(
        registry_module, "REGISTRY", other
    )


#: Arguments whose TYPE the plan depends on. A stand-in that types a row count as
#: a string fails validation for a reason with nothing to do with the
#: disagreement under test.
_NUMBERS = ("rows", "max_rows")


def a_stand_in(*names: str, required=()) -> ToolSpec:
    """A carving tool declaring exactly these arguments and nothing else.

    Everything this plan assumes about the sibling's tool is a question asked of
    its schema at proposal time, so a different schema is the whole of the
    difference between agreement and disagreement.
    """
    return ToolSpec(
        name=THE_TOOL,
        description="A stand-in for a carving tool that names things differently.",
        schema={
            "type": "object",
            "properties": {
                name: {"type": "integer" if name in _NUMBERS else "string"}
                for name in names
            },
            "required": list(required),
        },
        reads=("filesystem", "datasets"),
        writes=("filesystem", "datasets"),
        approval="always",
        provides=("data.eval_set.carve",),
        control=Control(
            label="Carve an eval set", group="Data", verb="carve", order=20
        ),
        handler=lambda **kwargs: {"ok": True},
    )


class CarveTestCase(unittest.TestCase):
    """Its own database, its own temp tree. Nothing here touches the checkout."""

    def setUp(self):
        self.root = support.sandbox(self)

    # -- files ------------------------------------------------------------

    #: A vocabulary wide enough that two rows drawn from it are not near
    #: neighbours. `carve_eval_set` runs a real near-duplicate check over what it
    #: writes, so a fixture of "ticket 1", "ticket 11", "ticket 111" is a fixture
    #: whose every row leaks - as the first version of this file discovered, with
    #: 30 of 30 eval rows found in the training half. That is the tool being
    #: right about the data, and it is driven on purpose in
    #: `ALeakingSplitIsAFailedStepTest` rather than tripped over here.
    WORDS = (
        "refund invoice delivery password upgrade cancel account shipping label "
        "return exchange warranty coupon discount receipt tracking courier parcel "
        "damaged missing duplicate charge subscription renewal downgrade transfer "
        "verify reset unlock suspend reopen escalate supervisor callback voucher "
        "credit debit statement threshold overdue reminder dispatch collection"
    ).split()

    def graded(self, rows: int = 400, name: str = "tickets.jsonl", answer=None) -> Path:
        """A dataset with answers in it and no two rows near-alike."""
        classes = ("billing", "shipping", "refund", "account")
        draw = random.Random(20260821)
        path = self.root / name
        path.write_text(
            "\n".join(
                json.dumps(
                    {
                        "text": " ".join(draw.sample(self.WORDS, 12)),
                        "answer": classes[i % 4] if answer is None else answer,
                    }
                )
                for i in range(rows)
            ),
            encoding="utf-8",
        )
        return path

    def ungraded(self, rows: int = 400, name: str = "raw.jsonl") -> Path:
        path = self.root / name
        path.write_text(
            "\n".join(json.dumps({"text": f"ticket {i}"}) for i in range(rows)),
            encoding="utf-8",
        )
        return path

    def eval_file(self, rows: int = 40, name: str = "eval.jsonl") -> Path:
        path = self.root / name
        path.write_text(
            "\n".join(
                json.dumps({"q": f"question {i}", "a": "yes"}) for i in range(rows)
            ),
            encoding="utf-8",
        )
        return path

    # -- situations -------------------------------------------------------

    def blocked(self, thread_id: int = 1, **paths) -> propose.Situation:
        """A real `BLOCKED__BUILD_EVAL_SET`, decided by the engine."""
        sheet, trail = evidence.assemble_facts(
            thread_id,
            {"goal_text": "route tickets", "modality": "text", "target_score": 0.9},
            evidence.USER,
        )
        result = diagnosis.diagnose(sheet)
        self.assertEqual(result.outcome, "BLOCKED__BUILD_EVAL_SET")
        return propose.Situation(
            outcome=result.outcome,
            result=result,
            values={row["fact"]: row["value"] for row in trail},
            origins={row["fact"]: row["origin"] for row in trail},
            hows={row["fact"]: row.get("how") or "" for row in trail},
            **paths,
        )

    def counted(self, path: Path, thread_id: int = 1) -> None:
        """Make `eval_size_n` genuinely MEASURED by counting a real file."""
        support.a_conversation(thread_id)
        result = REGISTRY.call(
            "measure_eval_set",
            {"path": str(path), "finish_the_count": True},
            actor=evidence.USER,
            thread_id=thread_id,
        )
        self.assertTrue(result.get("exact"), result)

    def refusal(self, situation) -> propose.NotEnoughToPropose:
        with self.assertRaises(propose.NotEnoughToPropose) as caught:
            propose.propose(situation)
        return caught.exception


# ---------------------------------------------------------------------------
# 1. The line.


class TheLineBetweenSplittingAndGradingTest(CarveTestCase):
    """Answers already in the file, or no build. Both directions, driven."""

    def test_a_dataset_that_already_carries_the_answers_gets_a_carve(self):
        plan = propose.propose(
            self.blocked(dataset_path=str(self.graded()), expected_field="answer")
        )
        self.assertEqual(plan.id, "carve_the_eval_set")
        self.assertEqual([step.tool for step in plan.steps][0], THE_TOOL)

    def test_a_dataset_with_no_answers_in_it_is_refused_and_grading_stays_yours(self):
        gap = self.refusal(
            self.blocked(dataset_path=str(self.ungraded()), expected_field="answer")
        )
        self.assertIn("no column called 'answer'", gap.detail)
        self.assertIn("writing them is yours", gap.detail)
        self.assertIn("graded by the person who cares about the answer", gap.detail)

    def test_the_harness_will_not_pick_the_column_that_defines_correct(self):
        """No `expected_field`, and no fallback picks a conventional name.

        The opposite of `_the_question_and_the_right_passage`, where letting the
        tool pick is right because it is naming a DOCUMENT. Here the column IS
        the definition of a right answer, and choosing it for somebody is the one
        judgement `docs/VISION.md` says this product never makes.
        """
        dataset = self.graded()
        gap = self.refusal(self.blocked(dataset_path=str(dataset)))
        self.assertEqual(gap.needs, ("expected_field",))
        self.assertIn("will not pick the column for you", gap.detail)
        # A conventional name was RIGHT THERE and was not taken.
        first = json.loads(dataset.read_text(encoding="utf-8").splitlines()[0])
        self.assertIn("answer", first)

    def test_blank_answers_are_ungraded_rows_and_are_counted_as_such(self):
        """A column full of whitespace is a column, and it is not a grade.

        `dataquality.is_null` treats absent, empty and whitespace-only alike,
        which are the three shapes an ungraded row actually arrives in, and the
        refusal has to carry the real count.
        """
        gap = self.refusal(
            self.blocked(
                dataset_path=str(self.graded(rows=400, answer="   ")),
                expected_field="answer",
            )
        )
        self.assertIn("0 of the 400 rows read", gap.detail)
        self.assertEqual(gap.needs, ("more graded examples",))

    def test_one_more_graded_row_is_the_difference_between_refusal_and_a_build(self):
        """The boundary, driven from both sides. The mutation check on the
        comparison itself: `<` and `<=` cannot both pass here."""
        minimum = propose.g0_minimum()
        for graded, expect_build in ((minimum - 1, False), (minimum, True)):
            path = self.root / f"boundary_{graded}.jsonl"
            draw = random.Random(graded)
            rows = [
                {"text": " ".join(draw.sample(self.WORDS, 12)), "answer": "yes"}
                for _ in range(graded)
            ]
            rows += [
                {"text": " ".join(draw.sample(self.WORDS, 12)), "answer": ""}
                for _ in range(400)
            ]
            path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
            situation = self.blocked(dataset_path=str(path), expected_field="answer")
            with self.subTest(graded=graded):
                if expect_build:
                    self.assertEqual(propose.propose(situation).id, "carve_the_eval_set")
                else:
                    gap = self.refusal(situation)
                    self.assertIn(f"G0 asks for {minimum}", gap.detail)

    def test_the_reader_stops_at_the_gates_question_and_no_further(self):
        found = propose.the_answers_are_already_in_the_data(
            str(self.graded(rows=5000)), "answer", at_least=propose.g0_minimum()
        )
        self.assertEqual(found.rows_read, propose.g0_minimum())
        self.assertEqual(found.rows_with_an_answer, propose.g0_minimum())
        self.assertIn("which is the question", found.stopped_because)

    def test_a_folder_of_documents_has_no_answer_column_and_is_told_so(self):
        folder = self.root / "docs"
        folder.mkdir()
        for index in range(5):
            (folder / f"note_{index}.txt").write_text(
                f"a note about something {index}", encoding="utf-8"
            )
        gap = self.refusal(
            self.blocked(dataset_path=str(folder), expected_field="answer")
        )
        self.assertIn("no column called 'answer'", gap.detail)
        self.assertIn("writing them is yours", gap.detail)


# ---------------------------------------------------------------------------
# 2. The half that was already true.


class TheRefusalThatWasTrueIsUntouchedTest(CarveTestCase):
    def test_somebody_with_an_eval_file_gets_the_build_they_always_got(self):
        """Even with a labelled dataset beside it: an uncounted eval file is
        counted, because counting is cheap and might open the gate outright."""
        plan = propose.propose(
            self.blocked(
                eval_path=str(self.eval_file()),
                dataset_path=str(self.graded()),
                expected_field="answer",
            )
        )
        self.assertEqual(plan.id, "build_the_eval_set")
        self.assertEqual(
            [step.tool for step in plan.steps],
            ["attach_context", "measure_eval_set", "run_diagnosis"],
        )

    def test_a_counted_short_eval_set_with_no_graded_data_refuses_as_before(self):
        evaluation = self.eval_file(rows=12)
        self.counted(evaluation)
        gap = self.refusal(self.blocked(eval_path=str(evaluation)))
        self.assertIn("has already been counted: 12", gap.detail)
        self.assertIn("Counting it again would change nothing", gap.detail)
        self.assertIn("writing them is yours", gap.detail)
        self.assertEqual(gap.needs, ("more graded examples",))

    def test_a_counted_short_eval_set_beside_graded_data_is_offered_the_carve(self):
        """The same half-truth through the other door. Twelve counted rows do not
        make "write more yourself" true when a labelled dataset is right there."""
        evaluation = self.eval_file(rows=12)
        self.counted(evaluation)
        plan = propose.propose(
            self.blocked(
                eval_path=str(evaluation),
                dataset_path=str(self.graded()),
                expected_field="answer",
            )
        )
        self.assertEqual(plan.id, "carve_the_eval_set")

    def test_no_eval_path_and_no_dataset_still_asks_where_the_file_is(self):
        gap = self.refusal(self.blocked())
        self.assertIn("cannot plan this without eval_path", gap.detail)


# ---------------------------------------------------------------------------
# 3. The whole plan, run.


class ThePlanRunsAndTheGateOpensOnACountTest(CarveTestCase):
    """Every step, against the real registry, on a real file. No key needed:
    every tool in this build reads the filesystem and nothing else."""

    def setUp(self):
        super().setUp()
        support.a_conversation(1)
        self.dataset = self.graded()
        self.plan = propose.propose(
            self.blocked(dataset_path=str(self.dataset), expected_field="answer")
        )

    def run_it(self):
        produced, payloads, verdicts = {}, {}, {}
        for step in self.plan.steps:
            arguments = step.bind(produced) if step.refs() else dict(step.arguments)
            result = REGISTRY.call(
                step.tool, arguments, approved=True, actor=evidence.USER, thread_id=1
            )
            payloads[step.id] = result
            verdicts[step.id] = step.exit_criterion.met(result)
            if not verdicts[step.id].ok:
                break
            produced[step.id] = step.harvest(result)
        return payloads, verdicts

    def test_the_four_steps_run_and_every_exit_criterion_is_met(self):
        _, verdicts = self.run_it()
        self.assertEqual(
            [step.id for step in self.plan.steps],
            ["carve", "attach", "count", "recheck"],
        )
        self.assertEqual(len(verdicts), 4)
        for step_id, verdict in verdicts.items():
            self.assertTrue(verdict.ok, f"{step_id}: {verdict.because}")

    def test_the_carve_wrote_two_new_files_and_left_the_source_alone(self):
        before = self.dataset.read_bytes()
        payloads, _ = self.run_it()
        carve = payloads["carve"]
        self.assertEqual(self.dataset.read_bytes(), before)
        self.assertTrue(Path(carve["eval_path"]).is_file())
        self.assertTrue(Path(carve["train_path"]).is_file())
        self.assertEqual(carve["eval_rows"] + carve["train_rows"], carve["rows_read"])
        self.assertEqual(Path(carve["eval_path"]).parent, Path(carve["into"]))

    def test_the_gate_opens_on_a_count_and_not_on_the_carves_own_arithmetic(self):
        payloads, _ = self.run_it()
        carve, counted = payloads["carve"], payloads["count"]
        self.assertEqual(carve["measured"], [])
        self.assertIn("did not count one", carve["does_not_open_g0"])
        self.assertEqual(counted["rows"], carve["eval_rows"])
        self.assertEqual(
            payloads["recheck"]["fact_origins"]["eval_size_n"], diagnosis.MEASURED
        )

    def test_the_reference_the_plan_follows_is_the_path_the_carve_reported(self):
        """Not a path this plan predicted. The tool names the files it writes."""
        payloads, _ = self.run_it()
        attach = next(step for step in self.plan.steps if step.id == "attach")
        self.assertEqual(attach.arguments["path"].step, "carve")
        self.assertEqual(attach.arguments["path"].output, "eval_path")
        self.assertEqual(
            payloads["attach"]["what_it_is"]["path"], payloads["carve"]["eval_path"]
        )

    def test_the_plan_does_not_pass_a_row_count_so_there_is_one_derivation(self):
        carve = next(step for step in self.plan.steps if step.tool == THE_TOOL)
        self.assertNotIn("rows", carve.arguments)
        payloads, _ = self.run_it()
        self.assertEqual(
            payloads["carve"]["method"]["rows_asked_for_came_from"],
            payloads["carve"]["floor"]["declared_in"],
        )

    def test_the_carve_says_grading_is_still_the_persons(self):
        payloads, _ = self.run_it()
        self.assertIn(
            "graded by the person who cares about the answer",
            payloads["carve"]["grading_is_still_yours"],
        )


class ALeakingSplitIsAFailedStepTest(CarveTestCase):
    """The guarantee that makes carving safe, driven on data that breaks it.

    `carve_eval_set` runs the real leak check over the two files it wrote. This
    build does not run a second one; it is HELD TO that answer. So the thing to
    prove is that a split which leaks fails its step - because a build that
    counted a leaking eval set and handed it to G0 is this task's worst outcome
    reached by accident rather than on purpose.

    THIS TEST USED TO PRODUCE A REAL LEAK AND NOW CANNOT, and the reason is the
    point rather than an inconvenience. The draw was made by EXACT row signature
    and verified with a STRICTLY STRONGER predicate - near duplicates over
    Jaccard 0.8 - so on a file of near-identical tickets it leaked reliably, and
    this test relied on that. It was reliable in the other direction too: on a
    161-row dataset built from this repository's own git log the tool came back
    leaking on 12 of 25 seeds, and on a 160-row fixture with no exact duplicates
    at all it leaked all 30 eval rows on 25 seeds out of 25. Drawing in the units
    the check judges by, the same 161-row file gives 0 leaks over the same 25. The draw now keeps whole groups of the same question
    together under the SAME definition the check uses, so this fixture comes back
    clean - measured below, because "it no longer leaks" is a claim.

    The reporting path is still exercised, on the one way the two can now
    disagree: a clustering pass whose search was NARROWED. That is not a
    contrived failure - `near_duplicate_clusters` reports `exhaustive: false`
    exactly when it happens, on a file bigger than the index can hold - and
    forcing it is the honest way to keep the `ok: false` path under test rather
    than deleting the test along with the defect.
    """

    def setUp(self):
        super().setUp()
        support.a_conversation(1)

    #: Near-duplicate TEXT - only the number differs - and four answers, so the
    #: tool's one-value refusal does not fire before its leak check.
    CLASSES = ("billing", "shipping", "refund", "account")

    def repetitive(self):
        path = self.root / "repetitive.jsonl"
        path.write_text(
            "\n".join(
                json.dumps(
                    {
                        "text": f"ticket number {i} about something",
                        "answer": self.CLASSES[i % 4],
                    }
                )
                for i in range(400)
            ),
            encoding="utf-8",
        )
        return path

    def carve_step(self, path):
        plan = propose.propose(
            self.blocked(dataset_path=str(path), expected_field="answer")
        )
        return next(step for step in plan.steps if step.tool == THE_TOOL)

    def test_the_fixture_that_used_to_leak_no_longer_does(self):
        """The regression pin. Same 400 near-identical tickets, same call."""
        carve = self.carve_step(self.repetitive())
        result = REGISTRY.call(
            THE_TOOL, dict(carve.arguments), approved=True,
            actor=evidence.USER, thread_id=1,
        )
        self.assertEqual((result.get("leakage") or {}).get("leaked_rows"), 0,
                         result["summary"])
        self.assertTrue(result["ok"], result["summary"])
        self.assertTrue(carve.exit_criterion.met(result).ok)
        # And the count the gate reads is the count of QUESTIONS, which is what
        # keeps 400 rephrasings of one ticket from clearing a threshold that
        # asks for thirty inputs.
        self.assertEqual(result["eval_distinct_questions"], result["rows_asked_for"])

    def test_a_carve_that_leaks_fails_its_criterion(self):
        """The surviving disagreement: the clustering saw less than the check did.

        `near_duplicate_clusters` is replaced with one that finds no pairs, which
        is what a fully saturated index degrades to and what the tool reports as
        `exhaustive: false`. The draw is then exactly the pre-fix draw, the check
        is unchanged, and the two disagree - which is the case the `ok: false`
        path exists for.
        """
        path = self.repetitive()
        carve = self.carve_step(path)

        def blind(texts, *, threshold=dataquality.JACCARD_THRESHOLD):
            return {key: key for key in texts}, {
                "keys": len(texts), "clusters": len(texts), "pairs_found": 0,
                "largest_cluster": 1, "threshold": threshold,
                "threshold_is": "our policy, not a property of the data",
                "method": "none - the search was fully narrowed",
                "exhaustive": False, "narrowed_by": ["saturated_shingles"],
                "provenance": dataquality.INFERRED,
            }

        original = dataquality.near_duplicate_clusters
        dataquality.near_duplicate_clusters = blind
        try:
            result = REGISTRY.call(
                THE_TOOL, dict(carve.arguments), approved=True,
                actor=evidence.USER, thread_id=1,
            )
        finally:
            dataquality.near_duplicate_clusters = original

        self.assertTrue(
            (result.get("leakage") or {}).get("leaked_rows"), result["summary"]
        )
        self.assertFalse(result["ok"])
        self.assertFalse(carve.exit_criterion.met(result).ok)
        self.assertIn("leak check", carve.exit_criterion.stated)
        # And the message says which of the two it is, because the old one told
        # the user to "remove the overlapping rows and re-split" - a remedy no
        # tool in this product implements.
        self.assertIn("disagreeing with itself", result["summary"])
        self.assertIn("exhaustive=False", result["summary"])

    def test_every_later_step_hangs_off_the_carve_so_one_failure_stops_them_all(self):
        """`app/storm.py` cancels a step whose `needs` contains a failed one, so
        the chain is what makes a failed carve stop the count."""
        plan = propose.propose(
            self.blocked(dataset_path=str(self.graded()), expected_field="answer")
        )
        self.assertEqual(
            {step.id: step.needs for step in plan.steps},
            {
                "carve": (),
                "attach": ("carve",),
                "count": ("attach",),
                "recheck": ("count",),
            },
        )


# ---------------------------------------------------------------------------
# 4. The size, and where it comes from.


class TheSizeComesFromTheGateTest(CarveTestCase):
    def test_what_the_count_is_held_to_follows_the_threshold(self):
        """Moved, not compared. A hardcoded 30 survives
        `assertEqual(value, g0_minimum())`; it does not survive this."""
        situation = self.blocked(
            dataset_path=str(self.graded()), expected_field="answer"
        )
        seen = {}
        for threshold in (propose.g0_minimum(), 47):
            # The stand-in takes the ledger `g0_minimum` now takes - the floor
            # is a thing one domain's gates state - and answers this threshold
            # whichever ledger is asked. Moving the number is still the whole
            # mutation; the signature is the only thing that changed.
            with mock.patch.object(
                propose, "g0_minimum", lambda spec=None, value=threshold: value
            ):
                plan = propose.propose(situation)
            count = next(step for step in plan.steps if step.tool == "measure_eval_set")
            seen[threshold] = count.exit_criterion.value
        self.assertEqual(seen[47], 47)
        self.assertEqual(seen[propose.g0_minimum()], propose.g0_minimum())

    def test_the_threshold_is_read_off_the_engine_and_not_typed_here(self):
        # FOUND BY THE FACT, NOT BY THE GATE ID, which is how the product now
        # finds it. Naming `G0_EVAL_SET` here would assert the coupling this
        # test is meant to guard against, and it would go on passing on a ledger
        # where the floor had moved to a differently-named gate.
        reading = diagnosis.default_spec().gate_reading(propose.THE_EVAL_SIZE_FACT)
        self.assertIsNotNone(reading)
        self.assertIn(
            f"{propose.THE_EVAL_SIZE_FACT} >= {propose.g0_minimum()}",
            str(reading.row["requires"]),
        )


# ---------------------------------------------------------------------------
# 5. Nothing lands on top of anything.


class NothingIsOverwrittenAndNothingIsWrittenYetTest(CarveTestCase):
    def test_the_destination_is_derived_from_the_dataset_and_does_not_exist(self):
        dataset = self.graded()
        into = propose.where_the_carve_would_land(str(dataset))
        self.assertEqual(into.parent, dataset.parent.resolve())
        self.assertTrue(into.name.startswith(dataset.stem))
        self.assertFalse(into.exists())

    def test_a_destination_that_already_exists_stops_the_plan(self):
        dataset = self.graded()
        propose.where_the_carve_would_land(str(dataset)).mkdir()
        gap = self.refusal(
            self.blocked(dataset_path=str(dataset), expected_field="answer")
        )
        self.assertIn("There is already something at", gap.detail)
        self.assertIn("cannot be undone", gap.detail)

    def test_proposing_writes_nothing_at_all(self):
        dataset = self.graded()
        before = sorted(path.name for path in self.root.iterdir())
        plan = propose.propose(
            self.blocked(dataset_path=str(dataset), expected_field="answer")
        )
        self.assertFalse(propose.where_the_carve_would_land(str(dataset)).exists())
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), before)
        self.assertTrue(plan.id)

    def test_the_same_call_names_the_same_place_and_the_same_plan(self):
        """`tests/test_a_plan_keeps_its_identity.py` says the clock is not part
        of a plan's identity, and a destination stamped with the time would make
        every re-proposal a different plan."""
        situation = self.blocked(
            dataset_path=str(self.graded()), expected_field="answer"
        )
        first = propose.propose(situation)
        second = propose.propose(situation)
        self.assertEqual(first.fingerprint(), second.fingerprint())
        self.assertEqual(
            [step.arguments for step in first.steps],
            [step.arguments for step in second.steps],
        )

    def test_the_sandbox_snapshots_the_dataset_and_reaches_nothing(self):
        dataset = self.graded()
        plan = propose.propose(
            self.blocked(dataset_path=str(dataset), expected_field="answer")
        )
        self.assertFalse(plan.environment.egress)
        self.assertEqual(
            [snapshot.path for snapshot in plan.environment.data], [str(dataset)]
        )


# ---------------------------------------------------------------------------
# 6. The cross-lane contract.


class WhenTheCarvingToolIsNotHereTest(CarveTestCase):
    """Driven with a registry the tool was taken out of, which is the state this
    lane was written in: the proposer was finished before the tool landed."""

    def test_the_refusal_names_the_missing_tool_and_blames_the_harness(self):
        one, two = instead(a_registry(without=THE_TOOL))
        with one, two:
            self.assertEqual(propose.carving_tools_missing(), (THE_TOOL,))
            self.assertFalse(propose.the_carve_is_registered())
            gap = self.refusal(
                self.blocked(dataset_path=str(self.graded()), expected_field="answer")
            )
        self.assertIn(THE_TOOL, gap.detail)
        self.assertIn("not registered here", gap.detail)
        self.assertIn("gap in the harness rather than in your data", gap.detail)
        self.assertNotIn("writing them is yours", gap.detail)
        self.assertIn(THE_TOOL, gap.needs)

    def test_ungraded_data_is_never_told_that_a_tool_is_coming(self):
        """The order of the questions. A person whose answers are not there has a
        permanent answer, and "the tool is missing" reads as *this will work once
        we ship it*."""
        one, two = instead(a_registry(without=THE_TOOL))
        with one, two:
            gap = self.refusal(
                self.blocked(dataset_path=str(self.ungraded()), expected_field="answer")
            )
        self.assertIn("writing them is yours", gap.detail)
        self.assertNotIn(THE_TOOL, gap.detail)

    def test_coverage_says_what_the_carve_does_and_stops_when_it_goes(self):
        entry = propose.COVERAGE["BLOCKED__BUILD_EVAL_SET"]
        self.assertIn(THE_TOOL, entry)
        self.assertIn("writing them is yours", entry)
        one, two = instead(a_registry(without=THE_TOOL))
        with one, two:
            gone = propose.COVERAGE["BLOCKED__BUILD_EVAL_SET"]
        self.assertNotIn(THE_TOOL, gone)
        self.assertIn("attach_context, then measure_eval_set", gone)
        # Covered either way: the outcome has had a proposer since the beginning.
        self.assertNotIn("BLOCKED__BUILD_EVAL_SET", propose.NOT_COVERED)

    def test_the_pinned_name_is_a_data_tool_that_actually_writes_files(self):
        """The pin is checked against the registry rather than against a
        document. `docs/ROADMAP.md` Milestone 15 calls this tool `split_dataset`;
        what shipped is `carve_eval_set`, and a test that read the roadmap would
        have been green about the wrong name."""
        writers = sorted(
            spec.name
            for spec in REGISTRY
            if spec.control.group == "Data" and "filesystem" in spec.writes
        )
        self.assertIn(THE_TOOL, writers)
        self.assertTrue(set(propose.THE_CARVING_TOOLS) <= set(writers))


class WhenTheTwoLanesDisagreeTest(CarveTestCase):
    """A schema that does not match stops the plan now, not after approval.

    This is not hypothetical. Every argument name this file offered first -
    `eval_path`, `train_path`, `eval_rows`, `expected_field`, an integer `seed` -
    was wrong about the tool that shipped, and this is the mechanism that turned
    that into a sentence somebody could act on.
    """

    def refuse_with(self, spec: ToolSpec) -> propose.NotEnoughToPropose:
        situation = self.blocked(
            dataset_path=str(self.graded()), expected_field="answer"
        )
        one, two = instead(a_registry(without=THE_TOOL, plus=spec))
        with one, two:
            return self.refusal(situation)

    def test_a_tool_that_will_not_say_where_it_writes_stops_the_plan(self):
        gap = self.refuse_with(a_stand_in("path", "answer_column"))
        self.assertIn("where to put what it writes", gap.detail)
        self.assertIn("'into', 'out_dir', 'destination'", gap.detail)
        self.assertIn("what a person approves is what appears on their disk", gap.detail)

    def test_a_tool_that_names_no_answer_column_stops_the_plan(self):
        gap = self.refuse_with(a_stand_in("path", "into"))
        self.assertIn("which column already holds the right answers", gap.detail)
        self.assertIn("holding out rows nobody graded", gap.detail)

    def test_a_tool_that_cannot_be_told_which_dataset_stops_the_plan(self):
        gap = self.refuse_with(a_stand_in("answer_column", "into"))
        self.assertIn("which dataset to carve the eval set out of", gap.detail)

    def test_a_required_argument_nothing_here_can_supply_stops_the_plan(self):
        gap = self.refuse_with(
            a_stand_in(
                "path",
                "answer_column",
                "into",
                "group_by",
                required=("path", "group_by"),
            )
        )
        self.assertIn("group_by", gap.detail)
        self.assertIn("refused after somebody approved the plan", gap.detail)

    def test_an_argument_the_tool_never_heard_of_is_dropped_rather_than_passed(self):
        situation = self.blocked(
            dataset_path=str(self.graded()), expected_field="answer"
        )
        one, two = instead(
            a_registry(
                without=THE_TOOL,
                plus=a_stand_in("dataset_path", "label_field", "out_dir"),
            )
        )
        with one, two:
            plan = propose.propose(situation)
        carve = next(step for step in plan.steps if step.tool == THE_TOOL)
        self.assertEqual(
            sorted(carve.arguments), ["dataset_path", "label_field", "out_dir"]
        )

    def test_the_real_tool_takes_every_argument_this_plan_relies_on(self):
        """The contract as it stands, asserted rather than assumed - so a rename
        in the sibling lane reddens this file rather than the product."""
        spec = REGISTRY.get(THE_TOOL)
        properties = set((spec.schema.get("properties") or {}).keys())
        self.assertTrue({"path", "answer_column", "into"} <= properties)
        self.assertEqual(
            set(spec.schema.get("required") or ()), {"path", "answer_column", "into"}
        )
        self.assertEqual(spec.measures, ())
        self.assertIn("filesystem", spec.writes)


# ---------------------------------------------------------------------------
# 7. The sentence that went false the day a tool wrote a file.


class ADiskEstimateSaysWhichKindOfWriteItIsTest(unittest.TestCase):
    """`_disk_cost` told every writer it wrote *rows in the harness database, no
    files*. Three sandbox tools already wrote files when that was written, and
    the two data-work tools do now; the sentence is false of all five, and it
    would have been printed in every carve proposal."""

    def setUp(self):
        self.root = support.sandbox(self)

    def test_a_tool_that_writes_files_is_not_described_as_writing_rows(self):
        writers = [spec.name for spec in REGISTRY if "filesystem" in spec.writes]
        self.assertTrue(writers, "no registered tool declares writes=('filesystem',)")
        self.assertIn(THE_TOOL, writers)
        for name in writers:
            said = propose._disk_cost(name).say()
            self.assertIn("writes FILES and not rows", said)
            self.assertNotIn("rows in the harness database", said)

    def test_a_tool_that_writes_rows_still_says_rows(self):
        said = propose._disk_cost("measure_eval_set").say()
        self.assertIn("rows in the harness database, no files", said)

    def test_a_tool_that_writes_nothing_still_proves_zero(self):
        estimate = propose._disk_cost("check_split_leakage")
        self.assertTrue(estimate.known)
        self.assertIn("declares writes=()", estimate.say())

    def test_the_carve_reaches_no_model_so_the_plan_costs_nothing_in_tokens(self):
        self.assertNotIn("providers", REGISTRY.get(THE_TOOL).reads)


# ---------------------------------------------------------------------------
# 8. The surface, and why it exists.


class TheCarveHasASurfaceAndTheReasonIsMeasuredTest(unittest.TestCase):
    """A card was built, and this is the measurement that says it had to be.

    `ResultView.tsx` is the generic key/value table every uncarded tool result
    falls to. It summarises a container at depth 3 and folds a string past 320
    characters behind a button. Both numbers are read out of that component
    here rather than remembered, and the captured fixtures' own `shape` blocks
    are compared against them - so the claim *"the generic table hides the leak
    pairs"* is checked rather than asserted, and it goes red the day somebody
    raises the cap and makes the card unnecessary.

    The fixtures are produced by `scripts/capture_datawork_fixtures.py` running
    the real tool; nothing in them was typed.
    """

    FRONTEND = REPO / "frontend" / "src"
    FIXTURES = FRONTEND / "fixtures" / "datawork"

    def component(self, name: str) -> str:
        return (self.FRONTEND / name).read_text(encoding="utf-8")

    def shapes(self) -> dict:
        return json.loads((self.FIXTURES / "SHAPES.json").read_text(encoding="utf-8"))

    def test_the_generic_table_caps_are_where_the_measurement_assumed(self):
        source = self.component("components/ResultView.tsx")
        self.assertIn("const MAX_DEPTH = 3;", source)
        self.assertIn("const LONG_TEXT = 320;", source)

    def test_a_real_carve_payload_is_deeper_than_that_table_will_draw(self):
        shapes = self.shapes()
        leaking = shapes["02-carved-and-leaking"]
        self.assertGreater(leaking["max_nesting_depth"], 3)
        self.assertGreater(leaking["rows_hidden_behind_those_summaries"], 0)
        # AND WHAT IS HIDDEN IS THE PART THAT MATTERS: the pairs of rows found
        # on both sides of a file this harness wrote.
        self.assertIn(
            "leakage.examples[]", leaking["what_is_summarised_away"]
        )
        self.assertGreaterEqual(
            leaking["strings_past_320_chars_that_get_a_show_all_button"], 2
        )

    def test_the_two_honesty_sentences_are_in_the_payload_and_are_not_folded(self):
        """The correction that this test was written to make.

        The card's first draft claimed both sentences were past the generic
        table's 320-character fold. They are not - 299 and 221, measured here
        rather than remembered - and the claim is corrected in the three files
        that carried it. What IS folded is `summary` and `method.how`, and the
        card's argument rests on the depth cap rather than on either.
        """
        payload = json.loads(
            (self.FIXTURES / "02-carved-and-leaking.json").read_text(encoding="utf-8")
        )["payload"]
        for field in ("does_not_open_g0", "grading_is_still_yours"):
            self.assertLess(len(payload[field]), 320, field)
        self.assertGreater(len(payload["summary"]), 320)
        self.assertGreater(len(payload["method"]["how"]), 320)
        self.assertIn("did not count one", payload["does_not_open_g0"])
        self.assertIn(
            "graded by the person who cares about the answer",
            payload["grading_is_still_yours"],
        )

    def test_neither_sentence_can_be_dropped_from_the_card_and_still_compile(self):
        """Typed as required strings on `Carve`, not optional ones. A card that
        drew a row count and left the gate sentence out would be a file we wrote
        looking like a gate we opened."""
        reader = self.component("lib/engine/datawork.ts")
        self.assertIn("openedNoGate: string;", reader)
        self.assertIn("gradingIsStillYours: string;", reader)
        self.assertNotIn("openedNoGate?:", reader)
        self.assertNotIn("gradingIsStillYours?:", reader)
        card = self.component("components/CarveCard.tsx")
        self.assertIn("{carve.openedNoGate}", card)
        self.assertIn("{carve.gradingIsStillYours}", card)

    def test_the_tool_is_referenced_from_the_frontend_at_all(self):
        """The check the retrieval bench had to invent, kept: before that lane,
        ZERO files under `frontend/src` named either of its tools. This is that
        question asked about this one."""
        naming = [
            path
            for path in self.FRONTEND.rglob("*.ts*")
            if THE_TOOL in path.read_text(encoding="utf-8")
        ]
        self.assertTrue(naming, f"no file under frontend/src names {THE_TOOL}")

    def test_the_card_is_reached_from_the_transcript(self):
        """The transcript reads a carve and draws its two cards."""
        transcript = self.component("components/Transcript.tsx")
        for needed in (
            "readCarve",
            "readCarveRefusal",
            "<CarveCard",
            "<CarveRefusalCard",
        ):
            self.assertIn(needed, transcript, needed)

    def test_a_carve_counts_as_a_card_where_that_is_now_decided(self):
        """The other half of the same property, which MOVED on 2026-09-11.

        This used to read `carve !== null` and `carveRefusal !== null` out of
        `Transcript.tsx`, where the thirteen-way "did anything recognise this"
        disjunction lived inline. It now lives in `components/cards.ts`,
        because the tool strip asks the same question to decide what may be
        folded into an icon and two readers would drift - a carve that stopped
        counting as a card there would be folded away silently.

        So the assertion follows the decision rather than the filename. What
        it holds is unchanged: a carve, and a refusal to carve, are cards.
        """
        cards = self.component("components/cards.ts")
        self.assertIn("readCarve(item.result) !== null", cards)
        self.assertIn("readCarveRefusal(item.result) !== null", cards)
        #: And the transcript asks that reader rather than deciding again.
        transcript = self.component("components/Transcript.tsx")
        self.assertIn("toolRowDrawsACard(item,", transcript)

    def test_the_stylesheet_writes_no_literal_colour_and_no_disabled_ink(self):
        """Law five: never hard-code a hex, or the component is wrong in one
        theme and nobody notices for a month. Page 03.3: --ink-4 misses both
        contrast floors and is for disabled controls only - not a unit, not a
        count."""
        sheet = (self.FRONTEND / "styles" / "datawork.css").read_text(encoding="utf-8")
        # Comments carry token names and prose; the rules are what ship.
        rules = re.sub(r"/\*.*?\*/", "", sheet, flags=re.S)
        self.assertEqual(re.findall(r"#[0-9A-Fa-f]{3,8}\b", rules), [])
        self.assertEqual(re.findall(r"\brgba?\(", rules), [])
        self.assertEqual([line for line in rules.splitlines() if "--ink-4" in line], [])

    def test_the_card_is_imported_where_the_stylesheet_is(self):
        app = (self.FRONTEND / "App.tsx").read_text(encoding="utf-8")
        self.assertIn("styles/datawork.css", app)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
