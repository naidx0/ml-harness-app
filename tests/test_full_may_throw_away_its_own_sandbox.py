"""Under Full a thread may delete the scratch box it made, and nothing else.

Max, 2026-09-18: *"under permission full, delete_sandbox auto-approves when the
sandbox was created by this thread's own run AND the sandbox does not hold the
eval run the thread's baseline was measured in. Any other sandbox still asks."*

## What it replaces

`FULL_NEVER = {delete_sandbox}` was the whole rule: Full was a zero-ask bypass
for every gated tool except the irreversible wipe. That is right about a
sandbox somebody spent an hour building and wrong about the one the run made
itself ten turns ago to try something in - a run that cannot tidy up stops and
asks the person to press a button about a directory they have never heard of,
which is the opposite of what Full is for.

## The two halves, and why both are read off disk

**It must be this thread's own.** The manifest records `thread_id` at the
moment the sandbox is made, because there is no later moment at which it can be
worked out: a directory cannot be asked which conversation asked for it. A
sandbox made before that field existed has no maker recorded, and a box that
belongs to nobody in particular is not this thread's - it asks.

**Nothing measured may live in it.** Two checks, and the second one is an
admission. An ADAPTER is the artefact nothing can give back: hours of this
machine's card, and the thing any score measured in that box was measured on.
And `eval_runs` records the thread, the file, the metric and the provider - but
NOT the sandbox, so from a row alone nothing can say which box a sandbox-arm
run happened in. So it does not guess: a thread with any completed sandbox-arm
run has ALL of its sandboxes protected. Being wrong that way costs a question;
being wrong the other way costs the measurement and the weights behind it,
after the number is already quoted in the transcript.

## Where the decision is taken

`app/autonomy.may_run` takes the answer as a parameter and stays what it has
always been: a policy table with no imports. `app/conductor._run_tool` asks
`app/tools/sandbox.deletable_without_asking`, once, into the SAME boolean it
writes to `tool.call` and hands the registry - so the transcript and the run
cannot disagree about whether anybody was asked.
"""

from __future__ import annotations

import unittest

from app import autonomy, conductor, events
from app.tools import sandbox as sandboxes
import support


def _a_sandbox_of(thread_id, name: str) -> dict:
    """A real sandbox, made the way `make_sandbox` makes one.

    Through `create` with the thread named, rather than by writing a manifest
    by hand: what is being tested is that the field the product writes is the
    field the rule reads, and a hand-written manifest would assert only that
    this test can spell.
    """
    return sandboxes.create(name, thread_id=thread_id, purpose="a scratch box")


def _an_adapter_in(name: str) -> None:
    """Put a trained adapter where `find_the_adapter` looks for one."""
    manifest = sandboxes.read_manifest(name)
    runs = sandboxes.folder(manifest, "runs_dir", sandboxes.RUNS)
    adapter = runs / "run_1" / "adapter"
    adapter.mkdir(parents=True, exist_ok=True)
    (adapter / "adapter_config.json").write_bytes(b'{"r": 16}')


