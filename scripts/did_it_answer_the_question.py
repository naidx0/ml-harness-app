#!/usr/bin/env python3
"""Drive a bank of questions against the live model and grade ONE thing:
**did the reply answer the question that was asked?**

## Why this exists and why it is not `harvest_the_walls.py`

That driver measures the WALLS - how often the harness interrupted a reply.
This one measures the defect that was left when the walls stopped being the
loudest thing in the transcript, and it is Max's original complaint: he asked
the product a question and got a gate ledger back. It has been fixed by prose
four times. Prose is not a wall, and the way anybody knows that is that
somebody ran a bank like this one before and after.

## THE RULER WAS WRONG, AND THAT IS THE MOST IMPORTANT THING IN THIS FILE

The detector that measured the last fix was `GATE_WORDS`: a hand-written list
of strings - `G0_EVAL_SET`, `NOT_REACHED`, `gates 0 of`, `define success`. It
was written against the wording the fix had just removed, so it went on
reporting a shape that had already changed clothes. Re-measured on this tree,
125 live non-training turns:

    a reader, going through every reply        15 of 125   (12%)
    the honest detector below                  13 of 125, 13 of them right
    `GATE_WORDS`                                7 of 125,  6 of them right

It sees 6 of the 15 occurrences a reader sees, and one of its seven catches is
a good answer explaining the five gates to somebody who asked what this product
can do. The committed claim `gate material 15/140 -> 6/140` is that proxy, and
it is optimistic by roughly the same 60% an earlier adversary found by hand.

**A DETECTOR WRITTEN AGAINST THE SHAPE YOU JUST FIXED WILL ALWAYS SAY YOU FIXED
IT.** That is not a bug in that list, it is what a vocabulary is: it can only
ever see the phrasing its author had in front of them, and the thing it watches
is a moving target because every fix moves it.

The replacement is a LOOKUP and not a vocabulary. On any turn, the engine's own
sentence is knowable exactly - the harness computed it, `conductor` renders it
through `verdict_sentence`, and the driver records it beside the reply. So the
question "did the model recite the engine's sentence?" is answered by comparing
the reply against THAT STRING, whatever it currently says. Change the engine's
`say` tomorrow and this detector changes with it, with nothing here to edit.
That is the same distinction that made the provenance wall work where the
verdict sentry could not: ask the records, do not ask a word list.

`recites_the_engine` is the detector and its docstring holds the calibration -
what it catches, what it misses, and the reading it was checked against.
`gate_words` is kept beside it, marked as the old proxy, so a re-score of any
file prints both and the gap between them stays visible rather than becoming
folklore.

## The bank

Twenty-nine questions across nine kinds, because the kinds are the finding. A
definitional question and a training question are not the same question wearing
different words - what their answers are MADE OF differs, and that is the
distinction every fix in this area has turned on:

    definitional  the model's own knowledge. No fact is needed. No tool.
    risk          the same.
    offtopic      the same, and not about this product at all.
    capability    the tool registry. Complete before anything runs.
    machine       an instrument on this machine.
    data          an instrument over the user's files.
    user_number   a number the USER supplied, this turn or the one before.
    two_part      one training half and one definitional half, in one message.
    training      the fact ledger, walked by the engine.

Only the last one is made of the decision tree. The four training phrasings are
Max's own, kept verbatim, and they are the regression rows: a fix that wins the
first eight kinds by making the training question stop reaching the engine has
traded the product away, which has happened twice.

`user_number` rows may carry a `prior` message. It is RUN as a real turn
against the live model before the graded question is asked - a fabricated
assistant reply would be a fabricated transcript, and the thing under test is
whether the harness can hold a number the user said one turn ago.

## The grading, which is mechanical so that it can be re-run

Three independent readings per reply, all printed:

* `answered` - does the reply contain what an answer to THIS question is made
  of? Declared per question as groups of alternatives; every group must match.
  A group is a facet ("the retrieval half", "the weights half"), so a reply
  that names one side of a comparison and not the other does not count.
* `recital` - did the reply give back the ENGINE'S OWN SENTENCE for this turn,
  rather than an answer? Computed against the recorded sentence, not a word
  list. This is the defect, named directly.
* `gate_words` - the OLD detector, kept only so its optimism stays measurable.

A keyword grader is not a judge and this file does not pretend otherwise. It
undercounts a right answer that used different words and it cannot see a reply
that is fluent and wrong. What it can do is be identical before and after, and
that is what a before/after needs. `--read` prints every reply so the numbers
can be checked by eye, which is how the last four fixes were found to be prose
and how this file's own ruler was found to be wrong.

## It cannot touch the real database

`tests/support.sandbox` rebinds `db.DB_PATH` into a temporary directory before
anything opens it, exactly as `scripts/harvest_the_walls.py` does and for the
reason written there.

## What this bank has measured, so a re-run has something to disagree with

145 turns a side against granite4-hermes at 3966702 and at the tree that
followed it, five passes of twenty-nine questions, two shards:

    column                            before     after        p
    recital, non-training           13 of 125   3 of 125    0.017
    answered, non-training          97 of 125  94 of 125    0.766
    THE FOUR TRAINING, answered      19 of 20   20 of 20    1.000
    empty replies, all               0 of 145   2 of 145    0.498
    gate_words, non-training          7 of 125   5 of 125    0.769

The last row is the old detector on the same two files, and it is the reason
this file was rewritten before anything it measures was touched: **it says the
change did nothing.**

`--compare before.json after.json` prints that table. `fisher` computes the p
column exactly, with `math.comb` and no dependency, and it was checked against
`scipy.stats.fisher_exact` on 300 random tables and on the three p values
already committed to this tree before it was believed.

## Run it with the same concurrency on both sides

Two shards is what the before and after in `conductor.constant_record` were
both run at. It matters: three concurrent drivers against one Ollama saturated
it here and turns stopped returning at all, which looks exactly like a harness
that hangs. If a run goes quiet, check `/api/ps` before blaming the tree.

Usage:
    python scripts/did_it_answer_the_question.py out.json -n 5
    python scripts/did_it_answer_the_question.py out.json -n 5 --shard 0/2
    python scripts/did_it_answer_the_question.py out.json -n 5 --kind training
    python scripts/did_it_answer_the_question.py --score out.json --read
    python scripts/did_it_answer_the_question.py --compare before.json after.json
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from pathlib import Path
from typing import NamedTuple

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

import support  # noqa: E402


class _Held:
    """Enough of a `TestCase` for `support.sandbox`, and it HOLDS the cleanups.

    See `scripts/harvest_the_walls.py`: a stand-in that drops the finaliser
    lets the garbage collector delete the sandbox out from under the run.
    """

    def __init__(self) -> None:
        self.kept: list = []

    def addCleanup(self, *args, **kwargs) -> None:
        self.kept.append((args, kwargs))


#: Groups of alternatives. Every group must match somewhere in the reply, and a
#: group matches if any of its strings appears. Lowercased, substring.
Needs = tuple[tuple[str, ...], ...]


class Q(NamedTuple):
    """One row of the bank.

    `prior` is a user message that is RUN as a real turn before the graded one,
    which is what makes `user_number` a two-turn kind rather than a fabricated
    transcript. `None` for every single-turn row, which is most of them.
    """

    name: str
    kind: str
    question: str
    needs: Needs
    prior: str | None = None


#: name, kind, question, what an answer to it is made of.
BANK: tuple[Q, ...] = (
    # -- definitional: made of the model's own knowledge, no fact needed ----
    Q(
        "lora",
        "definitional",
        "What is LoRA?",
        (("low-rank", "low rank", "adapter", "rank"),
         ("weight", "matri", "parameter", "layer")),
    ),
    Q(
        "rag_vs_finetuning",
        "definitional",
        "What is the difference between RAG and fine-tuning?",
        (("retriev", "rag", "index", "search", "look up", "looks up"),
         ("weight", "parameter", "fine-tun", "finetun", "train")),
    ),
    Q(
        "quantization",
        "definitional",
        "What does quantization mean?",
        (("bit", "precision", "float", "fp16", "int8", "smaller"),),
    ),
    Q(
        "epoch",
        "definitional",
        "What is an epoch in training?",
        (("pass", "iterat", "cycle", "sweep", "once through", "one complete"),
         ("dataset", "data set", "training data", "examples", "rows")),
    ),
    Q(
        "full_vs_lora",
        "definitional",
        "Explain the difference between full fine-tuning and LoRA.",
        (("all the weight", "all weight", "every parameter", "all parameters",
          "all of the parameters", "entire model", "whole model", "full model",
          "all the parameters", "updates all"),
         ("low-rank", "low rank", "adapter", "rank", "small number of",
          "few parameters", "frozen")),
    ),
    # -- risk: also made of the model's own knowledge ------------------------
    Q(
        "small_data_risk",
        "risk",
        "What are the risks of fine-tuning on a small dataset?",
        (("overfit", "memoris", "memoriz", "forget", "catastrophic",
          "generalis", "generaliz", "noise", "brittle", "variance"),),
    ),
    Q(
        "what_goes_wrong",
        "risk",
        "What can go wrong when I fine-tune a model?",
        (("overfit", "forget", "catastrophic", "degrad", "regress",
          "data quality", "leak", "hallucinat", "generalis", "generaliz",
          "bias", "cost"),),
    ),
    Q(
        "rag_downsides",
        "risk",
        "What are the downsides of using RAG?",
        (("latency", "chunk", "irrelevant", "context window", "retriev",
          "index", "stale", "top-k", "recall", "slower", "cost"),),
    ),
    # THE 0-OF-4 ROW. Max's first message in 2026, and the live proof that the
    # recital is not a rounding error: three of four replies came back asking
    # him to define success and supply twenty inputs.
    Q(
        "synthetic_data",
        "risk",
        "What could go wrong if I train on synthetic data generated by "
        "another model?",
        (("collaps", "distribution", "bias", "amplif", "artifact", "diversity",
          "hallucinat", "error", "quality", "drift", "inherit", "propagat",
          "narrow", "licen", "overfit", "echo", "degrad", "homogen"),),
    ),
    # -- capability: made of the tool registry -------------------------------
    Q(
        "capability",
        "capability",
        "can you only do informed decisions, or are you able to actually "
        "help me build everything?",
        (("i can", "i am able", "yes", "can help", "able to"),
         ("train", "index", "retriev", "eval", "dataset", "prompt", "profil",
          "sandbox", "build", "run")),
    ),
    Q(
        "build_things",
        "capability",
        "can you actually build things, or do you just give advice?",
        (("i can", "i am able", "yes", "can help", "able to", "not just"),
         ("train", "index", "retriev", "eval", "dataset", "prompt", "profil",
          "sandbox", "build", "run")),
    ),
    Q(
        "what_can_you_do",
        "capability",
        "what can you do?",
        (("train", "index", "retriev", "eval", "dataset", "prompt", "profil",
          "sandbox", "hardware", "model"),),
    ),
    Q(
        "what_is_this",
        "capability",
        "what is this?",
        (("harness", "machine learning", "ml", "assistant", "tool"),),
    ),
    # -- machine: made of an instrument on this machine ----------------------
    Q(
        "gpu",
        "machine",
        "what GPU do I have?",
        (("gpu", "vram", "cuda", "nvidia", "amd", "integrated", "graphics",
          "no discrete", "accelerator"),),
    ),
    Q(
        "ram",
        "machine",
        "how much RAM does this machine have?",
        (("gb", "ram", "memory"),),
    ),
    # -- data: made of an instrument over the user's files -------------------
    Q(
        "whats_in_my_dataset",
        "data",
        "what is in my dataset?",
        (("path", "where", "which", "attach", "point me", "folder", "file",
          "csv", "jsonl", "haven't", "have not", "no dataset", "not attached",
          "profile"),),
    ),
    Q(
        "what_datasets",
        "data",
        "what datasets do I have here?",
        (("attach", "context", "none", "no dataset", "nothing", "not yet",
          "folder", "file", "path", "empty", "haven't", "have not"),),
    ),
    # -- user_number: the number is in the thread, said by the user ----------
    # An answer to one of these has to USE the number. A reply that never
    # touches it answered a different, more general question - which is the
    # failure this kind exists to catch, and it was 2 of 8 before this run.
    Q(
        "enough_rows",
        "user_number",
        "I have 340 labelled examples. Is that enough to fine-tune?",
        (("340",),
         ("enough", "too few", "small", "depend", "more", "sufficient", "few",
          "start", "rule of thumb", "typical", "lora", "adapter")),
    ),
    Q(
        "vram_fit",
        "user_number",
        "My GPU has 8 GB of VRAM. What size model could I fine-tune on it?",
        (("8 gb", "8gb", "8 gigabyte", "8gb of", "8 gb of"),
         ("7b", "3b", "8b", "1b", "2b", "4b", "billion", "parameter", "qlora",
          "4-bit", "quantiz", "lora")),
    ),
    Q(
        "eval_rows_followup",
        "user_number",
        "Is that enough?",
        (("200",),
         ("enough", "depend", "more", "small", "few", "sufficient", "typical",
          "rule", "start")),
        prior="I have 200 rows in my eval set.",
    ),
    Q(
        "cost_followup",
        "user_number",
        "How long would that take to train?",
        (("50000", "50,000", "50k"),
         ("hour", "minute", "depend", "epoch", "throughput", "measure",
          "estimate", "unknown", "cannot", "can't", "don't know")),
        prior="My dataset has 50000 rows and I want to fine-tune a 7B model.",
    ),
    # -- two_part: the training half must not crowd out the other half -------
    Q(
        "train_and_lora",
        "two_part",
        "should i train a model for this application, and what is LoRA "
        "anyway?",
        (("low-rank", "low rank", "adapter", "rank"),),
    ),
    Q(
        "epoch_and_should",
        "two_part",
        "what is an epoch, and should i train a model for this application?",
        (("pass", "iterat", "cycle", "sweep", "once through", "one complete"),),
    ),
    # -- offtopic: not about this product at all -----------------------------
    # Two live replies refused "what is the capital of France" because "my
    # tools don't cover general knowledge". A harness that cannot say Paris
    # has confused having tools with only being allowed to use them.
    Q(
        "capital_of_france",
        "offtopic",
        "What is the capital of France?",
        (("paris",),),
    ),
    Q(
        "who_wrote_hamlet",
        "offtopic",
        "Who wrote Hamlet?",
        (("shakespear",),),
    ),
    # -- training: made of the fact ledger, walked by the engine -------------
    # Max's four phrasings, verbatim. THE REGRESSION ROWS.
    Q(
        "should_i_train",
        "training",
        "should i train a model for this application that i am working "
        "inside off",
        (),
    ),
    Q(
        "is_it_worth",
        "training",
        "is it worth training a model for this application",
        (),
    ),
    Q(
        "need_finetune",
        "training",
        "do I need to fine-tune at all?",
        (),
    ),
    Q(
        "would_training_help",
        "training",
        "would training help here?",
        (),
    ),
)

#: THE OLD DETECTOR, kept under its real name and not used as the headline.
#:
#: Every string here is a phrasing the engine used at the moment somebody wrote
#: this list down. That is exactly the problem: `constant_answer` changed what
#: the model is handed, the model changed what it recites, and this list went on
#: reporting the old shape. It fires on 7 of 96 non-training turns where the
#: real rate is 18 of 96. It stays so that a re-score prints both columns and
#: the size of that gap is visible in the output rather than in a commit
#: message.
#:
#: `gate ledger` IS DELIBERATELY ABSENT and its absence was measured. It is in
#: `run_diagnosis`'s own description ("returns the verdict, the gate ledger and
#: the path"), so a reply that answers "what can you do?" by listing the tools
#: says it - correctly, as an account of a tool, which is the answer.
GATE_WORDS = (
    "blocked__", "define_success", "not_reached", "g0_eval", "g1_baseline",
    "g2_prompt", "g3_retrieval", "g4_cheaper", "gates 0 of", "gates 1 of",
    "gates 2 of", "gates 3 of", "gates 4 of", "gates 5 of", "define success",
    "five gates", "5 gates",
)

#: What "the engine's verdict reached the user" means on a training turn. The
#: model calling the engine, the harness putting the card beside the reply, or
#: the verdict said in the prose. Any one of the three is the user seeing it.
VERDICT_WORDS = (
    "blocked", "define success", "do not train", "don't train", "not yet",
    "premature", "no eval", "eval set", "baseline", "cannot recommend",
    "can't recommend", "before recommending", "not recommend",
)

#: Generic English function words. THIS IS NOT A VOCABULARY ABOUT THE DEFECT
#: and the distinction is the whole point of the rewrite: nothing here mentions
#: gates, training, evaluation or any wording the engine has ever used. It is
#: the same list you would strip before comparing any two English sentences,
#: and it does not go stale when the engine's sentence changes.
_STOP = frozenset(
    """a an the and or but if then so than that this these those there here
    is are was were be been being am do does did doing done have has had
    having will would shall should can could may might must of in on at to
    for from with without into onto by as it its it's you your yours i me my
    mine we our ours they them their he she his her not no nor too very just
    only also about after before over under again further once all any both
    each few more most other some such own same what which who whom when
    where why how""".split()
)


def _keys(text: str) -> list[str]:
    """A sentence as a sequence of comparable content keys.

    Five-character prefixes rather than stems, because a prefix is arithmetic
    and a stemmer is a second vocabulary to keep in step with English.
    `defined`, `define` and `defining` all become `defin`; `inputs` and `input`
    both become `input`. Numbers survive whole, which matters: `20` is the most
    distinctive token in the engine's current sentence and a four-character
    truncation would still be `20`.
    """
    out: list[str] = []
    for word in re.findall(r"[a-z0-9']+", text.lower()):
        word = word.strip("'")
        if not word or word in _STOP:
            continue
        if word.isalpha() and len(word) < 3:
            continue
        out.append(word[:5])
    return out


def _longest_run(needle: list[str], hay: list[str], gap: int = 3) -> int:
    """Longest run of `needle` reproduced IN ORDER inside `hay`.

    Order is what separates a recital from a coincidence. A reply that happens
    to use `output` and `input` somewhere is not reciting anything; a reply
    carrying `20 example inputs ... the corresponding correct outputs`
    reproduces a run of the engine's sentence, in the engine's order.

    `gap` is how many of the reply's own content words may sit between two
    consecutive keys of the run, and it is 3 rather than 0 BECAUSE A STRICT
    ADJACENCY TEST WAS TRIED FIRST AND CAUGHT LESS THAN READING DID. It missed
    this live reply to *"can you actually build things?"* -

        "Please provide 20 example inputs and the corresponding correct
        outputs you expect for your task."

    - which is the engine's *"Write 20 inputs and the output you wanted"* with
    two words dropped into it; and this one, to *"what are the risks of
    fine-tuning on a small dataset?"* -

        "1. Specify at least 20 example inputs. 2. Indicate the desired output
        for each input."

    - where the three tokens between `inputs` and `output` include the list
    marker `2`. Both are recitals by any reading and a strict run scored them
    1 and 2. The engine's ORDER still has to hold; what is relaxed is only how
    tightly.
    """
    if not needle or not hay:
        return 0
    positions: dict[str, list[int]] = {}
    for index, key in enumerate(hay):
        positions.setdefault(key, []).append(index)
    best = 0
    for start in range(len(needle)):
        for begin in positions.get(needle[start], ()):
            length, at, step = 1, begin, start + 1
            while step < len(needle):
                onward = [
                    place
                    for place in positions.get(needle[step], ())
                    if at < place <= at + 1 + gap
                ]
                if not onward:
                    break
                at, length, step = onward[0], length + 1, step + 1
            best = max(best, length)
    return best


#: A run of this many of the engine's content keys, in the engine's order, is a
#: recital. CALIBRATED BY READING and the reading is in `recites_the_engine`.
RUN = 3
#: ...or this share of the engine sentence's distinct content keys, in any
#: order. The second arm catches a reordered recital; the first catches a
#: partial one.
#:
#: 0.55 RATHER THAN 0.50 IS THE ONE PLACE THIS FILE TRADES RECALL FOR
#: PRECISION, and it was decided by reading rather than by taste. At 0.50 the
#: detector picks up two more real recitals and two replies that are not:
#: *"An epoch in machine learning refers to one complete pass through the
#: entire training dataset... whether you should train depends on several
#: factors"* answers both halves of its question and shares `defin`, `succe`
#: and `good` with the outcome id by coincidence. A ruler that cries wolf on a
#: good answer is the failure this rewrite exists to end, in the other
#: direction, so the tie goes to precision and the two misses are named in
#: `recites_the_engine`.
COVER = 0.55


def recites_the_engine(prose: str, sentences: list[str]) -> dict | None:
    """Did this reply give back the engine's own sentence instead of an answer?

    ## Why this is a lookup and the thing it replaces was a vocabulary

    `sentences` is what the ENGINE said on this turn - recorded by `run` from
    the walk the harness performed, through `conductor.verdict_sentence`, which
    is the same function the verdict card and the withheld closing use. It is
    not written down here and it is not written down anywhere: change the
    engine's `say` and this function compares against the new one on the next
    run, with nothing to edit. That is the property `GATE_WORDS` did not have
    and could not have.

    ## The two arms, and why one of them is not enough

    * A RUN of `RUN` content keys in the engine's own order. Contiguity is the
      evidence: `input outpu wante` is the tail of the engine's sentence
      reproduced, and no answer about LoRA produces it by accident.
    * COVERAGE of `COVER` of the sentence's distinct keys in any order, which
      catches a recital that has been reordered or bulleted - which is exactly
      what the live misses do: *"1. Definition of Success... 2. Twenty example
      inputs..."* is the engine's sentence turned into a list.

    Either arm fires. A verbatim outcome id or verdict token fires on its own
    through the run arm, because an identifier tokenises into a run of keys.

    ## What it was calibrated against, and what it still misses

    The thresholds are not derived from anything. They were chosen by running
    the bank on this tree at 3966702, dumping every non-training reply that
    mentioned defining success, an eval set, twenty inputs, a verdict or a
    diagnosis - 72 of the 125 - and reading all of them.

        a reader, going through every reply        15 of 125
        THIS DETECTOR                              13 of 125, 13 of them right
        `GATE_WORDS`, the list this replaced        7 of 125,  6 of them right

    So this catches 13 of the 15 a reader finds and has fired on nothing a
    reader would not; the old list caught 6 of 15, which is the 60% shortfall
    the module docstring opens with, arrived at independently.

    **THE TWO IT MISSES ARE NAMED HERE RATHER THAN ROUNDED OFF.** Both are the
    define-good half of the engine's sentence without the twenty-inputs half:

        "The diagnosis phase (step G0) requires clear definitions: 1. Define
        Success: What exactly do you consider 'good' performance?"

        "The diagnosis phase hasn't run yet because we haven't provided enough
        information to define what success looks like."

    They sit at 0.50 coverage of the outcome id against a 0.55 threshold, and
    the two replies that come with them at 0.50 are good answers. See `COVER`.

    A reply is never scored against a sentence it could not have seen: the
    engine's sentences come off THIS turn's record.

    Returns the evidence rather than a bare bool - which sentence, which arm,
    how much - because a detector that cannot show its work is the previous
    detector with different numbers.
    """
    body = _keys(prose)
    if not body:
        return None
    best: tuple | None = None
    for sentence in sentences:
        needle = _keys(sentence)
        distinct = set(needle)
        # A needle shorter than this cannot support the coverage arm: two keys
        # out of three is a coincidence, not a recital. The run arm still
        # applies, and a run is contiguity rather than a ratio.
        if len(distinct) < 4:
            continue
        run = _longest_run(needle, body)
        cover = len(distinct & set(body)) / len(distinct)
        found = {
            "sentence": sentence,
            "run": run,
            "cover": round(cover, 2),
            "arm": "run" if run >= RUN else ("cover" if cover >= COVER else None),
        }
        # A FIRING CANDIDATE BEATS A STRONGER-LOOKING SILENT ONE, and getting
        # that backwards cost a real catch: the long sentence scored a longer
        # run than the outcome id did while firing on neither arm, so it won
        # the comparison and the id's 0.75 coverage was thrown away. Rank on
        # whether it fired first, and on how hard only among those that did.
        rank = (found["arm"] is not None, found["run"], found["cover"])
        if best is None or rank > best[0]:
            best = (rank, found)
    if best is None or best[1]["arm"] is None:
        return None
    return best[1]


def _matches(prose: str, needs: Needs) -> bool:
    body = prose.lower()
    return all(any(word in body for word in group) for group in needs)


def grade(row: dict) -> dict:
    """One reply, three readings. Mechanical, so a re-run is comparable."""
    prose = row.get("prose") or ""
    body = prose.lower()
    needs = {question.name: question.needs for question in BANK}[row["conversation"]]
    row["answered"] = bool(prose.strip()) and _matches(prose, needs)
    row["gate_words"] = any(word in body for word in GATE_WORDS)
    # Old files called it `gate_ledger`; keep the key so a re-score of one does
    # not silently report zeroes for a column that was never computed.
    row["gate_ledger"] = row["gate_words"]
    row["verdict_reached"] = (
        "run_diagnosis" in (row.get("tools") or [])
        or bool(row.get("verdicts"))
        or any(word in body for word in VERDICT_WORDS)
    )
    # THE REGRESSION ROW NEEDS MORE THAN ONE NUMBER, because `verdict_reached`
    # is mostly counting the model CALLING the engine and a change that left
    # the call in place while emptying the reply would sail through it.
    #
    # THESE TWO ARE FACTS OFF THE EVENT SPINE AND NOT A SECOND WORD LIST. That
    # is deliberate: a "did the verdict reach the user" detector built out of
    # phrases would be `GATE_WORDS` again, one column over. The verdict card is
    # written only when the reply itself settled the training decision, and an
    # empty reply is an empty reply. What the reply SAID is `recital`, which on
    # a training turn is the engine's own content arriving where it belongs.
    row["verdict_card"] = bool(row.get("verdicts"))
    # THE ENDING AND NOT THE LENGTH. On an `empty_reply` the harness writes the
    # closing sentence itself and that sentence is a `chat.delta`, so the prose
    # is two hundred characters long and the model said none of them. Reading
    # this off `len(prose)` reported zero empty replies on a run that had one.
    row["empty"] = row.get("ending") == "empty_reply" or not prose.strip()
    evidence = recites_the_engine(prose, row.get("engine_said") or [])
    row["recital"] = bool(evidence)
    row["recital_evidence"] = evidence
    if row["kind"] == "training":
        # The training rows are graded on the engine being reached at all -
        # that is what the question asks for and what may never be traded away.
        row["answered"] = row["verdict_reached"]
    elif row["kind"] == "two_part":
        # BOTH halves. The whole point of the kind is that the training half
        # eats the other one, so a reply that only reached the engine has not
        # answered the question that was asked.
        row["answered"] = row["answered"] and row["verdict_reached"]
    return row


def _said(payload: dict, conductor) -> list[str]:
    """The three strings one walk of the engine puts into the world.

    The rendered sentence, the outcome id, and the engine's `say` on its own -
    because a reply can recite any one of them without the other two. The id
    turns up as prose (*"blocked ... 1. Definition of Success"*) and the `say`
    turns up rearranged into a numbered list, and a needle that is only ever
    the whole concatenation sees neither at the coverage threshold.
    """
    return [
        item
        for item in (
            conductor.verdict_sentence(payload),
            payload.get("outcome"),
            payload.get("say"),
        )
        if item
    ]


def _engine_sentences(rows: list[dict], constant: list[str], conductor) -> list[str]:
    """Everything the ENGINE said on this turn, plus what it says to everybody.

    The constant is always in the list because it is what the engine reaches
    for a thread it knows nothing about - it is available to be recited on a
    turn where the model never called a tool at all, through the standing
    brief.
    """
    said = list(constant)
    for item in rows:
        if item["kind"] != "tool.result":
            continue
        result = item["payload"].get("result")
        if isinstance(result, dict) and result.get("decided_by") == "app/diagnosis.py":
            for sentence in _said(result, conductor):
                if sentence not in said:
                    said.append(sentence)
    return said


def run(
    passes: int,
    base_url: str,
    model: str,
    shard: tuple[int, int],
    only: str | None = None,
) -> list[dict]:
    from app import conductor, events
    from app.providers import store as provider_store

    row = provider_store.create("Live", base_url, model, "ollama")
    caps = conductor.build("ollama", base_url, model).capabilities(secret=None)
    ready = provider_store.record_capabilities(row["id"], caps)
    provider_store.set_active(ready["id"])
    print(f"connected: {model}, tool_calling={ready['tool_calling']}", flush=True)

    # The engine's answer to a thread it knows nothing about, computed once
    # through the same door every other walk uses. This is the lookup the
    # honest detector compares against; nothing about it is written down.
    blank = conductor._standing_diagnosis(None)
    constant = _said(blank or {}, conductor)
    print(f"the engine's constant: {constant[0]}", flush=True)

    index, total = shard
    bank = [question for question in BANK if only is None or question.kind == only]
    turns: list[dict] = []
    for sweep in range(passes):
        for position, question in enumerate(bank):
            if (sweep * len(bank) + position) % total != index:
                continue
            thread_id = events.create_thread(question.name)["id"]
            if question.prior:
                # A REAL TURN, not a fabricated assistant message. The thing
                # under test is whether a number the user said one turn ago is
                # still reachable, and a hand-written transcript would test the
                # hand-writing.
                events.add_message(thread_id, "user", question.prior)
                list(conductor.run_turn(thread_id))
            events.add_message(thread_id, "user", question.question)
            started = time.monotonic()
            rows = list(conductor.run_turn(thread_id))
            prose = "".join(
                item["payload"].get("text", "")
                for item in rows
                if item["kind"] == "chat.delta"
            )
            turn = grade(
                {
                    "conversation": question.name,
                    "kind": question.kind,
                    "pass": sweep,
                    "question": question.question,
                    "prior": question.prior,
                    "ending": rows[-1]["payload"].get("ending"),
                    "seconds": round(time.monotonic() - started, 1),
                    "chars": len(prose),
                    "tools": [
                        item["payload"].get("name")
                        for item in rows
                        if item["kind"] == "tool.call"
                    ],
                    # THE ARGUMENTS, NOT ONLY THE NAMES, and the reason is the
                    # `user_number` finding: five of five replies to "I have
                    # 340 labelled examples" called `profile_dataset`, and what
                    # made that a defect rather than diligence was the PATH it
                    # was called with - `340_labelled_examples`, invented out
                    # of the question. A list of tool names cannot show that.
                    "tool_args": [
                        {
                            "name": item["payload"].get("name"),
                            "arguments": item["payload"].get("arguments"),
                        }
                        for item in rows
                        if item["kind"] == "tool.call"
                    ],
                    "prose": prose,
                    "engine_said": _engine_sentences(rows, constant, conductor),
                    "notices": [
                        item["payload"]
                        for item in rows
                        if item["kind"] == "conductor.notice"
                    ],
                    "verdicts": [
                        item["payload"]
                        for item in rows
                        if item["kind"] == conductor.VERDICT_KIND
                    ],
                }
            )
            turns.append(turn)
            print(
                f"  p{sweep} {question.name:22}"
                f" {'ANSWERED' if turn['answered'] else '  ------'}"
                f" {'RECITAL' if turn['recital'] else '       '}"
                f" {'GW' if turn['gate_words'] else '  '}"
                f" {turn['ending']:<12} {turn['seconds']:>5}s {turn['chars']:>5}c"
                f" tools={turn['tools']}",
                flush=True,
            )
    return turns


def fisher(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher's exact on a 2x2 table. Exact, and no dependency.

    Rows are the two arms, columns are the two outcomes. The two-sided p is the
    sum of every table with the same margins whose probability is no greater
    than the observed one, which is the convention `scipy.stats.fisher_exact`
    uses and what this was checked against before it was committed.
    """
    n = a + b + c + d
    row1, row2 = a + b, c + d
    col1 = a + c
    total = math.comb(n, col1)

    def probability(k: int) -> float:
        return math.comb(row1, k) * math.comb(row2, col1 - k) / total

    observed = probability(a)
    low = max(0, col1 - row2)
    high = min(row1, col1)
    return min(
        1.0,
        sum(
            probability(k)
            for k in range(low, high + 1)
            if probability(k) <= observed * (1 + 1e-9)
        ),
    )


