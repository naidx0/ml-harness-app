"""The classical branch, which is a whole modality with nothing at the end of it.

`docs/VISION.md` names the hole and this module is stage 8's share of it:
*"'Do not train anything' is honest, and today it is a dead end. We tell somebody
their real problem is [...] and then we hand them nothing."*

Stage 8 declares twelve terminal outcomes and until this file none of them led
anywhere. Six of those twelve are a person with a spreadsheet being told, in the
engine's own words, to go and fit a tree:

    NO_DEEP__GRADIENT_BOOSTED_TREES   the default answer for tabular prediction
    NO_DEEP__TABPFN                   under 10,000 rows
    NO_DEEP__TUNE_THE_TREES_FIRST     "an untuned tree is not a baseline"
    NO_DEEP__FIND_THE_MISSING_FEATURE "re-fit the tuned tree"
    NO_DEEP__HYBRID_EMBED_PLUS_GBDT   "concatenate to the numeric features, fit a GBDT"
    NO_DEEP__CLASSICAL_FORECAST       "a GBDT on lag features as the baselines"

Every one of those sentences ends in *fit a tree and score it*, and the product
could not fit a tree. `app/tools/propose.py` says so out loud in the reason it
gives for all six - *"fitting a cheaper model [...] which this harness has no
tool to fit"* - and this module is that sentence stopping being true for the
first of them.

## Why sklearn and not the three libraries the engine names

The engine names LightGBM, XGBoost and CatBoost, and this file does not use any
of them, because **none of them is installed and installing one is a new
dependency**. That is not a footnote: it is reported in every reply, it is
MEASURED rather than remembered - `available()` asks `importlib.util.find_spec`
at call time - and the names it checks are read off
`S8_TABULAR_STANDARD.method.libs` in `docs/diagnosis_engine.yaml` rather than
typed here, so the day the engine names a fourth library this file starts
reporting on it without being edited.

`sklearn.ensemble.HistGradientBoostingClassifier` is a real gradient booster
with histogram binning, native NaN handling and native categorical support - the
same family as LightGBM and, on many tabular problems, close to it. It is
usually not the best of the four. Saying that is the point.

**AND SKLEARN IS NOT A DEPENDENCY OF THIS REPOSITORY EITHER.** `pyproject.toml`
declares fastapi, markdown, pyyaml and uvicorn, and nothing else. So every import of sklearn and numpy in this file is INSIDE the handler,
and a machine without them gets a refusal that names what is missing rather than
an `ImportError` at `import app.tools`. A module-level import here would have made
sklearn a runtime dependency of the whole product by accident, which is exactly
the "dependency as a side effect of a feature step" `AGENTS.md` forbids.

## What makes this an instrument rather than a wrapper

Four things, and each one is a place where the obvious version of this tool
would have produced a number that flatters.

**THE SCORE IS NEVER ALONE.** A tree that scores 73% on a set that is 70% one
class has done almost nothing, and "73%" on its own reads like a result. So
every reply carries, on THE SAME held-out rows: what the tree scored, what
answering the most common training label would have scored, the difference
between them in points, `evals.mcnemar` over the rows where the two disagreed,
and `evals.resolution_for` - the Wilson interval and what a set this size can
and cannot separate. All four come from `app/tools/evals.py` rather than from a
second implementation here, because a recall, an eval score and a tree's
accuracy stating their resolution three different ways is the drift this
repository has been bitten by more than once.

**THE BASELINE DOES NOT PEEK AND SAYS WHEN SOMETHING ELSE WOULD HAVE.** The
trivial baseline is the most common label among the rows the tree was FITTED on,
applied to the held-out rows - a real predictor, fitted where the tree was
fitted, scored where the tree was scored. The most common label in the held-out
rows themselves is a different and larger number, it is the best any constant
could do on those rows, and it is reported under
`best_constant_on_the_holdout` with `peeks: true` on it rather than quietly used
as the comparison.

**HOLD-OUT, AND THE SPLIT IS A HASH OF THE ROW.** A tree scored on rows it was
fitted on is meaningless and will look excellent, so nothing here ever scores a
fitted row. Which rows are held out is decided by
`signature_of_text("fit_a_tree_model/v1|<seed>|<row signature>")` and never by
shuffling, exactly as `carve_eval_set` decides its own split and through the
same two functions in `app/dataquality.py`. Three consequences: the split is the
same on any machine and in any process; it does not depend on the order the file
was read in; and **two identical rows hash the same and cannot land on opposite
sides**, so the commonest leak of all is impossible by construction rather than
by inspection. It is counted afterwards anyway, and reported, because a property
nobody verified is a claim.

A caller who already has a split - who ran `carve_eval_set`, say - passes
`holdout_path` and the split is theirs. Then it is CHECKED and not trusted:
`data.check_split_leakage` runs over the two files and a single shared row
refuses the fit, because a score measured across a leak is worse than no score.

**IT REFUSES WHERE FITTING WOULD BE THEATRE.** Six checks, all of them before
anything is fitted, each named in the reply whether it passed or not:

* a target column that is not there, is empty, or holds one value;
* a target with a different value in every row - that is an identifier, not a
  label - and a numeric target with more distinct values than
  `MAX_CLASSES`, which is a regression problem and is refused for a stated
  reason rather than silently scored (see below);
* fewer rows than a fit and a hold-out both need, read from
  `dataquality.MIN_ROWS_FOR_TRAINING` and from G0's own floor in the engine;
* no usable feature columns, or every one of them constant;
* **a leak from the target into a feature**, which is the classic tabular defect
  and is the reason this list is worth having at all. Two checks, because they
  catch different leaks - see `LEAK CHECKS` below;
* a hold-out that came out all one class, where the trivial baseline scores 100%
  and no comparison means anything.

Every refusal comes back in the SAME SHAPE as a success with the score holding
`None`, because a caller that special-cases a refusal is a caller that can
forget to.

## LEAK CHECKS, and what they do not catch

**A - the relabelling.** A feature column whose values each map to exactly one
target value, with no more distinct values than the target has classes. That is
the label under another name: `is_churned` beside `churn`, `label_encoded`
beside `label`, a flag somebody derived from the answer. Exact, one pass, no
statistics, and it cannot fire on an identifier column because an identifier has
far more distinct values than there are classes.

**B - the single-column oracle.** One feature, mapped value-to-majority-label on
the training rows and applied to the held-out rows, gets every held-out row
right. Either that column is the target under another name, or the problem is a
lookup table and not a model. Both are worth stopping to say, and the refusal
says both.

**WHAT NEITHER CATCHES, said here because a check whose limits are unstated
reads as a guarantee.** A leak spread across two columns that only works
together. A leak that holds for part of the data and not the rest. And the
commonest real one: a TEMPORAL leak - a column recorded after the label was
known, which is a fact about when your data was collected and is not visible in
the values at all. No program can see that one from the file. The reply says so.

## What it does not do, which is most of what the engine asked for

The engine's word is *tuning: "50-trial random or optuna search"*, and
G2_PROMPT_EXHAUSTED's `classical_deep` row requires `hparam_search_trials >= 50`
before a neural net is even arguable. **This tool runs ONE fit at scikit-learn's
defaults.** That is one trial, not fifty, and `not_tried` says so with the 50
read off the gate rather than typed - so a person who came here from
NO_DEEP__TUNE_THE_TREES_FIRST is told, by the tool that just fitted their tree,
that the tool did not do the thing that outcome asked for.

Also not done, and also named: no feature engineering (which is
NO_DEEP__FIND_THE_MISSING_FEATURE's whole answer and is a join or an aggregate
nobody here can guess); no TabPFN (`tabpfn` is not installed either, and
S8_TABULAR_SMALL is the outcome that wants it); no cross-validation - one split,
one fit, and the resolution block says what one split of that size can resolve;
no probability calibration; no text-column embedding, which is
NO_DEEP__HYBRID_EMBED_PLUS_GBDT's answer and needs an embedding model this
harness does not ship.

## `measures=()`, DELIBERATELY, AND THE FIVE GATES ARE UNTOUCHED

The tempting stamp is `baseline_score` with `trivial_baseline_score` beside it.
Both are declared measurable, `measure_baseline` and `run_eval` already stamp
them, and G1_BASELINE_MEASURED's own `what_counts_as_the_baseline` says that for
`classical_deep` the baseline IS *"a gradient-boosted tree, and TabPFN where the
size allows, both fitted and scored"*. It reads like this tool's job.

It is not, and the reason is a defect and not a scruple. Those facts are
**thread-scoped**. A thread is one conversation about one problem, and the eval
set the diagnosis spine runs on is the one G0 counted. If this tool stamped
`baseline_score` MEASURED, then a person whose thread is about fine-tuning a
language model, who fitted a tree on an unrelated spreadsheet in the same
conversation, would have G1 opened by that tree's accuracy - a number measured
by a different instrument on different rows about a different question. The
five-gate promise is that no training recommendation is reachable without a
measured baseline ON THE EVAL SET; a tree's accuracy on a table is not that
number and must not be able to become it.

So `measures=()`, no `bounds=` (wall 6 refuses a bound on a tool that measures
nothing), and `writes=()` - this tool records nothing at all. `decides_nothing`
in every reply says the same thing to the model, and
`tests/test_a_tree_is_scored_against_the_trivial_answer.py` asserts it against
the live gate ledger rather than believing this paragraph.

A row count is in the same position and is not stamped either: this tool reads
at most `max_rows` rows, and `ACTION__COUNT_THE_ROWS` is explicit that what it
needs is a tool that measures `tabular_rows`, which is a different contract from
this one. The reply says the count is this program's arithmetic over what it
read.
"""

from __future__ import annotations

import importlib.util
import math
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

from app import dataquality, diagnosis
from app.tools import data, evals
from app.tools.context import quarantine
from app.tools.registry import tool


# ---------------------------------------------------------------------------
# The numbers, and which of them are choices.


#: The draw's name. It is in the hash, so this tool's split is its own draw
#: rather than a copy of `carve_eval_set`'s - two operations that happened to
#: agree on which rows to hold out would be an accident nobody could reproduce
#: after either of them changed. Same primitive, different rule string; see
#: `datawork.SELECTION_RULE` for the other one.
SPLIT_RULE = "fit_a_tree_model/v1"

#: How much of the file is held out when the caller does not say. A STATED
#: CHOICE and not a measured optimum, in the same sense
#: `build_retrieval_index` declares `passage_chars` as one. A quarter is the
#: conventional split; nothing here measured that it is the right one, and the
#: floors below are what actually decide whether a split is usable.
DEFAULT_HOLDOUT = 0.25

#: The band the split may be asked for. Below the low bound the hold-out cannot
#: clear G0's floor on any file this tool would accept; above the high bound
#: there is not enough left to fit on.
MIN_HOLDOUT = 0.05
MAX_HOLDOUT = 0.5

#: The most distinct target values this tool will treat as classes. A CHOICE,
#: made here. The number is the engine's own largest class band -
#: `S8_TEXT_CLASSIFICATION_FEW_LABELS` is `classes_n <= 50` - which is where it
#: was taken from; it is not a measurement of anything and nothing in the
#: arithmetic below singles it out. Past it, a numeric target is a regression
#: problem and a non-numeric one is closer to an identifier than to a label.
MAX_CLASSES = 50

