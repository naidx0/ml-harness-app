"""A question about memory is answered from memory. It is still not a licence to train.

## What was wrong, in Max's own transcript

Max ran the product against his own insurance book - roughly a thousand support
tickets, tracked to clients and reasons, cloud models forbidden by compliance -
and asked it seven questions. It answered all seven with
`BLOCKED__DEFINE_SUCCESS_FIRST`.

Only one of the seven is a question the five gates are about:

    1. Can I train on this machine at all?      measured VRAM + model geometry
    2. Local, rented VM, or data centre?        the above + a constraint
    3. Is it worth training?                    THE FIVE GATES. answered right.
    4. What would it cost?                      the above + timings
    5. What is the best data - have or get?     the data, profiled
    6. Training environment - build and deploy? the sandbox, which exists
    7. Which model should I use?                hardware + task + catalogue

The gates exist to stop the product RECOMMENDING TRAINING without evidence.
They had ended up stopping it answering whether an 8 GB card holds a 7B model,
which needs no eval set, no baseline, no prompt work, no retrieval and no model
swap - it needs a measurement the harness had already taken. That is the gate
scoped to the wrong verb, and refusing a question you can answer is not honesty.

## The line this file exists to hold

Separating CAN from SHOULD is exactly the move an adversary would make to get a
training recommendation without the evidence, and `AGENTS.md` invariant 4 names
it: *"do not rename a training outcome to something that is not TRAIN__ so it
stops being checked - that removes the guarantee while keeping the claim, and it
is forbidden."* So this file's job is not to prove the new tools work. It is to
prove they cannot become a second door to the answer the gates guard.

Six walls, each checked here, and none of them a promise about anyone's care:

1. The feasibility tools answer with an EMPTY LEDGER - the state Max was in.
2. They emit no word the diagnosis engine owns. **The forbidden vocabulary is
   derived from `docs/diagnosis_engine.yaml`**, through
   `Spec.declared_outcomes()`, so a training outcome added next year is covered
   on the day it is added and not on the day somebody remembers this file.
3. The scanner that checks 2 is itself checked, against a payload built to fail
   it. A scanner that cannot fail is decoration.
4. They declare `measures=()`, so the instrument they are handed can stamp
   nothing. A fact that cannot be stamped cannot open a gate.
5. They declare `writes=()` and leave the claim ledger byte-identical, so no
   number they compute can be read back as evidence by anything else.
6. Calling them, in any order, any number of times, does not move the diagnosis
   by one character. The `BLOCKED__` answer Max got for question 3 is still the
   answer for question 3 afterwards, which is the correct answer to it.
"""

from __future__ import annotations

import unittest
from typing import Any, Iterator

from app import diagnosis, feasibility
from app.tools import REGISTRY, evidence

import support


#: Max's machine, stated rather than detected, so this file asserts the same
#: numbers on any machine that runs it. The real one measured 8.0 GB of VRAM
#: and 15.9 GB of RAM off an RTX 2060 SUPER through `nvidia-smi`.
MAX_VRAM_GB = 8.0

#: Two models that ship with this repository, so their geometry is read from a
#: real `config.json` rather than assumed. `support.sandbox()` seeds the
#: sandbox's `MODEL_CONFIG_ROOT` with them.
BIG = "Qwen/Qwen3-8B"
SMALL = "Qwen/Qwen3-4B"

FEASIBILITY_TOOLS = ("can_this_machine_train", "where_to_train")


def _strings(value: Any) -> Iterator[str]:
    """Every string anywhere in a payload, however deeply nested.

    A scan of the top-level keys would miss a training outcome quoted inside a
    sentence, which is precisely how a leak would arrive - not as a field called
    `outcome` but as prose that reads like one.
    """
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _strings(item)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            yield from _strings(item)


