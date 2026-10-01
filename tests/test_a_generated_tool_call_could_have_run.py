"""The deterministic half of a synthetic corpus: could this call have run?

`10-Signals/specs/synthetic-data.md` names this the piece everything else
depends on - "the piece that is right or wrong on its own merits" - and the
reason it is its own module with its own test is `recipes/hf-peft-dpo`'s: the
decision is the part that gets written wrong, and it is the part a suite with
no model, no torch and no network can still exercise.

TWO THINGS THIS FILE IS CAREFUL ABOUT.

**Empty is not "correct".** Every test below that asserts no faults is
asserting that the REGISTRY WOULD ACCEPT THE ARGUMENTS, and nothing more. A
well-formed call to the wrong tool has no faults and is still wrong; that
question belongs to a judge, and this module deliberately has no opinion about
it.

**The vocabulary is the registry's.** No tool name and no parameter name is
typed into the checker, so a tool registered tomorrow is covered the day it
lands and a tool renamed is caught rather than silently skipped.
"""

from __future__ import annotations

import unittest

import support

# Loaded by path, through `support.import_file`, for the reason that helper
# exists: `scripts/` ships no `__init__.py`, and a plain import would compile a
# `.pyc` beside the source inside the working tree. `import_file` sets
# `sys.dont_write_bytecode` for the duration and the import leaves nothing
# behind.
checker = support.import_file(
    "check_that_a_tool_call_could_run",
    support.REPO_ROOT / "scripts" / "check_that_a_tool_call_could_run.py",
)
the_tool_schemas_this_harness_ships = checker.the_tool_schemas_this_harness_ships
why_this_preference_pair_is_malformed = checker.why_this_preference_pair_is_malformed
why_this_tool_call_is_malformed = checker.why_this_tool_call_is_malformed


class TheSchemasComeFromTheRegistryTest(unittest.TestCase):
    def test_every_registered_tool_is_there_with_its_own_schema(self):
        from app.tools import REGISTRY

        schemas = the_tool_schemas_this_harness_ships()
        self.assertEqual(set(schemas), set(REGISTRY.names()))
        self.assertEqual(
            len(schemas), len(list(REGISTRY)),
            "a name that appears twice would hide one tool's schema behind another",
        )

    def test_it_is_a_copy_so_a_caller_cannot_edit_the_registry(self):
        schemas = the_tool_schemas_this_harness_ships()
        name = sorted(schemas)[0]
        schemas[name]["properties"] = {"invented": {"type": "string"}}
        again = the_tool_schemas_this_harness_ships()
        self.assertNotIn("invented", (again[name].get("properties") or {}))


class AWellFormedCallHasNoFaultsTest(unittest.TestCase):
    def setUp(self):
        self.schemas = the_tool_schemas_this_harness_ships()

    def test_a_real_call_with_its_real_arguments(self):
        faults = why_this_tool_call_is_malformed(
            {"name": "read_model_config", "arguments": {"repo_id": "org/model"}},
            self.schemas,
        )
        self.assertEqual(faults, [])

    def test_arguments_as_a_json_string_are_accepted(self):
        """Models emit both forms; refusing the string would drop good rows."""
        faults = why_this_tool_call_is_malformed(
            {"name": "read_model_config", "arguments": '{"repo_id": "org/model"}'},
            self.schemas,
        )
        self.assertEqual(faults, [])

    def test_a_tool_that_takes_nothing_needs_no_arguments(self):
        for missing in ({}, {"arguments": None}, {"arguments": {}}):
            with self.subTest(shape=missing):
                faults = why_this_tool_call_is_malformed(
                    {"name": "inspect_hardware", **missing}, self.schemas
                )
                self.assertEqual(faults, [])