#: sklearn's histogram booster bins at most 255 values, and one code is kept for
#: "a category the fit never saw". A text column with more distinct values than
#: this is closer to an identifier than to a category, so it is DROPPED and
#: named rather than binned into noise.
MAX_CATEGORIES = 254

#: The reply's cap on how many of anything it will list back - dropped columns,
#: class labels, leaking columns. The counts are always complete; the lists are
#: what a person can read.
LIST_CAP = 20

#: Read rather than truncate. A prefix of a sorted file is not a sample, which
#: is `carve_eval_set`'s rule and `measure_retriever_recall`'s rule, so a file
#: longer than the cap refuses instead of scoring its first N rows.
DEFAULT_ROW_LIMIT = data.DEFAULT_ROW_LIMIT
MAX_ROW_LIMIT = 5_000_000

#: THE MOST CELLS THIS TOOL WILL BUILD A MATRIX OUT OF. `max_rows` bounds rows
#: and `dataquality.COLUMN_CAP` bounds columns, and neither bounds their
#: PRODUCT: 200,000 rows of 500 columns is a hundred million float64 cells, or
#: eight hundred megabytes, allocated in one call before anything is fitted. A
#: refusal that names both doors is better than an out-of-memory error that
#: names neither. Twenty million cells is 160 MB, which is a choice and is
#: stated as one - it is also the bound that keeps the two leak checks, both of
#: which are one pass per column, to a few seconds.
MAX_CELLS = 20_000_000

#: How many trials this tool runs. It is one. Named as a constant so the
#: `not_tried` block subtracts it from the gate's own number rather than
#: printing a 49 nobody can trace.
TRIALS_RUN = 1

#: The estimator, by its import path, so the reply names what actually ran.
ESTIMATOR = "sklearn.ensemble.HistGradientBoostingClassifier"

#: The libraries whose absence is a fact about this machine. The three the
#: engine names are read off the spec; `tabpfn` is added because
#: `NO_DEEP__TABPFN` is one of the six dead ends this module is about and it has
#: no `method.libs` block to read.
EXTRA_LIBRARIES = ("tabpfn",)

#: What every reply says about what it recorded. There is one of these because
#: a refusal and a success must say the same thing about the ledger.
STAMPS_NOTHING = (
    "Nothing was recorded. This tool declares measures=() and writes=(), so the "
    "score above is in this reply and nowhere else. It is a tree's accuracy on "
    "a table, which is not baseline_score - baseline_score is a number measured "
    "on the eval set this thread's diagnosis runs on, by measure_baseline or "
    "run_eval, and a tree fitted on a spreadsheet must not be able to become it."
)

DECIDES_NOTHING = (
    "This decides nothing and opens nothing. It does not set "
    "hparam_search_trials - one fit is not a search - and it does not set "
    "feature_work_considered or model_swap_tried, which are yours to say "
    "because nobody else was there. The diagnosis is unchanged by having run it."
)


class Refusal(Exception):
    """Something that stops the fit, carrying the reply that says so.

    An exception rather than a returned dict for the reason `datawork.Refusal`
    gives: the checks run in a fixed order across two streaming passes, and a
    returned refusal has to be threaded back out through every loop by hand,
    which is how a check ends up reached on some paths and not others.
    """

    def __init__(self, payload: dict[str, Any]) -> None:
        super().__init__(str(payload.get("summary") or payload.get("error")))
        self.payload = dict(payload)


# ---------------------------------------------------------------------------
# What this machine has, and what the engine asked for. Both read, neither
# remembered.


def installed(name: str) -> bool:
    """Is this importable on this machine, asked now rather than recalled.

    `find_spec` and not a `try: import`, because importing a large library to
    find out whether it is there costs seconds and can raise for reasons that
    have nothing to do with whether it is installed.
    """
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):  # a namespace package with no spec
        return False


#: THE NODE THIS TOOL READS ITS METHOD BLOCK OFF, AND IT IS ML-ONLY BY NAME.
#: `S8_TABULAR_STANDARD` is one ledger's id for one ledger's branch, and this
#: module is the tabular branch: there is nothing about a gradient-boosted tree
#: that generalises to a ledger about agents. So this stays a name, and the
#: three readers below turn "this ledger has no such node" into an honest empty
#: answer rather than a read of whichever file a module default happened to
#: point at. That is Eclipse's contract for an unbound extension point: unbound
#: is empty, and empty is a fact the caller has to state.
#:
#: The declared alternative - `contract.knowledge` in the ledger, mapping an
#: engine-owned capability key to this ledger's node id - is `ledger_format: 4`
#: and is deliberately not done here; see `docs/CAPABILITY_BLOCKS.md` §8.2 and
#: step 3 of its migration path. What this pass owes is that a second domain
#: gets nothing rather than the wrong thing, and that is what these three do.
_THE_TABULAR_NODE = "S8_TABULAR_STANDARD"


def _the_tabular_node(spec: diagnosis.Spec | None = None) -> dict[str, Any] | None:
    """This ledger's tabular method node, or None when it declares none."""
    current = spec or diagnosis.default_spec()
    return current.node_index.get(_THE_TABULAR_NODE)


def libraries_the_engine_names(spec: diagnosis.Spec | None = None) -> list[str]:
    """LightGBM, XGBoost, CatBoost - read off the spec, not typed here.

    `S8_TABULAR_STANDARD.method.libs` is the engine's own answer to "what should
    a person fit". A list in this file would be a second copy of it, and the day
    somebody adds a fourth library to the spec this file would go on reporting
    on three. A spec that will not load is not this tool's news: the caller gets
    an empty list and the reply says the check could not be made.

    THE WALK ITSELF IS `Spec.method_libs` AND IS NO LONGER WRITTEN HERE. This
    file and `app/tools/propose.py` each had their own copy of it - one fixed to
    this node, one parameterised - and they agreed, which is the moment to
    collapse them rather than after they stop. Neither may import the other,
    because the registry imports both, so the one reader lives beside the spec.
    """
    try:
        current = spec or diagnosis.default_spec()
        if _the_tabular_node(current) is None:
            return []
        return list(current.method_libs(_THE_TABULAR_NODE))
    except Exception:  # noqa: BLE001 - a spec we cannot read is a fact, not a crash
        return []


def tuning_the_engine_asks_for(spec: diagnosis.Spec | None = None) -> str:
    """`"50-trial random or optuna search"`, in the engine's own words."""
    try:
        current = spec or diagnosis.default_spec()
        block = current.method_block(_THE_TABULAR_NODE)
        return str(block.get("tuning") or "")
    except Exception:  # noqa: BLE001
        return ""


#: THE FACT, NOT THE GATE ID. `G2_PROMPT_EXHAUSTED` was typed here and it was a
#: proxy for this name: what this function wants is the number of tuning trials
#: the ledger asks for, which is a thing said ABOUT `hparam_search_trials`.
THE_TRIALS_FACT = "hparam_search_trials"
_THE_CLASSICAL_ROW = "classical_deep"


def trials_the_gate_asks_for(spec: diagnosis.Spec | None = None) -> int | None:
    """The 50 in `hparam_search_trials >= 50`, found by the fact the gate reads.

    Off the gate rather than off the node's prose, because the gate is what
    actually decides, and because a number typed here would be the fabrication
    invariant wearing the engine's name the first time somebody edited the gate.

    Found by fact rather than by gate id, so a ledger that puts the trial count
    in a differently-named gate is followed, and a ledger with no such fact
    returns None - which every caller already treats as "the engine states no
    number" rather than as a failure.
    """
    try:
        current = spec or diagnosis.default_spec()
        reading = current.gate_reading(
            THE_TRIALS_FACT, method_class=_THE_CLASSICAL_ROW
        )
        if reading is None or reading.row_key != _THE_CLASSICAL_ROW:
            return None
        requires = str(reading.row.get("requires") or "")
        marker = f"{THE_TRIALS_FACT} >="
        if marker in requires:
            tail = requires.split(marker, 1)[1].strip().split()[0]
            return int(tail)
    except Exception:  # noqa: BLE001
        return None
    return None


def available() -> dict[str, Any]:
    """What is importable here, measured, with what the engine wanted beside it.

    Every field is the answer `find_spec` gave a moment ago. Nothing in here is
    remembered from a previous run and nothing is asserted about a machine this
    is not running on.
    """
    named = libraries_the_engine_names()
    wanted = {lib: installed(lib.lower()) for lib in named}
    wanted.update({lib: installed(lib) for lib in EXTRA_LIBRARIES})
    return {
        "sklearn": installed("sklearn"),
        "numpy": installed("numpy"),
        "engine_named": named,
        "boosters_the_engine_names": wanted,
        "missing": sorted(name for name, there in wanted.items() if not there),
        "how": (
            "importlib.util.find_spec on this machine, at the moment this tool "
            "ran. The names came from S8_TABULAR_STANDARD.method.libs in "
            "docs/diagnosis_engine.yaml plus tabpfn, which NO_DEEP__TABPFN wants."
        ),
    }


