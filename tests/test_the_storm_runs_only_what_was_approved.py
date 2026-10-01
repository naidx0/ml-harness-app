"""A storm may run only what was approved, and this is where that is proved.

`docs/THE_PROPOSAL_LOOP.md` section 5: *what they approved is what runs. Any
deviation stops and asks.* That sentence is either a mechanism or a label, and
the difference is a test that mutates an approved plan and watches the storm
refuse rather than a test that reads the code and agrees with it.

Four things are checked here, and each one was a way the contract could have
been decoration:

1. **The storm runs the approved build.** Every step, in dependency order,
   through the real registry, against a build a real proposer produced from a
   real diagnosis. Nothing is streamed that was not first written, so a client
   that reconnects mid-storm loses nothing.
2. **A plan that is not the approved plan does not run.** Approve a build,
   change it, hand the changed one to the storm: it refuses, names what changed,
   and starts nothing. The naming is checked against `Build.deviations_from` -
   sentence for sentence, on six different mutations - because a refusal that
   named things differently from the object's own answer would be a second
   opinion, and two opinions about what changed is how a contract drifts.
3. **A tool that changed under an approved plan stops it.** This is the
   deviation `Build.deviations_from` structurally cannot see: the step is byte
   for byte what it was and the thing it names is not. A tool that grew an
   argument, that disappeared, or that started requiring the person's permission
   each time is a different promise from the one they read.
4. **A step that cannot show it worked did not work.** The exit criterion is the
   one the build stated before it ran, evaluated by the build's own function.
   A step whose tool returned successfully and whose criterion was not met is
   `failed`, and the steps that needed it do not run.
"""

from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path

from app import build as buildmod
from app import diagnosis, events, storm
from app.build import (
    Build,
    Cost,
    Environment,
    Estimate,
    # Spelled `Criterion` here only because every use in this file is a sentence
    # about what a step must show, and `ExitCriterion(...)` three times in one
    # `Step(...)` reads as ceremony rather than as the claim it is.
    ExitCriterion as Criterion,
    Output,
    Step,
)
from app.main import app
from app.tools import REGISTRY, evidence, propose
from app.tools.registry import Registry

import support


# ---------------------------------------------------------------------------
# Scaffolding.


def a_cost() -> Cost:
    """The cheapest honest cost: nothing invented, everything accounted for."""
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


def registry_where(name: str, **changes) -> Registry:
    """The live registry with one tool declared differently.

    `Registry` has no `remove` and no `replace`, on purpose - nothing in the
    product may redeclare a tool at runtime - so drift is expressed the only way
    it can be: a second registry built from the same declarations with one of
    them changed, handed to the storm as the world it is running in.
    """
    other = Registry()
    for spec in REGISTRY:
        if spec.name == name:
            if changes.get("gone"):
                continue
            spec = replace(spec, **{k: v for k, v in changes.items() if k != "gone"})
        other.add(spec)
    return other


