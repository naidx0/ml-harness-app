//! Drives `engine::bootstrap` without opening a window, so the sidecar half of
//! Phase B is verifiable from a terminal rather than only by looking at one.
fn main() {
    let port: u16 = std::env::args()
        .nth(1)
        .and_then(|a| a.parse().ok())
        .unwrap_or(8078);
    let report = ml_harness_shell_lib::engine::bootstrap(port);
    println!(
        "started={} already={} interpreter={:?}",
        report.started, report.already_running, report.interpreter
    );
    println!("{}", report.detail);
    if report.started {
        println!("stopping the one we started");
        ml_harness_shell_lib::engine::stop_if_ours();
    }
}
