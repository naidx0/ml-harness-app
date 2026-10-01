"""PHASE 0a. A second domain diagnoses on this engine with no code of its own.

`docs/VISION.md` stakes the platform thesis on one sentence - *"A second ledger
runs on the same engine with no code change"* - and `docs/PHASES.md` makes it the
first experiment, because if the engine will not take a second ledger the pivot
is a rewrite rather than a content problem and the whole plan changes shape.

This file is that experiment, executed rather than asserted.

WHY THE SECOND LEDGER SPELLS EVERY NAME DIFFERENTLY, AND WHY THAT IS THE TEST.
Four names used to be Python constants holding the FIRST ledger's choices -
`ENTRY_STAGE = "stage_0_admissibility"`, `STAGE_9 =
"stage_9_method_selector"`, `UNSET = "UNSET"`, and the literal `"TRAIN__"`
inside SC1 - plus two more nobody had listed: the engine's exit check keyed off
the verdict string `"TRAIN"`, and the origin policy refused an
unsubstantiated outcome that `startswith("TRAIN__")`.

`docs/ledgers/ai_engineering.yaml` chooses a different name for every one of
them. `stage_0_can_we_answer`, `stage_9_shape_selector`, `S9_SWEEP_THE_GATES`,
`NOTHING_PROPOSED`, `BUILD__`, verdict `BUILD`. So a name leaking back into the
engine cannot pass here by coincidence: it has to be READ OUT OF THE FILE or
nothing works at all.

AND THE ML LEDGER IS THE OTHER HALF OF THE CLAIM. A generalisation that quietly
alters a machine-learning verdict is a regression wearing an architecture's
clothes, so `TheMlLedgerIsUnchangedTest` below drives every fixture in
`tests/diagnosis_fixtures.py` through a document reconstructed in the OLD FORMAT
and asserts the answers are identical, entry for entry. That is the same
document the engine read before this pass existed, read through the upgrader,
and it is what keeps the upgrader honest as the ML ledger goes on changing.
"""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

import yaml

from app.diagnosis import (
    MEASURED,
    SPEC_PATH,
    STATED,
    Fact,
    default_spec,
    diagnose,
    load_spec,
)

import diagnosis_fixtures as fixtures

LEDGER = Path(__file__).resolve().parents[1] / "docs" / "ledgers" / "ai_engineering.yaml"

#: Attribute a fact the way its own `source:` admits: a tool looked, or the
#: person answered. Not a licence the test grants itself - the ledger's own
#: `source:` column, read rather than restated.
_ORIGIN_FOR_SOURCE = {"inspect": MEASURED, "ask": STATED, "derive": MEASURED}


def _base() -> dict[str, object]:
    """One coherent story: a real agent, forty real failures, everything measured.

    Every case below is this story with ONE thing changed, which is what makes
    each of them a diagnosis rather than a coincidence.
    """
    return {
        "failing_cases_n": 40,
        "can_rerun_failures": True,
        "failure_rate_measured": True,
        "baseline_success_rate": 0.55,
        "target_success_rate": 0.9,
        "failure_reproduces": True,
        "has_traces": True,
        "tokens_per_run": 4200,
        "run_terminates": True,
        "simple_version_tried": True,
        "workflow_tried": True,
        "single_agent_tried": True,
        "tool_count": 3,
        "tool_call_success_rate": 0.95,
        "control_flow_is_dynamic": True,
        "one_context_is_insufficient": False,
        "failure_buckets": {"reasoning": 30, "tool_choice": 5, "format": 5},
    }


class SecondLedgerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec(LEDGER)

    def facts(self, *, drop=(), bare=(), **overrides):
        values = _base()
        values.update(overrides)
        for name in drop:
            values.pop(name, None)
        out = {}
        for name, value in values.items():
            if name in bare:
                out[name] = value  # bare is ASSERTED, and an assertion opens no gate
            else:
                out[name] = Fact(value, _ORIGIN_FOR_SOURCE[self.spec.facts[name]["source"]])
        return out

    def answer(self, **kwargs) -> str:
        return diagnose(self.facts(**kwargs), self.spec).outcome


