"""The capability list gets shorter without getting smaller.

## What changed and what the difference is

The list of what the harness can do is derived from `REGISTRY` and rendered into
every system prompt. It was rendered one way: name, the opening of the tool's own
description, and the tool's `required` list. That is 6,981 characters, and on
`granite4-hermes` the whole system prompt measured **8,025 tokens** - paid on
every turn of every conversation.

The middle two clauses are a **verbatim second copy**. When the connected model
can call tools, `app/conductor.py` sends `REGISTRY.model_tools()` in the same
request: 28,999 characters carrying all 28 full descriptions and all 28 parameter
schemas. The system prompt was restating the opening of each description
alongside them.

So there are two renderings now, and the short one drops exactly the duplicated
halves. Measured through `/api/chat`'s `prompt_eval_count`, which is the model's
own tokeniser rather than an estimate:

| what                        | before | after  |
| --------------------------- | ------ | ------ |
| the capability list, chars   |  6,981 |  2,730 |
| system prompt, tokens        |  8,025 |  7,108 |
| a turn's fixed cost, tokens  | 14,130 | 13,213 |

## The two things that would make this a defect rather than a saving

**A tool going missing.** The list's entire reason for being derived is that a
hand-written one goes stale. A short form that dropped a tool would be the old
defect with a new excuse, so the completeness assertions below run over both
renderings and over a registry the product does not own.

**The promise being false.** The short form tells the model the detail is "in the
tool definitions sent with this message". That is only true where the schemas are
actually sent - `tool_calling is True`, and nowhere else - and only true if those
schemas really carry the description and the `required` list. Both are asserted,
because a prompt that points at documentation which is not there is worse than
one that repeats itself.

`tests/test_instruction_set.py` holds the third condition: that the short form is
selected only in the state where the schemas travel with it.
"""

from __future__ import annotations

import unittest

from app import instructions
from app.instructions import capabilities
from app.tools import Control, Registry, ToolSpec
from app.tools.registry import REGISTRY


BOTH = (True, False)


def a_registry_nobody_ships() -> Registry:
    """One tool, in a group with no gloss, needing an argument and an approval.

    Everything the short form has to keep is on this one spec, so a rendering
    that quietly drops any of them has nowhere to hide.
    """
    registry = Registry()
    registry.add(
        ToolSpec(
            name="summon_a_pony",
            description=(
                "Summon a pony onto the user's machine. It is a very good pony. "
                "This sentence exists so the summary has something to cut."
            ),
            schema={
                "type": "object",
                "properties": {"stable_path": {"type": "string"}},
                "required": ["stable_path"],
            },
            reads=(),
            writes=(),
            approval="always",
            provides=("machine.hardware.inspect",),
            control=Control(label="Summon", group="Stable", verb="summon a pony"),
            handler=lambda stable_path: None,
        )
    )
    return registry


class NeitherFormCanLoseAToolTest(unittest.TestCase):
    def test_every_registered_tool_is_named_in_both_forms(self):
        for detail in BOTH:
            text = capabilities.render(detail=detail)
            for name in REGISTRY.names():
                with self.subTest(tool=name, detail=detail):
                    self.assertIn(f"- `{name}`", text)

    def test_the_two_forms_name_exactly_the_same_tools(self):
        """The saving is in the prose, not in the inventory."""
        long_ = capabilities.render(detail=True)
        short = capabilities.render(detail=False)
        for name in REGISTRY.names():
            with self.subTest(tool=name):
                self.assertEqual(long_.count(f"- `{name}`"), 1)
                self.assertEqual(short.count(f"- `{name}`"), 1)

    def test_every_group_survives_both_forms(self):
        groups = {spec.control.group for spec in REGISTRY}
        for detail in BOTH:
            text = capabilities.render(detail=detail)
            headings = [l for l in text.splitlines() if l.startswith("### ")]
            with self.subTest(detail=detail):
                self.assertEqual(len(headings), len(groups))

    def test_both_forms_are_derived_rather_than_written(self):
        """Rendered against a registry the product does not own.

        A test that only reads the real registry cannot tell a generated list
        from a hand-written one that happens to be correct today.
        """
        for detail in BOTH:
            text = capabilities.render(a_registry_nobody_ships(), detail=detail)
            with self.subTest(detail=detail):
                self.assertIn("`summon_a_pony`", text)
                self.assertIn("### Stable", text)
                self.assertIn("There are 1 of them", text)
                for name in REGISTRY.names():
                    self.assertNotIn(f"`{name}`", text)


