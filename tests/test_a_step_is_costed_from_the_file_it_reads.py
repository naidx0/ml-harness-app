"""The subject check guessed which argument was the subject. Twelve ways past it.

## Why this file exists, beside the one that already covers subjects

`tests/test_a_measurement_carries_its_subject.py` closed nineteen ways for a
real measurement of the WRONG THING to reach a proposal's cost. Its wall was
three checks in `Build._validate_subject`, and the third of them said: *the
subject a step declares must be named by one of the step's own arguments.*

**That third check was the first defect reproduced through its own fix.** It
scanned EVERY string argument for one that matched, which is an existence test
where an identity test was needed. So:

    arguments = {"eval_path": <a 777-row file>,
                 "input_field": "q",
                 "expected_field": <a 120-row file>,   # a COLUMN NAME to the tool
                 "sample": 500}
    operates_on = <the 120-row file>
    cost        = a genuine, ledger-stamped count of the 120-row file

Every check passed. The plan a person would have approved said **"120 requests
(inferred) - counted 120 rows in ...\\temp\\eval.jsonl; capped at 500"**, for a
step that opens the 777-row file and makes 500 requests. A four-fold
understatement, an impeccable provenance chain, and the wrong file - reached
through the door that was built to stop exactly that.

`TheOldRuleIsShownToPassTest` is the control for all of it: it reimplements the
previous check and requires it to ACCEPT the step above. A test file that only
showed the new rule refusing would be indistinguishable from a test file whose
attack was never possible.

## What is being defended, in one sentence

**A step is costed from the file it reads, and which file it reads is the
TOOL's statement, not this repository's guess.** `app/build.py`'s
`subject_of_a_call` asks the tool - `ToolSpec.subject`, the field
`declared_subject_arguments` specifies - and where the tool has not said, it
refuses to pick: it answers only when every argument that could be naming a
path names the SAME one. A call with nothing to guess between needs no guess; a
call with two files and no declaration is reported as undecidable, and
`app/tools/propose.py` turns that into an UNKNOWN cost with a step that goes
and counts.

**`ToolSpec.subject` shipped on 2026-08-27**, and it shipped because a build
needed it rather than because this file asked. `run_the_failures` takes three
arguments that can name a file - the failure set, the answers, the traces - so
the fallback above could decide nothing about it, and the workbench's 'after'
leg was refused outright until the tool said which one it opens. That is the
fallback behaving exactly as designed: it did not guess, and the missing
declaration surfaced as a refusal a person could read.
`TheDeclarationIsCheckedAtRegistrationTest` below is the wall on the
declaration itself.

## The routes, and where they came from

Three groups, and the middle one is the one that matters most:

* **DISCLOSED** - the hidden-path case as it was reported, and the stale-count
  case disclosed beside it (a subject recovered from the ledger carried no
  witness, so a file wholly replaced since it was counted still passed).
* **FOUND BY ATTACKING THE FIX** - four routes nobody reported, each of which
  was open in the first version of this fix and each of which is now closed in
  `app/build.py`. A fix that was only tested against the reported case would
  have shipped all four.
* **FALSE REFUSAL** - the opposite failure. A check that refuses every honest
  proposal is not a check, it is a product that says "I cannot cost this" to
  somebody who did the work. The honest number must still come out, and it does:
  500 requests, inferred, off a count of the file the step opens.

## The two mistakes this file must not make

1. **Being green because the attack was impossible.** Hence
   `TheOldRuleIsShownToPassTest`, which proves the attack passed the previous
   rule, and `test_the_number_it_would_have_shown`, which puts the wrong number
   on screen.
2. **Asserting the refusal instead of the product.** A raise is not a person
   being told the truth. So the product routes assert the ESTIMATE the person
   reads and the STEPS the plan actually contains.

## The pinned count

`ROUTES` names every route, `ROUTES_CLOSED` says how many are closed, and
`TheRouteListIsCompleteTest` asserts the list against the `# route:` markers, so
a route cannot be added without a decision or deleted without one.
"""

from __future__ import annotations

import json
import os
import re
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from app import build, db, diagnosis, events
from app.build import (
    Build,
    BuildInvalid,
    Cost,
    Environment,
    Estimate,
    ExitCriterion,
    Output,
    Reading,
    Ref,
    Risk,
    Step,
    Subject,
)
from app.tools import REGISTRY, evidence, propose

import support


# ---------------------------------------------------------------------------
# The routes.

