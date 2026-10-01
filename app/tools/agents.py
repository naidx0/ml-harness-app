"""Somebody else's agent, READ rather than run.

`docs/PHASES.md` Phase 1 names four instruments the AI-engineering ledger
cannot be honest without, and `docs/AGENT_INSTRUMENTS.md` is the format research
that decided what each of them accepts from a stranger's machine. This module is
those four:

    read_agent_traces        parse a trace file and report what the agent did
    read_tool_definitions    read somebody's tool schemas and report them
    run_the_failures         re-run the failure set and report the rate
    bound_the_loop           measure cost and termination over runs

## THE RULE THAT MAKES THEM INSTRUMENTS RATHER THAN PARSERS

**NOTHING HERE EXECUTES THE USER'S CODE.** Not to enumerate tools, not to replay
a run. `read_tool_definitions` reads Python by `ast.parse`, which builds a tree
and evaluates nothing; it will not import a module and it will not connect to an
MCP server. Both refusals are in `REFUSALS` with their reasons, and the second is
not a close call: MCP discovery over stdio means *spawning the server process*,
and an MCP server is arbitrary code whose whole purpose is to have effects.

The consequence is stated rather than hidden: **an input schema is never
reported from Python source.** The decorator conventions build their JSON Schema
from evaluated type hints through pydantic - `list[Ticket] | None` is not a
schema until `Ticket` is a class, and `Ticket` is not a class until the file has
run - so a schema reconstructed statically would be a schema nobody's model was
ever shown, printed beside counts taken from schemas that were.

## A FORMAT WE CANNOT READ IS A REFUSAL THAT NAMES WHAT IT NEEDED

Every reader here returns `refusals`, and every refusal says which container it
read, which one it wanted, and what the user would have to change. That is
affordable precisely because of the finding in `docs/AGENT_INSTRUMENTS.md` §1.3:
**there is no interchange format for what an agent did, and there IS a stable
interchange format for the envelope it comes in.** Arize Phoenix, Langfuse,
LangSmith, Braintrust and W&B Weave all INGEST OTLP. So declining every vendor's
private export costs the user one exporter configuration line rather than their
data, and buys us out of inheriting five release cadences.

    accepted:  OTLP/JSON in JSON Lines (the OTLP file exporter's own encoding),
               `resourceSpans[].scopeSpans[].spans[]`; and the same bytes as one
               JSON document with one fewer newline.
    dialects:  `gen_ai.*` (OpenTelemetry GenAI) and `openinference.*` (Arize),
               detected PER SPAN and counted, because a file that is 90% one and
               10% the other is a file whose instrumentation changed mid-corpus.

Two dialects rather than one is not generosity. The only public, licensed,
annotated corpus of agent traces in existence - TRAIL, 148 traces / 1,987 spans /
841 annotated errors, MIT - is in the OpenInference dialect. A reader that cannot
open it has been tested on nobody's traces but ours.

## EVERY ATTRIBUTE IS ABSENT UNTIL IT HAS BEEN SEEN IN THE FILE IN FRONT OF IT

The GenAI conventions are not stable. Not one span, event, metric or attribute in
`open-telemetry/semantic-conventions-genai` carries the Stable badge as of July
2026, and three names have already moved inside the development window:
`gen_ai.system` to `gen_ai.provider.name`, `prompt_tokens`/`completion_tokens` to
`input_tokens`/`output_tokens`, and the message-body EVENTS to attributes. One
file can carry both generations at once, because
`OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` is opt-in and the old
generation is still many instrumentations' default.

So this module reads BOTH generations of every name it reads at all, and asserts
nothing about which is required. Two of the sources read for the research
disagreed about whether `gen_ai.tool.name` is Required or Recommended; that
disagreement is not resolved here and does not need to be.

## THE ONE PLACE A PLAUSIBLE READER SILENTLY PRODUCES 100%

`tool_call_success_rate` is refused outright when **no tool span in the file
carries a status or an `error.type`**. "No errors recorded" and "no error
recording" are the same bytes, and a rate computed from the second is exactly the
invented number this product exists not to produce. When the file DOES record
errors, the rate counts an unset status as a success and says so in the same
sentence as the number - see `_rate_of`.

The same rule with money in it: a token total is refused WHOLE when any inference
span in the run lacks its counts. `app/build.py` already holds this line - *"a
total that quietly drops the term nobody could price is the most dangerous number
a proposal could carry, because it reads as complete"* - and a token total missing
three spans reads as complete too.

## WHY THIS IS A PACK AND NOT CORE

`app/tools/blocks.py`'s rule for the core is that *"a capability is core only if
EVERY ledger would name it, and the test for 'every' is a ledger that does not
exist yet"*, and it names a trace reader in the same paragraph as something that
fails the test. A data ledger does not want one. A machine does. So these four
declare `agent.*` and the pack is the namespace.

## WHAT THIS MODULE STAMPS, AND THE DENOMINATION THAT MADE IT POSSIBLE

`bound_the_loop` measures steps, tokens and wall-clock over a set of runs and
stamps `run_terminates` and `tokens_per_run`. It stamps no currency, and the
reason is a measurement rather than a gap:

1. No instrument can read US dollars out of a trace file. OpenTelemetry defines
   no cost attribute at all; OpenInference's `llm.cost.*` is somebody else's
   arithmetic against an undated price table, which is ASSERTED and never
   MEASURED. Shipping a price table is a number with an expiry date nobody
   re-measures, and taking a price the user states and calling the product
   MEASURED is laundering a STATED input into a gate-opening origin. So G4 was
   DENOMINATED IN TOKENS on 2026-08-25: the ledger asks for `tokens_per_run`,
   which this tool reads off OTel GenAI usage attributes or OpenInference token
   counts, and refuses to total when any inference span in a run lacks them -
   a partial total reads as complete, which is the most dangerous shape a
   number can take here.
2. `run_terminates` is a boolean, and `evidence.Instrument.measured` refuses a
   lone boolean in a call that was handed a path - correctly, because
   `bool(path)` is True for every path. Its reading stands next to
   `tokens_per_run`, the size of what stopped, in the same stamp call.

The ledger line this used to wait for was written on 2026-08-25 - G4's rows
read `tokens_per_run` in place of `cost_per_run_usd`, exactly as
`docs/AGENT_INSTRUMENTS.md` §5.3 argued on independent grounds - so the
attempts below simply succeed, and a currency figure stays available as a
DERIVED display whose provenance says "tokens MEASURED times a price STATED
by you on <date>", which is what `app/provenance.py` already exists to
express.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from app import dataquality, db, diagnosis
from app.tools import context, data, evals, evidence
from app.tools.evidence import Instrument, MeasurementError
from app.tools.registry import tool


# ---------------------------------------------------------------------------
# What we accept, named once so a refusal can quote it.

#: The container. `docs/AGENT_INSTRUMENTS.md` §1.2: the OTLP file exporter writes
#: OTLP/JSON, one top-level object per line, preferred extension `.jsonl`, one
#: signal per file, traces as `TracesData`.
CONTAINER = (
    "OTLP/JSON in JSON Lines - one OTLP object per line, "
    "resourceSpans[].scopeSpans[].spans[] - which is what the OpenTelemetry "
    "file exporter writes, or the same bytes as a single JSON document"
)

#: The two attribute vocabularies, both read, per span.
GEN_AI_OPERATION = "gen_ai.operation.name"
OPENINFERENCE_KIND = "openinference.span.kind"

#: What marks a span as a tool call, in each dialect.
EXECUTE_TOOL = "execute_tool"
OI_TOOL = "TOOL"

#: What marks a span as an inference call, in each dialect. Used only to decide
#: whether a run's token total is complete - see `_tokens_of_run`.
GEN_AI_INFERENCE = frozenset(
    {"chat", "text_completion", "generate_content", "embeddings"}
)
OI_INFERENCE = frozenset({"LLM", "EMBEDDING"})

#: A tool's name, both dialects, both generations.
TOOL_NAME_KEYS = ("gen_ai.tool.name", "tool.name")

#: Token counts. The first pair is the current OTel generation, the second is the
#: one deprecated at v1.27.0 and still emitted by default in many
#: instrumentations, the third is OpenInference. All three are read; a file
#: carrying two of them is a file mid-migration and that is not an error.
TOKEN_KEYS = (
    ("gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens"),
    ("gen_ai.usage.prompt_tokens", "gen_ai.usage.completion_tokens"),
    ("llm.token_count.prompt", "llm.token_count.completion"),
)

#: A cost attribute that a trace may carry. READ AND REPORTED, NEVER STAMPED:
#: OpenTelemetry defines no cost attribute, so anything here is somebody else's
#: multiplication against a price table with no date in the file.
COST_KEYS = ("llm.cost.total", "llm.cost.prompt", "llm.cost.completion")

#: An error on a span, beside the status. `error.type` is the one Stable
#: attribute in the whole agent-span table.
ERROR_TYPE = "error.type"

STATUS_UNSET = "STATUS_CODE_UNSET"
STATUS_OK = "STATUS_CODE_OK"
STATUS_ERROR = "STATUS_CODE_ERROR"
_STATUS_BY_NUMBER = {0: STATUS_UNSET, 1: STATUS_OK, 2: STATUS_ERROR}

#: Bounds on what will be held in memory at once. A trace directory is somebody
#: else's disk and it is not this product's job to be surprised by it.
MAX_TRACE_BYTES = 256 * 1024 * 1024
MAX_SPANS = 200_000
MAX_TRACE_FILES = 200
MAX_DEFINITION_BYTES = 8 * 1024 * 1024
MAX_DEFINITION_CHARS = 2_000_000

#: The disposition of a graded row that never finished. `docs/AGENT_INSTRUMENTS.md`
#: §4.4: NOT a sixth bucket, and it must not become one. A run that hit a bound
#: has no answer, and bucketing it as `format` or dropping it silently corrupt
#: the histogram in the same way - and the histogram is what routes the
#: diagnosis. It is counted on its own and it is G4's evidence.
DID_NOT_TERMINATE = "did_not_terminate"

#: What a failure-set row may call the field saying the run finished. Read
#: rather than assumed, and absent means "nobody said", which is not `false`.
TERMINATION_FIELDS = ("terminated", "did_terminate", "completed", "finished")
NON_TERMINATION_FIELDS = ("did_not_terminate", "timed_out", "hit_the_cap")

#: What a failure-set row may call the trace it belongs to. Without one of these
#: there is no join, and without the join three of the five buckets are not
#: decidable at all - see `_bucket_of`.
RUN_ID_FIELDS = ("trace_id", "traceId", "run_id", "runId", "trace")

#: The bucket nobody classified. IMPORTED rather than re-spelled: `evals.py`'s
#: comment on this constant is the whole design of a bucketer in two sentences -
#: *"a failure nobody classified is a fact about this bucketer and not about the
#: user's model"* - and a second spelling of it here would be a second answer.
UNCLASSIFIED = evals.UNCLASSIFIED

#: The five buckets, and which of them a rule in this file can decide. Written
#: down because the honest first version buckets what it can and reports the
#: rest, and because `context` is the one that can never be decided here: "the
#: answer was not knowable from what the model was given" needs
#: `gen_ai.input.messages`, which the convention marks Opt-In.
BUCKETS_THIS_FILE_CAN_DECIDE = ("format", "tool_execution", "tool_choice", "reasoning")
BUCKETS_THIS_FILE_CANNOT_DECIDE = ("context",)


class TraceError(ValueError):
    """A trace file this reader will not guess at. Carried, never raised at a user."""


# ---------------------------------------------------------------------------
# Refusals. Every one of them names what it read and what it needed.


def refusal(code: str, *, read: str, needed: str, **extra: Any) -> dict[str, Any]:
    """One refusal row. `read` is what was in front of us; `needed` is the door.

    A REFUSAL THAT NAMES NOTHING IS A WALL WITH NO DOOR, which is this
    repository's own sentence about `Registry.call` and about
    `evidence.resolves`. Every caller of this function is a place where a
    plausible reader would have guessed instead.
    """
    return {"refused": str(code), "read": str(read), "needed": str(needed), **extra}


#: The refusals that are policy rather than circumstance - true of every file,
#: stated once, and quotable to a user. `docs/AGENT_INSTRUMENTS.md` §7.
REFUSALS: dict[str, str] = {
    "vendor_export": (
        "A vendor's own trace export - LangSmith run trees, Langfuse public-API "
        "JSON, Braintrust rows, Weave call exports - is not read. All five of "
        "those products ingest OTLP, so producing a file this reads is one "
        "exporter configuration line; accepting five private schemas would be "
        "inheriting five release cadences and their breaking changes."
    ),
    "framework_log": (
        "A trace reconstructed from a framework log or a ReAct scratchpad is not "
        "read. A line saying `Action: search[...]` is a record of what a model "
        "TYPED, not of what RAN, and bucketing a failure from it would put a "
        "guess in a histogram that routes a diagnosis."
    ),
    "success_from_absence": (
        "A tool-call success rate is not reported from a file where no tool span "
        "carries a status or an error.type. No errors recorded and no error "
        "recording are the same bytes, and reporting 100% from the second is an "
        "invented number in the most dangerous possible place."
    ),
    "partial_total": (
        "A token total is not reported for a run where an inference span lacks "
        "its counts. The sum of the parts we could read reads as the whole and "
        "is smaller than it."
    ),
    "currency": (
        "A figure in currency is not produced. OpenTelemetry defines no cost "
        "attribute; a cost carried in a trace is somebody else's arithmetic "
        "against a price table with no date in the file, so it is ASSERTED and "
        "never MEASURED. Tokens are what a trace can be read for."
    ),
    "mcp_server": (
        "This does not connect to an MCP server to enumerate its tools. "
        "Discovery is a live JSON-RPC call, and over stdio that means spawning "
        "the server process - shell execution, which is a named invariant of "
        "this harness. Save the `tools/list` result to a file and point at that."
    ),
    "python_import": (
        "This does not import Python to enumerate its tools. Importing runs "
        "module-level code before any decorator is inspected. The tools are read "
        "with `ast.parse`, which evaluates nothing."
    ),
    "python_schema": (
        "No input schema is reported from Python source. The decorator "
        "conventions build their JSON Schema from evaluated type hints through "
        "pydantic, so there is no static route to it - a schema reconstructed "
        "from annotations nobody evaluated would be a schema no model was ever "
        "shown, printed beside counts taken from schemas that were."
    ),
    "description_score": (
        "No quality score is given to a tool description. Every study that "
        "scores them uses a rubric or an LLM judge, and a rating is not a "
        "measured rate. The way this product proves a description was the bug "
        "is to change it, re-run the same failure set, and report the paired "
        "difference with its resolution - or NO EVIDENCE, in those words."
    ),
    "description_rewrite": (
        "Descriptions are not rewritten to raise selection. Wording alone moves "
        "tool choice by tens of points; an instrument that optimises toward "
        "being chosen is building that lever, in a product whose first invariant "
        "is that it does not invent numbers."
    ),
    "counter_is_not_termination": (
        "`run_terminates` is not taken from somebody's word that they set "
        "max_iterations. Sixty-eight confirmed infinite agentic loops were found "
        "across 47 projects that had counters; the counters sat outside the "
        "feedback path that actually recursed."
    ),
    "bucket_without_termination": (
        "A run that never terminated is not bucketed. It has no answer, so it "
        "has a disposition instead: it is counted on its own, kept out of the "
        "histogram, and it is what G4 is asking about."
    ),
}


# ---------------------------------------------------------------------------
# OTLP/JSON: the envelope, and the two dialects inside it.


def _anyvalue(raw: Any) -> Any:
    """One OTLP `AnyValue`, unwrapped. Returns `None` for a shape we do not know.

    `intValue` arrives as a STRING - that is proto3's JSON mapping for 64-bit
    integers, not an exporter being odd - so it is read as one and converted
    here rather than compared as text somewhere downstream.
    """
    if not isinstance(raw, Mapping):
        return raw
    if "stringValue" in raw:
        return str(raw["stringValue"])
    if "intValue" in raw:
        try:
            return int(str(raw["intValue"]))
        except (TypeError, ValueError):
            return None
    if "doubleValue" in raw:
        try:
            return float(raw["doubleValue"])
        except (TypeError, ValueError):
            return None
    if "boolValue" in raw:
        return bool(raw["boolValue"])
    if "arrayValue" in raw:
        values = (raw.get("arrayValue") or {}).get("values") or []
        return [_anyvalue(one) for one in values]
    if "kvlistValue" in raw:
        return attribute_map((raw.get("kvlistValue") or {}).get("values"))
    if "bytesValue" in raw:
        return str(raw["bytesValue"])
    return None


def attribute_map(raw: Any) -> dict[str, Any]:
    """`[{key, value}]` as a plain mapping, or a plain mapping unchanged.

    BOTH SHAPES, and the second one is not sloppiness. OTLP/JSON specifies the
    array of `KeyValue`; a flat object is unambiguous, several tools that
    post-process traces emit one, and accepting it costs nothing and cannot be
    mistaken for anything else. What is NOT accepted is inventing an attribute
    that is not there, which is the only failure mode that matters here.
    """
    if isinstance(raw, Mapping):
        return {str(key): value for key, value in raw.items()}
    out: dict[str, Any] = {}
    for entry in raw or ():
        if not isinstance(entry, Mapping):
            continue
        key = entry.get("key")
        if key is None:
            continue
        out[str(key)] = _anyvalue(entry.get("value"))
    return out


def status_code(raw: Any) -> str:
    """`STATUS_CODE_*` for a span's status, or `""` when it carries none.

    `""` AND `STATUS_CODE_UNSET` ARE THE SAME ANSWER HERE and both mean *this
    span says nothing about whether it failed*. Keeping them apart from OK and
    ERROR is the whole of `_rate_of`'s refusal, so it is done once, here.
    """
    if not isinstance(raw, Mapping):
        return ""
    code = raw.get("code")
    if code is None:
        return ""
    if isinstance(code, bool):
        return ""
    if isinstance(code, int):
        return _STATUS_BY_NUMBER.get(code, "")
    text = str(code).strip().upper()
    if text in (STATUS_UNSET, STATUS_OK, STATUS_ERROR):
        return text
    if text in ("UNSET", "OK", "ERROR"):
        return f"STATUS_CODE_{text}"
    return ""


def dialect_of(attributes: Mapping[str, Any]) -> str:
    """`gen_ai`, `openinference`, `both`, or `""` for a span in neither.

    Both is a REAL case rather than a defensive one: Arize AX normalises spans
    arriving in the OTel dialect into OpenInference and keeps them side by side.
    """
    gen_ai = GEN_AI_OPERATION in attributes
    oi = OPENINFERENCE_KIND in attributes
    if gen_ai and oi:
        return "both"
    if gen_ai:
        return "gen_ai"
    if oi:
        return "openinference"
    return ""


def is_tool_span(attributes: Mapping[str, Any]) -> bool:
    """A span that executed a tool, in either dialect."""
    return (
        str(attributes.get(GEN_AI_OPERATION) or "") == EXECUTE_TOOL
        or str(attributes.get(OPENINFERENCE_KIND) or "").upper() == OI_TOOL
    )


def is_inference_span(attributes: Mapping[str, Any]) -> bool:
    """A span that called a model. Only used to decide whether tokens are whole."""
    return (
        str(attributes.get(GEN_AI_OPERATION) or "") in GEN_AI_INFERENCE
        or str(attributes.get(OPENINFERENCE_KIND) or "").upper() in OI_INFERENCE
    )


def tool_name_of(attributes: Mapping[str, Any]) -> str:
    """The tool a span called, or `""`. NEVER a guess from the span's name.

    `gen_ai.tool.name` is Required in the agent-spans document and was
    summarised as Recommended in the general one; that disagreement is not
    resolved and does not have to be, because an absent name is reported as
    absent rather than parsed out of `"execute_tool search_tickets"`.
    """
    for key in TOOL_NAME_KEYS:
        value = attributes.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def tokens_of(attributes: Mapping[str, Any]) -> tuple[int, int] | None:
    """`(input, output)` for one span, or `None` when it carries no counts.

    `None` IS THE LOAD-BEARING ANSWER. It is what makes a run's total refusable
    whole rather than quietly short - see `_tokens_of_run`.
    """
    for first, second in TOKEN_KEYS:
        left, right = attributes.get(first), attributes.get(second)
        if left is None and right is None:
            continue
        try:
            return (int(left or 0), int(right or 0))
        except (TypeError, ValueError):
            return None
    return None


def _nanos(value: Any) -> int | None:
    """A `*TimeUnixNano` field, which OTLP/JSON writes as a decimal string."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _span_from(raw: Mapping[str, Any], resource: Mapping[str, Any]) -> dict[str, Any]:
    """One OTLP span, flattened into the shape every reader here works on."""
    attributes = attribute_map(raw.get("attributes"))
    start = _nanos(raw.get("startTimeUnixNano"))
    end = _nanos(raw.get("endTimeUnixNano"))
    return {
        "trace_id": str(raw.get("traceId") or ""),
        "span_id": str(raw.get("spanId") or ""),
        "parent_span_id": str(raw.get("parentSpanId") or ""),
        "name": str(raw.get("name") or ""),
        "attributes": attributes,
        "resource": dict(resource),
        "status": status_code(raw.get("status")),
        "error_type": str(attributes.get(ERROR_TYPE) or ""),
        "start_ns": start,
        "end_ns": end,
        "dialect": dialect_of(attributes),
    }


