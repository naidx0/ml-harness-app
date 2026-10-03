//! The desktop shell: two commands, and nothing else.
//!
//! `docs/THE_PLAN.md` Phase B. `docs/ARCHITECTURE.md` §4.1 named three Rust
//! commands; V.2 drops `secret_get`/`secret_set` for three measured reasons —
//! the key never returns to the frontend today (`/api/providers` answers
//! `has_key`, a boolean), the consumer is the ENGINE, which cannot call the
//! shell that spawned it, and both paths land in the same DPAPI store anyway.
//!
//! So there are two, and the frontend already asks for exactly these by name:
//! `frontend/src/lib/engine/shell.ts` declares the command names, the argument
//! shapes and the return payloads, with tests driving a fake `invoke` against
//! them. This file is the other half of a contract that was written first.
//!
//! ## `engine_status` reads a file; it does not start anything
//!
//! V.1: *"the Tauri shell is a local process, not a browser: it reads
//! `engine.json` off disk exactly as the launcher does, and returns the same
//! `{base_url, token, engine, checkout}` shape `vite.config.ts` already serves.
//! **A direct swap, not a new mechanism.**"*
//!
//! It is a READ, and that is the whole security argument for handing a token to
//! a WebView at all: the file is already user-only on disk, the shell is already
//! running as that user, and nothing here mints, stores or transmits a secret
//! that was not already sitting in the user's own home directory.
//!
//! **It deliberately does not start the engine.** Starting processes is
//! `scripts/launch.py`'s job and it has thirty tests behind it; a second, less
//! careful implementation in Rust would be exactly the "second place that goes
//! stale" this repository refuses everywhere else. A window that finds no
//! engine says so — `frontend/src/lib/engine/config.ts` already renders that
//! state, because it is the state a dev server produces too.
//!
//! ## `pick_path` is the one thing a browser genuinely cannot do
//!
//! `Composer.tsx` says so in its own words: *"there is not going to be one
//! before Tauri: both hand back a `File` object, and every data tool in this
//! product takes a PATH on this machine, which a web page is not allowed to
//! learn."* This is that. Cancelling returns `None`, which the frontend treats
//! identically to "no shell" — leave the field alone and let them type.

pub mod carrier;
pub mod engine;

use std::path::PathBuf;

use serde::Serialize;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{Manager, WindowEvent};
use tauri_plugin_dialog::DialogExt;

/// The port the engine binds. `app/config.py` says why it is not configurable
/// there; this is the shell's copy of that one number and it is the only thing
/// duplicated from it.
const ENGINE_PORT: u16 = 8078;

/// What `engine_status` answers with.
///
/// Deliberately the shape the dev server's `/__engine/session` route already
/// returns, so `config.ts` reads ONE payload and not two. Two shapes would be
/// two opinions about what a session is, and the one that drifted would drift
/// in the packaged build — the one nobody runs while developing.
#[derive(Debug, Default, Serialize)]
pub struct EngineStatus {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub base_url: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub token: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub engine: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub checkout: Option<serde_json::Value>,
}

impl EngineStatus {
    fn error(reason: impl Into<String>) -> Self {
        Self {
            error: Some(reason.into()),
            ..Default::default()
        }
    }
}

/// Where the engine publishes itself.
///
/// THE SAME THREE PLACES `app/paths.py` DECIDES BETWEEN, in the same order and
/// for the same reasons — the environment override first because somebody who
/// named a path said something more specific than anything else knows; then the
/// per-user data root, which is where an INSTALLED engine writes; then the
/// repository, because a developer running from a checkout has it there and
/// `paths.data_root()` keeps it there rather than orphaning their database.
///
/// It is duplicated in Rust rather than shelled out to Python on purpose: the
/// shell has to answer this before it knows whether there is a Python to ask.
/// The duplication is three paths and a rule, and it is the smallest thing this
/// file could copy; anything more and the Python would have to be the source.
fn portfile_candidates() -> Vec<PathBuf> {
    let mut found = Vec::new();

    if let Ok(named) = std::env::var("MLH_ENGINE_FILE") {
        if !named.trim().is_empty() {
            found.push(PathBuf::from(named));
        }
    }

    if let Ok(root) = std::env::var("MLH_DATA_ROOT") {
        if !root.trim().is_empty() {
            found.push(PathBuf::from(root).join("engine.json"));
        }
    }

    // The installed data root on this platform: LOCALAPPDATA on Windows,
    // ~/.local/share on a Mac. Reading LOCALAPPDATA alone left a Mac app
    // unable to find its own engine (engine::installed_data_root).
    if let Some(root) = engine::installed_data_root() {
        found.push(root.join("engine.json"));
    }

    // The checkout, when this is running out of one. `src-tauri/` sits beside
    // `frontend/` at the repository root, so the parent of the manifest
    // directory is that root - the same marker `paths._checkout` decides by.
    let here = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    if let Some(repository) = here.parent() {
        if repository
            .join("docs")
            .join("diagnosis_engine.yaml")
            .is_file()
        {
            found.push(repository.join("engine.json"));
        }
    }

    found
}