class TheShortFormKeepsWhatTheSchemaCannotCarryTest(unittest.TestCase):
    """The three things a tool definition has no field for.

    `measures` and `approval` are the harness's own facts about a tool, not the
    model's arguments to it, so they appear nowhere in `model_tools()`. Dropping
    them to save characters would be dropping the only copy.
    """

    def test_an_approval_is_still_stated(self):
        short = capabilities.render(detail=False)
        approving = [s.name for s in REGISTRY if s.approval == "always"]
        self.assertTrue(approving, "no tool requires approval - check the registry")
        for name in approving:
            with self.subTest(tool=name):
                line = _line_for(short, name)
                self.assertIn("A person has to approve it before it runs.", line)

    def test_start_training_specifically_still_says_so(self):
        """The tool this whole product is careful about, kept as its own test."""
        line = _line_for(capabilities.render(detail=False), "start_training")
        self.assertIn("A person has to approve it before it runs.", line)

    def test_the_facts_a_tool_can_stamp_measured_are_still_stated(self):
        """A model reasoning about the five gates needs to know which tools open one."""
        short = capabilities.render(detail=False)
        measuring = [s for s in REGISTRY if s.measures]
        self.assertTrue(measuring, "no tool measures anything - check the registry")
        for spec in measuring:
            line = _line_for(short, spec.name)
            for fact in spec.measures:
                with self.subTest(tool=spec.name, fact=fact):
                    self.assertIn(f"`{fact}`", line)

    def test_the_short_form_still_says_the_list_is_derived(self):
        """A model handed a bare list cannot trust it against its own priors.

        `instructions.NON_NEGOTIABLE` names this sentence. It is repeated here
        against the short rendering specifically, because that is the rendering
        the law was not written against.
        """
        self.assertIn(
            "generated from the harness's own tool registry",
            capabilities.render(detail=False),
        )

    def test_the_short_form_still_counts_off_the_registry(self):
        self.assertIn(
            f"There are {len(REGISTRY)} of them", capabilities.render(detail=False)
        )

    def test_the_short_form_still_says_the_harness_does_the_second_half(self):
        """The sentence that closed the undersell. It is not padding."""
        self.assertIn(
            "A person is not being sent elsewhere to do the second half.",
            capabilities.render(detail=False),
        )


class ThePromiseTheShortFormMakesIsTrueTest(unittest.TestCase):
    """It points at the tool definitions. They have to actually contain it."""

    def test_it_points_at_the_tool_definitions(self):
        self.assertIn(
            "in the tool definitions sent with this message",
            capabilities.render(detail=False),
        )

    def test_every_definition_carries_the_description_the_list_stopped_repeating(self):
        for tool in REGISTRY.model_tools():
            function = tool["function"]
            with self.subTest(tool=function["name"]):
                self.assertTrue(
                    str(function.get("description") or "").strip(),
                    f"{function['name']} has no description in its schema, so the "
                    "short capability list is pointing the model at nothing.",
                )

    def test_every_definition_carries_the_required_list_the_list_stopped_repeating(self):
        by_name = {t["function"]["name"]: t["function"] for t in REGISTRY.model_tools()}
        for spec in REGISTRY:
            # LESS thread_id, since 2026-09-18: the wire declaration never
            # carries it (the registry fills it from the call site), after the
            # second live score row saw a model enumerate read_plan(thread_id=
            # 2..196). See tests/test_a_model_never_sees_a_thread_number.py.
            wanted = [n for n in ((spec.schema or {}).get("required") or ()) if n != "thread_id"]
            parameters = by_name[spec.name].get("parameters") or {}
            with self.subTest(tool=spec.name):
                self.assertEqual(list(parameters.get("required") or ()), wanted)

    def test_the_long_form_makes_no_such_promise(self):
        """Because in that state no schemas are sent, and it would be false."""
        self.assertNotIn(
            "in the tool definitions sent with this message",
            capabilities.render(detail=True),
        )


class TheShortFormIsActuallySmallerTest(unittest.TestCase):
    def test_it_is_smaller_than_the_form_it_replaces(self):
        self.assertLess(
            len(capabilities.render(detail=False)),
            len(capabilities.render(detail=True)),
        )

    def test_the_saving_reaches_the_assembled_prompt(self):
        self.assertLess(
            len(instructions.assemble(tool_calling=True)),
            len(instructions.assemble(tool_calling=None)),
        )

    def test_the_version_moves_when_either_form_moves(self):
        """The digest covers both, because both ship.

        A version that hashed only the long form would report the same string
        for two turns run under genuinely different prompts, which is the exact
        hole content-addressing exists to close.
        """
        material = capabilities.digest_material()
        self.assertIn(capabilities.render(detail=True).encode("utf-8"), material)
        self.assertIn(capabilities.render(detail=False).encode("utf-8"), material)


def _line_for(text: str, name: str) -> str:
    """The one rendered line for a tool, so an assertion cannot match a neighbour."""
    for line in text.splitlines():
        if line.startswith(f"- `{name}`"):
            return line
    raise AssertionError(f"{name} does not appear in the rendered list at all")


if __name__ == "__main__":
    unittest.main()
