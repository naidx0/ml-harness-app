"""Quantise a Hugging Face causal LM with bitsandbytes, and score what it made.

Read `recipes/hf-peft-lora/entrypoint.py` first: this file follows the same
shape deliberately, because the two recipes are read together and a reader who
knows one should not have to learn a second set of conventions. `--kind` and
`--job-json` are the only arguments, everything the caller chose arrives in
`job.json`, progress goes to stdout one line at a time, and the script hands
itself to its own pinned interpreter before importing anything heavy.

## WHAT THIS RECIPE IS FOR

`NO_TRAIN__QUANTIZE` is the ML ledger's answer to *"the model is good enough
and too expensive to serve."* Until now the outcome led nowhere, and its own
recorded reason said why: *"a quantising backend - a recipe, not a proposer."*
This is that backend.

## THE ONE DESIGN DECISION THAT DECIDES WHETHER THE NUMBER MEANS ANYTHING

`hf-peft-lora` states the rule: the control arm and the treated arm must differ
by ONE thing. It achieves that with `disable_adapter()` - literally the same
loaded tensors.

Quantisation cannot be switched off on a loaded model, so the control here is
the same checkpoint loaded a second time WITHOUT `BitsAndBytesConfig`. Every
other lever is pinned equal across the arms, and the pinning is the substance
of this file:

* the same tokenizer object, loaded once and shared;
* the same rows, in the same order, from `config.rows`;
* the same prompt template;
* the same greedy decode (`do_sample=False`) and the same `max_new_tokens`;
* the same `torch.manual_seed`;
* **the same compute dtype.** This one is the trap. bitsandbytes dequantises
  to `bnb_4bit_compute_dtype` to do the matmul, so a 4-bit arm computing in
  float16 against a control arm computing in float32 would differ by the
  quantisation AND by the arithmetic. The control is loaded at the quantised
  arm's compute dtype on purpose, and the resolved dtype of both arms is
  reported so a reader can check that rather than trust it.

What remains different is the numeric representation of the weights. That is
the thing under test, and it is the only thing.

## IT GENERATES AND IT DOES NOT GRADE

Answers go to `predictions.jsonl` and `predictions_base.jsonl` as text.
`app/tools/evals.py::grade` turns them into verdicts, in the harness, with the
same normalisation that graded the baseline. A grader in here would be a second
instrument, and two scores from two instruments are two facts rather than a
comparison.

## AND IT REPORTS WHAT QUANTISING ACTUALLY BOUGHT

Accuracy is only half the question. Nobody quantises for accuracy - they
quantise for memory and for speed, and a recipe that reported only a score
would leave the person unable to answer the question that sent them here. So
both arms report peak VRAM and total generate seconds, measured, and the
convert step reports bytes on disk. Every one of those is measured on this
machine in this run; none of them is a projection.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

RECIPE_DIR = Path(__file__).resolve().parent

#: Progress lines carry this prefix so a supervisor can pick structured events
#: out of a log that is also meant to be read by a person.
EVENT_PREFIX = "MLH_EVENT "

PREDICTIONS = "predictions.jsonl"

#: The control arm's file: the same checkpoint, unquantised.
PREDICTIONS_BASE = "predictions_base.jsonl"

#: Where `--kind convert` writes the quantised weights.
QUANTIZED_DIR = "quantized"

EVAL_STRIDE = 10


def vram_now() -> dict[str, float] | None:
    """What the CARD holds, not what this process allocated.

    Lifted deliberately from `recipes/hf-peft-lora`, where it was added after
    run 2 reported `peak_vram_gb 4.17` and then died CUDA out of memory on an
    8 GiB card whose preflight had recorded 6.98 GB free. The allocator
    high-water understated real demand by at least 2.8 GB and nothing in the
    record could say so.

    IT MATTERS MORE HERE THAN THERE. This recipe's whole output is a LATENCY
    RATIO, and a latency measured while the allocator is thrashing is not a
    latency - it is a measurement of the thrash. `max_memory_allocated`, the
    only VRAM figure this recipe recorded before today, cannot distinguish the
    two, so a 3B fp16 arm crawling on an 8 GiB card would have published a
    confident cost ratio built out of paging.
    """
    import torch

    if not torch.cuda.is_available():
        return None
    free, total = torch.cuda.mem_get_info(0)
    gib = 1024 ** 3
    reserved = torch.cuda.memory_reserved(0) / gib
    total_gb = round(total / gib, 2)
    return {
        "free_gb": round(free / gib, 2),
        "total_gb": total_gb,
        "reserved_gb": round(reserved, 2),
        "allocated_gb": round(torch.cuda.memory_allocated(0) / gib, 2),
        # THE VOID CONDITION, DECIDED BY THE RECIPE AND NOT BY A READER.
        # Registered before the 3B arm ran: reserved above the device total
        # means the allocator holds more than the card has, and any wall-clock
        # figure from that state is void rather than adjusted. Computing it
        # here is the difference between a rule and a rule applied by eye to a
        # column of numbers after seeing them.
        "over_committed": bool(round(reserved, 2) > total_gb),
    }



def _declared_defaults() -> dict:
    """This recipe's own `[defaults]` table, or {} if it has none."""
    try:
        import tomllib

        manifest = RECIPE_DIR / "recipe.toml"
        return dict(tomllib.loads(manifest.read_text(encoding="utf-8")).get("defaults") or {})
    except Exception:  # noqa: BLE001 - a missing table is a fallback, not a failure
        return {}


