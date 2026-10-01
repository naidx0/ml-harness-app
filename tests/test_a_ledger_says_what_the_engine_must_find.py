"""THE CONFORMANCE SUITE. At one ledger the format is a habit; at six it is an
interface, and an interface without a conformance suite is a rumour.

A corpus of tiny ledgers, each valid or invalid for EXACTLY ONE declared reason,
each asserting on a stable CHECK ID rather than on a message string. That is
JSON-Schema-Test-Suite's shape and it is why independent implementations of that
spec agree with each other. Asserting on prose would punish anybody who makes an
error message clearer, which is the opposite of what this file is for.

WHY THE CORPUS IS BUILT IN PYTHON RATHER THAN CHECKED IN AS TWENTY YAML FILES.
Every case here is `MINIMAL` with one thing changed, and the diff between the
valid document and the invalid one IS the case. Twenty files would hide that
diff in a directory listing and would drift apart the first time the format
gains a required key.

THE RULE THE WHOLE FORMAT IS DECIDED BY, and every case below is an instance of
it:

    THE LEDGER OWNS EVERY NAME. THE ENGINE OWNS EVERY RULE ABOUT NAMES.

And its corollary, which settles the required-versus-optional question that is
otherwise a matter of taste:

    THE AXIS IS NOT REQUIRED-TO-HAVE. IT IS REQUIRED-TO-STATE.

`commit_stages: []` is a legal answer and a MISSING `commit_stages` is not,
because the difference between "this domain has no irreversible outcome" and
"somebody forgot" is the entire honesty test, and a default would erase it.
"""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

import yaml

from app.diagnosis import (
    CURRENT_LEDGER_FORMAT,
    FORK_SELECTORS,
    SUPPORTED_LEDGER_FORMATS,
    LedgerError,
    SpecError,
    diagnose,
    load_spec,
    measured,
    stated,
)

# ---------------------------------------------------------------------------
# The smallest document this engine will load and walk. Deliberately a NON-
# COMMITTING ledger - `commit_stages: []`, no gates, no methods it can mint - so
# that the cases which add a commit stage are adding exactly one thing.
#
# A ledger like this is real rather than degenerate: a triage ledger that only
# ever routes into another discipline has no irreversible outcome of its own and
# the gates protect nothing there. It says so out loud, where a reviewer sees it
# in a diff, rather than being silently exempt.

MINIMAL: dict = {
    "ledger_format": CURRENT_LEDGER_FORMAT,
    "ledger_version": 1,
    "contract": {
        "roles": {
            "entry_stage": "stage_0_start",
            "commit_stages": [],
            "no_proposal": "NONE_YET",
        },
        "required_gates": [],
        "outcome_prefixes": {
            "ANSWER__": {"verdict": "DONE", "terminal": True, "meaning": "an answer"},
            "ACTION__": {"verdict": "BLOCKED", "terminal": True, "meaning": "go and do this"},
            "REROUTE": {"verdict": None, "terminal": False, "meaning": "continue elsewhere"},
        },
        "path_semantics": {"type": "list[PathEntry]"},
        "diagnosis": {"verdict": {"enum": ["DONE", "BLOCKED"]}},
    },
    "methods": {"NONE_YET": {"class": "none"}},
    "facts": {
        "colour": {"enum": ["red", "green"], "source": "ask", "scope": "thread"},
        "count": {"type": "int", "source": "inspect", "scope": "thread", "default": 0},
    },
    "fact_origins": {
        "vocabulary": {
            "MEASURED": "a tool ran",
            "STATED": "the person said so",
            "ASSERTED": "a model said so, or nobody said",
            "DEFAULTED": "the ledger's own default",
        },
        "origin_of_an_unattributed_value": "ASSERTED",
        "admissible_for_gates": {"ask": ["MEASURED", "STATED"], "inspect": ["MEASURED"]},
        "substantiation": {"ask": "say it yourself", "inspect": "let a tool count it"},
        "unsubstantiated_outcome": "ACTION__SUBSTANTIATE",
    },
    "gates": {},
    "stage_0_start": [
        {"node": "S0_RED", "condition": "colour == red", "outcome": "ANSWER__RED"},
        {"node": "S0_NOT_RED", "condition": "colour != red", "outcome": "ANSWER__NOT_RED"},
    ],
}


def _mutate(**changes):
    """MINIMAL with one path changed. Keys are dotted; a value of `_GONE` deletes."""
    doc = copy.deepcopy(MINIMAL)
    for dotted, value in changes.items():
        parts = dotted.split("__")
        target = doc
        for part in parts[:-1]:
            target = target[part]
        if value is _GONE:
            target.pop(parts[-1], None)
        else:
            target[parts[-1]] = value
    return doc


class _GONE:
    pass


