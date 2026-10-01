"""A sweep of chunk settings: it counts before it writes, it pairs, it corrects
for the family it ran - and it CROWNS NOTHING, including on a null where it
would be wrong to.

`app/tools/retrieval.py` gave the harness `retriever_recall_at_k`, which made
`S3_RETRIEVAL_IS_THE_BOTTLENECK` reachable: the engine can now tell somebody
their retriever scores 0.55 and to go and fix it. `compare_chunkings` is the
first half of the answer, and it is only one quarter of what that node asks
for - of the four levers `NO_TRAIN__FIX_RETRIEVAL` names, this harness owns
chunking and cannot pull the other three without shipping a model.

## WHY THIS FILE IS MOSTLY ABOUT REFUSING

`app/tools/evals.py` carries the lesson: *"Comparing two prompts on thirty rows
and declaring a winner is the never-invent-a-number failure wearing statistical
clothing."* A SWEEP IS STRICTLY WORSE THAN THAT TWO-RUN CASE, in two ways that
do not exist with two runs:

  THE MAXIMUM OF N NOISY ESTIMATES IS BIASED UPWARD. Measured here, in
  `TheNullCrownsNothingTest`: eight settings with identical true recall of 0.5,
  ninety questions, two hundred trials, and the best-of-eight averages several
  points above the truth. Nothing is wrong with the retriever; the selection was
  made on the noise.

  N SETTINGS IS N(N-1)/2 TESTS. Eight settings is twenty-eight, and at raw
  p<=0.05 apiece a large share of NULL families contain at least one "winner" -
  counted below, not asserted. That is `evals.py`'s "a user shown forty
  unresolvable deltas will believe the tenth" in a new costume.

So the tests are organised around what the tool must refuse to say:

  COUNT   - what it will write, before it writes it, in rebuilds, passages and
            posting rows, and NEVER a duration nobody has measured.
  PAIR    - question by question with McNemar, reusing `evals.mcnemar`; a
            question both settings answer the same way is not in the
            denominator of the comparison.
  CORRECT - Holm-Bonferroni over the family actually run, and the arithmetic
            saying how many questions would have to change before any pair
            could be separated at all.
  REFUSE  - passage-level ground truth (a passage key names a cut and this tool
            varies the cut), rows a score tie decided, rows only some settings
            scored, a family of one, a family of thirteen, a duplicate setting,
            a truncated index, a row cap, a name already taken.
  CROWN   - nothing. Ever. `crowned` is None on every path, including the one
            where four of six comparisons separate.

Nothing here uses a network and nothing here uses a model. Every number below is
arithmetic over files this module wrote.
"""

from __future__ import annotations

import json
import random
import re
import statistics
import unittest
from pathlib import Path

from app import build as build_costs, db
from app.tools import REGISTRY, evals, retrieval
from app.tools.evidence import USER

import support


#: Distinct rare terms, one per document, so a query naming one has exactly one
#: right answer and BM25's idf is doing visible work.
RARE = [
    "zarquon", "blorptide", "quibblesnap", "frobnicate", "wibblethorn",
    "gnarflux", "plumbago", "skerrivant", "thrumbolt", "vexilate",
    "morrowgate", "clindersome", "arbuthnot", "dwindlecap", "estovar",
    "fenwicket", "grumbleaxe", "hesperine", "inkwhistle", "jorbelisk",
]

#: One paragraph, repeated, that carries no rare term at all. It is what makes a
#: long document long without making it findable.
FILLER = (
    "Routine handling of the schedule, the approvals and the archive is "
    "described here in the same words used in every chapter of the handbook."
)


def flat_corpus(root: Path, count: int = 20) -> Path:
    """Documents that are ONE PARAGRAPH each, shorter than any window tested.

    THE STRUCTURAL NULL, ON DISK. `cut_into_passages` packs paragraphs up to the
    window and never splits one that fits, so a corpus whose every document is a
    single short paragraph is cut IDENTICALLY at 800 characters and at 3600.
    Every setting therefore indexes bit-identical passages, every hit vector is
    identical, and any separation the tool reported would be a separation it
    invented. Each rare term is shared with the next document so recall is
    nowhere near 1.0 and there is room for a maximum to look tempting.
    """
    folder = Path(root) / "flat"
    folder.mkdir(parents=True, exist_ok=True)
    for number in range(count):
        mine = RARE[number % len(RARE)]
        shared = RARE[(number + 1) % len(RARE)]
        padding = " ".join(["stage"] * (3 + (number % 7)))
        (folder / f"doc{number:02d}.md").write_text(
            f"Section {number} of the handbook covers the {mine} procedure and "
            f"also refers to the {shared} procedure, documented elsewhere. The "
            f"ordering of the stages is recorded here: {padding}.\n",
            encoding="utf-8",
        )
    return folder


def split_corpus(root: Path, count: int = 20) -> Path:
    """A corpus where the CUT decides which document wins, so something separates.

    The right document holds the two query terms FAR APART, in different
    paragraphs. A decoy holds them together in one short paragraph and is much
    longer overall. At a small window the decoy has a short passage with both
    terms and the right document has passages with one term each, so the decoy
    wins. At a window larger than the whole right document, that document
    becomes one passage holding both terms and is shorter than the decoy, so it
    wins. A bench that refuses everything is as useless as one that concludes
    everything, and this is the fixture that proves this one does not.
    """
    folder = Path(root) / "split"
    folder.mkdir(parents=True, exist_ok=True)
    for number in range(count):
        term = RARE[number % len(RARE)]
        right = [f"The {term} register is opened at the start of the period."]
        right.extend(FILLER for _ in range(3))
        right.append(
            "Reconciliation of the period is performed at the close and the "
            "reconciliation figures are entered into the register above."
        )
        (folder / f"doc{number:02d}.md").write_text(
            "\n\n".join(right) + "\n", encoding="utf-8"
        )
        decoy = [f"The {term} reconciliation note is filed with the ledger here."]
        decoy.extend(FILLER for _ in range(9))
        (folder / f"decoy{number:02d}.md").write_text(
            "\n\n".join(decoy) + "\n", encoding="utf-8"
        )
    return folder


def vanishing_corpus(root: Path, count: int = 6) -> Path:
    """A corpus where ONE DOCUMENT DISAPPEARS at one of the settings.

    THE FIXTURE THAT MAKES THE INTERSECTION RULE TESTABLE. Every other corpus in
    this file resolves every ground-truth row under every setting, so a sweep
    that compared the UNION of the rows each setting scored would look exactly
    like one that compared the intersection. Here the odd document is a single
    45-character paragraph whose only space is at character 36: at a 42-character
    window it is cut into a 36-character fragment and an 8-character one, both
    under MIN_PASSAGE_CHARS, so the document contributes no passage at all and
    its ground truth resolves to nothing. At an 800-character window it is one
    passage and resolves fine. The normal documents are paragraphs of 40 to 42
    characters, which survive both windows.
    """
    folder = Path(root) / "vanishing"
    folder.mkdir(parents=True, exist_ok=True)
    for number in range(count):
        term = RARE[number % len(RARE)]
        paragraphs = []
        for line in range(3):
            body = f"{term} procedure ordering stage part {line} "
            paragraphs.append((body + "handbook detail")[:42].strip().ljust(41, "x"))
        (folder / f"doc{number:02d}.md").write_text(
            "\n\n".join(paragraphs) + "\n", encoding="utf-8"
        )
    (folder / "odd.md").write_text(
        "vexilatepreamblevexilatepreamblevexi vexilate\n", encoding="utf-8"
    )
    return folder


def eval_file(root: Path, rows: list[dict], name: str = "eval.jsonl") -> Path:
    path = Path(root) / name
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    return path


def rare_questions(count: int = 20) -> list[dict]:
    return [
        {"q": f"{RARE[number % len(RARE)]} procedure", "doc": f"doc{number:02d}.md"}
        for number in range(count)
    ]


def split_questions(count: int = 20) -> list[dict]:
    return [
        {
            "q": f"{RARE[number % len(RARE)]} reconciliation",
            "doc": f"doc{number:02d}.md",
        }
        for number in range(count)
    ]


