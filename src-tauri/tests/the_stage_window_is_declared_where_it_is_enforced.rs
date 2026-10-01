//! The detached Stage window: one label, in three files, that must agree.
//!
//! ## The failure this exists to prevent
//!
//! `open_stage` builds a second window labelled `stage`. Tauri's capability
//! system is per-LABEL: `capabilities/default.json` lists which windows may
//! invoke which commands, and its own description says "the list is the
//! enforcement rather than a convention". A window whose label is not in that
//! list gets a webview that can call nothing — `engine_status` fails, the page
//! cannot resolve a session, and the Stage renders "could not read this
//! thread" with no clue that a JSON file three directories away is the reason.
//!
//! The same label is written in three places: the builder in `lib.rs`, the
//! `get_webview_window` lookups that re-point and close it, and the capability.
//! And the URL it loads carries `?stage=<thread>`, which `frontend/src/main.tsx`
//! reads to decide whether to render the instruments or the chat — a fourth
//! place, in another language, keyed on the same string.
//!
//! None of that is checkable by running the app in CI, because there is no
//! display. It is checkable by reading, and that is what this does.
//!
//! ## What this does NOT prove
//!
//! That the window opens, that it follows the thread, or that it folds into
//! the transcript row when the run finishes. Those need a real display and a
//! real run; `docs/PHASES.md` step S8 carries them as owed, and this test is
//! the half that can be known without one.

use std::path::PathBuf;

const LABEL: &str = "stage";

fn read(relative: &str) -> String {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(relative);
    std::fs::read_to_string(&path)
        .unwrap_or_else(|error| panic!("could not read {}: {error}", path.display()))
}

#[test]
fn the_capability_lists_the_window_the_shell_builds() {
    let capability = read("capabilities/default.json");
    let parsed: serde_json::Value =
        serde_json::from_str(&capability).expect("capabilities/default.json is not JSON");
    let windows = parsed["windows"]
        .as_array()
        .expect("the capability declares no windows");
    let labels: Vec<&str> = windows.iter().filter_map(|w| w.as_str()).collect();

    assert!(
        labels.contains(&"main"),
        "the main window lost its capability: {labels:?}"
    );
    assert!(
        labels.contains(&LABEL),
        "the Stage window is built with label {LABEL:?} and the capability does not list it, \
         so its webview could invoke nothing: {labels:?}"
    );
}

#[test]
fn the_shell_builds_and_finds_the_window_under_one_label() {
    let source = read("src/lib.rs");

    assert!(
        source.contains(&format!("WebviewWindowBuilder::new(&app, \"{LABEL}\"")),
        "no window is built under the label the capability grants"
    );
    // Re-pointing and closing both look the window up by the same string. A
    // lookup under a different label silently does nothing, which reads as
    // "the window did not close" rather than as a typo.
    assert_eq!(
        source
            .matches(&format!("get_webview_window(\"{LABEL}\")"))
            .count(),
        2,
        "open_stage re-points and close_stage destroys; both look the window up by label"
    );
    for command in ["fn open_stage", "fn close_stage"] {
        assert!(source.contains(command), "{command} is not defined");
    }
    for registered in ["open_stage,", "close_stage"] {
        assert!(
            source.contains(registered),
            "{registered} is defined and never registered in generate_handler!, so the page \
             calling it gets 'command not found'"
        );
    }
}

#[test]
fn the_url_it_loads_is_the_one_the_page_routes_on() {
    let source = read("src/lib.rs");
    assert!(
        source.contains("index.html?stage={thread_id}"),
        "the Stage window must load the app's own page with the thread in the query string"
    );

    // The other end of that contract, in TypeScript: main.tsx reads the same
    // parameter to decide which surface to render.
    let main_tsx = read("../frontend/src/main.tsx");
    assert!(
        main_tsx.contains("get('stage')") || main_tsx.contains("get(\"stage\")"),
        "frontend/src/main.tsx does not read ?stage=, so the window would render the chat"
    );
    assert!(
        main_tsx.contains("StageWindow"),
        "main.tsx reads ?stage= and renders no StageWindow"
    );
}
