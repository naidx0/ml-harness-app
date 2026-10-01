//! The engine, as a child of the window — started only when nobody else has one.
//!
//! `docs/THE_PLAN.md` Phase B: *"sidecar lifecycle with `prevent_close` + hide,
//! because the engine is designed to outlive the window; first-run bootstrap"*.
//!
//! ## The rule that decides everything here: KILL ONLY WHAT YOU STARTED
//!
//! `scripts/launch.py` has spent thirty tests learning this, and its refusal is
//! the sharpest sentence in that file: a port that is taken by something this
//! launcher cannot identify *"will not be touched"*. The shell inherits the
//! rule rather than re-deriving it. It records whether IT spawned the engine,
//! and on quit it stops that child and nothing else — a developer with an
//! engine already running from a terminal closes this window and their engine
//! is still there, which is the behaviour they would expect and the behaviour a
//! naive "clean up on exit" would take away from them.
//!
//! ## Why it does not re-implement `decide()`
//!
//! `app/launcher.py` answers "is there an engine, is it OURS, is it running MY
//! code, should it be replaced" and Phase V A6 moved it into the package so a
//! shell could call it. **This shell cannot call it**, because that answer is
//! needed before there is a Python process to ask — which is the one case A6's
//! extraction does not cover.
//!
//! So the shell asks a narrower question it can answer alone: *is something
//! answering `/health` and does it say it is us?* That is `identity.SERVICE`
//! over a socket, which is the same handshake `probe_engine` starts with. It
//! does not attempt "is it running MY code" — a version comparison the shell has
//! no fingerprint for — and it does not replace anything. Narrower, and honest
//! about being narrower, rather than a second half-right copy.
//!
//! ## First-run bootstrap, in the order the answers deserve to be believed
//!
//! An interpreter somebody NAMED (`MLH_PYTHON`), then one uv MADE here on a
//! previous run, then `python` on PATH — and only when all three fail does this
//! reach for the sidecar and make one. Making one is last on purpose: an
//! interpreter that is already on the machine is always a better answer than one
//! this downloads, and a shell that downloaded a runtime before trying `python`
//! would be spending somebody's bandwidth to ignore what they already had.
//!
//! ## Why uv and not a frozen Python
//!
//! Repo-internal and decisive: `jobspec.interpreter` hands `sys.executable` to a
//! training recipe, and under a freezer that is the APPLICATION — so a frozen
//! build would relaunch this product instead of running somebody's training
//! script, silently, with a plausible process appearing. Freezing breaks the
//! training executor. uv makes a REAL interpreter, which is what every
//! `recipes/*/requirements.lock` in this repository is already written against.
//!
//! The sidecar itself is fetched and checksum-verified by
//! `scripts/fetch_sidecar.py` rather than committed; that file argues the case.

use std::path::{Path, PathBuf};
use std::process::{Child, Command};
use std::process::Stdio;
#[cfg(windows)]
use std::os::windows::process::CommandExt;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use serde::Serialize;

/// How long to wait for a freshly started engine to answer `/health`.
///
/// `scripts/launch.py` waits sixty seconds and says why: a cold import of
/// fastapi plus the migrations on a OneDrive-backed checkout is not fast. The
/// same number, for the same reason, and the wait ends the moment it answers.
const READY_TIMEOUT: Duration = Duration::from_secs(60);

/// How long uv gets to make an interpreter and install the product into it.
///
/// Longer than the engine's wait and for a different reason: on a machine with
/// no Python at all this DOWNLOADS a CPython and then a dependency tree. Five
/// minutes is generous for a first run on a slow connection and still short
/// enough that a hung fetch ends in a sentence rather than a spinner forever.
const BOOTSTRAP_TIMEOUT: Duration = Duration::from_secs(300);

/// What `identity.SERVICE` publishes. A port that answers and does NOT say this
/// is somebody else's and is never touched.
const SERVICE: &str = "ml-harness-engine";

/// The Python the bootstrap asks uv for.
///
/// Pinned rather than "whatever is newest": `pyproject.toml` requires >=3.11,
/// and the newest release is regularly the one some wheel in the tree has no
/// build for yet. A first run that resolves differently every month is not a
/// bootstrap, it is a lottery.
const BOOTSTRAP_PYTHON: &str = "3.11";

/// The engine this shell started, if it started one. `None` means either
/// nothing is running or what IS running belongs to somebody else — and the
/// difference matters only at quit, where this decides what may be stopped.
pub static OURS: Mutex<Option<Child>> = Mutex::new(None);

