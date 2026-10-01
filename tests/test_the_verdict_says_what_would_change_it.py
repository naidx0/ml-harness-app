"""Two fields the card was drawing as named absences, and the derivation behind them.

`frontend/src/components/DiagnosisCard.tsx` reported both, in the product, in
prose a user could read:

> Page 23.4 specifies three controls that start the alternative work. The engine
> sends no alternatives with a verdict - `run_diagnosis` returns `say` and
> nothing that names a next action - so none are drawn here rather than
> invented.

> The diagnosis contract requires `revisit_if` alongside every verdict - what
> would change this answer. It is not on the wire yet.

The card was right on both counts and right to draw the absence rather than
three plausible buttons and a plausible sentence. `contract.diagnosis` in
`docs/diagnosis_engine.yaml` lists `revisit_if` beside `exit_criterion` and
`estimated_cost`, and `S9_MINT_TRAIN_VERDICT.requires_in_diagnosis` says
"revisit_if set - what would change this answer". The engine did not send it.

## What this file checks, and why it is mostly about derivation

The easy version of this feature is a table: outcome id on the left, a nice
sentence and a button on the right, fifty-five rows. It passes on the day it is
written and rots invisibly, because nothing makes it change when the graph
changes. So the tests below are less about the two fields existing and more
about where every character of them came from:

* every alternative's sentence appears **verbatim in the spec file**, so nobody
  can quietly start writing product prose in Python;
* every alternative's tool is a **registered tool**, or `None` - a remedy this
  harness cannot start says so instead of drawing a dead button;
* every revisit line names a **declared fact** and the value this run held, or
  says the value is not known;
* a gate-blocked run derives its revisit condition from the **gate row that was
  evaluated**, not from a node condition that does not exist;
* and none of it can reach the verdict: a `run_diagnosis` payload is identical
  in `outcome`, `verdict` and `gate_ledger` whether these fields compute or not.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from app import diagnosis
from app.tools import REGISTRY, next_moves

import diagnosis_fixtures
import support


SPEC_TEXT = Path(diagnosis.SPEC_PATH).read_text(encoding="utf-8")


def _normalised(text: str) -> str:
    return " ".join(str(text).split())


class EveryOutcomeSendsBoth(unittest.TestCase):
    """Across every fixture in the suite, not across one happy example."""

    def setUp(self) -> None:
        support.sandbox(self)
        self.spec = diagnosis.default_spec()

    def _every_result(self):
        for label, case in diagnosis_fixtures.SPREAD.items():
            yield label, diagnosis.diagnose(case["facts"])

    def test_nothing_raises_and_both_fields_are_always_present(self):
        seen = 0
        for label, result in self._every_result():
            with self.subTest(label):
                moves = next_moves.next_moves(result, spec=self.spec)
                self.assertIsInstance(moves["revisit_if"], list)
                self.assertIsInstance(moves["alternatives"], list)
                self.assertLessEqual(
                    len(moves["alternatives"]),
                    next_moves.HOW_MANY,
                    "graphite 23.4: three, because a fourth would be padding",
                )
                seen += 1
        self.assertGreater(seen, 20, "the fixture spread should not have shrunk")

    def test_every_alternative_sentence_is_the_spec_word_for_word(self):
        """Nothing here writes product prose. It reads the engine's.

        The card was bitten by exactly this: a lead-in that turned the engine's
        sentence into a claim it did not make, rendering "Ask me again if This
        run was not refused". The fix there was to stop putting words in the
        engine's mouth; the fix here is to make that structural.
        """
        checked = 0
        for label, result in self._every_result():
            for row in next_moves.alternatives(result, spec=self.spec)["alternatives"]:
                if row["move"] == next_moves.MOVES[2]:
                    # The third move is a sentence about a reading, built from
                    # the tool's own registered verb and the fact's own name.
                    # Both halves are quoted below rather than exempted.
                    self.assertIn(row["fact"], self.spec.facts)
                    self.assertTrue(row["verb"])
                    self.assertIn(_normalised(row["verb"]).lower(), row["text"].lower())
                    continue
                with self.subTest(label, source=row["from"]):
                    self.assertIn(
                        _normalised(row["text"])[:60],
                        _normalised(SPEC_TEXT),
                        f"{row['from']} carries a sentence that is not in "
                        f"{diagnosis.SPEC_PATH.name}",
                    )
                    checked += 1
        self.assertGreater(checked, 10)

    def test_every_named_tool_is_a_registered_tool(self):
        for label, result in self._every_result():
            for row in next_moves.alternatives(result, spec=self.spec)["alternatives"]:
                with self.subTest(label, tool=row["tool"]):
                    if row["tool"] is None:
                        self.assertFalse(row["starts_now"])
                        self.assertTrue(
                            row["why"],
                            "a remedy with no tool must say why there is no button",
                        )
                    else:
                        self.assertIn(row["tool"], REGISTRY)
                        self.assertTrue(row["starts_now"])
                        self.assertTrue(row["verb"])

    def test_every_revisit_line_names_a_declared_fact(self):
        for label, result in self._every_result():
            source = next_moves.revisit_if(result, spec=self.spec)["revisit_if_source"]
            for row in source["facts"]:
                with self.subTest(label, fact=row["fact"]):
                    self.assertIn(row["fact"], self.spec.facts)
                    if row["value_known"]:
                        # `_show`, not `str`: the condition is read by a person
                        # and by a model, and `None` is Python's word for the
                        # ledger's `null`. Asserting through the same renderer
                        # the payload used is what keeps the two in step.
                        self.assertEqual(
                            f"{row['fact']} changes from {next_moves._show(row['now'])}",
                            row["condition"],
                        )
                    else:
                        self.assertEqual(f"{row['fact']} changes", row["condition"])


class AGateBlockedRunSaysWhatWouldOpenIt(unittest.TestCase):
    """The runs that needed this most were the ones the first cut left empty.

    A gate is a predicate too - it lives in `passes_when` rather than in
    `condition:` - so a terminal node that IS a gate node has no compiled
    condition and derived nothing. Every `BLOCKED__` answer a failed gate
    produced therefore came back with an empty revisit list, which is the exact
    set of answers a person most needs a route out of.
    """

    def setUp(self) -> None:
        support.sandbox(self)

    def test_no_eval_set_is_told_which_number_opens_the_gate(self):
        result = REGISTRY.call(
            "run_diagnosis",
            {
                "facts": {
                    "goal_text": "route support tickets",
                    "modality": "text",
                    "target_score": 0.9,
                }
            },
            actor="user",
        )
        self.assertEqual("BLOCKED__BUILD_EVAL_SET", result["outcome"])
        self.assertEqual(["eval_size_n changes from 0"], result["revisit_if"])
        self.assertEqual("G0_EVAL_SET", result["revisit_if_source"]["gate"])
        self.assertEqual(
            "eval_size_n >= 30",
            result["revisit_if_source"]["condition"],
            "the condition on the wire must be the gate row that was evaluated",
        )

        starts = [a for a in result["alternatives"] if a["starts_now"]]
        self.assertTrue(starts, "a blocked gate must offer the tool that opens it")
        self.assertEqual("measure_eval_set", starts[0]["tool"])
        self.assertEqual(next_moves.MOVES[0], starts[0]["move"])

    def test_a_declared_revisit_line_is_passed_through_first_and_verbatim(self):
        """Three nodes carry a literal `revisit_if:` today. Theirs wins.

        A hand-written condition is more specific than any derivation, so it is
        not merged into the derived lines or reworded around them - it is the
        head of the list.
        """
        spec = diagnosis.default_spec()
        declared = {
            node_id: node["revisit_if"]
            for node_id, node in spec.node_index.items()
            if node.get("revisit_if")
        }
        self.assertTrue(declared, "the spec should still declare some revisit_if lines")

        node_id, lines = sorted(declared.items())[0]
        fake = diagnosis.Diagnosis(
            outcome="NO_TRAIN__CONTEXT_STUFFING",
            verdict="NO_TRAIN",
            path=[],
            gate_ledger={},
            proposed_method="UNSET",
            rejected=[],
            struck_methods=set(),
            constraints=set(),
            helper_answers=[],
            size_row=None,
            route=None,
            hardware_permits=None,
            hardware_reference=None,
            cost_provenance="UNKNOWN",
            node=node_id,
        )
        moves = next_moves.revisit_if(fake, spec=spec)
        self.assertEqual(list(lines), moves["revisit_if"][: len(lines)])
        self.assertEqual(len(lines), moves["revisit_if_source"]["declared"])


class TheSpecSaysHowAndTheCodeDoesThat(unittest.TestCase):
    """The two new contract blocks are not decoration.

    `contract.revisit_if_derivation` and `contract.alternatives_derivation`
    describe where every character of these fields comes from. A description
    nothing checks is a description that drifts, so the file they name has to be
    the file that does it, and the three moves they list have to be the three
    the code emits.
    """

    def setUp(self) -> None:
        self.spec = diagnosis.default_spec()

    def test_both_blocks_name_the_module_that_implements_them(self):
        for block in ("revisit_if_derivation", "alternatives_derivation"):
            with self.subTest(block):
                named = self.spec.contract[block]["implemented_by"]
                self.assertEqual("app/tools/next_moves.py", named)
                self.assertTrue(
                    (Path(diagnosis.SPEC_PATH).parents[1] / named).is_file(),
                    f"{block} names a file that does not exist",
                )

    def test_the_three_moves_the_spec_lists_are_the_three_the_code_emits(self):
        listed = self.spec.contract["alternatives_derivation"][
            "where_each_sentence_comes_from"
        ]
        self.assertEqual(set(next_moves.MOVES), set(listed))
        self.assertEqual(len(next_moves.MOVES), next_moves.HOW_MANY)

    def test_the_spec_says_the_gates_do_not_decide_feasibility(self):
        """The sentence the whole change turns on, kept where the engine is defined."""
        block = self.spec.contract["what_the_gates_decide"]
        self.assertIn("TRAIN__", block["they_decide"])
        self.assertIn("measures=()", block["they_decide"])
        self.assertIn("app/tools/feasible.py", block["they_do_not_decide"])
        for name in ("can_this_machine_train", "where_to_train"):
            self.assertEqual((), REGISTRY.get(name).measures, name)


class TheseFieldsCannotReachTheVerdict(unittest.TestCase):
    """A presentation field may never be able to change a decision."""

    def setUp(self) -> None:
        support.sandbox(self)

    def test_run_diagnosis_still_writes_and_measures_nothing(self):
        spec = REGISTRY.get("run_diagnosis")
        self.assertEqual((), spec.writes)
        self.assertEqual((), spec.measures)

    def test_a_derivation_that_raises_costs_the_two_fields_and_not_the_verdict(self):
        """The verdict is the product. These two are how it is read.

        Patched rather than argued: if `next_moves` throws, the payload must
        still carry the outcome, the verdict and the gate ledger, and must say
        that the two fields failed rather than sending an empty list that looks
        like a considered answer.
        """
        facts = {"goal_text": "route support tickets", "modality": "text"}
        healthy = REGISTRY.call("run_diagnosis", {"facts": dict(facts)}, actor="user")

        original = next_moves.next_moves

        def explode(*args, **kwargs):
            raise RuntimeError("derivation blew up")

        next_moves.next_moves = explode
        try:
            broken = REGISTRY.call("run_diagnosis", {"facts": dict(facts)}, actor="user")
        finally:
            next_moves.next_moves = original

        self.assertEqual(healthy["outcome"], broken["outcome"])
        self.assertEqual(healthy["verdict"], broken["verdict"])
        self.assertEqual(healthy["gate_ledger"], broken["gate_ledger"])
        self.assertEqual([], broken["revisit_if"])
        self.assertEqual([], broken["alternatives"])
        self.assertIn("derivation blew up", broken["next_moves_failed"])
        self.assertTrue(healthy["revisit_if"])

    def test_an_alternative_is_a_suggestion_and_never_an_outcome(self):
        """Derived from the spec, so a training outcome added later is covered."""
        spec = diagnosis.default_spec()
        outcomes = spec.declared_outcomes()
        self.assertGreater(len(outcomes), 40)

        for label, case in diagnosis_fixtures.SPREAD.items():
            result = diagnosis.diagnose(case["facts"])
            for row in next_moves.alternatives(result, spec=spec)["alternatives"]:
                with self.subTest(label, source=row["from"]):
                    self.assertNotIn(row["text"], outcomes)
                    self.assertNotIn(row["tool"], outcomes)


if __name__ == "__main__":
    unittest.main()
