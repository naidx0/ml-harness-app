"""Take a trained adapter to a Hugging Face repo, or say exactly why not.

    python scripts/publish_the_adapter.py --adapter runs/.../adapter --repo you/name --dry-run
    python scripts/publish_the_adapter.py --adapter runs/.../adapter --repo you/name

## Why this runs under a recipe's environment

`huggingface_hub` is NOT a dependency of this harness and is not in its venv. It
IS in all three recipe environments, because the recipes fetch base models.
Adding it to the harness would be a new runtime dependency for a step that runs
once, so this runs the way `build_recipe_env.py` does - under an interpreter
that already has the client.

That was checked rather than assumed. The string `huggingface_hub` does appear
in `app/build.py`, `app/tools/models.py`, `app/tools/propose.py` and
`app/tools/sandbox.py` - as a **capability label** inside `reads=(...)`, a
provenance tag meaning *this tool reads from Hugging Face*. It is not an import.
`push_to_hub`, `HfApi`, `create_repo` and `upload_folder` appear **zero** times
in `app/`, `scripts/` and the recipes' own code. Nothing here published anything
before this file, and a grep that reads a permissions annotation as an import
is how three separate plans came to say the publish path was one command away.

## The card is built from the run record, not written by hand

An adapter's `adapter_config.json` carries the base model, the rank, the alpha
and the target modules. The run that made it carries the sequence length, the
batch size and the measured peak VRAM. All of it goes in the card because it is
what somebody needs to judge or reproduce the thing, and because a card whose
numbers were typed rather than read goes stale the same way a README does.

**What it will not do is describe the adapter's quality.** Nothing here scored
it, so the card says what was trained and what has not been measured, in those
words.

## The refusal is the feature

Without a token this exits non-zero and names the environment variable, because
that message is the one a person actually meets. Same shape as
`app/feasibility.py` for hardware: say what is missing and what would fix it,
rather than failing inside somebody else's library.

**This never creates, prompts for, prints or stores a credential.** It reads
`HF_TOKEN` (or `HUGGINGFACE_HUB_TOKEN`) if one is already in the environment,
and otherwise stops.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: Read for EXISTENCE only. The value is never printed, logged or written.
TOKEN_VARIABLES = ("HF_TOKEN", "HUGGINGFACE_HUB_TOKEN")

#: What a LoRA adapter directory legitimately contains. Anything else in that
#: directory is NOT uploaded: an adapter folder picks up checkpoints, logs and
#: optimizer state, and publishing whatever happens to sit beside the weights is
#: how a private path or somebody's dataset leaves a machine by accident.
UPLOADABLE = (
    "adapter_config.json",
    "adapter_model.safetensors",
    "adapter_model.bin",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "vocab.json",
    "merges.txt",
)


def the_token() -> str | None:
    """The NAME of the variable that holds a token, or None. Never the value."""
    for name in TOKEN_VARIABLES:
        value = os.environ.get(name)
        if value and value.strip():
            return name
    return None


def read_adapter(directory: Path) -> dict:
    manifest = directory / "adapter_config.json"
    if not manifest.is_file():
        raise SystemExit(
            f"REFUSED: {directory} has no adapter_config.json, so it is not an "
            "adapter and there is nothing to publish."
        )
    body = json.loads(manifest.read_text(encoding="utf-8"))
    weights = [
        n for n in ("adapter_model.safetensors", "adapter_model.bin")
        if (directory / n).is_file()
    ]
    if not weights:
        raise SystemExit(
            f"REFUSED: {directory} has a config and no weights beside it. A "
            "training run killed before it saved leaves exactly this, and "
            "there is nothing in it to publish."
        )
    return {
        "base_model": body.get("base_model_name_or_path"),
        "r": body.get("r"),
        "lora_alpha": body.get("lora_alpha"),
        "target_modules": sorted(body.get("target_modules") or []),
        "bytes": sum((directory / n).stat().st_size for n in weights),
    }


def read_run_record(directory: Path) -> dict:
    """Sequence, batch and measured peak, from the run that made this adapter.

    Absent is reported as absent. A card that silently omitted the peak would
    read as though nothing had been measured; one that guessed it would be the
    invented number this project exists to refuse.
    """
    run_dir = directory.parent
    found: dict = {}
    job = run_dir / "job.json"
    if job.is_file():
        try:
            config = json.loads(job.read_text(encoding="utf-8")).get("config", {})
            for key in (
                "max_seq_len", "batch_size", "max_steps", "learning_rate",
                "grad_checkpointing", "load_in_4bit", "dataset_path",
                # WHICH COLUMNS WERE CONCATENATED, because the realised length
                # has two silent inputs and this is the second one. Naming
                # `text_field` alone takes a different path from naming a
                # prompt/completion pair from naming nothing at all, and on the
                # corpus this lane measures the difference is 95.1 tokens
                # against 206.3 - a 2.17x change in sequence length that no
                # output labels. A card that prints a cap and a peak without
                # saying which columns were trained on is a card whose reader
                # cannot reproduce either number.
                "text_field", "prompt_field", "completion_field",
                "base_dtype", "grad_accum", "lora_r", "seed", "optim",
            ):
                if config.get(key) is not None:
                    found[key] = config[key]
        except (OSError, ValueError):
            pass
    log = run_dir / "job.log"
    if log.is_file():
        try:
            for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
                if not line.startswith("MLH_EVENT ") or '"peak_vram_gb"' not in line:
                    continue
                try:
                    event = json.loads(line[len("MLH_EVENT "):])
                except ValueError:
                    continue
                # THREE PEAKS, THREE NAMES, AND THEY ARE THREE QUANTITIES.
                # This used to read `peak_vram_gb` alone and the card printed it
                # as "measured peak VRAM". Since the recipe learned to reset the
                # allocator before `train()`, that key is the PROCESS HIGH-WATER
                # MARK - the larger of the load transient and training - and the
                # training peak is `peak_train_vram_gb`. The two differ by the
                # fp16 weights that exist briefly before they are quantised
                # away, and every outcome band this lab registers is against the
                # training peak. Publishing the load-inclusive number under the
                # training peak's name is a number measured under one definition
                # read under another, which is the recurring fault of this
                # project wearing a new label.
                for key in ("peak_vram_gb", "peak_train_vram_gb",
                            "peak_load_vram_gb", "num_tokens", "train_runtime"):
                    if event.get(key) is not None:
                        found[key] = event[key]
        except OSError:
            pass
    return found


def _row(label: str, value: object) -> str:
    return f"| {label} | {value if value is not None else '**not recorded**'} |"


def _gib(value: object) -> str | None:
    return None if value is None else f"{value} GiB"


def _cap_and_realised(record: dict) -> str | None:
    """`cap / realised`, or the cap marked as a cap, or nothing.

    Never the cap alone under a bare "max sequence length" label. Research's
    card criterion states the must-not in one line - *print the cap and the
    realised length together, or print neither* - and the reason is that a peak
    is only interpretable beside the length that produced it.
    """
    cap = record.get("max_seq_len")
    tokens = record.get("num_tokens")
    steps = record.get("max_steps")
    batch = record.get("batch_size") or 1
    if cap is None:
        return None
    if tokens is None or not steps:
        return f"cap {cap}, **realised length not recorded**"
    realised = tokens / float(steps) / float(batch)
    # AND WHOSE TOKENS THEY ARE. Measured 2026-09-10 on one corpus: the same 400
    # rows realise 236.4 tokens under SmolLM2's 49,152-entry vocabulary and
    # 217.84 under Qwen's 151,936-entry one - a 9% difference from the tokeniser
    # alone, on identical text. A realised length with no tokeniser beside it
    # invites exactly the comparison that gap makes wrong, and the flagship run
    # was graded against a band computed in another model's tokens before
    # anybody noticed.
    return f"cap {cap} / realised {realised:.0f} tokens (this base's tokeniser)"


def _columns(record: dict) -> str | None:
    """Which columns were concatenated into the training text.

    The second silent input to the realised length. Naming none is a real,
    correct configuration - the recipe concatenates a prompt/completion pair by
    default - so its absence is reported as that rather than as missing.
    """
    named = [f"`{key.split('_')[0]}` = `{record[key]}`"
             for key in ("text_field", "prompt_field", "completion_field")
             if record.get(key) is not None]
    if named:
        return ", ".join(named)
    if record.get("dataset_path") is None:
        return None
    return "no field named - the recipe's concatenating default"


def _usage(base: str, repo: str, record: dict) -> list[str]:
    """The load the run actually did, not a generic one."""
    lines = ["from peft import PeftModel",
             "from transformers import AutoModelForCausalLM, AutoTokenizer"]
    dtype = str(record.get("base_dtype") or "torch.float16").replace("torch.", "")
    if record.get("load_in_4bit"):
        lines[1] = ("from transformers import (AutoModelForCausalLM, "
                    "AutoTokenizer, BitsAndBytesConfig)")
        lines += [
            "",
            "quantization = BitsAndBytesConfig(",
            '    load_in_4bit=True,',
            '    bnb_4bit_quant_type="nf4",',
            "    bnb_4bit_use_double_quant=True,",
            f"    bnb_4bit_compute_dtype=torch.{dtype},",
            ")",
            f'base = AutoModelForCausalLM.from_pretrained(',
            f'    "{base}", quantization_config=quantization, dtype=torch.{dtype}',
            ")",
        ]
    else:
        lines += [
            "",
            f'base = AutoModelForCausalLM.from_pretrained(',
            f'    "{base}", dtype=torch.{dtype}',
            ")",
        ]
    lines += [f'model = PeftModel.from_pretrained(base, "{repo}")',
              f'tokenizer = AutoTokenizer.from_pretrained("{base}")']
    return ["import torch"] + lines


def model_card(adapter: dict, record: dict, repo: str) -> str:
    base = adapter["base_model"] or "unknown"
    modules = ", ".join(f"`{m}`" for m in adapter["target_modules"]) or None
    dataset = record.get("dataset_path")
    lines = [
        "---",
        f"base_model: {base}",
        "library_name: peft",
        "tags:",
        "- lora",
        "- peft",
        "---",
        "",
        f"# {repo}",
        "",
        f"A LoRA adapter for `{base}`, trained locally on a single consumer GPU.",
        "",
        "## What it is",
        "",
        "| | |",
        "|---|---|",
        _row("base model", f"`{base}`"),
        _row("LoRA rank (r)", adapter["r"]),
        _row("LoRA alpha", adapter["lora_alpha"]),
        _row("target modules", modules),
        _row("adapter size on disk", f"{adapter['bytes'] / 1e6:.1f} MB"),
        # A CAP IS NOT A LENGTH, so the two are printed together or not at all.
        # `max_seq_len` is the ceiling a run was allowed; `num_tokens` divided by
        # steps and batch is what it actually fed the model. On this lab's own
        # corpus that is 206 against a cap of 2048, and a card printing only the
        # cap invites its reader to price a sequence ten times the one measured.
        _row("sequence: cap / realised", _cap_and_realised(record)),
        _row("columns trained on", _columns(record)),
        _row("batch size", record.get("batch_size")),
        _row("gradient accumulation", record.get("grad_accum")),
        _row("training steps", record.get("max_steps")),
        _row("4-bit base", record.get("load_in_4bit")),
        # THREE PEAKS UNDER THREE NAMES. The bands are registered against the
        # training peak; the process figure is the high-water mark and must
        # never be read against a band.
        _row("peak VRAM, training", _gib(record.get("peak_train_vram_gb"))),
        _row("peak VRAM, model load", _gib(record.get("peak_load_vram_gb"))),
        _row("peak VRAM, whole process", _gib(record.get("peak_vram_gb"))),
        _row("training data", f"`{Path(str(dataset)).name}`" if dataset else None),
        "",
        "Every figure above is read from the adapter's own `adapter_config.json`",
        "and from the run record that produced it. None of it is typed by hand.",
        "",
        "## What has NOT been measured",
        "",
        "**This adapter has not been scored.** No evaluation number is published",
        "here, because none was produced for this artefact. An adapter without a",
        "paired comparison against its own base, on held-out rows, is a trained",
        "object and not a demonstrated improvement - and claiming otherwise is",
        "exactly what the harness that made it exists to refuse.",
        "",
        "If you want to know whether it helps, run it and the base over the same",
        "held-out rows and compare them pairwise.",
        "",
        "## Using it",
        "",
        "```python",
        *_usage(base, repo, record),
        "```",
        "",
        "The load above is **the one this adapter was trained under**, read from",
        "the run record rather than written by hand. A snippet that omitted the",
        "dtype would load fp32 - four bytes a parameter, which for a 1.5B base",
        "will not fit beside anything on the 8 GiB card that produced this - and",
        "an adapter trained on a 4-bit base behaves differently on a base loaded",
        "any other way. **A card that ships a load its own machine cannot run has",
        "published an untested instruction.**",
        "",
    ]
    return "\n".join(lines)


NO_TOKEN = """
REFUSED: no Hugging Face token is set, so nothing was uploaded and no
repository was created.