ROUTES: dict[str, str] = {
    # DISCLOSED.
    "the_path_hidden_in_a_column_name": (
        "eval_path names the 777-row file, expected_field names the 120-row "
        "file, operates_on declares the 120-row file and the cost is a real "
        "count of it. The reported case: three checks, three passes, 120 "
        "requests shown for a step that makes 500."
    ),
    "the_file_replaced_since_it_was_counted": (
        "a genuine count of this very path, taken before the file was thrown "
        "away and rewritten. Identity matches, because it is the same name. "
        "Disclosed and unfixed; the ledger's own date is what closes it."
    ),
    # FOUND BY ATTACKING THE FIX. Each was open after the first version of it.
    "a_reference_where_no_tool_declared_the_reader": (
        "eval_path comes from an earlier step's output, so the only literal "
        "path left in the call is the decoy - which the ambiguity rule then "
        "read as 'the file this step operates on'. A cost pinned to a file "
        "chosen before the plan runs, for a step that opens one chosen during."
    ),
    "a_decoy_that_is_not_there_yet": (
        "eval_path names a bare filename that exists nowhere, so it is not a "
        "path by existence and not a path by separator - and the call reads as "
        "unambiguous. The file appears between the proposal and the approval."
    ),
    "a_subject_of_another_kind": (
        "the reading and the declaration are both a SUBJECT_DATASET whose key "
        "is the counted file, so the check that compares paths returns early "
        "and never looks at the call. The cheapest way past a check is to be a "
        "kind it does not compare."
    ),
    "a_decoy_inside_an_object_argument": (
        "the second path is a value inside an `object` argument rather than an "
        "argument itself, so a scan of the top level sees one path and calls "
        "the call unambiguous. `propose_build` takes both a path and an object "
        "with no declared keys, so this is reachable through the shipped "
        "registry rather than hypothetical."
    ),
    # THE DECLARATION - what this file asks app/tools/registry.py for.
    "the_declaration_decides_which_argument": (
        "with subject=('eval_path',) on measure_baseline the hidden path is not "
        "a candidate at all, and the refusal names the argument the tool reads."
    ),
    "a_declaration_is_consulted_rather_than_decoration": (
        "declaring subject=('expected_field',) makes an HONEST build refuse. A "
        "declaration nothing reads would leave it passing."
    ),
    # FALSE REFUSAL - these must all be ACCEPTED.
    "a_second_path_beside_a_declared_subject": (
        "a call carrying another real file in an argument the tool does not "
        "read is nobody's business once the tool has said which one it reads. "
        "This must PASS, or the declaration buys nothing."
    ),
    "the_same_file_named_twice_in_one_call": (
        "two arguments, one file. One path key, nothing to guess between, and "
        "no refusal."
    ),
    "an_ordinary_column_name_beside_a_path": (
        "input_field='q' and expected_field='a' are not paths and never become "
        "ones. The whole product would stop if they did."
    ),
    "the_honest_count_of_the_file_that_gets_scored": (
        "the positive control: count the file the step opens and the proposal "
        "says 500 requests, inferred. A fix that made every cost unknown would "
        "pass every other test in this file and fail this one."
    ),
}

ROUTES_CLOSED = 12


# ---------------------------------------------------------------------------
# THE CONTROL. The rule that was there before, reimplemented so it can be shown
# accepting the thing the rule that is there now refuses.


def the_previous_rule_accepts(step: Step) -> bool:
    """`Build._validate_subject` as it stood before this run, exactly.

    Copied out of the commit rather than described: *the subject a step declares
    must be named by one of the step's own literal string arguments.* Any of
    them. That is the whole of it, and the whole of the defect.
    """
    if step.operates_on is None or step.operates_on.kind != build.SUBJECT_PATH:
        return True
    for value in step.arguments.values():
        if isinstance(value, str) and value.strip():
            try:
                if build._path_key(value) == step.operates_on.key:
                    return True
            except build.CostError:  # pragma: no cover
                continue
    return False


FACTS_THAT_REACH_THE_BASELINE = {
    "goal_text": "route support tickets",
    "modality": "text",
    "task_family": "classification",
    "need_type": ["behaviour"],
    "target_score": 0.9,
}


