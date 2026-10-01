"""The seven planted cases from the design page, written before the check.

The page's section 6 names them and says what each must answer. They are here
first, and deliberately: a case written after the code it tests is a case shaped
by the code.

TWO AMENDMENTS, REGISTERED BEFORE THE FIRST RUN.

**Case 6 does not name its instrument, and the two candidates differ by more
than its tolerance.** The page expects `resident 5,133 MiB, matching the fit
bench's measured 5,129 within 10`. Measured on this machine tonight, granite at
65,536 reads **5,133 MiB** from the bench's own per-layer prediction and
**4,959 MiB** from `ollama ps` - a gap of 174, outside the case's +/-10 and
outside its +/-50 refutation line, because they are not the same quantity. The
bench validates against an `nvidia-smi` delta; `ollama ps` reports the runtime's
own accounting. Two fit-bench rows were withdrawn earlier tonight for exactly
this confusion. So case 6 here asserts the check reproduces THE BENCH'S OWN
PREDICTION, and names that as the instrument; a comparison against a live
resident figure is a different case and needs the card.

**The provenance count is reported, not predicted.** The page registers
*measured 9 of 11 or better*, and the eleven lines do not exist until somebody
writes them - so both numerator and denominator are the implementer's to choose,
which makes the prediction unfalsifiable in the direction that matters. What is
registered here instead is the claim nobody can tune: **zero `fits` lines
resting on a defaulted geometry**, whatever the page's length. The count is
printed with its denominator and reported, not predicted.

**And one deviation from the page's section 5.** It says the check ships beside
the card owner. `card_owner/` is excluded from any public mirror by this
repository's own release policy - it necessarily names a private path - so a
check that tells a person on a fresh machine what would run would not reach
them. It lives in `scripts/` instead.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "one_click_check", REPO / "scripts" / "one_click_check.py"
)
check = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
# REGISTERED BEFORE EXECUTION. `@dataclass` resolves its annotations through
# `sys.modules[cls.__module__]`, so a module loaded by path and never
# registered raises on the decorator rather than on anything it declares. The
# other loaders in this suite do not hit it only because none of them loads a
# module that uses dataclasses.
sys.modules[_spec.name] = check
_spec.loader.exec_module(check)

A_CARD = "NVIDIA GeForce RTX 2060 SUPER, 8192 MiB, 5979 MiB, 2213 MiB, 581.29, 7.5"


class CaseOneTheTrap(unittest.TestCase):
    """A model config passed as saved, geometry one level down."""

    def test_a_wrapped_config_says_pass_the_inner_object_and_never_does_not_fit(self):
        wrapped = {"config": {"num_hidden_layers": 40, "num_key_value_heads": 8,
                              "hidden_size": 2560, "num_attention_heads": 20}}
        line = check.a_fit_line("a-model", wrapped, ctx=65536, free_mib=8192)
        self.assertEqual(line.provenance, "unknown")
        self.assertIn("geometry not read", line.why)
        self.assertIn("inner object", line.why)
        self.assertNotIn("does not fit", line.value.lower())


class CaseTwoNoCard(unittest.TestCase):
    """A machine with no nvidia-smi. Not a failure - a fact."""

    def test_every_vram_line_says_not_found_and_the_exit_is_zero(self):
        page = check.the_page(nvidia_smi=None, holder=None, runtime=None, catalogue={})
        vram = [l for l in page.lines if "vram" in l.label.lower()]
        self.assertTrue(vram, "the page has no VRAM lines to report on")
        for line in vram:
            with self.subTest(line.label):
                self.assertEqual(line.provenance, "not found")
                self.assertIn("no nvidia-smi", line.why)
        self.assertEqual(page.exit_code, 0, "a machine with no card is a fact, not a failure")

    def test_the_ram_is_still_measured(self):
        page = check.the_page(nvidia_smi=None, holder=None, runtime=None, catalogue={})
        ram = [l for l in page.lines if l.label.lower().startswith("system ram")]
        self.assertTrue(ram)
        self.assertIn(ram[0].provenance, ("measured", "not found"))


class CaseThreeACardHeld(unittest.TestCase):
    """A foreign lock with identity, alive."""

    def test_the_holder_is_named_and_the_showcase_says_it_is_held(self):
        import os

        holder = {"lane": "another", "pid": os.getpid(),
                  "born": check.born_of(os.getpid()), "what": "a long run",
                  "since": "2026-09-06T01:00:00Z"}
        page = check.the_page(nvidia_smi=A_CARD, holder=holder, runtime=None, catalogue={})
        card = check.one(page, "card")
        self.assertIn("another", card.value)
        self.assertEqual(card.provenance, "measured")
        self.assertIn("held", card.value.lower())


class CaseFourALockWithoutIdentity(unittest.TestCase):
    """The old three-field line. Never 'free'."""

    def test_it_says_it_cannot_decide_rather_than_free(self):
        holder = {"lane": "practical", "since": "2026-09-05T18:52:10Z", "what": "an experiment"}
        page = check.the_page(nvidia_smi=A_CARD, holder=holder, runtime=None, catalogue={})
        card = check.one(page, "card")
        self.assertIn("cannot", card.value.lower())
        self.assertNotIn("free", card.value.lower())
        self.assertEqual(card.provenance, "unknown")


class CaseFiveTheHybrid(unittest.TestCase):
    """A header the walk reads as hybrid gets the per-layer walk, not the dense
    formula, and says which it used."""

    def test_a_hybrid_header_is_walked_per_layer_and_says_so(self):
        hybrid = {"num_hidden_layers": 40, "num_key_value_heads": 8, "hidden_size": 1536,
                  "num_attention_heads": 12, "layer_types": ["recurrent"] * 36 + ["full_attention"] * 4}
        line = check.a_fit_line("a-hybrid", hybrid, ctx=65536, free_mib=8192)
        self.assertIn("per-layer", line.why)
        self.assertNotEqual(line.provenance, "unknown")


class CaseSixThisMachineTonight(unittest.TestCase):
    """granite at 65,536, against THE BENCH'S OWN PREDICTION - see the
    amendment at the top of this file for why the instrument is named."""

    #: READ OFF THE HEADER, not invented. The first version of this fixture
    #: said `num_attention_heads: 20`, which makes head_dim 128 where the real
    #: header gives 40 heads and a head_dim of 64 - so the KV term came out
    #: twice too large and the case failed by 2,858 MiB. A fixture nobody read
    #: off the thing it describes is a guess with a number on it.
    GRANITE = {"num_hidden_layers": 40, "num_key_value_heads": 8, "hidden_size": 2560,
               "num_attention_heads": 40, "vocab_size": 100352}

    def test_it_reproduces_the_benchs_prediction_within_ten_mib(self):
        got = check.resident_mib(self.GRANITE, ctx=65536, weights_mib=2140)
        self.assertIsNotNone(got, "the walk produced no number")
        self.assertLess(abs(got - 5133), 10, f"the walk says {got}, the bench says 5133")

    #: The bench compares against a CALIBRATED usable figure for this card -
    #: 7,600 of the 8,192 it advertises, measured headroom - not against raw
    #: free VRAM. The page's expected numbers are computed against that, so the
    #: comparison uses it too; comparing my figure against 8,192 and the page's
    #: against 7,600 would have been two different questions with one tolerance.
    #:
    #: THE CHECK ITSELF DELIBERATELY USES FREE VRAM AS READ. A person on a fresh
    #: machine wants to know what fits in the memory that is free right now, not
    #: in a constant fitted on somebody else's card.
    USABLE = 7600

    def test_a_bigger_window_does_not_fit_and_a_smaller_one_does(self):
        big = check.a_fit_line("granite", self.GRANITE, ctx=131072,
                               free_mib=self.USABLE, weights_mib=2140)
        self.assertIn("does not fit", big.value.lower())
        smaller = check.a_fit_line("granite", self.GRANITE, ctx=98304,
                                   free_mib=self.USABLE, weights_mib=2140)
        self.assertIn("fits", smaller.value.lower())
        self.assertNotIn("does not", smaller.value.lower())

    def test_the_margins_agree_with_the_page_inside_its_own_tolerance(self):
        """The page says 131,072 misses by 428 and 98,304 fits with 1,004, and
        sets 50 MiB as the line at which the walk is the wrong walk.

        This walk lands 29 and 30 short of those - inside the page's own
        tolerance, and the residual is named rather than tuned away: the bench
        reads the real tensor list and takes the token embedding's own
        quantisation from it, while this computes that term from vocabulary and
        width at an assumed 4.5 bits. Moving a constant to close 29 MiB would be
        fitting to the answer.
        """
        for ctx, expected, direction in ((131072, 428, "does not fit by"), (98304, 1004, "fits with")):
            with self.subTest(ctx):
                line = check.a_fit_line("granite", self.GRANITE, ctx=ctx,
                                        free_mib=self.USABLE, weights_mib=2140)
                self.assertIn(direction, line.value.lower())
                # The first number in the sentence, whatever the wording. The
                # first version indexed into split() by position and broke on
                # "fits with 1,034 MiB to spare" - a parser that counts words is
                # a parser that breaks when somebody improves a sentence.
                got = int(re.search(r"([\d,]+) MiB", line.value).group(1).replace(",", ""))
                self.assertLess(abs(got - expected), 50, f"{ctx}: {line.value}")


class CaseSevenProvenance(unittest.TestCase):
    """The count is reported with its denominator. What is REGISTERED is the
    claim nobody can tune - see the amendment at the top."""

    def test_no_fits_line_ever_rests_on_a_defaulted_geometry(self):
        """THE REGISTERED CLAIM. Refutable whatever the page's length."""
        defaulted = {"hidden_size": 2560}  # not enough to compute anything
        line = check.a_fit_line("thin", defaulted, ctx=65536, free_mib=8192)
        self.assertEqual(line.provenance, "unknown")
        self.assertNotIn("fits", line.value.lower())

    def test_the_first_line_is_the_count_with_its_denominator(self):
        page = check.the_page(nvidia_smi=A_CARD, holder=None, runtime=None, catalogue={})
        self.assertRegex(page.first_line, r"^measured \d+ of \d+$")
        self.assertEqual(page.measured + page.not_measured, page.total)

    def test_the_page_is_complete_with_no_runtime_and_names_every_absence(self):
        page = check.the_page(nvidia_smi=None, holder=None, runtime=None, catalogue={})
        self.assertGreaterEqual(len(page.lines), 6)
        for line in page.lines:
            with self.subTest(line.label):
                self.assertTrue(line.value, f"{line.label} has no value")
                if line.provenance != "measured":
                    self.assertTrue(line.why, f"{line.label} is not measured and does not say why")