class EveryReasonItCouldNotRunTest(unittest.TestCase):
    def setUp(self):
        self.schemas = the_tool_schemas_this_harness_ships()

    def test_no_tool_named_at_all(self):
        self.assertEqual(
            why_this_tool_call_is_malformed({"arguments": {}}, self.schemas),
            ["no tool was named"],
        )

    def test_an_invented_tool_is_named_and_the_nearest_real_ones_offered(self):
        faults = why_this_tool_call_is_malformed(
            {"name": "inspect_hardwear", "arguments": {}}, self.schemas
        )
        self.assertEqual(len(faults), 1)
        self.assertIn("no tool called 'inspect_hardwear'", faults[0])
        self.assertIn("inspect_hardware", faults[0])

    def test_a_missing_required_parameter(self):
        faults = why_this_tool_call_is_malformed(
            {"name": "read_model_config", "arguments": {}}, self.schemas
        )
        self.assertIn("required parameter 'repo_id' is missing", faults)

    def test_a_parameter_the_tool_does_not_have(self):
        faults = why_this_tool_call_is_malformed(
            {"name": "read_model_config",
             "arguments": {"repo_id": "org/model", "temperature": 0.7}},
            self.schemas,
        )
        self.assertIn("'temperature' is not a parameter of read_model_config", faults)

    def test_a_reserved_argument_is_named_as_reserved_and_not_merely_unknown(self):
        """`actor` decides what a fact is WORTH. A call carrying one is not a
        typo, and a corpus that taught a model to send it would be teaching it
        to reach for the one argument the registry exists to refuse."""
        faults = why_this_tool_call_is_malformed(
            {"name": "read_model_config",
             "arguments": {"repo_id": "org/model", "actor": "user"}},
            self.schemas,
        )
        self.assertTrue(any("reserved argument" in f for f in faults), faults)

    def test_arguments_that_are_not_json(self):
        faults = why_this_tool_call_is_malformed(
            {"name": "read_model_config", "arguments": "{not json"}, self.schemas
        )
        self.assertEqual(len(faults), 1)
        self.assertIn("not parseable JSON", faults[0])

    def test_arguments_that_are_not_an_object(self):
        faults = why_this_tool_call_is_malformed(
            {"name": "read_model_config", "arguments": ["org/model"]}, self.schemas
        )
        self.assertIn("arguments are a list, not a JSON object", faults)

    def test_a_null_is_the_missing_value_it_is(self):
        faults = why_this_tool_call_is_malformed(
            {"name": "read_model_config", "arguments": {"repo_id": None}},
            self.schemas,
        )
        self.assertTrue(any("is null" in f for f in faults), faults)

    def test_a_wrong_type_names_both_sides(self):
        faults = why_this_tool_call_is_malformed(
            {"name": "read_model_config", "arguments": {"repo_id": 7}},
            self.schemas,
        )
        self.assertIn("'repo_id' is a int; read_model_config declares it string", faults)

    def test_a_boolean_is_not_an_integer_even_though_python_says_it_is(self):
        """`isinstance(True, int)` is True, so a naive check accepts
        `{"rows": true}` as a count. The spec calls this out by name and the
        checker handles it explicitly."""
        schemas = {"t": {"properties": {"rows": {"type": "integer"}}, "required": []}}
        faults = why_this_tool_call_is_malformed(
            {"name": "t", "arguments": {"rows": True}}, schemas
        )
        self.assertEqual(faults, ["'rows' is a boolean; t declares it integer"])

    def test_an_enum_lists_what_was_allowed(self):
        schemas = {
            "t": {"properties": {"method": {"type": "string",
                                            "enum": ["lora", "qlora"]}},
                  "required": []}
        }
        faults = why_this_tool_call_is_malformed(
            {"name": "t", "arguments": {"method": "full"}}, schemas
        )
        self.assertIn("'method' is 'full', which is not one of ['lora', 'qlora']", faults)

    def test_a_schema_with_no_declared_type_checks_nothing(self):
        schemas = {"t": {"properties": {"anything": {}}, "required": []}}
        self.assertEqual(
            why_this_tool_call_is_malformed(
                {"name": "t", "arguments": {"anything": [1, 2]}}, schemas
            ),
            [],
        )

    def test_every_fault_is_reported_not_just_the_first(self):
        """A generator gets one report per row; naming one fault at a time
        would make fixing a prompt take as many runs as the row has faults."""
        schemas = {
            "t": {"properties": {"a": {"type": "string"}}, "required": ["a", "b"]}
        }
        faults = why_this_tool_call_is_malformed(
            {"name": "t", "arguments": {"a": 1, "z": 2}}, schemas
        )
        self.assertGreaterEqual(len(faults), 3)


