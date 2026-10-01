"""What a thread in each mode is handed, and what it is for.

Max asked for this by name and described both halves: *"planning is discussion
with an ML expert who has a library of knowledge on the harness to help him.
Action or building full access mode is when the plan is built, the model
follows the plan, sets that as a goal function and executes on it rigorously
until it fulfils in full and finishes the actual plan everyone created."*

## What PLAN is handed, and why it is a list

Max, looking at the tool roster: *"it can view a file, it can view your
hardware, it can ask a question... it doesn't need to create sandboxes...
record stuff, read a file, list certain things you can look at. Listing runs,
read prices, read sandboxes."*

So planning gets **lookups and nothing else** - enough to have an informed
conversation, nothing that acts on the machine. The first cut of this file
handed planning NO tools at all, which fixed the loop it was written for and
made the consultation blind: a model that cannot read the repository cannot
help you choose what to do with it.

## Why a named list and not `writes == ()`

The same reason `app/autonomy.py` gives, and it bites here too. Twenty-nine
tools write nothing, and `fit_a_tree_model` is one of them - it writes no
file and it trains a model. `run_diagnosis` writes nothing and is the tool
whose only possible answer, in a thread with nothing measured, is the blocked
verdict the standing brief already carries. A derivation would admit both.

**`run_diagnosis` is deliberately NOT in planning.** Its answer is already on
every prompt in about 165 tokens (`conductor.standing_brief`), and offering a
tool that re-reads the prompt is what produced the turn this whole feature
exists because of: eight rounds, no answer.

Two tools here write a cache (`model_config_cache`) and are on the list
anyway: fetching a model's config in order to talk about it is a lookup, and
the cache is the lookup remembering what it read.

## What BUILD is

Exactly what the product did before this file existed: tools scoped per turn by
the standing diagnosis, approvals where the registry asks for them, autonomy
only if the person turned it on. **A mode does not widen anything.** `build` is
not "full access" in the sense of bypassing a gate - every approval, every
refusal and every whitelist behaves identically. What changes is that the plan
the person accepted is carried into the brief as the thing being executed.

## The one rule that makes the pair mean something

**A mode is set by a person, never by a model and never by a heuristic.** There
is no code path that reads the question and picks. Matching on the question is
the road `conductor.standing_brief` rejected twice, and the reason is in its
docstring: the four phrasings Max used are the standing proof of why.
"""

from __future__ import annotations

#: The two modes, and what a person is choosing between when they switch.
MODES: dict[str, str] = {
    "plan": (
        "Consultation. Lookups only - it can read your machine, your "
        "repository, your rows, what has already been run and what models "
        "exist. It cannot measure, train, carve or write, so the answer has "
        "to be an answer. The output is a phased plan you press Build on."
    ),
    "build": (
        "Execution. Tools are offered exactly as before - scoped per turn, "
        "gated where the registry gates them - and the plan you accepted is "
        "carried into every turn as the thing being worked through."
    ),
}

