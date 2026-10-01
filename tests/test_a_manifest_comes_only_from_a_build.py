"""A manifest is minted from a validated `Build`, or it is not minted.

`app/storm.py`'s `Manifest.of` used to say, in its own docstring, that "the
fingerprint is what says this dict came from a `Build` that passed the first
one". It said no such thing. `Build.fingerprint()` is `_digest` of the dict it is
handed, so whoever supplied the object supplied the hash, and the check reduced
to `_digest(x) == _digest(x)`. Everything `Build.validate` does that the storm's
own per-step checks do not repeat - the dependency graph, the argument types,
the enums, the references - was therefore checked by nobody at all for a plan
that arrived as a dict.

Two plans `Build.validate()` refuses loudly were declared through that hole and
ran to `done`. Both are constructed here, because a fix asserted against a
mutation nobody has watched fail is a fix nobody has evidence for:

1. **A dependency cycle.** `one` needs `two`, `two` needs `one`, and the `waves`
   are hand-written so nothing ever asks the graph a question. `Build.validate`
   names the cycle; the storm ran both steps to `done`.
2. **An argument its tool's schema forbids.** `list_runs` declares `limit` as an
   integer and the step passes it a sentence. `Build.validate` names the type;
   the storm dispatched the call.

Neither is reachable over HTTP - `POST /api/storms` re-proposes server-side and
never accepts a plan - and no model has an approve or a run tool. Both are
reachable from Python, which is where the guard was: a guard that reads as
protection in a review and is not one is worse than no guard, and that is a
thing this repository has now decided twice.

The last class in this file is the part that is not about the original finding.
It is three routes invented against the FIX, two of which worked the first time
they were tried, and they are here as tests rather than as a paragraph in a
report because that is the difference between a fix and a story about one.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from app import build as buildmod
from app import events, storm
from app.build import (
    Build,
    Cost,
    Environment,
    Estimate,
    ExitCriterion,
    Output,
    Step,
)
from app.tools import REGISTRY

import support


# ---------------------------------------------------------------------------
# Scaffolding. Plans are written as DICTS here, deliberately, because the door
# under test is the one a dict comes through.


def a_cost() -> Cost:
    """The cheapest honest cost. Nothing invented, every slot accounted for."""
    return Cost(
        model_tokens=Estimate.none(
            buildmod.MODEL_TOKENS, because="this step never asks the model"
        ),
        model_requests=Estimate.none(
            buildmod.MODEL_REQUESTS, because="this step never asks the model"
        ),
        wall_clock=Estimate.unknown(
            buildmod.WALL_CLOCK,
            why="nothing in this harness has timed this tool yet",
            find_out_by="run it once and read the seconds off the result",
        ),
        disk=Estimate.none(buildmod.DISK, because="this step writes no file"),
    )


COUNT_EXISTS = {
    "stated": "the tool answered with a count",
    "source": "tool_result",
    "subject": "count",
    "comparator": "exists",
    "value": None,
}
RUNS_EXIST = {
    "stated": "the tool answered with some runs",
    "source": "tool_result",
    "subject": "runs",
    "comparator": "exists",
    "value": None,
}
A_COUNT_OUTPUT = [
    {"name": "count", "type": "integer", "description": "how many", "at": "count"}
]
A_RUNS_OUTPUT = [
    {"name": "runs", "type": "array", "description": "the runs", "at": "runs"}
]


def a_step(
    step_id: str,
    tool: str = "list_context",
    *,
    arguments: dict | None = None,
    needs: tuple[str, ...] = (),
    produces: list | None = None,
    exit_criterion: dict | None = None,
) -> dict:
    return {
        "id": step_id,
        "tool": tool,
        "why": f"{step_id} is here so this test has something to run",
        "arguments": dict(arguments or {}),
        "produces": list(produces if produces is not None else A_COUNT_OUTPUT),
        "needs": list(needs),
        "cost": a_cost().as_dict(),
        "exit_criterion": dict(exit_criterion or COUNT_EXISTS),
        "risks": [],
    }


def signed(blueprint: dict) -> dict:
    """Stamp every step with the contract fingerprint `Step` would have stamped.

    So that the plan and the hash of the plan agree with each other, and the
    storm's existing per-step check has nothing to say. Without this the tests
    below would be watching a different refusal than the one they claim to be
    about, which is how a green suite comes to mean nothing.
    """
    for raw in blueprint["steps"]:
        raw["contract"] = buildmod._digest(
            {
                "id": raw["id"],
                "tool": raw["tool"],
                "arguments": raw["arguments"],
                "needs": raw["needs"],
                "produces": raw["produces"],
                "exit_criterion": raw["exit_criterion"],
            }
        )
    return blueprint


class ManifestTestCase(unittest.TestCase):
    """Its own database, because declaring writes a row and running writes events."""

    def setUp(self):
        self.root = support.sandbox(self)
        self.thread_id = events.create_thread("a manifest test")["id"]

    # -- plans as dicts ----------------------------------------------------

    def blueprint(self, build_id: str, steps: list[dict], waves: list[list[str]],
                  exit_subject: str) -> dict:
        return signed(
            {
                "id": build_id,
                "title": "a plan that was never a Build",
                "for_outcome": "BLOCKED__BUILD_EVAL_SET",
                "because": "a dict shaped like a plan is not a plan",
                "steps": steps,
                "edges": [
                    {"from": need, "to": raw["id"]}
                    for raw in steps
                    for need in raw["needs"]
                ],
                "waves": waves,
                "environment": {
                    "name": "a test sandbox",
                    "working_dir": str(self.root / "work"),
                    "egress": False,
                    "egress_reason": "",
                    "data": [],
                    "installs": [],
                    "python": "3.11.0",
                },
                "cost": a_cost().as_dict(),
                "exit_criterion": {
                    "stated": "every step answered",
                    "source": "outputs",
                    "subject": exit_subject,
                    "comparator": "exists",
                    "value": None,
                },
                "risks": [],
                "questions": [],
                "facts": {},
                "needs_approval": [],
                "step_states": list(buildmod.STEP_STATES),
                "say": "a plan that never passed validate()",
            }
        )

    def a_cyclic_plan(self) -> dict:
        """`one` needs `two`, `two` needs `one`, and the waves never ask."""
        return self.blueprint(
            "cyclic_plan",
            [
                a_step("one", needs=("two",)),
                a_step("two", needs=("one",)),
            ],
            waves=[["one"], ["two"]],
            exit_subject="one.count",
        )

    def a_type_violating_plan(self) -> dict:
        """`list_runs` declares `limit` an integer. This step passes a sentence."""
        return self.blueprint(
            "type_violating_plan",
            [
                a_step(
                    "read_runs",
                    "list_runs",
                    arguments={"limit": "all of them please"},
                    produces=A_RUNS_OUTPUT,
                    exit_criterion=RUNS_EXIST,
                )
            ],
            waves=[["read_runs"]],
            exit_subject="read_runs.runs",
        )

    # -- the doors ---------------------------------------------------------

    def declare(self, blueprint: dict) -> dict:
        return storm.declare(
            blueprint,
            approved=buildmod._digest(blueprint),
            thread_id=self.thread_id,
        )

    def a_real_build(self) -> Build:
        """A `Build` this test controls: two steps, real tools, in order."""
        def step(step_id: str, needs: tuple[str, ...] = ()) -> Step:
            return Step(
                id=step_id,
                tool="list_context",
                why=f"{step_id} lists what the harness has been pointed at",
                arguments={},
                produces=(Output("count", "integer", "how many", at="count"),),
                needs=needs,
                cost=a_cost(),
                exit_criterion=ExitCriterion(
                    stated="the tool answered with a count",
                    source="tool_result",
                    subject="count",
                    comparator="exists",
                ),
            )

        return Build(
            id="a_real_plan",
            title="a plan that really was a Build",
            for_outcome="BLOCKED__BUILD_EVAL_SET",
            because="the check has to let the real thing through or it is a wall",
            steps=(step("one"), step("two", needs=("one",))),
            environment=Environment(
                name="a test sandbox", working_dir=str(self.root / "work")
            ),
            exit_criterion=ExitCriterion(
                stated="both steps answered",
                source="outputs",
                subject="one.count",
                comparator="exists",
            ),
        )


# ---------------------------------------------------------------------------
# 1. The two failures, refused.


class APlanThatNeverValidatedIsRefusedTest(ManifestTestCase):
    """The finding, from both ends: what `Build.validate` says, and what the storm does.

    Each test first asks `Build.validate` - through the build's own code, not a
    reading of it - what is wrong with the plan, so that the refusal is checked
    against a fault that demonstrably exists rather than against a hope.
    """

    def test_a_dependency_cycle_is_refused_and_nothing_is_recorded(self):
        plan = self.a_cyclic_plan()

        # The fault, named by the build's own function.
        cycle = buildmod._find_cycle(
            {
                "one": Step(
                    id="one", tool="list_context", why="w", needs=("two",),
                    cost=a_cost(), exit_criterion=ExitCriterion(**COUNT_EXISTS),
                ),
                "two": Step(
                    id="two", tool="list_context", why="w", needs=("one",),
                    cost=a_cost(), exit_criterion=ExitCriterion(**COUNT_EXISTS),
                ),
            }
        )
        self.assertEqual(cycle, ["one", "two", "one"])

        with self.assertRaises(storm.StormRefused) as caught:
            self.declare(plan)
        self.assertIn("cycle", str(caught.exception))
        self.assertTrue(caught.exception.deviations)
        self.assertEqual(storm.list_for_thread(self.thread_id), [])

    def test_an_argument_its_tool_forbids_is_refused_and_never_dispatched(self):
        plan = self.a_type_violating_plan()

        # The fault is real: the schema says integer and the plan passes a string.
        self.assertEqual(
            REGISTRY.get("list_runs").schema["properties"]["limit"]["type"], "integer"
        )
        self.assertIsInstance(plan["steps"][0]["arguments"]["limit"], str)

        with self.assertRaises(storm.StormRefused) as caught:
            self.declare(plan)
        self.assertIn("integer", str(caught.exception))
        self.assertIn("read_runs", str(caught.exception))
        self.assertEqual(storm.list_for_thread(self.thread_id), [])

    def test_the_refusal_is_the_storms_own_refusal_and_not_a_leaked_exception(self):
        """`StormRefused` or nothing. A caller catches one type, not two.

        `Manifest.of` is documented to refuse by raising `StormRefused`, and a
        plan that fails somewhere `app/build.py` raises from would otherwise come
        out as a bare `BuildInvalid` past every handler in `app/main.py`.
        """
        for name, plan in (
            ("a cycle", self.a_cyclic_plan()),
            ("a type violation", self.a_type_violating_plan()),
        ):
            with self.subTest(name):
                with self.assertRaises(storm.StormRefused):
                    storm.Manifest.of(plan, fingerprint=buildmod._digest(plan))

    def test_the_fingerprint_alone_never_said_the_plan_was_a_plan(self):
        """The claim the old docstring made, shown to be arithmetic about nothing.

        `_digest(blueprint)` is what `Build.fingerprint()` computes, so a caller
        holding the dict holds the figure too. This is not a defect in the
        fingerprint - it says WHICH plan, which is real and is still checked -
        it is a defect in reading it as saying the plan was ever validated.
        """
        plan = self.a_cyclic_plan()
        self.assertEqual(buildmod._digest(plan), buildmod._digest(dict(plan)))
        with self.assertRaises(storm.StormRefused):
            storm.Manifest.of(plan, fingerprint=buildmod._digest(plan))


# ---------------------------------------------------------------------------
# 2. And the real thing still goes through, or this is a wall and not a door.


class APlanThatDidValidateStillRunsTest(ManifestTestCase):
    """A POSITIVE CONTROL. A check that refuses everything certifies nothing.

    Adversaries on this project have shipped three false greens, one of which
    reported 2211 violations out of 2211 from reading the wrong column. So the
    same door that refused the two plans above has to be shown passing a real
    one, through both of its entrances, agreeing with itself.
    """

    def test_a_build_is_accepted_and_runs(self):
        plan = self.a_real_build()
        declared = storm.declare(plan, thread_id=self.thread_id)
        list(storm.run(declared["storm"]))
        state = storm.attach(declared["storm"])
        self.assertEqual(state.state, "done")
        self.assertEqual(
            {name: step.state for name, step in state.steps.items()},
            {"one": "done", "two": "done"},
        )

    def test_the_dict_that_build_emitted_is_accepted_through_the_dict_door(self):
        """The door `POST /api/storms` uses: the plan as JSON, plus the figure."""
        plan = self.a_real_build()
        blueprint = json.loads(json.dumps(plan.as_dict()))
        through_the_dict = storm.Manifest.of(
            blueprint, fingerprint=plan.fingerprint()
        )
        through_the_object = storm.Manifest.of(plan)
        self.assertEqual(
            [item.as_dict() for item in through_the_dict.steps],
            [item.as_dict() for item in through_the_object.steps],
        )
        self.assertEqual(through_the_dict.waves, through_the_object.waves)

    def test_a_plan_a_real_proposer_wrote_survives_the_dict_door(self):
        """Not a plan this file invented. The one the product actually proposes.

        A test that only ever feeds the check its own fixtures is a test of the
        fixtures. `propose_build` is what writes the plans a person approves, and
        its output has to come back through this door unchanged.
        """
        from app import diagnosis
        from app.tools import evidence, propose

        path = self.root / "eval.jsonl"
        path.write_text(
            "\n".join(json.dumps({"q": f"q{i}", "a": "yes"}) for i in range(40)),
            encoding="utf-8",
        )
        sheet, trail = evidence.assemble_facts(
            self.thread_id,
            {"goal_text": "route support tickets", "modality": "text",
             "target_score": 0.9},
            evidence.USER,
        )
        result = diagnosis.diagnose(sheet)
        plan = propose.propose(
            propose.Situation(
                outcome=result.outcome,
                result=result,
                values={row["fact"]: row["value"] for row in trail},
                origins={row["fact"]: row["origin"] for row in trail},
                hows={row["fact"]: row.get("how") or "" for row in trail},
                eval_path=str(path),
            )
        )
        blueprint = json.loads(json.dumps(plan.as_dict()))
        manifest = storm.Manifest.of(blueprint, fingerprint=plan.fingerprint())
        self.assertEqual(
            list(manifest.step_ids), [step.id for step in plan.steps]
        )

    def test_no_cost_is_ever_rebuilt_from_json(self):
        """THE DOOR SECTION 4 WELDS SHUT, CHECKED RATHER THAN PROMISED.

        The fix turns a recorded plan back into a `Build`, and `Step` refuses to
        exist without a `Cost`. If that copy carried the plan's real costs it
        would be exactly the deserialiser `app/build.py` exists to prevent: a
        magnitude off disk whose provenance is a string that came back from
        SQLite. So every estimate in the copy has to be UNKNOWN and hold no
        number, no matter what the record says its costs were.
        """
        plan = self.a_real_build()
        blueprint = json.loads(json.dumps(plan.as_dict()))

        # The record's own costs are real ones, with real provenances on them.
        recorded = blueprint["steps"][0]["cost"]
        self.assertEqual(recorded["model_tokens"]["provenance"], buildmod.INFERRED)
        self.assertEqual(recorded["model_tokens"]["value"], 0.0)

        rebuilt = storm._a_build_again(blueprint)
        for step in rebuilt.steps:
            for dimension in buildmod.COST_DIMENSIONS:
                estimate = getattr(step.cost, dimension)
                self.assertEqual(estimate.provenance, buildmod.UNKNOWN, dimension)
                self.assertIsNone(estimate.value, dimension)
                self.assertIsNone(estimate.reading, dimension)


# ---------------------------------------------------------------------------
# 3. Three routes against the fix itself. Two of them worked.


class RoutesAgainstTheFixTest(ManifestTestCase):
    """What I tried against my own door, including the two that got through.

    Route one and route three are in this file because they succeeded on the
    first version of the fix - a plan ran to `done` through it, and a sentence I
    wrote appeared in a person's transcript under the harness's name. A fix whose
    author only ever tried the attacks it already stops is a fix with no evidence
    behind it.
    """

    def test_a_build_subclass_cannot_supply_its_own_validation(self):
        """ROUTE ONE, AND IT WORKED. `isinstance` was trusting the wrong thing.

        A `Build` is trusted because `__post_init__` validates it and an invalid
        one cannot exist. A SUBCLASS can override `validate` to return `self`,
        and then `isinstance(plan, Build)` is the whole check - which is the same
        shape as the defect being fixed, one level up: the object that is
        supposed to be checked supplies the checking.

        On the first version of this fix the plan below declared and ran to
        `done`. `type(plan) is Build` is what closed it.
        """

        class Compliant(Build):
            def validate(self, registry=None):
                return self

        sneaky = Compliant(
            id="a_real_plan",
            title="a plan that was never a Build",
            for_outcome="BLOCKED__BUILD_EVAL_SET",
            because="a subclass can replace the validation being trusted",
            steps=(
                Step(
                    id="read_runs",
                    tool="list_runs",
                    why="pass a sentence where the schema wants an integer",
                    arguments={"limit": "all of them please"},
                    produces=(Output("runs", "array", "the runs", at="runs"),),
                    cost=a_cost(),
                    exit_criterion=ExitCriterion(**RUNS_EXIST),
                ),
            ),
            environment=Environment(
                name="a test sandbox", working_dir=str(self.root / "work")
            ),
            exit_criterion=ExitCriterion(
                stated="it answered",
                source="outputs",
                subject="read_runs.runs",
                comparator="exists",
            ),
        )
        self.assertIsInstance(sneaky, Build)  # the check that was not enough
        self.assertIs(sneaky.validate(), sneaky)  # and why it was not

        with self.assertRaises(storm.StormRefused) as caught:
            storm.declare(sneaky, thread_id=self.thread_id)
        self.assertIn("integer", str(caught.exception))
        self.assertEqual(storm.list_for_thread(self.thread_id), [])

    def test_waves_that_disagree_with_the_graph_are_refused(self):
        """ROUTE TWO. The mechanism that made the cycle dangerous rather than silly.

        `_drive` iterates `manifest.waves`, which comes off the record. A plan
        whose graph is perfectly valid can therefore still carry a schedule that
        runs a step before the step it needs - and the graph check alone would
        never look, because there is nothing wrong with the graph.

        `Build.as_dict()["waves"]` is derived from `Build.waves()`, so the round
        trip catches it: the record's schedule has to be the schedule a validated
        build of that record computes for itself.
        """
        plan = self.a_real_build()
        blueprint = json.loads(json.dumps(plan.as_dict()))
        self.assertEqual(blueprint["waves"], [["one"], ["two"]])
        blueprint["waves"] = [["two"], ["one"]]

        with self.assertRaises(storm.StormRefused) as caught:
            storm.Manifest.of(blueprint, fingerprint=buildmod._digest(blueprint))
        self.assertTrue(
            any("waves" in note for note in caught.exception.deviations),
            caught.exception.deviations,
        )

    def test_the_sentence_that_reaches_the_transcript_is_the_builds_own(self):
        """ROUTE THREE, AND IT WORKED. `say` is not just a field of the record.

        `declare()` writes `blueprint["say"]` into the thread as an assistant
        message - it is the one part of a plan that becomes something a person
        reads as the harness speaking. The first version of this fix skipped
        `say` wholesale, because its cost line cannot be re-derived, and a
        sentence of my choosing duly appeared in a transcript over the harness's
        name.

        Only the first `Cost:` line is skipped now, and everything else has to be
        what a validated build of this plan says about itself.
        """
        plan = self.a_real_build()
        blueprint = json.loads(json.dumps(plan.as_dict()))
        blueprint["say"] = "Plan: this does nothing at all. Done when: immediately."

        with self.assertRaises(storm.StormRefused) as caught:
            storm.declare(
                blueprint,
                approved=buildmod._digest(blueprint),
                thread_id=self.thread_id,
            )
        self.assertTrue(
            any("say" in note for note in caught.exception.deviations),
            caught.exception.deviations,
        )
        self.assertEqual(
            [row for row in events.messages_for(self.thread_id)
             if row["role"] == "assistant"],
            [],
        )

    def test_the_cost_line_of_say_is_the_only_thing_skipped(self):
        """The skip is one line, and a second `Cost:` line is not smuggled through.

        Naming what a check does not cover is only worth something if the
        uncovered part is as small as it claims. `say`'s cost line cannot be
        re-derived because the validated copy carries no cost; a SECOND line
        beginning `Cost:` has no such excuse and is compared like any other.
        """
        plan = self.a_real_build()
        blueprint = json.loads(json.dumps(plan.as_dict()))
        lines = blueprint["say"].splitlines()
        self.assertEqual(len([x for x in lines if x.startswith("Cost:")]), 1)

        # The real say, with only its cost line rewritten: accepted.
        rewritten = [
            "Cost: whatever this module cannot check" if line.startswith("Cost:")
            else line
            for line in lines
        ]
        allowed = dict(blueprint, say="\n".join(rewritten))
        storm.Manifest.of(allowed, fingerprint=buildmod._digest(allowed))

        # The real say with an EXTRA cost line: refused.
        smuggled = dict(
            blueprint,
            say="\n".join(rewritten + ["Cost: and also your house"]),
        )
        with self.assertRaises(storm.StormRefused):
            storm.Manifest.of(smuggled, fingerprint=buildmod._digest(smuggled))

    def test_a_field_this_module_cannot_rebuild_is_refused_by_name(self):
        """A field the reconstruction does not know is not a field it may drop.

        The round trip would catch a dropped field anyway - that is what
        comparing the record against the rebuilt object's own `as_dict()` is for
        - but it would catch it as "step 'x' is not what a validated build says
        it is", which tells the next person nothing. This is the same refusal
        with the field named.

        THE DAY CAME, AND THIS TEST DID ITS JOB TWICE. It was written when
        `operates_on` was a field the storm could not rebuild at all, using it as
        the example of an unknown key. `app/build.py` then grew it for real -
        `Step.operates_on` is what a step's cost was measured against - and
        `app/storm.py` learned to record and rehydrate it, at which point this
        test went red.

        It went red for the RIGHT reason and the fix was in the storm, not here.
        A malformed subject was reaching `Subject(**raw)` and raising a bare
        `TypeError`, which surfaced as "this plan does not pass Build.validate
        ... missing 1 required positional argument: 'how'" - the field never
        named, exactly the failure the paragraph above describes. `_a_subject_again`
        now refuses it by name. So the assertion is unchanged and still means what
        it always meant; only the reason it passes has moved from "the storm has
        never heard of this key" to "the storm knows this key and says so when the
        record is wrong", which is the stronger of the two.
        """
        plan = self.a_real_build()
        blueprint = json.loads(json.dumps(plan.as_dict()))
        blueprint["steps"][0]["operates_on"] = {"kind": "file", "key": "somewhere"}

        with self.assertRaises(storm.StormRefused) as caught:
            storm.Manifest.of(blueprint, fingerprint=buildmod._digest(blueprint))
        self.assertIn("operates_on", str(caught.exception))

    def test_a_record_that_lies_about_its_own_edges_is_refused(self):
        """`edges` is what the diagram draws. It is derived, so it is compared.

        A plan whose picture disagrees with its dependencies would show a person
        one thing and run another, which is the failure the diagram exists to
        make impossible.
        """
        plan = self.a_real_build()
        blueprint = json.loads(json.dumps(plan.as_dict()))
        blueprint["edges"] = []

        with self.assertRaises(storm.StormRefused) as caught:
            storm.Manifest.of(blueprint, fingerprint=buildmod._digest(blueprint))
        self.assertTrue(
            any("edges" in note for note in caught.exception.deviations),
            caught.exception.deviations,
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
