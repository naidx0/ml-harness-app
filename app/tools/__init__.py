"""The tools the harness has, and the seed three that make the loop real.

Importing this package is what makes the tools exist - each one registers onto
`registry.REGISTRY` at import time, and `app/main.py` and `app/conductor.py`
both import from here rather than building their own list. One registry, one
truth about what the product can do.

Three tools ship first, chosen so the loop is exercisable end to end rather
than for coverage:

- **`inspect_hardware`** - the "look before you ask" rule (§9.3) needs
  something to look with, and this is the cheapest possible demonstration that
  a number reaching the user came from a measurement.
- **`run_diagnosis`** - the product's actual verdict. It is the reason the
  hard rule in `registry.py` exists, and it is the tool that proves a model can
  fill facts without deciding anything.
- **`list_runs`** - the transcript's link to work that already happened.

Every result carries its provenance where it carries a number, because
invariant 3 says a number with no provenance does not get displayed and the
tool result is where the number enters the conversation.

## The stamps, and why they are here rather than in a docstring

`inspect_hardware` and `run_diagnosis` are the two ends of the fact-origin
story, so they are worth reading together.

`inspect_hardware` MEASURES. It hands `hwdetect`'s per-field provenance to
`instrument.measured()` and stamps only the fields that came back `measured` -
a GPU nobody could read is not stamped at all, because a defaulted number
wearing a measurement badge is worse than no number.

`run_diagnosis` MEASURES NOTHING, and that is a structural property rather than
a description: it declares `measures=()`, so the instrument it is handed cannot
stamp anything, and the facts a model sends it are worth whatever the ACTOR is
worth - `ASSERTED` for a model, `STATED` for the person who clicked the control.
The engine then refuses to open a gate on an origin the ledger does not admit,
and this tool reports back exactly which fact was not good enough and which tool
would settle it.
"""

from __future__ import annotations

import json
from typing import Any

from app import db, diagnosis, full_defaults, hwdetect
from app.tools import evidence, next_moves
from app.tools.evidence import GeneratedRowsError, Instrument, MeasurementError
from app.tools.registry import (  # noqa: F401 - re-exported for callers
    ApprovalRequired,
    Control,
    Registry,
    ToolError,
    ToolSpec,
    REGISTRY,
    tool,
)


@tool(
    "inspect_hardware",
    description=(
        "Read this machine's processor, graphics card, video memory, system "
        "memory and free disk. Returns every value with its provenance: "
        "measured, inferred or defaulted. Use this instead of asking the user "
        "what hardware they have."
    ),
    schema={"type": "object", "properties": {}},
    reads=("hardware",),
    writes=(),
    measures=("ram_gb", "vram_gb", "disk_free_gb", "accelerator"),
    provides=("machine.hardware.inspect",),
    label="Inspect hardware",
    group="Look",
    verb="read this machine's hardware",
    order=10,
)
def inspect_hardware(*, instrument: Instrument) -> dict[str, Any]:
    """What is actually in this machine, and where each figure came from.

    `hwdetect.local_specs()` already refuses to invent a number - an
    undetectable GPU comes back as `None` with `defaulted` provenance rather
    than as a plausible card. That refusal is the whole value of the tool, so
    it is passed through unchanged rather than tidied into something that reads
    better.

    AND ONLY WHAT IT ACTUALLY MEASURED IS STAMPED. `local_specs()` reports each
    field as `measured`, `inferred` or `defaulted`; only the first is handed to
    `instrument.measured()`. A machine whose GPU could not be read contributes
    no `vram_gb` at all rather than a stamped 0, because "the tool ran and found
    nothing" and "the tool did not run" are the same state of knowledge and the
    engine already has a word for it.

    `accelerator` is stamped only from a reading, never from a guess: an
    `nvidia-smi` line that names a card is a measurement that this box has an
    NVIDIA accelerator. A machine we could not read is left for the user to
    answer, which is what the ledger's `fallback: ask` means.
    """
    specs = hwdetect.local_specs()
    provenance = specs.get("provenance") or {}
    sources = specs.get("sources") or {}

    def was_measured(field: str) -> bool:
        return provenance.get(field) == "measured"

    for field in ("ram_gb", "vram_gb", "disk_free_gb"):
        value = specs.get(field)
        if was_measured(field) and isinstance(value, (int, float)):
            instrument.measured(
                field,
                float(value),
                how=f"read from {sources.get(field, 'this machine')}",
            )

    name = str(specs.get("gpu_name") or "").lower()
    if was_measured("gpu_name") and name:
        vendor = None
        if "nvidia" in name or "geforce" in name or "quadro" in name or "tesla" in name:
            vendor = "nvidia"
        elif "apple" in name:
            vendor = "apple_silicon"
        elif "radeon" in name or "amd" in name:
            vendor = "amd"
        if vendor:
            instrument.measured(
                "accelerator",
                vendor,
                how=(
                    f"{sources.get('gpu_name', 'the machine')} named "
                    f"{specs.get('gpu_name')!r}"
                ),
            )

    return specs


def _is_full(thread_id: int | None) -> bool:
    """Is this thread the zero-ask bypass? `app/autonomy.py` owns the word."""
    if thread_id is None:
        return False
    try:
        from app import autonomy, events as _events

        row = _events.get_thread(int(thread_id)) or {}
        return autonomy.normalise(str(row.get("permission") or "ask")) == "full"
    except Exception:  # noqa: BLE001 - a permission that cannot be read is not full
        return False


