"""Fact sets for the diagnosis engine tests.

Each one is a consistent story about a real user, not a bag of values tuned
until a test went green. The comment above each says who the person is, because
a fixture nobody can describe in a sentence is a fixture nobody can tell is
wrong.

`MINTING` is keyed by the outcome each fact set must reach. The reachability
test does NOT read that keying as truth - it derives the list of outcomes that
must be covered from the YAML and then looks each one up here, so an outcome
with no fact set fails loudly instead of quietly not being checked.

THREE GROUPS, AND THEY COVER EVERY DECLARED OUTCOME BETWEEN THEM.

  MINTING   one fact set per TRAIN__ outcome, keyed by outcome.
  SPREAD    the no-train answers that carry a claim beyond the outcome id -
            which NODE answered, and what the failing half of a proposal does.
            Keyed by a label, because two of them reach the same outcome from
            different nodes and that difference is the thing being asserted.
  REACHING  one fact set for every remaining declared outcome, keyed by outcome.
            This group exists because the reachability test used to be scoped to
            TRAIN__ outcomes, and three NO_LLM__/REROUTE answers were killed by a
            widened condition with nothing to notice. A dead no-train outcome is
            a user the product cannot see, and the no-train answers ARE the
            product.

THERE WAS A FOURTH GROUP AND IT IS GONE, which is worth a paragraph rather than
a silent deletion. `CYCLING` held three fact sets that made the walk loop until
the cycle guard raised ERROR__CYCLE, and the suite ASSERTED the crash, because at
the time the crash was the truth and pretending otherwise would have been worse.
Three of the seven gate `on_fail` routes sent a failing run back into the stage
that had made the proposal, and that stage had no node answering the gate's own
question, so the same node proposed again. The stages carry those remedies now -
S7_QUANTIZATION_UNTRIED, S7_CACHING_UNTRIED, S8_TABULAR_DEEP_NEEDS_HPARAM_SEARCH,
S8_TABULAR_DEEP_NEEDS_FEATURE_WORK - so all three answer, and a group whose whole
definition was "these do not answer" has nothing left to hold. The fact sets did
not go anywhere: they are in SPREAD, under the same labels, asserting the answers
they now give instead of the exception they used to raise. The comment above them
says which gate each one fails and why the fix was an ordering change rather than
an addition. Keeping the story is the point - a reader who finds three fixtures
named `..._fails_g2` with no explanation cannot tell them from any other pair.

Nothing here lists the outcomes that must exist. That list is derived from the
YAML in tests/test_diagnosis_invariant.py; these three dicts are only where the
fact sets live. Add an outcome to the spec and the test fails until a fact set
for it appears in one of them.

THE FAILING HALVES ARE INDEXED, NOT COUNTED. RC5_FIXTURE_COVERAGE counts the
failing half PER PROPOSING NODE - one fact set for every node in the spec
carrying `propose:` - and it says in as many words that transcribing that list
is how two of them went missing. So no list of proposing nodes appears here
either. The cases that are a failing half carry `failing_half_of:` naming the
node they are the failing half OF, `failing_halves()` groups them by it, and
tests/test_diagnosis_fixtures.py derives the twelve nodes that owe one straight
out of the spec. A new proposing node therefore arrives as a failure with its
own id in the message, not as a number that quietly stopped matching.
"""

from __future__ import annotations

from typing import Any

from app.diagnosis import MEASURED, STATED, Fact, asserted, default_spec

# ---------------------------------------------------------------------------
# WHERE THESE FACTS CAME FROM, which is now half of what a fact is.
#
# A bare value is an ASSERTED value - see `fact_origins` in the spec - and an
# assertion opens no gate. So a fixture built out of bare values reaches
# ACTION__SUBSTANTIATE_CLAIMED_FACTS and nothing else, which is correct and
# useless: every story in this file would be the same story.
#
# So `_facts` attributes what it builds, and the attribution is one claim made
# once: THESE ARE RUNS WHERE THE HARNESS INSPECTED WHAT IT SAYS IT INSPECTS AND
# THE USER ANSWERED WHAT IT SAYS THEY ANSWER. A fact the ledger tags
# `source: inspect` is MEASURED here because the eval set was counted and the GPU
# was read; one tagged `source: ask` is STATED because the person typed it; one
# tagged `source: derive` is MEASURED because something computed it over data.
# That is not a licence the fixtures grant themselves - it is the ledger's own
# `source:` column, read rather than restated - and it is exactly the state of
# the world each fixture's comment already describes in a sentence.
#
# THE ADVERSARY CASE DOES THE OPPOSITE ON PURPOSE and lives in
# tests/test_fact_origins.py: it takes these same fact sets, changes no value,
# re-attributes every fact a gate reads as ASSERTED, and requires that no run
# reaches a TRAIN__ outcome. If the two ever agreed, one of them would be wrong.
_ORIGIN_FOR_SOURCE = {
    "inspect": MEASURED,
    "ask": STATED,
    "derive": MEASURED,
}


def attribute(values: dict[str, Any]) -> dict[str, Any]:
    """Stamp each value with the origin its ledger `source:` describes.

    Values already carrying a `Fact` are left alone, so a fixture can say
    something different about one fact - `asserted(...)` - without this undoing
    it. Keys that are not declared facts (the two helper booleans) pass through.
    """
    spec = default_spec()
    out: dict[str, Any] = {}
    for name, value in values.items():
        decl = spec.facts.get(name)
        if isinstance(value, Fact) or decl is None:
            out[name] = value
            continue
        source = decl["source"]
        if source not in _ORIGIN_FOR_SOURCE:
            raise AssertionError(
                f"fact {name!r} declares source {source!r}, which these fixtures "
                "have no story for. Decide what a run in which that fact was "
                "supplied actually looks like and add it to _ORIGIN_FOR_SOURCE - "
                "do not let it fall through to a bare value, because a bare value "
                "is an assertion and every fixture using this fact would quietly "
                "stop reaching its outcome."
            )
        out[name] = Fact(value, _ORIGIN_FOR_SOURCE[source])
    return out


# The facts every text-modality run needs before stage 0 will let it through.
_ADMISSIBLE: dict[str, Any] = {
    "modality": "text",
    "task_family": "generation",
    "eval_size_n": 100,
    "target_score": 0.85,
    "privacy": "public_ok",
    "needs_citations": False,
}

# A measured baseline that is short of the bar, plus a trivial baseline well
# below it so the "your labels are noise" node does not fire.
_MEASURED_AND_SHORT: dict[str, Any] = {
    "baseline_measured": True,
    "baseline_score": 0.55,
    "trivial_baseline_score": 0.20,
    "data_quality": 0.9,
}


