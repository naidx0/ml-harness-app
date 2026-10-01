"""Which approval-gated tools a thread may run without asking, by permission mode.

CS1, 2026-09-14: four ladder steps replace the binary autonomous switch.

  ask      — nothing gated runs without a click
  measure  — scoring / verification sample tools only
  write    — today's UNATTENDED whitelist (additive workspace writes)
  full     — zero-ask bypass: every gated tool except delete_sandbox
             (irreversible wipe). start_training and set_the_project_root
             auto-approve; model may settle ask-facts (see state_facts).

Max's original limits still hold: opt-in per thread, never the default for
destructive or GPU-spending training; every auto-approved call is recorded.
"""

from __future__ import annotations

#: Ladder steps a person can pick. Default is `ask`.
MODES: tuple[str, ...] = ("ask", "measure", "write", "full")

#: Gated tools `write` (and the older autonomous=1 path) may run unattended.
#: Each writes INTO the workspace or a sandbox; none removes; none is paid.
UNATTENDED: dict[str, str] = {
    "carve_rows": (
        "writes new tagged rows into a folder the person named; it creates a "
        "file and never edits the source it read"
    ),
    "drop_duplicates": (
        "writes a deduplicated copy beside the original and reports every "
        "removal; the input file is untouched"
    ),
    "carve_eval_set": (
        "writes two new files and a manifest into a destination that must not "
        "already exist, so it cannot overwrite a split somebody relied on"
    ),
    "run_sandbox_command": (
        "runs a free-text command inside an existing sandbox work dir with "
        "that sandbox's environment; disposable, and the person named the box"
    ),
    "synthesize_rows": (
        "writes generated rows into a new file, every one tagged synthetic; "
        "those rows can never open a gate, which is wall 8's whole point"
    ),
    "draw_verification_sample": (
        "reads a sample out of a file the person already pointed at and "
        "writes the sample beside it"
    ),
    "record_verification": (
        "records what a person found in that sample; it is a row in the "
        "ledger, not an action on the world"
    ),
    "scaffold_the_standing_constraints": (
        "writes the constraints file into the project's own folder, which is "
        "the file the harness maintains there on purpose"
    ),
    "record_a_standing_constraint": (
        "appends one constraint to that same file"
    ),
    "run_in_sandbox": (
        "runs inside the sandbox, which is the isolated, pinned place that "
        "exists so a run has somewhere of its own to write"
    ),
    "score_the_adapter": (
        "generates answers in the sandbox and grades them in this process; it "
        "writes eval rows and nothing outside the sandbox"
    ),
    "score_a_candidate_model": (
        "the same shape as scoring an adapter, for a model nobody trained"
    ),
    "build_environment": (
        "it writes inside a sandbox only - the directory it just made, and "
        "that sandbox's own virtualenv inside it. It touches no recipe's "
        "environment and nothing outside the sandboxes root, and a package "
        "that will not install takes the whole sandbox away again rather than "
        "leaving a half-built one behind"
    ),
    "write_the_results": (
        "it writes results.md, article.md and results.json into a NEW "
        "directory that must not already exist, so it cannot write over "
        "anybody's work; every number in them is read back from what this "
        "thread already measured and nothing is started, spent or removed"
    ),
}

#: Subset of UNATTENDED that `measure` may run — scoring and verification only.
MEASURE: dict[str, str] = {
    name: UNATTENDED[name]
    for name in (
        "draw_verification_sample",
        "record_verification",
        "score_the_adapter",
        "score_a_candidate_model",
    )
}

#: Gated tools that still stop and ask under `write` (and under `ask`).
NEVER_UNATTENDED: dict[str, str] = {
    "delete_sandbox": (
        "it removes a sandbox and every run inside it. Hours of work can end "
        "on one call, and no amount of care afterwards brings them back. A "
        "person says yes to a deletion. The one exception, under full only: a "
        "scratch box this conversation made itself, holding no trained "
        "adapter, on a thread that has measured nothing inside a sandbox."
    ),
    "start_training": (
        "it occupies this machine's GPU for as long as the run takes, and on "
        "rented hardware that is money. Autonomy is for the steps around "
        "training, not for spending the afternoon."
    ),
    "set_the_project_root": (
        "it changes where every later write lands. That is a decision about "
        "the workspace itself rather than a step inside the work, and a "
        "journey that silently re-pointed the project would put files "
        "somewhere the person never chose."
    ),
    "generate_rows": (
        "it has a connected model write a whole dataset - on an API key that "
        "is money, on this machine that is the card - and the rows it writes "
        "are ones nobody has read. What the model is told to invent is a "
        "person's decision, every time."
    ),
    "generate_tool_rows": (
        "it has a connected model propose tool chains and write the questions "
        "they answer - calls on an API key or the card, and rows nobody has "
        "read - and it RUNS the chains it proposes against this project. The "
        "chain is bounded to read-only, approval-free tools, and still what a "
        "dataset teaches is a person's decision, every time."
    ),
    "judge_rows": (
        "it puts every row in front of a connected model, one call per row, "
        "which on an API key is money and on this machine is the card; and "
        "the rubric it judges by is the person's to write, not a default."
    ),
    "run_project_command": (
        "it runs a free-text shell command in the project's own folder, which "
        "can change files outside any sandbox. Under full the person opted "
        "into that; under write it still asks."
    ),
}

