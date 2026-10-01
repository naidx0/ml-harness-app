"""A shell command that builds a window is `async`, or the window is white.

Max, 2026-09-11, with a screenshot: *"when looking at the pop out it loads
this white thing which i dont like, and in reality it doesnt load at all."*
A 560x760 shadowed rectangle, nothing painted, not an error page.

THE ROUTE WAS FINE. `?pane=plan&thread=64` rendered in a browser against the
dev server, with the title set and no console error. The URL was fine: tauri
2.11.5 joins `index.html?pane=...` onto the app origin and its protocol
handler strips the query before serving the file (read in the crate's own
`manager/webview.rs` and `protocol/tauri.rs`). The capability was fine:
`pane-*` was in the installed build's window list. What was wrong is written
on the builder Tauri ships: *"On Windows, this function deadlocks when used
in a synchronous command and event handlers... You should use `async`
commands and separate threads when creating windows."* A synchronous command
runs on the main thread; WebView2 initialises by pumping that thread's
message loop; so the Win32 window appeared and the webview in it never did.

This reads `src-tauri/src/lib.rs` as text because there is no Rust in the
gate, and the property is one a reader can check by eye: every command whose
body reaches for `WebviewWindowBuilder` is declared `async fn`. Two exits,
and each has a case that produces only it: a builder inside a synchronous
command fails the first test; a window-opening command that has gone missing
fails the second.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / "src-tauri" / "src" / "lib.rs"

#: `#[tauri::command]` then the signature it decorates, on the next line.
COMMAND = re.compile(r"#\[tauri::command\]\s*\n\s*(async\s+)?fn\s+([A-Za-z_][A-Za-z0-9_]*)")

#: The commands that open a window. A new one joins this list when it is
#: written, and the first test catches it whether or not anybody remembers.
OPENS_A_WINDOW = ("open_stage", "open_pane")


def commands(source: str) -> list[tuple[str, bool, str]]:
    """Every `(name, is_async, body)` for a `#[tauri::command]` in the file.

    The body runs to the next command attribute or to `pub fn run`, which is
    where the commands end and the builder begins - a coarse cut, and enough:
    the property is about what a command's text mentions, not about scope.
    """
    found = list(COMMAND.finditer(source))
    stop = source.find("pub fn run()")
    out = []
    for at, match in enumerate(found):
        end = found[at + 1].start() if at + 1 < len(found) else stop
        out.append((match.group(2), bool(match.group(1)), source[match.start() : end]))
    return out


class AWindowIsBuiltFromAnAsyncCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = LIB.read_text(encoding="utf-8")
        self.commands = commands(self.source)
        self.assertTrue(self.commands, f"no #[tauri::command] found in {LIB}")

    def test_no_synchronous_command_builds_a_window(self):
        """The property, for every command there is or will be."""
        offenders = [
            name
            for name, is_async, body in self.commands
            if "WebviewWindowBuilder" in body and not is_async
        ]
        self.assertEqual(
            offenders,
            [],
            "these commands build a window from a synchronous command, which on "
            "Windows is the white rectangle Max photographed on 2026-09-11: "
            + ", ".join(offenders),
        )

    def test_the_window_openers_are_there_and_async(self):
        """The two commands the page calls, by name, so a rename that dropped
        one out of the first test's reach still fails here."""
        by_name = {name: is_async for name, is_async, _ in self.commands}
        for name in OPENS_A_WINDOW:
            self.assertIn(name, by_name, f"{name} is no longer a #[tauri::command]")
            self.assertTrue(by_name[name], f"{name} is not `async fn`")

    def test_the_reader_sees_a_synchronous_builder(self):
        """The instrument, checked against a specimen it owns: a sync command
        with a builder in it reads as sync, so the first test CAN go red."""
        specimen = (
            "#[tauri::command]\n"
            "fn opens(app: tauri::AppHandle) -> Result<(), String> {\n"
            "    tauri::WebviewWindowBuilder::new(&app, \"x\", tauri::WebviewUrl::App(\"index.html\".into()))\n"
            "        .build().map_err(|e| e.to_string())?;\n"
            "    Ok(())\n"
            "}\n"
            "#[tauri::command]\n"
            "async fn fine(app: tauri::AppHandle) -> Result<(), String> { Ok(()) }\n"
            "pub fn run() {}\n"
        )
        got = [(name, is_async, "WebviewWindowBuilder" in body) for name, is_async, body in commands(specimen)]
        self.assertEqual(got, [("opens", False, True), ("fine", True, False)])


if __name__ == "__main__":
    unittest.main()
