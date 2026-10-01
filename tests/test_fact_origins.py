"""TEST 9. RC10. An assertion never mints, and this is the wall's own test.

RC1 is called the most important test in the repository. It asks whether the
five gates were passed on the path that reached a training recommendation. THIS
FILE ASKS THE OTHER HALF OF THAT QUESTION: whether passing them meant anything.

The defect it exists for, quoted from the adversary who found it:

    "FACT PROVENANCE IS NOT TRACKED, so the gates are only as true as whoever
     supplied the facts. A provider that merely ASSERTS eval_size_n /
     baseline_measured / baseline_score / prompt_iterations / retrieval_tried /
     model_swap_tried gets TRAIN__LORA_SFT with all five gates green.
     eval_size_n and baseline_measured are declared source: inspect - they must
     be MEASURED - but nothing enforces that they came from a tool rather than
     the model's mouth. The only defence is the instruction set, i.e. prose."

Every structural check in the repository passed while that was true, because
every structural check was about the shape of the graph. A graph of perfect
shape fed asserted facts gives a perfect TRAIN verdict to a user who has done
none of the work, and the user never finds out that nothing was checked.

WHERE THE FACT NAMES COME FROM, because this is the part that decides whether
this file is worth anything in a year. Nothing here writes down which facts a
gate reads. Each `passes_when` row's `requires` string is parsed with the
engine's own condition compiler and intersected with the ledger, so a fact added
to a gate row next year is covered on the day it is added. The six the adversary
named fall out of that derivation; they appear below ONLY as a lower bound on
it, asserted so that a derivation which quietly started returning nothing fails
here with a name rather than passing over an empty loop.

AND THE DERIVATION IS DONE TWICE, ON PURPOSE. `Spec.gate_row_facts` is the
engine's own answer and it is what the engine enforces against. If this file
reused it, a broken `_facts_read_by` returning empty sets would make the engine
challenge nothing and this test loop over nothing, and both would be green. So
the names are re-derived here from the raw `requires` strings and the two
answers are asserted equal.

WHAT THE FUZZ AT THE BOTTOM DOES AND WHY IT IS NOT RANDOM. The last adversary's
first 200,000-case fuzz reached ZERO TRAIN verdicts: pure random fact sets never
get down the training path, so it proved crash-resistance and tested the gates
vacuously - "gated the way an empty room is quiet". So the mutation sweep here
starts from the nine real TRAIN fixtures, changes NO VALUE, and moves only
origins. Every draw is one keystroke away from a training verdict, which is the
only neighbourhood where this property can be violated at all. And it asserts
non-vacuity in both directions: some draws must still mint, and some must be
refused. A sweep where nothing minted would be the empty room again.
"""

from __future__ import annotations

import ast
import random
import unittest

import diagnosis_fixtures as fixtures

from app.diagnosis import (
    ASSERTED,
    DEFAULTED,
    MEASURED,
    ORIGINS,
    STATED,
    Fact,
    FactError,
    bare,
    compile_condition,
    default_spec,
    diagnose,
    gates_passed_under,
)

# Fixed, so a failing draw is reproducible and today's green run is tomorrow's.
SEED = 20260819

# Nine fixtures, forty origin perturbations each. Under a second; the exhaustive
# question - does anything raise - belongs to tests/test_diagnosis_no_crash.py
# and is budgeted there.
DRAWS = 4_000

# The six facts the adversary named. THIS IS NOT THE INPUT TO ANY CHECK. It is a
# lower bound on the derivation, so that a derivation returning nothing fails
# with these names in the message instead of passing over an empty loop.
THE_SIX_FROM_THE_REPORT = frozenset(
    {
        "eval_size_n",
        "baseline_measured",
        "baseline_score",
        "prompt_iterations",
        "retrieval_tried",
        "model_swap_tried",
    }
)