class SubjectArgumentTestCase(unittest.TestCase):
    """Its own database, its own directory, and its own conversation.

    The conversation is not decoration: a fact is scoped to a thread, and a
    thread id that names no conversation is refused by the ledger. A test that
    filed its rows against thread 1 on an empty database would be exercising a
    route the product closed.
    """

    def setUp(self):
        self.root = support.sandbox(self)
        self.thread = self.a_conversation("the first")

    # -- scaffolding -------------------------------------------------------

    def a_conversation(self, name: str) -> int:
        project = db.create_project(f"project-{name}")
        return int(events.create_thread(name, project_id=project["id"])["id"])

    def rows_at(self, path: Path, rows: int) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(
                json.dumps({"q": f"question {i}", "a": "yes"}) for i in range(rows)
            ),
            encoding="utf-8",
        )
        return path

    def the_file_that_gets_scored(self, rows: int = 777) -> Path:
        return self.rows_at(self.root / "real" / "eval.jsonl", rows)

    def the_file_that_was_counted(self, rows: int = 120) -> Path:
        return self.rows_at(self.root / "temp" / "eval.jsonl", rows)

    def count_for_real(self, path: Path, thread: int | None = None) -> int:
        """`eval_size_n` genuinely MEASURED, by the real tool, in the real ledger."""
        result = REGISTRY.call(
            "measure_eval_set",
            {"path": str(path), "finish_the_count": True},
            actor=evidence.USER,
            thread_id=self.thread if thread is None else thread,
        )
        self.assertTrue(result.get("exact"), result)
        return int(result["rows"])

    def propose_through_the_tool(self, **arguments) -> dict:
        """The whole product path, so `recorded_at` is filled the way it is live."""
        return REGISTRY.call(
            "propose_build",
            {"facts": dict(FACTS_THAT_REACH_THE_BASELINE), **arguments},
            actor=evidence.USER,
            thread_id=self.thread,
        )

    # -- the pieces a hand-built step needs --------------------------------

    def a_count_of(self, path: Path, rows: int) -> Estimate:
        """The pre-fix arithmetic: a real count, capped, read one for one."""
        return (
            Estimate.measured(
                build.ROWS,
                reading=Reading.of_measured_fact(
                    "eval_size_n",
                    rows,
                    diagnosis.MEASURED,
                    f"counted {rows} rows in {build._path_key(path)}",
                    subject=Subject.of_recorded_path(
                        path, how="recovered from the derivation the ledger recorded"
                    ),
                ),
            )
            .capped_at(500, because="measure_baseline scores at most sample=500 rows")
            .counted_as(
                build.MODEL_REQUESTS, because="one request per row it scores"
            )
        )

    def a_cost_costing(self, requests: Estimate) -> Cost:
        return Cost(
            model_tokens=Estimate.unknown(
                build.MODEL_TOKENS, why="no tokenizer here", find_out_by="run a sample"
            ),
            model_requests=requests,
            wall_clock=Estimate.unknown(
                build.WALL_CLOCK, why="never timed", find_out_by="time one run"
            ),
            disk=Estimate.none(build.DISK, because="it writes no file"),
        )

    def a_scoring_step(self, arguments: dict, cost: Cost, operates_on) -> Step:
        return Step(
            id="baseline",
            tool="measure_baseline",
            why="Score what you already have on your own eval set.",
            arguments=arguments,
            produces=(
                Output("score", "number", "what it scored", at="baseline_score"),
            ),
            cost=cost,
            exit_criterion=ExitCriterion(
                stated="the model is scored on your eval rows",
                source="tool_result",
                subject="ok",
                comparator="is_true",
            ),
            operates_on=operates_on,
        )

    def a_build_of(self, *steps: Step) -> Build:
        return Build(
            id="a_plan_under_test",
            title="A plan this test builds",
            for_outcome="ACTION__MEASURE_BASELINE",
            because="this test needs a plan",
            steps=tuple(steps),
            environment=Environment(
                name="under_test",
                working_dir="runs/proposals/under_test",
                egress=True,
                egress_reason="scoring sends rows of the eval set to the model",
            ),
            exit_criterion=ExitCriterion(
                stated="baseline_measured is MEASURED",
                source="diagnosis",
                subject="fact_origins.baseline_measured",
                comparator="is_measured",
            ),
            risks=(Risk(what="it scores badly", what_we_do="that is the plan working"),),
        )

    # -- the attack itself, in one place -----------------------------------

    def the_hidden_path_step(self) -> tuple[Step, Path, Path]:
        """`eval_path` on the big file, the small file's path in `expected_field`."""
        scored = self.the_file_that_gets_scored()
        counted = self.the_file_that_was_counted()
        step = self.a_scoring_step(
            arguments={
                "eval_path": str(scored),
                "input_field": "q",
                # A COLUMN NAME, as far as measure_baseline is concerned.
                "expected_field": str(counted),
                "sample": 500,
            },
            cost=self.a_cost_costing(self.a_count_of(counted, 120)),
            operates_on=Subject.of_path(counted),
        )
        return step, scored, counted


# ---------------------------------------------------------------------------
# 1. The control. Nothing below means anything without this.


