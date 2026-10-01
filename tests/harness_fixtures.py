"""Fact sheets for the harness-building ledger, one per answer it can give.

The third ledger's answer to `diagnosis_fixtures.py` and to
`test_the_ai_ledger_builds_what_it_asks_for.py`'s `SHEETS`, and it exists for
the reason those do: a sweep that does not drive a ledger's sheets proves that
ledger's instruments unreachable while believing itself complete. When the
`agent` pack shipped, the block-reachability sweep did exactly that to a third
of the registry until AI sheets were added to it, and `docs/PHASES.md` records
it as a one-directional-bound defect.

## What is in here

`SHEETS` is one entry per outcome this ledger can reach, keyed by the answer it
produces, and every one of them is DRIVEN rather than asserted -
`test_the_harness_ledger_refuses_before_it_builds.py` walks each sheet through
the real engine and checks it lands where its key says.

## The origins are the point, not the values

Facts this ledger declares `source: inspect` are stamped MEASURED here, because
that is the only origin their gates admit and a fixture that used STATED would
be testing a route no real conversation can take. Facts declared `source: ask`
are STATED, because that is what a person answering a question produces. Getting
this backwards in either direction makes a fixture that passes and proves
nothing.
"""

from app import diagnosis


#: Every fact this ledger declares `source: inspect`. A tool stamps these or
#: nothing does, and only MEASURED opens their gates - so the fixture marks them
#: the way an instrument would rather than the way a person would.
MEASURED_FACTS = frozenset(
    {
        "success_check_characters",
        "success_check_is_a_program",
        "harness_tasks_n",
        "can_rerun_tasks",
        "solo_pass_rate",
        "pipeline_pass_rate",
        "single_loop_pass_rate",
        "components_ablated_n",
        "components_that_earned_their_place",
        "harness_tools_n",
        "tools_risk_annotated_n",
        "harness_spans_read",
        "harness_has_traces",
        "harness_tokens_per_run",
        "harness_run_terminates",
    }
)


def sheet(**facts) -> dict:
    """A fact sheet with each value carrying the origin its own `source:` admits."""
    return {
        name: (diagnosis.measured(value) if name in MEASURED_FACTS else diagnosis.stated(value))
        for name, value in facts.items()
    }


#: EVERYTHING PAST G1, which almost every sheet below starts from. Written once
#: so a sheet reads as its own delta from "the task set is in place and the bare
#: model fell short" - which is where this ledger's interesting answers live.
_PAST_THE_TASK_SET = {
    "success_check_named": True,
    "success_check_characters": 420,
    "success_check_is_a_program": True,
    "target_pass_rate": 0.9,
    "harness_tasks_n": 24,
    "can_rerun_tasks": True,
    "solo_pass_rate": 0.5,
}

#: A TOOL LAYER THAT IS FINISHED, and a run that is bounded. Everything G4 and
#: G5 want, so a sheet that wants to reach the mint does not have to restate it.
_THE_GATES_BELOW_THE_SHAPE = {
    "harness_tools_n": 3,
    "tools_risk_annotated_n": 3,
    "boundaries_are_typed": True,
    "approval_boundary_declared": True,
    "components_proposed_n": 1,
    "components_ablated_n": 1,
    "components_that_earned_their_place": 1,
    "harness_spans_read": 40,
    "harness_has_traces": True,
    "harness_tokens_per_run": 1200.0,
    "harness_run_terminates": True,
}


def _reaching(**over) -> dict:
    return sheet(**{**_PAST_THE_TASK_SET, **over})


def _minting(**over) -> dict:
    return sheet(**{**_PAST_THE_TASK_SET, **_THE_GATES_BELOW_THE_SHAPE, **over})


