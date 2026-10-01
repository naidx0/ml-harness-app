"""The prompt bench: it versions, it aims, it holds out - and it refuses.

`app/tools/prompts.py` is the first place in this product where the verdict *do
not train, fix the prompt* stops being advice and becomes an artifact. This file
is the adversarial half of that claim, organised around the five things the
bench has to get right and the one thing it has to refuse:

  VERSION  - a prompt is a numbered version of a named line, with a parent, a
             note saying what changed, and the eval run that scored it. You
             cannot say "better" without saying better than what.
  PIN      - the line fixes the instrument. Two prompts graded by different
             metrics, on different columns, or against different models were
             never comparable, and each of those is refused by name.
  AIM      - a change with `targets=` reports what it did to THAT bucket, and
             `TheBucketCannotResolveWhatItIsTooSmallToResolveTest` is the
             pay-off: fixing five of five format failures is reported as NO
             EVIDENCE, because six is the smallest bucket a clean sweep of which
             reaches p<=0.05, and that number is computed rather than quoted.
  HOLD OUT - few-shot exemplars come from the rows the model got WRONG, and
             their rows leave the score by construction. There is no argument
             that turns that off.
  REFUSE   - and this is the one that makes the product different from a prompt
             playground. `TheRefusalIsThePointTest` puts a five-point
             improvement in front of the bench on forty rows and demands the
             words NO EVIDENCE back, with the champion unchanged.

`TheWallIsInTheTableTest` is the reason the refusal is believable a year from
now: it goes around `attempt` entirely and writes straight to SQLite, and the
`CHECK` on `prompt_champions` rejects every shape of unresolved winner
including the NULL-shaped ones that a naive constraint would let through.

Nothing here uses a network. `PromptModel` answers from the row number and the
system prompt it was given, so every count asserted below is arithmetic over a
file this module wrote. The live half - two genuinely different prompts against
granite4-hermes on a real Ollama, on a scratch database - is not in this file,
because a test that needs somebody's model running is a test that fails on a
fresh checkout. It was run by hand and its numbers are in the commit that added
this file.
"""

from __future__ import annotations

import json
import re
import sqlite3
import unittest
from pathlib import Path

from app import db, events
from app.providers import Delta, store as provider_store
from app.tools import REGISTRY, evals, evidence, prompts
from app.tools.evidence import MODEL

import support


LABELS = ("yes", "no", "maybe", "never", "always")

#: The prompts under test. Each is a marker the scripted model recognises, so a
#: test says "this prompt gets twenty rows right" rather than trying to write a
#: prompt that really would.
BASE = "[A] Answer with one word."
REWRITE = "[B] Answer with exactly one of the five labels and nothing else."
WORSE = "[C] Answer at length, with reasoning."


def eval_file(root: Path, rows: int = 40, name: str = "eval.jsonl") -> Path:
    """`rows` questions with a five-label answer column, in equal proportion.

    Five distinct labels over forty rows is a CLOSED LABEL SET by
    `evals._label_set`'s two bounds, which is what lets the bucketer tell
    `wrong_facts` from `wrong_format` - and those two buckets are what the
    targeting tests below are about.
    """
    path = Path(root) / name
    path.write_text(
        "\n".join(
            json.dumps({"q": f"q{i}", "a": LABELS[i % len(LABELS)]})
            for i in range(rows)
        ),
        encoding="utf-8",
    )
    return path


class PromptModel:
    """Right on the first N rows, where N depends on the SYSTEM PROMPT.

    That dependency is the whole point: a prompt bench is untestable against a
    model whose behaviour does not change when the prompt does. `table` maps a
    marker to how many leading rows the model gets right while that marker is in
    the system prompt, and the first matching entry wins - so a few-shot variant,
    which carries its base prompt's marker AND the exemplar preamble, is keyed on
    whichever the test listed first.

    The three failure shapes cycle on the row index so every bucket is present
    and every bucket's membership is arithmetic:

        index % 3 == 0  ->  refuses
        index % 3 == 1  ->  wrong_format   (the right answer inside a sentence)
        index % 3 == 2  ->  wrong_facts    (a different member of the label set)
    """

    def __init__(self, table: dict[str, int], default: int = 0) -> None:
        self.table = dict(table)
        self.default = default
        self.asked: list[str] = []
        self.systems: list[str] = []

    def leading(self, system: str) -> int:
        for marker, count in self.table.items():
            if marker in str(system):
                return count
        return self.default

    def stream(self, conversation, offered=None, *, secret=None):
        system = conversation[0]["content"]
        question = conversation[-1]["content"]
        self.systems.append(str(system))
        self.asked.append(str(question))
        index = int(re.sub(r"\D", "", str(question)) or 0)
        if index < self.leading(system):
            yield Delta(kind="text", text=LABELS[index % len(LABELS)])
            return
        shape = index % 3
        if shape == 0:
            yield Delta(kind="text", text="I'm sorry, I cannot answer that.")
        elif shape == 1:
            yield Delta(kind="text", text=f"The answer is {LABELS[index % 5]}.")
        else:
            yield Delta(kind="text", text=LABELS[(index + 1) % len(LABELS)])