class SweepTest(unittest.TestCase):
    """Sandbox, two conversations, two corpora."""

    def setUp(self) -> None:
        self.root = support.sandbox(self)
        self.threads = support.conversations(2)
        self.thread = self.threads[0]["id"]
        self.other = self.threads[1]["id"]

    def sweep(self, corpus, evalset, settings, thread=None, **arguments):
        payload = {
            "corpus_path": str(corpus),
            "eval_path": str(evalset),
            "question_field": "q",
            "ground_truth_field": "doc",
            "settings": settings,
        }
        payload.update(arguments)
        # A caller that means "there is no ground-truth column" says so by
        # passing None, and the key is dropped rather than sent as null - a tool
        # argument that is present and empty is a different call from an absent
        # one, and the refusal being tested is about the absent one.
        payload = {key: value for key, value in payload.items() if value is not None}
        return REGISTRY.call(
            "compare_chunkings",
            payload,
            actor=USER,
            thread_id=thread or self.thread,
        )

    def flat_sweep(self, settings=(800, 1600, 2400, 3200), **arguments):
        corpus = flat_corpus(self.root)
        rows = eval_file(self.root, rare_questions(), "flat.jsonl")
        return self.sweep(corpus, rows, list(settings), k=1, **arguments)

    def split_sweep(self, **arguments):
        corpus = split_corpus(self.root)
        rows = eval_file(self.root, split_questions(), "split.jsonl")
        settings = [
            {"passage_chars": 150, "passage_overlap": 20},
            {"passage_chars": 300, "passage_overlap": 20},
            {"passage_chars": 700, "passage_overlap": 20},
            {"passage_chars": 5000, "passage_overlap": 20},
        ]
        return self.sweep(corpus, rows, settings, k=1, **arguments)

    def indexes_on_disk(self) -> int:
        with db.session() as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) AS n FROM retrieval_indexes"
                ).fetchone()["n"]
            )


# ---------------------------------------------------------------------------


class TheToolSurfaceIsDeclaredTest(SweepTest):
    """The name the two lanes agreed on, and what it may never be asked for."""

    def test_the_tool_is_named_exactly_as_the_brief_fixed_it(self):
        self.assertIn("compare_chunkings", REGISTRY)

    def test_it_measures_nothing_and_may_not_declare_a_bound(self):
        """`measures=()` is the whole stamping story and it is structural.

        A tool that measures nothing may not declare `bounds` either - the
        registry refuses that at registration - so this pair of assertions is
        the mechanical form of "this tool cannot record a fact".
        """
        spec = REGISTRY.get("compare_chunkings")
        self.assertEqual(spec.measures, ())
        self.assertEqual(spec.bounds, ())
        self.assertNotIn(
            "compare_chunkings",
            [t.name for t in REGISTRY if "retriever_recall_at_k" in t.measures],
        )

    def test_measure_retriever_recall_is_still_the_only_door_to_the_fact(self):
        self.assertEqual(
            [t.name for t in REGISTRY if "retriever_recall_at_k" in t.measures],
            ["measure_retriever_recall"],
        )

    def test_there_is_no_argument_that_asks_a_model_anything(self):
        """No judge, no provider, no prompt, no base url. Wall 7 with a corpus.

        The sweep runs eight indexes and could plausibly want a model to break a
        tie or to rewrite a query. There is no slot for one, and the reply says
        why rather than leaving the absence to be noticed.
        """
        properties = set(REGISTRY.get("compare_chunkings").schema["properties"])
        for reserved in (
            "judge",
            "judge_provider_id",
            "provider_id",
            "prompt",
            "model",
            "base_url",
            "origin",
            "measured",
            "evidence",
            "verdict",
            "outcome",
        ):
            with self.subTest(argument=reserved):
                self.assertNotIn(reserved, properties)

    def test_it_reads_no_provider_so_it_can_send_nothing_anywhere(self):
        spec = REGISTRY.get("compare_chunkings")
        self.assertNotIn("providers", spec.reads)
        self.assertNotIn("huggingface_hub", spec.reads)


# ---------------------------------------------------------------------------


class TheCostIsCountedBeforeItRunsTest(SweepTest):
    """What a sweep is about to do to somebody's database, in counts, first."""

    def test_without_run_it_writes_nothing_at_all(self):
        before = self.indexes_on_disk()
        plan = self.flat_sweep()
        self.assertTrue(plan["ok"])
        self.assertFalse(plan["ran"])
        self.assertEqual(self.indexes_on_disk(), before)
        self.assertIn("THIS HAS NOT RUN", plan["summary"])

    def test_the_planned_counts_are_exactly_what_the_run_writes(self):
        """THE COST PREVIEW AND THE BUILD RUN THE SAME CODE, checked rather than
        promised. `kept_passages` is what `build` writes from and what the plan
        counts with, so a plan that said 400 passages and a run that wrote 399
        is not a discrepancy this file could tolerate - it would mean the
        sentence a person approved was about a different piece of work."""
        plan = self.flat_sweep()
        done = self.flat_sweep(run=True)
        for planned, index in zip(plan["settings"], done["indexes"]):
            with self.subTest(setting=planned["index_name"]):
                self.assertEqual(planned["passages"], index["passages"])
        with db.session() as connection:
            for planned, index in zip(plan["settings"], done["indexes"]):
                rows = int(
                    connection.execute(
                        "SELECT COUNT(*) AS n FROM retrieval_postings WHERE index_id = ?",
                        (index["index_id"],),
                    ).fetchone()["n"]
                )
                passages = int(
                    connection.execute(
                        "SELECT COUNT(*) AS n FROM retrieval_passages WHERE index_id = ?",
                        (index["index_id"],),
                    ).fetchone()["n"]
                )
                with self.subTest(setting=planned["index_name"]):
                    self.assertEqual(planned["posting_rows"], rows)
                    self.assertEqual(planned["passages"], passages)
        self.assertEqual(
            plan["will_do"]["posting_rows_written"],
            sum(row["posting_rows"] for row in plan["settings"]),
        )

    def test_no_duration_is_stated_and_none_can_be(self):
        """`Estimate.unknown` cannot carry a value - the constructor refuses -
        so "about forty minutes" is not a sentence this tool is able to produce
        rather than one it has been asked not to."""
        plan = self.flat_sweep()
        wall = plan["cost"]["wall_clock"]
        self.assertEqual(wall["provenance"], build_costs.UNKNOWN)
        self.assertIsNone(wall["value"])
        self.assertTrue(wall["find_out_by"].strip())
        with self.assertRaises(build_costs.CostError):
            build_costs.Estimate.unknown(
                build_costs.WALL_CLOCK, why="because", find_out_by=""
            )

    def test_the_model_cost_is_zero_and_says_why_off_the_registration(self):
        plan = self.flat_sweep()
        for dimension in ("model_tokens", "model_requests"):
            with self.subTest(dimension=dimension):
                self.assertEqual(plan["cost"][dimension]["value"], 0.0)
                self.assertIn("providers", plan["cost"][dimension]["how"])

    def test_the_plan_names_rebuilds_and_reuse_separately(self):
        """A second sweep over the same corpus rebuilds NOTHING, and the plan
        says so before it runs. The parameters are in the index name, so
        `build`'s own reuse check does the caching."""
        self.flat_sweep(run=True)
        again = self.flat_sweep()
        self.assertEqual(again["will_do"]["rebuilds"], 0)
        self.assertEqual(again["will_do"]["reused_without_rebuilding"], 4)
        self.assertEqual(again["will_do"]["passages_written"], 0)
        self.assertTrue(all(row["already_built"] for row in again["settings"]))


    def test_the_comparison_is_over_the_rows_every_setting_scored(self):
        """`evals.compare`'s hardest-won property with N sides instead of two:
        every number is measured on the rows EVERY setting scored. A sweep that
        took the union would let a setting be credited for a question another
        setting never answered, which is the "-50.0% / a real difference" card
        that module's docstring is a report about.

        The fixture is self-checked: if the odd document ever stops vanishing at
        the small window, this test says so instead of quietly passing on a
        comparison where the union and the intersection are the same set.
        """
        corpus = vanishing_corpus(self.root)
        odd = (corpus / "odd.md").read_text(encoding="utf-8")
        self.assertEqual(len(retrieval.kept_passages(odd, 42, 0)[0]), 0)
        self.assertEqual(len(retrieval.kept_passages(odd, 800, 0)[0]), 1)

        rows = [
            {"q": f"{RARE[n % len(RARE)]} procedure", "doc": f"doc{n:02d}.md"}
            for n in range(6)
        ] + [{"q": "vexilate", "doc": "odd.md"}]
        path = eval_file(self.root, rows, "vanishing.jsonl")
        out = self.sweep(
            corpus,
            path,
            [{"passage_chars": 42, "passage_overlap": 0},
             {"passage_chars": 800, "passage_overlap": 0}],
            k=1,
            run=True,
        )
        self.assertEqual(out["questions"]["eligible"], 7)
        self.assertEqual(out["dropped_not_scored_by_every_setting"], 1)
        self.assertEqual(out["compared_questions"], 6)
        for row in out["per_setting"]:
            with self.subTest(setting=row["setting"]):
                self.assertEqual(row["of"], 6)
        self.assertIn("not scored by every setting", out["says"])
        # And the demoted per-setting number keeps the other denominator, so the
        # fact is not lost - it is labelled.
        own = {row["setting"]: row["own_run"]["of"] for row in out["per_setting"]}
        self.assertEqual(sorted(own.values()), [6, 7])

    def test_the_python_door_does_nothing_without_run_either(self):
        """The tool handler defaults `run` to False and so does the function
        underneath it. A sibling bench calling `sweep_chunkings` directly must
        get a plan and not eight rebuilds."""
        corpus = flat_corpus(self.root)
        rows = eval_file(self.root, rare_questions(), "flat.jsonl")
        plan = retrieval.sweep_chunkings(
            corpus_path=str(corpus),
            eval_path=str(rows),
            question_field="q",
            ground_truth_field="doc",
            thread_id=self.thread,
            settings=[800, 2400],
            k=1,
        )
        self.assertTrue(plan["ok"])
        self.assertFalse(plan["ran"])
        self.assertEqual(plan["measured"], [])
        self.assertEqual(self.indexes_on_disk(), 0)

    def test_the_plan_states_what_the_family_can_resolve_before_it_runs(self):
        plan = self.flat_sweep()
        stats = plan["statistics"]
        self.assertEqual(stats["family_size"], 6)
        self.assertEqual(stats["tightest_threshold"], retrieval.SWEEP_ALPHA / 6)
        self.assertEqual(
            stats["min_changed_questions_to_separate_any_pair"],
            retrieval.min_discordant_for(retrieval.SWEEP_ALPHA / 6),
        )


