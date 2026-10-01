"""Nineteen ways a real measurement of the wrong thing reaches a proposal's cost.

## Why this file exists

A proposal for a 777-row eval file promised **"model_requests: 120 requests
(inferred)"**, and the derivation it showed was *"counted 120 rows in
...\\Temp\\tmph_4tt4go\\eval.jsonl; capped at 500"*. Every clause of that is
true. The count happened, on a real file, and the ledger stamped it MEASURED.
The cap is `measure_baseline`'s own. The arithmetic is right. The answer is four
times too small, because the file counted is not the file the step runs on.

**An invented number fails the question "where did this come from?". This one
answers it correctly.** That is why it is the worse defect, and why it needs its
own file: every wall the product had was arranged around numbers with no origin,
and this number's origin was impeccable.

`app/build.py` grew `Subject`, `Reading` refuses to exist without one, and
`Build.validate` refuses a step whose cost descends from a measurement of
anything other than what that step operates on. This file is the ratchet on
that, in the shape `tests/test_laundering_routes.py` established: named routes,
a detector that is itself proved to fire, and a pinned count.

## What is being defended

**A MEASUREMENT IS BOUND TO WHAT IT MEASURED.** A cost is the one number in this
product a person reads before spending their own model's tokens and their own
hours. `docs/THE_PROPOSAL_LOOP.md` says cost "must be shown *before* they say
yes, not discovered afterwards". A four-fold understatement discovered afterwards
is the same broken promise as an invented number, arrived at through a door
nobody was watching.

## What a route is

One route is one way a number that was genuinely measured could end up costing a
step it is not about. They come in three groups and all three are needed:

* **PRODUCT routes** drive the real proposers through the real registry, with a
  real count written by a real tool into a real ledger. These are the ones that
  correspond to something a user can actually do.
* **TYPE routes** go at `app/build.py`'s own doors. A product route proves this
  build is right; a type route proves the shape is wrong to build.
* **FALSE-REFUSAL routes** are the opposite failure, and they are not padding.
  A check that refuses every measurement is not a check, it is a product that
  says "I cannot cost this" to somebody who did all the work. Two spellings of
  one file must MATCH.

## The two mistakes this file must not make

Both are ways to be confidently green while checking nothing, and both are the
same mistakes `tests/test_laundering_routes.py` records in the adversary's own
detector:

1. **A detector that can only ever see valid builds.** `Build.validate` refuses
   a mismatched step, so a sweep that only ever looks at builds finds nothing
   BECAUSE nothing can be built - which is indistinguishable from finding
   nothing because the check works. So the detector here is
   `foreign_subjects(step)`, which reads a `Step` (unvalidated: only `Build`
   validates), and `TheDetectorProvesItselfTest` hands it a step built from the
   exact wrong-file arithmetic and requires it to report exactly one.
2. **Asserting the refusal instead of the number.** "It raised" is not the
   product being right. The product being right is the person seeing UNKNOWN
   with both subjects named and a step in the build that goes and counts the
   file - so the product routes assert the ESTIMATE and the STEPS, not the
   exception.

## The controls

* `test_the_detector_sees_a_cost_measured_off_another_file` - the detector fires
  on a hand-built step. If this ever passes vacuously, every sweep below is
  worthless.
* `test_the_honest_number_still_gets_through` - count the 777-row file itself
  and the proposal says **500 requests, inferred**. This is the positive control
  in the other direction and it is the one that would catch a "fix" that made
  every cost unknown.
* `TheRecoveryOfASubjectIsPinnedToWhatTheToolsWriteTest` - the subject of a
  stored fact is read out of the derivation prose, because the ledger has no
  column for it. Both live minting tools are driven through the real registry
  and the recovered key must equal the file. A reworded `how` turns this red
  instead of quietly degrading every proposal to unknown.

## The pinned count

`ROUTES` names every route. `ROUTES_CLOSED` is how many are closed, and it is
asserted against the number of routes that actually exist, so a route cannot be
added without a decision about it and cannot be deleted quietly.
"""

from __future__ import annotations

import json
import os
import re
import unittest
from dataclasses import replace
from pathlib import Path

import diagnosis_fixtures

from app import build, diagnosis
from app.build import (
    Build,
    BuildInvalid,
    Cost,
    Environment,
    Estimate,
    ExitCriterion,
    Reading,
    Step,
    Subject,
    SubjectMismatch,
)
from app.tools import REGISTRY, evidence, propose

import support

#: Shared with the Phase-B journey test: the only files shaped like what the
#: instruments accept, and therefore the only honest thing to plan against.
HERE_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "agent"


# ---------------------------------------------------------------------------
# The routes, named. Grep this file for `# route:` and the whole list is on
# screen; the count below is asserted against it.

ROUTES: dict[str, str] = {
    # PRODUCT - through the real proposers, the real registry, a real ledger.
    "the_reported_case": (
        "eval_size_n counted off a 120-row file in a temp directory, a baseline "
        "proposed for a 777-row file. The case as reported."
    ),
    "a_file_of_the_same_name_elsewhere": (
        "two files both called eval.jsonl, in different folders. The one thing a "
        "path check has to get right and a filename check never could."
    ),
    "the_train_split_instead_of_the_eval_split": (
        "train.jsonl was counted, eval.jsonl is what the baseline scores."
    ),
    "the_folder_rather_than_the_file": (
        "the folder holding the eval set was counted; the step reads one file in "
        "it. A folder and a file inside it are different subjects, and a folder "
        "count is what a folder reader would write the day one ships."
    ),
    "a_count_with_no_record_of_what_it_counted": (
        "eval_size_n is MEASURED and the derivation names no file at all, so no "
        "subject can be recovered. Unrecoverable must mean unknown, never "
        "'probably this one'."
    ),
    "the_already_counted_refusal": (
        "BLOCKED__BUILD_EVAL_SET refusing to count a file because a DIFFERENT "
        "file was counted. The same omission wearing the clothes of a refusal."
    ),
    "the_substantiate_builds_scoring_step": (
        "ACTION__SUBSTANTIATE_CLAIMED_FACTS also plans a measure_baseline, costed "
        "by the same function, so it must say what it runs on and must not "
        "inherit a subject from anywhere else."
    ),
    # TYPE - at app/build.py's own doors.
    "a_reading_with_no_subject_at_all": (
        "the signature that made the defect possible: name, value, origin, how, "
        "and no statement of what was measured."
    ),
    "about_a_different_path": (
        "Estimate.about() handed a subject that is not the one the number was "
        "measured off. The door itself, refusing."
    ),
    "about_the_same_path_with_different_contents": (
        "the same path, the file rewritten underneath it. Same name, different "
        "file - which is why a key alone was not judged enough."
    ),
    "about_an_estimate_that_measured_nothing": (
        "a proved zero and an honest unknown are fine numbers and neither is a "
        "measurement OF anything, so neither may pass a subject check."
    ),
    "a_measured_cost_with_no_operates_on": (
        "a step costed from a measurement that does not say what it runs on. The "
        "defect stated exactly."
    ),
    "an_operates_on_no_argument_names": (
        "a step declaring a subject its own call does not mention - which is how "
        "a check that reads the declaration instead of the call gets fooled."
    ),
    "a_foreign_subject_inside_a_whole_build": (
        "the same mismatch through Build(), so an unvalidatable plan cannot reach "
        "a user."
    ),
    "a_subject_four_derivations_deep": (
        "cap, scale, reinterpret, sum. A number four steps from the instrument is "
        "still a measurement of what the instrument was pointed at."
    ),
    # FALSE REFUSAL - these must MATCH. A wall that blocks everything is not one.
    "the_same_file_by_a_relative_path": (
        "one file, two spellings. This must MATCH: a false refusal here costs a "
        "person a re-count for nothing."
    ),
    "the_same_file_through_dot_segments": (
        "one file, two spellings, with . and .. in the middle of one of them. "
        "This must MATCH."
    ),
    "the_same_file_in_another_case": (
        "one file, two spellings, on a filesystem that does not distinguish them."
    ),
    "the_same_file_counted_then_scored": (
        "the whole point: a count of THIS file costs this step, and the number is "
        "500 rather than unknown."
    ),
}

#: Every route is closed. There is no `@open_route` decorator in this file
#: because there was nothing to leave open: the fix landed in one change. If a
#: route is ever found open, it gets one - see `tests/test_laundering_routes.py`
#: for the shape - and this number comes down in the same diff.
ROUTES_CLOSED = 19


# ---------------------------------------------------------------------------
# The detector, and the thing it detects.


def foreign_subjects(step: Step) -> list[str]:
    """Every cost on `step` measured off something other than what it runs on.

    Reads a `Step` and not a `Build`, deliberately. `Build.validate` refuses a
    step like this, so a detector that took a build could only ever be handed
    clean input and would report nothing whether or not it worked. This one can
    be pointed at the defect itself, and `TheDetectorProvesItselfTest` does.
    """
    found: list[str] = []
    for dimension in build.COST_DIMENSIONS:
        estimate = getattr(step.cost, dimension, None) if step.cost else None
        if estimate is None:
            continue
        for subject in estimate.subjects():
            if step.operates_on is None:
                found.append(f"{step.id}.{dimension} measured off {subject.key}, "
                             "and the step does not say what it runs on")
                continue
            ok, why = step.operates_on.matches(subject)
            if not ok:
                found.append(f"{step.id}.{dimension}: {why}")
    return found