class PromptBenchTest(unittest.TestCase):
    """Sandbox, one local connection, two conversations, a forty-row eval set."""

    def setUp(self) -> None:
        self.root = support.sandbox(self)
        self.threads = support.conversations(2)
        self.thread = self.threads[0]["id"]
        self.other = self.threads[1]["id"]
        self.path = eval_file(self.root)
        row = provider_store.create(
            "Scripted", "http://127.0.0.1:11434", "scripted", "ollama"
        )
        provider_store.set_active(row["id"])
        self.provider = row

    def connect(self, model: PromptModel) -> PromptModel:
        """Point the eval bench at a scripted model, and put `build` back after."""
        original = evals.build
        evals.build = lambda adapter, base_url, name: model
        self.addCleanup(lambda: setattr(evals, "build", original))
        return model

    def reconnect(self, name: str, model: str) -> dict:
        """A second local connection, so a model swap can be exercised."""
        row = provider_store.create(
            name, "http://127.0.0.1:11434", model, "ollama"
        )
        provider_store.set_active(row["id"])
        return row

    def try_prompt(self, thread=None, **arguments):
        payload = {
            "line": "classify",
            "eval_path": str(self.path),
            "input_field": "q",
            "expected_field": "a",
            "sample": 40,
        }
        payload.update(arguments)
        return REGISTRY.call(
            "try_prompt", payload, actor=MODEL, thread_id=thread or self.thread
        )


# ---------------------------------------------------------------------------


class TheToolSurfaceIsDeclaredTest(PromptBenchTest):
    """What the bench may stamp - nothing - and what it may never be asked for."""

    def test_neither_tool_can_stamp_a_single_fact(self):
        """The answer to "should an unresolved winner be MEASURED": there is no
        path by which a winner is recorded as a fact at all."""
        for name in ("try_prompt", "read_prompt_bench"):
            with self.subTest(tool=name):
                self.assertEqual(REGISTRY.get(name).measures, ())
                self.assertEqual(REGISTRY.get(name).bounds, ())

    def test_the_two_gate_facts_it_looks_like_it_observes_are_still_refused(self):
        """`prompt_iterations` and `fewshot_tried` are two of the three facts
        `G2_PROMPT_EXHAUSTED` reads, and `evidence.may_be_declared_measurable`
        refuses both. Widening that is a change to the honesty machinery and it
        is deliberately NOT part of the step that built the bench - so the
        refusal is asserted here, where a future widening will have to come and
        change it on purpose."""
        for fact in ("prompt_iterations", "fewshot_tried"):
            with self.subTest(fact=fact):
                self.assertFalse(evidence.may_be_declared_measurable(fact))
                self.assertEqual(
                    [t.name for t in REGISTRY if fact in t.measures], []
                )

    def test_a_winning_attempt_mints_nothing_in_the_ledger(self):
        self.connect(PromptModel({BASE: 20, REWRITE: 34}))
        self.try_prompt(prompt=BASE)
        won = self.try_prompt(prompt=REWRITE)
        self.assertEqual(won["verdict"], "better")
        self.assertNotIn("measured_facts", won)
        stamped = [
            row
            for row in evidence.rows_for(self.thread)
            if row["tool"] in ("try_prompt", "read_prompt_bench")
        ]
        self.assertEqual(stamped, [])

    def test_neither_tool_accepts_a_reserved_argument(self):
        from app.tools.registry import RESERVED_ARGUMENTS

        for name in ("try_prompt", "read_prompt_bench"):
            properties = set(REGISTRY.get(name).schema["properties"])
            self.assertEqual(properties & RESERVED_ARGUMENTS, set())

    def test_there_is_no_argument_that_overrides_the_refusal(self):
        """A tool that refuses unless you ask it not to has not refused."""
        properties = set(REGISTRY.get("try_prompt").schema["properties"])
        for escape in ("force", "adopt", "adopt_anyway", "alpha", "p_value", "rerun"):
            self.assertNotIn(escape, properties)

    def test_an_attempt_needs_a_conversation_to_belong_to(self):
        refused = prompts.attempt(
            thread_id=None,
            line="classify",
            eval_path=str(self.path),
            input_field="q",
            expected_field="a",
            prompt=BASE,
        )
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["error"], "no_thread")

    def test_reading_the_bench_with_no_conversation_is_refused(self):
        refused = REGISTRY.call("read_prompt_bench", {}, actor=MODEL)
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["error"], "no_thread")


