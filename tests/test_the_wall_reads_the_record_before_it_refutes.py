"""The wall reads the record before it refutes, and a model name is not an instrument.

MEASURED 2026-09-23, a live journey at bdc6515 on a scratch engine with the
owner's local model, thread 2 of the scratch database. After seventeen tool
calls - `measure_baseline` among them, which returned model
`hf.co/openbmb/MiniCPM5-1B-GGUF:Q8_0`, rows_scored 20, baseline_score 0.0 and
stamped `baseline_score = 0.0` MEASURED with the account "... answered 0 of 20
rows of ..." - the model wrote its report, and the first sentence was:

    **Baseline (G1):** hf.co/openbmb/MiniCPM5-1B-GGUF:Q8_0 scores 0.0 on 20 rows of the (leaky) eval set.

That is `measure_baseline`'s own summary sentence said back. The provenance
wall withheld it as `invented_measurement`, instrument `q8_0`, "there is no such
tool in this harness", and the closing told the person "Nothing here holds it,
so there is nothing to correct it against." Both halves were false: the record
held 0.0 on 20 rows by measure_baseline, and `Q8_0` is the tail of the MODEL
NAME that measurement was of - the attribution verb `scores` made the wall read
the subject of a measurement as its instrument. The journey stopped one step
after its first real measurement.

One case per exit, and the controls are the half that keeps the wall a wall:

  (a) the exact sentence, the baseline rows on record  -> passes, and a
      `citation_matched_the_record` notice names fact, number and instrument;
  (b) the exact sentence, nothing on record            -> withheld as before;
  (c) the same number on a count the record does not hold ("on 40 rows")
                                                       -> withheld, and the
      reason names the row it contradicts;
  (d) an invented instrument and a number nothing holds -> withheld as before,
      and (d2) with a number the record DOES hold the closing no longer says
      "Nothing here holds it";
  (e) thread 93's shape, a registered tool that ran and recorded no such number
                                                       -> withheld as before.

(b), (d) and (e) are CONTROLS and were green before the change; (a), (c) and
(d2) are the ones that were red.

THE BARE PARENTHESIS IS NOT CAUGHT, BEFORE OR AFTER. `500 rows
(profile_repository)` with no preposition opens no frame in `app/provenance.py`
- a bare preposition is what admits a registered name there - so case (e) is
written `(from profile_repository)`, which is the nearest shape the wall has
ever withheld. Widening the frame to a bare parenthesis is not this change.
"""

from __future__ import annotations

import unittest

from app import conductor, events, provenance
from app.providers import Delta
from app.providers import store as provider_store
from app.tools import REGISTRY, evidence
from app.tools.evidence import Instrument

import support


MODEL = "hf.co/openbmb/MiniCPM5-1B-GGUF:Q8_0"
EVAL = "data/eval.jsonl"

#: Verbatim from the journey. Nothing in it is paraphrased.
SAID_BACK = (
    "**Baseline (G1):** hf.co/openbmb/MiniCPM5-1B-GGUF:Q8_0 scores 0.0 on 20 "
    "rows of the (leaky) eval set."
)
#: The same sentence on a count the record does not hold.
ON_FORTY = SAID_BACK.replace("on 20 rows", "on 40 rows")

NOTHING_HOLDS = "Nothing here holds it"

#: The notice's reason, written out rather than read off the module, so the
#: controls below stay runnable against the code that predates it.
CITED = "citation_matched_the_record"


def _stamp(thread_id: int, fact: str, value, how: str) -> None:
    """Stamp as `measure_baseline` stamps: through an instrument, with its own
    `provides`, and the `how` sentence it writes (app/tools/measure.py)."""
    Instrument(
        tool="measure_baseline",
        actor=evidence.MODEL,
        thread_id=thread_id,
        measures=frozenset({fact}),
        provides=frozenset(REGISTRY.get("measure_baseline").provides or ()),
    ).measured(fact, value, how=how)


def _plant_the_baseline(thread_id: int) -> None:
    """The three rows measure_baseline wrote on the journey's thread 2."""
    _stamp(
        thread_id, "baseline_score", 0.0,
        f"{MODEL} answered 0 of 20 rows of {EVAL} correctly, exact match",
    )
    _stamp(
        thread_id, "trivial_baseline_score", 0.05,
        f"always answering 'yes' scores 5% on the same 20 rows, exact match",
    )
    _stamp(
        thread_id, "baseline_measured", True,
        f"this run scored {MODEL} on 20 rows of {EVAL}",
    )


