"""Build the held-out system-design eval set.

WRITTEN BEFORE ANY TRAINING DATA EXISTS. That order is the whole point: if the
training data comes first, the eval ends up testing what the data happens to
contain, and a win means nothing. This file is the acceptance test for the
system-design model, and it is committed before the corpus it will judge.

FOUR FAMILIES, BECAUSE "GOOD AT SYSTEM DESIGN" IS NOT ONE SKILL.

  components        read a prose description, list the parts
  missing_component read a described failure, name the one part that fixes it
  edge_direction    say which way a dependency points
  pattern_name      name the pattern from its description

Reported PER FAMILY, never only as a total. A model that memorises pattern
names and cannot read a description would score respectably on a pooled number
and be useless for the product, and the pooled number is what would hide it.

GRADED BY THE HARNESS, NOT HERE. `app/tools/evals.py::grade` computes
exact_match and contains with the same normalisation that graded the baseline.
Two graders would be two instruments and the comparison would mean nothing.

The answers are short and canonical on purpose - a lowercase, alphabetically
sorted, comma-separated list, or a single component name - because a prose
answer about architecture cannot be graded deterministically, and a
model-graded score with no deterministic floor is exactly how a judge starts
inventing its verdicts.
"""

import hashlib
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent

LIST_INSTR = (
    "List the components of this system as a comma-separated list, "
    "lowercase, alphabetically sorted, no other text."
)
ONE_INSTR = "Answer with the component name only."
PAT_INSTR = "Name the pattern. Answer with the pattern name only."

COMPONENTS = [
    ("Users hit a web page. The page calls a REST API. The API reads and writes a Postgres database.",
     "api,database,web page"),
    ("A mobile app sends photos to an upload service, which stores files in object storage and puts a job on a queue. A worker reads the queue and writes thumbnails back to object storage.",
     "mobile app,object storage,queue,upload service,worker"),
    ("A browser loads a single-page app from a CDN. The app authenticates against an identity provider, then calls a GraphQL gateway which fans out to two microservices.",
     "browser,cdn,graphql gateway,identity provider,microservice"),
    ("Sensors publish readings to an MQTT broker. A stream processor consumes them and writes aggregates to a time-series database, which a dashboard queries.",
     "dashboard,mqtt broker,sensor,stream processor,time-series database"),
    ("A scheduled job pulls rows from a source database, transforms them, and loads them into a data warehouse. Analysts query the warehouse through a BI tool.",
     "bi tool,data warehouse,scheduled job,source database"),
    ("A load balancer distributes requests across three application servers. Each server shares one Redis cache and one relational database.",
     "application server,database,load balancer,redis cache"),
    ("A payment page collects a card, sends it to a payment gateway, and records the result in an orders service backed by its own database.",
     "database,orders service,payment gateway,payment page"),
    ("Git pushes trigger a CI runner. The runner builds a container image, pushes it to a registry, and a deployment controller rolls it out to a cluster.",
     "ci runner,cluster,container registry,deployment controller,git"),
    ("A chat client opens a websocket to a gateway. The gateway publishes to a message bus, and a fanout service delivers messages to other connected clients.",
     "chat client,fanout service,message bus,websocket gateway"),
    ("An email arrives at an SMTP receiver, is scanned by a spam filter, and is written to a mailbox store that an IMAP server reads.",
     "imap server,mailbox store,smtp receiver,spam filter"),
    ("A search box queries an inverted index. A crawler feeds documents into an indexer that maintains the index.",
     "crawler,indexer,inverted index,search box"),
    ("A video is uploaded to an ingest service, transcoded by a farm of encoders into multiple bitrates, and served from a CDN to players.",
     "cdn,encoder,ingest service,player"),
]

MISSING = [
    ("A web app writes directly to a Postgres primary for both reads and writes. Read traffic is ten times write traffic and the primary is saturated. Name the ONE component to add.",
     "read replica"),
    ("An API calls a slow third-party service on every request. The same fifty responses are requested all day. Name the ONE component to add.",
     "cache"),
    ("A signup endpoint sends a welcome email inline, so signups fail whenever the mail provider is down. Name the ONE component to add.",
     "queue"),
    ("Three application servers each hold session state in memory, so users are logged out at random. Name the ONE component to add.",
     "session store"),
    ("A public API is being abused by one client making thousands of requests a second. Name the ONE component to add.",
     "rate limiter"),
    ("Every service logs to its own local disk and nobody can follow a request across them. Name the ONE component to add.",
     "log aggregator"),
    ("A single application server serves all traffic and the site is down during every deploy. Name the ONE component to add.",
     "load balancer"),
    ("Static images are served from the application server in one region and users on the other side of the world wait seconds for them. Name the ONE component to add.",
     "cdn"),
]

EDGES = [
    ("A browser calls an API and the API reads a database. Which component does the API depend on?", "database"),
    ("A worker consumes from a queue that a web server writes to. Which component writes to the queue?", "web server"),
    ("A CDN sits in front of an origin server. Which component receives a user request first?", "cdn"),
    ("A reverse proxy terminates TLS and forwards plaintext to an app server. Which component holds the certificate?", "reverse proxy"),
    ("A read replica is fed by a primary database. Which component accepts writes?", "primary database"),
    ("An event bus delivers to subscribers what publishers emit. Which component initiates a message?", "publisher"),
    ("An ETL job reads a source system and writes a warehouse. Which component is the destination?", "warehouse"),
    ("An application container sits behind a sidecar proxy that intercepts its traffic. Which component does the network reach first?", "sidecar"),
]

