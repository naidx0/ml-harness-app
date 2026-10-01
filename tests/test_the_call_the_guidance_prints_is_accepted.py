"""The call the harness tells a model to make is a call the harness accepts.

Max's run of 2026-09-21. The walk stopped on `modality`, `run_diagnosis` said
to call state_facts with EXACTLY {"facts": {"modality": ...}}, and the model
reported that "state_facts cannot be called with the shape the engine names ...
`facts` is not a declared fact". Three shapes reached the tool that night and
every one of them was refused:

- the whole printed call pasted INTO the `facts` argument, one level deeper,
  refused as "'facts' is not a declared fact";
- the fact at the top level beside an empty `facts`, refused as "No facts were
  given" about a call that had given one;
- the object sent as a JSON string, which raised out of `dict()`.

And the shape that WAS accepted came back as "modality cannot, at this origin -
modality needs measure_eval_set", which the model read as a refusal: no gate
reads `modality`, the walk routes on it whatever its origin, and
measure_eval_set had already run.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402
from app import events  # noqa: E402
from app.tools import evidence  # noqa: E402
from app.tools.registry import REGISTRY  # noqa: E402


def _eval_file(folder: Path) -> Path:
    path = folder / "eval.jsonl"
    rows = [
        json.dumps({"input": f"question {i}", "expected": "yes" if i % 2 else "no"})
        for i in range(40)
    ]
    path.write_bytes(("\n".join(rows) + "\n").encode("utf-8"))
    return path


class TheCallTheGuidancePrintsIsAccepted(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(support.sandbox(self))
        self.thread = events.create_thread("the owner's walk")["id"]
        # Counted through the registry and nothing else: no `tool.call` row is
        # written, so nothing on this thread can derive a routing fact and the
        # walk has to stop on one.
        counted = REGISTRY.call(
            "measure_eval_set",
            {"path": str(_eval_file(self.root))},
            actor=evidence.MODEL,
            thread_id=self.thread,
        )
        self.assertTrue(counted["ok"], counted)
        stated = REGISTRY.call(
            "state_facts", {"facts": {"target_score": 0.8}}, actor=evidence.USER,
            thread_id=self.thread,
        )
        self.assertTrue(stated["ok"], stated)

    def walk(self) -> dict:
        return REGISTRY.call(
            "run_diagnosis", {"facts": {}}, actor=evidence.HARNESS, thread_id=self.thread
        )

    def printed_call(self, walked: dict) -> dict:
        """The JSON object the guidance tells the model to send, parsed."""
        found = re.search(r"(\{\"facts\": \{.*?\}\})", walked["next"])
        self.assertIsNotNone(found, walked["next"])
        return json.loads(found.group(1))

    def test_the_premise_the_walk_stops_on_a_routing_fact(self) -> None:
        walked = self.walk()
        self.assertEqual(walked["next_step"]["kind"], "gap", walked["next"])
        self.assertEqual(walked["next_step"]["tool"], "state_facts")

    def test_the_exact_printed_call_is_accepted_and_moves_the_walk(self) -> None:
        before = self.walk()
        fact = before["next_step"]["fact"]
        call = self.printed_call(before)
        out = REGISTRY.call("state_facts", call, actor=evidence.MODEL, thread_id=self.thread)
        self.assertTrue(out["ok"], out)
        self.assertEqual([row["fact"] for row in out["recorded"]], [fact])
        self.assertTrue(out["recorded"][0]["routes_the_walk_now"])
        self.assertNotIn("cannot, at this origin", out["summary"])
        self.assertNotIn(f"{fact} needs", out["summary"])
        after = self.walk()
        self.assertNotEqual(after.get("next_step", {}).get("fact"), fact)

    def test_the_printed_call_pasted_into_the_argument_is_accepted(self) -> None:
        call = self.printed_call(self.walk())
        out = REGISTRY.call(
            "state_facts", {"facts": call}, actor=evidence.MODEL, thread_id=self.thread
        )
        self.assertTrue(out["ok"], out)
        self.assertNotIn("facts", [row["fact"] for row in out["recorded"]])

    def test_a_fact_beside_an_empty_facts_object_is_read(self) -> None:
        fact, value = next(iter(self.printed_call(self.walk())["facts"].items()))
        out = REGISTRY.call(
            "state_facts", {"facts": {}, fact: value}, actor=evidence.MODEL,
            thread_id=self.thread,
        )
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["folded_into_facts"], [fact])

    def test_a_fact_at_the_top_level_alone_is_read(self) -> None:
        fact, value = next(iter(self.printed_call(self.walk())["facts"].items()))
        out = REGISTRY.call(
            "state_facts", {fact: value}, actor=evidence.MODEL, thread_id=self.thread
        )
        self.assertTrue(out["ok"], out)

    def test_the_object_sent_as_a_string_is_read(self) -> None:
        call = self.printed_call(self.walk())
        out = REGISTRY.call(
            "state_facts", {"facts": json.dumps(call["facts"])}, actor=evidence.MODEL,
            thread_id=self.thread,
        )
        self.assertTrue(out["ok"], out)

    def test_an_invented_name_at_the_top_level_is_still_refused_by_name(self) -> None:
        out = REGISTRY.call(
            "state_facts", {"you_have_an_eval_set": True}, actor=evidence.MODEL,
            thread_id=self.thread,
        )
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "rejected_fact")
        self.assertIn("you_have_an_eval_set", out["detail"])

    def test_an_empty_call_is_refused_with_the_exact_accepted_shape(self) -> None:
        out = REGISTRY.call(
            "state_facts", {"facts": {}}, actor=evidence.MODEL, thread_id=self.thread
        )
        self.assertFalse(out["ok"])
        shape = out["accepted_shape"]
        self.assertEqual(list(shape), ["facts"])
        self.assertEqual(list(shape["facts"]), out["the_walk_is_blocked_on"][:1])
        self.assertIn(json.dumps(shape), out["detail"])

    def test_no_guidance_line_prints_a_shape_without_the_wrapper(self) -> None:
        """Every `state_facts(...)` a reply prints carries `facts`."""
        source = (REPO / "app" / "tools" / "__init__.py").read_text(encoding="utf-8")
        bare = re.findall(r"state_facts\(\{\{'", source)
        self.assertEqual(bare, [], "a guidance sentence prints state_facts({'x': ...})")


if __name__ == "__main__":
    unittest.main()
