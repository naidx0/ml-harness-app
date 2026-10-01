"""The first gate, opened in a conversation that had never been shown a file.

## The defect, which was live in the owner's own database

`fact_evidence.thread_id` is nullable. `evidence.rows_for` reads a NULL there as
MACHINE SCOPE and shows the row to every thread, which is right: this box's GPU is
this box's GPU whichever conversation asked. Nothing anywhere enforced the other
half. `record()` accepted `thread_id=None` for ANY fact, and `POST
/api/tools/{name}` made the argument optional, so `measure_eval_set` called
without one counted a real file honestly and filed the answer where every
conversation on the machine could read it.

    measure_eval_set(path=<a real 120-row file>)  with thread_id=None
    -> fact_evidence(thread_id=NULL, eval_size_n=120, MEASURED)
    -> thread 4242, which has never been shown a file, reads
       Fact(value=120, origin='MEASURED')
    -> G0_EVAL_SET: PASSED, clause `eval_size_n >= 30`

The owner's database held exactly three NULL-thread rows. All three were
`eval_size_n`. None was hardware - so the mechanism that exists for the machine's
own facts was in use by exactly one fact, the one fact that must never use it.

AND `rows_for`'s OWN DOCSTRING NAMED THIS FAILURE FIRST, with the same fact and
the same number: "the eval set has 120 rows is a fact about one project and
leaking it sideways would open a gate in a conversation where nobody counted
anything." Somebody saw it, wrote it down, guarded the READ path, and left the
WRITE path open.

## Why 1057 tests could not see it

Every test starts from `support.sandbox()`, which gives it a clean ledger, and
every test passes a `thread_id`. So the suite always supplied the argument whose
absence is the bug, and always into an empty table where a leak has nowhere to
leak from. That is a systematic blind spot rather than one missing case, and it
is why this file is built the way it is:

  * `TheBypassTest` calls the real tool through the real registry with the
    argument LEFT OFF, which is what nothing did;
  * `ADirtyLedgerLeaksIntoACleanConversationTest` writes a row and then asks a
    DIFFERENT thread what it can see, which is what nothing did;
  * `TheDetectorSeesTheBugTest` reverts the scope check and watches all of the
    above go green in the bug's favour - because a procedure returning green
    against known-broken code certifies nothing.

## The positive controls, which are the point of the last class

Every refusal test here would pass against a `record()` that refused
everything, and against a `rows_for` that returned nothing to anybody. So each
refusal has a control beside it: the machine's own facts are still writable with
no thread at all and are still visible everywhere, the honest path with a thread
still records and still opens G0, and the reverted-check class reproduces the
original defect end to end.
"""

from __future__ import annotations

import json
import unittest

from app import db, diagnosis
from app.tools import evidence
from app.tools.evidence import MEASURED, ScopeError, USER
from app.tools.registry import REGISTRY

import support


#: The conversation that does the work.
COUNTING_THREAD = 7

#: The conversation that has never been shown a file. Any run in here that knows
#: how big an eval set is, is a run reading somebody else's measurement.
INNOCENT_THREAD = 4242

#: Big enough to clear `eval_size_n >= 30`, which is G0's clause. 120 because
#: that is the number that was actually in the owner's database.
ROWS = 120


def eval_file(root, rows: int = ROWS):
    """A real JSONL eval set, so the count that gets stamped is a real count."""
    path = root / "eval.jsonl"
    path.write_text(
        "".join(
            json.dumps({"input": f"q{i}", "output": f"a{i}"}) + "\n"
            for i in range(rows)
        ),
        encoding="utf-8",
    )
    return path


def sheet_for(thread_id: int) -> dict:
    """What the engine would be asked to reason over for this conversation.

    The three extra facts are what any run needs to get past stage 0 at all;
    `eval_size_n` is deliberately NOT among them, so whatever G0 sees came out of
    the ledger and out of nothing else.
    """
    facts, _trail = evidence.assemble_facts(thread_id)
    return {
        "goal_text": "route support tickets",
        "modality": "text",
        "target_score": 0.9,
        **facts,
    }


def gate_status(thread_id: int) -> str:
    row = diagnosis.diagnose(sheet_for(thread_id)).gate_ledger.get("G0_EVAL_SET")
    return (row or {}).get("status", "NOT REACHED")


def ledger_rows() -> list[dict]:
    with db.session() as connection:
        return [dict(r) for r in connection.execute("SELECT * FROM fact_evidence")]


