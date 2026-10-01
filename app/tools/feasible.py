"""The CAN questions, answered without the gates.

## The defect this module exists to close

Max ran the product against his own business - an insurance book, roughly a
thousand support tickets, cloud models forbidden by compliance - and asked it
seven questions. He got the same answer to all seven:
`BLOCKED__DEFINE_SUCCESS_FIRST`. Every one of them.

Only one of the seven was a question the five gates are about:

    1. Can I train on this machine at all?      hardware + model geometry
    2. Local, rented VM, or data centre?        hardware + model + constraints
    3. Is it worth training?                    THE FIVE GATES. correctly gated.
    4. What would it cost?                      hardware + model + timings
    5. What is the best data - have or get?     the data, profiled
    6. Training environment - build and deploy? the sandbox, which exists
    7. Which model should I use?                hardware + task + catalogue

Number 3 is the gates' question and it was answered correctly. The other six
need a measurement the harness had already taken, and they were refused because
the diagnosis tree was the only path and it stops two nodes in.

**The gate was scoped to the wrong verb.** It exists to stop us RECOMMENDING
TRAINING without evidence - without an eval set, a measured baseline, prompting
exhausted, retrieval considered, a cheaper model considered. Not one of those
five is an input to the question "does a 7B model fit in 8 GB". That question is
decided by the card's memory and the model's `config.json` and by nothing else,
and refusing it is not honesty. It is a gate answering a question it was not
asked.

## The line this module does not cross, and how it is held

Feasibility says CAN. The gates say SHOULD. An adversary reading the paragraph
above will try to make the first into a route to the second, so the separation
is structural rather than stated:

1. **These tools measure nothing.** Both declare `measures=()`, so the
   instrument the registry hands them can stamp no fact at all. A fact that
   cannot be stamped cannot open a gate. This is the same wall `run_diagnosis`
   stands behind and it is the one that matters.

2. **These tools decide nothing.** `writes=()`. Nothing they return is
   persisted, so calling one forty times accumulates no authority.

3. **The word `verdict` does not appear in what they return, and neither does
   any outcome id.** The diagnosis engine owns those words. A feasibility answer
   that borrowed one would be a rename away from looking like a decision, and
   `AGENTS.md` invariant 4 names exactly that move as forbidden.
   `tests/test_a_can_question_is_not_a_train_recommendation.py` derives the
   forbidden vocabulary from `docs/diagnosis_engine.yaml` rather than listing
   it, so a training outcome added next year is covered on the day it is added.

4. **Every answer says so in its own payload.** `this_is_not_a_recommendation`
   is a field, not a docstring, because the thing that reads these answers is a
   language model and the field is what it sees.

## What each tool answers, in Max's words

*"can we train - yes or no"* -> `can_this_machine_train`. A YES, a NO or an
UNKNOWN, with the seven-term sum that produced it and where each term came
from. UNKNOWN is not a hedge: it is what comes back when the model's geometry
has never been read, and it names the tool that would read it.

*"where should we train - local, vm, data center"* -> `where_to_train`. Decided
from the same arithmetic plus the compliance constraint, which is a declared
fact of the ledger and not a footnote. Somebody who may not send data to a
hosted model does not have a rented-VM option, and quoting them an hourly price
is worse than saying nothing.

*"how much could this cost - est"* -> the `cost` block of the same answer, and
the honest half of it is that the hours are UNKNOWN. Nothing in this harness
records how long a training step takes, so there is no measurement to derive
one from. `docs/THE_PROPOSAL_LOOP.md` already specifies the shape: *"I do not
know how long this takes, let me run it on 1% and find out."*

*"which models do we use - the following is best"* -> `find_models`, which
already works and is not touched here.
"""

from __future__ import annotations

from typing import Any

from app import feasibility
from app.tools import evidence, models
from app.tools.evidence import Instrument
from app.tools.registry import tool


#: What a caller gets when it names no sequence length. The same default
#: `find_models` uses, and for the same reason: this one number sets the
#: activation and logits terms, which between them are most of what moves, so an
#: answer budgeted against a default must say that it was.
DEFAULT_SEQ_LEN = models.DEFAULT_SEQ_LEN