class LedgerCase(unittest.TestCase):
    def load(self, doc):
        """Write the document to a TEMP file and load it. Never into the repo tree."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "case.yaml"
            path.write_text(
                yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
            return load_spec(path)

    def refuses(self, doc, check_id: str):
        with self.assertRaises(LedgerError) as caught:
            self.load(doc)
        self.assertEqual(
            caught.exception.check_id,
            check_id,
            f"refused for {caught.exception.check_id} rather than {check_id}:\n"
            f"{caught.exception}",
        )
        return caught.exception


class TheMinimalLedgerIsValidTest(LedgerCase):
    """Every invalid case below is this document with ONE thing wrong.

    A corpus whose baseline does not load proves nothing at all: every case
    would fail for the same hidden reason and the test would look thorough.
    """

    def test_it_loads(self):
        spec = self.load(MINIMAL)
        self.assertEqual(spec.roles.commit_stages, ())
        self.assertIsNone(spec.gated_prefix)
        self.assertIsNone(spec.mint_node)

    def test_it_diagnoses(self):
        spec = self.load(MINIMAL)
        self.assertEqual(diagnose({"colour": stated("red")}, spec).outcome, "ANSWER__RED")
        self.assertEqual(
            diagnose({"colour": stated("green")}, spec).outcome, "ANSWER__NOT_RED"
        )

    def test_a_ledger_with_no_derived_block_is_fine(self):
        """`derived:` used to be required and read by a key name. Both are gone."""
        self.assertNotIn("derived", MINIMAL)
        self.load(MINIMAL)

    def test_the_eight_blocks_the_old_header_called_required_are_not(self):
        """MEASURED, and it is the blocker that turned out not to be one.

        `docs/ledgers/ai_engineering.yaml` used to say that escalation_ladder,
        shadowing_rule, helpers, uninspectable_facts, static_checks,
        runtime_checks, sources_policy and sources were required by the loader.
        Not one of them ever was. That claim was written from memory rather than
        measured, and it is the reason a blocker list gets checked against the
        machine before anybody implements it.
        """
        for block in (
            "escalation_ladder", "shadowing_rule", "helpers", "uninspectable_facts",
            "static_checks", "runtime_checks", "sources_policy", "sources",
        ):
            self.assertNotIn(block, MINIMAL)
        self.load(MINIMAL)


class TheFormatVersionIsRefusedOrUpgradedNeverGuessedTest(LedgerCase):
    def test_a_newer_format_is_refused_and_names_both_numbers(self):
        error = self.refuses(_mutate(ledger_format=CURRENT_LEDGER_FORMAT + 1), "LF001")
        self.assertIn(str(CURRENT_LEDGER_FORMAT + 1), str(error))
        self.assertIn(str(CURRENT_LEDGER_FORMAT), str(error))
        self.assertIn("upgrade the harness", str(error))

    def test_a_document_with_no_format_at_all_is_refused(self):
        self.refuses(_mutate(ledger_format=_GONE), "LF001")

    def test_a_format_that_is_not_an_integer_is_refused(self):
        self.refuses(_mutate(ledger_format="3"), "LF001")

    def test_the_supported_set_is_a_contiguous_run_ending_at_current(self):
        """BACKWARD_TRANSITIVE, and not FORWARD compatible on purpose."""
        self.assertEqual(max(SUPPORTED_LEDGER_FORMATS), CURRENT_LEDGER_FORMAT)
        self.assertEqual(
            sorted(SUPPORTED_LEDGER_FORMATS),
            list(range(min(SUPPORTED_LEDGER_FORMATS), CURRENT_LEDGER_FORMAT + 1)),
            "a gap in the supported set means a format nobody can upgrade THROUGH",
        )

    def test_the_author_version_and_the_grammar_version_are_different_fields(self):
        with self.assertRaises(SpecError) as caught:
            self.load(_mutate(ledger_version=_GONE))
        self.assertIn("ledger_version", str(caught.exception))


class TheRolesBlockIsRequiredToBeStatedTest(LedgerCase):
    def test_no_roles_block_at_all(self):
        error = self.refuses(_mutate(contract__roles=_GONE), "LF012")
        self.assertIn("commit_stages: []", str(error))

    def test_each_role_must_be_written_even_when_the_answer_is_empty(self):
        for role in ("entry_stage", "commit_stages", "no_proposal"):
            with self.subTest(role=role):
                doc = copy.deepcopy(MINIMAL)
                doc["contract"]["roles"].pop(role)
                error = self.refuses(doc, "LF012")
                self.assertIn("required-to-STATE", str(error))

    def test_an_empty_commit_stages_list_is_a_legal_answer(self):
        """The whole point of required-to-state. Empty is fine; ABSENT is not."""
        spec = self.load(MINIMAL)
        self.assertEqual(spec.roles.commit_stages, ())

    def test_a_role_naming_a_stage_that_does_not_exist_is_refused(self):
        doc = copy.deepcopy(MINIMAL)
        doc["contract"]["roles"]["entry_stage"] = "stage_0_typo"
        self.refuses(doc, "LF014")
        doc = copy.deepcopy(MINIMAL)
        doc["contract"]["roles"]["commit_stages"] = ["stage_9_nowhere"]
        self.refuses(doc, "LF014")

    def test_an_unknown_key_in_roles_is_an_error_and_names_the_near_miss(self):
        doc = copy.deepcopy(MINIMAL)
        doc["contract"]["roles"]["commit_stage"] = "stage_0_start"
        error = self.refuses(doc, "LF013")
        self.assertIn("commit_stages", str(error))

    def test_an_x_prefixed_key_is_the_authors_own_and_is_carried_through(self):
        """A declared place for undeclared things.

        Without it people smuggle notes into keys the engine might one day
        claim, and then the day it claims one their file changes meaning.
        """
        doc = copy.deepcopy(MINIMAL)
        doc["contract"]["roles"]["x_note"] = "we may add a second commit stage"
        self.load(doc)


def _committing(**overrides):
    """MINIMAL plus a commit stage, a gate, a method and a gated prefix."""
    doc = copy.deepcopy(MINIMAL)
    doc["contract"]["roles"]["commit_stages"] = ["stage_9_commit"]
    doc["contract"]["roles"]["gate_sweep_node"] = "S9_SWEEP"
    doc["contract"]["required_gates"] = ["G0_ENOUGH"]
    # THE BASELINE HAD TO DECLARE ITS OWN NEW VERDICT. It did not, and it loaded
    # anyway, which is the defect LF028 exists for: `contract.diagnosis.verdict`
    # was written down by every ledger in this repository and read by nothing, so
    # the corpus that exists to hold the format honest was itself declaring the
    # vocabulary [DONE, BLOCKED] and then minting a verdict called DO.
    doc["contract"]["diagnosis"]["verdict"]["enum"] = ["DONE", "BLOCKED", "DO"]
    doc["contract"]["outcome_prefixes"]["DO__"] = {
        "verdict": "DO",
        "terminal": True,
        "gated": "all",
        "mintable_only_at": "S9_MINT",
        "meaning": "the expensive thing",
    }
    doc["methods"] = {"NONE_YET": {"class": "none"}, "THE_THING": {"class": "big"}}
    doc["gates"] = {
        "G0_ENOUGH": {
            "node": "S0_NOT_ENOUGH",
            "stage": "stage_0_start",
            "asks": "is there enough?",
            "passes_when": [{"method_class": "any", "requires": "count >= 10"}],
            "on_fail": {"outcome": "ACTION__GET_MORE"},
        }
    }
    doc["stage_0_start"] = [
        {"gate_ref": "G0_ENOUGH"},
        {"node": "S0_RED", "condition": "colour == red", "outcome": "ANSWER__RED"},
        {
            "node": "S0_PROPOSE",
            "condition": "colour != red",
            "propose": "THE_THING",
            "route": "stage_9_commit",
        },
    ]
    doc["stage_9_commit"] = [
        {"node": "S9_SWEEP", "condition": "always", "order": "G0_ENOUGH"},
        {
            "node": "S9_MINT",
            "condition": "proposed_method != NONE_YET",
            "outcome": "DO__{proposed_method}",
            "emits": ["DO__THE_THING"],
        },
    ]
    for dotted, value in overrides.items():
        parts = dotted.split("__")
        target = doc
        for part in parts[:-1]:
            target = target[part]
        if value is _GONE:
            target.pop(parts[-1], None)
        else:
            target[parts[-1]] = value
    return doc


class TheGatedPrefixIsTheRoleTrainWasPlayingTest(LedgerCase):
    def test_a_committing_ledger_loads_and_mints_its_own_prefix(self):
        spec = self.load(_committing())
        self.assertEqual(spec.gated_prefix, "DO__")
        self.assertEqual(spec.mint_node, "S9_MINT")
        result = diagnose({"colour": stated("green"), "count": measured(20)}, spec)
        self.assertEqual(result.outcome, "DO__THE_THING")
        self.assertEqual(result.verdict, "DO")
        self.assertEqual(result.gate_ledger["G0_ENOUGH"]["status"], "PASSED")

    def test_the_gate_still_refuses_a_prefix_the_engine_has_never_heard_of(self):
        """No `TRAIN__` and no verdict called TRAIN anywhere in this document."""
        spec = self.load(_committing())
        result = diagnose({"colour": stated("green"), "count": measured(2)}, spec)
        self.assertEqual(result.outcome, "ACTION__GET_MORE")
        self.assertEqual(result.gate_ledger["G0_ENOUGH"]["status"], "FAILED")

    def test_an_asserted_fact_cannot_open_the_gate_of_an_unknown_domain(self):
        spec = self.load(_committing())
        result = diagnose({"colour": stated("green"), "count": 20}, spec)
        self.assertEqual(result.outcome, "ACTION__SUBSTANTIATE")
        self.assertEqual([r["fact"] for r in result.unsubstantiated], ["count"])

    def test_two_nodes_minting_the_gated_prefix_is_refused(self):
        """SC1, and it is a sentence no schema language can state.

        A schema can say "this key must be a string". It cannot say "exactly one
        node may mint the irreversible verdict", which is why this check stays
        Python and is not something a ledger can declare itself out of.
        """
        doc = _committing()
        doc["stage_0_start"].insert(
            1, {"node": "S0_SNEAK", "condition": "colour == red", "outcome": "DO__THE_THING"}
        )
        with self.assertRaises(SpecError) as caught:
            self.load(doc)
        self.assertIn("SC1", str(caught.exception))
        self.assertIn("S0_SNEAK", str(caught.exception))

    def test_a_gated_prefix_minted_outside_a_commit_stage_is_refused(self):
        doc = _committing()
        doc["contract"]["outcome_prefixes"]["DO__"]["mintable_only_at"] = "S0_MINT_HERE"
        doc["stage_9_commit"] = [
            {"node": "S9_SWEEP", "condition": "always", "order": "G0_ENOUGH"},
            {"node": "S9_IDLE", "condition": "colour == red", "outcome": "ANSWER__RED"},
        ]
        doc["stage_0_start"].append(
            {
                "node": "S0_MINT_HERE",
                "condition": "proposed_method != NONE_YET",
                "outcome": "DO__{proposed_method}",
                "emits": ["DO__THE_THING"],
            }
        )
        with self.assertRaises(SpecError) as caught:
            self.load(doc)
        self.assertIn("SC1", str(caught.exception))

    def test_a_per_prefix_gate_subset_is_parsed_and_refused_not_ignored(self):
        """A key you do not understand is a refusal, never a shrug.

        Accepting `gated: [G0]` and silently applying every gate would mean an
        author could write a narrower set, believe it, and get the full one. Or
        worse, the reverse.
        """
        doc = _committing()
        doc["contract"]["outcome_prefixes"]["DO__"]["gated"] = ["G0_ENOUGH"]
        error = self.refuses(doc, "LF022")
        self.assertIn("not implemented", str(error))

    def test_commit_stages_with_no_gated_prefix_is_refused(self):
        doc = _committing()
        doc["contract"]["outcome_prefixes"]["DO__"].pop("gated")
        self.refuses(doc, "LF023")

    def test_a_gated_prefix_with_no_commit_stage_is_refused(self):
        doc = _committing()
        doc["contract"]["roles"]["commit_stages"] = []
        self.refuses(doc, "LF023")

    def test_a_gated_prefix_that_names_no_minting_node_is_refused(self):
        doc = _committing()
        doc["contract"]["outcome_prefixes"]["DO__"].pop("mintable_only_at")
        self.refuses(doc, "LF025")

    def test_two_gated_prefixes_are_refused_while_required_gates_is_one_flat_list(self):
        doc = _committing()
        doc["contract"]["outcome_prefixes"]["ALSO__"] = {
            "verdict": "DO", "terminal": True, "gated": "all",
            "mintable_only_at": "S9_MINT", "meaning": "another expensive thing",
        }
        self.refuses(doc, "LF024")

    def test_a_proposal_in_a_ledger_that_commits_to_nothing_is_refused(self):
        doc = copy.deepcopy(MINIMAL)
        doc["stage_0_start"][1] = {
            "node": "S0_NOT_RED", "condition": "colour != red", "propose": "NONE_YET",
        }
        self.refuses(doc, "LF041")


class TheExitCheckIsTheLastLineOfDefenceInEveryDomainTest(LedgerCase):
    """`_finish` refuses to RETURN a gated verdict whose gates are not passed.

    FOUND BY MUTATION, AND IT IS WORTH SAYING HOW. Every other name this pass
    moved out of Python was caught the moment it was put back: the second ledger
    stopped loading, or stopped diagnosing, and something went red. This one did
    not. The exit check used to read `if verdict == "TRAIN"`, and putting that
    literal back left the whole suite green - because the check is DEFENSIVE. It
    only fires when the graph is already broken, and no correct ledger breaks its
    own graph.

    So a ledger whose verdict is called BUILD, or DO, would have walked past the
    last line of defence in the file with every structural check passing, and
    nothing would ever have noticed until it mattered.

    THE CASE BELOW BREAKS THE GRAPH ON PURPOSE. A node between the sweep and the
    mint proposes a method of a DIFFERENT CLASS, so the gate entries the sweep
    wrote are recorded under a row that no longer applies. That is the same shape
    as the latching bypass, arriving after the sweep instead of before it, and it
    is exactly what the exit check exists to catch.
    """

    def _drifting(self, *, drifts=True):
        """A ledger whose commit stage changes its mind after the sweep.

        `drifts=False` proposes a method of the SAME class, so the row the sweep
        used still applies and the run is legitimate. That is the control: it is
        the CLASS CHANGE that breaks this, not the second proposal.
        """
        doc = _committing()
        doc["methods"]["THE_OTHER_THING"] = {"class": "other" if drifts else "big"}
        doc["methods"]["A_THIRD_THING"] = {"class": "other"}
        doc["gates"]["G0_ENOUGH"]["passes_when"] = [
            {"method_class": "any", "requires": "count >= 10"},
            {"method_class": "other", "requires": "count >= 1000"},
        ]
        doc["contract"]["outcome_prefixes"]["DO__"]["mintable_only_at"] = "S9_MINT"
        doc["stage_9_commit"] = [
            {"node": "S9_SWEEP", "condition": "always", "order": "G0_ENOUGH"},
            # THE BUG. A proposal arriving after the sweep changes which row
            # applies, and nothing re-asks it.
            {
                "node": "S9_CHANGE_ITS_MIND",
                "condition": "always",
                "propose": "THE_OTHER_THING",
            },
            {
                "node": "S9_MINT",
                "condition": "proposed_method != NONE_YET",
                "outcome": "DO__{proposed_method}",
                "emits": ["DO__THE_THING", "DO__THE_OTHER_THING", "DO__A_THIRD_THING"],
            },
        ]
        return doc

    def test_a_gated_verdict_whose_row_stopped_applying_raises_rather_than_renders(self):
        spec = self.load(self._drifting())
        with self.assertRaises(Exception) as caught:
            diagnose({"colour": stated("green"), "count": measured(20)}, spec)
        self.assertIn("ERROR__GATE_SKIPPED", str(caught.exception))
        self.assertIn("G0_ENOUGH", str(caught.exception))

    def test_the_same_graph_is_fine_while_the_row_still_applies(self):
        """Non-vacuity of the case above: it is the CLASS CHANGE that breaks it.

        Without this control, a mistake anywhere else in `_drifting` would raise
        for some unrelated reason and the case above would look like it was
        catching the defect.
        """
        spec = self.load(self._drifting(drifts=False))
        result = diagnose({"colour": stated("green"), "count": measured(20)}, spec)
        self.assertEqual(result.outcome, "DO__THE_OTHER_THING")
        self.assertEqual(result.gate_ledger["G0_ENOUGH"]["status"], "PASSED")


class TheGateSweepIsPartOfTheHonestyTestTest(LedgerCase):
    def test_a_ledger_with_gates_and_a_commit_stage_must_name_a_sweep(self):
        """Safe and broken is not the same as safe and working.

        Without a sweep the exit check would still refuse to mint - so the
        product stays safe - and it would refuse by raising, which is a stack
        trace in front of a user rather than a diagnosis. A build that stops is
        the only way anybody finds out which one they have.
        """
        doc = _committing()
        doc["contract"]["roles"].pop("gate_sweep_node")
        error = self.refuses(doc, "LF050")
        self.assertIn("re-asks every gate", str(error))

    def test_a_sweep_written_below_the_mint_is_refused(self):
        doc = _committing()
        doc["stage_9_commit"] = list(reversed(doc["stage_9_commit"]))
        with self.assertRaises(SpecError) as caught:
            self.load(doc)
        self.assertIn("AFTER the minting node", str(caught.exception))

    def test_a_sweep_outside_the_commit_stage_is_refused(self):
        """And the refusal is about the ROLE, not about a node that stopped being one.

        A node is executable BECAUSE it is the sweep, so pointing the role
        elsewhere used to fail with *"node S9_SWEEP has no outcome, no route, no
        proposal and no handler"* - true, useless, and about the wrong node.
        Reporting the cause before the symptom is the whole reason to order
        checks at all.
        """
        doc = _committing()
        doc["stage_0_start"].insert(
            0, {"node": "S0_SWEEP_HERE", "condition": "always", "order": "G0_ENOUGH"}
        )
        doc["contract"]["roles"]["gate_sweep_node"] = "S0_SWEEP_HERE"
        doc["stage_9_commit"] = doc["stage_9_commit"][1:]
        error = self.refuses(doc, "LF051")
        self.assertIn("gate_sweep_node", str(error))
        self.assertIn("stage_0_start", str(error))

    def test_a_sweep_naming_a_node_that_does_not_exist_is_refused(self):
        doc = _committing()
        doc["contract"]["roles"]["gate_sweep_node"] = "S9_SWEEEP"
        self.refuses(doc, "LF051")


class TheForkSchemaTest(LedgerCase):
    def _forking(self, **fork):
        doc = copy.deepcopy(MINIMAL)
        doc["stage_1_next"] = [
            {"node": "S1_DONE", "condition": "count >= 0", "outcome": "ANSWER__DONE"}
        ]
        doc["stage_0_start"] = [
            {
                "node": "S0_FORK",
                "condition": "always",
                "fork": {
                    "branch_on": "colour",
                    "select": "value",
                    "routes": {"red": "stage_1_next"},
                    "no_match": {"outcome": "ACTION__PICK_A_COLOUR"},
                    **fork,
                },
            }
        ]
        return doc

    def test_a_fork_the_engine_has_never_seen_by_name_still_runs(self):
        spec = self.load(self._forking())
        self.assertEqual(diagnose({"colour": stated("red")}, spec).outcome, "ANSWER__DONE")

    def test_no_match_answers_rather_than_crashing_when_it_declares_an_outcome(self):
        spec = self.load(self._forking())
        self.assertEqual(
            diagnose({"colour": stated("green")}, spec).outcome, "ACTION__PICK_A_COLOUR"
        )

    def test_no_match_may_route_instead(self):
        spec = self.load(self._forking(no_match={"route": "stage_1_next"}))
        self.assertEqual(diagnose({"colour": stated("green")}, spec).outcome, "ANSWER__DONE")

    def test_no_match_may_declare_the_case_an_engine_bug_and_say_why(self):
        """The third answer, and the reason `error:` is allowed at all.

        Both ML forks do exactly this, because it is what they did before the
        schema existed and an upgrader may not decide a question the old
        document never answered. What is NOT allowed is saying nothing.
        """
        spec = self.load(self._forking(no_match={"error": "colour is a closed enum"}))
        with self.assertRaises(Exception) as caught:
            diagnose({"colour": stated("green")}, spec)
        self.assertIn("closed enum", str(caught.exception))

    def test_every_one_of_the_four_keys_is_required(self):
        for key in ("branch_on", "select", "routes", "no_match"):
            with self.subTest(key=key):
                doc = self._forking()
                doc["stage_0_start"][0]["fork"].pop(key)
                error = self.refuses(doc, "LF043")
                self.assertIn(key, str(error))

    def test_the_missing_no_match_message_names_all_three_answers(self):
        doc = self._forking()
        doc["stage_0_start"][0]["fork"].pop("no_match")
        error = self.refuses(doc, "LF043")
        for answer in ("outcome:", "route:", "error:"):
            self.assertIn(answer, str(error))

    def test_a_selector_outside_the_closed_vocabulary_is_refused(self):
        error = self.refuses(self._forking(select="first_match"), "LF045")
        for known in FORK_SELECTORS:
            self.assertIn(known, str(error))

    def test_branching_on_something_undeclared_is_refused(self):
        self.refuses(self._forking(branch_on="hue"), "LF044")

    def test_branching_on_an_enum_MEMBER_rather_than_the_fact_is_refused(self):
        """`red` resolves to itself, so this would load and route on a constant."""
        self.refuses(self._forking(branch_on="red"), "LF044")

    def test_routing_to_something_that_is_not_a_stage_is_refused(self):
        error = self.refuses(self._forking(routes={"red": "S1_DONE"}), "LF046")
        self.assertIn("resumes the walk at a STAGE", str(error))

    def test_a_bare_routes_mapping_is_refused_and_names_the_fork_block(self):
        """The format-2 spelling, refused in format 3 rather than half-executed."""
        doc = copy.deepcopy(MINIMAL)
        doc["stage_1_next"] = [
            {"node": "S1_DONE", "condition": "count >= 0", "outcome": "ANSWER__DONE"}
        ]
        doc["stage_0_start"] = [
            {"node": "S0_FORK", "condition": "always", "routes": {"red": "stage_1_next"}}
        ]
        error = self.refuses(doc, "LF040")
        self.assertIn("fork:", str(error))

    def test_argmax_takes_the_largest_and_breaks_ties_in_declared_order(self):
        doc = copy.deepcopy(MINIMAL)
        doc["facts"]["tally"] = {
            "type": "map[str,int]", "source": "derive", "scope": "thread", "default": {},
        }
        doc["fact_origins"]["admissible_for_gates"]["derive"] = ["MEASURED"]
        doc["fact_origins"]["substantiation"]["derive"] = "compute it"
        doc["stage_1_next"] = [
            {"node": "S1_DONE", "condition": "count >= 0", "outcome": "ANSWER__FIRST"}
        ]
        doc["stage_2_other"] = [
            {"node": "S2_DONE", "condition": "count >= 0", "outcome": "ANSWER__SECOND"}
        ]
        doc["stage_0_start"] = [
            {
                "node": "S0_FORK",
                "condition": "always",
                "fork": {
                    "branch_on": "tally",
                    "select": "argmax",
                    "routes": {"a": "stage_1_next", "b": "stage_2_other"},
                    "no_match": {"outcome": "ACTION__COUNT_SOMETHING"},
                },
            }
        ]
        spec = self.load(doc)
        self.assertEqual(diagnose({"tally": stated({"b": 9, "a": 3})}, spec).outcome,
                         "ANSWER__SECOND")
        self.assertEqual(diagnose({"tally": stated({"a": 4, "b": 4})}, spec).outcome,
                         "ANSWER__FIRST")
        self.assertEqual(diagnose({"tally": stated({"z": 4})}, spec).outcome,
                         "ACTION__COUNT_SOMETHING")
        self.assertEqual(diagnose({"tally": stated({})}, spec).outcome,
                         "ACTION__COUNT_SOMETHING")


class TheDerivedBlockIsDeclaredNotScrapedTest(LedgerCase):
    def test_a_derived_enum_supplies_literals_the_way_a_facts_enum_does(self):
        doc = copy.deepcopy(MINIMAL)
        doc["derived"] = {"route": {"enum": ["FAST", "SLOW"], "means": "how it went"}}
        doc["stage_0_start"] = [
            {"node": "S0_FAST", "condition": "route == FAST", "outcome": "ANSWER__FAST"},
            {"node": "S0_ANY", "condition": "count >= 0", "outcome": "ANSWER__ANY"},
        ]
        spec = self.load(doc)
        self.assertIn("FAST", spec.literals)
        self.assertIn("SLOW", spec.literals)

    def test_a_derived_name_the_engine_cannot_compute_is_refused_at_load(self):
        """It used to load and die at run time with a stack trace instead."""
        doc = copy.deepcopy(MINIMAL)
        doc["derived"] = {"my_own_thing": {"means": "something the engine cannot make"}}
        error = self.refuses(doc, "LF030")
        self.assertIn("my_own_thing", str(error))


class TheStrictLoaderClosesThreeYamlHazardsTest(LedgerCase):
    """Constrained YAML with a strict loader, not a different file extension.

    Keeping YAML is what keeps the ARGUMENT in the ledger - the folded prose that
    is half the value of these files and the reason a reviewer can check them.
    What had to go is YAML 1.1's implicit typing, which is a live hazard for a
    document whose entire job is to be exactly what its author wrote.
    """

    def write(self, text: str):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "case.yaml"
            path.write_text(text, encoding="utf-8")
            return load_spec(path)

    def base_text(self, **changes) -> str:
        return yaml.safe_dump(_mutate(**changes), sort_keys=False, allow_unicode=True)

    def test_the_norway_problem_cannot_reach_an_enum(self):
        """`no` is a COUNTRY CODE, an answer, and a bucket name. Not a boolean.

        Under PyYAML as shipped, `[yes, no, on, off]` parses to
        `[True, False, True, False]`, so an enum member spelled `no` becomes a
        boolean - and `_collect_literals` would then offer the bare word `False`
        to every condition in the file as a value it may use.

        A DOCUMENT OF ITS OWN RATHER THAN A SUBSTITUTION INTO THE BASELINE:
        rewriting the baseline's enum would leave its conditions naming words
        that no longer exist, and the case would fail for that instead - a
        different defect wearing this one's clothes.
        """
        doc = _mutate()
        doc["facts"]["answered"] = {
            "enum": ["yes", "no"], "source": "ask", "scope": "thread",
        }
        doc["stage_0_start"] = [
            {"node": "S0_YES", "condition": "answered == yes", "outcome": "ANSWER__YES"},
            {"node": "S0_NO", "condition": "answered != yes", "outcome": "ANSWER__NO"},
        ]
        text = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
        text = text.replace("    - 'yes'\n    - 'no'", "    - yes\n    - no")
        self.assertIn("    - no\n", text, "the case must write the UNQUOTED spelling")
        spec = self.write(text)
        self.assertEqual(spec.facts["answered"]["enum"], ["yes", "no"])
        self.assertIn("no", spec.literals)
        self.assertNotIn("False", spec.literals)
        self.assertEqual(diagnose({"answered": stated("no")}, spec).outcome, "ANSWER__NO")

    def test_a_duplicate_key_is_refused_and_names_both_lines(self):
        text = self.base_text() + "\nledger_version: 99\n"
        with self.assertRaises(LedgerError) as caught:
            self.write(text)
        self.assertEqual(caught.exception.check_id, "LF003")
        self.assertIn("first defined at line", str(caught.exception))

    def test_a_duplicate_node_key_would_have_silently_deleted_a_node(self):
        """The failure class the loader exists to prevent, in its worst form.

        PyYAML keeps the LAST value, silently. In a hand-written ledger that is a
        node the file claims to have and the graph does not - which is exactly
        how four training outcomes came to be dead while the ML ledger claimed
        all nine were gated.
        """
        marker = "- node: S0_NOT_RED\n"
        text = self.base_text()
        self.assertIn(marker, text)
        text = text.replace(marker, marker + "  node: S0_SOMETHING_ELSE\n")
        with self.assertRaises(LedgerError) as caught:
            self.write(text)
        self.assertEqual(caught.exception.check_id, "LF003")
        self.assertIn("'node'", str(caught.exception))

    def test_an_anchor_and_alias_are_refused(self):
        """How the second ledger's `route:` came to be a mapping instead of a stage."""
        text = self.base_text().replace(
            "- node: S0_RED\n", "- &first\n  node: S0_RED\n"
        ) + "\nx_copy: *first\n"
        with self.assertRaises(LedgerError) as caught:
            self.write(text)
        self.assertEqual(caught.exception.check_id, "LF002")
        self.assertIn("write the value out", str(caught.exception))

    def test_a_sexagesimal_looking_string_stays_a_string(self):
        text = self.base_text().replace("ledger_version: 1", "ledger_version: 1\nx_at: 12:30")
        spec = self.write(text)
        self.assertEqual(spec.raw["x_at"], "12:30")

    def test_real_booleans_still_parse_as_booleans(self):
        """The narrowing must not take `true` with it."""
        text = self.base_text().replace(
            "    source: inspect\n    scope: thread\n    default: 0",
            "    source: inspect\n    scope: thread\n    default: 0\n    x_flag: true",
        )
        spec = self.write(text)
        self.assertIs(spec.facts["count"]["x_flag"], True)