def _column(turns: list[dict], key: str, kind: str | None = None) -> tuple[int, int]:
    rows = [row for row in turns if kind is None or row["kind"] == kind]
    return sum(1 for row in rows if row.get(key)), len(rows)


def compare(before: list[dict], after: list[dict]) -> None:
    """Before and after on the same bank, with Fisher's exact on each column.

    NOT WITH A HEADLINE. Both columns are printed with their p, and a p that is
    not small is printed as loudly as one that is - the last agent refused to
    call its own improvement significant and was right to.
    """
    print("\n  before / after, Fisher's exact two-sided")
    print(f"    {'column':<28}{'before':>12}{'after':>12}{'p':>10}")
    for label, key, kind in (
        ("answered, all", "answered", None),
        ("answered, non-training", "answered", "NON"),
        ("recital, non-training", "recital", "NON"),
        ("gate_words, non-training", "gate_words", "NON"),
        ("answered, THE FOUR TRAINING", "answered", "training"),
        ("engine content in reply, TRAINING", "recital", "training"),
        ("verdict card, TRAINING", "verdict_card", "training"),
        ("empty reply, TRAINING", "empty", "training"),
        ("empty reply, all", "empty", None),
        ("recital, synthetic_data", "recital", "synthetic_data"),
        ("answered, synthetic_data", "answered", "synthetic_data"),
        ("answered, user_number", "answered", "user_number"),
    ):
        def pick(turns: list[dict]) -> list[dict]:
            if kind is None:
                return turns
            if kind == "NON":
                return [row for row in turns if row["kind"] != "training"]
            if kind == "synthetic_data":
                return [row for row in turns if row["conversation"] == kind]
            return [row for row in turns if row["kind"] == kind]

        left, right = pick(before), pick(after)
        if not left or not right:
            continue
        a = sum(1 for row in left if row.get(key))
        c = sum(1 for row in right if row.get(key))
        p = fisher(a, len(left) - a, c, len(right) - c)
        print(
            f"    {label:<28}{a:>5} of {len(left):<4}{c:>5} of {len(right):<4}"
            f"{p:>10.3f}"
        )


