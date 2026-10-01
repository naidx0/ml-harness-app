"""The same omission, one notch in, on both sides of the same table.

`tests/test_a_thread_scoped_fact_needs_a_thread.py` closed a first-gate bypass:
a fact declares a scope, and a thread-scoped row written with no thread is
refused. This file is what an adversary found when they looked at the fix
instead of at the bug - the rule was written at ONE POINT OF THE TABLE, twice.

## DEFECT 1 - A THREAD ID HAD TO BE PRESENT, NOT TO MEAN ANYTHING

`record()` checked that `thread_id` was not None and nothing checked that it
named a conversation. `fact_evidence.thread_id` had no foreign key. So an
integer was enough, and the dangerous integer is the small one, because SQLite
hands out rowids in order from 1:

    # an empty database, no conversations in it at all
    measure_eval_set(path=<a real 120-row file>, thread_id=1)   -> accepted
    POST /api/threads                                           -> id 1
    -> the FIRST conversation the user ever opens reads
       Fact(value=120, origin='MEASURED'), having been shown no file

Measured against the shipped `TRAIN__LORA_SFT` fixture with `eval_size_n`
removed from it, so the only place that number could come from is the ledger:

    control thread   BLOCKED__BUILD_EVAL_SET   G0 FAILED, four NOT_REACHED
    seeded  thread   TRAIN__LORA_SFT           all five gates PASSED

`0`, `-1` and `999999` were accepted the same way. Reachable over HTTP by
anybody who types a thread id and from Python; not reachable by a model, because
`RESERVED_ARGUMENTS` refuses a schema that declares `thread_id` at all.

AND THE PRODUCT ALREADY KNEW HOW TO SAY THIS. `storm.declare` refuses with
"there is no thread {id}" and `events.add_message` returns `None` rather than
write into nothing. Two siblings of this table checked their parent row; the
ledger did not.

## DEFECT 2 - THE READ PATH NEVER LEARNED ABOUT SCOPE AT ALL

`rows_for()` served every NULL-thread row to every thread, whatever the ledger
declared. Only the WRITE path was taught. So any NULL row arriving by a route
`record()` does not cover reopened the gate in silence - a restored pre-v006
backup, a hand-edited database, a bulk import, a future migration. One INSERT
is the whole attack, and `record()` is never called:

    INSERT INTO fact_evidence (thread_id, fact, value, origin, ...)
        VALUES (NULL, 'eval_size_n', '120', 'MEASURED', ...)

    the same conversation, before   BLOCKED__BUILD_EVAL_SET, G0 FAILED
    the same conversation, after    TRAIN__LORA_SFT, all five gates PASSED

`TheReadPathKnowsAboutScopeTest` is that INSERT, written with raw SQL on
purpose. A test that went through `record()` would be testing the write path
again and would pass against a `rows_for` that had learned nothing.

## WHY THE FIX IS A FOREIGN KEY AND A CHECK IN `record()` AND NOT EITHER

`TheDetectorSeesTheBugTest` is the argument, run rather than written down. It
reverts the two halves separately and reports what each one alone leaves
standing:

    both in place            ScopeError, naming the argument, the fact and G0
    check reverted only      IntegrityError from SQLite - the store refuses
    check AND key reverted   THE ORIGINAL DEFECT, all five gates PASSED

The middle row is why the foreign key is worth its migration: with the sentence
gone the store still refuses, which is the property this project keeps asking
for and keeps implementing as a function somebody has to remember to call. The
bottom row is why the check is worth having beside it: without both, the leak is
live. And the top row is why neither is enough on its own - `FOREIGN KEY
constraint failed` names no argument, no fact, no gate and no door, and the
caller who trips this is exactly the caller who did not know the id had to mean
something.

## THE OPPOSITE FAILURE, WHICH MATTERS AS MUCH

A gate nothing can open is not a gate. `TheHonestPathIsUnchangedTest` is the
whole of the other direction: the machine is still measurable with no
conversation open, its four facts are still visible in every conversation, and
the honest path - count a real file in a real conversation, score a real
baseline against a scripted model - still opens G0 and G1 and still mints
TRAIN__LORA_SFT with all five gates PASSED.
"""

from __future__ import annotations