class ThePreferencePairKeepsTheRealAnswerTest(unittest.TestCase):
    """The row-level enforcement of "structure, not content"."""

    GOOD = {
        "prompt": "What is a button?",
        "chosen": "A clickable control that triggers one named action.",
        "rejected": "A button is the fastest way to double your conversions.",
    }

    def test_a_well_formed_pair(self):
        self.assertEqual(
            why_this_preference_pair_is_malformed(
                self.GOOD, source_answer=self.GOOD["chosen"]
            ),
            [],
        )

    def test_the_chosen_side_must_be_the_source_answer_verbatim(self):
        """THE ONE THAT MATTERS. If the generator is allowed to rewrite the
        right answer, the pipeline is inventing content and the whole honesty
        argument for it collapses."""
        row = dict(self.GOOD, chosen="A clickable control that does an action.")
        faults = why_this_preference_pair_is_malformed(
            row, source_answer=self.GOOD["chosen"]
        )
        self.assertTrue(any("verbatim" in f for f in faults), faults)

    def test_whitespace_alone_does_not_make_it_a_different_answer(self):
        row = dict(self.GOOD, chosen="  " + self.GOOD["chosen"] + "\n")
        self.assertEqual(
            why_this_preference_pair_is_malformed(
                row, source_answer=self.GOOD["chosen"]
            ),
            [],
        )

    def test_two_identical_sides_are_no_preference_at_all(self):
        row = dict(self.GOOD, rejected=self.GOOD["chosen"])
        faults = why_this_preference_pair_is_malformed(
            row, source_answer=self.GOOD["chosen"]
        )
        self.assertIn(
            "chosen and rejected are the same string; there is no preference here",
            faults,
        )

    def test_a_missing_or_stub_field_is_named(self):
        for field in ("prompt", "chosen", "rejected"):
            with self.subTest(field=field):
                row = dict(self.GOOD)
                row[field] = "  "
                faults = why_this_preference_pair_is_malformed(
                    row, source_answer=self.GOOD["chosen"]
                )
                self.assertTrue(any(field in f for f in faults), faults)

    def test_a_one_word_rejected_is_not_an_answer(self):
        row = dict(self.GOOD, rejected="no")
        faults = why_this_preference_pair_is_malformed(
            row, source_answer=self.GOOD["chosen"]
        )
        self.assertTrue(any("not an answer" in f for f in faults), faults)


class TheRewriteMayNotNameSomethingNewTest(unittest.TestCase):
    """The judge's second clause, moved into arithmetic.

    WHY IT MOVED. The generator is told "do not add a new fact, a number, or a
    name that is not already in the source answer", and the judge was asked to
    police it. Measured on 2026-09-03: the judge kept a row that turned `2.00`
    into `$2.00` for a shop that writes no currency symbol anywhere. A set
    difference cannot miss that, and its verdict is the same verdict tomorrow.

    Measured over every row this repository had generated (n=20): one flagged,
    and it was that one. Nineteen legitimate degradations passed.
    """

    REAL = "We do, for 2.00 a book. Add a note at checkout saying what to wrap."

    def adds(self, rejected, real=None):
        return checker.specifics_the_rewrite_adds(real or self.REAL, rejected)

    def test_the_measured_fabrication_is_caught(self):
        """Verbatim from run A, seed 8. A human found it by reading; this finds
        it without a model."""
        self.assertIn(
            ("money", "$"),
            self.adds("We do gift wrapping for $2.00 per book, no note needed."),
        )

    def test_an_honest_degradation_of_the_same_row_passes(self):
        """Verbatim from run B, seed 8 - the same seed, no currency invented.
        Without this the test above passes for a check that flags everything."""
        self.assertEqual(
            self.adds(
                "We do gift wrapping for 2.00 a book. We will wrap your books "
                "for you without requiring you to add any note at checkout."
            ),
            [],
        )

    def test_a_number_the_shop_never_quoted(self):
        self.assertIn(("num", "45"), self.adds("We do, for 2.00 a book, in 45 minutes."))

    def test_a_day_the_shop_never_promised(self):
        self.assertIn(("day", "friday"), self.adds("We do, for 2.00, ready Friday."))

    def test_a_name_the_shop_never_used(self):
        self.assertIn(("name", "Waterstones"), self.adds("We do, for 2.00, like Waterstones."))

    def test_dropping_a_condition_is_invisible_here_because_it_is_the_point(self):
        """THE ONE THAT KEEPS THIS CHECK NARROW. Removing "add a note at
        checkout" is the degradation the generator was asked for. A check that
        fired on it would refuse every good row in the corpus."""
        self.assertEqual(self.adds("We do, for 2.00 a book."), [])

    def test_the_first_word_of_a_sentence_is_not_a_name(self):
        """Capitalised by grammar, not by reference."""
        self.assertEqual(
            self.adds("Books are 2.00 each. Wrapping is included.",
                      "We wrap books for 2.00 each. It is included."),
            [],
        )

    def test_the_pronoun_i_is_not_a_name(self):
        """Measured: without this one confabulated control pair was 'caught' on
        the strength of a capitalised I - a right answer for a wrong reason.

        Bare `I` is already excluded by the one-letter filter; the contractions
        are what `_NOT_A_NAME` actually earns its place for, so both are
        asserted here. A mutation run found this: deleting the set left the
        suite green because the only case tested was the one the length filter
        already handled."""
        self.assertEqual(self.adds("We do, for 2.00, and I will wrap it."), [])
        self.assertEqual(self.adds("We do, for 2.00, and I'll wrap it."), [])
        self.assertEqual(self.adds("We do, for 2.00. I've wrapped it."), [])

    def test_the_pair_check_reports_it_as_a_fabrication_not_a_style_note(self):
        row = {
            "prompt": "Do you do gift wrapping?",
            "chosen": self.REAL,
            "rejected": "We do gift wrapping for $2.00 per book, no note needed.",
        }
        faults = checker.why_this_preference_pair_is_malformed(
            row, source_answer=self.REAL
        )
        self.assertTrue(any("fabrication" in f for f in faults), faults)
        self.assertTrue(any("$" in f for f in faults), faults)