class TheOldRuleIsShownToPassTest(SubjectArgumentTestCase):
    """A procedure that returns green against known-broken code certifies nothing."""

    def test_the_previous_rule_accepts_the_hidden_path_step(self):
        """THE CONTROL. If this ever fails, every refusal in this file is vacuous."""
        step, _scored, _counted = self.the_hidden_path_step()
        self.assertTrue(
            the_previous_rule_accepts(step),
            "the attack no longer passes the rule it was found in, so this file "
            "is proving nothing",
        )

    def test_the_previous_rule_is_not_a_function_that_says_yes(self):
        """The other half: the reimplemented rule must still refuse something."""
        step, scored, counted = self.the_hidden_path_step()
        blind = self.a_scoring_step(
            arguments={"eval_path": str(scored), "input_field": "q", "expected_field": "a"},
            cost=self.a_cost_costing(self.a_count_of(counted, 120)),
            operates_on=Subject.of_path(counted),
        )
        self.assertFalse(the_previous_rule_accepts(blind))

    def test_the_number_it_would_have_shown(self):
        """The understatement, on screen, in the units a person reads."""
        step, scored, counted = self.the_hidden_path_step()
        shown = step.cost.model_requests
        self.assertEqual(shown.value, 120.0)
        self.assertEqual(shown.provenance, build.INFERRED)
        self.assertIn(build._path_key(counted), shown.how)
        # And what the step will actually open, and what that would have cost.
        self.assertEqual(
            build._path_key(step.arguments["eval_path"]), build._path_key(scored)
        )
        self.assertEqual(
            len(scored.read_text(encoding="utf-8").splitlines()),
            777,
            "the step opens a file with 777 rows and the plan says 120 requests",
        )


# ---------------------------------------------------------------------------
# 2. The disclosed routes.


class TheDisclosedRoutesTest(SubjectArgumentTestCase):
    def test_the_path_hidden_in_a_column_name(self):
        # route: the_path_hidden_in_a_column_name
        step, scored, counted = self.the_hidden_path_step()
        with self.assertRaises(BuildInvalid) as raised:
            self.a_build_of(step)
        said = str(raised.exception)
        self.assertIn(build._path_key(counted), said)
        self.assertIn(build._path_key(scored), said)
        self.assertIn("does not declare which of its arguments it reads", said)

    def test_the_product_says_unknown_and_plans_the_count(self):
        """The person's experience of that call, which is not an exception."""
        scored = self.the_file_that_gets_scored()
        counted = self.the_file_that_was_counted()
        self.assertEqual(self.count_for_real(counted), 120)
        result = self.propose_through_the_tool(
            eval_path=str(scored),
            input_field="q",
            expected_field=str(counted),
            sample=500,
        )
        self.assertTrue(result["ok"], result)
        steps = {step["id"]: step for step in result["build"]["steps"]}
        requests = steps["baseline"]["cost"]["model_requests"]
        self.assertEqual(requests["provenance"], build.UNKNOWN)
        self.assertIsNone(requests["value"])
        self.assertIn(build._path_key(scored), requests["how"])
        self.assertIn(build._path_key(counted), requests["how"])
        # And the offer is a step that is really there, on the file named.
        self.assertEqual(steps["count"]["tool"], "measure_eval_set")
        self.assertEqual(
            build._path_key(steps["count"]["arguments"]["path"]),
            build._path_key(scored),
        )

    def test_the_file_replaced_since_it_was_counted(self):
        # route: the_file_replaced_since_it_was_counted
        evaluation = self.the_file_that_gets_scored(777)
        self.assertEqual(self.count_for_real(evaluation), 777)
        # The same path, thrown away and rewritten. The ledger now records BOTH
        # what the file looked like when it was counted and when the row was
        # written, so this is caught by the witness rather than by the date -
        # a stronger check, because a file rewritten within the same second
        # still fails on its size and mtime.
        self.rows_at(evaluation, 2)
        later = time.time() + 120
        os.utime(evaluation, (later, later))

        result = self.propose_through_the_tool(
            eval_path=str(evaluation), input_field="q", expected_field="a", sample=500
        )
        self.assertTrue(result["ok"], result)
        steps = {step["id"]: step for step in result["build"]["steps"]}
        requests = steps["baseline"]["cost"]["model_requests"]
        self.assertEqual(requests["provenance"], build.UNKNOWN, requests["say"])
        # REWRITTEN, NOT LOOSENED. This asserted the date route's wording -
        # "modified at ... recorded at ..." - which was the only route there
        # was when nothing recorded the file's state at the count. The witness
        # now catches it first and says more: both readings, side by side.
        self.assertIn("not the same file", requests["how"])
        self.assertIn("when that was measured", requests["how"])
        self.assertIn("now", requests["how"])
        self.assertEqual(steps["count"]["tool"], "measure_eval_set")

    def test_a_recovered_subject_that_nobody_can_date_is_matched_on_identity(self):
        """The honest limit of the date, asserted rather than described.

        A caller who cannot find the ledger row supplies no date, and no date
        means the check does not run. It never means the count is fresh, and the
        difference is only visible if somebody states it.
        """
        evaluation = self.the_file_that_gets_scored(50)
        undated = propose.subject_of_a_recorded_measurement(
            f"counted 50 rows in {evaluation}"
        )
        self.assertEqual(undated.measured_at, "")
        self.assertIn("nothing dates the row", undated.how)
        later = time.time() + 120
        os.utime(evaluation, (later, later))
        ok, why = Subject.of_path(evaluation).matches(undated)
        self.assertTrue(ok, why)

        dated = propose.subject_of_a_recorded_measurement(
            f"counted 50 rows in {evaluation}", measured_at="2000-01-01 00:00:00"
        )
        ok, why = Subject.of_path(evaluation).matches(dated)
        self.assertFalse(ok, why)
        self.assertIn("2000-01-01 00:00:00", why)