class TheRuleReadsTheManifestAndTheBoxTest(unittest.TestCase):
    """`deletable_without_asking`, on its own, with real sandboxes."""

    def setUp(self):
        support.sandbox(self)
        self.thread = int(events.create_thread("mine", None)["id"])

    def test_its_own_empty_scratch_box_is_deletable(self):
        _a_sandbox_of(self.thread, "scratch")
        answer, why = sandboxes.deletable_without_asking("scratch", self.thread)
        self.assertTrue(answer, why)
        self.assertEqual(sandboxes.ITS_OWN_AND_EMPTY_HANDED, why)

    def test_another_threads_box_is_not(self):
        other = int(events.create_thread("somebody else", None)["id"])
        _a_sandbox_of(other, "theirs")
        answer, why = sandboxes.deletable_without_asking("theirs", self.thread)
        self.assertFalse(answer)
        self.assertEqual(sandboxes.NOT_ITS_OWN, why)

    def test_a_box_made_before_makers_were_recorded_is_not(self):
        """Every sandbox on Max's disk today is one of these. They belong to
        nobody in particular, and nobody in particular is not this thread."""
        _a_sandbox_of(None, "older")
        answer, why = sandboxes.deletable_without_asking("older", self.thread)
        self.assertFalse(answer)
        self.assertEqual(sandboxes.MADE_BEFORE_MAKERS_WERE_RECORDED, why)

    def test_a_box_holding_an_adapter_is_not(self):
        """Hours of the card, and the thing any score in that box measured."""
        _a_sandbox_of(self.thread, "trained")
        _an_adapter_in("trained")
        answer, why = sandboxes.deletable_without_asking("trained", self.thread)
        self.assertFalse(answer)
        self.assertEqual(sandboxes.IT_HOLDS_AN_ADAPTER, why)

    def test_a_name_that_resolves_to_nothing_is_not(self):
        """"Cannot tell" is never "yes" for the one irreversible tool here."""
        answer, why = sandboxes.deletable_without_asking(
            "never-made", self.thread
        )
        self.assertFalse(answer)
        self.assertEqual(sandboxes.NO_SUCH_SANDBOX_TO_JUDGE, why)

    def test_a_path_shaped_name_is_not(self):
        """The same refusal `delete_sandbox` itself gives, reached earlier."""
        answer, _why = sandboxes.deletable_without_asking(
            "../not-a-sandbox", self.thread
        )
        self.assertFalse(answer)

    def test_the_reason_is_a_sentence_either_way(self):
        """It goes on the record. "The harness decided" is not an answer to
        somebody reading back a wipe that needed no click."""
        _a_sandbox_of(self.thread, "scratch")
        for name in ("scratch", "never-made"):
            with self.subTest(sandbox=name):
                _answer, why = sandboxes.deletable_without_asking(
                    name, self.thread
                )
                self.assertGreater(len(why.split()), 5, why)


class AMeasuredThreadProtectsAllOfItsBoxesTest(unittest.TestCase):
    """The admission: an eval row does not name the sandbox it ran in."""

    def setUp(self):
        support.sandbox(self)
        self.thread = int(events.create_thread("measured", None)["id"])

    def _a_sandbox_arm_run(self, *, graded: bool) -> None:
        """A completed eval run marked the way a sandbox arm is marked.

        `evals.SANDBOX_ARM_PREFIX` on the provider name, which is the product's
        own mark and the only thing in the row that says no connection produced
        these answers. Read from the module rather than written as `"sandbox:"`,
        because two literals in two places is how a mark stops being read.
        """
        from app.tools import evals

        run = evals.create_run(
            thread_id=int(self.thread),
            signature="an-arm",
            eval_path="rows.jsonl",
            eval_fingerprint="fingerprint",
            input_field="q",
            expected_field="a",
            metric=evals.EXACT_MATCH,
            prompt="",
            prompt_is_default=0,
            provider_id=None,
            provider_name=f"{evals.SANDBOX_ARM_PREFIX}adapter",
            model="an-adapter",
            locality="local",
            judge_model=None,
            planned=2,
            rows_available=2,
            trivial_baseline=0.5,
            trivial_answer="yes",
            latency_budget_ms=None,
        )
        if not graded:
            return
        for index in range(2):
            evals.record_row(
                int(run["id"]),
                index,
                question=f"question {index}",
                expected="yes",
                answer="yes",
                correct=True,
                verdicts={"exact_match": True},
                failure_mode=None,
                graded_by=evals.EXACT_MATCH,
                seconds=0.1,
            )

    def test_a_completed_sandbox_arm_protects_an_empty_box_too(self):
        _a_sandbox_of(self.thread, "scratch")
        self._a_sandbox_arm_run(graded=True)
        answer, why = sandboxes.deletable_without_asking("scratch", self.thread)
        self.assertFalse(answer)
        self.assertEqual(sandboxes.IT_HOLDS_A_MEASUREMENT, why)

    def test_a_run_row_with_no_graded_rows_is_not_a_measurement(self):
        """A run row is written BEFORE any grading, so a row on its own is an
        intention. Protecting on it would mean a started-and-abandoned scoring
        locked the thread's scratch boxes for ever."""
        _a_sandbox_of(self.thread, "scratch")
        self._a_sandbox_arm_run(graded=False)
        answer, why = sandboxes.deletable_without_asking("scratch", self.thread)
        self.assertTrue(answer, why)

    def test_a_baseline_measured_through_a_connection_does_not_protect(self):
        """THE CONTROL, and it is what stops this rule being vacuous the other
        way. `measure_baseline` scores through a CONNECTION - its run is not a
        sandbox arm - and a thread that measured a baseline has still not
        measured anything inside a box."""
        _a_sandbox_of(self.thread, "scratch")
        support.a_completed_eval_run(self.thread, "rows.jsonl", rows=4)
        answer, why = sandboxes.deletable_without_asking("scratch", self.thread)
        self.assertTrue(answer, why)