class StormTestCase(unittest.TestCase):
    """Every test gets its own database: proposing and running both read the ledger."""

    def setUp(self):
        self.root = support.sandbox(self)
        self.thread = events.create_thread("a storm test")
        self.thread_id = self.thread["id"]

    # -- a real build, from a real diagnosis --------------------------------

    def eval_file(self, rows: int = 40) -> Path:
        path = self.root / "eval.jsonl"
        path.write_text(
            "\n".join(json.dumps({"q": f"q{i}", "a": "yes"}) for i in range(rows)),
            encoding="utf-8",
        )
        return path

    def a_real_build(self) -> Build:
        """`BLOCKED__BUILD_EVAL_SET`: attach the file, count it, walk the tree again."""
        path = self.eval_file()
        sheet, trail = evidence.assemble_facts(
            self.thread_id,
            {"goal_text": "route support tickets", "modality": "text",
             "target_score": 0.9},
            evidence.USER,
        )
        result = diagnosis.diagnose(sheet)
        self.assertEqual(result.outcome, "BLOCKED__BUILD_EVAL_SET")
        return propose.propose(
            propose.Situation(
                outcome=result.outcome,
                result=result,
                values={row["fact"]: row["value"] for row in trail},
                origins={row["fact"]: row["origin"] for row in trail},
                hows={row["fact"]: row.get("how") or "" for row in trail},
                eval_path=str(path),
            )
        )

    def approved(self, plan: Build | None = None) -> tuple[Build, int]:
        """Approve a build and get the storm id back. Nothing has run yet."""
        plan = self.a_real_build() if plan is None else plan
        declared = storm.declare(plan, thread_id=self.thread_id)
        return plan, declared["storm"]

    # -- a build this test controls end to end -----------------------------

    def a_build_that_will_not_pass(self) -> Build:
        """Two steps: one whose stated criterion its result cannot meet, and one
        that needs it. Both tools are real and both succeed; the plan does not."""
        impossible = Step(
            id="look",
            tool="list_context",
            why="list what the harness has been pointed at",
            arguments={},
            produces=(Output("count", "integer", "how many contexts", at="count"),),
            cost=a_cost(),
            exit_criterion=Criterion(
                stated="there are at least a thousand contexts on file",
                source="tool_result",
                subject="count",
                comparator="at_least",
                value=1000,
            ),
        )
        dependent = Step(
            id="after",
            tool="list_runs",
            why="list the runs, once the contexts are known",
            arguments={},
            needs=("look",),
            cost=a_cost(),
            exit_criterion=Criterion(
                stated="the tool answered",
                source="tool_result",
                subject="count",
                comparator="at_least",
                value=0,
            ),
        )
        return Build(
            id="a_build_that_will_not_pass",
            title="A build whose first step cannot show it worked",
            for_outcome="ACTION__MEASURE_BASELINE",
            because="this test needs a step that succeeds and does not pass",
            steps=(impossible, dependent),
            environment=Environment(name="test", working_dir=str(self.root / "wd")),
            exit_criterion=Criterion(
                stated="both steps did what they said",
                source="tool_result",
                subject="count",
                comparator="at_least",
                value=0,
            ),
        )

    # -- reading a storm's log ---------------------------------------------

    def kinds(self, rows) -> list[str]:
        return [row["kind"] for row in rows]

    def payloads(self, rows, kind) -> list[dict]:
        return [row["payload"] for row in rows if row["kind"] == kind]


# ---------------------------------------------------------------------------
# 1. The storm runs the approved build.


class TheStormRunsTheApprovedBuildTest(StormTestCase):

    def test_every_step_runs_in_dependency_order_and_is_verified(self):
        plan, storm_id = self.approved()
        rows = list(storm.run(storm_id))

        started = [row["payload"]["step"] for row in rows
                   if row["kind"] == storm.STEP_STARTED]
        self.assertEqual(started, ["attach", "count", "recheck"])

        finished = self.payloads(rows, storm.STEP_FINISHED)
        for entry in finished:
            self.assertEqual(entry["state"], "done", entry)
            self.assertTrue(entry["verification"]["ok"], entry)

        # The criterion each step was judged by is the one the build stated
        # before it ran, not one chosen at execution time.
        stated = {step.id: step.exit_criterion.stated for step in plan.steps}
        self.assertEqual(
            {entry["step"]: entry["verification"]["stated"] for entry in finished},
            stated,
        )

    def test_nothing_is_streamed_that_was_not_first_written(self):
        """The property `app/events.py` exists for, asserted at the storm's door.

        Every frame a caller sees is a row that was committed first, so its id is
        replayable. If the storm streamed anything it had not written, a client
        that reconnected asking for everything after that id would never get it.
        """
        _, storm_id = self.approved()
        streamed = list(storm.run(storm_id))
        self.assertTrue(streamed)

        durable = {row["id"]: row["kind"]
                   for row in events.since(f"thread:{self.thread_id}", 0, 1000)}
        for row in streamed:
            self.assertIn(row["id"], durable)
            self.assertEqual(durable[row["id"]], row["kind"])
        self.assertEqual(
            [row["id"] for row in streamed], sorted(row["id"] for row in streamed)
        )

    def test_the_state_a_new_process_would_see_is_the_state_that_happened(self):
        _, storm_id = self.approved()
        list(storm.run(storm_id))

        attached = storm.attach(storm_id)
        self.assertEqual(
            {name: step.state for name, step in attached.steps.items()},
            {"attach": "done", "count": "done", "recheck": "done"},
        )
        # Its own picture, keyed on the same ids the executor reported under.
        drawn = attached.as_dict()
        self.assertEqual(
            [node["id"] for node in drawn["steps"]],
            [step["id"] for step in drawn["build"]["steps"]],
        )
        self.assertEqual(drawn["waves"], drawn["build"]["waves"])

    def test_a_finished_storm_is_a_record_rather_than_something_to_run_again(self):
        _, storm_id = self.approved()
        list(storm.run(storm_id))
        with self.assertRaises(storm.StormError):
            list(storm.run(storm_id))