# ---------------------------------------------------------------------------
# Scaffolding.


FACTS_THAT_REACH_THE_BASELINE = {
    "goal_text": "route support tickets",
    "modality": "text",
    "task_family": "classification",
    "need_type": ["behaviour"],
    "target_score": 0.9,
}

FACTS_THAT_STOP_AT_G0 = {
    "goal_text": "route support tickets",
    "modality": "text",
    "target_score": 0.9,
}



#: THE THIRD LEDGER'S FIXTURE FILES, on disk rather than written per test. The
#: harness instruments read a checker, a task set, two ablation arms and a tool
#: definitions file, and every one of them has to be a REAL file of the right
#: shape - a temporary file written inline would be four more things to keep in
#: step with the tools that parse them.
def _harness_fixture(name: str) -> str:
    return str(Path(__file__).resolve().parent / "fixtures" / "harness" / name)


def _harness_builds(case) -> list:
    """One real build from every harness proposer, driven through the engine.

    The sheet for each outcome comes from `harness_fixtures.SHEETS`, which is
    itself driven - `test_the_harness_ledger_refuses_before_it_builds` walks
    every one of them and asserts it lands on its own key - so a plan drawn here
    is a plan drawn for the situation the engine actually produces rather than
    for one assembled to reach a proposer.

    `spec` is not passed and cannot be: `Situation.spec` is a PROPERTY over the
    diagnosis, because "an answer carries the knowledge it was computed from" is
    how this file avoided threading a ledger handle through 9,800 lines. So the
    ledger reaches the proposer through `result`, which is where it belongs.
    """
    import harness_fixtures
    from app import diagnosis as _diagnosis
    from app.tools import propose as _propose

    spec = _diagnosis.spec_at("docs/ledgers/harness_design.yaml")
    tasks = _harness_fixture("journey-tasks.jsonl")
    arms = [
        {
            "component": "reranker",
            "with_answers": _harness_fixture("journey-with-reranker.jsonl"),
            "without_answers": _harness_fixture("journey-without-reranker.jsonl"),
        }
    ]
    shared = {
        "checker_path": _harness_fixture("journey-checker.py"),
        "tasks_path": tasks,
        "answers_path": _harness_fixture("journey-solo-answers.jsonl"),
        "tooldefs_path": _harness_fixture("journey-tools.json"),
        "trace_path": str(
            Path(__file__).resolve().parent / "fixtures" / "agent" / "journey-traces.jsonl"
        ),
        "ablation_arms": tuple(arms),
        "input_field": "task",
        "expected_field": "expected",
        "answer_field": "answer",
    }

    out = []
    for outcome in sorted(harness_fixtures.SHEETS):
        if outcome not in _propose.PROPOSERS:
            continue
        facts = harness_fixtures.SHEETS[outcome]
        result = _diagnosis.diagnose(facts, spec)
        case.assertEqual(result.outcome, outcome, "the fixture stopped reaching it")
        out.append(
            _propose.propose(
                _propose.Situation(
                    outcome=result.outcome,
                    result=result,
                    values={name: fact.value for name, fact in facts.items()},
                    origins=dict(result.fact_origins),
                    **shared,
                )
            )
        )
    return out