class TheErrorSaysWhereAndWhatToDoTest(LedgerCase):
    def test_a_refusal_carries_a_document_a_check_id_and_a_remedy(self):
        error = self.refuses(_mutate(ledger_format=99), "LF001")
        self.assertTrue(error.document and error.document.endswith(".yaml"))
        self.assertEqual(error.line, 1)
        self.assertTrue(error.remedy)
        self.assertIn("[LF001]", str(error))

    def test_a_ledger_error_is_a_spec_error(self):
        """Every existing caller catches SpecError. None of them had to change."""
        self.assertTrue(issubclass(LedgerError, SpecError))

    def test_check_ids_are_unique_per_reason(self):
        """Two different reasons sharing an id would make the corpus meaningless."""
        seen: dict[str, str] = {}
        cases = {
            "LF001": _mutate(ledger_format=99),
            "LF012": _mutate(contract__roles=_GONE),
            "LF022": _committing(),
            "LF030": _mutate(derived={"nope": {"means": "x"}}),
        }
        cases["LF022"]["contract"]["outcome_prefixes"]["DO__"]["gated"] = ["G0_ENOUGH"]
        for expected, doc in cases.items():
            with self.subTest(check=expected):
                error = self.refuses(doc, expected)
                self.assertNotIn(error.check_id, seen)
                seen[error.check_id] = expected