@tool(
    "run_diagnosis",
    description=(
        "Run the harness diagnosis over a sheet of facts and return the "
        "verdict, the five-gate ledger and the path taken. You supply facts "
        "only. You do not decide any gate and you cannot: the engine walks the "
        "tree itself. Facts must be names declared in the harness fact ledger; "
        "anything else is rejected. Facts YOU supply are recorded as ASSERTED "
        "and cannot open a gate on their own - a gate opens on a fact the "
        "harness measured with a tool, or on one the user said themselves. "
        "Anything already measured in this thread is merged in for you, so "
        "there is nothing to be gained by repeating a number back. If the "
        "answer says a fact is unsubstantiated, it also says which tool would "
        "settle it: run that tool, then run this again."
    ),
    schema={
        "type": "object",
        "properties": {
            "facts": {
                "type": "object",
                "description": (
                    "OPTIONAL, and it cannot open a gate. What tools have "
                    "already measured in this thread is merged in for you, "
                    "and that is the only thing a gate opens on. Facts you "
                    "send are ASSERTED - a claim, not a reading. Send none "
                    "to see where the thread stands. Names must be declared "
                    "facts (goal_text, target_score, task_family...); a gate "
                    "id is not a fact name."
                ),
                "additionalProperties": True,
            }
        },
    },
    reads=("facts",),
    writes=(),
    provides=("ledger.diagnosis.run",),
    label="Run the diagnosis",
    group="Decide",
    verb="run the diagnosis on the facts so far",
    order=20,
)
def run_diagnosis(
    facts: dict[str, Any] | None = None,
    *,
    instrument: Instrument,
    ledger: diagnosis.Spec,
) -> dict[str, Any]:
    """Facts in, verdict out - and the verdict is computed here, never supplied.

    `writes` is empty on purpose. This tool produces a diagnosis; it does not
    write one. Nothing it returns is persisted as a decision by the act of
    calling it, so a model calling it forty times cannot accumulate authority.

    `diagnosis.validate_facts` raises on any key that is not a declared fact,
    which is the third wall described in `registry.py`: gate ids are not facts,
    so there is no key a model could send that names one.

    `measures=()`, WHICH IS THE OTHER HALF OF THE SAME SENTENCE. This tool is
    handed an instrument, because it needs to know what actor is calling, and
    that instrument can stamp nothing at all. So the facts arriving in
    `arguments` are worth exactly what their speaker is worth - a model's are
    ASSERTED - and there is no code path from here to a MEASURED stamp. What
    gets merged on top of them is what tools already measured in this thread,
    which is the only way a gate ever opens.
    """
    supplied = dict(facts or {})
    try:
        # `persist=True`: THIS is the walk the conductor's turn goes through,
        # and the one caller allowed to make a correction the walk finds
        # durable (`evidence._a_modality_the_file_contradicts`). Every read
        # route calls `assemble_facts` without it and writes nothing.
        sheet, trail = evidence.assemble_facts(
            instrument.thread_id, supplied, instrument.actor, ledger=ledger,
            persist=True,
        )
        # THE LEDGER THIS THREAD IS RUNNING, NOT THE ONE THE MODULE DEFAULTS TO.
        # `diagnose(sheet)` fell back to `default_spec()`, so a thread that had
        # said it was an AI-engineering thread got the ML tree walked over its
        # facts - and `validate_facts` would have refused every one of them
        # first, with a sentence naming a file it was never asking about.
        result = diagnosis.diagnose(sheet, ledger)
    except diagnosis.FactError as error:
        # The same door as `state_facts`, for the same reason: a refusal that
        # names nothing costs a tool round and teaches the caller nothing. See
        # `evidence.fact_name_help`, which answers out of the ledger rather than
        # out of a list maintained here.
        return {
            "ok": False,
            "error": "rejected_fact",
            "detail": str(error),
            **evidence.fact_name_help(supplied, ledger=ledger),
            "for_this_tool": (
                "Send only facts you have actually established. Anything already "
                "measured in this thread is merged in for you."
            ),
        }
    except diagnosis.EngineError as error:
        return {"ok": False, "error": "engine_error", "detail": str(error)}
    except evidence.MeasurementError as error:
        # Wall 3 answering: a minting tool asked for the claim ledger. This tool
        # measures nothing, so it cannot be that - but `assemble_facts` is the
        # one call here that can raise it and a caught exception with a message
        # beats an uncaught one without.
        return {"ok": False, "error": "measurement_refused", "detail": str(error)}
    except Exception as error:  # noqa: BLE001 - see below
        # THE NET, AND WHY A TOOL IS ALLOWED ONE HERE WHEN THE ENGINE IS NOT.
        #
        # `app/diagnosis.py` rejects a malformed fact as a `FactError`, and a
        # `FactError` is a sentence: "need_type must be one of ...". That is the
        # contract, and the two branches above are it working. It was not
        # working: `{"need_type": 5}` raised a raw `TypeError` from inside
        # `_coerce`, no handler in this stack was looking for one, and it left
        # the ASGI app as an unhandled 500 with a traceback. A 200,000-draw fuzz
        # found 763 crashes and every one of them was that signature.
        #
        # The cause is fixed where it belongs, in `_coerce`. This is the second
        # line, and it is here rather than inside `diagnose()` on purpose: the
        # engine must keep raising loudly so that tests/test_diagnosis_no_crash
        # can fail on it, and it is the PRODUCT BOUNDARY that must never hand a
        # person a stack trace. Both, not one.
        return {
            "ok": False,
            "error": "engine_failed",
            "detail": f"{type(error).__name__}: {error}",
            "help": (
                "The diagnosis could not be computed from these facts. Nothing "
                "was recorded and no gate was decided. This is a defect in the "
                "harness rather than something to answer differently - the facts "
                "sent are in the transcript above."
            ),
        }

    # NOTHING IS WRITTEN HERE, and `writes=()` above is therefore true rather
    # than aspirational. The facts in this call are worth what this caller is
    # worth and they last exactly as long as this call. What the model claimed
    # is already in the transcript - `tool.call` carries the arguments verbatim -
    # so recording them again would buy nothing and would let a claim made three
    # turns ago outlive the sentence it was part of. Deliberate answers go in
    # through `state_facts`, where saying so is the act.
    payload = {
        "ok": True,
        # FIRST, AND THAT IS THE POINT. MEASURED 2026-09-13: the next-move
        # sentence was field fifteen of an eighteen-field result and the
        # owner's model ran fourteen more lookups without acting on it. A
        # dict preserves its order through JSON, so the one line that says
        # what to do next is the first line the model reads. Filled in below;
        # left empty when the walk has nothing to ask for.
        "next": "",
        "outcome": result.outcome,
        "verdict": result.verdict,
        "say": result.say,
        "proposed_method": result.proposed_method,
        "gate_ledger": result.gate_ledger,
        "path": [entry.as_dict() for entry in result.path],
        "constraints": sorted(result.constraints),
        "struck_methods": sorted(result.struck_methods),
        "cost_provenance": result.cost_provenance,
        "fact_origins": result.fact_origins,
        "facts_used": {
            row["fact"]: {
                "value": row["value"],
                "origin": row["origin"],
                "how": row["how"],
            }
            for row in trail
        },
        "your_facts_were_recorded_as": instrument.supplied_origin,
        "decided_by": "app/diagnosis.py",
    }

    # A GATE WHOSE FACTS ARE MEASURED BUT WHICH THE WALK NEVER REACHED, SAID.
    # Max's run of 2026-09-21: measure_baseline returned baseline_measured:
    # true, run_diagnosis showed G1 NOT_REACHED, and the model reported "a
    # discrepancy" in the engine's tracking. There was none: G1 sits in stage
    # 1, below S0_MODALITY_FORK, and the walk had stopped at a node above it,
    # so the gate was never asked. NOT_REACHED is the true status and stays;
    # what was missing is the sentence joining the two readings, so a gate
    # whose every fact is already MEASURED names the node the walk stopped at.
    stopped_at = next(
        (entry["id"] for entry in reversed(payload["path"]) if entry.get("kind") != "gate"),
        None,
    )
    held_above: dict[str, str] = {}
    for (gate_id, _row), needs in (getattr(ledger, "gate_row_facts", None) or {}).items():
        status = (result.gate_ledger.get(gate_id) or {}).get("status")
        if status != "NOT_REACHED" or gate_id in held_above or not needs:
            continue
        if all(result.fact_origins.get(name) == diagnosis.MEASURED for name in needs):
            held_above[gate_id] = (
                f"{gate_id}'s facts ({', '.join(sorted(needs))}) are measured, but the walk "
                f"stopped at {stopped_at or 'a node above it'} before reaching this gate. "
                "NOT_REACHED means not asked yet, not failed: settle what that node is "
                "waiting on and the gate is asked on the next walk."
            )
    if held_above:
        payload["measured_but_not_reached"] = held_above

    # THE TWO FIELDS THE CARD WAS DRAWING AS NAMED ABSENCES.
    #
    # `contract.diagnosis` requires `revisit_if` alongside every verdict and
    # graphite 23.4 wants three controls that start the alternative work.
    # Neither was on the wire, so `DiagnosisCard.tsx` drew a sentence saying so
    # rather than inventing either - which was the right call and is now the
    # wrong output. Both are derived in `app/tools/next_moves.py` from the
    # spec's own words and the registry's own `measures=` declarations; nothing
    # is authored beside the engine and nothing here can fail the diagnosis.
    #
    # Wrapped, because a derivation defect must not cost the verdict. The
    # verdict is the product; these two fields are how it is read. If the
    # derivation raises, the payload goes out without them and says why, which
    # is the state the card already knows how to render.
    try:
        payload.update(
            next_moves.next_moves(
                result, facts_used=payload["facts_used"], spec=ledger
            )
        )
    except Exception as error:  # noqa: BLE001 - see the paragraph above
        payload["revisit_if"] = []
        payload["alternatives"] = []
        payload["next_moves_failed"] = f"{type(error).__name__}: {error}"

    # THE NEXT MOVE, NAMED - AND THE GAP NAMED FIRST.
    #
    # MEASURED, 2026-09-13, on the owner's thread: the walk stopped at a node
    # reading `task_family` and `modality`, two facts NO tool in this harness
    # measures. `asking.frontier` knew that exactly - it carries them as
    # `gaps`, each with the sentence saying why nobody can collect it - and
    # this tool threw that away and returned the next ANSWERABLE question
    # instead (`classes_n`, settled by assess_the_data). So the model ran
    # assess_the_data, the fact it settled was not the fact the walk stopped
    # on, the verdict did not move, and it went round again. Ten turns, zero
    # steps ticked, the model writing "the engine is stuck in a loop" - and
    # it was right.
    #
    # A gap is a hard stop and a question is not, so the gap is named first,
    # with the door out of it: say the fact yourself with `state_facts`. And
    # a remedy already spent in this thread is never offered a second time -
    # that is the other half of the loop.
    from app import asking

    if ledger.as_written == asking.the_ledger_this_module_is_written_for().as_written:
        try:
            already = evidence.tools_already_run(instrument.thread_id)
            edge = asking.frontier(result)
            # A GAP THE WALK HIT FIRST OUTRANKS A QUESTION FURTHER DOWN.
            # `first_answerable` prefers an entry something can be RUN for,
            # which is right when the choice is between two measurable things
            # and wrong when the earliest blocker is one nothing measures: the
            # model has to decide `task_family` itself, and a walk that steps
            # over it to ask for a bar two nodes later is asking a question
            # whose answer the earlier one shapes.
            #
            # It only became visible on 2026-09-19. The first entry used to
            # carry `classes_n` as well - a measurable fact, so the entry was
            # answerable and got picked with its gap attached - and now that
            # the asker reads what the condition actually reached, the entry
            # carries the gap alone and was being skipped.
            first = edge.entries[0] if edge.entries else None
            entry = first if (first is not None and first.gaps) else (
                edge.first_answerable or first
            )
            gaps = [gap for gap in getattr(entry, "gaps", ()) if gap.fact not in sheet] if entry else []
            # AN INSPECT GAP IS NOT A DECISION, SO IT DOES NOT OUTRANK A
            # QUESTION. The rule above is for a gap the model must decide
            # (`task_family`); a fact the ledger declares `source: inspect` and
            # nothing registered reads is one the model may not state and no
            # tool can settle. Thread 93 on 2026-09-23, once its modality was
            # honest, stopped at ACTION__CLASSIFY_FAILURES and the gap-first
            # rule named `data_quality` - a dead end - over `failure_histogram`,
            # which `rebucket_failures` settles. Such a gap still stands in the
            # walk; it is the move only when there is no question to ask
            # instead, and then its sentence below says it is not stated.
            step = asking.next_step(result=result)
            card = step.question if step.kind == asking.QUESTION else None
            decidable = [
                gap for gap in gaps
                if (ledger.facts.get(gap.fact) or {}).get("source") != "inspect"
            ]
            if decidable or card is not None:
                gaps = decidable

            def _full_prerequisite(fact: str) -> tuple[str, str] | None:
                """Under Full, the tool that must run before a rule can settle
                `fact` - for a GAP as much as for a question.

                `full_defaults._from_the_eval_file` derives `task_family` and
                `modality` by reading the eval file, so on a Full thread with
                no eval set the honest move is "count one", not "decide it
                yourself". A gap is a fact no tool MEASURES; that is not the
                same as a fact the harness cannot work out.

                AND FOR A `derive` FACT, UNDER EVERY PERMISSION, because the
                harness derives those wherever the eval file can be read
                (`full_defaults.settle`). Telling a thread on `ask` to decide
                `modality` itself while the file that answers it is one
                count away was the owner's loop of 2026-09-21."""
                derived = (ledger.facts.get(fact) or {}).get("source") == "derive"
                if not derived and not _is_full(instrument.thread_id):
                    return None
                return full_defaults.prerequisite_for(fact, payload)

            if gaps:
                gap = gaps[0]
                accepts = (gap.declared or {}).get("accepts") or {}
                choices = accepts.get("one_of") or []
                payload["gaps"] = [
                    {"fact": g.fact, "why": g.settled_by.get("note") or g.reason, "accepts": (g.declared or {}).get("accepts")}
                    for g in gaps
                ]
                payload["next_step"] = {
                    "kind": "gap",
                    "fact": gap.fact,
                    "tool": "state_facts",
                    # So the next-move line never sends an inspect fact to
                    # state_facts; see the question branch below.
                    "source": (ledger.facts.get(gap.fact) or {}).get("source"),
                }
                #: MEASURED 2026-09-13, the second run: told to record the
                #: fact, the model called `state_facts` with `{"facts": {}}` -
                #: it had learnt the door and not what to put through it. An
                #: ellipsis is not an example. The sentence now carries a
                #: whole call with a real value in it.
                example = str(choices[0]) if choices else "your answer"
                if payload["next_step"]["source"] == "inspect":
                    # NOT "DECIDE IT AND STATE IT". The ledger says this fact
                    # is read off the data and the brief says an inspect fact
                    # is not stated; telling the model to state it is the
                    # contradiction thread 93 looped on, in the gap's words.
                    payload["next_step"]["tool"] = None
                    payload["next"] = (
                        f"Blocked on `{gap.fact}`, which the ledger says is read off the "
                        "data (source: inspect), and nothing registered in this harness "
                        "reads it yet. It is not something to state - a stated value opens "
                        "no gate - and no tool you can run will settle it. Say in one line "
                        f"that {gap.fact} cannot be measured here, and work the next step "
                        "of the plan."
                    )
                else:
                    payload["next"] = (
                        f"Blocked on `{gap.fact}`, and NOTHING in this harness measures it - "
                        "no tool will ever settle it, so running one more is the loop. "
                        "Decide it yourself from what you have already read"
                        + (f". It must be one of: {', '.join(str(c) for c in choices)}" if choices else "")
                        + ". Then call state_facts with EXACTLY this shape, your value in place of "
                        + f'the example: {{"facts": {{"{gap.fact}": "{example}"}}}} - and run '
                        "run_diagnosis again after it. An empty facts object records nothing "
                        "and leaves this verdict where it is."
                    )
                # UNDER FULL, A GAP THE HARNESS CAN WORK OUT IS NOT A DECISION.
                # `full_defaults._from_the_eval_file` reads the eval file's own
                # answers to tell extraction from classification from
                # generation, so on a Full thread with no eval set the move is
                # to count one - and then the family is derived rather than
                # guessed. `kind` stays `gap` and the `gaps` list still
                # reaches the model; what changes is the tool and the sentence.
                gap_ahead = _full_prerequisite(gap.fact)
                if gap_ahead is not None:
                    first_tool, why = gap_ahead
                    payload["next_step"]["tool"] = first_tool
                    payload["next"] = (
                        f"Blocked on `{gap.fact}`. No tool measures it, but the harness "
                        f"derives it rather than asking you - once {why}. Run "
                        f"{first_tool} now, then run_diagnosis again. If you would rather "
                        f'decide it yourself, state_facts({{"facts": {{"{gap.fact}": '
                        f'"{example}"}}}}) still settles it.'
                    )
            elif card is not None:
                tool = (evidence.resolves(card.fact, ledger) or {}).get("tool")
                because = card.because.as_dict() if card.because is not None else {}
                spent = bool(tool) and tool in already
                payload["next_step"] = {
                    "kind": "question",
                    "fact": card.fact,
                    "tool": tool,
                    "asks": because.get("asks") or "",
                    "unblocks": because.get("unblocks") or "",
                    "already_run": spent,
                }
                # AN INSPECT FACT IS READ OFF A FILE, SO THE MOVE NAMES THE FILE.
                # The owner's thread 93, 2026-09-23: stopped on `tabular_rows`
                # (`source: inspect`), `profile_dataset` spent on the EVAL file,
                # and every sentence below this said "record it with
                # state_facts" - the one thing the standing brief forbids for an
                # inspect fact. The model looped between the two for 471
                # reasoning events. `source` travels so the next-move line can
                # tell an inspect fact from an ask one; `on` is what to point
                # the instrument at, for an instrument that reads the TRAINING
                # data (it provides a `data.dataset.*` capability, which is the
                # registry's own word for that): the training split the thread
                # has already named, or "the training file" when it has named
                # none. An instrument that reads the machine or the eval set
                # gets no `on`, because "the training file" would be false.
                card_source = (ledger.facts.get(card.fact) or {}).get("source")
                payload["next_step"]["source"] = card_source
                card_on: str | None = None
                instrument_spec = REGISTRY.get(str(tool)) if tool else None
                if card_source == "inspect" and instrument_spec is not None and any(
                    str(capability).startswith("data.dataset.")
                    for capability in (instrument_spec.provides or ())
                ):
                    from app.tools import measure as _measure

                    named = _measure.training_file_on_record(instrument.thread_id)
                    card_on = named[0] if named else "the training file"
                    payload["next_step"]["on"] = card_on
                # ONE SHAPE FOR THE CALL, THE ONE THE TOOL ACCEPTS. These two
                # sentences used to print `state_facts({'privacy': ...})` - no
                # `facts` wrapper and an ellipsis for a value - while the gap
                # branch above printed {"facts": {...}}, so the same reply
                # taught two shapes and one of them was refused. Max's run of
                # 2026-09-21 spent rounds between them.
                card_choices = list(
                    ((ledger.facts.get(card.fact) or {}).get("enum")) or ()
                )
                card_example = str(card_choices[0]) if card_choices else "<your answer>"
                card_call = json.dumps({"facts": {card.fact: card_example}})
                card_one_of = (
                    f" It must be one of: {', '.join(str(c) for c in card_choices)}."
                    if card_choices
                    else ""
                )
                if spent and card_source == "inspect":
                    # Never "record it with state_facts": the ledger says an
                    # inspect fact is read, and the brief says it is not stated.
                    payload["next"] = (
                        f"`{tool}` has run in this conversation and `{card.fact}` is still "
                        f"unread. `{card.fact}` is read off the file by {tool}, not stated: run "
                        f"{tool} on {card_on or 'the file it is read from'}, then run_diagnosis "
                        "again. If it already read that file and the fact is still unread, say "
                        "in one line why and work the next step of the plan instead."
                    )
                elif spent:
                    payload["next"] = (
                        f"`{tool}` has already run in this conversation and `{card.fact}` is still "
                        "unanswered, so running it again returns this same verdict. Either record "
                        f"the value with state_facts, exactly this shape: {card_call}, from what "
                        "that run showed you, or say in one line why it cannot be settled here and "
                        "work the next step of the plan instead." + card_one_of
                    )
                elif tool == "state_facts":
                    # The tool that settles this fact IS the recording door,
                    # and "run state_facts - it measures it from this machine"
                    # was a false sentence about it.
                    payload["next"] = (
                        f"Blocked on `{card.fact}`, which is said rather than measured. Record "
                        f"it with state_facts, exactly this shape, your value in place of the "
                        f"example: {card_call}.{card_one_of} Then run_diagnosis again."
                    )
                elif tool:
                    payload["next"] = (
                        f"Blocked on `{card.fact}`. Run {tool}"
                        + (f" on {card_on}" if card_on else "")
                        + " - it measures it from this "
                        "machine - and then run_diagnosis again. Running run_diagnosis "
                        "again before that returns this same verdict."
                    )
                else:
                    payload["next"] = (
                        f"Blocked on `{card.fact}`, which no tool in this harness measures. "
                        f"Record it with state_facts, exactly this shape: {card_call}, from what "
                        "you have read, or ask the person for exactly that one thing." + card_one_of
                    )

                # AND UNDER FULL, GO AND MAKE THE THING. Max, 2026-09-19: "An
                # eval set exists - if it sees an eval set doesn't exist, GO
                # MAKE AN EVAL SET. A baseline hasn't been measured - GO MAKE A
                # BASELINE." The harness sets `target_score` by rule, and the
                # rule needs a measured baseline; the node that sends anybody
                # to measure one is a stage below a terminal the walk never
                # reaches, so the thread asked for the bar, failed to default
                # the bar, and said "run state_facts" a dozen times.
                #
                # ONLY UNDER FULL, because the promise is a Full-mode promise:
                # under Ask there is no rule waiting to fire and "it is settled
                # from the measurement" would be untrue. The branch above keeps
                # its `kind` and its `fact` - a gap is still a gap, and the
                # `gaps` list still reaches the model - and what changes is the
                # tool named and the sentence saying why.
                ahead = None
                if _is_full(instrument.thread_id):
                    ahead = _full_prerequisite(card.fact)
                if ahead is not None:  # noqa: SIM102 - read with the block below
                    first, why = ahead
                    payload["next_step"]["tool"] = first
                    payload["next_step"]["already_run"] = first in already
                    payload["next"] = (
                        f"Blocked on `{card.fact}`, and the harness sets it by rule once it "
                        f"has something to compute from - but {why}. Run {first} now, then "
                        "run_diagnosis again. Do not ask the person for the number: under "
                        "Full it is settled from the measurement."
                    )
            elif step.kind == asking.PROPOSE:
                payload["next_step"] = {"kind": "propose"}
                payload["next"] = "Every question the walk asks is answered; the next move is propose_build."
        except asking.AskingError as error:
            payload["next_step_failed"] = str(error)

    if result.unsubstantiated:
        payload["unsubstantiated"] = [
            dict(row, next_step=evidence.resolves(row["fact"], ledger))
            for row in result.unsubstantiated
        ]
        payload["help"] = (
            "This run was not refused. It was stopped at a fact nobody can vouch "
            "for. Each row above names the tool that would settle it - run it, "
            "then run the diagnosis again."
        )
    return payload


