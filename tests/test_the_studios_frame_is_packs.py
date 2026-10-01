"""The studios frame is not a second list beside the capability blocks.

A studio is a pack, read live off the registry through CAPABILITIES rather
than typed in a second manifest, so a tool that declares provides= on a new
capability is a pack on the day it is added rather than on the day somebody
remembers this endpoint.
"""

import unittest

from app.main import app
import support


class StudiosArePacks(unittest.TestCase):
    def setUp(self):
        support.sandbox(self)
        self.client = support.api_client(app)

    def test_the_frame_lists_every_pack_and_what_is_in_it(self):
        response = self.client.get("/api/studios")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("packs", body)
        self.assertIn("core", body)
        self.assertIn("agent", body["packs"])
        self.assertIn("ledger", body["core"])
        # pack_index is derived, not typed - every registered tool appears in
        # exactly one pack's list, and every pack with tools appears.
        pack_index = body["pack_index"]
        all_tools = {t for tools in pack_index.values() for t in tools}
        from app.tools.registry import REGISTRY

        self.assertEqual(all_tools, set(REGISTRY.names()))
        self.assertIn("read_agent_traces", pack_index.get("agent", []))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