class AGatedPrefixOverNoGatesIsRefusedTest(LedgerCase):
    """LF027. THE ONE-LINE EDIT THAT TURNED THE WHOLE HONESTY TEST OFF.

    Found by an adversary against the tree these tests shipped in, and it is the
    worst shape this format has had, because every OTHER corner of it was
    already refused. LF023 refuses a gated prefix without a commit stage and a
    commit stage without a gated prefix. LF025 refuses a missing
    `mintable_only_at`. LF050 refuses a missing sweep. LF051 refuses a sweep
    outside the commit stage. SC1 refuses a second minting node. All five stay
    satisfied when `required_gates` is `[]`, and all five become no-ops: `gated:
    all` over the empty set is vacuously true, the sweep has nothing to ask, and
    `_finish`'s ERROR__GATE_SKIPPED check compares against an empty list.

    The result was an irreversible verdict minted with an EMPTY gate ledger,
    while the gate that would have refused it sat defined, in full, in the same
    document.
    """

    def test_a_gated_prefix_over_an_empty_gate_list_is_refused(self):
        error = self.refuses(_committing(contract__required_gates=[]), "LF027")
        self.assertIn("vacuously true", str(error))

    def test_the_control_is_the_same_document_with_the_gate_named(self):
        """Non-vacuity: the only difference is the one list."""
        spec = self.load(_committing())
        self.assertEqual(spec.required_gates, ["G0_ENOUGH"])

    def test_what_it_would_have_minted_had_it_loaded(self):
        """The measured consequence, recorded so nobody has to take it on trust.

        `count: 1` fails `count >= 10`, which is the gate this ledger defines.
        With the gate named, that run is refused. The refused document is the
        same run with the list emptied, and there is nothing left to refuse it.
        """
        spec = self.load(_committing())
        refused = diagnose({"colour": stated("green"), "count": measured(1)}, spec)
        self.assertEqual(refused.outcome, "ACTION__GET_MORE")
        self.assertEqual(refused.gate_ledger["G0_ENOUGH"]["status"], "FAILED")
        self.assertEqual(refused.gate_ledger["G0_ENOUGH"]["clause"], "count >= 10")

    def test_a_non_committing_ledger_may_still_have_no_gates(self):
        """The check is about the GATED PREFIX, not about having gates.

        MINIMAL has `required_gates: []` and no gated prefix, and that is a
        ledger saying it commits to nothing irreversible. It must keep loading,
        or the fix would have turned a legal answer into an error.
        """
        self.assertEqual(MINIMAL["contract"]["required_gates"], [])
        self.assertIsNone(self.load(MINIMAL).gated_prefix)


