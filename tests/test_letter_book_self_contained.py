"""Letter must paint as a book even when opened as a lone file.

Opening a-letter.html without its sibling _book.css used to yield Times New
Roman on white, two 300×150 empty SVGs where the page arrows sit, and every
page dumped as bunched blue links. That is the screenshot the owner sent.
The chassis CSS and the icon sprite now live inside the HTML.
"""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / "docs" / "brand" / "elegant"
LETTER = ROOT / "a-letter.html"


#: A document read for prose, with its line breaks flattened. A phrase that
#: reads as one sentence can sit across two lines in the file, and a plain
#: substring search then reports it absent - which is how a check accused
#: docs/how-to-verify.md of not naming the product's claim when it did.
def _flat(text: str) -> str:
    return " ".join(text.split())


class LetterBookSelfContainedTest(unittest.TestCase):
    def setUp(self):
        self.html = LETTER.read_text(encoding="utf-8")

    def test_chassis_css_is_inside_the_file(self):
        self.assertNotIn('href="_book.css"', self.html)
        self.assertIn('id="book-chassis"', self.html)
        self.assertIn("--ground: #0F0F0F", self.html)
        self.assertIn("--indigo: #8B8AF6", self.html)

    def test_shell_script_and_icon_sprite_are_inside_the_file(self):
        self.assertNotIn('src="_book.js"', self.html)
        self.assertIn('id="book-shell"', self.html)
        self.assertIn('id="ic-send"', self.html)
        self.assertIn('id="ic-arrowleft"', self.html)

    def test_indigo_solid_is_the_app_fill_not_a_new_claim(self):
        self.assertIn("--indigo-solid: #6C63E0", self.html)
        self.assertIn("--indigo: #8B8AF6", self.html)
        self.assertIn("white on indigo #8B8AF6", self.html)
        self.assertIn("2.97", self.html)

    def test_the_surfaces_the_owner_could_not_see_are_in_the_markup(self):
        self.assertIn('class="composer"', self.html)
        self.assertIn("Ask the harness anything", self.html)
        self.assertIn('class="card"', self.html)
        self.assertIn('class="toolrow"', self.html)
        self.assertIn("inspect_hardware", self.html)

    def test_it_is_marked_as_a_draft_and_not_the_source_of_truth(self):
        self.assertIn('class="draftbar"', self.html)
        self.assertIn("Graphite remains the source of truth", self.html)
        cover = self.html.split('id="p01"', 1)[1].split("</section>", 1)[0]
        self.assertNotIn('width="96"', cover)
        self.assertIn("wordmark carve", cover)

    def test_composer_is_squared_and_send_stays_a_circle(self):
        self.assertIn("--r-composer: 10px", self.html)
        self.assertIn("border-radius: 50%", self.html)

    def test_the_confirmation_copy_lives_under_drafts(self):
        drafts = Path(__file__).resolve().parents[1] / "docs" / "brand" / "drafts"
        self.assertTrue((drafts / "README.md").exists())
        # THE WORLD TURNED ON 2026-08-29: the owner ordered Letter implemented
        # in full, so the drafts folder now records a CONFIRMED direction
        # rather than a pending one, and this asserts the record says so.
        readme = (drafts / "README.md").read_text(encoding="utf-8")
        self.assertIn("Letter is confirmed and implemented", _flat(readme))
        self.assertIn("2026-08-29", readme)
        parked = drafts / "letter.html"
        self.assertTrue(parked.exists(), "run pack.py so letter.html is parked")
        parked_html = parked.read_text(encoding="utf-8")
        self.assertIn('id="book-chassis"', parked_html)
        self.assertIn('class="draftbar"', parked_html)
        ds = (Path(__file__).resolve().parents[1] / "docs" / "DESIGN_SYSTEM.md").read_text(encoding="utf-8")
        self.assertIn("Direction A — Letter", _flat(ds))
        self.assertIn("LETTER IS NOW THE IMPLEMENTED", _flat(ds))