def facts_a_row_reads(spec, requires: str) -> frozenset[str]:
    """Re-derive, independently of the engine, the declared facts a row reads.

    Parsed with `compile_condition` so the dialect is read the way the engine
    reads it, then intersected with the ledger so that bare enum words - which
    the dialect allows inside set literals - are not mistaken for fact lookups.
    """
    tree = compile_condition(requires)
    return frozenset(
        n.id for n in ast.walk(tree) if isinstance(n, ast.Name)
    ) & set(spec.facts)


def every_fact_a_gate_reads(spec) -> frozenset[str]:
    """The union over every `passes_when` row of every gate."""
    names: set[str] = set()
    for gate in spec.gates.values():
        for row in gate["passes_when"]:
            names |= facts_a_row_reads(spec, row["requires"])
    return frozenset(names)


def reattributed(facts: dict, names, origin: str) -> dict:
    """The same fact set with the named facts' ORIGINS changed and no value touched.

    This is the whole experiment. If a single value moved, a failure here would
    be ambiguous between "the origin rule works" and "the fact set stopped being
    a training story", and the second reading is the one somebody would reach
    for to explain away a red test.
    """
    out = dict(facts)
    for name in names:
        if name in out:
            out[name] = Fact(bare(out[name]), origin)
    return out


class TheDerivationIsRealTest(unittest.TestCase):
    """The vacuum guard, first, because everything below loops over this set."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = default_spec()
        cls.read = every_fact_a_gate_reads(cls.spec)

    def test_the_gates_read_facts_at_all(self):
        self.assertTrue(
            self.read,
            "no gate row names a declared fact, so every assertion in this file "
            "would pass over an empty loop. Either the condition dialect changed "
            "under `compile_condition`, or the gates stopped asking about facts",
        )

    def test_the_derivation_covers_what_the_adversary_actually_found(self):
        missing = sorted(THE_SIX_FROM_THE_REPORT - self.read)
        self.assertEqual(
            missing,
            [],
            f"the derivation no longer reaches {missing}, which are the facts a "
            "provider asserted its way to TRAIN__LORA_SFT with. If a gate genuinely "
            "stopped reading one of them that is a spec change and this list "
            "should shrink deliberately - but a silent disappearance means the "
            "derivation broke, and this file is now testing nothing",
        )

    def test_the_engine_derives_the_same_facts_this_file_does(self):
        """Two derivations, because one of them checking itself proves nothing.

        `Spec.gate_row_facts` is what the engine enforces against. If it returned
        empty sets, the engine would challenge nothing and a version of this file
        that reused it would loop over nothing. Both would be green.
        """
        for gate_id, gate in sorted(self.spec.gates.items()):
            for row in gate["passes_when"]:
                key = (gate_id, row["method_class"])
                with self.subTest(gate=gate_id, row=row["method_class"]):
                    self.assertEqual(
                        set(self.spec.gate_row_facts[key]),
                        set(facts_a_row_reads(self.spec, row["requires"])),
                        f"the engine and this test disagree about what {gate_id} "
                        f"row {row['method_class']!r} reads",
                    )

    def test_every_fact_a_gate_reads_carries_a_source_the_policy_covers(self):
        """SC5, at the only place it bites: the facts that can open a gate."""
        for name in sorted(self.read):
            with self.subTest(fact=name):
                source = self.spec.facts[name].get("source")
                self.assertIn(
                    source,
                    self.spec.admissible_origins,
                    f"{name} declares source {source!r}, which fact_origins has no "
                    "row for. Its admissible set would be empty and the gate "
                    "reading it could never open",
                )
                self.assertTrue(self.spec.admissible_for(name))
                self.assertTrue(self.spec.substantiation(name).strip())


class AnAssertionNeverMintsTest(unittest.TestCase):
    """RC10, and the reason this file exists.

    Three widths, narrowing. All gates at once; one gate at a time; and the
    adversary's own six. Each takes a fact set that DOES mint, changes no value,
    and moves origins.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = default_spec()
        cls.read = every_fact_a_gate_reads(cls.spec)
        cls.refusal = cls.spec.unsubstantiated_outcome

    def test_the_fixtures_that_must_be_broken_actually_mint_first(self):
        """Non-vacuity. Breaking a fixture that never worked proves nothing."""
        self.assertTrue(fixtures.MINTING, "there are no training fixtures to break")
        for outcome, facts in sorted(fixtures.MINTING.items()):
            with self.subTest(outcome=outcome):
                self.assertEqual(diagnose(facts, self.spec).outcome, outcome)

    def test_no_train_outcome_survives_its_gate_facts_becoming_assertions(self):
        """THE ASSERTION. Same values, worse provenance, no training verdict."""
        for outcome, facts in sorted(fixtures.MINTING.items()):
            with self.subTest(outcome=outcome):
                claimed = reattributed(facts, self.read, ASSERTED)
                result = diagnose(claimed, self.spec)
                self.assertFalse(
                    result.outcome.startswith("TRAIN__"),
                    f"{outcome} was minted from claims. Not one value changed - "
                    f"only who says so - and the engine still answered "
                    f"{result.outcome} at {result.node}. The gate ledger says "
                    f"{ {g: e['status'] for g, e in result.gate_ledger.items()} }",
                )
                self.assertNotEqual(result.verdict, "TRAIN")
                self.assertEqual(result.outcome, self.refusal)

    def test_the_refusal_names_a_gate_and_the_facts_behind_it(self):
        for outcome, facts in sorted(fixtures.MINTING.items()):
            with self.subTest(outcome=outcome):
                result = diagnose(reattributed(facts, self.read, ASSERTED), self.spec)
                self.assertTrue(
                    result.unsubstantiated,
                    "the run was refused for unsubstantiated facts and named none "
                    "of them, so the user is told to show us something and not "
                    "told what",
                )
                for row in result.unsubstantiated:
                    self.assertIn(row["fact"], self.read)
                    self.assertIn(row["gate"], self.spec.required_gates)
                    self.assertEqual(row["origin"], ASSERTED)
                    self.assertEqual(
                        row["declared_source"], self.spec.facts[row["fact"]]["source"]
                    )
                    self.assertTrue(row["substantiation"].strip())

    def test_no_train_outcome_survives_one_gate_at_a_time(self):
        """Narrower, so a failure names the gate that let the claim through.

        The facts of ONE row are downgraded and the rest are left alone. Every
        row of every gate begins with a conjunct whose default is false or zero,
        so masking a row's facts always closes it - which is why this is an
        assertion rather than a survey.
        """
        for outcome, facts in sorted(fixtures.MINTING.items()):
            klass = self.spec.method_class(diagnose(facts, self.spec).proposed_method)
            for gate_id in self.spec.required_gates:
                row_key = self.spec.row_key(gate_id, klass)
                row = self.spec.gate_row(gate_id, klass)
                names = facts_a_row_reads(self.spec, row["requires"])
                with self.subTest(outcome=outcome, gate=gate_id, row=row_key):
                    result = diagnose(reattributed(facts, names, ASSERTED), self.spec)
                    self.assertFalse(
                        result.outcome.startswith("TRAIN__"),
                        f"{outcome} was minted with {sorted(names)} downgraded to "
                        f"claims. {gate_id} row {row_key!r} - {row['requires']!r} - "
                        "opened on something nobody can vouch for",
                    )

    def test_the_adversarys_own_six_facts(self):
        """The report's exact scenario, run.

        The names are still derived - the six are intersected with the derivation
        rather than typed into `reattributed` - so this stays a test of the
        mechanism rather than a test of a list.
        """
        six = sorted(THE_SIX_FROM_THE_REPORT & self.read)
        self.assertEqual(len(six), len(THE_SIX_FROM_THE_REPORT))

        facts = fixtures.MINTING["TRAIN__LORA_SFT"]
        self.assertEqual(diagnose(facts, self.spec).outcome, "TRAIN__LORA_SFT")

        result = diagnose(reattributed(facts, six, ASSERTED), self.spec)
        self.assertNotEqual(result.outcome, "TRAIN__LORA_SFT")
        self.assertEqual(result.verdict, "BLOCKED")
        self.assertEqual(result.outcome, self.refusal)

    def test_a_bare_fact_dict_is_a_dict_of_claims(self):
        """The channel this actually protects: JSON from the user's own model.

        `run_diagnosis` hands `diagnose` whatever the model typed, and every
        value in it is bare. Bare is ASSERTED, so this needs no boundary code and
        cannot be forgotten at a boundary somebody adds later.
        """
        for outcome, facts in sorted(fixtures.MINTING.items()):
            with self.subTest(outcome=outcome):
                stripped = {name: bare(value) for name, value in facts.items()}
                result = diagnose(stripped, self.spec)
                self.assertFalse(result.outcome.startswith("TRAIN__"))
                self.assertEqual(result.outcome, self.refusal)