# ---------------------------------------------------------------------------
# 3. Four routes found by attacking the fix. Each was open when it was written.


class FourAttacksOnTheFixTest(SubjectArgumentTestCase):
    def test_a_reference_where_no_tool_declared_the_reader(self):
        # route: a_reference_where_no_tool_declared_the_reader
        counted = self.the_file_that_was_counted()
        first = Step(
            id="count",
            tool="measure_eval_set",
            why="count something first, so there is an output to point at",
            arguments={"path": str(counted), "finish_the_count": True},
            produces=(Output("path", "string", "the file counted", at="path"),),
            cost=Cost(
                model_tokens=Estimate.none(build.MODEL_TOKENS, because="it is local"),
                model_requests=Estimate.none(
                    build.MODEL_REQUESTS, because="it is local"
                ),
                wall_clock=Estimate.unknown(
                    build.WALL_CLOCK, why="never timed", find_out_by="time one"
                ),
                disk=Estimate.unknown(
                    build.DISK, why="rows in the database", find_out_by="diff it"
                ),
            ),
            exit_criterion=ExitCriterion(
                stated="counted", source="tool_result", subject="exact",
                comparator="is_true",
            ),
        )
        # The file this step opens is chosen while the plan runs. The only
        # literal path left in the call is the one the cost was measured off.
        second = self.a_scoring_step(
            arguments={
                "eval_path": Ref("count", "path"),
                "input_field": "q",
                "expected_field": str(counted),
                "sample": 500,
            },
            cost=self.a_cost_costing(self.a_count_of(counted, 120)),
            operates_on=Subject.of_path(counted),
        )
        second = replace(second, needs=("count",))
        with self.assertRaises(BuildInvalid) as raised:
            self.a_build_of(first, second)
        self.assertIn("comes from an earlier step", str(raised.exception))

    def test_a_decoy_that_is_not_there_yet(self):
        # route: a_decoy_that_is_not_there_yet
        counted = self.the_file_that_was_counted()
        step = self.a_scoring_step(
            arguments={
                # Nothing at this path, no separator in it: not a path by
                # existence and not a path by shape. It is a file the moment
                # anybody creates it, which is any time before the approval.
                "eval_path": "ghost.jsonl",
                "input_field": "q",
                "expected_field": str(counted),
                "sample": 500,
            },
            cost=self.a_cost_costing(self.a_count_of(counted, 120)),
            operates_on=Subject.of_path(counted),
        )
        with self.assertRaises(BuildInvalid) as raised:
            self.a_build_of(step)
        self.assertIn("ghost.jsonl", str(raised.exception).lower())

    def test_a_subject_of_another_kind(self):
        # route: a_subject_of_another_kind
        scored = self.the_file_that_gets_scored()
        counted = self.the_file_that_was_counted()
        # The reading and the declaration agree, and neither is a path, so the
        # check that compares paths used to return before it looked at the call.
        as_a_dataset = Subject.named(
            build.SUBJECT_DATASET,
            build._path_key(counted),
            how="the eval set, named as a dataset rather than as a file",
        )
        requests = Estimate.measured(
            build.ROWS,
            reading=Reading.of_measured_fact(
                "eval_size_n",
                120,
                diagnosis.MEASURED,
                f"counted 120 rows in {build._path_key(counted)}",
                subject=as_a_dataset,
            ),
        ).counted_as(build.MODEL_REQUESTS, because="one request per row")
        step = self.a_scoring_step(
            arguments={
                "eval_path": str(scored),
                "input_field": "q",
                "expected_field": "a",
                "sample": 500,
            },
            cost=self.a_cost_costing(requests),
            operates_on=as_a_dataset,
        )
        with self.assertRaises(BuildInvalid) as raised:
            self.a_build_of(step)
        said = str(raised.exception)
        self.assertIn(build._path_key(scored), said)
        self.assertIn("kind", said)

    def test_a_decoy_inside_an_object_argument(self):
        # route: a_decoy_inside_an_object_argument
        counted = self.the_file_that_was_counted()
        elsewhere = self.the_file_that_gets_scored()
        step = Step(
            id="plan_again",
            tool="propose_build",
            why="a step whose second path is a value rather than an argument",
            arguments={
                # `facts` is an object with no declared keys, so any string can
                # travel in it - including a path, one level down from anything
                # that reads `arguments.values()`.
                "facts": {"goal_text": str(elsewhere)},
                "eval_path": str(counted),
            },
            cost=self.a_cost_costing(self.a_count_of(counted, 120)),
            exit_criterion=ExitCriterion(
                stated="a plan came back",
                source="tool_result",
                subject="ok",
                comparator="is_true",
            ),
            operates_on=Subject.of_path(counted),
        )
        with self.assertRaises(BuildInvalid) as raised:
            self.a_build_of(step)
        said = str(raised.exception)
        self.assertIn(build._path_key(elsewhere), said)
        self.assertIn("facts", said)