class APromptIsAVersionTest(PromptBenchTest):
    """Better than WHAT. The line, the version, the parent, the note."""

    def test_the_first_version_is_the_one_to_beat_because_it_is_first(self):
        self.connect(PromptModel({BASE: 20}))
        first = self.try_prompt(prompt=BASE, change_note="the prompt we started with")
        self.assertTrue(first["ok"], first.get("detail"))
        self.assertEqual(first["verdict"], "first")
        self.assertEqual(first["variant"]["version"], 1)
        self.assertIsNone(first["variant"]["parent_id"])
        self.assertTrue(first["champion_changed"])
        self.assertEqual(first["champion"]["basis"], "first")
        self.assertIn("nothing to beat", first["says"])
        # `basis='first'` claims nothing, and the table forbids it from claiming
        # anything: every comparison column is NULL.
        for column in ("p_value", "delta", "improved", "regressed", "paired_rows"):
            self.assertIsNone(first["champion"][column])

    def test_a_version_records_what_changed_and_what_scored_it(self):
        self.connect(PromptModel({BASE: 20, REWRITE: 34}))
        self.try_prompt(prompt=BASE, change_note="baseline")
        second = self.try_prompt(prompt=REWRITE, change_note="named the label set")
        self.assertEqual(second["variant"]["version"], 2)
        self.assertEqual(second["variant"]["change_note"], "named the label set")

        bench = REGISTRY.call(
            "read_prompt_bench", {"line": "classify"}, actor=MODEL,
            thread_id=self.thread,
        )
        versions = bench["versions"]
        self.assertEqual([v["version"] for v in versions], [1, 2])
        self.assertEqual(versions[1]["parent_id"], versions[0]["variant_id"])
        self.assertEqual(versions[0]["change_note"], "baseline")
        # The eval run each was scored by, which is the join that makes the
        # history checkable rather than remembered.
        for version in versions:
            self.assertIsNotNone(version["run_id"])
            stored = evals.read(version["run_id"], failures=0)
            self.assertEqual(stored["score"], version["score"])
            self.assertEqual(stored["prompt"], version["text"])

    def test_the_same_prompt_twice_is_refused_before_a_token_is_spent(self):
        model = self.connect(PromptModel({BASE: 20}))
        self.try_prompt(prompt=BASE)
        asked = len(model.asked)
        again = self.try_prompt(prompt=BASE, change_note="I forgot")
        self.assertFalse(again["ok"])
        self.assertEqual(again["error"], "nothing_changed")
        self.assertEqual(again["version"], 1)
        self.assertEqual(len(model.asked), asked, "it re-ran an identical prompt")

    def test_the_line_pins_the_instrument(self):
        """Two prompts graded by different metrics were never comparable, and
        unlike a changed eval FILE - which `evals.compare` catches by
        fingerprint - a changed METRIC produces two valid runs over the same
        fingerprint whose scores mean different things."""
        model = self.connect(PromptModel({BASE: 20, REWRITE: 34}))
        self.try_prompt(prompt=BASE)
        asked = len(model.asked)
        drifted = self.try_prompt(prompt=REWRITE, metric=evals.CONTAINS)
        self.assertFalse(drifted["ok"])
        self.assertEqual(drifted["error"], "different_instrument")
        self.assertIn("metric", drifted["mismatched"])
        self.assertEqual(len(model.asked), asked, "it spent tokens on a drift")

    def test_a_different_eval_file_on_the_same_line_is_refused(self):
        model = self.connect(PromptModel({BASE: 20, REWRITE: 34}))
        self.try_prompt(prompt=BASE)
        other = eval_file(self.root, rows=40, name="other.jsonl")
        asked = len(model.asked)
        drifted = self.try_prompt(prompt=REWRITE, eval_path=str(other))
        self.assertFalse(drifted["ok"])
        self.assertEqual(drifted["error"], "different_instrument")
        self.assertEqual(len(model.asked), asked)

    def test_a_run_that_did_not_finish_scores_nothing_and_crowns_nothing(self):
        """`evals`' rule, inherited: a score from a run that fell over is not a
        score. The version is kept and cannot be the one to beat."""
        self.connect(PromptModel({BASE: 20}))
        stopped = self.try_prompt(prompt=BASE, deadline_seconds=0)
        self.assertFalse(stopped["ok"])
        self.assertTrue(stopped["resumable"])
        self.assertFalse(stopped["complete"])
        self.assertEqual(stopped["verdict"], "incomplete")
        self.assertFalse(stopped["champion_changed"])
        self.assertIsNone(stopped["score"])
        self.assertIsNone(prompts.champion_of(stopped["line"]["id"]))
        self.assertEqual(len(prompts.variants_in(stopped["line"]["id"])), 1)

    def test_the_same_prompt_again_resumes_an_unfinished_version(self):
        """The duplicate refusal must not close the door the eval bench's own
        promise comes through: run this again with the same arguments and it
        continues."""
        self.connect(PromptModel({BASE: 20}))
        stopped = self.try_prompt(prompt=BASE, deadline_seconds=0)
        finished = self.try_prompt(prompt=BASE)
        self.assertTrue(finished["ok"], finished.get("detail"))
        self.assertTrue(finished["complete"])
        self.assertEqual(finished["run_id"], stopped["run_id"])
        self.assertEqual(finished["variant"]["id"], stopped["variant"]["id"])
        self.assertEqual(finished["verdict"], "first")
        self.assertEqual(len(prompts.variants_in(finished["line"]["id"])), 1)

    def test_a_line_with_no_prompt_and_no_history_is_refused(self):
        self.connect(PromptModel({BASE: 20}))
        refused = self.try_prompt()
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["error"], "no_prompt")