def not_tried_block() -> dict[str, Any]:
    """Everything this fit did not do, in the same breath as what it did.

    The retrieval bench names the three levers it cannot pull in every reply it
    produces, refusals included, *"because a person told 'fix your retriever'
    deserves to know which of the four things we can do with them and which they
    must do themselves"*. Same sentence, different bench. Shipping the one thing
    this file owns and omitting the rest would read as though one fit at
    defaults were the whole of the answer stage 8 gives.
    """
    have = available()
    asked = trials_the_gate_asks_for()
    missing = have["missing"]
    rows: list[dict[str, str]] = []

    if missing:
        rows.append(
            {
                "not_tried": ", ".join(missing),
                "why_not": (
                    f"not installed on this machine - {have['how']} - and "
                    "installing one would be a new dependency, which this "
                    "repository does not take on to add a feature. "
                    f"What ran instead is {ESTIMATOR}, a real histogram "
                    "gradient booster in the same family, which is usually not "
                    "the best of them on real tabular data."
                ),
                "who_can": (
                    "you, with a pip install and your own environment. The "
                    "comparison would then be worth making the same way this "
                    "one is - same rows, same split, the trivial answer beside "
                    "both scores."
                ),
            }
        )
    rows.append(
        {
            "not_tried": (
                f"a hyperparameter search - {tuning_the_engine_asks_for()}"
                if tuning_the_engine_asks_for()
                else "a hyperparameter search"
            ),
            "why_not": (
                f"this ran {TRIALS_RUN} fit at scikit-learn's defaults"
                + (
                    f", and G2_PROMPT_EXHAUSTED's classical_deep row asks for "
                    f"hparam_search_trials >= {asked}, which is {asked - TRIALS_RUN} "
                    "more than were run"
                    if isinstance(asked, int)
                    else ""
                )
                + ". NO_DEEP__TUNE_THE_TREES_FIRST is the outcome that asks for "
                "it, and its own sentence is that an untuned tree is not a "
                "baseline - it is a tree nobody tuned."
            ),
            "who_can": (
                "nobody here yet. A search is a different tool with a different "
                "contract: many fits, a held-out set that does not get looked at "
                "once per trial, and a stated stopping rule."
            ),
        }
    )
    rows.append(
        {
            "not_tried": "feature engineering - a join, an aggregate, a ratio, a lag",
            "why_not": (
                "nothing here can guess what your data is missing. That is "
                "NO_DEEP__FIND_THE_MISSING_FEATURE's whole answer and the engine "
                "is explicit that on tabular data it is nearly always where the "
                "signal is."
            ),
            "who_can": "you. Build the two or three obvious ones and re-fit.",
        }
    )
    rows.append(
        {
            "not_tried": "cross-validation",
            "why_not": (
                "one split, one fit. The resolution block says what a hold-out "
                "of this size can and cannot separate, which is the honest "
                "version of the same information and does not pretend to be a "
                "variance estimate."
            ),
            "who_can": "a tool that fits k times, which this is not.",
        }
    )
    rows.append(
        {
            "not_tried": "embedding any free-text column",
            "why_not": (
                "NO_DEEP__HYBRID_EMBED_PLUS_GBDT asks for a sentence encoder and "
                "this harness ships no AI. A text column with more than "
                f"{MAX_CATEGORIES} distinct values is dropped and named rather "
                "than binned into noise."
            ),
            "who_can": "you, with your own embedding model.",
        }
    )
    return {
        "machine": have,
        "levers": rows,
        "and_the_leak_nothing_here_can_see": (
            "A temporal leak - a column recorded after the label was known - is "
            "a fact about when your data was collected and is not in the values "
            "at all. No check below can see it, and it is the commonest real "
            "one. Neither is a leak spread across two columns that only works "
            "when both are present. AND THE THIRD ONE, WHICH THIS SENTENCE DID "
            "NOT USED TO NAME: a leak carried by ONE column with more distinct "
            "values than the checks can tabulate. Check A only fires on a "
            "column with no more distinct values than there are classes, and "
            "check B falls back the moment a held-out value was not seen in "
            "training - so a `band` column derived from a 400-value "
            "`risk_score`, or a category cut out of a continuous number, is "
            "invisible to both. Measured here, sweeping only the leaking "
            "column's width with the classes fixed at two: refused at 2 "
            "distinct values, and at 50, 51, 100 and 200 it was fitted and "
            "scored EVERY held-out row right, at p between 2.7e-23 and 6.9e-18, "
            "with both checks reporting nothing found. The check stops working "
            "exactly where the leak stops being obvious to a person. Check C "
            "catches the one shape of this that can be named exactly - a whole "
            "number that never repeats - and a column that repeats even once is "
            "past it. If a score here comes back at or near 100%, that is the "
            "case to suspect first: nothing in this reply treats a perfect "
            "hold-out score as remarkable, and it almost always is."
        ),
    }


# ---------------------------------------------------------------------------
# Refusals, all in the shape of a success.


def _refuse(error: str, summary: str, **rest: Any) -> Refusal:
    """A refusal carrying every key a scored run carries, holding the honest null.

    `nothing_was_fitted` is literally true on every one of these rather than
    reassuring: each raise below happens before the single `fit()` call.
    """
    return Refusal(
        {
            "ok": False,
            "error": error,
            "summary": summary,
            "nothing_was_fitted": True,
            "estimator": ESTIMATOR,
            "score": None,
            "trivial_baseline": None,
            "best_constant_on_the_holdout": None,
            "comparison": None,
            "resolution": evals.resolution_for(0, 0),
            "resolution_over_distinct_inputs": None,
            "measured": [],
            "not_measured": STAMPS_NOTHING,
            "decides_nothing": DECIDES_NOTHING,
            "not_tried": not_tried_block(),
            **rest,
        }
    )


# ---------------------------------------------------------------------------
# Reading. One reader, and it is the one this repository already has.


def _readable(path: Any, *, what: str) -> tuple[Path, dict[str, Any]]:
    """The path and its detected format, or a refusal that says which failed.

    `dataquality.detect_format` decides by content and never by extension, which
    is why a `.csv` that is really a parquet file is caught here rather than
    read as one enormous single-column table.
    """
    text = str(path or "").strip()
    if not text:
        raise _refuse(
            "no_path",
            f"No {what} was given, so there was nothing to read.",
        )
    p = Path(text)
    fmt = dataquality.detect_format(p)
    if not fmt.get("readable"):
        raise _refuse(
            "unreadable",
            f"The {what} at {text} could not be read as a table: "
            f"{fmt.get('how') or 'the format could not be determined'} "
            f"(detected {fmt.get('name')!r}). This tool reads what "
            "app/dataquality.py reads - CSV, TSV, JSONL and JSON - and it does "
            "not read parquet, because pandas and pyarrow are not installed.",
            path=text,
            detected=fmt,
        )
    return p, fmt


def _rows(path: Path, fmt: dict[str, Any], limit: int, *, what: str) -> list[dict]:
    """Every row, or a refusal. It never truncates.

    A prefix of a file is not a sample of it - on any file that arrived sorted
    it is a systematically different set of rows - so passing the cap refuses
    rather than scoring what was read so far. That is `carve_eval_set`'s rule
    and `measure_retriever_recall`'s rule, kept the same here on purpose.
    """
    out: list[dict[str, Any]] = []
    stream: Iterator[dict[str, Any]] = dataquality.iter_records(path, fmt)
    for record in stream:
        if not isinstance(record, dict):
            continue
        if len(out) >= limit:
            raise _refuse(
                "more_rows_than_the_cap",
                f"The {what} holds more than {limit:,} rows. Nothing was fitted: "
                "this tool reads the whole file or none of it, because the first "
                f"{limit:,} rows of a sorted file are not a sample of it. Raise "
                "max_rows if the whole file should be read.",
                path=str(path),
                max_rows=limit,
            )
        out.append(record)
    return out


def _columns_of(rows: list[dict[str, Any]], declared: list[str]) -> list[str]:
    """Column names, declared ones first, then anything a row added.

    `declared_columns` answers for a header-only CSV, which has columns and no
    rows under them. JSONL declares nothing, so the rows are the only source
    there and a key that appears on row four still counts as a column.
    """
    seen: list[str] = []
    for name in declared:
        if name not in seen:
            seen.append(name)
    for record in rows:
        for name in record:
            if name is not None and name not in seen:
                seen.append(name)
                if len(seen) >= dataquality.COLUMN_CAP:
                    return seen
    return seen


def _cell(record: dict[str, Any], column: str) -> Any:
    """One cell, with a missing key and an explicit null being the same thing."""
    value = record.get(column)
    return None if dataquality.is_null(value) else value


def _plural(count: int, word: str) -> str:
    """`1 distinct input`, `30 distinct inputs`. A refusal is a sentence."""
    return f"{count:,} {word}" + ("" if count == 1 else "s")


def _label(value: Any) -> str:
    """A target value as the string this tool compares and reports.

    Comparing labels as text rather than as whatever `json.loads` produced is
    what stops `1` from the CSV and `1` from the JSONL being two classes.
    """
    return str(value)


