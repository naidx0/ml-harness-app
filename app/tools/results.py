"""The results program: what a run measured, written down, and a draft article.

Max, 2026-09-18: *"what elements and tools and built frameworks do we provide
for this training and working loop - create data framework program, sandbox
program, environment training program etc"*, and earlier and repeatedly, that a
run should end in **"results and article"**.

Everything in this product measures. Nothing in it, until this file, wrote the
measurements down in the shape a person hands to somebody else. A thread that
ran the whole loop holds the baseline, the trivial baseline, the ruler each was
graded by, the eval set and what it can resolve, the adapter's arm and the
paired difference, the recipe and its pins, the machine - and it holds them as
rows in four tables and a transcript, which is the right shape for a machine and
no shape at all for a reader.

## THE RULE THIS FILE EXISTS TO ENFORCE

**No number reaches either page except through the ledger this module builds.**
`results.json` is that ledger: one entry per number, carrying the value, the
exact text it is rendered as, the origin word, the how-sentence and the record
it was read from. `results.md` renders entries. `article.md` renders entries and
links each one back. A number that is not an entry cannot appear, because
nothing else is ever formatted into either page - and
`tests/test_a_run_ends_in_results_and_an_article.py` tokenises both pages and
checks every token against the JSON, so this is a measurement rather than an
intention.

That is not tidiness. `app/journey_report.py` already learned the shape of the
defect: a report that showed a number with no word beside it "would be the exact
defect this product refuses everywhere else, wearing a necktie". An article is
worse than a report, because an article is the artefact that leaves the
building.

## THE FIVE ORIGIN WORDS, AND THE ONE THAT IS NEW

Four are `app/provenance.py`'s and they are used exactly as the fact ledger
wrote them: MEASURED, STATED, ASSERTED, DEFAULTED. A ledger fact's word is
copied off its row and never decided here.

RECORDED is the fifth and it is this module's, for a value read back from a
record THIS HARNESS WROTE and not from the fact ledger: the eval bench's own
tables, a run's `job.json`, a recipe's `requirements.lock`, a `tool.result` in
this thread's transcript. It is deliberately not MEASURED. Some of those values
were produced by an instrument and some were not, the record does not
distinguish, and `app/events.py::_as_a_claim` marks everything the transcript
hands back for exactly that reason. One word that says *this came out of a file
we wrote* is honest about all of them; MEASURED would be honest about some.

## WHAT IT REFUSES TO SAY

An adapter that was never scored produces an article that says the run is
unscored and stops. It does not compare the training run to the baseline, it
does not say "we would expect", and it does not reach for the base model's arm
as a stand-in. `_comparison` is the only thing that writes a comparison
sentence, it is reached only from a paired `evals.compare`, and the phrase
**"paired difference"** appears nowhere else - so the absence of a comparison is
checkable and not a matter of reading the prose carefully.

A section with nothing measured says so in one line. That is the same refusal
`app/run_record.py::price` makes - *unmeasurable renders unknown* - applied to
prose, where the temptation to fill a heading is strongest.

## WHICH PACK, AND WHY IT IS NOT `measurement`

`training.results.write`. `measurement.*` is where the facts that open gates are
measured, and this stamps nothing whatsoever - `measures=()`, no instrument,
no `Instrument` in the signature that could mint. The same argument put
`models.candidate.score` in `models`. Its subject is a training run, and the
person holding a finished run is the person who needs the write-up.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import db, events
from app.tools import datawork, evidence
from app.tools.evidence import Instrument
from app.tools.registry import tool


#: The three files, and the order they are written in. `results.json` last, so a
#: directory holding it holds all three - a reader that finds the ledger can
#: trust the two pages beside it.
RESULTS_MD = "results.md"
ARTICLE_MD = "article.md"
RESULTS_JSON = "results.json"

#: Who the article is written for. `engineer` keeps the instrument sentences -
#: which ruler, which arm, how many paired rows; `reader` drops them and keeps
#: the numbers and what they meant. Neither changes a number, and neither is
#: allowed to introduce one: both render the same entries.
AUDIENCES = ("engineer", "reader")

#: Read back from a record this harness wrote. See the module docstring.
RECORDED = "RECORDED"

#: The phrase that appears if, and only if, a paired comparison was made. A
#: test asserts its absence on an unscored run, which is why it is a constant
#: and not four sentences that happen to rhyme.
COMPARISON_PHRASE = "paired difference"

#: Every number on either page is one of these tokens. The same expression is
#: what the suite tokenises with, so "a number the page shows" means one thing.
TOKEN = re.compile(r"[0-9]+(?:[.,][0-9]+)*%?")

#: The `tool.result` payloads worth reading back for the data section, and what
#: each one is called when it is quoted. Duplicates and leakage are not on any
#: ledger - `drop_duplicates` and `check_split_leakage` both declare
#: `measures=()` and neither takes an instrument - so the transcript is the only
#: record of them there is, and reading it is the difference between a data
#: section and an empty heading.
DATA_TOOLS = ("profile_dataset", "drop_duplicates", "check_split_leakage")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _plain(value: Any) -> Any:
    """A value with any mark taken off it, as JSON can hold it.

    `app/events.py::_as_a_claim` marks every number the transcript hands back,
    and a marked int is still an int - but it is a SUBCLASS of one, and
    `json.dumps` on a subclass with instance state is a way to be surprised
    later. Everything that lands in an entry comes through here.
    """
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    if isinstance(value, str):
        return str(value)
    return value


def _percent(value: Any) -> str:
    return f"{float(value):.0%}"


def _signed_percent(value: Any) -> str:
    return f"{float(value):+.1%}"


class Ledger:
    """The numbers this write-up is allowed to use, and nothing else.

    Every entry carries the exact `text` it will be rendered as. The renderers
    never format a value themselves - they ask for an entry and print its text -
    which is what makes "every number on the page is on the ledger" a property
    of the code rather than a rule somebody has to remember.
    """

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []
        self._by_key: dict[str, dict[str, Any]] = {}

    def add(
        self,
        key: str,
        label: str,
        text: str,
        value: Any,
        *,
        origin: str,
        how: str,
        source: str,
        section: str,
    ) -> dict[str, Any]:
        entry = {
            "key": key,
            "label": label,
            "text": str(text),
            "value": _plain(value),
            "origin": str(origin),
            "how": str(how),
            "source": str(source),
            "section": section,
        }
        self.entries.append(entry)
        self._by_key[key] = entry
        return entry

    def get(self, key: str) -> dict[str, Any] | None:
        return self._by_key.get(key)

    def text(self, key: str) -> str:
        entry = self._by_key.get(key)
        return "" if entry is None else entry["text"]

    def has(self, *keys: str) -> bool:
        return all(key in self._by_key for key in keys)

    def of(self, section: str) -> list[dict[str, Any]]:
        return [entry for entry in self.entries if entry["section"] == section]


# ---------------------------------------------------------------------------
# Gathering. Nothing below measures anything; everything below reads a record.


def _the_run(run: Any) -> dict[str, Any] | None:
    """The training run this write-up is about, by id or by name.

    An integer is an id. Anything else is a name, matched exactly, newest
    first - `start_training` names a run `recipe:base_model` when nobody names
    it, so two runs of the same thing really do share a name and the newest is
    the one somebody means by it.
    """
    text = str(run or "").strip()
    if not text:
        return None
    rows = db.list_runs()
    try:
        wanted = int(text)
    except ValueError:
        wanted = None
    if wanted is not None:
        for row in rows:
            if int(row["id"]) == wanted:
                return dict(row)
        return None
    for row in rows:  # list_runs is newest first
        if str(row.get("name") or "") == text:
            return dict(row)
    return None


def _run_params(row: dict[str, Any]) -> dict[str, Any]:
    try:
        body = json.loads(str(row.get("params_json") or "{}"))
    except (TypeError, ValueError):
        return {}
    return body if isinstance(body, dict) else {}


def _facts(thread_id: int | None) -> dict[str, dict[str, Any]]:
    """The latest row per fact this thread can see.

    Latest wins, oldest-first input - the rule `app/journey_report.py` applies
    and `evidence.assemble_facts` applies, stated once more here rather than a
    fourth reading of the same table with a different tie-break.
    """
    latest: dict[str, dict[str, Any]] = {}
    try:
        for row in evidence.rows_for(thread_id):
            latest[str(row["fact"])] = row
    except Exception:  # noqa: BLE001 - a write-up never fails over its sources
        return {}
    return latest


def _transcript(thread_id: int | None) -> list[dict[str, Any]]:
    """Every `tool.result` this thread recorded, oldest first.

    Paged, because `events.since` takes a limit and a long thread is longer than
    any limit worth defaulting to - and a truncated read here would silently
    drop the data facts, which is the one thing this section is for.
    """
    if thread_id is None:
        return []
    rows: list[dict[str, Any]] = []
    after = 0
    for _page in range(40):
        try:
            batch = events.since(f"thread:{int(thread_id)}", after, 500)
        except Exception:  # noqa: BLE001
            break
        if not batch:
            break
        for row in batch:
            if row.get("kind") == "tool.result":
                rows.append(row)
        after = int(batch[-1]["id"])
        if len(batch) < 500:
            break
    return rows


def _latest_result(transcript: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    """The newest successful result of one tool, or `None`."""
    for row in reversed(transcript):
        payload = row.get("payload") or {}
        if str(payload.get("name") or "") != name:
            continue
        body = payload.get("result")
        if isinstance(body, dict) and body.get("ok"):
            return {"event_id": row.get("id"), "result": body}
    return None


def _eval_arms(thread_id: int | None) -> dict[str, Any]:
    """The baseline run, the adapter's arm and the base model's arm.

    `evals.SANDBOX_ARM_PREFIX` is what tells an arm from a baseline, and it is
    read rather than spelled: `app/tools/training.py::_store_an_arm` writes it
    and `propose.the_baseline_run_to_beat` reads it, and a third literal is how
    a mark stops being read.
    """
    from app.tools import evals

    out: dict[str, Any] = {"baseline": None, "adapter": None, "base": None}
    if thread_id is None:
        return out
    try:
        rows = evals.runs_in(int(thread_id))
    except Exception:  # noqa: BLE001
        return out
    for row in rows:  # newest first
        provider = str(row.get("provider_name") or "")
        graded = int(row.get("graded") or 0)
        if graded <= 0:
            continue
        if provider == f"{evals.SANDBOX_ARM_PREFIX}adapter":
            out["adapter"] = out["adapter"] or dict(row)
        elif provider == f"{evals.SANDBOX_ARM_PREFIX}base":
            out["base"] = out["base"] or dict(row)
        elif not provider.startswith(evals.SANDBOX_ARM_PREFIX):
            out["baseline"] = out["baseline"] or dict(row)
    return out


def _fact_entry(
    ledger: Ledger,
    facts: dict[str, dict[str, Any]],
    name: str,
    label: str,
    section: str,
    *,
    render=None,
) -> dict[str, Any] | None:
    """One ledger fact as an entry, ORIGIN COPIED OFF THE ROW.

    The origin word is never decided here. A fact the person STATED renders
    STATED; a fact a model ASSERTED renders ASSERTED and is on the page under
    that word rather than left out, because a number that was on the thread and
    is missing from the write-up is a different kind of lie.
    """
    row = facts.get(name)
    if row is None:
        return None
    value = row.get("value")
    if value is None:
        return None
    text = render(value) if render else f"{_plain(value)}"
    if not TOKEN.search(text):
        return None
    return ledger.add(
        name,
        label,
        text,
        value,
        origin=str(row.get("origin") or "DEFAULTED"),
        how=str(row.get("how") or "no how-sentence was recorded with this fact"),
        source=(
            f"the fact ledger, stamped by {row.get('tool') or 'an unnamed tool'}"
        ),
        section=section,
    )


def gather(run: Any, thread_id: int | None, into: Path) -> dict[str, Any]:
    """Everything the write-up can say, with every number on one ledger."""
    from app.tools import evals

    row = _the_run(run)
    if row is None:
        known = [
            f"{item['id']}: {item.get('name') or 'unnamed'}"
            for item in db.list_runs()[:10]
        ]
        return {
            "ok": False,
            "error": "no_such_run",
            "detail": (
                f"No training run matches {str(run)!r}. A run is named by the id "
                "start_training returned, or by its name."
            ),
            "runs": known,
            "nothing_was_written": True,
        }

    ledger = Ledger()
    params = _run_params(row)
    facts = _facts(thread_id)
    transcript = _transcript(thread_id)
    arms = _eval_arms(thread_id)

    # -- the run itself ----------------------------------------------------
    ledger.add(
        "run_id",
        "Run id",
        str(int(row["id"])),
        int(row["id"]),
        origin=RECORDED,
        how="the runs table's primary key, written when start_training created it",
        source="the runs table",
        section="run",
    )
    for key, label in (
        ("max_steps", "Training steps"),
        ("max_seq_len", "Sequence length"),
        ("batch_size", "Batch size"),
        ("lora_r", "LoRA rank"),
        ("learning_rate", "Learning rate"),
    ):
        value = params.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            ledger.add(
                key,
                label,
                f"{_plain(value)}",
                value,
                origin=RECORDED,
                how=(
                    "read from this run's own params_json, which start_training "
                    "wrote from the configuration it launched"
                ),
                source="the runs table",
                section="run",
            )

    # -- the machine -------------------------------------------------------
    for name, label, render in (
        ("vram_gb", "Video memory", lambda v: f"{float(v):g} GB"),
        ("ram_gb", "System memory", lambda v: f"{float(v):g} GB"),
        ("disk_free_gb", "Free disk", lambda v: f"{float(v):g} GB"),
    ):
        _fact_entry(ledger, facts, name, label, "machine", render=render)

    # -- the data ----------------------------------------------------------
    _fact_entry(
        ledger, facts, "labeled_examples_n", "Labelled rows", "data",
        render=lambda v: f"{int(v):,}",
    )
    _fact_entry(
        ledger, facts, "eval_size_n", "Eval set rows", "data",
        render=lambda v: f"{int(v):,}",
    )
    profiled = _latest_result(transcript, "profile_dataset")
    if profiled:
        duplicates = (profiled["result"].get("duplicates") or {}).get("exact")
        if isinstance(duplicates, int):
            ledger.add(
                "exact_duplicates_profiled",
                "Exact duplicates found",
                f"{int(duplicates):,}",
                duplicates,
                origin=RECORDED,
                how=(
                    "counted by profile_dataset over "
                    f"{profiled['result'].get('path') or 'a file this thread named'}"
                    ", read back from this thread's transcript"
                ),
                source=f"tool.result event {profiled['event_id']}",
                section="data",
            )
    deduped = _latest_result(transcript, "drop_duplicates")
    if deduped:
        removed = deduped["result"].get("rows_removed")
        if isinstance(removed, int):
            ledger.add(
                "duplicates_removed",
                "Duplicate rows removed",
                f"{int(removed):,}",
                removed,
                origin=RECORDED,
                how=(
                    "drop_duplicates wrote a deduplicated copy and reported what "
                    "it took out; read back from this thread's transcript"
                ),
                source=f"tool.result event {deduped['event_id']}",
                section="data",
            )
    leaked = _latest_result(transcript, "check_split_leakage")
    if leaked and leaked["result"].get("ran"):
        rows_leaked = leaked["result"].get("leaked_rows")
        if isinstance(rows_leaked, int):
            ledger.add(
                "leaked_rows",
                "Eval rows that also appear in train",
                f"{int(rows_leaked):,}",
                rows_leaked,
                origin=RECORDED,
                how=(
                    "check_split_leakage compared the two splits row by row; "
                    "read back from this thread's transcript"
                ),
                source=f"tool.result event {leaked['event_id']}",
                section="data",
            )

    # -- the baseline ------------------------------------------------------
    baseline_report: dict[str, Any] | None = None
    if arms["baseline"]:
        try:
            baseline_report = evals.read(int(arms["baseline"]["id"]), failures=0)
        except Exception:  # noqa: BLE001
            baseline_report = None
    if baseline_report and baseline_report.get("ok"):
        run_id = int(baseline_report["run_id"])
        ledger.add(
            "baseline_run_id",
            "Baseline eval run",
            str(run_id),
            run_id,
            origin=RECORDED,
            how="the eval bench's own run id for the run that graded the baseline",
            source="the eval_runs table",
            section="baseline",
        )
        score = baseline_report.get("score")
        if isinstance(score, (int, float)):
            ledger.add(
                "baseline_score",
                "Baseline score",
                _percent(score),
                score,
                origin=RECORDED,
                how=(
                    f"{baseline_report['correct']} of {baseline_report['graded']} "
                    f"rows graded correct by {baseline_report['metric']}, counted "
                    "off the stored rows of that run"
                ),
                source=f"eval run {run_id}",
                section="baseline",
            )
        trivial = baseline_report.get("trivial_baseline_score")
        if isinstance(trivial, (int, float)):
            ledger.add(
                "trivial_baseline_score",
                "Always answering the most common label",
                _percent(trivial),
                trivial,
                origin=RECORDED,
                how=(
                    "the share of the same rows that the single most common "
                    f"expected answer ({baseline_report.get('trivial_answer')!r}) "
                    "gets right, by the same ruler"
                ),
                source=f"eval run {run_id}",
                section="baseline",
            )
        ledger.add(
            "baseline_graded",
            "Rows graded",
            f"{int(baseline_report['graded']):,}",
            int(baseline_report["graded"]),
            origin=RECORDED,
            how="the number of stored result rows that run holds",
            source=f"eval run {run_id}",
            section="baseline",
        )
    else:
        # The ledger's own facts are the fallback, and they are a different
        # reading of the same quantity: a baseline measured through
        # `measure_baseline` stamps without storing an eval run.
        _fact_entry(
            ledger, facts, "baseline_score", "Baseline score", "baseline",
            render=_percent,
        )
        _fact_entry(
            ledger,
            facts,
            "trivial_baseline_score",
            "Always answering the most common label",
            "baseline",
            render=_percent,
        )

    # -- the adapter -------------------------------------------------------
    adapter_report: dict[str, Any] | None = None
    comparison: dict[str, Any] | None = None
    if arms["adapter"]:
        try:
            adapter_report = evals.read(int(arms["adapter"]["id"]), failures=0)
        except Exception:  # noqa: BLE001
            adapter_report = None
    if adapter_report and adapter_report.get("ok") and adapter_report.get("complete"):
        run_id = int(adapter_report["run_id"])
        ledger.add(
            "adapter_run_id",
            "Adapter eval run",
            str(run_id),
            run_id,
            origin=RECORDED,
            how="the eval bench's own run id for the arm that scored the adapter",
            source="the eval_runs table",
            section="adapter",
        )
        score = adapter_report.get("score")
        if isinstance(score, (int, float)):
            ledger.add(
                "adapter_score",
                "Adapter score",
                _percent(score),
                score,
                origin=RECORDED,
                how=(
                    f"{adapter_report['correct']} of {adapter_report['graded']} "
                    f"rows graded correct by {adapter_report['metric']}, on the "
                    "rows the baseline run graded"
                ),
                source=f"eval run {run_id}",
                section="adapter",
            )
        if baseline_report and baseline_report.get("ok"):
            try:
                comparison = evals.compare(
                    run_id, int(baseline_report["run_id"]), failures=0
                )
            except Exception:  # noqa: BLE001
                comparison = None
        if comparison and comparison.get("ok"):
            ledger.add(
                "paired_delta",
                "Paired difference against the baseline",
                _signed_percent(comparison["delta"]),
                comparison["delta"],
                origin=RECORDED,
                how=(
                    "the two runs paired row by row over the rows BOTH graded, "
                    "which is the only set on which a difference between them "
                    "means anything"
                ),
                source=(
                    f"eval runs {comparison['run_id']} and {comparison['against']}"
                ),
                section="adapter",
            )
            ledger.add(
                "paired_rows",
                "Rows both runs graded",
                f"{int(comparison['paired_rows']):,}",
                int(comparison["paired_rows"]),
                origin=RECORDED,
                how="the row indexes present in both runs' stored results",
                source=(
                    f"eval runs {comparison['run_id']} and {comparison['against']}"
                ),
                section="adapter",
            )
            ledger.add(
                "paired_improved",
                "Rows that improved",
                f"{int(comparison['improved']):,}",
                int(comparison["improved"]),
                origin=RECORDED,
                how="rows the adapter got right that the baseline got wrong",
                source=f"eval run {comparison['run_id']}",
                section="adapter",
            )
            ledger.add(
                "paired_regressed",
                "Rows that regressed",
                f"{int(comparison['regressed']):,}",
                int(comparison["regressed"]),
                origin=RECORDED,
                how="rows the baseline got right that the adapter got wrong",
                source=f"eval run {comparison['run_id']}",
                section="adapter",
            )

    # -- the recipe and its pins -------------------------------------------
    recipe_name = str(params.get("recipe") or "")
    pinned: dict[str, Any] = {}
    if recipe_name:
        from app.tools import sandbox as sandboxes

        try:
            pinned = sandboxes.pin(recipe_name)
        except Exception:  # noqa: BLE001
            pinned = {}
    for index, line in enumerate(list(pinned.get("installs") or ())):
        if not TOKEN.search(str(line)):
            continue
        ledger.add(
            f"pin_{index}",
            "Pinned requirement",
            str(line),
            str(line),
            origin=RECORDED,
            how=(
                f"a line of {recipe_name}'s requirements.lock, which is the "
                "record of exactly what that environment installs"
            ),
            source=str(pinned.get("lockfile") or "the recipe's lockfile"),
            section="environment",
        )
    if str(pinned.get("python") or ""):
        ledger.add(
            "recipe_python",
            "Python the recipe runs",
            str(pinned["python"]),
            str(pinned["python"]),
            origin=RECORDED,
            how=str(pinned.get("python_source") or "read from the environment"),
            source=str(pinned.get("interpreter") or "the recipe's interpreter"),
            section="environment",
        )

    return {
        "ok": True,
        "ledger": ledger,
        "run": row,
        "params": params,
        "thread_id": thread_id,
        "recipe": recipe_name,
        "pinned": pinned,
        "baseline": baseline_report,
        "adapter": adapter_report,
        "comparison": comparison,
        "resolution": (
            (baseline_report.get("resolution") or {}).get("says")
            if baseline_report
            else ""
        ),
        "metric": (baseline_report or {}).get("metric") or "",
        "eval_path": (baseline_report or {}).get("eval_path") or "",
        "accelerator": (facts.get("accelerator") or {}).get("value"),
        "base_model": str(_run_params(row).get("base_model") or ""),
        "into": str(into),
        "generated_at": _now(),
    }


# ---------------------------------------------------------------------------
# Rendering. Nothing here formats a value; everything here prints an entry.

#: The word beside every number, explained once, where the numbers are.
THE_KEY = (
    "Every number below carries the word that says where it came from. "
    "MEASURED means an instrument produced it while the engine watched. "
    "STATED means the person said it. ASSERTED means it was claimed without a "
    "witness, and an assertion opens no gate here. DEFAULTED means nobody "
    "supplied it. RECORDED means it was read back from a record this harness "
    "wrote - the eval bench's tables, a run's own parameters, a recipe's "
    "lockfile, this conversation's transcript - which is not a fresh reading "
    "and is not anybody's claim."
)

#: Headings, in the order the loop runs in. The key is what an entry's
#: `section` holds; the sentence is what stands there when nothing measured it.
SECTIONS: tuple[tuple[str, str, str], ...] = (
    (
        "run",
        "The run",
        "Nothing about this run's configuration is on record.",
    ),
    (
        "machine",
        "The machine",
        "No hardware reading is on this conversation's ledger, so nothing is "
        "said about the machine. inspect_hardware is the instrument that would "
        "put it there.",
    ),
    (
        "data",
        "The data",
        "No row count, duplicate count or leakage check is on this "
        "conversation's record, so nothing is said about the data.",
    ),
    (
        "baseline",
        "The baseline",
        "No baseline was measured on this conversation, so there is nothing to "
        "compare anything against.",
    ),
    (
        "adapter",
        "What training produced",
        "The adapter from this run was never scored, so this run is unscored "
        "and no comparison can be shown.",
    ),
    (
        "environment",
        "The environment",
        "This run names no recipe with a lockfile, so there is no pinned "
        "version list to report.",
    ),
)


def _anchor(title: str) -> str:
    return title.lower().replace(" ", "-")


def render_results(gathered: dict[str, Any]) -> str:
    """`results.md`: every number, its origin word and its how-sentence.

    A table per section, and the how-sentence in the table rather than in a
    footnote - `app/journey_report.py` makes the same choice for the same
    reason. A reader meets the number and the reason for believing it in one
    movement, or they meet the number.
    """
    ledger: Ledger = gathered["ledger"]
    out: list[str] = [
        "# Results",
        "",
        f"Run `{gathered['run'].get('name') or ''}`"
        + (f", recipe `{gathered['recipe']}`" if gathered["recipe"] else "")
        + (
            f", base model `{gathered['base_model']}`"
            if gathered["base_model"]
            else ""
        )
        + ".",
        "",
        THE_KEY,
        "",
    ]
    for key, title, nothing in SECTIONS:
        rows = ledger.of(key)
        out.append(f"## {title}")
        out.append("")
        if not rows:
            out.append(nothing)
            out.append("")
            continue
        out.append("| Quantity | Value | Origin | How |")
        out.append("| --- | --- | --- | --- |")
        for entry in rows:
            out.append(
                "| {label} | {text} | {origin} | {how} |".format(
                    label=entry["label"],
                    text=entry["text"],
                    origin=entry["origin"],
                    how=entry["how"].replace("|", "/"),
                )
            )
        out.append("")
        if key == "machine" and gathered.get("accelerator"):
            # NOT A NUMBER AND STILL A FACT. `inspect_hardware` stamps
            # `accelerator` as a word, and a machine section that printed only
            # the gigabytes would leave out the one field that decides whether
            # any of them can be used.
            out.append(
                f"Accelerator: `{gathered['accelerator']}`, stamped by "
                "inspect_hardware on this conversation."
            )
            out.append("")
        if key == "baseline" and gathered.get("resolution"):
            out.append(f"**What this eval set can resolve.** {gathered['resolution']}")
            out.append("")
        if key == "baseline" and gathered.get("metric"):
            out.append(
                f"Graded by `{gathered['metric']}`"
                + (f", over `{gathered['eval_path']}`." if gathered["eval_path"] else ".")
            )
            out.append("")
    out.append("## Where these came from")
    out.append("")
    out.append(
        "Every row above is an entry in `results.json` beside this file, with "
        "its value, its origin and the record it was read from. No number "
        "appears on this page that is not in that file."
    )
    out.append("")
    return "\n".join(out)


def _link(ledger: Ledger, key: str, section_title: str) -> str:
    """One number, as a link into `results.md`. The ONLY route a number takes.

    An article's numbers have to be checkable by the person reading the article,
    which means every one of them is a link to the row that carries its origin
    and its how-sentence. It also means the article cannot state a number the
    ledger does not hold: there is no branch here that renders a bare value.
    """
    text = ledger.text(key)
    return f"[{text}](results.md#{_anchor(section_title)})" if text else ""


def _comparison(gathered: dict[str, Any], audience: str) -> str:
    """The one sentence in this module that compares two things.

    Reached only from a paired `evals.compare` that returned `ok`, and it is
    the only place `COMPARISON_PHRASE` is written. An unscored run therefore
    produces an article in which the phrase does not occur, which is a
    checkable property and not a careful reading.
    """
    ledger: Ledger = gathered["ledger"]
    comparison = gathered["comparison"]
    delta = _link(ledger, "paired_delta", "What training produced")
    rows = _link(ledger, "paired_rows", "What training produced")
    improved = _link(ledger, "paired_improved", "What training produced")
    regressed = _link(ledger, "paired_regressed", "What training produced")
    resolved = bool(comparison.get("resolved"))
    head = (
        f"The {COMPARISON_PHRASE} against the baseline is {delta} over the "
        f"{rows} rows both runs graded"
    )
    if audience == "engineer":
        head += f", with {improved} rows improved and {regressed} regressed"
    head += "."
    if resolved:
        return head + " That is a real difference on this eval set."
    return (
        head
        + " This eval set cannot tell the two apart, so that difference is not "
        "evidence of anything - it is reported because hiding it would be worse."
    )


def render_article(gathered: dict[str, Any], audience: str) -> str:
    """`article.md`: why he built it, what it does, his opinion and its use.

    The five sections are fixed, and a section with nothing measured says so in
    one line. THE ONE-LINE REFUSAL IS THE POINT: a heading with no measurement
    under it is the exact place an article invents, and every article that ever
    invented anything did it under a heading somebody felt obliged to fill.

    EVERY DIGIT ON THIS PAGE IS EITHER INSIDE A LINK TO `results.md` OR INSIDE A
    CODE SPAN, and nothing else in this function is allowed to carry one. That
    is why the resolution sentence is pointed at rather than quoted here: it is
    a real sentence full of real numbers, and quoting it would put numbers in
    the article's prose that a reader cannot click through to. The suite strips
    the links and the code spans and asserts that no digit is left, which only
    means something while that rule has no exceptions.
    """
    ledger: Ledger = gathered["ledger"]
    engineer = audience == "engineer"
    out: list[str] = [
        "# " + (f"`{gathered['run'].get('name')}`" if gathered["run"].get("name") else "A training run"),
        "",
        "*Draft. Every number links to `results.md`, which carries its origin "
        "and how it was taken. Nothing here is a number that is not on that "
        "page.*",
        "",
        "## What I set out to do",
        "",
    ]
    goal = (gathered.get("params") or {}).get("base_model")
    if goal:
        out.append(
            f"I wanted to know whether fine-tuning `{goal}` on my own rows "
            "would beat what I already had - measured on the same rows, by the "
            "same ruler, so the answer would be a comparison and not an "
            "impression."
        )
    else:
        out.append(
            "This run's record does not say which base model it trained, so I "
            "cannot state what it set out to do."
        )
    if gathered["recipe"] and ledger.of("environment"):
        out.append("")
        out.append(
            f"It ran on the `{gathered['recipe']}` recipe, which pins its own "
            "environment - the versions it installs are on `results.md`, so "
            "anybody can rebuild what this ran in."
        )
    elif gathered["recipe"]:
        # THE RECIPE IS NAMED AND ITS PINS ARE NOT ON RECORD, and those are two
        # statements. Saying "it pins its own environment" with no version list
        # beside it is the article claiming a reproducibility this write-up
        # cannot show - which is the same move as claiming a comparison.
        out.append("")
        out.append(
            f"It ran on the `{gathered['recipe']}` recipe. No lockfile for it "
            "was readable when this was written, so I cannot list the versions "
            "it installed and will not claim the run is reproducible."
        )

    out += ["", "## What the data said", ""]
    data = ledger.of("data")
    if data:
        parts = [
            f"{entry['label'].lower()}: "
            + _link(ledger, entry["key"], "The data")
            for entry in data
        ]
        out.append("Before anything was trained, the data was counted - " + "; ".join(parts) + ".")
        if engineer:
            out.append("")
            out.append(
                "Duplicates and leakage are worth the sentence they cost: a "
                "duplicated row inflates a score without adding evidence, and a "
                "train row in the eval set is not a measurement at all."
            )
    else:
        out.append(
            "Nothing about the data was measured on this conversation, so I "
            "have nothing to say about it."
        )

    out += ["", "## What the baseline said", ""]
    baseline = ledger.get("baseline_score")
    if baseline:
        sentence = (
            "The baseline scored "
            + _link(ledger, "baseline_score", "The baseline")
        )
        trivial = ledger.get("trivial_baseline_score")
        if trivial:
            sentence += (
                ". Always answering the most common label scores "
                + _link(ledger, "trivial_baseline_score", "The baseline")
                + " on the same rows, which is the number that says whether the "
                "first one is an achievement"
            )
        out.append(sentence + ".")
        if engineer and gathered.get("resolution"):
            out.append("")
            out.append(
                "What this eval set can actually resolve - the difference a "
                "score has to exceed before it is evidence rather than noise - "
                "is stated in full on `results.md`, under the baseline."
            )
    else:
        out.append(
            "No baseline was measured on this conversation, so there is nothing "
            "for this run to be better or worse than."
        )

    out += ["", "## What training did", ""]
    if ledger.get("adapter_score"):
        out.append(
            "The trained adapter scored "
            + _link(ledger, "adapter_score", "What training produced")
            + " on the rows the baseline was graded on."
        )
        if gathered.get("comparison") and gathered["comparison"].get("ok"):
            out.append("")
            out.append(_comparison(gathered, audience))
        else:
            out.append("")
            out.append(
                "The two runs were not paired, so the two scores above are not "
                "a comparison and I will not present them as one."
            )
    else:
        out.append(
            "This run is unscored: no adapter from it was ever graded, so there "
            "is no result to report and nothing to compare. That is where this "
            "section stops."
        )

    out += ["", "## What I would do next", ""]
    if ledger.get("adapter_score") and gathered.get("comparison"):
        if gathered["comparison"].get("resolved"):
            out.append(
                "The difference is real on this eval set, so the next question "
                "is whether it holds on rows nobody has looked at yet."
            )
        else:
            out.append(
                "The eval set cannot resolve the difference this run produced. "
                "More rows, not more training, is the next move - a bigger "
                "difference measured on the same thin set would be the same "
                "non-answer."
            )
    elif ledger.get("baseline_score"):
        out.append(
            "Score the adapter on the rows the baseline was graded on. Until "
            "that happens this run has cost time and produced no evidence."
        )
    else:
        out.append(
            "Measure a baseline first. Without one there is no question this "
            "run can answer."
        )
    out.append("")
    return "\n".join(out)


def _write(directory: Path, name: str, body: str) -> dict[str, Any]:
    """One file, LF endings, UTF-8, encoded BEFORE the handle is opened.

    `open(..., "w")` truncates before it encodes, so a body that cannot be
    encoded leaves a zero-length file where a page used to be. The bytes are
    made first and written second for that reason, and `newline=""` keeps the
    LF endings this repository's own files have.
    """
    payload = body.encode("utf-8")
    path = directory / name
    with open(path, "wb") as handle:
        handle.write(payload)
    return {"name": name, "path": str(path), "bytes": len(payload)}


@tool(
    "write_the_results",
    description=(
        "End a training run in results and an article. Gathers what this "
        "conversation already measured - the baseline and the trivial baseline "
        "with their ruler, the adapter's score and the paired difference, the "
        "recipe and its pinned versions, the machine, the eval set and what it "
        "can resolve, the row counts, duplicates and leakage - and writes "
        "results.md, a draft article.md and results.json into a NEW directory. "
        "Every number on both pages is in results.json with its origin and how "
        "it was taken, and no number that is not on that ledger appears at all. "
        "An adapter that was never scored produces an article that says the run "
        "is unscored and stops there."
    ),
    schema={
        "type": "object",
        "properties": {
            "run": {
                "type": "string",
                "description": (
                    "Which training run to write up: the id start_training "
                    "returned, or the run's name."
                ),
            },
            "into": {
                "type": "string",
                "description": (
                    "A NEW directory for the three files. A name that is taken "
                    "is not refused - the next free one beside it is used, and "
                    "the reply says which."
                ),
            },
            "audience": {
                "type": "string",
                "description": (
                    "Who the article is written for. 'engineer' keeps the "
                    "instrument sentences - which ruler, which arm, how many "
                    "paired rows. 'reader' keeps the numbers and drops the "
                    "apparatus. Neither changes a number."
                ),
                "enum": list(AUDIENCES),
            },
        },
        "required": ["run", "into"],
    },
    reads=("runs", "evals", "recipes", "events", "filesystem"),
    writes=("filesystem",),
    # NOTHING. A write-up that could stamp would be a tool that reads every
    # record in the product and then mints off what it read, which is wall 3's
    # whole subject. `measures=()` is also what lets it read the transcript at
    # all - see `app/events.py::_refuse_a_minting_reader`.
    measures=(),
    approval="always",
    provides=("training.results.write",),
    label="Write the results",
    group="Train",
    verb="write up this run's results and a draft article",
    order=58,
)
def write_the_results(
    run: str,
    into: str,
    audience: str = "engineer",
    *,
    instrument: Instrument | None = None,
) -> dict[str, Any]:
    """The one door. Gather, then claim the directory, then write three files.

    THE DIRECTORY IS CLAIMED AFTER THE GATHER AND BEFORE THE WRITE, which is
    `app/tools/datawork.py`'s order and its reason: `_claim` is the only call
    that creates anything, so a run that cannot be found has not made a folder.

    The thread arrives by INJECTION rather than as an argument. Which
    conversation's measurements these are is a property of the call and not
    something a model should be able to name - a tool that could be pointed at
    another thread's ledger could write up somebody else's numbers under this
    run's name.
    """
    thread_id = getattr(instrument, "thread_id", None)
    chosen = str(audience or "engineer").strip().lower()
    if chosen not in AUDIENCES:
        chosen = "engineer"

    gathered = gather(run, thread_id, Path(str(into)))
    if not gathered.get("ok"):
        return gathered

    try:
        directory = datawork._claim(into, Path(db.DB_PATH))
    except datawork.Refusal as refused:
        return refused.payload

    ledger: Ledger = gathered["ledger"]
    results_md = render_results(gathered)
    article_md = render_article(gathered, chosen)
    body = {
        "generated_at": gathered["generated_at"],
        "run_id": int(gathered["run"]["id"]),
        "run_name": gathered["run"].get("name"),
        "thread_id": thread_id,
        "recipe": gathered["recipe"],
        "base_model": gathered["base_model"],
        "audience": chosen,
        "metric": gathered["metric"],
        "accelerator": gathered["accelerator"],
        "eval_path": gathered["eval_path"],
        "resolution": gathered["resolution"],
        "scored": bool(ledger.get("adapter_score")),
        "compared": bool(gathered.get("comparison")),
        "origin_key": THE_KEY,
        "numbers": ledger.entries,
    }
    written = [
        _write(directory, RESULTS_MD, results_md),
        _write(directory, ARTICLE_MD, article_md),
        _write(
            directory,
            RESULTS_JSON,
            json.dumps(body, indent=2, sort_keys=True, default=str),
        ),
    ]

    scored = bool(ledger.get("adapter_score"))
    return {
        "ok": True,
        "into": str(directory),
        "wrote": written,
        "run_id": int(gathered["run"]["id"]),
        "run_name": gathered["run"].get("name"),
        "audience": chosen,
        "numbers": len(ledger.entries),
        "scored": scored,
        "summary": (
            f"Wrote {RESULTS_MD}, {ARTICLE_MD} and {RESULTS_JSON} into "
            f"{directory}, carrying {len(ledger.entries)} numbers, every one "
            "with its origin and how it was taken."
            + (
                ""
                if scored
                else " This run is UNSCORED - no adapter from it has been "
                "graded - so the article says so and makes no comparison."
            )
        ),
        "measured_nothing": (
            "No fact was stamped. This reads what was already measured and "
            "writes it down; a write-up that could stamp would be a tool that "
            "reads every record in the product and then mints off what it read."
        ),
    }


__all__ = [
    "AUDIENCES",
    "ARTICLE_MD",
    "COMPARISON_PHRASE",
    "Ledger",
    "RECORDED",
    "RESULTS_JSON",
    "RESULTS_MD",
    "TOKEN",
    "gather",
    "render_article",
    "render_results",
    "write_the_results",
]