class TheRefusalIsThePointTest(PromptBenchTest):
    """Two prompts the eval set cannot tell apart are reported as the same.

    This is the class that makes the bench different from a prompt playground.
    """

    def test_a_five_point_gain_on_forty_rows_is_no_evidence(self):
        """50% then 55%: two rows changed out of forty. Every prompt playground
        on earth would call that an improvement."""
        self.connect(PromptModel({BASE: 20, REWRITE: 22}))
        self.try_prompt(prompt=BASE)
        attempt = self.try_prompt(prompt=REWRITE, change_note="tightened it")

        self.assertEqual(attempt["verdict"], "no_evidence")
        self.assertFalse(attempt["champion_changed"])
        self.assertIn("NO EVIDENCE", attempt["says"])
        self.assertAlmostEqual(attempt["paired"]["delta"], 0.05)
        self.assertEqual(attempt["comparison"]["improved"], 2)
        self.assertEqual(attempt["comparison"]["regressed"], 0)
        self.assertGreater(attempt["comparison"]["p_value"], prompts.RESOLUTION_ALPHA)
        # And the number of rows it would take is COMPUTED and reported.
        self.assertGreater(
            attempt["comparison"]["rows_that_would_resolve_this_delta"], 40
        )
        self.assertIn("more rows", attempt["says"])

    def test_the_one_to_beat_does_not_change_on_an_unresolved_gain(self):
        self.connect(PromptModel({BASE: 20, REWRITE: 22}))
        first = self.try_prompt(prompt=BASE)
        self.try_prompt(prompt=REWRITE)
        champion = prompts.champion_of(first["line"]["id"])
        self.assertEqual(champion["variant_id"], first["variant"]["id"])
        self.assertEqual(len(prompts.champions_of(first["line"]["id"])), 1)

    def test_a_resolved_gain_does_change_it_and_records_the_evidence(self):
        self.connect(PromptModel({BASE: 20, REWRITE: 34}))
        first = self.try_prompt(prompt=BASE)
        won = self.try_prompt(prompt=REWRITE, change_note="named the labels")
        self.assertEqual(won["verdict"], "better")
        self.assertTrue(won["champion_changed"])
        self.assertEqual(won["champion"]["basis"], "resolved")
        self.assertEqual(won["champion"]["beat_variant_id"], first["variant"]["id"])
        self.assertLessEqual(won["champion"]["p_value"], prompts.RESOLUTION_ALPHA)
        self.assertGreater(won["champion"]["improved"], won["champion"]["regressed"])
        self.assertIn("real difference", won["says"])

    def test_the_boundary_is_the_test_and_not_a_rule_of_thumb(self):
        """Five clean improvements out of forty rows do not resolve; six do. That
        is `CLEAN_SWEEP_ROWS`, and it is searched against `evals.mcnemar` rather
        than written down."""
        self.assertEqual(prompts.CLEAN_SWEEP_ROWS, 6)
        self.assertGreater(evals.mcnemar(5, 0), prompts.RESOLUTION_ALPHA)
        self.assertLessEqual(evals.mcnemar(6, 0), prompts.RESOLUTION_ALPHA)

        self.connect(PromptModel({BASE: 20, REWRITE: 25, WORSE: 26}))
        self.try_prompt(prompt=BASE)
        five = self.try_prompt(prompt=REWRITE)
        self.assertEqual(five["comparison"]["improved"], 5)
        self.assertEqual(five["verdict"], "no_evidence")
        six = self.try_prompt(prompt=WORSE)
        self.assertEqual(six["comparison"]["improved"], 6)
        self.assertEqual(six["verdict"], "better")

    def test_a_resolved_regression_is_a_finding_and_never_a_crowning(self):
        """McNemar is TWO-SIDED. A significant result is just as easily a
        significant regression, and `resolved` alone would crown one."""
        self.connect(PromptModel({BASE: 20, WORSE: 10}))
        first = self.try_prompt(prompt=BASE)
        worse = self.try_prompt(prompt=WORSE)
        self.assertTrue(worse["comparison"]["resolved"])
        self.assertEqual(worse["verdict"], "worse")
        self.assertFalse(worse["champion_changed"])
        self.assertIn("the wrong way", worse["says"])
        self.assertEqual(
            prompts.champion_of(first["line"]["id"])["variant_id"],
            first["variant"]["id"],
        )

    def test_the_badge_carries_the_resolution_beside_the_score(self):
        """`docs/PRODUCT_SPEC.md` §6.5: score after vs score before on n items,
        with the resolution. A score without its resolution is half a number."""
        self.connect(PromptModel({BASE: 20, REWRITE: 22}))
        self.try_prompt(prompt=BASE)
        attempt = self.try_prompt(prompt=REWRITE)
        self.assertRegex(attempt["says"], r"v2 \d+% vs v1 \d+% on 40 paired rows")
        self.assertRegex(attempt["says"], r"\+-\d+\.\d points at n=40")

    def test_a_no_evidence_attempt_is_still_recorded_as_a_version(self):
        """The refusal is about the CLAIM, not about the work. The rows are on
        disk and the attempt is in the history, which is what stops somebody
        making the same change twice."""
        self.connect(PromptModel({BASE: 20, REWRITE: 22}))
        first = self.try_prompt(prompt=BASE)
        attempt = self.try_prompt(prompt=REWRITE)
        bench = prompts.read_line(first["line"]["id"])
        self.assertEqual(len(bench["versions"]), 2)
        self.assertFalse(bench["versions"][1]["is_champion"])
        self.assertEqual(len(evals.results_for(attempt["run_id"])), 40)


