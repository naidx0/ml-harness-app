"""Launch a training run, and put it in the conversation while it happens.

We do not write a trainer. Unsloth already shipped a free, open-source, local
one across every accelerator vendor, and a slower copy of a free thing is not a
business (`docs/VISION.md`, "What we do not build"). What is missing from the
market is everything around it, so this file is the *around*: it picks a pinned
recipe, hands it a structured job, supervises the process, and turns what comes
back into events a person can read three weeks later.

## Nothing here is a stub

`docs/VISION.md` is explicit that a stub which looks like a trainer is worse
than no trainer, so there is no code path in this file that reports a training
run it did not run. Every claim it makes comes from a row in the jobs table, a
line in a log file on disk, or an exit code. When the pinned environment is not
built, `recipes/hf-peft-lora/entrypoint.py` refuses and says how to build it;
this module reports the refusal as a refusal.

## The transcript is the artifact, so the log becomes events

The runner streams the job's stdout to `<run>/job.log` as it arrives. That file
is durable and it is not a transcript: nothing in a conversation can see it,
and a log is lost the moment somebody tidies a folder. So `training_status`
*drains* it - every new line since last time becomes an event on the event
spine, with the structured `MLH_EVENT` lines becoming typed events and the rest
becoming ordinary log events.

Draining is what makes "long-running work lives in the conversation" true
across a restart. The two things that carry the state are both files on disk:
the log the job is writing, and a small offset beside it saying how much of it
has already been turned into events. Kill the engine mid-run and the job keeps
going - it is its own process group - and the next status call picks up from
the offset rather than replaying six hours of output into the thread.

## Every tool is also a control

`start_training` is declared `approval="always"`. A model that asks for it gets
a recorded "this needs an approval" in the transcript rather than a GPU
running for four hours; a person clicking the button is an approval, and
`REGISTRY.call(..., approved=True)` is the same entry point. One declaration,
two callers, and the expensive one cannot happen by accident.

## It may not decide a gate, and it does not

Memory feasibility is not one of the five gates. This tool reports what a run
would cost and what the estimator says about whether it fits, and it neither
reads nor writes `G0_EVAL_SET` through `G4_CHEAPER_MODEL_CONSIDERED`. Whether
training is the right thing to do at all is `app/diagnosis.py`'s answer and
nothing in this file can reach it.

# ===========================================================================
# SCORING WHAT WAS TRAINED - `score_the_adapter`
# ===========================================================================

Everything above is about starting a run. This is about the sentence that
makes starting one worth anything, and until now the product could not say it:
**this adapter beats the baseline you measured, by more than these rows can
resolve.** `app/tools/propose.py` refused to draw a full fine-tune for exactly
that reason, in its own words - a build that ran to the end "would hand you an
adapter and nothing that could say whether it is better than what you already
have, with 'the run exited zero' as the only thing anybody could check".

## WHY THE SANDBOX IS THE ANSWER AND NOT A PROVIDER

Every tool in this harness that can put text in front of a model declares
`providers` in its reads, and `app/providers.ADAPTERS` is exactly
`('openai-compatible', 'ollama')`. A LoRA adapter is a directory of
safetensors; it is neither. Making it one would mean writing a serving layer,
which is a product we are not building.

The sandbox already holds the answer. It has the environment that TRAINED the
adapter - the recipe's own `.venv`, 45 locked requirements, `peft` and
`transformers` among them, an isolated working directory and a snapshot of the
data as it was. The adapter does not need to become a provider; it needs to be
scored where it was made. That keeps every invariant at once: no new dependency
in the harness, no egress, and the thing doing the scoring is the same pinned
environment that did the training, which is the only reason the comparison
means anything.

`recipes/hf-peft-lora/recipe.toml` therefore declares `kinds = ["train",
"eval"]` and its entrypoint implements the second one. `app/jobspec.py` refuses
a kind the recipe did not declare, and that refusal was the whole blocker.

## THE FOUR THINGS THAT MAKE THE NUMBER HONEST

**ONE: THE SAME ROWS, BY CONSTRUCTION.** `baseline_run_id` is required, not
optional. The rows are read out of the baseline run's own `eval_results` - the
row indexes it actually graded - and those exact indexes are re-read from the
eval file and handed to the recipe in `job.json`. There is no path through this
function that scores a row set chosen any other way. `app/tools/evals.py`
records what happens when two arms grade different rows: a card reading "-50.0%
/ A real difference / MEASURED" sitting above "6 improved, 0 regressed". The
eval file's fingerprint is checked against the baseline's as well, so a file
that changed under the two runs is a refusal rather than a delta.

**TWO: THE SAME GRADER.** The recipe generates text and grades nothing. The
verdicts come from `evals.grade` - the same function, the same normalisation -
in this process, on both arms. Two graders would be two instruments, and two
scores from two instruments are two facts rather than a comparison.

**THREE: A CONTROL ARM WITH THE ADAPTER SWITCHED OFF.** The provider baseline
and the sandbox are still two different instruments in one respect that cannot
be removed: the baseline went through a chat endpoint under
`measure.BASELINE_SYSTEM`, and the adapter is a greedy continuation of a
prompt template. So the recipe also answers the same rows inside
`PeftModel.disable_adapter()`, which differs from the adapter arm by the LoRA
deltas and by NOTHING else - same weights, same tokenizer, same dtype, same
decode, same prompt. `against_the_base_model` is the comparison that isolates
what the training did; `against_the_baseline` is the one that answers the
user's question; both are reported and each says what it is.

**FOUR: IT STAMPS NOTHING.** `measures=()`. `run_eval` stamps `baseline_score`,
`trivial_baseline_score`, `baseline_measured` and `failure_histogram`, and
every one of those is a fact about the model the user is running today. Filing
an adapter's score under `baseline_score` would be a real measurement of a
different model under the wrong name, and `failure_histogram` routes stage 1 of
the diagnosis - bucketing an adapter's failures into it would re-route somebody's
diagnosis onto a model they have not deployed. The eval rows are written to
`eval_results`, which is this bench's own table and is not the fact ledger, and
`tests/test_an_adapter_is_scored_where_it_was_made.py` proves the five gates
are untouched by a call to this tool.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import db, events, feasibility, hwdetect, jobspec, runner
from app.tools import datawork
from app.tools.registry import tool


#: The marker a recipe puts on a structured progress line. Matches
#: `recipes/hf-peft-lora/entrypoint.py`; a recipe that does not use it still
#: works, its output just arrives as ordinary log events.
EVENT_PREFIX = "MLH_EVENT "

#: Where a job's drain offset lives: beside the log it describes, inside the
#: job's own run directory. On disk, because surviving a restart is the point.
OFFSET_NAME = "events.offset"

#: How many events one drain may append. A six-hour log is not something to
#: pour into a thread in one go; the offset advances by exactly what was
#: appended, so the next call continues rather than skipping.
DRAIN_LIMIT = 300

#: Default wall-clock bound for a training job, in seconds. Six hours. The
#: runner kills the whole process tree at this point, so it is a real bound and
#: not a hope - `app/runner.py` records the measurement that proves it.
DEFAULT_TIMEOUT_SECONDS = 6 * 3600

#: Default bound for a scoring run, in seconds. Twenty minutes, which is
#: `app/tools/sandbox.py`'s own default for a run inside a sandbox and is a
#: bound this file states rather than a measurement of anything. Scoring is a
#: forward pass per row and it is not a fine-tune; a run that hits this is
#: reported with the rows it did answer rather than as a failure.
DEFAULT_SCORING_TIMEOUT_SECONDS = 20 * 60

#: The file the eval kind writes, per arm. Named here and in
#: `recipes/hf-peft-lora/entrypoint.py`, which is a shared name between a tool
#: and a recipe rather than a duplicated decision - the recipe is the writer and
#: this is the reader.
PREDICTIONS = "predictions.jsonl"
PREDICTIONS_BASE = "predictions_base.jsonl"

#: The job kind that scores. `app/jobspec.KINDS` declares it and
#: `jobspec.validate` refuses it for a recipe that does not.
SCORING_KIND = "eval"

#: The most rows one scoring call will send into a sandbox. Each row is a
#: generate() call and the whole list travels inside `job.json`, so this bounds
#: both the wall clock and the size of that file. It is a bound this file
#: states; the reply always says how many rows were actually scored.
MAX_SCORED_ROWS = 500

#: How a row becomes a prompt for a raw causal language model, by default: the
#: input, verbatim. A model fine-tuned on `{"text": ...}` rows is a continuation
#: model and not a chat endpoint, so a template is the honest place to put any
#: framing rather than something this file adds behind the caller's back. Both
#: arms get the same one, so the comparison between them is unaffected by it.
DEFAULT_PROMPT_TEMPLATE = "{input}"

#: One job at a time in this process. This lock used to be standing in for a
#: missing claim in `app/db.py` - `next_queued_job` selected the oldest queued
#: row without marking it, so two supervisors would both start the same job,
#: and a `threading.Lock` covers one process while the defect was in the
#: database. Since 2026-09-02 the claim is atomic there (one UPDATE ...
#: RETURNING), so this lock is no longer the wall: it is what keeps ONE
#: process from running two trainings at once, which is its own reason and a
#: smaller one.
_SLOT = threading.Lock()

_SUPERVISORS: list[threading.Thread] = []

#: Only these may be spelled by a caller. Anything else in a config dict is
#: dropped rather than passed to a recipe, because `config` is the one
#: caller-controlled thing that reaches a job and a narrow door is the whole
#: reason `app/jobspec.py` exists.
CONFIG_KEYS = (
    "base_model",
    "dataset_path",
    "text_field",
    # The named-column pair the recipe grew on 2026-09-01. Review found the
    # recipe's own refusal naming a door this filter silently closed.
    "prompt_field",
    "completion_field",
    "max_steps",
    "batch_size",
    "grad_accum",
    "max_seq_len",
    "learning_rate",
    "lora_r",
    "lora_alpha",
    "lora_dropout",
    "logging_steps",
    "seed",
    "optim",
    "run_id",
    "grad_checkpointing",
    "min_free_vram_gb",
)

_RECIPE_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


# ---------------------------------------------------------------------------
# What recipes exist, and whether they can actually run.


def _directory_bytes(path: Path) -> int | None:
    try:
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    except OSError:
        return None


def recipe_report(name: str) -> dict[str, Any]:
    """One recipe: what it can do, and whether its environment is built.

    The disk figure is measured by walking the directory, never quoted from a
    table. A user about to spend five gigabytes deserves the number from their
    own disk.
    """
    try:
        recipe = jobspec.load_recipe(name)
    except jobspec.JobRejected as rejected:
        return {"name": name, "usable": False, "detail": str(rejected)}

    directory = recipe.entrypoint.parent
    venv = jobspec.venv_for(recipe)
    interpreter = (
        venv / "Scripts" / "python.exe"
        if (venv / "Scripts" / "python.exe").is_file()
        else venv / "bin" / "python"
    )
    lock = directory / "requirements.lock"
    built = interpreter.is_file()
    size = _directory_bytes(venv) if built else None
    return {
        "name": recipe.name,
        "kinds": list(recipe.kinds),
        "description": recipe.description,
        "pinned_environment": {
            "declared": lock.is_file(),
            "lockfile": str(lock) if lock.is_file() else None,
            "built": built,
            "interpreter": str(interpreter) if built else None,
            "on_disk_gb": None if size is None else round(size / (1024 ** 3), 2),
            "on_disk_provenance": "measured" if size is not None else "not built yet",
        },
        "usable": built or not lock.is_file(),
        "detail": (
            ""
            if built or not lock.is_file()
            else (
                "This recipe declares a pinned environment that has not been "
                "built. It will refuse to train until it is, and say how."
            )
        ),
    }


# ---------------------------------------------------------------------------
# The supervisor.


def _supervise(timeout: int) -> None:
    """Run one queued job to completion. Runs on a daemon thread.

    `runner.run_next_job` owns the process tree, the bound and the log. This
    adds exactly two things: the single-slot lock, and the fact that it is not
    the request thread - a training run that blocked the engine for six hours
    would take the conversation down with it, and the conversation is the
    product.
    """
    with _SLOT:
        try:
            runner.run_next_job(timeout=timeout, stream=True)
        except Exception:  # noqa: BLE001 - the job row already records the end
            pass


def start_supervisor(timeout: int = DEFAULT_TIMEOUT_SECONDS) -> threading.Thread:
    thread = threading.Thread(
        target=_supervise, args=(timeout,), name="mlh-training-supervisor",
        daemon=True,
    )
    _SUPERVISORS.append(thread)
    thread.start()
    return thread


def wait_for_supervisors(timeout: float = 60.0) -> bool:
    """Join every supervisor this process started. For tests and shutdown."""
    deadline = time.monotonic() + timeout
    for thread in list(_SUPERVISORS):
        thread.join(timeout=max(0.0, deadline - time.monotonic()))
    alive = [t for t in _SUPERVISORS if t.is_alive()]
    _SUPERVISORS[:] = alive
    return not alive


# ---------------------------------------------------------------------------
# Draining a job log into the event spine.


def _run_dir_for(job: dict[str, Any]) -> Path:
    recorded = job.get("log_path")
    if recorded:
        return Path(recorded).parent
    return jobspec.run_dir_for(job["id"])


def _log_path_for(job: dict[str, Any]) -> Path:
    recorded = job.get("log_path")
    if recorded:
        return Path(recorded)
    return jobspec.log_path_for(job["id"])


def _read_offset(run_dir: Path) -> int:
    try:
        body = json.loads((run_dir / OFFSET_NAME).read_text(encoding="utf-8"))
        value = int(body.get("lines", 0))
    except (OSError, ValueError, TypeError):
        return 0
    return max(0, value)


def _write_offset(run_dir: Path, lines: int) -> None:
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / OFFSET_NAME).write_text(
            json.dumps({"lines": int(lines)}), encoding="utf-8"
        )
    except OSError:
        pass


def structured(line: str) -> dict[str, Any] | None:
    """The structured payload inside a log line, or `None` if there is none.

    Searched for anywhere in the line rather than only at the start, and that
    is not defensive tidiness - it is a measured defect. The runner merges
    stderr into stdout so a traceback lands next to the line that caused it,
    and a progress bar writes to stderr with a carriage return and no newline.
    The result on disk is ` 40%|####| 4/10 [00:01<00:02]MLH_EVENT {...}`: the
    marker is real, the JSON is intact, and `startswith` finds none of it. Every
    per-step metric of a real training run was being filed as untyped log text
    because of it.
    """
    at = line.find(EVENT_PREFIX)
    if at < 0:
        return None
    try:
        payload = json.loads(line[at + len(EVENT_PREFIX):])
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def drain_log(
    job: dict[str, Any],
    *,
    run_id: int | None = None,
    thread_id: int | None = None,
    limit: int = DRAIN_LIMIT,
) -> dict[str, Any]:
    """Turn everything the job has printed since last time into events.

    Returns a summary rather than the events themselves; the events are on the
    spine, which is where a reconnecting client will find them anyway.
    """
    run_dir = _run_dir_for(job)
    log_path = _log_path_for(job)
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {"appended": 0, "lines_seen": 0, "log_path": str(log_path),
                "detail": "no log on disk yet"}

    already = _read_offset(run_dir)
    appended = 0
    consumed = already
    latest: dict[str, Any] | None = None
    for index in range(already, min(len(lines), already + limit)):
        # `consumed` advances for every line looked at, `appended` only for
        # lines that produced an event. They are different numbers because a
        # blank line produces nothing, and advancing the offset by `appended`
        # would leave the blanks to be re-read on every future call - which is
        # how a log with a run of empty lines pins the offset in place and the
        # rest of the run never reaches the transcript at all.
        consumed = index + 1
        line = lines[index]
        payload = structured(line)
        if payload is not None:
            kind = str(payload.pop("kind", "progress"))
            payload["job_id"] = job["id"]
            events.append(
                f"train.{kind}", payload, run_id=run_id, thread_id=thread_id
            )
            if kind in ("progress", "finished"):
                latest = dict(payload)
        else:
            if not line.strip():
                continue
            events.append(
                "train.log",
                {"job_id": job["id"], "text": line},
                run_id=run_id,
                thread_id=thread_id,
            )
        appended += 1
    _write_offset(run_dir, consumed)
    return {
        "appended": appended,
        "lines_seen": len(lines),
        "lines_drained": consumed,
        "log_path": str(log_path),
        "latest_progress": latest,
    }


# ---------------------------------------------------------------------------
# Costing a run before it starts.


def _vram_field() -> feasibility.Field:
    specs = hwdetect.local_specs()
    return feasibility.Field(
        specs.get("vram_gb"),
        (specs.get("provenance") or {}).get("vram_gb", "defaulted"),
        (specs.get("sources") or {}).get("vram_gb", "app/hwdetect.py"),
    )


def cost_preview(
    base_model: str,
    method: str,
    max_seq_len: int,
    batch_size: int,
    grad_checkpointing: bool = True,
) -> dict[str, Any]:
    """What this run is expected to need, and how confident that is.

    Uses the model's own geometry when its `config.json` has been read - which
    is what `find_models` and `read_model_config` are for - and says UNKNOWN
    when it has not, rather than borrowing another architecture's shape.

    `grad_checkpointing` is not a knob this function invents: it is passed
    through to the recipe in the same job config, so the estimate and the run
    cannot disagree about it. Estimating with checkpointing and then training
    without it is how a "fits" turns into an OOM twenty minutes in.
    """
    vram = _vram_field()
    geometry = feasibility.geometry_for(base_model)
    params_b, params_source = feasibility.parameters_b_for(base_model)
    estimate = feasibility.estimate_training_vram(
        params_b,
        method,
        max_seq_len,
        batch_size,
        geometry=geometry,
        grad_checkpointing=grad_checkpointing,
    )
    known = None
    if estimate["base_weights_gb"] is not None:
        known = (
            estimate["base_weights_gb"]
            + (estimate["gradients_gb"] or 0.0)
            + (estimate["optimizer_gb"] or 0.0)
        )
    decided = feasibility.verdict(
        vram,
        known,
        estimate["activations_gb"],
        overhead_gb=estimate["overhead_gb"],
        geometry_provenance=estimate["geometry_provenance"],
    )
    return {
        "verdict": decided["verdict"],
        "reason": decided.get("reason", ""),
        "needed_gb": estimate["total_gb"],
        "grad_checkpointing": bool(grad_checkpointing),
        "method": method,
        "max_seq_len": int(max_seq_len),
        "batch_size": int(batch_size),
        "vram_gb": vram.value,
        "vram_provenance": vram.provenance,
        "params_b": params_b,
        "params_source": params_source or (
            f"config.json for {base_model} has not been read; run "
            "read_model_config first if you want a number here"
        ),
        "geometry_provenance": estimate["geometry_provenance"],
        "terms_gb": {
            "base_weights": estimate["base_weights_gb"],
            "gradients": estimate["gradients_gb"],
            "optimizer": estimate["optimizer_gb"],
            "activations": estimate["activations_gb"],
            "logits": estimate["logits_gb"],
            "overhead": estimate["overhead_gb"],
        },
        "assumptions": estimate["assumptions"],
        "what_it_costs": (
            "Time on your own machine and its video memory. Nothing is billed, "
            "and the only thing that leaves this computer is the model download."
        ),
    }


# ---------------------------------------------------------------------------
# Scoring an adapter, in the sandbox that trained it. Read the second half of
# the module docstring before changing anything below.


class NotScorable(ValueError):
    """This adapter cannot be scored. The message is safe to show the caller."""


def _adapter_at(directory: Path) -> dict[str, Any]:
    """What is really in an adapter directory, read off disk.

    `adapter_config.json` is written by `save_pretrained` and carries
    `base_model_name_or_path` - which base model these deltas belong to. It is
    read rather than assumed because scoring an adapter against a base it was
    not trained on produces a number that looks exactly like a score.
    """
    manifest = directory / "adapter_config.json"
    if not manifest.is_file():
        raise NotScorable(
            f"{directory} is not an adapter: it has no adapter_config.json. "
            "Nothing was scored."
        )
    try:
        body = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as unreadable:
        raise NotScorable(
            f"{manifest} could not be read: {unreadable}. Without it there is "
            "no record of which base model this adapter belongs to."
        ) from None
    weights = [
        name
        for name in ("adapter_model.safetensors", "adapter_model.bin")
        if (directory / name).is_file()
    ]
    if not weights:
        raise NotScorable(
            f"{directory} has an adapter_config.json and no weights beside it. "
            "A training run that was killed before it saved leaves exactly "
            "this, and there is nothing in it to score."
        )
    sizes = {name: (directory / name).stat().st_size for name in weights}
    return {
        "path": str(directory),
        "base_model": str(body.get("base_model_name_or_path") or ""),
        "peft_type": str(body.get("peft_type") or ""),
        "r": body.get("r"),
        "lora_alpha": body.get("lora_alpha"),
        "target_modules": sorted(body.get("target_modules") or []),
        "weights": sizes,
        "bytes": sum(sizes.values()),
        "bytes_provenance": "measured by stat() on the files in this directory",
        "has_tokenizer": (directory / "tokenizer_config.json").is_file(),
    }


def find_the_adapter(
    sandbox_name: str, adapter_dir: str | None = None, instance: str | None = None
) -> dict[str, Any]:
    """The adapter this sandbox made, or the one the caller named.

    Searched newest-run-first inside the sandbox's own `runs/` tree, because
    `recipes/hf-peft-lora/entrypoint.py` writes its adapter to
    `<run_dir>/adapter` and a sandbox's runs are numbered. A caller may name a
    directory instead - an adapter from `start_training` lives under `runs/`
    rather than in a sandbox - and the reply says whether the adapter it is
    about to score was made in the sandbox that is about to score it, because
    that is the difference between a reproducible comparison and a plausible
    one.
    """
    from app.tools import sandbox as sandboxes

    manifest = sandboxes.read_manifest(sandbox_name, instance)
    home = sandboxes.folder(manifest, "runs_dir", sandboxes.RUNS)

    if adapter_dir:
        directory = Path(str(adapter_dir).strip().strip('"'))
        if not directory.is_dir():
            raise NotScorable(
                f"there is no directory at {directory}, so there is no adapter "
                "to score. Nothing was started."
            )
        found = _adapter_at(directory.resolve())
        inside = home.resolve() in directory.resolve().parents
        found["made_in_this_sandbox"] = inside
        found["found_by"] = "the path this call named"
        return found

    candidates: list[tuple[int, Path]] = []
    try:
        entries = sorted(home.iterdir())
    except OSError:
        entries = []
    for entry in entries:
        match = re.fullmatch(r"run_(\d+)", entry.name)
        if not match or not entry.is_dir():
            continue
        for inner in (entry / "adapter", entry):
            if (inner / "adapter_config.json").is_file():
                candidates.append((int(match.group(1)), inner))
                break
    if not candidates:
        raise NotScorable(
            f"sandbox {sandbox_name!r} has not trained anything: no run inside "
            f"{home} holds an adapter_config.json. Train in it first, or name "
            "an adapter directory with adapter_dir."
        )
    number, directory = max(candidates, key=lambda row: row[0])
    found = _adapter_at(directory)
    found["made_in_this_sandbox"] = True
    found["found_by"] = f"the newest run in this sandbox that holds one, run_{number}"
    return found


def rows_the_baseline_graded(baseline: dict[str, Any]) -> dict[str, Any]:
    """The exact rows a stored eval run graded, re-read from the eval file.

    THE ONE FUNCTION THAT MAKES "THE SAME ROWS" A PROPERTY RATHER THAN A HOPE.

    `evals._plan` is called rather than copied, and it is called for the file
    and the two columns the BASELINE used. That matters more than it looks:
    `row_index` in this product counts ELIGIBLE rows - rows carrying both
    columns - from zero in file order, and that rule lives in `_plan`. A second
    implementation of it here would disagree with the baseline's numbering the
    first time a row was missing a column, and every pair after that would be
    two different questions compared to each other. Reaching for a private
    function is the smaller sin.

    The text comes from the FILE and not from `eval_results`, because the
    stored copy is clipped at `evals.STORED_TEXT_CHARS`; asking the adapter a
    truncated question the baseline was never asked is the same defect wearing
    a different hat.
    """
    from app.tools import evals

    graded = sorted(int(row["row_index"]) for row in evals.results_for(baseline["run_id"]))
    if not graded:
        raise NotScorable(
            f"eval run {baseline['run_id']} has no graded rows on disk, so "
            "there is nothing to score the adapter on."
        )
    plan = evals._plan(
        str(baseline["eval_path"]),
        str(baseline["input_field"]),
        str(baseline["expected_field"]),
        max(graded) + 1,
        (),
    )
    if plan["fingerprint"] != baseline["eval_fingerprint"]:
        raise NotScorable(
            f"{baseline['eval_path']} is not the file eval run "
            f"{baseline['run_id']} graded: its rows no longer hash to the same "
            "eval set. Scoring an adapter on today's file and comparing it to "
            "yesterday's baseline would be two facts subtracted from each "
            "other. Re-run the baseline against this file and ask again."
        )
    by_index = {index: (question, expected) for index, question, expected in plan["chosen"]}
    missing = [index for index in graded if index not in by_index]
    if missing:  # pragma: no cover - the fingerprint check above catches this first
        raise NotScorable(
            f"{len(missing)} row(s) the baseline graded are not in "
            f"{baseline['eval_path']} any more, starting at row {missing[0]}. "
            "Nothing was scored."
        )
    return {
        "indexes": graded,
        "rows": [
            {"row_index": index, "input": by_index[index][0], "expected": by_index[index][1]}
            for index in graded
        ],
        "available": int(plan["available"]),
        "fingerprint": plan["fingerprint"],
    }


def read_predictions(path: Path) -> dict[int, dict[str, Any]]:
    """One arm's answers, by `row_index`. A short file is a short answer.

    Keyed on the index the recipe was given rather than on position, so a run
    that was killed at row forty pairs its forty answers against the right
    forty questions instead of against the first forty.
    """
    answers: dict[int, dict[str, Any]] = {}
    try:
        body = path.read_text(encoding="utf-8")
    except OSError:
        return answers
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict) or "row_index" not in row:
            continue
        try:
            answers[int(row["row_index"])] = row
        except (TypeError, ValueError):
            continue
    return answers


def _store_an_arm(
    *,
    arm: str,
    thread_id: int,
    baseline: dict[str, Any],
    chosen: dict[str, Any],
    answers: dict[int, dict[str, Any]],
    model_name: str,
    prompt_template: str,
    where: str,
    judged: dict[int, bool] | None = None,
    judge_model: str | None = None,
) -> dict[str, Any]:
    """Grade one arm's answers and keep every row, exactly as `run_eval` does.

    `evals.grade` decides the rule verdicts and `evals.bucket` names the
    failures - the same functions on the same rows that graded the baseline,
    which is what makes the two runs comparable at all. When the baseline was
    MODEL-graded, `judged` carries the anchor's own judge's verdict per row -
    obtained by `_judge_the_answers` in this process, before anything was
    written - and the rule verdicts are still computed and stored beside it,
    exactly as `run_eval` stores them, so the judge/rule gap stays readable.
    Nothing HERE asks a model anything either way: the answers were produced
    in the sandbox and this is the reading of them.

    The run is stored with `prompt_is_default = 0` and no provider, so nothing
    downstream can mistake it for the baseline `G1_BASELINE_MEASURED` reads.
    """
    from app.tools import evals

    rows = chosen["rows"]
    expected_values = [row["expected"] for row in rows]
    counts = Counter(evals.normalise_answer(value) for value in expected_values)
    trivial_answer, trivial_hits = counts.most_common(1)[0]
    labels = evals._label_set(expected_values)

    run_row = evals.create_run(
        thread_id=int(thread_id),
        signature=evals.signature_for(
            eval_fingerprint=str(chosen["fingerprint"]),
            input_field=str(baseline["input_field"]),
            expected_field=str(baseline["expected_field"]),
            # NOT an adapter in `app/providers` terms - there is no connection
            # here at all. The word is the column's, and what goes in it says
            # where the answers came from.
            adapter=f"{evals.SANDBOX_ARM_PREFIX}{arm}",
            base_url=where,
            model=model_name,
            prompt=prompt_template,
            metric=str(baseline["metric"]),
            judge_model=judge_model or "",
            sample=len(rows),
            hold_out=(),
        ),
        eval_path=str(baseline["eval_path"]),
        eval_fingerprint=str(chosen["fingerprint"]),
        input_field=str(baseline["input_field"]),
        expected_field=str(baseline["expected_field"]),
        metric=str(baseline["metric"]),
        prompt=prompt_template,
        prompt_is_default=0,
        provider_id=None,
        # THE MARK THAT SAYS NO CONNECTION PRODUCED THESE ANSWERS, and it is
        # `evals.SANDBOX_ARM_PREFIX` rather than a literal because
        # `propose.the_baseline_run_to_beat` now reads it to refuse pairing a
        # fine-tune against a previous fine-tune. Two literals in two modules is
        # how that stops being read.
        provider_name=f"{evals.SANDBOX_ARM_PREFIX}{arm}",
        model=model_name,
        locality="local",
        judge_model=judge_model,
        planned=len(rows),
        rows_available=int(chosen["available"]),
        trivial_baseline=float(trivial_hits / len(rows)),
        trivial_answer=str(trivial_answer),
        latency_budget_ms=None,
    )
    run_id = int(run_row["id"])

    for row in rows:
        answered = answers.get(row["row_index"])
        if answered is None:
            continue
        text = str(answered.get("answer", ""))
        verdicts = evals.grade(row["expected"], text)
        graded_by = str(baseline["metric"])
        if judged is not None:
            # The anchor's own judge's word for this row, obtained before any
            # run was written. The rule verdicts above stay beside it - the
            # judge/rule gap is a signal run_eval keeps, so this keeps it too.
            verdicts[evals.MODEL_GRADED] = bool(judged[row["row_index"]])
            graded_by = f"model:{judge_model}"
        correct = bool(verdicts[str(baseline["metric"])])
        evals.record_row(
            run_id,
            row["row_index"],
            question=row["input"],
            expected=row["expected"],
            answer=text,
            correct=correct,
            verdicts=verdicts,
            failure_mode=(
                None
                if correct
                else evals.bucket(row["expected"], text, verdicts, labels)
            ),
            graded_by=graded_by,
            seconds=float(answered.get("seconds") or 0.0),
        )
    return evals.read(run_id)


def _the_baseline_to_pair_against(
    baseline_run_id: int, thread_id: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The recorded run a new score will be paired against, or a refusal.

    EXTRACTED 2026-08-28, unchanged, so `score` and `score_candidate` cannot
    drift on what makes a baseline pairable. Every refusal here is about the
    RECORDING and none of them is about what is being scored, which is exactly
    why both callers need all five and neither needs a sixth.

    Returns `(baseline, chosen)` - the run, and the rows it actually graded.
    `rows_the_baseline_graded` is what makes the comparison paired: it keys on
    the rows the baseline scored rather than on position, so a re-exported file
    cannot quietly compare row 7 against a different row 7.
    """
    from app.tools import evals

    baseline = evals.read(int(baseline_run_id))
    if not baseline.get("ok"):
        raise NotScorable(
            f"there is no eval run {int(baseline_run_id)} on this machine. "
            "run_eval measures a baseline and read_eval_results lists the runs "
            "this conversation has."
        )
    if int(baseline["thread_id"]) != int(thread_id):
        raise NotScorable(
            f"eval run {int(baseline_run_id)} belongs to conversation "
            f"{baseline['thread_id']} and this call is in {int(thread_id)}. A "
            "measurement made in another conversation is somebody else's, and "
            "pairing against it here would file its rows under this thread."
        )
    if not baseline["complete"]:
        raise NotScorable(
            f"eval run {int(baseline_run_id)} did not finish, so it has no "
            "score to beat. A score from a run that fell over is not a score. "
            "Finish it - run_eval with the same arguments continues where it "
            "stopped - and ask again."
        )
    # A JUDGE-GRADED ANCHOR IS SCORABLE WHEN THE SAME JUDGE IS STILL HERE.
    # This used to be a flat refusal ("two graders... two facts rather than a
    # comparison"), and the refusal's premise was half right: the SANDBOX
    # cannot ask a model anything. But grading never happened in the sandbox
    # - `_store_an_arm` reads the generated answers in THIS process - so the
    # engine can put the same judge on the adapter's rows that graded the
    # baseline's. One instrument, three runs. What still refuses, each for
    # its own sentence: an anchor whose judge is no longer connected, and a
    # judge that would carry the rows off this machine.
    judge_row = None
    if str(baseline["metric"]) == evals.MODEL_GRADED:
        judge_row = _the_judge_the_baseline_used(baseline)

    chosen = rows_the_baseline_graded(baseline)
    if len(chosen["rows"]) > MAX_SCORED_ROWS:
        raise NotScorable(
            f"eval run {int(baseline_run_id)} graded {len(chosen['rows'])} "
            f"rows and one scoring call carries at most {MAX_SCORED_ROWS}. "
            "Every row travels inside the job's own job.json and is a separate "
            "generate() call; measure a baseline over fewer rows, or raise this "
            "bound on purpose rather than by accident."
        )

    return baseline, chosen, judge_row


