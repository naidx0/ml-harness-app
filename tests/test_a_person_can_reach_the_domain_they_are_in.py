"""The harness works out which discipline you are in. You still never pick.

## What this file used to say

It was a tripwire over a product gap, and every line of it was true and none of
it desirable: a person who opened the box and described **an agent that fails**
had every instrument that could help them refused with `not_in_this_domain`, and
no surface could move their thread. `docs/VISION.md` promised the opposite -
*"**You never pick one.** The harness infers the discipline… Different chats,
no."* - and nothing had ever inferred.

It went red on 2026-08-28, which is what a tripwire is for. This is the same
file asserting the other side of it.

## The inference is a LOOKUP, and that is the only reason it is allowed

Measured: **the two shipped ledgers share zero fact names.** Not few - none.
That is `docs/ledgers/ai_engineering.yaml` renaming every role on purpose so a
name leaking back into Python shows up as a failure. So a tool's `measures=`
names exactly one domain, and `_the_domain_this_tool_belongs_to` counts rather
than guesses. If two ledgers ever declare the same fact, that fact stops naming
a domain and the lookup returns nothing - asserted below, not assumed.

There are no keywords here, no heuristics and no list of domains. The ledgers
decide, which is the division this repository draws everywhere: the ledger owns
every name, the engine owns every rule about names.

## The guard is the whole of its safety

`evidence.ledger_for_thread` is explicit that *"a thread that said it was an
AI-engineering thread must never quietly get the ML one"*, and that rule is
kept: `events.adopt_ledger` refuses any thread that has **measured anything at
all**. A thread with evidence has named its domain by using it, and moving it
would leave those rows describing a domain the thread no longer runs -
`assemble_facts` would drop every one of them, and the conversation would forget
what it had looked at.

A thread with no evidence has invested nothing. Nothing is orphaned, and nothing
changes meaning.

## And it is still not a chooser

`ThreadCreate` has no `ledger` field and this file asserts it still does not.
The domain is inferred and RECORDED - as an event as well as a column, because a
domain the engine chose is something the person is entitled to see and disagree
with. That is the rule every other inferred value in this product follows.
"""

import unittest
from pathlib import Path

from app import diagnosis
from app import events
from app.tools import REGISTRY
from app.tools import evidence
import support


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "agent"
TRACES = str(FIXTURES / "journey-traces.jsonl")
TOOLDEFS = str(FIXTURES / "journey-tools.json")

ML_LEDGER = "docs/diagnosis_engine.yaml"
AI_LEDGER = "docs/ledgers/ai_engineering.yaml"

#: The instruments the AI ledger's G0 needs, each with the document it reads.
AGENT_INSTRUMENTS = (
    ("read_agent_traces", TRACES),
    ("read_tool_definitions", TOOLDEFS),
    ("bound_the_loop", TRACES),
)