import json
import sqlite3
import unittest
from pathlib import Path

import diagnosis_fixtures as fixtures

from app import db, diagnosis, events
from app.providers import Delta, store as provider_store
from app.tools import REGISTRY, evidence, measure
from app.tools.evidence import MACHINE, MEASURED, ScopeError, USER

import support


#: Big enough to clear G0's `eval_size_n >= 30`. 120 because that is the number
#: that was in the owner's real database.
ROWS = 120

#: The id a seed goes to when there is nothing to seed against. It is `1` and not
#: `4242` because `1` is the one that gets INHERITED: rowids are handed out in
#: order, so the first conversation anybody opens is the one that reads this row.
THE_ID_THE_FIRST_CONVERSATION_WILL_GET = 1


def eval_file(root: Path, rows: int = ROWS, labels: int = 5) -> Path:
    """A real JSONL eval set, so anything counted off it is a real count."""
    path = root / f"eval_{rows}.jsonl"
    path.write_text(
        "\n".join(
            json.dumps({"q": f"q{i}", "a": f"label{i % labels}"}) for i in range(rows)
        ),
        encoding="utf-8",
    )
    return path


def sheet_for(thread_id: int | None) -> dict:
    """The TRAIN__LORA_SFT fixture WITHOUT `eval_size_n`, plus this thread's ledger.

    The fixture is the shipped one, so this is the story the product itself says
    mints TRAIN__LORA_SFT. `eval_size_n` is removed from it, so the only place
    that number can come from is `assemble_facts` - which is what makes the
    outcome below a statement about the ledger and not about the fixture.
    """
    sheet = dict(fixtures.MINTING["TRAIN__LORA_SFT"])
    sheet.pop("eval_size_n", None)
    facts, _trail = evidence.assemble_facts(thread_id)
    sheet.update(facts)
    return sheet


def verdict(thread_id: int | None) -> tuple[str, dict[str, str]]:
    """`(outcome, {gate: status})` for this conversation. The whole assertion."""
    result = diagnosis.diagnose(sheet_for(thread_id))
    gates = {
        gate: row.get("status") for gate, row in (result.gate_ledger or {}).items()
    }
    return result.outcome, gates


def ledger_rows() -> list[dict]:
    """Straight out of the table, past every reader in the product."""
    with db.session() as connection:
        return [
            dict(row)
            for row in connection.execute("SELECT * FROM fact_evidence ORDER BY id")
        ]


def insert_a_row_with_sql(**overrides) -> None:
    """One row, written with SQL, with `record()` nowhere in the call stack.

    This is a restored backup, a hand edit, a bulk import and a future migration,
    all of which put rows into this table without asking this product's opinion.
    """
    row = {
        "thread_id": None,
        "fact": "eval_size_n",
        "value": json.dumps(ROWS),
        "origin": MEASURED,
        "actor": "user",
        "tool": "a restored backup",
        "how": f"counted {ROWS} rows in somebody else's eval.jsonl",
        "created_at": "2024-01-01 00:00:00",
    }
    row.update(overrides)
    evidence.ensure_table()
    with db.session() as connection:
        connection.execute(
            "INSERT INTO fact_evidence "
            "(thread_id, fact, value, origin, actor, tool, how, created_at) "
            "VALUES (:thread_id, :fact, :value, :origin, :actor, :tool, :how, "
            ":created_at)",
            row,
        )


class ScriptedModel:
    """Right on the first `correct` rows, wrong after. Answers from the question."""

    def __init__(self, correct: int, labels: int = 5) -> None:
        self.correct = correct
        self.labels = labels

    def stream(self, conversation, offered, *, secret=None):
        question = conversation[-1]["content"]
        index = int(str(question).lstrip("q") or 0)
        if index < self.correct:
            yield Delta(kind="text", text=f"label{index % self.labels}")
        else:
            yield Delta(kind="text", text="something else entirely")


# ---------------------------------------------------------------------------
# DEFECT 1. The construction, through the real tool, on an empty database.