class StepsWithNoDependencyOnEachOtherRunAtOnceTest(StormTestCase):
    """`docs/THE_PROPOSAL_LOOP.md`: *steps that do not depend on each other run
    at once. Steps that do, wait.*

    Proved with a barrier rather than a stopwatch. Two independent steps run a
    tool whose handler waits for the other one to arrive; if the storm ran them
    one after another the first would wait forever, time out, and the step would
    fail. So "both steps are done" IS the proof of concurrency, and there is no
    sleep anywhere and nothing to be flaky about.

    The handler is swapped and nothing else is. `tool_fingerprint()` covers what
    a tool accepts, touches and records - not which function object implements
    it - so this is not drift and the storm does not refuse it. That is the right
    line: a person approving a step approves what it does to their machine, and
    the harness replacing its own implementation is not a change to that.
    """

    def a_registry_that_needs_two_steps_at_once(self, barrier):
        def blocking(**_ignored):
            barrier.wait(timeout=20)
            return {"count": 7, "provenance": {"count": "measured"}}

        return registry_where("list_context", handler=blocking)

    def a_fanned_out_build(self) -> Build:
        def side(step_id: str) -> Step:
            return Step(
                id=step_id,
                tool="list_context",
                why=f"one half of a pair with nothing between them ({step_id})",
                arguments={},
                cost=a_cost(),
                exit_criterion=Criterion(
                    stated="the tool answered",
                    source="tool_result",
                    subject="count",
                    comparator="at_least",
                    value=7,
                ),
            )

        joined = Step(
            id="join",
            tool="list_runs",
            why="something that cannot start until both halves are in",
            arguments={},
            needs=("left", "right"),
            cost=a_cost(),
            exit_criterion=Criterion(
                stated="the tool answered",
                source="tool_result",
                subject="count",
                comparator="at_least",
                value=0,
            ),
        )
        return Build(
            id="a_build_that_fans_out",
            title="Two steps with nothing between them, and one that waits",
            for_outcome="ACTION__MEASURE_BASELINE",
            because="this test needs a wave with two steps in it",
            steps=(side("left"), side("right"), joined),
            environment=Environment(name="test", working_dir=str(self.root / "wd")),
            exit_criterion=Criterion(
                stated="everything ran",
                source="tool_result",
                subject="count",
                comparator="at_least",
                value=0,
            ),
        )

    def test_the_build_puts_them_in_one_wave(self):
        plan = self.a_fanned_out_build()
        self.assertEqual(plan.waves(), (("left", "right"), ("join",)))

    def test_two_independent_steps_are_in_flight_at_the_same_moment(self):
        import threading

        plan, storm_id = self.approved(self.a_fanned_out_build())
        barrier = threading.Barrier(2)
        rows = list(
            storm.run(
                storm_id, registry=self.a_registry_that_needs_two_steps_at_once(barrier)
            )
        )

        finished = {entry["step"]: entry
                    for entry in self.payloads(rows, storm.STEP_FINISHED)}
        # Neither of these could be `done` unless the other was running too.
        self.assertEqual(finished["left"]["state"], "done", finished["left"])
        self.assertEqual(finished["right"]["state"], "done", finished["right"])

    def test_a_step_that_depends_on_them_does_not_start_until_both_are_in(self):
        import threading

        plan, storm_id = self.approved(self.a_fanned_out_build())
        barrier = threading.Barrier(2)
        rows = list(
            storm.run(
                storm_id, registry=self.a_registry_that_needs_two_steps_at_once(barrier)
            )
        )

        finished_at = {row["payload"]["step"]: row["id"] for row in rows
                       if row["kind"] == storm.STEP_FINISHED}
        started_at = {row["payload"]["step"]: row["id"] for row in rows
                      if row["kind"] == storm.STEP_STARTED}
        self.assertGreater(started_at["join"], finished_at["left"])
        self.assertGreater(started_at["join"], finished_at["right"])
        self.assertEqual(storm.attach(storm_id).steps["join"].state, "done")