# ---------------------------------------------------------------------------
# 4. The declaration this fix asks app/tools/registry.py for.


class ADeclaringRegistry:
    """The live registry with one tool's `subject=` filled in.

    THE HALF THAT IS NOT WRITTEN YET, stood up here so this file can prove its
    own half against it. `ToolSpec.subject: tuple[str, ...] = ()` beside
    `measures=` and `bounds=`, naming the arguments through which a tool
    receives what it opens. `app/build.py` reads it with `getattr`, so the day
    it lands these tests describe the product instead of a proposal.
    """

    def __init__(self, tool_name: str, subject: tuple[str, ...]) -> None:
        self._tool = tool_name
        self._subject = tuple(subject)

    def _wrap(self, spec):
        if spec is None or spec.name != self._tool:
            return spec
        return _DeclaredSpec(spec, self._subject)

    def get(self, name):
        return self._wrap(REGISTRY.get(name))

    def __iter__(self):
        return iter(self._wrap(spec) for spec in REGISTRY)


class _DeclaredSpec:
    def __init__(self, spec, subject: tuple[str, ...]) -> None:
        self._spec = spec
        self.subject = tuple(subject)

    def __getattr__(self, item):
        return getattr(self._spec, item)


class TheToolIsWhatDecidesTest(SubjectArgumentTestCase):
    """`Build.__post_init__` validates against the live registry, so these patch
    it. `app/build.py::_registry` imports it at call time, which is what makes
    the patch reach the constructor."""

    def test_the_declaration_decides_which_argument(self):
        # route: the_declaration_decides_which_argument
        step, scored, counted = self.the_hidden_path_step()
        declaring = ADeclaringRegistry("measure_baseline", ("eval_path",))
        # First, at the door itself: with the declaration there is nothing to
        # weigh up. The tool reads eval_path, and that is the answer.
        runs_on, why_not = build.subject_of_a_call(
            declaring.get("measure_baseline"), step.arguments
        )
        self.assertEqual(why_not, "")
        self.assertEqual(runs_on.key, build._path_key(scored))
        self.assertIn("eval_path", runs_on.how)
        # And then through the wall, which now names the argument rather than
        # reporting that it cannot tell.
        with mock.patch("app.tools.registry.REGISTRY", declaring):
            with self.assertRaises(BuildInvalid) as raised:
                self.a_build_of(step)
        said = str(raised.exception)
        self.assertIn(build._path_key(counted), said)
        self.assertIn(build._path_key(scored), said)
        self.assertIn("eval_path", said)

    def test_a_declaration_is_consulted_rather_than_decoration(self):
        # route: a_declaration_is_consulted_rather_than_decoration
        scored = self.the_file_that_gets_scored()
        honest = self.a_scoring_step(
            arguments={
                "eval_path": str(scored),
                "input_field": "q",
                "expected_field": "a",
                "sample": 500,
            },
            cost=self.a_cost_costing(self.a_count_of(scored, 777)),
            operates_on=Subject.of_path(scored),
        )
        self.a_build_of(honest)  # valid today, against the live registry
        wrong = ADeclaringRegistry("measure_baseline", ("expected_field",))
        with mock.patch("app.tools.registry.REGISTRY", wrong):
            with self.assertRaises(BuildInvalid) as raised:
                self.a_build_of(honest)
        self.assertIn("expected_field", str(raised.exception))

    def test_a_second_path_beside_a_declared_subject(self):
        # route: a_second_path_beside_a_declared_subject
        """THE FALSE-REFUSAL CONTROL FOR THE DECLARATION, and its whole value.

        Undeclared, a call naming two files is undecidable and costs the person
        an unknown. Declared, the second file is none of this check's business -
        which is why the answer is a declaration and not a cleverer guess.
        """
        scored = self.the_file_that_gets_scored()
        alongside = self.the_file_that_was_counted()
        step = self.a_scoring_step(
            arguments={
                "eval_path": str(scored),
                "input_field": "q",
                "expected_field": str(alongside),
                "sample": 500,
            },
            cost=self.a_cost_costing(self.a_count_of(scored, 777)),
            operates_on=Subject.of_path(scored),
        )
        with self.assertRaises(BuildInvalid):
            self.a_build_of(step)  # undeclared: two paths, nothing says which
        declaring = ADeclaringRegistry("measure_baseline", ("eval_path",))
        with mock.patch("app.tools.registry.REGISTRY", declaring):
            plan = self.a_build_of(step)
        self.assertEqual(plan.step("baseline").cost.model_requests.value, 500.0)