TRAINING_METHODS = ("qlora", "lora", "full")


def _geometry_and_params(
    repo_id: str,
) -> tuple[feasibility.ModelGeometry | None, float | None, str | None]:
    """This model's real shape, read from its stored `config.json`, or nothing.

    Offline by construction - `feasibility.load_model_config` never fetches. A
    model whose config has not been read comes back as three `None`s and the
    answer is UNKNOWN, which is the fourth verdict doing its job.
    """
    geometry = feasibility.geometry_for(repo_id)
    params_b, params_source = feasibility.parameters_b_for(repo_id)
    return geometry, params_b, params_source


def _unknown_geometry_help(repo_id: str) -> dict[str, Any]:
    return {
        "missing": "geometry",
        "next_step": {
            "tool": "read_model_config",
            "arguments": {"repo_id": repo_id},
            "verb": "read this model's real config.json",
            "why": (
                f"the layers, heads and vocabulary of {repo_id} have never been "
                "read on this machine, and the activation and logits terms are "
                "computed from them. Borrowing another model's shape is the "
                "defect this estimator was rewritten to remove, so it answers "
                "UNKNOWN instead."
            ),
        },
    }


@tool(
    "can_this_machine_train",
    description=(
        "Answer YES or NO: can this machine train this model, at this method "
        "and this example length. Computed from the VRAM measured off this card "
        "and the layers, heads and vocabulary in the model's own config.json, "
        "and returned with every term of the sum and where it came from. This "
        "is a question about memory, not about whether training is a good idea "
        "- it consults no gate, opens none, and is not a recommendation to "
        "train. When the model's config has never been read the answer is "
        "UNKNOWN and it names the tool that would read it. A NO also carries "
        "the longest example length that WOULD fit, so the answer is actionable "
        "rather than only correct."
    ),
    schema={
        "type": "object",
        "properties": {
            "repo_id": {
                "type": "string",
                "description": "Hugging Face repo, e.g. 'Qwen/Qwen3-8B'.",
            },
            "method": {
                "type": "string",
                "description": (
                    "How it would be trained. QLoRA holds the base model at "
                    "about half a byte per parameter, LoRA at two, full at two "
                    "with gradients and optimizer state over every parameter."
                ),
                "enum": list(TRAINING_METHODS),
            },
            "seq_len": {
                "type": "integer",
                "description": (
                    "Tokens per training example. This one number drives the "
                    "activation and logits terms, which are most of what moves, "
                    "so measure the user's own data with profile_dataset and "
                    "pass what you measured. Left out, the answer is labelled "
                    "as budgeted against a default."
                ),
            },
            "batch": {
                "type": "integer",
                "description": "Examples per step. Default 1.",
            },
            "vram_gb": {
                "type": "number",
                "description": (
                    "Override the detected VRAM, for answering about a machine "
                    "that is not this one. Leave it out to use the measured "
                    "value from this card."
                ),
            },
        },
        "required": ["repo_id"],
    },
    reads=("hardware", "model_config_cache"),
    writes=(),
    measures=(),
    provides=("training.feasibility.check",),
    label="Can this machine train it",
    group="Look",
    verb="say yes or no whether a model fits this card",
    order=11,
)
def can_this_machine_train(
    repo_id: str,
    method: str = "qlora",
    seq_len: int | None = None,
    batch: int = 1,
    vram_gb: float | None = None,
) -> dict[str, Any]:
    """Yes or no, from a measured card and a real config. No gate is consulted."""
    if not isinstance(repo_id, str) or not repo_id.strip():
        return {
            "ok": False,
            "error": "no_repo_id",
            "detail": "repo_id is required - which model are we asking about?",
        }
    repo = repo_id.strip()

    normalized = str(method or "qlora").lower().replace("-", "").replace("_", "")
    if normalized not in TRAINING_METHODS:
        return {
            "ok": False,
            "error": "unknown_method",
            "detail": f"{method!r} is not a training method this harness sizes",
            "known_methods": list(TRAINING_METHODS),
        }

    if seq_len is None:
        length, length_source = DEFAULT_SEQ_LEN, "defaulted"
    else:
        try:
            length, length_source = max(64, min(int(seq_len), 131072)), "declared"
        except (TypeError, ValueError):
            length, length_source = DEFAULT_SEQ_LEN, "defaulted"
    try:
        examples = max(1, min(int(batch), 512))
    except (TypeError, ValueError):
        examples = 1

    if vram_gb is None:
        card = models._vram_field()
    else:
        try:
            card = feasibility.Field(float(vram_gb), "declared", "supplied by the caller")
        except (TypeError, ValueError):
            card = models._vram_field()

    geometry, params_b, params_source = _geometry_and_params(repo)
    answer = feasibility.can_train(
        vram=card,
        params_b=params_b,
        geometry=geometry,
        repo_id=repo,
        method=normalized,
        seq_len=length,
        batch=examples,
        params_source=params_source,
    )
    answer["ok"] = True
    answer["seq_len_provenance"] = length_source
    if length_source == "defaulted":
        answer["seq_len_note"] = (
            f"Budgeted against {DEFAULT_SEQ_LEN} tokens per example because "
            "nobody said how long the real examples are. Support tickets, chat "
            "turns and product descriptions are usually far shorter than that, "
            "and the answer moves with it - measure the data with "
            "profile_dataset and ask again."
        )
    if answer["answer"] == "UNKNOWN" and geometry is None:
        answer.update(_unknown_geometry_help(repo))
    answer["gates_consulted"] = []
    answer["why_no_gates"] = (
        "None. The five gates decide whether training is WORTH doing and they "
        "read an eval set, a baseline, prompt work, retrieval work and a model "
        "swap. Not one of those is an input to this sum, which is VRAM against "
        "the model's own geometry. Answering this does not open a gate and "
        "cannot: this tool declares measures=(), so it can stamp no fact at all."
    )
    return answer