def report(turns: list[dict], read: bool) -> None:
    kinds: dict[str, list[dict]] = {}
    for row in turns:
        kinds.setdefault(row["kind"], []).append(row)

    print(f"\n{len(turns)} turns")
    print(f"  {'kind':<14}{'answered':>12}{'recital':>14}{'gate_words':>14}")
    order = ("definitional", "risk", "offtopic", "capability", "machine", "data",
             "user_number", "two_part", "training")
    for kind in order:
        rows = kinds.get(kind) or []
        if not rows:
            continue
        answered = sum(1 for row in rows if row["answered"])
        recital = sum(1 for row in rows if row.get("recital"))
        gated = sum(1 for row in rows if row.get("gate_words"))
        print(
            f"  {kind:<14}{answered:>5} of {len(rows):<4}"
            f"{recital:>9} of {len(rows):<4}"
            f"{gated:>9} of {len(rows):<4}"
        )
    for label, rows in (
        ("NON-TRAINING", [row for row in turns if row["kind"] != "training"]),
        ("ALL", turns),
    ):
        if not rows:
            continue
        answered = sum(1 for row in rows if row["answered"])
        recital = sum(1 for row in rows if row.get("recital"))
        gated = sum(1 for row in rows if row.get("gate_words"))
        print(
            f"  {label:<14}{answered:>5} of {len(rows):<4}"
            f"{recital:>9} of {len(rows):<4}"
            f"{gated:>9} of {len(rows):<4}"
            f"   {100 * answered / len(rows):>3.0f}%"
            f" / {100 * recital / len(rows):>3.0f}%"
            f" / {100 * gated / len(rows):>3.0f}%"
        )

    print("\n  per question")
    for question in BANK:
        rows = [row for row in turns if row["conversation"] == question.name]
        if not rows:
            continue
        answered = sum(1 for row in rows if row["answered"])
        recital = sum(1 for row in rows if row.get("recital"))
        called = sum(1 for row in rows if "run_diagnosis" in (row["tools"] or []))
        print(
            f"    {question.name:<22} {question.kind:<13} answered"
            f" {answered}/{len(rows)}  recital {recital}/{len(rows)}"
            f"  run_diagnosis {called}/{len(rows)}"
        )

    # THE FOUR TRAINING PHRASINGS, ON THEIR OWN, IN FULL. They are the thing
    # that has been traded away twice, and one number is not enough to see it
    # go: the tool call, the verdict actually in front of the user, and the
    # silence, all three.
    training = [row for row in turns if row["kind"] == "training"]
    if training:
        called = sum(
            1 for row in training if "run_diagnosis" in (row["tools"] or [])
        )
        card = sum(1 for row in training if row.get("verdict_card"))
        engine = sum(1 for row in training if row.get("recital"))
        empty = sum(1 for row in training if row.get("empty"))
        print(
            f"\n  THE FOUR TRAINING PHRASINGS, {len(training)} turns:"
            f" run_diagnosis {called}, verdict card {card},"
            f" engine content in the reply {engine}, empty replies {empty}"
        )

    print("\n  endings")
    endings: dict[str, int] = {}
    for row in turns:
        endings[row["ending"]] = endings.get(row["ending"], 0) + 1
    for ending, count in sorted(endings.items(), key=lambda item: -item[1]):
        print(f"    {ending:<24} {count}")

    # THE DETECTOR SHOWS ITS WORK. Every row it fired on and every row it came
    # close on, so the thresholds can be argued with per row rather than in the
    # abstract - which is the failure mode of the list this replaced.
    print("\n  what the recital detector saw, non-training")
    for row in turns:
        if row["kind"] == "training":
            continue
        found = row.get("recital_evidence")
        if not found:
            continue
        print(
            f"    {row['conversation']:<22} p{row['pass']} arm={found['arm']:<6}"
            f" run={found['run']} cover={found['cover']}"
        )

    if read:
        print("\nREAD THESE.")
        for row in turns:
            print(
                f"\n  [{row['kind']}/{row['conversation']} p{row['pass']}] "
                f"answered={row['answered']} recital={row['recital']} "
                f"gate_words={row['gate_words']} tools={row['tools']}"
            )
            if row.get("prior"):
                print(f"    (prior turn) {row['prior']}")
            print(f"    Q: {row['question']}")
            print(f"    A: {row['prose'][:1200]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("second", type=Path, nargs="?", default=None)
    parser.add_argument("-n", "--passes", type=int, default=5)
    #: MAX'S CALL, 2026-09-08. See the note in
    #: `generate_the_preference_pairs.py` for the whole of it: the swap is his,
    #: the bench does not discriminate, the bugs are accepted in advance, and
    #: every result already in `runs/` remains a granite result.
    parser.add_argument("--model", default="minicpm5-hermes:latest")
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--shard", default="0/1", help="i/n, for parallel runs")
    parser.add_argument("--kind", default=None, help="run one kind only")
    parser.add_argument("--score", action="store_true", help="re-score a file")
    parser.add_argument(
        "--compare", action="store_true", help="two files, before and after"
    )
    parser.add_argument("--read", action="store_true")
    args = parser.parse_args()

    if args.compare:
        before = [grade(row) for row in json.loads(args.out.read_text("utf-8"))]
        after = [grade(row) for row in json.loads(args.second.read_text("utf-8"))]
        compare(before, after)
        return 0

    if args.score:
        rows = json.loads(args.out.read_text(encoding="utf-8"))
        report([grade(row) for row in rows], args.read)
        return 0

    _SANDBOX = _Held()
    support.sandbox(_SANDBOX)
    index, total = (int(part) for part in args.shard.split("/"))
    turns = run(
        max(1, args.passes), args.base_url, args.model, (index, total), args.kind
    )
    args.out.write_text(json.dumps(turns, indent=2), encoding="utf-8")
    report(turns, args.read)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