# ---------------------------------------------------------------------------
# 5. The opposite failure. A gate nothing can open is not a gate.


class TheHonestPathIsNotBrokenTest(SubjectArgumentTestCase):
    def test_the_honest_count_of_the_file_that_gets_scored(self):
        # route: the_honest_count_of_the_file_that_gets_scored
        """THE POSITIVE CONTROL. A fix that made every cost unknown passes
        everything above and fails here."""
        evaluation = self.the_file_that_gets_scored(777)
        self.assertEqual(self.count_for_real(evaluation), 777)
        result = self.propose_through_the_tool(
            eval_path=str(evaluation), input_field="q", expected_field="a", sample=500
        )
        self.assertTrue(result["ok"], result)
        steps = {step["id"]: step for step in result["build"]["steps"]}
        requests = steps["baseline"]["cost"]["model_requests"]
        self.assertEqual(requests["provenance"], build.INFERRED, requests["say"])
        self.assertEqual(requests["value"], 500.0)
        # The derivation quotes the tool's own sentence, in the tool's spelling.
        self.assertIn(str(evaluation).lower(), requests["how"].lower())
        # Counting again would change nothing, so the plan does not.
        self.assertNotIn("count", steps)

    def test_an_ordinary_column_name_beside_a_path(self):
        # route: an_ordinary_column_name_beside_a_path
        evaluation = self.the_file_that_gets_scored()
        runs_on, why_not = build.subject_of_a_call(
            REGISTRY.get("measure_baseline"),
            {
                "eval_path": str(evaluation),
                "input_field": "q",
                "expected_field": "a",
                "sample": 500,
            },
        )
        self.assertEqual(why_not, "")
        self.assertEqual(runs_on.key, build._path_key(evaluation))

    def test_the_same_file_named_twice_in_one_call(self):
        # route: the_same_file_named_twice_in_one_call
        evaluation = self.the_file_that_gets_scored()
        runs_on, why_not = build.subject_of_a_call(
            REGISTRY.get("measure_baseline"),
            {
                "eval_path": str(evaluation),
                "input_field": "q",
                # The same file, spelled with a dot segment in the middle.
                "expected_field": str(evaluation.parent / "." / evaluation.name),
                "sample": 500,
            },
        )
        self.assertEqual(why_not, "", "one file in two spellings is one file")
        self.assertEqual(runs_on.key, build._path_key(evaluation))

    def a_plan_in_its_own_conversation(
        self, name: str, facts: dict, evaluation: Path, *, count_first: bool
    ) -> Build:
        """One conversation, one situation, one build - through the real ledger."""
        thread = self.a_conversation(name)
        if count_first:
            self.count_for_real(evaluation, thread=thread)
        sheet, trail = evidence.assemble_facts(thread, dict(facts), evidence.USER)
        result = diagnosis.diagnose(sheet)
        situation = propose.Situation(
            outcome=result.outcome,
            result=result,
            values={row["fact"]: row["value"] for row in trail},
            origins={row["fact"]: row["origin"] for row in trail},
            hows={row["fact"]: row.get("how") or "" for row in trail},
            recorded_at=propose.when_each_row_was_written(thread, trail),
            eval_path=str(evaluation),
            dataset_path=str(evaluation),
            input_field="q",
            expected_field="a",
            sample=500,
        )
        return propose.propose(situation)

    def test_every_shipped_proposer_still_produces_a_valid_build(self):
        """The sweep. A build that cannot be constructed never reaches a user,
        so a check that over-refuses takes the product down with it.

        Three conversations, because a count written in one of them would change
        which outcome the others reach - which is the whole point of a fact
        being scoped to a conversation.
        """
        evaluation = self.the_file_that_gets_scored(40)
        plans = [
            self.a_plan_in_its_own_conversation(
                "measure the baseline",
                FACTS_THAT_REACH_THE_BASELINE,
                evaluation,
                count_first=True,
            ),
            self.a_plan_in_its_own_conversation(
                "build the eval set",
                {"goal_text": "route tickets", "modality": "text", "target_score": 0.9},
                evaluation,
                count_first=False,
            ),
            self.a_plan_in_its_own_conversation(
                "substantiate what was claimed",
                {"goal_text": "route tickets", "target_score": 0.9, "eval_size_n": 40},
                evaluation,
                count_first=False,
            ),
        ]
        self.assertEqual(
            sorted(plan.for_outcome for plan in plans),
            [
                "ACTION__MEASURE_BASELINE",
                "ACTION__SUBSTANTIATE_CLAIMED_FACTS",
                "BLOCKED__BUILD_EVAL_SET",
            ],
        )
        for plan in plans:
            for step in plan.steps:
                measured = [
                    item
                    for estimate in step.cost.estimates
                    for item in estimate.subjects()
                ]
                if not measured:
                    continue
                self.assertIsNotNone(step.operates_on, f"{plan.id}.{step.id}")
                # And the subject is what the CALL opens, asked of the tool.
                runs_on, why_not = build.subject_of_a_call(
                    REGISTRY.get(step.tool), step.arguments
                )
                self.assertIsNotNone(runs_on, f"{plan.id}.{step.id}: {why_not}")
                self.assertEqual(runs_on.key, step.operates_on.key)