/// Where the engine is, read off disk. Never starts anything.
#[tauri::command]
fn engine_status() -> EngineStatus {
    let candidates = portfile_candidates();
    for path in &candidates {
        let Ok(text) = std::fs::read_to_string(path) else {
            continue;
        };
        let parsed: serde_json::Value = match serde_json::from_str(&text) {
            Ok(value) => value,
            Err(error) => {
                // A portfile that is there and unreadable is a DIFFERENT answer
                // from one that is absent, and saying which is the difference
                // between "start the engine" and "something wrote nonsense into
                // your engine.json".
                return EngineStatus::error(format!(
                    "{} is not readable as JSON: {error}",
                    path.display()
                ));
            }
        };

        let text_at = |key: &str| {
            parsed
                .get(key)
                .and_then(|value| value.as_str())
                .map(str::to_owned)
        };

        // A PORTFILE IS NOT AN ENGINE, and believing one that is was a real
        // defect measured on 2026-08-28: a packaged shell read an engine.json
        // left behind by an engine that had died, reported a live session to
        // the page, and so the page never asked it to START one. Every request
        // then went to a dead port, the 47 MB sidecar beside the binary did
        // nothing, and the first-run bootstrap could not fire on any machine
        // where an engine had ever stopped without cleaning up after itself -
        // which is every machine, because a killed process cleans up nothing.
        //
        // `ours_is_answering` is the same narrow question the bootstrap asks
        // and it is asked here for the same reason: this is still a READ plus
        // one loopback GET, it starts nothing, and it replaces a claim with a
        // measurement. The file is NOT deleted - it may belong to somebody
        // else's engine that is merely slow to start, and a shell that tidied
        // away other people's files would be the same overreach as killing a
        // process it did not spawn.
        let port = parsed
            .get("port")
            .and_then(|value| value.as_u64())
            .and_then(|value| u16::try_from(value).ok());
        if let Some(port) = port {
            if !engine::ours_is_answering(port) {
                return EngineStatus::error(format!(
                    "{} names an engine on port {port} and nothing is answering there. It is a portfile left behind by an engine that stopped; the engine it describes is gone.",
                    path.display()
                ));
            }
        }

        return EngineStatus {
            base_url: text_at("base_url"),
            token: text_at("token"),
            error: None,
            // THE WHOLE PORTFILE MINUS THE TOKEN, which is the shape the dev
            // server's `/__engine/session` has always sent. This sent
            // `parsed["engine"]` - the nested block alone, `{engine_id, pid,
            // launch_nonce, started_at, uptime_seconds}` - and `build` never
            // reached the page at all.
            //
            // What that cost: `revisionIn` looks up `build.sha` by name, missed
            // it every time, fell through to scanning values for anything
            // revision-shaped, and found `engine_id` - 32 hex characters from
            // `secrets.token_hex(16)`, fresh on every start. So the page
            // compared a random per-process id against a git commit and
            // reported the engine stale, always, and a restart could only
            // produce a different random id. Max pressed Restart the engine ten
            // times and watched the revision change from c467f06b to ba572ca
            // while the banner stayed.
            //
            // The comment forty lines above this one names the hazard exactly:
            // two opinions about what a session is, and the one that drifted
            // would drift in the packaged build, the one nobody runs while
            // developing. It did. One shape now, and a test that compares them.
            engine: parsed
                .as_object()
                .map(|fields| {
                    let mut out = fields.clone();
                    out.remove("token");
                    serde_json::Value::Object(out)
                })
                .or_else(|| parsed.get("engine").cloned()),
            checkout: parsed.get("checkout").cloned(),
        };
    }

    EngineStatus::error(format!(
        "no engine.json in any of {}. Start the engine and reload.",
        candidates
            .iter()
            .map(|path| path.display().to_string())
            .collect::<Vec<_>>()
            .join(", ")
    ))
}