class TheSecondLedgerLoadsAndDiagnosesTest(SecondLedgerTest):
    def test_it_declares_its_own_names_and_the_engine_reads_them(self):
        """Not one of these is a name the engine could have supplied."""
        self.assertEqual(self.spec.roles.entry_stage, "stage_0_can_we_answer")
        self.assertEqual(self.spec.roles.commit_stages, ("stage_9_shape_selector",))
        self.assertEqual(self.spec.roles.gate_sweep_node, "S9_SWEEP_THE_GATES")
        self.assertEqual(self.spec.roles.no_proposal, "NOTHING_PROPOSED")
        self.assertEqual(self.spec.gated_prefix, "BUILD__")
        self.assertEqual(self.spec.mint_node, "S9_MINT_BUILD_VERDICT")

    def test_no_name_is_shared_with_the_first_ledger(self):
        """The two ledgers agree about NOTHING the engine has to find.

        This is what makes every other assertion in this file non-vacuous. If
        the second ledger reused the ML names, a constant left behind in the
        engine would go on working and this suite would go on passing.
        """
        ml = default_spec()
        pairs = {
            "entry_stage": (ml.roles.entry_stage, self.spec.roles.entry_stage),
            "commit_stages": (ml.roles.commit_stages, self.spec.roles.commit_stages),
            "gate_sweep_node": (ml.roles.gate_sweep_node, self.spec.roles.gate_sweep_node),
            "no_proposal": (ml.roles.no_proposal, self.spec.roles.no_proposal),
            "gated_prefix": (ml.gated_prefix, self.spec.gated_prefix),
            "mint_node": (ml.mint_node, self.spec.mint_node),
        }
        for role, (first, second) in pairs.items():
            with self.subTest(role=role):
                self.assertNotEqual(
                    first,
                    second,
                    f"both ledgers name {role} {first!r}. Give the second ledger a "
                    "different name, or this file stops proving anything: an engine "
                    "that still held the first ledger's constant would pass.",
                )
        self.assertEqual(ml.gates.keys() & self.spec.gates.keys(), set())
        self.assertEqual(ml.node_index.keys() & self.spec.node_index.keys(), set())

    def test_it_refuses_before_it_builds(self):
        """The refusals first, because they are the product.

        TWO SHEETS HERE CHANGED ON 2026-08-24 AND BOTH CHANGED BECAUSE THE ANSWER
        WAS WRONG, NOT BECAUSE THE TEST WAS.

        `failing_cases_n=4` used to reach BLOCKED__NOTHING_TO_MEASURE_AGAINST -
        the product telling somebody who had written down four real failures that
        there was nothing to measure against. It reaches
        ACTION__WRITE_DOWN_TEN_FAILURES now and the zero case keeps the BLOCKED
        one, which is what that outcome was always for.

        `failure_buckets={"tool_execution": 30}` used to reach
        NO_TOOLS__PROMPT_IS_THE_BUG - "the tools fire and the answers are still
        wrong, so the tools are not the bug" said to the one bucket that means a
        tool returned junk. `tool_execution` goes to stage_2_not_the_loop now;
        the PROMPT_IS_THE_BUG sheet is a tool_choice sheet, which is what that
        node's two conditions have always actually been about.
        """
        cases = {
            "ACTION__WRITE_DOWN_TEN_FAILURES": dict(failing_cases_n=4),
            "BLOCKED__NOTHING_TO_MEASURE_AGAINST": dict(failing_cases_n=0),
            "ACTION__BUILD_AN_EVAL_HARNESS": dict(can_rerun_failures=False),
            "ACTION__SET_A_TARGET_RATE": dict(drop=("target_success_rate",)),
            "BLOCKED__CANNOT_REPRODUCE": dict(failure_reproduces=False),
            "ACTION__MEASURE_THE_BASELINE": dict(
                failure_rate_measured=False, drop=("baseline_success_rate",)
            ),
            "NO_AGENT__SHIP_IT": dict(baseline_success_rate=0.95),
            "BLOCKED__NO_TRACES": dict(has_traces=False),
            "ACTION__CLASSIFY_THE_FAILURES": dict(failure_buckets={"reasoning": 3}),
            "NO_AGENT__ONE_API_CALL": dict(simple_version_tried=False),
            "NO_AGENT__A_SCRIPT": dict(control_flow_is_dynamic=False),
            "NO_AGENT__A_WORKFLOW": dict(workflow_tried=False),
            "NO_AGENT__ONE_AGENT_FIRST": dict(
                one_context_is_insufficient=True, single_agent_tried=False
            ),
            "NO_TOOLS__DESCRIPTION_IS_THE_BUG": dict(
                failure_buckets={"tool_choice": 30}, tool_call_success_rate=0.2
            ),
            "NO_TOOLS__PROMPT_IS_THE_BUG": dict(
                failure_buckets={"tool_choice": 30}, tool_call_success_rate=0.95
            ),
            "NO_AGENT__FIX_THE_TOOL": dict(failure_buckets={"tool_execution": 30}),
            "NO_AGENT__FIX_THE_CONTEXT": dict(failure_buckets={"context": 30}),
            "NO_AGENT__CONSTRAIN_THE_OUTPUT": dict(failure_buckets={"format": 30}),
            "ACTION__BOUND_THE_LOOP": dict(run_terminates=False),
        }
        for outcome, change in cases.items():
            with self.subTest(outcome=outcome):
                self.assertEqual(self.answer(**change), outcome)

    def test_three_gated_builds_are_reachable(self):
        """And each of them passed all five gates under its own class."""
        cases = {
            "BUILD__AGENT_WITH_TOOLS": dict(),
            "BUILD__MULTI_AGENT": dict(one_context_is_insufficient=True),
            "BUILD__TOOLS_FOR_AN_EXISTING_LOOP": dict(
                failure_buckets={"tool_choice": 30}, tool_count=0
            ),
        }
        for outcome, change in cases.items():
            with self.subTest(outcome=outcome):
                result = diagnose(self.facts(**change), self.spec)
                self.assertEqual(result.outcome, outcome)
                self.assertEqual(result.verdict, "BUILD")
                for gate_id in self.spec.required_gates:
                    self.assertEqual(
                        result.gate_ledger[gate_id]["status"],
                        "PASSED",
                        f"{outcome} was minted with {gate_id} not passed",
                    )

    def test_every_declared_outcome_is_reachable(self):
        """THE LIST COMES OUT OF THE FILE, ALWAYS.

        Derived from `declared_outcomes()` rather than written here, for the
        reason the ML ledger learned twice: an outcome the graph can no longer
        reach stays in a hand-kept copy and stays green. A ledger's refusals are
        the last thing that should be allowed to die quietly.
        """
        reachable = {}
        for label, change in {
            "some failures, not ten": dict(failing_cases_n=4),
            "no failures at all": dict(failing_cases_n=0),
            "cannot rerun": dict(can_rerun_failures=False),
            "no target": dict(drop=("target_success_rate",)),
            "no repro": dict(failure_reproduces=False),
            "unmeasured": dict(failure_rate_measured=False, drop=("baseline_success_rate",)),
            "already passes": dict(baseline_success_rate=0.95),
            "no traces": dict(has_traces=False),
            "unbucketed": dict(failure_buckets={"reasoning": 3}),
            "unroutable buckets": dict(failure_buckets={"latency": 30}),
            "no tools": dict(failure_buckets={"tool_choice": 30}, tool_count=0),
            "tools never called": dict(
                failure_buckets={"tool_choice": 30}, tool_call_success_rate=0.2
            ),
            "tools fire, wrong one": dict(
                failure_buckets={"tool_choice": 30}, tool_call_success_rate=0.95
            ),
            "the tool returned junk": dict(failure_buckets={"tool_execution": 30}),
            "not knowable from context": dict(failure_buckets={"context": 30}),
            "right answer, wrong shape": dict(failure_buckets={"format": 30}),
            "static control flow": dict(control_flow_is_dynamic=False),
            "no workflow": dict(workflow_tried=False),
            "simple untried": dict(simple_version_tried=False),
            "agent": dict(),
            "multi agent": dict(one_context_is_insufficient=True),
            "many agents, never built one": dict(
                one_context_is_insufficient=True, single_agent_tried=False
            ),
            "unbounded loop": dict(run_terminates=False),
            "claimed count": dict(bare=("failing_cases_n",)),
        }.items():
            reachable[self.answer(**change)] = label

        declared = self.spec.declared_outcomes()
        missing = sorted(declared - set(reachable))
        self.assertEqual(
            missing,
            [],
            f"{len(missing)} declared outcome(s) no fact set reaches: {missing}. An "
            "outcome the graph cannot reach is an answer the product claims it can "
            "give and cannot.",
        )