@tool(
    "where_to_train",
    description=(
        "Answer where a training run should happen: LOCAL on this machine, on a "
        "RENTED_VM by the hour, or on OWN_HARDWARE you buy and control. Decided "
        "from the same memory arithmetic as can_this_machine_train plus the "
        "compliance constraint recorded in this conversation - a user who may "
        "not send data to a third-party host has no rented-VM option, and this "
        "tool will not quote them a price for one. Rental prices are indicative "
        "and dated, never measured, and the answer says so. The hours a run "
        "takes are UNKNOWN because nothing in this harness has ever timed one, "
        "so no total is computed; the answer names the 1% run that would "
        "measure it instead. This is not a recommendation to train."
    ),
    schema={
        "type": "object",
        "properties": {
            "repo_id": {
                "type": "string",
                "description": "Hugging Face repo, e.g. 'Qwen/Qwen3-8B'.",
            },
            "method": {
                "type": "string",
                "description": "How it would be trained.",
                "enum": list(TRAINING_METHODS),
            },
            "seq_len": {
                "type": "integer",
                "description": "Tokens per training example. See can_this_machine_train.",
            },
            "batch": {
                "type": "integer",
                "description": "Examples per step. Default 1.",
            },
            "privacy": {
                "type": "string",
                "description": (
                    "Where this data is allowed to go. If the user has already "
                    "said, it is read from this conversation and you do not need "
                    "to repeat it. 'on_prem_only' and 'regulated' rule out every "
                    "hosted option."
                ),
                "enum": ["public_ok", "no_third_party_api", "on_prem_only", "regulated"],
            },
            "can_rent_cloud": {
                "type": "boolean",
                "description": (
                    "Whether renting a GPU by the hour is available to this "
                    "user at all. Read from this conversation when they have "
                    "said."
                ),
            },
            "vram_gb": {
                "type": "number",
                "description": (
                    "Override the detected VRAM, for answering about a machine "
                    "that is not this one. Leave it out to use the measured "
                    "value from this card."
                ),
            },
        },
        "required": ["repo_id"],
    },
    reads=("hardware", "model_config_cache", "facts"),
    writes=(),
    measures=(),
    provides=("training.placement.choose",),
    label="Where should this train",
    group="Look",
    verb="say whether to train local, rented or owned",
    order=12,
)
def where_to_train(
    repo_id: str,
    method: str = "qlora",
    seq_len: int | None = None,
    batch: int = 1,
    privacy: str | None = None,
    can_rent_cloud: bool | None = None,
    vram_gb: float | None = None,
    *,
    instrument: Instrument,
) -> dict[str, Any]:
    """Local, rented, or your own iron - from the machine, the job and the constraint.

    The constraint is read from the conversation's own fact ledger rather than
    only from the arguments, so a compliance answer the user gave three turns
    ago still decides this one. What the caller supplies is merged in at the
    origin the caller is worth - a model's is ASSERTED - and the origin is
    reported beside the answer, because "you told me you are regulated" and "the
    model assumed you are regulated" are different claims about the same word.
    """
    here = can_this_machine_train(
        repo_id=repo_id,
        method=method,
        seq_len=seq_len,
        batch=batch,
        vram_gb=vram_gb,
    )
    if not here.get("ok"):
        return here

    supplied: dict[str, Any] = {}
    if privacy is not None:
        supplied["privacy"] = privacy
    if can_rent_cloud is not None:
        supplied["can_rent_cloud"] = can_rent_cloud

    origins: dict[str, str] = {}
    try:
        sheet, _trail = evidence.assemble_facts(
            instrument.thread_id, supplied, instrument.actor
        )
        privacy_value = sheet["privacy"].value if "privacy" in sheet else None
        rent_value = sheet["can_rent_cloud"].value if "can_rent_cloud" in sheet else None
        for name in ("privacy", "can_rent_cloud"):
            if name in sheet:
                origins[name] = sheet[name].origin
    except Exception:  # noqa: BLE001 - a ledger read must never lose the answer
        # THE ANSWER SURVIVES A LEDGER IT CANNOT READ, and falls back to what
        # the caller said rather than to silence. A `privacy` the model guessed
        # is a weak input and it is reported as one; losing the whole placement
        # answer because a database was busy would be worse.
        privacy_value = privacy
        rent_value = can_rent_cloud
        origins = {k: "ASSERTED" for k in supplied}

    answer = feasibility.where_to_train(
        here, privacy=privacy_value, can_rent_cloud=rent_value
    )
    answer["ok"] = True
    answer["repo_id"] = here.get("repo_id")
    answer["method"] = here.get("method")
    answer["seq_len"] = here.get("seq_len")
    answer["constraint_origins"] = origins
    answer["can_this_machine_train"] = {
        "answer": here.get("answer"),
        "because": here.get("because"),
        "needed_gb": here.get("needed_gb"),
        "vram_gb": here.get("vram_gb"),
        "arithmetic": here.get("arithmetic"),
        "longest_example_that_fits": here.get("longest_example_that_fits"),
    }
    if privacy_value is None:
        answer["what_would_sharpen_this"] = {
            "fact": "privacy",
            "tool": "state_facts",
            "run_as": evidence.USER,
            "why": (
                "Nobody has said where this data is allowed to go, so this "
                "answer assumes renting is available. For a business under a "
                "compliance regime that assumption is the whole answer and it is "
                "wrong. It is the user's own fact to state, not a model's to "
                "guess."
            ),
        }
    answer["gates_consulted"] = []
    return answer