class ForbiddenVocabulary:
    """The words a feasibility answer may not say, read out of the spec.

    `TRAIN__LORA_SFT` is not written down here and neither are the other eight.
    They come from `Spec.declared_outcomes()`, which reads every node's
    `outcome:`, every gate's `on_fail.outcome`, every `emits` list and the
    unsubstantiated outcome - four places, because the file states an outcome in
    four places and a list that reads only the first goes stale silently.
    """

    def __init__(self, spec: diagnosis.Spec) -> None:
        self.spec = spec
        outcomes = spec.declared_outcomes()
        self.train_outcomes = frozenset(
            o for o in outcomes if o.startswith("TRAIN__")
        )
        self.every_outcome = frozenset(outcomes)
        self.gate_ids = frozenset(spec.required_gates)
        self.verdicts = frozenset(
            decl["verdict"]
            for decl in spec.contract["outcome_prefixes"].values()
            if decl.get("verdict")
        )

    def offences(self, payload: Any) -> list[str]:
        found: list[str] = []
        for text in _strings(payload):
            for outcome in self.every_outcome:
                if outcome in text:
                    found.append(f"outcome {outcome!r} in {text[:80]!r}")
            for gate in self.gate_ids:
                if gate in text:
                    found.append(f"gate id {gate!r} in {text[:80]!r}")
            if text in self.verdicts:
                found.append(f"the bare verdict word {text!r}")
        return found


class TheGateWasScopedToTheWrongVerb(unittest.TestCase):
    """Wall 1. The question Max asked seven times, answered from an empty ledger."""

    def setUp(self) -> None:
        support.sandbox(self)

    def test_an_empty_ledger_still_gets_a_yes_or_a_no(self):
        """No eval set, no baseline, no target score, no facts at all - and an answer.

        This is Max's exact state and it is the whole defect. The diagnosis is
        right to be blocked here; there is nothing to diagnose. The memory
        question has nothing to do with any of that.
        """
        blocked = REGISTRY.call(
            "run_diagnosis",
            {"facts": {"goal_text": "classify support tickets", "modality": "text"}},
            actor="model",
        )
        self.assertEqual(blocked["verdict"], "BLOCKED")
        self.assertEqual(blocked["outcome"], "BLOCKED__DEFINE_SUCCESS_FIRST")

        answer = REGISTRY.call(
            "can_this_machine_train",
            {"repo_id": SMALL, "method": "qlora", "seq_len": 2048, "vram_gb": MAX_VRAM_GB},
            actor="model",
        )
        self.assertTrue(answer["ok"])
        self.assertIn(answer["answer"], feasibility.ANSWERS)
        self.assertNotEqual(
            answer["answer"],
            "UNKNOWN",
            "the geometry ships with this repository, so there is nothing here "
            "the harness has not read and UNKNOWN would be a refusal it cannot "
            "justify",
        )

    def test_the_answer_carries_the_arithmetic_and_every_term_says_where_it_came_from(self):
        answer = REGISTRY.call(
            "can_this_machine_train",
            {"repo_id": BIG, "method": "qlora", "seq_len": 2048, "vram_gb": MAX_VRAM_GB},
            actor="model",
        )
        terms = answer["arithmetic"]
        self.assertGreaterEqual(len(terms), 7)
        for term in terms:
            self.assertTrue(term["source"], f"{term['term']} has no source")
            self.assertIsNotNone(term["gb"], f"{term['term']} has no figure")

        summed = round(sum(float(t["gb"]) for t in terms), 2)
        self.assertAlmostEqual(
            summed,
            float(answer["needed_gb"]),
            places=1,
            msg=(
                "the terms shown must add up to the figure the answer is "
                "computed from. A displayed sum that does not reach the "
                "displayed total is the shape of a number nobody checked - and "
                "it was live: the model ranker leaves the logits buffer out of "
                "the comparison while showing it in the total."
            ),
        )

    def test_the_eight_b_has_no_length_at_all(self):
        """THE STRONGER REFUSAL, kept as its own case so the change above is
        not read as the 8B quietly dropping out of the file. Its base weights
        exceed the card before an example is loaded, so there is no length to
        offer and none is invented."""
        answer = REGISTRY.call(
            "can_this_machine_train",
            {"repo_id": BIG, "method": "qlora", "seq_len": 2048, "vram_gb": MAX_VRAM_GB},
            actor="model",
        )
        self.assertEqual(answer["answer"], "NO")
        self.assertIsNone(answer["longest_example_that_fits"])

    def test_a_no_carries_the_yes_that_would_have_worked(self):
        """A no that leaves the person nowhere is the defect; a no with a
        length is an answer.

        THE MODEL CHANGED ON 2026-09-10 AND THE PROPERTY DID NOT. This asked
        the 8B, which missed by half a gigabyte and fitted at a shorter length.
        Under the measured terms the 8B's weights alone exceed the card - it
        has no fitting length at any sequence, and `record_that_this_card_refuses`
        says so in `no_length_fits` rather than omitting a field. That is a
        DIFFERENT and stronger refusal, and it is asserted in
        `test_the_eight_b_has_no_length_at_all` below.

        The 4B still has a boundary, so it is the model that can carry this
        property: NO at 2,048 (9.22 GiB), and a shorter example - 1,024, which
        the answer names - that really does fit.
        """
        answer = REGISTRY.call(
            "can_this_machine_train",
            #: 2,048 SINCE THE WORKSPACE HALVED. At 1,024 the 4B is 7.14 GiB
            #: and answers YES, so it can no longer carry a case about a NO.
            #: The boundary is between 1,024 and 1,280 now.
            {"repo_id": SMALL, "method": "qlora", "seq_len": 2048, "vram_gb": MAX_VRAM_GB},
            actor="model",
        )
        self.assertEqual(answer["answer"], "NO")
        longest = answer["longest_example_that_fits"]
        self.assertIsInstance(longest, int)
        self.assertLessEqual(longest, 1024)

        # And the length it names really does fit, computed the same way.
        at_that_length = REGISTRY.call(
            "can_this_machine_train",
            {"repo_id": SMALL, "method": "qlora", "seq_len": longest, "vram_gb": MAX_VRAM_GB},
            actor="model",
        )
        self.assertEqual(at_that_length["answer"], "YES")

    def test_an_unread_model_is_unknown_and_names_the_tool_that_reads_it(self):
        answer = REGISTRY.call(
            "can_this_machine_train",
            {"repo_id": "not-a-real-org/never-fetched", "vram_gb": MAX_VRAM_GB},
            actor="model",
        )
        self.assertEqual(answer["answer"], "UNKNOWN")
        self.assertEqual(answer["missing"], "geometry")
        self.assertEqual(answer["next_step"]["tool"], "read_model_config")
        self.assertIn(answer["next_step"]["tool"], REGISTRY)


