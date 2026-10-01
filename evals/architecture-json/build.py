"""Build the held-out set for the task Max actually described.

HIS WORDS: "a small coding model that reliably emits a system architecture as
valid JSON -- nodes with a label and a kind, and edges between them."

THE FIRST EVAL DID NOT MEASURE THAT. `evals/system-design/held-out.jsonl` asks
for a sorted comma-separated list of component names: no JSON, no kinds, no
edges. Every number on that line -- 30.1%, 32.7%, 35.7%, the failure histogram,
the NO_TRAIN__CONSTRAINED_DECODING verdict -- is a true measurement of a
DIFFERENT task. It is kept, because it is the only calibrated series on record
and because throwing away a real measurement to hide a mistake is worse than
the mistake. It is no longer the acceptance test.

WHAT THIS ONE MEASURES, AND WHY IT IS TWO THINGS.

  1. Does the output PARSE and satisfy the schema? That is the claim constrained
     decoding makes -- "format compliance becomes 100% by construction" -- and
     it is checkable without any opinion about architecture.
  2. Does it name the right components? Scored as set overlap over node labels,
     because a graph written with the same parts in a different order is the
     same graph, and exact-matching a serialised object measures key ordering.

They are reported separately and never pooled. A model that emits perfect JSON
about the wrong system and a model that describes the right system in prose are
opposite failures, and one number would call them equal.

THE EXPECTED COLUMN IS CANONICAL JSON -- keys in a fixed order, nodes sorted by
id, no whitespace -- so that a reader can see what "right" is. Nothing is graded
by string equality against it; it is the reference the two metrics above read.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).parent

INSTRUCTION = (
    "Return ONLY a JSON object with two keys: nodes and edges. "
    'Each node is {"id","label","kind"} where kind is one of '
    "service, datastore, queue, gateway, client, job, cache. "
    'Each edge is {"from","to"} using node ids, optionally with "label". '
    "No prose, no markdown fence."
)

# (description, nodes, edges) -- ids are short and derived from the label so a
# reader can check an edge without a lookup table.
CASES: list[tuple[str, list[tuple[str, str, str]], list[tuple[str, str]]]] = [
    (
        "A browser calls a REST API, and the API reads and writes a Postgres database.",
        [("browser", "Browser", "client"), ("api", "REST API", "service"), ("db", "Postgres database", "datastore")],
        [("browser", "api"), ("api", "db")],
    ),
    (
        "A mobile app uploads photos to an upload service, which stores files in object storage and puts a job on a queue. A worker reads the queue and writes thumbnails back to object storage.",
        [("app", "Mobile app", "client"), ("upload", "Upload service", "service"),
         ("store", "Object storage", "datastore"), ("queue", "Job queue", "queue"),
         ("worker", "Thumbnail worker", "job")],
        [("app", "upload"), ("upload", "store"), ("upload", "queue"), ("worker", "queue"), ("worker", "store")],
    ),
    (
        "A load balancer spreads requests across application servers that share one Redis cache and one relational database.",
        [("lb", "Load balancer", "gateway"), ("app", "Application server", "service"),
         ("cache", "Redis cache", "cache"), ("db", "Relational database", "datastore")],
        [("lb", "app"), ("app", "cache"), ("app", "db")],
    ),
    (
        "Sensors publish readings to an MQTT broker. A stream processor consumes them and writes aggregates to a time-series database that a dashboard queries.",
        [("sensor", "Sensor", "client"), ("broker", "MQTT broker", "queue"),
         ("proc", "Stream processor", "service"), ("tsdb", "Time-series database", "datastore"),
         ("dash", "Dashboard", "client")],
        [("sensor", "broker"), ("proc", "broker"), ("proc", "tsdb"), ("dash", "tsdb")],
    ),
    (
        "A scheduled job reads a source database, transforms the rows, and loads them into a data warehouse that analysts query through a BI tool.",
        [("job", "Scheduled job", "job"), ("src", "Source database", "datastore"),
         ("dw", "Data warehouse", "datastore"), ("bi", "BI tool", "client")],
        [("job", "src"), ("job", "dw"), ("bi", "dw")],
    ),
    (
        "A payment page sends card details to a payment gateway, and an orders service records the result in its own database.",
        [("page", "Payment page", "client"), ("gw", "Payment gateway", "gateway"),
         ("orders", "Orders service", "service"), ("db", "Orders database", "datastore")],
        [("page", "gw"), ("gw", "orders"), ("orders", "db")],
    ),
    (
        "A chat client opens a websocket to a gateway. The gateway publishes to a message bus and a fanout service delivers to other clients.",
        [("client", "Chat client", "client"), ("gw", "Websocket gateway", "gateway"),
         ("bus", "Message bus", "queue"), ("fanout", "Fanout service", "service")],
        [("client", "gw"), ("gw", "bus"), ("fanout", "bus"), ("fanout", "client")],
    ),
    (
        "A crawler feeds documents to an indexer that maintains an inverted index, which a search box queries.",
        [("crawler", "Crawler", "job"), ("indexer", "Indexer", "service"),
         ("index", "Inverted index", "datastore"), ("search", "Search box", "client")],
        [("crawler", "indexer"), ("indexer", "index"), ("search", "index")],
    ),
    (
        "A video is uploaded to an ingest service, transcoded by encoders into several bitrates, and served from a CDN to players.",
        [("ingest", "Ingest service", "service"), ("encoder", "Encoder", "job"),
         ("cdn", "CDN", "gateway"), ("player", "Player", "client")],
        [("ingest", "encoder"), ("encoder", "cdn"), ("player", "cdn")],
    ),
    (
        "A webhook receiver validates a signature, enqueues the payload, and a worker processes it against the orders service.",
        [("hook", "Webhook receiver", "service"), ("queue", "Payload queue", "queue"),
         ("worker", "Payload worker", "job"), ("orders", "Orders service", "service")],
        [("hook", "queue"), ("worker", "queue"), ("worker", "orders")],
    ),
    (
        "An authentication service issues tokens that an API gateway verifies before routing to downstream services, with sessions kept in a token store.",
        [("auth", "Authentication service", "service"), ("gw", "API gateway", "gateway"),
         ("down", "Downstream service", "service"), ("tokens", "Token store", "datastore")],
        [("auth", "tokens"), ("gw", "auth"), ("gw", "down")],
    ),
    (
        "A recommendation service reads features from a feature store, scores candidates with a model server, and returns results to a storefront.",
        [("rec", "Recommendation service", "service"), ("fs", "Feature store", "datastore"),
         ("model", "Model server", "service"), ("shop", "Storefront", "client")],
        [("rec", "fs"), ("rec", "model"), ("shop", "rec")],
    ),
    (
        "Logs are shipped by an agent to a log aggregator, which a dashboard queries.",
        [("agent", "Log agent", "job"), ("agg", "Log aggregator", "service"),
         ("dash", "Dashboard", "client")],
        [("agent", "agg"), ("dash", "agg")],
    ),
    (
        "An import service validates an uploaded CSV, writes good rows to the primary database and rejected rows to an error bucket.",
        [("imp", "Import service", "service"), ("db", "Primary database", "datastore"),
         ("errors", "Error bucket", "datastore")],
        [("imp", "db"), ("imp", "errors")],
    ),
    (
        "A tile server renders map tiles, caches them on disk, and a mobile client fetches them through a CDN.",
        [("tiles", "Tile server", "service"), ("disk", "Disk cache", "cache"),
         ("cdn", "CDN", "gateway"), ("mobile", "Mobile client", "client")],
        [("tiles", "disk"), ("cdn", "tiles"), ("mobile", "cdn")],
    ),
    (
        "A billing service reads usage from a metering service and issues invoices through a payment provider.",
        [("billing", "Billing service", "service"), ("meter", "Metering service", "service"),
         ("pay", "Payment provider", "gateway")],
        [("billing", "meter"), ("billing", "pay")],
    ),
    (
        "A retrieval service searches a vector database and hands passages to a language model, which answers a chat client.",
        [("ret", "Retrieval service", "service"), ("vec", "Vector database", "datastore"),
         ("llm", "Language model", "service"), ("chat", "Chat client", "client")],
        [("ret", "vec"), ("llm", "ret"), ("chat", "llm")],
    ),
    (
        "A CI runner builds a container image, pushes it to a registry, and a deployment controller rolls it out to a cluster.",
        [("ci", "CI runner", "job"), ("reg", "Container registry", "datastore"),
         ("deploy", "Deployment controller", "service"), ("cluster", "Cluster", "service")],
        [("ci", "reg"), ("deploy", "reg"), ("deploy", "cluster")],
    ),
    (
        "An email arrives at an SMTP receiver, is scanned by a spam filter, and written to a mailbox store an IMAP server reads.",
        [("smtp", "SMTP receiver", "service"), ("spam", "Spam filter", "service"),
         ("mail", "Mailbox store", "datastore"), ("imap", "IMAP server", "service")],
        [("smtp", "spam"), ("spam", "mail"), ("imap", "mail")],
    ),
    (
        "A dispatch service matches a rider on a mobile app to a driver, while a location service streams positions and a trip store records the journey.",
        [("app", "Mobile app", "client"), ("dispatch", "Dispatch service", "service"),
         ("driver", "Driver app", "client"), ("loc", "Location service", "service"),
         ("trips", "Trip store", "datastore")],
        [("app", "dispatch"), ("dispatch", "driver"), ("loc", "app"), ("loc", "driver"), ("dispatch", "trips")],
    ),
]


def canonical(nodes, edges) -> str:
    """One spelling of a graph, so a reader can see what right looks like."""
    return json.dumps(
        {
            "nodes": [
                {"id": i, "label": lab, "kind": k} for i, lab, k in sorted(nodes)
            ],
            "edges": [{"from": a, "to": b} for a, b in sorted(edges)],
        },
        separators=(",", ":"),
        ensure_ascii=False,
    )


def main() -> int:
    rows = []
    for index, (description, nodes, edges) in enumerate(CASES):
        ids = {i for i, _, _ in nodes}
        # An edge to a node that does not exist would make the reference itself
        # wrong, and a reference nobody checked is the defect this file is about.
        for a, b in edges:
            if a not in ids or b not in ids:
                print("REFUSING: row " + str(index) + " has an edge to an unknown id: " + a + "->" + b)
                return 1
        rows.append(
            {
                "row_id": index,
                "input": description + " " + INSTRUCTION,
                "expected": canonical(nodes, edges),
                "node_labels": sorted(lab.lower() for _, lab, _ in nodes),
                "edge_count": len(edges),
            }
        )

    out = HERE / "held-out.jsonl"
    with out.open("w", encoding="utf-8", newline=chr(10)) as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + chr(10))

    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    (HERE / "held-out.sha256").write_text(digest + "  held-out.jsonl" + chr(10), encoding="utf-8", newline=chr(10))

    nodes_total = sum(len(n) for _, n, _ in CASES)
    edges_total = sum(len(e) for _, _, e in CASES)
    print("rows: " + str(len(rows)))
    print("nodes across the set: " + str(nodes_total))
    print("edges across the set: " + str(edges_total))
    print("every edge names a node declared in its own row: checked, 0 dangling")
    print("sha256: " + digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