@tool(
    "record_that_this_card_refuses",
    description=(
        "Ask whether this machine can train a model and, ONLY IF THE ANSWER IS "
        "NO, record that refusal on this conversation so the diagnosis can stop "
        "recommending a run that cannot happen. A YES records nothing at all: "
        "this tool closes a route and never opens one. The refusal it records "
        "carries the margin and the longest example length that would fit, "
        "because NO by six hundredths of a gigabyte and NO by three are "
        "different answers wearing one word."
    ),
    schema={
        "type": "object",
        "properties": {
            "repo_id": {"type": "string", "description": "Hugging Face repo."},
            "method": {"type": "string", "enum": list(TRAINING_METHODS)},
            "seq_len": {"type": "integer", "description": "Tokens per example."},
            "batch": {"type": "integer", "description": "Examples per step."},
        },
        "required": ["repo_id"],
    },
    #: THE SAME READS AS THE TOOL IT ASKS, because it asks that tool and adds
    #: nothing of its own. `reads=("machine",)` stood here for a day and was a
    #: coined synonym: `app/build.py` classifies every read word as local or
    #: networked so an egress guarantee can be checked, and a word nobody has
    #: classified is a hole in that check rather than a description. `hardware`
    #: and `model_config_cache` are what `can_this_machine_train` declares.
    reads=("hardware", "model_config_cache"),
    writes=(),
    measures=("cannot_train_here", "training_headroom_gb", "longest_fitting_seq"),
    # WALL 6. Each bounds the QUESTION - which model, how trained, at what
    # length and batch - and none could be the answer to "does it fit" or "by
    # how much", which are computed from the model's geometry against the card.
    bounds=("repo_id", "method", "seq_len", "batch"),
    provides=("training.feasibility.record",),
    label="Record that the card refuses",
    group="Look",
    verb="record that this card cannot train it, and by how much",
    order=12,
)
def record_that_this_card_refuses(
    repo_id: str,
    method: str = "qlora",
    seq_len: int | None = None,
    batch: int = 1,
    *,
    instrument: Instrument,
) -> dict[str, Any]:
    """The closure half of the CAN question, and only the closure half.

    WHY THIS IS A SECOND TOOL AND NOT A FLAG ON THE FIRST. A tool whose
    `measures=` names a thread-scoped fact is REQUIRED to have a thread
    (`evidence.thread_is_required_by`). `can_this_machine_train` answers on an
    empty ledger with no conversation at all, and that is the defect its module
    was written to close - Max asked seven questions and was refused six of
    them for want of a precondition. Putting the stamp on it would put the
    precondition back. So the CAN tool keeps `measures=()` exactly as its
    docstring argues, and this one - which a walk calls, and a walk always has
    a thread - carries the closure.

    IT STAMPS NOTHING ON A YES. Not "can_train_here: true", not a headroom, not
    a sequence length. A fact recorded on a YES is a fact a planner can read as
    permission, and the separation this module defends is precisely that a CAN
    answer is not a SHOULD. On a YES the answer is returned and the ledger is
    untouched.
    """
    answer = can_this_machine_train(
        repo_id=repo_id, method=method, seq_len=seq_len, batch=batch
    )
    answer["recorded"] = []
    if answer.get("answer") != "NO":
        answer["why_nothing_was_recorded"] = (
            "Only a refusal is recorded. This answer is "
            f"{answer.get('answer')!r}, and a fact stamped on anything but a NO "
            "is a fact a planner could read as permission to train."
        )
        return answer

    needed = answer.get("needed_gb")
    card = answer.get("vram_gb")
    headroom = answer.get("headroom_gb")
    longest = answer.get("longest_example_that_fits")
    instrument.measured(
        "cannot_train_here",
        True,
        how=(
            f"{repo_id} at {answer.get('method')}, sequence "
            f"{answer.get('seq_len')}, needs {needed} GiB against {card} GiB "
            "measured off this card"
        ),
    )
    answer["recorded"].append("cannot_train_here")
    if headroom is not None:
        instrument.measured(
            "training_headroom_gb",
            float(headroom),
            how=f"{card} GiB on the card less {needed} GiB needed",
        )
        answer["recorded"].append("training_headroom_gb")
    if isinstance(longest, int):
        instrument.measured(
            "longest_fitting_seq",
            int(longest),
            how=(
                f"the longest example {repo_id} fits in {card} GiB at "
                f"{answer.get('method')}"
            ),
        )
        answer["recorded"].append("longest_fitting_seq")
    else:
        #: NOTHING FITS AT ANY LENGTH, WHICH IS A STRONGER REFUSAL AND MUST
        #: NOT ARRIVE AS A MISSING FIELD. `longest_fitting_seq` is absent here
        #: because the search found no length at all - the weights alone
        #: exceed the card - and a reader who saw two facts where three were
        #: promised would be left wondering which measurement failed.
        answer["no_length_fits"] = (
            f"No sequence length fits: {repo_id} exceeds this card before any "
            "example is loaded, so there is no shorter example to suggest. "
            "This is not a length to change; it is a smaller model or a "
            "bigger card."
        )
    return answer