def _as_float(value: Any) -> float | None:
    """A cell as a number, or None. `bool` is deliberately not a number here."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


# ---------------------------------------------------------------------------
# The split. A hash of the row, not a shuffle.


def _input_signature(record: dict[str, Any], columns: list[str]) -> int:
    """WHEN TWO ROWS ARE THE SAME INPUT. The features, and not the answer.

    `dataquality.row_signature` is the repository's one definition of "the same
    row" and it hashes the whole record, answer included. That is right for
    `carve_eval_set`, which is splitting graded examples. It is the wrong
    grouping HERE, and the difference matters twice:

    * two rows with identical features and different labels are the same INPUT.
      Putting one on each side of the split lets the tree have seen this exact
      question already, which is not leakage of the label but is a memorised
      row scored as though it were a new one;
    * the count that decides whether a hold-out can resolve anything is the
      count of distinct inputs. G0's recipe is *"30-50 real inputs"*, and
      `datawork._choose` learned this the expensive way: the same input forty
      times is one input, and counting rows let a forty-row eval file holding
      one distinct question clear a thirty-row threshold.

    Built through `dataquality.row_text` and `signature_of_text` so it is the
    same normalisation and the same stable, unsalted hash as every other
    signature in this product - a second hashing scheme here would be a second
    answer to "is this the same row".
    """
    return dataquality.signature_of_text(
        dataquality.row_text({column: record.get(column) for column in columns})
    )


def _split_key(seed: str, signature: int) -> int:
    """Where this input sits in the draw. Same primitive as `carve_eval_set`.

    Hashing the INPUT rather than its position is what makes two identical
    inputs take the same side: same signature, same key, so no ordering of the
    read can separate them. `dataquality.signature_of_text` is used rather than
    `hash()` because Python salts `hash()` per process and a split that comes
    out differently tomorrow is a split nobody can defend.
    """
    return dataquality.signature_of_text(f"{SPLIT_RULE}|{seed}|{signature}")


def _carve(
    rows: list[dict[str, Any]],
    columns: list[str],
    seed: str,
    fraction: float,
    min_inputs: int,
) -> tuple[list[int], list[int], dict[str, Any]]:
    """`(train_indices, holdout_indices, how)`. Whole groups of identical inputs.

    TAKING WHOLE GROUPS IS THE POINT, and it is `_choose`'s point in
    `app/tools/datawork.py` for the same reason: selecting individual rows would
    let the count land in the middle of a run of identical inputs and put the
    same input on both sides of the split. So the hold-out can come out larger
    than the fraction asked for, and never smaller.

    IT STOPS ON TWO CONDITIONS AND NOT ONE. Enough rows to fill the fraction,
    AND enough distinct inputs to clear `min_inputs` - because a hold-out of two
    hundred rows that is four inputs repeated fifty times each resolves exactly
    as much as four rows do. Whichever condition binds last is the one that
    decides how many groups are taken.
    """
    signatures = [_input_signature(record, columns) for record in rows]
    groups: dict[int, list[int]] = {}
    for position, signature in enumerate(signatures):
        groups.setdefault(signature, []).append(position)

    want_rows = max(1, int(round(len(rows) * fraction)))
    ranked = sorted(groups, key=lambda sig: (_split_key(seed, sig), sig))
    holdout: list[int] = []
    taken: set[int] = set()
    for signature in ranked:
        if len(holdout) >= want_rows and len(taken) >= min_inputs:
            break
        taken.add(signature)
        holdout.extend(groups[signature])
    train = [
        position
        for position, signature in enumerate(signatures)
        if signature not in taken
    ]
    how = {
        "rule": SPLIT_RULE,
        "seed": seed,
        "fraction_asked_for": fraction,
        "rows_asked_for": want_rows,
        "distinct_inputs_asked_for": min_inputs,
        "distinct_inputs_in_the_file": len(groups),
        "how": (
            f"an input is held out when signature_of_text('{SPLIT_RULE}|<seed>|"
            "<feature signature>') is among the lowest for the distinct inputs "
            "in this file. Whole groups of identical inputs move together, so "
            "the same input cannot land on both sides. The signature is built "
            "from the feature columns and NOT from the target, so two rows that "
            "ask the same question with different answers stay together. The "
            "same call gives the same split on any machine and in any process, "
            "and the split does not depend on the order the file was read in."
        ),
        "is": "a stated rule, not a measured optimum",
    }
    return sorted(train), sorted(holdout), how


# ---------------------------------------------------------------------------
# The leak checks.


def _relabelling_leak(
    rows: list[dict[str, Any]],
    columns: list[str],
    labels: list[str],
    classes: int,
) -> list[dict[str, Any]]:
    """Check A. A feature whose values each map to exactly one target value.

    Pure AND no more distinct values than the target has classes. The second
    half is what stops an identifier column - which is trivially pure, because
    every value appears once - from being reported as a leak; the identifier
    case has its own message and its own check.
    """
    found: list[dict[str, Any]] = []
    for column in columns:
        seen: dict[str, str] = {}
        distinct = 0
        pure = True
        for record, label in zip(rows, labels):
            key = _label(_cell(record, column))
            if key not in seen:
                seen[key] = label
                distinct += 1
                if distinct > classes:
                    pure = False
                    break
            elif seen[key] != label:
                pure = False
                break
        if pure and distinct <= classes and distinct > 1:
            found.append(
                {
                    "column": column,
                    "distinct_values": distinct,
                    "classes": classes,
                    "why": (
                        f"every one of the {distinct} values in {column!r} goes "
                        f"with exactly one of the {classes} target values, and "
                        "there are no more of them than there are classes. That "
                        "is the target under another name."
                    ),
                }
            )
    return found


def _oracle_leak(
    rows: list[dict[str, Any]],
    columns: list[str],
    labels: list[str],
    train: list[int],
    holdout: list[int],
) -> list[dict[str, Any]]:
    """Check B. A single feature that gets every held-out row right on its own.

    The mapping is learned on the TRAINING rows only and applied to the held-out
    ones, which is what separates a leak from an identifier: an identifier's
    values are all unseen at scoring time and it collapses to the fallback,
    while a genuine leak generalises perfectly.

    Perfect and not "nearly perfect", on purpose. A threshold below 1.0 turns
    this into a statistical claim that a small hold-out cannot support, and the
    message a perfect column earns is true either way: either it is the target
    under another name, or the problem is a lookup table and not a model.
    """
    if not holdout or not train:
        return []
    fallback = Counter(labels[i] for i in train).most_common(1)[0][0]
    found: list[dict[str, Any]] = []
    for column in columns:
        votes: dict[str, Counter] = {}
        for i in train:
            votes.setdefault(_label(_cell(rows[i], column)), Counter())[labels[i]] += 1
        table = {
            key: sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
            for key, counter in votes.items()
        }
        if len(table) <= 1:
            continue  # a constant column cannot be an oracle
        hits = 0
        unseen = 0
        for i in holdout:
            key = _label(_cell(rows[i], column))
            if key not in table:
                unseen += 1
            if table.get(key, fallback) == labels[i]:
                hits += 1
        if hits == len(holdout):
            found.append(
                {
                    "column": column,
                    "held_out_rows": len(holdout),
                    "values_unseen_in_training": unseen,
                    "why": (
                        f"{column!r} alone gets all {len(holdout)} held-out rows "
                        "right, mapping each of its values to the commonest "
                        "label it had in the training rows. Either it is the "
                        "target under another name, or this problem is a lookup "
                        "table and does not need a model."
                    ),
                }
            )
    return found


#: Date shapes this recognises, and it recognises nothing else on purpose. A
#: date parser that accepts everything accepts "12" as a year; these are the
#: unambiguous written forms, and a column this misses simply is not flagged -
#: which is the direction that costs nothing, because nothing here decides the
#: fit.
_DATE_FORMATS = (
    "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S", "%d-%b-%Y", "%b %d %Y", "%Y-%m",
)

#: How many of a column's values are read when asking whether it is a date. A
#: bound rather than the whole column, because this runs over every column of a
#: table that may hold two hundred thousand rows and it decides nothing.
_DATE_SAMPLE = 200


def _parses(text: str, shape: str) -> bool:
    from datetime import datetime

    try:
        datetime.strptime(text, shape)
    except ValueError:
        return False
    return True


def _date_columns(
    rows: list[dict[str, Any]], columns: list[str], train: list[int]
) -> list[dict[str, Any]]:
    """Columns whose values are written dates. Nothing here changes the fit.

    **THE SPLIT IS RANDOM AND THIS FILE CANNOT MAKE IT ANYTHING ELSE.** That is
    right for most tables and wrong for one shape: rows recorded over time,
    where what you are predicting drifts. Hashing the rows interleaves the
    hold-out with the training rows, so the model is scored on the same period
    it learned - and the number comes back far better than the model will be
    next month.

    MEASURED HERE, on 600 rows of a drifting series - one feature, one date
    column, the label a function of the feature AND of how far through the
    series the row is:

        the tool (hashed split)   tree 116/150 (77%)  trivial 70/150 (47%)
                                  p = 9.84e-08, separated
        the same estimator, fitted on the first 75% and scored on the LAST 25%
                                  tree  70/150 (47%)  trivial 19/150 (13%)

    Thirty points of the tool's score are the split. And the `date` column - 450
    distinct strings in the training rows - was silently dropped as *closer to
    an identifier than to a category*: the single strongest evidence that the
    split was the wrong one was seen, misclassified and discarded, and neither
    "time-ordered" nor "chronological" appeared anywhere in the reply.

    So this finds the evidence and says it. It does NOT split by time - there is
    no such argument and inventing one here would be a different tool - and it
    does not refuse, because a date column in a table of independent rows is
    ordinary. What it removes is the silence.
    """
    from datetime import datetime

    found: list[dict[str, Any]] = []
    for column in columns:
        values: list[str] = []
        for i in train:
            value = _cell(rows[i], column)
            if value is None:
                continue
            text = _label(value).strip()
            if text:
                values.append(text)
            if len(values) >= _DATE_SAMPLE:
                break
        if len(values) < 5:
            continue
        for shape in _DATE_FORMATS:
            # THE FIRST VALUE DECIDES WHETHER THE REST ARE WORTH PARSING. A
            # table may have five hundred columns and this runs over all of
            # them; without the early exit it is nine format attempts against
            # two hundred values per column, on a check that decides nothing.
            try:
                datetime.strptime(values[0], shape)
            except ValueError:
                continue
            if all(_parses(text, shape) for text in values[1:]):
                found.append(
                    {
                        "column": column,
                        "format": shape,
                        "values_read": len(values),
                        "distinct_in_the_sample": len(set(values)),
                    }
                )
                break
    return found


def _counter_columns(
    rows: list[dict[str, Any]],
    columns: list[str],
    train: list[int],
) -> list[dict[str, Any]]:
    """Check C. A NUMERIC feature that is a counter, which is an identifier.

    **THE CONCEPT WAS ALREADY HERE AND WAS APPLIED TO TEXT AND TO THE TARGET
    AND NOT TO A NUMERIC FEATURE.** `_plan_features` drops a text column with
    more than `MAX_CATEGORIES` distinct values in its own words - *closer to an
    identifier than to a category* - and the target check one screen down splits
    an identifier from a quantity on exactly the right property: *an identifier
    is a counter, a quantity has a fractional part*. A numeric FEATURE got
    neither test.

    MEASURED, on the real tool: 400 rows, `customer_id` = 1..400, `churn` =
    (id <= 200), one noise column. Scored 99 of 100 held-out rows, McNemar
    p = 2.4e-14, and the summary said it *separates them at the conventional
    0.05*. Neither leak check could fire - check A needs no more distinct values
    than there are classes, check B falls back on values it never saw - and
    `leak_checks` reported both as having run and found nothing. Write the
    IDENTICAL column as text and the same tool drops it. The asymmetry was the
    whole finding.

    THE RULE IS THE TARGET CHECK'S RULE, SO THERE IS ONE RULE AND NOT TWO: every
    training value parses as a number, every one is whole, and no two are the
    same. `revenue` with a fractional part is a quantity and is kept. An integer
    that repeats is a count and is kept. A whole number with a different value
    in every training row cannot be anything a tree learns FROM - every split on
    it partitions the training rows and nothing else - and if it happens to be
    ordinally aligned with the target, as a row id in a sorted export is, it
    produces a perfect score off a column that will never repeat.

    AND IT REFUSES RATHER THAN DROPPING, which is where it differs from the text
    case. A booster genuinely cannot bin 400 text values; it can and will split
    on 400 integers, and whether an ordinal integer is a measurement or an
    accident of export order is not a thing this file can read. So the column is
    named, `drop_columns` is the door, and the fit the user gets after dropping
    it is the answer to the question they were really asking.
    """
    found: list[dict[str, Any]] = []
    for column in columns:
        values = [_cell(rows[i], column) for i in train]
        present = [value for value in values if value is not None]
        if len(present) != len(train) or not present:
            continue  # a column with gaps is not a counter
        numbers = [_as_float(value) for value in present]
        if any(number is None for number in numbers):
            continue
        if any(number != int(number) for number in numbers):
            continue  # a quantity, not a counter
        distinct = {int(number) for number in numbers}
        if len(distinct) != len(numbers) or len(distinct) <= 1:
            continue
        found.append(
            {
                "column": column,
                "distinct_values": len(distinct),
                "training_rows": len(train),
                "why": (
                    f"{column!r} holds a different whole number in every one of "
                    f"the {len(train):,} training rows. That is a counter, which "
                    "is an identifier - the same test this tool applies to a "
                    "target column, and the same concept it applies to a text "
                    "column with too many values to bin. A tree can split on it "
                    "and the splits partition your training rows and nothing "
                    "else; where the numbering happens to run with the answer, "
                    "as a row id in a sorted export does, the score comes back "
                    "near perfect off a column that never repeats. Neither leak "
                    "check can see this: check A needs no more distinct values "
                    "than there are classes, and check B falls back on values it "
                    "never saw in training."
                ),
            }
        )
    return found


# ---------------------------------------------------------------------------
# The matrix. Fitted from the training rows and from nothing else.


def _plan_features(
    rows: list[dict[str, Any]], columns: list[str], train: list[int]
) -> dict[str, Any]:
    """How each column will be encoded, decided on the TRAINING rows only.

    THE VOCABULARY MUST NOT COME FROM THE HELD-OUT ROWS and neither must the
    numeric-or-categorical decision. A category list built over the whole file
    means the encoding of a training row depends on rows the fit is not allowed
    to see, which is a small leak that produces a slightly better number every
    time and is invisible in the result. A value that turns up only at scoring
    time is a missing value here, and it is counted and reported rather than
    quietly given a code.
    """
    numeric: list[str] = []
    categorical: list[str] = []
    vocabularies: dict[str, dict[str, int]] = {}
    dropped: list[dict[str, Any]] = []
    constant: list[str] = []

    for column in columns:
        values = [_cell(rows[i], column) for i in train]
        present = [value for value in values if value is not None]
        if not present:
            dropped.append(
                {"column": column, "why": "no value in any training row"}
            )
            continue
        numbers = [_as_float(value) for value in present]
        if all(number is not None for number in numbers):
            numeric.append(column)
            if len({number for number in numbers}) <= 1:
                constant.append(column)
            continue
        distinct = sorted({_label(value) for value in present})
        if len(distinct) > MAX_CATEGORIES:
            dropped.append(
                {
                    "column": column,
                    "why": (
                        f"{len(distinct):,} distinct text values over "
                        f"{len(train):,} training rows. A histogram booster bins "
                        f"at most {MAX_CATEGORIES} categories, and a column with "
                        "this many values is closer to an identifier than to a "
                        "category. Embedding it is the hybrid answer and needs a "
                        "model this harness does not ship."
                    ),
                }
            )
            continue
        categorical.append(column)
        vocabularies[column] = {value: code for code, value in enumerate(distinct)}
        if len(distinct) <= 1:
            constant.append(column)

    return {
        "numeric": numeric,
        "categorical": categorical,
        "vocabularies": vocabularies,
        "dropped": dropped,
        "constant": constant,
        "used": numeric + categorical,
        "how": (
            "A column is numeric when every value it has in the TRAINING rows "
            "parses as a finite number, and categorical otherwise. The category "
            "list comes from the training rows alone: a value that appears only "
            "in the held-out rows is a missing value, counted below, because a "
            "vocabulary built over the whole file lets the encoding of a "
            "training row depend on rows the fit may not see."
        ),
    }


def _matrix(
    numpy_module: Any,
    rows: list[dict[str, Any]],
    positions: list[int],
    plan: dict[str, Any],
) -> tuple[Any, int]:
    """`(X, unseen_cells)` for these rows, under a plan built on the train rows.

    Missing numbers and unseen categories both become NaN, which the histogram
    booster handles natively rather than by imputation - so nothing here invents
    a value to stand in for one that is not there.
    """
    np = numpy_module
    columns = plan["used"]
    matrix = np.full((len(positions), len(columns)), np.nan, dtype=float)
    unseen = 0
    for row_index, position in enumerate(positions):
        record = rows[position]
        for column_index, column in enumerate(columns):
            value = _cell(record, column)
            if value is None:
                continue
            if column in plan["vocabularies"]:
                code = plan["vocabularies"][column].get(_label(value))
                if code is None:
                    unseen += 1
                    continue
                matrix[row_index, column_index] = float(code)
            else:
                number = _as_float(value)
                if number is None:
                    unseen += 1
                    continue
                matrix[row_index, column_index] = number
    return matrix, unseen


# ---------------------------------------------------------------------------
# The reply.


def _summarise(payload: dict[str, Any]) -> str:
    """The count, what the trivial answer got, and what the rows can resolve."""
    score = payload["score"]
    trivial = payload["trivial_baseline"]
    comparison = payload["comparison"]
    resolution = payload["resolution"]
    missing = payload["not_tried"]["machine"]["missing"]

    head = (
        f"{ESTIMATOR.rsplit('.', 1)[-1]} scored {score['correct']} of "
        f"{score['of']} held-out rows ({score['accuracy']:.0%}). Always "
        f"answering {trivial['answer']!r} - the commonest label in the "
        f"{payload['split']['train_rows']} rows it was fitted on - scores "
        f"{trivial['correct']} of the same {trivial['of']} "
        f"({trivial['accuracy']:.0%})."
    )
    # AND IF SOME OF THOSE ROWS WERE UNWINNABLE, THAT BELONGS IN THE HEADLINE.
    # It was in `classes.says` and not here, so a score short by fifteen
    # impossible rows read as a score.
    unwinnable = (payload.get("classes") or {}).get("unwinnable_holdout_rows") or 0
    if unwinnable:
        head += (
            f" {unwinnable} of those {score['of']} rows carry a class that "
            "never appears in the training rows, so no model fitted on them "
            "could have got those rows right - both counts above are over a "
            "hold-out that includes them."
        )
    if comparison["disagreed"] == 0:
        middle = (
            " The two agreed on every held-out row, so there is no evidence of "
            "any difference between them at all."
        )
    else:
        middle = (
            f" They disagreed on {comparison['disagreed']} rows - the tree won "
            f"{comparison['improved']} and lost {comparison['regressed']} - and "
            f"McNemar's exact test over those rows gives p = "
            f"{comparison['mcnemar_p']:.3f}, which "
            + (
                "separates them at the conventional 0.05."
                if comparison["separated"]
                else "does not separate them at the conventional 0.05."
            )
        )
    tail = f" {resolution['says']}"
    # AND WHEN THE ROWS REPEAT, THE SENTENCE ABOVE IS NOT THE WHOLE OF IT. The
    # interval and the p-value are over rows; rows that share an input are one
    # observation written down more than once. Saying it here rather than only
    # in a key, because the summary is the sentence a person reads.
    over_inputs = payload.get("resolution_over_distinct_inputs") or {}
    if over_inputs.get("rows_repeat"):
        tail += f" {over_inputs['says']}"
    # AND IF THERE IS A DATE IN THIS FILE, THE SPLIT IS THE FIRST THING TO
    # DOUBT. Random over the rows, whatever the rows mean.
    if (payload.get("split") or {}).get("date_columns"):
        names = [row["column"] for row in payload["split"]["date_columns"]]
        tail += (
            f" THE SPLIT IS RANDOM AND THIS FILE HAS A DATE IN IT ({', '.join(names)}): "
            "if these rows were recorded over time and what you are predicting "
            "drifts, every figure above is measured on rows interleaved with the "
            "ones the tree learned from and is better than the model will be "
            "next month. See split.and_this_split_is_not_by_time."
        )
    tail += (
        " One fit at scikit-learn's defaults; no hyperparameter search was run."
    )
    if missing:
        tail += f" {', '.join(missing)} are not installed on this machine."
    return head + middle + tail


# ---------------------------------------------------------------------------
# The tool.


@tool(
    "fit_a_tree_model",
    description=(
        "Fit a gradient-boosted tree on a table and score it on rows it was NOT "
        "fitted on, beside what always answering the commonest training label "
        "would have scored on the same rows. This is what stage 8's classical "
        "outcomes - NO_DEEP__GRADIENT_BOOSTED_TREES and its five siblings - have "
        "been asking a person to go and do. The score never comes back alone: it "
        "carries the trivial baseline, the paired McNemar test over the rows "
        "where the two disagreed, and the Wilson interval for a hold-out that "
        "size. The split is decided by hashing each row, so it is reproducible "
        "and two identical rows cannot land on opposite sides; a split you "
        "already have can be passed as holdout_path and is CHECKED for leakage "
        "rather than trusted. It refuses rather than producing a flattering "
        "number: too few rows, one class, a target that is really an identifier "
        "or a continuous quantity, no varying features, a hold-out that is all "
        "one class, or a feature that leaks the target. It runs ONE fit at "
        "scikit-learn's defaults - not the 50-trial search the engine asks for - "
        "and every reply says so, along with which of the libraries the engine "
        "names are missing from this machine. It records nothing and opens "
        "nothing."
    ),
    schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "The tabular file to fit on. CSV, TSV, JSONL or JSON. Read "
                    "whole or not at all."
                ),
            },
            "target_column": {
                "type": "string",
                "description": (
                    "The column to predict. Name it only when the user has said "
                    "which it is; nothing here guesses a target."
                ),
            },
            "holdout_path": {
                "type": "string",
                "description": (
                    "A separate file of rows to score on - use it when the split "
                    "is already yours, for instance the two files carve_eval_set "
                    "wrote. Left out, the hold-out is carved from `path` by "
                    "hashing each row. Either way the two sides are checked for "
                    "shared rows and a leak refuses the fit."
                ),
            },
            "feature_columns": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Which columns to fit on. Left out, every column except the "
                    "target is used."
                ),
            },
            "drop_columns": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Columns to leave out. This is the door out of a leak "
                    "refusal: drop the column that carries the answer and run "
                    "again. There is deliberately no flag that scores anyway."
                ),
            },
            "holdout_fraction": {
                "type": "number",
                "description": (
                    f"How much of the file to hold out. Default {DEFAULT_HOLDOUT}, "
                    f"between {MIN_HOLDOUT} and {MAX_HOLDOUT}. A stated choice "
                    "rather than a measured optimum. Ignored when holdout_path "
                    "is given."
                ),
            },
            "seed": {
                "type": "string",
                "description": (
                    "Changes which rows are held out, and nothing else. The same "
                    "seed on the same file always gives the same split."
                ),
            },
            "max_rows": {
                "type": "integer",
                "description": (
                    f"Refuse above this many rows. Default {DEFAULT_ROW_LIMIT:,}. "
                    "It never truncates: a file longer than this is refused "
                    "rather than read in part."
                ),
            },
        },
        "required": ["path", "target_column"],
    },
    reads=("filesystem", "datasets"),
    # NOTHING. Not `facts`, not `filesystem` - this tool creates no file and
    # records no row. See the `measures=()` section of the module docstring for
    # why the tempting stamp is refused.
    writes=(),
    provides=("tabular.tree.fit",),
    label="Fit a tree model",
    group="Data",
    # Short on purpose: `conductor.standing_brief` prints one `name - verb` line
    # per registered tool on every turn, so a verb is a per-turn cost paid by
    # every user forever. See `WhatItCostsTest.BUDGET` in
    # `tests/test_the_diagnosis_is_not_optional.py`.
    verb="fit a tree and score it on held-out rows",
    order=31,
)
def fit_a_tree_model(
    path: str,
    target_column: str,
    holdout_path: str | None = None,
    feature_columns: list[str] | None = None,
    drop_columns: list[str] | None = None,
    holdout_fraction: float = DEFAULT_HOLDOUT,
    seed: str = "",
    max_rows: int = DEFAULT_ROW_LIMIT,
) -> dict[str, Any]:
    """A score with its baseline and its interval, or a refusal and no fit.

    The order here is load-bearing and is worth reading as an order. Everything
    that can refuse runs BEFORE the single `fit()` call: the imports, the read,
    the target, the features, check A, the split, the split's own floors, and
    check B. There is no state of the world in which this refused and also
    fitted, which is what `nothing_was_fitted` on every refusal means.
    """
    try:
        return _fit(
            path=path,
            target_column=target_column,
            holdout_path=holdout_path,
            feature_columns=feature_columns,
            drop_columns=drop_columns,
            holdout_fraction=holdout_fraction,
            seed=seed,
            max_rows=max_rows,
        )
    except Refusal as refusal:
        return refusal.payload


def _fit(
    *,
    path: str,
    target_column: str,
    holdout_path: str | None,
    feature_columns: list[str] | None,
    drop_columns: list[str] | None,
    holdout_fraction: float,
    seed: str,
    max_rows: int,
) -> dict[str, Any]:
    limit = data.bounded(max_rows, DEFAULT_ROW_LIMIT, 1, MAX_ROW_LIMIT)
    target = str(target_column or "").strip()
    seed_text = str(seed or "")

    # -- 0. the libraries, before anything is read -------------------------
    have = available()
    if not (have["sklearn"] and have["numpy"]):
        absent = [
            shown
            for key, shown in (("sklearn", "scikit-learn"), ("numpy", "numpy"))
            if not have[key]
        ]
        raise _refuse(
            "no_estimator",
            "Nothing was fitted: "
            + " and ".join(absent)
            + " could not be imported on this machine, and this repository does "
            "not declare either as a dependency - pyproject.toml lists fastapi, "
            "markdown, pyyaml and uvicorn and nothing else. "
            "`pip install "
            "scikit-learn` in the environment running this harness is what "
            "would make this tool work; nothing here will install it for you.",
            path=str(path),
        )
    import numpy as np  # noqa: PLC0415 - see the module docstring
    from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: PLC0415
    import sklearn  # noqa: PLC0415

    if not target:
        raise _refuse(
            "no_target",
            "No target_column was given. This tool does not guess which column "
            "is the answer - a guessed target produces a real-looking score for "
            "a question nobody asked.",
            path=str(path),
        )

    # -- 1. read ------------------------------------------------------------
    source, fmt = _readable(path, what="dataset")
    rows = _rows(source, fmt, limit, what="dataset")
    declared = dataquality.declared_columns(source, fmt)
    columns = _columns_of(rows, declared)

    holdout_rows: list[dict[str, Any]] = []
    leak_report: dict[str, Any] | None = None
    if holdout_path:
        other, other_fmt = _readable(holdout_path, what="hold-out file")
        holdout_rows = _rows(other, other_fmt, limit, what="hold-out file")
        columns = _columns_of(rows + holdout_rows, declared)
        leak_report = data.check_split_leakage(
            train_path=str(source), eval_path=str(other), max_rows=limit
        )
        leaked = leak_report.get("leaked_rows") or 0
        if leaked:
            raise _refuse(
                "the_split_leaks",
                f"{leaked:,} of the {leak_report.get('eval_rows'):,} rows in the "
                "hold-out file also appear in the file the tree would be fitted "
                "on. Nothing was fitted: a score measured across a leak is not a "
                "score, it is a measurement of how well the tree remembers. "
                "Remove the shared rows, or leave holdout_path out and let the "
                "split be carved by hashing each row, which cannot produce one.",
                path=str(source),
                holdout_path=str(other),
                split_leakage=leak_report,
            )

    if target not in columns:
        raise _refuse(
            "no_such_column",
            f"There is no column named {target!r} in {source.name}. The columns "
            f"it has are: {', '.join(columns[:LIST_CAP]) or 'none'}"
            + (f" and {len(columns) - LIST_CAP} more." if len(columns) > LIST_CAP else "."),
            path=str(source),
            target_column=target,
            columns=columns[:LIST_CAP],
            columns_n=len(columns),
        )

    # -- 2. the target ------------------------------------------------------
    all_rows = rows + holdout_rows
    kept = [record for record in all_rows if _cell(record, target) is not None]
    dropped_no_target = len(all_rows) - len(kept)
    if not kept:
        raise _refuse(
            "target_is_empty",
            f"Every one of the {len(all_rows):,} rows has nothing in {target!r}. "
            "A column that is present and empty is a column somebody added and "
            "never filled; there is no answer here to fit to.",
            path=str(source),
            target_column=target,
            rows_read=len(all_rows),
        )

    labels = [_label(_cell(record, target)) for record in kept]
    counts = Counter(labels)
    classes = len(counts)
    if classes == 1:
        raise _refuse(
            "one_class",
            f"Every row that has a {target!r} says the same thing "
            f"({next(iter(counts))!r}), across {len(kept):,} rows. There is "
            "nothing to predict: always answering that scores 100% and so would "
            "any model.",
            path=str(source),
            target_column=target,
            rows_used=len(kept),
        )
    # THREE WAYS A TARGET IS NOT A LABEL, AND THE ORDER DECIDES WHICH SENTENCE
    # THE USER GETS. It was wrong: a `revenue` column of three hundred distinct
    # floats over three hundred rows was reported as an identifier, because
    # "every row has its own value" was tested first and is true of both. It is
    # true of an id and of a price, and calling a price an id is a wrong
    # diagnosis in the same reply that refuses to give a wrong number. What
    # actually separates them is whether the values are whole: an identifier is
    # a counter, a quantity has a fractional part. So the numeric branch is
    # tested first and splits on that, and the all-distinct test only decides
    # for the values it can decide.
    numbers = [_as_float(value) for value in counts]
    all_numeric = all(number is not None for number in numbers)
    any_fractional = all_numeric and any(
        number != int(number) for number in numbers if number is not None
    )
    looks_like_a_counter = classes == len(kept) and not any_fractional
    if all_numeric and classes > MAX_CLASSES and not looks_like_a_counter:
        raise _refuse(
            "target_is_continuous",
            f"{target!r} holds {classes:,} distinct numbers over "
            f"{len(kept):,} rows"
            + (", with fractional values in it" if any_fractional else "")
            + ", so this is a regression problem and not a classification one. "
            "Nothing was fitted, and the reason is this harness rather than "
            "scikit-learn: HistGradientBoostingRegressor exists and would fit "
            "it in one line, but every score in this product travels with "
            "evals.resolution_for - a Wilson interval over a proportion - and "
            "an R-squared or an MAE has no such interval here. A continuous "
            "score reported without one would be the first bare number in this "
            "product. If the question really is a class - a band, a bucket, a "
            "yes or no - put that in a column and name it here.",
            path=str(source),
            target_column=target,
            rows_used=len(kept),
            distinct_targets=classes,
            max_classes=MAX_CLASSES,
        )
    if classes == len(kept):
        raise _refuse(
            "target_is_an_identifier",
            f"{target!r} has a different value in every one of the {len(kept):,} "
            "rows. That is an identifier, not a label - every row would be its "
            "own class, nothing would ever repeat between the fit and the "
            "hold-out, and any score off it would be meaningless.",
            path=str(source),
            target_column=target,
            rows_used=len(kept),
            distinct_targets=classes,
        )
    if classes > MAX_CLASSES:
        raise _refuse(
            "too_many_labels",
            f"{target!r} holds {classes:,} distinct values over {len(kept):,} "
            f"rows, which is past the {MAX_CLASSES} this tool will treat as "
            "classes. They are not numbers, so this is not a regression problem "
            "either - it is closer to free text or an identifier than to a "
            "label.",
            path=str(source),
            target_column=target,
            rows_used=len(kept),
            distinct_targets=classes,
            max_classes=MAX_CLASSES,
        )

    # -- 3. the features ----------------------------------------------------
    excluded = {target, *(str(name) for name in (drop_columns or []))}
    if feature_columns:
        wanted = [str(name) for name in feature_columns]
        unknown = [name for name in wanted if name not in columns]
        if unknown:
            raise _refuse(
                "no_such_feature_column",
                f"feature_columns names {', '.join(unknown[:LIST_CAP])}, which "
                f"{'is' if len(unknown) == 1 else 'are'} not in {source.name}. "
                f"Its columns are: {', '.join(columns[:LIST_CAP])}.",
                path=str(source),
                columns=columns[:LIST_CAP],
                columns_n=len(columns),
            )
        candidates = [name for name in wanted if name not in excluded]
    else:
        candidates = [name for name in columns if name not in excluded]
    if not candidates:
        raise _refuse(
            "no_features",
            "There is no column left to fit on: "
            + (
                f"{source.name} has only {target!r}."
                if len(columns) == 1
                else "every other column was dropped or excluded."
            ),
            path=str(source),
            target_column=target,
            columns=columns[:LIST_CAP],
            columns_n=len(columns),
        )

    # -- 4. check A, the relabelling leak, before anything is split ---------
    relabelling = _relabelling_leak(kept, candidates, labels, classes)
    if relabelling:
        names = [row["column"] for row in relabelling]
        raise _refuse(
            "a_feature_leaks_the_target",
            f"{names[0]!r} carries the answer: "
            + relabelling[0]["why"]
            + " Nothing was fitted, because a tree with that column in it would "
            "score near 100% and the number would mean nothing. Run again with "
            f"drop_columns={names[:LIST_CAP]!r}. There is deliberately no flag "
            "that scores anyway.",
            path=str(source),
            target_column=target,
            leaking_columns=relabelling[:LIST_CAP],
            leaking_columns_n=len(relabelling),
            check="A - a feature whose values each map to exactly one target value",
        )

    # -- 5. the split -------------------------------------------------------
    floor = data.eval_set_floor()
    holdout_floor = floor.get("rows")
    if not isinstance(holdout_floor, int) or holdout_floor <= 0:
        raise _refuse(
            "no_floor",
            "The number of rows a hold-out needs could not be read from the "
            f"engine ({floor.get('why_not')}). Nothing was fitted: a floor "
            "invented here would be a number nobody measured wearing the "
            "engine's name.",
            path=str(source),
        )

    if holdout_path:
        # `kept` was filtered out of `rows + holdout_rows` IN THAT ORDER, so the
        # boundary is a count and not a membership test. Membership would be
        # wrong twice over: `record in rows` on dicts is equality, so a
        # held-out row that happens to equal a training row would be filed on
        # the wrong side - which is the very case the leak check above exists
        # to catch, and it would have been hidden by the arithmetic that found
        # it.
        kept_from_train = sum(
            1 for record in rows if _cell(record, target) is not None
        )
        train_positions = list(range(kept_from_train))
        holdout_positions = list(range(kept_from_train, len(kept)))
        split_how = {
            "rule": "supplied by the caller",
            "seed": None,
            "how": (
                f"the rows in {source.name} were fitted on and the rows in "
                f"{Path(str(holdout_path)).name} were scored. The split is "
                "yours; what this tool did was check it, with "
                "check_split_leakage, rather than trust it."
            ),
            "is": "the caller's split, checked",
        }
    else:
        # WHAT THE CALLER ASKED FOR IS KEPT SEPARATELY FROM WHAT WAS USED.
        # `fraction_asked_for` used to report the CLAMPED number, so
        # `holdout_fraction=0.9` and `holdout_fraction=2.0` both came back as
        # `fraction_asked_for: 0.5` and `-1.0` came back as `0.05` - silently,
        # in a field whose name is a claim about the caller. A key that reports
        # our value under the caller's name is how somebody concludes their
        # argument was honoured.
        asked = holdout_fraction
        try:
            fraction = float(asked)
        except (TypeError, ValueError):
            fraction = DEFAULT_HOLDOUT
        if not math.isfinite(fraction):
            fraction = DEFAULT_HOLDOUT
        used = max(MIN_HOLDOUT, min(fraction, MAX_HOLDOUT))
        train_positions, holdout_positions, split_how = _carve(
            kept, candidates, seed_text, used, holdout_floor
        )
        split_how["fraction_asked_for"] = asked
        split_how["fraction_used"] = used
        split_how["fraction_was_clamped"] = used != fraction or fraction != asked
        if split_how["fraction_was_clamped"]:
            split_how["fraction_how"] = (
                f"you asked for holdout_fraction={asked!r} and this split used "
                f"{used}. The bounds are {MIN_HOLDOUT} and {MAX_HOLDOUT} - below "
                "the first the hold-out stops resolving anything, above the "
                "second the fit is on the smaller half - and a value outside "
                "them is moved to the nearest bound rather than refused. The "
                "number the score is over is fraction_used."
            )

    # THE COUNT THAT DECIDES IS THE COUNT OF DISTINCT INPUTS, on both sides, and
    # it is G0's own recipe rather than a threshold invented here: "30-50 real
    # INPUTS". `datawork._choose` learned what counting rows instead costs - a
    # forty-row eval file holding one distinct question, clearing a thirty-row
    # bar. A hold-out of two hundred rows that is four inputs repeated fifty
    # times each resolves what four rows resolve, and the Wilson interval below
    # would report it as two hundred.
    train_inputs = {_input_signature(kept[i], candidates) for i in train_positions}
    holdout_inputs = {_input_signature(kept[i], candidates) for i in holdout_positions}
    if len(holdout_inputs) < holdout_floor:
        raise _refuse(
            "hold_out_too_small",
            f"The hold-out came out at {len(holdout_positions):,} rows holding "
            + _plural(len(holdout_inputs), "distinct input")
            + f", and {holdout_floor} is the "
            f"floor - {floor.get('declared_in')}, the same threshold G0 asks an "
            "eval set to clear, and G0's own recipe counts real INPUTS rather "
            "than rows. Nothing was fitted: the same input repeated is one "
            "input, so a score over these rows cannot separate itself from the "
            "trivial answer and would be a number that reads like a result and "
            "is not one. The whole file holds "
            + _plural(
                int(
                    split_how.get(
                        "distinct_inputs_in_the_file",
                        len(train_inputs | holdout_inputs),
                    )
                ),
                "distinct input",
            )
            + f" across {len(kept):,} rows."
            + (
                ""
                if holdout_path
                else " Raise holdout_fraction, or bring rows that differ."
            ),
            path=str(source),
            rows_used=len(kept),
            holdout_rows=len(holdout_positions),
            holdout_distinct_inputs=len(holdout_inputs),
            holdout_floor=floor,
        )
    if len(train_positions) < dataquality.MIN_ROWS_FOR_TRAINING:
        raise _refuse(
            "too_few_rows_to_fit_on",
            f"{len(train_positions)} rows would be left to fit on, and this "
            f"harness already calls anything under {dataquality.MIN_ROWS_FOR_TRAINING} "
            "too small to train on (dataquality.MIN_ROWS_FOR_TRAINING). Nothing "
            "was fitted. A tree fitted on that many rows is a tree that "
            "memorised them.",
            path=str(source),
            rows_used=len(kept),
            train_rows=len(train_positions),
            floor=dataquality.MIN_ROWS_FOR_TRAINING,
        )

    holdout_labels = [labels[i] for i in holdout_positions]
    train_labels = [labels[i] for i in train_positions]
    if len(set(train_labels)) == 1:
        raise _refuse(
            "training_rows_are_one_class",
            f"All {len(train_positions):,} rows the tree would be fitted on say "
            f"{train_labels[0]!r}, even though the file has {classes} classes in "
            "it. Nothing was fitted: a classifier fitted on one class has "
            "learned one answer, and every held-out row of any other class is "
            "already wrong."
            + (
                " Change seed to draw a different split."
                if not holdout_path
                else " The split came from you; the minority class is all on "
                "the hold-out side of it."
            ),
            path=str(source),
            train_rows=len(train_positions),
            classes=classes,
            split=split_how,
        )
    if len(set(holdout_labels)) == 1:
        raise _refuse(
            "hold_out_is_one_class",
            f"All {len(holdout_positions)} held-out rows say "
            f"{holdout_labels[0]!r}. Always answering that scores 100% on them, "
            "so nothing a model did could be told from the trivial answer. "
            "Nothing was fitted."
            + (
                " Change seed to draw a different hold-out."
                if not holdout_path
                else ""
            ),
            path=str(source),
            holdout_rows=len(holdout_positions),
            split=split_how,
        )

    # A split this tool carved cannot put the same INPUT on both sides. That is
    # a property of `_carve` rather than an observation, so it is COUNTED and
    # reported rather than asserted in prose - and when the split came from the
    # caller, this is the count that says whether theirs did. It is stricter
    # than `check_split_leakage`, which compares whole rows: a held-out row
    # whose features the tree has already seen, with a different label written
    # beside them, is a question the tree has already been asked.
    shared = sum(
        1
        for i in holdout_positions
        if _input_signature(kept[i], candidates) in train_inputs
    )
    if shared:
        raise _refuse(
            "identical_rows_on_both_sides",
            f"{shared:,} of the {len(holdout_positions):,} held-out rows ask a "
            "question the tree would already have been fitted on - the same "
            "feature values appear on both sides. Nothing was fitted. "
            + (
                "This split came from you; leave holdout_path out and the split "
                "is carved by hashing each row, which cannot produce this."
                if holdout_path
                else "This is a defect in the split this tool carved and should "
                "not be reachable - please report it."
            ),
            path=str(source),
            identical_rows=shared,
            split=split_how,
        )

    # -- 6. the encoding, and check B ---------------------------------------
    plan = _plan_features(kept, candidates, train_positions)
    if not plan["used"]:
        raise _refuse(
            "no_usable_features",
            f"Not one of the {len(candidates)} candidate columns could be used: "
            + "; ".join(
                f"{row['column']!r} - {row['why']}" for row in plan["dropped"][:LIST_CAP]
            )
            + ". Nothing was fitted.",
            path=str(source),
            features=plan["dropped"][:LIST_CAP],
            features_n=len(plan["dropped"]),
        )
    cells = len(kept) * len(plan["used"])
    if cells > MAX_CELLS:
        raise _refuse(
            "too_much_to_fit_at_once",
            f"{len(kept):,} rows by {len(plan['used']):,} columns is "
            f"{cells:,} cells, and this tool builds at most {MAX_CELLS:,} in "
            "one matrix. Nothing was fitted, and nothing was truncated to make "
            "it fit - a tree fitted on a prefix of your rows or a guess at "
            "which columns mattered is a different experiment reported as this "
            "one. Lower max_rows, or name the columns to fit on in "
            "feature_columns.",
            path=str(source),
            rows_used=len(kept),
            features_n=len(plan["used"]),
            cells=cells,
            max_cells=MAX_CELLS,
        )
    if len(plan["constant"]) == len(plan["used"]):
        raise _refuse(
            "every_feature_is_constant",
            f"All {len(plan['used'])} usable columns hold the same value in "
            "every training row, so there is nothing for a tree to split on. "
            "Whatever it scored would be the trivial answer wearing a model's "
            "name. Nothing was fitted.",
            path=str(source),
            features=plan["used"][:LIST_CAP],
            features_n=len(plan["used"]),
        )

    oracle = _oracle_leak(
        kept, plan["used"], labels, train_positions, holdout_positions
    )
    if oracle:
        names = [row["column"] for row in oracle]
        raise _refuse(
            "a_feature_leaks_the_target",
            oracle[0]["why"]
            + " Nothing was fitted. Run again with "
            f"drop_columns={names[:LIST_CAP]!r} to see what the rest of the "
            "columns are worth. There is deliberately no flag that scores anyway.",
            path=str(source),
            target_column=target,
            leaking_columns=oracle[:LIST_CAP],
            leaking_columns_n=len(oracle),
            check=(
                "B - one feature, mapped value-to-commonest-label on the "
                "training rows, gets every held-out row right"
            ),
        )

    counters = _counter_columns(kept, plan["numeric"], train_positions)
    if counters:
        names = [row["column"] for row in counters]
        raise _refuse(
            "a_feature_is_an_identifier",
            counters[0]["why"]
            + " Nothing was fitted. Run again with "
            f"drop_columns={names[:LIST_CAP]!r} to see what the rest of the "
            "columns are worth. There is deliberately no flag that scores "
            "anyway.",
            path=str(source),
            target_column=target,
            identifier_columns=counters[:LIST_CAP],
            identifier_columns_n=len(counters),
            check=(
                "C - a numeric feature with a different whole number in every "
                "training row, which is a counter and so an identifier"
            ),
        )

    # -- 7. the one fit -----------------------------------------------------
    train_matrix, _ = _matrix(np, kept, train_positions, plan)
    holdout_matrix, unseen_cells = _matrix(np, kept, holdout_positions, plan)
    categorical_mask = np.array(
        [column in plan["vocabularies"] for column in plan["used"]], dtype=bool
    )
    code_of = {label: code for code, label in enumerate(sorted(set(train_labels)))}
    y_train = np.array([code_of[label] for label in train_labels], dtype=int)

    params = {
        "random_state": 0,
        "early_stopping": False,
        "categorical_features": "a boolean mask over the columns above",
    }
    estimator = HistGradientBoostingClassifier(
        random_state=0,
        early_stopping=False,
        categorical_features=categorical_mask,
    )
    started = time.monotonic()
    estimator.fit(train_matrix, y_train)
    predicted = estimator.predict(holdout_matrix)
    seconds = time.monotonic() - started

    label_of = {code: label for label, code in code_of.items()}
    predictions = [label_of.get(int(code)) for code in predicted]

    # -- 8. the two scores, on the same rows --------------------------------
    tree_right = [
        predictions[i] == holdout_labels[i] for i in range(len(holdout_labels))
    ]
    trivial_answer = sorted(
        Counter(train_labels).items(), key=lambda kv: (-kv[1], kv[0])
    )[0][0]
    trivial_right = [label == trivial_answer for label in holdout_labels]

    n = len(holdout_labels)
    correct = sum(tree_right)
    trivial_correct = sum(trivial_right)
    improved = sum(1 for i in range(n) if tree_right[i] and not trivial_right[i])
    regressed = sum(1 for i in range(n) if trivial_right[i] and not tree_right[i])
    p_value = evals.mcnemar(improved, regressed)

    # -- 8b. THE SAME TWO NUMBERS OVER INDEPENDENT UNITS --------------------
    #
    # **THE INTERVAL AND THE p-VALUE ABOVE ARE OVER ROWS, AND ROWS THAT SHARE
    # AN INPUT ARE NOT INDEPENDENT.** This module's own docstring says so where
    # the floor is applied - *a hold-out of two hundred rows that is four inputs
    # repeated fifty times each resolves what four rows resolve, and the Wilson
    # interval below would report it as two hundred* - and that sentence is the
    # stated justification for the distinct-input FLOOR. The floor defends the
    # below-thirty case only. Above it the overstatement is fully present, and
    # `holdout_distinct_inputs` sat in the payload beside `resolution.n` with
    # nothing reconciling them.
    #
    # MEASURED HERE: 160 distinct inputs each repeated ten times gave a hold-out
    # of 400 rows holding 40 distinct inputs.
    #
    #     over rows    n=400  ci [0.577, 0.671]  +-4.7 pts  p=7.279e-08  separated
    #     over inputs  n=40   ci [0.470, 0.758]  +-14.4 pts p=0.1338     NOT separated
    #
    # The interval is 3.04 times as wide and THE VERDICT FLIPS. Both numbers
    # were computable from the payload - `holdout_distinct_inputs` sat next to
    # `resolution.n` - and only one of them was reported.
    #
    # WHAT IS COUNTED HERE IS COUNTED AND NOT MODELLED. An input counts as right
    # only when the tree was right on EVERY row carrying it, which needs no
    # choice about how to aggregate a group whose rows disagree and is the
    # conservative direction where they do. Where each input carries one label -
    # the ordinary repeated-row case - it is exactly the number of inputs the
    # tree got right. The row-level figures are NOT replaced: both are real, and
    # which one a reader wants depends on whether their repeated rows are
    # repeated measurements or one measurement written down twice, which is
    # their question and not this file's.
    holdout_groups: dict[int, list[int]] = {}
    for position, index in enumerate(holdout_positions):
        holdout_groups.setdefault(
            _input_signature(kept[index], candidates), []
        ).append(position)
    inputs_n = len(holdout_groups)
    tree_right_on_input = [
        all(tree_right[j] for j in members) for members in holdout_groups.values()
    ]
    trivial_right_on_input = [
        all(trivial_right[j] for j in members) for members in holdout_groups.values()
    ]
    inputs_correct = sum(tree_right_on_input)
    inputs_trivial_correct = sum(trivial_right_on_input)
    inputs_improved = sum(
        1
        for i in range(inputs_n)
        if tree_right_on_input[i] and not trivial_right_on_input[i]
    )
    inputs_regressed = sum(
        1
        for i in range(inputs_n)
        if trivial_right_on_input[i] and not tree_right_on_input[i]
    )
    rows_repeat = inputs_n < n

    # WHETHER ANYTHING IN THIS FILE IS A DATE. Read off ALL the candidate
    # columns and not only the ones that survived `_plan_features` - the column
    # that gives a time ordering away is usually the one dropped for having a
    # different value in every row, which is exactly where it went unnoticed.
    date_columns = _date_columns(kept, candidates, train_positions)

    unseen_classes = sorted(set(holdout_labels) - set(train_labels))
    unwinnable = sum(1 for label in holdout_labels if label in set(unseen_classes))
    best_constant, best_hits = sorted(
        Counter(holdout_labels).items(), key=lambda kv: (-kv[1], kv[0])
    )[0]

    payload: dict[str, Any] = {
        "ok": True,
        "error": None,
        "nothing_was_fitted": False,
        "path": str(source),
        "holdout_path": str(holdout_path) if holdout_path else None,
        "target_column": target,
        "task": "classification",
        "estimator": ESTIMATOR,
        "rows": {
            "read": len(all_rows),
            "used": len(kept),
            "dropped_with_no_target": dropped_no_target,
            "max_rows": limit,
            "is": (
                "this program's arithmetic over the rows it read, not a "
                "measurement of the file. Nothing here is recorded as "
                "tabular_rows; that needs a tool that counts the whole file and "
                "says so."
            ),
        },
        "classes": {
            "n": classes,
            "in_training": len(set(train_labels)),
            "in_holdout": len(set(holdout_labels)),
            "in_holdout_but_never_in_training": [
                quarantine(label, source=f"the {target!r} column of {source.name}")
                for label in unseen_classes[:LIST_CAP]
            ],
            "in_holdout_but_never_in_training_n": len(unseen_classes),
            # HOW MANY ROWS THAT COSTS, which is the number the score is short
            # by and was nowhere in the reply. The count of CLASSES was here and
            # the count of ROWS was not, so a headline of 54 of 120 could be 15
            # rows no model could have got right and nothing said so.
            "unwinnable_holdout_rows": unwinnable,
            "says": (
                f"{len(unseen_classes)} of the classes in the held-out rows never "
                "appear in the rows the tree was fitted on, so the "
                f"{unwinnable} held-out row(s) carrying them could not have been "
                "got right whatever the tree learned."
                if unseen_classes
                else "Every class in the held-out rows also appears in the "
                "training rows."
            ),
        },
        "split": {
            "train_rows": len(train_positions),
            "train_distinct_inputs": len(train_inputs),
            "holdout_rows": n,
            "holdout_distinct_inputs": len(holdout_inputs),
            "inputs_on_both_sides": shared,
            "holdout_floor": floor,
            "date_columns": date_columns,
            "and_this_split_is_not_by_time": (
                (
                    "This file has "
                    + ", ".join(
                        f"{row['column']!r} (dates written {row['format']!r})"
                        for row in date_columns[:LIST_CAP]
                    )
                    + " in it, and this split is RANDOM over the rows. If these "
                    "rows were recorded over time and what you are predicting "
                    "drifts, a random split scores the tree on rows interleaved "
                    "with the ones it learned from, and the number comes back "
                    "better than the model will be next month. On a 600-row "
                    "drifting series built to check this, the hashed split "
                    "scored 116 of 150 and the same estimator fitted on the "
                    "first three quarters and scored on the last quarter got 70 "
                    "of 150 - thirty points of the first number were the split. "
                    "Nothing here splits by time and there is no argument that "
                    "makes it: sort by that column, cut it yourself, and pass "
                    "the later part as holdout_path."
                )
                if date_columns
                else "No column in this file is written as a date, so nothing "
                "here suggests the rows are ordered in time. That is not proof "
                "they are not: a row order with no timestamp in it is invisible "
                "to this and to every other check here."
            ),
            **split_how,
        },
        "split_leakage": leak_report,
        "features": {
            "used": plan["used"][:LIST_CAP],
            "used_n": len(plan["used"]),
            "numeric_n": len(plan["numeric"]),
            "categorical_n": len(plan["categorical"]),
            "constant": plan["constant"][:LIST_CAP],
            "constant_n": len(plan["constant"]),
            "dropped": plan["dropped"][:LIST_CAP],
            "dropped_n": len(plan["dropped"]),
            "cells_missing_or_unseen_in_the_holdout": unseen_cells,
            "how": plan["how"],
        },
        "leak_checks": [
            {
                "check": "A - the relabelling",
                "what": (
                    "a feature whose values each map to exactly one target "
                    "value, with no more distinct values than there are classes"
                ),
                "columns_checked": len(candidates),
                "found": 0,
            },
            {
                "check": "B - the single-column oracle",
                "what": (
                    "one feature, mapped value-to-commonest-label on the "
                    "training rows, getting every held-out row right"
                ),
                "columns_checked": len(plan["used"]),
                "found": 0,
            },
            {
                "check": "C - the numeric identifier",
                "what": (
                    "a numeric feature holding a different whole number in "
                    "every training row, which is a counter and so an "
                    "identifier - the test this tool already applied to the "
                    "target column and to a text column with too many values"
                ),
                "columns_checked": len(plan["numeric"]),
                "found": 0,
            },
        ],
        "fit": {
            "params": params,
            "trials": TRIALS_RUN,
            "seconds": seconds,
            "sklearn_version": sklearn.__version__,
            "how": (
                "one fit, at scikit-learn's defaults, with early stopping off "
                "and random_state=0 so the same call gives the same tree. "
                "Missing numbers and categories the fit never saw are left as "
                "NaN, which this estimator handles natively - nothing here "
                "invents a value to stand in for one that is not there."
            ),
        },
        "score": {
            "correct": correct,
            "of": n,
            "accuracy": correct / n,
            "how": (
                f"counted over {n} rows the tree was not fitted on, comparing "
                "its prediction with the value in the target column"
            ),
        },
        "trivial_baseline": {
            "answer": trivial_answer,
            "answer_is": quarantine(
                trivial_answer, source=f"the {target!r} column of {source.name}"
            ),
            "correct": trivial_correct,
            "of": n,
            "accuracy": trivial_correct / n,
            "how": (
                "the commonest label among the rows the tree was FITTED on, "
                "applied to every held-out row. A real predictor, fitted where "
                "the tree was fitted and scored where the tree was scored, so "
                "the two numbers are comparable."
            ),
        },
        "best_constant_on_the_holdout": {
            "answer": best_constant,
            "correct": best_hits,
            "of": n,
            "accuracy": best_hits / n,
            "peeks": True,
            "is": (
                "the best any single constant answer could have scored on these "
                "rows, which is only knowable by looking at them. It is an upper "
                "bound and NOT the comparison above; it is here so that a "
                "hold-out that happens to be lopsided is visible rather than "
                "flattering."
            ),
        },
        "comparison": {
            "difference_points": (correct - trivial_correct) / n * 100.0,
            "improved": improved,
            "regressed": regressed,
            "disagreed": improved + regressed,
            "agreed": n - improved - regressed,
            "mcnemar_p": p_value,
            "separated": p_value < 0.05,
            "how": (
                "McNemar's exact test over the held-out rows where the tree and "
                "the trivial answer disagreed. Paired, because both scored the "
                "SAME rows - rows they agree on carry no information about the "
                "difference. evals.mcnemar, the same test the eval bench uses."
            ),
        },
        "resolution": evals.resolution_for(correct, n),
        "resolution_over_distinct_inputs": {
            **evals.resolution_for(inputs_correct, inputs_n),
            "correct": inputs_correct,
            "of": inputs_n,
            "trivial_correct": inputs_trivial_correct,
            "improved": inputs_improved,
            "regressed": inputs_regressed,
            "mcnemar_p": evals.mcnemar(inputs_improved, inputs_regressed),
            "separated": evals.mcnemar(inputs_improved, inputs_regressed) < 0.05,
            "rows_repeat": rows_repeat,
            "how": (
                f"the same two functions over the {inputs_n} DISTINCT INPUTS in "
                f"the hold-out rather than over its {n} rows. An input counts as "
                "right only when the tree was right on every row carrying it, "
                "which is counted rather than modelled. Rows that share an input "
                "are not independent observations, so `resolution` above - which "
                "is over rows - is narrower than these rows support whenever "
                "this count is lower than that one, and this block is the "
                "version that is not."
            ),
            "says": (
                (
                    f"The hold-out is {n} rows holding {inputs_n} distinct "
                    "inputs, so the interval above is computed over more units "
                    "than there are independent observations. Over the inputs "
                    "(evals.resolution_for is the eval bench's function and its "
                    "sentence says 'rows'; here every one of them is a distinct "
                    "input): "
                    + evals.resolution_for(inputs_correct, inputs_n)["says"]
                    + " The paired test over inputs gives p = "
                    f"{evals.mcnemar(inputs_improved, inputs_regressed):.3g}"
                    + (
                        ", which separates them at the conventional 0.05."
                        if evals.mcnemar(inputs_improved, inputs_regressed) < 0.05
                        else ", which does not separate them at the conventional "
                        "0.05."
                    )
                )
                if rows_repeat
                else (
                    f"Every one of the {n} held-out rows is a different input, "
                    "so this is the same measurement as `resolution` above and "
                    "nothing here is overstated."
                )
            ),
        },
        "not_tried": not_tried_block(),
        "measured": [],
        "not_measured": STAMPS_NOTHING,
        "decides_nothing": DECIDES_NOTHING,
    }
    payload["summary"] = _summarise(payload)
    return payload


__all__ = [
    "DEFAULT_HOLDOUT",
    "ESTIMATOR",
    "MAX_CATEGORIES",
    "MAX_CELLS",
    "MAX_CLASSES",
    "Refusal",
    "SPLIT_RULE",
    "available",
    "fit_a_tree_model",
    "installed",
    "libraries_the_engine_names",
    "not_tried_block",
    "trials_the_gate_asks_for",
    "tuning_the_engine_asks_for",
]