@tool(
    "what_is_missing",
    #: SHORT ON PURPOSE, AND THE LENGTH IS A MEASURED CONSTRAINT. This tool is
    #: core, so its description is paid on every turn. The first version ran to
    #: 644 characters against a median of 345 and pushed
    #: `ACTION__SUBSTANTIATE_CLAIMED_FACTS` to 4,606 tokens against a 4,600
    #: budget - six over. Raising the budget to fit a tool is the one move
    #: `docs/PHASES.md` forbids by name; the description was the thing that was
    #: wrong.
    description=(
        "Ask what the harness still needs and get back ONE question. Call it "
        "first, and again after every answer, until it stops asking. It returns "
        "the single fact that would move this thread: what it is, why it is "
        "asked in the ledger's own words, and - when the harness must measure "
        "the fact rather than be told it - the tool that would settle it. "
        "Records nothing. When it has no question left, there is something to "
        "propose."
    ),
    schema={"type": "object", "properties": {}, "additionalProperties": False},
    reads=(),
    writes=(),
    provides=("ledger.asking.next_step",),
    label="Ask what is missing",
    group="Decide",
    #: THE BRIEF IS ONE LINE PER TOOL - `f"{name} - {verb}"` - and a core tool's
    #: line is paid on every turn. The first verb ran to 32 characters and put
    #: `ACTION__SUBSTANTIATE_CLAIMED_FACTS` six over its 4,600 budget and ten
    #: over the scoped 2,400. Raising a budget to fit a tool is the move
    #: `docs/PHASES.md` forbids by name, so the line got shorter instead. It
    #: also reads better: the name already says what is missing, so the verb
    #: should say what you get.
    verb="get the next question",
    #: BEFORE `run_diagnosis` (20) ON PURPOSE. A caller who runs the diagnosis
    #: first gets five gates reading NOT_REACHED and nothing to do about it;
    #: this says which single fact is in the way.
    order=10,
)
def what_is_missing(
    *, instrument: Instrument, ledger: diagnosis.Spec
) -> dict[str, Any]:
    """The question that would move this thread, derived from the ledger.

    ## WHY THIS EXISTS, AND IT IS NOT NEW MACHINERY

    `app/asking.py` already derives the whole thing - which fact, what it
    accepts, which node or gate it unblocks, and for a `source: inspect` fact
    the tool that measures it instead of a field to type in. It has been served
    at `GET /api/next_step` since it was written.

    **It was not a tool.** Measured 2026-09-09: 67 tools registered, all 67
    offered to a model, and not one of them the asker. So a model ran
    `run_diagnosis`, got five gates reading NOT_REACHED, and had sixty-seven
    doors and no way to learn which one. That is the whole of the owner's
    complaint that the harness *"throws tools in your face"* - the intake was
    built and unreachable from the surface a model actually sees.

    This registers it. There is no derivation here; every sentence in the
    answer comes out of `asking.py` and the ledger.

    ## WHAT IT MAY NOT DO

    **It takes no arguments, and that is structural rather than tidy.** A
    caller who could pass facts here could move the frontier by asserting
    things and so choose which question the person is shown. Facts go in
    through `state_facts` and `run_diagnosis`, where the boundary decides what
    a caller's word is worth. This one reads what is already established and
    nothing else.

    `writes=()` and `measures=()`: it opens no gate, stamps nothing, and
    calling it forty times accumulates no authority.
    """
    #: LOCAL, BECAUSE `asking` IMPORTS THIS REGISTRY. `app/asking.py` line 163
    #: does `from app.tools import REGISTRY, evidence` at module level, so
    #: importing it at the top of this file is a cycle. `asking.py` already
    #: solves the mirror image of this at its line 1222 - a local import of
    #: `propose`, with the same one-line reason - so this follows the house's
    #: own answer rather than inventing a second one.
    #:
    #: FOUND BY CALLING THE TOOL, NOT BY REGISTERING IT. The decorator validates
    #: the spec and never runs the body, so `what_is_missing` registered
    #: perfectly and raised `NameError: name 'asking' is not defined` the first
    #: time anything called it.
    from app import asking

    #: WHICH LEDGER THIS CONVERSATION IS RUNNING, ASKED FIRST. `asking.py` is
    #: written for one ledger and says so in `_spec`. `GET /api/next_step`
    #: already refuses a thread running another domain's tree, because before
    #: 2026-08-27 it answered one - handing an AI-engineering thread an outcome
    #: from the ML tree, a fact its ledger has never heard of, and a card naming
    #: a tool that could not measure anything in it. A tool is a wider door than
    #: a route, so it refuses on the same terms rather than a looser set.
    #: ASKED OF `asking`, NOT DERIVED HERE. `default_spec()` read from this file
    #: would make it the fourteenth entry in the census
    #: `tests/test_the_default_ledger_is_a_bounded_debt.py` keeps - a new file
    #: coupling to the first ledger, which is the event that test exists to
    #: catch. It would also be a SECOND definition of asking's own limit, free
    #: to drift from it the day that module stops defaulting.
    mine = asking.the_ledger_this_module_is_written_for().as_written
    running = ledger.as_written
    if running != mine:
        return {
            "ok": False,
            "error": "wrong_ledger",
            "detail": (
                f"This conversation is running {running}, and the next-question "
                f"machinery is written for {mine}. It would have answered - with "
                "an outcome from the other domain's tree, asking for a fact your "
                "ledger does not declare, and naming a tool that cannot measure "
                "anything in it. Nothing was recorded and no question is offered."
            ),
            "instead": (
                "Run `run_diagnosis` for this thread, which reads the ledger this "
                "conversation is actually running."
            ),
        }

    try:
        sheet, _trail = evidence.assemble_facts(
            instrument.thread_id, {}, instrument.actor, ledger=ledger
        )
        step = asking.next_step(result=diagnosis.diagnose(sheet, ledger))
    except asking.AskingError as error:
        #: A DEFECT IN THE HARNESS, SAID AS ONE. The ledger and the registry
        #: disagree about a fact. That is not something the caller can answer
        #: differently, and a card derived from a disagreement would be a
        #: confident question about the wrong thing.
        return {
            "ok": False,
            "error": "cannot_derive",
            "detail": (
                f"the next question could not be derived: {error}. That is a "
                "defect in the harness, not in the request. Nothing was recorded."
            ),
        }
    except diagnosis.EngineError as error:
        return {"ok": False, "error": "engine_error", "detail": str(error)}
    except evidence.MeasurementError as error:
        return {"ok": False, "error": "measurement_refused", "detail": str(error)}

    payload: dict[str, Any] = {"ok": True, **step.as_dict()}
    question = payload.get("question") or {}
    #: WHERE THE ANSWER GOES, NAMED BY THE TOOL THAT WILL NOT TAKE IT. A caller
    #: reading this should not have to infer from the absence of an argument
    #: that there is another door.
    payload["answer_through"] = {
        "tool": question.get("accepts", {}).get("measured_by")
        or ("state_facts" if question else None),
        "why": (
            "A fact the harness must measure is settled by running that tool and "
            "pointing it at something. A fact you are entitled to state is "
            "settled through `state_facts`, where saying it is the act."
        ),
    }
    if not question:
        payload["help"] = (
            "Nothing is missing. There is no question left to ask, so the next "
            "move is to propose rather than to gather."
        )
    return payload