class TheDeclaredVerdictVocabularyIsReadTest(LedgerCase):
    """LF028. `contract.diagnosis.verdict.enum` was written by every ledger and read by none.

    A vocabulary a document declares and the engine ignores is worse than no
    vocabulary: the author believes they constrained something. The verdict is
    the single word the interface branches on and a person is shown, so a prefix
    mapping to a word outside the declared set puts something on the screen the
    file says cannot happen.
    """

    def test_a_verdict_outside_the_declared_enum_is_refused(self):
        doc = _mutate()
        doc["contract"]["outcome_prefixes"]["ANSWER__"]["verdict"] = "SHIP_IT_NOW"
        error = self.refuses(doc, "LF028")
        self.assertIn("SHIP_IT_NOW", str(error))

    def test_a_verdict_that_is_not_a_word_at_all_is_refused(self):
        doc = _mutate()
        doc["contract"]["outcome_prefixes"]["ANSWER__"]["verdict"] = {"a": 1}
        self.refuses(doc, "LF028")

    def test_a_prefix_with_no_verdict_key_is_refused(self):
        doc = _mutate()
        doc["contract"]["outcome_prefixes"]["ANSWER__"].pop("verdict")
        self.refuses(doc, "LF028")

    def test_a_terminal_prefix_with_a_null_verdict_is_refused(self):
        """A run that ENDS here has to end with a verdict.

        This used to reach `_finish`, which raised EngineError on a null verdict
        - a stack trace where a diagnosis was owed, from a document that could
        have been refused at load.
        """
        doc = _mutate()
        doc["contract"]["outcome_prefixes"]["ANSWER__"]["verdict"] = None
        self.refuses(doc, "LF028")

    def test_a_missing_vocabulary_is_refused(self):
        self.refuses(_mutate(contract__diagnosis={"verdict": {}}), "LF028")

    def test_null_stays_legal_for_the_prefixes_a_walk_passes_through(self):
        """REROUTE is `verdict: null` and not terminal, and it must keep loading."""
        self.assertIsNone(MINIMAL["contract"]["outcome_prefixes"]["REROUTE"]["verdict"])
        self.load(MINIMAL)