# ---------------------------------------------------------------------------


class TheComparisonIsPairedTest(SweepTest):
    """A question both settings answer the same way carries no information."""

    def test_the_agreeing_questions_are_out_of_every_pairwise_number(self):
        vectors = [
            ("a", [True, True, True, True, False, False]),
            ("b", [True, True, True, False, True, False]),
        ]
        out = retrieval.compare_hit_vectors(vectors)
        pair = out["comparisons"][0]
        self.assertEqual(pair["a_better_on"], 1)
        self.assertEqual(pair["b_better_on"], 1)
        self.assertEqual(pair["changed"], 2)
        self.assertEqual(pair["agreed"], 4)
        self.assertEqual(pair["p"], evals.mcnemar(1, 1))

    def test_the_delta_is_identically_the_paired_strip_over_its_own_width(self):
        """`evals.compare`'s hardest-won property, transplanted: the headline
        cannot contradict the counts printed under it, because it IS them."""
        out = self.split_sweep(run=True)
        for pair in out["comparisons"]:
            with self.subTest(pair=(pair["a"], pair["b"])):
                self.assertAlmostEqual(
                    pair["delta"],
                    (pair["a_better_on"] - pair["b_better_on"])
                    / out["compared_questions"],
                    places=12,
                )
        rates = {row["setting"]: row["recall"] for row in out["per_setting"]}
        for pair in out["comparisons"]:
            with self.subTest(pair=(pair["a"], pair["b"])):
                self.assertAlmostEqual(
                    pair["delta"], rates[pair["a"]] - rates[pair["b"]], places=12
                )

    def test_the_p_value_is_evals_mcnemar_and_not_a_second_derivation(self):
        out = self.split_sweep(run=True)
        for pair in out["comparisons"]:
            with self.subTest(pair=(pair["a"], pair["b"])):
                self.assertEqual(
                    pair["p"],
                    evals.mcnemar(pair["a_better_on"], pair["b_better_on"]),
                )

    def test_the_resolution_is_evals_resolution_for_and_not_a_second_one(self):
        out = self.split_sweep(run=True)
        for row in out["per_setting"]:
            with self.subTest(setting=row["setting"]):
                self.assertEqual(
                    row["resolution"], evals.resolution_for(row["hits"], row["of"])
                )

    def test_every_setting_is_scored_on_the_same_questions(self):
        out = self.split_sweep(run=True)
        widths = {row["of"] for row in out["per_setting"]}
        self.assertEqual(len(widths), 1)
        self.assertEqual(widths.pop(), out["compared_questions"])

    def test_unpaired_vectors_are_refused_rather_than_truncated(self):
        out = retrieval.compare_hit_vectors(
            [("a", [True, False, True]), ("b", [True, False])]
        )
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "unpaired_vectors")


# ---------------------------------------------------------------------------


class TheMultiplicityIsCorrectedTest(SweepTest):
    """Twenty-eight tests at 0.05 apiece is not a 0.05 claim."""

    def test_holm_steps_down_and_stops_at_the_first_failure(self):
        marks = retrieval.holm([0.001, 0.02, 0.04, 0.9], alpha=0.05)
        self.assertEqual(
            [mark["separated"] for mark in marks], [True, False, False, False]
        )
        self.assertEqual(marks[0]["holm_threshold"], 0.05 / 4)
        self.assertEqual(marks[1]["holm_threshold"], 0.05 / 3)

    def test_holm_never_separates_more_than_bonferroni_would_reject(self):
        for values in (
            [0.001, 0.002, 0.003],
            [0.049, 0.049, 0.049],
            [0.0001, 0.2, 0.3, 0.4],
        ):
            marks = retrieval.holm(values, alpha=0.05)
            with self.subTest(values=values):
                for value, mark in zip(values, marks):
                    if value > 0.05:
                        self.assertFalse(mark["separated"])
                    self.assertGreaterEqual(mark["adjusted_p"], value)

    def test_the_adjusted_p_values_are_monotone(self):
        marks = retrieval.holm([0.02, 0.001, 0.03, 0.9], alpha=0.05)
        ordered = sorted(marks, key=lambda mark: mark["p"])
        adjusted = [mark["adjusted_p"] for mark in ordered]
        self.assertEqual(adjusted, sorted(adjusted))

    def test_min_discordant_is_arithmetic_and_agrees_with_evals_mcnemar(self):
        """The sentence a refusal owes the reader - "here is what would make it
        yes" - and it is checked against the test it is about rather than
        derived twice."""
        for family in (1, 3, 6, 15, 28, 66):
            alpha = retrieval.SWEEP_ALPHA / family
            needed = retrieval.min_discordant_for(alpha)
            with self.subTest(family=family):
                self.assertLessEqual(evals.mcnemar(needed, 0), alpha)
                self.assertGreater(evals.mcnemar(needed - 1, 0), alpha)

    def test_a_pair_that_would_pass_alone_is_refused_inside_a_family(self):
        """THE MULTIPLICITY CORRECTION, WHERE IT BITES. Six questions changing
        the same way is p=0.031, which clears 0.05 on its own and does not clear
        0.05/28. Two settings is a two-run comparison and the pair separates;
        the same evidence inside a family of eight does not."""
        alone = [
            ("a", [True] * 6 + [True] * 10),
            ("b", [False] * 6 + [True] * 10),
        ]
        pair_only = retrieval.compare_hit_vectors(alone)
        self.assertEqual(pair_only["family_size"], 1)
        self.assertTrue(pair_only["comparisons"][0]["separated"])
        self.assertAlmostEqual(pair_only["comparisons"][0]["p"], 0.03125, places=6)

        crowd = list(alone) + [
            (f"c{i}", [False] * 6 + [True] * 10) for i in range(6)
        ]
        family = retrieval.compare_hit_vectors(crowd)
        self.assertEqual(family["family_size"], 28)
        beaten = [
            pair
            for pair in family["comparisons"]
            if {pair["a"], pair["b"]} == {"a", "b"}
        ][0]
        self.assertAlmostEqual(beaten["p"], 0.03125, places=6)
        self.assertFalse(beaten["separated"])
        self.assertEqual(family["separated_n"], 0)
        self.assertEqual(family["verdict"], "no_evidence")
        self.assertIn("NO EVIDENCE", family["says"])

    def test_the_correction_states_only_numbers_this_payload_carries(self):
        """THE SENTENCE THE READER GETS, CHECKED AGAINST THE PAYLOAD UNDER IT.

        `correction` used to interpolate the REAL family size into a clause
        whose "roughly a one-in-three chance of at least one false separation
        at eight settings" was typed. On the twelve-setting sweep that renders
        as "66 tests ... at eight settings", which contradicts itself inside
        one sentence, and one in three was not the rate at any family size the
        tool allows - 1-(1-.05)^k is 33% at k=8 TESTS, while eight SETTINGS is
        k=28, where the independent figure is 76.2% and the measured one is
        42.0% (`test_pure_noise_between_eight_settings_...`).

        A number nobody computed, in the field whose whole job is to stop
        somebody believing a number nobody computed. So the sentence is now
        checked rather than read: every numeral in it must be one this payload
        carries, and the words the old defect was written in may not come back.
        """
        fossils = (
            "one-in-three",
            "one in three",
            "at eight settings",
            "twenty-eight",
        )
        for count in (2, 3, 8, 12):
            vectors = [
                (f"s{index}", [(row + index) % 3 != 0 for row in range(30)])
                for index in range(count)
            ]
            verdict = retrieval.compare_hit_vectors(vectors)
            sentence = verdict["correction"]
            allowed = {
                str(verdict["family_size"]),
                str(verdict["alpha"]),
                f"{verdict['tightest_threshold']:.5g}",
            }
            found = set(re.findall(r"\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", sentence))
            with self.subTest(settings=count):
                # THE WORDS FIRST, because the defect this test was written for
                # was spelled out rather than interpolated: a check that only
                # counts numerals never reaches a clause whose number is
                # "one-in-three". Ordered so a purely worded relapse fails on
                # its own line.
                for fossil in fossils:
                    self.assertNotIn(fossil, sentence.lower(), sentence)
                self.assertEqual(
                    found - allowed,
                    set(),
                    f"`correction` states {sorted(found - allowed)}, which is "
                    f"not the family size, the alpha or the tightest threshold "
                    f"this sweep computed. The sentence is:\n{sentence}",
                )
                # NON-VACUOUS THE OTHER WAY: the family size really is in
                # there, so an empty sentence could not pass the check above.
                self.assertIn(str(verdict["family_size"]), found)
                self.assertIn(f"{verdict['tightest_threshold']:.5g}", found)


