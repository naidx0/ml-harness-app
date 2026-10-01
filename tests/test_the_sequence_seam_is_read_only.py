"""What this product can read out of Sequence, and what it still refuses.

Sequence is the other repository on this machine
(`C:/Users/example/Projects/sequence`): a static
architecture analyser whose MCP server declares fifteen tools. The temptation
with two products on one disk is to wire them together. This file is the
opposite: it records, as tests, the two things ml-harness can honestly do with
Sequence today and the walls that stay up around them.

## The fixture is real, and how it was made is the point

`tests/fixtures/agent/sequence-mcp-tools.json` is a genuine `tools/list`
answer, spoken over stdio to `packages/mcp/dist/server.js` on 2026-09-02 by a
one-off script that lives outside this repository. It sent `initialize` and
`tools/list` and never `tools/call`.

That does not breach the invariant `app/tools/agents.py` states at
`REFUSALS["mcp_server"]` - *the product never spawns an MCP server* - and the
distinction is worth writing down rather than assuming: the refusal is about
what the PRODUCT does at runtime, on a user's machine, to a server it was
pointed at. Nothing in `app/` gained the ability to spawn anything. What
changed is that the fixture this suite reads is now a real server's words
instead of a hand-typed approximation of them, which makes the reader's
`shape: "mcp"` claim testable against something that was not written to
please it.

## The .seqd schema is refused, and the refusal is the feature

Sequence's diagram schema uses `$ref` and `$defs`. `app/tools/shapes.py`
implements a bounded subset of JSON Schema and REFUSES a schema using
keywords it does not implement, rather than skipping them and reporting a
compliance figure it did not really measure. Resolving `$ref` is far past a
bounded step and there is no queue row for it, so this test locks the refusal
rather than removing it - naming every keyword, so that adding support later
is a visible change to a list somebody must edit on purpose.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.tools import agents, shapes

import support

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "agent"
MCP_TOOLS = FIXTURES / "sequence-mcp-tools.json"
SEQD_SCHEMA = FIXTURES / "seqdiagram-v1.json"

#: The fifteen Sequence declares, in the order the server listed them.
SEQUENCE_TOOLS = [
    "scan_repo",
    "who_calls",
    "architecture_changed",
    "coverage",
    "find_negatives",
    "path_between",
    "explain_repo",
    "plain_tree",
    "classify_repo",
    "design_suggest",
    "validate_diagram",
    "export_diagram",
    "risks",
    "impact",
    "whiteboard",
]


class TheSavedToolsListReadsAsMcpTest(unittest.TestCase):
    def setUp(self):
        support.sandbox(self)
        self.thread = int(support.conversations(1)[0]["id"])

    def _read(self, path: Path) -> dict:
        from app.tools import REGISTRY, evidence

        return REGISTRY.call(
            "read_tool_definitions",
            {"path": str(path)},
            actor=evidence.USER,
            thread_id=self.thread,
        )

    def test_the_fifteen_tools_are_read_as_mcp(self):
        answered = self._read(MCP_TOOLS)

        self.assertTrue(answered.get("ok"), answered)
        self.assertEqual(answered["read_as"], "mcp x15")
        self.assertEqual(answered["tool_count"], 15)
        self.assertEqual(
            [tool["name"] for tool in answered["tools"]], SEQUENCE_TOOLS
        )

    def test_a_real_server_declares_what_the_reader_asks_of_it(self):
        """The reader's own quality columns, against words nobody wrote for it.

        A hand-typed fixture passes these by construction, which is why it is
        worth running them against a document a different product emitted:
        every one of Sequence's fifteen tools carries a description, no two
        names collide, and none of the descriptions addresses the model in the
        second person - the smell `descriptions_that_talk_to_the_model` looks
        for. Recording that here means a future Sequence release that breaks
        it shows up as a failing test rather than as nothing.
        """
        answered = self._read(MCP_TOOLS)

        self.assertEqual(answered["without_a_description"], [])
        self.assertEqual(answered["name_collisions"], [])
        self.assertEqual(answered["refusals"], [])
        self.assertEqual(answered["provenance"]["tool_count"], "measured")

    def test_the_fixture_is_a_real_answer_and_says_so(self):
        """A fixture that cannot say where it came from is a hand-typed one."""
        document = json.loads(MCP_TOOLS.read_text(encoding="utf-8"))

        recorded = document["_recorded"]
        self.assertEqual(recorded["server"]["name"], "@sequence/mcp")
        self.assertIn("initialize, then tools/list", recorded["command"])
        self.assertIn("never tools/call", recorded["command"])
        # The saved shape is a JSON-RPC response, which is what a client
        # would actually have on disk.
        self.assertEqual(document["jsonrpc"], "2.0")
        self.assertEqual(len(document["result"]["tools"]), len(SEQUENCE_TOOLS))

    def test_the_product_still_refuses_to_speak_to_a_live_server(self):
        """Reading a saved answer did not buy a connection."""
        refusal = agents.REFUSALS["mcp_server"]
        text = json.dumps(refusal) if not isinstance(refusal, str) else refusal
        self.assertRegex(text.lower(), r"never|refus|does not|not spawn")


class TheSeqdSchemaIsRefusedByNameTest(unittest.TestCase):
    """Every keyword the checker will not implement, listed.

    Measured 2026-09-02 against Sequence's `seqdiagram-v1.json`: thirteen
    keywords, and `minItems` is NOT among them because it sits inside `$defs`,
    which the walker reports whole rather than descending into. That absence
    is asserted too - it is the difference between "we checked the nested
    definitions" and "we stopped at the door", and only one of those is true.
    """

    EXPECTED = [
        "$.$defs",
        "$.properties.boundaries.items.$ref",
        "$.properties.edges.items.$ref",
        "$.properties.externalDependencies.items.$ref",
        "$.properties.flows.items.$ref",
        "$.properties.grounded.properties.graphId.minLength",
        "$.properties.grounded.properties.scopeNodeIds.items.minLength",
        "$.properties.grounded.properties.unknowns.items.minLength",
        "$.properties.groups.items.$ref",
        "$.properties.nodes.items.$ref",
        "$.properties.primaryNodeIds.items.minLength",
        "$.properties.title.minLength",
        "$.properties.unknowns.items.minLength",
    ]

    def test_the_walker_names_thirteen_keywords_and_no_others(self):
        schema = json.loads(SEQD_SCHEMA.read_text(encoding="utf-8"))

        found = shapes.unsupported_keywords(schema)

        self.assertEqual(sorted(found), self.EXPECTED)

    def test_six_refs_and_six_minlengths_and_the_defs_block(self):
        found = shapes.unsupported_keywords(
            json.loads(SEQD_SCHEMA.read_text(encoding="utf-8"))
        )
        self.assertEqual(len([f for f in found if f.endswith(".$ref")]), 6)
        self.assertEqual(len([f for f in found if f.endswith(".minLength")]), 6)
        self.assertIn("$.$defs", found)

    def test_min_items_is_absent_because_the_walker_stops_at_defs(self):
        raw = SEQD_SCHEMA.read_text(encoding="utf-8")
        self.assertIn(
            "minItems", raw, "the fixture no longer contains minItems at all"
        )
        found = shapes.unsupported_keywords(json.loads(raw))
        self.assertEqual(
            [f for f in found if f.endswith(".minItems")],
            [],
            "minItems surfaced, so the walker now descends into $defs and this "
            "test's whole argument needs rewriting",
        )

    def test_ref_is_not_quietly_supported(self):
        """The one keyword whose support would change every answer above."""
        self.assertNotIn("$ref", shapes.SUPPORTED)
        self.assertNotIn("$defs", shapes.SUPPORTED)


if __name__ == "__main__":
    unittest.main()
