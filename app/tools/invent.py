"""Invent a dataset: a generator writes rows, a judge scores them, pairs feed DPO.

## What this was written from

Max, 2026-09-12: *"does our harness have invent a dataset yet? how does
[Adaptive ML] have that feature, what's the backbone of that and how can we
leverage that in our system... lets create our own invent a dataset tools that
we can work and experiment with."*

Adaptive Engine's loop, as its own page describes it: *"Generate synthetic
data. Fine-tune with reinforcement learning"*, judged by *"bespoke AI judges"*,
validated by A/B, with production signals fed back. The backbone of every
system of that shape is three models and one loop: a GENERATOR writes prompts
and completions from seeds and a task; a JUDGE scores them against a rubric,
and that score is the filter for SFT and the reward for RL; a STUDENT is tuned
on what the judge kept and measured by the same judge.

This module is the first two thirds, in this product's idiom. The third - the
student - is what `hf-peft-lora` and `hf-peft-dpo` already do.

## What is kept from the product's own rules, and it is most of the design

* **Every row says where it came from.** `generated: true`, the generator's
  model name, the seed rows it was shown, the task it was asked - on the row,
  forever, the way `synthesize_rows` tags its samples. A row that cannot say
  who wrote it is a row nobody can vouch for.
* **Never the eval set.** A generated file cannot open G0 - `measures=()`, no
  instrument - and the manifest says so in the words `synthesize_rows` uses.
  The eval set is carved from what the person HAS; a model grading its own
  invented questions is a closed loop.
* **The judge's score is a reading.** It is written on the row as
  `judge_score` with `judge_model` and the rubric's fingerprint, so a later
  reader can tell a judged row from a row somebody typed a number onto.
* **The 10% a person reads stays.** `draw_verification_sample` and
  `record_verification` read `synthetic: true`, which every generated row also
  carries, so the gate the ledger writes into `BLOCKED__COLLECT_OR_SYNTHESIZE_DATA`
  applies unchanged.
* **Nothing is written over.** `into` is a NEW directory, claimed with the
  same `_claim` the amplifier uses.
* **And the claim is measured, never assumed.** Phase 2 measured that 200
  RESAMPLED rows bought nothing (adapter 0/30 against a 23% base). Generated
  rows earn their place the same way - by beating the baseline on the same
  held-out eval set - or the harness says NO EVIDENCE.

## What it does not do yet

Reinforcement learning. `judge_rows` writes `pairs.jsonl` - chosen and
rejected completions of one prompt, by judge score - which is rejection
sampling into preference data, the practical core of the RL loop Adaptive
sells, and `hf-peft-dpo` trains on it. A GRPO recipe is a later recipe.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from app import db, events
from app.providers import Delta, build, secrets, store
from app.tools import datawork
from app.tools.registry import tool

#: Rows one call may write. Enough to experiment with, small enough that a
#: mistaken task does not fill a disk with it.
MAX_GENERATED = 500
DEFAULT_GENERATED = 40
#: Rows asked of the generator per request. Ten keeps a small model's reply
#: parseable; forty in one reply is where a 4B starts to drift.
PER_REQUEST = 10
#: Seed rows shown per request as examples of the shape.
SEEDS_SHOWN = 3
#: The judge's scale and the default bar.
JUDGE_SCALE = 10
DEFAULT_THRESHOLD = 7
MAX_JUDGED = 2000

GENERATED_FILE = "generated.jsonl"
JUDGED_FILE = "judged.jsonl"
KEPT_FILE = "kept.jsonl"
PAIRS_FILE = "pairs.jsonl"

_JSON_LINE = re.compile(r"\{.*?\}(?=\s*(?:\{|$))", re.DOTALL)
_SCORE = re.compile(r'"score"\s*:\s*(\d+(?:\.\d+)?)')
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


# ---------------------------------------------------------------------------
# The connection
# ---------------------------------------------------------------------------


def _connected() -> tuple[Any, str | None, dict[str, Any]]:
    """The active model as an adapter, or a refusal a caller can return."""
    row = store.active()
    if row is None:
        raise datawork._refuse(
            "no_model_connected",
            "No model is connected, so nothing could generate or judge. Connect "
            "one on this machine or an API key, then call again.",
        )
    adapter = build(row["adapter"], row["base_url"], row["model"])
    key = secrets.get_key(str(row["id"]))
    return adapter, key, dict(row)


def _ask(adapter: Any, key: str | None, system: str, user: str) -> tuple[str, str | None]:
    """One reply as text, or `("", error)`. Never raises: a dead endpoint is a report."""
    parts: list[str] = []
    try:
        for delta in adapter.stream(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            None,
            secret=key,
        ):
            if not isinstance(delta, Delta):
                continue
            if delta.kind == "text" and delta.text:
                parts.append(delta.text)
            elif delta.kind == "error":
                return "", delta.detail or "the model returned an error"
    except Exception as error:  # noqa: BLE001 - a dead endpoint is a report
        return "", f"{type(error).__name__}: {error}"
    return "".join(parts).strip(), None


def _objects(text: str) -> list[dict[str, Any]]:
    """Every JSON object in a reply - fenced, as an array, or one per line."""
    body = text
    fenced = _FENCE.findall(text)
    if fenced:
        body = "\n".join(fenced)
    out: list[dict[str, Any]] = []
    stripped = body.strip()
    if stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                return [p for p in parsed if isinstance(p, dict)]
        except json.JSONDecodeError:
            pass
    for line in body.splitlines():
        line = line.strip().rstrip(",")
        if line.startswith("{") and line.endswith("}"):
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                out.append(parsed)
    if out:
        return out
    for match in _JSON_LINE.findall(body):
        try:
            parsed = json.loads(match)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            out.append(parsed)
    return out


def _norm(text: Any) -> str:
    return " ".join(str(text or "").lower().split())


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# generate_rows
# ---------------------------------------------------------------------------

_GENERATOR_SYSTEM = (
    "You write training rows for a small model. The task the rows must teach:\n"
    "{task}\n\n"
    "Reply with JSON lines only - one object per line, nothing before or after. "
    "{shape} Every prompt must be distinct from the examples and from each other, "
    "and every answer must be correct and complete for its prompt. Do not copy an "
    "example. Do not number the lines. Do not explain."
)
_SHAPE_ONE = 'Each object has exactly two fields: "prompt" and "answer".'
_SHAPE_TWO = (
    'Each object has exactly three fields: "prompt", "answer_a" and "answer_b" - '
    "two different complete answers to the same prompt, one deliberately better "
    "than the other."
)


def _seed_examples(seeds: list[dict[str, str]], salt: str, k: int) -> list[dict[str, str]]:
    if not seeds:
        return []
    picked = []
    for i in range(min(k, len(seeds))):
        digest = hashlib.sha256(f"{salt}|{i}".encode()).hexdigest()
        picked.append(seeds[int(digest, 16) % len(seeds)])
    return picked


@tool(
    "generate_rows",
    description=(
        "Invent new training rows: a connected model writes prompt/answer rows "
        "for a task you describe, shown a few of your own rows as the shape. "
        "Every row is tagged generated with the model and the seeds it saw. "
        "Never an eval set - judge_rows scores them, draw_verification_sample "
        "is the 10% a person reads, and only a held-out file measured by "
        "measure_eval_set can open a gate."
    ),
    schema={
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "What the rows must teach, in a sentence or two. The generator is given this verbatim.",
            },
            "into": {
                "type": "string",
                "description": "A directory for generated.jsonl and its manifest. Nothing is written over: if it exists, the next free name beside it is used and returned as `into`.",
            },
            "count": {"type": "integer", "description": f"Rows to write, 1-{MAX_GENERATED}. Default {DEFAULT_GENERATED}."},
            "path": {"type": "string", "description": "Optional: your own rows, shown as examples of the shape."},
            "prompt_column": {"type": "string", "description": "With path: the column holding the prompt."},
            "answer_column": {"type": "string", "description": "With path: the column holding the answer."},
            "answers_per_prompt": {
                "type": "integer",
                "description": "1 (default) or 2. Two writes a pair per prompt for judge_rows to rank into chosen/rejected.",
            },
            "seed": {"type": "string", "description": "Changes which seed rows are shown, and nothing else."},
        },
        "required": ["task", "into"],
    },
    reads=("filesystem", "datasets", "providers"),
    writes=("filesystem", "datasets"),
    measures=(),
    approval="always",
    provides=("data.synthetic.generate",),
    label="Invent rows with a model",
    group="Data",
    verb="invent training rows from a task and your seeds",
    order=22,
)
def generate_rows(
    task: str,
    into: str,
    count: int = DEFAULT_GENERATED,
    path: str | None = None,
    prompt_column: str | None = None,
    answer_column: str | None = None,
    answers_per_prompt: int = 1,
    seed: str = "",
) -> dict[str, Any]:
    want = datawork.data.bounded(count, DEFAULT_GENERATED, 1, MAX_GENERATED)
    per_prompt = 2 if int(answers_per_prompt or 1) >= 2 else 1
    task_text = " ".join(str(task or "").split())
    try:
        if len(task_text) < 12:
            raise datawork._refuse(
                "no_task",
                "Say what the rows must teach - a sentence or two - or the generator "
                "is inventing a dataset for nothing.",
            )
        seeds: list[dict[str, str]] = []
        source_record = None
        source: Path | None = None
        if path:
            source, fmt = datawork._readable(path)
            pc = str(prompt_column or "").strip()
            ac = str(answer_column or "").strip()
            if not pc or not ac:
                raise datawork._refuse(
                    "no_columns",
                    "With a seed file, name prompt_column and answer_column, or the "
                    "generator cannot tell which is which.",
                    path=str(source),
                )
            total = 0
            for record in datawork._records(source, fmt, datawork.DEFAULT_ROW_LIMIT):
                total += 1
                if record.get(pc) and record.get(ac):
                    seeds.append({"prompt": str(record[pc]), "answer": str(record[ac])})
            source_record = datawork._source_record(source, fmt, total)
            if not seeds:
                raise datawork._refuse(
                    "no_usable_seeds",
                    f"No row in {source.name} has both {pc!r} and {ac!r} filled, so there is nothing to show the generator.",
                    path=str(source),
                )
        adapter, key, row = _connected()
        # `_claim` guards a destination against the dataset being read; with no
        # seed file there is none, and the database file stands in - a file,
        # so no directory can be "inside" it and the other guards still run.
        directory = datawork._claim(into, source if source is not None else Path(db.DB_PATH))
        out_path = directory / GENERATED_FILE

        seen = {_norm(s["prompt"]) for s in seeds}
        written = 0
        duplicates = 0
        unparseable = 0
        requests = 0
        errors: list[str] = []
        shape = _SHAPE_TWO if per_prompt == 2 else _SHAPE_ONE
        system = _GENERATOR_SYSTEM.format(task=task_text, shape=shape)
        with open(out_path, "w", encoding="utf-8") as handle:
            while written < want and requests < (want // PER_REQUEST + 4):
                requests += 1
                shown = _seed_examples(seeds, f"{seed}|{requests}", SEEDS_SHOWN)
                ask = max(1, min(PER_REQUEST, (want - written + per_prompt - 1) // per_prompt))
                user = (
                    (
                        "Examples of the shape (do not copy them):\n"
                        + "\n".join(json.dumps(s, ensure_ascii=False) for s in shown)
                        + "\n\n"
                        if shown
                        else ""
                    )
                    + f"Write {ask} new rows now."
                )
                text, error = _ask(adapter, key, system, user)
                if error:
                    errors.append(error)
                    if len(errors) >= 3:
                        break
                    continue
                objects = _objects(text)
                if not objects:
                    unparseable += 1
                    if unparseable >= 3 and written == 0:
                        break
                    continue
                for obj in objects:
                    prompt = str(obj.get("prompt") or "").strip()
                    if not prompt or _norm(prompt) in seen:
                        duplicates += int(bool(prompt))
                        continue
                    answers = (
                        [obj.get("answer_a"), obj.get("answer_b")]
                        if per_prompt == 2
                        else [obj.get("answer")]
                    )
                    answers = [str(a).strip() for a in answers if a is not None and str(a).strip()]
                    if len(answers) < per_prompt:
                        unparseable += 1
                        continue
                    seen.add(_norm(prompt))
                    group = _fingerprint(prompt)
                    for variant, answer in enumerate(answers):
                        handle.write(
                            json.dumps(
                                {
                                    "prompt": prompt,
                                    "answer": answer,
                                    "generated": True,
                                    "synthetic": True,
                                    "origin": "generated",
                                    "generator": row["model"],
                                    "task": task_text,
                                    "seed_prompts": [s["prompt"][:80] for s in shown],
                                    "group_id": group,
                                    "variant": variant,
                                },
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
                        written += 1
                    if written >= want:
                        break
        manifest = datawork._write_manifest(
            directory,
            {
                "operation": "generate",
                "complete": written >= want,
                "task": task_text,
                "generator": row["model"],
                "source": source_record,
                "seed_rows": len(seeds),
                "rows_written": written,
                "distinct_prompts": len(seen) - len(seeds),
                "answers_per_prompt": per_prompt,
                "duplicates_dropped": duplicates,
                "unparseable_replies": unparseable,
                "requests": requests,
                "errors": errors,
                "wrote": [datawork._written(out_path, written)],
                "method": "a connected model wrote rows for the task, shown seed rows as the shape; tagged generated",
                "does_not_open_g0": (
                    "This wrote a generated file. It did not count one. G0 reads "
                    "eval_size_n, which is a count taken off a file that exists by "
                    "measure_eval_set - and a generated file is not an eval set by "
                    "construction: a model grading its own invented questions is a "
                    "closed loop."
                ),
            },
        )
        events.append(
            "dataset.generated",
            {"into": str(directory), "rows": written, "generator": row["model"], "task": task_text[:200]},
        )
        return {
            "ok": written > 0,
            "summary": (
                f"Wrote {written} generated rows ({len(seen) - len(seeds)} distinct prompts) "
                f"with {row['model']} for: {task_text[:80]}"
                if written
                else "Nothing usable came back from the generator - see errors and unparseable_replies."
            ),
            "into": str(directory),
            "generated_path": str(out_path),
            "manifest_path": manifest["path"],
            "rows_written": written,
            "distinct_prompts": len(seen) - len(seeds),
            "answers_per_prompt": per_prompt,
            "duplicates_dropped": duplicates,
            "unparseable_replies": unparseable,
            "requests": requests,
            "errors": errors,
            "generator": row["model"],
            "wrote": [datawork._written(out_path, written)],
            "measured": [],
            "next": (
                "judge_rows scores them against your rubric and keeps the ones above the bar; "
                "draw_verification_sample is the 10% a person reads before anything trains; "
                "carve the eval set from your OWN rows, never from these."
            ),
        }
    except datawork.Refusal as refusal:
        return dict(refusal.payload)


# ---------------------------------------------------------------------------
# judge_rows
# ---------------------------------------------------------------------------

_JUDGE_SYSTEM = (
    "You are a strict judge of one training row at a time. The rubric:\n{rubric}\n\n"
    f"Score the answer from 0 to {JUDGE_SCALE}: {JUDGE_SCALE} is exactly what the rubric "
    "asks for, 0 is wrong or missing. Reply with one JSON object and nothing else: "
    '{{"score": <number>, "reason": "<one sentence>"}}'
)


def _score_of(text: str) -> tuple[float | None, str]:
    for obj in _objects(text):
        try:
            score = float(obj.get("score"))
        except (TypeError, ValueError):
            continue
        return max(0.0, min(float(JUDGE_SCALE), score)), str(obj.get("reason") or "")
    match = _SCORE.search(text)
    if match:
        return max(0.0, min(float(JUDGE_SCALE), float(match.group(1)))), ""
    return None, ""


@tool(
    "judge_rows",
    description=(
        "Score every row of a generated file against a rubric with the connected "
        "model, keep the rows at or above a threshold, and - where two answers "
        "share a prompt - write chosen/rejected pairs for hf-peft-dpo. The score "
        "is written on each row with the judge's name; it is the judge's "
        "reading, not a measurement of the world."
    ),
    schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "The generated file (generate_rows' generated.jsonl, or any prompt/answer file)."},
            "rubric": {"type": "string", "description": "What a good answer is, in your words. The judge is given this verbatim."},
            "into": {"type": "string", "description": "A NEW directory for judged.jsonl, kept.jsonl, pairs.jsonl and the manifest."},
            "threshold": {"type": "number", "description": f"Keep rows scoring at or above this, 0-{JUDGE_SCALE}. Default {DEFAULT_THRESHOLD}."},
            "max_rows": {"type": "integer", "description": f"Refuse above this many rows. Default {MAX_JUDGED}."},
        },
        "required": ["path", "rubric", "into"],
    },
    reads=("filesystem", "datasets", "providers"),
    writes=("filesystem", "datasets"),
    measures=(),
    approval="always",
    provides=("data.synthetic.judge",),
    label="Judge rows against a rubric",
    group="Data",
    verb="score generated rows with a judge and keep the good ones",
    order=23,
)
def judge_rows(
    path: str,
    rubric: str,
    into: str,
    threshold: float = DEFAULT_THRESHOLD,
    max_rows: int = MAX_JUDGED,
) -> dict[str, Any]:
    bar = max(0.0, min(float(JUDGE_SCALE), float(threshold if threshold is not None else DEFAULT_THRESHOLD)))
    limit = datawork.data.bounded(max_rows, MAX_JUDGED, 1, MAX_JUDGED)
    rubric_text = " ".join(str(rubric or "").split())
    try:
        if len(rubric_text) < 12:
            raise datawork._refuse(
                "no_rubric",
                "Say what a good answer is - a sentence or two - or the judge is scoring against nothing.",
            )
        source, fmt = datawork._readable(path)
        rows: list[dict[str, Any]] = []
        for record in datawork._records(source, fmt, limit):
            rows.append(dict(record))
        usable = [r for r in rows if r.get("prompt") and r.get("answer") is not None]
        if not usable:
            raise datawork._refuse(
                "no_prompt_answer_rows",
                f"No row in {source.name} carries both prompt and answer, so there is nothing to judge.",
                path=str(source),
            )
        adapter, key, row = _connected()
        directory = datawork._claim(into, source)
        system = _JUDGE_SYSTEM.format(rubric=rubric_text)
        rubric_id = _fingerprint(rubric_text)
        judged_path = directory / JUDGED_FILE
        kept_path = directory / KEPT_FILE
        pairs_path = directory / PAIRS_FILE
        scored = 0
        unscored = 0
        kept = 0
        errors: list[str] = []
        histogram: dict[str, int] = {}
        by_group: dict[str, list[dict[str, Any]]] = {}
        with open(judged_path, "w", encoding="utf-8") as judged, open(kept_path, "w", encoding="utf-8") as keep:
            for r in usable:
                user = f"PROMPT:\n{r['prompt']}\n\nANSWER:\n{r['answer']}"
                text, error = _ask(adapter, key, system, user)
                score, reason = (None, "") if error else _score_of(text)
                if error:
                    errors.append(error)
                    if len(errors) >= 5:
                        break
                out = dict(r)
                out["judge_score"] = score
                out["judge_reason"] = reason
                out["judge_model"] = row["model"]
                out["judge_rubric"] = rubric_id
                if score is None:
                    unscored += 1
                else:
                    scored += 1
                    bucket = str(int(score))
                    histogram[bucket] = histogram.get(bucket, 0) + 1
                    if score >= bar:
                        keep.write(json.dumps(out, ensure_ascii=False) + "\n")
                        kept += 1
                    group = str(r.get("group_id") or _fingerprint(_norm(r["prompt"])))
                    by_group.setdefault(group, []).append(out)
                judged.write(json.dumps(out, ensure_ascii=False) + "\n")
        pairs = 0
        with open(pairs_path, "w", encoding="utf-8") as handle:
            for group, members in by_group.items():
                if len(members) < 2:
                    continue
                ranked = sorted(members, key=lambda m: m["judge_score"], reverse=True)
                best, worst = ranked[0], ranked[-1]
                if best["judge_score"] <= worst["judge_score"]:
                    continue
                handle.write(
                    json.dumps(
                        {
                            "prompt": best["prompt"],
                            "chosen": best["answer"],
                            "rejected": worst["answer"],
                            "chosen_score": best["judge_score"],
                            "rejected_score": worst["judge_score"],
                            "judge_model": row["model"],
                            "judge_rubric": rubric_id,
                            "generated": bool(best.get("generated")),
                            "synthetic": True,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                pairs += 1
        manifest = datawork._write_manifest(
            directory,
            {
                "operation": "judge",
                "complete": len(errors) < 5,
                "source": datawork._source_record(source, fmt, len(rows)),
                "judge": row["model"],
                "rubric": rubric_text,
                "rubric_id": rubric_id,
                "threshold": bar,
                "rows_read": len(rows),
                "rows_judged": scored,
                "rows_unscored": unscored,
                "rows_kept": kept,
                "pairs_written": pairs,
                "histogram": histogram,
                "errors": errors,
                "wrote": [
                    datawork._written(judged_path, scored + unscored),
                    datawork._written(kept_path, kept),
                    datawork._written(pairs_path, pairs),
                ],
                "method": "the connected model scored each row against the rubric, 0-10; kept at or above the threshold; pairs by rank within a prompt",
                "does_not_open_g0": "A judge's score is the judge's reading of a generated row. It opens no gate and counts no eval set.",
            },
        )
        events.append(
            "dataset.judged",
            {"into": str(directory), "judged": scored, "kept": kept, "pairs": pairs, "judge": row["model"]},
        )
        return {
            "ok": scored > 0,
            "summary": (
                f"Judged {scored} rows with {row['model']}: {kept} at or above {bar:g}, "
                f"{pairs} chosen/rejected pairs, {unscored} unscored."
            ),
            "into": str(directory),
            "judged_path": str(judged_path),
            "kept_path": str(kept_path),
            "pairs_path": str(pairs_path),
            "manifest_path": manifest["path"],
            "rows_read": len(rows),
            "rows_judged": scored,
            "rows_kept": kept,
            "rows_unscored": unscored,
            "pairs_written": pairs,
            "threshold": bar,
            "histogram": histogram,
            "errors": errors,
            "judge": row["model"],
            "wrote": [
                datawork._written(judged_path, scored + unscored),
                datawork._written(kept_path, kept),
                datawork._written(pairs_path, pairs),
            ],
            "measured": [],
            "next": (
                "kept.jsonl is what hf-peft-lora trains on after a person has read the 10% "
                "(draw_verification_sample); pairs.jsonl is what hf-peft-dpo trains on. "
                "Measure the result on the held-out eval set carved from your own rows - "
                "generated rows earn their place by beating the baseline there, or not at all."
            ),
        }
    except datawork.Refusal as refusal:
        return dict(refusal.payload)