def _documents(path: Path) -> Iterator[tuple[int, Any]]:
    """Every top-level JSON object in one file, by line and then as a whole.

    JSON LINES FIRST, AND THE WHOLE DOCUMENT ONLY AS A FALLBACK, because that is
    the direction that cannot mis-read: a `.jsonl` file's first line parses and
    the whole file does not, while a single-document file's first line does not
    parse and the whole file does. Trying the cheap one first also means a
    million-line trace is never held in memory.
    """
    handle, _ = dataquality.open_text(path, newline=None)
    lines: list[str] = []
    try:
        for number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                yield number, json.loads(stripped)
            except ValueError:
                lines.append(line)
                if len(lines) == 1 and number > 1:
                    # A file that parsed line by line and then stopped is a
                    # broken JSONL file, not a JSON document. Say so there.
                    raise TraceError(
                        f"line {number} of {path.name} is not a JSON object, and "
                        "the lines before it were. That is a JSON Lines file with "
                        "a broken line in it rather than a single JSON document."
                    )
                continue
    finally:
        handle.close()
    if not lines:
        return
    try:
        yield 0, json.loads("".join(lines))
    except ValueError as error:
        raise TraceError(
            f"{path.name} is neither JSON Lines nor a single JSON document: "
            f"{error}"
        ) from None


def _trace_files(root: Path) -> list[Path]:
    """The files a trace path names. A directory is read in sorted order."""
    if root.is_file():
        return [root]
    found = sorted(
        p
        for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in (".jsonl", ".json", ".ndjson")
    )
    return found[:MAX_TRACE_FILES]


