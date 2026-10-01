"""A call written as text in the round-cap answer runs, behind MLH_CAP_CALL=1.

Journey databases 2026-09-24 to 26: at the round cap the harness asks for an
answer with no tools on the wire, the owner's model writes its next move as a
`<function name=...>` tag, and the turn ended on the tag (4 of 7 lost calls).
Laws: with the flag on, exactly one whole tag naming a tool this turn offered
runs once and the turn still ends `answered_after_round_cap`; two tags, a tool
never offered, or the flag off, and nothing runs.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from app import conductor  # noqa: E402
from test_a_turn_always_speaks import ScriptedProvider, TurnTestCase, asks_n, says  # noqa: E402

TAG = '<function name="list_runs">{"limit": 99}</function>'


class ACallWrittenAtTheRoundCapRunsTest(TurnTestCase):
    def turn(self, last, flag="1"):
        self.connect()
        thread_id = self.new_thread()
        self.install(ScriptedProvider([*asks_n(8), says(last)]))
        env = {conductor.CAP_CALL_FLAG: flag} if flag else {}
        with mock.patch.dict(os.environ, env, clear=False):
            if not flag:
                os.environ.pop(conductor.CAP_CALL_FLAG, None)
            list(conductor.run_turn(thread_id, max_tool_rounds=8))
        rows = self.rows(thread_id)
        calls = [r for r in rows if r["kind"] == "tool.call"]
        return calls, rows[-1]["payload"]

    def test_one_tag_runs_once(self):
        calls, end = self.turn("Next I list the runs.\n" + TAG)
        self.assertEqual(len(calls), 9)
        self.assertEqual(calls[-1]["payload"]["name"], "list_runs")
        self.assertEqual(end["ending"], "answered_after_round_cap")

    def test_flag_off_runs_nothing(self):
        calls, end = self.turn(TAG, flag="")
        self.assertEqual(len(calls), 8)
        self.assertEqual(end["ending"], "answered_after_round_cap")

    def test_two_tags_run_nothing(self):
        calls, _ = self.turn(TAG + "\n" + TAG.replace("99", "98"))
        self.assertEqual(len(calls), 8)

    def test_a_tool_never_offered_runs_nothing(self):
        calls, _ = self.turn('<function name="delete_sandbox"></function>')
        self.assertEqual(len(calls), 8)


class MiniCPMParamBodiesTest(TurnTestCase):
    """`<param name="k">v</param>` bodies read as arguments, only under the flag."""

    def read(self, flag):
        from app.providers import _text_call
        tag = ('<function name="measure_eval_set"><param name="path">data/splits/eval.jsonl'
               '</param><param name="limit">40</param></function>')
        with mock.patch.dict(os.environ, {conductor.CAP_CALL_FLAG: flag}):
            return _text_call(tag, frozenset({"measure_eval_set"}))

    def test_params_are_arguments_with_the_flag(self):
        self.assertEqual(
            self.read("1"),
            ("measure_eval_set", {"path": "data/splits/eval.jsonl", "limit": 40}),
        )

    def test_params_stay_text_without_it(self):
        self.assertIsNone(self.read(""))