#[derive(Debug, Serialize)]
pub struct Bootstrap {
    pub started: bool,
    pub already_running: bool,
    pub interpreter: Option<String>,
    pub detail: String,
}

/// Where a usable Python might be, in the order they should be believed.
pub fn interpreters() -> Vec<(String, PathBuf)> {
    let mut found: Vec<(String, PathBuf)> = Vec::new();

    // A person or a build that named one said something more specific than
    // anything below. `app/paths.py::python_executable` reads the same variable
    // and refuses under a freezer without it, so the two halves agree.
    if let Ok(named) = std::env::var("MLH_PYTHON") {
        if !named.trim().is_empty() {
            found.push(("MLH_PYTHON".into(), PathBuf::from(named)));
        }
    }

    // The interpreter uv made on a previous first run. It lives in the per-user
    // data root — the same directory `app/paths.py` puts the database and the
    // portfile in — so an installed copy has ONE home rather than two.
    if let Some(root) = data_root() {
        found.push((
            "made by uv on a previous run".into(),
            venv_interpreter(&root.join("python")),
        ));
    }

    found.push(("python on PATH".into(), PathBuf::from("python")));
    found
}

/// Where an installed copy keeps its things.
///
/// `app/paths.py`'s rule, in Rust, and only the branch the shell needs: this is
/// asked before there is a Python to ask, which is the one case A6's extraction
/// does not cover. `lib.rs::portfile_candidates` reads the same two variables in
/// the same order for the same reason.
fn data_root() -> Option<PathBuf> {
    if let Ok(named) = std::env::var("MLH_DATA_ROOT") {
        if !named.trim().is_empty() {
            return Some(PathBuf::from(named));
        }
    }
    if cfg!(windows) {
        std::env::var("LOCALAPPDATA")
            .ok()
            .map(|local| PathBuf::from(local).join("ml-harness"))
    } else {
        std::env::var("HOME").ok().map(|home| {
            PathBuf::from(home)
                .join(".local")
                .join("share")
                .join("ml-harness")
        })
    }
}

/// The interpreter inside a virtual environment, by platform layout.
fn venv_interpreter(venv: &Path) -> PathBuf {
    if cfg!(windows) {
        venv.join("Scripts").join("python.exe")
    } else {
        venv.join("bin").join("python")
    }
}

/// The `uv` shipped beside this binary, when there is one.
///
/// Found by LOOKING rather than by composing a target triple, because Tauri
/// renames an external binary to `uv-<triple>` at bundle time and a triple this
/// file guessed would be a second opinion about the build's own target — wrong
/// on exactly the cross-compiled builds nobody tests by hand. `None` means no
/// sidecar, which is the ordinary state of a `cargo run` from a checkout and
/// gets its own sentence rather than a silent fallthrough.
fn uv_sidecar() -> Option<PathBuf> {
    let exe = std::env::current_exe().ok()?;
    let beside = exe.parent()?;
    for entry in std::fs::read_dir(beside).ok()?.flatten() {
        let name = entry.file_name();
        let name = name.to_string_lossy();
        let stem = name.strip_suffix(".exe").unwrap_or(&name);
        if stem == "uv" || stem.starts_with("uv-") {
            let path = entry.path();
            if path.is_file() {
                return Some(path);
            }
        }
    }
    None
}

/// What to install into a fresh interpreter, and what to call it when saying so.
fn payload() -> Result<(String, PathBuf), String> {
    let beside = std::env::current_exe()
        .ok()
        .and_then(|exe| exe.parent().map(Path::to_path_buf));
    choose_payload(repository_root(), beside.as_deref())
}

/// The decision, as a function of what was found rather than of where it ran.
///
/// SPLIT OUT SO THE WHEEL BRANCH IS REACHABLE IN A TEST. `repository_root()` is
/// a compile-time path plus an existence check, and on the machine anybody runs
/// tests on that path exists — so the packaged branch, the one every INSTALLED
/// copy takes, was the only branch that could never be exercised where it would
/// be noticed. Two arguments and no environment, and both branches are ordinary
/// test cases.
///
/// Two real answers and no guess. A checkout installs ITSELF, which is what a
/// developer wants. A packaged build installs the wheel `bundle.resources`
/// ships beside it — the same wheel `.github/workflows/gate.yml` already builds
/// and imports on both platforms, so what this installs is an artefact CI has
/// already proven imports.
fn choose_payload(
    repository: Option<PathBuf>,
    beside: Option<&Path>,
) -> Result<(String, PathBuf), String> {
    if let Some(root) = repository {
        return Ok(("the checkout this binary was built in".into(), root));
    }
    if let Some(beside) = beside {
        let resources = beside.join("resources");
        if let Ok(entries) = std::fs::read_dir(&resources) {
            let mut wheels: Vec<PathBuf> = entries
                .flatten()
                .map(|entry| entry.path())
                .filter(|path| {
                    path.extension().and_then(|e| e.to_str()) == Some("whl")
                        && path
                            .file_name()
                            .and_then(|n| n.to_str())
                            .is_some_and(|n| n.starts_with("ml_harness-"))
                })
                .collect();
            // NEWEST WINS, by name, because a bundle that somehow carries two
            // wheels should install the later one rather than whichever the
            // filesystem happened to hand back first.
            wheels.sort();
            if let Some(wheel) = wheels.pop() {
                return Ok(("the wheel shipped beside this binary".into(), wheel));
            }
        }
    }
    Err(
        "there is no checkout beside this binary and no wheel in its resources \
         directory, so there is nothing to install into an interpreter. A \
         packaged build ships one - see bundle.resources in tauri.conf.json."
            .into(),
    )
}