def read_spans(path: str | Path) -> dict[str, Any]:
    """Every span in one OTLP file or directory of them, with what was refused.

    The return shape is the same whether it worked or not: `spans` is a list,
    `refusals` is a list, and a caller reads both. Nothing here raises at a
    person - a reader that raises turns a reportable limit into a traceback in
    whatever happened to be iterating, which `dataquality.whole_document_limit`
    already learned.
    """
    root = Path(path)
    out: dict[str, Any] = {
        "path": str(root),
        "files": [],
        "spans": [],
        "refusals": [],
        "documents": 0,
        "bytes": 0,
    }
    if not root.exists():
        out["refusals"].append(
            refusal(
                "no_such_path",
                read=f"nothing at {root}",
                needed="a path on this machine to a trace file or a folder of them",
            )
        )
        return out

    files = _trace_files(root)
    if not files:
        out["refusals"].append(
            refusal(
                "no_trace_files",
                read=f"{root} holds no .jsonl, .ndjson or .json file",
                needed=CONTAINER,
            )
        )
        return out

    total = 0
    for one in files:
        try:
            total += one.stat().st_size
        except OSError:
            continue
    out["bytes"] = total
    if total > MAX_TRACE_BYTES:
        out["refusals"].append(
            refusal(
                "too_large",
                read=f"{total:,} bytes across {len(files)} file(s)",
                needed=(
                    f"under {MAX_TRACE_BYTES:,} bytes in one read. Point at one "
                    "run's file, or split the directory - nothing was read, so "
                    "no number here is a count of it."
                ),
            )
        )
        return out

    spans: list[dict[str, Any]] = []
    documents = 0
    not_otlp: list[str] = []
    for one in files:
        out["files"].append(str(one))
        try:
            for _, document in _documents(one):
                documents += 1
                resource_spans = (
                    document.get("resourceSpans")
                    if isinstance(document, Mapping)
                    else None
                )
                if not isinstance(resource_spans, list):
                    not_otlp.append(one.name)
                    continue
                for entry in resource_spans:
                    if not isinstance(entry, Mapping):
                        continue
                    resource = attribute_map(
                        (entry.get("resource") or {}).get("attributes")
                    )
                    for scope in entry.get("scopeSpans") or ():
                        if not isinstance(scope, Mapping):
                            continue
                        for raw in scope.get("spans") or ():
                            if isinstance(raw, Mapping):
                                spans.append(_span_from(raw, resource))
                                if len(spans) >= MAX_SPANS:
                                    out["refusals"].append(
                                        refusal(
                                            "too_many_spans",
                                            read=f"more than {MAX_SPANS:,} spans",
                                            needed=(
                                                "a smaller set of runs. Every "
                                                "number below is over the first "
                                                f"{MAX_SPANS:,} spans and says so."
                                            ),
                                        )
                                    )
                                    out["spans"] = spans
                                    out["documents"] = documents
                                    return out
        except TraceError as error:
            out["refusals"].append(
                refusal("not_json", read=str(error), needed=CONTAINER)
            )
        except OSError as error:
            out["refusals"].append(
                refusal(
                    "unreadable",
                    read=f"{one.name} could not be read: {error}",
                    needed="a readable file",
                )
            )

    out["spans"] = spans
    out["documents"] = documents
    if not_otlp:
        out["refusals"].append(
            refusal(
                "not_otlp",
                read=(
                    f"{len(set(not_otlp))} document(s) with no `resourceSpans` "
                    f"array: {', '.join(sorted(set(not_otlp))[:5])}"
                ),
                needed=CONTAINER,
                what_to_do=(
                    "Every major tracing product ingests OTLP. If this came out "
                    "of one of them, point its OTLP file exporter at a directory "
                    "and re-run once; that is a configuration line rather than a "
                    "change to your system. " + REFUSALS["vendor_export"]
                ),
            )
        )
    return out