class TwoTheCasesDidNotCoverAndThePageFound(unittest.TestCase):
    """Both found by RUNNING it, and both are the void rule reached by a door
    the seven planted cases left open. Case 7 guards a defaulted GEOMETRY; these
    are a defaulted free-VRAM figure and a substituted head count, and each
    produced a confident, measured-looking, wrong line."""

    def test_a_missing_kv_head_count_is_not_the_attention_head_count(self):
        """A grouped-query model has far fewer KV heads than attention heads -
        eight against thirty-two is ordinary - so substituting one for the
        other overstates the cache by that ratio. On this machine's own page it
        printed `does not fit by 14,458 MiB` for a model whose header simply
        omits the field."""
        no_kv = {"num_hidden_layers": 36, "num_attention_heads": 32, "hidden_size": 4096}
        line = check.a_fit_line("no-kv", no_kv, ctx=65536, free_mib=8192)
        self.assertEqual(line.provenance, "unknown")
        self.assertIn("num_key_value_heads missing", line.why)
        self.assertNotIn("fit", line.value.lower())

    def test_free_vram_that_could_not_be_read_makes_every_fit_unknown(self):
        """The first version read field four of hwdetect's nvidia-smi line and
        got the COMPUTE CAPABILITY, 7.5, then computed six fit lines against
        7.5 MiB and marked them measured. A number from the wrong column is
        worse than a missing one: it has the shape of an answer."""
        page = check.the_page(nvidia_smi=A_CARD, holder=None, runtime=None,
                              free_mib=None,
                              catalogue={"m": {"ctx": 65536, "weights_mib": 2098,
                                               "config": CaseSixThisMachineTonight.GRANITE}})
        free = check.one(page, "VRAM free")
        self.assertEqual(free.provenance, "not found")
        fit = check.one(page, "m at 65,536")
        self.assertEqual(fit.provenance, "unknown")
        self.assertIn("free VRAM not found", fit.why)
        self.assertNotIn("does not fit", fit.value.lower())

    def test_the_free_reader_asks_for_the_column_it_wants(self):
        source = (REPO / "scripts" / "one_click_check.py").read_text(encoding="utf-8")
        self.assertIn("memory.free", source)


