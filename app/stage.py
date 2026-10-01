"""The Stage's one read: everything its five panels draw, for one thread.

## Why one route and not five tool calls

The Stage is a full-width instrument surface - the Bench (every run's rows
side by side), the Sandbox Ledger, Progression (loss beside held-out score),
the Gate Map and Retrieval & Split. Max's decision of 2026-09-02 fixed its
shape: one surface, three sizes (a detached window while a run spends, an
inline transcript row when it is done, a split in the shell between), and one
rule above the rest - **the transcript is the record and the conversation is
the driver.** The Stage never writes. It is a second READER of what the thread
already measured.

A reader that drove `read_eval_results` seven times through the user's door
would file seven "run by you" rows into the thread it is trying to read, which
is the reader writing. So the Stage reads through this module instead, off the
same tables and the same functions the tools wrote through: `evals.results_for`
for the rows, `evals.compare` for the paired verdict (McNemar, the same code
path - a second implementation of "is this difference real" would disagree with
the first within a month), `sandbox.every` and each run's own `job.log` for the
sandbox ledger, `sandbox._gpu_occupancy` for what is on the card, and
`journey_report.build` for the diagnosis. Nothing is computed here that a tool
did not already compute; this file joins and it does not judge.

## What a panel gets

- `runs`: every eval run in the thread, oldest first, with `rows` - one
  `{row_index, correct, failure_mode, bucketed_by}` per graded row - so the Bench
  can draw a cell per row and outline the ones that flipped. `baseline_run_id`
  is the oldest complete run measured under the default prompt, which is what
  `measure_baseline` produces and what every later run is paired against.
- `comparisons`: for every run that is not the baseline, `evals.compare(run,
  baseline)` cut down to what the Bench states: improved, regressed, p, verdict,
  and the rows behind each.
- `sandboxes`: `sandbox.report` for each of the project's sandboxes, plus the
  runs inside it read off `job.json` and the `MLH_EVENT` lines of `job.log` -
  kind, steps, elapsed, peak VRAM, the loss curve as (step, loss) points, and the
  final loss. Read, never re-derived: a run that wrote no events has no curve.
- `gpu`: the card now, and the guard's sentence for it, or nulls where there is
  no card.
- `diagnosis`: the journey report - verdict, gate ledger, facts with origins.

Every number here carries the provenance the producing tool gave it. The Stage
draws provenance tags off these fields; it never invents one.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app import db, journey_report
from app.tools import evals, sandbox

#: One loss point per this many steps at most, so a 10,000-step log is a curve
#: rather than a payload. The endpoints are always kept.
CURVE_POINTS = 120

_EVENT = re.compile(r"^MLH_EVENT (\{.*\})\s*$")


def _project_of(thread_id: int) -> int | None:
    with db.session() as connection:
        row = connection.execute(
            "SELECT project_id FROM threads WHERE id = ?", (int(thread_id),)
        ).fetchone()
    if row is None:
        raise KeyError(thread_id)
    return None if row["project_id"] is None else int(row["project_id"])


def _run_summary(run_id: int) -> dict[str, Any]:
    report = evals.read(int(run_id), failures=0)
    rows = [
        {
            "row_index": int(r["row_index"]),
            "correct": bool(r["correct"]),
            "failure_mode": r.get("failure_mode"),
            "bucketed_by": r.get("bucketed_by"),
        }
        for r in evals.results_for(int(run_id))
    ]
    keep = (
        "run_id", "complete", "reused", "eval_path", "eval_fingerprint", "metric",
        "prompt_is_default", "provider", "model", "locality", "judge_model",
        "planned", "graded", "correct", "score", "partial_score", "scores",
        "trivial_baseline_score", "resolution", "failure_histogram", "self_graded",
        "summary",
    )
    out = {k: report.get(k) for k in keep if k in report}
    out["prompt"] = (report.get("prompt") or "")[:160]
    out["rows"] = rows
    return out


def _baseline_of(runs: list[dict[str, Any]]) -> int | None:
    for run in runs:  # oldest first
        if run.get("complete") and run.get("prompt_is_default"):
            return int(run["run_id"])
    for run in runs:
        if run.get("complete"):
            return int(run["run_id"])
    return None


def _comparison(run_id: int, baseline_id: int) -> dict[str, Any] | None:
    paired = evals.compare(int(run_id), int(baseline_id), failures=0)
    if not paired.get("ok"):
        return None
    keep = (
        "run_id", "against", "paired_rows", "same_rows", "score", "score_against",
        "delta", "correct", "correct_against", "improved", "regressed", "changed",
        "p_value", "test", "resolved", "verdict", "rows_that_would_resolve_this_delta",
        "improved_rows", "regressed_rows", "measured_on",
    )
    return {k: paired.get(k) for k in keep if k in paired}


def _curve(events: list[dict[str, Any]]) -> list[dict[str, float]]:
    points = [
        {"step": int(e["step"]), "loss": float(e["loss"])}
        for e in events
        if "step" in e and "loss" in e
    ]
    if len(points) <= CURVE_POINTS:
        return points
    stride = max(1, len(points) // CURVE_POINTS)
    kept = points[::stride]
    if kept[-1] is not points[-1]:
        kept.append(points[-1])
    return kept


def _runs_inside(manifest_report: dict[str, Any]) -> list[dict[str, Any]]:
    # The listing's report names the sandbox's directory; the runs live in its
    # fixed `runs/` child (`sandbox.RUNS`), the same place `sandbox.run` writes.
    runs_dir = manifest_report.get("runs_dir") or ""
    if not runs_dir and manifest_report.get("path"):
        runs_dir = str(Path(str(manifest_report["path"])) / sandbox.RUNS)
    root = Path(str(runs_dir)) if runs_dir else None
    if root is None or not root.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name):
        if not entry.is_dir():
            continue
        job: dict[str, Any] = {}
        try:
            job = json.loads((entry / "job.json").read_text("utf-8"))
        except (OSError, ValueError):
            pass
        events: list[dict[str, Any]] = []
        try:
            for line in (entry / "job.log").read_text("utf-8", "replace").splitlines():
                match = _EVENT.match(line)
                if not match:
                    continue
                try:
                    events.append(json.loads(match.group(1)))
                except ValueError:
                    continue
        except OSError:
            pass
        last = events[-1] if events else {}
        config = job.get("config") or {}
        out.append(
            {
                "name": entry.name,
                "kind": job.get("kind"),
                "recipe": job.get("recipe"),
                "base_model": config.get("base_model"),
                "max_steps": config.get("max_steps"),
                "steps": last.get("steps") or last.get("step"),
                "elapsed_seconds": last.get("elapsed_seconds"),
                "peak_vram_gb": max(
                    (float(e["peak_vram_gb"]) for e in events if "peak_vram_gb" in e),
                    default=None,
                ),
                "final_loss": last.get("final_loss"),
                "adapter_dir": last.get("adapter_dir"),
                "curve": _curve(events),
                "events": len(events),
                "has_adapter": (entry / "adapter").is_dir(),
                "has_predictions": (entry / "predictions.jsonl").is_file(),
            }
        )
    return out


def build(thread_id: int) -> dict[str, Any]:
    """The whole Stage payload for one thread. Raises KeyError for no thread."""
    project_id = _project_of(int(thread_id))

    listed = evals.runs_in(int(thread_id), limit=50)
    runs = [_run_summary(int(row["id"])) for row in reversed(listed)]
    baseline_id = _baseline_of(runs)
    comparisons: dict[str, Any] = {}
    if baseline_id is not None:
        for run in runs:
            rid = int(run["run_id"])
            if rid == baseline_id or not run.get("complete"):
                continue
            paired = _comparison(rid, baseline_id)
            if paired is not None:
                comparisons[str(rid)] = paired

    boxes: list[dict[str, Any]] = []
    try:
        for reported in sandbox.every(project_id=project_id):
            box = dict(reported)
            box["runs"] = _runs_inside(reported)
            boxes.append(box)
    except sandbox.SandboxRejected:
        boxes = []

    occupancy = sandbox._gpu_occupancy()
    gpu = {
        "occupancy": occupancy,
        "guard": sandbox._gpu_is_crowded(occupancy),
        "crowded_above_gb": sandbox.GPU_CROWDED_ABOVE_GB,
    }

    try:
        diagnosis = journey_report.build(int(thread_id))
    except KeyError:
        diagnosis = None

    return {
        "thread_id": int(thread_id),
        "project_id": project_id,
        "baseline_run_id": baseline_id,
        "runs": runs,
        "comparisons": comparisons,
        "sandboxes": boxes,
        "gpu": gpu,
        "diagnosis": diagnosis,
        "reads": {
            "runs": "evals.runs_in + evals.read + evals.results_for",
            "comparisons": "evals.compare, paired against baseline_run_id",
            "sandboxes": "sandbox.every + each run's job.json and MLH_EVENT lines",
            "gpu": "sandbox._gpu_occupancy - nvidia-smi and ollama /api/ps",
            "diagnosis": "journey_report.build",
        },
    }