def venv_python() -> Path:
    if os.name == "nt":
        return RECIPE_DIR / ".venv" / "Scripts" / "python.exe"
    return RECIPE_DIR / ".venv" / "bin" / "python"


def in_pinned_venv() -> bool:
    try:
        return Path(sys.prefix).resolve() == (RECIPE_DIR / ".venv").resolve()
    except OSError:
        return False


def emit(kind: str, **payload) -> None:
    body = dict(payload)
    body["kind"] = kind
    print(EVENT_PREFIX + json.dumps(body, default=str), flush=True)


def bootstrap(argv: list[str]) -> int:
    python = venv_python()
    if not python.is_file():
        print(
            "REFUSED: this recipe's pinned environment has not been built.\n"
            f"Expected an interpreter at: {python}\n"
            "\n"
            "Build it from the repository root:\n"
            "  python -m venv recipes/hf-quantize/.venv\n"
            "  recipes/hf-quantize/.venv/Scripts/python.exe -m pip install \\\n"
            "      --index-url https://download.pytorch.org/whl/cu124 torch==2.6.0\n"
            "  recipes/hf-quantize/.venv/Scripts/python.exe -m pip install \\\n"
            "      -r recipes/hf-quantize/requirements.lock\n"
            "\n"
            "torch is installed first and from a different index on purpose:\n"
            "PyPI's Windows wheel is CPU-only, and bitsandbytes 4-bit needs\n"
            "CUDA. Nothing is quantised until this exists, because a run that\n"
            "quietly used whatever happened to be importable would not be\n"
            "reproducible.",
            file=sys.stderr,
        )
        emit("refused", reason="pinned environment not built", expected=str(python))
        return 2

    emit("bootstrap", interpreter=str(python), recipe="hf-quantize")
    print(f"handing off to the pinned interpreter: {python}", flush=True)
    completed = subprocess.run([str(python), str(Path(__file__).resolve())] + argv)
    return completed.returncode


