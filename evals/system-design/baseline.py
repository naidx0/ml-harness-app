"""Score a model on the held-out system-design set, before anything is trained.

WHY THIS EXISTS BEFORE ANY TRAINING DATA. A tuned adapter is only worth what it
beats. Running the baseline first means the number the tune has to clear was
fixed before the corpus that produces the tune existed, so nobody can quietly
choose the comparison after seeing the result.

IT IMPORTS THE HARNESS GRADER RATHER THAN SCORING FOR ITSELF.
`app.tools.evals.grade` is the same function, with the same normalisation, that
`recipes/hf-peft-lora` eval output is graded by. A second grader here would be a
second instrument, and two scores from two instruments are two facts rather than
a comparison - which is the rule `recipes/hf-peft-lora/recipe.toml` already
states about its own eval path.

IT REPORTS PER FAMILY AND REFUSES TO REPORT ONLY A TOTAL. Four families are
four different skills; pooling them lets a model that has memorised pattern
names and cannot read a description hide behind a respectable average.

IT VERIFIES THE EVAL FILE'S HASH FIRST. The set is only "held out" if it is the
set that was committed; a file edited after a disappointing baseline is the
oldest trick there is, and the check costs nothing.
"""

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO))

from app.tools.evals import CONTAINS, EXACT_MATCH, grade  # noqa: E402
from app.tools.measure import normalise_answer  # noqa: E402

SET_F1 = "set_f1"

#: The one family whose answer is a SET and not a string.
#:
#: CHANGED AFTER SEEING THE METRIC RETURN ZERO, WHICH IS THE MOST DANGEROUS
#: MOMENT TO CHANGE A METRIC, so the reason is written here rather than assumed.
#: `exact_match` scored minicpm5-hermes 0 of 12 on this family. Reading the
#: answers, it was not wrong about the systems: for
#: "api,database,web page" it returned "postgres database, rest api, web page",
#: and elsewhere "sensors" for "sensor" and one extra component. Those are word
#: choice, plurals and ordering - a STRING comparison applied to an UNORDERED
#: SET, measuring formatting and reporting it as knowledge.
#:
#: Set F1 on the same twelve rows is 65%. The direction of the change is in my
#: favour, and the defence is not the number: a set is not a string, and this
#: was true before the run. I did not see it before the run, and that is the
#: actual failure here.
#:
#: exact_match STAYS for the other three families, where it is right - "cache"
#: and "circuit breaker" are single canonical answers, and being loose about
#: them would let a wrong answer inside a right one count.
SET_FAMILIES = {"components"}


def set_f1(expected: str, answer: str) -> float:
    """Overlap between two comma-separated component sets, normalised per item.

    Uses the harness's own `normalise_answer` on each item so the same case,
    whitespace and edge-punctuation rules apply here as everywhere else. What it
    deliberately does NOT do is stem, alias or fuzzy-match: "postgres database"
    still misses "database", and that stays a miss. Anything cleverer would be a
    scoring policy nobody can see, which is the rule `normalise_answer` itself
    is written to hold.
    """
    def items(value: str) -> set[str]:
        parts = str(value).replace(";", ",").split(",")
        return {normalise_answer(p) for p in parts if normalise_answer(p)}

    want, got = items(expected), items(answer)
    if not want:
        return 0.0
    hit = len(want & got)
    if not hit:
        return 0.0
    precision = hit / len(got)
    recall = hit / len(want)
    return 2 * precision * recall / (precision + recall)

OLLAMA_CHAT = "http://127.0.0.1:11434/v1/chat/completions"

SYSTEM = (
    "You answer questions about software system design. "
    "Answer with exactly what is asked for and nothing else: no explanation, "
    "no preamble, no punctuation beyond what the answer needs."
)


