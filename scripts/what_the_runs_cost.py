"""Every run on this disk, what it cost, and what it will not say.

    python scripts/what_the_runs_cost.py              # every run, one line each
    python scripts/what_the_runs_cost.py --priceable  # only the ones that price
    python scripts/what_the_runs_cost.py --missing    # only the ones that do not

## Why this exists, and it is not convenience

Three readers counted the priceable runs on this disk tonight and got 0, 5 and
33. None was lying and none had a broken regex:

* **0** - globbed `runs/*/job.json`, and the records are deeper.
* **33** - counted every run naming a base and reporting a peak.
* **5** - required base, sequence, batch, checkpointing AND peak.

They are the same tree read under different definitions of *priceable*, and the
ladder below prints every rung: 33 carry a base and a peak, **17 of those are
training peaks and the rest measure inference**, 14 of those record sequence and
batch, and 5 of those record checkpointing. Nobody was wrong; each was standing
on a different rung and reporting the height. The argument cannot be had while a
total is the only thing either side can see. **If a reader has to know the directory layout to count the
runs, the layout is the record and the record is decoration.** So this prints
the rows, not a total, and the total is something a reader can recompute from
what is printed.

## The column that decides the count

`ckpt` is the one that moves 33 to 5, and it is worth reading carefully:

* **`True` / `False`** - the config said so. A measurement of a configuration.
* **`(default)`** - the config did not say, and `recipes/hf-peft-lora` resolves
  it to True at line 405. The run almost certainly used checkpointing. The
  record still does not KNOW it, because a value the runner defaulted is
  DEFAULTED and not MEASURED, and this project keeps those apart everywhere
  else. Measured: 49 of the 54 run records are in this state, and 9 of them
  would otherwise price on all five fields.

That is the whole disagreement, printed rather than argued. A reader who wants
the 33 can take `(default)` at face value; a reader fitting an estimator to
these numbers should not, because the runs that would falsify a checkpointing
assumption are exactly the ones that do not record it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app import run_record  # noqa: E402  - after the path is set

#: What `recipes/hf-peft-lora/entrypoint.py` resolves the field to when a config
#: is silent, read once here so the note beside a row is a fact about the recipe
#: rather than a guess by this script. NOT applied to the record: this script
#: annotates, it does not fill in.
THE_RECIPES_DEFAULT = True

EVERY = 0
NOTHING_TO_READ = 1


def a_row(run_dir: Path) -> dict:
    """One run, with the descriptive columns the record does not carry."""
    record = run_record.read(run_dir) or {}
    try:
        spec = json.loads((run_dir / "job.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        spec = {}
    config = spec.get("config") or {}
    return {
        "where": str(run_dir.relative_to(REPO)) if run_dir.is_relative_to(REPO) else str(run_dir),
        "recipe": spec.get("recipe") or "?",
        "kind": record.get("kind") or spec.get("kind") or "?",
        "base": str(record.get("base_model") or "?").split("/")[-1],
        "seq": record.get("max_seq_len"),
        "batch": record.get("batch_size"),
        "r": config.get("lora_r"),
        "ckpt": record.get("grad_checkpointing"),
        "peak": record.get("peak_vram_gb"),
        "from": record.get("peak_from"),
        "missing": run_record.missing_from(record),
    }


def say(value, when_absent: str = "-") -> str:
    return when_absent if value is None else str(value)


def ckpt_of(row: dict) -> str:
    """`True`, `False`, or the recipe's default said out loud as an assumption."""
    if row["ckpt"] is None:
        return f"({str(THE_RECIPES_DEFAULT).lower()}?)"
    return str(row["ckpt"]).lower()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--priceable", action="store_true", help="only runs that price")
    parser.add_argument("--missing", action="store_true", help="only runs that do not")
    parser.add_argument("--root", default=str(REPO / "runs"))
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    rows = [a_row(where) for where in run_record.every_run(Path(args.root))]
    if not rows:
        print(f"no run records under {args.root}", file=sys.stderr)
        return NOTHING_TO_READ

    shown = rows
    if args.priceable:
        shown = [row for row in rows if not row["missing"]]
    elif args.missing:
        shown = [row for row in rows if row["missing"]]

    print(f"{'base':14} {'kind':6} {'seq':>5} {'bs':>3} {'r':>3} {'ckpt':>8} "
          f"{'peak':>6} {'from':>13}  where")
    for row in sorted(shown, key=lambda r: (r["base"], say(r["seq"]), say(r["batch"]))):
        print(
            f"{row['base'][:14]:14} {str(row['kind'])[:6]:6} {say(row['seq']):>5} "
            f"{say(row['batch']):>3} {say(row['r']):>3} {ckpt_of(row):>8} "
            f"{say(row['peak']):>6} {say(row['from']):>13}  {row['where']}"
        )

    priceable = [row for row in rows if not row["missing"]]
    #: THE NUMBER A READER CAN RECOMPUTE, and the one the arguments were about.
    only_for_want_of_checkpointing = [
        row for row in rows if row["missing"] == ("grad_checkpointing",)
    ]
    #: THE LADDER, because three readers got 0, 5 and 33 and every one of those
    #: numbers is a different rung. Printed in order so a disagreement lands on
    #: a rung rather than on a total.
    def carrying(*fields):
        return [r for r in rows if all(r.get(f) is not None for f in fields)]

    with_peak = carrying("base", "peak")
    training = [r for r in with_peak if r["kind"] == "train" and r["from"] == "finished"]
    geometry = [r for r in training if r["seq"] is not None and r["batch"] is not None]

    print()
    print(f"{len(rows)} run record(s) under {args.root}")
    print(f"  base + peak                       : {len(with_peak)}")
    print(f"    ...of which TRAINING peaks      : {len(training)}   (the rest measure inference)")
    print(f"      ...with sequence and batch    : {len(geometry)}")
    print(f"        ...and checkpointing        : {len(priceable)}")
    print(f"  would price but for checkpointing : {len(only_for_want_of_checkpointing)}")

    shapes = sorted({(r["base"], r["seq"], r["batch"]) for r in training}, key=str)
    known = [s for s in shapes if s[1] is not None and s[2] is not None]
    print()
    print(f"distinct training configurations: {len(shapes)}, "
          f"of which {len(known)} have a known geometry")
    for base, seq, batch in shapes:
        peaks = sorted({r["peak"] for r in training
                        if (r["base"], r["seq"], r["batch"]) == (base, seq, batch)})
        note = "" if seq is not None and batch is not None else "   <- geometry unrecorded"
        print(f"   {base:14} seq {say(seq):>5}  batch {say(batch):>3}   "
              f"peak {', '.join(str(p) for p in peaks)}{note}")
    print()
    print("`(true?)` is the recipe's default showing through, not a recorded value.")
    return EVERY


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