def preflight() -> tuple[bool, list[dict]]:
    """Everything that can fail before a GPU-hour is spent, checked first.

    `bitsandbytes` 4-bit is CUDA-only. A CPU-only torch here does not run
    slowly - it raises, or worse, silently falls back - so both are refusals
    with the command that fixes them rather than a warning nobody reads.
    """
    checks: list[dict] = []

    def record(name: str, ok: bool, detail: str) -> bool:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        return bool(ok)

    ok = True
    try:
        import torch
    except Exception as missing:  # noqa: BLE001
        record("torch imports", False, f"{missing}")
        return False, checks
    ok &= record("torch imports", True, f"torch {torch.__version__}")

    cuda_build = bool(getattr(torch.version, "cuda", None))
    ok &= record(
        "torch is a CUDA build",
        cuda_build,
        f"torch.version.cuda={torch.version.cuda!r}"
        if cuda_build
        else "this is the CPU-only wheel from PyPI. Reinstall with "
        "--index-url https://download.pytorch.org/whl/cu124 torch==2.6.0",
    )
    available = bool(torch.cuda.is_available())
    ok &= record(
        "a CUDA device is visible",
        available,
        torch.cuda.get_device_name(0) if available else "torch.cuda.is_available() is False",
    )
    if available:
        major, minor = torch.cuda.get_device_capability(0)
        # bitsandbytes' 4-bit kernels need Turing or newer.
        good = (major, minor) >= (7, 5)
        ok &= record(
            "compute capability is 7.5 or newer",
            good,
            f"compute capability {major}.{minor}"
            + ("" if good else " - bitsandbytes 4-bit needs Turing (7.5) or newer"),
        )

    try:
        import bitsandbytes

        ok &= record("bitsandbytes imports", True, f"bitsandbytes {bitsandbytes.__version__}")
    except Exception as missing:  # noqa: BLE001
        ok &= record("bitsandbytes imports", False, f"{missing}")

    try:
        import transformers

        ok &= record("transformers imports", True, f"transformers {transformers.__version__}")
    except Exception as missing:  # noqa: BLE001
        ok &= record("transformers imports", False, f"{missing}")

    return bool(ok), checks


def eval_rows(config: dict) -> list[dict]:
    """The rows to answer, exactly as the harness chose them.

    Copied in substance from `hf-peft-lora` and for its reason: `row_index` in
    this product counts ELIGIBLE rows and that rule lives in
    `app/tools/evals.py::_plan`. A recipe that opened the eval file and counted
    for itself would disagree about which row is row 7 the first time a row was
    missing a column, and every paired comparison built on it would silently be
    pairing different questions.
    """
    rows = config.get("rows")
    if not isinstance(rows, list) or not rows:
        raise SystemExit(
            "REFUSED: this eval was given no rows. `config.rows` is a list of "
            "{'row_index': int, 'input': str} chosen by the harness; nothing "
            "here reads your eval file, because which row is row 7 is decided "
            "in one place and this is not it."
        )
    out: list[dict] = []
    seen: set[int] = set()
    for position, row in enumerate(rows):
        if not isinstance(row, dict) or "row_index" not in row:
            raise SystemExit(
                f"REFUSED: row {position} of config.rows has no 'row_index'. "
                "Numbering it by position would pair it against whatever "
                "happened to be seventh somewhere else."
            )
        try:
            index = int(row["row_index"])
        except (TypeError, ValueError):
            raise SystemExit(
                f"REFUSED: row {position} has row_index={row['row_index']!r}, "
                "which is not a row number."
            ) from None
        if index in seen:
            raise SystemExit(
                f"REFUSED: row_index {index} appears twice in config.rows. One "
                "row cannot have two answers under one index."
            )
        seen.add(index)
        out.append({"row_index": index, "input": str(row.get("input", ""))})
    return out


def _quant_settings(config: dict) -> dict:
    """The quantisation the caller asked for, over this recipe's declared table."""
    declared = _declared_defaults()

    def pick(name, fallback):
        value = config.get(name)
        return declared.get(name, fallback) if value is None else value

    bits = int(pick("bits", 4))
    if bits not in (4, 8):
        raise SystemExit(
            f"REFUSED: bits={bits}. bitsandbytes offers 4 and 8; a number that "
            "is neither would silently become one of them."
        )
    quant_type = str(pick("quant_type", "nf4"))
    if bits == 4 and quant_type not in ("nf4", "fp4"):
        raise SystemExit(
            f"REFUSED: quant_type={quant_type!r}. 4-bit bitsandbytes has two, "
            "'nf4' and 'fp4'."
        )
    return {
        "bits": bits,
        "quant_type": quant_type,
        "double_quant": bool(pick("double_quant", True)),
        "compute_dtype": str(pick("compute_dtype", "float16")),
    }