class WhoSaidItIsPartOfWhetherItCountsTest(unittest.TestCase):
    """The design decision, executed: a person is not a model.

    Three origins would have collapsed "a human said so" and "a model said so"
    into one word, and the admissibility table could then only have been wrong in
    one of two directions - refuse both, and G2 is unpassable for every honest
    user because no tool can check whether somebody rewrote their prompt; admit
    both, and the wall is not there at all. Four origins is what lets the table
    say the true thing, and this class is that sentence made mechanical, derived
    per fact from the ledger's own `source:` column.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = default_spec()
        cls.read = every_fact_a_gate_reads(cls.spec)

    def test_an_ask_fact_is_opened_by_the_user_and_not_by_a_model(self):
        asked = sorted(n for n in self.read if self.spec.facts[n]["source"] == "ask")
        self.assertTrue(asked, "no gate reads a fact the user is asked for")
        for name in asked:
            with self.subTest(fact=name):
                self.assertIn(STATED, self.spec.admissible_for(name))
                self.assertNotIn(ASSERTED, self.spec.admissible_for(name))

    def test_an_inspect_fact_is_not_opened_by_anybody_saying_so(self):
        inspected = sorted(n for n in self.read if self.spec.facts[n]["source"] == "inspect")
        self.assertTrue(inspected, "no gate reads a fact the harness inspects")
        for name in inspected:
            with self.subTest(fact=name):
                self.assertEqual(self.spec.admissible_for(name), frozenset({MEASURED}))

    def test_the_same_value_from_a_person_and_from_a_model_answer_differently(self):
        """End to end, on the fact the split was invented for.

        prompt_iterations is `source: ask`. Five, from the person who did the
        five rewrites, opens G2. Five, from a model reporting on their week,
        does not. Same number, same fact set, different answer - which is the
        whole of the design decision in one pair of assertions.
        """
        facts = fixtures.MINTING["TRAIN__LORA_SFT"]
        self.assertEqual(bare(facts["prompt_iterations"]), 5)

        by_the_person = reattributed(facts, ["prompt_iterations"], STATED)
        self.assertEqual(diagnose(by_the_person, self.spec).outcome, "TRAIN__LORA_SFT")

        by_the_model = reattributed(facts, ["prompt_iterations"], ASSERTED)
        refused = diagnose(by_the_model, self.spec)
        self.assertEqual(refused.outcome, self.spec.unsubstantiated_outcome)
        self.assertEqual(
            [row["fact"] for row in refused.unsubstantiated], ["prompt_iterations"]
        )

    def test_the_user_saying_so_does_not_open_a_fact_the_harness_must_measure(self):
        """The other half, and the one a sympathetic reading would get wrong.

        eval_size_n is `source: inspect`. A user honestly and correctly saying
        "there are a hundred rows in my eval file" still does not open G0,
        because the promise attached to that tag is that the harness COUNTED
        them. This is the strictest line in the policy and it is deliberate: G0
        and G1 are the two gates every other gate stands on.
        """
        facts = fixtures.MINTING["TRAIN__LORA_SFT"]
        result = diagnose(reattributed(facts, ["eval_size_n"], STATED), self.spec)
        self.assertEqual(result.outcome, self.spec.unsubstantiated_outcome)
        self.assertEqual([row["fact"] for row in result.unsubstantiated], ["eval_size_n"])
        self.assertEqual(result.unsubstantiated[0]["origin"], STATED)


class AClaimIsOnlyChallengedWhenItIsLoadBearingTest(unittest.TestCase):
    """Steps 1 and 3 of `fact_origins.rule`, which are what keep this humane.

    A rule that refused every run carrying any unattributed fact would be easy to
    write and would be wrong twice: it would challenge a claim that made no
    difference, and it would tell a user who has done none of the work to go and
    substantiate their admission of having done none of it.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = default_spec()

    def test_a_row_that_fails_on_its_values_is_a_failed_gate_not_a_challenge(self):
        """"You have tried prompting once" gets "go and iterate", never "prove it".

        The check is ordered so the values are asked first. Reversing that order
        produces a product that argues with people about facts it was going to
        reject anyway.
        """
        facts = fixtures.MINTING["TRAIN__LORA_SFT"]
        thin = reattributed(dict(facts, prompt_iterations=1), ["prompt_iterations"], ASSERTED)
        result = diagnose(thin, self.spec)
        self.assertNotEqual(result.outcome, self.spec.unsubstantiated_outcome)
        self.assertEqual(result.unsubstantiated, [])
        self.assertEqual(result.gate_ledger["G2_PROMPT_EXHAUSTED"]["status"], "FAILED")

    def test_a_claim_inside_a_disjunct_something_else_satisfies_is_not_challenged(self):
        """Step 3. The masked re-evaluation, in the one place it can be seen.

        G2's llm_weights row ends in a three-way disjunction: a prompt optimiser,
        OR a metric that is not programmatic, OR an eval set too small for the
        difference to be resolvable. The LoRA fixture satisfies the first. Take
        away the programmatic metric and the second disjunct is satisfied too -
        by an ABSENCE, which no origin can taint. Now downgrade the prompt
        optimiser to a claim: the row still passes without it, so it was not
        load-bearing, and challenging it would be the engine picking a fight it
        does not need to have.
        """
        facts = dict(fixtures.MINTING["TRAIN__LORA_SFT"])
        del facts["metric_is_programmatic"]
        self.assertEqual(diagnose(facts, self.spec).outcome, "TRAIN__LORA_SFT")

        claimed = reattributed(facts, ["prompt_optimizer_tried"], ASSERTED)
        result = diagnose(claimed, self.spec)
        self.assertEqual(
            result.outcome,
            "TRAIN__LORA_SFT",
            "a claim that made no difference to the row was treated as if it had. "
            "The masked re-evaluation in step 3 of fact_origins.rule is what "
            "distinguishes them and it did not run, or it ran the wrong way",
        )
        self.assertEqual(result.gate_ledger["G2_PROMPT_EXHAUSTED"]["status"], "PASSED")

    def test_a_fact_nobody_supplied_is_not_a_claim(self):
        """Absence is not an assertion. It is the ledger's default, and it fails.

        Worth pinning because the two are one keystroke apart in the engine and
        conflating them would produce the same outcome for "you did not tell me"
        and "you told me and nobody can vouch for it" - two different sentences
        the user needs to hear differently.
        """
        facts = dict(fixtures.MINTING["TRAIN__LORA_SFT"])
        del facts["model_swap_tried"]
        result = diagnose(facts, self.spec)
        self.assertEqual(result.unsubstantiated, [])
        self.assertEqual(result.gate_ledger["G4_CHEAPER_MODEL_CONSIDERED"]["status"], "FAILED")
        self.assertNotEqual(result.outcome, self.spec.unsubstantiated_outcome)