class TheBypassTest(unittest.TestCase):
    """The construction, run against the real tool through the real door."""

    def setUp(self):
        self.root = support.sandbox(self)
        evidence.ensure_table()
        # Both conversations are REAL conversations. `record` now refuses an id
        # that names nothing, and the leak this file is about has nothing to do
        # with that: the innocent thread is one the user genuinely opened, and it
        # must still see nothing.
        support.a_conversation(COUNTING_THREAD, INNOCENT_THREAD)
        self.path = eval_file(self.root)

    def test_counting_an_eval_set_with_no_thread_is_refused(self):
        with self.assertRaises(ScopeError) as caught:
            REGISTRY.call(
                "measure_eval_set",
                {"path": str(self.path)},
                actor=USER,
                thread_id=None,
            )
        self.assertIn("thread_id", str(caught.exception))

    def test_nothing_at_all_was_written(self):
        """"Nothing was recorded" is in the message, so it had better be true."""
        with self.assertRaises(ScopeError):
            REGISTRY.call(
                "measure_eval_set",
                {"path": str(self.path)},
                actor=USER,
                thread_id=None,
            )
        self.assertEqual(ledger_rows(), [])

    def test_the_refusal_names_the_argument_the_fact_and_the_gate(self):
        """A refusal that names nothing is a wall with no door.

        The caller who hits this is exactly the caller who does not know the
        argument exists - that was the defect - so the message has to carry the
        argument, where it goes, what this particular fact would have done, and
        what may legitimately be written with no conversation.
        """
        with self.assertRaises(ScopeError) as caught:
            REGISTRY.call(
                "measure_eval_set",
                {"path": str(self.path)},
                actor=USER,
                thread_id=None,
            )
        message = str(caught.exception)
        for expected in (
            "thread_id",                    # the argument
            "measure_eval_set",             # who tried
            "eval_size_n",                  # which fact
            "scope: thread",                # what the ledger says about it
            "G0_EVAL_SET",                  # what it would have opened
            "docs/diagnosis_engine.yaml",   # where that is declared
            "vram_gb",                      # what may be written with no thread
            "Nothing was recorded",
        ):
            with self.subTest(names=expected):
                self.assertIn(expected, message)

    def test_saying_it_yourself_with_no_thread_is_refused_too(self):
        """WALL 5 IS NOT ABOUT THE STAMP. `state_facts` writes STATED and
        ASSERTED rows through `Instrument.supplied`, and a model's guess at
        `prompt_iterations` spread across every conversation on the machine is
        the same leak by the same mechanism. The stamp is what makes the leaked
        row dangerous; the leak is not a property of the stamp."""
        with self.assertRaises(ScopeError) as caught:
            REGISTRY.call(
                "state_facts",
                {"facts": {"prompt_iterations": 5}},
                actor=USER,
                thread_id=None,
            )
        self.assertIn("prompt_iterations", str(caught.exception))
        self.assertEqual(ledger_rows(), [])

    def test_the_ledger_refuses_a_bare_record_too(self):
        """Not only through a tool. `record` is exported, and the wall is on it
        rather than on the callers somebody remembered - which is the mistake
        wall 3 made once already, guarding `assemble_facts` and not `rows_for`."""
        with self.assertRaises(ScopeError):
            evidence.record(
                fact="eval_size_n",
                value=120,
                origin=evidence.ASSERTED,
                actor=evidence.MODEL,
                how="straight into the table",
                thread_id=None,
            )
        self.assertEqual(ledger_rows(), [])

    def test_a_fact_nobody_declared_is_refused_with_no_thread(self):
        """Fail closed on a name the ledger has never heard of."""
        with self.assertRaises(ScopeError) as caught:
            evidence.record(
                fact="answer_given",
                value=True,
                origin=evidence.ASSERTED,
                actor=evidence.MODEL,
                how="a real local model invented this name",
                thread_id=None,
            )
        self.assertIn("not a declared fact", str(caught.exception))

    # -- the controls -----------------------------------------------------

    def test_the_machine_can_still_be_measured_with_no_conversation(self):
        """POSITIVE CONTROL. A wall that refuses everything is not a wall.

        `inspect_hardware` measures four facts and every one of them is the
        machine's own. A person looking at their own hardware page has no
        conversation open and must not be made to invent one.
        """
        result = REGISTRY.call("inspect_hardware", {}, actor=USER, thread_id=None)
        self.assertTrue(result.get("measured_facts"), result)
        written = {row["fact"] for row in ledger_rows()}
        self.assertTrue(
            written <= set(evidence.facts_at_scope(evidence.MACHINE)), written
        )
        self.assertTrue(
            all(row["thread_id"] is None for row in ledger_rows()),
            "the hardware rows should be at machine scope",
        )

    def test_a_machine_row_really_is_visible_from_every_conversation(self):
        """POSITIVE CONTROL for the read side: machine scope still means what it
        says, so this change narrowed the WRITE path and not the product."""
        REGISTRY.call("inspect_hardware", {}, actor=USER, thread_id=None)
        seen, _ = evidence.assemble_facts(INNOCENT_THREAD)
        self.assertTrue(
            set(seen) & set(evidence.facts_at_scope(evidence.MACHINE)), seen
        )

    def test_counting_the_same_file_with_a_thread_still_works(self):
        """POSITIVE CONTROL. The honest path is unchanged and still opens G0."""
        result = REGISTRY.call(
            "measure_eval_set",
            {"path": str(self.path)},
            actor=USER,
            thread_id=COUNTING_THREAD,
        )
        self.assertEqual(result["rows"], ROWS)
        self.assertEqual(result["measured_facts"][0]["value"], ROWS)
        rows = ledger_rows()
        self.assertEqual([row["thread_id"] for row in rows], [COUNTING_THREAD])
        self.assertEqual(gate_status(COUNTING_THREAD), "PASSED")