def _bnb_config(settings: dict):
    import torch
    from transformers import BitsAndBytesConfig

    compute = getattr(torch, settings["compute_dtype"])
    if settings["bits"] == 8:
        return BitsAndBytesConfig(load_in_8bit=True), compute
    return (
        BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type=settings["quant_type"],
            bnb_4bit_use_double_quant=settings["double_quant"],
            bnb_4bit_compute_dtype=compute,
        ),
        compute,
    )


def _dir_bytes(path: Path) -> int:
    total = 0
    for entry in path.rglob("*"):
        if entry.is_file():
            total += entry.stat().st_size
    return total


def convert(config: dict, run_dir: Path) -> int:
    """Quantise the model and write it, reporting what it cost and what it saved."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    base_model = str(config.get("base_model") or "").strip()
    if not base_model:
        print("REFUSED: config is missing 'base_model'", file=sys.stderr)
        emit("refused", reason="missing base_model")
        return 4

    settings = _quant_settings(config)
    quant_config, compute = _bnb_config(settings)
    out_dir = run_dir / QUANTIZED_DIR

    emit("convert_loading", base_model=base_model, **settings)
    print(
        f"quantising {base_model} to {settings['bits']}-bit "
        f"({settings['quant_type'] if settings['bits'] == 4 else 'int8'})",
        flush=True,
    )

    started = time.monotonic()
    torch.cuda.reset_peak_memory_stats(0)
    model = AutoModelForCausalLM.from_pretrained(
        base_model, quantization_config=quant_config, device_map={"": 0}
    )
    tokenizer = AutoTokenizer.from_pretrained(base_model)
    loaded = round(time.monotonic() - started, 2)
    peak_gb = round(torch.cuda.max_memory_allocated(0) / (1024 ** 3), 3)

    out_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(out_dir))
    tokenizer.save_pretrained(str(out_dir))

    written = _dir_bytes(out_dir)
    elapsed = round(time.monotonic() - started, 2)
    emit(
        "convert_finished",
        seconds=elapsed,
        load_seconds=loaded,
        peak_vram_gb=peak_gb,
        peak_vram_provenance="torch.cuda.max_memory_allocated during this load",
        quantized_dir=str(out_dir),
        bytes_on_disk=written,
        bytes_provenance="measured by stat() over the files this step wrote",
        base_model=base_model,
        **settings,
    )
    print(
        f"quantised in {elapsed}s, peak VRAM {peak_gb} GB, "
        f"{written / (1024 ** 2):.1f} MB written to {out_dir}. "
        "Nothing here scored anything.",
        flush=True,
    )
    return 0


def evaluate(config: dict, run_dir: Path) -> int:
    """Answer the rows quantised, and again unquantised, in one process.

    The two arms are two loads of the SAME checkpoint. Everything a reload can
    change is pinned equal above; what is left is the numeric representation of
    the weights, which is the thing under test.
    """
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    started = time.monotonic()
    rows = eval_rows(config)
    base_model = str(config.get("base_model") or "").strip()
    if not base_model:
        raise SystemExit(
            "REFUSED: config is missing 'base_model'. This recipe scores a "
            "checkpoint against itself; without one there is nothing to load."
        )
    # THIS RECIPE DECLARES `eval`, SO score_the_adapter CAN REACH IT.
    #
    # It drives whatever recipe the sandbox was pinned to, and a sandbox pinned
    # to this one would arrive here carrying `adapter_dir`. Nothing below loads
    # an adapter: the two arms are two loads of the same base checkpoint. So a
    # silent pass would answer every row with the UNADAPTED model and report it
    # as the adapter's score - a real number about a different model, which is
    # the exact failure `_adapter_at` reads adapter_config.json to prevent.
    # Refusing is the only honest option, and it names the recipe that can.
    if config.get("adapter_dir"):
        raise SystemExit(
            "REFUSED: this job names an adapter_dir and this recipe cannot load "
            "one. hf-quantize scores a checkpoint against a quantised copy of "
            "ITSELF; it has no peft in its lockfile and no code path that "
            "applies deltas. Scoring here would answer every row with the "
            "unadapted base and report it as the adapter's score. Score an "
            "adapter in the environment that trained it - hf-peft-lora "
            "declares the same eval kind for exactly that reason."
        )
    template = str(config.get("prompt_template") or "{input}")
    if "{input}" not in template:
        raise SystemExit(
            "REFUSED: prompt_template does not contain {input}, so every row "
            "would be sent the same prompt and the score would be a fact about "
            "one question asked fifty times."
        )
    declared = _declared_defaults()
    max_new_tokens = max(1, int(config.get("max_new_tokens") or declared.get("max_new_tokens", 64)))
    max_seq_len = max(8, int(config.get("max_seq_len") or declared.get("max_seq_len", 512)))
    stop_at_newline = bool(config.get("stop_at_newline", True))
    include_base = bool(config.get("include_base", True))
    seed = int(config.get("seed", 0))

    settings = _quant_settings(config)
    quant_config, compute = _bnb_config(settings)

    emit(
        "eval_loading",
        base_model=base_model,
        rows=len(rows),
        include_base=include_base,
        **settings,
    )
    print(
        f"scoring {len(rows)} rows: {base_model} at {settings['bits']}-bit"
        + (" and at full precision" if include_base else ""),
        flush=True,
    )

    # ONE tokenizer for both arms. Two would be a second difference between
    # them, and the whole point of doing both here is that there is only one.
    tokenizer = AutoTokenizer.from_pretrained(base_model)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    def answer_all(arm: str, model, path: Path) -> tuple[int, float]:
        answered = 0
        spent = 0.0
        model.eval()
        with open(path, "w", encoding="utf-8") as handle:
            for position, row in enumerate(rows):
                prompt = template.replace("{input}", row["input"])
                encoded = tokenizer(
                    prompt,
                    return_tensors="pt",
                    truncation=True,
                    max_length=max_seq_len,
                ).to(model.device)
                torch.manual_seed(seed)
                at = time.monotonic()
                with torch.no_grad():
                    produced = model.generate(
                        **encoded,
                        max_new_tokens=max_new_tokens,
                        do_sample=False,
                        pad_token_id=tokenizer.pad_token_id,
                    )
                took = time.monotonic() - at
                spent += took
                text = tokenizer.decode(
                    produced[0][encoded["input_ids"].shape[1]:],
                    skip_special_tokens=True,
                ).strip()
                if stop_at_newline and "\n" in text:
                    text = text.split("\n", 1)[0].strip()
                handle.write(
                    json.dumps(
                        {
                            "row_index": row["row_index"],
                            "answer": text,
                            "seconds": round(took, 3),
                            "arm": arm,
                        }
                    )
                    + "\n"
                )
                answered += 1
                if position % EVAL_STRIDE == 0:
                    emit(
                        "eval_progress",
                        arm=arm,
                        done=answered,
                        of=len(rows),
                        # BOTH ARMS, EVERY STRIDE. The void rule reads the
                        # BASE arm, but recording only that arm would make
                        # "the quantised arm was fine" an assumption.
                        vram=vram_now(),
                    )
        return answered, round(spent, 2)

    torch.cuda.reset_peak_memory_stats(0)
    quantised = AutoModelForCausalLM.from_pretrained(
        base_model, quantization_config=quant_config, device_map={"": 0}
    )
    quantised_dtype = str(next(quantised.parameters()).dtype)
    answered, quant_seconds = answer_all("quantized", quantised, run_dir / PREDICTIONS)
    quant_peak_gb = round(torch.cuda.max_memory_allocated(0) / (1024 ** 3), 3)
    del quantised
    torch.cuda.empty_cache()

    answered_base = 0
    base_seconds = 0.0
    base_peak_gb = None
    base_dtype = None
    if include_base:
        print("scoring the same rows again at full precision", flush=True)
        torch.cuda.reset_peak_memory_stats(0)
        # THE CONTROL LOADS AT THE QUANTISED ARM'S COMPUTE DTYPE. bitsandbytes
        # dequantises to `compute` to do the matmul, so a control in float32
        # would differ by the arithmetic as well as by the weights.
        full = AutoModelForCausalLM.from_pretrained(
            base_model, torch_dtype=compute, device_map={"": 0}
        )
        base_dtype = str(next(full.parameters()).dtype)
        answered_base, base_seconds = answer_all("base", full, run_dir / PREDICTIONS_BASE)
        base_peak_gb = round(torch.cuda.max_memory_allocated(0) / (1024 ** 3), 3)
        del full
        torch.cuda.empty_cache()

    elapsed = round(time.monotonic() - started, 2)
    emit(
        "eval_finished",
        seconds=elapsed,
        answered=answered,
        answered_base=answered_base,
        predictions=str(run_dir / PREDICTIONS),
        predictions_base=str(run_dir / PREDICTIONS_BASE) if include_base else None,
        base_model=base_model,
        quantized_dtype=quantised_dtype,
        base_dtype=base_dtype,
        quantized_peak_vram_gb=quant_peak_gb,
        base_peak_vram_gb=base_peak_gb,
        quantized_generate_seconds=quant_seconds,
        base_generate_seconds=base_seconds,
        vram_at_end=vram_now(),
        measurement_provenance=(
            "peak VRAM from torch.cuda.max_memory_allocated around each arm, "
            "which is an ALLOCATOR high-water and not device occupancy; "
            "free/total/reserved/allocated from mem_get_info and the caching "
            "allocator, per stride and at the end, for both arms; "
            "generate seconds summed per row in this process"
        ),
        max_new_tokens=max_new_tokens,
        prompt_template=template,
        **settings,
    )
    print(
        f"wrote {answered} answers to {run_dir / PREDICTIONS}"
        + (f" and {answered_base} to {run_dir / PREDICTIONS_BASE}" if include_base else "")
        + ". Nothing here graded anything.",
        flush=True,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", required=True)
    parser.add_argument("--job-json", required=True)
    args = parser.parse_args()

    if not in_pinned_venv():
        return bootstrap(["--kind", args.kind, "--job-json", args.job_json])

    job_json = Path(args.job_json)
    job = json.loads(job_json.read_text(encoding="utf-8"))
    config = job.get("config") or {}
    run_dir = job_json.parent

    print(f"recipe hf-quantize, kind {args.kind}, interpreter {sys.executable}", flush=True)

    ok, checks = preflight()
    emit("preflight", ok=ok, checks=checks)
    for check in checks:
        mark = "ok " if check["ok"] else "RED"
        print(f"preflight {mark} {check['check']}: {check['detail']}", flush=True)
    if not ok:
        print(
            "REFUSED: a preflight check is red, so nothing was quantised or "
            "scored. The detail above says which one and what to do about it.",
            file=sys.stderr,
        )
        return 3

    if args.kind == "convert":
        return convert(config, run_dir)
    if args.kind == "eval":
        return evaluate(config, run_dir)
    print(f"REFUSED: this recipe does not implement kind {args.kind!r}", file=sys.stderr)
    emit("refused", reason=f"unimplemented kind {args.kind}")
    return 5


if __name__ == "__main__":
    raise SystemExit(main())