class TheRefusalIsANextStepAndNotARefusalTest(unittest.TestCase):
    """What the user is actually told, which is the reason for a distinct outcome.

    Failing the gate silently was the cheaper option and it says something false:
    "build an eval set" to somebody who has just said they have one reads as the
    product not listening. Everything asserted here is read out of the spec, so
    the product cannot start composing sentences about facts the engine did not
    name.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = default_spec()
        cls.result = diagnose(
            fixtures.REACHING["ACTION__SUBSTANTIATE_CLAIMED_FACTS"], cls.spec
        )

    def test_the_verdict_is_blocked_and_the_prefix_agrees(self):
        prefix, decl = self.spec.outcome_prefix(self.result.outcome)
        self.assertEqual(prefix, "ACTION__")
        self.assertEqual(self.result.verdict, decl["verdict"])
        self.assertEqual(self.result.verdict, "BLOCKED")
        self.assertTrue(decl["terminal"])

    def test_it_stops_at_the_gates_own_node(self):
        gate = self.spec.gates["G0_EVAL_SET"]
        self.assertEqual(self.result.node, gate["node"])
        self.assertEqual(self.result.path[-1].id, gate["node"])
        self.assertEqual(self.result.path[-1].kind, "node")

    def test_what_it_says_is_the_gates_own_words(self):
        """And the words are a next step, not the cheaper remedy said louder.

        The two substrings are the difference this outcome exists to carry: it
        names the fact, and it says what would settle it. The wrong sentence
        here - the one silently failing the gate would have produced - is
        G0's own `on_fail.recipe`, "30-50 real inputs sampled from actual
        traffic", which tells somebody who has just said they have an eval set
        to go and build one.
        """
        expected = self.spec.gates["G0_EVAL_SET"]["on_unsubstantiated"]["note"]
        self.assertEqual(self.result.say, expected)
        self.assertIn("eval_size_n", self.result.say)
        self.assertIn("count it myself", self.result.say.lower())
        self.assertNotEqual(self.result.say, self.spec.gates["G0_EVAL_SET"]["on_fail"]["recipe"])

    def test_every_gate_can_say_it_in_its_own_words(self):
        """A gate with no wording of its own would fall back to silence."""
        for gate_id, gate in sorted(self.spec.gates.items()):
            with self.subTest(gate=gate_id):
                note = (gate.get("on_unsubstantiated") or {}).get("note")
                self.assertTrue(
                    note and note.strip(),
                    f"{gate_id} has no on_unsubstantiated note, so a run refused "
                    "there is refused without a next step - which is the one "
                    "thing this outcome exists not to do",
                )

    def test_the_substantiation_line_is_the_one_the_spec_holds_for_that_source(self):
        row = self.result.unsubstantiated[0]
        self.assertEqual(row["fact"], "eval_size_n")
        self.assertEqual(row["declared_source"], "inspect")
        self.assertEqual(
            row["substantiation"],
            self.spec.origin_policy["substantiation"]["inspect"],
        )

    def test_the_ledger_shows_the_gate_did_not_pass_and_why(self):
        entry = self.result.gate_ledger["G0_EVAL_SET"]
        self.assertEqual(entry["status"], "FAILED")
        self.assertEqual(entry["unsubstantiated"], ["eval_size_n"])
        self.assertEqual(entry["clause"], "eval_size_n >= 30")
        self.assertNotIn(
            "G0_EVAL_SET",
            gates_passed_under(self.result.path, "llm_weights", self.spec),
        )

    def test_it_is_recorded_in_rejected_with_the_origin_that_caused_it(self):
        reasons = [r for r in self.result.rejected if "G0_EVAL_SET" in r.get("reason", "")]
        self.assertTrue(reasons)
        self.assertIn("eval_size_n", reasons[0]["evidence"])
        self.assertIn(ASSERTED, reasons[0]["evidence"])


class NoDefaultOpensAGateTest(unittest.TestCase):
    """RC9. Belt and braces on the claim every default in the ledger makes.

    DEFAULTED is admissible nowhere, so this cannot fail through the origin rule.
    It can fail through somebody editing a default from false to true or from 0
    to 100 - which is a one-character change that would hand every empty intake a
    passed gate, and nothing else in the suite is looking at it.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = default_spec()

    def test_the_empty_fact_set_passes_no_gate(self):
        result = diagnose({}, self.spec)
        self.assertNotEqual(result.verdict, "TRAIN")
        for klass in sorted(self.spec.method_classes):
            self.assertEqual(gates_passed_under(result.path, klass, self.spec), set())

    def test_no_default_is_admissible_anywhere(self):
        for source, allowed in self.spec.admissible_origins.items():
            with self.subTest(source=source):
                self.assertNotIn(DEFAULTED, allowed)

    def test_a_caller_may_not_claim_the_engines_own_origin(self):
        with self.assertRaises(FactError) as caught:
            diagnose({"eval_size_n": Fact(100, DEFAULTED)}, self.spec)
        self.assertIn("only the", str(caught.exception))

    def test_an_origin_the_vocabulary_does_not_hold_is_refused(self):
        with self.assertRaises(FactError):
            Fact(100, "TRUSTWORTHY")


