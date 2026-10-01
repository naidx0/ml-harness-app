"""`generate_tool_rows`: the chain is real, the question comes last.

`app/tools/chainfirst.py` says why. Pinned here:

- the row carries prompt/completion for the LoRA recipe, and the chain with
  the real result excerpts beside them;
- the executors are the registry: the result in the row is what the tool
  returned here, not what the model said it returned;
- only approval-free, write-nothing, local-read tools may be in a chain,
  derived from what each declares; naming another is refused;
- a proposal the selector rejects is reported on the kept step.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402
from app.providers import Delta  # noqa: E402
from app.tools import chainfirst, invent  # noqa: E402
from app.tools.registry import REGISTRY  # noqa: E402


class _Scripted:
    def __init__(self, scripts):
        self.scripts = list(scripts)
        self.asked: list[list[dict]] = []

    def stream(self, messages, tools=None, *, secret=None):
        self.asked.append([dict(m) for m in messages])
        text = self.scripts.pop(0) if self.scripts else ""
        yield Delta(kind="text", text=text)
        yield Delta(kind="end")


PROPOSE = json.dumps({"tool": "list_runs", "arguments": {}})
PROPOSE_TWO = "\n".join(
    [
        json.dumps({"tool": "delete_sandbox", "arguments": {"name": "x"}}),
        json.dumps({"tool": "list_runs", "arguments": {}}),
    ]
)
QUESTION = json.dumps({"question": "What has been run in this project so far?", "answer": "No training runs are recorded yet."})


class _ChainFirst(unittest.TestCase):
    def setUp(self) -> None:
        self.root = support.sandbox(self)
        self.original_build = invent.build
        self.original_active = invent.store.active
        invent.store.active = lambda: {"id": 1, "adapter": "ollama", "base_url": "http://127.0.0.1:11434", "model": "fake-gen"}
        self.addCleanup(setattr, invent, "build", self.original_build)
        self.addCleanup(setattr, invent.store, "active", self.original_active)

    def install(self, scripts) -> _Scripted:
        provider = _Scripted(scripts)
        invent.build = lambda *a, **k: provider
        return provider

    def generate(self, **kw):
        return chainfirst.generate_tool_rows(
            task="Answer questions about this project's runs by calling the right tools.",
            into=str(self.root / kw.pop("into", "rows")),
            **kw,
        )


class ARowIsAChainThatRanTest(_ChainFirst):
    def test_prompt_completion_and_the_real_result_ride_together(self):
        provider = self.install([PROPOSE, QUESTION])
        out = self.generate(count=1, chain_length=1, tools=["list_runs"])
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["rows_written"], 1)
        rows = [json.loads(line) for line in Path(out["rows_path"]).read_text(encoding="utf-8").splitlines()]
        row = rows[0]
        self.assertEqual(row["origin"], "chain_first")
        self.assertEqual(row["question"], "What has been run in this project so far?")
        self.assertIn("Question: What has been run", row["prompt"])
        self.assertIn("- list_runs:", row["prompt"], "the tools offered are in the prompt")
        self.assertEqual(json.loads(row["completion"]), {"tool": "list_runs", "arguments": {}})
        self.assertEqual(row["chain"][0]["tool"], "list_runs")
        self.assertIn("the runs table in this harness database", row["chain"][0]["result_excerpt"], "the excerpt is the registry's result")
        self.assertTrue(row["generated"] and row["synthetic"])
        # The updater was shown the real result, not asked to imagine one.
        updater_request = provider.asked[-1]
        self.assertIn("list_runs", updater_request[-1]["content"])
        manifest = json.loads(Path(out["manifest_path"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest["operation"], "generate_tool_rows")
        self.assertEqual(manifest["rows_written"], 1)

    def test_a_rejected_proposal_is_reported_on_the_kept_step(self):
        self.install([PROPOSE_TWO, QUESTION])
        out = self.generate(count=1, chain_length=1, tools=["list_runs"])
        row = json.loads(Path(out["rows_path"]).read_text(encoding="utf-8").splitlines()[0])
        rejected = row["chain"][0]["rejected"]
        self.assertEqual(rejected[0]["tool"], "delete_sandbox")
        self.assertIn("not a tool a chain may call", rejected[0]["why"])

    def test_a_chain_that_never_ran_writes_no_row(self):
        self.install(["not json at all", "still not"])
        out = self.generate(count=1, chain_length=1, tools=["list_runs"])
        self.assertFalse(out["ok"])
        self.assertEqual(out["rows_written"], 0)
        self.assertGreater(out["unparseable_replies"], 0)


class OnlyHarmlessToolsMayBeInAChainTest(_ChainFirst):
    def test_the_candidate_set_is_derived_from_declarations(self):
        names = {spec.name for spec in chainfirst.candidates()}
        self.assertIn("list_runs", names)
        for spec in chainfirst.candidates():
            with self.subTest(tool=spec.name):
                self.assertEqual(spec.approval, "never")
                self.assertEqual(spec.writes, ())
                self.assertEqual(spec.measures, ())
        for name in REGISTRY.names():
            spec = REGISTRY.get(name)
            if spec.approval == "always" or spec.writes:
                self.assertNotIn(name, names)
        for name in chainfirst.NEVER_IN_A_CHAIN:
            self.assertNotIn(name, names)

    def test_naming_a_tool_a_chain_may_not_call_is_refused_with_the_list(self):
        self.install([PROPOSE, QUESTION])
        out = self.generate(count=1, tools=["delete_sandbox"])
        self.assertEqual(out["error"], "not_chainable")
        self.assertIn("list_runs", out["chainable"])
        self.assertTrue(out["nothing_was_written"])

    def test_a_task_too_short_to_teach_anything_is_refused(self):
        self.install([PROPOSE, QUESTION])
        out = chainfirst.generate_tool_rows(task="rows", into=str(self.root / "r"))
        self.assertEqual(out["error"], "no_task")


if __name__ == "__main__":
    unittest.main()