# ---------------------------------------------------------------------------
# 5b. The declaration itself, and the wall in front of it.


class TheDeclarationIsCheckedAtRegistrationTest(SubjectArgumentTestCase):
    """`subject=` names an argument the tool takes, or the tool does not register.

    THE SAME WALL `bounds=` GETS, AND FOR A SHARPER REASON. A bound naming
    nothing relaxes nothing and merely misleads a reader. A SUBJECT naming
    nothing is worse than that: `subject_of_a_call` would find none of the
    declared names present in any call and report every step using the tool as
    undecidable - so the tool would be uncostable forever, and the message
    would point at the call rather than at the typo that caused it.

    Driven against the real registry, through `_validate`, which is the code
    path every `@tool` decorator runs at import.
    """

    def _spec(self, **overrides):
        from app.tools.registry import Control, ToolSpec

        base = dict(
            name="a_tool_for_this_test",
            description="reads a file and says something about it",
            schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
            reads=("filesystem",),
            writes=(),
            approval="never",
            control=Control(label="X", group="Look", verb="look", order=1),
            handler=lambda path: {"ok": True},
            provides=("data.dataset.profile",),
        )
        base.update(overrides)
        return ToolSpec(**base)

    def test_a_subject_naming_a_real_argument_registers(self):
        from app.tools.registry import _validate

        _validate(self._spec(subject=("path",)))

    def test_a_subject_naming_nothing_is_refused_and_says_what_is_there(self):
        from app.tools.registry import ToolError, _validate

        with self.assertRaises(ToolError) as caught:
            _validate(self._spec(subject=("pth",)))
        message = str(caught.exception)
        self.assertIn("subject=['pth']", message)
        # The arguments it DOES take, because a reader who mistyped one needs
        # the list rather than a second trip to the schema.
        self.assertIn("path", message)

    def test_declaring_none_is_legal_and_means_the_tool_has_not_said(self):
        """Not "operates on nothing". A field defaulting to `()` cannot tell
        those apart, and reading the default as a claim would refuse every
        proposal this product makes."""
        from app.tools.registry import _validate

        _validate(self._spec())
        self.assertEqual((), build.declared_subject_arguments(self._spec()))

    def test_the_tool_that_needed_it_declares_it(self):
        """`run_the_failures`, and the argument is the failure set. The other
        two paths it takes are the answers and the traces; what the work is
        proportional to is how many QUESTIONS it grades."""
        spec = REGISTRY.get("run_the_failures")
        self.assertEqual(("failures_path",), build.declared_subject_arguments(spec))
        for name in build.declared_subject_arguments(spec):
            self.assertIn(name, spec.schema["properties"])

    def test_without_it_that_tools_calls_are_undecidable(self):
        """THE MEASUREMENT THAT MADE THE FIELD NECESSARY, taken rather than
        described: strip the declaration and a call passing a failure set and
        an answers file can no longer be costed at all."""
        from dataclasses import replace as _replace

        spec = REGISTRY.get("run_the_failures")
        questions = self.rows_at(self.root / "questions.jsonl", 12)
        answers = self.rows_at(self.root / "after.jsonl", 12)
        arguments = {
            "failures_path": str(questions),
            "answers_path": str(answers),
            "input_field": "input",
            "expected_field": "expected",
            "answer_field": "answer",
        }
        runs_on, _why = build.subject_of_a_call(spec, arguments)
        self.assertIsNotNone(runs_on)
        self.assertEqual(build.Subject.of_path(questions).key, runs_on.key)

        undeclared = _replace(spec, subject=())
        nothing, why_not = build.subject_of_a_call(undeclared, arguments)
        self.assertIsNone(nothing)
        self.assertIn("2 different paths", why_not)


# ---------------------------------------------------------------------------
# 6. The count.


class TheRouteListIsCompleteTest(unittest.TestCase):
    def test_every_route_is_named_and_the_count_is_pinned(self):
        self.assertEqual(len(ROUTES), ROUTES_CLOSED)

    def test_every_route_has_a_reason_a_person_can_read(self):
        for name, reason in ROUTES.items():
            self.assertGreater(len(reason), 30, name)

    def test_every_named_route_has_a_test_that_marks_it(self):
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