class TheModeDecidesTest(unittest.TestCase):
    """`autonomy.may_run`, which is where the ladder step is applied."""

    def test_full_deletes_its_own(self):
        self.assertTrue(
            autonomy.may_run("full", "delete_sandbox", own_sandbox=True)
        )

    def test_full_still_asks_for_anything_else(self):
        self.assertFalse(
            autonomy.may_run("full", "delete_sandbox", own_sandbox=False)
        )

    def test_write_always_asks(self):
        """Full is the mode the person opted into for a zero-ask run. Write is
        additive workspace writes, and a delete is not additive."""
        self.assertFalse(
            autonomy.may_run("write", "delete_sandbox", own_sandbox=True)
        )

    def test_measure_and_ask_always_ask(self):
        for mode in ("ask", "measure"):
            with self.subTest(mode=mode):
                self.assertFalse(
                    autonomy.may_run(mode, "delete_sandbox", own_sandbox=True)
                )

    def test_the_default_is_the_old_answer(self):
        """A caller that does not ask the question gets what it got before. A
        rule that opened a delete because somebody forgot an argument would be
        the wrong way round for the one irreversible tool here."""
        self.assertFalse(autonomy.may_run("full", "delete_sandbox"))

    def test_it_widens_nothing_else(self):
        """DERIVED, over every classified name: `own_sandbox` is about one
        tool, and a flag that quietly covered a second one would be exactly the
        wall-with-a-door this file is arguing against."""
        every = {**autonomy.UNATTENDED, **autonomy.NEVER_UNATTENDED}
        for mode in autonomy.MODES:
            for name in every:
                if mode == "full" and name == autonomy.OWN_SANDBOX_UNDER_FULL:
                    continue
                with self.subTest(mode=mode, tool=name):
                    self.assertEqual(
                        autonomy.may_run(mode, name),
                        autonomy.may_run(mode, name, own_sandbox=True),
                    )

    def test_the_exception_names_the_tool_it_is_about(self):
        self.assertEqual("delete_sandbox", autonomy.OWN_SANDBOX_UNDER_FULL)
        self.assertIn(autonomy.OWN_SANDBOX_UNDER_FULL, autonomy.FULL_NEVER)


