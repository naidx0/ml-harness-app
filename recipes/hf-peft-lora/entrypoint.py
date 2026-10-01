"""Drive a LoRA supervised fine-tune through Hugging Face peft + trl.

Read `recipes/demo-metrics/entrypoint.py` for the shape every recipe follows:
`--kind` and `--job-json` are the only arguments, everything the caller chose
arrives in `job.json`, and progress goes to stdout one line at a time because
the runner streams stdout to the job log and a job that prints nothing for six
hours cannot be told apart from a job that is stuck.

Three things this file does that the demo recipe does not.

**It runs in its own pinned environment, or it does not run.** `unsloth` pins
`trl<=0.24.0` and `transformers<=5.5.0`; asking for `trl>=1.0` alongside it
silently downgrades Unsloth by a year rather than failing. One shared
environment cannot serve both backends, so each recipe owns a `.venv` beside
its `requirements.lock`. `jobspec.Recipe.interpreter` is still the harness's
own `sys.executable` - changing that is `app/jobspec.py`'s call and not this
file's - so the first thing this script does is hand itself to the pinned
interpreter and inherit its streams. The child's stdout is the parent's, so
streaming is unaffected, and the runner's `taskkill /T` owns the whole tree.

**It refuses to start on a red preflight.** The single worst trap for the
person this product is for: `pip install torch` on Windows yields a 122 MB
CPU-only wheel, the CUDA build is a 2.75 GB wheel from a different index, and a
user who gets the wrong one completes every step, clicks train, and gets a
silently CPU-bound run with no error at all. Twenty times slower and no
message. So a CPU-only torch is a refusal here, with the exact command to fix
it, and every other check that can fail before a GPU-hour is spent runs first.

**It reports cost as it goes.** Elapsed, steps done against steps asked for,
tokens per second and peak VRAM, emitted as `MLH_EVENT` lines that
`app/tools/training.py` turns into events in the conversation. The cost of a
local run is your time and your machine, not a bill, and the product says so
in those words rather than implying a dollar figure it cannot know.

## AND IT SCORES WHAT IT TRAINED, WHICH IS WHY `kinds` HAS TWO ENTRIES

`--kind eval` loads a LoRA adapter onto its base model **in this same pinned
environment** and generates one answer per row. That is the only place in this
product where an adapter can be put in front of text at all: every registered
tool that scores a model sends rows to a `providers` connection, and
`app/providers` has two kinds of connection, neither of which is a directory of
safetensors. The environment that trained it already has `peft` and
`transformers`; it is where the scoring belongs.

Three properties of the eval path decide whether the number it produces is
worth anything, so they are stated here and enforced below.

**IT GENERATES AND IT DOES NOT GRADE.** Answers go to `predictions.jsonl` as
text. `app/tools/evals.py::grade` turns them into verdicts, in the harness,
with the same normalisation that graded the baseline. A grader in here would be
a second instrument, and two scores from two instruments are two facts rather
than a comparison.

**THE ROWS ARRIVE IN `job.json` AND ARE NEVER RE-DERIVED FROM A FILE.**
`row_index` in this product counts ELIGIBLE rows - rows with both the input and
the expected column - from zero, in file order, and that rule lives in
`app/tools/evals.py::_plan`. A recipe that opened the eval file and counted for
itself would disagree about which row is row 7 the first time a row was missing
a column, and every paired comparison built on it would silently be pairing
different questions.

**THE CONTROL ARM IS THE SAME LOADED WEIGHTS WITH THE ADAPTER SWITCHED OFF.**
`include_base` runs the rows a second time inside `PeftModel.disable_adapter()`,
so the base and the adapter differ by the LoRA deltas and by nothing else - not
the tokenizer, not the dtype, not the decoding, not the prompt. That is the
only comparison in this product that isolates what the training did.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


RECIPE_DIR = Path(__file__).resolve().parent

#: Progress lines carry this prefix so a supervisor can pick structured events
#: out of a log that is also meant to be read by a person. Everything without
#: it is ordinary output and is treated as such.
EVENT_PREFIX = "MLH_EVENT "


def _declared_defaults() -> dict:
    """This recipe's own `[defaults]` table, or {} if it has none.

    Read with the standard library only: this file runs inside the recipe's
    pinned virtualenv, which holds torch and peft and nothing this harness
    chose to add for it.
    """
    try:
        import tomllib

        from pathlib import Path as _Path

        manifest = _Path(__file__).resolve().parent / "recipe.toml"
        return dict(tomllib.loads(manifest.read_text(encoding="utf-8")).get("defaults") or {})
    except Exception:  # noqa: BLE001 - a missing or damaged table is a fallback, not a failure
        return {}


def venv_python() -> Path:
    """The interpreter this recipe is pinned to."""
    if os.name == "nt":
        return RECIPE_DIR / ".venv" / "Scripts" / "python.exe"
    return RECIPE_DIR / ".venv" / "bin" / "python"


def in_pinned_venv() -> bool:
    try:
        return Path(sys.prefix).resolve() == (RECIPE_DIR / ".venv").resolve()
    except OSError:
        return False


def emit(kind: str, **payload) -> None:
    """One structured progress line, plus a human line for the log reader."""
    body = dict(payload)
    body["kind"] = kind
    print(EVENT_PREFIX + json.dumps(body, default=str), flush=True)


def post(base_url: str, token: str | None, path: str, payload: dict) -> dict | None:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        base_url + path,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        # A metric that could not be posted is a lost metric, not a lost run.
        # The log still has it, and the log is what the transcript reads.
        print(f"note: could not post to {path}: {exc}", flush=True)
        return None


# ---------------------------------------------------------------------------
# Stage one: get into the pinned environment, or explain exactly why not.


def bootstrap(argv: list[str]) -> int:
    python = venv_python()
    if not python.is_file():
        print(
            "REFUSED: this recipe's pinned environment has not been built.\n"
            f"Expected an interpreter at: {python}\n"
            "\n"
            "Build it from the repository root:\n"
            "  uv venv --python 3.11 recipes/hf-peft-lora/.venv\n"
            "  uv pip install --python recipes/hf-peft-lora/.venv/Scripts/python.exe \\\n"
            "      --index-url https://download.pytorch.org/whl/cu124 torch==2.6.0\n"
            "  uv pip sync --python recipes/hf-peft-lora/.venv/Scripts/python.exe \\\n"
            "      recipes/hf-peft-lora/requirements.lock\n"
            "\n"
            "It is about 4.8 GB on disk, measured on the machine this lock was\n"
            "resolved on. Nothing is trained until it exists: a run that quietly\n"
            "used whatever happened to be importable would not be reproducible,\n"
            "and an unreproducible training run is worse than none.",
            file=sys.stderr,
        )
        emit("refused", reason="pinned environment not built", expected=str(python))
        return 2

    emit("bootstrap", interpreter=str(python), recipe="hf-peft-lora")
    print(f"handing off to the pinned interpreter: {python}", flush=True)
    # Streams are inherited, so the runner's log keeps receiving lines live and
    # `taskkill /F /T` on the runner's child still reaches this grandchild.
    completed = subprocess.run([str(python), str(Path(__file__).resolve())] + argv)
    return completed.returncode


# ---------------------------------------------------------------------------
# Stage two: the preflight doctor.


def preflight(config: dict, require_cuda: bool = True) -> tuple[bool, list[dict]]:
    """Every check that can fail before a GPU-hour is spent. Red means stop.

    `require_cuda=False` is the eval path and it is a different trade rather
    than a relaxation. Training on the CPU-only wheel is the trap this whole
    function exists for: twenty times slower, no error, and a person who
    completed every step. Generating a few hundred short answers on a CPU is
    slow and it is not silent - the sandbox bounds it with a wall-clock timeout
    and the result reports which device answered - so a missing GPU stops a
    fine-tune and only annotates a score.
    """
    checks: list[dict] = []

    def record(name, ok, detail, fatal=True):
        checks.append({"check": name, "ok": bool(ok), "detail": detail,
                       "fatal": bool(fatal)})
        return ok

    try:
        import torch
    except Exception as exc:  # noqa: BLE001
        record("torch importable", False, f"{type(exc).__name__}: {exc}")
        return False, checks

    record("torch importable", True, f"torch {torch.__version__}")

    cuda_ok = bool(torch.cuda.is_available())
    record(
        "cuda available",
        cuda_ok,
        (
            f"torch.version.cuda={torch.version.cuda}, "
            f"torch.cuda.is_available()={cuda_ok}"
        )
        + ("" if require_cuda else ". This run scores rather than trains, so "
           "the CPU is slow and not silent - it is annotated, not refused.")
        + (
            ""
            if cuda_ok
            else (
                ". This is the CPU-only wheel. Reinstall from "
                "https://download.pytorch.org/whl/cu124 - training on CPU here "
                "would be roughly twenty times slower and would look like it "
                "was working."
            )
        ),
        fatal=require_cuda,
    )
    if not cuda_ok:
        # Everything below reads the device. There is nothing to read.
        return (not require_cuda), checks

    name = torch.cuda.get_device_name(0)
    major, minor = torch.cuda.get_device_capability(0)
    record("gpu detected", True, f"{name}, compute capability {major}.{minor}")

    free_bytes, total_bytes = torch.cuda.mem_get_info(0)
    free_gb = round(free_bytes / (1024 ** 3), 2)
    total_gb = round(total_bytes / (1024 ** 3), 2)
    needed = config.get("min_free_vram_gb")
    record(
        "free vram",
        needed is None or free_gb >= float(needed),
        f"{free_gb} GB free of {total_gb} GB total"
        + ("" if needed is None else f"; this run asked for {needed} GB"),
    )

    if major == 7 and minor == 5:
        record(
            "turing caveats",
            True,
            "compute capability 7.5: no FlashAttention-2 and no native bf16, "
            "so this run uses fp16. That is a real limit of this card, not a "
            "setting to change.",
            fatal=False,
        )

    ok = all(check["ok"] for check in checks if check["fatal"])
    return ok, checks


# ---------------------------------------------------------------------------
# Stage two: the run.


def vram_now() -> dict[str, float] | None:
    """What the CARD holds, not what this process allocated.

    THE DISTINCTION COST A RUN AND TWO WRONG DIAGNOSES. Run 2 reported
    `peak_vram_gb 4.17` - a `max_memory_allocated` high-water - and then failed
    with CUDA out of memory on an 8 GiB card whose preflight had recorded 6.98
    GB free at the start. So the allocator figure understated the real demand by
    at least 2.8 GB, and nothing in the record could say so: every VRAM number
    this project has registered a band against is `max_memory_allocated`.

    `mem_get_info` answers the other question - free and total on the DEVICE,
    including every other process and every reserved-but-unallocated block. The
    preflight already called it and only printed it; it belongs in the progress
    events and the finished record too, because a run that dies at step 25 needs
    the occupancy AT step 25 and not at step 0.
    """
    import torch

    if not torch.cuda.is_available():
        return None
    free, total = torch.cuda.mem_get_info(0)
    gib = 1024 ** 3
    return {
        "free_gb": round(free / gib, 2),
        "total_gb": round(total / gib, 2),
        # RESERVED is the number that explains an OOM the allocated figure
        # cannot: the caching allocator holds blocks it is not currently using,
        # and they are unavailable to anyone including itself for a different
        # shape.
        "reserved_gb": round(torch.cuda.memory_reserved(0) / gib, 2),
        "allocated_gb": round(torch.cuda.memory_allocated(0) / gib, 2),
    }


def load_rows(
    path: Path,
    text_field: str,
    prompt_field: str | None = None,
    completion_field: str | None = None,
) -> list[dict]:
    """Read a JSONL dataset without pulling the whole thing into memory twice.

    Deliberately small and explicit rather than a `datasets.load_dataset` call:
    the failure this avoids is a silent one, where a file with the wrong column
    name trains happily on an empty string.

    `prompt_field`/`completion_field` map a dataset's own column names onto
    the prompt/completion pair. Found missing on the first end-to-end walk
    (2026-09-01): the harness's own carve/synthesize chain preserves the
    dataset's columns — q and a, in that walk — and this recipe could read
    only `text` or a literal prompt/completion pair, so the product's own
    pipeline produced a file its own recipe refused. Named columns, never
    guessed: a recipe that guessed which column is the prompt would train on
    the wrong half silently, which is the exact failure this loader exists
    to make loud.
    """
    if bool(prompt_field) != bool(completion_field):
        # Half a mapping is the silent-wrong-column failure this loader
        # exists to make loud: with only one named, the loader used to fall
        # back to `text` as if nothing had been said.
        raise SystemExit(
            f"prompt_field={prompt_field!r} and completion_field="
            f"{completion_field!r}: name both columns or neither. Nothing "
            "was trained."
        )
    rows: list[dict] = []
    with open(path, encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError as exc:
                raise SystemExit(f"{path}:{number} is not valid JSON: {exc}")
            if not isinstance(row, dict):
                raise SystemExit(f"{path}:{number} is not a JSON object")
            if prompt_field and completion_field:
                if prompt_field in row and completion_field in row:
                    rows.append(
                        {
                            "prompt": str(row[prompt_field]),
                            "completion": str(row[completion_field]),
                        }
                    )
                else:
                    raise SystemExit(
                        f"{path}:{number} is missing {prompt_field!r} or "
                        f"{completion_field!r}, which the config named. "
                        "Nothing was trained."
                    )
            elif text_field in row:
                rows.append({"text": str(row[text_field])})
            elif "prompt" in row and "completion" in row:
                rows.append(
                    {"prompt": str(row["prompt"]), "completion": str(row["completion"])}
                )
            else:
                raise SystemExit(
                    f"{path}:{number} has neither a {text_field!r} field nor a "
                    "prompt/completion pair. Name the columns with "
                    "prompt_field/completion_field in the config. "
                    "Nothing was trained."
                )
    if not rows:
        raise SystemExit(f"{path} has no usable rows. Nothing was trained.")
    return rows


def train(config: dict, run_dir: Path, base_url: str, token: str | None) -> int:
    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import TrainerCallback
    from trl import SFTConfig, SFTTrainer

    started = time.monotonic()
    run_id = config.get("run_id")
    # THE RECIPE'S OWN DECLARED DEFAULTS, read from the recipe.toml beside this
    # file. They live there rather than only here because a second reader needs
    # them - the journey overview offers them into the step's form so a person
    # can see and change the LoRA rank and the learning rate instead of
    # discovering the knobs exist by reading a trainer. The literals below are
    # the fallback, so a recipe.toml without the table trains identically.
    declared = _declared_defaults()
    base_model = config["base_model"]
    dataset_path = Path(config["dataset_path"])
    text_field = str(config.get("text_field", "text"))
    max_steps = int(config.get("max_steps", declared.get("max_steps", 20)))
    batch_size = int(config.get("batch_size", 1))
    max_length = int(config.get("max_seq_len", declared.get("max_seq_len", 512)))
    learning_rate = float(config.get("learning_rate", declared.get("learning_rate", 2e-4)))
    lora_r = int(config.get("lora_r", declared.get("lora_r", 16)))
    logging_steps = max(1, int(config.get("logging_steps", 1)))

    prompt_field = config.get("prompt_field")
    completion_field = config.get("completion_field")
    rows = load_rows(
        dataset_path,
        text_field,
        str(prompt_field) if prompt_field else None,
        str(completion_field) if completion_field else None,
    )
    dataset = Dataset.from_list(rows)
    emit(
        "dataset",
        rows=len(rows),
        path=str(dataset_path),
        columns=sorted(dataset.column_names),
    )
    print(f"dataset: {len(rows)} rows from {dataset_path}", flush=True)

    output_dir = run_dir / "adapter"
    args = SFTConfig(
        output_dir=str(output_dir),
        max_steps=max_steps,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=int(config.get("grad_accum", 1)),
        learning_rate=learning_rate,
        logging_steps=logging_steps,
        max_length=max_length,
        packing=False,
        # Whatever the estimate was computed with. `app/tools/training.py`
        # passes the same value into the memory preview and into this config,
        # so the two cannot disagree - estimating with checkpointing and then
        # training without it is how a "fits" becomes an OOM at minute twenty.
        gradient_checkpointing=bool(config.get("grad_checkpointing", True)),
        save_strategy="no",
        report_to=[],
        # The runner merges stderr into stdout, and a progress bar writes to
        # stderr with a carriage return and no newline - so its output lands in
        # the middle of the next real line. `app/tools/training.py` copes with
        # that, and a log a person is meant to read should not need coping
        # with. The step lines below say the same thing in words.
        disable_tqdm=True,
        # Turing has no native bf16. fp16 is the honest choice on sm_75 and
        # the preflight already said so out loud.
        fp16=torch.cuda.is_available(),
        bf16=False,
        seed=int(config.get("seed", 0)),
        optim=str(config.get("optim", "adamw_torch")),
        dataset_text_field="text",
    )

    peft_config = LoraConfig(
        r=lora_r,
        lora_alpha=int(config.get("lora_alpha", declared.get("lora_alpha", lora_r * 2))),
        lora_dropout=float(config.get("lora_dropout", declared.get("lora_dropout", 0.05))),
        bias="none",
        task_type="CAUSAL_LM",
    )

    # `num_tokens` ARRIVES PER STEP AND NOT IN THE FINAL METRICS. The first
    # version of this recorded it from `result.metrics`, where it is absent, so
    # the finished record carried `num_tokens: null` - a field added to make a
    # peak interpretable, shipped uninterpretable. Caught by running it.
    seen = {"num_tokens": None}

    class Progress(TrainerCallback):
        """Cost and progress, as they happen, into the log and the engine."""

        def on_log(self, args, state, control, logs=None, **kwargs):
            if not logs:
                return
            if logs.get("num_tokens") is not None:
                seen["num_tokens"] = logs["num_tokens"]
            elapsed = round(time.monotonic() - started, 2)
            step = int(state.global_step)
            peak_gb = (
                round(torch.cuda.max_memory_allocated(0) / (1024 ** 3), 2)
                if torch.cuda.is_available()
                else None
            )
            # Still the PROCESS high-water mark, as it has always been. The
            # reset before `train()` would otherwise make these lines mean
            # something narrower from this commit onwards, with nothing saying
            # so - a field quietly changing definition mid-history.
            if peak_gb is not None and seen.get("load_peak_gb") is not None:
                peak_gb = max(peak_gb, seen["load_peak_gb"])
            payload = {
                "step": step,
                "total_steps": max_steps,
                # OCCUPANCY BESIDE ALLOCATION, every logged step.
                "vram": vram_now(),
                "elapsed_seconds": elapsed,
                "peak_vram_gb": peak_gb,
            }
            payload.update(
                {k: v for k, v in logs.items() if isinstance(v, (int, float))}
            )
            emit("progress", **payload)
            loss = logs.get("loss")
            if loss is not None:
                print(
                    f"step {step}/{max_steps} loss {float(loss):.4f} "
                    f"elapsed {elapsed}s peak_vram {peak_gb} GB",
                    flush=True,
                )
                if run_id:
                    post(
                        base_url,
                        token,
                        f"/api/runs/{run_id}/metrics",
                        {"step": step, "name": "loss", "value": float(loss)},
                    )

    print(f"loading {base_model}", flush=True)
    emit("loading", base_model=base_model)
    # ## A 4-BIT BASE, AND WHY IT IS OFF UNLESS ASKED FOR
    #
    # Measured on this card 2026-09-09, fp16 LoRA, gradient checkpointing on:
    # SmolLM2-1.7B peaked at 6.65 / 6.96 / 7.05 GiB at sequence 256 / 384 / 512.
    # An 8 GiB card with a desktop on it has about 6.5 GiB to give, so THE
    # LARGEST BASE THIS RECIPE COULD TRAIN IN FP16 WAS ALREADY OVER THE LINE AT
    # THE SHORTEST SEQUENCE ANYBODY WOULD USE. Every estimate that said a 1.5B
    # model fits here was computed for a 4-bit base, and this recipe had no way
    # to load one - `bitsandbytes` was not in the lockfile and nothing here
    # named it. So the plan and the recipe disagreed, and the recipe was right.
    #
    # `model=base_model` as a string lets TRL construct the model, which is the
    # simplest thing and cannot carry a quantization config. Passing the object
    # is the only way in, so the string path is kept EXACTLY as it was for the
    # default and the object path is taken only when asked.
    #
    # DEFAULT FALSE, deliberately. Quantising changes the numbers a run
    # produces, and flipping the default would silently make new runs
    # incomparable with old ones. (This paragraph used to add "every adapter on
    # this disk was trained fp16" - measured false on 2026-09-10, see the dtype
    # note above: they were trained fp32 because nothing passed a dtype.)
    # ## THE DTYPE THIS RECIPE CLAIMED AND DID NOT PASS
    #
    # `fp16=True` is set in the trainer args above, the comment beside it
    # explains that Turing has no native bf16, and the paragraph below used to
    # say "every adapter on this disk was trained fp16". **All of that was
    # false.** `model=base_model` hands TRL a STRING, TRL calls
    # `from_pretrained` without a dtype, and transformers then defaults to
    # fp32 - it does not honour the checkpoint's own `torch_dtype` unless asked.
    #
    # MEASURED 2026-09-10 on this machine, `SmolLM2-135M`:
    #     from_pretrained(name)                     -> torch.float32
    #     from_pretrained(name, dtype=float16)      -> torch.float16
    #     the checkpoint's config says              -> bfloat16
    #
    # So `fp16=True` was autocast over fp32 master weights: every adapter here
    # labelled fp16 was trained with a base at FOUR bytes per parameter, not
    # two, and every memory estimate this project made for the fp16 path priced
    # the base at half what it cost. That is most of an evening's worth of
    # "the estimator is optimistic".
    #
    # `float16` and not `auto`, deliberately: `auto` would take the bfloat16 in
    # the checkpoint's config, and this card is sm_75 with no native bf16 -
    # which is the same reason `fp16=True` is set rather than `bf16=True`.
    base_dtype_name = str(config.get("base_dtype", "float16")).strip() or "float16"
    base_dtype = getattr(torch, base_dtype_name, None)
    if base_dtype is None:
        print(
            f"REFUSED: base_dtype {base_dtype_name!r} is not a torch dtype. "
            "Nothing was trained; guessing one would train at a precision "
            "nobody asked for and report the peak as though they had.",
            file=sys.stderr,
        )
        emit("refused", reason="unknown base_dtype", base_dtype=base_dtype_name)
        return 7

    load_in_4bit = bool(config.get("load_in_4bit", False))
    model_for_trainer = base_model
    if not load_in_4bit:
        from transformers import AutoModelForCausalLM

        model_for_trainer = AutoModelForCausalLM.from_pretrained(
            base_model, dtype=base_dtype
        )
        emit("base_loaded", base_model=base_model, dtype=str(base_dtype),
             quantized=False,
             says=("loaded at the precision this recipe declares; before "
                   "2026-09-10 it silently loaded fp32"))
    if load_in_4bit:
        try:
            from transformers import AutoModelForCausalLM, BitsAndBytesConfig
            from peft import prepare_model_for_kbit_training
            import bitsandbytes  # noqa: F401 - imported to fail HERE, not inside transformers
        except ImportError as absent:
            print(
                "REFUSED: load_in_4bit was asked for and this recipe's pinned "
                f"environment cannot do it: {absent}. bitsandbytes must be in "
                "recipes/hf-peft-lora/requirements.lock and installed into its "
                ".venv - `python scripts/build_recipe_env.py hf-peft-lora`. "
                "Nothing was trained; a run that quietly fell back to fp16 "
                "would report a peak from a different configuration than the "
                "one that was requested.",
                file=sys.stderr,
            )
            emit("refused", reason="bitsandbytes not available", load_in_4bit=True)
            return 6
        # float16 compute, not bfloat16: this card is sm_75 and has no native
        # bf16, which is the same reason `fp16=True` is set above. Double
        # quantisation is on because it costs accuracy that is not measurable
        # here and saves memory that is.
        quantization = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.float16,
        )
        model_for_trainer = AutoModelForCausalLM.from_pretrained(
            base_model, quantization_config=quantization, dtype=torch.float16
        )
        # Casts the norms and the embedding output back to fp32 and makes the
        # inputs require grad, which is what lets gradient checkpointing work
        # through a frozen quantised base. Without it the run trains and the
        # loss does not move.
        model_for_trainer = prepare_model_for_kbit_training(
            model_for_trainer, use_gradient_checkpointing=args.gradient_checkpointing
        )
        emit(
            "quantized_base",
            quant_type="nf4",
            double_quant=True,
            compute_dtype="float16",
            says=(
                "the base is loaded 4-bit; the adapter trains in fp16 on top of "
                "it, and this run's peak is not comparable with an fp16 one"
            ),
        )

    trainer = SFTTrainer(
        model=model_for_trainer,
        args=args,
        train_dataset=dataset,
        peft_config=peft_config,
        callbacks=[Progress()],
    )

    trainable = sum(p.numel() for p in trainer.model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in trainer.model.parameters())
    emit(
        "adapter",
        trainable_parameters=trainable,
        total_parameters=total,
        trainable_fraction=round(trainable / total, 6) if total else None,
    )
    print(
        f"LoRA adapter: {trainable:,} trainable of {total:,} parameters "
        f"({trainable / total:.3%})" if total else "LoRA adapter attached",
        flush=True,
    )

    # ## TWO PEAKS, BECAUSE ONE OF THEM WAS ANSWERING A DIFFERENT QUESTION
    #
    # `torch.cuda.max_memory_allocated` is a HIGH-WATER MARK FROM PROCESS START
    # and `reset_peak_memory_stats` appears nowhere in this recipe, so every
    # peak this file has ever reported includes whatever the LOAD transiently
    # allocated - for a 4-bit run, the fp16 weights that exist briefly before
    # they are quantised away. Measured: the allocator-only estimate misses the
    # reported peaks by +0.735 at a realised 104 tokens, +0.729 at 207 and
    # +0.424 at 2048 - near-constant in the short regime, which is the
    # signature of a fixed transient rather than a training term.
    #
    # Resetting here separates them. **Both are kept, and the old name keeps its
    # old meaning**: `peak_vram_gb` stays the process high-water mark, so every
    # number already published against it still compares, and
    # `peak_train_vram_gb` is the new, narrower one. Renaming the old field
    # would have silently changed what a hundred recorded numbers meant.
    load_peak_gb = (
        round(torch.cuda.max_memory_allocated(0) / (1024 ** 3), 2)
        if torch.cuda.is_available()
        else None
    )
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats(0)
    seen["load_peak_gb"] = load_peak_gb

    result = trainer.train()
    trainer.model.save_pretrained(str(output_dir))
    try:
        trainer.processing_class.save_pretrained(str(output_dir))
    except Exception:  # noqa: BLE001 - a missing tokenizer copy is not a failed run
        pass

    elapsed = round(time.monotonic() - started, 2)
    train_peak_gb = (
        round(torch.cuda.max_memory_allocated(0) / (1024 ** 3), 2)
        if torch.cuda.is_available()
        else None
    )
    # The old field keeps the old meaning: the highest the process ever went,
    # which after the reset is the larger of the load transient and training.
    peak_gb = (
        max(x for x in (load_peak_gb, train_peak_gb) if x is not None)
        if (load_peak_gb is not None or train_peak_gb is not None)
        else None
    )
    metrics = getattr(result, "metrics", {}) or {}
    emit(
        "finished",
        elapsed_seconds=elapsed,
        steps=max_steps,
        # The base belongs in the event that carries the peak, so one object
        # answers "what did this cost, for what model". It is already in
        # `job.json`, but a log-only reader had to join two files to learn it
        # and three readers got three answers trying.
        base_model=base_model,
        peak_vram_gb=peak_gb,
        # THE FIELDS THAT MAKE A PEAK PLACEABLE, and each was absent. A run
        # record carrying a number and not the configuration that produced it
        # cannot be compared with anything: `load_in_4bit` appeared in 0 of 43
        # existing records, and `grad_checkpointing` was left to its default by
        # 38 of them - so two runs at four times the memory read identically.
        # Every value here is known at this point and none is re-derived.
        # BOTH PEAKS. `peak_vram_gb` above is the process high-water mark and
        # keeps its old meaning; these two say which part of it was which.
        peak_train_vram_gb=train_peak_gb,
        peak_load_vram_gb=load_peak_gb,
        # AND WHAT THE CARD LOOKED LIKE WHEN IT FINISHED. The three peaks are
        # this process's allocator; this is the device.
        vram_at_end=vram_now(),
        load_in_4bit=bool(load_in_4bit),
        base_dtype=str(base_dtype),
        revision=config.get("revision"),
        optimizer=str(args.optim),
        # THE RESOLVED LIST, not the absence. LoraConfig leaves target_modules
        # to peft's default, so the config says None and the run actually
        # trained q_proj/v_proj - writing None would record a question.
        target_modules=sorted(
            getattr(trainer.model.peft_config.get("default", None),
                    "target_modules", None) or []
        ) or None,
        batch_size=int(batch_size),
        grad_accum=int(config.get("grad_accum", 1)),
        max_seq_len=int(max_length),
        # `max_seq_len` is a CAP. Two runs under one 512 cap realised 36 and
        # 339 tokens per step, a 9.4x spread that three lanes explained three
        # different ways before anybody read this field.
        num_tokens=metrics.get("num_tokens", seen["num_tokens"]) or seen["num_tokens"],
        train_runtime=metrics.get("train_runtime"),
        train_samples_per_second=metrics.get("train_samples_per_second"),
        final_loss=metrics.get("train_loss"),
        adapter_dir=str(output_dir),
    )
    print(
        f"done in {elapsed}s, peak VRAM {peak_gb} GB, adapter written to "
        f"{output_dir}",
        flush=True,
    )
    print(
        "Cost of this run: "
        f"{elapsed} seconds of your own machine's time and {peak_gb} GB of its "
        "video memory. No money was spent, and nothing left this computer "
        "except the model download.",
        flush=True,
    )
    if run_id:
        post(base_url, token, f"/api/runs/{run_id}/complete", {})
    return 0


# ---------------------------------------------------------------------------
# Stage three: scoring what was trained, in the environment that trained it.


#: The file the harness reads back. One JSON object per row, in the order the
#: rows arrived, carrying the `row_index` it was given rather than a position -
#: a run that stops early leaves a short file whose rows are still identified,
#: and the harness pairs on the index and never on the line number.
PREDICTIONS = "predictions.jsonl"

#: The control arm's file: the same rows through the same weights with the
#: adapter switched off.
PREDICTIONS_BASE = "predictions_base.jsonl"

#: How often a progress line goes out while generating. A three-hundred-row
#: eval should say something more than twice and less than three hundred times.
EVAL_STRIDE = 10


def eval_rows(config: dict) -> list[dict]:
    """The rows to answer, exactly as the harness chose them.

    Refuses rather than repairs. A row with no `row_index` cannot be paired
    against anything, and quietly numbering it by position is how a comparison
    ends up pairing two different questions - which is the defect
    `app/tools/evals.py` calls the -50% headline.
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
        # THE CALLER'S OWN IDENTITY FOR THE ROW, CARRIED THROUGH IF THEY GAVE
        # ONE, and this is not a convenience.
        #
        # `row_index` is POSITIONAL on purpose - it counts eligible rows from
        # zero in file order, the rule lives in `app/tools/evals.py::_plan`, and
        # every paired comparison in this product depends on it meaning that.
        # But a scorer that keys its reference on the eval file's OWN ids reads
        # `row_index` as if it were one, and the two conventions collide in
        # silence.
        #
        # Measured 2026-09-10: `evals/architecture-json/edge_direction.py` keys
        # every `held-out*.jsonl` by `row_id` and looks up `ref[row_index]`. The
        # extra held-out set starts its ids at 100 - chosen SO an extra could
        # never be mistaken for an original - so a predictions file straight
        # from this recipe scored answer 0 against the original set's row 0, all
        # the way down, and produced a table that looked entirely reasonable.
        #
        # Carrying the id changes neither convention and makes that impossible
        # to do by accident. Only `row_id` is passed, not arbitrary keys: this
        # file writes what the caller reads back, and a pass-through of
        # everything is a way to smuggle a field nobody chose.
        kept = {"row_index": index, "input": str(row.get("input", ""))}
        if row.get("row_id") is not None:
            kept["row_id"] = row["row_id"]
        out.append(kept)
    return out


