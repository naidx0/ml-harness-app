"""A KNOWN HOLE, PINNED SO IT CANNOT BE DISCOVERED A THIRD TIME.

`retriever_recall_at_k` is declared `source: inspect`, which in this ledger
means one thing: a tool ran and the engine watched it. `spec.admissible_for`
returns exactly `{"MEASURED"}` for it.

THAT RULE IS ENFORCED AT GATES AND NOWHERE ELSE. The policy table it comes from
is called `admissible_for_gates` in `docs/diagnosis_engine.yaml`, and the name
is accurate rather than incidental. `on_unsubstantiated`, the second defence, is
also a per-gate property - it is what turns an asserted `eval_size_n` into
`ACTION__SUBSTANTIATE_CLAIMED_FACTS` before anything routes on it.

AND NO GATE READS THIS FACT. G1_BASELINE_MEASURED mentions it once, in prose, in
a `retriever_weights` note about what a baseline means when the thing being
trained is a retriever. It is not in any `passes_when`. So both defences are
structurally unable to apply, and the three S3 nodes that read
`retriever_recall_at_k` read its VALUE whatever its origin.

## What that costs, in the engine's own words

`S3_RECALL_UNMEASURED` exists to say:

    "You have built retrieval and I cannot tell whether it works. That one
     number decides whether the answer here is 'fix the retriever', 'train the
     retriever' or 'the generator is the problem', and they are three different
     pieces of work."

A person who types "my recall is about 0.95" is routed away from *fix the
retriever* on a number nobody read. That is the defect the node was written to
prevent, arriving through a door the node does not watch.

## Why this file pins it instead of fixing it

THE FIX IS A DECISION, NOT A PATCH, and it is larger than the fact it was found
on. Requiring an admissible origin at every node that reads a `source: inspect`
fact would change routing across the whole engine, and getting it wrong turns
diagnoses into refusals for people whose facts are perfectly ordinary. It needs
its own fixture sheet and its own adversary, the way the gate rule got one.

IT ALSO PREDATES THE RETRIEVAL BENCH. Before `app/tools/retrieval.py` there was
no way to measure this fact at all, so a typed number was the only number
available and the question never arose. Now that a reading is possible,
accepting a claim in its place is a choice rather than a necessity - which is
what makes this worth writing down rather than shrugging at.

Found by an adversary told to invent its own routes, on the run that built the
bench. Two of its three findings were real defects and were fixed in the same
run; this is the third.
"""

import unittest

from app.tools import evidence

import support  # noqa: F401  - installs the suite's sandbox fences


FACT = "retriever_recall_at_k"


class TheLedgerAsksForAReading(unittest.TestCase):
    def test_the_fact_admits_only_a_measurement(self):
        """The control. If this ever fails, the rest of the file is moot."""
        spec = evidence.spec()
        self.assertEqual(spec.facts[FACT].get("source"), "inspect")
        self.assertEqual(set(spec.admissible_for(FACT)), {"MEASURED"})

    def test_and_a_tool_can_now_supply_one(self):
        """The half that was missing until the retrieval bench landed. Without
        this, the hole below is unavoidable rather than chosen."""
        self.assertTrue(evidence.may_be_declared_measurable(FACT))
        from app.tools import registry

        measurers = [
            name
            for name in registry.REGISTRY.names()
            if FACT in (getattr(registry.REGISTRY.get(name), "measures", ()) or ())
        ]
        self.assertEqual(measurers, ["measure_retriever_recall"])


class ButNothingEnforcesItWhereThisFactIsRead(unittest.TestCase):
    def test_no_gate_condition_reads_it(self):
        """Both defences are per-gate, so a fact no gate reads has neither.

        Prose does not count and this test is careful about the difference:
        G1_BASELINE_MEASURED names the fact in a note and would pass a naive
        substring search over the gate declaration.
        """
        spec = evidence.spec()
        gates = getattr(spec, "gates", {}) or {}
        # NOT VACUOUS. An assertion that a list is empty passes for free when
        # there is nothing to search, so the five gates are counted first.
        self.assertEqual(len(gates), 5, "the gate set changed; re-read this file")
        self.assertIn("G1_BASELINE_MEASURED", gates)
        reading = [
            name
            for name, gate in gates.items()
            if FACT in str(gate.get("passes_when", ""))
        ]
        self.assertEqual(
            reading,
            [],
            "a gate now reads %s - the origin rule applies to it and this "
            "file should be deleted rather than relaxed" % FACT,
        )

    def test_the_admissibility_policy_is_named_for_gates_and_means_it(self):
        """`admissible_for_gates` is the key in the ledger. The name IS the
        scope, and this asserts the scope is still what the name says - so the
        day somebody adds a node-level rule, this file fails and gets read."""
        from pathlib import Path

        ledger = Path(__file__).resolve().parents[1] / "docs" / "diagnosis_engine.yaml"
        raw = ledger.read_text(encoding="utf-8")
        self.assertIn("admissible_for_gates", raw)
        self.assertNotIn("admissible_for_nodes", raw)


if __name__ == "__main__":
    unittest.main()
