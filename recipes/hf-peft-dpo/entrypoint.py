"""Direct preference optimisation of a LoRA adapter, in this recipe's own venv.

The second real trainer this harness ships. `hf-peft-lora` learns from
DEMONSTRATIONS - here is a prompt, here is the answer, imitate it. This learns
from PREFERENCES - here is a prompt and two answers, one of them is better -
which is a different objective over different data, and pointing either one at
the other's file trains happily on nothing useful.

## The shape is `hf-peft-lora`'s, deliberately

Same four stages, same event protocol, same refusal codes: bootstrap into the
pinned interpreter or explain exactly why not (2), preflight or stop (3), a
config that names what it needs (4), then train. A person reading both logs
should not have to learn two products, and a difference between them should mean
a real difference in the work rather than a difference in who wrote it.

## What it refuses, and why each one is a silent failure otherwise

* **A demonstrations file.** `text`, or `prompt`/`completion`, is
  `hf-peft-lora`'s data. DPO needs `prompt`, `chosen`, `rejected`. Handed the
  wrong one, `DPOTrainer` would either raise deep inside a collator or - worse -
  train on a mangled interpretation, and the adapter would be a real artifact of
  a meaningless run.
* **The CPU-only torch wheel.** Twenty times slower with no error. Same trap,
  same refusal.
* **Too few pairs.** DPO on a handful of preferences is noise fitted with
  confidence. The floor is stated here and the ledger's own floor is stated in
  `app/tools/propose.py`; this one is the backend's, and it refuses rather than
  producing an adapter nobody should trust.

## One thing that is NOT configurable, and the reason is memory

`ref_model` is never passed. trl 0.24 serves the reference by disabling the
LoRA adapter on the model already loaded - `dpo_trainer.py:915-921` and
`:934-936` - so a LoRA-DPO run holds ONE set of base weights. Passing a
`ref_model` alongside a `peft_config` is refused by trl itself at
`:582-586` ("For training PEFT adapters with DPO there is no need to pass a
reference model"), and it would double the residency that
`can_this_machine_train` sized the run against.

## `adapter_dir`: DPO on top of an SFT pass, and what trl does with it

`docs/diagnosis_engine.yaml` declares `DPO: {prerequisite: LORA_SFT}` - you do
not jump to preference optimisation before an imitation pass. So this recipe
takes an optional `adapter_dir`, the adapter `hf-peft-lora` produced, and
**merges it into the base weights HERE, explicitly, before trl sees anything.**
The policy then starts from the SFT weights and the reference - the same model
with the new adapter disabled - IS the SFT model rather than the raw base.

**THE MERGE USED TO BE LEFT TO trl AND THAT WAS THE BUG.**
`dpo_trainer.py:578-580` really does merge an already-loaded `PeftModel`, and
that reading was right; what was wrong was the conclusion drawn from it. Leaving
the merge inside trl left this code with no handle on the merged weights, and
every route back to them turned out to hand back the model with LoRA wrappers
still attached - `trainer.model.get_base_model()` does, and so does the merged
object itself once `get_peft_model` has MUTATED IT IN PLACE.

Measured on a real run, which is the only way it was found: the saved
`merged_base` was a state dict of `base_layer` / `lora_A` / `lora_B` keys, and
loading it as a causal LM silently dropped all of them and RANDOMLY INITIALISED
sixty attention projections. An artifact that loads and is wrong.

**The consequence for whatever runs the result.** The adapter this run writes is
an adapter over SFT-MERGED weights. It is not loadable on the raw base model and
it is not stackable on the SFT adapter - both run, both return text, neither is
what was trained. The run saves the merged base beside it and CHECKS THE FILE's
own tensor keys before believing it did.
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
from typing import Any, Iterable

RECIPE_DIR = Path(__file__).resolve().parent
RECIPE_NAME = "hf-peft-dpo"

#: Structured progress, one line, so a log a person reads and a log a machine
#: parses are the same log. `hf-peft-lora` uses the same prefix on purpose.
EVENT_PREFIX = "MLH_EVENT "

#: Below this, a preference dataset is not a signal. `docs/diagnosis_engine.yaml`
#: has its own floor for the OUTCOME (`S5_PREFERENCES_NOT_DEMONSTRATIONS` reads
#: 1,000); this is the BACKEND's floor, and it is lower because the two answer
#: different questions - the ledger asks whether DPO is the right thing to do,
#: this asks whether the run would produce anything at all.
FEWEST_PAIRS = 50


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
            f"  uv venv --python 3.11 recipes/{RECIPE_NAME}/.venv\n"
            f"  uv pip install --python recipes/{RECIPE_NAME}/.venv/Scripts/python.exe \\\n"
            "      --index-url https://download.pytorch.org/whl/cu124 torch==2.6.0\n"
            f"  uv pip sync --python recipes/{RECIPE_NAME}/.venv/Scripts/python.exe \\\n"
            f"      recipes/{RECIPE_NAME}/requirements.lock\n"
            "\n"
            "It is about 4.8 GB on disk and it is NOT shared with hf-peft-lora,\n"
            "even though the pins are identical - a recipe is a named backend a\n"
            "plan says out loud, and two of them sharing one environment is two\n"
            "plans that could drift apart with nowhere to put the difference.\n"
            "\n"
            "Nothing is trained until it exists: a run that quietly used whatever\n"
            "happened to be importable would not be reproducible, and an\n"
            "unreproducible training run is worse than none.",
            file=sys.stderr,
        )
        emit("refused", reason="pinned environment not built", expected=str(python))
        return 2

    emit("bootstrap", interpreter=str(python), recipe=RECIPE_NAME)
    print(f"handing off to the pinned interpreter: {python}", flush=True)
    completed = subprocess.run([str(python), str(Path(__file__).resolve())] + argv)
    return completed.returncode


# ---------------------------------------------------------------------------
# Stage two: the preflight doctor.


def preflight(config: dict) -> tuple[bool, list[dict]]:
    """Every check that can fail before a GPU-hour is spent. Red means stop."""
    checks: list[dict] = []

    def note(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    try:
        import torch
    except ImportError as exc:  # pragma: no cover - the venv guarantees it
        note("torch", False, f"torch is not importable in the pinned venv: {exc}")
        return False, checks

    note("torch", True, f"torch {torch.__version__}")

    # THE TRAP THIS FUNCTION EXISTS FOR. PyPI's Windows wheel is CPU-only and
    # every setup step succeeds on it; the run is then twenty times slower with
    # no error anywhere.
    cuda = bool(torch.cuda.is_available())
    note(
        "cuda",
        cuda,
        f"torch.cuda.is_available() is {cuda}"
        + (
            ""
            if cuda
            else " - this is the CPU-only wheel. Reinstall torch from "
            "download.pytorch.org/whl/cu124; nothing is trained on it."
        ),
    )

    try:
        from trl import DPOTrainer  # noqa: F401

        note("trl", True, "trl exposes DPOTrainer")
    except ImportError as exc:
        note("trl", False, f"trl does not expose DPOTrainer: {exc}")

    path = str(config.get("dataset_path") or "")
    if not path:
        note("dataset", False, "config names no dataset_path")
    elif not Path(path).is_file():
        note("dataset", False, f"there is no file at {path}")
    else:
        note("dataset", True, f"dataset is at {path}")

    return all(check["ok"] for check in checks), checks


# ---------------------------------------------------------------------------
# The data contract, and the refusal that matters most.


def load_pairs(path: Path) -> list[dict]:
    """Preference triples, or a refusal that names the other recipe.

    Explicit rather than `datasets.load_dataset` for `hf-peft-lora`'s reason:
    the failure being avoided is the silent one, where a file with the wrong
    columns trains happily on empty strings.
    """
    rows: list[dict] = []
    looked_like_demonstrations = 0

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

            if {"prompt", "chosen", "rejected"} <= set(row):
                rows.append(
                    {
                        "prompt": str(row["prompt"]),
                        "chosen": str(row["chosen"]),
                        "rejected": str(row["rejected"]),
                    }
                )
                continue

            if "text" in row or {"prompt", "completion"} <= set(row):
                looked_like_demonstrations += 1
                continue

            raise SystemExit(
                f"{path}:{number} has no prompt/chosen/rejected triple. "
                "Nothing was trained."
            )

    if looked_like_demonstrations and not rows:
        raise SystemExit(
            f"{path} is a DEMONSTRATIONS file - {looked_like_demonstrations} of "
            "its rows carry `text`, or a prompt/completion pair, and none "
            "carries `prompt`/`chosen`/`rejected`.\n"
            "\n"
            "That is what `hf-peft-lora` trains on, and it is a different "
            "objective: imitate this answer, rather than prefer this answer to "
            "that one. Training it here would produce a real adapter from a "
            "meaningless run. Point this file at hf-peft-lora, or bring "
            "preference pairs here. Nothing was trained."
        )
    if not rows:
        raise SystemExit(f"{path} has no usable rows. Nothing was trained.")
    if len(rows) < FEWEST_PAIRS:
        raise SystemExit(
            f"{path} holds {len(rows)} preference pairs and this backend will "
            f"not train on fewer than {FEWEST_PAIRS}. Below that, what comes out "
            "is noise fitted with confidence - and an adapter nobody should "
            "trust is worse than no adapter. Nothing was trained."
        )
    return rows


# ---------------------------------------------------------------------------
# Stage three: the run.


#: What an unmerged state dict looks like. `peft` wraps a target `Linear` in a
#: `lora.Linear` whose parameters are `base_layer.weight`, `lora_A.<name>.weight`
#: and `lora_B.<name>.weight` - so any of these in a file that claims to hold
#: merged weights means the merge did not happen.
ADAPTER_KEY_MARKERS = ("lora_", "base_layer")


def adapter_keys_in(keys: Iterable[str]) -> list[str]:
    """The keys in a state dict that prove it is NOT merged. Pure, so it is tested.

    SPLIT OUT FROM THE FILE READING ON PURPOSE. The decision - "does this look
    like an adapter rather than merged weights" - is the part that was wrong
    twice, and it is the part a test suite running in an interpreter with no
    torch and no safetensors can still exercise. That interpreter having neither
    is the whole point of a pinned recipe environment, so a guard whose only
    test needed them would be a guard nothing checks until somebody trains.

    The reading around it is exercised by a real run, which is where both
    defects were found and is the only place they could have been.
    """
    return sorted(
        key
        for key in keys
        if any(marker in str(key) for marker in ADAPTER_KEY_MARKERS)
    )


def the_base_this_adapter_belongs_to(
    recorded: dict, merged_base: "Path | None"
) -> dict:
    """Correct an adapter manifest to name the weights it is actually relative to.

    THE SILENT WRONG ANSWER THIS CLOSES, measured on a real run 2026-09-04.
    `peft`'s `save_pretrained` writes `base_model_name_or_path` from the model
    it was handed, which for a continued run is the string the RAW BASE was
    loaded from - `HuggingFaceTB/SmolLM2-135M`. But the adapter a continued run
    produces is relative to the SFT-MERGED weights, and
    `recipes/hf-peft-lora/entrypoint.py::resolve_base_model` reads exactly that
    field when a caller names no `base_model`.

    So the default path scores raw base + DPO adapter: a model nobody trained,
    reported under this run's name. `resolve_base_model`'s own docstring names
    the failure - "scoring an adapter against a base it was not trained on
    produces a number that looks like a score" - and offers an override, but
    nothing makes a caller use it and the recorded value points them the wrong
    way. A manifest that is merely silent would be safer than one that is
    confidently wrong.

    Pure, and separate from the writing, so it is tested in an interpreter with
    no torch: this is the decision, and the decision is the part that was wrong.

    `merged_base` is `None` for a run that started from the raw base, and then
    what peft recorded is already right and is left alone.
    """
    if merged_base is None:
        return dict(recorded)
    corrected = dict(recorded)
    corrected["base_model_name_or_path"] = str(merged_base)
    # KEPT, NOT REPLACED. Which model the lineage started from is still a true
    # and useful fact; it is just not the thing to load this adapter onto.
    corrected["mlh_trained_from_base"] = recorded.get("base_model_name_or_path")
    corrected["mlh_merged_base"] = str(merged_base)
    return corrected


def _point_the_adapter_at_its_own_base(output: Path, merged_base: "Path | None") -> None:
    """Rewrite the saved manifest in place. Raises rather than shipping a wrong one."""
    manifest = output / "adapter_config.json"
    body = json.loads(manifest.read_text(encoding="utf-8"))
    corrected = the_base_this_adapter_belongs_to(body, merged_base)
    manifest.write_text(json.dumps(corrected, indent=2), encoding="utf-8")
    if merged_base is not None:
        back = json.loads(manifest.read_text(encoding="utf-8"))
        if back.get("base_model_name_or_path") != str(merged_base):
            raise SystemExit(
                f"REFUSED: {manifest} still does not name the merged base. An "
                "adapter whose manifest points at weights it was not trained "
                "on is worse than one with no manifest."
            )
        emit("adapter_base_corrected", adapter=str(output),
             now_points_at=str(merged_base),
             was=back.get("mlh_trained_from_base"))


def _save_the_merged_base(merged: Any, run_dir: Path) -> Path:
    """Write the weights the preference adapter will be relative to, and PROVE it.

    ## Why this file has to exist at all

    The adapter this run produces sits on the SFT-MERGED weights, not on the raw
    base and not on the SFT adapter. Loaded onto the raw base it is a difference
    from something else; stacked on the SFT adapter it is that difference
    applied twice. Both run and both return text. So the merged base travels
    with the adapter or neither is usable.

    ## The guard reads the FILE, and the version that did not is why

    The first guard here loaded the directory back with
    `AutoModelForCausalLM.from_pretrained` and checked the RESULT for adapter
    keys. It always passed, and it could not have failed: transformers drops
    keys it does not recognise on load, so the check ran against a state dict
    that had already been cleaned of the exact thing it was looking for - while
    the file on disk still carried them, and loading it randomly initialised
    sixty attention projections with a warning nobody would read.

    A check that cannot observe the failure it is written for is worse than no
    check, because it reports success. So this reads the SAFETENSORS KEYS off
    the file, which is where the defect actually lives.
    """
    from safetensors.torch import load_file

    where = run_dir / "merged_base"
    merged.save_pretrained(str(where))

    shards = sorted(where.glob("*.safetensors"))
    if not shards:
        raise SystemExit(
            f"nothing was written to {where}. The merged base is what the "
            "adapter applies to, so an adapter without it is unusable."
        )
    keys: set[str] = set()
    for shard in shards:
        keys |= set(load_file(str(shard)))
    stray = sorted(key for key in keys if "lora_" in key or "base_layer" in key)
    if stray:
        raise SystemExit(
            f"the merged base at {where} still carries adapter keys - "
            f"{len(stray)} of them, first three {stray[:3]}. That means it is "
            "NOT merged: loading it would silently drop those keys and randomly "
            "initialise the layers they stand in for. Refusing rather than "
            "leaving an artifact that loads and is wrong."
        )
    emit("merged_base", path=str(where), keys=len(keys), adapter_keys=0)
    print(
        f"the SFT-merged base this adapter applies to: {where} "
        f"({len(keys)} tensors, no adapter keys)",
        flush=True,
    )
    return where


def train(config: dict, run_dir: Path, base_url: str, token: str | None) -> int:
    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import TrainerCallback
    from trl import DPOConfig, DPOTrainer

    started = time.monotonic()
    run_id = config.get("run_id")
    base_model = config["base_model"]
    dataset_path = Path(config["dataset_path"])
    adapter_dir = str(config.get("adapter_dir") or "").strip()
    #: Set only by a continued run. `None` means the adapter really is
    #: relative to the raw base and peft's own manifest is already right.
    merged_base_path: Path | None = None

    pairs = load_pairs(dataset_path)
    emit("dataset", rows=len(pairs), path=str(dataset_path))
    print(f"{len(pairs)} preference pairs from {dataset_path}", flush=True)

    dataset = Dataset.from_list(pairs)
    output = run_dir / "adapter"

    peft_config = LoraConfig(
        r=int(config.get("lora_r", 16)),
        lora_alpha=int(config.get("lora_alpha", 32)),
        lora_dropout=float(config.get("lora_dropout", 0.05)),
        bias="none",
        task_type="CAUSAL_LM",
    )

    arguments = DPOConfig(
        output_dir=str(output),
        per_device_train_batch_size=int(config.get("batch_size", 1)),
        gradient_accumulation_steps=int(config.get("grad_accum", 4)),
        learning_rate=float(config.get("learning_rate", 5e-6)),
        max_steps=int(config.get("max_steps", 20)),
        logging_steps=1,
        save_strategy="no",
        report_to=[],
        # `beta` is DPO's own knob and has no analogue in the SFT recipe: how
        # hard to move away from the reference. Left at trl's default unless the
        # plan named one, and the plan says which it used.
        beta=float(config.get("beta", 0.1)),
        max_length=int(config.get("max_seq_len", 1024)),
    )

    class Progress(TrainerCallback):
        def on_log(self, args, state, control, logs=None, **kwargs):  # noqa: ANN001
            if not logs:
                return
            emit("step", step=int(state.global_step), **{
                key: value for key, value in logs.items() if isinstance(value, (int, float))
            })
            if run_id and "loss" in logs:
                post(
                    base_url,
                    token,
                    f"/api/runs/{run_id}/metrics",
                    {"step": int(state.global_step), "name": "loss",
                     "value": float(logs["loss"])},
                )

    # THE SFT PASS THIS ONE CONTINUES, WHEN THERE IS ONE.
    #
    # THE MERGE IS DONE HERE, EXPLICITLY, AND THE FIRST VERSION LEFT IT TO trl.
    # `dpo_trainer.py:578-580` does merge an already-loaded `PeftModel`, and
    # that part was read correctly - but leaving it there left this code with no
    # handle on the merged weights, and the only way back to them looked like
    # `trainer.model.get_base_model()`. IT IS NOT. On a `PeftModel`,
    # `get_base_model()` returns the transformer with its `Linear` layers STILL
    # REPLACED by `lora.Linear` wrappers, so saving it wrote a state dict full
    # of `base_layer` / `lora_A` / `lora_B` keys.
    #
    # MEASURED, on a real run, which is the only reason this was found: loading
    # that directory as a `LlamaForCausalLM` silently dropped every one of those
    # keys and RANDOMLY INITIALISED 60 attention projections - "You should
    # probably TRAIN this model on a down-stream task", on a model that was
    # supposed to be the thing the adapter applies to. A wrong artifact that
    # loads is worse than one that does not.
    #
    # Doing the merge here fixes it twice over: `merged` is a plain
    # `LlamaForCausalLM` this code can save without asking trl for it back, and
    # trl then sees a model that is not a `PeftModel` and simply attaches the
    # fresh DPO adapter - so the reference `null_ref_context` disables down to
    # is the SFT model, which is the setup this recipe claims.
    policy = base_model
    merged = None
    if adapter_dir:
        if not (Path(adapter_dir) / "adapter_config.json").is_file():
            raise SystemExit(
                f"config names adapter_dir {adapter_dir!r} and there is no "
                "adapter_config.json in it. That path is meant to be the "
                "directory hf-peft-lora wrote. Nothing was trained."
            )
        from peft import PeftModel
        from transformers import AutoModelForCausalLM

        merged = PeftModel.from_pretrained(
            AutoModelForCausalLM.from_pretrained(base_model), adapter_dir
        ).merge_and_unload()
        policy = merged
        emit("continuing", from_adapter=adapter_dir, base_model=base_model,
             merged=type(merged).__name__)
        print(
            f"continuing from the SFT adapter at {adapter_dir}, merged into the "
            "base weights before the preference adapter is attached",
            flush=True,
        )

        # SAVED HERE, BEFORE THE TRAINER EXISTS, AND THE ORDER IS THE WHOLE FIX.
        #
        # `get_peft_model` MUTATES THE MODEL IN PLACE - it replaces each target
        # `Linear` with a `lora.Linear` wrapper on the object it was handed. So
        # the second version of this saved `merged` AFTER training and got a
        # state dict full of `base_layer` / `lora_A` / `lora_B` keys, because by
        # then `merged` was no longer the merged model: it was the merged model
        # wearing the DPO adapter. The first version had the same bug by a
        # different route, through `trainer.model.get_base_model()`.
        #
        # Saving before the trainer is built is correct on the merits and not
        # merely convenient: the SFT-merged base does not change during a DPO
        # run - only the new adapter trains - so this is exactly the artifact
        # the adapter will be relative to, and taking it now means no later
        # mutation can reach it.
        merged_base_path = _save_the_merged_base(merged, run_dir)

    trainer = DPOTrainer(
        model=policy,
        # NO `ref_model`, AND IT IS NOT AN OMISSION. trl serves the reference by
        # disabling the adapter on the model already loaded, so this run holds
        # one set of base weights. Passing one beside a `peft_config` is refused
        # by trl itself, and it would double the residency the fit check sized.
        args=arguments,
        train_dataset=dataset,
        peft_config=peft_config,
        callbacks=[Progress()],
    )

    emit("training", base_model=base_model, pairs=len(pairs),
         max_steps=arguments.max_steps, beta=arguments.beta)
    print(f"training {base_model} on {len(pairs)} pairs, beta {arguments.beta}",
          flush=True)

    trainer.train()
    trainer.save_model(str(output))
    # BEFORE anything reports success: an adapter whose manifest names
    # weights it was not trained on is a wrong number waiting to be taken.
    _point_the_adapter_at_its_own_base(output, merged_base_path)

    peak = (
        round(torch.cuda.max_memory_allocated() / 1e9, 2)
        if torch.cuda.is_available()
        else None
    )
    seconds = round(time.monotonic() - started, 1)
    emit("trained", adapter_dir=str(output), seconds=seconds, peak_vram_gb=peak)
    print(f"adapter written to {output} in {seconds}s"
          + (f", peak {peak} GB" if peak is not None else ""), flush=True)
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

    print(f"recipe {RECIPE_NAME}, kind {args.kind}, interpreter {sys.executable}",
          flush=True)

    # This recipe declares one kind. `app/jobspec.py` refuses an undeclared kind
    # before anything runs, so reaching here with another is a bug rather than a
    # user error - and it says so rather than doing something plausible.
    if args.kind != "train":
        print(
            f"REFUSED: {RECIPE_NAME} declares only `train` and was asked for "
            f"{args.kind!r}. recipe.toml is the list, and jobspec refuses an "
            "undeclared kind before this file runs.",
            file=sys.stderr,
        )
        emit("refused", reason="undeclared kind", kind=args.kind)
        return 4

    ok, checks = preflight(config)
    emit("preflight", ok=ok, checks=checks)
    for check in checks:
        mark = "ok " if check["ok"] else "RED"
        print(f"preflight {mark} {check['check']}: {check['detail']}", flush=True)
    if not ok:
        print(
            "REFUSED: a preflight check is red, so nothing was trained. The "
            "detail above says which one and what to do about it.",
            file=sys.stderr,
        )
        return 3

    for required in ("base_model", "dataset_path"):
        if not config.get(required):
            print(f"REFUSED: config is missing {required!r}", file=sys.stderr)
            emit("refused", reason=f"missing {required}")
            return 4

    return train(config, run_dir, base_url, token)


if __name__ == "__main__":
    raise SystemExit(main())