# ---------------------------------------------------------------------------


class TheNullCrownsNothingTest(SweepTest):
    """Settings that do not differ, and what the tool says about them."""

    def test_the_structural_null_says_no_evidence_and_crowns_nothing(self):
        """Eight windows over a corpus of single short paragraphs cut it
        IDENTICALLY, so every hit vector is the same vector. If this reported a
        winner it would have invented one."""
        out = self.flat_sweep(
            settings=(800, 1200, 1600, 2000, 2400, 2800, 3200, 3600), run=True
        )
        self.assertEqual(len({row["passages"] for row in out["indexes"]}), 1)
        self.assertEqual(len({row["hits"] for row in out["per_setting"]}), 1)
        self.assertEqual(out["family_size"], 28)
        self.assertEqual(out["separated_n"], 0)
        self.assertEqual(out["verdict"], "no_evidence")
        self.assertIsNone(out["crowned"])
        self.assertIn("NO EVIDENCE", out["says"])
        self.assertEqual(
            sorted(out["not_beaten_by_anything"]),
            sorted(row["setting"] for row in out["per_setting"]),
        )
        for pair in out["comparisons"]:
            with self.subTest(pair=(pair["a"], pair["b"])):
                self.assertEqual(pair["changed"], 0)
                self.assertEqual(pair["p"], 1.0)

    def test_the_null_recall_is_not_perfect_so_a_maximum_had_room_to_tempt(self):
        """A null where every setting scores 100% proves nothing about a tool
        that refuses to crown: there is nothing to crown. The fixture is built
        so recall is well under 1.0 and the settings are still identical."""
        out = self.flat_sweep(run=True)
        recalls = {row["recall"] for row in out["per_setting"]}
        self.assertEqual(len(recalls), 1)
        only = recalls.pop()
        self.assertGreater(only, 0.0)
        self.assertLess(only, 1.0)

    def test_the_simulated_null_counts_the_false_winners_both_ways(self):
        """THE MEASUREMENT THAT DEFENDS THE CORRECTION, rather than an argument
        for it. Eight settings whose TRUE recall is identical at 0.5, ninety
        questions, two hundred trials, drawn independently - the worst case for
        false positives. Counted: how many of those null families would hand
        somebody at least one "winner" at raw p<=0.05, and how many do after
        Holm.

        The seed is fixed and CPython's Mersenne Twister is stable, so these are
        exact counts rather than a tolerance. If a future Python moves them the
        test fails loudly and the numbers get re-pasted, which is the right
        failure: the claim in the module docstring is a count.
        """
        rng = random.Random(20260821)
        trials = 200
        uncorrected = 0
        corrected = 0
        crowned = 0
        maxima = []
        means = []
        for _ in range(trials):
            vectors = [
                (f"s{i}", [rng.random() < 0.5 for _ in range(90)]) for i in range(8)
            ]
            verdict = retrieval.compare_hit_vectors(vectors)
            self.assertTrue(verdict["ok"])
            if verdict["crowned"] is not None:
                crowned += 1
            if any(pair["p"] <= 0.05 for pair in verdict["comparisons"]):
                uncorrected += 1
            if verdict["separated_n"]:
                corrected += 1
            recalls = [row["recall"] for row in verdict["per_setting"]]
            maxima.append(max(recalls))
            means.append(sum(recalls) / len(recalls))

        self.assertEqual(uncorrected, 85)
        self.assertEqual(corrected, 7)
        self.assertEqual(crowned, 0)
        # The corrected family-wise rate is at or under the nominal 5%; the
        # uncorrected one is many times it. Asserted as an inequality as well as
        # a count, so the POINT survives a re-paste.
        self.assertLessEqual(corrected, trials * 0.05)
        self.assertGreater(uncorrected, 10 * corrected)
        # And the bias the correction does NOTHING about, measured on the same
        # trials: the best of eight is several points above the truth, and every
        # setting's true recall is 0.5.
        self.assertAlmostEqual(statistics.mean(means), 0.50172, places=4)
        self.assertAlmostEqual(statistics.mean(maxima), 0.57689, places=4)
        self.assertGreater(statistics.mean(maxima) - statistics.mean(means), 0.05)

    def test_the_confirmation_reports_the_shrinkage_the_maximum_hides(self):
        """The split-half is the only part of the sweep that touches the upward
        bias. Under the null the setting chosen on one half falls back towards
        the truth on the other half, and the tool reports both numbers."""
        rng = random.Random(20260821)
        chosen_on = []
        confirmed = []
        for _ in range(200):
            vectors = [
                (f"s{i}", [rng.random() < 0.5 for _ in range(90)]) for i in range(8)
            ]
            confirmation = retrieval.confirm_on_held_out(vectors)
            self.assertTrue(confirmation["ok"])
            row = confirmation["rows"][0]
            chosen_on.append(row["chosen_on_recall"])
            confirmed.append(row["confirmed_recall"])
        self.assertGreater(statistics.mean(chosen_on), statistics.mean(confirmed))
        self.assertAlmostEqual(statistics.mean(confirmed), 0.5, places=2)
        self.assertGreater(
            statistics.mean(chosen_on) - statistics.mean(confirmed), 0.05
        )

    def test_the_confirmation_says_it_is_not_a_correction_to_subtract(self):
        """MEASURED AND THEN SAID. The split-half gap is the bias of a choice
        made on HALF the questions, which runs larger in expectation than the
        bias in the whole-sweep maximum - so a reader who subtracted it would be
        over-correcting. The tool says that rather than leaving the number to be
        misused."""
        out = self.flat_sweep(run=True)
        says = out["confirmation"]["says"]
        self.assertEqual(out["confirmation"]["gap_direction"], "fell")
        self.assertTrue(out["confirmation"]["gap_is_a_read_on_selection"])
        self.assertIn("IT IS NOT A CORRECTION TO SUBTRACT", says)
        self.assertIn("half your questions", says)
        self.assertIn("IN EXPECTATION", says)

    def test_a_gap_that_went_the_other_way_is_not_called_selection(self):
        """THE SENTENCE THIS BLOCK USED TO SHIP WAS FALSE WHENEVER THE GAP CAME
        OUT NEGATIVE, and negative is not rare. It asserted, unconditionally,
        that the difference between the two numbers "is the part of the lead that
        was selection rather than retrieval" and that "the gap here is larger
        than the bias in the whole-sweep maximum above". The upward bias of a
        maximum is NON-NEGATIVE by construction, so a negative gap is neither a
        quantity of it nor larger than one.

        Counted below on the same iid null this file already simulates: the gap
        is negative in a substantial minority of trials, so roughly one reply in
        eleven carried a number whose stated meaning was wrong. The tool now
        reads the sign before it writes the sentence."""
        rng = random.Random(20260821)
        negative = 0
        checked = 0
        for _ in range(1000):
            vectors = [
                (f"s{i}", [rng.random() < 0.5 for _ in range(90)]) for i in range(8)
            ]
            out = retrieval.confirm_on_held_out(vectors)
            self.assertTrue(out["ok"])
            gaps = [row["shrinkage"] for row in out["rows"]]
            if all(gap < 0 for gap in gaps):
                negative += 1
                checked += 1
                self.assertEqual(out["gap_direction"], "rose")
                self.assertFalse(out["gap_is_a_read_on_selection"])
                self.assertIn("THAT IS NOT A MEASUREMENT OF SELECTION",
                              out["says"])
                self.assertIn("non-negative by construction", out["says"])
                # And the claim that made it false is gone from that branch.
                self.assertNotIn("part of the lead that was selection",
                                 out["says"])
                self.assertNotIn("larger than the bias in the whole-sweep",
                                 out["says"])
            elif all(gap > 0 for gap in gaps):
                self.assertEqual(out["gap_direction"], "fell")
                self.assertTrue(out["gap_is_a_read_on_selection"])
        # NON-VACUOUS: the negative branch is not a hypothetical. This exact
        # count is the reach of the defect that was there.
        self.assertEqual(negative, 63)
        self.assertEqual(checked, 63)

    def test_the_split_does_not_claim_to_be_lines_of_the_eval_file(self):
        """`split_by` said "alternating questions in file order". The vectors it
        splits are over the rows this comparison KEPT - rows some setting could
        not score and rows a tie decided are already out - so position 0 is the
        first surviving row and not the first line of the file. It also assumes
        the two halves are interchangeable, which a hit vector cannot show."""
        out = self.flat_sweep(run=True)
        confirmation = out["confirmation"]
        self.assertIn("rows this comparison kept", confirmation["split_by"])
        self.assertIn("not by line in your file", confirmation["says"])
        self.assertIn("interchangeable", confirmation["assumes"])
        self.assertIn("interchangeable", confirmation["says"])

    def test_an_eval_file_that_alternates_easy_and_hard_breaks_the_split(self):
        """THE ASSUMPTION, BROKEN ON PURPOSE. An eval generator that emits one
        easy and one hard question per document produces a file with a period-two
        structure, and a split by alternating position hands the two halves
        different questions. The gap it reports is then 100 points and is a fact
        about the file rather than about selection. Nothing is crowned either
        way, which is the guarantee that has to hold whatever the split does."""
        vectors = [
            (f"s{i}", [(q % 2 == 0) == (i % 2 == 0) for q in range(120)])
            for i in range(8)
        ]
        confirmation = retrieval.confirm_on_held_out(vectors)
        self.assertEqual(
            [row["shrinkage"] for row in confirmation["rows"]], [1.0] * 4
        )
        # It reads as a 100-point selection cost and it is nothing of the
        # kind. The branch no longer ASSERTS that the gap is selection - it says
        # the gap is consistent with that and names the alternative in the same
        # breath, which is the only honest thing available from a hit vector.
        self.assertEqual(confirmation["gap_direction"], "fell")
        self.assertIn("CONSISTENT WITH that reading rather than proof of it",
                      confirmation["says"])
        self.assertNotIn("part of the lead that was selection",
                         confirmation["says"])
        self.assertIn("interchangeable", confirmation["says"])
        self.assertIn("alternate easy and hard", confirmation["says"])
        verdict = retrieval.compare_hit_vectors(vectors)
        self.assertIsNone(verdict["crowned"])
        self.assertEqual(verdict["separated_n"], 0)

    def test_a_tie_at_the_top_is_reported_as_a_tie(self):
        out = self.flat_sweep(run=True)
        self.assertTrue(out["confirmation"]["tie_on_the_choosing_half"])
        self.assertEqual(
            len(out["confirmation"]["chosen"]), len(out["per_setting"])
        )


