"""The most common early answer could not ask its question, twice over.

An empty sheet reaches `BLOCKED__DEFINE_SUCCESS_FIRST` two nodes in. That is not
an edge case - it is the answer Max got to all seven questions he asked this
product about his own insurance book, and the file says so where it counts the
gates. A run that stops there has passed no gate and failed none, so all five
rows of `gate_ledger` read NOT_REACHED with `clause: null`, which is the engine
correctly refusing to invent a status for a gate it never reached.

## FAULT ONE: NOTHING ON THE WIRE SAID WHAT THE WALK WAS ASKING

`PathEntry.clause` carried the row's `requires` string on gate entries and null
on node entries, and the contract said so in as many words. So for this run
every clause on the whole payload was null - five in the ledger, one per node on
the path - and a surface that derives its question from the frontier's clause had
nothing at all to read. The condition was parsed at load time and sitting in
`Spec.conditions` the entire time; the wire simply did not carry it.

Measured before the fix, on `diagnose({})`:

    path   S0_RULES_SUFFICE              clause= None
    path   S0_NO_DEFINITION_OF_SUCCESS   clause= None
    ledger G0_EVAL_SET NOT_REACHED       clause= None      (and four more)

`app/asking.py` is NOT the consumer that was broken, and saying otherwise would
be this file inheriting a claim it did not check. `asking.next_step({})` returned
a `target_score` card before this change and returns one after, because
`facts_read_by` reads the compiled tree out of `Spec.conditions` rather than the
wire. The consumer that had nothing is anything downstream of the payload -
`QuestionCard.tsx` derives its frontier from `gate_ledger` alone and gets null.
What this file pins is the WIRE: the condition each entry was decided by is on
it, on both kinds of entry, and it is the file's own string.

## FAULT TWO: A NODE'S `say:` IS NOT A QUESTION

Gates carry `asks:` - *"Is there a set of examples we can score, so that 'better'
is a measurement and not a feeling?"* - and the six ASK NODES carried only
`say:`, which is what the node says when it FIRES. `app/asking.py::Because`
documented the mismatch and deliberately did not paper over it: *"Writing a
question here to fill the gap would be this module inventing the engine's
reasoning ... the durable fix is an `asks:` line on the ask nodes, in the YAML,
where a reviewer can see it."* This file checks the six lines are there, are
questions, are not copies of `say:`, and are written for a person rather than for
the ledger.
"""

from __future__ import annotations

import re
import unittest

import diagnosis_fixtures as fixtures

from app import asking, diagnosis


SPEC_TEXT = diagnosis.SPEC_PATH.read_text(encoding="utf-8")

#: The six ASK NODES, read out of the file's own ASK policy block rather than
#: listed here. The block is a comment - it is the file explaining its own rule -
#: so it is matched as text, and the test below fails loudly if the block moves
#: or is renamed rather than quietly checking nothing.
_ASK_POLICY = re.compile(
    r"#\s+ASK\s+A terminal ACTION__ node.*?Saying \"I could not read X",
    re.DOTALL,
)


def ask_nodes() -> list[str]:
    block = _ASK_POLICY.search(SPEC_TEXT)
    if block is None:  # pragma: no cover - the guard is the point
        raise AssertionError(
            "the ASK policy block in docs/diagnosis_engine.yaml has moved or been "
            "reworded; this test derives the six ask nodes from it and must not "
            "fall back to a list of its own"
        )
    return re.findall(r"\bS[0-9]+_[A-Z0-9_]+\b", block.group(0))


def all_results(spec):
    for outcome, facts in fixtures.MINTING.items():
        yield f"minting:{outcome}", diagnosis.diagnose(facts, spec)
    for label, case in fixtures.SPREAD.items():
        yield f"spread:{label}", diagnosis.diagnose(case["facts"], spec)
    for outcome, facts in fixtures.REACHING.items():
        yield f"reaching:{outcome}", diagnosis.diagnose(facts, spec)