class NoLedgerNameLivesInTheEngineExceptWhereItIsQuarantinedTest(unittest.TestCase):
    """The CLASS fix, guarded so a new instance cannot arrive quietly.

    Every test above proves the six known names are gone. None of them stops a
    seventh being added next month, and the six that were there were added the
    same way: one at a time, each one reasonable on its own, none of them
    reviewed as "the engine is learning a ledger's vocabulary again".

    So this reads `app/diagnosis.py` and finds every string constant that LOOKS
    like a ledger's name - a node id, a stage name, an outcome prefix - and
    insists it appears only in one of two places:

      * a function that IS an ML computation, registered in `ACTION_HANDLERS` or
        `CONDITION_HANDLERS`. `docs/LEDGER_FORMAT.md` deliberately leaves those
        for a later pass, because they are a plug-in-architecture question and
        mixing it with the naming question would answer neither well;
      * `_upgrade_2_to_3`, where the FORMAT-2 grammar's conventions live. An
        upgrader is allowed to know the old grammar's names - that is what an
        upgrader IS - and the point is that they are quarantined in front of the
        validator where neither the checks nor the walk can see them.

    THE PERMITTED SET IS DERIVED, NEVER TRANSCRIBED. It is the handler registries
    themselves, so a handler added tomorrow is covered on the day it is added and
    a handler deleted stops being an excuse the same day.
    """

    #: A string that looks like something a LEDGER names rather than something
    #: the engine owns.
    LEDGER_NAME = __import__("re").compile(
        r"^(S[0-9]+_[A-Z][A-Z0-9_]*|G[0-9]_[A-Z][A-Z0-9_]*|stage_[0-9][a-z0-9_]*"
        r"|TRAIN__|UNSET|NO_TRAIN__[A-Z_]*)$"
    )

    #: THE DEBT REGISTER, and it is deliberately a list rather than a rule.
    #:
    #: Everything else is DERIVED - the handler registries answer for themselves.
    #: These three cannot be, so each is written down with the reason it is still
    #: here, in the one place a reviewer will see a fourth being added. A
    #: convention (`functions starting _ml_`) would have let a fourth arrive
    #: without anybody deciding to allow it, which is exactly how the first six
    #: got in.
    QUARANTINED = {
        "_upgrade_2_to_3": (
            "the FORMAT-2 grammar's own conventions. An upgrader is allowed to know "
            "the names of the grammar it upgrades FROM; that is what an upgrader is. "
            "They are quarantined in front of the validator, so neither the checks "
            "nor the walk can see them."
        ),
        "_check_ml_size_table": (
            "SC4, which is a theorem about ONE LEDGER'S TABLE rather than about "
            "ledgers. It is guarded on the node existing and skipped for any ledger "
            "that has none. The right home is a per-ledger check registry, which the "
            "ledger's own `static_checks:` block is already the documentation half "
            "of; that is its own piece of work."
        ),
        "_from_scratch_cost": (
            "an ML COMPUTATION reached through the derived value "
            "`from_scratch_cost_estimate`. It reads numbers off S9_FROM_SCRATCH the "
            "way the action handlers read numbers off their own nodes, and it is in "
            "the same deferred bucket - docs/LEDGER_FORMAT.md keeps the plug-in "
            "question separate from the naming one on purpose. It is not in a "
            "registry only because it is a value rather than a node."
        ),
    }

    def test_every_quarantined_function_still_exists(self):
        """A debt register that names a function nobody has is a register nobody reads."""
        import app.diagnosis as engine

        for name in self.QUARANTINED:
            with self.subTest(function=name):
                self.assertTrue(
                    hasattr(engine, name),
                    f"{name} is gone; take it out of QUARANTINED so the list stays "
                    "the list of debts that are actually owed",
                )

    def test_the_only_ledger_names_left_are_in_a_handler_or_the_upgrader(self):
        import ast

        source = (Path(__file__).resolve().parents[1] / "app" / "diagnosis.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)

        from app.diagnosis import ACTION_HANDLERS, CONDITION_HANDLERS

        permitted_functions = set(self.QUARANTINED)
        # The ML computations, found by asking the registries rather than by
        # listing them. `_action("S9_SIZE_TO_METHOD")` decorates `_size_to_method`,
        # so the registry's VALUES carry the function names.
        for registry in (ACTION_HANDLERS, CONDITION_HANDLERS):
            permitted_functions.update(fn.__name__ for fn in registry.values())

        offenders: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name in permitted_functions:
                continue
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Constant)
                    and isinstance(inner.value, str)
                    and self.LEDGER_NAME.match(inner.value)
                ):
                    offenders.append(f"{node.name}() line {inner.lineno}: {inner.value!r}")

        self.assertEqual(
            offenders,
            [],
            "the engine names a ledger's own vocabulary outside a handler and "
            "outside the format-2 upgrader:\n  " + "\n  ".join(offenders) + "\n"
            "A name belongs to the ledger. If the engine needs to find something, "
            "the ledger declares it in `contract.roles` or "
            "`contract.outcome_prefixes` and the engine reads it there.",
        )

    def test_the_permitted_set_is_not_empty_so_the_check_is_not_trivially_green(self):
        from app.diagnosis import ACTION_HANDLERS, CONDITION_HANDLERS

        self.assertGreater(len(ACTION_HANDLERS), 5)
        self.assertGreaterEqual(len(CONDITION_HANDLERS), 1)

    def test_the_engine_no_longer_exports_the_four_constants(self):
        import app.diagnosis as engine

        for name in ("ENTRY_STAGE", "STAGE_9", "UNSET", "ROUTE_KEYS"):
            with self.subTest(constant=name):
                self.assertFalse(
                    hasattr(engine, name),
                    f"app.diagnosis.{name} is back. It is a NAME, and a name belongs "
                    "to the ledger that chose it.",
                )