class SubjectTestCase(unittest.TestCase):
    """Its own database and its own directory, like every proposal test."""

    def setUp(self):
        self.root = support.sandbox(self)
        self.thread = 1
        support.a_conversation(self.thread)

    # -- files -------------------------------------------------------------

    def rows_at(self, path: Path, rows: int) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(
                json.dumps({"q": f"question {i}", "a": "yes"}) for i in range(rows)
            ),
            encoding="utf-8",
        )
        return path

    def the_real_eval_set(self, rows: int = 777) -> Path:
        return self.rows_at(self.root / "real" / "eval.jsonl", rows)

    # -- the ledger --------------------------------------------------------

    def count_for_real(self, path: Path, thread: int | None = None) -> int:
        """Make eval_size_n genuinely MEASURED, through the real tool."""
        support.a_conversation(thread if thread is not None else self.thread)
        result = REGISTRY.call(
            "measure_eval_set",
            {"path": str(path), "finish_the_count": True},
            actor=evidence.USER,
            thread_id=thread if thread is not None else self.thread,
        )
        self.assertTrue(result.get("exact"), result)
        return int(result["rows"])

    def situation(
        self, facts: dict, *, thread: int | None = None, actor=evidence.USER, **extra
    ) -> propose.Situation:
        thread_id = thread if thread is not None else self.thread
        sheet, trail = evidence.assemble_facts(thread_id, dict(facts), actor)
        result = diagnosis.diagnose(sheet)
        return propose.Situation(
            outcome=result.outcome,
            result=result,
            values={row["fact"]: row["value"] for row in trail},
            origins={row["fact"]: row["origin"] for row in trail},
            hows={row["fact"]: row.get("how") or "" for row in trail},
            **extra,
        )

    def bench_situation(
        self, histogram, *, outcome: str, thread: int, facts=None, **extra
    ) -> propose.Situation:
        """A situation for an outcome the eval and prompt benches unlock.

        The OUTCOME comes from a fact sheet the fixtures build, because a
        MEASURED `failure_histogram` can only be minted by running `run_eval`
        against somebody's model and a test that needs a model running fails on
        a fresh checkout. Everything this file actually checks - the values, the
        origins, the derivations and the dates behind a costed step - still
        comes out of the real ledger for `thread`, so a build costed off the
        wrong file is caught here exactly as the others are.
        """
        sheet = dict(diagnosis_fixtures.MINTING["TRAIN__LORA_SFT"])
        sheet["failure_histogram"] = diagnosis.measured(histogram)
        sheet.update(facts or {})
        result = diagnosis.diagnose(sheet)
        self.assertEqual(result.outcome, outcome)
        _sheet, trail = evidence.assemble_facts(thread, {}, evidence.USER)
        return propose.Situation(
            outcome=result.outcome,
            result=result,
            values={row["fact"]: row["value"] for row in trail},
            origins={row["fact"]: row["origin"] for row in trail},
            hows={row["fact"]: row.get("how") or "" for row in trail},
            recorded_at=propose.when_each_row_was_written(thread, trail),
            **extra,
        )

    def a_corpus(self, name: str = "corpus") -> Path:
        """A folder of documents to index. Never the eval file - that is refused."""
        folder = self.root / name
        folder.mkdir(parents=True, exist_ok=True)
        for index in range(3):
            (folder / f"doc_{index}.txt").write_text(
                f"document {index}: the refund window is thirty days\n",
                encoding="utf-8",
            )
        return folder

    def questions_at(self, path: Path, rows: int = 60) -> Path:
        """An eval set shaped for recall: a question, and the document that answers it."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(
                json.dumps({"q": f"question {i}", "doc": f"doc_{i % 3}.txt"})
                for i in range(rows)
            ),
            encoding="utf-8",
        )
        return path

    def training_data_at(self, path: Path, rows: int = 200) -> Path:
        """Data to fine-tune ON, in the shape `hf-peft-lora` reads.

        Never the eval file: the training build refuses that outright, because
        an adapter scored on rows it was trained on produces a number that
        measures memory rather than learning - and a high one.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(
                json.dumps({"text": f"a training example, number {i}"})
                for i in range(rows)
            ),
            encoding="utf-8",
        )
        return path

    def preference_data_at(self, path: Path, rows: int = 4000) -> Path:
        """What a preference run trains on, which is not what an SFT run does.

        prompt/chosen/rejected rather than a `text`: `hf-peft-dpo` refuses the
        other shape by name, and four thousand of them because the ledger's own
        condition for this route is `preference_pairs_n >= 1000`.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(
                json.dumps(
                    {
                        "prompt": f"ticket {i}",
                        "chosen": "the reply we want",
                        "rejected": "the reply we do not",
                    }
                )
                for i in range(rows)
            ),
            encoding="utf-8",
        )
        return path

    def sft_adapter_at(self, path: Path) -> Path:
        """The pass a preference run continues from, which the ledger requires."""
        path.mkdir(parents=True, exist_ok=True)
        (path / "adapter_config.json").write_text("{}", encoding="utf-8")
        return path

    def count_pairs_for_real(self, path: Path, thread: int) -> int:
        """Make `preference_pairs_n` genuinely MEASURED, through the real tool.

        THE SAME THESIS AS `count_for_real` AND IT BITES HARDER HERE. The
        preference build refuses to plan a GPU run against a count of a file it
        is not going to train on, and the row that satisfies it has to be the
        LEDGER'S - with the derivation `count_preference_pairs` actually wrote
        and the date it was actually written. A fixture `hows` string would test
        the parser rather than the instrument.
        """
        support.a_conversation(thread)
        result = REGISTRY.call(
            "count_preference_pairs",
            {"path": str(path), "finish_the_count": True},
            actor=evidence.USER,
            thread_id=thread,
        )
        self.assertTrue(result.get("exact"), result)
        return int(result["preference_pairs"])

    def preference_situation(self, *, thread: int, **extra):
        """A situation for `TRAIN__DPO`, in `training_situation`'s shape."""
        sheet = dict(diagnosis_fixtures.MINTING["TRAIN__DPO"])
        result = diagnosis.diagnose(sheet)
        self.assertEqual(result.outcome, "TRAIN__DPO")
        _sheet, trail = evidence.assemble_facts(thread, {}, evidence.USER)
        values = {name: getattr(value, "value", value) for name, value in sheet.items()}
        origins = dict(result.fact_origins)
        values.update({row["fact"]: row["value"] for row in trail})
        origins.update({row["fact"]: row["origin"] for row in trail})
        return propose.Situation(
            outcome=result.outcome,
            result=result,
            values=values,
            origins=origins,
            hows={row["fact"]: row.get("how") or "" for row in trail},
            recorded_at=propose.when_each_row_was_written(thread, trail),
            **extra,
        )

    def training_situation(self, *, thread: int, **extra):
        """A situation for `TRAIN__LORA_SFT`, in `retrieval_situation`'s shape.

        Same merge and the same reason: the fine-tune's own numbers come off
        `baseline_score`, which is `source: inspect` and can only be minted by
        `measure_baseline` against somebody's model, so the fixture sheet sits
        underneath and the LEDGER OVERWRITES IT. That matters here more than
        anywhere: this build refuses unless `eval_size_n` is a measured count of
        the file the fine-tune would be judged on, and it is the ledger's row -
        with its real derivation and its real date - that has to satisfy it.
        """
        sheet = dict(diagnosis_fixtures.MINTING["TRAIN__LORA_SFT"])
        result = diagnosis.diagnose(sheet)
        self.assertEqual(result.outcome, "TRAIN__LORA_SFT")
        _sheet, trail = evidence.assemble_facts(thread, {}, evidence.USER)
        values = {name: getattr(value, "value", value) for name, value in sheet.items()}
        origins = dict(result.fact_origins)
        values.update({row["fact"]: row["value"] for row in trail})
        origins.update({row["fact"]: row["origin"] for row in trail})
        return propose.Situation(
            outcome=result.outcome,
            result=result,
            values=values,
            origins=origins,
            hows={row["fact"]: row.get("how") or "" for row in trail},
            recorded_at=propose.when_each_row_was_written(thread, trail),
            **extra,
        )

    def table_at(self, path: Path, rows: int = 3000) -> Path:
        """A tabular file with a real label column, for the tree fit.

        Not JSONL: `fit_a_tree_model` reads a table, and the proposer reads the
        label column off this file at proposal time to decide whether there are
        enough graded rows to fit on at all.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(
                ["size,region,label"]
                + [
                    f"{index},{index % 7},{('yes', 'no', 'maybe')[index % 3]}"
                    for index in range(rows)
                ]
            ),
            encoding="utf-8",
        )
        return path

    def tabular_situation(self, *, thread: int, **extra):
        """A situation for `NO_DEEP__GRADIENT_BOOSTED_TREES`, the same way.

        `SPREAD['tabular_default']` under the ledger, for `training_situation`'s
        reason: `tabular_rows` is `source: inspect` and nothing in this harness
        mints one, so the fixture sheet has to sit underneath - and every value
        and derivation the ledger DOES hold still wins, which is what this file
        checks costs against.
        """
        sheet = dict(diagnosis_fixtures.SPREAD["tabular_default"]["facts"])
        result = diagnosis.diagnose(sheet)
        self.assertEqual(result.outcome, "NO_DEEP__GRADIENT_BOOSTED_TREES")
        _sheet, trail = evidence.assemble_facts(thread, {}, evidence.USER)
        values = {name: getattr(value, "value", value) for name, value in sheet.items()}
        origins = dict(result.fact_origins)
        values.update({row["fact"]: row["value"] for row in trail})
        origins.update({row["fact"]: row["origin"] for row in trail})
        return propose.Situation(
            outcome=result.outcome,
            result=result,
            values=values,
            origins=origins,
            hows={row["fact"]: row.get("how") or "" for row in trail},
            recorded_at=propose.when_each_row_was_written(thread, trail),
            **extra,
        )

    def retrieval_situation(self, outcome: str, *, thread: int, **extra):
        """A situation for one of the two outcomes the retrieval bench answers.

        Same shape and same reason as `bench_situation`: the outcome comes from
        a fact sheet the fixtures build, because `retriever_recall_at_k` is
        `source: inspect` and only a real run against a real index can mint one,
        while the values, origins, derivations and dates behind every costed step
        still come out of the real ledger for `thread`.
        """
        sheet = dict(
            diagnosis_fixtures.REACHING.get(outcome)
            or diagnosis_fixtures.REACHING["ACTION__MEASURE_RETRIEVER_RECALL"]
        )
        if outcome == "NO_TRAIN__RAG":
            sheet["retrieval_tried"] = diagnosis.stated(False)
        result = diagnosis.diagnose(sheet)
        self.assertEqual(result.outcome, outcome)
        _sheet, trail = evidence.assemble_facts(thread, {}, evidence.USER)
        # THE LEDGER WINS AND THE FIXTURE FILLS THE REST, which is what the
        # engine actually decided on: `retriever_recall_at_k` is source: inspect
        # and no run has minted one in this thread, so without the sheet
        # underneath it the situation would carry an origin with no value behind
        # it - and a proposer deriving a row count from that recall would be
        # deriving it from nothing. Every cost this file checks still comes off
        # the ledger rows, because those overwrite these.
        values = {name: getattr(value, "value", value) for name, value in sheet.items()}
        origins = dict(result.fact_origins)
        values.update({row["fact"]: row["value"] for row in trail})
        origins.update({row["fact"]: row["origin"] for row in trail})
        return propose.Situation(
            outcome=result.outcome,
            result=result,
            values=values,
            origins=origins,
            hows={row["fact"]: row.get("how") or "" for row in trail},
            recorded_at=propose.when_each_row_was_written(thread, trail),
            **extra,
        )

    def a_baseline_for(self, path: Path, **extra) -> Build:
        situation = self.situation(
            FACTS_THAT_REACH_THE_BASELINE,
            eval_path=str(path),
            input_field="q",
            expected_field="a",
            sample=500,
            **extra,
        )
        self.assertEqual(situation.outcome, "ACTION__MEASURE_BASELINE")
        return propose.propose(situation)

    # -- assertions --------------------------------------------------------

    def assert_refused_and_offers_to_measure(
        self, plan: Build, *, expected: Path, found: Path | None
    ) -> None:
        """The product behaviour a mismatch has to produce, not just a raise."""
        requests = plan.step("baseline").cost.model_requests
        self.assertEqual(requests.provenance, build.UNKNOWN, requests.say())
        self.assertIsNone(requests.value)
        self.assertIn(build._path_key(expected), requests.how)
        if found is not None:
            self.assertIn(build._path_key(found), requests.how)
        self.assertIn("count the eval set", requests.find_out_by)
        # And the offer is a step that is really in the plan, against the right
        # file, not a sentence about a step.
        self.assertEqual(plan.steps[0].tool, "measure_eval_set")
        self.assertEqual(
            build._path_key(plan.steps[0].arguments["path"]),
            build._path_key(expected),
        )


# ---------------------------------------------------------------------------
# 1. The detector proves itself. Nothing below means anything without this.


class TheDetectorProvesItselfTest(SubjectTestCase):
    """A procedure returning green against known-broken code certifies nothing."""

    def a_wrong_cost(self, measured_of: Subject) -> Cost:
        """The pre-fix arithmetic exactly: count one file, cost another."""
        rows = Estimate.measured(
            build.ROWS,
            reading=Reading.of_measured_fact(
                "eval_size_n",
                120,
                diagnosis.MEASURED,
                f"counted 120 rows in {measured_of.key}",
                subject=measured_of,
            ),
        )
        return Cost(
            model_tokens=Estimate.unknown(
                build.MODEL_TOKENS, why="no tokenizer", find_out_by="run a sample"
            ),
            model_requests=rows.capped_at(500, because="the sample cap").counted_as(
                build.MODEL_REQUESTS, because="one request per row"
            ),
            wall_clock=Estimate.unknown(
                build.WALL_CLOCK, why="never timed", find_out_by="time one run"
            ),
            disk=Estimate.none(build.DISK, because="it writes no file"),
        )

    def a_step_costed_off(self, measured_of: Subject, runs_on: Subject | None) -> Step:
        return Step(
            id="baseline",
            tool="measure_baseline",
            why="a step this control builds by hand",
            arguments={
                "eval_path": runs_on.key if runs_on else "",
                "input_field": "q",
                "expected_field": "a",
            },
            cost=self.a_wrong_cost(measured_of),
            exit_criterion=ExitCriterion(
                stated="it scored", source="tool_result", subject="ok",
                comparator="is_true",
            ),
            operates_on=runs_on,
        )

    def test_the_detector_sees_a_cost_measured_off_another_file(self):
        """THE CONTROL. If this stops firing, every sweep below is vacuous."""
        counted = self.rows_at(self.root / "temp" / "eval.jsonl", 120)
        scored = self.the_real_eval_set()
        step = self.a_step_costed_off(
            Subject.of_path(counted), Subject.of_path(scored)
        )
        found = foreign_subjects(step)
        self.assertEqual(len(found), 1, found)
        self.assertIn(build._path_key(counted), found[0])
        self.assertIn(build._path_key(scored), found[0])
        # And the number it would have shown is the reported one.
        self.assertEqual(step.cost.model_requests.value, 120.0)

    def test_the_detector_is_silent_when_the_measurement_is_of_the_right_file(self):
        """The other half. A detector that fires on everything says nothing."""
        scored = self.the_real_eval_set()
        step = self.a_step_costed_off(Subject.of_path(scored), Subject.of_path(scored))
        self.assertEqual(foreign_subjects(step), [])

    def test_the_product_refuses_the_step_the_detector_catches(self):
        """The wall and the detector must agree, or one of them is decoration."""
        counted = self.rows_at(self.root / "temp" / "eval.jsonl", 120)
        scored = self.the_real_eval_set()
        step = self.a_step_costed_off(
            Subject.of_path(counted), Subject.of_path(scored)
        )
        with self.assertRaises(BuildInvalid) as raised:
            Build(
                id="a_plan_that_may_not_exist",
                title="Score the eval set",
                for_outcome="ACTION__MEASURE_BASELINE",
                because="this control needs a build",
                steps=(step,),
                environment=Environment(
                    name="control", working_dir="runs/control", egress=True,
                    egress_reason="scoring sends rows to the connected model",
                ),
                exit_criterion=ExitCriterion(
                    stated="a baseline exists", source="diagnosis",
                    subject="fact_origins.baseline_measured", comparator="is_measured",
                ),
            )
        self.assertIn(build._path_key(counted), str(raised.exception))
        self.assertIn(build._path_key(scored), str(raised.exception))


# ---------------------------------------------------------------------------
# 2. The product routes.


class TheProductRoutesTest(SubjectTestCase):
    """What a person can actually do, through the real proposers."""

    def test_the_reported_case(self):
        # route: the_reported_case
        counted = self.rows_at(self.root / "temp" / "eval.jsonl", 120)
        scored = self.the_real_eval_set(777)
        self.assertEqual(self.count_for_real(counted), 120)
        plan = self.a_baseline_for(scored)
        self.assert_refused_and_offers_to_measure(
            plan, expected=scored, found=counted
        )
        # The exact number the defect produced must not be anywhere in the cost.
        self.assertNotIn(
            120.0, [e.value for e in plan.step("baseline").cost.estimates]
        )

    def test_a_file_of_the_same_name_elsewhere(self):
        # route: a_file_of_the_same_name_elsewhere
        counted = self.rows_at(self.root / "one" / "eval.jsonl", 40)
        scored = self.rows_at(self.root / "two" / "eval.jsonl", 400)
        self.assertEqual(counted.name, scored.name)
        self.count_for_real(counted)
        self.assert_refused_and_offers_to_measure(
            self.a_baseline_for(scored), expected=scored, found=counted
        )

    def test_the_train_split_instead_of_the_eval_split(self):
        # route: the_train_split_instead_of_the_eval_split
        train = self.rows_at(self.root / "data" / "train.jsonl", 5000)
        evaluation = self.rows_at(self.root / "data" / "eval.jsonl", 60)
        self.count_for_real(train)
        self.assert_refused_and_offers_to_measure(
            self.a_baseline_for(evaluation), expected=evaluation, found=train
        )

    def test_the_folder_rather_than_the_file(self):
        # route: the_folder_rather_than_the_file
        #
        # THE DAY CAME. This comment used to read "no reader in this harness
        # counts a folder today... `counted 90 rows in <folder>` is exactly
        # what a folder reader would write the day one ships, and the recovery
        # and the comparison have to be right BEFORE that day rather than
        # after it." One shipped on 2026-09-19, and the recovery below is
        # unchanged, which is what that sentence was for.
        #
        # What `measure_eval_set` does with a folder now is the thing this
        # file is about - the SUBJECT. A folder holding exactly one data file
        # is that file, and the row it stamps says the FILE, not the folder,
        # because the folder is not what was counted. A folder holding more
        # than one SPLIT is refused with the list: `data/splits` is train,
        # valid and eval, and their sum stamped as `eval_size_n` would open G0
        # on training rows. What makes it a split directory is what the files
        # are called, not how many there are - a corpus of 5,200 examples in
        # one folder is a legitimate eval set and is still counted whole.
        folder = self.root / "corpus"
        evaluation = self.rows_at(folder / "eval.jsonl", 90)
        counted = REGISTRY.call(
            "measure_eval_set",
            {"path": str(folder), "finish_the_count": True},
            actor=evidence.USER,
            thread_id=self.thread,
        )
        self.assertTrue(counted.get("exact"), counted)
        self.assertEqual(counted.get("path"), str(evaluation))
        self.assertIn(
            str(evaluation),
            counted["measured_facts"][0]["how"],
            "the row must name the file it counted, never the folder it was handed",
        )

        splits = self.root / "splits"
        self.rows_at(splits / "train.jsonl", 500)
        self.rows_at(splits / "eval.jsonl", 40)
        refused = REGISTRY.call(
            "measure_eval_set",
            {"path": str(splits), "finish_the_count": True},
            actor=evidence.USER,
            thread_id=self.thread,
        )
        self.assertFalse(refused.get("ok"), refused)
        self.assertEqual(refused.get("error"), "a_folder_of_splits_is_not_an_eval_set")
        self.assertEqual(refused.get("measured_facts"), [])
        self.assertEqual(len(refused.get("files") or []), 2)

        base = self.situation(
            FACTS_THAT_REACH_THE_BASELINE,
            eval_path=str(evaluation),
            input_field="q",
            expected_field="a",
            sample=500,
        )
        as_if = propose.Situation(
            outcome="ACTION__MEASURE_BASELINE",
            result=base.result,
            values={**base.values, "eval_size_n": 90},
            origins={**base.origins, "eval_size_n": diagnosis.MEASURED},
            hows={**base.hows, "eval_size_n": f"counted 90 rows in {folder}"},
            eval_path=str(evaluation),
            input_field="q",
            expected_field="a",
            sample=500,
        )
        self.assert_refused_and_offers_to_measure(
            propose.propose(as_if), expected=evaluation, found=folder
        )

    def test_a_count_with_no_record_of_what_it_counted(self):
        # route: a_count_with_no_record_of_what_it_counted
        #
        # `how` is free text every minting tool composes for itself, so a tool
        # that names no file is a tool somebody could write tomorrow. The
        # situation is built directly rather than through a probe tool, because
        # what is being checked is what the PROPOSER does with such a row.
        scored = self.the_real_eval_set(777)
        situation = self.situation(
            FACTS_THAT_REACH_THE_BASELINE,
            eval_path=str(scored),
            input_field="q",
            expected_field="a",
            sample=500,
        )
        blind = propose.Situation(
            outcome="ACTION__MEASURE_BASELINE",
            result=situation.result,
            values={**situation.values, "eval_size_n": 120},
            origins={**situation.origins, "eval_size_n": diagnosis.MEASURED},
            hows={**situation.hows, "eval_size_n": "I read it somewhere"},
            eval_path=str(scored),
            input_field="q",
            expected_field="a",
            sample=500,
        )
        self.assertIsNone(propose.subject_of_a_recorded_measurement("I read it somewhere"))
        plan = propose.propose(blind)
        requests = plan.step("baseline").cost.model_requests
        self.assertEqual(requests.provenance, build.UNKNOWN)
        self.assertIn("nothing in what was recorded says what was counted", requests.how)
        self.assertEqual(plan.steps[0].tool, "measure_eval_set")

    def test_the_already_counted_refusal(self):
        # route: the_already_counted_refusal
        # Four rows, so the count on file leaves G0 shut and the outcome is
        # still BLOCKED__BUILD_EVAL_SET. A longer count would open the gate and
        # this route would be testing a different question.
        counted = self.rows_at(self.root / "temp" / "eval.jsonl", 4)
        fresh = self.rows_at(self.root / "real" / "new_eval.jsonl", 44)
        self.count_for_real(counted)

        situation = self.situation(FACTS_THAT_STOP_AT_G0, eval_path=str(fresh))
        self.assertEqual(situation.outcome, "BLOCKED__BUILD_EVAL_SET")
        # It must NOT say "already counted" about a file nobody counted.
        plan = propose.propose(situation)
        self.assertEqual([step.tool for step in plan.steps],
                         ["attach_context", "measure_eval_set", "run_diagnosis"])
        self.assertIn(build._path_key(counted), plan.because)
        self.assertIn(build._path_key(fresh), plan.because)

        # And it must still refuse for the file that really was counted.
        again = self.situation(FACTS_THAT_STOP_AT_G0, eval_path=str(counted))
        with self.assertRaises(propose.NotEnoughToPropose) as raised:
            propose.propose(again)
        self.assertIn("more graded examples", str(raised.exception))

    def test_the_substantiate_builds_scoring_step(self):
        # route: the_substantiate_builds_scoring_step
        #
        # SAID PLAINLY BECAUSE IT WOULD OTHERWISE READ AS A PASS IT IS NOT:
        # the engine challenges `eval_size_n` first and stops, so a scoring step
        # does not appear in a substantiate build reachable through the tree
        # today. The branch in `_propose_substantiate` that costs a
        # model-reaching tool is nonetheless live code - `_reaches_the_model`
        # picks it - and a proposer that costs a step and says nothing about
        # what it runs on is the defect's second half. So the challenge list is
        # set directly, which is the only honest way to reach the branch.
        scored = self.the_real_eval_set(777)
        situation = self.situation(
            {**FACTS_THAT_REACH_THE_BASELINE, "eval_size_n": 400},
            actor=evidence.MODEL,
            eval_path=str(scored),
            input_field="q",
            expected_field="a",
            sample=500,
        )
        self.assertEqual(situation.outcome, "ACTION__SUBSTANTIATE_CLAIMED_FACTS")
        self.assertEqual(
            [row.get("fact") for row in situation.result.unsubstantiated],
            ["eval_size_n"],
            "the tree now challenges more than this; re-read the comment above",
        )
        challenged = replace(
            situation.result,
            unsubstantiated=[
                *situation.result.unsubstantiated,
                {"fact": "baseline_measured", "gate": "G1_BASELINE_MEASURED"},
            ],
        )
        plan = propose.propose(replace(situation, result=challenged))
        scoring = [item for item in plan.steps if item.tool == "measure_baseline"]
        self.assertTrue(scoring, [item.tool for item in plan.steps])
        for step in scoring:
            self.assertEqual(foreign_subjects(step), [])
            self.assertIsNotNone(step.operates_on)
            self.assertEqual(step.operates_on.key, build._path_key(scored))
            self.assertEqual(step.cost.model_requests.provenance, build.UNKNOWN)


# ---------------------------------------------------------------------------
# 3. The type routes - the shape, not this build.


class TheTypeRoutesTest(SubjectTestCase):
    def a_reading_of(self, subject: Subject, rows: int = 120) -> Reading:
        return Reading.of_measured_fact(
            "eval_size_n",
            rows,
            diagnosis.MEASURED,
            f"counted {rows} rows in {subject.key}",
            subject=subject,
        )

    def test_a_reading_with_no_subject_at_all(self):
        # route: a_reading_with_no_subject_at_all
        with self.assertRaises(TypeError):
            Reading.of_measured_fact(  # noqa - the signature that allowed the defect
                "eval_size_n", 120, diagnosis.MEASURED, "counted 120 rows"
            )

    def test_about_a_different_path(self):
        # route: about_a_different_path
        counted = self.rows_at(self.root / "temp" / "eval.jsonl", 120)
        scored = self.the_real_eval_set()
        rows = Estimate.measured(
            build.ROWS, reading=self.a_reading_of(Subject.of_path(counted))
        )
        with self.assertRaises(SubjectMismatch) as raised:
            rows.about(Subject.of_path(scored))
        self.assertIn("expected a measurement of", str(raised.exception))
        self.assertIn(build._path_key(scored), str(raised.exception))
        self.assertIn(build._path_key(counted), str(raised.exception))

    def test_about_the_same_path_with_different_contents(self):
        # route: about_the_same_path_with_different_contents
        evaluation = self.the_real_eval_set(100)
        when_counted = Subject.of_path(evaluation)
        self.rows_at(evaluation, 900)
        now = Subject.of_path(evaluation)
        self.assertEqual(when_counted.key, now.key)
        self.assertNotEqual(when_counted.witness, now.witness)
        rows = Estimate.measured(build.ROWS, reading=self.a_reading_of(when_counted))
        with self.assertRaises(SubjectMismatch) as raised:
            rows.about(now)
        self.assertIn("the same path and not the same file", str(raised.exception))

    def test_about_an_estimate_that_measured_nothing(self):
        # route: about_an_estimate_that_measured_nothing
        evaluation = self.the_real_eval_set()
        subject = Subject.of_path(evaluation)
        for estimate in (
            Estimate.none(build.MODEL_REQUESTS, because="it never asks the model"),
            Estimate.unknown(
                build.MODEL_REQUESTS, why="never counted", find_out_by="count it"
            ),
        ):
            with self.assertRaises(SubjectMismatch) as raised:
                estimate.about(subject)
            self.assertIn("descends from no measurement", str(raised.exception))

    def test_a_measured_cost_with_no_operates_on(self):
        # route: a_measured_cost_with_no_operates_on
        evaluation = self.the_real_eval_set()
        rows = Estimate.measured(
            build.ROWS, reading=self.a_reading_of(Subject.of_path(evaluation))
        )
        step = Step(
            id="count",
            tool="measure_eval_set",
            why="a step that does not say what it runs on",
            arguments={"path": str(evaluation)},
            cost=Cost(
                model_tokens=Estimate.none(build.MODEL_TOKENS, because="local"),
                model_requests=rows.counted_as(
                    build.MODEL_REQUESTS, because="one each"
                ),
                wall_clock=Estimate.unknown(
                    build.WALL_CLOCK, why="never timed", find_out_by="time it"
                ),
                disk=Estimate.none(build.DISK, because="no file"),
            ),
            exit_criterion=ExitCriterion(
                stated="counted", source="tool_result", subject="exact",
                comparator="is_true",
            ),
        )
        self.assertEqual(len(foreign_subjects(step)), 1)
        with self.assertRaises(BuildInvalid) as raised:
            self.a_build_of(step)
        self.assertIn("does not say what it operates on", str(raised.exception))

    def test_an_operates_on_no_argument_names(self):
        # route: an_operates_on_no_argument_names
        evaluation = self.the_real_eval_set()
        elsewhere = self.rows_at(self.root / "temp" / "eval.jsonl", 120)
        step = Step(
            id="count",
            tool="measure_eval_set",
            why="a step whose declaration and whose call disagree",
            arguments={"path": str(elsewhere)},
            cost=self.a_free_cost(),
            exit_criterion=ExitCriterion(
                stated="counted", source="tool_result", subject="exact",
                comparator="is_true",
            ),
            operates_on=Subject.of_path(evaluation),
        )
        with self.assertRaises(BuildInvalid) as raised:
            self.a_build_of(step)
        self.assertIn("none of the arguments it passes", str(raised.exception))

    def test_a_foreign_subject_inside_a_whole_build(self):
        # route: a_foreign_subject_inside_a_whole_build
        evaluation = self.the_real_eval_set()
        elsewhere = self.rows_at(self.root / "temp" / "eval.jsonl", 120)
        rows = Estimate.measured(
            build.ROWS, reading=self.a_reading_of(Subject.of_path(elsewhere))
        )
        step = Step(
            id="count",
            tool="measure_eval_set",
            why="a step costed off another file",
            arguments={"path": str(evaluation)},
            cost=Cost(
                model_tokens=Estimate.none(build.MODEL_TOKENS, because="local"),
                model_requests=rows.counted_as(
                    build.MODEL_REQUESTS, because="one each"
                ),
                wall_clock=Estimate.unknown(
                    build.WALL_CLOCK, why="never timed", find_out_by="time it"
                ),
                disk=Estimate.none(build.DISK, because="no file"),
            ),
            exit_criterion=ExitCriterion(
                stated="counted", source="tool_result", subject="exact",
                comparator="is_true",
            ),
            operates_on=Subject.of_path(evaluation),
        )
        with self.assertRaises(BuildInvalid) as raised:
            self.a_build_of(step)
        self.assertIn("a measurement of something else", str(raised.exception))

    def test_a_subject_four_derivations_deep(self):
        # route: a_subject_four_derivations_deep
        evaluation = self.the_real_eval_set()
        elsewhere = self.rows_at(self.root / "temp" / "eval.jsonl", 120)
        rows = Estimate.measured(
            build.ROWS, reading=self.a_reading_of(Subject.of_path(elsewhere))
        )
        deep = Estimate.summed(
            [
                rows.capped_at(500, because="a cap")
                .scaled_by(2, because="two passes")
                .counted_as(build.MODEL_REQUESTS, because="one each"),
                Estimate.none(build.MODEL_REQUESTS, because="a step that asks nothing"),
            ],
            dimension=build.MODEL_REQUESTS,
        )
        self.assertEqual(deep.provenance, build.INFERRED)
        self.assertEqual(
            [item.key for item in deep.subjects()], [build._path_key(elsewhere)]
        )
        with self.assertRaises(SubjectMismatch):
            deep.about(Subject.of_path(evaluation))

    # -- helpers -----------------------------------------------------------

    def a_free_cost(self) -> Cost:
        return Cost(
            model_tokens=Estimate.none(build.MODEL_TOKENS, because="local"),
            model_requests=Estimate.none(build.MODEL_REQUESTS, because="local"),
            wall_clock=Estimate.unknown(
                build.WALL_CLOCK, why="never timed", find_out_by="time it"
            ),
            disk=Estimate.none(build.DISK, because="no file"),
        )

    def a_build_of(self, *steps: Step) -> Build:
        return Build(
            id="a_plan_this_test_builds",
            title="A plan this test builds",
            for_outcome="BLOCKED__BUILD_EVAL_SET",
            because="this test needs a build",
            steps=tuple(steps),
            environment=Environment(name="t", working_dir="runs/t"),
            exit_criterion=ExitCriterion(
                stated="it finished", source="diagnosis",
                subject="fact_origins.eval_size_n", comparator="is_measured",
            ),
        )


# ---------------------------------------------------------------------------
# 4. The false-refusal routes. A wall that blocks everything is not a wall.


class TheWallDoesNotBlockTheHonestNumberTest(SubjectTestCase):
    def test_the_same_file_by_a_relative_path(self):
        # route: the_same_file_by_a_relative_path
        evaluation = self.the_real_eval_set()
        # A RELATIVE PATH CAN ONLY NAME A FILE UNDER THE WORKING DIRECTORY,
        # and on a machine whose temp lives on another volume than the
        # checkout there is no such name: `os.path.relpath` raises
        # "path is on mount 'C:', start on mount 'D:'". That is true of the
        # GitHub Windows runner, where this errored on every run. The
        # scenario is not expressible there rather than broken, so it says so.
        if os.path.splitdrive(str(evaluation))[0].lower() != (
            os.path.splitdrive(os.getcwd())[0].lower()
        ):
            self.skipTest(
                "the eval file and the working directory are on different "
                "volumes, so no relative path names this file"
            )
        relative = os.path.relpath(str(evaluation), os.getcwd())
        ok, why = Subject.of_path(evaluation).matches(Subject.of_path(relative))
        self.assertTrue(ok, why)

    def test_the_same_file_through_dot_segments(self):
        # route: the_same_file_through_dot_segments
        evaluation = self.the_real_eval_set()
        winding = evaluation.parent / "." / ".." / evaluation.parent.name / evaluation.name
        ok, why = Subject.of_path(evaluation).matches(Subject.of_path(winding))
        self.assertTrue(ok, why)

    def test_the_same_file_in_another_case(self):
        # route: the_same_file_in_another_case
        if os.path.normcase("A") != os.path.normcase("a"):
            self.skipTest(
                "this filesystem distinguishes case, so two cases are two files "
                "and folding them would be the wrong answer"
            )
        evaluation = self.the_real_eval_set()
        ok, why = Subject.of_path(evaluation).matches(
            Subject.of_path(str(evaluation).upper())
        )
        self.assertTrue(ok, why)

    def test_the_honest_number_still_gets_through(self):
        """THE POSITIVE CONTROL IN THE OTHER DIRECTION.

        A 'fix' that made every cost UNKNOWN would pass every route above and
        would have removed the one derived number this product can prove. 777
        rows, a cap of 500, one request per row: 500, INFERRED, with the file it
        was counted off named in its own derivation.
        """
        # route: the_same_file_counted_then_scored
        scored = self.the_real_eval_set(777)
        self.assertEqual(self.count_for_real(scored), 777)
        plan = self.a_baseline_for(scored)
        requests = plan.step("baseline").cost.model_requests
        self.assertEqual(requests.provenance, build.INFERRED)
        self.assertEqual(requests.value, 500.0)
        self.assertIn("counted 777 rows", requests.how)
        self.assertEqual(
            [item.key for item in requests.subjects()], [build._path_key(scored)]
        )
        # And with the count already in hand the build does not count again.
        self.assertEqual(
            [step.tool for step in plan.steps], ["measure_baseline", "run_diagnosis"]
        )


# ---------------------------------------------------------------------------
# 5. The recovery of a subject is prose, so it is pinned to what the tools write.


class TheRecoveryOfASubjectIsPinnedToWhatTheToolsWriteTest(SubjectTestCase):
    """`app/tools/evidence.py` has no column for what a measurement was of.

    So the subject of a stored fact is read out of the derivation the measuring
    tool wrote. That is a parser over prose and it will stop matching the day
    somebody rewords a `how`. This is what makes that loud: both live minting
    tools are driven through the real registry and the recovery must work.
    """

    def a_recovered_subject(self, thread: int) -> Subject | None:
        rows = [
            row
            for row in evidence.rows_for(thread)
            if row["fact"] == "eval_size_n" and row["origin"] == evidence.MEASURED
        ]
        self.assertTrue(rows, "nothing stamped eval_size_n MEASURED")
        return propose.subject_of_a_recorded_measurement(rows[-1]["how"])

    def test_measure_eval_set_writes_a_derivation_the_subject_can_be_read_from(self):
        evaluation = self.the_real_eval_set(50)
        self.count_for_real(evaluation, thread=61)
        recovered = self.a_recovered_subject(61)
        self.assertIsNotNone(recovered, "measure_eval_set reworded its `how`")
        self.assertEqual(recovered.key, build._path_key(evaluation))

    def test_profile_dataset_writes_a_derivation_the_subject_can_be_read_from(self):
        evaluation = self.the_real_eval_set(50)
        support.a_conversation(62)
        result = REGISTRY.call(
            "profile_dataset",
            {"path": str(evaluation), "split": "eval"},
            actor=evidence.USER,
            thread_id=62,
        )
        self.assertTrue(result.get("ok"), result)
        recovered = self.a_recovered_subject(62)
        self.assertIsNotNone(recovered, "profile_dataset reworded its `how`")
        self.assertEqual(recovered.key, build._path_key(evaluation))

    def test_a_recovered_subject_now_carries_the_witness_the_ledger_kept(self):
        """REWRITTEN. This asserted the opposite - "carries no witness and says
        so" - and it was right when nothing recorded what the file looked like
        at the moment of the count. `build.counted_rows_how` now writes that
        into the derivation, so the limit is closed and the test that named it
        has to move with it rather than be loosened.

        The witness is legitimate here for the reason `of_recorded_path`
        refuses to stat: it was written AT THE COUNT, so it describes the file
        as it was then. A witness taken now would certify itself.
        """
        evaluation = self.the_real_eval_set(50)
        self.count_for_real(evaluation, thread=63)
        recovered = self.a_recovered_subject(63)
        self.assertRegex(recovered.witness, r"^\d+ bytes, modified \d+$")
        self.assertIn("recovered from the derivation", recovered.how)
        self.assertIn("when it was counted", recovered.how)
        ok, why = Subject.of_path(evaluation).matches(recovered)
        self.assertTrue(ok, why)

    def test_a_row_written_before_the_witness_clause_still_recovers(self):
        """Every derivation already in a ledger has no semicolon and runs to
        the end of the string. Those rows must keep working, matched by
        identity and date exactly as they were."""
        evaluation = self.the_real_eval_set(50)
        old_style = f"counted 50 rows in {evaluation}"
        recovered = propose.subject_of_a_recorded_measurement(old_style)
        self.assertIsNotNone(recovered)
        self.assertEqual(recovered.key, build._path_key(evaluation))
        self.assertEqual(recovered.witness, "")
        self.assertIn("no witness", recovered.how)

    def test_a_file_changed_after_the_count_is_caught_by_the_witness(self):
        """THE CASE THIS EXISTS FOR. Count a file, change it, and the record
        still names what it was: the recovered witness and the live one differ,
        which is how a reader of an export can tell that the file in front of
        them is not the file the number came from."""
        evaluation = self.the_real_eval_set(50)
        self.count_for_real(evaluation, thread=64)
        recovered = self.a_recovered_subject(64)

        with open(evaluation, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"q": "one more", "a": "row"}) + chr(10))

        live = Subject.of_path(evaluation)
        self.assertNotEqual(
            recovered.witness,
            live.witness,
            "the file changed and the record did not notice",
        )
        ok, why = live.matches(recovered)
        self.assertFalse(ok, "a changed file matched a measurement of the old one")
        # The refusal names both readings rather than the mechanism, which is
        # the sentence a reader can act on: "the same path and not the same
        # file: it was N bytes ... when that was measured and it is M bytes ...
        # now".
        self.assertIn("not the same file", why.lower())
        self.assertIn("when that was measured", why.lower())


# ---------------------------------------------------------------------------
# 6. The sweep: every step of every build every proposer can produce.


class NoShippedProposalIsCostedOffSomethingElseTest(SubjectTestCase):
    """Read `TheDetectorProvesItselfTest` first. This sweep is only worth what
    that control is worth."""

    def every_build(self) -> list[Build]:
        evaluation = self.the_real_eval_set(60)
        builds: list[Build] = []

        builds.append(
            propose.propose(
                self.situation(
                    FACTS_THAT_STOP_AT_G0, thread=71, eval_path=str(evaluation)
                )
            )
        )
        builds.append(
            propose.propose(
                self.situation(
                    {**FACTS_THAT_REACH_THE_BASELINE, "eval_size_n": 400},
                    thread=72,
                    actor=evidence.MODEL,
                    eval_path=str(evaluation),
                    input_field="q",
                    expected_field="a",
                )
            )
        )

        self.count_for_real(evaluation, thread=73)
        builds.append(
            propose.propose(
                self.situation(
                    FACTS_THAT_REACH_THE_BASELINE,
                    thread=73,
                    eval_path=str(evaluation),
                    input_field="q",
                    expected_field="a",
                )
            )
        )
        builds.append(
            propose.propose(
                self.situation(
                    {
                        "goal_text": "route tickets",
                        "target_score": 0.9,
                        "baseline_measured": True,
                        "baseline_score": 0.5,
                    },
                    thread=73,
                    dataset_path=str(evaluation),
                )
            )
        )
        # THE ROW COUNT. One step, `profile_dataset`, costed off the table it
        # opens - which is the property this whole file sweeps for. It is the
        # newest build and the cheapest, and it is here because a one-step plan
        # is exactly where a subject naming the wrong file would go unnoticed.
        builds.append(
            propose.propose(
                self.situation(
                    {
                        "goal_text": "route tickets",
                        "target_score": 0.9,
                        "baseline_measured": True,
                        "baseline_score": 0.5,
                        "modality": "tabular",
                        "task_family": "classification",
                        "labeled_examples_n": 400,
                        "eval_size_n": 40,
                    },
                    thread=73,
                    dataset_path=str(evaluation),
                )
            )
        )
        # THE METRIC. One local step, costed off the eval file it opens.
        # `bench_situation` for the reason it documents: a MEASURED
        # `failure_histogram` cannot be minted without a model, and a stated one
        # is challenged into ACTION__SUBSTANTIATE_CLAIMED_FACTS instead - which
        # would have quietly appended a SECOND copy of that build here while the
        # count still matched.
        builds.append(
            propose.propose(
                self.bench_situation(
                    {"wrong_style": 30},
                    outcome="ACTION__MAKE_THE_METRIC_PROGRAMMATIC",
                    thread=73,
                    facts={
                        "metric_is_programmatic": diagnosis.measured(False),
                        "prompt_optimizer_tried": diagnosis.stated(False),
                    },
                    eval_path=str(evaluation),
                    input_field="q",
                    expected_field="a",
                )
            )
        )
        # The three the eval and prompt benches unlocked. Thread 73 already
        # carries a real counted `eval_size_n`, so these are costed off a
        # measurement rather than off nothing - which is what makes them worth
        # putting through this file's checks at all.
        builds.append(
            propose.propose(
                self.bench_situation(
                    {},
                    outcome="ACTION__CLASSIFY_FAILURES",
                    thread=73,
                    eval_path=str(evaluation),
                    input_field="q",
                    expected_field="a",
                )
            )
        )
        builds.append(
            propose.propose(
                self.bench_situation(
                    {"wrong_style": 30},
                    outcome="NO_TRAIN__BETTER_PROMPT",
                    thread=73,
                    facts={"prompt_iterations": 0},
                    eval_path=str(evaluation),
                    input_field="q",
                    expected_field="a",
                    prompt="Answer with the label only, in lower case.",
                )
            )
        )
        builds.append(
            propose.propose(
                self.bench_situation(
                    {"wrong_style": 30},
                    outcome="NO_TRAIN__FEW_SHOT",
                    thread=73,
                    facts={"prompt_iterations": 3, "fewshot_tried": False},
                    eval_path=str(evaluation),
                    input_field="q",
                    expected_field="a",
                )
            )
        )

        # THE TWO THE RETRIEVAL BENCH UNLOCKED. Guarded by the same question
        # `propose.PROPOSERS` asks - `app/tools/retrieval.py` registers the three
        # tools these steps name, and while it is absent there is no proposer for
        # the sweep to cover and the identity below still holds exactly. The
        # questions file is counted for real in this thread first, so the
        # subject-matching this whole file is about decides whether the plan
        # counts again, off a measurement of THIS file rather than of the eval
        # set the earlier builds used.
        if propose.the_retrieval_bench_is_registered():
            corpus = self.a_corpus()
            questions = self.questions_at(self.root / "real" / "questions.jsonl")
            self.count_for_real(questions, thread=73)
            for outcome in ("NO_TRAIN__RAG", "ACTION__MEASURE_RETRIEVER_RECALL"):
                builds.append(
                    propose.propose(
                        self.retrieval_situation(
                            outcome,
                            thread=73,
                            corpus_path=str(corpus),
                            eval_path=str(questions),
                            input_field="q",
                            expected_field="doc",
                        )
                    )
                )

        # THE ONE THE CHUNKING SWEEP UNLOCKED, behind the same registry question.
        if propose.the_chunking_sweep_is_registered():
            builds.append(
                propose.propose(
                    self.retrieval_situation(
                        "NO_TRAIN__FIX_RETRIEVAL",
                        thread=73,
                        corpus_path=str(self.a_corpus("bottleneck")),
                        eval_path=str(
                            self.questions_at(self.root / "real" / "questions.jsonl")
                        ),
                        input_field="q",
                        expected_field="doc",
                        chunk_settings=(400, 900, 2000),
                    )
                )
            )

        # THE ONE THE TRAINING BENCH UNLOCKED, behind the same registry question
        # and with the backend staged, because the build refuses unless the
        # recipe the engine hands off to is BUILT on this machine and a test
        # sandbox ships a recipes tree with nothing pinned in it.
        #
        # IT CARRIES NO MEASURED COST AT ALL, and that is the honest state of it
        # rather than an omission: no step of it scores a row, so there is no
        # per-row arithmetic to derive and nothing for this file's checks to
        # bite on. It is swept anyway, because the identity below is what stops
        # a proposer being added without every check in this file running over
        # it - and the day a step of this build IS costed off a count, it is
        # already here.
        if propose.the_training_bench_is_registered():
            support.pin_a_training_recipe(propose.THE_LORA_RECIPE)
            # AND THE EVAL SET IS COUNTED AGAIN HERE, which is this whole file's
            # thesis happening live rather than an inconvenience. The retrieval
            # builds above counted `questions.jsonl` in this same thread, so the
            # newest `eval_size_n` row is a count of THAT file - and the training
            # build refuses to plan a GPU run against a count of a file it is
            # not going to score. Counting the eval set again is what makes the
            # winning row a count of the right thing.
            self.count_for_real(evaluation, thread=73)
            builds.append(
                propose.propose(
                    self.training_situation(
                        thread=73,
                        dataset_path=str(
                            self.training_data_at(self.root / "real" / "train.jsonl")
                        ),
                        eval_path=str(evaluation),
                        base_model="Qwen/Qwen3-4B",
                        max_seq_len=512,
                    )
                )
            )

        # THE SECOND TRAINING BACKEND, behind the same registry question, with
        # its OWN recipe staged - a separate pinned environment from the
        # supervised one, which is the whole reason `the_recipe_on_this_machine`
        # takes a name. It carries no measured cost either, and is swept for the
        # identity check for the same reason the one above is.
        if propose.the_training_bench_is_registered():
            support.pin_a_training_recipe(propose.THE_DPO_RECIPE)
            _pairs = self.preference_data_at(self.root / "real" / "pairs.jsonl")
            # COUNTED THROUGH THE REAL INSTRUMENT, in this thread, so the row
            # the build reads is the one `count_preference_pairs` wrote. The
            # eval set was counted again above for the same reason: a build that
            # plans a GPU run against a count of the wrong file is the defect
            # this whole file is about.
            self.count_pairs_for_real(_pairs, thread=73)
            builds.append(
                propose.propose(
                    self.preference_situation(
                        thread=73,
                        dataset_path=str(_pairs),
                        eval_path=str(evaluation),
                        base_model="Qwen/Qwen3-4B",
                        max_seq_len=512,
                        adapter_dir=str(
                            self.sft_adapter_at(self.root / "real" / "sft_adapter")
                        ),
                    )
                )
            )

        # THE ONE THE TREE FIT UNLOCKED, behind the same registry question. Like
        # the training build it carries no measured cost - no step of it scores
        # a row, so there is no per-row arithmetic to derive - and it is swept
        # for the same reason: the identity below is what stops a proposer being
        # added without every check in this file running over it, and the day a
        # step of this build IS costed off a count it is already here.
        if propose.the_tabular_bench_is_registered():
            builds.append(
                propose.propose(
                    self.tabular_situation(
                        thread=73,
                        dataset_path=str(
                            self.table_at(self.root / "real" / "table.csv")
                        ),
                        expected_field="label",
                    )
                )
            )

        # THE ONE THE AGENT INSTRUMENTS UNLOCKED, on the second ledger. Swept
        # like the rest so a proposer cannot arrive without every check in
        # this file running over it - including these, whose subject is that
        # a measured cost names what it runs on.
        if propose.the_agent_instruments_are_registered():
            _ai = diagnosis.spec_at("docs/ledgers/ai_engineering.yaml")
            for _from_zero in (False, True):
                _raw = {
                    "failing_cases_n": 12,
                    "can_rerun_failures": True,
                    "failure_rate_measured": True,
                    "baseline_success_rate": 1 / 12,
                    "target_success_rate": 0.9,
                    "failure_reproduces": True,
                    "has_traces": True,
                    "tokens_per_run": 250.0,
                    "run_terminates": True,
                    "simple_version_tried": True,
                    "workflow_tried": True,
                    "tool_count": 0 if _from_zero else 3,
                    "tool_call_success_rate": None if _from_zero else 2 / 3,
                    "control_flow_is_dynamic": True,
                    "one_context_is_insufficient": False,
                    "failure_buckets": (
                        {"tool_choice": 12}
                        if _from_zero
                        else {"reasoning": 9, "format": 1, "tool_execution": 1}
                    ),
                }
                _origin = {
                    "inspect": diagnosis.MEASURED,
                    "derive": diagnosis.MEASURED,
                    "ask": diagnosis.STATED,
                }
                _sheet = {
                    n: diagnosis.Fact(v, _origin[_ai.facts[n]["source"]])
                    for n, v in _raw.items()
                }
                _result = diagnosis.diagnose(_sheet, _ai)
                builds.append(
                    propose.propose(
                        propose.Situation(
                            outcome=_result.outcome,
                            result=_result,
                            values={
                                n: getattr(f, "value", f) for n, f in _sheet.items()
                            },
                            origins=dict(_result.fact_origins),
                            traces_path=str(
                                HERE_FIXTURES / "journey-traces.jsonl"
                            ),
                            failures_path=str(
                                HERE_FIXTURES / "journey-failures.jsonl"
                            ),
                            tooldefs_path=str(
                                HERE_FIXTURES / "journey-tools.json"
                            ),
                            input_field="input",
                            expected_field="expected",
                            answer_field="answer",
                        )
                    )
                )
            # MULTI_AGENT - hardest by design, same measurement core, one extra ladder rung
            _raw = {
                "failing_cases_n": 12,
                "can_rerun_failures": True,
                "failure_rate_measured": True,
                "baseline_success_rate": 1 / 12,
                "target_success_rate": 0.9,
                "failure_reproduces": True,
                "has_traces": True,
                "tokens_per_run": 250.0,
                "run_terminates": True,
                "simple_version_tried": True,
                "workflow_tried": True,
                "single_agent_tried": True,
                "tool_count": 3,
                "tool_call_success_rate": 2 / 3,
                "control_flow_is_dynamic": True,
                "one_context_is_insufficient": True,
                "failure_buckets": {"reasoning": 9, "format": 1, "tool_execution": 1},
            }
            _origin = {
                "inspect": diagnosis.MEASURED,
                "derive": diagnosis.MEASURED,
                "ask": diagnosis.STATED,
            }
            _sheet = {
                n: diagnosis.Fact(v, _origin[_ai.facts[n]["source"]])
                for n, v in _raw.items()
            }
            _result = diagnosis.diagnose(_sheet, _ai)
            builds.append(
                propose.propose(
                    propose.Situation(
                        outcome=_result.outcome,
                        result=_result,
                        values={
                            n: getattr(f, "value", f) for n, f in _sheet.items()
                        },
                        origins=dict(_result.fact_origins),
                        traces_path=str(HERE_FIXTURES / "journey-traces.jsonl"),
                        failures_path=str(HERE_FIXTURES / "journey-failures.jsonl"),
                        tooldefs_path=str(HERE_FIXTURES / "journey-tools.json"),
                        input_field="input",
                        expected_field="expected",
                        answer_field="answer",
                    )
                )
            )

        # THE FOUR SECOND-LEDGER ACTION__/BLOCKED__ BUILDS, wired 2026-08-27.
        # This sweep is about a cost that names its own subject, and these four
        # are exactly the shape it exists for: each one's steps run over a file
        # the PERSON named, so a cost taken off anything else would be a
        # measurement of the wrong thing. They are called directly rather than
        # through `propose.propose` because an ACTION__ is what the engine says
        # when a fact is MISSING - minting each one would need a fact sheet
        # built to be incomplete in one specific way, and the situation below
        # is the same shape the walk would hand them. See the twin fixture in
        # tests/test_the_proposal_is_executable.py.
        _agent_paths = {
            "ACTION__BUILD_AN_EVAL_HARNESS": {"failures_path": True},
            "ACTION__MEASURE_THE_BASELINE": {"failures_path": True},
            "BLOCKED__NO_TRACES": {"trace_path": True},
            "ACTION__CLASSIFY_THE_FAILURES": {"trace_path": True, "failures_path": True},
        }
        for _outcome, _wants in _agent_paths.items():
            if _outcome not in propose.PROPOSERS:
                continue
            _kw: dict[str, str] = {}
            if _wants.get("trace_path"):
                _kw["trace_path"] = str(HERE_FIXTURES / "journey-traces.jsonl")
            if _wants.get("failures_path"):
                _kw["failures_path"] = str(HERE_FIXTURES / "journey-failures.jsonl")
                _kw["input_field"] = "input"
                _kw["expected_field"] = "expected"
                _kw["answer_field"] = "answer"
            builds.append(
                propose.PROPOSERS[_outcome](
                    propose.Situation(
                        outcome=_outcome,
                        result=diagnosis.diagnose(
                            {}, diagnosis.spec_at("docs/ledgers/ai_engineering.yaml")
                        ),
                        **_kw,
                    )
                )
            )

        # THE SIX WORKBENCH BUILDS, and this sweep is the one that had to be
        # satisfied before they could exist. Each draws TWO legs that call the
        # same tool on two different answer files over one question set, and
        # what settles which file a leg is costed from is `run_the_failures`
        # declaring `subject=("failures_path",)` - the field
        # `app/build.py::declared_subject_arguments` had specified and the
        # registry had not yet grown. Before that declaration this build could
        # not be validated at all, which is how the gap was found.
        if propose.the_paired_proof_is_possible():
            _after = self.root / "after" / "answers.jsonl"
            _after.parent.mkdir(parents=True, exist_ok=True)
            _rows = [
                json.loads(line)
                for line in (HERE_FIXTURES / "journey-failures.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]
            for _row in _rows:
                _row["answer"] = _row["expected"]
            _after.write_text(
                "\n".join(json.dumps(_row) for _row in _rows) + "\n", encoding="utf-8"
            )
            for _outcome in sorted(propose._PROPOSERS_THE_PAIRED_PROOF_BRINGS):
                builds.append(
                    propose.PROPOSERS[_outcome](
                        propose.Situation(
                            outcome=_outcome,
                            result=diagnosis.diagnose(
                                {},
                                diagnosis.spec_at("docs/ledgers/ai_engineering.yaml"),
                            ),
                            failures_path=str(HERE_FIXTURES / "journey-failures.jsonl"),
                            after_answers_path=str(_after),
                            input_field="input",
                            expected_field="expected",
                            answer_field="answer",
                        )
                    )
                )

        # THE FORMAT METER, and this sweep is one it has to satisfy: its count
        # step is costed from a measurement of the outputs file, so a subject
        # naming anything else would be a real number about a different file.
        # `measure_the_format` declares `subject=("path",)` - it takes two paths
        # and only one of them is the thing being counted.
        if propose.the_format_can_be_measured():
            _format = HERE_FIXTURES.parent / "format"
            builds.append(
                propose.PROPOSERS["ACTION__MEASURE_THE_FORMAT"](
                    propose.Situation(
                        outcome="ACTION__MEASURE_THE_FORMAT",
                        result=diagnosis.diagnose({}, diagnosis.default_spec()),
                        outputs_path=str(_format / "outputs.jsonl"),
                        schema_path=str(_format / "schema.json"),
                    )
                )
            )


        # THE CANDIDATE SCORER'S TWO OUTCOMES. Both take the same proposer and
        # differ only in the question at the end, so both are drawn here - the
        # roster counts PROPOSERS entries, not distinct functions, and a build
        # that is never drawn is a build nothing checks.
        #
        # A real completed eval run has to exist first: this proposer REFUSES
        # without one, because a candidate's score is only worth having as a
        # paired comparison against the same rows.
        support.a_completed_eval_run(73, evaluation)
        for _outcome in ("NO_TRAIN__SWAP_MODEL", "NO_TRAIN__USE_EXISTING_BASE"):
            builds.append(
                propose.PROPOSERS[_outcome](
                    propose.Situation(
                        outcome=_outcome,
                        result=diagnosis.diagnose(
                            dict(diagnosis_fixtures.REACHING["NO_TRAIN__USE_EXISTING_BASE"])
                        ),
                        eval_path=str(evaluation),
                        input_field="q",
                        expected_field="a",
                        base_model="Qwen/Qwen3-4B",
                        thread_id=73,
                    )
                )
            )

        # THE THIRD LEDGER'S TWELVE, drawn from its own driven fixtures. A loop
        # over PROPOSERS rather than a written list, so the next harness outcome
        # arrives in this sweep by existing.
        if propose.the_harness_bench_is_registered():
            builds.extend(_harness_builds(self))

        self.assertEqual(len(builds), len(propose.PROPOSERS))
        return builds

    def test_no_step_of_any_proposal_is_costed_off_another_thing(self):
        for plan in self.every_build():
            for step in plan.steps:
                self.assertEqual(
                    foreign_subjects(step), [], f"{plan.id}.{step.id}"
                )

    def test_every_measured_cost_in_every_proposal_says_what_it_runs_on(self):
        for plan in self.every_build():
            for step in plan.steps:
                measured = [
                    item
                    for estimate in step.cost.estimates
                    for item in estimate.subjects()
                ]
                if measured:
                    self.assertIsNotNone(
                        step.operates_on, f"{plan.id}.{step.id} is costed blind"
                    )

    def test_a_declared_subject_is_always_named_by_the_call_itself(self):
        for plan in self.every_build():
            for step in plan.steps:
                if step.operates_on is None:
                    continue
                named = [
                    value
                    for value in step.arguments.values()
                    if isinstance(value, str)
                    and value.strip()
                    and build._path_key(value) == step.operates_on.key
                ]
                self.assertTrue(
                    named,
                    f"{plan.id}.{step.id} declares {step.operates_on.key} and no "
                    "argument names it",
                )


# ---------------------------------------------------------------------------
# 7. The count.


class TheRouteListIsCompleteTest(unittest.TestCase):
    def test_every_route_is_named_and_the_count_is_pinned(self):
        self.assertEqual(len(ROUTES), ROUTES_CLOSED)

    def test_every_route_has_a_reason_a_person_can_read(self):
        for name, reason in ROUTES.items():
            self.assertGreater(len(reason), 30, name)

    def test_every_named_route_has_a_test_that_marks_it(self):
        """A route in the list with nothing marking it is a route nobody runs."""
        marker = re.compile(r"^\s*# route: ([a-z0-9_]+)\s*$")
        marked = {
            found.group(1)
            for found in (
                marker.match(line)
                for line in Path(__file__).read_text(encoding="utf-8").splitlines()
            )
            if found
        }
        self.assertEqual(marked, set(ROUTES), marked.symmetric_difference(ROUTES))


if __name__ == "__main__":
    unittest.main()