@tool(
    "list_runs",
    description=(
        "List the training runs recorded on this machine, newest first, with "
        "their status. Use it to answer 'how did that go' without asking the "
        "user to remember."
    ),
    schema={
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "How many runs to return. Default 20.",
            }
        },
    },
    reads=("runs",),
    writes=(),
    provides=("machine.runs.list",),
    label="List runs",
    group="Look",
    verb="list the runs on this machine",
    order=30,
)
def list_runs(limit: int = 20) -> dict[str, Any]:
    try:
        bound = max(1, min(int(limit), 200))
    except (TypeError, ValueError):
        bound = 20
    runs = db.list_runs()
    return {
        "count": len(runs),
        "returned": min(len(runs), bound),
        "runs": runs[:bound],
        "provenance": {"count": "measured", "returned": "measured"},
        "source": "the runs table in this harness database",
    }


# Importing a tool module is what registers its tools. These live in their own
# files because "search the Hub and rank by fit" and "launch a training run"
# are each larger than the three seed tools put together, and a registry file
# that grows without bound is how a tool ends up declared twice.
from app.tools import context as context  # noqa: E402,F401 - registers on import
from app.tools import data as data  # noqa: E402,F401 - registers on import

# AFTER `data`, and forced rather than tidy: `datawork` is the WRITING half of
# the same lane and it imports the reading half rather than repeating it -
# `data.eval_set_floor` for G0's threshold, `data.check_split_leakage` to verify
# what it wrote, `data.bounded` for the same clamp on `max_rows`. Keeping the
# two in separate modules is what lets a test say "no tool declared in data.py
# writes a file, and every tool that writes one is declared in datawork.py",
# which is a property of the code rather than a habit of its authors.
from app.tools import datawork as datawork  # noqa: E402,F401 - registers on import