def runs_of(spans: Iterable[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """One run is one `traceId`. Spans with no trace id are not a run.

    `docs/AGENT_INSTRUMENTS.md` §1.5: without the grouping we cannot say where a
    run began, and a set of runs is the unit every number in `bound_the_loop` is
    denominated in.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    for span in spans:
        trace_id = str(span.get("trace_id") or "")
        if trace_id:
            grouped.setdefault(trace_id, []).append(dict(span))
    return grouped


def _agent_spans(spans: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Spans carrying either dialect's marker, which is what makes this a trace
    OF AN AGENT rather than a well-formed OTLP file of HTTP and DB spans."""
    return [dict(span) for span in spans if span.get("dialect")]


def _rate_of(tool_spans: list[Mapping[str, Any]]) -> dict[str, Any]:
    """The tool-call success rate, or the refusal that says why there is none.

    THE ONE PLACE A PLAUSIBLE READER SILENTLY PRODUCES 100%. Failure is an
    explicit `STATUS_CODE_ERROR` or an `error.type`; success is the rest - and
    "the rest" is only meaningful in a file that records errors AT ALL. So the
    rate is refused outright when no tool span carries either, and where it is
    reported, the count of spans that carry an explicit disposition travels with
    it so a reader can see how much of the numerator is inferred from absence.
    """
    total = len(tool_spans)
    if not total:
        return {
            "ok": False,
            **refusal(
                "no_tool_spans",
                read="no span in this file is an execute_tool or a TOOL span",
                needed=(
                    "at least one tool span. `tool_call_success_rate` is a rate "
                    "over tool calls, and there are none here to be a rate over."
                ),
            ),
        }
    failed = [
        span
        for span in tool_spans
        if span.get("status") == STATUS_ERROR or span.get("error_type")
    ]
    explicit = [
        span
        for span in tool_spans
        if span.get("status") in (STATUS_OK, STATUS_ERROR) or span.get("error_type")
    ]
    if not explicit:
        return {
            "ok": False,
            **refusal(
                "no_tool_status",
                read=(
                    f"{total} tool span(s), and not one of them carries a status "
                    "code or an error.type"
                ),
                needed=(
                    "a file where at least one tool span records its outcome. "
                    + REFUSALS["success_from_absence"]
                ),
                tool_spans=total,
            ),
        }
    succeeded = total - len(failed)
    return {
        "ok": True,
        "tool_calls": total,
        "failed": len(failed),
        "succeeded": succeeded,
        "explicit_status_n": len(explicit),
        "rate": succeeded / total,
        "resolution": evals.resolution_for(succeeded, total),
        "counted_as": (
            f"{len(failed)} of {total} tool span(s) carry STATUS_CODE_ERROR or "
            f"an error.type and are counted as failures; the other {succeeded} "
            f"are counted as successes because this file records errors "
            f"({len(explicit)} span(s) carry an explicit disposition)"
        ),
    }


def _tokens_of_run(spans: list[Mapping[str, Any]]) -> dict[str, Any]:
    """A run's token total, or the refusal that keeps it from reading complete."""
    inference = [span for span in spans if is_inference_span(span["attributes"])]
    if not inference:
        return {
            "ok": False,
            "why": "no inference span in this run carries an operation this reader knows",
        }
    missing = [
        span["span_id"]
        for span in inference
        if tokens_of(span["attributes"]) is None
    ]
    if missing:
        return {
            "ok": False,
            "why": (
                f"{len(missing)} of {len(inference)} inference span(s) in this run "
                "carry no token counts. " + REFUSALS["partial_total"]
            ),
            "spans_without_tokens": len(missing),
        }
    pairs = [tokens_of(span["attributes"]) or (0, 0) for span in inference]
    return {
        "ok": True,
        "input": sum(left for left, _ in pairs),
        "output": sum(right for _, right in pairs),
        "total": sum(left + right for left, right in pairs),
        "inference_spans": len(inference),
    }


def _terminated(spans: list[Mapping[str, Any]]) -> bool | None:
    """Did this run reach a root span that ended? `None` when it cannot be said.

    A ROOT SPAN WITH NO `endTimeUnixNano` IS THE OBSERVATION, and it is a
    narrower claim than "the loop is infinite": it says the exporter wrote this
    run's root and never wrote its end. `None` is returned when there is no root
    at all - a trace whose root span is in a file we were not given is not a
    trace of a run that failed to stop.
    """
    ids = {str(span.get("span_id") or "") for span in spans}
    roots = [
        span
        for span in spans
        if not span.get("parent_span_id")
        or str(span.get("parent_span_id")) not in ids
    ]
    if not roots:
        return None
    return all(span.get("end_ns") is not None for span in roots)


# ---------------------------------------------------------------------------
# The bucket vocabulary, read off whichever ledger this thread is running.


def bucket_vocabulary(fact: str, spec: diagnosis.Spec | None = None) -> tuple[str, ...]:
    """The buckets this ledger's own fork routes on, keyed by the FACT.

    DERIVED FROM THE FACT THIS TOOL IS ABOUT TO STAMP, not from a node id, and
    that is the one improvement this file makes on `evals.routable_modes`.
    That function names `S1_ROUTE_BY_FAILURE_MODE`, which is ONE ledger's
    spelling; its own docstring says so and refuses to fall back for a second
    ledger, which is right and is also why it answers `()` for the AI ledger
    whose fork is called `S1_FORK_BY_FAILURE_BUCKET`. Measured on 2026-08-24:

        ML routable_modes: 8 names        AI routable_modes: ()

    Asking "which node in this ledger forks on `failure_buckets`?" needs no node
    id from either ledger and gets the right answer from both. `fork.branch_on`
    is the engine's own grammar, parsed at load time, and a ledger that renames
    its fork node tomorrow is followed rather than silently emptied.

    `()` is still a legal answer, for a ledger with no such fork, and the caller
    must be able to say so: a bucketer that ran and cannot name its buckets has
    produced a histogram nothing can route.
    """
    current = spec or diagnosis.default_spec()
    name = str(fact)
    try:
        for node in current.node_index.values():
            fork = node.get("fork") if isinstance(node, Mapping) else None
            if not isinstance(fork, Mapping):
                continue
            if str(fork.get("branch_on") or "") != name:
                continue
            return tuple(sorted(fork.get("routes") or ()))
    except Exception:  # noqa: BLE001 - a ledger that will not walk is not our news
        return ()
    return ()


# ---------------------------------------------------------------------------
# Tool definitions: four static documents and one AST.


def _describe_one(
    name: Any,
    description: Any,
    schema: Any,
    *,
    source: str,
    schema_read: bool = True,
) -> dict[str, Any]:
    """One tool, as counts and structure. NEVER a rating - see REFUSALS.

    Every description goes through `context.quarantine`, no exceptions and no
    "just the short ones". Tool poisoning is OWASP MCP03:2025 and the MCP
    specification itself says clients MUST treat annotations as untrusted; we
    are reading these off a stranger's disk and putting them in front of a
    model, and the envelope whose `role` is `data` and whose `trusted` is false
    is the only path they may take. A description that trips
    `find_instruction_like` is itself a finding worth showing - it is either an
    attack or a prompt template somebody forgot was in there.
    """
    text = "" if description is None else str(description)
    properties: dict[str, Any] = {}
    required: list[str] = []
    if isinstance(schema, Mapping):
        raw = schema.get("properties")
        if isinstance(raw, Mapping):
            properties = {str(k): v for k, v in raw.items()}
        raw_required = schema.get("required")
        if isinstance(raw_required, list):
            required = [str(one) for one in raw_required]
    undocumented = sorted(
        key
        for key, value in properties.items()
        if not (
            str((value.get("description") if isinstance(value, Mapping) else "") or "")
        ).strip()
    )
    row: dict[str, Any] = {
        "name": str(name or ""),
        "source": source,
        "description_present": bool(text.strip()),
        "description_characters": len(text),
        "parameters_declared": len(properties),
        "schema": "read" if schema_read else "not read (python source)",
    }
    if schema_read:
        row["parameters_required"] = len(required)
        row["parameters_without_a_description"] = undocumented
    row["description"] = context.quarantine(
        text, source=f"{source} tool definition for {name!r}"
    )
    return row


def _mcp_tools(document: Any) -> list[Any] | None:
    """A saved `tools/list` result, or a bare array of MCP tool objects."""
    if isinstance(document, Mapping):
        for key in ("tools", "result"):
            inner = document.get(key)
            if isinstance(inner, Mapping):
                inner = inner.get("tools")
            if isinstance(inner, list):
                return inner
    if isinstance(document, list) and any(
        isinstance(one, Mapping) and "inputSchema" in one for one in document
    ):
        return document
    return None


def _tools_array(document: Any) -> list[Any] | None:
    """An OpenAI or Anthropic tools array, wherever it is nested in the file."""
    if isinstance(document, list):
        return document
    if isinstance(document, Mapping):
        for key in ("tools", "functions"):
            inner = document.get(key)
            if isinstance(inner, list):
                return inner
    return None


def _shape_of(entry: Mapping[str, Any]) -> str:
    """Which of the four JSON shapes one entry is. `""` for none of them.

    THE OPENAI TRAP IS TWO SHAPES AND NOT ONE. Chat Completions nests the tool
    under `function`; the Responses API removed that wrapper. A reader that
    handles one and not the other reports `tool_count: 0` on half the files it
    is given, and zero is a number that opens nothing and explains nothing.
    """
    if "inputSchema" in entry:
        return "mcp"
    if "input_schema" in entry:
        return "anthropic"
    if isinstance(entry.get("function"), Mapping):
        return "openai_chat_completions"
    if entry.get("type") == "function" and "name" in entry:
        return "openai_responses"
    if "name" in entry and ("parameters" in entry or "description" in entry):
        return "openai_responses"
    # An Anthropic-defined tool - bash, the text editor - is declared by `type`
    # and `name` with NO input_schema at all. A schema-less entry in an
    # Anthropic array is a legitimate tool rather than a malformed one.
    if "name" in entry and "type" in entry:
        return "anthropic"
    return ""


def _from_json(document: Any) -> tuple[list[dict[str, Any]], str] | None:
    """Every tool in a JSON document, and which shape it was read as."""
    entries = _mcp_tools(document)
    shape = "mcp" if entries is not None else ""
    if entries is None:
        entries = _tools_array(document)
    if entries is None:
        return None

    rows: list[dict[str, Any]] = []
    shapes: Counter[str] = Counter()
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        kind = shape or _shape_of(entry)
        if not kind:
            continue
        shapes[kind] += 1
        if kind == "openai_chat_completions":
            inner = entry.get("function") or {}
            rows.append(
                _describe_one(
                    inner.get("name"),
                    inner.get("description"),
                    inner.get("parameters"),
                    source=kind,
                )
            )
        elif kind == "mcp":
            rows.append(
                _describe_one(
                    entry.get("name"),
                    entry.get("description"),
                    entry.get("inputSchema"),
                    source=kind,
                )
            )
        elif kind == "anthropic":
            rows.append(
                _describe_one(
                    entry.get("name"),
                    entry.get("description"),
                    entry.get("input_schema"),
                    source=kind,
                )
            )
        else:
            rows.append(
                _describe_one(
                    entry.get("name"),
                    entry.get("description"),
                    entry.get("parameters"),
                    source=kind,
                )
            )
    if not shapes:
        return None
    return rows, ", ".join(f"{name} x{count}" for name, count in sorted(shapes.items()))


#: Decorators that turn a Python function into a tool. Matched on the DOTTED
#: TAIL, so `@tool`, `@mcp.tool()`, `@server.tool()` and `@agent.function_tool`
#: are all the same call. Nothing is imported to find out.
TOOL_DECORATORS = frozenset(
    {"tool", "function_tool", "ai_function", "strands", "tool_plugin"}
)


def _decorator_tail(node: ast.AST) -> str:
    """The last dotted name of a decorator expression, without evaluating it."""
    if isinstance(node, ast.Call):
        return _decorator_tail(node.func)
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _literal_kwarg(node: ast.AST, name: str) -> str | None:
    """A decorator's `name=`/`description=` when it is a plain string literal.

    `ast.Constant` only. An f-string, a concatenation or a variable is left
    alone rather than half-evaluated, because the point of reading Python this
    way is that nothing is evaluated.
    """
    if not isinstance(node, ast.Call):
        return None
    for keyword in node.keywords:
        if keyword.arg == name and isinstance(keyword.value, ast.Constant):
            if isinstance(keyword.value.value, str):
                return keyword.value.value
    return None


def _positional_literal(node: ast.AST) -> str | None:
    """A decorator's first positional argument when it is a string literal."""
    if not isinstance(node, ast.Call) or not node.args:
        return None
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def _from_python(source: str, where: str) -> list[dict[str, Any]]:
    """Decorated functions, by AST. Name and description only, never a schema.

    `ast.parse` builds a tree and evaluates nothing - no import, no module-level
    code, no decorator call. `ast.get_docstring` returns the description exactly
    as the decorator would take it, because every convention read for
    `docs/AGENT_INSTRUMENTS.md` §2.1 derives it the same way: function name to
    tool name, docstring to description, type hints to schema.

    The third of those is where this stops. See REFUSALS['python_schema'].
    """
    tree = ast.parse(source, filename=where)
    rows: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            tail = _decorator_tail(decorator)
            if tail not in TOOL_DECORATORS and not tail.endswith("_tool"):
                continue
            name = (
                _literal_kwarg(decorator, "name")
                or _positional_literal(decorator)
                or node.name
            )
            description = (
                _literal_kwarg(decorator, "description")
                or ast.get_docstring(node)
                or ""
            )
            rows.append(
                _describe_one(
                    name,
                    description,
                    None,
                    source=f"python source (@{tail})",
                    schema_read=False,
                )
            )
            break
    return rows


def read_definitions(path: str | Path) -> dict[str, Any]:
    """Every tool declared by one file, or the refusal that says what was wanted."""
    root = Path(path)
    out: dict[str, Any] = {"path": str(root), "tools": [], "refusals": []}
    if not root.is_file():
        out["refusals"].append(
            refusal(
                "no_such_file",
                read=f"{root} is not a file on this machine",
                needed=(
                    "a saved MCP tools/list result, an OpenAI tools array (either "
                    "shape), an Anthropic tools array, or a Python file whose "
                    "tools are decorated. " + REFUSALS["mcp_server"]
                ),
            )
        )
        return out
    try:
        size = root.stat().st_size
    except OSError as error:
        out["refusals"].append(
            refusal("unreadable", read=str(error), needed="a readable file")
        )
        return out
    if size > MAX_DEFINITION_BYTES:
        out["refusals"].append(
            refusal(
                "too_large",
                read=f"{size:,} bytes",
                needed=(
                    f"under {MAX_DEFINITION_BYTES:,} bytes. Nothing was read, so "
                    "no number here is a count of it."
                ),
            )
        )
        return out

    try:
        handle, encoding = dataquality.open_text(root, newline=None)
        try:
            text = handle.read(MAX_DEFINITION_CHARS + 1)
        finally:
            handle.close()
    except OSError as error:
        out["refusals"].append(
            refusal("unreadable", read=str(error), needed="a readable file")
        )
        return out
    out["encoding"] = encoding
    if len(text) > MAX_DEFINITION_CHARS:
        out["refusals"].append(
            refusal(
                "too_long",
                read=f"more than {MAX_DEFINITION_CHARS:,} characters",
                needed="a smaller file",
            )
        )
        return out

    if root.suffix.lower() == ".py":
        try:
            out["tools"] = _from_python(text, root.name)
        except SyntaxError as error:
            out["refusals"].append(
                refusal(
                    "python_did_not_parse",
                    read=f"{root.name} line {error.lineno}: {error.msg}",
                    needed=(
                        "a Python file this build's parser can read. Nothing was "
                        "imported and nothing was run - "
                        + REFUSALS["python_import"]
                    ),
                )
            )
            return out
        out["read_as"] = "python source, by ast.parse"
        out["schema_note"] = REFUSALS["python_schema"]
        if not out["tools"]:
            out["refusals"].append(
                refusal(
                    "no_decorated_tools",
                    read=f"{root.name} parses and declares no decorated tool",
                    needed=(
                        "a function decorated with one of "
                        + ", ".join(f"@{one}" for one in sorted(TOOL_DECORATORS))
                        + ", or any decorator whose name ends in `_tool`"
                    ),
                )
            )
        return out

    try:
        document = json.loads(text)
    except ValueError as error:
        try:
            document = [json.loads(line) for line in text.splitlines() if line.strip()]
        except ValueError:
            out["refusals"].append(
                refusal(
                    "not_json",
                    read=f"{root.name} does not parse as JSON: {error}",
                    needed=(
                        "a saved MCP tools/list result, an OpenAI tools array "
                        "(either shape), or an Anthropic tools array"
                    ),
                )
            )
            return out

    found = _from_json(document)
    if found is None:
        out["refusals"].append(
            refusal(
                "not_tool_definitions",
                read=(
                    f"{root.name} parses as JSON and holds no array of tool "
                    "definitions this reader recognises"
                ),
                needed=(
                    "one of four documents: an MCP tools/list result "
                    "(`inputSchema`), an OpenAI Chat Completions tools array "
                    "(`{type: function, function: {...}}`), an OpenAI Responses "
                    "tools array (`{type: function, name, parameters}`), or an "
                    "Anthropic tools array (`{name, description, input_schema}`)"
                ),
            )
        )
        return out

    rows, shapes = found
    out["tools"] = rows
    out["read_as"] = shapes
    return out


def _collisions(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Names declared more than once. The MCP spec scopes uniqueness to ONE
    server and tells aggregating clients to disambiguate, so a collision is a
    real defect in the file rather than a curiosity."""
    counts = Counter(str(row.get("name") or "") for row in rows)
    return [
        {"name": name, "declared": count}
        for name, count in sorted(counts.items())
        if count > 1
    ]


# ---------------------------------------------------------------------------
# The failure set, and the three dispositions a graded row can have.


def _field(row: Mapping[str, Any], names: Iterable[str]) -> Any:
    for name in names:
        if name in row and not dataquality.is_null(row.get(name)):
            return row.get(name)
    return None


def _did_not_terminate(row: Mapping[str, Any]) -> bool | None:
    """Did this case's run finish? `None` when the file does not say.

    ABSENCE IS NOT `false`. A failure set with no termination column is a
    failure set about which termination is unknown, and treating that as "they
    all finished" would hand G4 a claim nobody made.
    """
    for name in NON_TERMINATION_FIELDS:
        if name in row and not dataquality.is_null(row.get(name)):
            return bool(row.get(name))
    for name in TERMINATION_FIELDS:
        if name in row and not dataquality.is_null(row.get(name)):
            value = row.get(name)
            if isinstance(value, str):
                return value.strip().lower() in ("false", "no", "0")
            return not bool(value)
    return None


def _bucket_of(
    expected: Any,
    answer: Any,
    verdicts: Mapping[str, bool],
    labels: frozenset[str],
    run: Mapping[str, Any] | None,
    tools_seen_anywhere: bool,
) -> str:
    """One failing row's bucket, in the AI ledger's five, or `unclassified`.

    PRECEDENCE, AND EVERY LINE OF IT IS A DECISION:

    1. **`tool_execution`** - the trace says a tool in this run carried
       `STATUS_CODE_ERROR` or an `error.type`. A recorded error is the one
       unambiguous signal in the file and it outranks everything read from text.
    2. **`format`** - the expected answer is present in the reply and the reply
       is not it, or the expected answer parses as JSON and the reply does not,
       or the expected column is a closed vocabulary and the reply is not a
       member of it. This is the only bucket decidable from the answer ALONE,
       and it is the head of the distribution rather than the tail: TRAIL's own
       corpus puts formatting errors and instruction non-compliance at 353 of
       841 annotated errors, and this repository reached the same conclusion
       twice on unrelated data.
    3. **`tool_choice`** - the trace says this run called no tool at all, in a
       file where other runs did. "The WRONG tool was called" is not decidable
       here and is not claimed: knowing which tool should have been called means
       knowing the answer, which is what the failure set does not carry.
    4. **`reasoning`** - the trace says tools ran in this run and none of them
       failed, and the answer is still wrong.
    5. **`unclassified`** - everything else, reported on its own and kept out of
       the stamped histogram.

    `context` IS NEVER RETURNED, and that is a refusal rather than a gap. "The
    answer was not knowable from what the model was given" needs the input the
    model was given, which is `gen_ai.input.messages` - an attribute the
    convention marks Opt-In and most emitters do not write, because it is where
    the PII lives. A `context` count guessed from an answer string would be a
    fact about this bucketer sitting in a histogram that routes a diagnosis.
    """
    if run is not None:
        failed = [
            span
            for span in run.get("tool_spans") or ()
            if span.get("status") == STATUS_ERROR or span.get("error_type")
        ]
        if failed:
            return "tool_execution"

    text = str(answer or "").strip()
    if verdicts.get(evals.CONTAINS) and not verdicts.get(evals.EXACT_MATCH):
        return "format"
    if _looks_like_json(str(expected)) and text and not _looks_like_json(text):
        return "format"
    if labels and evals.normalise_answer(text) not in labels:
        return "format"

    if run is not None:
        if not run.get("tool_spans") and tools_seen_anywhere:
            return "tool_choice"
        if run.get("tool_spans"):
            return "reasoning"
    return UNCLASSIFIED


def _looks_like_json(text: str) -> bool:
    stripped = str(text).strip()
    if not stripped or stripped[0] not in "[{":
        return False
    try:
        json.loads(stripped)
    except ValueError:
        return False
    return True


# ---------------------------------------------------------------------------
# THE FOUR INSTRUMENTS.


@tool(
    "read_agent_traces",
    description=(
        "Read an OpenTelemetry trace file and report what an agent actually "
        "did: how many runs, how many tool calls, which tools were called and "
        "how often they failed. Accepts OTLP/JSON in JSON Lines - what the "
        "OpenTelemetry file exporter writes - carrying either the gen_ai.* or "
        "the openinference.* attributes. Every other trace format is refused "
        "by name, with what to export instead. It does not run anything."
    ),
    schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "An OTLP trace file on this machine, or a folder of them."
                ),
            }
        },
        "required": ["path"],
    },
    reads=("filesystem", "traces"),
    writes=("facts",),
    measures=("tool_call_success_rate", "has_traces"),
    provides=("agent.traces.read",),
    label="Read agent traces",
    group="Look",
    verb="read an agent trace",
    order=40,
)
def read_agent_traces(path: str, *, instrument: Instrument) -> dict[str, Any]:
    """What the agent did, counted off the file, with every refusal named.

    THE STAMP ORDER IS THE DESIGN AND NOT A TIDY-UP. `tool_call_success_rate`
    goes first so that `has_traces` is never the only thing this call minted -
    the same rule `run_eval` follows for `baseline_measured` and for the same
    reason, which the evidence ledger states in its own words: *a boolean cannot
    carry the caller mark, there are only two of them, and `bool(anything
    non-zero)` is the one that opens the gate.* What makes a flag mean anything
    is the reading standing next to it.

    So a file this reader cannot get a rate out of gets NO STAMP AT ALL, and
    says so with the reason and what would fix it. That is the honest state and
    it is worth naming precisely: `has_traces` is stampable exactly when the
    file also supports a tool-call rate, because that rate is the only reading
    the AI ledger declares that this instrument produces. A ledger fact for the
    count of agent spans would separate the two; there is not one, and the
    refusal says so rather than working around it.
    """
    read = read_spans(path)
    spans = read["spans"]
    agent = _agent_spans(spans)
    tool_spans = [span for span in agent if is_tool_span(span["attributes"])]
    runs = runs_of(agent)
    dialects = Counter(span["dialect"] for span in agent if span["dialect"])
    called = Counter(
        tool_name_of(span["attributes"])
        for span in tool_spans
        if tool_name_of(span["attributes"])
    )

    payload: dict[str, Any] = {
        "ok": bool(agent),
        "path": str(path),
        "files_read": read["files"],
        "documents_read": read["documents"],
        "spans_read": len(spans),
        "agent_spans": len(agent),
        "runs": len(runs),
        "tool_spans": len(tool_spans),
        "dialects": dict(dialects),
        "tools_called": dict(called.most_common()),
        "distinct_tools_called": len(called),
        "refusals": list(read["refusals"]),
        "container": CONTAINER,
        "provenance": {
            "spans_read": "measured",
            "agent_spans": "measured",
            "runs": "measured",
            "tool_spans": "measured",
            "tools_called": "measured",
        },
        "tools_called_is_not_tools_defined": (
            "These are the tools this trace shows being CALLED. A tool that is "
            "never called looks exactly like a tool that does not work, and the "
            "difference is the single most common real agent defect - so "
            "tool_count comes from read_tool_definitions and never from here."
        ),
    }

    if not spans and not read["refusals"]:
        payload["refusals"].append(
            refusal(
                "no_spans",
                read=f"{read['documents']} OTLP document(s) with no spans in them",
                needed=CONTAINER,
            )
        )
    if spans and not agent:
        payload["refusals"].append(
            refusal(
                "not_an_agent_trace",
                read=(
                    f"{len(spans)} well-formed OTLP span(s), and not one carries "
                    f"{GEN_AI_OPERATION} or {OPENINFERENCE_KIND}"
                ),
                needed=(
                    "spans from an instrumented agent. A well-formed OTLP file of "
                    "HTTP and database spans is not an agent trace and must not "
                    "open a gate by looking like one."
                ),
            )
        )
    if agent and not runs:
        payload["refusals"].append(
            refusal(
                "no_trace_grouping",
                read="agent spans that carry no traceId",
                needed=(
                    "a traceId on each span. One run is one traceId; without the "
                    "grouping there is no way to say where a run began."
                ),
            )
        )

    rate = _rate_of(tool_spans)
    payload["tool_call_success_rate"] = rate
    if not rate.get("ok"):
        payload["refusals"].append({k: v for k, v in rate.items() if k != "ok"})

    if rate.get("ok"):
        instrument.measured(
            "tool_call_success_rate",
            float(rate["rate"]),
            how=(
                f"{rate['succeeded']} of {rate['tool_calls']} tool span(s) in "
                f"{path} succeeded - {rate['counted_as']}"
            ),
            # Wall 8. A trace export is not something synthesize_rows writes,
            # and the wall costs one read to say so rather than assuming it.
            from_file=path,
        )
    if agent and rate.get("ok"):
        instrument.measured(
            "has_traces",
            True,
            how=(
                f"{len(agent)} of {len(spans)} span(s) in {path} carry "
                f"{GEN_AI_OPERATION} or {OPENINFERENCE_KIND}, across {len(runs)} "
                f"run(s), and {rate['tool_calls']} of them are tool calls"
            ),
            from_file=path,
        )
    elif agent:
        payload["nothing_was_recorded"] = (
            f"{len(agent)} agent span(s) were read and has_traces was NOT "
            "stamped. A boolean is the one thing the evidence ledger cannot "
            "check - `bool(path)` is true for every path - so it refuses a flag "
            "stamped in a call that measured nothing else, and the only reading "
            "this instrument produces that the ledger declares is "
            "tool_call_success_rate, which this file does not support. The "
            "counts above are real and are in the transcript; nothing was "
            "written to the fact ledger. A fact for the number of agent spans "
            "would let the flag stand next to a reading."
        )
    return payload


@tool(
    "read_tool_definitions",
    description=(
        "Read somebody's tool definitions off a file and report what they "
        "declare: how many tools, which have descriptions, how long each is, "
        "which parameters are undocumented, and any name collisions. Accepts a "
        "saved MCP tools/list result, an OpenAI tools array in either shape, an "
        "Anthropic tools array, or Python source read by ast.parse. It never "
        "imports Python, never connects to a server, and never scores a "
        "description."
    ),
    schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "A tool-definition file on this machine: JSON, or .py source."
                ),
            }
        },
        "required": ["path"],
    },
    reads=("filesystem",),
    writes=("facts",),
    measures=("tool_count",),
    provides=("agent.tools.read",),
    label="Read tool definitions",
    group="Look",
    verb="read tool definitions",
    order=41,
)
def read_tool_definitions(path: str, *, instrument: Instrument) -> dict[str, Any]:
    """Counts and structure, never a rating.

    WHY THERE IS NO SCORE, stated where somebody will be tempted to add one. The
    research is unambiguous that descriptions in the wild are broken - 97.1% of
    856 tools across 103 MCP servers carry at least one description smell, and
    wording alone moves tool selection by tens of points - and every one of
    those studies scores descriptions with a rubric or an LLM judge. A rubric
    score is a rating. The same work measured 16.67% REGRESSIONS from augmented
    descriptions, which a rubric would have scored as improvements.

    So the way this product proves a description was the bug is the way it
    proves anything: change it, re-run the same failure set, and report the
    paired difference with its resolution. That is `run_the_failures` plus
    `evals.compare`, and both exist.

    A ZERO IS STAMPED ONLY WHEN A TOOLS ARRAY WAS FOUND AND WAS EMPTY. A
    document with no tools array in it at all is not a system with no tools; it
    is a file we were not able to read as tool definitions, and calling that a
    measured zero is `inspect_hardware`'s doctrine inverted - the tool did not
    run, so the ledger's own default is the honest answer.
    """
    report = read_definitions(path)
    rows = report["tools"]
    collisions = _collisions(rows)
    flagged = [
        {"name": row["name"], "instruction_like": row["description"]["instruction_like"]}
        for row in rows
        if row["description"]["instruction_like"]
    ]
    payload: dict[str, Any] = {
        "ok": not report["refusals"],
        "path": str(path),
        "read_as": report.get("read_as", ""),
        "tool_count": len(rows),
        "tools": rows,
        "without_a_description": sorted(
            row["name"] for row in rows if not row["description_present"]
        ),
        "name_collisions": collisions,
        "descriptions_that_talk_to_the_model": flagged,
        "refusals": report["refusals"],
        "provenance": {"tool_count": "measured" if rows else "not measured"},
        "no_score_is_given": REFUSALS["description_score"],
        "how_to_prove_a_description_was_the_bug": (
            "Change the description, re-run the same failure set with "
            "run_the_failures, and read the paired difference. A difference "
            "inside what those cases can resolve is reported as NO EVIDENCE."
        ),
    }
    if report.get("schema_note"):
        payload["schema_note"] = report["schema_note"]
    if flagged:
        payload["untrusted"] = (
            "A tool description is untrusted text. Tool poisoning is "
            "OWASP MCP03:2025 and the MCP specification says clients MUST treat "
            "annotations as untrusted; every description above is wrapped in a "
            "quarantine envelope whose role is `data`. The tools named here "
            "carry lines addressed at a model, which is either an attack or a "
            "prompt template somebody forgot was in there."
        )

    if not report["refusals"]:
        try:
            instrument.measured(
                "tool_count",
                len(rows),
                how=(
                    f"counted {len(rows)} tool definition(s) in {path}, read as "
                    f"{report.get('read_as', 'tool definitions')}"
                ),
                from_file=path,
            )
        except MeasurementError as error:
            payload["nothing_was_recorded"] = str(error)
    return payload


@tool(
    "run_the_failures",
    description=(
        "Score a failure set against what the agent actually answered, and "
        "bucket what failed. Give it the failure file - the cases and what "
        "should have happened - and the answers your agent produced for them. "
        "Reports the rate with its resolution, never an impression, and a "
        "histogram in the buckets this conversation's ledger routes on. A case "
        "whose run never terminated is counted on its own and is not bucketed. "
        "Point it at the traces too and three more buckets become decidable."
    ),
    schema={
        "type": "object",
        "properties": {
            "failures_path": {
                "type": "string",
                "description": (
                    "The failure set: one row per case, with the input and what "
                    "should have happened."
                ),
            },
            "input_field": {
                "type": "string",
                "description": "The column holding the case that was sent.",
            },
            "expected_field": {
                "type": "string",
                "description": "The column holding what should have happened.",
            },
            "answer_field": {
                "type": "string",
                "description": (
                    "The column holding what the agent actually answered. It may "
                    "be in the failure file itself or in answers_path."
                ),
            },
            "answers_path": {
                "type": "string",
                "description": (
                    "A separate file of the agent's answers, in the same row "
                    "order as the failure set."
                ),
            },
            "label": {
                "type": "string",
                "description": (
                    "What to call this recording, so two of them can be told "
                    "apart later - 'before the description change', 'after'. "
                    "Yours; nothing here invents one."
                ),
            },
            "traces_path": {
                "type": "string",
                "description": (
                    "The OTLP traces for those runs. Joined by trace id, and "
                    "without it only the format bucket is decidable."
                ),
            },
        },
        "required": ["failures_path", "input_field", "expected_field", "answer_field"],
    },
    reads=("filesystem", "datasets", "traces"),
    writes=("facts",),
    measures=(
        "failing_cases_n",
        "baseline_success_rate",
        "can_rerun_failures",
        "failure_rate_measured",
        "failure_buckets",
    ),
    provides=("agent.failures.run",),
    # WHAT THIS TOOL OPENS, said by the tool. Three of its arguments can name a
    # file and only one of them is the set of cases: `answers_path` is where the
    # agent's replies were written and `traces_path` is optional telemetry, so a
    # validator scanning for paths sees three and can decide nothing. The
    # failure set is what a run is a run OF - it is what the case count, the
    # success rate and the bucket census are all measured over - so it is the
    # file a step calling this tool has to be costed from.
    subject=("failures_path",),
    label="Run the failures",
    group="Data",
    verb="re-run the failure set",
    order=42,
)
def run_the_failures(
    failures_path: str,
    input_field: str,
    expected_field: str,
    answer_field: str,
    answers_path: str | None = None,
    traces_path: str | None = None,
    label: str | None = None,
    *,
    instrument: Instrument,
    ledger: diagnosis.Spec,
) -> dict[str, Any]:
    """A rate, not an impression - and three dispositions rather than two.

    ## Why this grades answers rather than driving the agent

    Running somebody's agent means running somebody's code, and their code is
    theirs. Where an agent exposes an OpenAI-shaped chat endpoint it is already
    reachable as an `openai-compatible` provider and `run_eval`'s machinery
    drives it; where it does not, the honest fallback is the one the ML ledger
    already uses for a model it cannot drive - **they run it, they hand us the
    record, and we read it.** That is what this does, and it is why
    `can_rerun_failures` is MEASURED here rather than asked: a file of answers
    for these cases is the re-run, and the count of joined rows is the evidence.

    ## The three dispositions

        passed            -> not in the histogram
        failed, bucketed  -> in the histogram, one of this ledger's buckets
        did_not_terminate -> NOT in the histogram, counted on its own, G4's

    A run that never stopped has no answer. Bucketing it as `format`, or as a
    refusal, or dropping it silently all corrupt the histogram the same way, and
    the histogram is what routes the diagnosis. It is still a failure - it is in
    the denominator of the rate and it is not in the numerator - because a loop
    that does not stop did not succeed.

    ## What is stamped, and in what order

    `failing_cases_n` first, because it is an integer and it is the reading the
    two flags stand next to; then the rate; then the flags; then the histogram.
    The histogram is stamped only when the buckets it holds are ones this
    ledger's own fork routes on, read off the ledger by
    `bucket_vocabulary(...)`, and an empty histogram is not stamped at all -
    `run_eval`'s rule, and `inspect_hardware`'s doctrine underneath it.
    """
    cases, refusals = _load_pairs(
        failures_path, input_field, expected_field, answer_field, answers_path
    )
    payload: dict[str, Any] = {
        "ok": bool(cases),
        "failures_path": str(failures_path),
        "cases": len(cases),
        "refusals": list(refusals),
    }
    if not cases:
        payload["nothing_was_recorded"] = (
            "No case in this failure set carried all three of the fields named, "
            "so nothing was graded and no fact was stamped."
        )
        return payload

    runs: dict[str, dict[str, Any]] = {}
    tools_seen_anywhere = False
    if traces_path:
        read = read_spans(traces_path)
        payload["traces"] = {
            "path": str(traces_path),
            "spans_read": len(read["spans"]),
            "refusals": read["refusals"],
        }
        agent = _agent_spans(read["spans"])
        for trace_id, spans in runs_of(agent).items():
            tool_spans = [s for s in spans if is_tool_span(s["attributes"])]
            tools_seen_anywhere = tools_seen_anywhere or bool(tool_spans)
            runs[trace_id] = {
                "spans": spans,
                "tool_spans": tool_spans,
                "terminated": _terminated(spans),
            }
        payload["traces"]["runs"] = len(runs)
    else:
        payload["without_traces"] = (
            "No traces were given, so only the format bucket is decidable from "
            "the answers alone. tool_choice, tool_execution and reasoning all "
            "need the record of what ran; context needs the input the model was "
            "given, which is an Opt-In attribute and is never bucketed here."
        )

    labels = evals._label_set([case["expected"] for case in cases])
    passed = 0
    unterminated: list[int] = []
    buckets: Counter[str] = Counter()
    unclassified = 0
    joined = 0
    examples: list[dict[str, Any]] = []
    # KEPT SO A SECOND RECORDING CAN BE COMPARED TO THIS ONE. Migration 12 and
    # the module's storage section carry the argument; the short version is
    # that every refusal this ledger reaches most often names a cheap fix, and
    # a fix is only worth naming if the person can find out whether it worked.
    # Finding that out is a PAIRED comparison, and a paired comparison needs
    # both recordings.
    graded_cases: list[dict[str, Any]] = []

    for index, case in enumerate(cases):
        run = None
        if case.get("run_id") and case["run_id"] in runs:
            run = runs[case["run_id"]]
            joined += 1
        stopped = case.get("did_not_terminate")
        if stopped is None and run is not None and run["terminated"] is False:
            stopped = True
        verdicts = evals.grade(case["expected"], case["answer"])
        record = {
            "case_key": case_key(case["input"], case["expected"]),
            "input": case["input"],
            "expected": case["expected"],
            "answer": case["answer"],
            "terminated": not stopped,
            "passed": False,
            "bucket": None,
        }
        graded_cases.append(record)
        if stopped:
            unterminated.append(index)
            continue
        if verdicts[evals.EXACT_MATCH]:
            passed += 1
            record["passed"] = True
            continue
        mode = _bucket_of(
            case["expected"],
            case["answer"],
            verdicts,
            labels,
            run,
            tools_seen_anywhere,
        )
        record["bucket"] = None if mode == UNCLASSIFIED else mode
        if mode == UNCLASSIFIED:
            unclassified += 1
        else:
            buckets[mode] += 1
        if len(examples) < 5:
            examples.append(
                {
                    "expected": str(case["expected"])[:200],
                    "agent_said": str(case["answer"])[:200],
                    "bucket": mode,
                }
            )

    total = len(cases)
    rate = passed / total
    vocabulary = bucket_vocabulary("failure_buckets", ledger)
    routable = {name: count for name, count in buckets.items() if name in vocabulary}
    unroutable = {
        name: count for name, count in buckets.items() if name not in vocabulary
    }

    # THE RECORDING, written before anything is stamped. A run that graded
    # rows and kept none of them is a rate nobody can ever check a change
    # against, which is the state this ledger's six cheapest refusals were in
    # until migration 12. `label` is the person's - two recordings over the
    # same questions are told apart by what they call them, never by their ids.
    recording: dict[str, Any] = {}
    if instrument.thread_id is not None:
        try:
            row = record_run(
                thread_id=int(instrument.thread_id),
                signature=set_signature(cases),
                failures_path=str(failures_path),
                answers_path=str(answers_path or ""),
                traces_path=str(traces_path or ""),
                input_field=str(input_field),
                expected_field=str(expected_field),
                answer_field=str(answer_field),
                label=str(label or ""),
                graded=total,
                passed=passed,
                unterminated=len(unterminated),
                buckets_json=json.dumps(dict(sorted(buckets.items())), sort_keys=True),
            )
            written = record_cases(row["id"], graded_cases)
            recording = {
                "run_id": row["id"],
                "signature": row["signature"],
                "label": row["label"],
                "cases_kept": written,
            }
            if written < len(graded_cases):
                # A duplicated question is the person's export being ordinary,
                # and the honest response is to say which count is which rather
                # than record two verdicts for one question.
                recording["duplicate_questions"] = len(graded_cases) - written
                recording["what_that_means"] = (
                    f"{len(graded_cases) - written} case(s) in {failures_path} ask "
                    "the same question as another case, by input and expected "
                    "answer. One verdict per question is kept, because a "
                    "comparison pairs on the question."
                )
        except Exception as error:  # noqa: BLE001 - a lost recording is not a lost run
            # THE GRADING STANDS EVEN IF THE WRITE DOES NOT. What this tool
            # measured is measured; the recording is what lets a LATER run be
            # compared to it. Losing the second must never cost the first.
            recording = {"not_recorded": f"{type(error).__name__}: {error}"}

    payload.update(
        {
            "recording": recording
            or {
                "not_recorded": (
                    "this call names no conversation, and a recording belongs to "
                    "one for the same reason every fact it produces does"
                )
            },
            "graded": total,
            "passed": passed,
            "failed": total - passed,
            "did_not_terminate": len(unterminated),
            "success_rate": rate,
            "resolution": evals.resolution_for(passed, total),
            "failure_buckets": dict(sorted(routable.items())),
            "unclassified": unclassified,
            "joined_to_a_trace": joined,
            "bucket_vocabulary": list(vocabulary),
            "buckets_this_reader_can_decide": list(BUCKETS_THIS_FILE_CAN_DECIDE),
            "buckets_this_reader_cannot_decide": list(BUCKETS_THIS_FILE_CANNOT_DECIDE),
            "examples": examples,
            "dispositions": (
                "passed, failed-and-bucketed, or did_not_terminate. The third is "
                "not a sixth bucket: it is kept out of the histogram, counted on "
                "its own, and it is what G4 is asking about. "
                + REFUSALS["bucket_without_termination"]
            ),
            "provenance": {
                "graded": "measured",
                "passed": "measured",
                "success_rate": "measured",
                "failure_buckets": "measured",
                "did_not_terminate": "measured",
            },
            "summary": (
                f"{passed} of {total} case(s) in {failures_path} passed - "
                f"{rate:.0%}"
                + (
                    f", with {len(unterminated)} run(s) that never terminated"
                    if unterminated
                    else ""
                )
                + f". {evals.resolution_for(passed, total)['says']}"
            ),
        }
    )
    if unroutable:
        payload["buckets_this_ledger_does_not_route"] = dict(sorted(unroutable.items()))
    if not vocabulary:
        payload["no_bucket_vocabulary"] = (
            f"{ledger.as_written} declares no fork on failure_buckets, so there "
            "is no vocabulary to bucket into and nothing was stamped for the "
            "histogram. The five buckets are the five routes of the ledger's own "
            "fork; a bucketer that names its own would be routing a diagnosis on "
            "a vocabulary the engine has never heard of."
        )

    instrument.measured(
        "failing_cases_n",
        total,
        how=(
            f"counted {total} case(s) in {failures_path} carrying "
            f"{input_field!r}, {expected_field!r} and an answer"
        ),
        # Wall 8. G0 in the AI ledger is "something to measure against", and a
        # file of amplified cases is the same rows counted twice.
        from_file=failures_path,
    )
    instrument.measured(
        "baseline_success_rate",
        rate,
        how=(
            f"{passed} of {total} case(s) matched what should have happened, by "
            f"exact match after case and whitespace normalisation; "
            f"{len(unterminated)} run(s) never terminated and are counted as "
            f"failures with no bucket"
        ),
        from_file=failures_path,
    )
    instrument.measured(
        "can_rerun_failures",
        True,
        how=(
            f"this call graded {total} case(s) against answers the agent "
            f"produced for them, from {answers_path or failures_path}"
        ),
        from_file=answers_path or failures_path,
    )
    instrument.measured(
        "failure_rate_measured",
        True,
        how=f"a rate over {total} case(s), not an impression: {passed} passed",
        from_file=failures_path,
    )
    if routable:
        instrument.measured(
            "failure_buckets",
            dict(sorted(routable.items())),
            how=(
                f"{sum(routable.values())} of {total - passed - len(unterminated)} "
                f"failing case(s) bucketed by rule (never by a model): "
                + ", ".join(f"{k} {v}" for k, v in sorted(routable.items()))
                + (
                    f"; {unclassified} failure(s) no rule could name are left out "
                    "rather than guessed at"
                    if unclassified
                    else ""
                )
            ),
            from_file=failures_path,
        )
    else:
        payload["no_histogram_recorded"] = (
            "Nothing was recorded for failure_buckets. "
            + (
                "Every failure this reader saw was one no rule could name, and a "
                "failure nobody classified is a fact about this bucketer rather "
                "than about the agent."
                if unclassified
                else "No case failed with an answer to bucket."
            )
        )
    return payload


def _load_pairs(
    failures_path: str,
    input_field: str,
    expected_field: str,
    answer_field: str,
    answers_path: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The cases, joined to their answers, plus what could not be read.

    The answers may live in the failure file itself or in a second file in the
    same row order. A row missing any of the three fields is DROPPED and
    counted, never defaulted: a case with no expected answer cannot be graded,
    and grading it against an empty string would put a pass or a fail in the
    denominator that nobody measured.
    """
    refusals: list[dict[str, Any]] = []
    root = Path(failures_path)
    if not root.exists():
        return [], [
            refusal(
                "no_such_file",
                read=f"nothing at {root}",
                needed="a failure set on this machine",
            )
        ]
    limit = dataquality.whole_document_limit(root)
    if limit is not None:
        return [], [refusal("too_large", read=limit["why"], needed=limit["what_to_do"])]

    rows = list(dataquality.iter_records(root))
    answers: list[Mapping[str, Any]] = []
    if answers_path:
        other = Path(answers_path)
        if not other.exists():
            refusals.append(
                refusal(
                    "no_such_answers_file",
                    read=f"nothing at {other}",
                    needed="the file of answers your agent produced",
                )
            )
        else:
            answers = list(dataquality.iter_records(other))
            if len(answers) != len(rows):
                refusals.append(
                    refusal(
                        "row_counts_disagree",
                        read=(
                            f"{len(rows)} case(s) and {len(answers)} answer(s); "
                            "they are joined by row order"
                        ),
                        needed=(
                            "the same number of rows in the same order, or a "
                            "trace id on both sides"
                        ),
                    )
                )

    cases: list[dict[str, Any]] = []
    dropped = 0
    for index, row in enumerate(rows):
        merged: dict[str, Any] = dict(row)
        if index < len(answers):
            merged.update({str(k): v for k, v in answers[index].items()})
        question = merged.get(str(input_field))
        expected = merged.get(str(expected_field))
        answer = merged.get(str(answer_field))
        if dataquality.is_null(question) or dataquality.is_null(expected):
            dropped += 1
            continue
        if dataquality.is_null(answer) and _did_not_terminate(merged) is not True:
            dropped += 1
            continue
        cases.append(
            {
                "input": question,
                "expected": expected,
                "answer": "" if answer is None else answer,
                "run_id": str(_field(merged, RUN_ID_FIELDS) or ""),
                "did_not_terminate": _did_not_terminate(merged),
            }
        )
    if dropped:
        refusals.append(
            refusal(
                "rows_dropped",
                read=(
                    f"{dropped} row(s) of {len(rows)} carry no {input_field!r}, no "
                    f"{expected_field!r} or no {answer_field!r}"
                ),
                needed=(
                    "all three on every row. A row with no expected answer cannot "
                    "be graded, and grading it against nothing would put a result "
                    "nobody measured into the denominator."
                ),
            )
        )
    return cases, refusals


@tool(
    "bound_the_loop",
    description=(
        "Measure what a set of agent runs cost and whether they stop: steps per "
        "run, tool calls per run, tokens per run and wall clock per run, over "
        "every run in an OTLP trace file. Never one run - termination is a "
        "property of a bound over a distribution. It reports tokens and refuses "
        "to turn them into money, because no price in a trace carries a date."
    ),
    schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "An OTLP trace file on this machine, or a folder of them."
                ),
            },
            "step_cap": {
                "type": "integer",
                "description": (
                    "A step count above which a run is reported as having hit a "
                    "bound. A run that hit it is evidence of NON-termination "
                    "within that bound, never of termination."
                ),
            },
        },
        "required": ["path"],
    },
    reads=("filesystem", "traces"),
    writes=("facts",),
    measures=("run_terminates", "tokens_per_run"),
    bounds=("step_cap",),
    provides=("agent.loop.bound",),
    label="Bound the loop",
    group="Look",
    verb="bound cost and termination",
    order=43,
)
def bound_the_loop(
    path: str, step_cap: int | None = None, *, instrument: Instrument
) -> dict[str, Any]:
    """Steps, tokens and wall clock over a SET of runs, and no currency at all.

    ## Why a set, always

    A single run that stopped proves nothing. Termination is a property of a
    bound over a distribution, and the distribution has a tail which is the
    whole risk - so the report is the set, the maximum, and how many hit the
    cap. `run_terminates` is every run in the set reaching a terminal state, and
    a run that hit OUR cap is evidence of non-termination within that bound
    rather than of anything else.

    And the gate this feeds may not be satisfied by somebody saying they set
    `max_iterations`. Sixty-eight confirmed infinite agentic loops were found
    across 47 projects, in eight frameworks, over 6,549 repositories, and every
    one of them had a counter; the counters sat outside the feedback path that
    recursed.

    ## WHAT THIS TOOL STAMPS, AND THE PARTIAL-TOTAL REFUSAL

    It stamps `run_terminates` (every run in the set reached a root span that
    ended) and `tokens_per_run` (the median per-run token total over the set),
    in one call, because each is the reading that makes the other mean
    something: a flag with no size beside it is a badge, and a size with no
    proof of stopping is a bill with no end.

    **The denomination is tokens, deliberately.** No instrument can read US
    dollars from a trace: OpenTelemetry defines no cost attribute at all, and
    OpenInference's `llm.cost.*` is somebody else's multiplication against an
    undated price table. The ledger was denominated in what an instrument can
    read on 2026-08-25; a currency figure stays available as a DERIVED display
    whose provenance says "tokens MEASURED times a price STATED by you on
    <date>", which is what `app/provenance.py` already exists to express.

    **And the total is all-or-nothing.** If any inference span in any run
    lacks its token counts, nothing is stamped: a total missing three spans
    reads as complete, and a complete-looking number is the most dangerous
    thing this tool could hand a gate.
    """
    read = read_spans(path)
    agent = _agent_spans(read["spans"])
    grouped = runs_of(agent)
    cap = data.bounded(step_cap, 0, 0, 1_000_000) if step_cap is not None else 0

    rows: list[dict[str, Any]] = []
    for trace_id, spans in sorted(grouped.items()):
        tool_spans = [s for s in spans if is_tool_span(s["attributes"])]
        tokens = _tokens_of_run(spans)
        starts = [s["start_ns"] for s in spans if s["start_ns"] is not None]
        ends = [s["end_ns"] for s in spans if s["end_ns"] is not None]
        wall = (max(ends) - min(starts)) / 1e9 if starts and ends else None
        asserted_cost = [
            {"attribute": key, "value": s["attributes"][key]}
            for s in spans
            for key in COST_KEYS
            if key in s["attributes"]
        ]
        rows.append(
            {
                "trace_id": trace_id,
                "steps": len(spans),
                "tool_calls": len(tool_spans),
                "tokens": tokens,
                "wall_clock_seconds": wall,
                "terminated": _terminated(spans),
                "hit_the_cap": bool(cap) and len(spans) >= cap,
                "cost_in_the_file": asserted_cost,
            }
        )

    steps = [row["steps"] for row in rows]
    token_totals = [row["tokens"]["total"] for row in rows if row["tokens"]["ok"]]
    walls = [row["wall_clock_seconds"] for row in rows if row["wall_clock_seconds"]]
    stopped = [row["terminated"] for row in rows]
    hit = [row for row in rows if row["hit_the_cap"]]
    every_run_stopped = bool(rows) and all(one is True for one in stopped)
    unknown = [row["trace_id"] for row in rows if row["terminated"] is None]
    any_cost_in_the_file = any(row["cost_in_the_file"] for row in rows)

    payload: dict[str, Any] = {
        "ok": bool(rows),
        "path": str(path),
        "runs": len(rows),
        "per_run": rows,
        "steps": _spread(steps),
        "tokens_per_run": _spread(token_totals),
        "wall_clock_seconds": _spread(walls),
        "runs_without_a_token_total": len(rows) - len(token_totals),
        "runs_that_hit_the_cap": len(hit),
        "step_cap": cap or None,
        "runs_whose_termination_is_unknown": unknown,
        "run_terminates": every_run_stopped,
        "refusals": list(read["refusals"]),
        "provenance": {
            "runs": "measured",
            "steps": "measured",
            "tokens_per_run": "measured",
            "wall_clock_seconds": "measured",
            "run_terminates": "measured",
        },
        "no_currency": REFUSALS["currency"],
        "a_counter_is_not_a_proof": REFUSALS["counter_is_not_termination"],
    }
    if len(rows) - len(token_totals):
        payload["token_totals_refused"] = REFUSALS["partial_total"]
    if hit:
        payload["hitting_the_cap_means"] = (
            f"{len(hit)} run(s) reached {cap} spans. A run that hit our cap is "
            "evidence of non-termination WITHIN that bound. It is never evidence "
            "that the run terminates."
        )
    if any_cost_in_the_file:
        payload["cost_in_the_file_is_asserted"] = (
            "Some spans carry an llm.cost.* attribute. That is somebody else's "
            "arithmetic against a price table with no date in this file, so it "
            "is reported as ASSERTED and is not a measurement of anything here."
        )
    if not rows:
        payload["nothing_was_recorded"] = (
            "No run was read, so there is nothing to bound. A set of runs is the "
            "unit every number here is denominated in."
        )
        return payload

    # STAMP ORDER IS THE DESIGN, AND IT IS THE SAME RULE read_agent_traces
    # FOLLOWS: the reading goes in FIRST so the flag is never the only thing
    # this call minted. `Instrument.measured` refuses a lone boolean that was
    # handed a path - correctly - and run_terminates is a boolean, so it may
    # only be stamped once tokens_per_run is already on the record beside it.

    # THE TOKEN STAMP IS ALL-OR-NOTHING, AND THAT IS THE WHOLE DESIGN. A total
    # missing three inference spans reads as complete and is smaller than it -
    # the most dangerous number a gate could be handed - so a single refused
    # run refuses the fact for the whole set, with the refusal named.
    partial = len(rows) - len(token_totals)
    if partial:
        payload["token_totals_refused"] = REFUSALS["partial_total"]
        payload["tokens_per_run_not_stamped"] = (
            f"{partial} of {len(rows)} run(s) carry an inference span without "
            "token counts, so no per-run total here could be trusted complete. "
            "Fix the instrumentation on those spans and re-read; nothing is "
            "stamped from a set this tool knows is short."
        )
        return payload

    median_tokens = _spread(token_totals).get("median")
    try:
        instrument.measured(
            "tokens_per_run",
            median_tokens,
            how=(
                f"median across {len(token_totals)} run(s) in {path}, each "
                "total summed from every inference span's usage attributes; "
                f"spread {_spread(token_totals)}"
            ),
            from_file=path,
        )
    except MeasurementError as error:
        payload["tokens_per_run_not_stamped"] = str(error)
        return payload

    try:
        instrument.measured(
            "run_terminates",
            every_run_stopped,
            how=(
                f"every one of {len(rows)} run(s) in {path} reached a root span "
                f"that ended, over {sum(steps)} spans; median "
                f"{median_tokens} tokens/run stands beside this flag"
            ),
            from_file=path,
        )
    except MeasurementError as error:
        payload["run_terminates_not_stamped"] = str(error)
    return payload


