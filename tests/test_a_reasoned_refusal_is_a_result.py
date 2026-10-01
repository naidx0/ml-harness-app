"""A harness tool that ran and refused, with its reasons, is shown as a result.

The harness's tools refuse as data - "no plan, and why", a carve that found
leakage - and the outgoing transcript drew each refusal as its own card. The
facade used to send every `ok: false` as their `session.tool.failed`, and
their renderer shows its generic error card before it consults the tool-card
registry, so the reasons never reached the screen. These tests hold the line
between the two kinds of "no": a refusal the tool made (a result) and one it
never got to make (a failure).
"""

from __future__ import annotations

import unittest

import support  # noqa: F401  - puts the repo root on the path

from app.facade.translate import reasoned_refusal


def payload(result, ok=True):
    return {"name": "carve_rows", "ok": ok, "result": result}


class ReasonedRefusalTest(unittest.TestCase):
    def test_a_refusal_with_reasons_is_a_result(self):
        self.assertTrue(
            reasoned_refusal(payload({"ok": False, "error": "leakage", "detail": "3 rows overlap", "overlap": [1, 2, 3]}))
        )

    def test_a_bare_refusal_stays_a_failure(self):
        self.assertFalse(reasoned_refusal(payload({"ok": False, "error": "tool_failed", "detail": "boom"})))

    def test_a_tool_that_never_ran_stays_a_failure(self):
        for kind in ("approval_required", "not_offered", "no_such_tool", "malformed_call"):
            with self.subTest(kind=kind):
                self.assertFalse(reasoned_refusal(payload({"ok": False, "error": kind, "why": "x"})))

    def test_a_crashed_call_stays_a_failure(self):
        self.assertFalse(reasoned_refusal(payload({"ok": False, "error": "x", "rows": []}, ok=False)))

    def test_a_success_is_not_a_refusal(self):
        self.assertFalse(reasoned_refusal(payload({"ok": True, "rows": []})))
        self.assertFalse(reasoned_refusal(payload("plain text")))


if __name__ == "__main__":
    unittest.main()