from app.tools import measure as measure  # noqa: E402,F401 - registers on import
from app.tools import harness as harness  # noqa: E402,F401 - registers on import
from app.tools import models as models  # noqa: E402,F401 - registers on import
from app.tools import knowledge as knowledge  # noqa: E402,F401 - registers on import
from app.tools import planning as planning  # noqa: E402,F401 - registers on import
from app.tools import goal_todo as goal_todo  # noqa: E402,F401 - CS9 ask-gated goal/todo
# AFTER `planning`: delegation hands out a phase of the plan and folds the
# result back into it, so it is the same document's tools one level up.
from app.tools import delegation as delegation  # noqa: E402,F401 - registers on import
from app.tools import recall as recall  # noqa: E402,F401 - registers on import
from app.tools import memory as memory  # noqa: E402,F401 - registers on import
from app.tools import invent as invent  # noqa: E402,F401 - registers on import
from app.tools import chainfirst as chainfirst  # noqa: E402,F401 - registers on import
from app.tools import observe as observe  # noqa: E402,F401 - registers on import
from app.tools import training as training  # noqa: E402,F401 - registers on import

# AFTER `models`, and forced rather than tidy: the feasibility tools reuse
# `models._vram_field` and `models.DEFAULT_SEQ_LEN` so that the yes/no answer
# and the model ranking are budgeted against the same card and the same default
# example length. Two surfaces answering "does this fit" from two different
# numbers is the drift this import order exists to prevent.
from app.tools import feasible as feasible  # noqa: E402,F401 - registers on import