class AThreadIdMustNameARealConversationTest(unittest.TestCase):
    """No conversations exist. Every id is therefore a lie, including `1`."""

    def setUp(self):
        self.root = support.sandbox(self)
        evidence.ensure_table()
        self.path = eval_file(self.root)
        self.assertEqual(events.list_threads(), [], "this database has no threads")

    def seed(self, thread_id):
        return REGISTRY.call(
            "measure_eval_set",
            {"path": str(self.path)},
            actor=USER,
            thread_id=thread_id,
        )

    def test_the_id_the_first_conversation_will_get_is_refused(self):
        with self.assertRaises(ScopeError) as caught:
            self.seed(THE_ID_THE_FIRST_CONVERSATION_WILL_GET)
        self.assertIn("there is no such conversation", str(caught.exception))

    def test_nothing_at_all_was_written(self):
        """"Nothing was recorded" is in the message, so it had better be true."""
        with self.assertRaises(ScopeError):
            self.seed(THE_ID_THE_FIRST_CONVERSATION_WILL_GET)
        self.assertEqual(ledger_rows(), [])

    def test_the_first_conversation_the_user_opens_inherits_nothing(self):
        """THE DEFECT, END TO END, and the only assertion that matters.

        Seed, then open the first conversation, then ask the engine what it
        knows. Before the fix this thread answered TRAIN__LORA_SFT with five
        gates PASSED, having been shown nothing.
        """
        with self.assertRaises(ScopeError):
            self.seed(THE_ID_THE_FIRST_CONVERSATION_WILL_GET)
        thread = events.create_thread("the first conversation")
        self.assertEqual(thread["id"], THE_ID_THE_FIRST_CONVERSATION_WILL_GET)

        facts, _trail = evidence.assemble_facts(thread["id"])
        self.assertNotIn("eval_size_n", facts)

        outcome, gates = verdict(thread["id"])
        self.assertEqual(outcome, "BLOCKED__BUILD_EVAL_SET")
        self.assertEqual(gates["G0_EVAL_SET"], "FAILED")
        self.assertEqual(
            [status for status in gates.values() if status == "PASSED"], []
        )

    def test_zero_and_negative_and_absent_ids_are_all_refused(self):
        for thread_id in (0, -1, 999_999, 2):
            with self.subTest(thread_id=thread_id):
                with self.assertRaises(ScopeError):
                    self.seed(thread_id)
                self.assertEqual(ledger_rows(), [])

    def test_a_non_integer_id_is_refused_rather_than_coerced(self):
        """`True` is an `int` in Python and `"1"` looks like one. Neither is an id."""
        for thread_id in (True, "1", 1.0):
            with self.subTest(thread_id=thread_id):
                with self.assertRaises(ScopeError):
                    self.seed(thread_id)
                self.assertEqual(ledger_rows(), [])

    def test_the_refusal_names_the_door(self):
        """A refusal that names nothing is a wall with no door, and the caller
        who trips this one is exactly the caller who did not know the id had to
        mean something."""
        with self.assertRaises(ScopeError) as caught:
            self.seed(THE_ID_THE_FIRST_CONVERSATION_WILL_GET)
        message = str(caught.exception)
        for expected in (
            "measure_eval_set",          # who tried
            "eval_size_n",               # which fact
            "thread 1",                  # which id
            "INHERITS",                  # why that id is the dangerous one
            "G0_EVAL_SET",               # what it would have opened
            "POST /api/threads",         # where a real id comes from
            "app/conductor.py",          # and where the other one comes from
            "app/storm.py",              # the siblings that already say this
            "Nothing was recorded",
        ):
            with self.subTest(names=expected):
                self.assertIn(expected, message)

    def test_a_zero_id_is_told_it_could_never_have_worked(self):
        """A different sentence, because it is a different mistake: `999999`
        might name a conversation on some database and `0` never can."""
        with self.assertRaises(ScopeError) as caught:
            self.seed(0)
        self.assertIn("POSITIVE integer", str(caught.exception))

    def test_the_ledger_refuses_a_bare_record_too(self):
        """Not only through a tool. The wall is on `record`, not on the callers
        somebody remembered - which is the mistake wall 3 made once already."""
        with self.assertRaises(ScopeError):
            evidence.record(
                fact="prompt_iterations",
                value=5,
                origin=evidence.ASSERTED,
                actor=evidence.MODEL,
                how="straight into the table",
                thread_id=THE_ID_THE_FIRST_CONVERSATION_WILL_GET,
            )
        self.assertEqual(ledger_rows(), [])

    def test_a_machine_fact_filed_against_a_thread_that_is_not_there_is_refused(self):
        """SCOPE IS NOT THE EXEMPTION. "The box is the same box" is a reason to
        allow NO thread; it is never a reason to allow a WRONG one, and a
        hardware row filed against thread 1 is still a row thread 1 inherits."""
        with self.assertRaises(ScopeError):
            REGISTRY.call(
                "inspect_hardware",
                {},
                actor=USER,
                thread_id=THE_ID_THE_FIRST_CONVERSATION_WILL_GET,
            )
        self.assertEqual(ledger_rows(), [])