class ACancelledStormStopsBetweenStepsTest(StormTestCase):

    def test_cancelling_a_storm_nobody_is_running_ends_it(self):
        _, storm_id = self.approved()
        answer = storm.cancel(storm_id)
        self.assertEqual(answer["state"], "cancelled")
        attached = storm.attach(storm_id)
        self.assertEqual(attached.state, "cancelled")
        # And a cancelled storm is a record, not something to run.
        with self.assertRaises(storm.StormError):
            list(storm.run(storm_id))

    def test_cancelling_runs_nothing_that_had_not_started(self):
        _, storm_id = self.approved()
        storm.cancel(storm_id)
        self.assertEqual(
            {name: step.state for name, step in storm.attach(storm_id).steps.items()},
            {"attach": "queued", "count": "queued", "recheck": "queued"},
        )


# ---------------------------------------------------------------------------
# 2. Approval is a contract.


class ApprovalIsAContractTest(StormTestCase):
    """Approve a build, mutate it, run it - and watch the storm refuse."""

    def mutations(self, plan: Build) -> dict[str, Build]:
        """Six ways an approved plan can come back different."""
        first, second, third = plan.steps
        return {
            "a different argument": replace(
                plan,
                steps=(
                    replace(
                        first,
                        arguments={**dict(first.arguments), "note": "changed later"},
                    ),
                    second,
                    third,
                ),
            ),
            "a step added": replace(
                plan,
                steps=plan.steps
                + (
                    Step(
                        id="extra",
                        tool="list_runs",
                        why="a step nobody approved",
                        arguments={},
                        cost=a_cost(),
                        exit_criterion=Criterion(
                            stated="it answered",
                            source="tool_result",
                            subject="count",
                            comparator="at_least",
                            value=0,
                        ),
                    ),
                ),
            ),
            "a step removed": replace(plan, steps=(first, second)),
            "a different build": replace(plan, id="some_other_build"),
            "a different outcome": replace(
                plan, for_outcome="ACTION__MEASURE_BASELINE"
            ),
            "a different environment": replace(
                plan,
                environment=Environment(
                    name="somewhere else", working_dir=str(self.root / "elsewhere")
                ),
            ),
        }

    def test_a_mutated_plan_is_refused_and_names_what_changed(self):
        """THE TEST THE CONTRACT STANDS ON. Approve, mutate, run, refuse."""
        plan, storm_id = self.approved()
        changed = replace(
            plan,
            steps=(
                replace(
                    plan.steps[0],
                    arguments={
                        **dict(plan.steps[0].arguments),
                        "note": "slipped in after approval",
                    },
                ),
                plan.steps[1],
                plan.steps[2],
            ),
        )

        rows = list(storm.run(storm_id, plan=changed))

        self.assertEqual(self.kinds(rows), [storm.REFUSED])
        refusal = rows[0]["payload"]
        self.assertIn("step 'attach' does something different now",
                      refusal["deviations"])
        self.assertEqual(refusal["state"], "waiting_approval")

        # NOTHING RAN. Not the step that changed, and not the two that did not.
        self.assertNotIn(
            storm.STEP_STARTED,
            [row["kind"] for row in events.since(f"thread:{self.thread_id}", 0, 500)],
        )
        self.assertEqual(
            {name: step.state for name, step in storm.attach(storm_id).steps.items()},
            {"attach": "queued", "count": "queued", "recheck": "queued"},
        )

    def test_the_storm_names_the_same_deviations_the_build_itself_does(self):
        """A second opinion about what changed is how a contract drifts.

        `Build.deviations_from` is the object's own answer and the storm's
        manifest is a reduction of it that lives on disk. On six mutations they
        must say exactly the same sentences - not merely both be non-empty.
        """
        plan, storm_id = self.approved()
        _, manifest = storm.load(storm_id)
        for description, mutated in self.mutations(plan).items():
            with self.subTest(description):
                self.assertEqual(
                    set(manifest.deviations_from(mutated)),
                    set(mutated.deviations_from(plan)),
                )
                self.assertTrue(manifest.deviations_from(mutated))

    def test_every_mutation_stops_the_storm(self):
        plan, storm_id = self.approved()
        for description, mutated in self.mutations(plan).items():
            with self.subTest(description):
                rows = list(storm.run(storm_id, plan=mutated))
                self.assertEqual(self.kinds(rows), [storm.REFUSED])
                self.assertTrue(rows[0]["payload"]["deviations"])

    def test_the_approved_plan_itself_is_not_a_deviation(self):
        """The check has to let the real thing through, or it is just a wall."""
        plan, storm_id = self.approved()
        _, manifest = storm.load(storm_id)
        self.assertEqual(manifest.deviations_from(plan), ())
        rows = list(storm.run(storm_id, plan=plan))
        self.assertNotIn(storm.REFUSED, self.kinds(rows))
        self.assertEqual(storm.attach(storm_id).steps["count"].state, "done")

    def test_a_plan_that_does_not_hash_to_its_approval_is_refused(self):
        plan, _ = self.approved()
        blueprint = plan.as_dict()
        blueprint["steps"][0]["arguments"]["role"] = "something else"
        with self.assertRaises(storm.StormRefused):
            storm.Manifest.of(blueprint, fingerprint=plan.fingerprint())

    def test_a_step_edited_after_it_was_fingerprinted_is_refused(self):
        """The plan and the hash of the plan have to agree with each other."""
        plan, _ = self.approved()
        blueprint = plan.as_dict()
        blueprint["steps"][1]["arguments"]["finish_the_count"] = False
        with self.assertRaises(storm.StormRefused) as caught:
            storm.Manifest.of(blueprint, fingerprint=buildmod._digest(blueprint))
        self.assertIn("count", caught.exception.deviations[0])

    def test_a_step_naming_a_tool_only_a_person_may_run_is_refused(self):
        plan, _ = self.approved()
        blueprint = plan.as_dict()
        blueprint["steps"][0]["tool"] = "state_facts"
        blueprint["steps"][0]["arguments"] = {"facts": {}}
        blueprint["steps"][0]["contract"] = ""
        with self.assertRaises(storm.StormRefused) as caught:
            storm.Manifest.of(blueprint, fingerprint=buildmod._digest(blueprint))
        self.assertIn("state_facts", str(caught.exception))

    def test_a_step_sending_an_argument_the_tool_does_not_take_is_refused(self):
        plan, _ = self.approved()
        blueprint = plan.as_dict()
        blueprint["steps"][0]["arguments"]["invented"] = "nonsense"
        blueprint["steps"][0]["contract"] = ""
        with self.assertRaises(storm.StormRefused) as caught:
            storm.Manifest.of(blueprint, fingerprint=buildmod._digest(blueprint))
        self.assertIn("invented", str(caught.exception))