class TheLedgerIsFullyTaggedTest(unittest.TestCase):
    """Every fact carries a source, and the policy has a row for every source.

    The brief for this pass said seventeen of the ledger's facts were tagged and
    every hardware fact was untagged. THAT WAS ALREADY FIXED before this pass
    started - all sixty-eight carry a `source:`, hardware included - and the
    finding is recorded here as a test rather than as a note in a commit message,
    because "somebody already did it" is exactly the state that silently reverts.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = default_spec()

    def test_every_declared_fact_carries_a_source(self):
        untagged = sorted(n for n, d in self.spec.facts.items() if not d.get("source"))
        self.assertEqual(
            untagged,
            [],
            f"{untagged} carry no `source:`. A fact with no source has no "
            "admissible origin set, so a gate reading it can never open, and the "
            "interface has nothing to put in its provenance badge",
        )

    def test_the_hardware_facts_are_tagged_as_inspected(self):
        """Named separately because they are the class the product claims to read."""
        for name in ("accelerator", "vram_gb", "ram_gb", "disk_free_gb"):
            with self.subTest(fact=name):
                self.assertEqual(self.spec.facts[name]["source"], "inspect")
                self.assertEqual(self.spec.facts[name].get("fallback"), "ask")

    def test_every_source_the_ledger_uses_has_a_policy_row_and_a_remedy(self):
        used = {d["source"] for d in self.spec.facts.values()}
        self.assertTrue(used)
        for source in sorted(used):
            with self.subTest(source=source):
                self.assertIn(source, self.spec.admissible_origins)
                self.assertIn(source, self.spec.origin_policy["substantiation"])

    def test_the_vocabulary_in_the_file_and_in_the_module_are_the_same_four(self):
        self.assertEqual(set(self.spec.origin_policy["vocabulary"]), set(ORIGINS))

    def test_every_fact_comes_back_with_an_origin(self):
        """Invariant 3 needs one per number, not one per hardware number."""
        result = diagnose(fixtures.MINTING["TRAIN__LORA_SFT"], self.spec)
        self.assertEqual(set(result.fact_origins), set(self.spec.facts))
        for name, origin in result.fact_origins.items():
            with self.subTest(fact=name):
                self.assertIn(origin, ORIGINS)

    def test_a_cost_is_measured_only_when_the_hardware_was(self):
        """A number the user typed into a box is not a number read off the machine.

        `fallback: ask` on those four lines makes a stated number a legitimate
        INPUT. It does not make it a measurement, and the previous reading -
        "was the key present" - called them the same thing.
        """
        facts = fixtures.MINTING["TRAIN__LORA_SFT"]
        self.assertEqual(diagnose(facts, self.spec).cost_provenance, "MEASURED")

        typed_in = reattributed(facts, ["vram_gb"], STATED)
        self.assertEqual(diagnose(typed_in, self.spec).cost_provenance, "UNKNOWN")

        missing = dict(facts)
        del missing["vram_gb"]
        self.assertEqual(diagnose(missing, self.spec).cost_provenance, "UNKNOWN")


class MutatingTheOriginsOfTheRealTrainingStoriesTest(unittest.TestCase):
    """The sweep, and it mutates the nine real TRAIN fixtures rather than nothing.

    A previous fuzz of this engine drew 200,000 random fact sets and reached ZERO
    TRAIN verdicts, which measured crash-resistance and tested the gates the way
    an empty room is quiet. Random fact sets never get down the training path. So
    every draw here starts from a fact set that DOES mint, changes no value, and
    moves origins only - the one neighbourhood where this property can be broken.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = default_spec()
        cls.read = sorted(every_fact_a_gate_reads(cls.spec))
        cls.seeds = sorted(fixtures.MINTING.items())

    def test_the_sweep_is_not_running_over_nothing(self):
        self.assertTrue(self.seeds, "no training fixtures to mutate")
        self.assertTrue(self.read, "no gate-read facts to move the origins of")

    def test_no_origin_perturbation_of_a_training_story_raises(self):
        rng = random.Random(SEED)
        for index in range(DRAWS):
            outcome, facts = self.seeds[index % len(self.seeds)]
            moved = dict(facts)
            for name in rng.sample(self.read, rng.randint(1, len(self.read))):
                if name in moved:
                    moved[name] = Fact(bare(moved[name]), rng.choice(ORIGINS[:3]))
            try:
                diagnose(moved, self.spec)
            except Exception as exc:  # noqa: BLE001 - the assertion IS "no exception"
                self.fail(
                    f"diagnose() raised {type(exc).__name__}: {exc}\n"
                    f"seed={SEED} draw #{index} from {outcome}, origins: "
                    + ", ".join(
                        f"{n}={moved[n].origin}"
                        for n in self.read
                        if isinstance(moved.get(n), Fact)
                    )
                )

    def test_a_training_verdict_never_survives_its_claims_being_named_as_claims(self):
        """The differential property, over the whole sweep.

        For every draw that still trains: re-attribute every gate-read fact
        ASSERTED and it must stop training. That is the promise stated without
        reference to which gate or which fact, so it holds for a fact somebody
        adds to a gate row next year.

        The census at the end is the non-vacuity guard, and it is the specific
        one this repository has been bitten by twice: a sweep in which nothing
        minted would satisfy every assertion in the loop and prove nothing.
        """
        rng = random.Random(SEED)
        minted = refused = other = 0
        for index in range(DRAWS):
            outcome, facts = self.seeds[index % len(self.seeds)]
            moved = dict(facts)
            for name in rng.sample(self.read, rng.randint(1, len(self.read))):
                if name in moved:
                    moved[name] = Fact(bare(moved[name]), rng.choice(ORIGINS[:3]))
            result = diagnose(moved, self.spec)
            if result.outcome.startswith("TRAIN__"):
                minted += 1
                claimed = diagnose(reattributed(moved, self.read, ASSERTED), self.spec)
                self.assertFalse(
                    claimed.outcome.startswith("TRAIN__"),
                    f"seed={SEED} draw #{index} from {outcome} still minted "
                    f"{claimed.outcome} with every gate-read fact an assertion",
                )
            elif result.outcome == self.spec.unsubstantiated_outcome:
                refused += 1
                self.assertTrue(result.unsubstantiated)
            else:
                other += 1

        self.assertGreater(
            minted,
            0,
            f"{DRAWS} draws and not one training verdict among them, so the "
            "assertion inside the loop never ran. This is the vacuous pass this "
            "repository has already been bitten by twice: gated the way an empty "
            f"room is quiet. Census - minted {minted}, refused {refused}, other "
            f"{other}",
        )
        self.assertGreater(
            refused,
            0,
            f"{DRAWS} draws and not one refusal, so the origin rule never fired. "
            f"Census - minted {minted}, refused {refused}, other {other}",
        )


if __name__ == "__main__":
    unittest.main()
