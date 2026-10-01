"""Basilica is the implemented direction, and this proves the transcription.

The failure mode this exists for was measured on Letter: a book that names
faces and hues means nothing if the token layer drifts or the faces are named
but not shipped — the owner reviewed that build and saw Segoe on rounded
purple. Every assertion below binds the app to the book's own values, so the
next drift fails a test instead of a review.
"""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
BOOK = ROOT / "docs" / "brand" / "basilica" / "basilica.html"


def _the_marks_own_points() -> tuple[str, str]:
    """The cleave's two outlines, from the script that draws the icon.

    READ RATHER THAN TYPED, for the reason this whole test exists: the claim is
    that the book, the rail, the tab and the taskbar are ONE object. A pair of
    literals copied in here would pass on the day they were copied and go on
    passing after the mark moved, which is the only way this can fail.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "mlh_make_icon", ROOT / "scripts" / "make_icon.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.glyph(24)
TOKENS = ROOT / "frontend" / "src" / "styles" / "tokens.css"
MAIN = ROOT / "frontend" / "src" / "main.tsx"
ICON = ROOT / "frontend" / "src" / "components" / "Icon.tsx"
SHELL = ROOT / "frontend" / "src" / "styles" / "shell.css"


#: A document read for prose, with its line breaks flattened. A phrase that
#: reads as one sentence can sit across two lines in the file, and a plain
#: substring search then reports it absent - which is how a check accused
#: docs/how-to-verify.md of not naming the product's claim when it did.
def _flat(text: str) -> str:
    return " ".join(text.split())


class BasilicaIsImplementedTest(unittest.TestCase):
    def setUp(self):
        self.book = BOOK.read_text(encoding="utf-8")
        self.tokens = TOKENS.read_text(encoding="utf-8")

    def test_the_book_exists_and_carries_its_investigation(self):
        # The book is a synthesis of two INVESTIGATED references plus one
        # owner's correction, and it says which and when — a design with no
        # provenance is a mood board.
        self.assertIn("#1A1A18", self.book)
        self.assertIn("#6088EE", self.book)
        self.assertIn("arenaphysica.com", self.book)
        self.assertIn("polarity.io", self.book)
        self.assertIn("darker grey theme than blue", self.book)

    def test_the_token_layer_is_transcribed_not_remembered(self):
        # The stone and the inks are the owner's 2026-09-12 correction - one
        # step lighter, more contrast - folded into the book first and read
        # into the tokens from it, as the 2026-08-29 correction was.
        for value in ("#1F1F1D", "#181817", "#24241F", "#2B2A27", "#33322F",
                      "#F8F3E6", "#6088EE", "#4E74DC", "#D6BA78"):
            self.assertIn(value, self.tokens, f"the book's {value} is not in tokens.css")
            self.assertIn(value, self.book, f"{value} is in tokens.css and not in the book")

    def test_gold_spends_only_on_selection(self):
        # Gold is gilding: ::selection and the selected state, nothing else.
        self.assertIn("--selection-bg:rgba(214,186,120,.30)", self.tokens)
        self.assertIn("--state-selected:rgba(214,186,120,.12)", self.tokens)

    def test_the_ramp_is_masonry(self):
        # "More square boxes" was the order; 2/2/2/4/6 under the historic names
        # is the implementation. A soft radius creeping back fails here.
        self.assertIn("--r-4:2px; --r-8:2px; --r-10:2px; --r-14:4px; --r-18:6px;", self.tokens)

    def test_the_faces_are_bundled_not_named(self):
        # Letter's fonts never rendered because nothing shipped them. The four
        # faces are woff2 imports that resolve inside the build.
        main = MAIN.read_text(encoding="utf-8")
        for pkg in ("@fontsource/marcellus", "@fontsource/cormorant-garamond",
                    "@fontsource/ibm-plex-sans", "@fontsource/ibm-plex-mono"):
            self.assertIn(pkg, main, f"{pkg} is not imported — the face will not render")
        self.assertIn('--font-display:"Marcellus"', self.tokens)

    def test_the_script_face_is_retired(self):
        # "The cursive looks horrible" — it is gone, everywhere, including the
        # token that could quietly bring it back.
        self.assertNotIn("Pinyon", self.tokens)
        self.assertNotIn("font-script", self.tokens)
        self.assertNotIn("font-script", SHELL.read_text(encoding="utf-8"))

    def test_the_wordmark_is_an_inscription(self):
        shell = SHELL.read_text(encoding="utf-8")
        i = shell.index(".wordmark {")
        block = shell[i:shell.index("}", i)]
        self.assertIn("var(--font-display)", block)
        self.assertIn("uppercase", block)
        self.assertIn(".18em", block)

    def test_the_mark_is_the_cleave(self):
        # 2026-09-11, the owner, on the running product: "the harness still
        # has the lightning bolts a lot on it as well right now, which is
        # very annoying." His earlier call - "keep the bolt universal, it
        # looks a lot better", 2026-08-31 - was made when the bolt WAS the
        # identity. It stopped being that the morning he picked the gauge for
        # the application icon, and a product with two marks has two answers
        # to "what is this". The gauge in turn stopped being it on 2026-09-14,
        # when Max reversed his own call of the day before: "cleave, go with
        # the cleave." The argument is unchanged and it is why this test keeps
        # asserting the DEPARTED marks are absent, one more of them each time.
        #
        # THE BOLT IS ASSERTED GONE, not merely un-asserted. It lived in two
        # places and only one of them is the product - the other is this
        # book, which would otherwise go on documenting a mark nothing ships.
        icon = ICON.read_text(encoding="utf-8")
        cap, body = _the_marks_own_points()
        for surface in (icon, self.book):
            # The value arc and the pivot: the two parts of the drawing that
            # are the same numbers in the .ico, the favicon and the sprite.
            # Redrawn 2026-09-12 in the product's own tokens by the icons
            # lane (4677c28): the value arc, the tail-and-hub needle and the
            # accent are the same numbers in Icon.tsx, the book's sprite,
            # icon.svg and the favicon.
            # THE CLEAVE'S TWO OUTLINES, AND THEY ARE NOT TYPED HERE. The
            # points come out of the generator that draws the .ico and the
            # favicon, so this cannot pass while the book and the taskbar
            # disagree - which is the only failure worth having a test for.
            self.assertIn(cap, surface)
            self.assertIn(body, surface)
            # EVERY MARK BEFORE IT IS ASSERTED GONE, not merely un-asserted:
            # the gauge's value arc and needle, and the bolt before that.
            self.assertNotIn("A 7.92 7.92 0 0 1 16.66 8.47", surface)
            self.assertNotIn("15.82,9.63", surface)
            self.assertNotIn("#8b8af6", surface)
            self.assertNotIn("M25.946 44.938", surface)
            self.assertNotIn("boltfill", surface)
            self.assertNotIn("boltgrad", surface)
        self.assertNotIn('x="5" y="8" width="4.6"', icon)

    def test_section_cards_cast_the_popover_shadow(self):
        # The owner pointed at the old Machine dropdown: cards carry that
        # panel's depth (--e2), the diagnosis card one step deeper, and the
        # e2 token is the 6/18 drop with the cream top-light.
        shell = SHELL.read_text(encoding="utf-8")
        i = shell.index(".card {")
        block = shell[i:shell.index("}", i)]
        self.assertIn("box-shadow: var(--e2)", block)
        self.assertIn("box-shadow: var(--e3)", shell[shell.index(".card--diagnosis"):][:200])
        self.assertIn("--e2:inset 0 1px 0 rgba(241,235,219,.06), 0 6px 18px rgba(0,0,0,.42);", self.tokens)
        self.assertIn("0 6px 18px rgba(0,0,0,.42)", self.book)

    def test_the_supersession_is_recorded(self):
        ds = (ROOT / "docs" / "DESIGN_SYSTEM.md").read_text(encoding="utf-8")
        self.assertIn("BASILICA IS NOW THE IMPLEMENTED", _flat(ds))
        self.assertIn("PUMICE", ds)
        # And the trail stays walkable — the Letter step is history, not erased.
        self.assertIn("LETTER IS NOW THE IMPLEMENTED", _flat(ds))


if __name__ == "__main__":
    unittest.main()