class TheOriginPolicyHoldsInADomainItHasNeverSeenTest(SecondLedgerTest):
    """A model's claim cannot open a gate in a ledger the policy never met.

    The origin machinery was built for the ML ledger and every argument for it
    is written in that file. Not one line of it is about machine learning, and
    this is where that stops being an opinion.
    """

    def test_a_claimed_inspect_fact_refuses_the_gate(self):
        result = diagnose(self.facts(bare=("failing_cases_n",)), self.spec)
        self.assertEqual(result.outcome, "ACTION__SUBSTANTIATE_CLAIMED_FACTS")
        self.assertEqual(
            [row["fact"] for row in result.unsubstantiated], ["failing_cases_n"]
        )
        self.assertEqual(result.unsubstantiated[0]["declared_source"], "inspect")
        self.assertEqual(result.unsubstantiated[0]["origin"], "ASSERTED")

    def test_the_refusal_names_what_would_substantiate_it(self):
        result = diagnose(self.facts(bare=("run_terminates",)), self.spec)
        self.assertEqual(result.outcome, "ACTION__SUBSTANTIATE_CLAIMED_FACTS")
        # RETIRED AND REWRITTEN 2026-08-25: this asserted "no instrument yet",
        # which was the honest sentence on 2026-08-24 and is a false sentence
        # the day `app/tools/agents.py` ships - ALL nine inspect facts are
        # measured now (the gate was denominated in tokens, so the last one
        # came with it), and the refusal must point at the instrument rather
        # than mourn an absence that ended. The sentence that must hold is the
        # actionable one: name where substantiation comes from.
        lowered = result.unsubstantiated[0]["substantiation"].lower()
        self.assertIn(
            "agents.py",
            lowered,
            "the ledger's substantiation line for `inspect` should name the "
            "instruments that can measure the fact, because refusing without "
            "saying what would substantiate it is not this product's voice",
        )

    def test_a_stated_answer_still_opens_an_ask_gate(self):
        """The other direction, which is the one a wall this tight tends to break."""
        self.assertEqual(self.answer(), "BUILD__AGENT_WITH_TOOLS")