def digest_of(data: bytes) -> str:
    """sha256 with line endings normalised to LF first.

    THE PIN IS THE COMMITTED BYTES AND THE CHECK READ THE WORKING TREE.
    Measured 2026-09-09: `held-out.sha256` holds 0413b0f8..., which is exactly
    the sha of the bytes git stores; on Windows with `core.autocrlf=true` the
    same commit renders 196 CRLF lines on disk and hashes to d4900fda... So
    this script REFUSED TO RUN AT ALL in a Windows checkout - "the set is only
    held out if it is the set that was committed" was true, and the set WAS the
    set that was committed; the check was comparing a rendering with a record.

    Normalised, the file on disk matches the pin exactly, so nothing had
    drifted. Same fault as `scripts/the_vendored_copy.py` the same afternoon,
    and the same fix: a line ending is a property of whoever checked the file
    out, not of the set.

    What it gives up: a change that ONLY altered line endings would no longer
    be caught. For a held-out set whose subject is its rows, that is the right
    trade, and smaller than an integrity check nobody on Windows can pass.
    """
    return hashlib.sha256(data.replace(bytes([13, 10]), bytes([10]))).hexdigest()


def check_hash(path: Path) -> str:
    digest = digest_of(path.read_bytes())
    recorded = HERE / "held-out.sha256"
    if recorded.exists():
        want = recorded.read_text(encoding="utf-8").split()[0]
        if want != digest:
            raise SystemExit(
                "REFUSING: " + path.name + " does not match its recorded hash.\n"
                "  recorded " + want + "\n  actual   " + digest + "\n"
                "The set is only held out if it is the set that was committed."
            )
    return digest