class TheStoreRefusesItWithoutBeingAskedTest(unittest.TestCase):
    """The half no future caller can forget, hit with SQL rather than with Python."""

    def setUp(self):
        self.root = support.sandbox(self)
        evidence.ensure_table()
        self.thread = events.create_thread("a real conversation")

    def test_a_row_naming_no_conversation_is_refused_by_the_foreign_key(self):
        for thread_id in (self.thread["id"] + 1, 999_999):
            with self.subTest(thread_id=thread_id):
                with self.assertRaises(sqlite3.IntegrityError) as caught:
                    insert_a_row_with_sql(thread_id=thread_id)
                self.assertIn("FOREIGN KEY", str(caught.exception))

    def test_zero_and_negative_are_refused_by_the_check(self):
        """A foreign key refuses `0` only because no `threads` row happens to
        have that id, and "happens to" is not a rule."""
        for thread_id in (0, -1):
            with self.subTest(thread_id=thread_id):
                with self.assertRaises(sqlite3.IntegrityError) as caught:
                    insert_a_row_with_sql(thread_id=thread_id)
                self.assertIn("CHECK constraint", str(caught.exception))

    def test_a_real_conversation_and_no_conversation_are_both_still_writable(self):
        """POSITIVE CONTROL. A table that refused every INSERT would pass both
        assertions above."""
        insert_a_row_with_sql(thread_id=self.thread["id"])
        insert_a_row_with_sql(thread_id=None, fact="vram_gb", value="24.0")
        self.assertEqual(len(ledger_rows()), 2)

    def test_the_shipped_schema_and_the_migration_agree(self):
        """`evidence.ensure_table` still creates this table on a database that
        has somehow lost it, so there are two statements that can produce it and
        they must produce the same thing. A constraint that depends on which
        code path ran is not a constraint."""
        with db.session() as connection:
            live = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' "
                "AND name = 'fact_evidence'"
            ).fetchone()[0]

        def shape(sql: str) -> str:
            body = sql[sql.index("(") :].strip().rstrip(";").strip()
            return " ".join(body.split())

        self.assertEqual(shape(live), shape(evidence._SCHEMA))
        self.assertIn("REFERENCES threads(id)", shape(live))
        self.assertIn("CHECK (thread_id IS NULL OR thread_id > 0)", shape(live))


# ---------------------------------------------------------------------------
# DEFECT 2. The read path, attacked with SQL so the write path cannot answer.