class TheConductorTakesItOnceTest(unittest.TestCase):
    """The seam: one boolean, into the event and into the registry."""

    def setUp(self):
        support.sandbox(self)
        self.thread = int(events.create_thread("seam", None)["id"])

    def _call(self, name, arguments=None):
        class Call:
            id = "call-1"

        call = Call()
        call.name = name
        call.arguments = arguments or {}
        return call

    def _run(self, name, arguments, permission):
        return list(
            conductor._run_tool(
                self.thread,
                [],
                self._call(name, arguments),
                permission=permission,
            )
        )

    def test_full_deletes_its_own_box_with_no_approval(self):
        _a_sandbox_of(self.thread, "scratch")
        rows = self._run("delete_sandbox", {"name": "scratch"}, "full")
        results = [r for r in rows if r["kind"] == "tool.result"]
        self.assertNotEqual(
            "approval_required", results[-1]["payload"]["result"].get("error")
        )
        self.assertTrue(results[-1]["payload"]["result"].get("ok"), results[-1])
        self.assertEqual([], sandboxes.every(project_id=None))

    def test_another_threads_box_still_asks_under_full(self):
        other = int(events.create_thread("somebody else", None)["id"])
        _a_sandbox_of(other, "theirs")
        rows = self._run("delete_sandbox", {"name": "theirs"}, "full")
        results = [r for r in rows if r["kind"] == "tool.result"]
        self.assertEqual(
            "approval_required", results[-1]["payload"]["result"].get("error")
        )
        self.assertEqual(
            1, len(sandboxes.every(project_id=None)), "it was deleted anyway"
        )

    def test_under_write_its_own_box_still_asks(self):
        _a_sandbox_of(self.thread, "scratch")
        rows = self._run("delete_sandbox", {"name": "scratch"}, "write")
        results = [r for r in rows if r["kind"] == "tool.result"]
        self.assertEqual(
            "approval_required", results[-1]["payload"]["result"].get("error")
        )
        self.assertEqual(1, len(sandboxes.every(project_id=None)))

    def test_the_record_says_it_was_auto_approved_and_why(self):
        """A wipe that went through with no click is the row somebody reads
        afterwards asking how."""
        _a_sandbox_of(self.thread, "scratch")
        rows = self._run("delete_sandbox", {"name": "scratch"}, "full")
        call = [r for r in rows if r["kind"] == "tool.call"][-1]
        self.assertTrue(call["payload"]["auto_approved"])
        self.assertEqual(
            sandboxes.ITS_OWN_AND_EMPTY_HANDED, call["payload"]["own_sandbox"]
        )

    def test_the_record_says_why_it_asked_too(self):
        """A refusal with no reason is the log saying nothing."""
        other = int(events.create_thread("somebody else", None)["id"])
        _a_sandbox_of(other, "theirs")
        rows = self._run("delete_sandbox", {"name": "theirs"}, "full")
        call = [r for r in rows if r["kind"] == "tool.call"][-1]
        self.assertNotIn("auto_approved", call["payload"])
        self.assertEqual(sandboxes.NOT_ITS_OWN, call["payload"]["own_sandbox"])

    def test_every_other_tools_record_is_unchanged(self):
        """THE CONTROL ON THE EVENT. The reason key appears for one tool; a row
        for anything else must read back exactly as it did before."""
        rows = self._run("carve_rows", {}, "full")
        call = [r for r in rows if r["kind"] == "tool.call"][-1]
        self.assertNotIn("own_sandbox", call["payload"])


class TheMakerIsRecordedWhereItIsMadeTest(unittest.TestCase):
    """`make_sandbox` writes it, because nothing later can work it out."""

    def setUp(self):
        support.sandbox(self)
        self.thread = int(events.create_thread("maker", None)["id"])

    def test_the_tool_records_the_calling_thread(self):
        from app.tools import REGISTRY

        made = REGISTRY.call(
            "make_sandbox",
            {"name": "through-the-door", "purpose": "a box"},
            approved=True,
            actor="model",
            thread_id=self.thread,
        )
        self.assertTrue(made.get("ok", True), made)
        manifest = sandboxes.read_manifest("through-the-door")
        self.assertEqual(self.thread, manifest["thread_id"])

    def test_it_is_not_in_the_fingerprint(self):
        """Two sandboxes with the same pin, the same reach and the same data
        are the same ENVIRONMENT whoever asked for one. A fingerprint that
        disagreed would make reproducibility a property of the conversation."""
        mine = sandboxes.create("mine", thread_id=self.thread)
        theirs = sandboxes.create("theirs", thread_id=self.thread + 1)
        self.assertEqual(mine["fingerprint"], theirs["fingerprint"])


if __name__ == "__main__":
    unittest.main()