class ScriptedModel:
    """Says what the test told it to, one round at a time."""

    id = "fake"
    locality = "local"

    def __init__(self, rounds):
        self.rounds = list(rounds)

    def stream(self, messages, tools=None, *, secret=None):
        for delta in self.rounds.pop(0) if self.rounds else []:
            yield delta

    def capabilities(self, *, secret=None):
        raise AssertionError("the loop must not probe mid-turn")


class _Wall(unittest.TestCase):
    def setUp(self):
        support.sandbox(self)
        self.thread_id = int(events.create_thread("thread 2")["id"])
        events.add_message(self.thread_id, "user", "measure my baseline and report it")

    def read(self, sentence, *, ran=None):
        ground = provenance.Ground(self.thread_id)
        for name, result in (ran or {}).items():
            ground.note_tool(name, result)
        return provenance.reads_as_a_measurement(sentence, ground)

    def notices(self, reason=None):
        return [
            row["payload"]
            for row in events.since(f"thread:{self.thread_id}")
            if row["kind"] == "conductor.notice"
            and (reason is None or row["payload"].get("reason") == reason)
        ]

    def withheld_reason(self, row, sentence):
        """The transcript's `reason` line, from the conductor's own recorder."""
        conflict = dict(row, kind=conductor.INVENTED_MEASUREMENT, sentence=sentence)
        (event,) = list(conductor._withheld(self.thread_id, conflict))
        return event["payload"]["reason"]

    def turn(self, sentence):
        """The sentence, said by a model, through `run_turn`. Returns the ending,
        what reached the user from the model, and the harness's closing."""
        row = provider_store.create("Fake", "http://127.0.0.1:11434", "fake-model", "ollama")
        ready = provider_store.record_capabilities(
            row["id"],
            type("Caps", (), {"tool_calling": True, "detail": "set by the test",
                              "ctx_len": None, "provenance": {}})(),
        )
        provider_store.set_active(ready["id"])
        model = ScriptedModel([[Delta(kind="text", text=sentence + " ")]])
        original = conductor.build
        conductor.build = lambda *a, **k: model
        self.addCleanup(setattr, conductor, "build", original)
        list(conductor.run_turn(self.thread_id))
        rows = events.since(f"thread:{self.thread_id}")
        deltas = [row["payload"] for row in rows if row["kind"] == "chat.delta"]
        shown = "".join(d.get("text", "") for d in deltas if d.get("written_by") != "harness")
        closing = "".join(d.get("text", "") for d in deltas if d.get("written_by") == "harness")
        return rows[-1]["payload"]["ending"], shown, closing


class ACitationOfTheRecordPassesTest(_Wall):
    """(a) The journey's sentence, with the rows the journey had written."""

    def setUp(self):
        super().setUp()
        _plant_the_baseline(self.thread_id)

    def test_the_sentence_is_not_withheld(self):
        self.assertIsNone(self.read(SAID_BACK))

    def test_a_notice_records_fact_number_and_instrument(self):
        self.read(SAID_BACK)
        (notice,) = self.notices(CITED)
        self.assertEqual(provenance.CITATION_MATCHED, CITED)
        self.assertEqual(notice["fact"], "baseline_score")
        self.assertEqual(notice["number"], "0.0")
        self.assertEqual(notice["instrument"], "measure_baseline")
        # THE NAME IS THE SUBJECT, AND THE NOTICE SAYS SO IN THE RECORD'S OWN
        # SPELLING - never promoted to an instrument.
        self.assertEqual(notice["subject"], MODEL)
        self.assertIn("measure_baseline", notice["text"])
        self.assertIn("not an instrument", notice["text"])

    def test_through_the_loop_it_reaches_the_person(self):
        ending, shown, closing = self.turn(SAID_BACK)
        self.assertNotEqual(ending, conductor.MEASUREMENT_WITHHELD)
        self.assertIn("scores 0.0 on 20 rows", shown)
        self.assertNotIn(NOTHING_HOLDS, closing)
        self.assertEqual(len(self.notices(CITED)), 1)
        self.assertFalse(
            [n for n in self.notices() if n.get("kind") == conductor.INVENTED_MEASUREMENT]
        )