class TheReadPathKnowsAboutScopeTest(unittest.TestCase):
    """One INSERT, no `record()`, and the question is what any thread can see."""

    def setUp(self):
        self.root = support.sandbox(self)
        evidence.ensure_table()
        self.thread = events.create_thread("a conversation that counted nothing")
        self.other = events.create_thread("another one, equally innocent")
        self.assertEqual(evidence.scope_of("eval_size_n"), evidence.THREAD)

    def test_the_conversation_is_blocked_before_the_insert(self):
        """NON-VACUITY. Every assertion below is worthless if this thread could
        not have reached TRAIN__LORA_SFT in the first place."""
        outcome, gates = verdict(self.thread["id"])
        self.assertEqual(outcome, "BLOCKED__BUILD_EVAL_SET")
        self.assertEqual(gates["G0_EVAL_SET"], "FAILED")

    def test_no_thread_can_see_a_null_row_for_a_thread_scoped_fact(self):
        """THE DEFECT. The row is in the table; nobody may read it."""
        insert_a_row_with_sql()
        self.assertEqual(len(ledger_rows()), 1, "the row really was written")
        for thread_id in (self.thread["id"], self.other["id"], 4242, None):
            with self.subTest(thread=thread_id):
                self.assertEqual(evidence.rows_for(thread_id), [])
                facts, _trail = evidence.assemble_facts(thread_id)
                self.assertNotIn("eval_size_n", facts)

    def test_the_gate_stays_shut_and_the_outcome_does_not_move(self):
        insert_a_row_with_sql()
        outcome, gates = verdict(self.thread["id"])
        self.assertEqual(outcome, "BLOCKED__BUILD_EVAL_SET")
        self.assertEqual(gates["G0_EVAL_SET"], "FAILED")
        self.assertEqual(
            [status for status in gates.values() if status == "PASSED"], []
        )

    def test_a_fact_the_ledger_has_never_heard_of_is_refused_too(self):
        """`scope_of` reads an unknown name as THREAD, which is the direction
        this has to fail in, and the read path inherits that by asking it."""
        insert_a_row_with_sql(fact="answer_given", value=json.dumps(True))
        self.assertEqual(evidence.rows_for(self.thread["id"]), [])

    def test_the_row_is_not_hidden_from_the_person_whose_database_it_is(self):
        """A row nothing shows has been deleted as far as anybody can tell, and
        this product deletes nothing. It can open no gate and it is still here."""
        insert_a_row_with_sql()
        unscoped = evidence.rows_no_thread_can_see()
        self.assertEqual([row["fact"] for row in unscoped], ["eval_size_n"])
        self.assertEqual(unscoped[0]["value"], ROWS)
        self.assertEqual(unscoped[0]["tool"], "a restored backup")

    def test_the_evidence_route_shows_it_beside_the_live_ledger(self):
        insert_a_row_with_sql()
        client = support.api_client(__import__("app.main", fromlist=["app"]).app)
        response = client.get(
            f"/api/evidence?thread_id={self.thread['id']}",
            headers=support.auth_headers(),
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["rows"], [])
        self.assertEqual([row["fact"] for row in body["unscoped"]], ["eval_size_n"])
        self.assertIn("no gate", body["unscoped_note"])

    # -- the controls -----------------------------------------------------

    def test_a_null_row_for_a_machine_fact_is_still_seen_everywhere(self):
        """POSITIVE CONTROL, and it is the whole reason NULL means anything. A
        reader that refused every NULL row would pass every assertion above."""
        insert_a_row_with_sql(fact="vram_gb", value="24.0", tool="inspect_hardware")
        for thread_id in (self.thread["id"], self.other["id"], None):
            with self.subTest(thread=thread_id):
                facts, _trail = evidence.assemble_facts(thread_id)
                self.assertEqual(facts["vram_gb"].value, 24.0)
        self.assertEqual(evidence.rows_no_thread_can_see(), [])

    def test_a_row_that_names_a_thread_is_still_that_thread_s(self):
        """POSITIVE CONTROL for the other half of the clause. The change is to
        NULL rows and to nothing else."""
        insert_a_row_with_sql(thread_id=self.thread["id"])
        mine, _ = evidence.assemble_facts(self.thread["id"])
        theirs, _ = evidence.assemble_facts(self.other["id"])
        self.assertEqual(mine["eval_size_n"].value, ROWS)
        self.assertNotIn("eval_size_n", theirs)


# ---------------------------------------------------------------------------
# The mutation check. A procedure that returns green against known-broken code
# certifies nothing, and `flake_hunt` on this project once returned 18/18 clean
# against the commit holding the bug it was hunting.