# AFTER `training`, and forced rather than tidy: `sandbox` reuses
# `app/jobspec.py` and `app/runner.py` directly, and it sits beside the training
# tools in the same control group because a sandbox is where the work that group
# runs actually runs. It makes the `Environment` a `Build` carries, so it has to
# exist before anything plans with one.
from app.tools import sandbox as sandbox  # noqa: E402,F401 - registers on import
from app.tools import workspace_shell as workspace_shell  # noqa: E402,F401 - AU4

# AFTER `measure`, and the order is forced rather than tidy: `evals` reuses
# `measure.normalise_answer` and `measure.BASELINE_SYSTEM` so that a baseline and
# an eval score are produced by the same instrument, and a module cannot import a
# module that has not been imported yet.
from app.tools import evals as evals  # noqa: E402,F401 - registers on import

#: EDGE DIRECTION IS A PAIR, NOT A METRIC IN `evals`. It aggregates over EDGES
#: rather than averaging a boolean over rows, so it cannot ride in `evals.grade`
#: without either discarding the edge denominator - which is the reason it
#: resolves at all - or reporting a mean of booleans while calling it a share
#: of edges. It registers as its own tool for that reason.
from app.tools import edge_direction_metric as edge_direction_metric  # noqa: E402,F401

#: AND THE PAIRING IS NOT TWO SCORES. `b` and `c` need to know WHICH edges
#: changed, not how many each arm got, so a paired test cannot be assembled
#: from two scores no matter how carefully they are quoted. This writes the
#: one table both counts come off - which is the whole of the research lane's
#: refusal 5, `b` and `c` drawn from different tables.
from app.tools import pair_edge_direction as pair_edge_direction  # noqa: E402,F401


