"""Training rows for architecture-as-JSON, in the shape `hf-peft-lora` eats.

    python evals/architecture-json/build_training_set.py --rows 400

## THE THING TO KNOW BEFORE USING THIS

**There was no training set.** The only twenty architecture graphs in this
repository are `held-out.jsonl`, and they are the acceptance test. Training on
them would measure memory and report it as capability, which is the one failure
this eval was built to avoid. So these rows are GENERATED, and generated rows
have a cost that has to be stated before anyone trains on them.

**What is guaranteed.** The reference graph is correct by construction: the
description is written FROM the graph, not parsed into one, so a label can never
disagree with its node and an edge can never point at an id that does not exist.
Every row is checked against the held-out twenty three ways before it ships.

**What is NOT guaranteed, and this is the limitation to carry into any result.**
The descriptions come from sentence templates over a component vocabulary. They
are structurally varied and *stylistically narrow*. A model trained here may
learn this generator's phrasing rather than the task, and the held-out set is
written in a different voice by a different hand. **If training lifts the
held-out score, that is real; if it does not, "the prose was too uniform" is a
live explanation and not an excuse invented afterwards.** It is written here in
advance so nobody has to decide later whether it was.

## THE VOCABULARY, AND A DIAGNOSTIC THAT MUST NOT BE OPTIMISED

Labels are COMPOSED - a modifier drawn from a long list, then a noun - rather
than drawn from a fixed pool of names. The reason is one measurable property:
**every label appears verbatim in its own description** (0 of 1,838 failures
measured 2026-09-10), so the only rule the rows can teach is "take the label
out of the sentence".

That is the rule worth teaching, because the acceptance sets satisfy it too:

    held-out.jsonl        69 of 79 labels (87%) appear verbatim in their prompt
    held-out-extra.jsonl  74 of 76 labels (97%)

**A vocabulary count is NOT the ceiling, and the arithmetic that says it is was
wrong.** The reasoning went: the training set had 47 distinct labels, six in
seven of the words the model is scored on never appeared in it, so a model
cannot say a word it has never seen. The first half is a fact and the
conclusion does not follow - a copy rule reaches 87% of the held-out labels
without knowing any of them, because they are sitting in the input.

**And "reachability of held-out labels from the training vocabulary" is a
diagnostic that cannot be used as a target.** Raising it means putting the
acceptance set's words into training, which is the leak this whole file exists
to avoid. Measured, on this very rewrite: adding a list of ordinary component
names to lift reachability took held-out.jsonl from 16% to 50% and
held-out-extra from 12% to 13%. Forty-five hand-written "general knowledge"
names, of which 35 were in held-out.jsonl and 3 were in held-out-extra - the
asymmetry is the tell, since a vocabulary drawn from the world hits two
hand-written sets at similar rates. The list was not general knowledge; it was
held-out.jsonl recited from memory by someone who had read it all day. It was
removed. THE ROW-LEVEL LEAK CHECKS BELOW WOULD NOT HAVE CAUGHT IT: they compare
rows, and this was a leak of vocabulary.
## THE SHAPE

`prompt` / `completion`, which `hf-peft-lora` reads directly - see its loader,
which takes either a `text` field or a prompt/completion pair. The prompt is the
description plus **the eval's own INSTRUCTION, imported from `build.py` rather
than restated**, so the model is trained on the exact ask it is scored on. A
training prompt that differs from the eval prompt by one clause is a different
task, and that clause would be invisible in the result.

The completion is the canonical serialisation `build.py` produces: keys in fixed
order, nodes sorted by id, no whitespace.

## THE SPLIT

Three files, disjoint by construction and checked:

    train.jsonl   the rows to train on
    valid.jsonl   held back from training, same generator - measures fit
    held-out.jsonl  NOT produced here. Twenty hand-written systems, a different
                    voice, and the only acceptance test. Never trained on.

`valid` and `train` share a generator, so a good `valid` score says the model
learned the generator. Only `held-out` says it learned the task.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from build import INSTRUCTION, canonical  # noqa: E402  - one instruction, one source

NEWLINE = chr(10)

#: (label, kind, id-stem). Deliberately wider than the twenty so the generator
#: is not paraphrasing the acceptance set.
#: COMPOSED, NOT LISTED, AND THE MEASUREMENT IS WHY.
#:
#: The first version drew component names from seven fixed lists and produced a
#: training vocabulary of FORTY-SEVEN distinct labels over 400 rows. Measured
#: 2026-09-10 against the acceptance sets: `held-out.jsonl` uses 74 distinct
#: labels of which 12 are reachable from that vocabulary (16%), and
#: `held-out-extra.jsonl` uses 76 of which 9 are reachable (12%). So roughly
#: SIX IN SEVEN of the words the model is scored on never appeared in its
#: training data at all.
#:
#: THAT IS NOT A STYLE PROBLEM, WHICH IS WHAT I REGISTERED. It is a lexical one,
#: and it is worse: a model cannot be taught to say a word it has never seen, so
#: the ceiling was set by the vocabulary rather than by the task. ML BUILD's
#: adapter matched 15 of 56 reference edges where the naming-rule PROMPT matches
#: 42 of 56 - the prompt tells the model to reuse the description's own words
#: and the descriptions contain the right ones; training on a fixed pool taught
#: it to emit one of forty-seven instead.
#:
#: So labels are now COMPOSED from a modifier and a noun, drawn from wide lists,
#: and the label always appears verbatim in the description that asks for it.
#: What the model can learn from that is the transferable rule - take the name
#: from the words in front of you - rather than a list it will never finish.
MODIFIERS = ["billing", "booking", "catalogue", "search", "routing", "pricing",
             "inventory", "ledger", "media", "identity", "rendering", "payroll",
             "compliance", "shipping", "returns", "fraud", "loyalty", "quoting",
             "onboarding", "settlement", "dispatch", "scheduling", "telemetry",
             "moderation", "translation", "archive", "claims", "roster",
             "tariff", "insight", "consent", "escrow", "provisioning",
             "reconciliation", "notification", "subscription", "attendance",
             "valuation", "curation", "matching", "forecast", "intake",
             "renewal", "grading", "licensing", "clearing", "sampling"]
CLIENT_NOUNS = ["browser", "mobile app", "desktop client", "kiosk terminal",
                "partner integration", "command line tool", "handheld scanner",
                "operator console", "review tool", "field tablet", "web page",
                "reporting dashboard", "voice assistant", "smart display"]
GATEWAY_NOUNS = ["gateway", "load balancer", "reverse proxy", "edge router",
                 "request router", "ingress controller", "api front door"]
SERVICE_NOUNS = ["service", "engine", "processor", "handler", "coordinator",
                 "manager", "resolver", "broker service", "orchestrator"]
STORE_NOUNS = ["database", "store", "warehouse", "archive", "index", "ledger",
               "object storage", "document store", "log store", "registry",
               "bucket", "table", "vault"]
CACHE_NOUNS = ["cache", "result cache", "lookup cache", "session cache",
               "edge cache", "memo store"]
QUEUE_NOUNS = ["queue", "event bus", "message broker", "work queue",
               "retry queue", "stream", "topic"]
JOB_NOUNS = ["job", "worker", "batch job", "nightly job", "sweeper",
             "collector", "exporter", "importer"]


def composed(rng, modifiers, nouns, taken):
    """A label built from two words, and an id derived from it.

    The id is derived from the label so a reader can check an edge without a
    lookup table - the same rule `build.py` states for the hand-written cases.
    """
    for _ in range(80):
        label = rng.choice(modifiers) + " " + rng.choice(nouns)
        stem = "".join(w[:4] for w in label.split())[:12]
        if stem not in taken:
            taken.add(stem)
            return label[0].upper() + label[1:], stem
    raise RuntimeError("vocabulary exhausted")


CLIENTS = [(m + " " + n, "") for m in MODIFIERS[:1] for n in CLIENT_NOUNS[:1]]

def pick(rng, pool, taken):
    for _ in range(60):
        label, stem = rng.choice(pool)
        if stem not in taken:
            taken.add(stem)
            return label, stem
    raise RuntimeError("vocabulary exhausted")


def a_system(rng):
    """(description, nodes, edges). The description is written FROM the graph.

    EVERY LABEL APPEARS VERBATIM IN THE DESCRIPTION, which is the property the
    naming-rule prompt relies on and the one a fixed vocabulary destroyed. A
    model that learns "take the name from the words in front of you" carries
    that to a system it has never seen; a model that learns forty-seven names
    carries nothing.
    """
    taken: set[str] = set()
    nodes, edges, sentences = [], [], []

    client, cid = composed(rng, MODIFIERS, CLIENT_NOUNS, taken)
    shape = rng.choice(["direct", "gateway", "queue", "cache", "fanout"])

    if shape == "direct":
        svc, sid = composed(rng, MODIFIERS, SERVICE_NOUNS, taken)
        store, stid = composed(rng, MODIFIERS, STORE_NOUNS, taken)
        nodes += [(cid, client, "client"), (sid, svc, "service"), (stid, store, "datastore")]
        edges += [(cid, sid), (sid, stid)]
        sentences.append("The " + client.lower() + " calls the " + svc.lower()
                         + ", which reads and writes the " + store.lower() + ".")
    elif shape == "gateway":
        gw, gid = composed(rng, MODIFIERS, GATEWAY_NOUNS, taken)
        svc, sid = composed(rng, MODIFIERS, SERVICE_NOUNS, taken)
        store, stid = composed(rng, MODIFIERS, STORE_NOUNS, taken)
        nodes += [(cid, client, "client"), (gid, gw, "gateway"),
                  (sid, svc, "service"), (stid, store, "datastore")]
        edges += [(cid, gid), (gid, sid), (sid, stid)]
        sentences.append("The " + client.lower() + " sends requests through the "
                         + gw.lower() + " to the " + svc.lower()
                         + ", which persists to the " + store.lower() + ".")
    elif shape == "queue":
        svc, sid = composed(rng, MODIFIERS, SERVICE_NOUNS, taken)
        q, qid = composed(rng, MODIFIERS, QUEUE_NOUNS, taken)
        worker, wid = composed(rng, MODIFIERS, JOB_NOUNS, taken)
        store, stid = composed(rng, MODIFIERS, STORE_NOUNS, taken)
        nodes += [(cid, client, "client"), (sid, svc, "service"), (qid, q, "queue"),
                  (wid, worker, "job"), (stid, store, "datastore")]
        edges += [(cid, sid), (sid, qid), (wid, qid), (wid, stid)]
        sentences.append("The " + client.lower() + " submits work to the " + svc.lower()
                         + ", which places it on the " + q.lower() + ". The "
                         + worker.lower() + " takes items off the " + q.lower()
                         + " and writes results to the " + store.lower() + ".")
    elif shape == "cache":
        svc, sid = composed(rng, MODIFIERS, SERVICE_NOUNS, taken)
        cache, chid = composed(rng, MODIFIERS, CACHE_NOUNS, taken)
        store, stid = composed(rng, MODIFIERS, STORE_NOUNS, taken)
        nodes += [(cid, client, "client"), (sid, svc, "service"),
                  (chid, cache, "cache"), (stid, store, "datastore")]
        edges += [(cid, sid), (sid, chid), (sid, stid)]
        sentences.append("The " + client.lower() + " queries the " + svc.lower()
                         + ". It checks the " + cache.lower()
                         + " first and falls back to the " + store.lower() + ".")
    else:
        gw, gid = composed(rng, MODIFIERS, GATEWAY_NOUNS, taken)
        one, oid = composed(rng, MODIFIERS, SERVICE_NOUNS, taken)
        two, tid = composed(rng, MODIFIERS, SERVICE_NOUNS, taken)
        store, stid = composed(rng, MODIFIERS, STORE_NOUNS, taken)
        nodes += [(cid, client, "client"), (gid, gw, "gateway"), (oid, one, "service"),
                  (tid, two, "service"), (stid, store, "datastore")]
        edges += [(cid, gid), (gid, oid), (gid, tid), (oid, stid), (tid, stid)]
        sentences.append("The " + client.lower() + " reaches the " + gw.lower()
                         + ", which routes to the " + one.lower() + " and the "
                         + two.lower() + ". Both write to the " + store.lower() + ".")
    return " ".join(sentences), nodes, edges

def would_leak(nodes, description, held_out):
    """None when clean. Three checks, the same three the ladder builder uses."""
    labels = {label.strip().lower() for _, label, _ in nodes}
    words = {w for w in description.lower().replace(",", " ").replace(".", " ").split()
             if len(w) > 4}
    for row in held_out:
        text = row["input"].lower()
        if description.lower() in text:
            return "verbatim match with held-out row " + str(row["row_id"])
        theirs = {str(l).strip().lower() for l in row["node_labels"]}
        if labels and labels <= theirs:
            return ("every label is in held-out row " + str(row["row_id"])
                    + " - the same system under another sentence")
        shared = words & {w for w in text.replace(",", " ").replace(".", " ").split()
                          if len(w) > 4}
        if len(shared) >= 6:
            return ("shares " + str(len(shared)) + " content words with held-out row "
                    + str(row["row_id"]) + ": " + ", ".join(sorted(shared)[:6]))
    return None


def carve(rows, want_valid, slack):
    """CARVED, NOT SPLIT - and carved on the DESCRIPTION rather than the prompt.

    ML BUILD found train/eval leakage carrying a whole result: three eval rows
    were near-duplicates of training rows at up to 0.944 similarity with no
    exact string match, and removing them turned p = 0.039 into p = 0.070. Their
    advice was to carve rather than split, because `carve_eval_set` runs the
    leakage check on its own output and refuses a leaking split.

    MEASURED HERE FIRST, because the check has a trap. Run over the full prompt,
    this generator read 70.5% leakage between two halves of its own training
    set. Run over the DESCRIPTION alone it reads 15.5%. The difference is the
    shared INSTRUCTION - about sixty tokens identical on every row - which
    dominates a token-similarity score and makes any two rows look alike. The
    prompt is what a model sees; the description is what actually varies, and it
    is what a leakage question about content has to be asked on.

    So valid rows are admitted one at a time and only while the harness's own
    check still returns clean against the training half.
    """
    import tempfile
    from app.tools.data import check_split_leakage

    train = rows[:len(rows) - want_valid - slack]
    pool = rows[len(train):]
    kept = []
    with tempfile.TemporaryDirectory() as tmp:
        here = Path(tmp)
        train_file = here / "train_probe.jsonl"
        train_file.write_text(
            NEWLINE.join(json.dumps({"prompt": describe(r), "completion": r["completion"]})
                         for r in train) + NEWLINE, encoding="utf-8")
        for candidate in pool:
            if len(kept) >= want_valid:
                break
            trial = kept + [candidate]
            probe = here / "valid_probe.jsonl"
            probe.write_text(
                NEWLINE.join(json.dumps({"prompt": describe(r), "completion": r["completion"]})
                             for r in trial) + NEWLINE, encoding="utf-8")
            found = check_split_leakage(str(train_file), str(probe))
            if not (found.get("leaked_rows") or 0):
                kept.append(candidate)
    return train, kept


def describe(row):
    """The row's description with the shared instruction removed."""
    return row["prompt"].split("Return ONLY")[0].strip()

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rows", type=int, default=400)
    parser.add_argument("--valid", type=int, default=40)
    parser.add_argument("--seed", type=int, default=20260910)
    parser.add_argument("--train-slack", type=int, default=260,
                        help="extra rows generated so valid can be carved from a pool")
    args = parser.parse_args()

    held_out = [json.loads(l) for l in (HERE / "held-out.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    rng = random.Random(args.seed)

    wanted = args.rows + args.valid + args.train_slack
    rows, seen, refused = [], set(), 0
    while len(rows) < wanted:
        description, nodes, edges = a_system(rng)
        if description in seen:
            continue
        why = would_leak(nodes, description, held_out)
        if why is not None:
            refused += 1
            continue
        seen.add(description)
        ids = {i for i, _, _ in nodes}
        for a, b in edges:
            if a not in ids or b not in ids:
                print("REFUSING: generated an edge to an unknown id: " + a + "->" + b)
                return 1
        rows.append({"prompt": description + " " + INSTRUCTION,
                     "completion": canonical(nodes, edges)})

    rng.shuffle(rows)
    train_rows, valid_rows = carve(rows, args.valid, args.train_slack)
    split = {"valid.jsonl": valid_rows, "train.jsonl": train_rows}
    for name, part in split.items():
        out = HERE / name
        with out.open("w", encoding="utf-8", newline=NEWLINE) as handle:
            for row in part:
                handle.write(json.dumps(row, ensure_ascii=False) + NEWLINE)
        digest = hashlib.sha256(out.read_bytes().replace(bytes([13, 10]), bytes([10]))).hexdigest()
        print(f"{name:12s} {len(part):4d} rows  sha {digest[:12]}")

    print()
    print(f"refused for overlap with the held-out twenty: {refused}")
    print("leakage checked three ways: verbatim, label-subset, content-word overlap")
    print("instruction imported from build.py, so training and eval ask the same thing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