/// A real path on this machine, or `None` when the person cancelled.
///
/// `kind` is a closed set on the frontend side and matched exhaustively here:
/// anything else falls to the file picker rather than silently doing nothing,
/// because a button that opens no dialog is the worst of the three outcomes.
#[tauri::command]
async fn pick_path(app: tauri::AppHandle, kind: String) -> Option<String> {
    let dialog = app.dialog().clone();
    let chosen = if kind == "directory" {
        dialog.file().blocking_pick_folder()
    } else {
        dialog.file().blocking_pick_file()
    };
    chosen
        .and_then(|path| path.into_path().ok())
        .map(|path| path.display().to_string())
}

/// Start the engine if nobody else has. Reported, never silent.
///
/// A COMMAND RATHER THAN SOMETHING THAT HAPPENS AT STARTUP, and the difference
/// is what the person sees. A shell that spawned a process before the window
/// existed would either block the window on a sixty-second wait or start
/// something the page has no way to describe. This way `config.ts` asks for a
/// session, gets "no engine", and the page can say what it is about to do
/// before it does it.
#[tauri::command]
async fn start_engine() -> engine::Bootstrap {
    tauri::async_runtime::spawn_blocking(|| engine::bootstrap(ENGINE_PORT))
        .await
        .unwrap_or(engine::Bootstrap {
            started: false,
            already_running: false,
            interpreter: None,
            detail: "the bootstrap task did not finish".into(),
        })
}

/// Replace the engine that is answering, whoever started it.
///
/// `start_engine` refuses when one is already up, which is right for a start
/// and useless for the case the window can actually see: an engine on older
/// code than the page. This reads the same `engine.json` the status command
/// does, asks that engine to exit using its own published token, and then
/// bootstraps a new one. See `engine::restart`.
#[tauri::command]
async fn restart_engine() -> engine::Bootstrap {
    let status = tauri::async_runtime::spawn_blocking(|| engine_status())
        .await
        .unwrap_or_else(|_| EngineStatus::error("could not read engine.json"));
    let base = status
        .base_url
        .clone()
        .unwrap_or_else(|| format!("http://127.0.0.1:{ENGINE_PORT}"));
    let token = status.token.clone();
    tauri::async_runtime::spawn_blocking(move || {
        engine::restart(ENGINE_PORT, &base, token.as_deref())
    })
    .await
    .unwrap_or(engine::Bootstrap {
        started: false,
        already_running: false,
        interpreter: None,
        detail: "the restart task did not finish".into(),
    })
}

/// The page's wire to the engine - see `engine::engine_request` for why the
/// browser's networking is not part of this product's failure modes anymore.
#[derive(Debug, Serialize)]
pub struct CarriedResponse {
    pub status: u16,
    pub body: String,
}

#[tauri::command]
async fn engine_fetch(
    url: String,
    method: String,
    token: Option<String>,
    body: Option<String>,
) -> Result<CarriedResponse, String> {
    tauri::async_runtime::spawn_blocking(move || {
        engine::engine_request(&url, &method, token.as_deref(), body.as_deref())
            .map(|(status, body)| CarriedResponse { status, body })
    })
    .await
    .map_err(|error| error.to_string())?
}

/// The page's streaming wire to the engine - see `carrier.rs`. Frames go out on
/// the channel as they are read, so a live event stream is live in the window.
#[tauri::command]
async fn engine_stream(
    id: u32,
    url: String,
    method: String,
    headers: Vec<(String, String)>,
    body: Option<String>,
    on_frame: tauri::ipc::Channel<carrier::Frame>,
) {
    let _ = tauri::async_runtime::spawn_blocking(move || {
        let bytes = body.unwrap_or_default().into_bytes();
        carrier::carry(id, &url, &method, &headers, &bytes, |frame| {
            let _ = on_frame.send(frame);
        });
    })
    .await;
}

/// Stop a carried stream: the page aborted the request it belongs to.
#[tauri::command]
fn engine_stream_cancel(id: u32) {
    carrier::cancel(id);
}

/// The window controls, as commands. The native title bar is gone - the app
/// owns its whole frame, Claude-desktop style, so minimize/maximize/close
/// become three quiet buttons in the app's own top strip. Commands rather
/// than the JS window API: three verbs need no permission surface beyond
/// invoke, and the close path MUST run through the same CloseRequested logic
/// as the native box (hide to tray), which `window.close()` from JS honors.
#[tauri::command]
fn window_minimize(window: tauri::WebviewWindow) {
    let _ = window.minimize();
}