# ---------------------------------------------------------------------------


class TheSweepStillConcludesWhenItCanTest(SweepTest):
    """A bench that refuses everything certifies nothing."""

    def test_a_real_difference_separates_and_the_answer_is_still_a_set(self):
        out = self.split_sweep(run=True)
        self.assertEqual(out["verdict"], "some_settings_separated")
        self.assertGreater(out["separated_n"], 0)
        self.assertIsNone(out["crowned"])
        self.assertEqual(sorted(out["not_beaten_by_anything"]), ["5000/20", "700/20"])
        self.assertIn("THAT IS A SET AND NOT A WINNER", out["says"])
        self.assertEqual(
            {row["setting"]: row["hits"] for row in out["per_setting"]},
            {"150/20": 0, "300/20": 0, "700/20": 20, "5000/20": 20},
        )

    def test_the_whole_curve_is_reported_and_not_only_the_best(self):
        out = self.split_sweep(run=True)
        self.assertEqual(len(out["per_setting"]), 4)
        for row in out["per_setting"]:
            with self.subTest(setting=row["setting"]):
                self.assertIn(f"{row['setting']} {row['hits']}/{row['of']}", out["says"])

    def test_each_setting_keeps_its_own_recall_demoted_and_labelled(self):
        """`evals.compare` keeps `aggregate` for the same reason: a setting's
        recall over its own rows is a real fact and it is not the number the
        comparison is made of."""
        out = self.split_sweep(run=True)
        for row in out["per_setting"]:
            with self.subTest(setting=row["setting"]):
                self.assertIn("own_run", row)
                self.assertIn("different denominator", row["own_run"]["says"])


# ---------------------------------------------------------------------------


