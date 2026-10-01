"""The journey, as a page somebody can read - and print.

Phase C's first surface, and Phase F's foundation. A conversation that ran the
loop holds everything a 2-3 page report needs - what was measured and by which
tool, what the gates said, what was approved and executed, whether verification
passed - but it holds it as events and rows, which is the right shape for a
machine and the wrong one for a person's manager.

## THE ONE RULE THIS MODULE EXISTS TO ENFORCE

Every number on the page carries its origin, rendered BESIDE the value rather
than in a footnote: `MEASURED`, `STATED`, `ASSERTED`, `DEFAULTED` - the same
vocabulary `app/provenance.py` speaks. A report that showed "tokens_per_run:
250" with no word beside it would be the exact defect this product refuses
everywhere else, wearing a necktie.

## WHY HTML AND NOT A PDF LIBRARY

A PDF generator is a new dependency, and a new dependency is its own step with
its own acceptance; nothing about this surface needs one. The browser already
prints a well-styled page to PDF better than most libraries, so the route
renders standalone HTML with print CSS and says so at the top. When a real
`.pdf` endpoint is owed, it is a step of its own and this module's structure is
what it would render.
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from typing import Any

from app import diagnosis, events, storm
from app.tools import evidence


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _cell(value: Any) -> str:
    """One table cell: objects as JSON, everything else escaped verbatim."""
    if isinstance(value, (dict, list)):
        return _esc(json.dumps(value, sort_keys=True)[:400])
    if value is None:
        return "-"
    return _esc(value)


def build(thread_id: int) -> dict[str, Any]:
    """Everything the page shows, as data - the JSON half of the surface."""
    thread = events.get_thread(thread_id)
    if thread is None:
        raise KeyError(f"thread {thread_id} not found")

    ledger = evidence.ledger_for_thread(thread_id)
    rows = evidence.rows_for(thread_id)

    # THE VERDICT IS WALKED ON THE WALK'S OWN SHEET, `evidence.assemble_facts`.
    #
    # 2026-09-23, the owner's thread 93: the Stage pane said "500 from
    # /api/threads/93/stage". This built its own sheet - the latest row per
    # fact, each wrapped as a plain `diagnosis.Fact(value, origin)` - and the
    # thread holds three rows the harness wrote under permission `full`
    # (`task_family`, `target_score`, `privacy`, origin DEFAULTED, each with the
    # rule in `how`). A plain `Fact(value, DEFAULTED)` is the one claim
    # `resolve_facts` refuses from a caller, so `diagnose` raised FactError and
    # every reader of this function - the Stage, `/ui/report`, the export, the
    # journey's verdict - went down with it.
    #
    # NOT "LEAVE THE FACT OUT", although that is what the refusal says. The
    # sentence is written for a caller who invented the origin; these rows were
    # not invented (`evidence.record` refuses a DEFAULTED row from anybody but
    # the harness). Left out, `target_score` falls to the FILE's default, which
    # is none, and thread 93 reads BLOCKED__DEFINE_SUCCESS_FIRST about a bar the
    # harness computed and the walk is acting on. `assemble_facts` is the one
    # producer of `diagnosis.Settled`, the carrier that lets the engine's own
    # default back in with its `how` - and it resolves two rows about one fact
    # by origin strength, so a later STATED row no longer outranks a
    # measurement here when it does not in the walk. The comment above claimed
    # this function applied "the same rule assemble_facts applies"; it did not,
    # and thread 93's verdict differed from the walk's on exactly that.
    #
    # A row whose origin is missing or outside the vocabulary cannot be stored
    # (`fact_evidence.origin` is NOT NULL and `record` checks it), so it can only
    # arrive by a hand edit or an import. It is not guessed down to DEFAULTED
    # any more - that guess is what manufactured this refusal - and not dropped
    # in silence either: `Fact` raises FactError naming the origin, and the
    # routes answer 422 with that sentence.
    sheet, trail = evidence.assemble_facts(thread_id, ledger=ledger)
    result = diagnosis.diagnose(sheet, ledger) if sheet else None

    # "FACTS ON RECORD" IS THE SAME SHEET, from the same trail. It used to be
    # the latest row per fact, and on thread 93 that put `eval_size_n` STATED
    # (row 937, the model under Full) beside a verdict that had walked on
    # MEASURED (row 926, `measure_eval_set`) - a table headed as the facts
    # contradicting the verdict printed above it. A reader who checks one
    # against the other is exactly who this page is for.
    #
    # The trail names the winner but not its stored row, and the row is where
    # the time lives. The winner is the latest row of the strongest origin
    # (`assemble_facts`' own rule), and every row of one origin has one rank,
    # so the latest stored row with the winner's fact AND origin IS the
    # winner - found here without writing a second copy of the ranking.
    winning_row: dict[str, dict[str, Any]] = {}
    origin_of = {entry["fact"]: entry["origin"] for entry in trail}
    for row in rows:
        if origin_of.get(row["fact"]) == row["origin"]:
            winning_row[row["fact"]] = row

    # `row["id"]`, NOT `row["storm"]`. `list_for_thread` selects the storms
    # table's own columns, where the primary key is `id`; `"storm"` is the name
    # `Storm.as_dict()` gives that same number on the way OUT. Reading the
    # output name off an input row raised KeyError for every thread that had a
    # storm, and `thread_report_ep` turns KeyError into 404 - so the report, the
    # printable page and the export were all 404 for exactly the threads that
    # had completed a journey, and 200 for the ones that had not.
    storms = [
        attached.as_dict()
        for attached in (
            storm.attach(row["id"]) for row in storm.list_for_thread(thread_id)
        )
    ]

    return {
        "thread_id": thread_id,
        "thread_name": thread.get("name"),
        "ledger": str(ledger.path),
        "generated_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds"),
        "verdict": {
            "outcome": result.outcome if result else None,
            "say": result.say if result else None,
            "gates": result.gate_ledger if result else {},
            "fact_origins": result.fact_origins if result else {},
        },
        "facts": sorted(
            (
                {
                    "fact": entry["fact"],
                    "value": entry["value"],
                    "origin": entry["origin"],
                    "tool": entry["tool"],
                    "how": entry["how"],
                    # `created_at` IS THE COLUMN; `written_at` is only this
                    # payload's name for it, kept because the Stage fixtures
                    # read that key. Reading `written_at` off the stored row
                    # left "When" blank on every report until 2026-09-23.
                    "written_at": winning_row.get(entry["fact"], {}).get("created_at"),
                }
                for entry in trail
            ),
            key=lambda item: item["fact"],
        ),
        "storms": storms,
    }


_PRINT_CSS = """
body { font-family: Georgia, 'Times New Roman', serif; margin: 2.5rem auto;
       max-width: 46rem; color: #111; background: #fff; line-height: 1.45; }
h1 { font-size: 1.4rem; margin: 0 0 .2rem; }
h2 { font-size: 1.05rem; border-bottom: 1px solid #ccc; padding-bottom: .25rem;
     margin-top: 1.8rem; }
table { width: 100%; border-collapse: collapse; font-size: .85rem;
        font-family: ui-monospace, Consolas, monospace; }
th, td { text-align: left; padding: .3rem .45rem; border-bottom: 1px solid #ddd;
         vertical-align: top; }
th { font-family: inherit; font-size: .72rem; text-transform: uppercase;
     letter-spacing: .04em; color: #555; }
.origin-MEASURED { color: #065f2b; font-weight: bold; }
.origin-STATED   { color: #1c4d8f; font-weight: bold; }
.origin-ASSERTED { color: #8a1f1f; font-weight: bold; }
.origin-DEFAULTED{ color: #777; }
.pill { display: inline-block; padding: .1rem .5rem; border: 1px solid #999;
        border-radius: 3px; font-size: .78rem; font-family: inherit; }
.muted { color: #666; font-size: .8rem; }
@media print { body { margin: 0; } .no-print { display: none; } }
"""


def render_html(report: dict[str, Any]) -> str:
    """The printable half. Every dynamic string goes through `_esc`."""
    verdict = report["verdict"]
    out: list[str] = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        "<title>Journey report</title>",
        f"<style>{_PRINT_CSS}</style></head><body>",
        "<h1>Journey report</h1>",
        "<p class='muted'>"
        f"thread #{_esc(report['thread_id'])} {_esc(report['thread_name'] or '')}"
        f" &middot; ledger {_esc(report['ledger'])}"
        f" &middot; generated {_esc(report['generated_at'])}"
        "</p>",
        "<p class='no-print muted'>To keep this as a PDF: print this page"
        " (Ctrl/Cmd+P) and choose 'Save as PDF'. The layout is written for it."
        "</p>",
        "<h2>Verdict</h2>",
    ]

    outcome = verdict.get("outcome")
    if outcome:
        out.append(f"<p><span class='pill'>{_esc(outcome)}</span></p>")
        if verdict.get("say"):
            out.append(f"<p>{_esc(verdict['say'])}</p>")
        gates = verdict.get("gates") or {}
        if gates:
            out.append(
                "<table><tr><th>Gate</th><th>Status</th><th>Row</th>"
                "<th>Clause</th></tr>"
            )
            for gate_id in sorted(gates):
                entry = gates[gate_id] or {}
                status = str(entry.get("status") or "-")
                tone = "origin-MEASURED" if status == "PASSED" else ""
                out.append(
                    f"<tr><td>{_esc(gate_id)}</td>"
                    f"<td class='{tone}'>{_esc(status)}</td>"
                    f"<td>{_esc(entry.get('row') or '-')}</td>"
                    f"<td>{_esc(entry.get('clause') or '-')}</td></tr>"
                )
            out.append("</table>")
    else:
        out.append("<p class='muted'>No facts on this thread yet, so there is "
                   "nothing to diagnose. The report will fill in as instruments "
                   "stamp.</p>")

    out.append("<h2>Facts on record</h2>")
    facts = report["facts"]
    if facts:
        out.append(
            "<table><tr><th>Fact</th><th>Value</th><th>Origin</th>"
            "<th>Tool</th><th>When</th></tr>"
        )
        for fact in facts:
            origin = str(fact.get("origin") or "DEFAULTED")
            out.append(
                f"<tr><td>{_esc(fact['fact'])}</td>"
                f"<td>{_cell(fact.get('value'))}</td>"
                f"<td class='origin-{_esc(origin)}'>{_esc(origin)}</td>"
                f"<td>{_esc(fact.get('tool') or '-')}</td>"
                f"<td>{_esc((fact.get('written_at') or '')[:19])}</td></tr>"
            )
        out.append("</table>")
        out.append(
            "<p class='muted'>MEASURED = an instrument produced it while the "
            "engine watched. STATED = the person said it in their own person. "
            "ASSERTED = claimed without a witness, and an assertion opens no "
            "gate here.</p>"
        )
    else:
        out.append("<p class='muted'>Nothing stamped yet.</p>")

    out.append("<h2>Approved builds that ran</h2>")
    storms = report["storms"]
    if not storms:
        out.append("<p class='muted'>None yet.</p>")
    for s in storms:
        manifest = s.get("manifest") or {}
        out.append(
            f"<p><strong>{_esc(manifest.get('title') or s.get('build', {}).get('id'))}</strong> "
            f"<span class='pill'>{_esc(s.get('state'))}</span> "
            + (
                f"<span class='pill'>deviations: {_esc(len(s.get('deviations') or []))}</span>"
                if s.get("deviations")
                else "<span class='pill'>deviations: none</span>"
            )
            + "</p>"
        )
        out.append("<table><tr><th>Step</th><th>State</th><th>Saw</th>"
                   "<th>Because</th></tr>")
        for step in s.get("steps") or []:
            verification = step.get("verification") or {}
            out.append(
                f"<tr><td>{_esc(step.get('id'))}</td>"
                f"<td>{_esc(step.get('state'))}</td>"
                f"<td>{_cell(verification.get('saw'))}</td>"
                f"<td>{_esc(verification.get('because') or '')}</td></tr>"
            )
        out.append("</table>")

    out.append(
        "<p class='muted' style='margin-top:2rem'>Generated by ML Harness."
        " Every figure above carries where it came from; that is the product.</p>"
    )
    out.append("</body></html>")
    return "".join(out)