class TheVerbatimCheckReadsTheFileNotTheRowTest(unittest.TestCase):
    """A check that compares `chosen` to itself passes for every row ever
    written, including the one case it exists to catch. So the source is
    re-read, and a row that names no source says so."""

    def a_stamped_row(self, root, chosen):
        source = root / "train.jsonl"
        source.write_text(
            '{"instruction": "Can I return a book?", "response": '
            '"Unmarked books can be returned within 30 days with a receipt."}\n',
            encoding="utf-8",
        )
        return {
            "prompt": "Can I return a book?",
            "chosen": chosen,
            "rejected": "Books can always be returned, no receipt needed.",
            "provenance": {
                "source": {
                    "path": str(source),
                    "row_index": 0,
                    "answer_field": "response",
                }
            },
        }

    def test_the_real_answer_comes_back_off_the_named_line(self):
        root = support.sandbox(self)
        answer, why_not = checker.the_source_answer_behind(
            self.a_stamped_row(root, "anything")
        )
        self.assertIsNone(why_not)
        self.assertEqual(
            answer, "Unmarked books can be returned within 30 days with a receipt."
        )

    def test_a_rewritten_chosen_is_caught_against_the_file(self):
        """THE ONE THAT MATTERS. This row's `chosen` is self-consistent; only
        the file disagrees with it."""
        root = support.sandbox(self)
        row = self.a_stamped_row(root, "Books can be returned whenever you like.")
        answer, why_not = checker.the_source_answer_behind(row)
        self.assertIsNone(why_not)
        faults = checker.why_this_preference_pair_is_malformed(
            row, source_answer=answer
        )
        self.assertTrue(any("verbatim" in f for f in faults), faults)

    def test_a_row_with_no_provenance_says_so_rather_than_passing(self):
        _, why_not = checker.the_source_answer_behind({"chosen": "x", "prompt": "y"})
        self.assertIn("names no source", why_not)

    def test_a_source_that_moved_says_so_rather_than_passing(self):
        root = support.sandbox(self)
        row = self.a_stamped_row(root, "anything")
        (root / "train.jsonl").unlink()
        _, why_not = checker.the_source_answer_behind(row)
        self.assertIn("could not be read back", why_not)

    def test_an_index_past_the_end_of_the_file_says_so(self):
        root = support.sandbox(self)
        row = self.a_stamped_row(root, "anything")
        row["provenance"]["source"]["row_index"] = 99
        _, why_not = checker.the_source_answer_behind(row)
        self.assertIn("could not be read back", why_not)


if __name__ == "__main__":
    unittest.main()
