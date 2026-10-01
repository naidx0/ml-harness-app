"""The wall that would have caught the 2026-09-10 leak, driven both ways.

## What happened, and why a tool had to change rather than a document

`check_split_leakage` shipped, and `carve_eval_set` runs it on its own output
and refuses to write a leaking split. **Neither helps a split somebody made by
hand.** `runs/honest-path` was split on 19 August without either, and measured on
2026-09-10 it carried **3 of 24 eval rows into the train file** at up to 0.944
similarity — none of them an exact string match, so reading the two files would
not have found it. That contamination was carrying the only statistically
resolved training result this project had produced: removing the leaked rows
took McNemar from p = 0.0391 to p = 0.0703.

Nothing refused it, because nothing was asked.

So `start_training` now asks, in the same place and for the same reason as the
synthetic-verification wall one door up: *a leaked row that never reaches a gate
still reaches the weights AND the score, and the score is what gets believed.*

## The three states, and why the third one is reported rather than skipped

- **Leaks** → refused, naming the file and the count.
- **Clean** → proceeds, and `leakage.ran` is `True` in the reply.
- **Not checked** → proceeds, and `leakage.ran` is `False` **with a reason**.

That third case is the one this repository keeps getting wrong. A check that did
not run and a check that found nothing are both silence, and silence gets read as
the reassuring one. `test_a_clean_check_and_an_absent_one_do_not_look_alike`
is the whole argument in one assertion.
"""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import support  # noqa: F401  - installs the suite's sandbox fences

from app.tools import data as datatools

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Real rows from this project's own bookshop corpus, so the near-match logic is
#: exercised on the register it was tuned for rather than on lorem ipsum.
SHARED = {
    "instruction": "My parcel arrived damaged.",
    "response": (
        "I am sorry. Send a photo of the packaging and the book and we will "
        "post a replacement the same day, no need to return the damaged copy."
    ),
}
ONLY_TRAIN = {
    "instruction": "Do you buy comics?",
    "response": "We do not deal in comics or graphic novels.",
}
ONLY_EVAL = {
    "instruction": "Can I bring my dog in?",
    "response": "Well behaved dogs are welcome anywhere on the ground floor.",
}


def write(path: Path, rows) -> str:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return str(path)


class TheLeakCheckItselfSeesTheOverlapTest(unittest.TestCase):
    """The instrument, before anything is asserted about the wall built on it.

    If `check_split_leakage` cannot see a planted overlap, every assertion in
    the class below passes for the wrong reason.
    """

    def test_a_planted_overlap_is_found(self):
        with TemporaryDirectory() as tmp:
            here = Path(tmp)
            train = write(here / "train.jsonl", [ONLY_TRAIN, SHARED])
            evalset = write(here / "eval.jsonl", [ONLY_EVAL, SHARED])
            found = datatools.check_split_leakage(train, evalset)
        self.assertTrue(found.get("ran"))
        self.assertGreater(
            found.get("leaked_rows") or 0, 0,
            "the leak checker did not see a row present in both files, so the "
            "wall built on it cannot be trusted either.",
        )

    def test_a_clean_split_is_reported_clean(self):
        """The other direction. A checker that says 'leak' to everything would
        pass the test above and refuse every honest training run there is."""
        with TemporaryDirectory() as tmp:
            here = Path(tmp)
            train = write(here / "train.jsonl", [ONLY_TRAIN])
            evalset = write(here / "eval.jsonl", [ONLY_EVAL])
            found = datatools.check_split_leakage(train, evalset)
        self.assertTrue(found.get("ran"))
        self.assertEqual(
            found.get("leaked_rows") or 0, 0,
            "two files sharing no rows were reported as leaking, which would "
            "make the wall refuse everything.",
        )


