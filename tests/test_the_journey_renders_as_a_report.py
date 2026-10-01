"""Phase C's first surface: the journey as a page somebody can read.

The Phase-B journey already proved the loop closes; this file proves it can be
HANDED OVER. `app/journey_report.py` composes one conversation - verdict, gates
with their clauses, every fact beside its origin, every approved storm with what
its steps saw - into JSON and into standalone printable HTML, and these routes
serve both:

    GET /api/threads/{id}/report     the data
    GET /ui/report/{id}              the page (print-to-PDF is the export)

THE INVARIANT UNDER TEST IS THE PROVENANCE ONE, WEARING A NECKTIE. Every value
on the page sits beside its origin word, and an ASSERTED fact is styled as
claimed rather than shown as if measured. A report that displayed numbers
without their provenance would be the defect this product exists to refuse,
formatted nicely.
"""

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from app import diagnosis
from app import events
from app import storm
from app.main import app
from app.tools import REGISTRY
from app.tools import propose
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


class TheJourneyRendersAsAReport(unittest.TestCase):
    def setUp(self):
        support.sandbox(self)
        self.client = support.api_client(app)
        thread = events.create_thread("report-me", ledger=AI_LEDGER)
        self.thread_id = thread["id"]

    def _seed(self):
        for name, args in (
            ("read_agent_traces", {"path": TRACES}),
            ("read_tool_definitions", {"path": TOOLDEFS}),
            ("bound_the_loop", {"path": TRACES}),
            (
                "run_the_failures",
                {
                    "failures_path": FAILURES,
                    "input_field": "input",
                    "expected_field": "expected",
                    "answer_field": "answer",
                    "traces_path": TRACES,
                },
            ),
        ):
            result = REGISTRY.call(name, args, actor="user", thread_id=self.thread_id)
            self.assertTrue(result.get("ok"), f"{name}: {result}")
        stated = REGISTRY.call(
            "state_facts", {"facts": PERSON_FACTS}, actor="user", thread_id=self.thread_id
        )
        self.assertTrue(stated.get("ok"), stated)

    def test_the_json_report_carries_the_verdict_and_the_origins(self):
        self._seed()
        response = self.client.get(f"/api/threads/{self.thread_id}/report")
        self.assertEqual(response.status_code, 200)
        report = response.json()

        self.assertEqual(report["verdict"]["outcome"], "BUILD__AGENT_WITH_TOOLS")
        origins = report["verdict"]["fact_origins"] or {}
        for name in ("has_traces", "tokens_per_run", "tool_count", "failing_cases_n"):
            self.assertEqual(
                origins.get(name),
                "MEASURED",
                f"{name} must read MEASURED in a report a manager will read",
            )
        by_name = {row["fact"]: row for row in report["facts"]}
        self.assertEqual(by_name["tokens_per_run"]["tool"], "bound_the_loop")

    def test_a_thread_that_APPROVED_A_BUILD_still_renders(self):
        """The case this file's own docstring claimed and never drove.

        Every test above seeds facts and stops, so `storm.list_for_thread`
        returned an empty list and the line that composes the storms never ran.
        It was wrong: it read `row["storm"]` off a row selected out of the
        storms TABLE, whose primary key is `id` - `"storm"` is the name
        `Storm.as_dict()` gives that number on the way out. The KeyError became
        `404 thread not found` at `app/main.py:1092`, so the report, the
        printable page and the export were 404 for exactly the threads that had
        finished a journey, and 200 for the ones that had not.

        Driven rather than asserted: a real plan, a real approval, then the
        three handover routes.
        """
        self._seed()
        # The outcome comes from the REPORT, not from a bare `diagnose({})`:
        # the thread's facts live in its evidence, and an empty sheet walks to
        # BLOCKED__NOTHING_TO_MEASURE_AGAINST no matter what was seeded.
        first = self.client.get(f"/api/threads/{self.thread_id}/report")
        self.assertEqual(first.status_code, 200)
        outcome = first.json()["verdict"]["outcome"]

        situation = propose.Situation(
            outcome=outcome,
            result=diagnosis.diagnose({}, diagnosis.spec_at(AI_LEDGER)),
            failures_path=FAILURES,
            traces_path=TRACES,
            input_field="input",
            expected_field="expected",
            answer_field="answer",
        )
        plan = propose.PROPOSERS[outcome](situation)
        declared = storm.declare(plan, thread_id=self.thread_id)

        response = self.client.get(f"/api/threads/{self.thread_id}/report")
        self.assertEqual(
            response.status_code,
            200,
            "a thread with an approved build must still hand itself over",
        )
        storms = response.json()["storms"]
        self.assertEqual(
            [row["storm"] for row in storms],
            [declared["storm"]],
            "the report must carry the storm that was approved on this thread",
        )

        page = TestClient(app).get(f"/ui/report/{self.thread_id}")
        self.assertEqual(page.status_code, 200)
        export = self.client.get(f"/api/threads/{self.thread_id}/export")
        self.assertEqual(export.status_code, 200)
        self.assertEqual(export.json()["kind"], "ml-harness/journey-export")

    def test_an_unknown_thread_is_a_404_on_both_routes(self):
        self.assertEqual(self.client.get("/api/threads/999999/report").status_code, 404)
        # The UI route is unauthenticated like every read-only page, so it is
        # fetched without the header.
        anonymous = TestClient(app)
        self.assertEqual(anonymous.get("/ui/report/999999").status_code, 404)

    def test_the_html_page_shows_every_value_beside_its_origin_word(self):
        self._seed()
        anonymous = TestClient(app)  # read-only page: no token, by design
        response = anonymous.get(f"/ui/report/{self.thread_id}")
        self.assertEqual(response.status_code, 200)
        html_text = response.text

        self.assertIn("BUILD__AGENT_WITH_TOOLS", html_text)
        self.assertIn("G1_FAILURE_RATE_MEASURED", html_text)
        self.assertIn("PASSED", html_text)
        # The provenance words are ON THE PAGE, next to values - not in a
        # legend that hopes the reader remembers which number was whose.
        self.assertIn("class='origin-MEASURED'", html_text)
        self.assertIn("class='origin-STATED'", html_text)
        # The print hint is present and nothing here needs JS to export.
        self.assertIn("Save as PDF", html_text)

    def test_hostile_fact_values_arrive_escaped(self):
        """A fact's `how` is text somebody else's tool wrote; it is data.

        THE SPECIMEN IS A FACT THIS LEDGER DECLARES, since 2026-09-23. It was
        `goal_text`, which `docs/ledgers/ai_engineering.yaml` does not declare,
        and "Facts on record" now draws the sheet the verdict walked
        (`evidence.assemble_facts`), which drops an undeclared row - so the
        hostile string never reached the page and `&lt;script&gt;` was absent
        for the wrong reason. `failure_buckets` is declared and free-keyed, so
        the hostile text rides in a key and is rendered through `_cell`.
        """
        from app.tools import evidence

        token = evidence._STAMPING.set(True)
        try:
            evidence.record(
                fact="failure_buckets",
                value={"<script>alert(1)</script>": 1},
                origin=evidence.STATED,
                actor="user",
                how="<img src=x onerror=alert(2)>",
                tool="a_test",
                thread_id=self.thread_id,
                ledger=diagnosis_spec(),
            )
        finally:
            evidence._STAMPING.reset(token)
        response = TestClient(app).get(f"/ui/report/{self.thread_id}")
        self.assertNotIn("<script>", response.text)
        self.assertNotIn("<img src=x", response.text)
        self.assertIn("&lt;script&gt;", response.text)


    def test_the_export_is_a_self_describing_download(self):
        """Phase F's artifact exists before any share destination does.

        The bundle names the engine build that produced it, so a report pasted
        into an issue is attributable to the code that measured it - and it
        carries no secrets by construction: it reads the same rows the page
        reads.
        """
        self._seed()
        response = self.client.get(f"/api/threads/{self.thread_id}/export")
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response.headers.get("content-disposition", ""))
        bundle = response.json()
        self.assertEqual(bundle["kind"], "ml-harness/journey-export")
        self.assertEqual(bundle["version"], 1)
        self.assertTrue(bundle["engine"]["engine_id"])
        self.assertTrue(len(bundle["engine"]["code_fingerprint"]) == 64)
        self.assertEqual(
            bundle["report"]["verdict"]["outcome"], "BUILD__AGENT_WITH_TOOLS"
        )
        # AND THE OTHER DIRECTION: an unknown thread exports nothing.
        self.assertEqual(self.client.get("/api/threads/999999/export").status_code, 404)


def diagnosis_spec():
    from app import diagnosis

    return diagnosis.spec_at(AI_LEDGER)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
