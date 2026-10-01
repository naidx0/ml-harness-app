"""What dtype the embedding is actually in, before and after the peft call.

    python scripts/what_dtype_is_the_embedding.py [--base HuggingFaceTB/SmolLM2-1.7B]

Run it with a recipe's interpreter, which is the only one that can do the load:

    recipes/hf-peft-lora/.venv/Scripts/python.exe scripts/what_dtype_is_the_embedding.py

## The 0.435 GiB fork, and why neither reading of the source settles it

`docs/judge_runs/2026-09-09-what-actually-fits-measured-at-two-model-sizes.md`
reports a MEASURED parameter inventory after a 4-bit load:

    quantised, torch.uint8        805,306,368 params  ->  0.750 GiB
    left torch.float16            100,763,648 params  ->  0.188 GiB
    resident after the 4-bit load                         0.962 GiB

and concludes *"the embedding is fp16."* Research read two lines of the pinned
source and reached the opposite conclusion, and **both of its readings are
correct as readings** - verified in this repository's own venv:

* `peft/utils/other.py`, inside `prepare_model_for_kbit_training`:
  *"cast all non INT8 parameters to fp32"* - every fp16/bf16 parameter that is
  not a `Params4bit` goes to fp32.
* `transformers/integrations/bitsandbytes.py::get_keys_to_not_convert` returns
  the tied keys plus the last module as untouched, so `nn.Embedding` is never
  quantised.

So the two facts are not in conflict at all - they are about TWO DIFFERENT
MOMENTS, and the page above does not record which moment its inventory was
taken at. That is the whole of the disagreement: 0.188 GiB fp16 or 0.375 GiB
fp32, a difference that carried to Qwen's larger vocabulary is 0.435 GiB -
wider than the gap between two of the three registered outcome bands.

**The inventory was ad hoc and left no script**, which is why a number with real
provenance still cannot answer a question about its own order. This is that
script, and it takes the inventory on BOTH SIDES of the call, so the answer does
not depend on anybody remembering when the first one ran.

## Two things it does that the ad hoc version did not

**`remove_duplicate=False`.** `Module.named_parameters` deduplicates by default,
so a tied embedding and `lm_head` sharing one tensor appear ONCE. That is the
right default for counting memory and the wrong one for asking whether the tie
is intact - a deduplicated dump cannot tell a tied pair from a broken one, and
which of those is true is the other half of the same question. Both counts are
taken and the pair is reported.

**It refuses rather than reporting a number from a different configuration.**
No CUDA, or no bitsandbytes, means the load is not the load the question is
about; an fp32 CPU inventory printed under this script's name would answer a
question nobody asked, in the reassuring direction.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict

DEFAULT_BASE = "HuggingFaceTB/SmolLM2-1.7B"


def inventory(model) -> dict:
    """Bytes and counts by dtype, both deduplicated and not.

    `numel() * element_size()` rather than a dtype table, because a `Params4bit`
    is stored as packed `uint8` and its element size is the honest byte count.
    """
    rows = []
    by_dtype: dict = defaultdict(lambda: {"params": 0, "bytes": 0, "tensors": 0})
    for name, param in model.named_parameters(remove_duplicate=False):
        kind = str(param.dtype)
        klass = type(param).__name__
        size = param.numel() * param.element_size()
        key = kind + "|" + klass
        by_dtype[key]["params"] += param.numel()
        by_dtype[key]["bytes"] += size
        by_dtype[key]["tensors"] += 1
        rows.append({"name": name, "dtype": kind, "class": klass,
                     "numel": param.numel(), "bytes": size})

    deduped = {id(p) for _, p in model.named_parameters(remove_duplicate=True)}
    everything = [id(p) for _, p in model.named_parameters(remove_duplicate=False)]
    return {
        "by_dtype": {k: dict(v) for k, v in sorted(by_dtype.items())},
        "total_bytes_with_duplicates": sum(r["bytes"] for r in rows),
        "tensors_with_duplicates": len(everything),
        "tensors_deduplicated": len(deduped),
        "rows": rows,
    }


def embedding_rows(inv: dict) -> list:
    return [r for r in inv["rows"]
            if "embed" in r["name"].lower() or "lm_head" in r["name"].lower()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--json", default=None, help="write the full dump here")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    try:
        import torch
        from transformers import AutoModelForCausalLM, BitsAndBytesConfig
        from peft import prepare_model_for_kbit_training
        import bitsandbytes  # noqa: F401 - fail HERE rather than inside transformers
    except ImportError as absent:
        print("REFUSED: this interpreter cannot do the 4-bit load: "
              + str(absent) + ".\nRun it in a recipe environment: "
              "recipes/hf-peft-lora/.venv/Scripts/python.exe", file=sys.stderr)
        return 2
    if not torch.cuda.is_available():
        print("REFUSED: no CUDA. A CPU inventory is a different configuration "
              "and would answer a question nobody asked.", file=sys.stderr)
        return 2

    # EXACTLY THE RECIPE'S LOAD. Copied rather than imported, because the point
    # is to measure what `recipes/hf-peft-lora/entrypoint.py` does; if the two
    # ever drift, the drift is the finding and a shared helper would hide it.
    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.float16,
    )
    torch.cuda.reset_peak_memory_stats(0)
    model = AutoModelForCausalLM.from_pretrained(
        args.base, quantization_config=quantization, dtype=torch.float16
    )
    before = inventory(model)
    before_resident = torch.cuda.memory_allocated(0)
    before_peak = torch.cuda.max_memory_allocated(0)

    # `use_gradient_checkpointing=True` is what entrypoint.py passes when its
    # own flag is set, which is the configuration every published peak was
    # measured under.
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    after = inventory(model)
    after_resident = torch.cuda.memory_allocated(0)
    after_peak = torch.cuda.max_memory_allocated(0)

    gib = 1024 ** 3
    tied = before["tensors_with_duplicates"] > before["tensors_deduplicated"]
    print("base                 " + args.base)
    print("tied?                "
          + str(before["tensors_with_duplicates"]) + " tensors with duplicates, "
          + str(before["tensors_deduplicated"]) + " deduplicated -> "
          + ("TIED" if tied else "NOT TIED"))
    for label, inv, resident, peak in (
        ("BEFORE prepare_model_for_kbit_training", before, before_resident, before_peak),
        ("AFTER  prepare_model_for_kbit_training", after, after_resident, after_peak),
    ):
        print("\n--- " + label)
        for key, row in inv["by_dtype"].items():
            print("    {:<34} {:>13,} params  {:>7.3f} GiB  ({} tensors)".format(
                key, row["params"], row["bytes"] / gib, row["tensors"]))
        print("    {:<34} {:>29.3f} GiB".format(
            "parameter bytes (with duplicates)",
            inv["total_bytes_with_duplicates"] / gib))
        print("    {:<34} {:>29.3f} GiB".format(
            "cuda resident (memory_allocated)", resident / gib))
        print("    {:<34} {:>29.3f} GiB".format("cuda peak so far", peak / gib))
        for row in embedding_rows(inv):
            print("      {:<44} {:<16} {:>13,}  {:.3f} GiB".format(
                row["name"], row["dtype"], row["numel"], row["bytes"] / gib))

    if args.json:
        from pathlib import Path

        Path(args.json).write_text(json.dumps(
            {"base": args.base,
             "before": {k: v for k, v in before.items() if k != "rows"},
             "after": {k: v for k, v in after.items() if k != "rows"},
             "before_resident_bytes": before_resident,
             "after_resident_bytes": after_resident,
             "before_peak_bytes": before_peak,
             "after_peak_bytes": after_peak,
             "embedding_before": embedding_rows(before),
             "embedding_after": embedding_rows(after)},
            indent=2), encoding="utf-8")
        print("\nwrote " + args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