#[cfg(test)]
mod payload_tests {
    use super::*;

    fn a_directory(name: &str) -> PathBuf {
        let path = std::env::temp_dir().join(format!("mlh-payload-{}-{name}", std::process::id()));
        let _ = std::fs::remove_dir_all(&path);
        std::fs::create_dir_all(path.join("resources")).unwrap();
        path
    }

    fn a_wheel(beside: &Path, name: &str) {
        std::fs::write(beside.join("resources").join(name), b"not really a wheel").unwrap();
    }

    #[test]
    fn a_checkout_installs_itself() {
        let beside = a_directory("checkout");
        a_wheel(&beside, "ml_harness-0.1.0-py3-none-any.whl");

        let (what, source) =
            choose_payload(Some(PathBuf::from("/somewhere/checkout")), Some(&beside)).unwrap();

        // THE CHECKOUT WINS EVEN WITH A WHEEL SITTING THERE, and that order is
        // the whole reason a developer's `cargo run` installs the code they are
        // editing rather than whatever a previous build left in resources/.
        assert!(what.contains("checkout"), "{what}");
        assert_eq!(source, PathBuf::from("/somewhere/checkout"));
        let _ = std::fs::remove_dir_all(&beside);
    }

    #[test]
    fn an_installed_copy_installs_the_wheel_beside_it() {
        // THE BRANCH EVERY INSTALL TAKES AND NO DEVELOPER MACHINE CAN REACH.
        let beside = a_directory("installed");
        a_wheel(&beside, "ml_harness-0.1.0-py3-none-any.whl");

        let (what, source) = choose_payload(None, Some(&beside)).unwrap();

        assert!(what.contains("wheel"), "{what}");
        assert_eq!(
            source.file_name().unwrap(),
            "ml_harness-0.1.0-py3-none-any.whl"
        );
        let _ = std::fs::remove_dir_all(&beside);
    }

    #[test]
    fn two_wheels_means_the_newer_one() {
        let beside = a_directory("two");
        a_wheel(&beside, "ml_harness-0.1.0-py3-none-any.whl");
        a_wheel(&beside, "ml_harness-0.2.0-py3-none-any.whl");

        let (_, source) = choose_payload(None, Some(&beside)).unwrap();

        assert_eq!(
            source.file_name().unwrap(),
            "ml_harness-0.2.0-py3-none-any.whl"
        );
        let _ = std::fs::remove_dir_all(&beside);
    }

    #[test]
    fn somebody_elses_wheel_is_not_ours() {
        // `bundle.resources` is a glob and a directory is a place other things
        // land. A wheel that is not this product is not a payload for it.
        let beside = a_directory("stranger");
        a_wheel(&beside, "requests-2.32.0-py3-none-any.whl");

        let refused = choose_payload(None, Some(&beside)).unwrap_err();

        assert!(refused.contains("no wheel"), "{refused}");
    }

    #[test]
    fn no_checkout_and_no_wheel_is_a_sentence_not_a_shrug() {
        let beside = a_directory("empty");

        let refused = choose_payload(None, Some(&beside)).unwrap_err();

        // It has to name what a packaged build would have, or the person
        // reading it learns only that something is missing.
        assert!(refused.contains("bundle.resources"), "{refused}");
        let _ = std::fs::remove_dir_all(&beside);
    }
}