class AGateIdentifiesItselfTruthfullyTest(LedgerCase):
    """LF015. The ids a gate DISPLAYS have to name the things they claim to name.

    A gate's `node:` is a name that exists nowhere else in the document - it is
    the id the gate machinery writes onto the path - so "is it in node_index"
    is the wrong question and the answer is no for all ten gates in the two real
    ledgers. The two real defects are collision and disagreement, and both reach
    `app/asking.py:_because_for`, which turns a path entry back into the gate
    that wrote it and puts its `stage:` on the card.
    """

    def test_two_gates_sharing_a_node_id_are_refused(self):
        doc = _committing()
        doc["contract"]["required_gates"] = ["G0_ENOUGH", "G1_ALSO"]
        doc["gates"]["G1_ALSO"] = copy.deepcopy(doc["gates"]["G0_ENOUGH"])
        doc["stage_0_start"].insert(1, {"gate_ref": "G1_ALSO"})
        doc["stage_9_commit"][0]["order"] = "G0_ENOUGH, G1_ALSO"
        error = self.refuses(doc, "LF015")
        self.assertIn("S0_NOT_ENOUGH", str(error))

    def test_a_gate_node_that_collides_with_a_real_node_is_refused(self):
        doc = _committing()
        doc["gates"]["G0_ENOUGH"]["node"] = "S0_RED"
        error = self.refuses(doc, "LF015")
        self.assertIn("S0_RED", str(error))

    def test_a_gate_stage_that_names_no_stage_is_refused(self):
        self.refuses(_committing(gates__G0_ENOUGH__stage="stage_nowhere"), "LF015")

    def test_a_gate_stage_that_is_not_where_its_gate_ref_sits_is_refused(self):
        """Written by hand, never read against the reference, wrong forever."""
        error = self.refuses(
            _committing(gates__G0_ENOUGH__stage="stage_9_commit"), "LF015"
        )
        self.assertIn("stage_0_start", str(error))

    def test_the_control_is_the_same_document_telling_the_truth(self):
        spec = self.load(_committing())
        self.assertEqual(spec.gates["G0_ENOUGH"]["stage"], "stage_0_start")
        self.assertNotIn(spec.gates["G0_ENOUGH"]["node"], spec.node_index)