class ItSaysNoWordTheEngineOwns(unittest.TestCase):
    """Walls 2 and 3. The vocabulary is derived, and the derivation is exercised."""

    def setUp(self) -> None:
        support.sandbox(self)
        self.spec = diagnosis.default_spec()
        self.forbidden = ForbiddenVocabulary(self.spec)

    def test_the_spec_really_does_declare_training_outcomes(self):
        """The guard against a vacuous pass.

        Every assertion below is "this word does not appear". If the derivation
        produced an empty set they would all pass while checking nothing, which
        is the failure mode a hand-written list at least makes visible.
        """
        self.assertGreaterEqual(len(self.forbidden.train_outcomes), 9)
        self.assertIn("TRAIN__LORA_SFT", self.forbidden.train_outcomes)
        self.assertGreater(len(self.forbidden.every_outcome), 40)

    def test_the_scanner_catches_a_payload_that_leaks_one(self):
        """Wall 3. A check that cannot fail is not a check."""
        planted = {
            "answer": "YES",
            "notes": ["this run would reach TRAIN__LORA_SFT once the card is bigger"],
        }
        self.assertTrue(self.forbidden.offences(planted))

        planted_gate = {"answer": "YES", "gates": {"G0_EVAL_SET": "not needed"}}
        self.assertTrue(self.forbidden.offences(planted_gate))

    def test_no_feasibility_answer_says_an_outcome_a_gate_or_a_verdict(self):
        payloads = [
            REGISTRY.call(
                "can_this_machine_train",
                {"repo_id": repo, "method": method, "vram_gb": MAX_VRAM_GB},
                actor="model",
            )
            for repo in (BIG, SMALL)
            for method in ("qlora", "lora", "full")
        ]
        payloads.append(
            REGISTRY.call(
                "where_to_train", {"repo_id": BIG, "privacy": "regulated"}, actor="user"
            )
        )
        payloads.append(
            REGISTRY.call("where_to_train", {"repo_id": SMALL}, actor="model")
        )
        for payload in payloads:
            with self.subTest(payload.get("repo_id"), method=payload.get("method")):
                self.assertEqual([], self.forbidden.offences(payload))

    def test_the_word_verdict_is_not_a_key_of_a_feasibility_answer(self):
        """`verdict` is the diagnosis engine's word and it stays that way.

        The fit words live under `fit` instead. This is not fussiness about
        naming: a payload with a `verdict` key is one careless renderer away
        from being drawn on the do-not-train card as the engine's answer.
        """
        answer = REGISTRY.call(
            "can_this_machine_train", {"repo_id": SMALL, "vram_gb": MAX_VRAM_GB}, actor="model"
        )
        self.assertNotIn("verdict", answer)
        self.assertIn("fit", answer)
        self.assertIn(answer["fit"], feasibility.VERDICTS)