def _the_judge_the_baseline_used(baseline: dict[str, Any]) -> dict[str, Any]:
    """The connection that can grade the way the anchor was graded.

    The anchor run records the judge's MODEL NAME (`judge_model`), not a
    connection id — connections come and go and a run outlives them — so the
    judge is found among today's connections by that name. The refusals:

    - no connection serves that model any more: naming a different judge
      would be a different instrument wearing the same column, so the person
      reconnects the judge or re-anchors under a rule metric;
    - the only match is remote: this scoring path has no per-actor consent
      plumbing, and a judge off this machine would be sent every question,
      every expected answer and every generation. Local or nothing, said
      plainly, rather than a quiet upload.

    The ACTIVE connection wins a tie so that "the model I am talking to
    right now" is the reading a person would expect.
    """
    from app.providers import store

    wanted = str(baseline.get("judge_model") or "").strip()
    if not wanted:
        raise NotScorable(
            f"eval run {baseline['run_id']} says it was model-graded but "
            "records no judge model, so there is no way to grade these rows "
            "the same way. Re-run the baseline and ask again."
        )
    matches = [
        row for row in store.list_all() if str(row.get("model")) == wanted
    ]
    if not matches:
        raise NotScorable(
            f"eval run {baseline['run_id']} was graded by {wanted}, and no "
            "connection serves that model any more. Grading these rows with "
            "a different judge would be a different instrument wearing the "
            f"same column. Connect {wanted} again, or re-anchor the baseline "
            f"with {evals_metric_names()} and ask again."
        )
    local = [row for row in matches if row.get("kind") == "local"]
    if not local:
        raise NotScorable(
            f"the only connection serving {wanted} is remote, and grading "
            "here would send every question, expected answer and generated "
            "answer off this machine. Connect a local copy of the judge, or "
            f"re-anchor the baseline with {evals_metric_names()}."
        )
    active = [row for row in local if row.get("is_active")]
    if len(local) > 1 and not active:
        # Two local doors to one model name and nothing says which graded the
        # anchor. Picking the newer would be a guess wearing the judge's name.
        raise NotScorable(
            f"{len(local)} local connections serve {wanted} and none is "
            "active, so which one graded the anchor cannot be known. Activate "
            "the one you mean and ask again."
        )
    return active[0] if active else local[0]