class APersonReachesTheDomainTheyAreInTest(unittest.TestCase):
    def setUp(self):
        self.root = support.sandbox(self)

    def _a_table(self, name="rows.csv"):
        path = self.root / name
        path.write_text(
            "q,a\n" + "\n".join(f"ticket {i},label" for i in range(30)),
            encoding="utf-8",
        )
        return str(path)

    def test_a_thread_a_person_can_start_still_begins_on_the_default(self):
        """Unchanged, and it must be: the domain is not known when a person has
        said one sentence and attached nothing."""
        thread = events.create_thread("an agent that keeps looping")
        self.assertEqual(thread["ledger"], diagnosis.DEFAULT_LEDGER)
        self.assertEqual(diagnosis.DEFAULT_LEDGER, ML_LEDGER)

    def test_reaching_for_an_agent_instrument_moves_the_thread_and_runs_it(self):
        """THE GAP THIS FILE WAS WRITTEN OVER, now closed.

        Both halves matter. The tool RUNS - a refusal that also moved the thread
        would make the person ask twice. And the thread ENDS UP on the ledger
        that declares what they just measured, so the next question comes from
        the right tree.
        """
        thread_id = events.create_thread("an agent that keeps looping")["id"]

        result = REGISTRY.call(
            "read_agent_traces", {"path": TRACES}, actor="user", thread_id=thread_id
        )
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(events.get_thread(thread_id)["ledger"], AI_LEDGER)

    def test_the_whole_first_gate_can_now_be_opened_from_a_default_thread(self):
        """Not one tool - the set a person actually needs to get anywhere.

        `G0_SOMETHING_TO_MEASURE` is what stands between a greenfield agent
        conversation and every other question the AI ledger asks.
        """
        thread_id = events.create_thread("an agent that keeps looping")["id"]
        for name, document in AGENT_INSTRUMENTS:
            with self.subTest(tool=name):
                result = REGISTRY.call(
                    name, {"path": document}, actor="user", thread_id=thread_id
                )
                self.assertTrue(result.get("ok"), result)
        self.assertEqual(events.get_thread(thread_id)["ledger"], AI_LEDGER)

    def test_the_move_is_recorded_where_the_person_can_see_it(self):
        """A domain the engine chose is not a private decision.

        Every other inferred value in this product carries where it came from.
        This one is an event on the thread carrying both names, so a surface can
        show it and a person can disagree with it - which is the difference
        between an inference and a thing that silently happened to them.
        """
        thread_id = events.create_thread("an agent that keeps looping")["id"]
        REGISTRY.call(
            "read_agent_traces", {"path": TRACES}, actor="user", thread_id=thread_id
        )
        recorded = events.latest("thread.ledger.inferred", thread_id)
        self.assertIsNotNone(recorded, "the thread moved and said nothing")

    def test_a_thread_that_has_measured_something_is_NOT_moved(self):
        """THE GUARD, and it is the whole of this change's safety.

        This thread profiled a table, so it has a MEASURED fact the ML ledger
        declares - it has named its domain by using it. The agent tool is
        refused exactly as before, and the thread does not move: moving it would
        leave that row describing a domain the thread no longer runs, and
        `assemble_facts` would drop it silently.
        """
        thread_id = events.create_thread("a tabular problem")["id"]
        profiled = REGISTRY.call(
            "profile_dataset",
            {"path": self._a_table()},
            actor="user",
            thread_id=thread_id,
        )
        self.assertTrue(profiled.get("ok"), profiled)
        self.assertTrue(evidence.rows_for(thread_id), "the setup measured nothing")

        result = REGISTRY.call(
            "read_agent_traces", {"path": TRACES}, actor="user", thread_id=thread_id
        )
        self.assertFalse(result.get("ok"))
        self.assertEqual(result.get("error"), "not_in_this_domain")
        self.assertEqual(events.get_thread(thread_id)["ledger"], ML_LEDGER)

    def test_it_is_still_not_a_chooser(self):
        """`docs/VISION.md`: "Different tools, yes - dozens… Different chats, no."

        The domain is inferred and recorded. It is not a field somebody fills
        in, and `events.create_thread`'s own docstring says the parameter exists
        for the first of those and not the second.
        """
        from app.main import ThreadCreate

        self.assertNotIn("ledger", set(ThreadCreate.model_fields))

    def test_the_ledgers_share_no_fact_names_which_is_what_makes_this_a_lookup(self):
        """The invariant the inference rests on, pinned.

        If two ledgers ever declare the same fact name, that fact stops naming a
        domain - `_the_domain_this_tool_belongs_to` returns nothing rather than
        breaking a tie by whichever file the glob found first. Then this fails,
        and what it is asking for is a re-read of that function.
        """
        declared: dict[str, list[str]] = {}
        for path in diagnosis.known_ledgers():
            spec = diagnosis.spec_at(path)
            for fact in spec.facts:
                declared.setdefault(fact, []).append(spec.as_written)

        self.assertEqual(
            {fact: owners for fact, owners in declared.items() if len(owners) > 1}, {}
        )
        self.assertGreater(len(declared), 50, "the sweep read almost no facts")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