class TheNodeEntryCarriesItsCondition(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = diagnosis.default_spec()
        cls.results = list(all_results(cls.spec))
        cls.gate_nodes = {g["node"] for g in cls.spec.gates.values()}

    def test_a_node_entry_carries_the_condition_it_was_decided_by(self):
        """Every node on every fixture's path, against the file's own string."""
        checked = 0
        for label, result in self.results:
            with self.subTest(case=label):
                for entry in result.path:
                    if entry.kind != "node":
                        continue
                    declared = self.spec.node_index.get(entry.id)
                    if declared is None:
                        continue
                    checked += 1
                    self.assertEqual(
                        entry.clause,
                        " ".join(str(declared["condition"]).split()),
                    )
        # 1315 node entries carry a declared condition across the three fixture
        # groups, measured on the day this was written. The floor is a floor -
        # it exists so a fixture set that shrank to nothing would fail here
        # rather than pass vacuously, not as a claim about the real number.
        self.assertGreater(checked, 100, "the sweep looked at almost no node entries")

    def test_the_clause_is_the_authors_string_and_not_this_engines_dialect(self):
        """Read off the spec, never rebuilt from the compiled tree.

        `ast.unparse` would put the normalizer's Python on the wire in place of
        the author's `need_type contains cost`, and the whole value of showing a
        clause is that a person can check it against the file. So every clause a
        node entry carries has to be findable in the file's own text.
        """
        for label, result in self.results:
            with self.subTest(case=label):
                for entry in result.path:
                    if entry.kind != "node" or entry.clause is None:
                        continue
                    self.assertIn(
                        entry.clause,
                        SPEC_TEXT,
                        f"{entry.id} carries a clause that is not in the file",
                    )

    def test_a_gates_own_node_keeps_a_null_clause_because_it_has_none(self):
        """The one null that survives, and the reason it is honest.

        S0_NO_EVAL_SET and the other four live in the `gates:` block and have no
        `condition:` of their own. Copying the gate row's `requires` onto them
        would be the engine inventing a condition the node does not have.
        """
        self.assertTrue(self.gate_nodes)
        for node_id in self.gate_nodes:
            self.assertNotIn(
                node_id,
                self.spec.node_index,
                f"{node_id} is now declared in a stage; this test's premise moved",
            )
        seen = 0
        for label, result in self.results:
            with self.subTest(case=label):
                for entry in result.path:
                    if entry.kind == "node" and entry.id in self.gate_nodes:
                        seen += 1
                        self.assertIsNone(entry.clause)
        self.assertGreater(seen, 0, "no gate node was walked; this test is vacuous")

    def test_a_gate_entry_still_carries_its_rows_requires_verbatim(self):
        """The half that already worked, pinned so the new half cannot cost it."""
        for label, result in self.results:
            with self.subTest(case=label):
                for entry in result.path:
                    if entry.kind != "gate":
                        continue
                    rows = self.spec.gates[entry.id]["passes_when"]
                    match = [r for r in rows if r["method_class"] == entry.row]
                    self.assertEqual(len(match), 1)
                    self.assertEqual(entry.clause, match[0]["requires"])


class TheCommonEarlyOutcomeCanBeAskedAQuestion(unittest.TestCase):
    """The consequence, measured rather than asserted."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = diagnosis.default_spec()
        cls.result = diagnosis.diagnose({}, cls.spec)

    def test_the_empty_sheet_still_stops_where_the_brief_says_it_does(self):
        self.assertEqual(self.result.outcome, "BLOCKED__DEFINE_SUCCESS_FIRST")
        self.assertEqual(self.result.verdict, "BLOCKED")
        self.assertEqual(self.result.path[-1].id, "S0_NO_DEFINITION_OF_SUCCESS")

    def test_the_gate_ledger_offers_this_run_no_clause_at_all(self):
        """Not a defect - the walk never reached a gate. It is the reason the
        path had to carry one."""
        for gate_id, row in self.result.gate_ledger.items():
            with self.subTest(gate=gate_id):
                self.assertEqual(row["status"], "NOT_REACHED")
                self.assertIsNone(row["clause"])
        self.assertEqual(self.result.unsubstantiated, [])

    def test_the_frontier_node_puts_its_condition_on_the_wire(self):
        frontier = self.result.path[-1].as_dict()
        self.assertEqual(frontier["kind"], "node")
        self.assertEqual(
            frontier["clause"],
            "target_score is null and not user_can_produce(20, 'graded examples')",
        )

    def test_a_card_is_derivable_from_the_wire_alone(self):
        """The whole point, done the way a surface with only the payload must.

        Pull the identifiers out of the frontier entry's clause, keep the ones
        the run's own `fact_origins` calls DEFAULTED, and ask for a card. Nothing
        here reads `Spec.conditions`; a consumer holding the JSON payload has
        exactly this much.
        """
        wire = {
            "path": [e.as_dict() for e in self.result.path],
            "fact_origins": self.result.fact_origins,
        }
        frontier = wire["path"][-1]
        self.assertIsNotNone(
            frontier["clause"],
            "the frontier entry carries no clause, so a consumer holding only "
            "the payload has nothing to pull a fact name out of",
        )
        names = [
            word
            for word in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", frontier["clause"])
            if wire["fact_origins"].get(word) == diagnosis.DEFAULTED
        ]
        self.assertEqual(names, ["target_score"])

        card = asking.question_for("target_score")
        self.assertIsInstance(card, asking.Question)
        self.assertEqual(card.answer, asking.NUMBER)
        self.assertEqual(card.arrives_as, diagnosis.STATED)
        self.assertIsNone(card.declared["default"])
        self.assertFalse(card.declared["declares_a_default"])


class TheAskNodesAskSomething(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = diagnosis.default_spec()
        cls.nodes = ask_nodes()

    def test_the_six_are_read_out_of_the_files_own_policy_block(self):
        self.assertEqual(len(self.nodes), 6, f"found {self.nodes}")
        for node_id in self.nodes:
            self.assertIn(node_id, self.spec.node_index)

    def test_every_ask_node_carries_a_question_and_not_only_a_verdict(self):
        for node_id in self.nodes:
            with self.subTest(node=node_id):
                node = self.spec.node_index[node_id]
                asks = " ".join(str(node.get("asks") or "").split())
                self.assertTrue(
                    asks,
                    f"{node_id} has `say:` and no `asks:`, so a card built from it "
                    "shows what this fork decides where the question belongs",
                )
                self.assertTrue(
                    asks.endswith("?"),
                    f"{node_id} `asks:` is a statement: {asks!r}",
                )

    def test_the_question_is_not_the_same_line_as_what_the_node_says(self):
        """The mismatch `asking.Because` documented. A copy would close the field
        without closing the gap."""
        for node_id in self.nodes:
            with self.subTest(node=node_id):
                node = self.spec.node_index[node_id]
                asks = " ".join(str(node.get("asks") or "").split()).strip('"')
                said = " ".join(str(node.get("say") or "").split()).strip('"')
                self.assertNotEqual(asks, said)
                action = " ".join(str(node.get("action") or "").split()).strip('"')
                self.assertNotEqual(asks, action)

    def test_the_question_is_written_for_a_person_and_not_for_the_ledger(self):
        """No fact identifier in it. `retriever_recall_at_k` is what the answer
        is recorded as; it is not what you say to somebody."""
        for node_id in self.nodes:
            node = self.spec.node_index[node_id]
            asks = str(node.get("asks") or "")
            for fact in self.spec.facts:
                with self.subTest(node=node_id, fact=fact):
                    self.assertNotIn(
                        fact,
                        asks,
                        f"{node_id} asks the person about {fact!r} by its ledger "
                        "name; `action:` is where the field name belongs",
                    )

    def test_the_register_matches_the_asks_the_gates_already_carry(self):
        """One plain sentence ending in a question mark, same as all five gates."""
        gate_asks = [
            " ".join(str(g["asks"]).split()) for g in self.spec.gates.values() if g.get("asks")
        ]
        self.assertEqual(len(gate_asks), 5, "the gates' own `asks:` lines moved")
        # Measured, so the tolerance below has an origin. The five gate `asks:`
        # lines run 71-93 characters; the six node lines run 35-123, and the
        # longest of them - S4, which has two facts to ask about - is 30 over
        # the longest gate. The allowance is 40, chosen to sit just above that
        # measured spread. It is a house-style tolerance and not a measurement
        # of anything; re-pin it against the file rather than widening it.
        longest_gate = max(len(a) for a in gate_asks)
        for node_id in self.nodes:
            with self.subTest(node=node_id):
                asks = " ".join(str(self.spec.node_index[node_id].get("asks") or "").split())
                self.assertEqual(asks.count("?"), 1)
                self.assertLessEqual(
                    len(asks),
                    longest_gate + 40,
                    "a node question far longer than any gate's is a paragraph "
                    "wearing a question mark",
                )

    def test_no_other_node_grew_an_asks_line_by_accident(self):
        carrying = sorted(n for n, d in self.spec.node_index.items() if d.get("asks"))
        self.assertEqual(carrying, sorted(self.nodes))

    def test_and_something_actually_reads_them(self):
        """The half that was missing, and without it the six lines were DEAD.

        `_because_for` read `node.get("say")` and nothing in `app/` read
        `node["asks"]` at all, so every one of these questions was a string in a
        YAML file that no code path could reach. A test that only asserts the
        lines EXIST passes just as well when they are unreachable, which is what
        it did.
        """
        result = diagnosis.diagnose({})
        entry = type(result.path[0])
        for node_id in self.nodes:
            with self.subTest(node=node_id):
                because = asking._because_for(entry(node_id, "node", None, None), result)
                self.assertEqual(
                    because.asks,
                    _one_line(self.spec.node_index[node_id]["asks"]),
                    "the node's question does not reach the card",
                )
                self.assertNotEqual(
                    because.asks,
                    _one_line(self.spec.node_index[node_id].get("say")),
                    "the card is showing what this fork decides, not the question",
                )

    def test_but_a_node_with_no_question_still_falls_back_to_what_it_says(self):
        """`asks:` first, `say:` second, nothing third. Most nodes have only
        `say:`, and showing them blank would be a worse card than showing the
        verdict."""
        bare = [
            n
            for n, d in self.spec.node_index.items()
            if d.get("say") and not d.get("asks")
        ]
        self.assertTrue(bare, "no node has say: without asks: - test is vacuous")
        result = diagnosis.diagnose({})
        entry = type(result.path[0])
        node_id = sorted(bare)[0]
        because = asking._because_for(entry(node_id, "node", None, None), result)
        self.assertEqual(because.asks, _one_line(self.spec.node_index[node_id]["say"]))


def _one_line(value) -> str:
    text = " ".join(str(value or "").split())
    if len(text) >= 2 and text[0] == text[-1] == '"':
        text = text[1:-1].strip()
    return text


if __name__ == "__main__":
    unittest.main()