class TheSweepReAsksUnderTheProposalsOwnClassTest(SecondLedgerTest):
    """The latching fix, in a ledger the engine has never seen.

    This is the piece that would be quietly lost if `gate_sweep_node` were still
    bound to the string "S9_GATE_SWEEP". The second ledger's sweep is called
    something else, so if the binding were by node id the sweep would simply not
    run - and the failure mode would not be a crash. It would be gates passed
    under the wrong row looking passed.
    """

    def test_a_gate_passed_under_any_is_re_asked_under_agent(self):
        result = diagnose(self.facts(), self.spec)
        ids = [e.id for e in result.path]
        self.assertIn("S9_SWEEP_THE_GATES", ids)

        rows = [
            e.row for e in result.path if e.kind == "gate" and e.id == "G2_SIMPLE_VERSION_TRIED"
        ]
        self.assertEqual(
            rows,
            ["any", "agent"],
            "G2 should be passed once under `any` on the spine and asked AGAIN under "
            "`agent` at the sweep. One entry means the sweep did not run; two "
            "identical entries mean the row machinery stopped distinguishing them.",
        )
        self.assertEqual(result.gate_ledger["G2_SIMPLE_VERSION_TRIED"]["row"], "agent")
        self.assertEqual(
            result.gate_ledger["G2_SIMPLE_VERSION_TRIED"]["clause"],
            "simple_version_tried and workflow_tried",
        )

    def test_the_agent_row_is_the_one_that_can_refuse(self):
        """The `any` row passes and the `agent` row does not, and agent is asked.

        `workflow_tried` is false and `simple_version_tried` is true, so the two
        rows disagree. If the sweep asked the wrong row this would build.
        """
        answer = self.answer(workflow_tried=False)
        self.assertNotEqual(answer, "BUILD__AGENT_WITH_TOOLS")
        self.assertEqual(answer, "NO_AGENT__A_WORKFLOW")

    def test_the_tools_branch_pays_for_the_gates_it_skipped(self):
        """It never enters stage_5_control_flow, so it meets G2 and G4 only here."""
        result = diagnose(
            self.facts(failure_buckets={"tool_choice": 30}, tool_count=0), self.spec
        )
        ids = [e.id for e in result.path]
        self.assertNotIn("S5_A_SCRIPT", ids, "the tools branch should not enter stage 5")
        sweep_at = ids.index("S9_SWEEP_THE_GATES")
        for gate_id in ("G2_SIMPLE_VERSION_TRIED", "G4_COST_AND_TERMINATION_BOUNDED"):
            with self.subTest(gate=gate_id):
                self.assertGreater(
                    ids.index(gate_id),
                    sweep_at,
                    f"{gate_id} was passed BEFORE the sweep on a branch that never "
                    "enters the stage it heads - which would mean it was never asked",
                )
        self.assertEqual(result.outcome, "BUILD__TOOLS_FOR_AN_EXISTING_LOOP")