#: The tools a planning turn is handed. Lookups only: every one of these
#: answers a question about what already exists, and none of them changes
#: the machine, the data or the ledger.
PLAN_TOOLS: dict[str, str] = {
    "inspect_hardware": "what this machine is",
    "can_this_machine_train": "whether a model would fit on it, as a reading",
    "where_to_train": "the options, given the card",
    "read_gpu_prices": "what renting would cost",
    "list_local_models": "what is already downloaded here",
    "find_models": "models that exist elsewhere - the cache it writes is the lookup remembering what it read",
    "read_model_config": "one model's shape - same cache, same reason",
    "read_model_shortlist": "what has already been shortlisted",
    "profile_repository": "read a codebase and describe it",
    "preview_dataset_rows": "look at the actual rows",
    "check_split_leakage": "whether two files overlap",
    "list_context": "what is attached to this project",
    "read_context_file": "read one of them",
    "search_the_index": "find something in what is attached",
    "list_runs": "what has been run",
    "read_eval_results": "how a run scored",
    "read_agent_results": "how an agent run went",
    "read_prompt_bench": "what prompt attempts scored",
    "list_sandboxes": "what sandboxes exist",
    "list_recipes": "what a recipe can do",
    "read_local_recipes": "the recipes on this machine",
    "read_the_standing_constraints": "what has been ruled out and why",
    "map_the_ask": "the playbook steps for a kind of ask",
    "recall": "what earlier conversations in this project already settled",
    "remember": "save a durable fact - a decision, a ruled-out option - for every later thread",
    #: THE MOVE. Everything above answers a question about the world; this
    #: produces the thing the mode is for. Without it a model that acts
    #: through tools kept choosing the next lookup and went silent when the
    #: budget ran out - thread 64, twice, 2026-09-11. See app/tools/planning.py.
    "write_plan": "save the phased plan - this is how a plan is delivered",
    "compile_the_plan": "write the journey out as the plan, phases and tool-call steps filled in",
    "read_plan": "read the saved plan, to revise it rather than start over",
    "read_observation": "read a packed tool result back in full - a lookup, of what this conversation already holds",
    #: THE DIAGNOSIS MACHINERY IS NOT HERE, AND THAT IS MEASURED. Three arms
    #: on the owner's own question through his own model, 2026-09-11:
    #:
    #:   lookups only (no move)          - empty_reply, twice, in the live thread
    #:   lookups + write_plan + the core - 0 of 3 wrote a plan, mean 169 s;
    #:                                     every turn reached for the diagnosis
    #:   lookups + write_plan, no core   - 0 of 3 SAVED a plan, mean 77 s - but
    #:                                     one turn WROTE a six-phase plan in
    #:                                     28 s, as prose, and a gate-reader
    #:                                     false catch withheld it whole
    #:
    #: So the core stays out of planning: with it on offer a small model spends
    #: every round reaching for `run_diagnosis` and narrates a BLOCKED verdict
    #: instead of planning, which is the eight-round loop this feature exists
    #: because of. The verdict is on every prompt anyway (`standing_brief`).
    #: What planning needs is the move, and the prose it writes when it takes
    #: no move is captured as the plan by the conductor - see `run_turn`.
    #:
    #: `test_a_constant_is_not_a_record` still holds the core on every BUILD
    #: turn, which is where the withdrawal was measured to silence the model.
}

#: THE MODE A PERSON'S NEW CONVERSATION OPENS IN, applied at the one door a
#: person opens one through: `POST /api/threads`. Named for the door rather
#: than called a default, because it is not one and must not become one.
#:
#: `events.create_thread` is a storage primitive with forty-four callers in
#: the test suite and one in the product. Making IT open threads in `plan`
#: took the tools away from every fixture that builds a thread and then
#: exercises a turn - four assertions in the tool-scoping tests failed with
#: the plan lookups listed where the scoped set was expected, and those
#: tests are about the diagnosis scoping, not about modes. So the primitive
#: keeps giving what it has always given and the product asks for planning
#: explicitly, in the route that a person's click reaches.
#:
#: `test_a_thread_plans_before_it_builds` asserts the BEHAVIOUR through that
#: route rather than the value of this name; a constant is not a record.
WHEN_A_PERSON_OPENS_A_CONVERSATION = "plan"

#: THE PLAN TOOLS ARE LEDGER TOOLS, and so they are offered wherever the
#: ledger pack is - build included. A first cut withheld them in build; the
#: standing brief names every tool in an active pack with its verb, so that
#: would have had the brief describing a tool the turn did not offer, which
#: is the recital fault `standing_brief` documents. And the registry refuses
#: a tool with no capability at all - a tool in no block reaches no model.
#: Two real tools joining the core moves the measured prompt budget by
#: their measured size, which is the protocol those constants record.


def is_a_mode(value: object) -> bool:
    """True for exactly the two names above. Nothing is coerced."""
    return isinstance(value, str) and value in MODES


def normalise(value: object) -> str:
    """The mode a row means, for a column that predates this feature.

    A row written before v016 has no opinion; it reads `build`, which is what
    it was doing. Anything unrecognised reads `build` too rather than raising -
    a thread whose mode column got a typo should still answer, and the control
    will show the person which mode it is in.
    """
    return value if is_a_mode(value) else "build"


def offers_tools(mode: object) -> bool:
    """Whether a turn in this mode is handed a tool list at all.

    True in both modes now. Kept because it reads at the call site and
    because a future mode may genuinely have none; `tools_for` is what
    decides WHICH.
    """
    return bool(PLAN_TOOLS) or normalise(mode) != "plan"


def tools_for(mode: object, available: object) -> frozenset[str]:
    """The names this mode may offer, intersected with what exists.

    `build` returns `available` untouched - the per-turn scoping the
    standing diagnosis already does, unchanged. A mode widens nothing.

    `plan` returns the lookups above, and deliberately NOT the intersection
    with the diagnosis's scoping: a consultation should be able to read the
    repository whatever gate the ledger is sitting at. The intersection that
    IS applied is with the registry, so a name removed from the roster stops
    being offered here on the same day rather than raising later.
    """
    names = frozenset(str(n) for n in available)
    if normalise(mode) != "plan":
        return names
    return frozenset(PLAN_TOOLS)
