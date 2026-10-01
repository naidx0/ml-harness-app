"""The freshness-stamped knowledge: a model shortlist and a GPU price table.

## Why these are tools and not ledger facts

`docs/diagnosis_engine.yaml` holds what is true about the USER'S situation and
what a gate may believe. These two files hold what is true about THE WORLD as
of a stamped instant - which models exist and what rented compute asks. A
world-fact is nobody's evidence: it opens no gate, it is scoped to no thread,
and its only honest provenance is "fetched from <source> at <time>". So the
tools below measure nothing, stamp nothing, and put the date IN the answer -
every reply carries `fetched_at`, `age_days` and a plain sentence when the
snapshot is old.

## Staleness is reported, never guessed around

`scripts/refresh_knowledge.py` writes the snapshots and is the only thing that
does. Prices move daily and models monthly, so the two files carry different
budgets (STALE_AFTER_DAYS). A stale file is still served - last month's truth
with its date beats an error - but the answer says so, `mlh doctor` says so,
and refreshing is one command the reply names.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.tools.registry import tool

#: Where the snapshots live: package data beside the code, exactly like
#: `app/model_configs/`, so an installed copy has them out of the box.
KNOWLEDGE_ROOT = Path(__file__).resolve().parents[1] / "knowledge"

#: How old each snapshot may be before every answer starts saying "stale".
#: Prices are marketplace asks and drift daily; the model ladder moves when
#: labs ship, which is monthly at the fastest.
STALE_AFTER_DAYS = {"model_shortlist.json": 60, "gpu_prices.json": 21,
                    "local_recipes.json": 45}

REFRESH_COMMAND = "python scripts/refresh_knowledge.py"


def age_days(fetched_at: str) -> float | None:
    """Days since the stamp, or None when the stamp is unreadable."""
    try:
        stamped = datetime.fromisoformat(fetched_at)
    except (TypeError, ValueError):
        return None
    return (datetime.now(timezone.utc) - stamped).total_seconds() / 86400.0


def load(name: str) -> dict[str, Any]:
    """One snapshot, with its age computed and its staleness said out loud."""
    path = KNOWLEDGE_ROOT / name
    if not path.is_file():
        return {
            "ok": False,
            "error": "missing_knowledge",
            "detail": f"{path} does not exist. Run `{REFRESH_COMMAND}` to fetch it.",
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {
            "ok": False,
            "error": "unreadable_knowledge",
            "detail": f"{path} is not readable as JSON: {error}",
        }
    age = age_days(str(data.get("fetched_at")))
    budget = STALE_AFTER_DAYS.get(name)
    # A file with no freshness budget is CURATED, not fetched - the playbook
    # is versioned by git and edited by hand, so a missing fetched_at is its
    # normal state, not staleness. Only fetched snapshots can go stale.
    stale = budget is not None and (age is None or age > budget)
    data.update(
        ok=True,
        age_days=None if age is None else round(age, 1),
        stale=stale,
        staleness=(
            (f"fetched {round(age, 1)} days ago, inside its {budget}-day budget."
             if budget is not None and age is not None
             else "curated by hand, versioned in git - no freshness budget applies.")
            if not stale
            else (
                f"STALE: fetched {round(age, 1)} days ago against a {budget}-day "
                f"budget. The rows below were true then, not necessarily now. "
                f"Refresh with `{REFRESH_COMMAND}`."
                if age is not None
                else f"UNDATED: the snapshot carries no readable fetched_at, so its "
                     f"age is unknown. Refresh with `{REFRESH_COMMAND}`."
            )
        ),
    )
    return data


@tool(
    name="read_model_shortlist",
    description=(
        "The curated model ladder with live-fetched facts: parameters, license, "
        "gating, last release and 30-day downloads per entry, each read from the "
        "Hugging Face API when the snapshot was taken. The ladder itself is "
        "editorial; every number is the API's. The answer carries fetched_at and "
        "says plainly when the snapshot is stale."
    ),
    schema={"type": "object", "properties": {}},
    reads=("knowledge",),
    writes=(),
    measures=(),
    approval="never",
    provides=("knowledge.models.shortlist",),
    label="Read the model shortlist",
    group="Choose",
    verb="read the model ladder",
    order=26,
)
def read_model_shortlist() -> dict[str, Any]:
    answer = load("model_shortlist.json")
    if answer.get("ok"):
        answer["summary"] = (
            f"{len(answer.get('models', []))} models on the ladder, "
            + answer["staleness"]
        )
    return answer


@tool(
    name="read_gpu_prices",
    description=(
        "What rented single GPUs actually ask right now: live marketplace offers "
        "(vast.ai, verified on-demand) sampled at the stamped instant - min and "
        "median USD/hour and VRAM per card. Not a vendor rate card and not a "
        "promise; the fetched_at is part of the number, and the answer says "
        "plainly when the snapshot is stale."
    ),
    schema={"type": "object", "properties": {}},
    reads=("knowledge",),
    writes=(),
    measures=(),
    approval="never",
    provides=("knowledge.gpu.prices",),
    label="Read GPU rental prices",
    group="Look",
    verb="read what rented GPUs ask",
    order=27,
)
def read_gpu_prices() -> dict[str, Any]:
    answer = load("gpu_prices.json")
    if answer.get("ok"):
        answer["summary"] = (
            f"{len(answer.get('gpus', []))} GPU types priced off "
            f"{answer.get('market_offers_seen', '?')} live offers, "
            + answer["staleness"]
        )
    return answer


def doctor_row() -> dict[str, Any]:
    """The `mlh doctor` view: fine, known-open (stale), or broken.

    Stale is OPEN, not broken - the install is healthy, the world moved - and
    the detail names the age and the one command that resets it. Missing or
    unreadable files are BROKEN: a build that shipped without its knowledge is
    the ledgers' V.0 defect wearing a new file extension.
    """
    ages, stale_bits, broken = [], [], []
    for name in STALE_AFTER_DAYS:
        answer = load(name)
        if not answer.get("ok"):
            broken.append(f"{name}: {answer.get('detail')}")
            continue
        ages.append(f"{name.split('.')[0]} {answer['age_days']}d")
        if answer["stale"]:
            stale_bits.append(
                f"{name} is {answer['age_days']} days old "
                f"(budget {STALE_AFTER_DAYS[name]}d)"
            )
    if broken:
        return {"check": "knowledge", "ok": False,
                "detail": "; ".join(broken),
                "why": "the freshness-stamped world knowledge (model ladder, GPU prices)"}
    if stale_bits:
        return {"check": "knowledge", "ok": False, "open": True,
                "detail": "; ".join(stale_bits),
                "why": ("world knowledge past its freshness budget - the install is "
                        f"healthy, the world moved. `{REFRESH_COMMAND}` resets it.")}
    return {"check": "knowledge", "ok": True,
            "detail": ", ".join(ages),
            "why": "the freshness-stamped world knowledge (model ladder, GPU prices)"}


def _score_journeys(book: dict[str, Any], ask: str) -> list[tuple[int, list[str], dict[str, Any]]]:
    """Every journey the words touch, most keyword hits first. Pure code."""
    lowered = str(ask).lower()
    scored = []
    for journey in book.get("journeys", []):
        hits = [k for k in journey["keywords"] if k in lowered]
        if hits:
            scored.append((len(hits), hits, journey))
    scored.sort(key=lambda t: -t[0])
    return scored


def match_journey(ask: str) -> str | None:
    """The playbook's best match for a sentence, or None — nothing invented.

    The same scoring `map_the_ask` serves through the tool door, exposed as a
    plain function so the conductor can name the journey a thread's goal
    mapped to without a tool call. It carries exactly the authority the match
    has: "these words contained these keywords", nothing more.
    """
    book = load("playbook.json")
    if not book.get("ok"):
        return None
    scored = _score_journeys(book, ask)
    return scored[0][2]["name"] if scored else None


def journey_names() -> list[str]:
    """Every route the playbook carries, in its own order.

    One reader for the list, so the overview, the chooser and its refusal
    cannot disagree about which routes exist.
    """
    book = load("playbook.json")
    if not book.get("ok"):
        return []
    return [str(j["name"]) for j in book.get("journeys", []) if j.get("name")]


#: Ways a person says, in the same sentence as their goal, that they have
#: nothing yet. A CLOSED LIST matched literally, for the same reason the
#: preference-pair degradations are a closed list: the alternative is asking a
#: model whether somebody has data, and a model that guesses wrong here sends
#: them down a route whose first step asks for a folder that does not exist.
#:
#: FOUND ON THE NO-DATA WALK. "I want to fine-tune a model so it writes product
#: copy in our brand voice. I dont have a dataset yet." mapped to
#: `train_on_my_files`, whose first step is "record where your material lives".
#: The keywords that matched were `fine-tune` and `model`; the clause saying
#: there was nothing to point at was not weighed at all, and nothing anywhere
#: on the route said it could not start.
NO_MATERIAL_YET: tuple[str, ...] = (
    "no dataset",
    "no data",
    "no examples",
    "no training data",
    "not have a dataset",
    "not have any data",
    "not have data",
    "dont have a dataset",
    "dont have any data",
    "dont have data",
    "havent collected",
    "have not collected",
    "nothing to train on",
    "starting from nothing",
)


#: Ways a person says the training already happened. A CLOSED LIST for the same
#: reason as NO_MATERIAL_YET.
#:
#: FOUND ON THE ADAPTER WALK. "I trained an adapter last week and I want to know
#: if it is any good" mapped to `train_on_my_files` - a seventeen-step route
#: that begins by carving rows and ends by training one. The words `trained` and
#: `model` were weighed; "I trained ... last week", meaning it is already done,
#: was not. Somebody holding a finished adapter was handed the instructions for
#: making another.
ALREADY_TRAINED: tuple[str, ...] = (
    "i trained",
    "we trained",
    "already trained",
    "have trained",
    "trained an adapter",
    "trained a model",
    "my adapter",
    "have an adapter",
    "already fine-tuned",
    "already finetuned",
    "just fine-tuned",
    # The same thing in the other word order, which is how it was actually
    # typed on the closed-list walk. A literal list grows by what people are
    # observed to write, not by what reads well when writing the list.
    "fine-tuned a model already",
    "finetuned a model already",
    "trained a model already",
)


#: Ways a person says they already hold the test the last number was measured
#: on. A CLOSED LIST, for the same reason as the two above it.
#:
#: FOUND ON THE IMPROVE WALK. "My adapter scored 0.62 on my eval set and I want
#: the next one to score higher. I still have the eval set and the baseline run"
#: maps to `make_an_eval`, whose FIRST step is `carve_eval_set`. The route
#: begins by building the thing they just said they have - and a newly carved
#: eval set is not the one 0.62 was measured on, so the next number would not
#: be comparable to the number they want to beat. Nothing said so.
ALREADY_HAVE_THE_EVAL: tuple[str, ...] = (
    "still have the eval",
    "have the eval set",
    "have an eval set",
    "my eval set",
    "already have an eval",
    "have its eval",
    "same eval set",
    "keep the eval",
    "have the baseline",
    "still have the baseline",
)


def _says_they_have_the_eval_set(ask: str) -> str | None:
    """The phrase saying the test already exists, or None."""
    flat = ask.lower().replace("’", "").replace("'", "")
    for phrase in ALREADY_HAVE_THE_EVAL:
        if phrase in flat:
            return phrase
    return None


#: Why building a second eval set quietly destroys the comparison. This is the
#: product's own rule read back to the person: `score_the_adapter` reuses the
#: baseline run's graded rows, its eval file, its columns and its metric
#: unchanged, "that is what makes the comparison a comparison". A number
#: measured on different rows is not higher or lower than the old one; it is
#: about a different question.
THE_NUMBER_TO_BEAT_IS_TIED_TO_ITS_EVAL_SET = (
    "Keep the eval set and the baseline run you already have. A score is only "
    "higher or lower than another score when both were measured on the same "
    "rows: score_the_adapter reuses the baseline run's graded rows, eval file, "
    "columns and metric unchanged, which is what makes it a comparison rather "
    "than two numbers. Carving a fresh eval set here would produce a number "
    "that cannot be compared with the one you are trying to beat, and nothing "
    "later would be able to tell the two apart."
)


def _says_it_is_already_trained(ask: str) -> str | None:
    """The phrase saying the training is done, or None."""
    flat = ask.lower().replace("’", "").replace("'", "")
    for phrase in ALREADY_TRAINED:
        if phrase in flat:
            return phrase
    return None


def _what_scoring_needs() -> str:
    """What has to exist before "is it any good" has an answer.

    The eval-set threshold is READ FROM THE LEDGER rather than typed here. The
    number is 30 today and it is the ledger's to change; a sentence that
    hardcoded it would go quietly wrong the day it moved, which is the mistake
    the no-verdict card nearly shipped with "0 of 5 gates".
    """
    try:
        from app import diagnosis

        rule = str(diagnosis.load_spec().gate_row("G0_EVAL_SET", "any").get("requires") or "")
    except Exception:  # pragma: no cover - a ledger that will not load
        rule = ""
    threshold = f" ({rule})" if rule else ""
    return (
        "Scoring an adapter is a comparison, so it needs two things that do not "
        "exist yet in this conversation. First an eval set the model never "
        f"studied for, big enough to satisfy G0_EVAL_SET{threshold} - that is "
        "the denominator every later number is quoted over, and make_an_eval is "
        "the journey that builds it. Then a baseline: the same rows scored "
        "without the adapter, which becomes the run id to beat. With both, "
        "score_the_adapter takes your adapter_dir directly and grades it on the "
        "baseline's own rows, so the two numbers are about the same questions."
    )


def _says_there_is_no_material(ask: str) -> str | None:
    """The phrase the person used to say they have nothing, or None.

    Apostrophes are dropped before matching so "don't" and "dont" are one case.
    The matched phrase is returned rather than a boolean, so the answer can
    quote the person back to themselves instead of asserting something about
    them.
    """
    flat = ask.lower().replace("’", "").replace("'", "")
    for phrase in NO_MATERIAL_YET:
        if phrase in flat:
            return phrase
    return None


#: What to do about it, in the product's own doctrine rather than a new opinion.
#: This is the sentence BLOCKED__DEFINE_SUCCESS_FIRST already gives, kept
#: consistent on purpose: two different first instructions for one situation
#: would be the product disagreeing with itself.
WHAT_MAKES_IT_PASSABLE = (
    "Write about 20 to 30 examples: an input you would really send, and the "
    "output you wanted back. That is the material this route needs AND the "
    "definition of good that G0_EVAL_SET asks for, so it is one piece of work "
    "rather than two. The make_an_eval journey is the one that builds it."
)

#: Said out loud because the route itself contains a step that looks like a way
#: out of having no data, and is not one. `synthesize_rows` resamples the
#: STRUCTURE of rows that already exist and copies their answers verbatim; with
#: nothing to sample it produces nothing. A person reading "data generation:
#: amplify the training half" in a route they were just handed can reasonably
#: think the harness will make the first examples for them, and the one moment
#: not to leave that open is the moment they have said they have none.
SYNTHESIS_IS_NOT_A_FIRST_DATASET = (
    "The synthesize_rows step later in this route does not help here: it "
    "resamples the shape of rows you already have and copies their answers "
    "word for word, so with nothing to sample it produces nothing. The first "
    "examples have to be real, and they have to be yours."
)


@tool(
    name="map_the_ask",
    description=(
        "Turn a person's sentence into the journey that serves it: keyword-"
        "match against the curated playbook and return the ordered steps, each "
        "naming a registered tool, why it runs, and what goes in it. This "
        "exists so a small conductor model does not need ML methodology in its "
        "weights - the map carries it, and the model's job shrinks to relaying "
        "steps and asking the person for the blanks."
    ),
    schema={
        "type": "object",
        "properties": {
            "ask": {"type": "string",
                    "description": "The person's own words for what they want."},
        },
        "required": ["ask"],
    },
    reads=("knowledge",),
    writes=(),
    measures=(),
    approval="never",
    provides=("context.ask.map",),
    label="Map the ask",
    group="Context",
    verb="map what you asked to the journey that serves it",
    order=4,
)
def map_the_ask(ask: str) -> dict[str, Any]:
    book = load("playbook.json")
    if not book.get("ok"):
        return book
    scored = _score_journeys(book, ask)
    if not scored:
        names = [j["name"] for j in book.get("journeys", [])]
        answer = {
            "ok": True,
            "matched": None,
            "summary": (
                "No journey in the playbook matches those words. The journeys "
                f"that exist: {', '.join(names)}. Say more about what you have "
                "and what you want, or run run_diagnosis and follow its cards."
            ),
            "journeys_available": names,
        }
        # WHAT WAS HEARD SURVIVES A ROUTE THAT DID NOT MATCH.
        #
        # Measured on the closed-list walk: "My adapter is done. What now?"
        # matched `my adapter` and matched no journey, and the answer was "no
        # journey matches those words" - throwing away the one fact the person
        # had given. Somebody who says they have a trained adapter and is told
        # nothing was understood will not say it again.
        heard = {
            "you_said_it_is_already_trained": _says_it_is_already_trained(ask),
            "you_said_you_have_no_material": _says_there_is_no_material(ask),
            "you_said_you_have_the_eval_set": _says_they_have_the_eval_set(ask),
        }
        heard = {key: value for key, value in heard.items() if value}
        if heard:
            answer.update(heard)
            answer["what_was_understood"] = (
                "No route matched, but this much was: "
                + "; ".join(f"you said {value!r}" for value in heard.values())
                + ". Say what you want to happen next and the route follows from that."
            )
            answer["summary"] = answer["what_was_understood"]
        return answer
    scored.sort(key=lambda t: -t[0])
    top_score, hits, best = scored[0]
    # A TIE IS NOT A CHOICE, AND THE READER SHOULD SEE IT.
    #
    # Measured over 28 asks from this repository's own corpora: exactly one
    # produced a tie, and `sort` broke it by declaration order - which is not a
    # fact about the sentence. Rather than invent a tiebreak (longer keyword?
    # earlier journey? each defensible and none measured), the answer names the
    # journeys that scored the same. Picking silently is the part that was
    # wrong; picking is fine as long as the runner-up is on the record.
    also = [j["name"] for score, _, j in scored[1:] if score == top_score]
    answer = {
        "ok": True,
        "matched": best["name"],
        "matched_on": hits,
        "says": best["says"],
        "steps": best["steps"],
        "law": (
            "Steps are the canonical order, not a script to run blind: tools "
            "that write need the person's approval, state_facts carries THEIR "
            "words, and the diagnosis cards outrank this map wherever the two "
            "disagree."
        ),
        "summary": (
            f"Matched '{best['name']}' on {hits}. {len(best['steps'])} steps, "
            "each naming the registered tool and its arguments."
        ),
    }
    if also:
        answer["also_matched"] = also
        answer["the_match_was_not_clear_cut"] = (
            f"{', '.join([best['name']] + also)} each matched the same number of "
            "words in that sentence. This one was taken because it is declared "
            "first, which is not a fact about what you asked - say more about "
            "what you have and what you want if it is the wrong one."
        )
    trains = any(
        step.get("tool") in {"run_in_sandbox", "synthesize_rows"}
        for step in best.get("steps", [])
    )
    said_done = _says_it_is_already_trained(ask)
    if said_done is not None and trains:
        # They are holding the thing this route ends by making. The route is
        # still their goal - "is it any good" is a question about a trained
        # model - but the answer starts near the end of it, not at step one.
        answer["you_said_it_is_already_trained"] = said_done
        answer["you_may_not_need_the_early_steps"] = (
            f"You said {said_done!r}. This route builds an adapter and this one "
            "already exists, so the steps that carve and train are not where "
            "this starts. What is missing is what would let anyone say whether "
            "it is any good."
        )
        answer["what_scoring_needs"] = _what_scoring_needs()

    said_has_eval = _says_they_have_the_eval_set(ask)
    if said_has_eval is not None and any(
        step.get("tool") == "carve_eval_set" for step in best.get("steps", [])
    ):
        # They are holding the test this route starts by building, and the
        # danger is not wasted work - it is a second eval set that silently
        # makes the next number incomparable with the one they quoted.
        answer["you_said_you_have_the_eval_set"] = said_has_eval
        answer["do_not_carve_a_second_eval_set"] = (
            f"You said {said_has_eval!r}. This route begins by carving one, and "
            "that step is not where this starts."
        )
        answer["the_number_to_beat_is_tied_to_its_eval_set"] = (
            THE_NUMBER_TO_BEAT_IS_TIED_TO_ITS_EVAL_SET
        )

    said_none = _says_there_is_no_material(ask)
    if said_none is not None:
        # The route still stands - it IS what they asked for - and saying it
        # cannot start is not the same as choosing a different goal for them.
        # Nothing here invents a dataset or offers a proxy for one.
        answer["you_said_you_have_no_material"] = said_none
        answer["route_cannot_start_yet"] = (
            f"You said {said_none!r}. This route begins by pointing at material "
            "that already exists, so it cannot start yet, and nothing here will "
            "stand in for material you do not have."
        )
        answer["what_makes_it_passable"] = WHAT_MAKES_IT_PASSABLE
        if any(step.get("tool") == "synthesize_rows" for step in best.get("steps", [])):
            answer["synthesis_is_not_a_first_dataset"] = SYNTHESIS_IS_NOT_A_FIRST_DATASET
        answer["summary"] = (
            f"Matched {best['name']!r} on {hits}, and it cannot start yet: you "
            f"said {said_none!r}. {WHAT_MAKES_IT_PASSABLE}"
        )
    return answer


@tool(
    name="read_local_recipes",
    description=(
        "How people actually RUN models like yours locally: validated, "
        "launch-measured serving recipes from 0xSero's Local AI Registry - "
        "model, quantization, engine, launchable-or-not - snapshotted with a "
        "date. The registry practices this product's own law: every field "
        "there carries provenance, and an unobserved fact says unknown."
    ),
    schema={"type": "object", "properties": {}},
    reads=("knowledge",),
    writes=(),
    measures=(),
    approval="never",
    provides=("knowledge.local.recipes",),
    label="Read local serving recipes",
    group="Choose",
    verb="read how models like this are actually run",
    order=28,
)
def read_local_recipes() -> dict[str, Any]:
    answer = load("local_recipes.json")
    if answer.get("ok"):
        answer["summary"] = (
            f"{len(answer.get('recipes', []))} validated local-serving recipes, "
            + answer["staleness"]
        )
    return answer