class ATheToolCannotChangeUnderTheApprovedPlanTest(StormTestCase):
    """The deviation a build-to-build comparison structurally cannot see."""

    def refusal(self, storm_id: int, registry: Registry) -> dict:
        rows = list(storm.run(storm_id, registry=registry))
        self.assertEqual(self.kinds(rows), [storm.REFUSED])
        return rows[0]["payload"]

    def test_a_tool_whose_schema_grew_an_argument_stops_the_storm(self):
        _, storm_id = self.approved()
        wider = dict(REGISTRY.get("measure_eval_set").schema)
        wider["properties"] = {
            **dict(wider.get("properties") or {}),
            "hurry_up": {"type": "boolean", "description": "added after approval"},
        }
        payload = self.refusal(
            storm_id, registry_where("measure_eval_set", schema=wider)
        )
        self.assertTrue(
            any("measure_eval_set" in note for note in payload["deviations"]),
            payload,
        )
        self.assertEqual(
            {name: step.state for name, step in storm.attach(storm_id).steps.items()},
            {"attach": "queued", "count": "queued", "recheck": "queued"},
        )

    def test_a_tool_that_started_needing_permission_is_named_as_that(self):
        _, storm_id = self.approved()
        payload = self.refusal(
            storm_id, registry_where("attach_context", approval="always")
        )
        self.assertTrue(
            any("permission" in note for note in payload["deviations"]), payload
        )

    def test_a_tool_that_is_no_longer_registered_stops_the_storm(self):
        _, storm_id = self.approved()
        payload = self.refusal(storm_id, registry_where("attach_context", gone=True))
        self.assertTrue(
            any("no longer a registered tool" in note
                for note in payload["deviations"]),
            payload,
        )

    def test_a_tool_that_gained_network_access_cannot_run_in_a_sealed_sandbox(self):
        """The egress rule is re-checked against the tools the plan names.

        A sandbox that has no egress cannot leak, whatever the model says - and
        that guarantee is worth nothing if a tool can acquire the ability to
        leave the machine between a proposal and a run.
        """
        _, storm_id = self.approved()
        _, manifest = storm.load(storm_id)
        self.assertFalse(manifest.environment["egress"])
        reaching = registry_where(
            "measure_eval_set",
            reads=tuple(REGISTRY.get("measure_eval_set").reads) + ("providers",),
        )
        with self.assertRaises(storm.StormRefused) as caught:
            storm.Manifest.of(
                manifest.blueprint,
                fingerprint=manifest.fingerprint,
                registry=reaching,
            )
        self.assertIn("egress", str(caught.exception))

    def test_the_unchanged_registry_is_not_drift(self):
        _, storm_id = self.approved()
        _, manifest = storm.load(storm_id)
        self.assertEqual(manifest.drift(), ())