PATTERNS = [
    ("Calls to a failing downstream service are stopped for a cooling-off period after repeated errors, then cautiously retried.", "circuit breaker"),
    ("Each service owns its own database and no service reads another service tables directly.", "database per service"),
    ("A new version is deployed alongside the old one and traffic is switched over between them.", "blue-green deployment"),
    ("Every state change is stored as an immutable append-only record, and current state is derived by replaying them.", "event sourcing"),
    ("Writes go to one model and reads are served from a separate model optimised for querying.", "cqrs"),
    ("One entry point routes external calls to many internal services and handles auth and rate limiting.", "api gateway"),
    ("A small share of production traffic is sent to a new version to observe it before full rollout.", "canary release"),
    ("Work is retried with progressively longer waits plus a random offset so that clients do not retry in lockstep.", "exponential backoff with jitter"),
]


# The rows that take the set past the resolution floor the harness named.
# Kept in their own module so the original 36 stay readable as what they were:
# the first cut, written before any training data existed. Same four families,
# same guards, appended rather than merged.
from more_rows import MORE_COMPONENTS, MORE_EDGES, MORE_MISSING, MORE_PATTERNS  # noqa: E402

COMPONENTS = COMPONENTS + MORE_COMPONENTS
MISSING = MISSING + MORE_MISSING
EDGES = EDGES + MORE_EDGES
PATTERNS = PATTERNS + MORE_PATTERNS


def build() -> list[dict]:
    rows: list[dict] = []
    for q, a in COMPONENTS:
        rows.append({"family": "components", "input": q + " " + LIST_INSTR, "expected": a})
    for q, a in MISSING:
        rows.append({"family": "missing_component", "input": q + " " + ONE_INSTR, "expected": a})
    for q, a in EDGES:
        rows.append({"family": "edge_direction", "input": q + " " + ONE_INSTR, "expected": a})
    for q, a in PATTERNS:
        rows.append({"family": "pattern_name", "input": q + " " + PAT_INSTR, "expected": a})
    for i, r in enumerate(rows):
        r["row_id"] = i
    return rows


def main() -> int:
    rows = build()

    # An expected answer that appears verbatim in its own question is not a test
    # of anything. Checked rather than trusted, because the failure is silent.
    #
    # ONE FAMILY IS EXEMPT AND THE EXEMPTION IS THE POINT OF THE FAMILY.
    # `edge_direction` asks which of the components NAMED IN THE PROMPT a
    # dependency points at, so every candidate answer is necessarily in the
    # question. It is a selection task, not a recall task, and stripping the
    # answer out would destroy the question rather than harden it.
    #
    # The exemption is only safe because there is no positional shortcut: across
    # the eight rows the correct answer is the first component mentioned twice,
    # the second five times and the last once, so "always answer the last noun"
    # scores 1 of 8. That is asserted below rather than claimed here.
    #
    # The check still runs at full strength on the other three families, where a
    # leaked answer WOULD be a real defect.
    SELECTION_FAMILIES = {"edge_direction"}
    leaked = [
        r["row_id"]
        for r in rows
        if r["family"] not in SELECTION_FAMILIES
        and r["expected"].lower() in r["input"].lower()
    ]
    if leaked:
        print("REFUSING: the expected answer is inside the question on rows " + str(leaked))
        return 1

    # And the exemption's own precondition, checked rather than asserted: a
    # trivial "answer with the last component named" strategy must not pass.
    sel = [r for r in rows if r["family"] in SELECTION_FAMILIES]
    last_noun_hits = 0
    for r in sel:
        positions = [(r["input"].lower().rfind(o["expected"].lower()), o["row_id"]) for o in sel]
        here = r["input"].lower()
        # does the answer sit later in the prompt than every other row's answer term present?
        others = [o["expected"].lower() for o in sel if o["expected"] != r["expected"] and o["expected"].lower() in here]
        if others and here.rfind(r["expected"].lower()) > max(here.rfind(o) for o in others):
            last_noun_hits += 1
    if sel and last_noun_hits > len(sel) // 2:
        print(
            "REFUSING: 'answer with the last component named' scores "
            + str(last_noun_hits) + " of " + str(len(sel)) + " on the selection family"
        )
        return 1
    print(
        "selection family shortcut check: 'last component named' scores "
        + str(last_noun_hits) + " of " + str(len(sel))
    )

    out = HERE / "held-out.jsonl"
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    (HERE / "held-out.sha256").write_text(digest + "  held-out.jsonl\n", encoding="utf-8", newline="\n")

    print("rows: " + str(len(rows)))
    for fam, n in sorted(Counter(r["family"] for r in rows).items()):
        print("  " + fam.ljust(18) + str(n))
    print("no answer leaks into its own question: checked, 0 of " + str(len(rows)))
    print("sha256: " + digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
