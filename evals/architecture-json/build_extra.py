"""Twenty more held-out systems, so a real improvement can be resolved.

    python evals/architecture-json/build_extra.py

## WHY THIS EXISTS

ML BUILD computed what the current acceptance test can show, over discordant
edges on the 49 matched:

    7 fixed, 0 newly broken   p = 0.0156  RESOLVES
    8 fixed, 1 broken         p = 0.0391  RESOLVES
    9 fixed, 2 broken         p = 0.0654  NO EVIDENCE

**A training run that fixes nine reversals and breaks two is a genuine
improvement this eval cannot show.** Twenty rows and 62 edges is the binding
constraint, and no amount of care in the training fixes a denominator.

## IT IS A SEPARATE FILE, AND THAT IS THE WHOLE DESIGN

`held-out.jsonl` is NOT extended. Every figure this lab has published — 13
reversed of 49 matched, node-label F1 at 79-81% across four prompt shapes, the
whole ladder — is measured against those twenty rows, and appending to the file
would silently change the denominator under every one of them. A number nobody
can recompute is a number nobody should quote.

So these are `held-out-extra.jsonl`, **row_ids 100-119** so they can never
collide with 0-19, and the scorers take both files. The old set stays pinned and
comparable; the combined set is what a training judgement should use, and it must
say which of the two it used.

## THE VOICE IS DELIBERATELY NOT THE GENERATOR'S

`train.jsonl` comes from five sentence templates. If the acceptance test were
written the same way, a model that learned the template would score well on both
and nobody could tell learning from matching. These are written as prose: varied
sentence order, some passive, some naming the direction implicitly ("reads
from", "is populated by"), a few with topologies the generator cannot produce —
two stores, a monitoring path, a service that both reads and writes a cache.

**That is a real difference from the generator and it cuts both ways.** If a
model trained on templates scores badly here, "the prose is unlike the training
data" is a live explanation as much as "it cannot do the task". The point of the
acceptance test is that it does not resemble the training set.

## CORRECT BY CONSTRUCTION

Same rule as `build.py`: the description is written FROM the graph. Every edge is
checked against the declared ids before anything is written, and the whole file
is checked against `train.jsonl` for leakage by the harness's own checker.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))

from build import INSTRUCTION, canonical  # noqa: E402 - one instruction, one source

NEWLINE = chr(10)

#: (description, nodes, edges). Ids short and derived from the label so an edge
#: can be checked without a lookup table.
CASES: list[tuple[str, list[tuple[str, str, str]], list[tuple[str, str]]]] = [
    ("Field engineers file inspection reports from a tablet. The reports land in a "
     "submission service, which stores the photographs in a media bucket and the "
     "structured answers in a compliance database.",
     [("tablet", "Tablet", "client"), ("submit", "Submission service", "service"),
      ("bucket", "Media bucket", "datastore"), ("compliance", "Compliance database", "datastore")],
     [("tablet", "submit"), ("submit", "bucket"), ("submit", "compliance")]),

    ("A payroll run is kicked off on a schedule. The payroll job reads employment "
     "records from the HR store, and every payslip it produces is written to the "
     "document archive.",
     [("payroll", "Payroll job", "job"), ("hr", "HR store", "datastore"),
      ("archive", "Document archive", "datastore")],
     [("payroll", "hr"), ("payroll", "archive")]),

    ("Shoppers browse a storefront. Prices shown on the page come from a pricing "
     "service, which is populated overnight by a competitor scraper.",
     [("storefront", "Storefront", "client"), ("pricing", "Pricing service", "service"),
      ("scraper", "Competitor scraper", "job")],
     [("storefront", "pricing"), ("scraper", "pricing")]),

    ("An access badge is presented at a turnstile. The turnstile asks the access "
     "controller whether to open, and the controller checks the badge against the "
     "cardholder directory and appends the attempt to an audit trail.",
     [("turnstile", "Turnstile", "client"), ("controller", "Access controller", "service"),
      ("directory", "Cardholder directory", "datastore"), ("audit", "Audit trail", "datastore")],
     [("turnstile", "controller"), ("controller", "directory"), ("controller", "audit")]),

    ("Telemetry from delivery vans is collected by a fleet collector. It keeps a "
     "rolling window in a hot cache for the live map, and flushes older points into "
     "a history warehouse.",
     [("van", "Delivery van", "client"), ("collector", "Fleet collector", "service"),
      ("hot", "Hot cache", "cache"), ("history", "History warehouse", "datastore"),
      ("map", "Live map", "client")],
     [("van", "collector"), ("collector", "hot"), ("collector", "history"), ("map", "hot")]),

    ("A translation request enters through a language gateway. The gateway hands it "
     "to a translation service, which looks for a previous answer in a phrase cache "
     "before calling the model host.",
     [("gw", "Language gateway", "gateway"), ("translate", "Translation service", "service"),
      ("phrases", "Phrase cache", "cache"), ("host", "Model host", "service")],
     [("gw", "translate"), ("translate", "phrases"), ("translate", "host")]),

    ("Bank statements arrive as files. An ingest service drops each file into raw "
     "storage and announces it on a parsing queue. The statement parser consumes "
     "those announcements and writes normalised transactions to the ledger.",
     [("ingest", "Ingest service", "service"), ("raw", "Raw storage", "datastore"),
      ("queue", "Parsing queue", "queue"), ("parser", "Statement parser", "job"),
      ("ledger", "Ledger", "datastore")],
     [("ingest", "raw"), ("ingest", "queue"), ("parser", "queue"), ("parser", "ledger")]),

    ("A clinician opens a patient record in the review console. The console reads "
     "from the records service, which draws demographics from the patient database "
     "and recent results from the lab feed.",
     [("console", "Review console", "client"), ("records", "Records service", "service"),
      ("patients", "Patient database", "datastore"), ("lab", "Lab feed", "service")],
     [("console", "records"), ("records", "patients"), ("records", "lab")]),

    ("Every commit triggers a build. The build agent pulls the source from the code "
     "host, and pushes the finished image to the artefact registry.",
     [("agent", "Build agent", "job"), ("code", "Code host", "datastore"),
      ("registry", "Artefact registry", "datastore")],
     [("agent", "code"), ("agent", "registry")]),

    ("Support tickets are created in a help desk. A triage service watches the desk "
     "and writes a priority score back to it, using a model served by the scoring "
     "service.",
     [("desk", "Help desk", "service"), ("triage", "Triage service", "service"),
      ("scoring", "Scoring service", "service")],
     [("triage", "desk"), ("triage", "scoring")]),

    ("Warehouse scanners report picks to a stock service. The stock service keeps "
     "counts in an inventory database, and when a count falls below its threshold "
     "it places an order on the replenishment queue.",
     [("scanner", "Warehouse scanner", "client"), ("stock", "Stock service", "service"),
      ("inventory", "Inventory database", "datastore"), ("replenish", "Replenishment queue", "queue")],
     [("scanner", "stock"), ("stock", "inventory"), ("stock", "replenish")]),

    ("A newsletter is assembled by a digest job, which reads subscriber preferences "
     "from the preferences store and hands the finished mail to the delivery "
     "service.",
     [("digest", "Digest job", "job"), ("prefs", "Preferences store", "datastore"),
      ("delivery", "Delivery service", "service")],
     [("digest", "prefs"), ("digest", "delivery")]),

    ("Match results are entered by a referee app. The results service records them "
     "in the fixtures database and publishes a change event to the standings bus, "
     "which the league table service consumes.",
     [("referee", "Referee app", "client"), ("results", "Results service", "service"),
      ("fixtures", "Fixtures database", "datastore"), ("bus", "Standings bus", "queue"),
      ("table", "League table service", "service")],
     [("referee", "results"), ("results", "fixtures"), ("results", "bus"), ("table", "bus")]),

    ("Photographs are uploaded to a gallery service, which writes originals to cold "
     "storage. A resizing worker later reads those originals and writes web-sized "
     "copies to the delivery cache.",
     [("gallery", "Gallery service", "service"), ("cold", "Cold storage", "datastore"),
      ("resizer", "Resizing worker", "job"), ("delivery", "Delivery cache", "cache")],
     [("gallery", "cold"), ("resizer", "cold"), ("resizer", "delivery")]),

    ("A tenant signs in through the identity provider. Once a session exists, the "
     "portal reads tenant settings from the configuration store on every page load.",
     [("portal", "Portal", "client"), ("idp", "Identity provider", "service"),
      ("config", "Configuration store", "datastore")],
     [("portal", "idp"), ("portal", "config")]),

    ("Sensor faults are raised into an alerting service. It suppresses duplicates "
     "using a recent-alerts cache, and forwards what survives to the on-call "
     "notifier.",
     [("sensor", "Sensor", "client"), ("alerting", "Alerting service", "service"),
      ("recent", "Recent-alerts cache", "cache"), ("notifier", "On-call notifier", "service")],
     [("sensor", "alerting"), ("alerting", "recent"), ("alerting", "notifier")]),

    ("A nightly export job reads the reporting warehouse and drops CSV files into a "
     "partner bucket, from which the partner's own loader collects them.",
     [("export", "Export job", "job"), ("warehouse", "Reporting warehouse", "datastore"),
      ("bucket", "Partner bucket", "datastore"), ("loader", "Partner loader", "service")],
     [("export", "warehouse"), ("export", "bucket"), ("loader", "bucket")]),

    ("Calls into the contact centre are routed by a switch to an agent desktop. The "
     "desktop pulls the caller's history from the CRM while the call connects.",
     [("switch", "Call switch", "gateway"), ("desktop", "Agent desktop", "client"),
      ("crm", "CRM", "datastore")],
     [("switch", "desktop"), ("desktop", "crm")]),

    ("Course videos are served to students from an edge cache. On a miss the cache "
     "fetches from the video origin, which reads the file from lecture storage.",
     [("student", "Student", "client"), ("edge", "Edge cache", "cache"),
      ("origin", "Video origin", "service"), ("lectures", "Lecture storage", "datastore")],
     [("student", "edge"), ("edge", "origin"), ("origin", "lectures")]),

    ("A moderation queue holds flagged posts. Human moderators work the queue "
     "through a review tool, and their decisions are written to the moderation log "
     "and applied by the content service.",
     [("queue", "Moderation queue", "queue"), ("tool", "Review tool", "client"),
      ("log", "Moderation log", "datastore"), ("content", "Content service", "service")],
     [("tool", "queue"), ("tool", "log"), ("content", "log")]),
]

#: 100 upward, so an extra row can never be mistaken for one of the original
#: twenty in any file that merges them.
FIRST_ROW_ID = 100


def main() -> int:
    rows = []
    for offset, (description, nodes, edges) in enumerate(CASES):
        ids = {i for i, _, _ in nodes}
        for a, b in edges:
            if a not in ids or b not in ids:
                print("REFUSING: case " + str(offset) + " has an edge to an unknown id: "
                      + a + "->" + b)
                return 1
        labels = [lab for _, lab, _ in nodes]
        if len(set(labels)) != len(labels):
            print("REFUSING: case " + str(offset) + " repeats a label, so an edge "
                  "endpoint would be ambiguous")
            return 1
        rows.append({
            "row_id": FIRST_ROW_ID + offset,
            "input": description + " " + INSTRUCTION,
            "expected": canonical(nodes, edges),
            "node_labels": sorted(lab.lower() for lab in labels),
            "edge_count": len(edges),
        })

    out = HERE / "held-out-extra.jsonl"
    with out.open("w", encoding="utf-8", newline=NEWLINE) as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + NEWLINE)

    digest = hashlib.sha256(out.read_bytes().replace(bytes([13, 10]), bytes([10]))).hexdigest()
    (HERE / "held-out-extra.sha256").write_text(digest + "  held-out-extra.jsonl" + NEWLINE,
                                                encoding="utf-8")
    print("rows:        " + str(len(rows)) + "  (row_ids " + str(FIRST_ROW_ID) + "-"
          + str(FIRST_ROW_ID + len(rows) - 1) + ")")
    print("edges:       " + str(sum(r["edge_count"] for r in rows)))
    print("sha256:      " + digest[:12] + "  (LF-normalised, pinned beside the file)")
    print()
    print("held-out.jsonl is UNCHANGED - every published figure is against those 20 rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