# AFTER `evals`, and forced for the same reason: the prompt bench does not
# score anything itself. It calls `evals.run` to measure a prompt and
# `evals.compare` to refuse the differences the eval set cannot resolve, so
# `evals` has to exist before it.
from app.tools import prompts as prompts  # noqa: E402,F401 - registers on import

# THE FORMAT INSTRUMENT, and it goes after the benches for one reason: it is the
# tool `stage_4_format`'s only ASK NODE has been waiting for since the ledger
# shipped. It imports nothing the benches own and reads no model - it counts
# rows on a disk against a schema the person named - so its position here is
# about where a reader looks for it rather than about what it needs.
from app.tools import shapes as shapes  # noqa: E402,F401 - registers on import

# AFTER `evals` as well, and forced for a third time: the retrieval bench does
# not invent a way to report a score. It imports `evals.resolution_for` so that
# a recall and an eval score state their resolution with the same instrument,
# and `evals.normalise_answer` so that "the answer text appears in this passage"
# is decided by the same normalisation every other metric in this product uses.
# A second answer to either question is the drift this import order prevents.
from app.tools import retrieval as retrieval  # noqa: E402,F401 - registers on import

# AFTER `evals` for the fourth time, and for the same reason as the three above:
# `classical` scores a gradient-boosted tree and does not invent a way to report
# the number. It imports `evals.resolution_for` for the interval and
# `evals.mcnemar` for the paired comparison against the trivial answer, so a
# tree's accuracy, a retriever's recall and an eval score all state their
# resolution with one instrument. AFTER `data` too, for `data.bounded`,
# `data.eval_set_floor` - the hold-out floor is G0's own threshold read off the
# engine rather than chosen here - and `data.check_split_leakage`, which is what
# checks a split the caller supplied instead of trusting it.
#
# IT IMPORTS NOTHING FROM sklearn AT MODULE LEVEL and must not: sklearn and
# numpy are not in `pyproject.toml`, so an import here would make them
# dependencies of `import app.tools` and therefore of the whole product. The
# imports are inside the handler and a machine without them gets a refusal
# naming what is missing.
from app.tools import classical as classical  # noqa: E402,F401 - registers on import