def _spread(values: list[Any]) -> dict[str, Any]:
    """A set of runs, reported as a set: n, min, median, max, total.

    NO MEAN, DELIBERATELY. A loop's step count is a distribution with a tail and
    the tail is the entire risk; a mean is the one summary that hides it.
    """
    numbers = sorted(one for one in values if isinstance(one, (int, float)))
    if not numbers:
        return {"n": 0, "says": "no run carried this, so there is nothing to report"}
    middle = len(numbers) // 2
    median = (
        numbers[middle]
        if len(numbers) % 2
        else (numbers[middle - 1] + numbers[middle]) / 2
    )
    return {
        "n": len(numbers),
        "min": numbers[0],
        "median": median,
        "max": numbers[-1],
        "total": sum(numbers),
    }


# ---------------------------------------------------------------------------
# What a graded run leaves behind, so a second one can be compared to it
# ---------------------------------------------------------------------------

#: How much of a case's text is kept. Enough to read a row back and recognise
#: it; not enough for this table to become a copy of somebody's failure export.
STORED_TEXT_CHARS = 2_000


def ensure_tables() -> None:
    """Bring the schema up to date. The agent tables are migration 12's."""
    from app import migrations

    migrations.migrate()


def _clip(value: Any) -> str:
    body = str(value if value is not None else "")
    if len(body) <= STORED_TEXT_CHARS:
        return body
    return body[:STORED_TEXT_CHARS] + " ... [truncated by app/tools/agents.py]"