class TheDetectorSeesTheBugTest(unittest.TestCase):
    """Put each defect back, one at a time, and watch the right thing happen."""

    def setUp(self):
        self.root = support.sandbox(self)
        evidence.ensure_table()
        self.path = eval_file(self.root)

    def without_the_check(self):
        """Revert wall 5's second half in `record`, leaving the store's."""
        saved = evidence.names_a_conversation
        evidence.names_a_conversation = lambda thread_id: True
        self.addCleanup(setattr, evidence, "names_a_conversation", saved)

    def without_the_foreign_key(self):
        """Rebuild `fact_evidence` in its pre-migration-7 shape."""
        with db.session() as connection:
            connection.execute("ALTER TABLE fact_evidence RENAME TO fact_evidence_v6")
            connection.execute(
                "CREATE TABLE fact_evidence ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, thread_id INTEGER, "
                "fact TEXT NOT NULL, value TEXT NOT NULL, origin TEXT NOT NULL, "
                "actor TEXT NOT NULL, tool TEXT, how TEXT NOT NULL, "
                "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            connection.execute("DROP TABLE fact_evidence_v6")
        saved = evidence.ensure_table
        evidence.ensure_table = lambda: None  # it would put the constraints back
        self.addCleanup(setattr, evidence, "ensure_table", saved)

    def seed(self):
        return REGISTRY.call(
            "measure_eval_set",
            {"path": str(self.path)},
            actor=USER,
            thread_id=THE_ID_THE_FIRST_CONVERSATION_WILL_GET,
        )

    def test_with_both_halves_the_refusal_is_a_sentence(self):
        with self.assertRaises(ScopeError) as caught:
            self.seed()
        self.assertIn("G0_EVAL_SET", str(caught.exception))

    def test_with_the_check_reverted_the_store_still_refuses(self):
        """THE ARGUMENT FOR THE FOREIGN KEY, run rather than asserted. The
        sentence is gone - this is `FOREIGN KEY constraint failed` and it names
        nothing - and the leak is still shut."""
        self.without_the_check()
        with self.assertRaises(sqlite3.IntegrityError) as caught:
            self.seed()
        self.assertIn("FOREIGN KEY", str(caught.exception))
        self.assertEqual(ledger_rows(), [])

    def test_with_both_reverted_the_original_defect_is_back(self):
        """THE POSITIVE CONTROL FOR THIS WHOLE FILE. Without it, every refusal
        above could be a refusal of something that was never possible."""
        self.without_the_check()
        self.without_the_foreign_key()
        result = self.seed()
        self.assertEqual(result["rows"], ROWS)

        thread = events.create_thread("the first conversation")
        self.assertEqual(thread["id"], THE_ID_THE_FIRST_CONVERSATION_WILL_GET)
        facts, _trail = evidence.assemble_facts(thread["id"])
        self.assertEqual(facts["eval_size_n"].value, ROWS)
        self.assertEqual(facts["eval_size_n"].origin, MEASURED)

        outcome, gates = verdict(thread["id"])
        self.assertEqual(outcome, "TRAIN__LORA_SFT")
        self.assertEqual(set(gates.values()), {"PASSED"})
        self.assertEqual(len(gates), 5)

    def test_reverting_the_read_path_puts_the_sql_leak_back(self):
        """DEFECT 2's detector. `record()` is not involved in either direction."""
        thread = events.create_thread("a conversation that counted nothing")
        insert_a_row_with_sql()

        blocked, gates = verdict(thread["id"])
        self.assertEqual(blocked, "BLOCKED__BUILD_EVAL_SET")
        self.assertEqual(gates["G0_EVAL_SET"], "FAILED")

        saved = evidence.rows_for
        evidence.rows_for = lambda thread_id: (
            evidence._ledger_rows("WHERE thread_id IS NULL", ())
            if thread_id is None
            else evidence._ledger_rows(
                "WHERE thread_id IS NULL OR thread_id = ?", (int(thread_id),)
            )
        )
        self.addCleanup(setattr, evidence, "rows_for", saved)

        leaked, gates = verdict(thread["id"])
        self.assertEqual(leaked, "TRAIN__LORA_SFT")
        self.assertEqual(set(gates.values()), {"PASSED"})


# ---------------------------------------------------------------------------
# The opposite failure. A gate nothing can open is not a gate.


class TheHonestPathIsUnchangedTest(unittest.TestCase):
    """Everything this change must not have narrowed, measured rather than argued."""

    def setUp(self):
        self.root = support.sandbox(self)
        evidence.ensure_table()
        self.path = eval_file(self.root, rows=100, labels=5)
        row = provider_store.create(
            "Scripted", "http://127.0.0.1:11434", "scripted", "ollama"
        )
        provider_store.set_active(row["id"])
        original = measure.build
        measure.build = lambda *a, **k: ScriptedModel(correct=55)
        self.addCleanup(lambda: setattr(measure, "build", original))

    def test_the_machine_is_still_measurable_with_no_conversation_open(self):
        """A person looking at their own hardware page has no conversation and
        must not be made to invent one."""
        result = REGISTRY.call("inspect_hardware", {}, actor=USER, thread_id=None)
        self.assertTrue(result.get("measured_facts"), result)
        rows = ledger_rows()
        self.assertTrue(rows)
        self.assertTrue(all(row["thread_id"] is None for row in rows), rows)
        self.assertTrue(
            {row["fact"] for row in rows} <= set(evidence.facts_at_scope(MACHINE)),
            rows,
        )

    def test_its_four_facts_are_still_visible_in_every_conversation(self):
        if not support.a_gpu_was_measured():
            # FOUR is the count on a machine with a readable card. Without one
            # `inspect_hardware` stamps two, and this test's subject - that
            # machine-scope facts reach every conversation - is unchanged by
            # how many there are, so it is checked where there are four.
            self.skipTest(support.NO_GPU_HERE)
        REGISTRY.call("inspect_hardware", {}, actor=USER, thread_id=None)
        written = {row["fact"] for row in ledger_rows()}
        self.assertEqual(written, set(evidence.facts_at_scope(MACHINE)))
        self.assertEqual(len(written), 4, written)
        for thread in support.conversations(3):
            with self.subTest(thread=thread["id"]):
                facts, _trail = evidence.assemble_facts(thread["id"])
                self.assertTrue(written <= set(facts), facts)

    def test_counting_a_real_file_in_a_real_conversation_opens_the_first_gate(self):
        thread = events.create_thread("a conversation doing real work")
        result = REGISTRY.call(
            "measure_eval_set",
            {"path": str(self.path), "finish_the_count": True},
            actor=USER,
            thread_id=thread["id"],
        )
        self.assertEqual(result["rows"], 100)
        facts, _trail = evidence.assemble_facts(thread["id"])
        self.assertEqual(facts["eval_size_n"].origin, MEASURED)

    def test_the_honest_path_still_mints_train_lora_sft_with_five_gates(self):
        """THE WHOLE PRODUCT, THROUGH THE REAL TOOLS, IN ONE CONVERSATION.

        Count the file, score the baseline against a scripted model, say the
        things only the user can say, and walk the tree. Both numbers below are
        arithmetic over a file this test wrote: 100 rows over five equal classes,
        and a model right on 55 of them.
        """
        thread = events.create_thread("a conversation doing real work")
        counted = REGISTRY.call(
            "profile_dataset",
            {"path": str(self.path), "split": "eval", "max_rows": 100},
            actor=USER,
            thread_id=thread["id"],
        )
        self.assertEqual(counted["measured_facts"][0]["value"], 100)
        scored = REGISTRY.call(
            "measure_baseline",
            {
                "eval_path": str(self.path),
                "input_field": "q",
                "expected_field": "a",
                "sample": 100,
            },
            actor=USER,
            thread_id=thread["id"],
        )
        self.assertTrue(scored["ok"], scored.get("summary"))
        self.assertEqual(scored["baseline_score"], 0.55)

        spec = diagnosis.default_spec()
        sheet = {
            name: diagnosis.bare(value)
            for name, value in fixtures.MINTING["TRAIN__LORA_SFT"].items()
        }
        asked = {
            name: value
            for name, value in sheet.items()
            if spec.facts[name]["source"] == "ask"
        }
        REGISTRY.call(
            "state_facts", {"facts": asked}, actor=USER, thread_id=thread["id"]
        )
        result = REGISTRY.call(
            "run_diagnosis",
            {"facts": sheet},
            actor=evidence.MODEL,
            thread_id=thread["id"],
        )
        self.assertEqual(result["outcome"], "TRAIN__LORA_SFT", result.get("say"))
        self.assertEqual(len(result["gate_ledger"]), 5, result["gate_ledger"])
        for gate, entry in result["gate_ledger"].items():
            self.assertEqual(entry["status"], "PASSED", gate)
        self.assertEqual(result["fact_origins"]["eval_size_n"], MEASURED)
        self.assertEqual(result["fact_origins"]["baseline_score"], MEASURED)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