class TheWallIsInTheTableTest(PromptBenchTest):
    """The refusal survives a code path that has never heard of it.

    `attempt` reads `resolved` off `evals.compare` and adds `improved >
    regressed`. That is control flow, and control flow is what the next author
    forgets. These tests go around it entirely.
    """

    def a_line_with_two_variants(self) -> tuple[int, int, int]:
        """Built once per test and cached, so a test may attempt several
        forbidden crownings against the same two real rows."""
        if getattr(self, "_line", None) is None:
            self.connect(PromptModel({BASE: 20, REWRITE: 22}))
            first = self.try_prompt(prompt=BASE)
            second = self.try_prompt(prompt=REWRITE)
            self._line = (
                first["line"]["id"],
                first["variant"]["id"],
                second["variant"]["id"],
            )
        return self._line

    def crowning(self, **columns):
        line, old, new = self.a_line_with_two_variants()
        row = {
            "line_id": line,
            "variant_id": new,
            "beat_variant_id": old,
            "basis": "resolved",
        }
        row.update(columns)
        names = sorted(row)
        with db.session() as connection:
            connection.execute(
                "INSERT INTO prompt_champions (%s) VALUES (%s)"
                % (", ".join(names), ", ".join("?" for _ in names)),
                tuple(row[name] for name in names),
            )

    def test_a_winner_with_a_p_value_above_alpha_cannot_be_written(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.crowning(paired_rows=40, improved=2, regressed=0, p_value=0.5)

    def test_a_winner_with_no_p_value_at_all_cannot_be_written(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.crowning(paired_rows=40, improved=2, regressed=0)

    def test_the_null_shaped_winner_cannot_be_written_either(self):
        """SQLite's CHECK fails only on FALSE and NULL PASSES, so `improved >
        regressed` on its own would admit a row with a NULL `improved`. That is
        precisely the row a careless INSERT writes, and it is why every column in
        the constraint is tested IS NOT NULL first."""
        with self.assertRaises(sqlite3.IntegrityError):
            self.crowning(paired_rows=40, improved=None, regressed=0, p_value=0.001)
        with self.assertRaises(sqlite3.IntegrityError):
            self.crowning(paired_rows=None, improved=9, regressed=0, p_value=0.001)

    def test_a_resolved_regression_cannot_be_written_as_a_win(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.crowning(paired_rows=40, improved=0, regressed=9, p_value=0.001)

    def test_a_win_over_nobody_cannot_be_written(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.crowning(
                beat_variant_id=None,
                paired_rows=40,
                improved=9,
                regressed=0,
                p_value=0.001,
            )

    def test_first_cannot_become_the_hole_by_claiming_a_delta(self):
        """A row exempt from justifying its figures must carry none."""
        with self.assertRaises(sqlite3.IntegrityError):
            self.crowning(basis="first", beat_variant_id=None, p_value=0.001)
        with self.assertRaises(sqlite3.IntegrityError):
            self.crowning(basis="first", beat_variant_id=None, delta=0.4)

    def test_an_invented_basis_cannot_be_written(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.crowning(basis="obviously_better")

    def test_a_real_winner_still_goes_in(self):
        """The constraint has to admit the honest row, or it is not a wall, it is
        a bricked-up door."""
        self.crowning(paired_rows=40, improved=9, regressed=0, p_value=0.001)

    def test_the_alpha_in_the_table_and_the_alpha_in_the_code_are_one_number(self):
        from app.migrations import v009_a_prompt_is_a_version as migration

        self.assertIn(
            f"p_value <= {prompts.RESOLUTION_ALPHA}", migration.SQL
        )
        self.assertEqual(migration.VERSION, 9)

    def test_the_code_never_makes_the_significance_decision_itself(self):
        """`attempt` reads `resolved` off `evals.compare`. If it re-tested, the
        two could drift; asserting the flag is what pins them together."""
        self.connect(PromptModel({BASE: 20, REWRITE: 34}))
        self.try_prompt(prompt=BASE)
        won = self.try_prompt(prompt=REWRITE)
        comparison = won["comparison"]
        self.assertEqual(
            comparison["resolved"],
            comparison["p_value"] <= prompts.RESOLUTION_ALPHA
            and comparison["changed"] > 0,
        )

    def test_nothing_in_the_product_updates_or_deletes_a_prompt_row(self):
        """Append-only, asserted over the source rather than trusted. The same
        discipline `app/migrations/v008_an_eval_keeps_its_rows.py` states for the
        eval tables."""
        root = Path(__file__).resolve().parents[1] / "app"
        crownings = 0
        for path in root.rglob("*.py"):
            body = path.read_text(encoding="utf-8")
            crownings += body.count("INSERT INTO prompt_champions")
            for forbidden in (
                "UPDATE prompt_lines",
                "UPDATE prompt_variants",
                "UPDATE prompt_scores",
                "UPDATE prompt_champions",
                "DELETE FROM prompt_lines",
                "DELETE FROM prompt_variants",
                "DELETE FROM prompt_scores",
                "DELETE FROM prompt_champions",
            ):
                self.assertNotIn(forbidden, body, f"{path.name} issues {forbidden}")
        self.assertEqual(
            crownings, 1, "a winner is recorded in exactly one place or in none"
        )


class TheBucketCannotResolveWhatItIsTooSmallToResolveTest(PromptBenchTest):
    """A change aimed at a named failure mode, and what that bucket can say.

    `docs/VISION.md` quotes the engine: *"Rewrite the system prompt against the
    failure buckets. Name the rule that was broken, explicitly."* Aiming is half
    of that. Checking the aim against the bucket is the other half, and the
    bucket has a resolution of its own.
    """

    def test_a_bucket_of_five_cannot_be_resolved_even_if_all_five_are_fixed(self):
        """A prompt playground would report "100% of your format failures fixed".
        Six is the smallest bucket a clean sweep of which reaches p<=0.05, and
        that number is searched against the same test that will judge it."""
        rows = [1, 4, 7, 10, 13]
        new_rows = {index: {"correct": True} for index in rows}
        effect = prompts.bucket_effect(rows, new_rows, "wrong_format")
        self.assertEqual(effect["fixed"], 5)
        self.assertFalse(effect["resolved"])
        self.assertIn("NO EVIDENCE", effect["says"])
        self.assertGreater(
            effect["p_value_if_every_row_were_fixed"], prompts.RESOLUTION_ALPHA
        )
        self.assertEqual(
            effect["rows_a_clean_sweep_needs_to_resolve"], prompts.CLEAN_SWEEP_ROWS
        )

    def test_a_bucket_of_six_swept_clean_does_resolve(self):
        rows = [1, 4, 7, 10, 13, 16]
        effect = prompts.bucket_effect(
            rows, {index: {"correct": True} for index in rows}, "wrong_format"
        )
        self.assertTrue(effect["resolved"])
        self.assertLessEqual(effect["p_value"], prompts.RESOLUTION_ALPHA)

    def test_a_targeted_change_reports_that_bucket_and_not_only_the_total(self):
        self.connect(PromptModel({BASE: 20, REWRITE: 34}))
        self.try_prompt(prompt=BASE)
        aimed = self.try_prompt(prompt=REWRITE, targets="wrong_format")
        self.assertEqual(aimed["variant"]["targets"], "wrong_format")
        self.assertEqual(aimed["targeted"]["mode"], "wrong_format")
        self.assertGreater(aimed["targeted"]["rows"], 0)
        self.assertIn("wrong_format", aimed["says"])
        # Every bucket of the run being beaten is reported, not only the target.
        self.assertEqual(
            sorted(aimed["bucket_effects"]["buckets"]),
            ["refuses", "wrong_facts", "wrong_format"],
        )

    def test_collateral_damage_is_reported_beside_the_bucket_that_improved(self):
        """An aggregate can sit still while a change fixes every format failure
        and breaks an equal number of factual ones. Those are opposite findings
        and a bench that reported only the total would show neither."""
        self.connect(PromptModel({BASE: 30, REWRITE: 20}))
        self.try_prompt(prompt=BASE)
        broke = self.try_prompt(prompt=REWRITE, targets="refuses")
        self.assertGreater(broke["bucket_effects"]["collateral_rows"], 0)
        self.assertIn("broke", broke["says"])
        self.assertIn("correct before", broke["says"])
        # Grouped by how they fail NOW, which is the half that says what to do.
        self.assertTrue(
            set(broke["bucket_effects"]["collateral"])
            <= set(evals.routable_modes()) | {evals.UNCLASSIFIED, "?"}
        )

    def test_inconsistent_can_never_be_aimed_at_and_says_why(self):
        """It is a property of two rows rather than one, so the eval bench
        derives it at report time and never stores it against a row. There is no
        bucket of rows to measure a change against."""
        self.connect(PromptModel({BASE: 20}))
        self.assertIn("inconsistent", evals.routable_modes())
        refused = self.try_prompt(prompt=BASE, targets="inconsistent")
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["error"], "not_a_row_local_mode")
        self.assertNotIn("inconsistent", refused["modes"])

    def test_a_failure_mode_the_engine_never_heard_of_is_refused(self):
        self.connect(PromptModel({BASE: 20}))
        refused = self.try_prompt(prompt=BASE, targets="vibes")
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["error"], "unknown_failure_mode")
        self.assertIn("wrong_format", refused["modes"])

    def test_the_modes_come_from_the_engine_and_not_from_a_list_here(self):
        self.connect(PromptModel({BASE: 20}))
        refused = self.try_prompt(prompt=BASE, targets="vibes")
        self.assertEqual(
            sorted(refused["modes"]),
            sorted(
                (set(evals.routable_modes()) | {evals.UNCLASSIFIED})
                - set(prompts.NOT_A_ROW_LOCAL_MODE)
            ),
        )


class FewShotComesFromTheFailuresTest(PromptBenchTest):
    """Exemplars from the rows the model got wrong, held out by construction."""

    def test_exemplars_are_failing_rows_and_never_successful_ones(self):
        self.connect(PromptModel({BASE: 20}))
        first = self.try_prompt(prompt=BASE)
        run = first["run_id"]
        chosen = prompts.choose_exemplars(run, 6)
        failing = {
            row["row_index"]
            for row in evals.results_for(run)
            if row["failure_mode"]
        }
        self.assertEqual(len(chosen["exemplars"]), 6)
        for item in chosen["exemplars"]:
            self.assertIn(item["row_index"], failing)

    def test_the_choice_is_spread_across_buckets_rather_than_one_of_them(self):
        self.connect(PromptModel({BASE: 20}))
        first = self.try_prompt(prompt=BASE)
        chosen = prompts.choose_exemplars(first["run_id"], 6)
        modes = {item["failure_mode"] for item in chosen["exemplars"]}
        self.assertEqual(modes, {"refuses", "wrong_facts", "wrong_format"})

    def test_a_target_draws_from_that_bucket_deliberately(self):
        self.connect(PromptModel({BASE: 20}))
        first = self.try_prompt(prompt=BASE)
        chosen = prompts.choose_exemplars(first["run_id"], 4, mode="refuses")
        self.assertEqual(
            {item["failure_mode"] for item in chosen["exemplars"]}, {"refuses"}
        )

    def test_the_exemplar_carries_the_right_answer_and_not_the_wrong_one(self):
        self.connect(PromptModel({BASE: 20}))
        first = self.try_prompt(prompt=BASE)
        chosen = prompts.choose_exemplars(first["run_id"], 3)
        rows = {row["row_index"]: row for row in evals.results_for(first["run_id"])}
        for item in chosen["exemplars"]:
            row = rows[item["row_index"]]
            self.assertEqual(item["expected"], row["expected"])
            self.assertNotEqual(item["expected"], row["answer"])

    def test_the_exemplar_rows_leave_the_score_by_construction(self):
        """Scoring a prompt on the rows it was handed as examples is a leak, and
        this product exists to catch leaks."""
        self.connect(
            PromptModel({prompts.EXEMPLAR_PREAMBLE: 32, BASE: 20})
        )
        first = self.try_prompt(prompt=BASE)
        shot = self.try_prompt(fewshot_from_failures=6, change_note="six examples")

        held = set(shot["variant"]["exemplars"])
        self.assertEqual(held, {20, 21, 22, 23, 24, 25})
        graded = {row["row_index"] for row in evals.results_for(shot["run_id"])}
        self.assertEqual(held & graded, set(), "an exemplar row was scored on")
        self.assertEqual(len(graded), 34)
        for row in held:
            self.assertIn(row, set(shot["paired"]["only_the_other_graded"]))

    def test_the_paired_delta_is_now_the_only_delta_when_rows_were_held_out(self):
        """REWRITTEN. This test used to assert the defect.

        It read `assertNotAlmostEqual(comparison["delta"], paired["delta"])` -
        pinning `evals.compare`'s headline as the difference of two AGGREGATE
        scores, which is right when both runs graded the same rows and
        misleading the moment they did not. Few-shot is exactly that moment, and
        this module's own `paired()` docstring said so; the correction was never
        applied to `compare`, which is what `read_eval_results` and the
        comparison card show directly. It is applied now, so `compare`'s delta
        and this module's paired delta are the SAME number by construction, and
        asserting they differ was asserting the bug.

        What replaces it is stronger rather than looser: all three deltas are
        pinned to exact values, and the aggregate difference - still reported,
        under `aggregate`, because it is a real fact about two runs - is pinned
        to the value it has and named as not being the difference between them.
        See `tests/test_the_headline_delta_is_measured_on_the_paired_rows.py`.
        """
        self.connect(PromptModel({prompts.EXEMPLAR_PREAMBLE: 32, BASE: 20}))
        self.try_prompt(prompt=BASE)
        shot = self.try_prompt(fewshot_from_failures=6)

        self.assertEqual(shot["paired"]["rows"], 34)
        self.assertAlmostEqual(shot["paired"]["score_against"], 20 / 34)
        self.assertAlmostEqual(shot["paired"]["score"], 26 / 34)
        self.assertAlmostEqual(shot["paired"]["delta"], 6 / 34)
        self.assertAlmostEqual(shot["comparison"]["delta"], 6 / 34)
        self.assertAlmostEqual(
            shot["comparison"]["delta"], shot["paired"]["delta"], places=12
        )
        self.assertEqual(shot["verdict"], "better")
        self.assertAlmostEqual(shot["champion"]["delta"], 6 / 34)

        # The misleading half, kept and labelled. The champion scored 20 of its
        # own 40 rows; the challenger 26 of its own 34, six of the champion's
        # failures having been taken out as exemplars. Subtracting those two is
        # +26.5 points where the honest paired difference is +17.6.
        aggregate = shot["comparison"]["aggregate"]
        self.assertFalse(shot["comparison"]["same_rows"])
        self.assertAlmostEqual(aggregate["score_against"], 20 / 40)
        self.assertAlmostEqual(aggregate["score"], 26 / 34)
        self.assertAlmostEqual(aggregate["difference"], 26 / 34 - 20 / 40)
        self.assertGreater(aggregate["difference"], shot["comparison"]["delta"])
        self.assertEqual(aggregate["only_the_other_graded_count"], 6)

    def test_what_was_asked_for_and_what_was_found_are_reported_separately(self):
        """A request for twenty exemplars answered with seven is a finding about
        how few failures there are, and reporting the seven as the request hides
        it."""
        self.connect(PromptModel({prompts.EXEMPLAR_PREAMBLE: 32, BASE: 20}))
        self.try_prompt(prompt=BASE)
        shot = self.try_prompt(fewshot_from_failures=20, targets="refuses")
        self.assertEqual(shot["fewshot"]["requested"], 20)
        self.assertEqual(shot["fewshot"]["chosen_count"], 7)
        self.assertEqual(len(shot["variant"]["exemplars"]), 7)

    def test_the_aggregate_delta_is_named_as_the_wrong_number_to_read(self):
        """Both numbers are shown, so the badge has to say which one means what
        or a reader is left to reconcile two different figures."""
        self.connect(PromptModel({prompts.EXEMPLAR_PREAMBLE: 32, BASE: 20}))
        self.try_prompt(prompt=BASE)
        shot = self.try_prompt(fewshot_from_failures=6)
        self.assertIn("NOT the number to read", shot["says"])
        self.assertIn("rows both runs graded", shot["says"])

    def test_the_exemplars_are_in_the_stored_prompt_that_actually_ran(self):
        self.connect(PromptModel({prompts.EXEMPLAR_PREAMBLE: 32, BASE: 20}))
        self.try_prompt(prompt=BASE)
        shot = self.try_prompt(fewshot_from_failures=6)
        text = shot["variant"]["text"]
        self.assertIn(prompts.EXEMPLAR_PREAMBLE, text)
        self.assertIn(BASE, text)
        self.assertIn("Input: q20", text)
        self.assertIn("Correct answer: always", text)
        stored = evals.read(shot["run_id"], failures=0)
        self.assertEqual(stored["prompt"], text)

    def test_a_truncated_row_is_not_an_exemplar_and_the_skip_is_counted(self):
        """`evals` stores at most `STORED_TEXT_CHARS` per field. A cut-off
        expected answer teaches the cut-off answer."""
        path = Path(self.root) / "long.jsonl"
        rows = [{"q": f"q{i}", "a": LABELS[i % 5]} for i in range(40)]
        rows[21] = {"q": "q21 " + ("x" * (evals.STORED_TEXT_CHARS + 100)), "a": "no"}
        path.write_text(
            "\n".join(json.dumps(row) for row in rows), encoding="utf-8"
        )
        self.connect(PromptModel({BASE: 20}))
        first = self.try_prompt(prompt=BASE, line="long", eval_path=str(path))
        chosen = prompts.choose_exemplars(first["run_id"], 20)
        self.assertEqual(chosen["skipped_truncated"], 1)
        self.assertNotIn(
            21, {item["row_index"] for item in chosen["exemplars"]}
        )

    def test_the_truncation_marker_is_still_the_one_the_eval_bench_writes(self):
        """Pinned deliberately: `evals._clip` is private, so this suite goes red
        if it changes rather than the bench quietly shipping truncated
        exemplars."""
        clipped = evals._clip("y" * (evals.STORED_TEXT_CHARS + 10))
        self.assertIn(prompts.TRUNCATION_MARKER, clipped)

    def test_few_shot_with_nothing_to_learn_from_is_refused(self):
        self.connect(PromptModel({BASE: 20}))
        refused = self.try_prompt(fewshot_from_failures=6)
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["error"], "no_failures_to_learn_from")

    def test_a_shortfall_against_the_engines_five_is_reported_not_hidden(self):
        self.connect(PromptModel({prompts.EXEMPLAR_PREAMBLE: 32, BASE: 20}))
        self.try_prompt(prompt=BASE)
        shot = self.try_prompt(fewshot_from_failures=3)
        self.assertEqual(shot["fewshot"]["engine_asks_for"], 5)
        self.assertIn("5-20 exemplars", shot["fewshot"]["note"])

    def test_the_exemplar_count_is_capped_rather_than_trusted(self):
        self.connect(PromptModel({prompts.EXEMPLAR_PREAMBLE: 40, BASE: 20}))
        self.try_prompt(prompt=BASE)
        shot = self.try_prompt(fewshot_from_failures=500)
        self.assertLessEqual(len(shot["variant"]["exemplars"]), prompts.MAX_EXEMPLARS)


class ADifferentModelIsNotAPromptChangeTest(PromptBenchTest):
    """The refusal `evals.compare` does not make, because it is not its question.

    `compare` checks the eval set and not the connection - correctly, because
    "did swapping the model help" is a legitimate thing to ask of two runs. It is
    not what a PROMPT bench is asking, and a prompt that scores better because
    the connection changed underneath it is the easiest way to believe a prompt
    change worked.
    """

    def test_two_variants_scored_by_different_models_are_not_compared(self):
        self.connect(PromptModel({BASE: 20, REWRITE: 34}))
        self.try_prompt(prompt=BASE)
        self.reconnect("Scripted two", "scripted-large")
        swapped = self.try_prompt(prompt=REWRITE)
        self.assertEqual(swapped["verdict"], "different_models")
        self.assertFalse(swapped["champion_changed"])
        self.assertIn("two different models", swapped["says"])
        self.assertNotIn("comparison", swapped)

    def test_the_version_is_still_kept_when_the_model_moved(self):
        self.connect(PromptModel({BASE: 20, REWRITE: 34}))
        first = self.try_prompt(prompt=BASE)
        self.reconnect("Scripted two", "scripted-large")
        swapped = self.try_prompt(prompt=REWRITE)
        bench = prompts.read_line(first["line"]["id"])
        self.assertEqual(len(bench["versions"]), 2)
        self.assertEqual(bench["versions"][1]["model"], "scripted-large")
        self.assertEqual(swapped["against"]["model"], "scripted")


class ABenchBelongsToOneConversationTest(PromptBenchTest):
    """Thread scoping, both directions, for `v006`/`v007`'s reason."""

    def test_a_line_in_another_conversation_cannot_be_read(self):
        self.connect(PromptModel({BASE: 20}))
        mine = self.try_prompt(prompt=BASE)
        refused = REGISTRY.call(
            "read_prompt_bench",
            {"line_id": mine["line"]["id"]},
            actor=MODEL,
            thread_id=self.other,
        )
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["error"], "no_such_line")

    def test_a_line_name_is_free_in_a_second_conversation(self):
        self.connect(PromptModel({BASE: 20}))
        mine = self.try_prompt(prompt=BASE)
        theirs = self.try_prompt(prompt=BASE, thread=self.other)
        self.assertTrue(theirs["ok"], theirs.get("detail"))
        self.assertNotEqual(theirs["line"]["id"], mine["line"]["id"])
        self.assertEqual(theirs["verdict"], "first")

    def test_listing_shows_only_this_conversations_lines(self):
        self.connect(PromptModel({BASE: 20}))
        self.try_prompt(prompt=BASE)
        listed = REGISTRY.call(
            "read_prompt_bench", {}, actor=MODEL, thread_id=self.other
        )
        self.assertEqual(listed["count"], 0)
        listed = REGISTRY.call(
            "read_prompt_bench", {}, actor=MODEL, thread_id=self.thread
        )
        self.assertEqual([row["name"] for row in listed["lines"]], ["classify"])

    def test_an_attempt_narrates_onto_the_event_spine(self):
        self.connect(PromptModel({BASE: 20, REWRITE: 22}))
        self.try_prompt(prompt=BASE)
        self.try_prompt(prompt=REWRITE)
        kinds = [
            row["kind"]
            for row in events.since(f"thread:{self.thread}")
            if row["kind"].startswith("prompt.")
        ]
        self.assertEqual(kinds, [prompts.ADOPTED, prompts.NO_EVIDENCE])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