class TheRefusalIsWiredIntoTheTrainingDoorTest(unittest.TestCase):
    """Pinned by reading the door — AND DRIVEN, 2026-09-10, both ways.

    The first version of this docstring said driving it end to end needed a
    built recipe environment and a live thread with a measured baseline, so it
    only read the source. Both existed. Driven through `Registry.call` on thread
    46, whose baselines were measured on `runs/honest-path/eval.jsonl`:

        dataset_path runs/honest-path/train.jsonl   (3 exact rows in both)
          -> ok False, error `eval_set_leaks_into_this_data`, nothing trained,
             leakage.ran True, 3 leaked at rate 0.125, and the strip left all 3

        dataset_path evals/architecture-json/train.jsonl   (a different domain)
          -> ok True, job 5, run 1122, leakage.ran True, 0 leaked

    **The second call is the one that matters.** A wall that refused everything
    would pass the first and block every honest run there is; only the clean
    case shows it discriminates. The assertions below stay source-level because
    they must hold on a machine with no GPU and no built environment, but they
    are no longer the only evidence."""

    def setUp(self):
        self.source = (REPO_ROOT / "app" / "tools" / "training.py").read_text(
            encoding="utf-8"
        )

    def test_start_training_asks_the_leak_question(self):
        self.assertIn("check_split_leakage", self.source,
                      "start_training no longer consults the leak checker, so a "
                      "contaminated split can reach the weights again.")
        self.assertIn("eval_set_leaks_into_this_data", self.source,
                      "the refusal this wall exists to produce is gone.")

    def test_the_refusal_says_nothing_was_trained(self):
        """A refusal that leaves the reader unsure whether a GPU is running is
        worse than no refusal."""
        self.assertIn("Nothing was trained.", self.source)

    def test_the_refusal_names_the_way_out(self):
        self.assertIn("carve_eval_set", self.source,
                      "the refusal must name the tool that produces a split "
                      "which passes, or it is a dead end.")

    def test_a_clean_check_and_an_absent_one_do_not_look_alike(self):
        """THE WHOLE ARGUMENT, in one assertion.

        `leakage` is returned on SUCCESS as well as on refusal, carrying `ran`.
        Without that, a run whose eval set was never checked and a run whose
        eval set was checked and found clean produce identical replies - and
        this repository's recurring defect is exactly that confusion, read as
        the reassuring one.
        """
        self.assertIn('"leakage": leakage', self.source,
                      "the leak report is no longer returned, so a check that "
                      "did not run is indistinguishable from one that passed.")
        # Every branch that sets it must say whether it ran.
        self.assertIn('"ran": False', self.source)
        self.assertIn('"ran": True', self.source)
        self.assertIn("no thread_id, so there is no eval set to check against",
                      self.source)