class ItCannotOpenAGate(unittest.TestCase):
    """Walls 4, 5 and 6. Structure, not intention."""

    def setUp(self) -> None:
        support.sandbox(self)
        self.threads = support.conversations(1)
        self.thread_id = self.threads[0]["id"]

    def test_neither_tool_can_stamp_anything(self):
        """`measures=()` is the wall. A fact nothing stamped cannot open a gate."""
        for name in FEASIBILITY_TOOLS:
            spec = REGISTRY.get(name)
            self.assertIsNotNone(spec, f"{name} is not registered")
            self.assertEqual((), spec.measures, f"{name} claims to measure something")
            self.assertEqual((), spec.writes, f"{name} claims to write something")

    def test_neither_tool_offers_a_slot_for_a_decision(self):
        """Wall 2 of the registry, checked at this surface rather than assumed."""
        from app.tools.registry import RESERVED_ARGUMENTS

        for name in FEASIBILITY_TOOLS:
            properties = set((REGISTRY.get(name).schema.get("properties") or {}))
            self.assertEqual(
                set(),
                {p for p in properties if p.lower() in RESERVED_ARGUMENTS},
                f"{name} accepts an argument that names a decision or a provenance",
            )

    def test_calling_them_leaves_the_claim_ledger_untouched(self):
        before = evidence.ledger_view(self.thread_id)
        for _ in range(3):
            REGISTRY.call(
                "can_this_machine_train",
                {"repo_id": BIG, "vram_gb": MAX_VRAM_GB},
                actor="model",
                thread_id=self.thread_id,
            )
            REGISTRY.call(
                "where_to_train",
                {"repo_id": BIG, "privacy": "regulated", "can_rent_cloud": False},
                actor="user",
                thread_id=self.thread_id,
            )
        self.assertEqual(before, evidence.ledger_view(self.thread_id))

    def test_the_diagnosis_is_the_same_before_and_after(self):
        """Wall 6, and the one an adversary would actually try.

        The attack is not "make the tool emit TRAIN". It is to run the
        feasibility tools until something they leave behind opens a gate, then
        run the diagnosis. There is nothing left behind, so there is nothing to
        accumulate.
        """
        facts = {
            "goal_text": "classify support tickets",
            "modality": "text",
            "target_score": 0.9,
            "labeled_examples_n": 1000,
        }

        def diagnose() -> dict[str, Any]:
            return REGISTRY.call(
                "run_diagnosis", {"facts": dict(facts)}, actor="model", thread_id=self.thread_id
            )

        before = diagnose()
        for method in ("qlora", "lora", "full"):
            REGISTRY.call(
                "can_this_machine_train",
                {"repo_id": BIG, "method": method, "vram_gb": MAX_VRAM_GB},
                actor="model",
                thread_id=self.thread_id,
            )
            REGISTRY.call(
                "where_to_train",
                {"repo_id": BIG, "method": method},
                actor="model",
                thread_id=self.thread_id,
            )
        after = diagnose()

        self.assertEqual(before["outcome"], after["outcome"])
        self.assertEqual(before["verdict"], after["verdict"])
        self.assertEqual(before["gate_ledger"], after["gate_ledger"])
        self.assertEqual(before["proposed_method"], after["proposed_method"])
        self.assertEqual("BLOCKED", after["verdict"])

    def test_a_yes_on_the_hardware_does_not_pass_the_hardware_gate_question(self):
        """The specific rename this invariant forbids, tried from the other side.

        A model that gets YES from `can_this_machine_train` and then asserts the
        five gate facts still does not train, because an asserted fact whose
        ledger source is `inspect` cannot open a gate. The feasibility answer
        adds nothing to that attempt - which is the point of measuring it.
        """
        REGISTRY.call(
            "can_this_machine_train",
            {"repo_id": SMALL, "vram_gb": MAX_VRAM_GB},
            actor="model",
            thread_id=self.thread_id,
        )
        result = REGISTRY.call(
            "run_diagnosis",
            {
                "facts": {
                    "goal_text": "classify support tickets",
                    "modality": "text",
                    "target_score": 0.9,
                    "eval_size_n": 200,
                    "baseline_measured": True,
                    "baseline_score": 0.6,
                    "trivial_baseline_score": 0.3,
                    "prompt_iterations": 5,
                    "fewshot_tried": True,
                    "retrieval_tried": True,
                    "model_swap_tried": True,
                    "labeled_examples_n": 5000,
                }
            },
            actor="model",
            thread_id=self.thread_id,
        )
        self.assertNotEqual("TRAIN", result["verdict"])
        self.assertFalse(result["outcome"].startswith("TRAIN__"))