# AFTER `evals`, `context` and `data`, and forced rather than tidy. `agents`
# reads the four instruments the AI-engineering ledger cannot be honest without
# (`docs/PHASES.md` Phase 1) and it does not invent a second answer to anything
# this product already answers: `evals.resolution_for` for the interval on a
# tool-call rate and on a failure rate, `evals.grade` and `evals.normalise_answer`
# so a case is graded by the same instrument every other score in the product
# uses, `evals.UNCLASSIFIED` for the bucket nobody named, `context.quarantine`
# because a tool description read off a stranger's disk is untrusted text, and
# `data.bounded` for the same clamp on a caller's integer.
#
# IT IMPORTS NOTHING NEW. There is no OTLP library, no protobuf, no YAML reader
# and no HTTP client in it - the container is JSON Lines and the Python reader is
# `ast`, both of which are the standard library, because a new dependency is a
# named invariant of this project and because the whole point of the AST route
# is that nothing is evaluated.
from app.tools import agents as agents  # noqa: E402,F401 - registers on import

# AFTER `evals`, `training` and `sandbox`, and forced rather than tidy: the
# results program reads all three back. `evals.read` and `evals.compare` are
# where a score and a paired difference come from, `sandbox.pin` is where a
# recipe's pinned versions come from, and the run itself comes out of the runs
# table `training.start_training` wrote. It invents no second answer to any of
# them - that is the whole of what a write-up is - and it stamps nothing, which
# is what lets it read this thread's transcript for the duplicate and leakage
# counts that no ledger holds.
from app.tools import results as results  # noqa: E402,F401 - registers on import

# LAST, and the order matters. `propose` reads the registry to cost a step off
# what the tool it names declared about itself, and it imports `measure` for the
# sample caps `measure_baseline` actually enforces. Importing it after the rest
# means every tool it can plan with already exists.
from app.tools import propose as propose  # noqa: E402,F401 - registers on import


__all__ = [
    "ApprovalRequired",
    "Control",
    "Instrument",
    "GeneratedRowsError",
    "MeasurementError",
    "REGISTRY",
    "Registry",
    "ToolError",
    "ToolSpec",
    "agents",
    "classical",
    "context",
    "data",
    "datawork",
    "evals",
    "evidence",
    "feasible",
    "inspect_hardware",
    "list_runs",
    "measure",
    "models",
    "next_moves",
    "prompts",
    "propose",
    "results",
    "retrieval",
    "run_diagnosis",
    "sandbox",
    "tool",
    "training",
]