# ---------------------------------------------------------------------------
# 3. A step that cannot show it worked did not work.


class AStepThatCannotShowItWorkedDidNotWorkTest(StormTestCase):

    def test_a_tool_that_succeeded_still_fails_a_criterion_it_does_not_meet(self):
        plan, storm_id = self.approved(self.a_build_that_will_not_pass())
        rows = list(storm.run(storm_id))

        finished = {entry["step"]: entry for entry in
                    self.payloads(rows, storm.STEP_FINISHED)}
        # The tool itself was perfectly happy: it ran, it answered, it reported
        # no error, and it produced the output the plan said it would.
        self.assertEqual(finished["look"]["result"]["count"], 0)
        self.assertNotIn("error", finished["look"]["result"])
        self.assertEqual(finished["look"]["outputs"], {"count": 0})
        # The step was not.
        self.assertEqual(finished["look"]["state"], "failed")
        self.assertFalse(finished["look"]["verification"]["ok"])
        self.assertEqual(
            finished["look"]["verification"]["stated"],
            "there are at least a thousand contexts on file",
        )

    def test_a_step_that_needed_a_failed_step_does_not_run(self):
        _, storm_id = self.approved(self.a_build_that_will_not_pass())
        rows = list(storm.run(storm_id))

        self.assertEqual(
            [row["payload"]["step"] for row in rows
             if row["kind"] == storm.STEP_STARTED],
            ["look"],
        )
        skipped = self.payloads(rows, storm.STEP_SKIPPED)
        self.assertEqual([entry["step"] for entry in skipped], ["after"])
        self.assertIn("'look'", skipped[0]["because"])
        self.assertEqual(storm.attach(storm_id).state, "failed")

    def test_the_whole_build_is_judged_by_the_criterion_it_declared(self):
        """Not by whether the steps happened to finish.

        The storm evaluates the build's own `exit_criterion` against the
        observation its `source` names, and reports what it saw. It does not get
        to pick a looser one because everything ran.
        """
        plan, storm_id = self.approved()
        list(storm.run(storm_id))
        attached = storm.attach(storm_id)
        self.assertEqual(
            attached.verification["stated"], plan.exit_criterion.stated
        )
        # `source: diagnosis` means the tree walked again over what the ledger
        # holds now - which is what the steps have just been changing.
        fresh = REGISTRY.call(
            "run_diagnosis", {"facts": {}}, actor=evidence.HARNESS,
            thread_id=self.thread_id,
        )
        seen, _ = buildmod._dig(fresh, plan.exit_criterion.subject)
        self.assertEqual(attached.verification["saw"], seen)

    def test_the_build_that_ran_actually_passes_its_own_criterion(self):
        """AND THE LINE THAT WAS MISSING, WHICH IS THE ONLY ONE THAT CARED.

        The test above asserts WHICH criterion was judged and WHAT was seen. It
        never asserted the verdict, and on 2026-08-24 the verdict was `false`
        for every run of this plan and had been since the plan was written:
        `app/tools/propose.py` stated `value="passed"` while the engine writes
        `PASSED`, so `_compare`'s `equals` - an exact string test, as it has to
        be - reported `saw 'PASSED', wanted 'passed'`. Every step finished,
        `deviations` was empty, the eval set was really carved and really
        counted, and the storm still ended `failed`. Two of the product's builds
        carried that literal and they are the two most common early ones.

        Driven end to end over HTTP before the fix and after: `state: failed`
        with `verification.ok: false` became `state: done` with
        `verification.ok: true` and `because: "saw 'PASSED', wanted 'PASSED'"`.

        THE FACTS ARE SAID THROUGH `state_facts` AND NOT HANDED TO
        `assemble_facts`, which is the difference between this and
        `a_real_build`. The criterion's `source` is `diagnosis`, so it is judged
        by a FRESH walk over what the thread's ledger holds - and a fact that
        was only ever an argument to a helper is not in that ledger, so the
        re-walk stops above the gate tree and sees `NOT_REACHED`. That is the
        engine being right, not the plan being wrong, and a test that did not
        record the facts would have been asserting against the wrong state.
        """
        path = self.eval_file()
        said = REGISTRY.call(
            "state_facts",
            {"facts": {"goal_text": "route support tickets", "modality": "text",
                       "target_score": 0.9}},
            actor=evidence.USER,
            thread_id=self.thread_id,
        )
        self.assertTrue(said["ok"], said)
        sheet, trail = evidence.assemble_facts(self.thread_id, {}, evidence.USER)
        result = diagnosis.diagnose(sheet)
        self.assertEqual(result.outcome, "BLOCKED__BUILD_EVAL_SET")
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
        storm_id = storm.declare(plan, thread_id=self.thread_id)["storm"]
        list(storm.run(storm_id))

        attached = storm.attach(storm_id)
        self.assertEqual(attached.verification["saw"], diagnosis.GATE_PASSED)
        self.assertTrue(attached.verification["ok"], attached.verification)
        self.assertEqual(attached.deviations, ())
        self.assertEqual(attached.state, "done")

    def test_no_plan_compares_a_gate_status_against_a_word_the_engine_never_writes(
        self,
    ):
        """THE STRUCTURAL HALF, so a third copy of the literal cannot be typed.

        Every proposer this product has, walked; every exit criterion whose
        subject is a gate's status, checked against the statuses
        `app/diagnosis.py` can actually write. A criterion comparing against
        anything else is a plan that can never pass, and it fails silently -
        the work happens, the storm reports `failed`, and nothing says why.
        """
        statuses = {diagnosis.GATE_PASSED, "FAILED", "NOT_REACHED", "UNSUBSTANTIATED"}
        checked = 0
        for outcome in sorted(propose.COVERAGE):
            plan = self.a_plan_for(outcome)
            if plan is None:
                continue
            criteria = [plan.exit_criterion] + [
                step.exit_criterion for step in plan.steps if step.exit_criterion
            ]
            for criterion in criteria:
                subject = str(criterion.subject or "")
                if not subject.startswith("gate_ledger.") or not subject.endswith(
                    ".status"
                ):
                    continue
                checked += 1
                self.assertEqual(criterion.comparator, "equals", subject)
                self.assertIn(
                    criterion.value,
                    statuses,
                    f"{outcome} compares {subject} against {criterion.value!r}, "
                    "which this engine never writes, so the plan cannot pass",
                )
        self.assertGreater(checked, 0, "no plan compared a gate status at all")

    def a_plan_for(self, outcome):
        """One plan per covered outcome, or None where this fixture cannot reach.

        A proposer that refuses for want of a fact this test has not supplied is
        not the subject here; what is under test is the criteria of the plans
        that DO come out, and skipping the rest is honest rather than lenient -
        `checked` is asserted non-zero so a skip-everything run is red.
        """
        path = self.eval_file()
        sheet, trail = evidence.assemble_facts(
            self.thread_id,
            {"goal_text": "route support tickets", "modality": "text",
             "target_score": 0.9},
            evidence.USER,
        )
        result = diagnosis.diagnose(sheet)
        try:
            return propose.propose(
                propose.Situation(
                    outcome=outcome,
                    result=result,
                    values={row["fact"]: row["value"] for row in trail},
                    origins={row["fact"]: row["origin"] for row in trail},
                    hows={row["fact"]: row.get("how") or "" for row in trail},
                    eval_path=str(path),
                    input_field="q",
                    expected_field="a",
                )
            )
        except Exception:  # noqa: BLE001 - see the docstring
            return None