def _forking(no_match, routes=None):
    """`_committing()` with a fork in stage 0 whose `no_match:` is under test."""
    doc = _committing()
    doc["stage_0_start"].insert(
        1,
        {
            "node": "S0_FORK",
            "condition": "colour == green",
            "fork": {
                "branch_on": "colour",
                "select": "value",
                "routes": routes or {"green": "stage_9_commit"},
                "no_match": no_match,
            },
        },
    )
    return doc


class AForkIsAPlaceALedgerStatesAnOutcomeTest(LedgerCase):
    """THE FIFTH SITE, AND THE HOLE IT OPENED IN SC1.

    `fork:` arrived with `no_match: {outcome: ...}`, which is a fifth way a
    ledger may state an outcome, and the three checks that scan for outcomes
    each knew their own list of places to look. SC1's list was one entry long -
    a node's `outcome:` - so a ledger written after that change could mint the
    expensive irreversible verdict from a fork in ANY node, load clean, and come
    back with the gated verdict having walked past `emits:`, past the mint's
    `mintable_only_at`, and past every reachability check in the suite. SC1
    would have reported `found []` and been satisfied that nobody minted at all.

    `Spec.outcome_sites()` is now the single enumeration and every check reads
    it. `test_every_outcome_shaped_string_in_a_real_ledger_is_found` below scans
    the raw document, so a SIXTH site cannot be added silently either.
    """

    def test_a_fork_may_state_an_ordinary_outcome(self):
        """The control. This is legal and both real ledgers use it."""
        spec = self.load(_forking({"outcome": "ACTION__GET_MORE"}))
        self.assertIn("ACTION__GET_MORE", spec.declared_outcomes())

    def test_a_fork_stating_the_gated_prefix_is_refused(self):
        doc = _forking({"outcome": "DO__THE_THING"})
        with self.assertRaises(SpecError) as caught:
            self.load(doc)
        self.assertIn("SC1", str(caught.exception))
        self.assertIn("S0_FORK", str(caught.exception))

    def test_a_fork_in_the_minting_node_itself_is_refused(self):
        """Right node, right `emits:`, and still a verdict from an uncosted branch.

        `emits:` says what the TEMPLATE stands for. It never said that nothing
        else at that node states a gated outcome, so a fork written into the
        mint satisfied both halves of SC1 as it stood.
        """
        doc = _committing()
        doc["stage_9_commit"][1]["fork"] = {
            "branch_on": "colour",
            "select": "value",
            "routes": {"red": "stage_0_start"},
            "no_match": {"outcome": "DO__SOMETHING_ELSE"},
        }
        with self.assertRaises(SpecError) as caught:
            self.load(doc)
        self.assertIn("SC1", str(caught.exception))
        self.assertIn("DO__SOMETHING_ELSE", str(caught.exception))

    def test_a_gate_on_fail_may_not_state_the_gated_prefix_either(self):
        """A gate's `on_fail` is reached BY FAILING the gate. Minting there is the
        prefix meaning its own opposite."""
        doc = _committing()
        doc["gates"]["G0_ENOUGH"]["on_fail"]["outcome"] = "DO__THE_THING"
        with self.assertRaises(SpecError) as caught:
            self.load(doc)
        self.assertIn("SC1", str(caught.exception))

    def test_a_fork_stated_outcome_is_in_declared_outcomes(self):
        """Reachability checks read `declared_outcomes()`. It missed this site,
        so an outcome only a fork named was reachable by a real sheet and
        invisible to every check that asks what this ledger can produce."""
        spec = self.load(_forking({"outcome": "ACTION__GET_MORE"}))
        sites = [s for s in spec.outcome_sites() if "fork" in s.where]
        self.assertEqual([(s.outcome, s.node) for s in sites],
                         [("ACTION__GET_MORE", "S0_FORK")])