def resolve_base_model(config: dict, adapter_dir: Path | None) -> str:
    """Which base model these weights belong to, read rather than assumed.

    The adapter's own `adapter_config.json` records `base_model_name_or_path`,
    written by `save_pretrained` at the end of the run that made it. A caller
    may override it - a merged or relocated base is a real situation - and the
    override is reported, because scoring an adapter against a base it was not
    trained on produces a number that looks like a score.
    """
    named = str(config.get("base_model") or "").strip()
    if named:
        return named
    if adapter_dir is None:
        raise SystemExit(
            "REFUSED: this eval names neither an adapter nor a base model, so "
            "there is nothing to load."
        )
    manifest = adapter_dir / "adapter_config.json"
    try:
        body = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(
            f"REFUSED: cannot read {manifest}: {exc}. Without it there is no "
            "record of which base model this adapter belongs to, and guessing "
            "one would produce a score for a pairing nobody made."
        ) from None
    base = str(body.get("base_model_name_or_path") or "").strip()
    if not base:
        raise SystemExit(
            f"REFUSED: {manifest} does not say which base model this adapter "
            "was trained on. Pass base_model explicitly if you know it."
        )
    return base


def evaluate(config: dict, run_dir: Path) -> int:
    """Answer the rows with the adapter, and again with it switched off.

    THE CONTROL ARM IS THE POINT OF DOING BOTH IN ONE PROCESS. The base and
    the adapter run through the same loaded weights, the same tokenizer, the
    same dtype, the same prompt and the same greedy decode; the only difference
    is `disable_adapter()`. Two separate runs would differ by everything a
    reload can change, and the delta between them would carry all of it.

    Greedy (`do_sample=False`) so the same rows through the same weights give
    the same answers. That is a real property of this arm and it is one the
    provider arm does not have - `app/tools/evals.py` says so in its own
    DETERMINISM section - which is exactly why the two arms are reported as
    two arms.
    """
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    started = time.monotonic()
    rows = eval_rows(config)
    raw_adapter = str(config.get("adapter_dir") or "").strip()
    adapter_dir = Path(raw_adapter).resolve() if raw_adapter else None
    if adapter_dir is not None and not (adapter_dir / "adapter_config.json").is_file():
        raise SystemExit(
            f"REFUSED: {adapter_dir} has no adapter_config.json, so it is not "
            "an adapter this can load. Nothing was scored."
        )
    base_model = resolve_base_model(config, adapter_dir)
    template = str(config.get("prompt_template") or "{input}")
    if "{input}" not in template:
        raise SystemExit(
            "REFUSED: prompt_template does not contain {input}, so every row "
            "would be sent the same prompt and the score would be a fact about "
            "one question asked fifty times."
        )
    max_new_tokens = max(1, int(config.get("max_new_tokens", 32)))
    max_seq_len = max(8, int(config.get("max_seq_len", 512)))
    stop_at_newline = bool(config.get("stop_at_newline", True))
    include_base = bool(config.get("include_base", True)) and adapter_dir is not None
    torch.manual_seed(int(config.get("seed", 0)))

    device = "cuda" if torch.cuda.is_available() else "cpu"
    wanted = str(config.get("dtype") or "auto")
    if device == "cpu":
        # fp16 on a CPU is a correctness and speed trap in equal measure.
        dtype = torch.float32
        dtype_why = "float32, because this is running on the CPU"
    elif wanted != "auto":
        dtype = getattr(torch, wanted)
        dtype_why = f"{wanted}, because the job asked for it"
    else:
        dtype = "auto"
        dtype_why = "the dtype recorded in the model's own config"

    emit(
        "eval_loading",
        base_model=base_model,
        adapter_dir=str(adapter_dir) if adapter_dir else None,
        rows=len(rows),
        device=device,
        include_base=include_base,
    )
    print(
        f"scoring {len(rows)} rows on {device}: base {base_model}"
        + (f", adapter {adapter_dir}" if adapter_dir else ", no adapter"),
        flush=True,
    )

    # The tokenizer beside the adapter is the one the run that made it saved,
    # so it is preferred over the base model's. A mismatch between the
    # tokenizer that trained and the tokenizer that scores is invisible in the
    # output and fatal to the number.
    tokenizer_from = (
        str(adapter_dir)
        if adapter_dir is not None and (adapter_dir / "tokenizer_config.json").is_file()
        else base_model
    )
    try:
        tokenizer = AutoTokenizer.from_pretrained(tokenizer_from)
        model = AutoModelForCausalLM.from_pretrained(base_model, dtype=dtype)
    except OSError as missing:
        # The offline case, and it is the ordinary one rather than an error:
        # a no-egress sandbox is handed HF_HUB_OFFLINE=1 on purpose.
        print(
            f"REFUSED: {base_model} is not in this machine's model cache and "
            "this sandbox has no egress, so it was not downloaded. Nothing was "
            f"scored.\n{type(missing).__name__}: {missing}\n"
            "Either fetch the base model first with the tools that do that, or "
            "make the sandbox with egress and say what the network is for.",
            file=sys.stderr,
        )
        emit("refused", reason="base model not available offline", base_model=base_model)
        return 5

    if adapter_dir is not None:
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, str(adapter_dir))
    model.to(device)

    # TURING HAS NO NATIVE BF16, AND `is_bf16_supported()` SAYS TRUE ANYWAY.
    # Measured on this machine, torch 2.6.0+cu124, RTX 2060 SUPER (7.5):
    # `torch.cuda.is_bf16_supported()` -> True, and the same call with
    # `including_emulation=False` -> False. So a model whose config says
    # bfloat16 runs emulated here, which is the same limit the training path
    # already refuses to be quiet about. Both arms are converted together, so
    # the comparison between them is unchanged either way; what changes is how
    # long a real model takes.
    if device == "cuda" and getattr(model, "dtype", None) is torch.bfloat16:
        try:
            native = bool(torch.cuda.is_bf16_supported(including_emulation=False))
        except TypeError:  # a torch without the argument answers the old way
            native = bool(torch.cuda.is_bf16_supported())
        if not native:
            model.to(torch.float16)
            dtype_why = (
                "float16: this model's config says bfloat16 and this GPU has no "
                "native bf16, so bf16 here is emulated. Both arms were "
                "converted, so the comparison between them is unaffected."
            )
            print(f"note: {dtype_why}", flush=True)

    model.eval()
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    resolved_dtype = str(getattr(model, "dtype", dtype))
    emit(
        "eval_loaded",
        seconds=round(time.monotonic() - started, 2),
        dtype=resolved_dtype,
        dtype_why=dtype_why,
        tokenizer_from=tokenizer_from,
    )

    def answer_all(arm: str, path: Path) -> int:
        """One pass over the rows, written a line at a time.

        A line at a time for the reason `app/tools/evals.py` commits a row at a
        time: a run that is killed at row forty has forty answers on disk, and
        the harness can say so rather than losing the work.
        """
        written = 0
        with open(path, "w", encoding="utf-8") as handle:
            for position, row in enumerate(rows, start=1):
                prompt = template.format(input=row["input"])
                encoded = tokenizer(
                    prompt, return_tensors="pt", truncation=True,
                    max_length=max_seq_len,
                )
                encoded = {k: v.to(device) for k, v in encoded.items()}
                at = time.monotonic()
                with torch.inference_mode():
                    produced = model.generate(
                        **encoded,
                        max_new_tokens=max_new_tokens,
                        do_sample=False,
                        pad_token_id=tokenizer.pad_token_id,
                    )
                fresh = produced[0][encoded["input_ids"].shape[-1]:]
                text = tokenizer.decode(fresh, skip_special_tokens=True).strip()
                if stop_at_newline and text:
                    text = text.split("\n")[0].strip()
                handle.write(
                    json.dumps(
                        {
                            "row_index": row["row_index"],
                            **({"row_id": row["row_id"]}
                               if row.get("row_id") is not None else {}),
                            "answer": text,
                            "seconds": round(time.monotonic() - at, 3),
                            "arm": arm,
                            #: WHICH MODEL PRODUCED THIS ROW, IN THE ROW.
                            #: `arm` says "base" or "adapter"; it does not say
                            #: WHICH base. A comparison across two arms is
                            #: meaningless unless both name their model, and
                            #: an identity that lives only in the run log or a
                            #: commit message cannot be checked by whoever
                            #: reads the artefact later.
                            #:
                            #: MEASURED 2026-09-10: kill 13 paired this
                            #: recipe's adapter against a naming-rule baseline
                            #: on a DIFFERENT base model, and the only record
                            #: of which model that was sat in the prose of a
                            #: commit message. The research lane could not
                            #: check the one fact its refusal turned on, so
                            #: the refusal was unenforceable. Cheap to fix
                            #: here; expensive once an arm exists whose entire
                            #: meaning is which model produced it.
                            "model": base_model,
                            **({"adapter": str(adapter_dir)}
                               if arm != "base" and adapter_dir is not None
                               else {}),
                        }
                    )
                    + "\n"
                )
                handle.flush()
                written += 1
                if position % EVAL_STRIDE == 0 or position == len(rows):
                    emit(
                        "eval_progress",
                        arm=arm,
                        answered=position,
                        rows=len(rows),
                        elapsed_seconds=round(time.monotonic() - started, 2),
                    )
                    print(f"{arm}: answered {position}/{len(rows)}", flush=True)
        return written

    arm = "adapter" if adapter_dir is not None else "base"
    answered = answer_all(arm, run_dir / PREDICTIONS)

    answered_base = 0
    if include_base:
        print("scoring the same rows again with the adapter switched off",
              flush=True)
        with model.disable_adapter():
            answered_base = answer_all("base", run_dir / PREDICTIONS_BASE)

    elapsed = round(time.monotonic() - started, 2)
    peak_gb = (
        round(torch.cuda.max_memory_allocated(0) / (1024 ** 3), 2)
        if device == "cuda"
        else None
    )
    emit(
        "eval_finished",
        arm=arm,
        rows=len(rows),
        answered=answered,
        answered_base=answered_base,
        predictions=str(run_dir / PREDICTIONS),
        predictions_base=str(run_dir / PREDICTIONS_BASE) if include_base else None,
        base_model=base_model,
        adapter_dir=str(adapter_dir) if adapter_dir else None,
        device=device,
        dtype=resolved_dtype,
        max_new_tokens=max_new_tokens,
        prompt_template=template,
        stop_at_newline=stop_at_newline,
        decoding="greedy",
        elapsed_seconds=elapsed,
        peak_vram_gb=peak_gb,
        graded_by="nothing in here - the harness grades these with evals.grade",
    )
    print(
        f"done in {elapsed}s: {answered} answer(s) written to "
        f"{run_dir / PREDICTIONS}"
        + (
            f" and {answered_base} to {run_dir / PREDICTIONS_BASE}"
            if include_base
            else ""
        )
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

    port = os.environ.get("MLH_PORT", "8078")
    base_url = f"http://127.0.0.1:{port}"
    token = os.environ.get("MLH_TOKEN")

    print(f"recipe hf-peft-lora, kind {args.kind}, interpreter {sys.executable}",
          flush=True)

    scoring = args.kind == "eval"
    ok, checks = preflight(config, require_cuda=not scoring)
    emit("preflight", ok=ok, checks=checks)
    for check in checks:
        mark = "ok " if check["ok"] else "RED"
        print(f"preflight {mark} {check['check']}: {check['detail']}", flush=True)
    if not ok:
        print(
            "REFUSED: a preflight check is red, so nothing was "
            + ("scored" if scoring else "trained")
            + ". The detail above says which one and what to do about it.",
            file=sys.stderr,
        )
        return 3

    if scoring:
        return evaluate(config, run_dir)

    for required in ("base_model", "dataset_path"):
        if not config.get(required):
            print(f"REFUSED: config is missing {required!r}", file=sys.stderr)
            emit("refused", reason=f"missing {required}")
            return 4

    return train(config, run_dir, base_url, token)


if __name__ == "__main__":
    raise SystemExit(main())
