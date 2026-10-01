"""A dataset can be invented - and every invented row says who wrote it.

`app/tools/invent.py`: a generator writes rows for a task from the person's
seeds; a judge scores them against the person's rubric; pairs feed DPO. No
model is called here - a scripted provider stands in - so every case is about
the tagging, the deduplication, the refusals, the files, and the gates that
stay shut.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import support  # noqa: E402
from app.providers import Delta  # noqa: E402
from app.tools import invent  # noqa: E402
from app.tools.registry import REGISTRY  # noqa: E402


class _Scripted:
    """Answers each request with the next script; remembers what it was asked."""

    def __init__(self, scripts):
        self.scripts = list(scripts)
        self.asked: list[list[dict]] = []

    def stream(self, messages, tools=None, *, secret=None):
        self.asked.append([dict(m) for m in messages])
        text = self.scripts.pop(0) if self.scripts else ""
        if text == "<error>":
            yield Delta(kind="error", detail="the model is gone")
            return
        yield Delta(kind="text", text=text)
        yield Delta(kind="end")


def rows(n: int, start: int = 0) -> str:
    return "\n".join(
        json.dumps({"prompt": f"What is item {i}?", "answer": f"Item {i} is the {i}th thing."})
        for i in range(start, start + n)
    )


class _Invented(unittest.TestCase):
    def setUp(self) -> None:
        self.root = support.sandbox(self)
        self.original_build = invent.build
        self.original_active = invent.store.active
        invent.store.active = lambda: {"id": 1, "adapter": "ollama", "base_url": "http://127.0.0.1:11434", "model": "fake-gen"}
        self.addCleanup(setattr, invent, "build", self.original_build)
        self.addCleanup(setattr, invent.store, "active", self.original_active)

    def install(self, scripts) -> _Scripted:
        provider = _Scripted(scripts)
        invent.build = lambda *a, **k: provider
        return provider

    def seeds(self) -> Path:
        path = self.root / "seeds.jsonl"
        path.write_text(
            "\n".join(
                json.dumps({"q": f"seed question {i}", "a": f"seed answer {i}"}) for i in range(5)
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    def read(self, path) -> list[dict]:
        return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


class GenerateRowsTest(_Invented):
    def test_rows_are_written_tagged_with_who_wrote_them(self):
        self.install([rows(10), rows(10, 10)])
        out = invent.generate_rows("teach the model to name items", str(self.root / "gen"), count=20, path=str(self.seeds()), prompt_column="q", answer_column="a")
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["rows_written"], 20)
        written = self.read(out["generated_path"])
        self.assertEqual(len(written), 20)
        for r in written:
            self.assertTrue(r["generated"] and r["synthetic"])
            self.assertEqual(r["origin"], "generated")
            self.assertEqual(r["generator"], "fake-gen")
            self.assertIn("teach the model", r["task"])
            self.assertTrue(r["seed_prompts"])
        manifest = json.loads(Path(out["manifest_path"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest["operation"], "generate")
        self.assertIn("does_not_open_g0", manifest)

    def test_the_generator_is_shown_seeds_and_the_task(self):
        provider = self.install([rows(10)])
        invent.generate_rows("teach the model to name items", str(self.root / "gen"), count=5, path=str(self.seeds()), prompt_column="q", answer_column="a")
        system, user = provider.asked[0][0]["content"], provider.asked[0][1]["content"]
        self.assertIn("teach the model to name items", system)
        self.assertIn("seed question", user)
        self.assertIn("Write 5 new rows", user)

    def test_a_prompt_that_copies_a_seed_or_repeats_itself_is_dropped(self):
        copied = json.dumps({"prompt": "seed question 1", "answer": "x"})
        twice = json.dumps({"prompt": "Fresh one?", "answer": "y"})
        self.install([copied + "\n" + twice + "\n" + twice, rows(3, 100)])
        out = invent.generate_rows("teach the model to name items", str(self.root / "gen"), count=4, path=str(self.seeds()), prompt_column="q", answer_column="a")
        self.assertEqual(out["duplicates_dropped"], 2)
        prompts = [r["prompt"] for r in self.read(out["generated_path"])]
        self.assertEqual(len(prompts), len(set(prompts)))
        self.assertNotIn("seed question 1", prompts)

    def test_two_answers_per_prompt_share_a_group(self):
        two = "\n".join(json.dumps({"prompt": f"P{i}", "answer_a": "good", "answer_b": "worse"}) for i in range(3))
        self.install([two])
        out = invent.generate_rows("teach the model to name items", str(self.root / "gen"), count=6, answers_per_prompt=2)
        self.assertEqual(out["rows_written"], 6)
        written = self.read(out["generated_path"])
        groups = {}
        for r in written:
            groups.setdefault(r["group_id"], []).append(r["variant"])
        self.assertEqual(len(groups), 3)
        self.assertTrue(all(sorted(v) == [0, 1] for v in groups.values()))

    def test_no_seeds_is_allowed_a_fenced_array_is_read_and_junk_is_counted(self):
        fenced = "```json\n[" + ",".join(json.dumps({"prompt": f"Q{i}", "answer": "A"}) for i in range(3)) + "]\n```"
        self.install(["I cannot do that.", fenced])
        out = invent.generate_rows("teach the model to name items", str(self.root / "gen"), count=3)
        self.assertEqual(out["rows_written"], 3)
        self.assertEqual(out["unparseable_replies"], 1)
        self.assertEqual(self.read(out["generated_path"])[0]["seed_prompts"], [])

    def test_refusals_say_why_and_write_nothing(self):
        self.install([rows(3)])
        self.assertEqual(invent.generate_rows("x", str(self.root / "gen"))["error"], "no_task")
        self.assertEqual(
            invent.generate_rows("teach the model to name items", str(self.root / "gen"), path=str(self.seeds()))["error"],
            "no_columns",
        )
        invent.store.active = lambda: None
        self.assertEqual(invent.generate_rows("teach the model to name items", str(self.root / "gen"))["error"], "no_model_connected")
        self.assertFalse((self.root / "gen").exists())

    def test_a_dead_generator_is_a_report_not_a_crash(self):
        self.install(["<error>", "<error>", "<error>"])
        out = invent.generate_rows("teach the model to name items", str(self.root / "gen"), count=5)
        self.assertFalse(out["ok"])
        self.assertEqual(out["rows_written"], 0)
        self.assertEqual(len(out["errors"]), 3)

    def test_it_cannot_open_a_gate(self):
        spec = REGISTRY.get("generate_rows")
        self.assertEqual(spec.measures, ())
        self.assertEqual(spec.approval, "always")
        self.assertIn("data.synthetic.generate", spec.provides)

    def test_wall_8_refuses_to_count_an_invented_file_as_an_eval_set(self):
        """The amplifier's wall, applied to the inventor's rows without a
        change: every generated row carries `synthetic: true`, and a fact
        measured off a file holding such rows is refused at the stamp."""
        from app import events
        from app.tools import evidence

        self.install([rows(10)])
        out = invent.generate_rows("teach the model to name items", str(self.root / "gen"), count=10)
        thread = events.create_thread("t")["id"]
        counted = REGISTRY.call(
            "measure_eval_set", {"path": out["generated_path"]},
            approved=True, actor=evidence.MODEL, thread_id=thread,
        )
        self.assertFalse(counted.get("ok"), counted)
        self.assertIn("generated", json.dumps(counted).lower())


class JudgeRowsTest(_Invented):
    def generated(self, pairs: bool = False) -> Path:
        path = self.root / "generated.jsonl"
        lines = []
        for i in range(4):
            if pairs:
                for variant, answer in enumerate(("a fine answer", "a weak answer")):
                    lines.append(json.dumps({"prompt": f"Q{i}", "answer": answer, "generated": True, "synthetic": True, "group_id": f"g{i}", "variant": variant}))
            else:
                lines.append(json.dumps({"prompt": f"Q{i}", "answer": f"A{i}", "generated": True, "synthetic": True, "group_id": f"g{i}"}))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def test_scores_are_written_on_the_row_with_the_judge_and_kept_above_the_bar(self):
        self.install(['{"score": 9, "reason": "clear"}', '{"score": 3, "reason": "vague"}', 'score: 8', "no number here"])
        out = invent.judge_rows(str(self.generated()), "a good answer names the item and its place", str(self.root / "judged"), threshold=7)
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["rows_judged"], 2, "the bare 'score: 8' and the wordless reply are not JSON scores")
        self.assertEqual(out["rows_unscored"], 2)
        self.assertEqual(out["rows_kept"], 1)
        judged = self.read(out["judged_path"])
        self.assertEqual(judged[0]["judge_score"], 9)
        self.assertEqual(judged[0]["judge_model"], "fake-gen")
        self.assertEqual(judged[0]["judge_reason"], "clear")
        self.assertIsNone(judged[3]["judge_score"])
        self.assertEqual([r["prompt"] for r in self.read(out["kept_path"])], ["Q0"])

    def test_two_answers_to_one_prompt_become_a_chosen_rejected_pair(self):
        scripts = []
        for _ in range(4):
            scripts += ['{"score": 9, "reason": "good"}', '{"score": 2, "reason": "weak"}']
        self.install(scripts)
        out = invent.judge_rows(str(self.generated(pairs=True)), "a good answer is fine", str(self.root / "judged"))
        self.assertEqual(out["pairs_written"], 4)
        pair = self.read(out["pairs_path"])[0]
        self.assertEqual(pair["chosen"], "a fine answer")
        self.assertEqual(pair["rejected"], "a weak answer")
        self.assertGreater(pair["chosen_score"], pair["rejected_score"])
        self.assertTrue(pair["synthetic"])

    def test_a_tie_is_not_a_pair(self):
        self.install(['{"score": 5}'] * 8)
        out = invent.judge_rows(str(self.generated(pairs=True)), "a good answer is fine", str(self.root / "judged"))
        self.assertEqual(out["pairs_written"], 0)

    def test_the_judge_is_given_the_rubric_and_the_row(self):
        provider = self.install(['{"score": 7, "reason": "ok"}'] * 4)
        invent.judge_rows(str(self.generated()), "a good answer names the item and its place", str(self.root / "judged"))
        self.assertIn("names the item and its place", provider.asked[0][0]["content"])
        self.assertIn("PROMPT:\nQ0", provider.asked[0][1]["content"])

    def test_refusals(self):
        self.install([])
        self.assertEqual(invent.judge_rows(str(self.generated()), "x", str(self.root / "j"))["error"], "no_rubric")
        empty = self.root / "empty.jsonl"
        empty.write_text(json.dumps({"other": 1}) + "\n", encoding="utf-8")
        self.assertEqual(invent.judge_rows(str(empty), "a good answer is fine", str(self.root / "j"))["error"], "no_prompt_answer_rows")

    def test_it_cannot_open_a_gate(self):
        spec = REGISTRY.get("judge_rows")
        self.assertEqual(spec.measures, ())
        self.assertIn("data.synthetic.judge", spec.provides)


if __name__ == "__main__":
    unittest.main()