class TheRefusalIsThePointTest(SweepTest):
    """Every way a sweep can look like a comparison without being one."""

    def test_passage_level_ground_truth_is_refused_because_a_key_names_a_cut(self):
        """THE REFUSAL ONLY A SWEEP CAN REACH. `alpha.md#3` is the fourth
        passage AT ONE CHUNKING; this tool varies the chunking, so the same key
        names different text at every setting. `measure_retriever_recall` scores
        one index and accepts a passage key happily - asserted here too, because
        the point is that the sweep is stricter and not that the key is bad."""
        corpus = flat_corpus(self.root)
        rows = eval_file(
            self.root,
            [
                {"q": f"{RARE[n % len(RARE)]} procedure", "doc": f"doc{n:02d}.md#0"}
                for n in range(20)
            ],
            "bykey.jsonl",
        )
        out = self.sweep(corpus, rows, [800, 2400], k=1, run=True)
        self.assertEqual(out["error"], "ground_truth_is_not_invariant_under_the_cut")
        self.assertEqual(out["measured"], [])
        self.assertEqual(out["verdict"], "nothing_was_compared")
        self.assertIn("A PASSAGE KEY NAMES A CUT", out["summary"])

        alone = REGISTRY.call(
            "measure_retriever_recall",
            {
                "eval_path": str(rows),
                "question_field": "q",
                "ground_truth_field": "doc",
                "index_id": out["indexes"][0]["index_id"],
                "k": 1,
            },
            actor=USER,
            thread_id=self.thread,
        )
        self.assertEqual(alone["ground_truth_level"], retrieval.PASSAGE_LEVEL)
        self.assertEqual(
            [row["fact"] for row in alone["measured"]], ["retriever_recall_at_k"]
        )

    def test_a_family_of_one_is_not_a_comparison(self):
        out = self.flat_sweep(settings=(1200,), run=True)
        self.assertEqual(out["error"], "not_enough_settings")
        self.assertEqual(self.indexes_on_disk(), 0)

    def test_a_duplicate_setting_would_inflate_the_family_and_is_refused(self):
        out = self.flat_sweep(settings=(800, 800, 1600), run=True)
        self.assertEqual(out["error"], "duplicate_settings")
        self.assertIn("inflates the family size", out["summary"])
        self.assertEqual(self.indexes_on_disk(), 0)

    def test_the_cap_is_a_judgement_on_a_plateau_and_says_so(self):
        """THE ARITHMETIC DOES NOT PICK TWELVE, and the refusal used to read as
        though it did. `min_discordant_for` climbs in steps: eleven, twelve,
        thirteen and fourteen settings all need TWELVE changed questions before
        McNemar's exact test can reach the Holm threshold, and the next step is
        at fifteen. So the cap sits in the middle of a plateau and where on it to
        stop is a choice. The floor never coming back down is the part that IS
        derived, and both halves are now said."""
        floors = {
            settings: retrieval.min_discordant_for(
                retrieval.SWEEP_ALPHA / (settings * (settings - 1) // 2)
            )
            for settings in range(2, 17)
        }
        self.assertEqual(
            [floors[settings] for settings in range(11, 15)], [12, 12, 12, 12]
        )
        self.assertEqual(floors[10], 11)
        self.assertEqual(floors[15], 13)
        # Never comes back down, which is the claim the cap really rests on.
        self.assertEqual(
            sorted(floors[settings] for settings in range(2, 17)),
            [floors[settings] for settings in range(2, 17)],
        )
        corpus = flat_corpus(self.root)
        rows = eval_file(self.root, rare_questions(), "flat.jsonl")
        out = self.sweep(corpus, rows, list(range(400, 400 + 13 * 100, 100)), k=1)
        self.assertEqual(out["error"], "too_many_settings")
        self.assertIn("JUDGEMENT AND NOT A DERIVATION", out["detail"])
        self.assertIn("plateau", out["detail"])

    def test_too_many_settings_is_refused_with_what_it_could_not_resolve(self):
        out = self.flat_sweep(
            settings=tuple(400 + 100 * i for i in range(13)), run=True
        )
        self.assertEqual(out["error"], "too_many_settings")
        self.assertIn("78 pairwise comparisons", out["summary"])
        self.assertEqual(self.indexes_on_disk(), 0)

    def test_no_settings_is_refused_with_the_reason_there_is_no_default(self):
        corpus = flat_corpus(self.root)
        rows = eval_file(self.root, rare_questions(), "flat.jsonl")
        out = REGISTRY.call(
            "compare_chunkings",
            {
                "corpus_path": str(corpus),
                "eval_path": str(rows),
                "question_field": "q",
                "ground_truth_field": "doc",
                "run": True,
            },
            actor=USER,
            thread_id=self.thread,
        )
        self.assertEqual(out["error"], "no_settings")
        self.assertIn("WHICH SETTINGS TO TRY IS THE FAMILY SIZE", out["summary"])

    def test_a_setting_is_never_clamped_into_range(self):
        """`build` clamps one index's parameters because one index is one index.
        A sweep's settings ARE the experiment, and moving one silently changes
        what was compared while leaving the reply looking the same."""
        out = self.flat_sweep(settings=(150, 800), run=True)
        self.assertEqual(out["error"], "overlap_past_the_window")
        self.assertEqual(self.indexes_on_disk(), 0)
        normalised = retrieval.normalise_settings([150, 800])
        self.assertIn("error", normalised)

    def test_no_ground_truth_is_refused_before_a_single_index_is_built(self):
        corpus = flat_corpus(self.root)
        rows = eval_file(
            self.root,
            [{"q": f"{term} procedure"} for term in RARE],
            "bare.jsonl",
        )
        out = self.sweep(
            corpus, rows, [800, 2400], run=True, ground_truth_field=None
        )
        self.assertEqual(out["error"], "no_ground_truth")
        self.assertEqual(self.indexes_on_disk(), 0)
        self.assertIn("I will not ask a model which passage", out["summary"])
        # And the example it gives is a real document from THIS corpus rather
        # than a made-up path, which is the difference between a refusal you can
        # act on and one you have to interpret.
        self.assertIn("doc00.md", out["summary"])

    def test_the_row_cap_is_a_refusal_because_a_prefix_is_not_a_sample(self):
        corpus = flat_corpus(self.root)
        rows = eval_file(self.root, rare_questions(), "flat.jsonl")
        out = self.sweep(corpus, rows, [800, 2400], max_questions=5, run=True)
        self.assertEqual(out["error"], "hit_row_cap")
        self.assertEqual(self.indexes_on_disk(), 0)
        self.assertIn("PREFIX", out["summary"])

    def test_a_setting_that_would_truncate_the_index_is_refused(self):
        """A truncated index is not the corpus, so a recall against it is not a
        recall over the corpus - and comparing a truncated index with a whole
        one is comparing two different corpora. Caught in the plan, so it costs
        nothing to discover."""
        old = retrieval.MAX_PASSAGES
        retrieval.MAX_PASSAGES = 10
        self.addCleanup(setattr, retrieval, "MAX_PASSAGES", old)
        out = self.flat_sweep(run=True)
        self.assertEqual(out["error"], "would_truncate")
        self.assertEqual(self.indexes_on_disk(), 0)

    def test_a_name_already_taken_is_a_refusal_and_not_an_overwrite(self):
        corpus = flat_corpus(self.root)
        other = Path(self.root) / "other"
        other.mkdir()
        (other / "unrelated.md").write_text(
            "A completely different document about something else entirely, "
            "long enough to survive the minimum passage length.\n",
            encoding="utf-8",
        )
        retrieval.build(
            path=str(other),
            thread_id=self.thread,
            name=f"flat#chunk-800-{retrieval.DEFAULT_PASSAGE_OVERLAP}",
        )
        rows = eval_file(self.root, rare_questions(), "flat.jsonl")
        out = self.sweep(corpus, rows, [800, 2400], k=1, run=True)
        self.assertEqual(out["error"], "name_taken")
        self.assertEqual(self.indexes_on_disk(), 1)

    def test_an_index_in_another_conversation_is_not_reused(self):
        self.flat_sweep(run=True)
        plan = self.flat_sweep(thread=self.other)
        self.assertEqual(plan["will_do"]["reused_without_rebuilding"], 0)
        self.assertEqual(plan["will_do"]["rebuilds"], 4)

    def test_a_sweep_with_no_conversation_refuses_and_names_the_door(self):
        corpus = flat_corpus(self.root)
        rows = eval_file(self.root, rare_questions(), "flat.jsonl")
        out = retrieval.sweep_chunkings(
            corpus_path=str(corpus),
            eval_path=str(rows),
            question_field="q",
            ground_truth_field="doc",
            thread_id=None,
            settings=[800, 2400],
            run=True,
        )
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "no_thread")
        self.assertTrue(str(out["detail"]).strip())


# ---------------------------------------------------------------------------


class TheRowsThatCarryNoInformationAreDroppedTest(SweepTest):
    """A tie-break must never decide which chunking wins."""

    def test_a_row_a_score_tie_decided_is_out_of_every_setting_at_once(self):
        """A corpus holding a document and a byte-identical copy of it scores
        both identically, so whether the right one lands in the top k is the
        alphabetical order of two file names. `measure_retriever_recall` already
        refuses to STAMP such a run; a sweep must additionally refuse to COMPARE
        on it, because the tie-break would be choosing the winner."""
        folder = Path(self.root) / "twins"
        folder.mkdir()
        body = (
            "The zarquon protocol governs the first stage of the ordering and "
            "is described here at sufficient length to be indexed properly.\n"
        )
        (folder / "alpha.md").write_text(body, encoding="utf-8")
        (folder / "zzz_copy.md").write_text(body, encoding="utf-8")
        (folder / "beta.md").write_text(
            "The blorptide index governs the second stage of the ordering and "
            "is also described here at a workable length for indexing.\n",
            encoding="utf-8",
        )
        rows = eval_file(
            self.root,
            [
                {"q": "zarquon protocol", "doc": "alpha.md"},
                {"q": "blorptide index", "doc": "beta.md"},
            ],
            "twins.jsonl",
        )
        out = self.sweep(folder, rows, [900, 1800], k=1, run=True)
        self.assertEqual(out["dropped_decided_by_a_tie"], 1)
        self.assertEqual(out["compared_questions"], 1)
        for row in out["per_setting"]:
            with self.subTest(setting=row["setting"]):
                self.assertEqual(row["of"], 1)
        self.assertIn("decided by a score tie", out["says"])

    def test_nothing_left_to_compare_is_a_refusal_and_not_a_zero(self):
        folder = Path(self.root) / "alltwins"
        folder.mkdir()
        body = (
            "The zarquon protocol governs the first stage of the ordering and "
            "is described here at sufficient length to be indexed properly.\n"
        )
        for name in ("alpha.md", "zzz_copy.md"):
            (folder / name).write_text(body, encoding="utf-8")
        rows = eval_file(
            self.root, [{"q": "zarquon protocol", "doc": "alpha.md"}], "one.jsonl"
        )
        out = self.sweep(folder, rows, [900, 1800], k=1, run=True)
        self.assertEqual(out["error"], "no_comparable_questions")
        self.assertEqual(out["compared_questions"], 0)
        self.assertEqual(out["verdict"], "nothing_was_compared")
        self.assertEqual(out["measured"], [])

    def test_unlabelled_rows_are_counted_and_named_in_the_denominator(self):
        corpus = flat_corpus(self.root)
        rows = rare_questions()
        for row in rows[10:]:
            row["doc"] = ""
        path = eval_file(self.root, rows, "partly.jsonl")
        out = self.sweep(corpus, path, [800, 2400], k=1, run=True)
        self.assertEqual(out["questions"]["unlabelled"], 10)
        self.assertEqual(out["questions"]["eligible"], 10)
        self.assertIn("carry no ground truth", out["says"])


# ---------------------------------------------------------------------------