#: ONE ENTRY PER OUTCOME, and the key is the outcome the engine must reach.
#: Every terminal answer this ledger can give is here except the two error
#: outcomes, which are engine bugs rather than diagnoses, and
#: `SPEC__SUBSTANTIATE_CLAIMED_FACTS`, which is reached by the origin policy
#: rather than by any node.
SHEETS: dict[str, dict] = {
    # ---- stage 0: is there a task at all -------------------------------
    "BLOCKED__NO_SUCCESS_CRITERION": sheet(),
    "SPEC__WRITE_THE_TASK": sheet(
        success_check_named=True, success_check_characters=0,
        success_check_is_a_program=False, target_pass_rate=0.9,
    ),
    "SPEC__SET_THE_BAR": sheet(
        success_check_named=True, success_check_characters=420,
        success_check_is_a_program=True,
    ),
    # ---- stage 1: is there enough to measure on ------------------------
    "SPEC__BUILD_A_STARTER_EVAL": sheet(
        success_check_named=True, success_check_characters=420,
        success_check_is_a_program=True, target_pass_rate=0.9,
        harness_tasks_n=6, can_rerun_tasks=True,
    ),
    "SPEC__MAKE_THE_TASKS_RERUNNABLE": sheet(
        success_check_named=True, success_check_characters=420,
        success_check_is_a_program=True, target_pass_rate=0.9,
        harness_tasks_n=24, can_rerun_tasks=False,
    ),
    # ---- stage 2: what does the model do alone -------------------------
    "SPEC__RUN_THE_MODEL_ALONE": sheet(
        success_check_named=True, success_check_characters=420,
        success_check_is_a_program=True, target_pass_rate=0.9,
        harness_tasks_n=24, can_rerun_tasks=True,
    ),
    "NO_HARNESS__ONE_CALL": _reaching(solo_pass_rate=0.95),
    "NO_HARNESS__NOT_AN_AI_PROBLEM": _reaching(the_failure_is_not_the_model=True),
    "HANDOFF__DIAGNOSE_THE_EXISTING_AGENT": _reaching(the_loop_exists_and_fails=True),
    "HANDOFF__THE_KNOWLEDGE_IS_THE_PROBLEM": _reaching(the_answer_was_never_knowable=True),
    "NO_HARNESS__A_PIPELINE_FIRST": _reaching(steps_depend_on_the_last=True),
    # ---- stage 3: is the tool layer the problem ------------------------
    "NO_TOOLING__FEWER_TOOLS": _reaching(
        harness_tools_n=30, tool_choice_is_ambiguous=True
    ),
    "NO_TOOLING__REWRITE_THE_DESCRIPTIONS": _reaching(
        harness_tools_n=6, tool_choice_is_ambiguous=True
    ),
    "NO_TOOLING__TYPE_THE_BOUNDARY": _reaching(
        harness_tools_n=6, boundaries_are_typed=False
    ),
    # ---- stage 4: what shape, if any -----------------------------------
    "NO_HARNESS__USE_AN_EXISTING_ONE": _reaching(
        boundaries_are_typed=True, an_existing_harness_does_this=True
    ),
    "NO_HARNESS__A_SCRIPT": _reaching(boundaries_are_typed=True),
    "NO_HARNESS__ONE_LOOP_FIRST": _reaching(
        boundaries_are_typed=True,
        steps_depend_on_the_last=True,
        pipeline_pass_rate=0.7,
        one_context_cannot_hold_it=True,
    ),
    # ---- the four builds ------------------------------------------------
    "HARNESS__TOOL_LAYER": _minting(
        harness_tools_n=0,
        tools_risk_annotated_n=0,
        the_model_must_reach_external_systems=True,
    ),
    "HARNESS__FIXED_PIPELINE": _minting(the_model_must_reach_external_systems=True),
    "HARNESS__AGENT_LOOP": _minting(
        steps_depend_on_the_last=True, pipeline_pass_rate=0.7
    ),
    "HARNESS__AGENT_TEAM": _minting(
        steps_depend_on_the_last=True,
        pipeline_pass_rate=0.7,
        one_context_cannot_hold_it=True,
        single_loop_pass_rate=0.8,
    ),
    # ---- the remedy stages, reached from the sweep's own gate failures --
    "SPEC__NAME_THE_COMPONENTS": _minting(
        the_model_must_reach_external_systems=True,
        components_proposed_n=0,
        components_ablated_n=0,
        components_that_earned_their_place=0,
    ),
    "SPEC__ABLATE_THE_HARNESS": _minting(
        the_model_must_reach_external_systems=True,
        components_proposed_n=3,
        components_ablated_n=1,
        components_that_earned_their_place=1,
    ),
    "NO_HARNESS__STRIP_A_COMPONENT": _minting(
        the_model_must_reach_external_systems=True,
        components_proposed_n=3,
        components_ablated_n=3,
        components_that_earned_their_place=2,
    ),
    "SPEC__DECLARE_THE_BLAST_RADIUS": _minting(
        the_model_must_reach_external_systems=True, tools_risk_annotated_n=1
    ),
    "SPEC__DRAW_THE_APPROVAL_BOUNDARY": _minting(
        steps_depend_on_the_last=True,
        pipeline_pass_rate=0.7,
        approval_boundary_declared=False,
    ),
    "SPEC__INSTRUMENT_THE_LOOP": _minting(
        the_model_must_reach_external_systems=True,
        harness_spans_read=0,
        harness_has_traces=False,
    ),
    "SPEC__BOUND_THE_RUN": _minting(
        the_model_must_reach_external_systems=True, harness_run_terminates=False
    ),
}


def every_sheet():
    """`(label, facts)` for every sheet, for a sweep that wants them all."""
    yield "harness: an empty sheet", {}
    for outcome, facts in sorted(SHEETS.items()):
        yield f"harness: {outcome}", facts
