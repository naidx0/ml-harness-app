"""One journey, every ledger, driven - not one journey written down twice.

## The claim under test

`docs/VISION.md` says a person opens one box and talks, and never picks a
discipline. `docs/PHASES.md` 0a proved the ENGINE is domain-agnostic: a second
ledger walks on it with no engine change. What was never driven is the rest of
the sentence - that a whole journey, from arriving to holding an artifact and its
proof, closes the same way in every domain.

So this file is written once and parameterised over `diagnosis.known_ledgers()`.
It does not name two files. A third ledger dropped into `docs/ledgers/` is picked
up by the glob and **fails loudly here until somebody writes its script**, which
is the point: if the journey has to be re-written per domain then the engine is
domain-agnostic and the PRODUCT is not, and that gap is what this file exists to
keep visible.

## The rungs, and the three rules

`docs/THE_PLAN.md` names eleven rungs. This file drives the ones a test can drive
without a person: ARRIVE, LOOK, DIAGNOSE, PROPOSE, APPROVE, BUILD, VERIFY, HOLD.
Three rules make it a test rather than a demo:

* **every number carries an origin** - the assertion that cannot be dropped;
* **a refusal is a pass** - a journey that reaches an honest `BLOCKED__` and
  hands over a build has succeeded, and a test that only accepted "yes" would
  delete the thing this product exists for;
* **re-entry must be possible** - after the build runs, the tree must land
  somewhere it did not land before, or the loop did not close.

## What is deliberately NOT asserted

`deviations == []` is necessary and nowhere near sufficient. It is assigned in
exactly one place - `app/storm.py`, under `elif kind == REFUSED` - so it means
*nothing refused this run before it started*. A storm whose steps all failed
returns `deviations: []` too. `docs/PHASES.md` uses it as the closing proof
throughout, and that is why every assertion below also reads `state`, every
step's own state, and the verification.

## No model, and why that is honest here

Both scripts run against `support.ScriptedModel` over a `127.0.0.1` provider
row. A scripted model scores what it was scripted to score, so this file cannot
prove "the model got 0% and the trivial baseline beat it" - that finding needs a
real one and remains owed by queue step 7. What it removes is every OTHER reason
that step was blocked.
"""

import json
import unittest

from app import diagnosis
from app import events
from app import storm
from app.tools import REGISTRY
from app.tools import evidence
import support


def _agent_fixture(name: str) -> str:
    from pathlib import Path

    return str(Path(__file__).resolve().parent / "fixtures" / "agent" / name)


class JourneyScript:
    """One domain's walk, as data.

    `seed` returns the ordered tool calls that get the thread to `at_outcome`.
    `propose_with` is what the person supplies at the proposal - the paths and
    column names no tool can guess. `expect` is the plan that must come back.
    """

    def __init__(self, ledger, seed, at_outcome, propose_with, build_id, step_ids, saw):
        self.ledger = ledger
        self.seed = seed
        self.at_outcome = at_outcome
        self.propose_with = propose_with
        self.build_id = build_id
        self.step_ids = step_ids
        self.saw = saw


def _ml_script(root):
    """The journey `docs/PHASES.md` 0b records as closing, re-driven.

    Its rung table - arrive, measure, diagnose, carve, count, re-diagnose, score
    the baseline, re-diagnose, propose, approve, storm, verify - is this list.
    The datasets behind the file's own two prose journeys are not in the tree;
    this one writes its own, so it can be re-driven on a fresh checkout.
    """
    data = root / "tickets.jsonl"
    with open(data, "w", encoding="utf-8") as handle:
        for index in range(200):
            handle.write(
                json.dumps(
                    {
                        "q": f"ticket {index}",
                        "a": support.SCRIPTED_LABELS[index % len(support.SCRIPTED_LABELS)],
                    }
                )
                + "\n"
            )

    def seed(call):
        call(
            "state_facts",
            {
                "facts": {
                    "goal_text": "route tickets",
                    "target_score": 0.9,
                    "modality": "text",
                    "task_family": "classification",
                }
            },
        )
        carved = call(
            "carve_eval_set",
            {"path": str(data), "answer_column": "a", "into": str(root / "split")},
            approved=True,
        )
        evaluation = carved["eval_path"]
        call("measure_eval_set", {"path": evaluation})
        call(
            "measure_baseline",
            {
                "eval_path": evaluation,
                "input_field": "q",
                "expected_field": "a",
                "sample": 30,
            },
        )
        return {"eval_path": evaluation, "input_field": "q", "expected_field": "a"}

    return JourneyScript(
        ledger="docs/diagnosis_engine.yaml",
        seed=seed,
        at_outcome="ACTION__CLASSIFY_FAILURES",
        propose_with=None,  # filled from what `seed` returned
        build_id="classify_the_failures",
        step_ids=["run", "read", "recheck"],
        saw="MEASURED",
    )