class EveryOutcomeInARealLedgerIsFoundBySiteEnumerationTest(unittest.TestCase):
    """THE CHECK THAT CANNOT GO STALE, and the reason a sixth site is a red test.

    `outcome_sites()` is a hand-written list of places to look, and a hand-written
    list of places to look is exactly what went wrong. So this does not trust it:
    it walks the RAW document for every string that carries a declared prefix and
    asserts that each one was found. Add a sixth grammatical home for an outcome
    and this fails before SC1 has a chance to go blind.
    """

    def _scan(self, raw, prefixes):
        found = []

        def walk(value):
            if isinstance(value, str):
                if any(value.startswith(p) for p in prefixes) and "{" not in value:
                    found.append(value)
            elif isinstance(value, dict):
                for key, item in value.items():
                    if key in ("meaning", "note", "say", "asks", "action", "recipe"):
                        continue
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)

        # Only the parts of the document that DECIDE. `contract` declares the
        # prefixes themselves and would match every one of them.
        for key, block in raw.items():
            if key in ("contract",):
                continue
            walk(block)
        return set(found)

    def test_both_shipped_ledgers(self):
        import app.diagnosis as engine

        for path in (
            Path("docs/diagnosis_engine.yaml"),
            Path("docs/ledgers/ai_engineering.yaml"),
        ):
            with self.subTest(ledger=str(path)):
                spec = load_spec(path)
                prefixes = [
                    p
                    for p, decl in spec.contract["outcome_prefixes"].items()
                    if decl.get("terminal")
                ]
                in_document = self._scan(spec.raw, prefixes)
                enumerated = {s.outcome for s in spec.outcome_sites()}
                missed = in_document - enumerated
                self.assertEqual(
                    missed,
                    set(),
                    f"{path} states these outcomes somewhere Spec.outcome_sites() does "
                    f"not look: {sorted(missed)}. A new grammatical home for an outcome "
                    "is a change to outcome_sites(), or SC1 goes blind to it.",
                )
                self.assertTrue(engine.OutcomeSite)


class TheConditionDialectHasNoSilentDropTest(LedgerCase):
    """Two holes an adversary found in the expression sandbox, both silent.

    Neither was remote code execution and saying so is part of the finding. Both
    were the same defect this file refuses everywhere else in the grammar: a
    thing the author wrote that the engine accepted and then ignored.
    """

    def test_a_keyword_argument_is_refused_rather_than_dropped(self):
        """`_names_used.visit_Call` visited `func` and `args` and not `keywords`,
        so a keyword slot escaped BOTH the AST allowlist and the
        undeclared-name check - and the evaluator dropped it unrun."""
        doc = _mutate()
        doc["stage_0_start"][0]["condition"] = "len(colour, default=0) > 0"
        with self.assertRaises(SpecError) as caught:
            self.load(doc)
        self.assertIn("keyword", str(caught.exception))

    def test_the_same_expression_positionally_is_still_read(self):
        """Control: the refusal is about the keyword, not about the call."""
        doc = _mutate()
        doc["stage_0_start"][0]["condition"] = "len(colour) > 0"
        self.load(doc)

    def test_an_undeclared_name_in_a_keyword_slot_no_longer_hides(self):
        doc = _mutate()
        doc["stage_0_start"][0]["condition"] = "len(colour, default=no_such_fact) > 0"
        with self.assertRaises(SpecError):
            self.load(doc)

    def test_arithmetic_on_text_is_refused_rather_than_allocated(self):
        """`'a' * 2_000_000_000` is two constants an author can type, and it takes
        two gigabytes before anything else in the engine gets a say."""
        doc = _mutate()
        doc["facts"]["label"] = {"type": "string", "source": "ask", "scope": "thread"}
        doc["stage_0_start"][0]["condition"] = "len(label * count) > 0"
        spec = self.load(doc)
        with self.assertRaises(SpecError) as caught:
            diagnose({"label": stated("a"), "count": stated(3)}, spec)
        self.assertIn("arithmetic", str(caught.exception))

    def test_arithmetic_on_numbers_still_works(self):
        """Control, and it is the shape both real ledgers use:
        `labeled_examples_n >= 8 * classes_n`."""
        doc = _mutate()
        doc["stage_0_start"][0]["condition"] = "count * 2 >= 4"
        spec = self.load(doc)
        self.assertEqual(diagnose({"count": stated(3)}, spec).outcome, "ANSWER__RED")
        self.assertEqual(diagnose({"count": stated(1)}, spec).outcome, "ANSWER__NOT_RED")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