class MaxsFiveQuestions(unittest.TestCase):
    """The verification: his machine, his constraint, his questions.

    8 GB RTX 2060 SUPER, 15.9 GB RAM, roughly a thousand support tickets, cloud
    ruled out by compliance. The numbers below are stated rather than detected
    so the file asserts the same thing on any machine, and they are the numbers
    his machine actually reported.
    """

    def setUp(self) -> None:
        support.sandbox(self)
        self.threads = support.conversations(1)
        self.thread_id = self.threads[0]["id"]
        REGISTRY.call(
            "state_facts",
            {"facts": {"privacy": "regulated"}},
            actor="user",
            thread_id=self.thread_id,
        )

    def test_one_can_we_train_on_this_machine(self):
        answer = REGISTRY.call(
            "can_this_machine_train",
            #: 512 SINCE 2026-09-10, and the length is the whole change.
            #: The measured terms put the 4B at 7.38 GiB at 1,024 - inside 10%
            #: of an 8 GB card, which this tool calls SPILLS and answers NO,
            #: because a yes there is a yes that OOMs on the first long batch.
            #: At 512 it is 6.33 and the answer is an honest YES.
            {"repo_id": SMALL, "method": "qlora", "seq_len": 512, "vram_gb": MAX_VRAM_GB},
            actor="model",
            thread_id=self.thread_id,
        )
        self.assertEqual("YES", answer["answer"])
        self.assertEqual([], answer["gates_consulted"])

    def test_two_where_should_we_train(self):
        if not support.a_gpu_was_measured():
            # LOCAL is a claim about a card this machine can read. Without
            # one `where_to_train` answers UNKNOWN, which is the product
            # being right rather than the test being wrong.
            self.skipTest(support.NO_GPU_HERE)
        answer = REGISTRY.call(
            "where_to_train",
            {"repo_id": SMALL, "method": "qlora", "seq_len": 512},
            actor="model",
            thread_id=self.thread_id,
        )
        self.assertEqual("LOCAL", answer["answer"])
        self.assertFalse(answer["cloud_available"])
        self.assertEqual("STATED", answer["constraint_origins"]["privacy"])

    def test_three_is_it_worth_training_is_the_gated_one_and_stays_gated(self):
        result = REGISTRY.call(
            "run_diagnosis",
            {
                "facts": {
                    "goal_text": "route support tickets to the right team",
                    "modality": "text",
                    "labeled_examples_n": 1000,
                }
            },
            actor="model",
            thread_id=self.thread_id,
        )
        self.assertEqual("BLOCKED", result["verdict"])
        self.assertTrue(result["revisit_if"], "a blocked answer must say what would change it")

    def test_four_what_would_it_cost_says_unknown_where_it_is_unknown(self):
        answer = REGISTRY.call(
            "where_to_train",
            {"repo_id": BIG, "method": "qlora", "seq_len": 2048},
            actor="model",
            thread_id=self.thread_id,
        )
        cost = answer["cost"]
        self.assertEqual("UNKNOWN", cost["hours"]["provenance"])
        self.assertIsNone(cost["hours"]["value"])
        self.assertIsNone(cost["total_usd"])
        self.assertIn("1%", cost["hours"]["find_out_by"])

    def test_seven_which_model_still_ranks_and_the_gate_does_not_swallow_it(self):
        """`find_models` already worked. Nothing here may have taken that away.

        The ranking is not asserted - it reaches the network and this suite does
        not. What is asserted is that the tool is registered, reachable with no
        gate passed and no fact recorded, and unchanged in what it declares.
        """
        spec = REGISTRY.get("find_models")
        self.assertIsNotNone(spec)
        self.assertEqual((), spec.measures)
        self.assertEqual("never", spec.approval)
        self.assertEqual(
            "rank models by fit for this machine and this job", spec.control.verb
        )


if __name__ == "__main__":
    unittest.main()