/// Make an interpreter with the shipped uv, and install the product into it.
///
/// An interpreter that cannot `import app` is not a bootstrap, it is a
/// directory — so the install is part of this function rather than a hopeful
/// second step, and a failure to install is a failure to bootstrap.
fn bootstrap_with_uv() -> Result<PathBuf, String> {
    let uv = uv_sidecar().ok_or(
        "no uv sidecar beside this binary. A packaged build ships one \
         (bundle.externalBin, fetched by scripts/fetch_sidecar.py); a checkout \
         does not, which is why an interpreter already on this machine is tried \
         first and is the answer a developer actually has.",
    )?;
    let (what, source) = payload()?;
    let home = data_root().ok_or("this machine has no per-user data directory to build in")?;
    let venv = home.join("python");

    run(
        Command::new(&uv)
            .arg("venv")
            .arg("--python")
            .arg(BOOTSTRAP_PYTHON)
            .arg(&venv),
        "make an interpreter",
    )?;

    let interpreter = venv_interpreter(&venv);
    run(
        Command::new(&uv)
            .arg("pip")
            .arg("install")
            .arg("--python")
            .arg(&interpreter)
            .arg(&source),
        &format!("install {what} into it"),
    )?;
    write_stamp(&venv, &source);

    Ok(interpreter)
}

/// The file inside the uv-made environment that names what it was filled from.
const PAYLOAD_STAMP: &str = "ml-harness-payload.txt";

/// What a payload IS, for "has it changed since the environment was filled".
///
/// Size and modification time rather than a hash: a rebuilt wheel keeps the
/// name `ml_harness-0.1.0-py3-none-any.whl` (the version never moves), so the
/// name cannot say it changed, and reading two megabytes on every launch to
/// learn what `stat` already knows is waste. A checkout is named by its
/// `pyproject.toml`, which is where its dependencies live.
fn payload_identity(source: &Path) -> Option<String> {
    let file = if source.is_dir() {
        source.join("pyproject.toml")
    } else {
        source.to_path_buf()
    };
    let meta = std::fs::metadata(&file).ok()?;
    let modified = meta
        .modified()
        .ok()?
        .duration_since(std::time::UNIX_EPOCH)
        .ok()?
        .as_secs();
    Some(format!("{}|{}|{}", source.display(), meta.len(), modified))
}

fn write_stamp(venv: &Path, source: &Path) {
    if let Some(identity) = payload_identity(source) {
        let _ = std::fs::write(venv.join(PAYLOAD_STAMP), identity);
    }
}

/// Was this environment filled from something other than `source`?
///
/// No stamp counts as stale: every environment made before the stamp existed
/// was filled once and never again, which is the fault this closes.
fn is_stale(venv: &Path, source: &Path) -> bool {
    let Some(now) = payload_identity(source) else {
        return false;
    };
    std::fs::read_to_string(venv.join(PAYLOAD_STAMP))
        .map(|then| then.trim() != now)
        .unwrap_or(true)
}

/// Bring the uv-made environment up to the payload this binary ships.
///
/// AN UPGRADE NEVER REACHED THE ENGINE. `bootstrap_with_uv` fills the
/// environment once, on a first run, and every later launch found that
/// interpreter first and ran it - so installing a new build replaced the
/// window and left the engine on whatever the first install carried. Measured
/// 2026-09-30 on the owner's machine: the environment's `ml_harness` was
/// installed 2026-09-14 while the installer beside it was built 2026-09-26.
///
/// `--reinstall-package` and not `--reinstall`: the product is the thing that
/// changed, and reinstalling the whole dependency tree would turn every launch
/// after an upgrade into a download. A dependency the new payload ADDS is
/// still resolved, because the install resolves the payload's requirements.
///
/// Returns a sentence when it tried, so the launch can say what it did. A
/// failure leaves the old environment in place: an engine on last week's code
/// is a better answer than no engine.
fn refresh_made_interpreter() -> Option<String> {
    let venv = data_root()?.join("python");
    let interpreter = venv_interpreter(&venv);
    if !interpreter.is_file() {
        return None;
    }
    let (what, source) = payload().ok()?;
    if !is_stale(&venv, &source) {
        return None;
    }
    let uv = uv_sidecar()?;
    match run(
        Command::new(&uv)
            .arg("pip")
            .arg("install")
            .arg("--reinstall-package")
            .arg("ml-harness")
            .arg("--python")
            .arg(&interpreter)
            .arg(&source),
        &format!("refresh {what} in {}", venv.display()),
    ) {
        Ok(()) => {
            write_stamp(&venv, &source);
            Some(format!("refreshed {} from {what}", venv.display()))
        }
        Err(why) => Some(why),
    }
}

#[cfg(test)]
mod stamp_tests {
    use super::*;

