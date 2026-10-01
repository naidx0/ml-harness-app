"""The results program: a run ends in results and an article, or it says why.

Max has asked for this twice - once as *"the run should end in results and
article"*, and again on 2026-09-18 as part of *"what elements and tools and
built frameworks do we provide for this training and working loop"*. An article
is the artefact that leaves the building, so the rules it is held to here are
stricter than the ones a tool result is held to, not looser.

## THE THREE PROPERTIES, AND HOW EACH IS MEASURED

**Every number on the page is on the ledger.** Both pages are tokenised with
`results.TOKEN` - the same expression the renderer's rule is written against -
and every token is looked for in `results.json`. That is a measurement over the
bytes that were written, not a reading of the renderer's intentions.

**Every number in the article is checkable by the person reading it.** The
links to `results.md` and the code spans are stripped out of `article.md` and
the remainder must contain no digit at all. A number in an article's prose that
a reader cannot click through to is exactly the number nobody checks.

**A comparison is made or it is absent.** `results.COMPARISON_PHRASE` is written
in one function, reached only from a paired `evals.compare`. An unscored run's
article must not contain it - which is a property of the bytes and not a matter
of reading the prose carefully for hedging.

## WHY THE FIXTURES ARE REAL ROWS

The baseline is `support.a_completed_eval_run`, which is what every other test
in this suite that needs a pairable baseline uses; the adapter's arm is written
through `evals.create_run` and `evals.record_row` with the provider name
`_store_an_arm` really writes, over the SAME row indexes. Two fake numbers
handed to the renderer would prove the renderer can format, which is not the
thing in doubt: what is in doubt is whether the write-up reads the records this
product actually keeps.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db  # noqa: E402
from app.tools import blocks, evals, results  # noqa: E402
from app.tools.evidence import Instrument  # noqa: E402
from app.tools.registry import REGISTRY  # noqa: E402
from tests import support  # noqa: E402


#: The five sections the article always has, whether or not anything filled them.
THE_FIVE = (
    "## What I set out to do",
    "## What the data said",
    "## What the baseline said",
    "## What training did",
    "## What I would do next",
)

#: A markdown link into the results page, and an inline code span. Stripping
#: these two is what leaves the article's own PROSE, which must be digit-free.
_LINK = re.compile(r"\[[^\]]*\]\(results\.md[^)]*\)")
_CODE = re.compile(r"`[^`]*`")


def _tokens(text: str) -> list[str]:
    return results.TOKEN.findall(text)


class ARunEndsInResultsAndAnArticleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = support.sandbox(self)
        self.thread = support.conversations(1)[0]
        self.thread_id = int(self.thread["id"])
        self.eval_path = Path(self.root) / "eval.jsonl"
        self.eval_path.write_bytes(b'{"q": "one", "a": "yes"}\n')
        # The instrument is the injection channel the registry uses, and the
        # thread arrives on it rather than as an argument - see the handler's
        # docstring. A test that passed a thread id in would be exercising a
        # door this tool deliberately does not have.
        self.instrument = Instrument(tool="write_the_results", thread_id=self.thread_id)

    # -- fixtures ----------------------------------------------------------

    def a_training_run(self, name: str = "hf-peft-lora:SmolLM2-135M") -> dict:
        return db.create_run(
            name,
            json.dumps(
                {
                    "recipe": "hf-peft-lora",
                    "base_model": "HuggingFaceTB/SmolLM2-135M",
                    "max_steps": 200,
                    "max_seq_len": 512,
                    "batch_size": 4,
                    "lora_r": 16,
                    "grad_checkpointing": True,
                },
                sort_keys=True,
            ),
        )

    def a_scored_adapter(self, baseline: dict, *, right_every: int = 3) -> dict:
        """An adapter arm over the SAME rows, written the way `score` writes one.

        `evals.SANDBOX_ARM_PREFIX` is read rather than spelled, for the reason
        `_store_an_arm`'s own comment gives: two literals in two modules is how
        a mark stops being read.
        """
        rows = evals.results_for(int(baseline["id"]))
        run = evals.create_run(
            thread_id=self.thread_id,
            signature="an-adapter-arm",
            eval_path=str(self.eval_path),
            eval_fingerprint="fingerprint",
            input_field="q",
            expected_field="a",
            metric=evals.EXACT_MATCH,
            prompt="{input}",
            prompt_is_default=0,
            provider_id=None,
            provider_name=f"{evals.SANDBOX_ARM_PREFIX}adapter",
            model="adapters/adapter-1",
            locality="local",
            judge_model=None,
            planned=len(rows),
            rows_available=len(rows),
            trivial_baseline=0.5,
            trivial_answer="yes",
            latency_budget_ms=None,
        )
        for row in rows:
            index = int(row["row_index"])
            right = bool(index % 2) or (index % right_every == 0)
            evals.record_row(
                int(run["id"]),
                index,
                question=row["input"],
                expected=row["expected"],
                answer="yes" if right else "no",
                correct=right,
                verdicts={"exact_match": right},
                failure_mode=None if right else "wrong_facts",
                graded_by=evals.EXACT_MATCH,
                seconds=0.1,
            )
        return dict(run)

    def a_hardware_reading(self) -> None:
        """A MEASURED `vram_gb` row, stamped through an instrument.

        Not `evidence.record` with `origin=MEASURED`: that route is refused,
        and rightly - "a row that went round it carries a badge nobody earned".
        The write-up copies the origin word off the row, so the row has to have
        earned the word or this test proves nothing about the word.
        """
        instrument = Instrument(
            tool="inspect_hardware",
            actor="tool",
            thread_id=self.thread_id,
            measures=frozenset({"vram_gb"}),
            provides=frozenset({"machine.hardware.inspect"}),
        )
        instrument.measured(
            "vram_gb", 8.0, how="read from nvidia-smi on this machine"
        )

    # -- the scored run ----------------------------------------------------

    def test_a_scored_run_writes_three_files_and_every_number_is_on_the_ledger(self):
        run = self.a_training_run()
        baseline = support.a_completed_eval_run(self.thread_id, self.eval_path, rows=40)
        self.a_scored_adapter(baseline)
        self.a_hardware_reading()

        into = Path(self.root) / "writeup"
        written = results.write_the_results(
            run=str(run["id"]), into=str(into), instrument=self.instrument
        )
        self.assertTrue(written["ok"], written)
        self.assertTrue(written["scored"], written)

        directory = Path(written["into"])
        page = (directory / results.RESULTS_MD).read_text(encoding="utf-8")
        article = (directory / results.ARTICLE_MD).read_text(encoding="utf-8")
        body = json.loads(
            (directory / results.RESULTS_JSON).read_text(encoding="utf-8")
        )

        # EVERY ENTRY CARRIES AN ORIGIN AND A HOW-SENTENCE. An entry with a
        # blank origin would satisfy the token check below and would be the
        # exact defect the token check exists to stop.
        self.assertTrue(body["numbers"])
        for entry in body["numbers"]:
            with self.subTest(number=entry["key"]):
                self.assertIn(
                    entry["origin"],
                    ("MEASURED", "STATED", "ASSERTED", "DEFAULTED", results.RECORDED),
                )
                self.assertGreater(len(entry["how"].split()), 4, entry)
                self.assertIn(entry["text"], page)

        # AND NO NUMBER ON EITHER PAGE IS ABSENT FROM THE LEDGER.
        ledger_tokens = set(_tokens(json.dumps(body, sort_keys=True)))
        for name, text in ((results.RESULTS_MD, page), (results.ARTICLE_MD, article)):
            for token in _tokens(text):
                with self.subTest(page=name, token=token):
                    self.assertIn(
                        token,
                        ledger_tokens,
                        f"{name} shows {token!r} and results.json does not hold "
                        "it. Every number on a page this product writes comes "
                        "off the ledger or it does not go on the page.",
                    )

        for heading in THE_FIVE:
            self.assertIn(heading, article)

        # The measured things are actually there, rather than five headings
        # saying nothing was measured.
        self.assertIn("Baseline score", page)
        self.assertIn("Adapter score", page)
        self.assertIn("Video memory", page)
        self.assertIn(results.COMPARISON_PHRASE, article)

    def test_every_number_in_the_article_is_a_link_the_reader_can_follow(self):
        run = self.a_training_run()
        baseline = support.a_completed_eval_run(self.thread_id, self.eval_path, rows=40)
        self.a_scored_adapter(baseline)

        written = results.write_the_results(
            run=str(run["id"]),
            into=str(Path(self.root) / "linked"),
            instrument=self.instrument,
        )
        article = (Path(written["into"]) / results.ARTICLE_MD).read_text(
            encoding="utf-8"
        )
        self.assertIn("](results.md#", article)

        prose = _CODE.sub("", _LINK.sub("", article))
        self.assertEqual(
            _tokens(prose),
            [],
            "article.md states a number outside a link to results.md and "
            "outside a code span. A number a reader cannot click through to is "
            "the number nobody checks, which is the whole reason this page "
            "links every one of them.",
        )

    # -- the unscored run --------------------------------------------------

    def test_an_unscored_run_says_so_and_makes_no_comparison(self):
        """No adapter arm on the thread. The article stops rather than reaches.

        THE BASELINE IS STILL THERE, deliberately: a run with nothing at all on
        its thread would produce an article with nothing in it, and an article
        that says nothing cannot overclaim. The dangerous case is the one where
        there IS a number to reach for - the baseline, the base model's arm, the
        loss curve - and the honest answer is still that this run is unscored.
        """
        run = self.a_training_run()
        support.a_completed_eval_run(self.thread_id, self.eval_path, rows=40)

        written = results.write_the_results(
            run=str(run["id"]),
            into=str(Path(self.root) / "unscored"),
            instrument=self.instrument,
        )
        self.assertTrue(written["ok"], written)
        self.assertFalse(written["scored"])
        self.assertIn("UNSCORED", written["summary"])

        directory = Path(written["into"])
        article = (directory / results.ARTICLE_MD).read_text(encoding="utf-8")
        self.assertIn("## What training did", article)
        self.assertIn("unscored", article)
        self.assertNotIn(
            results.COMPARISON_PHRASE,
            article,
            "the article compared something on a run whose adapter was never "
            "scored. The ledger cannot show that comparison, so the article "
            "may not make it.",
        )
        self.assertFalse(json.loads(
            (directory / results.RESULTS_JSON).read_text(encoding="utf-8")
        )["scored"])

    def test_a_section_with_nothing_measured_says_so_in_one_line(self):
        """An empty thread fills no heading and invents nothing."""
        run = self.a_training_run()
        written = results.write_the_results(
            run=str(run["id"]),
            into=str(Path(self.root) / "empty"),
            instrument=self.instrument,
        )
        page = (Path(written["into"]) / results.RESULTS_MD).read_text(
            encoding="utf-8"
        )
        self.assertIn("No baseline was measured on this conversation", page)
        self.assertIn("No hardware reading is on this conversation", page)
        article = (Path(written["into"]) / results.ARTICLE_MD).read_text(
            encoding="utf-8"
        )
        self.assertIn("Measure a baseline first", article)
        self.assertNotIn(results.COMPARISON_PHRASE, article)

    # -- the destination ---------------------------------------------------

    def test_a_destination_that_is_taken_is_redirected_and_not_refused(self):
        """Max, 2026-09-17: a folder that exists gets the next free name beside
        it. The same `datawork._claim` every data tool uses, so there is one
        answer to "where did my files go" and not two."""
        run = self.a_training_run()
        into = Path(self.root) / "taken"
        into.mkdir()
        (into / "somebody_elses.txt").write_bytes(b"not ours\n")

        written = results.write_the_results(
            run=str(run["id"]), into=str(into), instrument=self.instrument
        )
        self.assertTrue(written["ok"], written)
        self.assertNotEqual(Path(written["into"]), into)
        self.assertTrue((Path(written["into"]) / results.RESULTS_MD).is_file())
        self.assertFalse((into / results.RESULTS_MD).exists())
        self.assertTrue((into / "somebody_elses.txt").is_file())

    def test_a_run_nobody_has_says_which_runs_there_are(self):
        self.a_training_run()
        refused = results.write_the_results(
            run="a-run-that-was-never-started",
            into=str(Path(self.root) / "nowhere"),
            instrument=self.instrument,
        )
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["error"], "no_such_run")
        self.assertTrue(refused["runs"])
        self.assertTrue(refused["nothing_was_written"])
        self.assertFalse((Path(self.root) / "nowhere").exists())

    # -- the census --------------------------------------------------------

    def test_the_pack_census_moves_and_this_tool_stamps_nothing(self):
        self.assertIn("training.results.write", blocks.CAPABILITIES)
        self.assertEqual(blocks.pack_of("training.results.write"), "training")
        self.assertIn("write_the_results", blocks.tools_in({"training"}))

        spec = REGISTRY.get("write_the_results")
        self.assertIsNotNone(spec)
        self.assertEqual(
            spec.measures,
            (),
            "a write-up that could stamp would read every record in the "
            "product and then mint off what it read, which is wall 3's whole "
            "subject",
        )
        self.assertEqual(spec.approval, "always")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
