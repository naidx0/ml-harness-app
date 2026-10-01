"""A tool a person runs under a conversation is in that conversation.

The behaviour has been right since the owner asked "you sent 13 steps with 0
output - where are you getting this information from?": `run_tool_ep` writes the
same `tool.call` / `tool.result` pair the conductor writes, marked
`driven_by: "user"`, whenever the run is filed under a thread.

What was wrong was the sentence the CONTROLS DIALOG showed above the buttons -
"A tool run from here is not written to the transcript... it appends no event"
- which was true when it was written and false by the time anybody read it.
This test is the wall that keeps the two together: the claim the interface
makes about the product is checked against the product.

The frontend half is `Controls.tsx`; there is no assertion here about its
words, because a test that greps a sentence passes on a sentence that has been
edited into nonsense. What this holds is the BEHAVIOUR the sentence describes,
so a future change that makes the old text true again fails here first.
"""

from __future__ import annotations

import unittest

from app.main import app
from app import events
import support


class ARunAPersonFiledIsInTheThreadTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = support.sandbox(self)
        self.client = support.api_client(app)
        self.thread = int(support.conversations(1)[0]["id"])

    def _rows(self, thread_id: int) -> list[dict]:
        """The tool rows this thread holds, read the way every reader reads
        them. `since` hands back a decoded payload with every value marked as a
        claim (wall 3), so a string arrives wrapped; `_said` unwraps one."""
        return [
            row
            for row in events.since(f"thread:{thread_id}", 0)
            if row["kind"] in ("tool.call", "tool.result")
        ]

    @staticmethod
    def _said(value):
        if isinstance(value, dict) and "value" in value and "role" in value:
            return value["value"]
        return value

    def test_a_run_filed_under_a_conversation_writes_both_rows(self):
        answered = self.client.post(
            "/api/tools/inspect_hardware",
            json={"arguments": {}, "thread_id": self.thread},
        )
        self.assertEqual(answered.status_code, 200, answered.text)

        rows = self._rows(self.thread)
        kinds = [row["kind"] for row in rows]
        self.assertEqual(kinds, ["tool.call", "tool.result"])
        self.assertTrue(all(self._said(r["payload"]["driven_by"]) == "user" for r in rows))
        self.assertEqual(self._said(rows[0]["payload"]["name"]), "inspect_hardware")
        self.assertTrue(self._said(rows[1]["payload"]["ok"]))
        # The pair shares one id, which is what lets a reader join them.
        self.assertEqual(self._said(rows[0]["payload"]["id"]), self._said(rows[1]["payload"]["id"]))

    def test_a_run_with_no_conversation_files_nothing(self):
        """The other half of the sentence, and it is still true: a row belongs
        to a thread only when the caller said which one."""
        before = len(self._rows(self.thread))
        answered = self.client.post(
            "/api/tools/inspect_hardware",
            json={"arguments": {}},
        )
        self.assertEqual(answered.status_code, 200, answered.text)
        self.assertEqual(len(self._rows(self.thread)), before)


if __name__ == "__main__":
    unittest.main()