#: Under `full`, only irreversible wipe still never auto-approves.
#: Max 2026-09-15: full is zero-ask bypass — training and project-root
#: moves are the person's when they chose full, not further questions.
FULL_NEVER: frozenset[str] = frozenset(("delete_sandbox",))

#: The one exception to FULL_NEVER, and the only one there is.
#:
#: Max, 2026-09-18: under `full`, a thread may throw away ITS OWN scratch box.
#: A run that made somewhere to try something and then cannot tidy it up is a
#: run that stops to ask the person about a directory they never heard of -
#: which is the opposite of what `full` is for, and it is what the record shows
#: happening.
#:
#: NARROW, AND THE NARROWNESS IS THE POINT. Two facts have to be true and
#: neither is this module's to know: the sandbox's manifest must record that
#: THIS thread made it, and nothing measured or trained may live in it.
#: `app/tools/sandbox.deletable_without_asking` reads both off disk and answers
#: with its reason; this module stays what it has always been, a policy table
#: with no imports, and takes that answer as a parameter.
#:
#: DEFAULT FALSE, so every caller that does not ask the question gets the old
#: answer. A rule that opened a delete because somebody forgot to pass an
#: argument would be the wrong way round for the one irreversible tool here.
OWN_SANDBOX_UNDER_FULL: str = "delete_sandbox"


def normalise(mode: str | None) -> str:
    """Unknown or empty → `ask`."""
    m = (mode or "ask").strip().lower()
    return m if m in MODES else "ask"


def autonomous_from_permission(mode: str) -> bool:
    """Derive the legacy `threads.autonomous` bit for one release."""
    return normalise(mode) in ("write", "full")


def covers_for(mode: str) -> dict[str, str]:
    """Tools this mode auto-approves, with reasons."""
    m = normalise(mode)
    if m == "ask":
        return {}
    if m == "measure":
        return dict(MEASURE)
    if m == "write":
        return dict(UNATTENDED)
    # full: every gated name that is classified, minus FULL_NEVER
    out = dict(UNATTENDED)
    for name, reason in NEVER_UNATTENDED.items():
        if name not in FULL_NEVER:
            out[name] = reason
    return out


def never_covers_for(mode: str) -> dict[str, str]:
    """Tools that still ask under this mode (among classified gated tools)."""
    m = normalise(mode)
    if m == "ask":
        return {**UNATTENDED, **NEVER_UNATTENDED}
    if m == "measure":
        out = {n: r for n, r in UNATTENDED.items() if n not in MEASURE}
        out.update(NEVER_UNATTENDED)
        return out
    if m == "write":
        return dict(NEVER_UNATTENDED)
    return {n: NEVER_UNATTENDED[n] for n in FULL_NEVER if n in NEVER_UNATTENDED}


def may_run(mode: str | None, name: str, *, own_sandbox: bool = False) -> bool:
    """May this permission mode auto-approve this tool?

    `own_sandbox` is the caller's answer to the only question that can open
    `delete_sandbox`: is this sandbox one this thread made, with nothing
    measured or trained in it? It is a parameter rather than a lookup because
    this module is a policy table and importing the filesystem into it would
    make the table depend on the machine it is read on. It is ignored for every
    other tool and in every other mode, so a caller that passes it everywhere
    cannot widen anything by accident.
    """
    m = normalise(mode)
    if m == "full" and name == OWN_SANDBOX_UNDER_FULL and own_sandbox:
        return True
    return name in covers_for(m)


def may_run_unattended(name: str) -> bool:
    """Legacy: write-mode whitelist. Prefer `may_run(mode, name)`."""
    return name in UNATTENDED


def why(name: str) -> str | None:
    """The recorded reason, either way, or None for a tool nobody classified."""
    return UNATTENDED.get(name) or NEVER_UNATTENDED.get(name)
