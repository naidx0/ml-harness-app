"""The Stage reads a default the harness settled, and never answers a bare 500.

2026-09-23, on the owner's real thread 93: the Stage pane said
`500 from /api/threads/93/stage`. `stage.build` -> `journey_report.build` ->
`diagnosis.diagnose` -> `resolve_facts` raised

    FactError: fact 'task_family' was supplied with origin 'DEFAULTED'. ...
    Leave the fact out to get the default.

Thread 93 holds three DEFAULTED rows - `task_family`, `target_score`,
`privacy` - each written by the harness under permission `full`
(`app/full_defaults.py`), each with a `how` naming the rule and its numbers.
`journey_report.build` read the latest row per fact and wrapped every one in a
plain `diagnosis.Fact(value, origin)`, which is exactly the claim
`resolve_facts` refuses from a caller. The walk never met that refusal because
it reads the sheet through `evidence.assemble_facts`, the one producer of
`diagnosis.Settled` - the carrier that says "this DEFAULTED value is the
engine's own".

## WHY NOT "LEAVE THE FACT OUT", WHICH IS WHAT THE ERROR SAYS

The sentence is addressed to a caller who invented a DEFAULTED origin. These
rows were not invented: `evidence.record` refuses a DEFAULTED row from anybody
but the harness. Leaving them out would hand the engine the FILE's default, and
`target_score` declares none - so thread 93's report would read
BLOCKED__DEFINE_SUCCESS_FIRST, "nobody has defined success", about a thread
whose bar the harness had computed (0.269) and the walk was acting on. A Stage
that shows a different verdict from the one the conversation got is a second
opinion, and `app/journey.py` already says what that costs.

So the report's sheet is `assemble_facts`' sheet, and each exit below has a case
that produces only it:

  * a harness-settled DEFAULTED row -> 200, the settled value resolved, the
    origin still DEFAULTED, the verdict equal to the walk's;
  * a row whose origin the ledger cannot read -> 422 with the engine's sentence,
    never a bare 500 (the column is NOT NULL, so this is planted on the read);
  * no such thread -> 404, unchanged.
"""

from __future__ import annotations

import unittest
from unittest import mock

from app import diagnosis, journey_report, stage
from app.main import app
from app.tools import evidence
import support

SETTLED_BAR = 0.27