# ---------------------------------------------------------------------------
# 4. The routes.


class TheStormApiTest(StormTestCase):
    """Approval, and running, over HTTP - where a caller supplies the plan."""

    def setUp(self):
        super().setUp()
        self.client = support.api_client(app)
        self.path = self.eval_file()
        self.said = REGISTRY.call(
            "state_facts",
            {"facts": {"goal_text": "route support tickets", "modality": "text",
                       "target_score": 0.9}},
            actor=evidence.USER,
            thread_id=self.thread_id,
        )
        self.assertTrue(self.said["ok"], self.said)

    def proposal(self) -> dict:
        return {"facts": {}, "eval_path": str(self.path)}

    def a_fingerprint(self) -> str:
        proposed = REGISTRY.call(
            "propose_build", self.proposal(), actor=evidence.USER,
            thread_id=self.thread_id,
        )
        self.assertTrue(proposed["ok"], proposed)
        return proposed["approve"]

    def test_approving_records_the_contract_and_runs_nothing(self):
        response = self.client.post(
            "/api/storms",
            json={"thread_id": self.thread_id, "approve": self.a_fingerprint(),
                  "proposal": self.proposal()},
        )
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(body["state"], "queued")
        self.assertEqual([node["state"] for node in body["steps"]],
                         ["queued", "queued", "queued"])
        self.assertTrue(body["build"]["steps"])

    def test_a_fingerprint_that_is_not_this_plan_is_refused(self):
        response = self.client.post(
            "/api/storms",
            json={"thread_id": self.thread_id,
                  "approve": "0" * 64,
                  "proposal": self.proposal()},
        )
        self.assertEqual(response.status_code, 409, response.text)
        detail = response.json()["detail"]
        self.assertEqual(detail["error"], "not_the_plan_you_approved")
        self.assertEqual(
            self.client.get(f"/api/storms?thread_id={self.thread_id}").json()["storms"],
            [],
        )

    def test_running_it_through_the_route_finishes_every_step(self):
        approved = self.client.post(
            "/api/storms",
            json={"thread_id": self.thread_id, "approve": self.a_fingerprint(),
                  "proposal": self.proposal()},
        ).json()
        storm_id = approved["storm"]

        ran = self.client.post(
            f"/api/storms/{storm_id}/run", json={"background": False}
        )
        self.assertEqual(ran.status_code, 200, ran.text)
        body = ran.json()
        self.assertEqual([node["state"] for node in body["steps"]],
                         ["done", "done", "done"])
        self.assertTrue(body["events"])

        # And the progress is in the conversation, replayable by id.
        stream = self.client.get(
            f"/api/events?scope=thread:{self.thread_id}&follow=false"
        )
        self.assertEqual(stream.status_code, 200)
        self.assertIn("storm.step.finished", stream.text)

    def test_cancelling_through_the_route_ends_a_storm_that_never_started(self):
        approved = self.client.post(
            "/api/storms",
            json={"thread_id": self.thread_id, "approve": self.a_fingerprint(),
                  "proposal": self.proposal()},
        ).json()
        cancelled = self.client.post(f"/api/storms/{approved['storm']}/cancel")
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertEqual(cancelled.json()["state"], "cancelled")
        self.assertEqual(
            [node["state"] for node in cancelled.json()["steps"]],
            ["queued", "queued", "queued"],
        )
        # And it stays cancelled: a cancelled storm is a record.
        refused = self.client.post(
            f"/api/storms/{approved['storm']}/run", json={"background": False}
        )
        self.assertEqual(refused.status_code, 409, refused.text)

    def test_the_storms_of_a_thread_are_listed_newest_first(self):
        response = self.client.post(
            "/api/storms",
            json={"thread_id": self.thread_id, "approve": self.a_fingerprint(),
                  "proposal": self.proposal()},
        )
        # Assert the status BEFORE reading the body. This test used to go
        # straight to .json() and then index `first["storm"]`, so on the rare
        # run where the POST did not return a storm it failed with
        # `KeyError: 'storm'` and threw away the only thing that would have
        # explained why. Every other test in this class already asserts the
        # status first; this one did not, and that is what made an
        # intermittent failure uncharacterisable rather than merely rare.
        self.assertEqual(response.status_code, 201, response.text)
        first = response.json()
        listed = self.client.get(f"/api/storms?thread_id={self.thread_id}").json()
        self.assertEqual([row["id"] for row in listed["storms"]], [first["storm"]])
        self.assertEqual(listed["storms"][0]["fingerprint"], self.a_fingerprint())

    def test_an_unknown_storm_is_a_404(self):
        self.assertEqual(self.client.get("/api/storms/4321").status_code, 404)
        self.assertEqual(
            self.client.post("/api/storms/4321/run", json={"background": False})
            .status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
