"""The app icon ships every size the shell asks for, with the small cut intact.

## Why an icon has a test

`src-tauri/tauri.conf.json` lists the icon files under `bundle.icon`, and the
window, the taskbar, the installer and the tray all resolve from there. A file
listed there and missing from disk is a build that fails late; a `.ico` that
quietly lost its 16px entry is a taskbar that renders a shrunk 256 and looks
like a smudge. Neither shows up in any other test.

## The one that matters

`scripts/make_icon.py` draws TWO cuts - detailed at 256/128/64, simplified at
48/32/16 - because detail that cannot be resolved at 16px reads as mud rather
than as detail, and because a dark tile disappears into a dark taskbar. A `.ico`
can carry different artwork per size, and Pillow only does that when it is
handed the frames explicitly. **Regenerating with a single image would silently
produce six scaled copies of the same drawing** - every size still present,
every assertion about presence still passing, and the small-size work gone. So
this asserts the artwork actually DIFFERS between the cuts, which is the thing
that would be lost.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

ICONS = REPO / "src-tauri" / "icons"
CONFIG = REPO / "src-tauri" / "tauri.conf.json"


class TheConfiguredIconsExistTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = json.loads(CONFIG.read_text(encoding="utf-8"))

    def test_every_file_bundle_icon_names_is_on_disk(self):
        for relative in self.config["bundle"]["icon"]:
            path = REPO / "src-tauri" / relative
            self.assertTrue(path.is_file(),
                            "tauri.conf.json lists " + relative + " and it is "
                            "not there, so the bundle fails at build time "
                            "rather than here.")

    def test_the_product_name_is_the_one_the_window_shows(self):
        self.assertEqual(self.config["productName"], "ML Harness")
        self.assertEqual(self.config["app"]["windows"][0]["title"], "ML Harness")


class TheIcoCarriesEverySizeTest(unittest.TestCase):
    #: 24 included: the generator this replaced listed it as one of "the
    #: sizes Windows actually loads", and the replacement dropped it.
    #: 30 and 36 joined on 2026-09-13: they are what the taskbar asks for at
    #: 125% and 150% display scaling, and a missing entry means Windows scales
    #: the 32 into the slot, which is the softness the owner pointed at.
    WANTED = [(16, 16), (24, 24), (30, 30), (32, 32), (36, 36), (48, 48),
              (64, 64), (128, 128), (256, 256)]

    def setUp(self) -> None:
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            self.skipTest("Pillow is not installed in this interpreter")

    def test_all_six_sizes_are_present(self):
        from PIL import Image
        with Image.open(ICONS / "icon.ico") as ico:
            self.assertEqual(sorted(ico.ico.sizes()), sorted(self.WANTED),
                             "a size went missing from the .ico, so Windows "
                             "will scale a neighbour into that slot.")

    def test_the_small_cut_is_not_just_the_large_one_shrunk(self):
        """THE ASSERTION THAT PROTECTS THE WORK, rather than the file's presence.

        Both cuts are legible; that cannot be asserted mechanically. What can be
        is that they are DIFFERENT drawings - the simplified tile is lighter, so
        its silhouette survives on a dark taskbar. If a regenerate ever produces
        six scaled copies of one image, every other assertion here still passes
        and only this one fails.
        """
        from PIL import Image

        def frame(size):
            with Image.open(ICONS / "icon.ico") as im:
                im.size = (size, size)
                return im.convert("RGBA").resize((64, 64), Image.NEAREST).tobytes()

        small, large = frame(16), frame(256)
        differing = sum(1 for a, b in zip(small, large) if a != b) / 4
        self.assertGreater(
            differing, 64 * 64 * 0.25,
            "the 16px and 256px frames are nearly the same drawing, so the "
            "simplified cut was lost and the small sizes are a shrunk 256.")

    def _ink(self, size: int):
        """Every pixel of the mark itself at one size: its coverage of the
        frame, and how bright it is. Alpha over half is the mark; the rest is
        the frame it sits in."""
        from PIL import Image

        with Image.open(ICONS / "icon.ico") as im:
            im.size = (size, size)
            pixels = list(im.convert("RGBA").getdata())
        ink = [p for p in pixels if p[3] > 128]
        luma = [(p[0] * 299 + p[1] * 587 + p[2] * 114) // 1000 for p in ink]
        return len(ink) / len(pixels), sum(luma) / max(1, len(luma))

    def test_the_mark_is_bright_enough_to_have_a_silhouette_on_a_dark_taskbar(self):
        """THE PROPERTY THE SMALL CUT EXISTS FOR, restated for a mark with no
        tile behind it.

        This read one pixel at (50%, 14%) and asserted the small frame was
        LIGHTER there than the large one. That was the right check for the
        gauge, whose drawing was a dark squircle tile: the sampled point was
        tile, and lightening it at 16px was how the icon kept an edge against a
        dark taskbar.

        The cleave has no tile. It is a stone on transparency, so that point is
        now inside the cap and the comparison measures facet shading rather
        than a silhouette - which is why it went red on a mark that is in fact
        perfectly legible. The property itself did not change, so it is stated
        against what carries it now: the mark's own ink, against the darkest
        ground it will ever sit on. `--bg-ground` is #1F1F1D, luma 31.
        MEASURED 2026-09-14: 118 at 16px, and every size within 7 of that.
        """
        _, luma = self._ink(16)
        self.assertGreater(
            luma, 90,
            "the mark's ink is too dark to separate from a #1F1F1D taskbar at "
            "16px, so the icon reads as a smudge rather than an application.")

    def test_the_mark_keeps_its_mass_when_it_is_simplified(self):
        """A tile always filled its frame; a stone can quietly shrink to a
        speck, and the simplified cut is exactly where that would happen -
        widening the parting and rounding the joins eats area. MEASURED
        2026-09-14: 29.3% to 30.9% across all nine sizes, both cuts.
        """
        cover = {size: self._ink(size)[0] for size in (16, 24, 32, 48, 128, 256)}
        for size, share in cover.items():
            self.assertGreater(share, 0.20, f"the mark is a speck at {size}px")
            self.assertLess(share, 0.60, f"the mark has no frame at {size}px")
        spread = max(cover.values()) - min(cover.values())
        self.assertLess(
            spread, 0.06,
            f"the mark's mass moves by {spread:.1%} between sizes, so the "
            "simplified cut is not the same object as the detailed one.")


class TheGeneratorIsTheSourceTest(unittest.TestCase):
    """An icon that arrives as four binaries is an icon nobody can change."""

    def test_the_script_that_draws_them_is_in_the_tree(self):
        self.assertTrue((REPO / "scripts" / "make_icon.py").is_file(),
                        "the icon lost its source, so the next change to it "
                        "has to be made in a raster editor by eye.")


if __name__ == "__main__":
    unittest.main()
