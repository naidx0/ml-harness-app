"""A refusal that does not say what would have worked is a wall with no door.

Watched against the live model rather than imagined. `granite4-hermes`, running
locally, calls `state_facts` with fact names the ledger does not declare -
`answer_given`, `hardware_is_sufficient_for_training`, `you_have_an_eval_set` -
and the registry correctly refuses every one. That refusal is the fact-origin
system working exactly as designed: a fact name a model invented is a fact the
engine has never heard of, and accepting it would be the first crack in the only
thing that makes a gate mean anything.

WHAT WAS WRONG WAS THE REPLY. `'answer_given' is not a declared fact; the ledger
is in docs/diagnosis_engine.yaml` is true, unarguable, and useless to a caller
that cannot open that file. So the round is spent, the user watches a failed step
go past in their transcript, and the model's second guess is no better informed
than its first. The ledger declares every fact with a type and a source and the
registry declares which tool measures which fact; all of that was sitting there
unread at the one moment a caller needed it.

So: THE REFUSAL IS THE MECHANISM AND THE INSTRUCTION IS THE COURTESY. This file
tests the mechanism. `test_instruction_set.py` and the drift check at the bottom
of this one cover the courtesy, and the split matters - this project has learned
twice that prose is not a wall, and a fix that lived only in the prompt would be
a fix that a smaller model, or a colder context, walks straight through.

The sweep is here too. The same defect - a refusal that names no alternative -
was looked for everywhere the registry and the tools refuse a caller, and the
three other places it was found are pinned below so they cannot come back.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from app import diagnosis, instructions
from app.tools import REGISTRY
from app.tools import evidence
from app.tools.registry import (
    ApprovalRequired,
    Control,
    Registry,
    ToolError,
    ToolSpec,
)

import support


#: The three names a real local model actually sent, in one session, to a tool
#: that refused all three. Not invented for this test.
OBSERVED_INVENTIONS = (
    "answer_given",
    "hardware_is_sufficient_for_training",
    "you_have_an_eval_set",
)


def _probe(**overrides):
    base = dict(
        name="probe_tool",
        description="A tool used only by this test.",
        schema={"type": "object", "properties": {}},
        reads=(),
        writes=(),
        approval="never",
        provides=("context.dataset.preview",),
        control=Control(label="Probe", group="Test", verb="probe"),
        handler=lambda: {"ok": True},
    )
    base.update(overrides)
    return ToolSpec(**base)


class TheRefusedFactNamesTheLegalOnesTest(unittest.TestCase):
    """Defect 1, at the surface the model actually meets."""

    def setUp(self):
        support.sandbox(self)

    def _refusal(self, **facts):
        result = REGISTRY.call(
            "state_facts", {"facts": facts}, actor=evidence.MODEL, thread_id=1
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "rejected_fact")
        return result

    def test_the_three_names_the_live_model_sent_are_still_refused(self):
        """The wall first. A door is only worth having in a wall that holds."""
        result = self._refusal(**{name: True for name in OBSERVED_INVENTIONS})
        self.assertEqual(sorted(result["unknown_facts"]), sorted(OBSERVED_INVENTIONS))
        for name in OBSERVED_INVENTIONS:
            self.assertNotIn(name, diagnosis.default_spec().facts)

    def test_an_eval_set_invention_is_answered_with_the_eval_fact(self):
        result = self._refusal(you_have_an_eval_set=True)
        candidates = result["did_you_mean"]["you_have_an_eval_set"]
        named = [row["fact"] for row in candidates]
        self.assertIn("eval_size_n", named)
        first = candidates[0]
        self.assertEqual(first["fact"], "eval_size_n")
        self.assertEqual(first["accepts"], {"type": "int"})
        self.assertEqual(first["source"], "inspect")
        # And the match is checkable rather than trusted: the word that earned
        # the suggestion is a word the caller typed.
        for word in first["matched_on"]:
            self.assertIn(word, "you_have_an_eval_set")

    def test_a_hardware_invention_is_answered_with_the_hardware_facts_and_the_tool(self):
        """The hardest of the three, and the reason `measures=` is a signal.

        Nothing in the ledger contains the word "hardware". `inspect_hardware`
        declares `measures=` on the four facts that are the answer, so the
        registry's own declaration is what carries the match - and the tool it
        names is a better reply than the fact ids on their own, because all four
        are `source: inspect` and stating them was never going to work.

        A FIFTH ARRIVED ON 2026-09-10 AND IT IS NOT A REGRESSION.
        `training_headroom_gb` matches on its OWN name rather than through a
        tool - the caller typed "training" - and it scores above all four
        because a name match is worth more than a tool match, by design. This
        test asserted a set of exactly four and went red, which is the assertion
        doing its job: a second tool now measures something hardware-adjacent
        and the ledger changed underneath a number written when only one did.

        It is kept rather than filtered out, and the reason is the caller's.
        `hardware_is_sufficient_for_training` is a question about a margin, and
        the margin is what that fact IS. The tool behind it answers on a YES
        too - with `recorded: []` and `why_nothing_was_recorded` saying why -
        so a caller sent there is never left holding a door that does not open.

        WHAT THE TEST ASSERTS NOW is the thing it was always about: every
        suggestion names the tool that actually measures it. The four keep
        `inspect_hardware` by name, so a suggestion drifting to the wrong door
        is still red.
        """
        result = self._refusal(hardware_is_sufficient_for_training=True)
        candidates = result["did_you_mean"]["hardware_is_sufficient_for_training"]
        named = {row["fact"] for row in candidates}
        self.assertEqual(
            named,
            {"accelerator", "vram_gb", "ram_gb", "disk_free_gb", "training_headroom_gb"},
        )
        doors = {row["fact"]: row["settled_by"]["tool"] for row in candidates}
        self.assertEqual(
            doors["training_headroom_gb"], "record_that_this_card_refuses"
        )
        for row in candidates:
            self.assertEqual(row["source"], "inspect")
            self.assertEqual(row["settled_by"]["run_as"], "harness")
            self.assertEqual(row["opens_a_gate_when_the_origin_is"], ["MEASURED"])
            if row["fact"] != "training_headroom_gb":
                self.assertEqual(row["settled_by"]["tool"], "inspect_hardware")

    def test_a_name_nothing_resembles_gets_no_invented_suggestion(self):
        """`answer_given` is not a fact this product has, and says so.

        A filled list would be the least-bad of sixty-eight and would cost the
        caller the same round the refusal is trying to save. What it gets
        instead is the fifteen-odd facts the five gates actually read, which is
        the ledger's own answer to "what would move this forward".
        """
        result = self._refusal(answer_given=True)
        self.assertNotIn("answer_given", result.get("did_you_mean", {}))
        self.assertEqual(result["nothing_in_the_ledger_resembles"], ["answer_given"])
        lines = result["the_five_gates_read"]
        self.assertTrue(any(line.startswith("eval_size_n:") for line in lines))
        self.assertTrue(any(line.startswith("model_swap_tried:") for line in lines))
        self.assertLess(len(lines), len(diagnosis.default_spec().facts))

    def test_a_valid_name_sent_alongside_an_invalid_one_is_named_back(self):
        """LAW SUBSTITUTED 2026-09-18. This read "nothing is recorded, and the
        caller is told which half was fine". Max's thread 78: nine facts sent
        twice, one undeclared name each time, and target_score thrown away
        with it both times - so the turn ended asking the person for what it
        had already tried to record. The good half now LANDS, and the caller
        is told which half did not."""
        from app import events

        thread = int(events.create_thread("door")["id"])
        result = REGISTRY.call(
            "state_facts", {"facts": {"retrieval_tried": True, "answer_given": True}},
            actor=evidence.MODEL, thread_id=thread,
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["unknown_facts"], ["answer_given"])
        self.assertEqual(list(result["rejected"]), ["answer_given"])
        self.assertEqual({row["fact"] for row in result["recorded"]}, {"retrieval_tried"})
        self.assertEqual({row["fact"] for row in evidence.rows_for(thread)}, {"retrieval_tried"})

    def test_the_refusal_never_names_a_fact_the_ledger_does_not_declare(self):
        """The property, over a corpus rather than over three cases.

        A suggestion engine that can emit a name is a suggestion engine that can
        emit a wrong one, and a model handed a plausible non-existent id would
        burn the round twice. Every candidate is checked against the ledger.
        """
        declared = diagnosis.default_spec().facts
        corpus = [
            *OBSERVED_INVENTIONS,
            "eval_set_size", "gpu_memory", "has_baseline", "budget", "vram",
            "num_examples", "training_data_size", "user_tried_prompting",
            "privacy_ok", "latency", "dataset_size", "the_user_is_happy",
            "foo", "", "   ", "12345", "GATE_G0", "gates_passed",
        ]
        for name in corpus:
            with self.subTest(name=name):
                for row in evidence.nearest_facts(name):
                    self.assertIn(row["fact"], declared)
                    self.assertTrue(row["matched_on"])

    def test_run_diagnosis_gets_the_same_door(self):
        """Two tools take facts. A door on one of them is a door somewhere."""
        result = REGISTRY.call(
            "run_diagnosis",
            {"facts": {"you_have_an_eval_set": True}},
            actor=evidence.MODEL,
            thread_id=1,
        )
        self.assertEqual(result["error"], "rejected_fact")
        named = [row["fact"] for row in result["did_you_mean"]["you_have_an_eval_set"]]
        self.assertIn("eval_size_n", named)


class TheSweepTest(unittest.TestCase):
    """Defect 2. The same class of refusal, everywhere else it was found."""

    def setUp(self):
        support.sandbox(self)

    def test_an_invented_tool_name_is_answered_with_the_real_ones(self):
        """The registry's own version of defect 1, and it was the loudest.

        `no tool named 'get_hardware_info'` reached the transcript as a
        `no_such_tool` step with no list of what does exist. There are nineteen
        tools; nineteen names is a list a caller can read.
        """
        with self.assertRaises(ToolError) as caught:
            REGISTRY.call("get_hardware_info")
        message = str(caught.exception)
        self.assertIn("inspect_hardware", message)
        for name in REGISTRY.names():
            self.assertIn(name, message)

    def test_an_invented_tool_name_that_resembles_nothing_still_gets_the_list(self):
        with self.assertRaises(ToolError) as caught:
            REGISTRY.call("zzzz")
        for name in REGISTRY.names():
            self.assertIn(name, str(caught.exception))

    def test_an_empty_registry_says_it_is_empty_rather_than_listing_nothing(self):
        with self.assertRaises(ToolError) as caught:
            Registry().call("anything_at_all")
        self.assertIn("none at all", str(caught.exception))

    def test_an_approval_refusal_says_where_an_approval_comes_from(self):
        """"Needs an approval" with no account of how one is obtained is a wall.

        A model cannot supply one - that is the point of the mechanism - so the
        only useful reply is the one that says so and names what to do instead.
        """
        registry = Registry()
        registry.add(_probe(approval="always"))
        with self.assertRaises(ApprovalRequired) as caught:
            registry.call("probe_tool")
        message = str(caught.exception)
        self.assertIn("not something a tool call can carry", message)
        self.assertIn("control", message)

    def test_a_missing_argument_refusal_names_the_arguments_that_exist(self):
        """The specimen is derived. It used to be `run_diagnosis`, whose
        `facts` argument stopped being required on 2026-09-11; the property
        had not changed and the test went red anyway. See
        `support.a_tool_that_requires_an_argument`."""
        tool = support.a_tool_that_requires_an_argument()
        wanted = list(tool.schema["required"])[0]
        result = REGISTRY.call(
            tool.name, {"not_an_argument_of_this_tool": 40}, actor=evidence.MODEL
        )
        self.assertEqual(result["error"], "missing_arguments")
        self.assertTrue(
            any(line.startswith(wanted + ":") for line in result["accepts"]),
            "the refusal did not name " + wanted + ", which is what it accepts",
        )
        self.assertIn("not_an_argument_of_this_tool", result["ignored_arguments"])

    def test_a_dropped_argument_names_the_ones_that_would_have_been_kept(self):
        """A drop reported without an alternative is a guess invited."""
        result = REGISTRY.call(
            "list_runs", {"limit": 5, "how_many": 5}, actor=evidence.MODEL
        )
        self.assertEqual(result["ignored_arguments"], ["how_many"])
        self.assertTrue(any(line.startswith("limit:") for line in result["accepts"]))
        self.assertIn("no such parameter", result["ignored_because"])

    def test_a_reserved_argument_says_there_is_no_name_that_would_work(self):
        """The one refusal whose honest answer is "nothing, and here is why".

        Naming an alternative here would be naming a way round wall 4. What the
        caller gets instead is the reserved list in full and the real route: run
        the tool that measures the thing.
        """
        result = REGISTRY.call(
            "list_runs", {"limit": 5, "origin": "MEASURED"}, actor=evidence.MODEL
        )
        self.assertEqual(result["refused_arguments"], ["origin"])
        self.assertIn("run the tool that measures", result["refused_because"])

    def test_a_tool_that_declares_an_unmeasurable_fact_is_told_which_are_measurable(self):
        """The registration-time twin, read by an author instead of a model."""
        registry = Registry()
        with self.assertRaises(ToolError) as caught:
            registry.add(
                _probe(
                    name="liar_tool",
                    measures=("prompt_iterations",),
                    handler=lambda *, instrument: {"ok": True},
                )
            )
        message = str(caught.exception)
        self.assertIn("prompt_iterations", message)
        self.assertIn("ask", message)  # the reason survives
        self.assertIn("eval_size_n", message)  # and now the legal set is named
        self.assertIn("vram_gb", message)

    def test_a_bound_naming_nothing_is_told_what_the_tool_takes(self):
        registry = Registry()
        with self.assertRaises(ToolError) as caught:
            registry.add(
                _probe(
                    name="bounded_tool",
                    schema={
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                    },
                    measures=("eval_size_n",),
                    bounds=("max_rows",),
                    handler=lambda path=None, *, instrument: {"ok": True},
                )
            )
        self.assertIn("'path'", str(caught.exception))


class TheDeclarationIsReadNotRememberedTest(unittest.TestCase):
    """Everything the door says comes off the ledger and the registry."""

    def test_every_measurable_fact_names_the_tool_that_measures_it(self):
        """Everything the door says comes off the ledger and the registry.

        WIDENED 2026-08-25: this swept every tool's `measures=` against the
        DEFAULT ledger alone, which was the whole world when there was one.
        The four agent instruments measure the second ledger's facts, so each
        fact is now read from a ledger that actually declares it - the same
        union registration asks for - and the door line must still name the
        instrument. An id NO ledger declares still fails here, which is the
        teeth.
        """
        for spec in REGISTRY:
            for fact in spec.measures:
                with self.subTest(tool=spec.name, fact=fact):
                    declaring = evidence.ledgers_declaring(fact)
                    self.assertTrue(
                        declaring,
                        f"{fact!r} is measured by {spec.name} and declared by no "
                        "ledger in this product",
                    )
                    line = evidence.declaration_line(
                        fact, diagnosis.spec_at(declaring[0])
                    )
                    # The door names AN instrument, not necessarily THIS one:
                    # several tools may measure one fact (`baseline_score` is
                    # measure_baseline's to settle even though run_eval also
                    # declares it), and which one settles is the ledger's
                    # resolves() choice, asserted in its own file.
                    self.assertIn("measured by", line)

    def test_the_gate_vocabulary_is_derived_from_the_gate_predicates(self):
        derived = set()
        for row in diagnosis.default_spec().gate_row_facts.values():
            derived |= set(row)
        self.assertEqual(set(evidence.gate_facts()), derived)
        self.assertIn("eval_size_n", derived)

    def test_a_declaration_line_never_claims_a_shape_the_ledger_did_not(self):
        spec = diagnosis.default_spec()
        for name, decl in spec.facts.items():
            with self.subTest(fact=name):
                line = evidence.declaration_line(name)
                self.assertTrue(line.startswith(f"{name}: "))
                self.assertIn(f"source {decl.get('source')}", line)
                if "enum" in decl:
                    for member in decl["enum"]:
                        self.assertIn(member, line)


class TheInstructionIsTheCourtesyTest(unittest.TestCase):
    """The prose half - and it is checked against the ledger, not trusted.

    An instruction naming a fact id is an instruction that can go stale the day
    somebody renames one, and a stale example is worse than none: it teaches the
    model a name the refusal will then reject. So every id the prompt quotes has
    to still exist.
    """

    #: A backticked lowercase token that is neither a fact nor a tool. Kept
    #: explicit so a new one has to be typed rather than absorbed.
    ALLOWED = frozenset()

    def _quoted_ids(self):
        pattern = re.compile(r"`([a-z][a-z0-9_]*)`")
        for path in sorted(Path(instructions.HERE).glob("*.md")):
            for token in pattern.findall(path.read_text(encoding="utf-8")):
                if "_" in token:
                    yield path.name, token

    def test_every_id_the_prompt_quotes_still_exists(self):
        facts = diagnosis.default_spec().facts
        tools = set(REGISTRY.names())
        found = list(self._quoted_ids())
        self.assertTrue(found, "the prompt quotes no ids at all - check the regex")
        for filename, token in found:
            with self.subTest(file=filename, token=token):
                self.assertTrue(
                    token in facts or token in tools or token in self.ALLOWED,
                    f"{filename} quotes {token!r}, which is neither a declared "
                    "fact nor a registered tool. A prompt that names an id the "
                    "harness will refuse teaches the model to spend a round.",
                )

    def test_the_prompt_tells_the_model_that_fact_names_cannot_be_invented(self):
        prompt = instructions.assemble(tool_calling=True)
        self.assertTrue(
            instructions.contains(prompt, "You cannot invent one"),
            "the tools fragment no longer says fact names are fixed ids",
        )
        self.assertTrue(instructions.contains(prompt, "eval_size_n"))


if __name__ == "__main__":
    unittest.main()
