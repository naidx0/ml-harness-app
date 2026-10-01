"""What a run has to record before anybody can say what it cost.

## The state this exists to end, measured 2026-09-09

The harness holds **21 trained adapters**. Joining every `job.json` that names a
base to every `job.log` that records a peak gives **33 runs** - the join works,
and 18 of those are SmolLM2-1.7B. But joining the five fields somebody needs in
order to PRICE a run - base, sequence, batch, checkpointing, peak - gives
**five records, and those five are only TWO distinct configurations**, one of
them a fourfold replicate:

    SmolLM2-135M  seq 256  batch 4  checkpointing on   peak 0.73   (x4)
    SmolLM2-135M  seq 512  batch 1  checkpointing on   peak 0.63

Twenty-one adapters, two priced points. The binding field is
**`grad_checkpointing`, absent from 28 of the 33** joinable runs, with
`max_seq_len` absent from 19 - and checkpointing is not a knob among knobs, it
is a precondition: with it off a 135M model does not fit at sequence 2048 at
all. A record that omits it does not describe a configuration, it describes a
family of them.

## Why a schema rather than a better reader

Three readers have now tried to reconstruct this from what is on disk and all
three got a different number. One globbed `runs/*/job.json` and found ZERO,
because the records live one level deeper at `runs/*/job_*/job.json`. One could not
find the peak in the log at all, and I explained that by saying no summary line
exists - which is FALSE, measured after I had written it down: all 17 logs
carrying a peak carry both a per-step stream and an end-of-run summary event, 0
carry only one. I had a working reader and invented a reason for someone else's
broken one. One - this author - looked for `gradient_checkpointing` and
reported the field missing everywhere, when it is spelled `grad_checkpointing`
and is present five times.

**A reader cannot reliably reconstruct what a writer never joined.** Each of
those three failures is a different reader making a different reasonable guess
about a shape nobody declared. This module declares it.

## What it will not do

`price` returns `None` when a field is absent rather than filling it in. That is
the same refusal `app/feasibility.py` makes when it is given a parameter count
and no geometry, and for the same reason: a priced run with an assumed sequence
length is a number about a configuration that was never executed, and it would
enter the harness's own error history as evidence. Unmeasurable renders unknown.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

#: THE CONTRACT. A run record answers "what did this cost on this machine", and
#: it cannot answer it while any of these is missing.
#:
#: `grad_checkpointing` is in the list for a reason the other four are not: it
#: is a PRECONDITION rather than a setting. The three that move memory on this
#: card are sequence, batch and checkpointing; rank, target modules and
#: optimizer state are rounding error. Recording the small ones and omitting the
#: decisive one is how twenty-one adapters became two priced points.
THE_FIELDS: tuple[str, ...] = (
    "base_model",
    "max_seq_len",
    "batch_size",
    "grad_checkpointing",
    "peak_vram_gb",
)

#: The spellings each field has actually appeared under on disk. This is a
#: migration aid and not a licence: `describe` writes the canonical name, and
#: this map exists so `price` can read the records that already exist.
#:
#: `gradient_checkpointing` is NOT here, deliberately. It is what this author
#: guessed the key was, found nothing, and reported the field absent from every
#: record. No writer has ever emitted it, so admitting it would be encoding a
#: reader's mistake as a format.
THE_SPELLINGS: dict[str, tuple[str, ...]] = {
    "base_model": ("base_model", "model", "base"),
    "max_seq_len": ("max_seq_len", "max_seq_length", "seq_len"),
    "batch_size": ("batch_size", "per_device_train_batch_size"),
    "grad_checkpointing": ("grad_checkpointing",),
}

#: The marker every runner event is prefixed with.
THE_EVENT_MARKER = "MLH_EVENT"

#: Which event's peak is a TRAINING cost, in preference order. `finished` is a
#: training job's own summary; `progress` is a step inside one. `eval_finished`
#: is deliberately last: it is a real measurement of a different quantity, and a
#: record that took it silently would price inference as training.
THE_PEAK_COMES_FROM = ("finished", "progress", "eval_finished")



def _read(config: dict[str, Any], name: str) -> Any:
    """One field out of a config, under any spelling a writer has used.

    `base_model` is normalised to the bare repo name it was written with; the
    rest come back as they were stored. Nothing is coerced - a sequence length
    stored as the string "512" is returned as the string, because silently
    turning it into an int would be this module guessing at the exact point it
    exists to stop guessing.
    """
    for spelling in THE_SPELLINGS.get(name, (name,)):
        if config.get(spelling) not in (None, ""):
            return config[spelling]
    return None


def describe(config: dict[str, Any], peak_vram_gb: float | None) -> dict[str, Any]:
    """The record a runner writes, in canonical spellings.

    A RUNNER CALLS THIS, not a reader. The whole argument of this module is that
    the join belongs to whoever had all five values in hand at once, and that is
    the process that ran the job.
    """
    record = {name: _read(config, name) for name in THE_FIELDS if name != "peak_vram_gb"}
    record["peak_vram_gb"] = peak_vram_gb
    return record


def _describing(record: dict, kind, peak_from) -> dict:
    """`kind` and `peak_from` ride beside the five, and are not among them.

    They are not in `THE_FIELDS` on purpose: a record missing them is still a
    priceable record, it just cannot be filtered by quantity. Putting them in
    the contract would make every historical run unpriceable to buy a label.
    """
    record["kind"] = kind
    record["peak_from"] = peak_from
    return record


def missing_from(record: dict[str, Any] | None) -> tuple[str, ...]:
    """Which of `THE_FIELDS` this record cannot answer for.

    A field present but null is missing. That is not pedantry: the two model
    configs that failed a sibling gate today carried `revision` as a key with
    `None` beside it, and a key whose value is absent is a field nobody filled
    in wearing the appearance of one somebody did.
    """
    if not record:
        return THE_FIELDS
    return tuple(name for name in THE_FIELDS if record.get(name) in (None, ""))


def price(run_dir: Path) -> dict[str, Any] | None:
    """The joined record for one run directory, or `None` if it cannot be made.

    Reads what is on disk today - `job.json` for the configuration and
    `job.log` for the peak - so the runs that exist can be priced without being
    re-run. Returns `None` rather than a partial record: a caller that wants to
    know WHY calls `missing_from` on `read(run_dir)`.
    """
    record = read(run_dir)
    return None if missing_from(record) else record


def read(run_dir: Path) -> dict[str, Any] | None:
    """Everything about this run that is on disk, with the gaps left as `None`."""
    job = Path(run_dir) / "job.json"
    if not job.is_file():
        return None
    try:
        spec = json.loads(job.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    config = spec.get("config") or {}
    value, where = peak_and_where(Path(run_dir) / "job.log")
    return _describing(describe(config, value), spec.get("kind"), where)


def peak_in(log: Path) -> float | None:
    """The largest peak this run ever reported, or `None` if it reported none."""
    value, _kind = peak_and_where(log)
    return value


def peak_and_where(log: Path) -> tuple[float | None, str | None]:
    """The peak, and WHICH KIND OF EVENT reported it.

    TWO QUANTITIES WORE ONE FIELD NAME AND IT COST TWO LANES AN EVENING.
    `peak_vram_gb` is emitted by three kinds of event - `progress` (4,061 of
    them), `finished` (17) and `eval_finished` (16) - and **every one of the 33
    logs that carries a peak carries more than one kind**. An eval peak is
    weights plus about a fifth of a gigabyte: no optimizer state, no gradients,
    no retained activations. A training peak is the thing an estimator predicts.
    Reading one as the other is a like-for-like violation that no amount of
    care at the call site can catch, because the number arrives wearing the
    right name.

    `finished` wins when it is there, because a training job's cost is what it
    peaked at while training. Measured over all 33: where a `finished` peak
    exists, `max()` over every event equals it exactly - so this changes no
    number already reported. What it changes is the **16 logs with a peak and
    no `finished` event**, where `max()` was returning an eval or progress peak
    and calling it the run's cost.

    A null is not a reading. `peak_vram_gb` is
    `torch.cuda.max_memory_allocated(0)` **or None when CUDA is unavailable**,
    so a CPU run emits the field with nothing in it - a measurement-shaped
    absence, which is the exact case `missing_from` treats as missing.
    """
    try:
        text = Path(log).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, None

    seen: dict[str, list[float]] = {}
    for line in text.splitlines():
        marker = line.find(THE_EVENT_MARKER)
        if marker < 0:
            continue
        try:
            event = json.loads(line[marker + len(THE_EVENT_MARKER):].strip())
        except (ValueError, TypeError):
            continue
        if not isinstance(event, dict):
            continue
        value = event.get("peak_vram_gb")
        if value is None:
            continue
        kind = str(event.get("kind") or ("progress" if "step" in event else "unknown"))
        seen.setdefault(kind, []).append(float(value))

    if not seen:
        return None, None
    for preferred in THE_PEAK_COMES_FROM:
        if seen.get(preferred):
            return max(seen[preferred]), preferred
    kind = max(seen, key=lambda k: max(seen[k]))
    return max(seen[kind]), kind


def every_run(runs_root: Path) -> Iterator[Path]:
    """Every directory holding a `job.json`, at whatever depth it sits.

    NOT `runs/*/job.json`. The records live at `runs/<run>/job_<n>/job.json`,
    one level deeper than the obvious glob, and a reader that assumed otherwise
    reported zero runs on a tree holding thirty-three.
    """
    for job in sorted(Path(runs_root).rglob("job.json")):
        yield job.parent