def evals_metric_names() -> str:
    """The rule metrics, named the way the old refusal named them."""
    from app.tools import evals

    return f"{evals.EXACT_MATCH} or {evals.CONTAINS}"


def _judge_the_answers(
    judge_row: dict[str, Any],
    rows: list[dict[str, Any]],
    answers: dict[int, dict[str, Any]],
    *,
    arm: str,
) -> dict[int, bool]:
    """Every answered row's verdict from the anchor's own judge, or a refusal.

    Judged IN FULL BEFORE ANYTHING IS RECORDED, which is what lets the
    refusals below say "nothing was recorded" and mean it: run_eval grades
    row by row and can resume, but an arm half-graded by a judge and half by
    nothing is not a run this product should store. The judge is reached
    through `evals.build` — the same seam `run_eval` uses, which is also what
    lets a test script it — and the verdict is read by `evals._read_verdict`,
    whose unreadable answer stops everything for run_eval's reason: reading
    it as either grade would be a reading nobody made.
    """
    from app.tools import evals

    adapter = evals.build(
        judge_row["adapter"], judge_row["base_url"], judge_row["model"]
    )
    key = evals.secrets.get_key(str(judge_row["id"]))
    verdicts: dict[int, bool] = {}
    for row in rows:
        answered = answers.get(row["row_index"])
        if answered is None:
            continue
        answer = str(answered.get("answer", ""))
        text, error, _seconds = evals._ask(
            adapter,
            key,
            evals.JUDGE_SYSTEM,
            evals._judge_question(row["input"], row["expected"], answer),
        )
        if error is not None:
            raise NotScorable(
                f"the grading model stopped answering at row "
                f"{row['row_index']} of the {arm} arm: {error}. Nothing was "
                "recorded — every arm is judged in full before any run is "
                "written."
            )
        verdict = evals._read_verdict(text)
        if verdict is None:
            raise NotScorable(
                f"the grading model was asked for CORRECT or INCORRECT at "
                f"row {row['row_index']} of the {arm} arm and said "
                f"{text[:200]!r}. That is not a verdict, and reading it as "
                "either one would be a reading nobody made. Nothing was "
                "recorded."
            )
        verdicts[row["row_index"]] = verdict
    return verdicts