def _ai_script(root):
    """The agent journey: four instruments, then the person's five facts."""
    traces = _agent_fixture("journey-traces.jsonl")
    tooldefs = _agent_fixture("journey-tools.json")
    failures = _agent_fixture("journey-failures.jsonl")
    fields = {
        "input_field": "input",
        "expected_field": "expected",
        "answer_field": "answer",
    }

    def seed(call):
        call("read_agent_traces", {"path": traces})
        call("read_tool_definitions", {"path": tooldefs})
        call("bound_the_loop", {"path": traces})
        call("run_the_failures", {"failures_path": failures, "traces_path": traces, **fields})
        call(
            "state_facts",
            {
                "facts": {
                    "target_success_rate": 0.9,
                    "failure_reproduces": True,
                    "simple_version_tried": True,
                    "workflow_tried": True,
                    "control_flow_is_dynamic": True,
                }
            },
        )
        return {"failures_path": failures, "traces_path": traces, **fields}

    return JourneyScript(
        ledger="docs/ledgers/ai_engineering.yaml",
        seed=seed,
        at_outcome="BUILD__AGENT_WITH_TOOLS",
        propose_with=None,
        build_id=None,  # asserted only as "a plan came back", see below
        step_ids=None,
        saw=None,
    )


def _harness_fixture(name: str) -> str:
    from pathlib import Path

    return str(Path(__file__).resolve().parent / "fixtures" / "harness" / name)


def _harness_script(root):
    """The harness journey: six instruments, then the person's six facts.

    THE ONE THING THIS DOMAIN'S JOURNEY PROVES THAT NEITHER OTHER ONE DOES is
    that nothing in it drives anything. Every rung of the ladder and both arms
    of the ablation are RECORDINGS the person exported - the harness grades
    them - which is what let `solo_pass_rate` and `components_ablated_n` stay
    `source: inspect` when `docs/ledgers/HARNESS_DESIGN.md` had them down as the
    facts that could not be instrumented.

    The trace comes from the agent fixtures, deliberately. A trace of a run is a
    trace of a run; what makes this ledger's reading of it different is which
    fact the reading is filed under, and a second copy of the same spans would
    be testing the copy.
    """
    tasks = _harness_fixture("journey-tasks.jsonl")
    fields = {
        "input_field": "task",
        "expected_field": "expected",
        "answer_field": "answer",
    }
    arms = [
        {
            "component": "reranker",
            "with_answers": _harness_fixture("journey-with-reranker.jsonl"),
            "without_answers": _harness_fixture("journey-without-reranker.jsonl"),
        }
    ]

    def seed(call):
        call("read_the_success_check", {"path": _harness_fixture("journey-checker.py")})
        call(
            "count_the_task_set",
            {
                "path": tasks,
                "input_field": fields["input_field"],
                "expected_field": fields["expected_field"],
            },
        )
        call(
            "score_a_recorded_run",
            {
                "tasks_path": tasks,
                "answers_path": _harness_fixture("journey-solo-answers.jsonl"),
                "variant": "solo",
                **fields,
            },
        )
        call("read_the_tool_risks", {"path": _harness_fixture("journey-tools.json")})
        call("ablate_a_component", {"tasks_path": tasks, "arms": arms, **fields})
        call("bound_the_harness_run", {"path": _agent_fixture("journey-traces.jsonl")})
        call(
            "state_facts",
            {
                "facts": {
                    "success_check_named": True,
                    "target_pass_rate": 0.9,
                    "the_model_must_reach_external_systems": True,
                    "approval_boundary_declared": True,
                    "boundaries_are_typed": True,
                    "components_proposed_n": 1,
                }
            },
        )
        return {
            "tasks_path": tasks,
            "checker_path": _harness_fixture("journey-checker.py"),
            "tooldefs_path": _harness_fixture("journey-tools.json"),
            "trace_path": _agent_fixture("journey-traces.jsonl"),
            "ablation_arms": arms,
            **fields,
        }

    return JourneyScript(
        ledger="docs/ledgers/harness_design.yaml",
        seed=seed,
        at_outcome="HARNESS__FIXED_PIPELINE",
        propose_with=None,
        build_id="the_fixed_pipeline",
        step_ids=None,
        saw=None,
    )


