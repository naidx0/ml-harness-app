"""No tool a model can call may set a gate outcome. Proved, not asserted.

`AGENTS.md` invariant 4 says the five-gate test may never be weakened and no
`TRAIN__` outcome may be renamed out of the check. That guards the engine. This
file guards the other door: the tool surface, which is where a model would
reach if it wanted to be helpful about a gate.

The check is structural rather than a review convention. A future agent who
writes a tool declaring `writes=["gate_ledger"]`, or one accepting a `verdict`
argument, gets a red suite at import time rather than a merged change and a
product that agrees with whatever the user hoped.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app import db, diagnosis
from app.tools import REGISTRY
from app.tools.registry import (
    ApprovalRequired,
    Control,
    Registry,
    RESERVED_ARGUMENTS,
    RESERVED_WRITES,
    ToolError,
    ToolSpec,
)

import support


def _spec(**overrides):
    base = dict(
        name="probe_tool",
        description="A tool used only by this test.",
        schema={"type": "object", "properties": {}},
        reads=(),
        writes=(),
        approval="never",
        # WALL 7: a tool declares which capability block it is in, from the
        # engine's published vocabulary, or it does not register. A throwaway
        # probe is still a tool, so it still says.
        provides=("context.dataset.preview",),
        control=Control(label="Probe", group="Test", verb="probe"),
        handler=lambda: {"ok": True},
    )
    base.update(overrides)
    return ToolSpec(**base)


class TheHardRuleTest(unittest.TestCase):
    """Three walls, each tested on its own.

    `setUp` sandboxes because `run_diagnosis` now reads the fact-evidence
    ledger before it walks the tree - the measured facts of this thread are
    merged over whatever the caller supplied - and a test that reads a store
    needs a store of its own. It had none while the tool touched nothing.
    """

    def setUp(self):
        self.root = support.sandbox(self)

    def test_no_registered_tool_declares_a_reserved_write(self):
        """Wall 1, applied to the tools that actually ship."""
        for spec in REGISTRY:
            with self.subTest(tool=spec.name):
                claimed = {w.lower() for w in spec.writes}
                self.assertEqual(
                    claimed & RESERVED_WRITES,
                    set(),
                    f"{spec.name} claims authority over a gate outcome",
                )

    def test_registering_a_tool_that_writes_a_gate_is_refused(self):
        registry = Registry()
        for reserved in sorted(RESERVED_WRITES):
            with self.subTest(write=reserved):
                with self.assertRaises(ToolError) as caught:
                    registry.add(_spec(writes=(reserved,)))
                self.assertIn("gate outcome", str(caught.exception))

    def test_no_registered_tool_accepts_a_reserved_argument(self):
        """Wall 2, applied to the tools that actually ship."""
        for spec in REGISTRY:
            properties = spec.schema.get("properties") or {}
            for key in properties:
                with self.subTest(tool=spec.name, argument=key):
                    self.assertNotIn(key.lower(), RESERVED_ARGUMENTS)

    def test_registering_a_tool_that_accepts_a_verdict_is_refused(self):
        registry = Registry()
        for reserved in sorted(RESERVED_ARGUMENTS):
            with self.subTest(argument=reserved):
                with self.assertRaises(ToolError):
                    registry.add(
                        _spec(
                            schema={
                                "type": "object",
                                "properties": {reserved: {"type": "string"}},
                            }
                        )
                    )

    def test_the_diagnosis_tool_computes_the_verdict_rather_than_taking_one(self):
        """Wall 3. The model supplies facts; the engine walks the tree.

        A fact sheet with nothing in it must not produce a training
        recommendation, and the outcome must be the engine's own.
        """
        spec = REGISTRY.get("run_diagnosis")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.writes, ())
        self.assertEqual(sorted((spec.schema.get("properties") or {})), ["facts"])

        result = REGISTRY.call("run_diagnosis", {"facts": {}})
        self.assertTrue(result["ok"])
        self.assertEqual(result["decided_by"], "app/diagnosis.py")
        self.assertFalse(
            result["outcome"].startswith("TRAIN__"),
            "an empty fact sheet reached a training outcome",
        )

    def test_a_model_cannot_smuggle_a_gate_in_as_a_fact(self):
        """Gate ids are not facts, and the engine rejects anything that is not.

        This is the same wall `diagnosis.validate_facts` already builds; the
        test is here because this is the door a model would knock on.
        """
        for gate in (
            "G0_EVAL_SET",
            "G1_BASELINE_MEASURED",
            "G2_PROMPT_EXHAUSTED",
            "G3_RETRIEVAL_CONSIDERED",
            "G4_CHEAPER_MODEL_CONSIDERED",
        ):
            with self.subTest(gate=gate):
                result = REGISTRY.call("run_diagnosis", {"facts": {gate: True}})
                self.assertFalse(result["ok"])
                self.assertEqual(result["error"], "rejected_fact")

        spec = diagnosis.default_spec()
        self.assertEqual(
            [name for name in spec.facts if diagnosis.GATE_ID_RE.match(name)],
            [],
            "a fact is now named like a gate, which reopens the door",
        )

    def test_a_model_cannot_smuggle_a_verdict_in_through_an_extra_argument(self):
        """Arguments outside the schema are dropped, and the drop is visible.

        Rewritten when reserved names got their own report. A name from
        `RESERVED_ARGUMENTS` comes back as `refused_arguments`, not merely
        `ignored_arguments`, because a caller reaching for `outcome` is doing
        something a caller reaching for `wobble` is not.
        """
        result = REGISTRY.call(
            "run_diagnosis", {"facts": {}, "outcome": "TRAIN__LORA", "wobble": 1}
        )
        self.assertEqual(result["refused_arguments"], ["outcome"])
        self.assertEqual(result["ignored_arguments"], ["wobble"])
        self.assertNotEqual(result["outcome"], "TRAIN__LORA")


class OneDeclarationTwoCallersTest(unittest.TestCase):
    """VISION: every tool is also a control. One declaration, or it drifts."""

    def test_every_tool_is_also_a_control(self):
        controls = {c["name"] for c in REGISTRY.controls()}
        models = {t["function"]["name"] for t in REGISTRY.model_tools()}
        self.assertEqual(controls, models)
        self.assertEqual(controls, set(REGISTRY.names()))

    def test_a_control_field_exists_for_every_schema_property(self):
        for control in REGISTRY.controls():
            spec = REGISTRY.get(control["name"])
            properties = set((spec.schema.get("properties") or {}).keys())
            fields = {f["name"] for f in control["fields"]}
            with self.subTest(tool=control["name"]):
                self.assertEqual(fields, properties)

    def test_a_control_carries_what_a_person_needs_to_press_it(self):
        for control in REGISTRY.controls():
            with self.subTest(tool=control["name"]):
                self.assertTrue(control["label"].strip())
                self.assertTrue(control["group"].strip())
                self.assertTrue(control["verb"].strip())
                self.assertTrue(control["description"].strip())
                self.assertIn("needs_approval", control)

    def test_the_model_declaration_is_openai_shaped(self):
        for declaration in REGISTRY.model_tools():
            self.assertEqual(declaration["type"], "function")
            function = declaration["function"]
            self.assertTrue(function["name"])
            self.assertTrue(function["description"])
            self.assertEqual(function["parameters"]["type"], "object")


class RegistryBehaviourTest(unittest.TestCase):
    def test_a_duplicate_name_is_refused(self):
        registry = Registry()
        registry.add(_spec())
        with self.assertRaises(ToolError):
            registry.add(_spec())

    def test_a_bad_name_is_refused(self):
        registry = Registry()
        for name in ("", "A", "Has Spaces", "UPPER", "x"):
            with self.subTest(name=name):
                with self.assertRaises(ToolError):
                    registry.add(_spec(name=name))

    def test_a_tool_with_no_description_is_refused(self):
        """A model cannot choose a tool it cannot read."""
        registry = Registry()
        with self.assertRaises(ToolError):
            registry.add(_spec(description="   "))

    def test_approval_is_enforced_at_the_only_call_site(self):
        registry = Registry()
        registry.add(_spec(approval="always"))
        with self.assertRaises(ApprovalRequired):
            registry.call("probe_tool")
        self.assertEqual(registry.call("probe_tool", approved=True), {"ok": True})

    def test_an_unknown_approval_value_is_refused(self):
        registry = Registry()
        with self.assertRaises(ToolError):
            registry.add(_spec(approval="sometimes"))

    def test_calling_an_unregistered_tool_raises(self):
        with self.assertRaises(ToolError):
            Registry().call("nothing_like_this")

    def test_the_decorator_leaves_the_function_callable(self):
        registry = Registry()

        @registry.tool(
            "double_it",
            description="Double a number.",
            schema={
                "type": "object",
                "properties": {"n": {"type": "integer"}},
                "required": ["n"],
            },
            provides=("context.dataset.preview",),
            label="Double",
            group="Test",
            verb="double a number",
        )
        def double_it(n: int) -> dict:
            return {"n": n * 2}

        self.assertEqual(double_it(3), {"n": 6})
        self.assertEqual(registry.call("double_it", {"n": 3}), {"n": 6})


class SeedToolsTest(unittest.TestCase):
    """The three tools that make the loop exercisable."""

    def setUp(self):
        self.root = support.sandbox(self)

    def test_inspect_hardware_returns_provenance_for_every_number(self):
        result = REGISTRY.call("inspect_hardware")
        self.assertIn("provenance", result)
        for key in ("ram_gb", "disk_free_gb", "vram_gb"):
            with self.subTest(field=key):
                self.assertIn(key, result)
                self.assertIn(key, result["provenance"])

    def test_list_runs_reads_the_database(self):
        db.create_run("first", "{}")
        db.create_run("second", "{}")
        result = REGISTRY.call("list_runs")
        self.assertEqual(result["count"], 2)
        self.assertEqual({r["name"] for r in result["runs"]}, {"first", "second"})
        self.assertEqual(result["provenance"]["count"], "measured")

    def test_list_runs_bounds_a_hostile_limit(self):
        db.create_run("only", "{}")
        self.assertEqual(REGISTRY.call("list_runs", {"limit": -5})["returned"], 1)
        self.assertEqual(
            REGISTRY.call("list_runs", {"limit": "not a number"})["returned"], 1
        )

    def test_run_diagnosis_reports_a_bad_fact_rather_than_crashing(self):
        result = REGISTRY.call("run_diagnosis", {"facts": {"not_a_fact": 1}})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "rejected_fact")


if __name__ == "__main__":
    unittest.main()