class TheForkIsExecutedFromTheFileTest(SecondLedgerTest):
    """`select: argmax` and a `no_match:` the ML ledger does not use.

    Both ML forks declare `no_match: {error: ...}`, which preserves what they
    did before the schema existed. This ledger declares an OUTCOME, so the third
    answer is exercised by something rather than only documented.
    """

    def test_argmax_takes_the_bucket_with_the_most_failures(self):
        self.assertEqual(
            self.answer(failure_buckets={"tool_choice": 30, "reasoning": 29},
                        tool_call_success_rate=0.2),
            "NO_TOOLS__DESCRIPTION_IS_THE_BUG",
        )
        self.assertEqual(
            self.answer(failure_buckets={"tool_choice": 29, "reasoning": 30},
                        control_flow_is_dynamic=False),
            "NO_AGENT__A_SCRIPT",
        )

    def test_an_unroutable_histogram_gets_the_declared_outcome_not_a_crash(self):
        """The one known gap in the ML ledger, closed here by declaring an answer."""
        self.assertEqual(
            self.answer(failure_buckets={"latency": 30, "cost": 12}),
            "ACTION__CLASSIFY_THE_FAILURES",
        )


# ---------------------------------------------------------------------------


def _downgrade_to_format_2(raw: dict) -> dict:
    """Rebuild a FORMAT-2 document from the current ML ledger.

    The inverse of `_upgrade_2_to_3`, written here rather than in the engine
    because nothing in the product ever needs to write an old format - only to
    read one. What it produces is the shape the ML ledger had on disk before
    `contract.roles` existed: a `version:` integer, no roles block, no `gated:`
    or `mintable_only_at:` on the TRAIN__ prefix, forks as bare `routes:`
    mappings, and `derived.route` as a paragraph of prose.

    This is what makes `TheMlLedgerIsUnchangedTest` mean something as the ML
    ledger goes on changing: the old document is DERIVED from the current one,
    so it cannot go stale, and the upgrader has to keep working on whatever the
    file becomes rather than on a snapshot somebody took once.
    """
    out = copy.deepcopy(raw)
    out["version"] = out.pop("ledger_version")
    out.pop("ledger_format")

    contract = out["contract"]
    roles = contract.pop("roles")
    prefix = contract["outcome_prefixes"]["TRAIN__"]
    prefix.pop("gated")
    prefix.pop("mintable_only_at")

    for key, value in list(out.items()):
        if not key.startswith("stage_"):
            continue
        for node in value:
            if isinstance(node, dict) and isinstance(node.get("fork"), dict):
                node["routes"] = node.pop("fork")["routes"]

    route = out["derived"]["route"]
    out["derived"]["route"] = (
        "The S9_HARDWARE_ROUTER verdict: " + " | ".join(route["enum"]) + ". " + route["means"]
    )
    assert roles["entry_stage"] == "stage_0_admissibility", roles
    return out