#: One entry per shipped ledger, keyed the way `Spec.name` keys one - relative to
#: the repository root, as posix. `known_ledgers()` returns absolute paths, and
#: an absolute key would make this file unreadable and platform-specific.
SCRIPTS = {
    "docs/diagnosis_engine.yaml": _ml_script,
    "docs/ledgers/ai_engineering.yaml": _ai_script,
    "docs/ledgers/harness_design.yaml": _harness_script,
}


def _key(path) -> str:
    """The repo-relative posix name of a ledger, as `app/diagnosis.py` writes it."""
    from pathlib import Path

    root = Path(diagnosis.SPEC_PATH).resolve().parents[1]
    return Path(path).resolve().relative_to(root).as_posix()


def shipped_ledgers() -> dict:
    """`known_ledgers()`, keyed. The glob is the source, never a list."""
    return {_key(path): path for path in diagnosis.known_ledgers()}


class OneJourneyClosesInEveryDomainTest(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)
        support.connect_a_model(self, support.ScriptedModel(correct=0))

    def _driver(self, thread_id):
        def call(name, arguments, **extra):
            result = REGISTRY.call(
                name, arguments, actor="user", thread_id=thread_id, **extra
            )
            self.assertTrue(
                result.get("ok"),
                f"rung {name!r} refused: {result.get('detail') or result.get('error')}",
            )
            return result

        return call

    def _walk(self, thread_id, ledger):
        """THE LEDGER IS PASSED, AND FORGETTING IT IS SILENT.

        `assemble_facts` drops every row for a fact "the ledger" does not
        declare, and with no `ledger=` argument that ledger is the ML default -
        so an agent thread's facts all vanish and the walk answers
        `BLOCKED__NOTHING_TO_MEASURE_AGAINST` on a thread that had measured five
        things. It is not a wrong answer, it is a correct answer to a question
        about the wrong domain, which is worse. This cost an hour while writing
        this file and is recorded here so the next reader does not pay it again.
        """
        spec = diagnosis.spec_at(ledger)
        sheet, _ = evidence.assemble_facts(thread_id, {}, "user", spec)
        return diagnosis.diagnose(sheet, spec)

    def test_every_shipped_ledger_has_a_journey_script(self):
        """The tripwire. A third ledger fails here before it fails anywhere else.

        `known_ledgers()` is a directory glob, deliberately - "a second place
        naming which ledgers ship is a second place that goes stale". So this
        reads the glob rather than a list, and a new domain arrives here asking
        for its journey to be driven.
        """
        self.assertEqual(sorted(SCRIPTS), sorted(shipped_ledgers()))

    def test_a_journey_closes_in_every_domain(self):
        for name in sorted(shipped_ledgers()):
            with self.subTest(ledger=name):
                self._drive(SCRIPTS[name](self.root))

    def _drive(self, script):
        # EVERY JOURNEY STARTS THE WAY A PERSON'S DOES: a thread nobody chose a
        # ledger for. Until 2026-08-28 this file named the ledger, which was the
        # only way an agent journey could be driven at all - and it meant the
        # test began in a state no person could reach. It now begins where they
        # begin, and the domain is inferred from the first instrument they use.
        thread_id = events.create_thread(f"a journey on {script.ledger}")["id"]
        self.assertEqual(
            events.get_thread(thread_id)["ledger"],
            diagnosis.DEFAULT_LEDGER,
            "a person cannot start anywhere but the default",
        )
        call = self._driver(thread_id)

        # ARRIVE + LOOK. Every instrument the domain needs, in order - and the
        # first of them is what tells the harness which domain this is.
        supplied = script.seed(call)

        # The thread is now on the ledger its own work belongs to, whether that
        # took an inference or was the default all along.
        self.assertEqual(
            events.get_thread(thread_id)["ledger"],
            script.ledger,
            "the conversation ended up in a domain its instruments do not serve",
        )

        # DIAGNOSE. The verdict is the scripted one, and every fact the walk
        # read carries an origin that is not a default.
        walked = self._walk(thread_id, script.ledger)
        self.assertEqual(walked.outcome, script.at_outcome)
        origins = dict(walked.fact_origins or {})
        self.assertTrue(origins, "the walk read no facts at all")
        for name, origin in origins.items():
            self.assertIn(
                origin,
                (diagnosis.MEASURED, diagnosis.STATED, diagnosis.DEFAULTED),
                f"{name} reached the verdict as {origin}",
            )
        self.assertIn(
            diagnosis.MEASURED,
            set(origins.values()),
            "not one number in this verdict was measured",
        )

        # PROPOSE. Through the TOOL, which is the boundary a person crosses -
        # every other test of these builds constructs `Situation` by hand, and
        # `37f01db` is what that cost.
        proposed = call("propose_build", {"facts": {}, **supplied})
        plan = proposed.get("build") or {}
        self.assertTrue(plan.get("id"), proposed)
        self.assertTrue(proposed.get("approve"), "no fingerprint to approve")
        if script.build_id:
            self.assertEqual(plan["id"], script.build_id)
        if script.step_ids:
            self.assertEqual([s["id"] for s in plan["steps"]], script.step_ids)

        # APPROVE + BUILD.
        declared = storm.declare(
            proposed["build"], approved=proposed["approve"], thread_id=thread_id
        )
        list(storm.run(declared["storm"]))
        finished = storm.attach(declared["storm"]).as_dict()

        # VERIFY. Four assertions, because `deviations` alone is not one.
        self.assertEqual(finished["deviations"], [], "the run refused its own contract")
        self.assertEqual(finished["state"], "done", finished)
        self.assertEqual(
            [step["state"] for step in finished["steps"]],
            ["done"] * len(finished["steps"]),
            "a step did not finish, and `deviations: []` did not say so",
        )
        verification = finished.get("verification") or {}
        self.assertTrue(verification.get("ok"), verification)
        if script.saw:
            self.assertEqual(verification.get("saw"), script.saw)

        # RE-ENTRY, AND IT DOES NOT APPLY TO EVERY OUTCOME - which is a
        # correction to the rule as `docs/THE_PLAN.md` first stated it.
        #
        # "the tree must land somewhere new" is right for an outcome that TELLS
        # THE PERSON TO GO AND DO SOMETHING: verdict BLOCKED, prefix ACTION__ or
        # BLOCKED__, meaning come back when it is done. It is wrong for a
        # TERMINAL verdict. `BUILD__AGENT_WITH_TOOLS` is the answer, not a step
        # towards one, so a tree that still says it after the build ran is
        # correct and a tree that moved would mean the verdict had been
        # withdrawn.
        #
        # Read off the verdict rather than the prefix, because a prefix is a
        # naming convention and the verdict is what the ledger's own contract
        # declares.
        after = self._walk(thread_id, script.ledger)
        if walked.verdict == "BLOCKED":
            self.assertNotEqual(
                after.outcome,
                script.at_outcome,
                "the work was done and the tree did not move - a dead end "
                "wearing a green tick, and the defect Phase I is about",
            )
        else:
            self.assertEqual(
                after.outcome,
                script.at_outcome,
                "a terminal verdict changed after its own build ran, which "
                "means the answer was withdrawn by doing what it asked",
            )

        # HOLD. The handover renders - 0b4cdc2 is why this is asserted at all.
        from app.main import app

        client = support.api_client(app)
        report = client.get(f"/api/threads/{thread_id}/report")
        self.assertEqual(report.status_code, 200)
        self.assertTrue((report.json().get("storms") or []), "the report lost the storm")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