class SettingsThatAreTheSameExperimentAreNamedTest(SweepTest):
    """Different numbers, one cut - said out loud, because "no evidence that
    these settings differ" and "these settings ARE the same index" are different
    facts and only one of them is about chunking.

    `normalise_settings` already refuses a setting typed twice, and its stated
    reason is about the RESULTING CUT: one index compared with itself is a
    comparison whose answer is known before it runs, and it inflates the family
    every other p-value is corrected against. `flat_corpus` above is documented
    as making that happen without a repeated number - a window wider than every
    paragraph is inert - so the argument applied and was not being made.

    It is a FACT and not a refusal. A caller cannot know their corpus is flat at
    these windows, and "these eight windows all cut your corpus the same way" is
    the most useful thing this tool can say about such a corpus. Refusing would
    throw that finding away.
    """

    def test_the_plan_says_how_many_distinct_cuts_these_settings_really_are(self):
        plan = self.flat_sweep()
        self.assertEqual(plan["will_do"]["settings"], 4)
        self.assertEqual(plan["will_do"]["distinct_cuts"], 1)
        self.assertEqual(plan["will_do"]["pairwise_comparisons"], 6)
        self.assertEqual(
            plan["will_do"]["pairwise_comparisons_over_distinct_cuts"], 0
        )
        self.assertEqual(
            plan["cuts"]["identical_groups"],
            [["800/200", "1600/200", "2400/200", "3200/200"]],
        )
        self.assertIn("ARE 1 DISTINCT CUT OF THIS CORPUS", plan["summary"])
        self.assertIn("NOT a finding about chunking", plan["summary"])

    def test_two_settings_with_the_same_passage_count_are_not_the_same_cut(self):
        """THE CHECK IS OF THE TEXT AND NOT OF THE COUNT, and this is the case
        that tells the two apart. One long paragraph cut at 400, 401 and 410
        characters gives THREE passages every time and three DIFFERENT sets of
        three: `_split_long` searches backwards from the window edge for a word
        boundary, so a one-character change in the window moves every cut. A
        fingerprint over passage counts would call these one experiment and be
        wrong in the direction that matters - it would tell a person their sweep
        did not vary chunking when it did."""
        folder = Path(self.root) / "wordy"
        folder.mkdir(parents=True, exist_ok=True)
        for number in range(8):
            term = RARE[number % len(RARE)]
            body = " ".join(
                term if position == 3 else f"word{position:03d}"
                for position in range(140)
            )
            (folder / f"doc{number:02d}.md").write_text(body, encoding="utf-8")

        counts = set()
        texts = set()
        for chars in (400, 401, 410):
            kept = [
                piece
                for path in sorted(folder.iterdir())
                for piece, _ in retrieval.kept_passages(
                    path.read_text(encoding="utf-8"), chars, 0
                )[0]
            ]
            counts.add(len(kept))
            texts.add(tuple(kept))
        # Same number of passages, three different cuts. A counter would tie.
        self.assertEqual(len(counts), 1)
        self.assertEqual(len(texts), 3)

        rows = eval_file(
            self.root,
            [
                {"q": f"{RARE[number % len(RARE)]}", "doc": f"doc{number:02d}.md"}
                for number in range(8)
            ],
            "wordy.jsonl",
        )
        plan = self.sweep(
            folder,
            rows,
            [
                {"passage_chars": 400, "passage_overlap": 0},
                {"passage_chars": 401, "passage_overlap": 0},
                {"passage_chars": 410, "passage_overlap": 0},
            ],
            k=1,
        )
        self.assertEqual(
            {row["passages"] for row in plan["settings"]}, {counts.pop()}
        )
        self.assertEqual(plan["will_do"]["distinct_cuts"], 3)
        self.assertEqual(plan["cuts"]["identical_groups"], [])
        self.assertNotIn("DISTINCT CUT", plan["summary"])

    def test_the_fixture_really_is_one_cut_and_the_split_corpus_is_four(self):
        """The flat corpus is checked to be one cut and the split corpus four, so
        neither side of the report is taken on trust."""
        flat = flat_corpus(self.root)
        texts = {
            tuple(
                piece
                for path in sorted(Path(flat).iterdir())
                for piece, _ in retrieval.kept_passages(
                    path.read_text(encoding="utf-8"), chars, 200
                )[0]
            )
            for chars in (800, 1600, 2400, 3200)
        }
        self.assertEqual(len(texts), 1)

        rows = eval_file(self.root, split_questions(), "split.jsonl")
        plan = self.sweep(
            split_corpus(self.root),
            rows,
            [
                {"passage_chars": 150, "passage_overlap": 20},
                {"passage_chars": 300, "passage_overlap": 20},
                {"passage_chars": 700, "passage_overlap": 20},
                {"passage_chars": 5000, "passage_overlap": 20},
            ],
            k=1,
        )
        self.assertEqual(plan["will_do"]["distinct_cuts"], 4)
        self.assertEqual(plan["cuts"]["identical_groups"], [])
        self.assertEqual(plan["cuts"]["says"], "")
        self.assertNotIn("DISTINCT CUT", plan["summary"])

    def test_a_partial_collapse_names_only_the_settings_that_collapsed(self):
        """Two of four, not all or nothing. `split_corpus`'s documents are cut
        differently at 150 and at 700, and identically at 5000 and 9000 - both of
        those windows are wider than any document in it."""
        rows = eval_file(self.root, split_questions(), "split.jsonl")
        plan = self.sweep(
            split_corpus(self.root),
            rows,
            [
                {"passage_chars": 150, "passage_overlap": 20},
                {"passage_chars": 700, "passage_overlap": 20},
                {"passage_chars": 5000, "passage_overlap": 20},
                {"passage_chars": 9000, "passage_overlap": 20},
            ],
            k=1,
        )
        self.assertEqual(plan["will_do"]["distinct_cuts"], 3)
        self.assertEqual(
            plan["cuts"]["identical_groups"], [["5000/20", "9000/20"]]
        )
        self.assertEqual(plan["will_do"]["pairwise_comparisons"], 6)
        self.assertEqual(
            plan["will_do"]["pairwise_comparisons_over_distinct_cuts"], 3
        )
        self.assertIn("ARE 3 DISTINCT CUTS OF THIS CORPUS, NOT 4", plan["summary"])

    def test_the_collapse_is_said_in_the_run_too_and_before_the_verdict(self):
        """A person who only ran it still has to be told. And the sentence comes
        BEFORE "NO EVIDENCE that any of these settings differs", because it
        changes what that verdict is about."""
        out = self.flat_sweep(run=True)
        self.assertEqual(out["verdict"], "no_evidence")
        says = out["says"]
        self.assertIn("ARE 1 DISTINCT CUT OF THIS CORPUS", says)
        self.assertLess(
            says.index("ARE 1 DISTINCT CUT OF THIS CORPUS"),
            says.index("NO EVIDENCE that any of these"),
        )

    def test_a_setting_typed_twice_is_still_refused_rather_than_reported(self):
        """The distinction, asserted so it is not lost: a repeated NUMBER is a
        caller's error and stays a refusal; an inert WINDOW is a fact about the
        corpus the caller could not have known, and is reported."""
        corpus = flat_corpus(self.root)
        rows = eval_file(self.root, rare_questions(), "flat.jsonl")
        out = self.sweep(corpus, rows, [800, 1600, 800], k=1)
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "duplicate_settings")


# ---------------------------------------------------------------------------