class TheMlLedgerIsUnchangedTest(unittest.TestCase):
    """THE HALF THAT MATTERS AS MUCH AS THE SECOND LEDGER.

    A generalisation that quietly alters a machine-learning verdict is a
    regression wearing an architecture's clothes. So the whole fixture corpus is
    driven through BOTH documents - the format-3 file in the repository and a
    format-2 document rebuilt from it - and every field of every answer must
    agree, not merely the outcome id. An outcome that stayed the same while the
    path moved is a behaviour change and this is what would catch it.
    """

    @classmethod
    def setUpClass(cls):
        cls.new = default_spec()
        text = yaml.safe_dump(
            _downgrade_to_format_2(cls.new.raw), sort_keys=False, allow_unicode=True
        )
        # A TEMP DIRECTORY, never the repository tree. `load_spec` takes a path,
        # so the document has to exist somewhere; a test that leaves a file in
        # the tree - even briefly, even cleaned up in a `finally` - is a test
        # that fails a concurrent run and lies to `git status` while it does.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "diagnosis_engine_format2.yaml"
            path.write_text(text, encoding="utf-8")
            cls.old = load_spec(path)

    def sheets(self):
        for label, facts in sorted(fixtures.MINTING.items()):
            yield f"MINTING::{label}", facts
        for label, facts in sorted(fixtures.REACHING.items()):
            yield f"REACHING::{label}", facts
        for label, case in sorted(fixtures.SPREAD.items()):
            yield f"SPREAD::{label}", case["facts"]
            if case.get("mints_when"):
                yield (
                    f"SPREAD::{label}+mints_when",
                    {**case["facts"], **case["mints_when"]},
                )

    def test_the_old_format_still_loads(self):
        self.assertEqual(self.old.ledger_format, 2)
        self.assertEqual(self.new.ledger_format, 3)
        self.assertEqual(self.old.roles, self.new.roles)
        self.assertEqual(self.old.gated_prefix, self.new.gated_prefix)
        self.assertEqual(self.old.mint_node, self.new.mint_node)
        self.assertEqual(self.old.literals, self.new.literals)

    def test_every_fixture_answers_identically_in_both_formats(self):
        sheets = list(self.sheets())
        self.assertGreater(len(sheets), 70, "the fixture corpus shrank")
        for label, facts in sheets:
            with self.subTest(sheet=label):
                a, b = diagnose(facts, self.new), diagnose(facts, self.old)
                self.assertEqual(a.outcome, b.outcome)
                self.assertEqual(a.verdict, b.verdict)
                self.assertEqual([e.as_dict() for e in a.path], [e.as_dict() for e in b.path])
                self.assertEqual(a.gate_ledger, b.gate_ledger)
                self.assertEqual(a.proposed_method, b.proposed_method)
                self.assertEqual(a.rejected, b.rejected)
                self.assertEqual(a.struck_methods, b.struck_methods)
                self.assertEqual(a.route, b.route)
                self.assertEqual(a.size_row, b.size_row)
                self.assertEqual(a.cost_provenance, b.cost_provenance)
                self.assertEqual(a.fact_origins, b.fact_origins)
                self.assertEqual(a.unsubstantiated, b.unsubstantiated)

    def test_the_repository_ledger_is_still_the_one_the_engine_defaults_to(self):
        self.assertEqual(default_spec().path, SPEC_PATH)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
