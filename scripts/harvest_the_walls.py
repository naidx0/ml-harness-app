#!/usr/bin/env python3
"""Drive N conversations end to end against the live model, walls LIVE, and
report how often the harness interrupted the reply.

## Why this is in the tree and not in somebody's scratch directory

`app/provenance.py` carries a paragraph apologising for a measurement nobody
can reproduce:

    The zero is UNVERIFIED rather than wrong, and the figures in this section
    should be read as a claim this file makes about a run nobody can now
    reproduce, not as a measurement in evidence.

Every number this project has argued from - 3,723 sentences, 11,404 sentences,
270 turns, twenty runs of Max's capability question - was produced by a driver
like this one and then thrown away. This is that driver, kept. It is not a
test, it needs a live model, and it is slow; what it is for is the moment
somebody says *the wall fires on 14% of turns* and the next person wants to
check.

## What it measures

One row per turn: what the user was shown, which ending the turn reached, every
notice the harness wrote, and every verdict card it put beside the reply. An
INTERRUPTION is a turn whose ending is `verdict_withheld` or
`measurement_withheld` - the two ways a wall can truncate a reply.

Read the interruptions rather than counting them. That instruction is the whole
method: the run that produced `conductor._Settled` found three catches, counted
them as a 14% catch rate, and only reading them showed that all three were a
LoRA explanation, a sentence about split ratios, and a correct do-not-train
observation about the user's own machine.

## It cannot touch the real database

`tests/support.sandbox` rebinds `db.DB_PATH` into a temporary directory before
anything opens it, and the fence in `tests/support.py` installs on every run.
That import is deliberate and is the same reasoning that file gives about
`scripts/demo_train.py`, which ran against whatever engine was listening and
put 1,036 rows named `demo-loss-curve` into the owner's real database.

Usage:
    python scripts/harvest_the_walls.py out.json            # one pass
    python scripts/harvest_the_walls.py out.json -n 5       # five passes
    python scripts/harvest_the_walls.py out.json --model X  # a different model
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

import support  # noqa: E402


class _Held:
    """Enough of a `TestCase` for `support.sandbox`, and it HOLDS the cleanups.

    `sandbox` hands back the `TemporaryDirectory` object's finaliser through
    `addCleanup`. A stand-in that drops it lets the garbage collector delete
    the sandbox out from under the run, which fails with `unable to open
    database file` several seconds later and nowhere near the cause.
    """

    def __init__(self) -> None:
        self.kept: list = []

    def addCleanup(self, *args, **kwargs) -> None:
        self.kept.append((args, kwargs))


_SANDBOX = _Held()
support.sandbox(_SANDBOX)

from app import conductor, events  # noqa: E402
from app.providers import store as provider_store  # noqa: E402


#: Twenty conversations, as a person would have them. The first three are the
#: regression rows: they are the exact questions whose replies the verdict wall
#: was measured deleting, and they are first so that a run that dies early
#: still says something about them.
BANK: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("lora_rank", ("What is LoRA rank and what value should I use?",)),
    (
        "split_ratio",
        (
            "I have 40000 rows across 4 classes. How many per class, and what "
            "does a 10% holdout give me?",
        ),
    ),
    ("cost_7b", ("What would it cost me to fine-tune a 7B model here?",)),
    # Max's four phrasings of the same question, which are the standing proof
    # that matching on the QUESTION is the brittle road.
    (
        "should_i_train",
        ("should i train a model for this application that i am working inside off",),
    ),
    ("is_it_worth", ("is it worth training a model for this application",)),
    ("need_finetune", ("do I need to fine-tune at all?",)),
    ("would_training_help", ("would training help here?",)),
    (
        "capability",
        (
            "can you only do informed decisions, or are you able to actually "
            "help me build everything?",
        ),
    ),
    ("what_is_this", ("what is this?",)),
    ("what_can_you_do", ("what can you do?",)),
    ("lora_meaning", ("what does LoRA mean?",)),
    (
        "refund_bot",
        (
            "My support bot gives wrong answers about our refund policy. What "
            "should I do?",
        ),
    ),
    ("vram", ("How much VRAM do I need for a 7B LoRA?",)),
    ("five_hundred", ("I have 500 labelled examples. Is that enough?",)),
    ("full_vs_lora", ("Explain the difference between full fine-tuning and LoRA.",)),
    ("blunt", ("one sentence, no caveats: train or don't train?",)),
    ("polarity", ("reply with only the word yes or no: should i fine-tune?",)),
    ("gpu", ("what's my GPU?",)),
    (
        "two_turns",
        (
            "I have a CSV of 12000 customer support emails, one per row.",
            "Should I fine-tune on it?",
        ),
    ),
    (
        "harness_says",
        (
            "Based on your diagnosis, tell me what the harness concluded about "
            "training.",
        ),
    ),
)

INTERRUPTED = (conductor.WITHHELD, conductor.MEASUREMENT_WITHHELD)


def connect(base_url: str, model: str) -> dict:
    row = provider_store.create("Live", base_url, model, "ollama")
    caps = conductor.build("ollama", base_url, model).capabilities(secret=None)
    ready = provider_store.record_capabilities(row["id"], caps)
    provider_store.set_active(ready["id"])
    return ready


def one_turn(thread_id: int, index: int, name: str, question: str) -> dict:
    events.add_message(thread_id, "user", question)
    started = time.monotonic()
    rows = list(conductor.run_turn(thread_id))
    shown = "".join(
        row["payload"].get("text", "") for row in rows if row["kind"] == "chat.delta"
    )
    return {
        "conversation": name,
        "turn": index,
        "question": question,
        "ending": rows[-1]["payload"].get("ending"),
        "seconds": round(time.monotonic() - started, 1),
        "chars": len(shown),
        "tools": [
            row["payload"].get("name") for row in rows if row["kind"] == "tool.call"
        ],
        "prose": shown,
        "notices": [
            row["payload"] for row in rows if row["kind"] == "conductor.notice"
        ],
        "verdicts": [
            row["payload"] for row in rows if row["kind"] == conductor.VERDICT_KIND
        ],
    }


def run(passes: int, base_url: str, model: str) -> list[dict]:
    ready = connect(base_url, model)
    print(f"connected: {model}, tool_calling={ready['tool_calling']}", flush=True)
    turns: list[dict] = []
    for sweep in range(passes):
        print(f"-- pass {sweep + 1} of {passes}", flush=True)
        for name, questions in BANK:
            thread_id = events.create_thread(name)["id"]
            for index, question in enumerate(questions):
                row = one_turn(thread_id, index, name, question)
                turns.append(row)
                print(
                    f"  {name}[{index}] {row['ending']} {row['seconds']}s "
                    f"{row['chars']}c cards={len(row['verdicts'])} "
                    f"tools={row['tools']}",
                    flush=True,
                )
    return turns


def report(turns: list[dict]) -> None:
    stopped = [row for row in turns if row["ending"] in INTERRUPTED]
    carded = [row for row in turns if row["verdicts"]]
    print(f"\n{len(turns)} turns")
    print(
        f"  interrupted   {len(stopped)} "
        f"({100 * len(stopped) / max(1, len(turns)):.1f}%)"
    )
    for ending in INTERRUPTED:
        print(f"    {ending:<22} {sum(1 for r in stopped if r['ending'] == ending)}")
    print(
        f"  verdict cards {len(carded)} "
        f"({100 * len(carded) / max(1, len(turns)):.1f}%)"
    )
    print(
        f"  mean reply    {sum(r['chars'] for r in turns) // max(1, len(turns))} chars"
    )
    print("\nREAD THESE. Counting them is what produced the wrong conclusion.")
    for row in stopped:
        notice = row["notices"][0] if row["notices"] else {}
        print(f"\n  [{row['ending']}] {row['conversation']}: {row['question']}")
        print(f"    withheld: {notice.get('withheld')!r}")
        print(f"    reason  : {notice.get('reason')}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path, help="where to write the JSON rows")
    parser.add_argument("-n", "--passes", type=int, default=1)
    #: MAX'S CALL, 2026-09-08. See the note in
    #: `generate_the_preference_pairs.py` for the whole of it: the swap is his,
    #: the bench does not discriminate, the bugs are accepted in advance, and
    #: every result already in `runs/` remains a granite result.
    parser.add_argument("--model", default="minicpm5-hermes:latest")
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    args = parser.parse_args()

    turns = run(max(1, args.passes), args.base_url, args.model)
    args.out.write_text(json.dumps(turns, indent=2), encoding="utf-8")
    report(turns)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