def case_key(question: Any, expected: Any) -> str:
    """What makes two rows the same QUESTION, across two recordings.

    NOT THE ROW'S POSITION, and that is the whole design. `eval_results` pairs
    on `row_index` because an eval set is a file this harness carved and counts
    through. A failure set is the person's export, and between two recordings
    they will have re-exported it, sorted it, dropped a fixed case or added
    three new ones - so pairing on position compares case 7 of one run against
    a different case 7 of the other and calls the difference an improvement.

    The digest is over the input and the expected answer, normalised the way
    `evals.grade` normalises before it compares, so two spellings that this
    product would grade identically are one case here too.
    """
    left = dataquality.normalise_text(str(question if question is not None else ""))
    right = dataquality.normalise_text(str(expected if expected is not None else ""))
    return hashlib.sha256(f"{left}\x00{right}".encode()).hexdigest()[:32]


def set_signature(cases: Iterable[Mapping[str, Any]]) -> str:
    """A digest of the QUESTIONS in a failure set, order-independent.

    Sorted before hashing, so the same export saved twice by two different
    tools is one signature. It answers "are these two runs about the same set
    of questions" without trusting that the file kept its name or its path -
    which a person moving a file between two recordings is entitled to do.
    """
    keys = sorted(case_key(case.get("input"), case.get("expected")) for case in cases)
    return hashlib.sha256("\n".join(keys).encode()).hexdigest()[:32]


