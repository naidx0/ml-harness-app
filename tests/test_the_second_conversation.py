"""The suite had one conversation, so it could not tell scoped from global.

## The class, not the instance

A first-gate bypass sat in `evidence.record` for three commits with 1057 tests
green over it, and the finder's account of why is a statement about this suite
rather than about that function:

> the suite cannot see it because `support.sandbox()` gives every test a clean
> ledger and tests always pass a thread_id

Half of that is an argument nobody supplies. The other half is deeper and has no
missing-argument fix: **a record scoped to one conversation and a record visible
to every conversation are indistinguishable when there is only ever one
conversation to look at.** Every test in this repository ran in a fresh database
with at most one thread in it. Under that shape, a table with a `thread_id`
column and a table with no scope column at all produce identical observations,
so no assertion anybody could have written would have separated them.

That is not one missing case. It is a family, and this file is the shape of the
test that sees the family: two conversations, in two projects, doing the same
work, and then asking each what it can see of the other.

`support.conversations()` exists so that costs one line.

## What the sweep found

`app/tools/context.py` keeps attachments in a `contexts` table with **no scope
column of any kind** - no `thread_id`, no `project_id`. Both of its tools say
otherwise in the text a model reads:

    attach_context: "Record a folder, a file or a git repository as part of
                     THIS PROJECT, so the harness can refer to it later."
    list_context:   "List everything attached to THIS PROJECT so far."

So a folder attached in one project, with the role its owner typed, is returned
verbatim to a model running in a different project's conversation. It is the
same omission as the eval-set leak wearing different clothes: a record that is
genuinely written, genuinely stored, and attached to nothing that says where it
belongs.

`test_context_tools.py` cannot see it and never could. It calls
`REGISTRY.call("attach_context", ...)` and `REGISTRY.call("list_context")` with
no thread and no project, because in a sandbox there is only one of each - and
under that shape the leak and the correct behaviour print the same thing.

## How an open defect is recorded here

Same idiom as `tests/test_laundering_routes.py`, for the same reasons.
`@open_defect(...)` marks a test that fails against the product as it stands,
names the defect in `OPEN_DEFECTS`, and is an `expectedFailure` rather than a
skip: a skip measures nothing and reads as green at a glance, while an expected
failure runs the probe, watches the leak happen, and is counted on its own line.
When somebody scopes the table, `unittest` reports an unexpected success and the
build goes red, so the decorator cannot be left behind.

`EveryOpenDefectFailsForTheRightReasonTest` re-runs each one and reads the
traceback, because `expectedFailure` swallows a crash in a probe's own
scaffolding exactly as happily as it swallows the leak.

## The controls

A cross-conversation probe that finds a leak everywhere is not a detector, it is
a broken fixture. `ScopedRecordsAreNotVisibleSidewaysTest` runs the same shape
against the records the product scopes correctly - messages, events, threads -
and they must come back separated. If those fail, the open defect below is
passing on a technicality.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Callable

from app import events
from app.tools import REGISTRY

import support


#: Defect id -> what is unscoped, in one line. Filled by the decorator.
OPEN_DEFECTS: dict[str, str] = {}

#: How many cross-conversation leaks are open. ONE at the commit this file was
#: written against. Lower it in the same diff that deletes an `@open_defect`
#: line; raising it needs a reason written next to it.
#: 1 -> 0 on 2026-09-11: `contexts_are_machine_wide` closed - see the
#: `contexts` entry in STORE_SCOPE for how, and why at the thread.
OPEN_DEFECTS_NOW = 0


def open_defect(defect: str, what: str) -> Callable[[Callable], Callable]:
    """Mark one probe as CURRENTLY LEAKING, by name and with a reason."""

    def decorate(method: Callable) -> Callable:
        if defect in OPEN_DEFECTS:
            raise AssertionError(f"{defect} is declared open twice")
        OPEN_DEFECTS[defect] = what
        method.open_defect = defect  # type: ignore[attr-defined]
        return unittest.expectedFailure(method)

    return decorate


class TwoConversationsTestCase(unittest.TestCase):
    """Two projects, two threads, and a private folder in the first one."""

    def setUp(self):
        self.root = support.sandbox(self)
        self.alice, self.bob = support.conversations(2)

        self.private = self.root / "alice-private"
        self.private.mkdir()
        (self.private / "records.jsonl").write_text(
            '{"patient": 1}\n' * 7, encoding="utf-8"
        )


class TheFixtureIsWhatMakesTheProbePossibleTest(TwoConversationsTestCase):
    """Before asserting about leaks, assert the two conversations are two."""

    def test_the_two_conversations_are_separate_threads_in_separate_projects(self):
        self.assertNotEqual(self.alice["id"], self.bob["id"])
        self.assertNotEqual(
            self.alice["project"]["id"], self.bob["project"]["id"]
        )
        self.assertEqual(self.alice["project_id"], self.alice["project"]["id"])
        self.assertEqual(self.bob["project_id"], self.bob["project"]["id"])

    def test_a_sandbox_without_the_fixture_has_no_conversation_at_all(self):
        """Why the leak was invisible, stated as a fact about the old shape.

        A bare sandbox holds zero threads. Every test that called a tool without
        a `thread_id` was not choosing a conversation - there was none to
        choose - so "visible in this conversation" and "visible in all of them"
        were the same observation.
        """
        fresh = support.sandbox(self)
        self.assertTrue(Path(fresh).is_dir())
        # A second sandbox rebinds the database; this one starts empty again.
        self.assertEqual(events.list_threads(), [])


class ScopedRecordsAreNotVisibleSidewaysTest(TwoConversationsTestCase):
    """THE CONTROLS. Where the product scopes a record, the probe must agree."""

    def test_a_message_stays_in_the_conversation_it_was_typed_in(self):
        events.add_message(self.alice["id"], "user", "my eval set is at C:/secret")

        self.assertEqual(
            [row["content"] for row in events.messages_for(self.bob["id"])],
            [],
            "the transcript is thread-scoped and this probe says it is not, so "
            "the fixture is wrong rather than the product",
        )
        self.assertEqual(len(events.messages_for(self.alice["id"])), 1)

    def test_an_event_stays_in_the_conversation_it_was_appended_to(self):
        events.append("probe.control", {"n": 1}, thread_id=self.alice["id"])

        self.assertEqual(events.since(f"thread:{self.bob['id']}"), [])
        self.assertEqual(len(events.since(f"thread:{self.alice['id']}")), 1)

    def test_a_thread_belongs_to_one_project(self):
        alices = events.list_threads(project_id=self.alice["project"]["id"])
        bobs = events.list_threads(project_id=self.bob["project"]["id"])

        self.assertEqual([row["id"] for row in alices], [self.alice["id"]])
        self.assertEqual([row["id"] for row in bobs], [self.bob["id"]])


class AttachedContextIsVisibleInEveryConversationTest(TwoConversationsTestCase):
    """The open defect. `contexts` has no scope column, and the tools claim one.

    Both halves are asserted, because either alone is arguable. The tools SAY
    "this project" - so the promise exists - and the table HAS no column that
    could keep it. A leak with no promise behind it is a design decision; a
    promise with no column behind it is a defect.
    """

    def test_the_tools_promise_a_project_scope(self):
        """Not the defect - the reason the next one is a defect and not a choice."""
        attach = REGISTRY.get("attach_context")
        listing = REGISTRY.get("list_context")

        self.assertIn("this project", attach.description)
        self.assertIn("this project", listing.description)
        self.assertIn("this project", listing.control.verb)

    def test_the_contexts_table_has_the_column_that_keeps_that_promise(self):
        """The mechanism, read off the schema rather than inferred from a symptom.

        This used to assert the column was ABSENT, as the record of the open
        defect; it flipped on 2026-09-11 when the column arrived. The two
        tests after it are what prove the column is populated and read.
        """
        from app import db
        from app.tools import context as context_tools

        context_tools.ensure_contexts_table()
        with db.session() as connection:
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(contexts)")
            }

        self.assertIn("thread_id", columns)

    # CLOSED 2026-09-11. This carried `@open_defect("contexts_are_machine_wide", ...)`:
    # attachments in a `contexts` table with no thread_id and no project_id, so
    # `list_context` returned every project's attachments to every conversation.
    # The fix is the scope column above plus the filter in
    # `context.list_contexts(thread_id)`, and the registry hands the tool the
    # calling thread. The probe is unchanged and now passes on its own.
    def test_a_folder_attached_in_one_project_is_not_offered_to_another(self):
        attached = REGISTRY.call(
            "attach_context",
            {
                "path": str(self.private),
                "role": "confidential patient records",
                "note": "do not share",
            },
            actor="user",
            thread_id=self.alice["id"],
        )
        self.assertTrue(attached["ok"])

        seen = REGISTRY.call(
            "list_context", {}, actor="model", thread_id=self.bob["id"]
        )

        self.assertEqual(
            [row["path"] for row in seen["contexts"]],
            [],
            "contexts_are_machine_wide: a folder attached in "
            f"{self.alice['project']['name']!r} was returned to a model running "
            f"in {self.bob['project']['name']!r}. Roles seen: "
            f"{[row['role'] for row in seen['contexts']]}",
        )

    def test_the_owning_conversation_still_sees_its_own_attachment(self):
        """The opposite failure. A scope that hides everything is not a scope.

        Whoever closes the defect above must keep this green: the leak is
        `list_context` showing too much, and the fix is not showing nothing.
        """
        REGISTRY.call(
            "attach_context",
            {"path": str(self.private), "role": "the eval data"},
            actor="user",
            thread_id=self.alice["id"],
        )

        seen = REGISTRY.call(
            "list_context", {}, actor="model", thread_id=self.alice["id"]
        )

        self.assertEqual(seen["count"], 1)
        self.assertEqual(seen["contexts"][0]["role"], "the eval data")


#: Every store a registered tool declares it writes to, and what keeps a record
#: in it from being seen by a conversation that did not produce it. DERIVED
#: against the live registry by the test below, so a tool added next year with a
#: `writes=` nobody has classified fails here rather than leaking quietly.
#:
#: This is the roster the eval-set leak would have appeared on. Reading it is the
#: cheapest way to ask "which of the product's records are conversation-shaped",
#: which is the question a suite with one conversation cannot ask at all.
STORE_SCOPE: dict[str, str] = {
    "events": "scoped: the events table carries thread_id and project_id",
    "facts": "scoped: fact_evidence carries thread_id",
    "contexts": (
        "scoped: contexts carries thread_id since 2026-09-11. It was the open "
        "defect `contexts_are_machine_wide` - no scope column at all, so every "
        "attachment appeared in every conversation, which the owner named as "
        "the bug. The scope landed at the THREAD rather than the project the "
        "defect proposed: he asked for chat-specific, and a thread is strictly "
        "inside its project, so the recorded assertion holds either way. The "
        "column is added by the table's own owner, `ensure_contexts_table`, "
        "not by a migration - the table itself is made on first ask, and a "
        "migration altering it broke every fresh database. Rows from before "
        "the column carry NULL and appear only in an unscoped listing."
    ),
    "threads": (
        "scoped: the threads row IS the conversation. `write_plan` and "
        "`read_plan` write and read one column, `plan`, of the calling "
        "thread's own row, resolved from the thread_id the call arrived "
        "with - the registry fills it in, the model never names it. Nothing "
        "here can reach another thread's row."
    ),
    "project": (
        "PROJECT SCOPE, which is a third answer this table did not have before "
        "and is the honest one. `set_the_project_root` writes one column of one "
        "row of `projects`, and a project is neither a conversation nor the "
        "machine: it is the thing conversations are grouped INTO. Every thread "
        "carries `project_id` (migration v004) and `events.create_thread` puts "
        "one there even when the caller does not, so 'which project' is always "
        "answerable from a thread - which is exactly how the tool resolves it. "
        "THE RESIDUE, NAMED RATHER THAN LEFT TO BE FOUND: a second conversation "
        "IN THE SAME PROJECT sees the root the first one set, and that is the "
        "point rather than a leak - a project root is a property of the project "
        "and `docs/PRODUCT_SPEC.md` 4.3 says every run inherits what is at it. "
        "A conversation in a DIFFERENT project sees nothing, because the write "
        "names a project id and the read resolves one from its own thread."
    ),
    "memory": (
        "PROJECT SCOPE for the notes and MACHINE SCOPE for the profile, and "
        "both on purpose (`app/memory.py`, 2026-09-11). `remember` writes one "
        "of two targets: `project` rows carry `project_id`, resolved from the "
        "thread the call arrived with - the registry fills it in, the model "
        "never names it - so a second conversation IN THE SAME PROJECT reads "
        "what the first one remembered, which is the feature (Hermes' "
        "MEMORY.md, per project), and a conversation in another project reads "
        "nothing. `user` rows carry NULL and are the one profile of the one "
        "person at this machine (Hermes' USER.md); they are about the person, "
        "not about a project, and are on every prompt by design. THE RESIDUE, "
        "NAMED: an entry the model writes is read by every later thread of the "
        "project, so the number rule applies at the door - a figure with no "
        "origin word is refused - and the pane shows every row for the person "
        "to prune."
    ),
    "jobs": (
        "machine scope on purpose: a job is a process on this box, the job "
        "queue is one queue, and `training_status` is asked about a job id the "
        "caller already has rather than handed the list"
    ),
    "runs": (
        "machine scope on purpose: `list_runs` says so in its own source line "
        "- 'the runs table in this harness database' - and a training run is a "
        "thing that happened on this machine rather than a claim about a project"
    ),
    "filesystem": (
        "machine scope on purpose: a sandbox (`app/tools/sandbox.py`) is a "
        "directory on this disk under this database's own artifact root, the "
        "same kind of object as a `runs` row and a `jobs` row and classified "
        "the same way. It has to be: a pinned environment is gigabytes and the "
        "whole point of `list_sandboxes` is that an experiment is resumed "
        "rather than duplicated, which a per-conversation list could not do "
        "across a restart. THE RESIDUE, NAMED RATHER THAN LEFT TO BE FOUND: a "
        "sandbox holds a COPY of the data it was given, so the listing shows a "
        "second conversation the source paths, sizes and digests of files the "
        "first one snapshotted. Not the bytes - nothing here reads a snapshot "
        "back out - and the same shape of exposure `runs` already carries, "
        "where a training run's params name the dataset it trained on. If that "
        "becomes unacceptable it becomes unacceptable for all three together, "
        "and the answer is a thread_id in the manifest and a filter in "
        "`every()`, not a special case for this one."
    ),
    "datasets": (
        "NOT A STORE AT ALL, which is why it gets its own row rather than "
        "riding on `filesystem`. `carve_eval_set` and `drop_duplicates` "
        "(app/tools/datawork.py) write files into a directory THE PERSON "
        "NAMED, outside the artifact root and outside anything this product "
        "owns. There is no table, no id and no listing tool: nothing in the "
        "harness can enumerate what a carve wrote, so there is no query a "
        "second conversation could run to find it. The only record that a "
        "directory exists is the reply in the conversation that asked for it "
        "and the manifest inside the directory itself, which is why "
        "`datawork` writes one. THE RESIDUE, NAMED RATHER THAN LEFT TO BE "
        "FOUND: those files sit on a shared disk, so anyone who already has "
        "the path can read them - which is equally true of the source data "
        "they were split from, and is not something this product mediates or "
        "could. `filesystem` is declared beside it on the same two tools and "
        "means something different: that is WHERE (a path on this disk), and "
        "this is WHAT (the user's own data, copied). The second needed saying "
        "separately because `filesystem`'s note below is about sandboxes "
        "under the artifact root, and quietly widening it to cover somebody's "
        "home directory is exactly what this roster exists to stop."
    ),
    "model_config_cache": (
        "machine scope on purpose: a model's config.json is the same file "
        "whoever asks, and caching it per conversation would refetch it for "
        "every new thread"
    ),
    "evals": (
        "scoped: eval_runs carries thread_id as a NOT NULL foreign key to "
        "threads, and eval_results hangs off eval_runs, so a per-row result "
        "reaches a conversation only through a run that names one. Both readers "
        "check it - run_eval will not reuse a run from another conversation and "
        "read_eval_results refuses a run id that is not this thread's, on both "
        "ids of a comparison. It has to be scoped: a run holds the user's own "
        "eval rows and the model's answers to them, and every fact it produces "
        "is declared scope: thread in docs/diagnosis_engine.yaml"
    ),
    "prompts": (
        "scoped: prompt_lines carries thread_id as a NOT NULL foreign key to "
        "threads with ON DELETE CASCADE, and prompt_variants, prompt_scores and "
        "prompt_champions all hang off a line, so a stored prompt reaches a "
        "conversation only through a line that names one. Both readers check it "
        "- try_prompt looks a line up by (thread_id, name) and read_prompt_bench "
        "refuses a line id that is not this thread's. It has to be scoped: a "
        "variant carries the user's own prompt and the run that scored it holds "
        "their eval rows, and docs/PRODUCT_SPEC.md 6.5 is explicit that this is "
        "the thread's lab notebook and not a registry anything else can read"
    ),
    "retrieval": (
        "scoped: retrieval_indexes carries thread_id as a NOT NULL foreign key "
        "to threads with ON DELETE CASCADE, and retrieval_documents, "
        "retrieval_passages and retrieval_postings all hang off an index, so a "
        "passage reaches a conversation only through an index that names one. "
        "Every reader checks it - build_retrieval_index will not reuse or "
        "replace an index from another conversation, and search_the_index and "
        "measure_retriever_recall both go through `retrieval._index_for`, which "
        "refuses an index id that is not this thread's and defaults to this "
        "thread's most recent. IT HAS TO BE SCOPED, and more obviously than any "
        "other row here: an index holds THE TEXT of the user's own documents, "
        "so an unscoped one would let a second conversation retrieve the "
        "contents of the first one's corpus by typing a query. That is the "
        "eval-set leak with a search box on it"
    ),
}


class EveryStoreAToolWritesHasADeclaredScopeTest(unittest.TestCase):
    """The derived half. The instance above is one row of this table.

    A suite that can only see the leak it was told about will be told about the
    next one by a user. `writes=` on a `ToolSpec` already names every store the
    product writes through, and the registry already holds every tool - so the
    list of places a conversation-shaped record could leak from is derivable
    rather than remembered.
    """

    def setUp(self):
        support.sandbox(self)

    def test_every_declared_store_is_classified(self):
        declared = {store for spec in REGISTRY for store in spec.writes}

        unclassified = sorted(declared - set(STORE_SCOPE))
        self.assertEqual(
            unclassified,
            [],
            "a registered tool writes to a store whose scope nobody has "
            "written down. Say in STORE_SCOPE whether a record in it belongs to "
            "one conversation or to the machine, and if it belongs to one "
            "conversation, that the table has a column saying which.\n\n"
            f"Unclassified: {unclassified}",
        )

        stale = sorted(set(STORE_SCOPE) - declared)
        self.assertEqual(
            stale,
            [],
            f"STORE_SCOPE names stores no tool writes to any more: {stale}",
        )

    def test_the_stores_called_scoped_really_have_a_scope_column(self):
        """Not the roster's word for it - the schema's.

        `facts`, `events`, `evals`, `prompts` and `retrieval` are classified as
        scoped. If any of them loses its column, the classification is a comment
        rather than a fact, and this is where that is caught.
        """
        from app import db
        from app.tools import evidence as evidence_tools

        evidence_tools.ensure_table()
        tables = {
            "facts": "fact_evidence",
            "events": "events",
            "evals": "eval_runs",
            "prompts": "prompt_lines",
            "retrieval": "retrieval_indexes",
        }
        for store, table in tables.items():
            with self.subTest(store=store):
                self.assertIn("scoped", STORE_SCOPE[store])
                with db.session() as connection:
                    columns = {
                        row[1]
                        for row in connection.execute(f"PRAGMA table_info({table})")
                    }
                self.assertIn(
                    "thread_id",
                    columns,
                    f"{table} is classified as thread-scoped and has no "
                    "thread_id column",
                )


class TheOpenDefectRosterIsHonestTest(unittest.TestCase):
    def test_the_count_matches_the_decorations(self):
        self.assertEqual(
            len(OPEN_DEFECTS),
            OPEN_DEFECTS_NOW,
            "OPEN_DEFECTS_NOW disagrees with the @open_defect lines in this "
            "file. Change both in one diff, with the reason.",
        )


class EveryOpenDefectFailsForTheRightReasonTest(unittest.TestCase):
    """`expectedFailure` swallows a broken probe exactly as it swallows a leak.

    Each open defect is re-run through a fresh `TestResult` and its traceback is
    read: it must be the probe's own assertion and it must name the defect. That
    makes every open defect a positive control in its own right - live proof
    that the two-conversation fixture can actually see a leak - for as long as
    it stays open.
    """

    def test_each_open_defect_fails_on_its_own_assertion(self):
        case = AttachedContextIsVisibleInEveryConversationTest
        methods = {
            name: function
            for name, function in vars(case).items()
            if getattr(function, "open_defect", None)
        }
        self.assertEqual(
            sorted(getattr(f, "open_defect") for f in methods.values()),
            sorted(OPEN_DEFECTS),
            "an @open_defect decoration did not land on a test method",
        )

        for name, function in sorted(methods.items()):
            defect = getattr(function, "open_defect")
            with self.subTest(defect=defect):
                result = unittest.TestResult()
                case(name).run(result)

                self.assertEqual(
                    len(result.expectedFailures),
                    1,
                    f"{defect} did not leak - it is closed, so delete its "
                    "@open_defect line and lower OPEN_DEFECTS_NOW",
                )
                _, trace = result.expectedFailures[0]
                self.assertIn(
                    "AssertionError",
                    trace,
                    f"{defect} raised something other than its own assertion, "
                    f"so expectedFailure is hiding a broken probe:\n{trace}",
                )
                self.assertIn(
                    defect,
                    trace,
                    f"{defect} failed on a different assertion than the one "
                    f"that names it:\n{trace}",
                )


if __name__ == "__main__":
    unittest.main()