    fn a_place(name: &str) -> (PathBuf, PathBuf) {
        let root = std::env::temp_dir().join(format!("mlh-stamp-{}-{name}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        let venv = root.join("python");
        std::fs::create_dir_all(&venv).unwrap();
        let wheel = root.join("ml_harness-0.1.0-py3-none-any.whl");
        std::fs::write(&wheel, b"the first build").unwrap();
        (venv, wheel)
    }

    #[test]
    fn an_environment_with_no_stamp_is_stale() {
        // Every environment made before this fix: filled once, never again.
        let (venv, wheel) = a_place("unstamped");
        assert!(is_stale(&venv, &wheel));
    }

    #[test]
    fn a_stamped_environment_is_current_until_the_payload_changes() {
        let (venv, wheel) = a_place("stamped");
        write_stamp(&venv, &wheel);
        assert!(!is_stale(&venv, &wheel));

        // THE UPGRADE: same file name, different build.
        std::fs::write(&wheel, b"the second build, which is longer").unwrap();
        assert!(is_stale(&venv, &wheel));
    }

    #[test]
    fn a_checkout_is_named_by_its_pyproject() {
        let (venv, _) = a_place("checkout");
        let checkout = venv.parent().unwrap().join("checkout");
        std::fs::create_dir_all(&checkout).unwrap();
        std::fs::write(checkout.join("pyproject.toml"), b"[project]\n").unwrap();
        write_stamp(&venv, &checkout);
        assert!(!is_stale(&venv, &checkout));

        std::fs::write(checkout.join("pyproject.toml"), b"[project]\ndependencies = [\"x\"]\n").unwrap();
        assert!(is_stale(&venv, &checkout));
    }

    #[test]
    fn a_payload_that_cannot_be_read_never_forces_a_refresh() {
        let (venv, _) = a_place("missing");
        assert!(!is_stale(&venv, &venv.join("no-such.whl")));
    }
}

#[cfg(test)]
mod adopt_tests {
    use super::*;

    #[test]
    fn a_child_that_already_exited_is_given_up_on_at_once() {
        let port = std::net::TcpListener::bind("127.0.0.1:0")
            .unwrap()
            .local_addr()
            .unwrap()
            .port();
        let child = if cfg!(windows) {
            Command::new("cmd").args(["/C", "exit 3"]).spawn().unwrap()
        } else {
            Command::new("sh").args(["-c", "exit 3"]).spawn().unwrap()
        };
        let started = Instant::now();

        assert!(adopt_when_ready(child, port).is_none());
        // Before the fix this took READY_TIMEOUT, sixty seconds.
        assert!(started.elapsed() < Duration::from_secs(10), "{:?}", started.elapsed());
    }
}

/// Run one uv command to completion, with a deadline, and report what it said.
///
/// The stderr goes into the error on purpose. uv's failures are specific — no
/// network, no matching CPython, a dependency that has no wheel for this
/// platform — and a shell that swallowed them would turn four different
/// problems into one shrug.
/// THE ENGINE IS NOT A TERMINAL, and on Windows it was drawing one.
///
/// Max, watching the packaged app start: *"I don't want it to open the
/// background terminal execution every time it launches a package. The
/// package should load the front end and the engine as one process... It
/// should be the same way Claude opens up, and it's one desktop
/// application."*
///
/// `main.rs` already carries `windows_subsystem = "windows"`, so the SHELL
/// has no console. But a GUI process that spawns a CONSOLE subsystem child -
/// `uv.exe`, `python.exe` - makes Windows allocate a fresh console for the
/// child and show it. The shell being windowless does not cover what it
/// launches; each child decides for itself, and the default is to appear.
///
/// `CREATE_NO_WINDOW` is the documented flag for exactly this: the child
/// still gets stdio handles and still shows in Task Manager - which is what
/// Max asked for - it simply never gets a window. Applied at the two funnels
/// every spawn in this file goes through rather than at each call, so a
/// fourth spawn added later cannot forget it.
///
/// It is a no-op off Windows, where nothing draws a console in the first
/// place.
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

fn without_a_console(command: &mut Command) -> &mut Command {
    #[cfg(windows)]
    command.creation_flags(CREATE_NO_WINDOW);
    command
}

fn run(command: &mut Command, doing: &str) -> Result<(), String> {
    let mut child = without_a_console(command)
        .spawn()
        .map_err(|error| format!("could not {doing}: {error}"))?;

    let started = Instant::now();
    loop {
        match child.try_wait() {
            Ok(Some(status)) if status.success() => return Ok(()),
            Ok(Some(status)) => {
                return Err(format!("could not {doing}: uv exited with {status}"));
            }
            Ok(None) => {
                if started.elapsed() >= BOOTSTRAP_TIMEOUT {
                    let _ = child.kill();
                    let _ = child.wait();
                    return Err(format!(
                        "could not {doing}: uv was still running after {}s and was \
                         stopped. On a first run this step downloads a Python and a \
                         dependency tree, so the usual cause is a connection that \
                         stalled rather than one that failed.",
                        BOOTSTRAP_TIMEOUT.as_secs()
                    ));
                }
                std::thread::sleep(Duration::from_millis(250));
            }
            Err(error) => return Err(format!("could not {doing}: {error}")),
        }
    }
}

/// Is something on this port, and does it say it is us?
///
/// NARROWER THAN `probe_engine` ON PURPOSE — see the module docstring. This
/// answers "ours or not", which is all that is needed to decide whether to
/// start one, and it never answers "stale", because acting on that would mean
/// killing a process the shell cannot fingerprint.
pub fn ours_is_answering(port: u16) -> bool {
    let url = format!("http://127.0.0.1:{port}/health");
    match minreq_get(&url) {
        Some(body) => body.contains(SERVICE),
        None => false,
    }
}

/// The shell as the page's wire to the engine. `engine_fetch` exists because
/// the WebView's OWN networking kept finding new ways to refuse loopback -
/// CORS, private-network preflights, and whatever Chromium adds next year.
/// The Rust half of this app has none of those rules: it is a local process
/// talking to a local port, which is the whole architecture. The page asks
/// the shell to carry the request, and the browser's opinion of 127.0.0.1
/// stops being part of the product. This is what makes the two halves ONE
/// package in practice: the window cannot be cut off from its own engine by
/// a browser policy.
pub fn engine_request(
    url: &str,
    method: &str,
    token: Option<&str>,
    body: Option<&str>,
) -> Result<(u16, String), String> {
    use std::io::{Read, Write};
    use std::net::TcpStream;

    let rest = url
        .strip_prefix("http://")
        .ok_or_else(|| format!("only http:// loopback urls are carried, got {url}"))?;
    let (authority, path) = rest.split_once('/').unwrap_or((rest, ""));
    if !(authority.starts_with("127.0.0.1") || authority.starts_with("localhost")) {
        return Err("the shell only carries requests to this machine".into());
    }
    let mut stream = TcpStream::connect(authority).map_err(|e| e.to_string())?;
    stream
        .set_read_timeout(Some(Duration::from_secs(600)))
        .map_err(|e| e.to_string())?;
    let payload = body.unwrap_or("");
    let auth = token
        .map(|t| format!("Authorization: Bearer {t}\r\n"))
        .unwrap_or_default();
    write!(
        stream,
        "{method} /{path} HTTP/1.0\r\nHost: {authority}\r\n{auth}Content-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{payload}",
        payload.len()
    )
    .map_err(|e| e.to_string())?;
    let mut raw = String::new();
    stream.read_to_string(&mut raw).map_err(|e| e.to_string())?;
    let status: u16 = raw
        .split_whitespace()
        .nth(1)
        .and_then(|s| s.parse().ok())
        .unwrap_or(0);
    let body_out = raw
        .split_once("\r\n\r\n")
        .map(|(_, b)| b.to_string())
        .unwrap_or_default();
    Ok((status, body_out))
}

/// One GET, no dependencies, no redirects. Enough to read a small JSON body.
///
/// Hand-rolled rather than pulling an HTTP client in for one request: this asks
/// loopback for a few hundred bytes, and a crate for that is a dependency to
/// audit and update forever.
fn minreq_get(url: &str) -> Option<String> {
    use std::io::{Read, Write};
    use std::net::TcpStream;

    let rest = url.strip_prefix("http://")?;
    let (authority, path) = rest.split_once('/').unwrap_or((rest, ""));
    let mut stream = TcpStream::connect(authority).ok()?;
    stream.set_read_timeout(Some(Duration::from_secs(2))).ok()?;
    write!(
        stream,
        "GET /{path} HTTP/1.0\r\nHost: {authority}\r\nConnection: close\r\n\r\n"
    )
    .ok()?;
    let mut body = String::new();
    stream.read_to_string(&mut body).ok()?;
    Some(body)
}

/// One spawn, one shape, so nothing here can drift about how the engine is
/// invoked.
///
/// `scripts/launch.py` builds the same argv and says why there is no
/// `--reload`: reload puts a supervisor between the pid that answers and the
/// pid that owns the socket, and `/health`'s pid is only true without it.
fn spawn_engine(interpreter: &Path, home: &Path, port: u16) -> std::io::Result<Child> {
    /* SOMEWHERE TO WRITE, now that there is no console to write to.

       Suppressing the child's window closed the only place this engine's
       output had ever gone. `logs/engine.log` is NOT that place and never
       was - `scripts/launch.py` owns that file, and a shell-spawned engine
       has never touched it - so this writes its own, named for who started
       it. Two launchers appending to one file would interleave two engines'
       tracebacks and leave nobody able to say which was which.

       APPEND, not truncate: the interesting run is usually the one before
       the restart. A failure to open the file is not a failure to start the
       engine - it falls back to `null`, which is exactly where the output
       was going a moment ago. */
    let log = data_root()
        .map(|home| home.join("logs"))
        .and_then(|logs| std::fs::create_dir_all(&logs).ok().map(|_| logs))
        .map(|logs| logs.join("engine-shell.log"))
        .and_then(|path| {
            std::fs::OpenOptions::new()
                .create(true)
                .append(true)
                .open(path)
                .ok()
        });

    let mut started = Command::new(interpreter);
    started
        .args([
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
        ])
        .arg(port.to_string())
        .arg("--log-level")
        .arg("info")
        .current_dir(home)
        .env("MLH_PORT", port.to_string());
    if let Some(file) = log {
        match file.try_clone() {
            Ok(second) => {
                started.stdout(Stdio::from(file)).stderr(Stdio::from(second));
            }
            //: One handle and no way to make a second is not a reason to
            //: refuse to start; stderr is the half worth keeping.
            Err(_) => {
                started.stderr(Stdio::from(file));
            }
        }
    }
    without_a_console(&mut started).spawn()
}

/// Wait for a spawned engine to answer, and adopt it if it does.
///
/// Returns `None` when it never answered — having already stopped it, because
/// this window is the only thing that knows that process exists and leaving it
/// running would be leaving a port taken by something nobody can name.
///
/// A CHILD THAT HAS ALREADY EXITED WILL NEVER ANSWER, and waiting out the full
/// minute for it made the next candidate wait too. On a machine whose `python`
/// on PATH has no `app` in it, that interpreter dies inside a second with
/// `ModuleNotFoundError`, and the first launch sat sixty seconds on a corpse
/// before reaching the one that could work.
fn adopt_when_ready(child: Child, port: u16) -> Option<()> {
    let mut child = child;
    let started = Instant::now();
    while started.elapsed() < READY_TIMEOUT {
        if ours_is_answering(port) {
            *OURS.lock().unwrap() = Some(child);
            return Some(());
        }
        if let Ok(Some(_)) = child.try_wait() {
            return None;
        }
        std::thread::sleep(Duration::from_millis(250));
    }
    let _ = child.kill();
    let _ = child.wait();
    None
}

/// Start the engine if nobody else has, and wait until it answers.
pub fn bootstrap(port: u16) -> Bootstrap {
    if ours_is_answering(port) {
        return Bootstrap {
            started: false,
            already_running: true,
            interpreter: None,
            detail: format!(
                "an ML Harness engine is already answering on {port}. It was not \
                 started by this window and will not be stopped by it."
            ),
        };
    }

    // A checkout is where a developer's engine belongs — `paths.data_root()`
    // keeps the database there rather than orphaning it in %LOCALAPPDATA% — and
    // an installed copy has no checkout, so it runs from its own data root and
    // finds `app` because the bootstrap installed it.
    let home = repository_root()
        .or_else(data_root)
        .unwrap_or_else(|| PathBuf::from("."));

    let refreshed = refresh_made_interpreter()
        .map(|note| format!(" Before starting: {note}."))
        .unwrap_or_default();

    let mut tried: Vec<String> = Vec::new();
    for (why, interpreter) in interpreters() {
        match spawn_engine(&interpreter, &home, port) {
            Ok(child) => {
                if adopt_when_ready(child, port).is_some() {
                    return Bootstrap {
                        started: true,
                        already_running: false,
                        interpreter: Some(interpreter.display().to_string()),
                        detail: format!(
                            "started the engine on {port} with {} ({why}), and it \
                             answered /health saying it is ours.{refreshed}",
                            interpreter.display()
                        ),
                    };
                }
                tried.push(format!(
                    "{} ({why}) started and exited or did not answer within {}s",
                    interpreter.display(),
                    READY_TIMEOUT.as_secs()
                ));
            }
            Err(error) => tried.push(format!("{} ({why}): {error}", interpreter.display())),
        }
    }

    // NOTHING ON THIS MACHINE COULD RUN IT, so make something that can. This is
    // the first-run path — a person who installed the app and has no Python is
    // the case the sidecar exists for — and it is last because an interpreter
    // already here always beats one this downloads.
    match bootstrap_with_uv() {
        Err(why) => tried.push(format!("uv bootstrap: {why}")),
        Ok(interpreter) => match spawn_engine(&interpreter, &home, port) {
            Err(error) => tried.push(format!("uv made {}: {error}", interpreter.display())),
            Ok(child) => {
                if adopt_when_ready(child, port).is_some() {
                    return Bootstrap {
                        started: true,
                        already_running: false,
                        interpreter: Some(interpreter.display().to_string()),
                        detail: format!(
                            "no interpreter on this machine could run the engine, so uv                              made one at {} and it answered on {port}.",
                            interpreter.display()
                        ),
                    };
                }
                tried.push(format!(
                    "uv made {} and the engine it started did not answer within {}s",
                    interpreter.display(),
                    READY_TIMEOUT.as_secs()
                ));
            }
        },
    }

    Bootstrap {
        started: false,
        already_running: false,
        interpreter: None,
        detail: format!(
            "no engine is answering on {port} and none could be started. Tried: {}. \
             Set MLH_PYTHON to an interpreter that has this project installed.",
            tried.join("; ")
        ),
    }
}

/// The checkout this binary sits in, when it sits in one.
fn repository_root() -> Option<PathBuf> {
    let here = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let root = here.parent()?;
    root.join("docs")
        .join("diagnosis_engine.yaml")
        .is_file()
        .then(|| root.to_path_buf())
}

/// Replace whatever engine is answering on `port` with a fresh one.
///
/// THE WINDOW COULD START AN ENGINE AND COULD NOT REPLACE ONE. `bootstrap`
/// refuses when something is already answering, and `stop_if_ours` only ends a
/// child this window spawned - both correct on their own, and between them
/// they left the one case that matters uncovered: an engine somebody else
/// started, running older code, visible to the window as wrong and
/// unreplaceable by it. Max, 2026-09-21: *"the whole thing with the app should
/// be one package, and the engine should be easy for people to restart, they
/// shouldn't be running scripts on their own."*
///
/// NOTHING HERE KILLS A PROCESS. It asks the engine to exit, over loopback,
/// carrying the bearer token that engine published to `engine.json` - so the
/// only caller that can stop it is one that can already read its secrets, and
/// a pid we merely believe is ours is never signalled. An engine that does not
/// answer that route is one this shell should not be stopping anyway.
pub fn restart(port: u16, base_url: &str, token: Option<&str>) -> Bootstrap {
    if ours_is_answering(port) {
        let url = format!("{}/api/engine/shutdown", base_url.trim_end_matches('/'));
        match engine_request(&url, "POST", token, Some("{}")) {
            Ok((status, _)) if (200..300).contains(&status) => {}
            Ok((status, body)) => {
                return Bootstrap {
                    started: false,
                    already_running: true,
                    interpreter: None,
                    detail: format!(
                        "the engine on {port} refused to stop (HTTP {status}): {}.                          It may be older than this app and not know the route.",
                        body.trim()
                    ),
                };
            }
            Err(why) => {
                return Bootstrap {
                    started: false,
                    already_running: true,
                    interpreter: None,
                    detail: format!("could not ask the engine on {port} to stop: {why}"),
                };
            }
        }
        // It said it would go. Wait for the socket, because the next thing
        // that happens is a new engine binding the same port.
        let waited = Instant::now();
        while waited.elapsed() < Duration::from_secs(20) {
            if !ours_is_answering(port) {
                break;
            }
            std::thread::sleep(Duration::from_millis(200));
        }
        if ours_is_answering(port) {
            return Bootstrap {
                started: false,
                already_running: true,
                interpreter: None,
                detail: format!(
                    "the engine on {port} accepted the stop and is still answering                      twenty seconds later. Nothing was started; something is                      restarting it."
                ),
            };
        }
        // A child of ours that has now exited must not be held onto - the
        // handle would keep a zombie and the next stop_if_ours would signal a
        // pid that has been recycled.
        *OURS.lock().unwrap() = None;
    }
    bootstrap(port)
}

/// Stop the engine THIS SHELL started. Never one it merely found.
///
/// The whole of the rule in four lines: if `OURS` holds a child, it is one this
/// window spawned, and stopping it on quit is tidying up after itself. If it
/// holds nothing, something else owns whatever is running - a terminal, another
/// window, `scripts/launch.py` - and their engine surviving this window closing
/// is the correct outcome rather than an oversight.
pub fn stop_if_ours() {
    if let Some(mut child) = OURS.lock().unwrap().take() {
        let _ = child.kill();
        let _ = child.wait();
    }
}