def record_run(**columns: Any) -> dict[str, Any]:
    ensure_tables()
    names = sorted(columns)
    with db.session() as connection:
        cursor = connection.execute(
            "INSERT INTO agent_runs (%s) VALUES (%s)"  # noqa: S608 - names are ours
            % (", ".join(names), ", ".join("?" for _ in names)),
            tuple(columns[name] for name in names),
        )
        row = connection.execute(
            "SELECT * FROM agent_runs WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return dict(row)


def record_cases(run_id: int, rows: Iterable[Mapping[str, Any]]) -> int:
    """Write one row per graded case. Returns how many were written.

    A DUPLICATED QUESTION IS REFUSED RATHER THAN AVERAGED. The unique index on
    `(run_id, case_key)` is the wall; this reports how many rows survived it,
    so a caller can say "your export has the same question twice" instead of
    silently recording one verdict for two rows. `INSERT OR IGNORE` rather than
    a raise, because a duplicate is the person's file being ordinary and not
    the product falling over.
    """
    ensure_tables()
    written = 0
    with db.session() as connection:
        for row in rows:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO agent_results "
                "(run_id, case_key, input, expected, answer, passed, terminated, "
                " bucket, bucketed_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    int(run_id),
                    str(row["case_key"]),
                    _clip(row.get("input")),
                    _clip(row.get("expected")),
                    _clip(row.get("answer")),
                    1 if row.get("passed") else 0,
                    0 if row.get("terminated") is False else 1,
                    row.get("bucket") or None,
                    str(row.get("bucketed_by") or "rules"),
                ),
            )
            written += cursor.rowcount or 0
    return written