class ItemSeventyTheCatalogueIsASnapshot(unittest.TestCase):
    """The catalogue is six models frozen at the moment somebody wrote it, and
    nothing regenerates it. Measured within hours: a seventh was on disk."""

    ENTRY = {"ctx": 65536, "weights_mib": 2098,
             "config": CaseSixThisMachineTonight.GRANITE}

    def test_a_model_on_disk_the_catalogue_does_not_name_is_named(self):
        page = check.the_page(nvidia_smi=A_CARD, holder=None, runtime=None, free_mib=8192,
                              catalogue={"granite4.2:3b": self.ENTRY},
                              on_disk=["granite4.2:3b", "something-else:latest"])
        line = check.one(page, "not in this catalogue")
        self.assertIn("something-else", line.value)
        self.assertEqual(line.provenance, "unknown")
        self.assertIn("nothing regenerates it", line.why)

    def test_a_tag_and_its_bare_name_are_the_same_model(self):
        """`granite4.2:3b` in the catalogue covers `granite4.2` on disk. A page
        that reported a model missing because of a tag suffix would be crying
        wolf about its own naming."""
        page = check.the_page(nvidia_smi=A_CARD, holder=None, runtime=None, free_mib=8192,
                              catalogue={"granite4.2:3b": self.ENTRY},
                              on_disk=["granite4.2:3b"])
        self.assertEqual(check.one(page, "not in this catalogue").value, "none")

    def test_a_full_catalogue_says_none_and_counts_as_measured(self):
        page = check.the_page(nvidia_smi=A_CARD, holder=None, runtime=None, free_mib=8192,
                              catalogue={"a": self.ENTRY}, on_disk=["a"])
        line = check.one(page, "not in this catalogue")
        self.assertEqual(line.value, "none")
        self.assertEqual(line.provenance, "measured")

    def test_a_page_that_was_not_told_what_is_on_disk_carries_no_such_line(self):
        """Absent is absent. A page with no runtime to ask must not report an
        empty answer as a complete one."""
        page = check.the_page(nvidia_smi=A_CARD, holder=None, runtime=None, catalogue={})
        with self.assertRaises(KeyError):
            check.one(page, "not in this catalogue")


class TheLawsItEnforcesOnItself(unittest.TestCase):
    def test_it_never_writes_a_lock(self):
        source = (REPO / "scripts" / "one_click_check.py").read_text(encoding="utf-8")
        for forbidden in ("write_text", "O_CREAT", "take(", "acquire("):
            with self.subTest(forbidden):
                self.assertNotIn(forbidden, source)

    def test_it_loads_no_model(self):
        source = (REPO / "scripts" / "one_click_check.py").read_text(encoding="utf-8")
        for forbidden in ("/api/generate", "num_predict", "ollama run"):
            with self.subTest(forbidden):
                self.assertNotIn(forbidden, source)

    def test_it_carries_a_witness_of_what_it_read(self):
        page = check.the_page(nvidia_smi=A_CARD, holder=None, runtime=None, catalogue={})
        self.assertIsInstance(page.witnesses, dict)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