def _facts(*parts: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for part in parts:
        merged.update(part)
    merged.update(overrides)
    return attribute(merged)


# ---------------------------------------------------------------------------
# One minting fact set per TRAIN__ outcome. Nine outcomes, nine stories.

MINTING: dict[str, dict[str, Any]] = {}

# A support team whose model gets the facts right and the tone wrong. Prompting,
# few-shot and a prompt optimiser have all been done and measured.
MINTING["TRAIN__LORA_SFT"] = _facts(
    _ADMISSIBLE,
    _MEASURED_AND_SHORT,
    failure_histogram={"wrong_style": 30},
    prompt_iterations=5,
    fewshot_tried=True,
    prompt_optimizer_tried=True,
    metric_is_programmatic=True,
    labeled_examples_n=800,
    retrieval_tried=True,
    model_swap_tried=True,
    accelerator="nvidia",
    vram_gb=24.0,
    ram_gb=64.0,
    disk_free_gb=500.0,
)

# The same team, except they can say which of two replies is better and cannot
# write the ideal one themselves. Too few written demonstrations for SFT.
MINTING["TRAIN__DPO"] = _facts(
    MINTING["TRAIN__LORA_SFT"],
    labeled_examples_n=60,
    preference_pairs_n=4000,
    user_can_rank_but_not_write=True,
)

# A coding-agent task where the reward is a test suite that either passes or
# does not, and the task takes several steps.
MINTING["TRAIN__RL_GRPO"] = _facts(
    MINTING["TRAIN__LORA_SFT"],
    labeled_examples_n=60,
    preference_pairs_n=0,
    user_can_rank_but_not_write=False,
    reward_is_programmatic=True,
    task_is_multistep=True,
)

# A team whose model does not speak their domain's vocabulary at all. Retrieval
# was built and it did not help, and they have a large static internal corpus.
MINTING["TRAIN__CONTINUED_PRETRAINING"] = _facts(
    _ADMISSIBLE,
    _MEASURED_AND_SHORT,
    need_type=["knowledge"],
    failure_histogram={"wrong_facts": 40},
    knowledge_volatility="static",
    corpus_tokens=5_000_000,
    calls_per_day=5_000,
    retrieval_tried=True,
    retriever_recall_at_k=0.92,
    unlabeled_domain_tokens=200_000_000,
    prompt_iterations=5,
    fewshot_tried=True,
    prompt_optimizer_tried=True,
    metric_is_programmatic=True,
    model_swap_tried=True,
    accelerator="nvidia",
    vram_gb=48.0,
    ram_gb=128.0,
    disk_free_gb=2000.0,
)

# The retriever fixture, and the one the spec calls not optional. Retrieval is
# built, recall is the bottleneck, every free fix has been done, and there are
# labelled query-positive pairs. It passes G3 under llm_weights on the way down
# the LLM spine and must be asked the retriever question again at the sweep.
MINTING["TRAIN__EMBEDDING_FINETUNE"] = _facts(
    _ADMISSIBLE,
    _MEASURED_AND_SHORT,
    need_type=["knowledge"],
    failure_histogram={"wrong_facts": 40},
    knowledge_volatility="static",
    corpus_tokens=5_000_000,
    calls_per_day=5_000,
    retrieval_tried=True,
    retriever_recall_at_k=0.55,
    reranker_tried=True,
    query_rewriting_tried=True,
    labeled_query_positive_pairs=6_000,
    model_swap_tried=True,
    accelerator="nvidia",
    vram_gb=24.0,
    ram_gb=64.0,
    disk_free_gb=500.0,
)

# THE BRANCH THAT WAS DEAD. Quality already meets the bar; the bill does not.
# High volume, a teacher whose licence permits distillation, quantisation and
# caching already in place.
MINTING["TRAIN__DISTILLATION"] = _facts(
    _ADMISSIBLE,
    need_type=["cost"],
    baseline_measured=True,
    baseline_score=0.91,
    trivial_baseline_score=0.20,
    data_quality=0.9,
    deployment="cloud_api",
    current_precision="fp16",
    calls_per_day=50_000,
    latency_budget_ms=2000,
    quality_loss_tolerance="small",
    teacher_license_permits_distillation=True,
    quantization_tried=True,
    caching_enabled=True,
    retrieval_tried=True,
    model_swap_tried=True,
    accelerator="nvidia",
    vram_gb=24.0,
    ram_gb=64.0,
    disk_free_gb=500.0,
)

# Five million rows of clickstream with a very high-cardinality item sequence.
# Entered at stage 8 straight from the modality fork, so it owes four gates.
MINTING["TRAIN__TABULAR_DEEP"] = _facts(
    modality="tabular",
    task_family="prediction",
    eval_size_n=5_000,
    target_score=0.80,
    privacy="public_ok",
    needs_citations=False,
    tabular_rows=5_000_000,
    tabular_features=120,
    classes_n=2,
    has_high_cardinality_sequence=True,
    has_free_text_columns=False,
    baseline_measured=True,
    baseline_score=0.71,
    trivial_baseline_score=0.30,
    data_quality=0.9,
    hparam_search_trials=60,
    feature_work_considered=True,
    model_swap_tried=True,
    accelerator="nvidia",
    vram_gb=24.0,
    ram_gb=64.0,
    disk_free_gb=500.0,
)

# Sixty thousand labelled examples, a capability gap the scaffold did not close,
# and a machine large enough for the file's own full-fine-tune figure.
MINTING["TRAIN__FULL_FINETUNE"] = _facts(
    _ADMISSIBLE,
    _MEASURED_AND_SHORT,
    failure_histogram={"wrong_reasoning": 40},
    labeled_examples_n=60_000,
    model_swap_tried=True,
    agent_scaffold_tried=True,
    task_is_multistep=True,
    prompt_iterations=5,
    fewshot_tried=True,
    prompt_optimizer_tried=True,
    metric_is_programmatic=True,
    retrieval_tried=True,
    accelerator="nvidia",
    vram_gb=160.0,
    ram_gb=512.0,
    disk_free_gb=8000.0,
    quality_loss_tolerance="small",
)

# The rare honest from-scratch case: no open-weight base fits at all, the token
# budget clears the compute-optimal floor, and the money is there for the size
# the file actually prices.
MINTING["TRAIN__FROM_SCRATCH"] = _facts(
    _ADMISSIBLE,
    _MEASURED_AND_SHORT,
    failure_histogram={"wrong_reasoning": 40},
    labeled_examples_n=2_000,
    model_swap_tried=True,
    agent_scaffold_tried=True,
    task_is_multistep=True,
    prompt_iterations=5,
    fewshot_tried=True,
    prompt_optimizer_tried=True,
    metric_is_programmatic=True,
    retrieval_tried=True,
    no_suitable_open_weight_base_exists=True,
    tokens_available=50_000_000_000,
    target_params=1_000_000_000,
    budget_usd=2_000.0,
    accelerator="nvidia",
    vram_gb=24.0,
    ram_gb=64.0,
    disk_free_gb=2000.0,
)


# ---------------------------------------------------------------------------
# The no-train spread, and the failing halves. These are the product.
#
# Each case names the node it must stop at as well as the outcome, because two
# different nodes emit NO_TRAIN__SHIP_AS_IS for two very different reasons and a
# test that only checked the outcome would not notice them swapping.

SPREAD: dict[str, dict[str, Any]] = {}


def _case(
    label: str,
    outcome: str,
    node: str,
    facts: dict[str, Any],
    *,
    failing_half_of: str | None = None,
    proposes: str | None = None,
    refused_by: str | None = None,
    mints_when: dict[str, Any] | None = None,
) -> None:
    """One no-train answer, and optionally the four fields that make it a failing half.

    `failing_half_of` is the node whose proposal this fact set kills, and it is
    the key RC5 counts by. `proposes` is the method that node puts forward -
    asserted rather than assumed, because a node appearing in `path` proves only
    that it was EVALUATED; `note_node` writes the id before the condition runs.
    `refused_by` is the gate or node that said no. `mints_when` is the single
    fact that turns this back into a training verdict, and it is what makes the
    case a diagnosis rather than a coincidence: without it, a fixture that landed
    on the cheap answer because of some unrelated fact would look identical.
    """
    case: dict[str, Any] = {"outcome": outcome, "node": node, "facts": attribute(facts)}
    if failing_half_of is not None:
        case["failing_half_of"] = failing_half_of
        case["proposes"] = proposes
        case["refused_by"] = refused_by
        # Attributed for the same reason the fact set is. `mints_when` is applied
        # on top of these facts and asserted to produce a training verdict; left
        # bare it would be an assertion, the gate it opens would refuse it, and
        # the case would stop being the thing it claims to be - quietly, because
        # the run would still not train.
        case["mints_when"] = None if mints_when is None else attribute(mints_when)
    SPREAD[label] = case


def failing_halves() -> dict[str, list[str]]:
    """SPREAD labels grouped by the proposing node each one is the failing half of.

    Derived from the cases themselves rather than written out, for the reason
    RC5 gives about its own list: a hand-kept index of what is covered is a list
    that goes stale in the direction nobody looks.
    """
    grouped: dict[str, list[str]] = {}
    for label, case in SPREAD.items():
        node = case.get("failing_half_of")
        if node is not None:
            grouped.setdefault(node, []).append(label)
    return grouped


# No eval set. Nothing downstream is decidable.
_case(
    "no_eval_set",
    "BLOCKED__BUILD_EVAL_SET",
    "S0_NO_EVAL_SET",
    _facts(_ADMISSIBLE, eval_size_n=12),
)

# An eval set, but nobody has scored the thing that already exists.
_case(
    "baseline_unmeasured",
    "ACTION__MEASURE_BASELINE",
    "S1_UNMEASURED",
    _facts(_ADMISSIBLE, baseline_measured=False),
)

# The highest-value answer in the engine: it already works, and nothing about
# cost, speed or privacy is in the way.
_case(
    "already_passes",
    "NO_TRAIN__SHIP_AS_IS",
    "S1_ALREADY_PASSES",
    _facts(
        _ADMISSIBLE,
        baseline_measured=True,
        baseline_score=0.91,
        trivial_baseline_score=0.20,
        data_quality=0.9,
        need_type=[],
    ),
)

# Facts that change weekly cannot live in weights.
_case(
    "volatile_knowledge",
    "NO_TRAIN__RAG",
    "S3_VOLATILE_KNOWLEDGE",
    _facts(
        _ADMISSIBLE,
        _MEASURED_AND_SHORT,
        need_type=["knowledge"],
        failure_histogram={"wrong_facts": 40},
        knowledge_volatility="weekly",
        retrieval_tried=True,
    ),
)

# Five prompt rewrites with no few-shot attempt is not an exhausted prompt. G2
# fails and the run is sent to the cheapest thing they have not done.
_case(
    "prompt_not_exhausted",
    "NO_TRAIN__FEW_SHOT",
    "S5_FEWSHOT_UNTRIED",
    _facts(
        _ADMISSIBLE,
        _MEASURED_AND_SHORT,
        failure_histogram={"wrong_style": 30},
        prompt_iterations=5,
        fewshot_tried=False,
        labeled_examples_n=800,
    ),
)

# THE BRANCH THAT WAS DEAD, answered no-train. Quality passes, the volume does
# not yet pay for a student model, so the answer is to ship what they have.
_case(
    "cost_pressure_below_the_line",
    "NO_TRAIN__SHIP_AS_IS",
    "S7_PRESSURE_BELOW_THE_LINE",
    _facts(
        _ADMISSIBLE,
        need_type=["cost"],
        baseline_measured=True,
        baseline_score=0.91,
        trivial_baseline_score=0.20,
        data_quality=0.9,
        deployment="cloud_api",
        current_precision="fp16",
        calls_per_day=400,
        latency_budget_ms=2000,
        caching_enabled=True,
        teacher_license_permits_distillation=True,
    ),
)

# The latency branch, still cheap to fix: a local deployment running at fp16.
_case(
    "latency_quantize_first",
    "NO_TRAIN__QUANTIZE",
    "S7_QUANTIZE",
    _facts(
        _ADMISSIBLE,
        need_type=["latency"],
        baseline_measured=True,
        baseline_score=0.91,
        trivial_baseline_score=0.20,
        data_quality=0.9,
        deployment="local_gpu",
        current_precision="fp16",
        calls_per_day=50_000,
        latency_budget_ms=300,
        teacher_license_permits_distillation=True,
    ),
)

# The privacy branch: quality passes and the model may not leave the building.
_case(
    "privacy_forces_distillation_licence_check",
    "BLOCKED__LICENCE",
    "S7_DISTILL_BLOCKED_BY_LICENCE",
    _facts(
        _ADMISSIBLE,
        privacy="on_prem_only",
        need_type=["privacy"],
        baseline_measured=True,
        baseline_score=0.91,
        trivial_baseline_score=0.20,
        data_quality=0.9,
        deployment="local_gpu",
        current_precision="int4",
        calls_per_day=400,
        latency_budget_ms=2000,
        caching_enabled=True,
        teacher_license_permits_distillation=False,
    ),
)

# The default answer for tabular, and usually the final one.
_case(
    "tabular_default",
    "NO_DEEP__GRADIENT_BOOSTED_TREES",
    "S8_TABULAR_STANDARD",
    _facts(
        modality="tabular",
        task_family="prediction",
        eval_size_n=5_000,
        target_score=0.80,
        privacy="public_ok",
        needs_citations=False,
        tabular_rows=5_000_000,
        tabular_features=120,
        classes_n=2,
        has_high_cardinality_sequence=False,
        has_free_text_columns=False,
    ),
)

# THE FAILING HALF OF THE DISTILLATION FIXTURE. Everything the minting version
# has, except nobody checked whether something smaller off the shelf already
# does the job. G4 fails at the sweep and the proposal dies.
_case(
    "distillation_fails_g4",
    "NO_TRAIN__SWAP_MODEL",
    "S6_SWAP_THE_MODEL",
    _facts(MINTING["TRAIN__DISTILLATION"], model_swap_tried=False),
    failing_half_of="S7_DISTILL",
    proposes="DISTILLATION",
    refused_by="G4_CHEAPER_MODEL_CONSIDERED",
    mints_when={"model_swap_tried": True},
)

# THE FAILING HALF OF THE TABULAR FIXTURE. Five million rows and a real sequence
# feature, but GBDT and TabPFN were never fitted and scored. The tabular branch
# skips four gates on its way here and the sweep is where it pays for them.
_case(
    "tabular_deep_fails_g4",
    "NO_TRAIN__SWAP_MODEL",
    "S6_SWAP_THE_MODEL",
    _facts(MINTING["TRAIN__TABULAR_DEEP"], model_swap_tried=False),
    failing_half_of="S8_TABULAR_DEEP_JUSTIFIED",
    proposes="TABULAR_DEEP",
    refused_by="G4_CHEAPER_MODEL_CONSIDERED",
    mints_when={"model_swap_tried": True},
)

# The labelled pairs are there and the free fixes are done, but retrieval itself
# was never built, so G3 cannot pass and the answer is to build the retriever,
# not to train one.
#
# NOT A FAILING HALF, AND RC5 SAYS IT IS. RC5_FIXTURE_COVERAGE credits this fact
# set with covering S3_TRAIN_THE_RETRIEVER_NOT_THE_LLM, and it does not: G3 is
# the LEADING gate of stage_3_knowledge, so `retrieval_tried: false` fails it at
# the top of the stage, under the provisional llm_weights row, before any node in
# stage 3 is evaluated. The proposing node is not on the path and
# `proposed_method` comes back UNSET. That is a gate stopping a run, which is
# worth a fixture - it is just not the shape RC5 counts, which is a PROPOSAL
# reaching the sweep and being refused there. `retriever_fails_g4` below is the
# one that is, so the true count was ten owed, not nine.
_case(
    "retriever_fails_g3",
    "NO_TRAIN__RAG",
    "S3_BUILD_RAG",
    _facts(MINTING["TRAIN__EMBEDDING_FINETUNE"], retrieval_tried=False),
)

# A teaching outcome, reachable only because the goal is learning. It is not a
# TRAIN__ verdict and must never answer a production goal.
_case(
    "teaching_from_scratch",
    "TEACH__FROM_SCRATCH_NANOGPT",
    "S9_FROM_SCRATCH_EDUCATIONAL",
    _facts(
        MINTING["TRAIN__FROM_SCRATCH"],
        goal_is_learning=True,
        target_params=124_000_000,
        no_suitable_open_weight_base_exists=False,
    ),
)

# THE THREE THAT USED TO CRASH. These were group `CYCLING` and the suite asserted
# they raised ERROR__CYCLE, because their gate's `on_fail` routed back into the
# stage that had made the proposal and that stage had no node answering the
# gate's own question - so the same node proposed again until the cycle guard
# stopped the walk. The stages now carry that remedy, so all three answer, and
# the assertion is the answer rather than the crash. They are the users the gates
# exist for: a tabular team that never ran a hyperparameter search, and a
# cost-pressured team that never tried quantisation.

# Five million rows and a real sequence feature, but not one hyperparameter
# search on the trees. G2 fails under classical_deep.
_case(
    "tabular_deep_fails_g2",
    "NO_DEEP__TUNE_THE_TREES_FIRST",
    "S8_TABULAR_DEEP_NEEDS_HPARAM_SEARCH",
    _facts(MINTING["TRAIN__TABULAR_DEEP"], hparam_search_trials=0),
)

# The search was run; nobody asked whether the missing signal is a feature
# rather than a bigger model. G3 fails under classical_deep.
_case(
    "tabular_deep_fails_g3",
    "NO_DEEP__FIND_THE_MISSING_FEATURE",
    "S8_TABULAR_DEEP_NEEDS_FEATURE_WORK",
    _facts(MINTING["TRAIN__TABULAR_DEEP"], feature_work_considered=False),
)

# Fifty thousand calls a day and the model still running at fp16. G2 fails under
# llm_efficiency, and quantising is the cheap thing they skipped.
_case(
    "distillation_fails_g2",
    "NO_TRAIN__QUANTIZE",
    "S7_QUANTIZATION_UNTRIED",
    _facts(MINTING["TRAIN__DISTILLATION"], quantization_tried=False),
)


# ---------------------------------------------------------------------------
# REACHING. One fact set for every declared outcome that MINTING and SPREAD do
# not already reach, so the reachability check can cover all of them.
#
# Keyed by outcome, like MINTING, and for the same reason: the test derives the
# outcome list from the YAML and looks each one up, so an outcome nobody wrote a
# fact set for is a loud failure, not a silent omission.
#
# These are shorter stories than the SPREAD ones. SPREAD asserts which node
# answered because two nodes there emit the same outcome for different reasons.
# These assert only that a user exists who gets this answer at all - which is
# exactly what was not being checked when NO_LLM__SETFIT, NO_LLM__ENCODER_FINETUNE
# and the classification reroute went dead.

REACHING: dict[str, dict[str, Any]] = {}

# -- stage 0: is the question answerable at all -----------------------------

# Pulling an invoice number and a date out of a fixed template. Two fields, one
# page of rules, and the person asking agrees. This is not a model problem.
REACHING["NO_ML__WRITE_CODE"] = _facts(
    _ADMISSIBLE, task_family="extraction", classes_n=3, user_confirms=True
)

# Nobody has said what "good" means and nobody can grade twenty examples to show
# us. There is nothing to be right about yet.
#
# AND NO COUNTED EVAL SET EITHER, which this fixture used to carry (100 rows,
# MEASURED) while still expecting the blocked outcome. From 2026-09-21
# `user_can_produce(20, 'graded examples')` reads a MEASURED `eval_size_n`:
# somebody with a hundred counted graded rows has not merely shown they COULD
# produce twenty, they already did, and blocking them on the question was the
# deadlock that killed every Full run Max ever started - target_score waiting
# on a baseline, the baseline waiting below the gate target_score holds shut.
# So the case that produces ONLY this outcome is the one with no counted rows,
# which is what the comment above always described.
REACHING["BLOCKED__DEFINE_SUCCESS_FIRST"] = _facts(
    {
        k: v
        for k, v in _ADMISSIBLE.items()
        if k not in ("target_score", "eval_size_n")
    }
)

# The same, except they CAN grade examples. So the question is answerable and
# what is missing is only the number they are aiming at.
REACHING["ACTION__SET_A_TARGET_SCORE"] = _facts(
    {k: v for k, v in _ADMISSIBLE.items() if k != "target_score"},
    user_can_produce=True,
)

# The harness could not work out what kind of data this is, and the whole tree
# forks on that. Ask, do not guess.
REACHING["ACTION__NAME_THE_MODALITY"] = _facts(
    {k: v for k, v in _ADMISSIBLE.items() if k != "modality"}
)

# -- stage 1: is the baseline telling us anything ---------------------------

# A keyword baseline scores 0.52 where the LLM scores 0.55. Three points is not
# a model gap; the task or the labels are wrong.
REACHING["BLOCKED__FIX_LABELS_OR_TASK"] = _facts(
    _ADMISSIBLE,
    baseline_measured=True,
    baseline_score=0.55,
    trivial_baseline_score=0.52,
    data_quality=0.9,
)

# Six failures looked at by hand. Not enough to know what is actually going
# wrong, and every branch below here routes on that answer.
# The card has answered and the answer was no. Nothing else on this thread has
# been measured, and that is the whole point: the baseline the gates below would
# demand would have to be taken on the model that will not load.
#
# `cannot_train_here` is MEASURED here because `attribute` stamps every fact at
# the origin its ledger `source:` describes, and this one is `inspect`. That is
# exactly what `S0_THE_CARD_ALREADY_SAID_NO` requires - it reads the ORIGIN
# through `measured()`, so a caller who merely said it walks into the gates.
REACHING["NO_TRAIN__WONT_FIT_THIS_MACHINE"] = _facts(
    _ADMISSIBLE,
    cannot_train_here=True,
    training_headroom_gb=-0.52,
    longest_fitting_seq=1152,
)

REACHING["ACTION__CLASSIFY_FAILURES"] = _facts(
    _ADMISSIBLE, _MEASURED_AND_SHORT, failure_histogram={"wrong_style": 6}
)

# Thirty-four failures spread over three buckets with no dominant one. One
# fine-tune cannot fix three different problems.
REACHING["ACTION__SPLIT_THE_TASK"] = _facts(
    _ADMISSIBLE,
    _MEASURED_AND_SHORT,
    failure_histogram={"wrong_style": 12, "wrong_facts": 12, "wrong_format": 10},
)

# -- stage 5: behaviour, and the cheap things before it ---------------------

# One prompt rewrite. The cheapest thing in the file has barely been started.
REACHING["NO_TRAIN__BETTER_PROMPT"] = _facts(
    _ADMISSIBLE,
    _MEASURED_AND_SHORT,
    failure_histogram={"wrong_style": 30},
    prompt_iterations=1,
)

# Prompts rewritten and few-shot done, the metric is programmatic and the eval
# set is big enough - so an automatic prompt optimiser is the next cheap step.
REACHING["NO_TRAIN__PROMPT_OPTIMIZER"] = _facts(
    _ADMISSIBLE,
    _MEASURED_AND_SHORT,
    failure_histogram={"wrong_style": 30},
    prompt_iterations=5,
    fewshot_tried=True,
    prompt_optimizer_tried=False,
    metric_is_programmatic=True,
)

# The same team with forty eval examples. An optimiser cannot search against a
# set that small without fitting it, so grow the set first.
REACHING["ACTION__GROW_THE_EVAL_SET"] = _facts(
    _ADMISSIBLE,
    _MEASURED_AND_SHORT,
    eval_size_n=40,
    failure_histogram={"wrong_style": 30},
    prompt_iterations=5,
    fewshot_tried=True,
    prompt_optimizer_tried=False,
    metric_is_programmatic=True,
)

# And again with a big enough eval set but a score only a human can give. The
# optimiser has nothing to optimise against.
REACHING["ACTION__MAKE_THE_METRIC_PROGRAMMATIC"] = _facts(
    _ADMISSIBLE,
    _MEASURED_AND_SHORT,
    failure_histogram={"wrong_style": 30},
    prompt_iterations=5,
    fewshot_tried=True,
    prompt_optimizer_tried=False,
    metric_is_programmatic=False,
)

# Everything cheap is genuinely done and there are twenty written examples.
# Twenty is not a training set.
REACHING["BLOCKED__COLLECT_OR_SYNTHESIZE_DATA"] = _facts(
    _ADMISSIBLE,
    _MEASURED_AND_SHORT,
    failure_histogram={"wrong_style": 30},
    prompt_iterations=5,
    fewshot_tried=True,
    prompt_optimizer_tried=True,
    metric_is_programmatic=True,
    labeled_examples_n=20,
)

# -- stage 4: the output shape ---------------------------------------------

# The model returns JSON that does not parse and nobody has turned on a grammar.
REACHING["NO_TRAIN__CONSTRAINED_DECODING"] = _facts(
    _ADMISSIBLE,
    _MEASURED_AND_SHORT,
    failure_histogram={"wrong_format": 30},
    constrained_decoding_tried=False,
)

# Constrained decoding is on and nobody measured whether it holds.
REACHING["ACTION__MEASURE_THE_FORMAT"] = _facts(
    _ADMISSIBLE,
    _MEASURED_AND_SHORT,
    failure_histogram={"wrong_format": 30},
    constrained_decoding_tried=True,
)

# It is on, the shape IS expressible as a schema, and seventy per cent of
# outputs match. A decoder that is on and not holding is a bug in the decoder.
REACHING["ACTION__FIX_THE_DECODER"] = _facts(
    _ADMISSIBLE,
    _MEASURED_AND_SHORT,
    failure_histogram={"wrong_format": 30},
    constrained_decoding_tried=True,
    schema_compliance=0.70,
    schema_expressible=True,
)

# Every output now matches the schema and the score did not move. The failures
# were bucketed as format and they are not format.
REACHING["ACTION__RE_BUCKET_THE_FAILURES"] = _facts(
    _ADMISSIBLE,
    _MEASURED_AND_SHORT,
    failure_histogram={"wrong_format": 30},
    constrained_decoding_tried=True,
    schema_compliance=1.0,
    schema_expressible=True,
)

# -- stage 3: knowledge ------------------------------------------------------

# Retrieval is built, but nobody has said how fast these facts move, and that
# single answer decides between RAG and weights.
REACHING["ACTION__STATE_KNOWLEDGE_VOLATILITY"] = _facts(
    _ADMISSIBLE,
    _MEASURED_AND_SHORT,
    need_type=["knowledge"],
    failure_histogram={"wrong_facts": 40},
    retrieval_tried=True,
)

# A static thirty-thousand-token handbook and a hundred calls a day. The whole
# corpus fits in the context window; there is nothing to retrieve from.
REACHING["NO_TRAIN__CONTEXT_STUFFING"] = _facts(
    _ADMISSIBLE,
    _MEASURED_AND_SHORT,
    need_type=["knowledge"],
    failure_histogram={"wrong_facts": 40},
    retrieval_tried=True,
    knowledge_volatility="static",
    corpus_tokens=30_000,
    calls_per_day=100,
)

# Retrieval is built and recall is 0.55, and the free fixes - a reranker, query
# rewriting - have not been tried. Fix the retriever before training one.
REACHING["NO_TRAIN__FIX_RETRIEVAL"] = _facts(
    _ADMISSIBLE,
    _MEASURED_AND_SHORT,
    need_type=["knowledge"],
    failure_histogram={"wrong_facts": 40},
    retrieval_tried=True,
    knowledge_volatility="static",
    corpus_tokens=5_000_000,
    calls_per_day=5_000,
    retriever_recall_at_k=0.55,
    reranker_tried=False,
)

# Retrieval is built and nobody has scored it. Every answer below this depends
# on that number.
REACHING["ACTION__MEASURE_RETRIEVER_RECALL"] = _facts(
    _ADMISSIBLE,
    _MEASURED_AND_SHORT,
    need_type=["knowledge"],
    failure_histogram={"wrong_facts": 40},
    retrieval_tried=True,
    knowledge_volatility="static",
    corpus_tokens=5_000_000,
    calls_per_day=5_000,
)

# -- stage 6: capability -----------------------------------------------------

# A multi-step task run as one prompt against one model. A bigger model was
# tried; a scaffold was not.
REACHING["NO_TRAIN__AGENT_SCAFFOLD"] = _facts(
    _ADMISSIBLE,
    _MEASURED_AND_SHORT,
    failure_histogram={"wrong_reasoning": 40},
    model_swap_tried=True,
    task_is_multistep=True,
    agent_scaffold_tried=False,
)

# -- stage 7: cost and latency ----------------------------------------------

# The bill is the complaint, but the quality is short of the bar as well. A
# cheaper model that is still wrong is not the answer.
REACHING["ACTION__FIX_QUALITY_FIRST"] = _facts(
    _ADMISSIBLE, _MEASURED_AND_SHORT, failure_histogram={"too_expensive": 40}
)

# Quality passes, fifty thousand calls a day against a hosted API, and no cache.
# Repeat traffic is free money before anything is trained.
REACHING["NO_TRAIN__CACHE_AND_ROUTE"] = _facts(
    _ADMISSIBLE,
    need_type=["cost"],
    baseline_measured=True,
    baseline_score=0.91,
    trivial_baseline_score=0.20,
    data_quality=0.9,
    deployment="cloud_api",
    current_precision="fp16",
    calls_per_day=50_000,
    latency_budget_ms=2000,
    caching_enabled=False,
    teacher_license_permits_distillation=True,
)

# -- stage 8: the classical branch ------------------------------------------

_TABULAR: dict[str, Any] = {
    "modality": "tabular",
    "task_family": "prediction",
    "eval_size_n": 5_000,
    "target_score": 0.80,
    "privacy": "public_ok",
    "needs_citations": False,
}

# The row count could not be read off the file, and every node in the tabular
# branch turns on it. Saying so is an answer; raising is not.
REACHING["ACTION__COUNT_THE_ROWS"] = _facts(_TABULAR)

# Four hundred rows. This is a question for statistics, not for a model.
REACHING["NO_ML__STATISTICS_OR_MORE_DATA"] = _facts(
    _TABULAR, tabular_rows=400, tabular_features=12, classes_n=2
)

# Four thousand rows, thirty columns, three classes. The tabular foundation
# model handles this size without a fit at all.
REACHING["NO_DEEP__TABPFN"] = _facts(
    _TABULAR, tabular_rows=4_000, tabular_features=30, classes_n=3
)

# Two hundred thousand rows with a free-text notes column: embed the text,
# hand the vector to the trees.
REACHING["NO_DEEP__HYBRID_EMBED_PLUS_GBDT"] = _facts(
    _TABULAR,
    tabular_rows=200_000,
    tabular_features=60,
    classes_n=2,
    has_free_text_columns=True,
)

# A demand forecast. Classical forecasting, not a neural net.
REACHING["NO_DEEP__CLASSICAL_FORECAST"] = _facts(
    _TABULAR, modality="timeseries", task_family="forecasting"
)

# ONE OF THE THREE OUTCOMES THAT WENT DEAD, AND IT HAS NOW MOVED HOUSE. Forty
# closed-set labels and two thousand examples of them: few-shot contrastive
# fitting, not an LLM. The pass that widened S8_TABULAR_STANDARD to `>= 1000`
# swallowed exactly this user, and the reachability test could not see it because
# the outcome is NO_LLM__ rather than TRAIN__.
#
# IT USED TO BE A TABULAR STORY AND IT IS A TEXT ONE NOW, which is worth writing
# down rather than quietly rewriting. SetFit and an encoder fine-tune are things
# you do to TEXT with a fixed label set; the fixture said `modality: tabular`
# only because stage 8 was the tabular stage and the modality fork was the only
# door into it. There is a second door now - S1_CLOSED_SET_CLASSIFICATION, which
# takes a text or code run to stage 8 AFTER the LLM baseline has been measured
# and found short - and S8_TEXT_CLASSIFICATION_FEW_LABELS was guarded to
# `modality in {text, code}` to match. Under the old facts this fixture stopped
# at S8_TABULAR_UNMATCHED and answered NO_DEEP__GRADIENT_BOOSTED_TREES: a team
# with forty text labels told to fit a tree. The fixture was describing the wrong
# user, and it took the new guard to make that visible.
REACHING["NO_LLM__SETFIT"] = _facts(
    _ADMISSIBLE,
    _MEASURED_AND_SHORT,
    task_family="classification",
    classes_n=40,
    labeled_examples_n=2_000,
    labels_are_closed_set=True,
    requires_multistep_reasoning=False,
)

# THE SECOND ONE. Two hundred labels and twenty thousand labelled examples: too
# many classes for SetFit, plenty of data for an encoder. Moved to text for the
# same reason as the fixture above, and the two together are what makes the split
# at `classes_n <= 50` a tested boundary rather than a written one.
REACHING["NO_LLM__ENCODER_FINETUNE"] = _facts(
    REACHING["NO_LLM__SETFIT"],
    classes_n=200,
    labeled_examples_n=20_000,
)

# An image classifier nobody has yet tried an off-the-shelf model on.
REACHING["NO_TRAIN__OFF_THE_SHELF_MODEL"] = _facts(
    modality="image",
    task_family="classification",
    eval_size_n=300,
    target_score=0.90,
    privacy="public_ok",
    needs_citations=False,
    offtheshelf_measured=False,
)

# -- stage 9: the last two ways a proposal dies -----------------------------

# The LoRA fixture, from someone who asked to train from scratch. No open-weight
# base is missing, so the from-scratch case does not hold and we say so.
REACHING["NO_TRAIN__USE_EXISTING_BASE"] = _facts(
    MINTING["TRAIN__LORA_SFT"],
    user_requested_from_scratch=True,
    no_suitable_open_weight_base_exists=False,
)

# THE THIRD OUTCOME THAT WENT DEAD IS THE REROUTE THIS RUN DEPENDS ON. A tabular
# classification problem whose labels are open-ended: stage 8 strikes the neural
# LLM methods, then S8_CLASSIFICATION_NEEDS_REASONING sends the run back to
# stage 1 to be diagnosed as a text problem. Stage 5 then proposes LORA_SFT -
# which stage 8 struck on the way past - and stage 9 refuses it by name instead
# of quietly minting it.
REACHING["NO_TRAIN__RULED_OUT_EARLIER"] = _facts(
    _TABULAR,
    task_family="classification",
    tabular_rows=5_000,
    tabular_features=800,
    classes_n=40,
    labels_are_closed_set=False,
    has_free_text_columns=False,
    baseline_measured=True,
    baseline_score=0.55,
    trivial_baseline_score=0.20,
    data_quality=0.9,
    need_type=["knowledge"],
    failure_histogram={"wrong_style": 30},
    prompt_iterations=5,
    fewshot_tried=True,
    prompt_optimizer_tried=True,
    metric_is_programmatic=True,
    labeled_examples_n=800,
    retrieval_tried=True,
    model_swap_tried=True,
    accelerator="nvidia",
    vram_gb=24.0,
    ram_gb=64.0,
    disk_free_gb=500.0,
)

# THE USER WHOSE MODEL FILLED IN THE FORM FOR THEM, which is the whole reason
# origins exist. Everything about this run is the LoRA story - the same team,
# the same tone problem, the same eight hundred demonstrations, the same 24 GB
# card - and one thing is different: nobody counted the eval set. A model
# reported "eval_size_n: 100" and the harness wrote it down.
#
# eval_size_n is declared `source: inspect`. That tag is this product promising
# to COUNT the eval set rather than to take a number for it, and the count is
# what makes every score downstream mean anything. So G0's predicate is true and
# the gate does not open, and the answer is not "build an eval set" - they have
# just said they have one, and saying it back to them reads as not listening.
# The answer is: show me. Point the harness at the file and it will count.
#
# The single `asserted(...)` here is the entire fixture. Everything else is
# attributed exactly as `_facts` attributes every other fact set in this file,
# which is what makes the difference legible: change that one call to a bare 100
# and nothing moves, because bare IS asserted; change it to `measured(100)` and
# this run mints TRAIN__LORA_SFT.
REACHING["ACTION__SUBSTANTIATE_CLAIMED_FACTS"] = _facts(
    MINTING["TRAIN__LORA_SFT"],
    eval_size_n=asserted(100),
)


# ---------------------------------------------------------------------------
# THE FAILING HALVES RC5 SAID WERE OWED. They are SPREAD cases like any other;
# they sit down here rather than up in the SPREAD block only because one of them
# is built from a REACHING fact set defined above.
#
# RC5_FIXTURE_COVERAGE named them by node and called the gap a gap: twelve
# proposing nodes, six fact sets covering three of them, "NINE PROPOSING NODES
# STILL OWE A FAILING HALF". Nine is off by one, and the extra one is written
# here too - see `retriever_fails_g4` and the note above `retriever_fails_g3`.
# RC5 credits that older fixture with covering
# S3_TRAIN_THE_RETRIEVER_NOT_THE_LLM, but it fails G3 at the TOP of stage 3, so
# the proposing node is never reached and `proposed_method` comes back UNSET. Ten
# were owed. Each one below reaches its node, lets it propose, and then has the
# proposal refused - and the assertion is the node that answered instead,
# because the cheaper answer is the product.
#
# ONE THING RC5 ASKS FOR CANNOT BE DONE, AND SAYING SO IS BETTER THAN FAKING IT.
# RC5's wording is "flipping one fact so A GATE FAILS AT THE SWEEP". That is
# exactly right for eight of the ten. It is impossible for the two proposing
# nodes that live INSIDE stage 9 - S9_FULL_FT_JUSTIFIED and S9_FROM_SCRATCH -
# because S9_GATE_SWEEP is the first item of that stage and both nodes sit below
# it. No gate is ever evaluated after they propose. Nor could one be: both
# propose an llm_weights method into a run whose sweep already ran under
# llm_weights, so row_key does not change and nothing would be re-asked even if
# a second sweep existed.
#
# That is not a hole in the engine. Stage 9 has two other ways to refuse a
# proposal, and those two nodes are refused by them here: S9_PROPOSAL_WAS_STRUCK,
# where an earlier stage struck the method by name, and
# S9_FROM_SCRATCH_EDUCATIONAL, where the from-scratch case genuinely holds and
# the answer is still nanoGPT. The other eight fail a real gate at the sweep.
# Both shapes carry `refused_by`, so the test asserts the mechanism and not only
# the destination.

# The domain-dialect team from TRAIN__CONTINUED_PRETRAINING - two hundred million
# tokens of internal writing, retrieval built and measured - who never once put
# three in-house documents in the prompt as examples. G2 is not asked on the way
# down, because a wrong_facts run enters at stage 3 and never passes stage 5; the
# sweep asks it, and the cheapest way to teach a model a dialect is to show it
# some of the dialect.
_case(
    "domain_dialect_fails_g2",
    "NO_TRAIN__FEW_SHOT",
    "S5_FEWSHOT_UNTRIED",
    _facts(MINTING["TRAIN__CONTINUED_PRETRAINING"], fewshot_tried=False),
    failing_half_of="S3_DOMAIN_DIALECT_GAP",
    proposes="CONTINUED_PRETRAINING",
    refused_by="G2_PROMPT_EXHAUSTED",
    mints_when={"fewshot_tried": True},
)

# A bespoke report layout no JSON schema can express, eight hundred written
# examples of it - and one rewrite of the system prompt. The spec's own note on
# S4_IDIOSYNCRATIC_FORMAT says this node used to emit TRAIN__LORA_SFT straight
# out of stage 4 and so "skipped G2 and G4 entirely - a fine-tune recommended
# without few-shot ever being tried". This is that sentence executed: the node
# proposes now instead of minting, and the sweep asks the question stage 4 has no
# node able to ask.
_S4_FORMAT_FINE_TUNE: dict[str, Any] = _facts(
    _ADMISSIBLE,
    _MEASURED_AND_SHORT,
    failure_histogram={"wrong_format": 30},
    constrained_decoding_tried=True,
    schema_compliance=0.74,
    schema_expressible=False,
    labeled_examples_n=800,
    prompt_iterations=5,
    fewshot_tried=True,
    prompt_optimizer_tried=True,
    metric_is_programmatic=True,
    retrieval_tried=True,
    model_swap_tried=True,
    accelerator="nvidia",
    vram_gb=24.0,
    ram_gb=64.0,
    disk_free_gb=500.0,
)

_case(
    "format_fine_tune_fails_g2",
    "NO_TRAIN__BETTER_PROMPT",
    "S5_BETTER_PROMPT",
    _facts(_S4_FORMAT_FINE_TUNE, prompt_iterations=1),
    failing_half_of="S4_IDIOSYNCRATIC_FORMAT",
    proposes="LORA_SFT",
    refused_by="G2_PROMPT_EXHAUSTED",
    mints_when={"prompt_iterations": 5},
)

# The support team from TRAIN__LORA_SFT, who never put a good reply in front of
# the model before deciding to put one into it. G3's own note is the argument:
# "Retrieved exemplars are the cheaper alternative to a style fine-tune."
# `knowledge_volatility` is static in both halves rather than in the flip alone,
# so that the refused run lands on the remedy for the missing retriever instead
# of on the node that asks how fast the facts move.
_case(
    "demonstrations_fail_g3",
    "NO_TRAIN__RAG",
    "S3_BUILD_RAG",
    _facts(
        MINTING["TRAIN__LORA_SFT"],
        knowledge_volatility="static",
        retrieval_tried=False,
    ),
    failing_half_of="S5_DEMONSTRATIONS_AVAILABLE",
    proposes="LORA_SFT",
    refused_by="G3_RETRIEVAL_CONSIDERED",
    mints_when={"retrieval_tried": True},
)

# Four thousand preference pairs, a team that can rank two replies and cannot
# write the ideal one - and nobody searched for a model already tuned to this
# taste. Preference-tuned open weights are the most crowded shelf there is, which
# is what G4 is for: "Someone has usually already trained this."
_case(
    "preferences_fail_g4",
    "NO_TRAIN__SWAP_MODEL",
    "S6_SWAP_THE_MODEL",
    _facts(MINTING["TRAIN__DPO"], model_swap_tried=False),
    failing_half_of="S5_PREFERENCES_NOT_DEMONSTRATIONS",
    proposes="DPO",
    refused_by="G4_CHEAPER_MODEL_CONSIDERED",
    mints_when={"model_swap_tried": True},
)

# The coding-agent team from TRAIN__RL_GRPO, whose reward is a test suite that
# passes or does not - and who never tried a reasoning model. Reinforcement
# learning is the most expensive thing this file can recommend and G4 is the last
# cheap question in front of it. It lands on the same remedy as the DPO case
# above, which is not a duplicate: two different nodes propose two different
# methods and the same gate stops both, and a test that checked only destinations
# could not tell those apart.
_case(
    "verifiable_reward_fails_g4",
    "NO_TRAIN__SWAP_MODEL",
    "S6_SWAP_THE_MODEL",
    _facts(MINTING["TRAIN__RL_GRPO"], model_swap_tried=False),
    failing_half_of="S5_VERIFIABLE_REWARD",
    proposes="RL_GRPO",
    refused_by="G4_CHEAPER_MODEL_CONSIDERED",
    mints_when={"model_swap_tried": True},
)

# Eight thousand labelled examples, a bigger model tried, an agent scaffold
# built, a programmatic metric and a hundred eval rows - and no prompt optimiser.
# A wrong_reasoning run enters at stage 6 straight from the failure router, so G2
# is never asked on the way down and the sweep is the first time anybody does.
# This node proposes UNSET, so the sweep runs under the provisional llm_weights
# row and the size table below it never gets to name a method at all.
_S6_CAPABILITY_GAP: dict[str, Any] = _facts(
    _ADMISSIBLE,
    _MEASURED_AND_SHORT,
    failure_histogram={"wrong_reasoning": 40},
    labeled_examples_n=8_000,
    model_swap_tried=True,
    agent_scaffold_tried=True,
    task_is_multistep=True,
    prompt_iterations=5,
    fewshot_tried=True,
    metric_is_programmatic=True,
    retrieval_tried=True,
    accelerator="nvidia",
    vram_gb=24.0,
    ram_gb=64.0,
    disk_free_gb=500.0,
)

_case(
    "capability_gap_fails_g2",
    "NO_TRAIN__PROMPT_OPTIMIZER",
    "S5_PROMPT_OPTIMIZER_UNTRIED",
    _facts(_S6_CAPABILITY_GAP, prompt_optimizer_tried=False),
    failing_half_of="S6_GENUINELY_ABSENT",
    proposes="UNSET",
    refused_by="G2_PROMPT_EXHAUSTED",
    mints_when={"prompt_optimizer_tried": True},
)

# Five thousand labelled photographs, an off-the-shelf classifier measured at
# 0.71 against a 0.90 target - and no trivial baseline, so nobody knows whether
# majority-class already scores 0.70.
#
# THE ONLY FIXTURE IN THIS FILE THAT FAILS G1, and the image fork is what makes
# it possible. S0_MODALITY_FORK sends image and audio to
# stage_8_offtheshelf_first, which carries no gate_ref at all, so a vision run
# reaches the sweep having been asked exactly one gate - G0, back in stage 0.
# Every text run passes G1 at the top of stage 1 or stops there, so for a text
# run G1 can only ever fail before any proposal exists. Here the proposal is
# already made when the question is finally put, and the answer is the one stage
# 1 would have given: go and measure the thing you are trying to beat.
_S8_VISION_GAP: dict[str, Any] = _facts(
    modality="image",
    task_family="classification",
    eval_size_n=300,
    target_score=0.90,
    privacy="public_ok",
    needs_citations=False,
    offtheshelf_measured=True,
    baseline_measured=True,
    baseline_score=0.71,
    data_quality=0.9,
    labeled_examples_n=5_000,
    prompt_iterations=5,
    fewshot_tried=True,
    prompt_optimizer_tried=True,
    metric_is_programmatic=True,
    retrieval_tried=True,
    model_swap_tried=True,
    accelerator="nvidia",
    vram_gb=24.0,
    ram_gb=64.0,
    disk_free_gb=500.0,
)

_case(
    "vision_gap_fails_g1",
    "ACTION__MEASURE_BASELINE",
    "S1_UNMEASURED",
    _S8_VISION_GAP,
    failing_half_of="S8_VISION_AUDIO_GAP",
    proposes="UNSET",
    refused_by="G1_BASELINE_MEASURED",
    mints_when={"trivial_baseline_score": 0.30},
)

# THE FIRST OF THE TWO STAGE-9 PROPOSALS, and no gate can refuse it - see the
# header above. The tabular team from NO_TRAIN__RULED_OUT_EARLIER, with sixty
# thousand labelled rows and a machine big enough for a full fine-tune. Stage 8
# struck LORA_SFT and FULL_FINETUNE by name on the way past and then sent the run
# back to be diagnosed as text; stage 5 proposes the LoRA, the size table offers
# the full fine-tune, S9_FULL_FT_JUSTIFIED takes it - and S9_PROPOSAL_WAS_STRUCK
# refuses it by name rather than quietly minting a method this run already ruled
# out.
#
# NO `mints_when`, and that is an answer rather than a missing field. The strike
# lasts the life of the run, so no single fact turns this fact set into a
# training verdict. The counterexample is REACHING's version of the same story
# with 800 examples instead of 60,000: same outcome, same node, but
# `proposed_method` is LORA_SFT there and FULL_FINETUNE here, and that difference
# is what proves S9_FULL_FT_JUSTIFIED did the proposing.
_case(
    "full_ft_is_struck",
    "NO_TRAIN__RULED_OUT_EARLIER",
    "S9_PROPOSAL_WAS_STRUCK",
    _facts(
        REACHING["NO_TRAIN__RULED_OUT_EARLIER"],
        labeled_examples_n=60_000,
        vram_gb=160.0,
        ram_gb=512.0,
        disk_free_gb=8000.0,
        quality_loss_tolerance="small",
    ),
    failing_half_of="S9_FULL_FT_JUSTIFIED",
    proposes="FULL_FINETUNE",
    refused_by="S9_PROPOSAL_WAS_STRUCK",
)

# THE SECOND. Every clause of the from-scratch case holds - no open-weight base
# fits, fifty billion tokens against a 124M-parameter target, and the budget
# clears the file's own price for that size - so S9_FROM_SCRATCH really does
# propose. And the goal is learning, so the answer is still nanoGPT.
#
# Worth being explicit about how this differs from `teaching_from_scratch` above,
# which lands on the same node with the same outcome. There the from-scratch case
# does NOT hold - no_suitable_open_weight_base_exists is false, so S9_FROM_SCRATCH
# never fires and the proposal stays LORA_SFT. Here it fires and is overruled.
# Same answer, opposite reason, and `proposed_method` is the only thing that
# tells them apart: LORA_SFT there, FROM_SCRATCH here. That is the argument for
# asserting the proposal and not only the outcome.
_case(
    "from_scratch_is_taught_instead",
    "TEACH__FROM_SCRATCH_NANOGPT",
    "S9_FROM_SCRATCH_EDUCATIONAL",
    _facts(
        MINTING["TRAIN__FROM_SCRATCH"],
        goal_is_learning=True,
        target_params=124_000_000,
        tokens_available=50_000_000_000,
    ),
    failing_half_of="S9_FROM_SCRATCH",
    proposes="FROM_SCRATCH",
    refused_by="S9_FROM_SCRATCH_EDUCATIONAL",
    mints_when={"goal_is_learning": False},
)

# THE ONE `retriever_fails_g3` DOES NOT COVER. Everything the minting retriever
# fixture has - recall measured at 0.55, a reranker tried, query rewriting tried,
# six thousand labelled query-positive pairs - except that nobody measured an
# off-the-shelf domain embedding model first.
#
# G4 is the only gate that can refuse this proposal, and the node's own condition
# is why: it requires retrieval_tried, reranker_tried and query_rewriting_tried,
# which is precisely the retriever_weights row of G2 and strictly more than the
# retriever_weights row of G3. A run that reaches this node has already answered
# both by construction. So the failing half has to be the one gate that asks
# about something the node does not: is there a domain embedding model on the
# shelf that already does this.
#
# It is also the clearest demonstration of the latching rule in the file. The
# ledger comes back with G2 and G3 PASSED under `retriever_weights` - not under
# the `llm_weights` rows the walk down stage 3 wrote - because the proposal
# changed class at the sweep and both questions were asked again.
_case(
    "retriever_fails_g4",
    "NO_TRAIN__SWAP_MODEL",
    "S6_SWAP_THE_MODEL",
    _facts(MINTING["TRAIN__EMBEDDING_FINETUNE"], model_swap_tried=False),
    failing_half_of="S3_TRAIN_THE_RETRIEVER_NOT_THE_LLM",
    proposes="EMBEDDING_FINETUNE",
    refused_by="G4_CHEAPER_MODEL_CONSIDERED",
    mints_when={"model_swap_tried": True},
)


# ---------------------------------------------------------------------------
# THE NEW TERMINATOR OF STAGE 8, which nothing in the suite reached.
#
# S1_CLOSED_SET_CLASSIFICATION opened a second door into stage_8_classical - text
# and code, not just tabular - and that made S8_TABULAR_UNMATCHED, whose condition
# is `modality == tabular`, stop covering everything that can reach the bottom of
# the stage. S8_TEXT_CLASSIFICATION_NEEDS_LABELS is the terminator now, and the
# spec's own comment names the user it was written for: "a text classifier with
# 60 labels and 500 examples".
#
# This is that user, and until it existed no fact set in the repository reached
# that node. Its outcome already had a fixture - BLOCKED__COLLECT_OR_SYNTHESIZE_DATA
# is reached from stage 5 as well - so the reachability check could not have
# noticed: a terminator can be untested while the outcome it emits is covered
# from somewhere else entirely. Sixty labels needs about five hundred examples per
# label to fine-tune an encoder and it has ten; SetFit wants fifty labels or
# fewer. The honest answer is that there is not enough data yet for either.
_case(
    "text_classifier_between_the_two_encoders",
    "BLOCKED__COLLECT_OR_SYNTHESIZE_DATA",
    "S8_TEXT_CLASSIFICATION_NEEDS_LABELS",
    _facts(
        _ADMISSIBLE,
        _MEASURED_AND_SHORT,
        task_family="classification",
        classes_n=60,
        labeled_examples_n=600,
        labels_are_closed_set=True,
        requires_multistep_reasoning=False,
    ),
)

# THE OTHER TWO TERMINATORS NOTHING REACHED, and they are the same finding twice
# more. A stage's last node is the one that catches every run the nodes above it
# did not, so it is the node whose absence is a stack trace - and all three of
# these were untested while the OUTCOME each emits was covered from somewhere
# else entirely. ACTION__RE_BUCKET_THE_FAILURES has a fixture that reaches it
# from stage 4; BLOCKED__COLLECT_OR_SYNTHESIZE_DATA has one that reaches it from
# stage 5. So the reachability check was green on both, and neither terminator
# had ever run. Covering an outcome is not covering the node that emits it.

# A support team whose retrieval works - recall 0.92 - on a body of knowledge
# that changes slowly. Not fast enough for RAG to be the answer on its own, not
# static enough to be a dialect the weights should learn. Nothing in stage 3 is
# their problem, and the last node of the stage says exactly that: the failures
# were bucketed as missing knowledge and the knowledge is not what is missing.
#
# `knowledge_volatility: slow` is the whole fixture. It is the one member of that
# enum no other fact set uses, and it is the member every node in stage 3 above
# the terminator declines: S3_VOLATILE_KNOWLEDGE wants weekly or faster,
# S3_DOMAIN_DIALECT_GAP and S3_NOT_ENOUGH_DOMAIN_TEXT both want static. An enum
# member that falls between every case is precisely what a stage terminator is
# for, and precisely what nobody writes a fixture for.
_case(
    "knowledge_moves_slowly_and_is_not_the_problem",
    "ACTION__RE_BUCKET_THE_FAILURES",
    "S3_KNOWLEDGE_GAP_IS_NOT_RETRIEVAL",
    _facts(
        _ADMISSIBLE,
        _MEASURED_AND_SHORT,
        need_type=["knowledge"],
        failure_histogram={"wrong_facts": 40},
        knowledge_volatility="slow",
        retrieval_tried=True,
        retriever_recall_at_k=0.92,
        corpus_tokens=5_000_000,
        calls_per_day=5_000,
    ),
)

# The third answer stage 6 can give, and the only one no fixture asked for. A
# team whose model cannot do the reasoning, who have already tried a bigger model
# and already built the scaffold - so every cheap thing stage 6 knows about is
# done - and who have three hundred examples. S6_GENUINELY_ABSENT wants a
# thousand before it will propose anything, so the capability really is absent
# and there is still nothing to train on. That is a blocked answer, not a
# training one, and it is the bottom of the stage.
_case(
    "capability_absent_and_nothing_to_train_on",
    "BLOCKED__COLLECT_OR_SYNTHESIZE_DATA",
    "S6_ABSENT_AND_NO_DATA",
    _facts(
        _ADMISSIBLE,
        _MEASURED_AND_SHORT,
        failure_histogram={"wrong_reasoning": 40},
        model_swap_tried=True,
        agent_scaffold_tried=True,
        task_is_multistep=True,
        labeled_examples_n=300,
    ),
)