def get_run(run_id: int) -> dict[str, Any] | None:
    ensure_tables()
    with db.session() as connection:
        row = connection.execute(
            "SELECT * FROM agent_runs WHERE id = ?", (int(run_id),)
        ).fetchone()
    return None if row is None else dict(row)


def runs_in(thread_id: int, limit: int = 50) -> list[dict[str, Any]]:
    """Every agent run in this conversation, newest first.

    THREAD SCOPED, for `eval_runs`' reason: every fact these runs produce is
    declared `scope: thread`, and a run readable from another conversation
    would be a measurement about somebody else's system answering this
    person's gates.
    """
    ensure_tables()
    with db.session() as connection:
        rows = connection.execute(
            "SELECT * FROM agent_runs WHERE thread_id = ? ORDER BY id DESC LIMIT ?",
            (int(thread_id), int(limit)),
        ).fetchall()
    return [dict(row) for row in rows]


def cases_of(run_id: int) -> list[dict[str, Any]]:
    ensure_tables()
    with db.session() as connection:
        rows = connection.execute(
            "SELECT * FROM agent_results WHERE run_id = ? ORDER BY case_key",
            (int(run_id),),
        ).fetchall()
    return [dict(row) for row in rows]


@tool(
    "read_agent_results",
    description=(
        "Read back a graded failure run, or compare two of them. With "
        "`against`, it compares them PAIRWISE over the cases both graded - "
        "McNemar's exact test - and when the cases cannot separate the two it "
        "says NO EVIDENCE rather than reporting a small win. This is how you "
        "find out whether a fix worked. Costs nothing and asks nothing of your "
        "agent."
    ),
    schema={
        "type": "object",
        "properties": {
            "run_id": {
                "type": "integer",
                "description": "Which recording to read. Default: the newest in this conversation.",
            },
            "against": {
                "type": "integer",
                "description": (
                    "Compare `run_id` against this earlier recording, paired on "
                    "the cases both graded."
                ),
            },
        },
    },
    reads=("runs",),
    writes=(),
    approval="never",
    provides=("agent.results.read",),
    label="Read back a graded run, or compare two",
    group="Look",
    verb="read back what a graded run found",
    order=44,
)
def read_agent_results(
    run_id: int | None = None,
    against: int | None = None,
    *,
    instrument: Instrument,
    ledger: diagnosis.Spec,
) -> dict[str, Any]:
    """What a recording found, and whether a second one moved it.

    ## The comparison is PAIRED and that is the whole point

    `docs/PHASES.md` names the six outcomes this ledger reaches most often -
    *the tool description is the bug*, *the prompt is the bug*, *constrain the
    output* - and every one is a cheap local fix. A cheap fix is worth naming
    only if the person can find out whether it worked, and finding that out by
    subtracting two aggregate rates is how a difference that is really noise
    gets reported as an improvement.

    So two runs are compared over the cases BOTH graded, keyed by question
    rather than by position, with McNemar's exact test over the ones that
    changed their verdict. `evals.mcnemar` and `evals.resolution_for` are the
    same functions the eval bench uses; a second implementation here would be a
    second answer to "is this difference real", and the two would disagree
    within a month.

    ## What it refuses

    Two runs over different question sets. `signature` is a digest of the
    questions themselves, so a person who re-exported their failures under a
    new path still gets a comparison - and a person who changed WHICH failures
    they are testing gets told that the sets differ, with the counts, instead
    of a delta measured across two subjects.
    """
    thread_id = instrument.thread_id
    if thread_id is None:
        return {
            "ok": False,
            "error": "no_thread",
            "detail": (
                "A recording belongs to one conversation, for the same reason "
                "every fact it produced does."
            ),
        }

    recent = runs_in(int(thread_id))
    if not recent:
        return {
            "ok": False,
            "error": "no_runs",
            "summary": (
                "Nothing has been graded in this conversation yet. "
                "run_the_failures records what it grades; run it first."
            ),
        }

    newest = recent[0]
    run = get_run(int(run_id)) if run_id is not None else newest
    if run is None or int(run["thread_id"]) != int(thread_id):
        return {
            "ok": False,
            "error": "no_such_run",
            "summary": (
                f"There is no recording {run_id} in this conversation. "
                f"The ones there are: {[row['id'] for row in recent]}."
            ),
        }

    cases = cases_of(int(run["id"]))
    mine = {row["case_key"]: row for row in cases}
    report: dict[str, Any] = {
        "ok": True,
        "run_id": int(run["id"]),
        "label": run["label"],
        "failures_path": run["failures_path"],
        "signature": run["signature"],
        "graded": int(run["graded"]),
        "passed": int(run["passed"]),
        "did_not_terminate": int(run["unterminated"]),
        "success_rate": (int(run["passed"]) / int(run["graded"])) if run["graded"] else None,
        "resolution": evals.resolution_for(int(run["passed"]), int(run["graded"])),
        "failure_buckets": json.loads(run["buckets_json"] or "{}"),
        "cases_kept": len(cases),
        "runs_here": [
            {"run_id": row["id"], "label": row["label"], "graded": row["graded"],
             "passed": row["passed"], "signature": row["signature"]}
            for row in recent
        ],
        "measured": [],
        "records_nothing": (
            "No fact was recorded. Reading back a run that already happened is "
            "not a new reading of anything."
        ),
    }

    if against is None:
        report["what_now"] = (
            "Change one thing, record your agent's answers again, run "
            "run_the_failures on the same failure set with a different label, "
            "then read this with `against` pointed at this run."
        )
        return report

    other = get_run(int(against))
    if other is None or int(other["thread_id"]) != int(thread_id):
        return {
            "ok": False,
            "error": "no_such_run",
            "summary": f"There is no recording {against} in this conversation.",
        }
    if int(other["id"]) == int(run["id"]):
        return {
            "ok": False,
            "error": "same_run",
            "summary": (
                "A run compared with itself moves nothing and resolves nothing. "
                "Point `against` at the earlier recording."
            ),
        }

    theirs = {row["case_key"]: row for row in cases_of(int(other["id"]))}
    shared = sorted(set(mine) & set(theirs))
    only_new = sorted(set(mine) - set(theirs))
    only_old = sorted(set(theirs) - set(mine))

    if not shared:
        return {
            "ok": False,
            "error": "no_shared_cases",
            "summary": (
                f"Recording {run['id']} and recording {against} share not one "
                "question, so there is nothing to pair. A comparison here is "
                "over the same failures asked twice; these are two different "
                "sets of failures."
            ),
            "only_in_this_run": len(only_new),
            "only_in_the_other": len(only_old),
        }

    improved = [key for key in shared if mine[key]["passed"] and not theirs[key]["passed"]]
    regressed = [key for key in shared if theirs[key]["passed"] and not mine[key]["passed"]]
    changed = len(improved) + len(regressed)
    new_passed = sum(1 for key in shared if mine[key]["passed"])
    old_passed = sum(1 for key in shared if theirs[key]["passed"])
    paired_new = new_passed / len(shared)
    paired_old = old_passed / len(shared)
    delta = paired_new - paired_old
    p_value = evals.mcnemar(len(improved), len(regressed))
    resolved = changed > 0 and p_value < 0.05
    same_set = run["signature"] == other["signature"]

    mismatch = (
        ""
        if same_set
        else (
            f" These two recordings are not over the same question set: "
            f"{len(only_old)} question(s) only recording {against} graded and "
            f"{len(only_new)} only recording {run['id']} graded are excluded "
            "from both sides."
        )
    )

    if resolved:
        says = (
            f"{delta:+.1%} on {len(shared)} paired case(s): {len(improved)} "
            f"improved and {len(regressed)} regressed, McNemar exact "
            f"p={p_value:.3g}. That is a real difference on these failures."
            + mismatch
        )
    elif changed == 0:
        says = (
            f"Not one of the {len(shared)} paired case(s) changed its verdict. "
            "These two recordings are the same on these failures - there is no "
            "evidence of any difference, and none to report as a small win."
            + mismatch
        )
    else:
        says = (
            f"NO EVIDENCE. The rates differ by {delta:+.1%} over the "
            f"{len(shared)} case(s) both graded, but only {changed} changed "
            f"({len(improved)} improved, {len(regressed)} regressed) and "
            f"McNemar's exact test gives p={p_value:.3g}. These failures cannot "
            "tell the two apart. Write down more failures and ask again."
            + mismatch
        )

    report.update(
        {
            "against": int(other["id"]),
            "against_label": other["label"],
            "paired_cases": len(shared),
            "same_question_set": same_set,
            "score": paired_new,
            "score_against": paired_old,
            "delta": delta,
            "improved": len(improved),
            "regressed": len(regressed),
            "changed": changed,
            "p_value": p_value,
            "test": "McNemar, two-sided exact binomial over the cases that changed",
            "resolved": resolved,
            "verdict": "different" if resolved else "no_evidence",
            "only_in_this_run": len(only_new),
            "only_in_the_other": len(only_old),
            "says": says,
            "measured_on": (
                f"the {len(shared)} case(s) both recordings graded, paired by "
                "question rather than by row position"
            ),
        }
    )
    report.pop("what_now", None)
    return report


__all__ = [
    "BUCKETS_THIS_FILE_CANNOT_DECIDE",
    "BUCKETS_THIS_FILE_CAN_DECIDE",
    "CONTAINER",
    "DID_NOT_TERMINATE",
    "REFUSALS",
    "TraceError",
    "attribute_map",
    "bound_the_loop",
    "bucket_vocabulary",
    "dialect_of",
    "is_inference_span",
    "is_tool_span",
    "read_agent_traces",
    "read_definitions",
    "read_spans",
    "read_tool_definitions",
    "refusal",
    "run_the_failures",
    "runs_of",
    "status_code",
    "tokens_of",
    "tool_name_of",
]