class WithNothingOnRecordItIsWithheldAsBeforeTest(_Wall):
    """(b) THE CONTROL. Same words, no rows: the refusal is exactly today's."""

    def test_the_refusal_is_unchanged(self):
        row = self.read(SAID_BACK)
        self.assertIsNotNone(row)
        self.assertEqual(row["refuted_by"], provenance.NO_SUCH_INSTRUMENT)
        self.assertEqual(row["instrument"], "q8_0")
        self.assertEqual(row["number"], "0.0")
        self.assertIn(
            "there is no such tool in this harness", self.withheld_reason(row, SAID_BACK)
        )
        self.assertIn(NOTHING_HOLDS, provenance.refusal_sentence(row))
        self.assertEqual(self.notices(CITED), [])

    def test_through_the_loop_it_is_withheld(self):
        ending, shown, closing = self.turn(SAID_BACK)
        self.assertEqual(ending, conductor.MEASUREMENT_WITHHELD)
        self.assertNotIn("0.0", shown)
        self.assertIn(NOTHING_HOLDS, closing)


class TheRightNumberOnTheWrongCountTest(_Wall):
    """(c) 0.0 is on record, measured on 20 rows. "On 40 rows" is not."""

    def setUp(self):
        super().setUp()
        _plant_the_baseline(self.thread_id)

    def test_it_is_withheld_and_the_reason_names_the_row(self):
        row = self.read(ON_FORTY)
        self.assertIsNotNone(row)
        self.assertEqual(row["refuted_by"], provenance.ANOTHER_COUNT)
        self.assertEqual(
            self.withheld_reason(row, ON_FORTY),
            "the record holds 0.0 on 20 rows by measure_baseline; the reply said "
            "0.0 on 40",
        )
        closing = provenance.refusal_sentence(row)
        self.assertNotIn(NOTHING_HOLDS, closing)
        self.assertIn("20 rows", closing)
        self.assertIn("measure_baseline", closing)
        self.assertEqual(self.notices(CITED), [])

    def test_through_the_loop_the_closing_names_the_record(self):
        ending, shown, closing = self.turn(ON_FORTY)
        self.assertEqual(ending, conductor.MEASUREMENT_WITHHELD)
        self.assertNotIn("40", shown)
        self.assertNotIn(NOTHING_HOLDS, closing)
        self.assertIn("20 rows", closing)


class AnInventedInstrumentIsStillInventedTest(_Wall):
    """(d) A name no record's account contains is refuted as before."""

    def setUp(self):
        super().setUp()
        _plant_the_baseline(self.thread_id)

    def test_a_number_nothing_holds_is_withheld_as_before(self):
        sentence = "measure_accuracy scored 0.91 on 20 rows of your eval set."
        row = self.read(sentence)
        self.assertEqual(row["refuted_by"], provenance.NO_SUCH_INSTRUMENT)
        self.assertEqual(row["instrument"], "measure_accuracy")
        self.assertEqual(row["number"], "0.91")
        self.assertIn(NOTHING_HOLDS, provenance.refusal_sentence(row))
        self.assertEqual(self.notices(CITED), [])

    def test_d2_a_number_the_record_holds_is_withheld_but_not_called_unheld(self):
        """G3. The instrument is invented, so the sentence stops - but the
        closing may not tell the person nothing holds a number the record holds."""
        sentence = "measure_accuracy scored 0.0 on 20 rows of your eval set."
        row = self.read(sentence)
        self.assertEqual(row["refuted_by"], provenance.NO_SUCH_INSTRUMENT)
        closing = provenance.refusal_sentence(row)
        self.assertNotIn(NOTHING_HOLDS, closing)
        self.assertIn("measure_baseline", closing)


class ThreadNinetyThreesShapeTest(_Wall):
    """(e) A registered tool that RAN and recorded no such number. The record
    holding other numbers - the baseline - backs nothing here."""

    def setUp(self):
        super().setUp()
        _plant_the_baseline(self.thread_id)

    def test_it_is_withheld(self):
        sentence = "The eval set has 500 rows (from profile_repository)."
        row = self.read(
            sentence,
            ran={"profile_repository": {"ok": True, "files": 12, "languages": ["python"]}},
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["instrument"], "profile_repository")
        self.assertEqual(row["number"], "500")
        self.assertEqual(row["refuted_by"], provenance.NOT_OURS)
        self.assertIn(NOTHING_HOLDS, provenance.refusal_sentence(row))
        self.assertEqual(self.notices(CITED), [])


if __name__ == "__main__":
    unittest.main()