class ADirtyLedgerLeaksIntoACleanConversationTest(unittest.TestCase):
    """The half the suite could not see: a ledger that is not empty.

    `support.sandbox()` gives every test a clean table, so no test ever asked
    what a SECOND conversation can see. These do.
    """

    def setUp(self):
        self.root = support.sandbox(self)
        evidence.ensure_table()
        # Both conversations are REAL conversations. `record` now refuses an id
        # that names nothing, and the leak this file is about has nothing to do
        # with that: the innocent thread is one the user genuinely opened, and it
        # must still see nothing.
        support.a_conversation(COUNTING_THREAD, INNOCENT_THREAD)
        self.path = eval_file(self.root)
        REGISTRY.call(
            "measure_eval_set",
            {"path": str(self.path)},
            actor=USER,
            thread_id=COUNTING_THREAD,
        )

    def test_the_thread_that_counted_can_see_its_own_count(self):
        """POSITIVE CONTROL. If this failed, everything below would pass for the
        uninteresting reason that nobody can see anything."""
        seen, _ = evidence.assemble_facts(COUNTING_THREAD)
        self.assertEqual(diagnosis.bare(seen["eval_size_n"]), ROWS)
        self.assertEqual(seen["eval_size_n"].origin, MEASURED)
        self.assertEqual(gate_status(COUNTING_THREAD), "PASSED")

    def test_a_conversation_that_never_saw_a_file_knows_nothing_about_one(self):
        seen, _ = evidence.assemble_facts(INNOCENT_THREAD)
        self.assertNotIn("eval_size_n", seen)

    def test_the_first_gate_does_not_open_in_that_conversation(self):
        """The consequence a user would meet, which is the thing that matters."""
        self.assertNotEqual(gate_status(INNOCENT_THREAD), "PASSED")

    def test_and_it_is_told_to_build_one_rather_than_congratulated(self):
        outcome = diagnosis.diagnose(sheet_for(INNOCENT_THREAD)).outcome
        self.assertEqual(outcome, "BLOCKED__BUILD_EVAL_SET")


class TheDetectorSeesTheBugTest(unittest.TestCase):
    """MUTATION CHECK. Revert the scope rule; watch every assertion above invert.

    A procedure that returns green against known-broken code certifies nothing,
    and the tests above are all refusals - they would pass against a `record()`
    that raised on everything and against a `rows_for` that returned nothing.
    This class puts the defect back, in the one place the fix lives, and asserts
    that the defect is then reproducible end to end. If this class ever fails,
    the tests above are measuring something other than what they claim.

    The mutation is `scope_of` answering MACHINE for everything, which is exactly
    the state of the world before any fact declared a scope: `record` had no
    reason to refuse a NULL thread for any fact at all.
    """

    def setUp(self):
        self.root = support.sandbox(self)
        evidence.ensure_table()
        # Both conversations are REAL conversations. `record` now refuses an id
        # that names nothing, and the leak this file is about has nothing to do
        # with that: the innocent thread is one the user genuinely opened, and it
        # must still see nothing.
        support.a_conversation(COUNTING_THREAD, INNOCENT_THREAD)
        self.path = eval_file(self.root)
        saved = evidence.scope_of
        # `scope_of` now takes the ledger the call is being judged against - a
        # fact's scope is declared by ITS OWN ledger, and a second ledger
        # declares different facts. The mutation is unchanged: answer MACHINE
        # for everything, whichever ledger is asked, which is exactly the state
        # of the world before any fact declared a scope.
        evidence.scope_of = lambda fact, ledger=None: evidence.MACHINE
        self.addCleanup(setattr, evidence, "scope_of", saved)

    def test_with_the_check_reverted_the_count_is_written_with_no_thread(self):
        result = REGISTRY.call(
            "measure_eval_set",
            {"path": str(self.path)},
            actor=USER,
            thread_id=None,
        )
        self.assertEqual(result["rows"], ROWS)
        self.assertEqual([row["thread_id"] for row in ledger_rows()], [None])

    def test_with_the_check_reverted_the_innocent_thread_reads_the_measurement(self):
        REGISTRY.call(
            "measure_eval_set",
            {"path": str(self.path)},
            actor=USER,
            thread_id=None,
        )
        seen, _ = evidence.assemble_facts(INNOCENT_THREAD)
        self.assertEqual(diagnosis.bare(seen["eval_size_n"]), ROWS)
        self.assertEqual(seen["eval_size_n"].origin, MEASURED)

    def test_with_the_check_reverted_the_first_gate_opens_on_somebody_elses_file(self):
        """THE DEFECT ITSELF, reproduced, so the fix above is not decoration."""
        REGISTRY.call(
            "measure_eval_set",
            {"path": str(self.path)},
            actor=USER,
            thread_id=None,
        )
        self.assertEqual(gate_status(INNOCENT_THREAD), "PASSED")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
