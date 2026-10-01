"""Every conversation was told the ML ledger's gates, whatever ledger it was on.

## The gap, which the third ledger wrote down about itself

`docs/ledgers/harness_design.yaml`'s own `known_gaps`:

    the_system_prompt_is_still_single_ledger: OPEN. `app/instructions/
    02_five_gates.md` states the ML ledger's gates in prose to every
    conversation regardless of ledger... Capability blocks scoped the TOOLS to
    the domain and the instructions were not part of that change.

**It is not merely a stale paragraph.** The fragment opens with *"You may not
recommend any form of training until all five of these are true, and you may not
soften, skip, reorder or bargain with them"* — a rule stated in the strongest
words the prompt uses, about a verdict two of the three ledgers cannot reach. A
person asking whether to build a harness was being told, by the model's own
instructions, that they need thirty graded eval rows before anything can happen.

## Why the ML ledger keeps its file and the others are rendered

`02_five_gates.md` is argued prose rather than a list of names — *"if the trivial
baseline is within five points of the model, the task or the labels are broken
and no method will help"*, *"vibes do not count"* — and nothing can regenerate
that from a YAML `asks:` line. Deleting it so three ledgers look alike would
lose the best-written page in the prompt to gain a shape.

So the default ledger gets its file, byte for byte, and every other ledger gets
its own gates read off its own contract. A fourth ledger needs no edit here,
which is the property that stops this going stale a second time.
"""

import unittest

from app import conductor, diagnosis, instructions


HARNESS = "docs/ledgers/harness_design.yaml"
AI = "docs/ledgers/ai_engineering.yaml"


def spec(name: str) -> diagnosis.Spec:
    return diagnosis.spec_at(name)


class TheDefaultLedgerKeepsItsProseTest(unittest.TestCase):
    def test_it_is_the_file_byte_for_byte(self):
        """Not "similar to". The argued sentences in that fragment are the
        product of several corrections and none of them survives a renderer."""
        self.assertEqual(
            instructions.gates_for(None), instructions.read(instructions.THE_ML_GATES)
        )

    def test_the_ml_spec_itself_gets_the_same_file(self):
        """Passing the default ledger explicitly must not produce a rendered
        version of it — that would be two spellings of one ledger's gates."""
        self.assertEqual(
            instructions.gates_for(diagnosis.default_spec()),
            instructions.read(instructions.THE_ML_GATES),
        )

    def test_the_prose_that_a_renderer_could_not_reproduce_is_still_there(self):
        text = instructions.gates_for(None)
        self.assertIn("Vibes do not count", text)
        # Collapsed, because the fragment is hard-wrapped and the sentence this
        # is about spans a line break - asserting the wrapped form would be a
        # test of the wrapping.
        flat = " ".join(text.split()).lower()
        self.assertIn(
            "if the trivial baseline is within five points of the model, "
            "the task or the labels are broken",
            flat,
        )


class EveryOtherLedgerGetsItsOwnTest(unittest.TestCase):
    def test_the_harness_ledger_states_six_gates_and_names_them(self):
        text = instructions.gates_for(spec(HARNESS))
        self.assertIn("## The six gates", text)
        for gate_id in spec(HARNESS).required_gates:
            with self.subTest(gate=gate_id):
                self.assertIn(gate_id, text)

    def test_the_ai_ledger_states_its_own_five(self):
        text = instructions.gates_for(spec(AI))
        for gate_id in spec(AI).required_gates:
            with self.subTest(gate=gate_id):
                self.assertIn(gate_id, text)

    def test_no_other_ledger_is_told_about_training_or_an_eval_set(self):
        """THE DEFECT ITSELF. These are the sentences that were reaching every
        conversation, and neither is true of either other domain."""
        for name in (HARNESS, AI):
            with self.subTest(ledger=name):
                text = instructions.gates_for(spec(name))
                self.assertNotIn("any form of training", text)
                self.assertNotIn("An eval set exists", text)
                self.assertNotIn("prompt optimiser", text)

    def test_each_gate_carries_the_question_it_asks(self):
        """A list of ids would be a table of contents. What makes a gate
        actionable is the question, and every ledger states one."""
        text = instructions.gates_for(spec(HARNESS))
        for gate_id, gate in spec(HARNESS).gates.items():
            if gate_id not in spec(HARNESS).required_gates:
                continue
            with self.subTest(gate=gate_id):
                self.assertIn(str(gate["asks"]).strip(), text)

    def test_it_says_what_the_gates_are_for_in_that_ledgers_own_words(self):
        text = instructions.gates_for(spec(HARNESS))
        self.assertIn("WHETHER BUILDING THE HARNESS IS WORTH DOING", text)

    def test_it_is_read_off_the_contract_rather_than_written_here(self):
        """The property that stops this going stale a second time: a fourth
        ledger, or a renamed gate, needs no edit in `app/instructions`."""
        source = (
            instructions.HERE.parent / "instructions" / "__init__.py"
        ).read_text(encoding="utf-8")
        for gate_id in spec(HARNESS).required_gates:
            with self.subTest(gate=gate_id):
                self.assertNotIn(gate_id, source)


class TheFallbackIsTheFileAndNotSilenceTest(unittest.TestCase):
    """A prompt with no gates section is a model told it may recommend the
    expensive thing whenever it likes — worse than the wrong domain's gates."""

    def test_a_ledger_that_cannot_be_read_falls_back(self):
        class _Broken:
            @property
            def required_gates(self):
                raise RuntimeError("unreadable")

        self.assertEqual(
            instructions.gates_for(_Broken()),
            instructions.read(instructions.THE_ML_GATES),
        )

    def test_a_ledger_with_no_required_gates_falls_back(self):
        class _Empty:
            as_written = "docs/ledgers/nothing.yaml"
            required_gates: list[str] = []
            gates: dict[str, object] = {}
            contract: dict[str, object] = {}

        self.assertEqual(
            instructions.gates_for(_Empty()),
            instructions.read(instructions.THE_ML_GATES),
        )

    def test_a_thread_nobody_can_resolve_is_none_rather_than_a_crash(self):
        self.assertIsNone(conductor._ledger_of(None))


class TheAssembledPromptCarriesItTest(unittest.TestCase):
    def test_the_whole_prompt_swaps_the_section_and_nothing_else(self):
        """The gates section is the ONE core file that is true of one ledger.
        Everything else — how to say where a number came from, never to invent
        one, what to do when you do not know — is true of the product, and this
        asserts those did not move."""
        ml = instructions.assemble(tool_calling=False)
        harness = instructions.assemble(tool_calling=False, ledger=spec(HARNESS))

        self.assertIn("## The five gates", ml)
        self.assertIn("## The six gates", harness)
        for shared in ("never invent a number", "Say where it came from"):
            with self.subTest(fragment=shared):
                self.assertEqual(shared.lower() in ml.lower(), shared.lower() in harness.lower())

    def test_the_prompt_stays_roughly_the_size_it_was(self):
        """A rendered section that ran away would move a bound this repository
        has raised nine times. Measured: the three differ by a few hundred
        characters, which is the length of a sixth gate."""
        sizes = [
            len(instructions.assemble(tool_calling=False, ledger=one))
            for one in (None, spec(AI), spec(HARNESS))
        ]
        self.assertLess(max(sizes) - min(sizes), 1000, sizes)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