class TheStageReadsADefaultTheHarnessSettled(unittest.TestCase):
    def setUp(self):
        support.sandbox(self)
        self.client = support.api_client(app)
        self.thread = int(support.conversations(1)[0]["id"])
        self.ledger = evidence.ledger_for_thread(self.thread)
        token = evidence._STAMPING.set(True)
        try:
            evidence.record(
                fact="eval_size_n",
                value=40,
                origin=evidence.MEASURED,
                actor=evidence.MODEL,
                how="counted 40 rows in a test file",
                tool="measure_eval_set",
                thread_id=self.thread,
                ledger=self.ledger,
            )
        finally:
            evidence._STAMPING.reset(token)
        # Thread 93's two offenders that matter, written the way
        # `full_defaults` writes them: origin DEFAULTED, actor harness.
        for fact, value in (("target_score", SETTLED_BAR), ("task_family", "extraction")):
            evidence.record(
                fact=fact,
                value=value,
                origin=diagnosis.DEFAULTED,
                actor=evidence.HARNESS,
                how=f"Full: settled {fact} by a written rule, in a test",
                thread_id=self.thread,
                ledger=self.ledger,
            )

    def _sheet_the_report_diagnosed(self) -> tuple[dict, dict]:
        with mock.patch.object(
            journey_report.diagnosis, "diagnose", wraps=diagnosis.diagnose
        ) as spy:
            report = journey_report.build(self.thread)
        self.assertEqual(spy.call_count, 1)
        return report, spy.call_args.args[0]

    def test_a_settled_default_reaches_the_engine_as_the_harness_settled_it(self):
        report, sheet = self._sheet_the_report_diagnosed()
        values, origins = diagnosis.resolve_facts(sheet, self.ledger)
        self.assertEqual(values["target_score"], SETTLED_BAR)
        self.assertEqual(values["task_family"], "extraction")
        self.assertEqual(origins["target_score"], diagnosis.DEFAULTED)
        self.assertEqual(
            report["verdict"]["fact_origins"]["target_score"], diagnosis.DEFAULTED,
            "the report must still say the weakest word on the sheet",
        )

    def test_the_report_verdict_is_the_walk_s_and_not_the_file_default_s(self):
        report, _sheet = self._sheet_the_report_diagnosed()
        walked, _trail = evidence.assemble_facts(self.thread, ledger=self.ledger)
        walk = diagnosis.diagnose(walked, self.ledger)
        self.assertEqual(report["verdict"]["outcome"], walk.outcome)
        self.assertEqual(report["verdict"]["fact_origins"], walk.fact_origins)

        # THE NEGATIVE CONTROL: "leave it out" is a different, false verdict.
        # `target_score` declares no default, so the file's answer is null.
        left_out = {
            name: fact for name, fact in walked.items()
            if fact.origin != diagnosis.DEFAULTED
        }
        blind = diagnosis.diagnose(left_out, self.ledger)
        self.assertNotEqual(
            blind.outcome, walk.outcome,
            "if leaving the settled facts out changed nothing, this test proves nothing",
        )

    def test_the_stage_route_answers_200_with_the_diagnosis(self):
        response = self.client.get(f"/api/threads/{self.thread}/stage")
        self.assertEqual(response.status_code, 200, response.text[:400])
        payload = stage.build(self.thread)
        self.assertEqual(
            payload["diagnosis"]["verdict"]["fact_origins"]["task_family"],
            diagnosis.DEFAULTED,
        )
        self.assertEqual(
            response.json()["diagnosis"]["verdict"]["outcome"],
            payload["diagnosis"]["verdict"]["outcome"],
        )

    def test_an_origin_the_ledger_cannot_read_is_a_422_with_its_sentence(self):
        """Planted on the READ: `fact_evidence.origin` is NOT NULL and `record`
        validates it, so only a hand-edited or imported row could carry this."""
        real = evidence.rows_for

        def with_a_blank_origin(thread_id):
            rows = real(thread_id)
            return rows + [dict(rows[-1], fact="privacy", value="on_prem_only", origin=None)]

        with mock.patch.object(evidence, "rows_for", with_a_blank_origin):
            with self.assertRaises(diagnosis.FactError):
                stage.build(self.thread)
            for path in (
                f"/api/threads/{self.thread}/stage",
                f"/api/threads/{self.thread}/report",
                f"/api/threads/{self.thread}/export",
                f"/ui/report/{self.thread}",
            ):
                with self.subTest(path=path):
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, 422, response.text[:400])
                    self.assertIn("is not a fact origin", response.json()["detail"])

    def test_the_facts_table_is_the_sheet_the_verdict_walked(self):
        """Thread 93's shape: `eval_size_n` MEASURED (row 926), then STATED
        again by the model under Full (row 937). The walk keeps the measurement
        - a stated word does not outrank an instrument - and until 2026-09-23
        the "Facts on record" table showed the latest row, STATED, beside a
        verdict that had used MEASURED."""
        evidence.record(
            fact="eval_size_n",
            value=40,
            origin=evidence.STATED,
            actor=evidence.USER,
            how="said again after it was counted, in a test",
            tool="state_facts",
            thread_id=self.thread,
            ledger=self.ledger,
        )
        report = journey_report.build(self.thread)
        table = {row["fact"]: row for row in report["facts"]}
        self.assertEqual(table["eval_size_n"]["origin"], evidence.MEASURED)
        self.assertEqual(table["eval_size_n"]["tool"], "measure_eval_set")
        walked, _trail = evidence.assemble_facts(self.thread, ledger=self.ledger)
        # THE SET, not a hand-listed fact: every row the table draws carries
        # the origin the verdict used, and the table draws every fact the walk
        # was handed.
        self.assertEqual(set(table), set(walked))
        for name, row in table.items():
            with self.subTest(fact=name):
                self.assertEqual(row["origin"], report["verdict"]["fact_origins"][name])

    def test_every_fact_on_record_says_when_it_was_written(self):
        """The table read `written_at`; the column is `created_at`, so "When"
        was blank on every report ever rendered."""
        stored = {
            row["fact"]: row["created_at"] for row in evidence.rows_for(self.thread)
        }
        report = journey_report.build(self.thread)
        for row in report["facts"]:
            with self.subTest(fact=row["fact"]):
                self.assertTrue(row["written_at"], "a fact on record has a time")
                self.assertEqual(row["written_at"], stored[row["fact"]])
        page = journey_report.render_html(report)
        self.assertIn(f"<td>{stored['eval_size_n'][:19]}</td>", page)

    def test_no_such_thread_is_still_a_404(self):
        self.assertEqual(self.client.get("/api/threads/999999/stage").status_code, 404)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