Set one of {variables} to a token with write access, from
https://huggingface.co/settings/tokens, and run this again. In PowerShell:

    $env:HF_TOKEN = "hf_..."

This script never creates, prompts for or stores a credential - a token is
yours to place. Everything up to the upload has already been done and can be
inspected: run the same command with --dry-run to write the model card and
list exactly which files would be sent.
"""

NO_CLIENT = """
REFUSED: huggingface_hub is not importable from this interpreter
({executable}).

It is NOT a dependency of the harness and is not in its venv. It IS in every
recipe environment, so run this under one of those:

    recipes/hf-peft-lora/.venv/Scripts/python.exe \\
        scripts/publish_the_adapter.py --adapter ... --repo ...
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish a LoRA adapter.")
    parser.add_argument("--adapter", required=True, help="the adapter directory")
    parser.add_argument("--repo", required=True, help="owner/name on the Hub")
    parser.add_argument("--private", action="store_true", help="create it private")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="write the card and list what would upload; contact nothing",
    )
    args = parser.parse_args(argv)

    directory = Path(args.adapter).expanduser().resolve()
    adapter = read_adapter(directory)
    record = read_run_record(directory)
    card = model_card(adapter, record, args.repo)
    files = [n for n in UPLOADABLE if (directory / n).is_file()]

    # THE PREVIEW MUST BE THE UPLOAD. This line used to list `files` alone while
    # the upload sends `[*files, "README.md"]`, so the list a person inspects
    # before approving a publish omitted THE MODEL CARD - the one file a reader
    # of the repository actually reads, and the one carrying every measured
    # figure. Found by running the refusal on a real adapter rather than
    # asserting it; the behaviour was right and the report was wrong, which is
    # the worse way round for a step whose entire purpose is inspection before
    # upload. Built from the same expression the upload iterates, so the two
    # cannot drift apart again.
    would_send = [*files, "README.md"]

    print(f"adapter : {directory}")
    print(f"base    : {adapter['base_model']}")
    print(f"repo    : {args.repo}")
    print(f"files   : {', '.join(would_send) or '(none)'}")
    # THREE PEAKS, THREE NAMES, here too. The card was fixed and this summary
    # one line below it was not: it printed `peak_vram_gb` - the process
    # high-water mark since the recipe learned to reset the allocator - under
    # the unqualified label "peak", which is the exact defect the card carried.
    for label, key in (("peak train", "peak_train_vram_gb"),
                       ("peak load ", "peak_load_vram_gb"),
                       ("peak proc ", "peak_vram_gb")):
        print(f"{label}: {record.get(key, 'not recorded')}")

    if args.dry_run:
        (directory / "README.md").write_text(card, encoding="utf-8")
        print(
            f"\nDRY RUN. Card written to {directory / 'README.md'}. "
            "Nothing was uploaded and nothing was contacted."
        )
        return 0

    variable = the_token()
    if variable is None:
        print(NO_TOKEN.format(variables=" or ".join(TOKEN_VARIABLES)), file=sys.stderr)
        return 2

    try:
        from huggingface_hub import HfApi
    except ImportError:
        print(NO_CLIENT.format(executable=sys.executable), file=sys.stderr)
        return 3

    (directory / "README.md").write_text(card, encoding="utf-8")
    api = HfApi(token=os.environ[variable])
    api.create_repo(args.repo, repo_type="model", private=bool(args.private),
                    exist_ok=True)
    for name in would_send:
        api.upload_file(
            path_or_fileobj=str(directory / name),
            path_in_repo=name,
            repo_id=args.repo,
            repo_type="model",
        )
    print(f"\npublished: https://huggingface.co/{args.repo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
