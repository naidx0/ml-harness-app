"""A tool run a person files under a thread appears in that thread.

The owner, reading a thread whose whole journey had been driven through the
user door (2026-09-01): "you sent 13 steps with 0 output... the model didn't
do any work, where are you getting this information from?" Every run was
real — the ledger, the bench and the files held all of it — and the
transcript showed none of it, because only the conductor ever wrote
`tool.call`/`tool.result` rows.

The walls:

  - a user-door run WITH a thread_id writes the same event pair the
    conductor writes, marked `driven_by: "user"`, carrying the result;
  - a run WITHOUT a thread_id writes nothing — a row belongs to a
    conversation only when the caller said which one, which is also what
    keeps self-refreshing surfaces (the attach popover's listing) quiet;
  - a refused run leaves no dangling row: the events are appended after the
    tool answered, so a 404/428 writes neither half of the pair.
"""

import unittest

from app import events, main
import support


def _tool_events(thread_id: int) -> list[dict]:
    rows = events.since(f"thread:{thread_id}", 0)
    return [row for row in rows if str(row.get("kind", "")).startswith("tool.")]


class ARunYouFiledIsARowYouCanSeeTest(unittest.TestCase):
    def setUp(self):
        support.sandbox(self)
        self.client = support.api_client(main.app)
        self.thread = events.create_thread("a visible journey")

    def test_a_filed_run_writes_the_pair_the_conductor_writes(self):
        answer = self.client.post(
            "/api/tools/list_context",
            json={"arguments": {}, "thread_id": self.thread["id"]},
        )
        self.assertEqual(answer.status_code, 200)
        pair = _tool_events(self.thread["id"])
        self.assertEqual([row["kind"] for row in pair], ["tool.call", "tool.result"])
        call, result = pair[0]["payload"], pair[1]["payload"]
        self.assertEqual(call["name"], "list_context")
        self.assertEqual(call["driven_by"], "user")
        self.assertEqual(result["id"], call["id"])
        self.assertTrue(result["ok"])
        self.assertIn("contexts", result["result"])

    def test_a_run_with_no_thread_stays_off_every_transcript(self):
        answer = self.client.post(
            "/api/tools/list_context", json={"arguments": {}}
        )
        self.assertEqual(answer.status_code, 200)
        self.assertEqual(
            _tool_events(self.thread["id"]),
            [],
            "a run nobody filed under a conversation must not appear in one",
        )

    def test_a_thread_that_does_not_exist_cannot_be_filed_under(self):
        answer = self.client.post(
            "/api/tools/list_context",
            json={"arguments": {}, "thread_id": 987654},
        )
        self.assertEqual(answer.status_code, 404)
        self.assertEqual(_tool_events(987654), [])

    def test_a_refused_run_leaves_no_dangling_row(self):
        answer = self.client.post(
            "/api/tools/no_such_tool_anywhere",
            json={"arguments": {}, "thread_id": self.thread["id"]},
        )
        self.assertEqual(answer.status_code, 404)
        self.assertEqual(_tool_events(self.thread["id"]), [])

    def test_a_tool_that_answers_not_ok_is_a_failed_row_not_a_green_one(self):
        """The specimen is DERIVED, not named.

        This called `run_diagnosis` with no arguments, which used to refuse
        because `facts` was required. That argument became optional on
        2026-09-11 and the call started succeeding - so a test about how a
        FAILED row is recorded quietly became a test about a green one.
        See `support.a_tool_that_requires_an_argument`.
        """
        tool = support.a_tool_that_requires_an_argument()
        answer = self.client.post(
            "/api/tools/" + tool.name,
            json={"arguments": {}, "thread_id": self.thread["id"]},
        )
        self.assertEqual(answer.status_code, 200)
        body = answer.json()["result"]
        self.assertFalse(
            body.get("ok", True),
            tool.name + " answered ok to a call missing " + str(list(tool.schema["required"])),
        )
        pair = _tool_events(self.thread["id"])
        self.assertEqual(pair[-1]["kind"], "tool.result")
        self.assertFalse(pair[-1]["payload"]["ok"])


if __name__ == "__main__":
    unittest.main()