#[tauri::command]
fn window_toggle_maximize(window: tauri::WebviewWindow) {
    if window.is_maximized().unwrap_or(false) {
        let _ = window.unmaximize();
    } else {
        let _ = window.maximize();
    }
}

#[tauri::command]
fn window_close(window: tauri::WebviewWindow) {
    // The same door as the native close box: CloseRequested fires, the
    // handler hides to tray, and the engine keeps training.
    let _ = window.close();
}

/// The detached instrument window — docs/PHASES.md, "The Stage", size C.
///
/// One window, labelled `stage`, at the app's own page with `?stage=<thread>`
/// so the bundle decides in `main.tsx` to render the instruments and not the
/// chat. Opening it for a second thread re-points the one window rather than
/// stacking another: two instrument windows for two threads is two places to
/// look, and the shell's calm depends on there being one. It carries no chat
/// box — the conversation is the driver, in the main window.
///
/// ## ASYNC, AND THAT IS THE WHOLE OF A BUG
///
/// Max, 2026-09-11, with a screenshot of a 560×760 window that was pure
/// white: *"when looking at the pop out it loads this white thing which i
/// dont like, and in reality it doesnt load at all."* The route rendered
/// in a browser; the URL joined and served correctly (read in tauri
/// 2.11.5's `manager/webview.rs` and `protocol/tauri.rs`); the capability
/// covered the label. What was wrong is documented on the builder itself:
/// *"On Windows, this function deadlocks when used in a synchronous command
/// and event handlers... You should use `async` commands and separate
/// threads when creating windows."* A synchronous command runs ON the main
/// thread, and WebView2 needs that thread's message loop pumped to
/// initialise - so the Win32 window appeared and the webview inside it
/// never did. Both window-opening commands are `async` for that reason,
/// and `tests/test_a_window_is_opened_off_the_main_thread.py` holds them
/// there.
#[tauri::command]
async fn open_stage(app: tauri::AppHandle, thread_id: i64) -> Result<(), String> {
    let url = format!("index.html?stage={thread_id}");
    // Re-pointing is a rebuild: the page decides which thread it follows from
    // its own query string at load, so a new thread is a new load. One label,
    // so there is never more than one.
    if let Some(existing) = app.get_webview_window("stage") {
        existing.destroy().map_err(|error| error.to_string())?;
    }
    tauri::WebviewWindowBuilder::new(&app, "stage", tauri::WebviewUrl::App(url.into()))
        .title(format!("Instruments · thread {thread_id}"))
        .inner_size(1280.0, 800.0)
        .min_inner_size(720.0, 480.0)
        .decorations(false)
        .shadow(true)
        .build()
        .map_err(|error| error.to_string())?;
    Ok(())
}

/// Open ONE pane in its own window, bound to the thread it was opened from.
///
/// Max, describing what he wants the shell to do: *"I want a lot of the
/// windows to pop out as well... especially in a stage environment when you
/// have evals and benches and sandboxes running... And same for the markdown
/// plans. When you switch chats, it doesn't close, but that one relates to
/// the chat it was open from. That way it doesn't mess up between different
/// chat switches."*
///
/// ## WHY THE LABEL CARRIES THE THREAD
///
/// `open_stage` uses the single label `stage` and DESTROYS the existing
/// window when it is re-pointed, which is the right behaviour for one
/// instrument that follows the conversation you are looking at. It is the
/// wrong behaviour for what is asked for here: a window per pane per thread,
/// so a plan opened from thread 12 is still thread 12's plan after you have
/// moved to thread 19, and opening thread 19's plan gives you a second
/// window rather than stealing the first.
///
/// A window that already exists is FOCUSED, never rebuilt. Rebuilding would
/// throw away an unsaved edit in a plan the person is in the middle of.
///
/// ## THE LABEL IS SANITISED, and that is not paranoia
///
/// A Tauri label is an identifier, and `pane` arrives from the page. Only
/// letters, digits, `-` and `_` survive; anything else is dropped, and an
/// empty result is refused rather than silently opening a window called
/// `pane--12`. The frontend passes a `PaneId`, so in practice nothing is
/// ever stripped - this is about what the command GUARANTEES, not about
/// what today's caller happens to send.
///
/// `async` for the reason `open_stage` gives: a window built from a
/// synchronous command on Windows is a white rectangle.
#[tauri::command]
async fn open_pane(app: tauri::AppHandle, pane: String, thread_id: i64) -> Result<(), String> {
    let safe: String = pane
        .chars()
        .filter(|c| c.is_ascii_alphanumeric() || *c == '-' || *c == '_')
        .collect();
    if safe.is_empty() {
        return Err(format!("{pane:?} is not a pane name this shell can open"));
    }

    let label = format!("pane-{safe}-{thread_id}");
    if let Some(existing) = app.get_webview_window(&label) {
        let _ = existing.unminimize();
        existing.set_focus().map_err(|error| error.to_string())?;
        return Ok(());
    }

    let url = format!("index.html?pane={safe}&thread={thread_id}");
    tauri::WebviewWindowBuilder::new(&app, &label, tauri::WebviewUrl::App(url.into()))
        .title(format!("{safe} · thread {thread_id}"))
        // Wide enough for the rail AND a pane at the inspector's own width,
        // and for the Stage's split size (2026-09-12: every pane pops out).
        .inner_size(920.0, 760.0)
        .min_inner_size(480.0, 360.0)
        .decorations(false)
        .shadow(true)
        .build()
        .map_err(|error| error.to_string())?;
    Ok(())
}