def ask(model: str, prompt: str, timeout: int) -> str:
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,
            # 2048, NOT the ~120 an answer needs. The first run of this script
            # asked for 120 and scored minicpm5-hermes at 17%, which was not a
            # score at all: it is a REASONING model, the whole budget went into
            # its think block, `/v1/chat/completions` strips thinking, and 30 of
            # 36 answers came back EMPTY STRING and were graded wrong. An empty
            # answer is indistinguishable from a wrong one at the grader, so the
            # instrument reported a knowledge result for a truncation fault.
            # The budget has to cover the deliberation the model will do whether
            # or not anyone wants it.
            "max_tokens": 2048,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_CHAT, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        payload = json.loads(r.read().decode("utf-8"))
    return payload["choices"][0]["message"]["content"].strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--eval", default=str(HERE / "held-out.jsonl"))
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    path = Path(args.eval)
    digest = check_hash(path)
    rows = [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]

    print("model:     " + args.model)
    print("eval:      " + path.name + "  (" + str(len(rows)) + " rows, sha256 " + digest[:12] + ")")
    print("grader:    app.tools.evals.grade  (exact_match, contains)")
    print("")

    per = defaultdict(lambda: {"n": 0, EXACT_MATCH: 0, CONTAINS: 0})
    records = []
    errors = 0
    started = time.time()

    for row in rows:
        try:
            answer = ask(args.model, row["input"], args.timeout)
        except (urllib.error.URLError, OSError, KeyError) as exc:
            errors += 1
            answer = ""
            print("  row " + str(row["row_id"]) + " ERRORED: " + type(exc).__name__)
        verdict = grade(row["expected"], answer)
        f1 = set_f1(row["expected"], answer) if row["family"] in SET_FAMILIES else None
        fam = per[row["family"]]
        fam["n"] += 1
        fam[EXACT_MATCH] += int(verdict[EXACT_MATCH])
        fam[CONTAINS] += int(verdict[CONTAINS])
        if f1 is not None:
            fam[SET_F1] = fam.get(SET_F1, 0.0) + f1
        records.append(
            {
                "row_id": row["row_id"],
                "family": row["family"],
                "expected": row["expected"],
                "answer": answer,
                EXACT_MATCH: verdict[EXACT_MATCH],
                CONTAINS: verdict[CONTAINS],
                SET_F1: f1,
            }
        )

    elapsed = time.time() - started

    print("family              n   exact          contains")
    print("-" * 52)
    tot_n = tot_e = tot_c = 0
    for fam in sorted(per):
        d = per[fam]
        tot_n += d["n"]
        tot_e += d[EXACT_MATCH]
        tot_c += d[CONTAINS]
        print(
            fam.ljust(18)
            + str(d["n"]).rjust(3)
            + ("   " + str(d[EXACT_MATCH]) + "/" + str(d["n"])).ljust(9)
            + ("(" + str(round(100 * d[EXACT_MATCH] / d["n"])) + "%)").ljust(7)
            + ("   " + str(d[CONTAINS]) + "/" + str(d["n"])).ljust(9)
            + "(" + str(round(100 * d[CONTAINS] / d["n"])) + "%)"
        )
    print("-" * 52)
    # NO POOLED TOTAL ACROSS THE FOUR FAMILIES, DELIBERATELY.
    # They are scored by two different metrics now, and a single percentage over
    # a mix of exact_match and set F1 is a number nobody can reproduce or act on.
    # The headline is the two figures below, each over the rows it applies to.
    single_n = sum(per[f]["n"] for f in per if f not in SET_FAMILIES)
    single_e = sum(per[f][EXACT_MATCH] for f in per if f not in SET_FAMILIES)
    set_n = sum(per[f]["n"] for f in per if f in SET_FAMILIES)
    set_f1_sum = sum(per[f].get(SET_F1, 0.0) for f in per if f in SET_FAMILIES)
    print(
        "single-answer".ljust(18)
        + str(single_n).rjust(3)
        + "   exact " + str(single_e) + "/" + str(single_n)
        + " (" + str(round(100 * single_e / single_n)) + "%)"
    )
    if set_n:
        print(
            "component sets".ljust(18)
            + str(set_n).rjust(3)
            + "   mean set F1 " + str(round(100 * set_f1_sum / set_n)) + "%"
        )
    print("")
    print("errored rows: " + str(errors) + "  (scored 0, not dropped)")
    print("elapsed: " + str(round(elapsed, 1)) + "s")

    # AN EMPTY ANSWER IS NOT A WRONG ANSWER, AND THE GRADER CANNOT TELL.
    # `grade` sees "" and returns false for both metrics, which is correct for a
    # metric and wrong for a report: the model may never have answered at all.
    # The first run of this script scored 17% on 30 empty strings caused by a
    # token budget too small for a reasoning model's think block, and that number
    # would have gone into a record as a capability measurement.
    # So this refuses to certify a score rather than printing one with a caveat -
    # a caveat makes the error legible and still lets the number travel.
    blank = sum(1 for r in records if not r["answer"].strip())
    if blank:
        share = round(100 * blank / len(records))
        print("")
        print("EMPTY ANSWERS: " + str(blank) + " of " + str(len(records)) + " (" + str(share) + "%)")
        if share >= 10:
            print(
                "THIS IS NOT A SCORE. At or above 10% empty, the run is measuring "
                "whether the model replied, not whether it was right. Raise "
                "max_tokens, check the endpoint strips thinking, and re-run."
            )
            out = Path(args.out) if args.out else HERE / (
                "VOID-" + args.model.replace(":", "_").replace("/", "_") + ".json"
            )
            out.write_text(
                json.dumps(
                    {"model": args.model, "void": True, "reason": "empty answers",
                     "empty": blank, "of": len(records), "records": records},
                    indent=1,
                ),
                encoding="utf-8",
                newline="\n",
            )
            print("written as VOID: " + out.name)
            return 3

    out = Path(args.out) if args.out else HERE / ("baseline-" + args.model.replace(":", "_").replace("/", "_") + ".json")
    out.write_text(
        json.dumps(
            {
                "model": args.model,
                "eval_sha256": digest,
                "eval_rows": len(rows),
                "grader": "app.tools.evals.grade",
                "errored_rows": errors,
                "per_family": {k: dict(v) for k, v in per.items()},
                "total": {"n": tot_n, EXACT_MATCH: tot_e, CONTAINS: tot_c},
                "records": records,
            },
            indent=1,
        ),
        encoding="utf-8",
        newline="\n",
    )
    print("written: " + out.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