def score(
    *,
    sandbox_name: str,
    baseline_run_id: int,
    thread_id: int,
    adapter_dir: str | None = None,
    base_model: str | None = None,
    prompt_template: str = DEFAULT_PROMPT_TEMPLATE,
    max_new_tokens: int = 32,
    include_base: bool = True,
    timeout_seconds: int = DEFAULT_SCORING_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Score an adapter where it was made and pair it against the baseline.

    Raises `NotScorable` for everything it will not do, so the tool handler has
    one place to turn a refusal into a message. The work is here rather than in
    the handler for `evals.run`'s reason: a sibling that wants the comparison
    without a registered tool call can have it, and nothing in here can stamp a
    fact because nothing in here holds an instrument.
    """
    from app.tools import evals, sandbox as sandboxes

    baseline, chosen, judge_row = _the_baseline_to_pair_against(
        baseline_run_id, thread_id
    )

    adapter = find_the_adapter(sandbox_name, adapter_dir)
    base = str(base_model or adapter["base_model"] or "").strip()
    if not base:
        raise NotScorable(
            f"{adapter['path']} does not record which base model it was "
            "trained on, and none was named. Pass base_model if you know it; "
            "guessing one produces a number that looks like a score."
        )

    template = str(prompt_template or DEFAULT_PROMPT_TEMPLATE)
    if "{input}" not in template:
        raise NotScorable(
            "prompt_template has no {input} in it, so every row would be sent "
            "the same prompt and the score would be a fact about one question "
            "asked "
            f"{len(chosen['rows'])} times."
        )

    manifest = sandboxes.read_manifest(sandbox_name)
    pinned = manifest.get("pin") or {}
    if SCORING_KIND not in (pinned.get("kinds") or ()):
        raise NotScorable(
            f"sandbox {sandbox_name!r} pins {pinned.get('recipe')!r}, which "
            f"declares {list(pinned.get('kinds') or ())} and not "
            f"{SCORING_KIND!r}. app/jobspec.py refuses a kind a recipe did not "
            "declare, so there is nothing here that could score an adapter. "
            "Make a sandbox on a recipe that can."
        )

    started = time.monotonic()
    ran = sandboxes.run(
        sandbox_name,
        kind=SCORING_KIND,
        config={
            "rows": [
                {"row_index": row["row_index"], "input": row["input"]}
                for row in chosen["rows"]
            ],
            "adapter_dir": adapter["path"],
            "base_model": base,
            "prompt_template": template,
            "max_new_tokens": int(max_new_tokens),
            "include_base": bool(include_base),
        },
        timeout_seconds=int(timeout_seconds),
    )
    run_dir = Path(ran["run_dir"])
    answers = read_predictions(run_dir / PREDICTIONS)
    if not answers:
        return {
            "ok": False,
            "error": "nothing_was_answered",
            "sandbox": sandbox_name,
            "adapter": adapter,
            "detail": (
                "The scoring run produced no answers, so there is nothing to "
                "grade and nothing was written. What the run printed is below; "
                "a refusal from the recipe says what it needed."
            ),
            "exit_code": ran["exit_code"],
            "timed_out": ran["timed_out"],
            "output": ran["output"],
            "run_dir": ran["run_dir"],
            "reach": ran["reach"],
        }

    # BOTH ARMS ARE JUDGED BEFORE EITHER IS RECORDED, when the anchor was
    # model-graded, so a judge that fails or stops making sense leaves the
    # bench exactly as it was rather than holding one arm of a comparison.
    base_answers = read_predictions(run_dir / PREDICTIONS_BASE)
    judge_name = str(judge_row["model"]) if judge_row is not None else None
    judged_adapter = judged_base = None
    if judge_row is not None:
        judged_adapter = _judge_the_answers(
            judge_row, chosen["rows"], answers, arm="adapter"
        )
        if include_base and base_answers:
            judged_base = _judge_the_answers(
                judge_row, chosen["rows"], base_answers, arm="base"
            )

    name_of_this = f"{base} + {Path(adapter['path']).name} (LoRA)"
    adapter_report = _store_an_arm(
        arm="adapter",
        thread_id=int(thread_id),
        baseline=baseline,
        chosen=chosen,
        answers=answers,
        model_name=name_of_this,
        prompt_template=template,
        where=adapter["path"],
        judged=judged_adapter,
        judge_model=judge_name,
    )
    base_report = None
    if include_base and base_answers:
        base_report = _store_an_arm(
            arm="base",
            thread_id=int(thread_id),
            baseline=baseline,
            chosen=chosen,
            answers=base_answers,
            model_name=f"{base} (adapter disabled)",
            prompt_template=template,
            where=base,
            judged=judged_base,
            judge_model=judge_name,
        )

    against_baseline = evals.compare(adapter_report["run_id"], int(baseline_run_id))
    against_base = (
        evals.compare(adapter_report["run_id"], base_report["run_id"])
        if base_report
        else None
    )
    return _scoring_report(
        sandbox_name=sandbox_name,
        adapter=adapter,
        base=base,
        base_was_named=bool(str(base_model or "").strip()),
        include_base=bool(include_base),
        base_answers=len(base_answers or {}),
        baseline=baseline,
        chosen=chosen,
        ran=ran,
        adapter_report=adapter_report,
        base_report=base_report,
        against_baseline=against_baseline,
        against_base=against_base,
        template=template,
        judge=judge_name,
        seconds=round(time.monotonic() - started, 2),
    )


def score_candidate(
    *,
    sandbox_name: str,
    baseline_run_id: int,
    thread_id: int,
    base_model: str,
    prompt_template: str = DEFAULT_PROMPT_TEMPLATE,
    max_new_tokens: int = 32,
    timeout_seconds: int = DEFAULT_SCORING_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Score a model NOBODY HAS TRAINED, on the rows the baseline graded.

    THE OUTCOMES THIS EXISTS FOR SAID A PLAN WOULD STOP ONE STEP SHORT.
    `NO_TRAIN__SWAP_MODEL` and `NO_TRAIN__USE_EXISTING_BASE` both carried the
    same refusal: *"find_models and read_model_config can find a candidate and
    nothing here can connect it or score it, so a plan would stop one step short
    of the number that decides the question."* This is that step, and it does not
    need a connection: the recipe's `eval` kind loads a base model and answers
    with it, which is what `include_base` has always used for the control arm of
    an adapter run. Here that arm is the whole run.

    ONE ARM AND ONE COMPARISON, WHICH IS WHY THIS IS NOT `score()`. That function
    reports two comparisons and `_scoring_report`'s docstring keeps them apart
    because they answer different questions - against the base model on one
    instrument, and against the person's baseline across two. A candidate has no
    adapter to isolate, so there is nothing to compare it against but the
    baseline. Reusing that report would carefully explain a distinction that does
    not exist here.

    `measures` nothing, and neither does its tool. The number this produces is an
    eval run and a paired verdict, not a fact: `model_swap_tried` and
    `quantization_tried` are `source: ask`, and `evidence.may_be_declared_measurable`
    refuses those to any instrument forever. The person still answers the gate
    question - they answer it having just seen the candidate's score on their own
    rows instead of from memory, which is the whole of what this buys.
    """
    from app.tools import evals, sandbox as sandboxes

    baseline, chosen, judge_row = _the_baseline_to_pair_against(
        baseline_run_id, thread_id
    )

    candidate = str(base_model or "").strip()
    if not candidate:
        raise NotScorable(
            "no model was named, and there is no adapter here to read one off. "
            "find_models ranks what fits this machine and read_model_config "
            "reads a real config.json; name the repo you want scored. Guessing "
            "one produces a number that looks like a score."
        )

    template = str(prompt_template or DEFAULT_PROMPT_TEMPLATE)
    if "{input}" not in template:
        raise NotScorable(
            "prompt_template has no {input} in it, so every row would be sent "
            "the same prompt and the score would be a fact about one question "
            f"asked {len(chosen['rows'])} times."
        )

    manifest = sandboxes.read_manifest(sandbox_name)
    pinned = manifest.get("pin") or {}
    if SCORING_KIND not in (pinned.get("kinds") or ()):
        raise NotScorable(
            f"sandbox {sandbox_name!r} pins {pinned.get('recipe')!r}, which "
            f"declares {list(pinned.get('kinds') or ())} and not "
            f"{SCORING_KIND!r}. app/jobspec.py refuses a kind a recipe did not "
            "declare, so there is nothing here that could score a model. Make a "
            "sandbox on a recipe that can."
        )

    started = time.monotonic()
    ran = sandboxes.run(
        sandbox_name,
        kind=SCORING_KIND,
        config={
            "rows": [
                {"row_index": row["row_index"], "input": row["input"]}
                for row in chosen["rows"]
            ],
            # NO `adapter_dir`. The recipe reads an empty one as "there is no
            # adapter", switches its control arm off because there is nothing to
            # be a control FOR, and answers as the bare model into
            # `predictions.jsonl`.
            "adapter_dir": "",
            "base_model": candidate,
            "prompt_template": template,
            "max_new_tokens": int(max_new_tokens),
            "include_base": False,
        },
        timeout_seconds=int(timeout_seconds),
    )
    run_dir = Path(ran["run_dir"])
    answers = read_predictions(run_dir / PREDICTIONS)
    if not answers:
        return {
            "ok": False,
            "error": "nothing_was_answered",
            "sandbox": sandbox_name,
            "candidate": candidate,
            "detail": (
                "The scoring run produced no answers, so there is nothing to "
                "grade and nothing was written. What the run printed is below; a "
                "refusal from the recipe says what it needed."
            ),
            "exit_code": ran["exit_code"],
            "timed_out": ran["timed_out"],
            "output": ran["output"],
            "run_dir": ran["run_dir"],
            "reach": ran["reach"],
        }

    judged = (
        _judge_the_answers(judge_row, chosen["rows"], answers, arm="candidate")
        if judge_row is not None
        else None
    )
    report = _store_an_arm(
        arm="candidate",
        thread_id=int(thread_id),
        baseline=baseline,
        chosen=chosen,
        answers=answers,
        model_name=candidate,
        prompt_template=template,
        where=candidate,
        judged=judged,
        judge_model=str(judge_row["model"]) if judge_row is not None else None,
    )
    against_baseline = evals.compare(report["run_id"], int(baseline_run_id))

    return {
        "ok": True,
        "sandbox": sandbox_name,
        "candidate": candidate,
        "rows_scored": len(answers),
        "rows_the_baseline_graded": len(chosen["rows"]),
        "complete": bool(report["complete"]),
        "candidate_run_id": report["run_id"],
        "baseline_run_id": int(baseline_run_id),
        "against_baseline": against_baseline,
        "seconds": round(time.monotonic() - started, 2),
        "run_dir": ran["run_dir"],
        "exit_code": ran["exit_code"],
        "timed_out": ran["timed_out"],
        "reach": ran["reach"],
        # THE COMPARISON CROSSES TWO INSTRUMENTS AND THE REPLY SAYS SO, because
        # `score()` learned this the hard way and a quieter version of the same
        # number here would be the same defect.
        "what_this_compares": (
            f"{candidate}, answering in a sandbox by greedy continuation, against "
            "your baseline, which went through a chat endpoint under a system "
            "prompt. Both are measurements of your own rows and they are not the "
            "same instrument, so a difference inside what these rows can resolve "
            "is reported as no evidence rather than as a win."
        ),
        "no_fact_was_stamped": (
            "Nothing here opened a gate. Whether you have considered a cheaper "
            "model is yours to say - this is the number to say it against."
        ),
    }


def _scoring_report(**part: Any) -> dict[str, Any]:
    """One scored adapter, described so that neither comparison can be misread.

    Two comparisons come back and they answer different questions. The one
    against the BASE MODEL is measured on one instrument - same weights, same
    tokenizer, same decode, the adapter switched off - and isolates what the
    training did. The one against the BASELINE answers the user's question and
    crosses two instruments: their baseline went through a chat endpoint under
    a system prompt, and this went through a greedy continuation in a sandbox.
    Both are true, neither is the other, and a reply that printed one number
    would be picking which without saying so.
    """
    adapter_report = part["adapter_report"]
    base_report = part["base_report"]
    against_baseline = part["against_baseline"]
    against_base = part["against_base"]
    ran = part["ran"]
    baseline = part["baseline"]
    adapter = part["adapter"]
    include_base = bool(part.get("include_base", True))
    base_answers = int(part.get("base_answers") or 0)

    incomplete = not adapter_report["complete"]
    lead = (
        f"{adapter_report['graded']} of {adapter_report['planned']} rows were "
        "answered before the run stopped, so there is no score for this "
        "adapter - every answered row is on disk and the comparison below did "
        "not run."
        if incomplete
        else f"The adapter scored {adapter_report['score']:.0%} on the "
        f"{adapter_report['graded']} rows eval run {baseline['run_id']} graded."
    )

    # WHICH BASE MODEL THESE DELTAS WERE PUT BACK ON. `_adapter_at` reads
    # `base_model_name_or_path` out of `adapter_config.json` and its docstring
    # says why: *scoring an adapter against a base it was not trained on
    # produces a number that looks exactly like a score.* It does, and until
    # this the two names sat in the payload side by side and nothing compared
    # them - an adapter loaded onto a model of the same architecture it had
    # never seen came back `ok: True` with a score and a verdict, and the words
    # "different base" appeared nowhere. The override is not refused, because a
    # local snapshot directory holding the same weights is exactly what it
    # exists for and nothing here can tell that from a different model. What is
    # refused is saying it quietly.
    trained_on = str(adapter.get("base_model") or "")
    disagreement = (
        bool(part.get("base_was_named"))
        and bool(trained_on)
        and str(trained_on).strip() != str(part["base"]).strip()
    )
    mismatch_line = (
        "THIS IS NOT THE BASE MODEL THE ADAPTER RECORDS IT WAS TRAINED ON. "
        f"Its adapter_config.json says {trained_on!r} and base_model overrode "
        f"that with {part['base']!r}. If those are the same weights under two "
        "names this number is fine; if they are not, LoRA deltas added to a "
        "model that never produced them make a number that looks exactly like "
        "a score and is not one. Nothing here can tell the two cases apart, "
        "which is why it is the first thing said rather than a field."
        if disagreement
        else ""
    )
    # AND WHETHER THE ADAPTER WAS MADE WHERE IT IS BEING SCORED, which was in
    # the payload as `made_in_this_sandbox` and in no sentence. It is a
    # path-containment test and not an environment-identity one - nothing a
    # training run writes records which pinned environment made an adapter - so
    # what it says is what it can support and no more.
    elsewhere_line = (
        ""
        if adapter.get("made_in_this_sandbox", True)
        else (
            "This adapter was not made in the sandbox that scored it: it came "
            f"from {adapter.get('found_by') or 'a path this call named'}, and "
            f"sandbox {part['sandbox_name']!r} supplied the interpreter and the "
            "locked requirements. Nothing written by a training run records "
            "which environment produced an adapter, so this is a statement "
            "about directories and not about versions."
        )
    )

    verdict_line = _labelled(
        "AGAINST YOUR MEASURED BASELINE",
        f"eval run {baseline['run_id']}, "
        f"{baseline.get('provider') or 'a connection'} through a chat endpoint "
        "under a system prompt, against this greedy continuation in a sandbox - "
        "two instruments",
        against_baseline,
        arm_name="the adapter's arm",
    )
    control_line = _labelled(
        "AGAINST THE BASE MODEL",
        "the same weights with the adapter switched off, same tokenizer, same "
        "decode, same prompt - one instrument, and the comparison that isolates "
        "what the training did",
        against_base,
        arm_name="the base model's arm",
    ) or _no_control_arm(include_base, base_answers, ran)

    # AND WHEN THE TWO RESOLVED VERDICTS POINT OPPOSITE WAYS, THAT IS THE
    # HEADLINE. An adapter that beats the baseline and loses to the base model
    # made the model worse; the decoding path made up the difference. Both
    # sentences were already here and a reader met the flattering one first.
    contradiction = _contradiction(against_baseline, against_base)

    return {
        "ok": bool(adapter_report["complete"]),
        "sandbox": part["sandbox_name"],
        "adapter": part["adapter"],
        "base_model": part["base"],
        "scored": {
            "rows": len(part["chosen"]["rows"]),
            "row_indexes_from": (
                f"the rows eval run {baseline['run_id']} graded, read back by "
                "row_index and re-read from " + str(baseline["eval_path"])
            ),
            "eval_path": baseline["eval_path"],
            "eval_fingerprint": part["chosen"]["fingerprint"],
            "metric": baseline["metric"],
            "prompt_template": part["template"],
            "graded_by": (
                f"model:{part['judge']}, in this process - the same judge, "
                "on the same rows, that graded the baseline, with the rule "
                "verdicts stored beside every row. The sandbox generated "
                "text and graded nothing."
                if part.get("judge")
                else "app/tools/evals.py::grade, in this process - the same "
                "function, on the same rows, that graded the baseline. The "
                "sandbox generated text and graded nothing."
            ),
        },
        "adapter_run_id": adapter_report["run_id"],
        "base_run_id": base_report["run_id"] if base_report else None,
        "baseline_run_id": int(baseline["run_id"]),
        "adapter_score": adapter_report,
        "base_score": base_report,
        "against_the_baseline": against_baseline,
        "against_the_base_model": against_base,
        "two_instruments": (
            "The baseline was measured through a connection - a chat endpoint, "
            "under app/tools/measure.py's thin baseline system prompt. This "
            "adapter was scored in a sandbox by greedy continuation of "
            f"{part['template']!r}, with the same rows and the same grader. "
            "Those are two instruments, and the difference between them "
            "carries the decoding path as well as the model. That is why the "
            "base model was scored in here too: against_the_base_model is one "
            "instrument throughout and is the comparison that isolates the "
            "adapter."
        ),
        "base_model_recorded_by_the_adapter": trained_on,
        "base_model_disagrees_with_the_adapter": disagreement,
        "made_in_this_sandbox": adapter.get("made_in_this_sandbox"),
        "measured_nothing": (
            "No fact was stamped. baseline_score, baseline_measured, "
            "trivial_baseline_score and failure_histogram are facts about the "
            "model you are running today; an adapter's score filed under any "
            "of those names would be a real measurement of a different model "
            "under the wrong name. The rows are in this bench's own tables and "
            "the five gates are exactly where they were."
        ),
        "run": {
            "exit_code": ran["exit_code"],
            "timed_out": ran["timed_out"],
            "timeout_seconds": ran["timeout_seconds"],
            "run_dir": ran["run_dir"],
            "interpreter": ran["interpreter"],
            "pinned": ran["pinned"],
            "recipe": ran["recipe"],
            "seconds": part["seconds"],
            "seconds_provenance": "measured with time.monotonic() around the run",
            "log_tail": ran["output"].splitlines()[-20:],
        },
        "reach": ran["reach"],
        # THE ORDER IS THE ARGUMENT. The mismatch first, because a score
        # measured on the wrong weights is not a score and every sentence after
        # it inherits that. Then the contradiction, because a reader who meets
        # a resolved win first has already decided. Then the reading, then each
        # comparison under its own name.
        "says": " ".join(
            piece
            for piece in (
                mismatch_line,
                contradiction,
                lead,
                verdict_line,
                control_line,
                elsewhere_line,
            )
            if piece
        ),
    }


def _labelled(
    name: str, instrument: str, comparison: dict[str, Any] | None, *, arm_name: str
) -> str:
    """One comparison, under its own name, or "" when there is no comparison.

    **THE KEYS WERE LABELLED AND THE PROSE WAS NOT, AND THE PROSE IS THE FIELD
    THAT CARRIES THE CONTRADICTION.** `says` used to be
    `" ".join((lead, verdict_line, control_line))`, and neither comparison said
    which one it was. An adapter that beats the baseline and loses to the base
    model produces `evals.compare`'s own sentence twice - "That is a real
    difference on this eval set" - about opposite findings, so the training had
    made the model worse and the first verdict a reader met was a resolved win.
    `test_opposite_resolved_verdicts_are_the_headline` builds that case out of a
    real eval file rather than out of a stub.

    NON-VACUOUS: swapping `verdict_line` and `control_line` here and running
    `tests/test_an_adapter_is_scored_where_it_was_made.py` gave "Ran 56 tests /
    FAILED (failures=1)", and the one failure was
    `test_each_comparison_is_under_its_own_name`. The other 55 - which include
    all 44 that predate this change - stayed green under the swap.

    THE INCOMPLETE-RUN ADVICE IS ALSO REWRITTEN HERE. `evals.compare` tells a
    caller to finish an unfinished run with `run_eval`, which is correct for
    every run `run_eval` made and impossible for a sandbox arm: `run_eval`
    cannot generate from an adapter and `score_the_adapter` does not resume. So
    an arm that stopped is named and the honest instruction is given.
    """
    if not comparison:
        return ""
    if comparison.get("ok"):
        return f"{name} ({instrument}): {comparison.get('says') or ''}".strip()
    detail = str(comparison.get("detail") or "")
    if comparison.get("error") == "incomplete_run":
        detail = (
            f"{arm_name} stopped before it answered every row, so there is no "
            "score for it and this comparison did not run. The rows it did "
            "answer are on disk in the run directory below. score_the_adapter "
            "does not resume: raise timeout_seconds, or measure a baseline over "
            "fewer rows, and score again - and run_eval cannot finish this arm, "
            "because nothing outside the sandbox can generate from the adapter."
        )
    return f"{name} ({instrument}): {detail}".strip()


def _no_control_arm(include_base: bool, base_answers: int, ran: dict[str, Any]) -> str:
    """Why there is no control arm, distinguishing the three ways there isn't one.

    The sentence this replaces told a caller to *ask again with include_base*
    whatever had happened - including to a caller who had passed
    `include_base=True` and whose control arm had been killed by the timeout.
    Advice that the caller has already taken reads as a bug in them.
    """
    if not include_base:
        return (
            "AGAINST THE BASE MODEL: not measured. include_base was not set, so "
            "nothing here separates what the adapter did from what the base "
            "model already did. Ask again with include_base to get the "
            "comparison that isolates the training."
        )
    if ran.get("timed_out"):
        return (
            "AGAINST THE BASE MODEL: NOT MEASURED, THOUGH YOU ASKED FOR IT. The "
            f"run hit its {ran.get('timeout_seconds')}s bound and was killed "
            f"with {base_answers} control answers written, so the comparison "
            "that isolates the training is missing and the only verdict above "
            "is the one that crosses two instruments. Raise timeout_seconds and "
            "score again."
        )
    return (
        "AGAINST THE BASE MODEL: NOT MEASURED, THOUGH YOU ASKED FOR IT. The run "
        f"finished with exit code {ran.get('exit_code')} and wrote "
        f"{base_answers} control answers, so there is nothing to compare the "
        "adapter against on one instrument. What the run printed is in the log "
        "tail below."
    )


def _contradiction(
    against_baseline: dict[str, Any] | None, against_base: dict[str, Any] | None
) -> str:
    """The one sentence a reader must not have to assemble themselves.

    Only when BOTH comparisons resolved and they point opposite ways. A
    disagreement where one side is `no_evidence` is not a contradiction, it is
    one measurement and one absence, and saying otherwise would be inventing a
    conflict out of a null.
    """
    if not (against_baseline and against_base):
        return ""
    if not (against_baseline.get("ok") and against_base.get("ok")):
        return ""
    if not (against_baseline.get("resolved") and against_base.get("resolved")):
        return ""
    one = float(against_baseline.get("delta") or 0.0)
    other = float(against_base.get("delta") or 0.0)
    if one == 0.0 or other == 0.0 or (one > 0) == (other > 0):
        return ""
    better, worse = (
        ("your measured baseline", "the base model it was trained from")
        if one > 0
        else ("the base model it was trained from", "your measured baseline")
    )
    return (
        "THE TWO COMPARISONS DISAGREE AND BOTH RESOLVED. This adapter is better "
        f"than {better} and worse than {worse}, on the same rows. The one that "
        "isolates the training is the base-model comparison - same weights, "
        "same decode, the adapter switched off - so a win against the baseline "
        "beside a loss against the base model says the decoding path made up a "
        "difference the training did not."
    )


# ---------------------------------------------------------------------------
# The tools.


@tool(
    "list_recipes",
    description=(
        "List the training backends this harness can drive, whether each one's "
        "pinned environment has been built, and how much disk it is using - "
        "measured, not quoted. Use it before offering to train, so the answer "
        "reflects this machine rather than a promise."
    ),
    schema={"type": "object", "properties": {}},
    reads=("recipes",),
    writes=(),
    provides=("training.recipe.list",),
    label="List training backends",
    group="Train",
    verb="list the training backends on this machine",
    order=50,
)
def list_recipes() -> dict[str, Any]:
    names = jobspec.available_recipes()
    reports = [recipe_report(name) for name in names]
    trainers = [r for r in reports if "train" in (r.get("kinds") or [])]
    return {
        "ok": True,
        "count": len(reports),
        "recipes": reports,
        "ready_to_train": [r["name"] for r in trainers if r.get("usable")],
        "source": "the recipes/ directory this harness ships",
        "note": (
            "A recipe with a lockfile and no built environment will refuse to "
            "train and print the exact commands to build it. It will not train "
            "against whatever happens to be installed."
        ),
    }


@tool(
    "start_training",
    description=(
        "Start a real training run through a pinned recipe and stream it into "
        "this conversation. Needs an approval before it can run, because it "
        "occupies the machine's GPU for as long as it takes. Returns the job "
        "id to ask about later; the run survives this app restarting."
    ),
    schema={
        "type": "object",
        "properties": {
            "recipe": {
                "type": "string",
                "description": "Which pinned backend to drive, e.g. 'hf-peft-lora'.",
            },
            "base_model": {
                "type": "string",
                "description": "Hugging Face repo to fine-tune, e.g. 'Qwen/Qwen3-4B'.",
            },
            "dataset_path": {
                "type": "string",
                "description": "Path to a JSONL file on this machine.",
            },
            "text_field": {
                "type": "string",
                "description": "Which JSONL field holds the training text. Default 'text'.",
            },
            "prompt_field": {
                "type": "string",
                "description": (
                    "For prompt/completion data: the field holding the prompt "
                    "(e.g. 'q'). Name it together with completion_field; the "
                    "recipe refuses half a mapping."
                ),
            },
            "completion_field": {
                "type": "string",
                "description": (
                    "For prompt/completion data: the field holding the "
                    "completion (e.g. 'a'). Loss is computed on this half only."
                ),
            },
            "method": {
                "type": "string",
                "description": "Training method. Decides how the run is costed.",
                "enum": ["lora", "qlora", "full"],
            },
            "max_steps": {
                "type": "integer",
                "description": "How many optimizer steps to run.",
            },
            "max_seq_len": {
                "type": "integer",
                "description": (
                    "Sequence length. Sets the activation term, which is "
                    "usually the largest thing in the memory budget."
                ),
            },
            "batch_size": {"type": "integer", "description": "Per-device batch size."},
            "learning_rate": {"type": "number", "description": "Learning rate."},
            "lora_r": {"type": "integer", "description": "LoRA rank."},
            "grad_checkpointing": {
                "type": "boolean",
                "description": (
                    "Recompute activations instead of holding them. Roughly "
                    "30% slower per step and it is what makes a large model "
                    "fit a small card. On by default, and the memory estimate "
                    "assumes whatever is set here."
                ),
            },
            "run_name": {
                "type": "string",
                "description": "A name for this run, so it can be found later.",
            },
            "thread_id": {
                "type": "integer",
                "description": (
                    "Conversation this run belongs to, so its progress appears "
                    "in the right thread."
                ),
            },
            "timeout_seconds": {
                "type": "integer",
                "description": (
                    "Hard wall-clock bound. The whole process tree is killed at "
                    "this point. Default six hours."
                ),
            },
        },
        "required": ["recipe", "base_model", "dataset_path"],
    },
    reads=("recipes", "hardware", "datasets"),
    writes=("jobs", "runs", "events"),
    approval="always",
    provides=("training.run.start",),
    label="Start training",
    group="Train",
    verb="start a training run on this machine",
    order=51,
)
def start_training(
    recipe: str,
    base_model: str,
    dataset_path: str,
    text_field: str = "text",
    prompt_field: str | None = None,
    completion_field: str | None = None,
    method: str = "lora",
    max_steps: int = 20,
    max_seq_len: int = 512,
    batch_size: int = 1,
    learning_rate: float = 2e-4,
    lora_r: int = 16,
    grad_checkpointing: bool = True,
    run_name: str | None = None,
    thread_id: int | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    if not isinstance(recipe, str) or not _RECIPE_NAME.match(recipe or ""):
        return {"ok": False, "error": "unknown_recipe",
                "detail": f"{recipe!r} is not a recipe name",
                "available": jobspec.available_recipes()}
    if method not in ("lora", "qlora", "full"):
        method = "lora"

    data = Path(str(dataset_path))
    if not data.is_file():
        return {
            "ok": False,
            "error": "no_dataset",
            "detail": f"there is no file at {data}",
            "help": (
                "Point at a JSONL file that exists on this machine. Nothing is "
                "queued until there is one, because a job that fails at minute "
                "one on a missing path has still taken the slot."
            ),
        }

    # THE 10% SOMEBODY HAS TO HAVE READ. `docs/diagnosis_engine.yaml` writes it
    # into the recipe of BLOCKED__COLLECT_OR_SYNTHESIZE_DATA - "have a human
    # verify a 10% sample before training on any of it" - and until 2026-08-27
    # it was a sentence in a data file that nothing in this product enforced.
    # Asked here because this is the door: a generated row that never reaches a
    # gate can still reach the weights, and the weights are what ships.
    permitted = datawork.may_be_trained_on(data)
    if not permitted["ok"]:
        return {
            "ok": False,
            "error": permitted["error"],
            "detail": permitted["why"],
            "dataset_path": str(data),
            "generated_rows": permitted["generated_rows"],
            "help": (
                "draw_verification_sample writes the rows out for you to read; "
                "record_verification files what you decided. Nothing was queued "
                "and no GPU was taken."
            ),
        }

    report = recipe_report(recipe)
    if not report.get("usable"):
        return {
            "ok": False,
            "error": "recipe_not_ready",
            "detail": report.get("detail") or "this recipe cannot run",
            "recipe": report,
        }

    # THE EVAL SET THIS CONVERSATION ALREADY MEASURED AGAINST, checked for
    # leakage against what is about to be trained on.
    #
    # WHY HERE, and it is the synthetic wall's argument one door along: a leaked
    # row that never reaches a gate still reaches the weights AND the score, and
    # the score is what gets believed. `check_split_leakage` shipped, and
    # `carve_eval_set` runs it on its own output - but a split somebody made by
    # hand never passes through either. Measured 2026-09-10 on this project's
    # own flagship data: 3 of 24 eval rows were in the train file at up to 0.944
    # similarity, NONE an exact string match, and that contamination was
    # carrying the only statistically resolved training result the project had.
    # Nothing refused it, because nothing was asked.
    #
    # The eval set is not a parameter: it is whichever one THIS THREAD has
    # already measured a baseline on, which is the only one a later comparison
    # can be made against. No thread, or no eval run on it, means the check did
    # not run - and that is REPORTED rather than passed over, because "we looked
    # and it was clean" and "we never looked" are the two states this repository
    # keeps confusing.
    leakage: dict[str, Any] = {"ran": False, "why": "no thread_id, so there is no eval set to check against"}
    if thread_id is not None:
        from app.tools import data as datatools, evals as evaltools

        # The eval sets this conversation has actually run against, newest
        # first. More than one is possible and each is checked: a thread that
        # measured two baselines can be scored on either, so leaking into
        # either one is a leak.
        seen: list[str] = []
        for run in evaltools.runs_in(int(thread_id)):
            candidate = str(run.get("eval_path") or "").strip()
            if candidate and candidate not in seen:
                seen.append(candidate)
        eval_path = seen[0] if seen else ""
        if not eval_path:
            leakage = {
                "ran": False,
                "why": (
                    f"conversation {int(thread_id)} has not measured a baseline "
                    "yet, so there is no eval set to check this data against"
                ),
            }
        else:
            checked, worst, worst_path = [], None, ""
            for candidate in seen:
                try:
                    found = datatools.check_split_leakage(str(data), candidate)
                except Exception as unreadable:  # noqa: BLE001 - an unreadable
                    # eval file is a check that DID NOT RUN, and saying so is
                    # the whole point of this block.
                    checked.append({"eval_path": candidate, "ran": False,
                                    "why": f"could not be read: {unreadable}"})
                    continue
                checked.append({
                    "eval_path": candidate,
                    "ran": bool(found.get("ran")),
                    "leaked_rows": found.get("leaked_rows"),
                    "leak_rate": found.get("leak_rate"),
                    "summary": found.get("summary"),
                })
                if found.get("ran") and (found.get("leaked_rows") or 0) > 0:
                    # A RAW HIT IS NOT YET A REFUSAL. `check_split_leakage`
                    # shingles whole rows, so a repeated instruction makes every
                    # pair look like a near-duplicate: measured on
                    # evals/architecture-json, train against its own carved
                    # valid split reads 0.95 raw and 0.00 on the description
                    # alone. Re-read it with each file's own per-field template
                    # removed, and refuse only on a leak that survives that.
                    # See app/tools/templates.py.
                    import tempfile

                    from app.tools import templates

                    confirmed, note = found, "no repeated template to strip"
                    mine, theirs = templates.affixes_for_pair(data, Path(candidate))
                    if mine or theirs:
                        with tempfile.TemporaryDirectory() as scratch:
                            here = Path(scratch)
                            left = templates.without_template(data, mine, here / "t.jsonl")
                            right = templates.without_template(
                                Path(candidate), theirs, here / "e.jsonl"
                            )
                            try:
                                again = datatools.check_split_leakage(str(left), str(right))
                            except Exception:  # noqa: BLE001 - an unreadable
                                # rewrite is a check that did not run, and the
                                # raw reading stands rather than being trusted.
                                again = None
                        if again is not None and again.get("ran"):
                            note = (
                                f"stripped a repeated template from fields "
                                f"{sorted(mine) or '[]'}/{sorted(theirs) or '[]'}; "
                                f"without it {again.get('leaked_rows')} rows leak"
                            )
                            confirmed = again
                    checked[-1]["template"] = note
                    checked[-1]["leaked_rows_without_template"] = confirmed.get("leaked_rows")
                    if (confirmed.get("leaked_rows") or 0) == 0:
                        continue
                    if worst is None or (confirmed.get("leaked_rows") or 0) > (worst.get("leaked_rows") or 0):
                        worst, worst_path = confirmed, candidate
            leakage = {"ran": True, "eval_sets_checked": checked}
            if worst is not None:
                found, eval_path = worst, worst_path
                return {
                    "ok": False,
                    "error": "eval_set_leaks_into_this_data",
                    "detail": found.get("summary"),
                    "leaking_eval_path": eval_path,
                    "leakage": leakage,
                    "help": (
                        "Nothing was trained. Rows this conversation will be "
                        "SCORED on are in the file it would be trained on, so "
                        "the resulting number would measure memorisation and "
                        "read as improvement. Remove the overlapping rows, or "
                        "carve a fresh split with carve_eval_set, which runs "
                        "this same check on its own output and refuses to write "
                        "a leaking one."
                    ),
                }

    preview = cost_preview(
        base_model,
        method,
        int(max_seq_len),
        int(batch_size),
        bool(grad_checkpointing),
    )

    name = run_name or f"{recipe}:{base_model}"
    run = db.create_run(
        name,
        json.dumps(
            {
                "recipe": recipe,
                "base_model": base_model,
                "method": method,
                "max_steps": int(max_steps),
                "max_seq_len": int(max_seq_len),
                "batch_size": int(batch_size),
                "learning_rate": float(learning_rate),
                "lora_r": int(lora_r),
                "grad_checkpointing": bool(grad_checkpointing),
                "dataset_path": str(data),
            },
            sort_keys=True,
        ),
    )

    config: dict[str, Any] = {
        "base_model": str(base_model),
        "dataset_path": str(data),
        "text_field": str(text_field),
        # The named-column pair. Review (2026-09-01) found CONFIG_KEYS admitting
        # these while nothing ever put them in - a filter cannot add a key.
        **({"prompt_field": str(prompt_field)} if prompt_field else {}),
        **({"completion_field": str(completion_field)} if completion_field else {}),
        "max_steps": int(max_steps),
        "max_seq_len": int(max_seq_len),
        "batch_size": int(batch_size),
        "learning_rate": float(learning_rate),
        "lora_r": int(lora_r),
        "grad_checkpointing": bool(grad_checkpointing),
        "run_id": run["id"],
    }
    if preview["needed_gb"] is not None:
        config["min_free_vram_gb"] = preview["needed_gb"]
    config = {k: v for k, v in config.items() if k in CONFIG_KEYS}

    spec = jobspec.JobSpec(recipe=recipe, kind="train", config=config)
    try:
        jobspec.validate(spec)
    except jobspec.JobRejected as rejected:
        return {"ok": False, "error": "job_rejected", "detail": str(rejected)}

    job = db.create_job(f"run:{run['id']}", spec)

    try:
        bound = max(30, min(int(timeout_seconds), 24 * 3600))
    except (TypeError, ValueError):
        bound = DEFAULT_TIMEOUT_SECONDS

    started_event = events.append(
        "train.started",
        {
            "job_id": job["id"],
            "run_id": run["id"],
            "recipe": recipe,
            "base_model": base_model,
            "method": method,
            "max_steps": int(max_steps),
            "dataset_path": str(data),
            "timeout_seconds": bound,
            "cost_preview": preview,
            "interpreter": report["pinned_environment"]["interpreter"],
        },
        run_id=run["id"],
        thread_id=thread_id,
    )
    start_supervisor(bound)

    return {
        "ok": True,
        "job_id": job["id"],
        "run_id": run["id"],
        "event_id": started_event["id"],
        "recipe": recipe,
        "status": job["status"],
        "run_dir": str(jobspec.run_dir_for(job["id"])),
        "timeout_seconds": bound,
        "cost_preview": preview,
        # REPORTED ON SUCCESS TOO, and that is the point of carrying it here. A
        # clean leak check and a leak check that never ran produce the same
        # silence, and the second one is what let a contaminated split reach the
        # weights. `ran: false` says so, with the reason.
        "leakage": leakage,
        # THE SENTENCE THIS REPLACES WAS TRUE OF A RUNNING JOB AND FALSE OF A
        # QUEUED ONE, and it did not say which it meant. It read: "The run has
        # its own process group, so closing this app does not stop it."
        #
        # A job is created `queued`. `start_supervisor` starts a DAEMON thread,
        # and only when that thread reaches `runner.run_next_job` is a child
        # process spawned with its own group. Until then the job depends
        # entirely on this process staying alive - and a daemon thread dies with
        # it, silently, leaving a row that looks exactly like a job about to
        # start. Measured 2026-09-10: a `start_training` call from a short-lived
        # script left job 5 `queued` with no error anywhere.
        #
        # Through the engine that window is a moment. For anything calling this
        # directly it is permanent, and the old sentence told that caller the
        # opposite of the truth.
        "next": (
            "Ask training_status with this job id for progress. It is QUEUED "
            "until a supervisor picks it up, and the supervisor is a thread in "
            "the process that called this - so a caller that exits straight "
            "away leaves the job queued and unstarted. Once it starts, the run "
            "has its own process group and closing this app does not stop it."
        ),
    }


@tool(
    "training_status",
    description=(
        "Report a training run: whether it is still going, what it has printed "
        "since last time, how long it has taken and what it is spending. Every "
        "new line becomes an event in the conversation, so asking twice does "
        "not repeat itself."
    ),
    schema={
        "type": "object",
        "properties": {
            "job_id": {"type": "integer", "description": "The job to report on."},
            "thread_id": {
                "type": "integer",
                "description": "Conversation the progress belongs in.",
            },
            "tail": {
                "type": "integer",
                "description": "How many log lines to include. Default 20.",
            },
        },
        "required": ["job_id"],
    },
    reads=("jobs", "runs"),
    writes=("events",),
    provides=("training.run.status",),
    label="Training status",
    group="Train",
    verb="report on a training run",
    order=52,
)
def training_status(
    job_id: int, thread_id: int | None = None, tail: int = 20
) -> dict[str, Any]:
    try:
        identifier = int(job_id)
    except (TypeError, ValueError):
        return {"ok": False, "error": "bad_job_id", "detail": f"{job_id!r}"}

    job = db.get_job(identifier)
    if job is None:
        return {"ok": False, "error": "no_such_job", "detail": f"no job {identifier}"}

    run_id = None
    intake = str(job.get("intake_id") or "")
    if intake.startswith("run:"):
        try:
            run_id = int(intake.split(":", 1)[1])
        except ValueError:
            run_id = None

    drained = drain_log(job, run_id=run_id, thread_id=thread_id)

    try:
        bound = max(1, min(int(tail), 200))
    except (TypeError, ValueError):
        bound = 20
    try:
        lines = (
            _log_path_for(job)
            .read_text(encoding="utf-8", errors="replace")
            .splitlines()
        )
    except OSError:
        lines = []

    elapsed = _elapsed_seconds(job)
    finished = job.get("status") == "done"
    return {
        "ok": True,
        "job_id": identifier,
        "run_id": run_id,
        "recipe": job.get("recipe"),
        "status": job.get("status"),
        "state": latest_state(job, lines),
        "exit_code": job.get("exit_code"),
        "finished": finished,
        "succeeded": finished and job.get("exit_code") == 0,
        "created_at": job.get("created_at"),
        "finished_at": job.get("finished_at"),
        "elapsed_seconds": elapsed,
        "elapsed_provenance": "measured" if elapsed is not None else "unknown",
        "events_appended": drained["appended"],
        "latest_progress": latest_progress(lines),
        "log_path": drained["log_path"],
        "log_tail": [line for line in lines[-bound:] if structured(line) is None],
        "metrics": db.metrics_for(run_id) if run_id else [],
        "what_it_costs": (
            "Time on your own machine. No money, and no data left this computer."
        ),
    }


@tool(
    "score_a_candidate_model",
    description=(
        "Score a model nobody has trained - a smaller one, a different one, the "
        "base you would otherwise fine-tune - on exactly the rows your baseline "
        "was graded on, and report the paired difference. Use it when the "
        "question is whether a cheaper or different model would do, before "
        "committing to training anything. It answers in a sandbox and needs no "
        "connection."
    ),
    schema={
        "type": "object",
        "properties": {
            "sandbox": {
                "type": "string",
                "description": (
                    "The sandbox to answer in. It must pin a recipe that "
                    "declares the eval kind; make_sandbox builds one."
                ),
            },
            "baseline_run_id": {
                "type": "integer",
                "description": (
                    "The eval run to pair against. Its rows are the rows this "
                    "scores, so the comparison is paired rather than two "
                    "numbers about two samples."
                ),
            },
            "thread_id": {
                "type": "integer",
                "description": (
                    "The conversation this scoring belongs to. It must be the "
                    "one the baseline run was measured in."
                ),
            },
            "base_model": {
                "type": "string",
                "description": (
                    "The Hugging Face repo to score, e.g. 'Qwen/Qwen3-4B'. "
                    "Required: there is no adapter here to read one off, and a "
                    "guessed model produces a number that looks like a score."
                ),
            },
            "prompt_template": {
                "type": "string",
                "description": (
                    "How a row becomes a prompt, containing {input}. Default is "
                    "the input verbatim."
                ),
            },
            "max_new_tokens": {
                "type": "integer",
                "description": (
                    "How many tokens each answer may be. Default 32. Too few "
                    "truncates a right answer into a wrong one."
                ),
            },
            "timeout_seconds": {
                "type": "integer",
                "description": (
                    "Hard wall-clock bound on the scoring run. Default twenty "
                    "minutes."
                ),
            },
        },
        "required": ["sandbox", "baseline_run_id", "thread_id", "base_model"],
    },
    # `providers` IS NOT IN HERE, for `score_the_adapter`'s reason and one more.
    # `app/tools/propose.py` derives its roster of things that score a model
    # through a CONNECTION from that word, and two tests pin that roster to
    # exactly three names. This scores in a sandbox, so declaring it would be
    # false in the one place the product checks.
    reads=("recipes", "runs", "evals", "datasets", "filesystem"),
    writes=("evals", "filesystem"),
    # NOTHING, AND IT CANNOT BE OTHERWISE. The facts this number informs -
    # `model_swap_tried`, `quantization_tried` - are `source: ask`, and
    # `evidence.may_be_declared_measurable` refuses an `ask` fact to any
    # instrument forever. The person answers the gate; this is what they answer
    # it against.
    measures=(),
    approval="always",
    provides=("models.candidate.score",),
    label="Score a candidate",
    group="Choose",
    verb="score a model nobody trained, on the rows your baseline was graded on",
    order=58,
)
def score_a_candidate_model(
    sandbox: str,
    baseline_run_id: int,
    thread_id: int,
    base_model: str,
    prompt_template: str = DEFAULT_PROMPT_TEMPLATE,
    max_new_tokens: int = 32,
    timeout_seconds: int = DEFAULT_SCORING_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """The one door. Every refusal below names what would have worked."""
    from app.tools import sandbox as sandboxes

    try:
        name = sandboxes.sandbox_name(sandbox, shape=False)
    except sandboxes.SandboxRejected as rejected:
        return {
            "ok": False,
            "error": "sandbox_rejected",
            "detail": str(rejected),
            "help": "Nothing was started. list_sandboxes says what is there.",
        }
    try:
        return score_candidate(
            sandbox_name=name,
            baseline_run_id=int(baseline_run_id),
            thread_id=int(thread_id),
            base_model=base_model,
            prompt_template=prompt_template,
            max_new_tokens=int(max_new_tokens),
            timeout_seconds=int(timeout_seconds),
        )
    except NotScorable as refused:
        return {
            "ok": False,
            "error": "not_scorable",
            "detail": str(refused),
            "help": "Nothing was started and nothing was recorded.",
        }


@tool(
    "score_the_adapter",
    description=(
        "Score a LoRA adapter on the SAME rows a stored eval run graded, "
        "inside the sandbox that trained it, and report the paired comparison "
        "against that baseline. Nothing outside a sandbox can load an adapter: "
        "every scorer in this harness talks to a connection, and an adapter is "
        "a directory of weights. This runs the sandbox's own pinned "
        "environment, generates one answer per row, grades those answers with "
        "the same rule that graded the baseline, and answers the rows a second "
        "time with the adapter switched off so the comparison that isolates "
        "the training is there too. A difference inside what these rows can "
        "resolve is reported as NO EVIDENCE. It stamps no fact: an adapter's "
        "score is not the baseline the gates read. Needs an approval, because "
        "it starts a process on this machine."
    ),
    schema={
        "type": "object",
        "properties": {
            "sandbox": {
                "type": "string",
                "description": (
                    "Which sandbox to score in, exactly as it is named. Its "
                    "recipe must declare the 'eval' kind."
                ),
            },
            "baseline_run_id": {
                "type": "integer",
                "description": (
                    "The completed eval run to beat. Its graded rows ARE the "
                    "rows the adapter is scored on - that is what makes the "
                    "comparison a comparison - and its eval file, columns and "
                    "metric are reused unchanged."
                ),
            },
            "thread_id": {
                "type": "integer",
                "description": (
                    "The conversation this scoring belongs to. It must be the "
                    "one the baseline run was measured in."
                ),
            },
            "adapter_dir": {
                "type": "string",
                "description": (
                    "The adapter to score. Left out, the newest adapter this "
                    "sandbox trained is used, and the reply says which."
                ),
            },
            "base_model": {
                "type": "string",
                "description": (
                    "Override the base model. Default: the one the adapter's "
                    "own adapter_config.json records it was trained on."
                ),
            },
            "prompt_template": {
                "type": "string",
                "description": (
                    "How a row becomes a prompt, containing {input}. Default "
                    "is the input verbatim, because an adapter trained on text "
                    "rows is a continuation model and not a chat endpoint. "
                    "Both arms get the same template."
                ),
            },
            "max_new_tokens": {
                "type": "integer",
                "description": (
                    "How many tokens each answer may be. Default 32. Too few "
                    "truncates a right answer into a wrong one."
                ),
            },
            "include_base": {
                "type": "boolean",
                "description": (
                    "Also answer the same rows with the adapter disabled, on "
                    "the same loaded weights. On by default: it is the only "
                    "comparison that isolates what the training did."
                ),
            },
            "timeout_seconds": {
                "type": "integer",
                "description": (
                    "Hard wall-clock bound on the scoring run. The whole "
                    "process tree is killed at this point. Default twenty "
                    "minutes."
                ),
            },
        },
        "required": ["sandbox", "baseline_run_id", "thread_id"],
    },
    # `providers` IS DELIBERATELY NOT IN HERE and its absence is the whole
    # point of this tool. A tool that reads `providers` sends rows to a
    # connection; this one sends them to a process in a sandbox, which is why
    # it can be pointed at an adapter at all. `app/tools/propose.py` derives
    # its roster of scorers from that word, so declaring it would be false in
    # the one place the product checks.
    reads=("recipes", "runs", "evals", "datasets", "filesystem"),
    writes=("evals", "filesystem"),
    # NOTHING. Read THE FOUR THINGS THAT MAKE THE NUMBER HONEST, item four.
    measures=(),
    approval="always",
    provides=("training.adapter.score",),
    label="Score the adapter",
    group="Train",
    verb="score this adapter against the baseline, in the sandbox that made it",
    order=57,
)
def score_the_adapter(
    sandbox: str,
    baseline_run_id: int,
    thread_id: int,
    adapter_dir: str | None = None,
    base_model: str | None = None,
    prompt_template: str = DEFAULT_PROMPT_TEMPLATE,
    max_new_tokens: int = 32,
    include_base: bool = True,
    timeout_seconds: int = DEFAULT_SCORING_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """The one door. Every refusal below names what would have worked."""
    from app.tools import sandbox as sandboxes

    try:
        name = sandboxes.sandbox_name(sandbox, shape=False)
    except sandboxes.SandboxRejected as rejected:
        return {
            "ok": False,
            "error": "sandbox_rejected",
            "detail": str(rejected),
            "help": "Nothing was started. list_sandboxes says what is there.",
        }
    try:
        return score(
            sandbox_name=name,
            baseline_run_id=int(baseline_run_id),
            thread_id=int(thread_id),
            adapter_dir=adapter_dir,
            base_model=base_model,
            prompt_template=prompt_template,
            max_new_tokens=int(max_new_tokens),
            include_base=bool(include_base),
            timeout_seconds=int(timeout_seconds),
        )
    except NotScorable as refused:
        return {
            "ok": False,
            "error": "not_scorable",
            "detail": str(refused),
            "help": (
                "Nothing was started and nothing was recorded. An adapter is "
                "scored on the rows a completed eval run already graded, so "
                "measure a baseline with run_eval first if there is not one."
            ),
        }
    except sandboxes.SandboxRejected as rejected:
        return {
            "ok": False,
            "error": "sandbox_rejected",
            "detail": str(rejected),
            "help": "Nothing was started. list_sandboxes says what is there.",
        }
    except (TypeError, ValueError) as unusable:
        return {
            "ok": False,
            "error": "bad_arguments",
            "detail": str(unusable),
        }


def latest_progress(lines: list[str]) -> dict[str, Any] | None:
    """The last progress line the job printed, whenever it printed it.

    Read from the log rather than from whatever this call happened to drain.
    Those are different questions and answering the second one makes the
    product go blank exactly when it matters: a status call that drains nothing
    because it already drained everything used to report `null` progress for a
    finished run, so the last thing a user saw was "no progress yet" next to a
    completed job.
    """
    for line in reversed(lines):
        payload = structured(line)
        if payload is not None and payload.get("kind") in ("progress", "finished"):
            return payload
    return None


def latest_state(job: dict[str, Any], lines: list[str]) -> str:
    """`queued`, `running` or `done` - what is actually happening.

    The jobs table could not answer this on its own until 2026-09-02:
    `db.next_queued_job` selected the oldest queued row and never marked it,
    so `status` read `queued` for the entire life of a six-hour job and only
    flipped at the end. Reporting that word to a user watching their GPU at
    100% is the product lying quietly, so this derived the state from the
    thing that was actually moving - whether the job had written to its log.

    The fix landed where the docstring said it belonged, in `app/db.py`, as a
    claimed row. The stored status is now true while the job runs, so it is
    read first. The log-line derivation is kept underneath it for the rows
    that predate the claim, where `queued` is what a running job still says.
    """
    stored = job.get("status")
    if stored in ("done", "running"):
        return str(stored)
    return "running" if lines else "queued"


def _elapsed_seconds(job: dict[str, Any]) -> float | None:
    """Wall clock from the job row, in seconds. `None` when it cannot be read.

    SQLite writes `CURRENT_TIMESTAMP` in UTC without a zone marker, so both
    ends are read as UTC deliberately rather than as local time - reading the
    start as local and the end as UTC is how an elapsed figure comes out four
    hours wrong on this machine and looks plausible.
    """
    started = _parse_stamp(job.get("created_at"))
    if started is None:
        return None
    ended = _parse_stamp(job.get("finished_at")) or datetime.now(timezone.utc)
    return round((ended - started).total_seconds(), 1)


def _parse_stamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


__all__ = [
    "CONFIG_KEYS",
    "DEFAULT_PROMPT_TEMPLATE",
    "DEFAULT_SCORING_TIMEOUT_SECONDS",
    "DEFAULT_TIMEOUT_SECONDS",
    "EVENT_PREFIX",
    "MAX_SCORED_ROWS",
    "NotScorable",
    "PREDICTIONS",
    "PREDICTIONS_BASE",
    "SCORING_KIND",
    "cost_preview",
    "drain_log",
    "find_the_adapter",
    "latest_progress",
    "latest_state",
    "list_recipes",
    "read_predictions",
    "recipe_report",
    "rows_the_baseline_graded",
    "score",
    "score_the_adapter",
    "start_supervisor",
    "start_training",
    "structured",
    "training_status",
    "wait_for_supervisors",
]