class TheSharedTemplateTrapTest(unittest.TestCase):
    """A repeated instruction must not read as a leak, and a leak must survive
    having it removed.

    `check_split_leakage` shingles whole rows, so boilerplate every row carries
    dominates the similarity. Without this, the wall above would refuse a
    legitimate fine-tune on any templated corpus.

    **THE SPECIMEN IS CONSTRUCTED HERE, not borrowed from the corpus.** It used
    to be `evals/architecture-json` train-vs-valid, measured at 0.95 raw and
    0.00 on the description alone. On 2026-09-10 that corpus was regenerated
    with composed labels and the false positive stopped reproducing: the raw
    reading went from 38 of 40 valid rows at 0.892 to 0 of 40. The test had
    silently lost the thing it was about, and it failed loudly ONLY because it
    asserted its own premise before its claim.

    A test whose subject is a data file another lane regenerates does not own
    its subject. So the pair below is built in this file from two disjoint word
    lists, and cannot stop reproducing unless someone edits it.
    """

    ARCH = REPO_ROOT / "evals" / "architecture-json"
    SUFFIX = (" Return ONLY a JSON object with two keys: nodes and edges, "
              "and nothing else at all.")

    def _stripped(self, left: Path, right: Path) -> dict:
        from tempfile import TemporaryDirectory
        from app.tools import templates
        mine, theirs = templates.affixes_for_pair(left, right)
        with TemporaryDirectory() as scratch:
            here = Path(scratch)
            a = templates.without_template(left, mine, here / "a.jsonl")
            b = templates.without_template(right, theirs, here / "b.jsonl")
            return datatools.check_split_leakage(str(a), str(b))

    #: Two vocabularies with no word in common, each row ending in the same
    #: instruction. There IS no leak here, and that is the point: any
    #: similarity the checker reports is the boilerplate and nothing else.
    #: LENGTH IS THE WHOLE MECHANISM, so this is a realistic instruction and
    #: not a token. The checker shingles whole rows: boilerplate only drowns
    #: the content when there is more of it than there is content. Shorten
    #: this and the specimen stops reproducing the trap - which the premise
    #: assertion below will say out loud rather than passing quietly.
    BOILERPLATE = (
        " Return ONLY a JSON object with two keys: nodes and edges. Each node"
        " is an object with id, label and kind, where kind is one of service,"
        " datastore, queue, gateway, client, job, cache. Each edge is an object"
        " with from and to using node ids, optionally with a label. No prose,"
        " no markdown fence.")

    LEFT_WORDS = ("alpha", "bravo", "charlie", "delta", "echo", "foxtrot")
    RIGHT_WORDS = ("quebec", "romeo", "sierra", "tango", "uniform", "victor")

    def _templated(self, here, name, words, n, start):
        """n rows over `words`, every one ending in the same instruction."""
        import json
        out = []
        for i in range(n):
            word = words[(i + start) % len(words)]
            out.append(json.dumps({
                "prompt": ("The " + word + " number " + str(i + start)
                           + " calls the " + word + " sink." + self.BOILERPLATE),
                "completion": json.dumps(
                    {"nodes": [{"id": word[:4], "label": word}]}),
            }))
        path = here / name
        path.write_text(chr(10).join(out), encoding="utf-8")
        return path

    def test_a_shared_instruction_reads_as_a_leak_and_stripping_clears_it(self):
        """BOTH HALVES, on a specimen that cannot stop reproducing.

        The premise is asserted before the claim. A test that checked only the
        stripped reading would pass forever on two files that never tripped the
        false positive at all, and would report that as the strip working - the
        exact shape of `a transform that removes nothing reports success`.
        """
        from tempfile import TemporaryDirectory
        from app.tools import templates
        with TemporaryDirectory() as scratch:
            here = Path(scratch)
            left = self._templated(here, "train.jsonl", self.LEFT_WORDS, 60, 0)
            right = self._templated(here, "valid.jsonl", self.RIGHT_WORDS, 20, 500)

            self.assertEqual(
                set(self.LEFT_WORDS) & set(self.RIGHT_WORDS), set(),
                "the two halves must share no content word, or a similarity "
                "between them is not necessarily the boilerplate and this "
                "specimen proves nothing.")

            raw = datatools.check_split_leakage(str(left), str(right))
            self.assertGreater(
                raw.get("leaked_rows") or 0, 0,
                "two files sharing only a repeated instruction no longer read "
                "as leaking, so either the checker changed or this specimen "
                "stopped exercising it. Do not delete this assertion to go "
                "green: it is the premise of the one below.")

            mine, theirs = templates.affixes_for_pair(left, right)
            a = templates.without_template(left, mine, here / "a.jsonl")
            b = templates.without_template(right, theirs, here / "b.jsonl")
            self.assertEqual(
                datatools.check_split_leakage(str(a), str(b)).get("leaked_rows") or 0,
                0,
                "a split still reads as leaking once its repeated instruction "
                "is removed, so start_training would refuse a legitimate "
                "fine-tune on any templated corpus.")

    def test_the_shipped_corpus_is_not_refused_by_the_wall(self):
        """The property the training run actually needs, on the real files.

        This is NOT the trap test, it is the consequence. `start_training`
        calls `check_split_leakage` and refuses on any leaked row, so the
        corpus ML BUILD trains on has to read clean AS IT SHIPS. Measured
        2026-09-10: under the previous fixed-vocabulary generator it read 38 of
        40 valid rows at 0.892, which is a refusal; composing the labels took
        it to 0 of 40.

        If this fails the fine-tune is blocked at the door, and the fix is the
        generator or a documented strip - never a lower threshold.
        """
        train = self.ARCH / "train.jsonl"
        valid = self.ARCH / "valid.jsonl"
        if not (train.is_file() and valid.is_file()):
            self.skipTest("the architecture-json corpus is not on this machine")
        found = datatools.check_split_leakage(str(train), str(valid))
        self.assertEqual(
            found.get("leaked_rows") or 0, 0,
            "the shipped train/valid pair reads as leaking, so start_training "
            "will refuse it. " + str(found.get("summary")))

    def test_a_genuinely_clean_pair_stays_clean(self):
        train = self.ARCH / "train.jsonl"
        held = self.ARCH / "held-out.jsonl"
        if not (train.is_file() and held.is_file()):
            self.skipTest("the architecture-json corpus is not on this machine")
        self.assertEqual(self._stripped(train, held).get("leaked_rows") or 0, 0)

    def test_a_real_duplicate_survives_the_stripping(self):
        """THE CONTROL, and it failed for two earlier versions of the helper.

        One stripped raw characters off a JSONL line, leaving text that was no
        longer JSON - the checker then read zero rows and called it clean.
        Another detected no template in a ONE-ROW eval and stripped only the
        training side, so the two copies of an identical row no longer matched.
        """
        with TemporaryDirectory() as tmp:
            here = Path(tmp)
            dup = {"prompt": "A browser calls a REST API and it writes Postgres." + self.SUFFIX,
                   "completion": '{"nodes":[]}'}
            other = {"prompt": "A phone app talks to a queue worker over grpc." + self.SUFFIX,
                     "completion": '{"nodes":[]}'}
            train = write(here / "train.jsonl", [other, dup])
            evalset = write(here / "eval.jsonl", [dup])
            found = self._stripped(Path(train), Path(evalset))
        self.assertGreater(
            found.get("leaked_rows") or 0, 0,
            "an identical row under a shared instruction went unnoticed once "
            "the instruction was stripped. The stripping has blinded the check.",
        )

    def test_the_rewrite_is_still_readable_jsonl(self):
        """The defect that made the control pass for the wrong reason: a rewrite
        that is not JSON makes the checker read zero rows and report clean."""
        from tempfile import TemporaryDirectory as TD
        from app.tools import templates
        with TD() as tmp:
            here = Path(tmp)
            rows = [{"prompt": f"Row {i}." + self.SUFFIX, "completion": "{}"} for i in range(4)]
            src = Path(write(here / "src.jsonl", rows))
            out = templates.without_template(src, templates.affixes_of(src), here / "out.jsonl")
            lines = [l for l in out.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual(len(lines), len(rows), "rows were lost in the rewrite")
        for line in lines:
            json.loads(line)  # raises if the rewrite broke the JSON


if __name__ == "__main__":
    unittest.main()
