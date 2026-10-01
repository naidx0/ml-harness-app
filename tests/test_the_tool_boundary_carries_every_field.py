"""A plan drawn through the tool is the plan a person gets.

## The defect this file was written against

`Situation.answer_field` has existed since the agent instruments landed, and
three proposers read it. `propose_build` - the registered tool a model actually
calls - never had the argument. Its `Situation(...)` constructor set
`input_field` and `expected_field` and stopped.

So there were two ways to draw the same plan and they disagreed:

* built by hand in a test, `answer_field` was the real column and the build ran;
* drawn through `POST /api/tools/propose_build`, it was `""`, the guard passed
  because it tested `input_field` alone, the plan was drawn, approved, declared -
  and the `rerun` step failed with

      12 row(s) of 12 carry no 'input', no 'expected' or no ''

  where the empty quotes at the end are the missing field printing itself.

**Every test of these builds constructed `Situation` by hand**, so the boundary
that a person actually crosses was the one nothing drove. That is the general
shape and it is why this file exists at the boundary rather than beside the
proposers.

## What is asserted

Two things, and the second is the one that would have caught it:

1. the tool accepts the argument at all; and
2. the plan it returns carries the value THROUGH to the step that grades, rather
   than accepting it and dropping it.

A test that only checked (1) would have passed against a constructor that took
the argument and ignored it.
"""

import json
import unittest
from pathlib import Path

from app import events
from app.tools import REGISTRY
import support


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "agent"
TRACES = str(FIXTURES / "journey-traces.jsonl")
TOOLDEFS = str(FIXTURES / "journey-tools.json")
FAILURES = str(FIXTURES / "journey-failures.jsonl")
AI_LEDGER = "docs/ledgers/ai_engineering.yaml"

PERSON_FACTS = {
    "target_success_rate": 0.9,
    "failure_reproduces": True,
    "simple_version_tried": True,
    "workflow_tried": True,
    "control_flow_is_dynamic": True,
}

#: The three columns a recording of somebody's agent run actually has. An eval
#: set has two - the question and the right answer. A FAILURE set has a third,
#: what the agent said, and forgetting it is the defect above.
FIELDS = {"input_field": "input", "expected_field": "expected", "answer_field": "answer"}


class TheToolBoundaryCarriesEveryFieldTest(unittest.TestCase):
    def setUp(self):
        support.sandbox(self)
        self.thread_id = events.create_thread("agent that fails", ledger=AI_LEDGER)["id"]
        for name, args in (
            ("read_agent_traces", {"path": TRACES}),
            ("read_tool_definitions", {"path": TOOLDEFS}),
            ("bound_the_loop", {"path": TRACES}),
            ("run_the_failures", {"failures_path": FAILURES, "traces_path": TRACES, **FIELDS}),
        ):
            result = REGISTRY.call(name, args, actor="user", thread_id=self.thread_id)
            self.assertTrue(result.get("ok"), f"{name}: {result}")
        stated = REGISTRY.call(
            "state_facts", {"facts": PERSON_FACTS}, actor="user", thread_id=self.thread_id
        )
        self.assertTrue(stated.get("ok"), stated)

    def _propose(self, **over):
        arguments = {
            # `facts` is required and empty is right: everything this thread
            # knows was stamped by the four instruments in setUp, and
            # `propose_build` assembles the sheet from the thread's own evidence.
            # Passing values here would be supplying what the tools measured.
            "facts": {},
            "failures_path": FAILURES,
            "traces_path": TRACES,
            **FIELDS,
            **over,
        }
        return REGISTRY.call(
            "propose_build", arguments, actor="user", thread_id=self.thread_id
        )

    def test_the_tool_takes_the_answer_column(self):
        """(1). Necessary, and on its own it proves nothing."""
        properties = set(REGISTRY.get("propose_build").schema.get("properties") or {})
        self.assertIn("answer_field", properties)

    def test_the_plan_it_draws_carries_that_column_into_the_grading_step(self):
        """(2). The assertion that would have caught the defect.

        Read out of the returned plan rather than off the Situation, because
        what a person approves is the JSON this tool handed back.
        """
        result = self._propose()
        self.assertTrue(result.get("ok"), result)

        blob = json.dumps(result.get("build") or {})
        self.assertIn(
            '"answer_field": "answer"',
            blob,
            "the tool accepted the column and dropped it before the step",
        )
        self.assertNotIn(
            '"answer_field": ""',
            blob,
            "a step was drawn with an empty answer column, which is the defect",
        )

    def test_omitting_it_is_refused_BEFORE_a_plan_is_drawn(self):
        """The guard used to name three fields and test one.

        A refusal before the plan is cheap. A plan that is drawn, approved,
        declared and then fails on the third column is the thing
        `NotEnoughToPropose` exists to prevent, and it is what the missing check
        produced.
        """
        result = self._propose(answer_field="")
        self.assertFalse(result.get("ok"), result)
        detail = json.dumps(result)
        self.assertIn("answer_field", detail)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