class TheMaximumIsNotAdmissibleAsTheFactTest(SweepTest):
    """What may be written down, and what re-measuring does and does not fix."""

    def test_a_sweep_records_nothing_at_all(self):
        before = len(self.facts())
        out = self.split_sweep(run=True)
        self.assertEqual(out["measured"], [])
        self.assertEqual(len(self.facts()), before)

    def test_the_reply_says_re_measuring_buys_provenance_and_not_selection(self):
        out = self.split_sweep(run=True)
        self.assertIn("measures=()", out["not_measured"])
        self.assertIn("What it buys about SELECTION is nothing",
                      out["not_measured"])
        self.assertIn("PROVENANCE", out["not_measured"])

    def test_the_reply_never_promises_the_same_number_back(self):
        """THE SENTENCE THIS PARAGRAPH USED TO CARRY WAS FALSE, and it was false
        on ordinary runs rather than in a corner. It said that re-running
        `measure_retriever_recall` on the setting you pick and this same file
        "returns a bit-for-bit identical number with a stamp on it". A sweep
        drops every row some setting could not score and every row a tie decided
        under ANY setting; a single run keeps its own. Different denominators,
        different number - and if the setting's own run hits one of the seven
        refusals, no number at all.

        Asserted over every reply shape, including the plan and the refusal,
        because the constant travels on all of them."""
        corpus = flat_corpus(self.root)
        good = eval_file(self.root, rare_questions(), "flat.jsonl")
        bare = eval_file(
            self.root, [{"q": f"{t} procedure"} for t in RARE], "bare.jsonl"
        )
        replies = {
            "plan": self.sweep(corpus, good, [800, 2400], k=1),
            "run": self.sweep(corpus, good, [800, 2400], k=1, run=True),
            "refusal": self.sweep(
                corpus, bare, [800, 2400], k=1, run=True, ground_truth_field=None
            ),
        }
        for label, reply in replies.items():
            with self.subTest(reply=label):
                sentence = reply["stamps_nothing"]
                for promise in (
                    "bit-for-bit",
                    "identical number",
                    "returns a bit",
                ):
                    self.assertNotIn(promise, sentence)
                self.assertIn("different denominators", sentence)
                self.assertIn("no number", sentence)

    def test_re_measuring_hands_back_a_different_denominator_when_rows_dropped(
        self,
    ):
        """DRIVEN, NOT ARGUED. `vanishing_corpus` loses one document at the
        42-character window, so the sweep compares 6 of the 7 questions while
        `measure_retriever_recall` on either index scores every row that index
        can score. Doing exactly what the reply tells a person to do returns a
        different number from the curve they were reading - and the reply now
        says so, with the count, before they go and do it."""
        corpus = vanishing_corpus(self.root)
        rows = [
            {"q": f"{RARE[n % len(RARE)]} procedure", "doc": f"doc{n:02d}.md"}
            for n in range(6)
        ] + [{"q": "vexilate", "doc": "odd.md"}]
        path = eval_file(self.root, rows, "vanishing.jsonl")
        out = self.sweep(
            corpus,
            path,
            [{"passage_chars": 42, "passage_overlap": 0},
             {"passage_chars": 800, "passage_overlap": 0}],
            k=1,
            run=True,
        )
        self.assertEqual(out["compared_questions"], 6)
        # The reply counted it in advance rather than leaving it to be found.
        told = out["re_measuring"]
        self.assertEqual(told["rows_this_comparison_used"], 6)
        self.assertEqual(told["rows_dropped_before_comparing"], 1)
        self.assertEqual(told["settings_whose_own_run_uses_the_same_rows"], 1)
        self.assertIn("different denominator", told["says"])
        self.assertIn(told["says"], out["says"])

        # And now go and do the thing the reply tells the person to do, for the
        # setting whose own run does NOT use the same rows.
        wider = [row for row in out["per_setting"] if row["own_run"]["of"] != 6][0]
        again = REGISTRY.call(
            "measure_retriever_recall",
            {
                "eval_path": out["eval_path"],
                "question_field": "q",
                "ground_truth_field": "doc",
                "index_id": wider["index_id"],
                "k": 1,
            },
            actor=USER,
            thread_id=self.thread,
        )
        self.assertEqual(again["questions_scored"], 7)
        self.assertNotEqual(again["questions_scored"], wider["of"])
        self.assertNotEqual(again["hits"], wider["hits"])
        # The RATE happens to coincide here at 1.0, which is exactly why the
        # promise survived: two different measurements can agree by accident.
        # The claim that was false is that they are the same measurement.
        self.assertEqual(again["recall_at_k"], wider["recall"])

    def test_re_measuring_does_return_the_same_number_when_nothing_was_dropped(
        self,
    ):
        """THE OTHER HALF, so the sentence above is not read as "it never
        matches". When a sweep drops nothing, the denominators agree and the
        figure does come back identical with a stamp on it - which is exactly
        why the old unconditional promise survived so long."""
        out = self.split_sweep(run=True)
        self.assertEqual(out["dropped_not_scored_by_every_setting"], 0)
        self.assertEqual(out["dropped_decided_by_a_tie"], 0)
        told = out["re_measuring"]
        self.assertEqual(told["rows_dropped_before_comparing"], 0)
        self.assertEqual(
            told["settings_whose_own_run_uses_the_same_rows"],
            len(out["per_setting"]),
        )
        leader = max(out["per_setting"], key=lambda row: row["hits"])
        again = REGISTRY.call(
            "measure_retriever_recall",
            {
                "eval_path": out["eval_path"],
                "question_field": "q",
                "ground_truth_field": "doc",
                "index_id": leader["index_id"],
                "k": 1,
            },
            actor=USER,
            thread_id=self.thread,
        )
        self.assertEqual(again["recall_at_k"], leader["recall"])
        self.assertEqual(
            [row["fact"] for row in again["measured"]], ["retriever_recall_at_k"]
        )

    def test_the_reply_names_the_index_id_each_setting_lives_in(self):
        """"The setting you pick" was not a thing a person could pass to
        anything. `measure_retriever_recall` takes `index_id`, and without one it
        scores the NEWEST index in the conversation - which after a sweep is
        whichever setting happened to be last in the list. The ids are in the
        reply now, and the reply says that the default is an order rather than a
        choice."""
        out = self.split_sweep(run=True)
        told = out["re_measuring"]
        self.assertIn("index_id", told["how_to_name_a_setting"])
        self.assertIn("an order, not a", told["how_to_name_a_setting"])
        for row in out["per_setting"]:
            with self.subTest(setting=row["setting"]):
                self.assertIn(f"index_id {row['index_id']}", told["says"])

    def facts(self):
        with db.session() as connection:
            return connection.execute(
                "SELECT * FROM fact_evidence WHERE fact = 'retriever_recall_at_k'"
            ).fetchall()


# ---------------------------------------------------------------------------


class TheThreeLeversAreNamedEveryTimeTest(SweepTest):
    """A person told to fix their retriever is owed the whole answer."""

    def test_every_reply_names_the_three_levers_this_harness_cannot_pull(self):
        corpus = flat_corpus(self.root)
        good = eval_file(self.root, rare_questions(), "flat.jsonl")
        bare = eval_file(
            self.root, [{"q": f"{t} procedure"} for t in RARE], "bare.jsonl"
        )
        replies = {
            "plan": self.sweep(corpus, good, [800, 2400], k=1),
            "run": self.sweep(corpus, good, [800, 2400], k=1, run=True),
            "refusal": self.sweep(
                corpus, bare, [800, 2400], k=1, run=True, ground_truth_field=None
            ),
            "settings_refusal": self.sweep(corpus, good, [800], k=1, run=True),
        }
        for label, reply in replies.items():
            with self.subTest(reply=label):
                self.assertIn("levers", reply)
                named = " ".join(
                    row["lever"] for row in reply["levers"]["we_cannot_pull"]
                )
                self.assertIn("dense", named)
                self.assertIn("reranker", named)
                self.assertIn("query rewriting", named)
                self.assertIn("chunking", reply["levers"]["we_can_vary"])
                # AND IN THE SENTENCE, not only in the structured block. A
                # person who reads the summary and nothing else must not come
                # away thinking a chunk sweep is the whole of "fix your
                # retriever".
                for lever in ("dense retrieval", "reranker", "query rewriting"):
                    self.assertIn(lever, reply["summary"])


    def test_a_refusal_raised_after_building_still_names_all_three(self):
        """The reply that goes through `_sweep_refusal` is the one somebody
        reads at the worst moment - they asked for a comparison, they paid for
        an index, and they got neither. It is the last place the three levers
        should be allowed to fall out of."""
        corpus = flat_corpus(self.root)
        rows = eval_file(
            self.root,
            [
                {"q": f"{RARE[n % len(RARE)]} procedure", "doc": f"doc{n:02d}.md#0"}
                for n in range(20)
            ],
            "bykey.jsonl",
        )
        out = self.sweep(corpus, rows, [800, 2400], k=1, run=True)
        self.assertEqual(out["error"], "ground_truth_is_not_invariant_under_the_cut")
        named = " ".join(row["lever"] for row in out["levers"]["we_cannot_pull"])
        self.assertIn("dense", named)
        self.assertIn("reranker", named)
        self.assertIn("query rewriting", named)

    def test_each_lever_says_why_not_and_who_can(self):
        reply = self.flat_sweep()
        for row in reply["levers"]["we_cannot_pull"]:
            with self.subTest(lever=row["lever"]):
                self.assertTrue(row["why_not"].strip())
                self.assertTrue(row["who_can"].strip())

    def test_the_engine_node_this_answers_is_still_there(self):
        """If `S3_RETRIEVAL_IS_THE_BOTTLENECK` is renamed or its outcome
        changes, this tool is answering a question the engine no longer asks and
        this file should say so first."""
        from app import diagnosis

        node = diagnosis.default_spec().node_index["S3_RETRIEVAL_IS_THE_BOTTLENECK"]
        self.assertEqual(node["outcome"], "NO_TRAIN__FIX_RETRIEVAL")
        for lever in ("Chunking", "reranker", "query rewriting", "BM25"):
            with self.subTest(lever=lever):
                self.assertIn(lever, node["action"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