/// Close the instrument window, if there is one. Called when the run it was
/// following finishes and its content has folded into the transcript row —
/// never two records of one thing.
#[tauri::command]
fn close_stage(app: tauri::AppHandle) {
    if let Some(existing) = app.get_webview_window("stage") {
        let _ = existing.destroy();
    }
}

/// Does closing this window hide it to the tray, or really close it?
///
/// One window is the application and the rest are views of it. The app's
/// window hides, because the engine is designed to outlive it and a close box
/// that killed a six-hour training run would make the most expensive thing
/// this product does the easiest thing to lose. A view has nothing to lose,
/// and the tray restores `main` alone - a hidden view would be a window that
/// exists, cannot be seen, and cannot be got back.
pub(crate) fn hides_to_tray(label: &str) -> bool {
    label == "main"
}

#[cfg(test)]
mod which_windows_hide {
    use super::hides_to_tray;

    #[test]
    fn the_app_window_hides_and_a_view_closes() {
        assert!(
            hides_to_tray("main"),
            "the engine must outlive the app window"
        );
        assert!(
            !hides_to_tray("stage"),
            "the Stage window is a view: hiding it leaves a window nothing can restore, \
             because the tray menu shows `main` alone"
        );
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            engine_status,
            pick_path,
            start_engine,
            restart_engine,
            engine_fetch,
            engine_stream,
            engine_stream_cancel,
            window_minimize,
            window_toggle_maximize,
            window_close,
            open_stage,
            open_pane,
            close_stage
        ])
        .on_window_event(|window, event| {
            // `prevent_close` + hide, and THE_PLAN says why in five words: the
            // engine is DESIGNED TO OUTLIVE THE WINDOW. A run started from this
            // window can be a training job measured in hours, and a close box
            // that killed it would make the most expensive thing this product
            // does the easiest thing to lose.
            //
            // Hiding rather than closing also keeps the token: `config.ts`
            // caches a session and the engine mints a fresh token on every
            // start, so a window that quit and relaunched the engine would log
            // out every tab that was open. That is a real symptom this product
            // has already had once.
            //
            // THAT ARGUMENT IS ABOUT THE APP'S WINDOW AND ONLY THAT ONE. The
            // Stage's detached window (docs/PHASES.md, "The Stage", size C) is
            // a VIEW of a thread, not the app: nothing is lost by closing it,
            // the engine never noticed it opened, and the tray menu restores
            // `main` alone - so hiding it would leave a window that exists,
            // cannot be seen, and cannot be got back. It closes for real.
            if let WindowEvent::CloseRequested { api, .. } = event {
                if hides_to_tray(window.label()) {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .setup(|app| {
            // THE WAY BACK, and it is what makes the hide above legitimate. A
            // window that hides with no tray is an application the person can
            // neither reach nor quit - so the two are built together or neither
            // is. "Quit" is a real quit: it is the one path that stops an engine
            // this window started.
            let show = MenuItem::with_id(app, "show", "Show ML Harness", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &quit])?;

            TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .tooltip("ML Harness - the engine keeps running while this is hidden")
                .menu(&menu)
                .show_menu_on_left_click(true)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show" => {
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                    "quit" => app.exit(0),
                    _ => {}
                })
                .build(app)?;

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("the shell could not start")
        .run(|_app, event| {
            // ONLY WHAT THIS WINDOW STARTED. A developer with an engine already
            // running from a terminal closes this and their engine is still
            // there - see `engine::stop_if_ours`, which is four lines and the
            // whole of the rule.
            if let tauri::RunEvent::ExitRequested { .. } = event {
                engine::stop_if_ours();
            }
        });
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Read, Write};
    use std::net::{TcpListener, TcpStream};

    /// A portfile, written where `MLH_ENGINE_FILE` points.
    fn portfile(directory: &std::path::Path, port: u16) -> PathBuf {
        let path = directory.join("engine.json");
        std::fs::write(
            &path,
            format!(
                r#"{{"host":"127.0.0.1","port":{port},
                   "base_url":"http://127.0.0.1:{port}",
                   "token":"a-token","service":"ml-harness-engine"}}"#
            ),
        )
        .unwrap();
        path
    }

    /// A port with nothing on it: bound, read back, then dropped.
    fn a_closed_port() -> u16 {
        let held = TcpListener::bind("127.0.0.1:0").unwrap();
        held.local_addr().unwrap().port()
    }

    /// Something that answers `/health` the way the engine does, once.
    ///
    /// IT DRAINS THE WHOLE REQUEST BEFORE ANSWERING, and that is not politeness.
    /// A first `read` returns as few as five bytes, and on Windows a socket
    /// closed with unread data still in its receive buffer sends RST rather
    /// than FIN - so the client's read fails with a reset and the response it
    /// was already sent is never seen. Cost an hour on 2026-08-28.
    fn an_engine_saying_it_is_ours() -> (u16, std::thread::JoinHandle<()>) {
        let listening = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listening.local_addr().unwrap().port();
        let serving = std::thread::spawn(move || {
            if let Ok((mut stream, _)) = listening.accept() {
                let mut request = Vec::new();
                let mut chunk = [0u8; 512];
                while !request.windows(4).any(|w| w == b"\r\n\r\n") {
                    match stream.read(&mut chunk) {
                        Ok(0) | Err(_) => break,
                        Ok(read) => request.extend_from_slice(&chunk[..read]),
                    }
                }
                let body = r#"{"service":"ml-harness-engine","status":"ok"}"#;
                let _ = stream.write_all(
                    format!(
                        "HTTP/1.0 200 OK\r\nContent-Length: {}\r\n\r\n{body}",
                        body.len()
                    )
                    .as_bytes(),
                );
                let _ = stream.flush();
            }
        });
        (port, serving)
    }

    /// THE DEFECT, BOTH WAYS ROUND, in one test because `MLH_ENGINE_FILE` is
    /// process-global and two tests setting it would race each other.
    ///
    /// Measured 2026-08-28: a packaged shell read an `engine.json` left behind
    /// by an engine that had died and reported a live session, so the page
    /// never asked it to start one and the sidecar beside the binary did
    /// nothing. A portfile is evidence that an engine once existed. It is not
    /// evidence that one is running.
    #[test]
    fn a_portfile_with_nothing_behind_it_is_not_an_engine() {
        let home = std::env::temp_dir().join(format!("mlh-shell-test-{}", std::process::id()));
        std::fs::create_dir_all(&home).unwrap();

        // 1. A portfile naming a port nobody is listening on.
        let stale = portfile(&home, a_closed_port());
        std::env::set_var("MLH_ENGINE_FILE", &stale);
        let answered = engine_status();
        assert!(
            answered.token.is_none(),
            "a dead engine's token was handed to the page"
        );
        let said = answered.error.expect("a stale portfile must be an error");
        assert!(
            said.contains("nothing is answering"),
            "the reason has to name what is wrong, not just fail: {said}"
        );

        // AND THE FILE IS STILL THERE. It may belong to somebody else's engine
        // that is merely slow; tidying it away would be the same overreach as
        // killing a process this did not spawn.
        assert!(
            stale.is_file(),
            "engine_status deleted a file it only reads"
        );

        // 2. The same portfile, with something answering that says it is us.
        let (live, serving) = an_engine_saying_it_is_ours();
        portfile(&home, live);
        let answered = engine_status();
        assert_eq!(
            answered.token.as_deref(),
            Some("a-token"),
            "error was {:?}",
            answered.error
        );
        assert!(answered.error.is_none(), "{:?}", answered.error);

        std::env::remove_var("MLH_ENGINE_FILE");
        let _ = TcpStream::connect(("127.0.0.1", live));
        let _ = serving.join();
        let _ = std::fs::remove_dir_all(&home);
    }
}
