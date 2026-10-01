//! The signing config in `release.yml`, checked against the type that reads it.
//!
//! ## The failure this exists to prevent
//!
//! Phase C's remaining blocker is a certificate: it needs a verified identity
//! and money, and no command produces one. So `.github/workflows/release.yml`
//! is built to be ONE SECRET AWAY — it passes a thumbprint to `tauri build`
//! with `--config` and signs only when `WINDOWS_CERTIFICATE_THUMBPRINT` is set.
//!
//! **Which means the signing path has never run, and would first run on the day
//! it matters most.** `tauri_utils::config::WindowsConfig` is
//! `#[serde(rename_all = "camelCase", deny_unknown_fields)]`, so one mistyped
//! key is not a warning and not a silently ignored field — it is a hard parse
//! error, discovered with a certificate finally in hand, a release waiting, and
//! a workflow nobody can debug against because the secret only exists in CI.
//!
//! This deserializes the workflow's OWN JSON into the real type on every push,
//! so the day the certificate arrives, the config is already known to parse.
//!
//! ## Why it reads the workflow rather than restating it
//!
//! A test carrying its own copy of the JSON would prove that copy parses. The
//! thing that has to parse is the one the release actually runs, and a second
//! copy is the second place that goes stale — the failure mode this repository
//! refuses everywhere else. So the workflow is the source, and this extracts
//! from it by string rather than by parsing YAML, because the one line it needs
//! is unambiguous and a YAML dependency for it would be a dependency to keep
//! forever.
//!
//! ## What it does NOT prove
//!
//! That signtool works, that the certificate is valid, that SmartScreen is
//! satisfied. None of those can be known without a certificate. It proves the
//! one thing that is knowable now: the shape is right.

use std::path::PathBuf;

/// The `--config` JSON out of the release workflow, with the secret filled in.
fn signing_config_from_the_workflow() -> String {
    let workflow = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("src-tauri has a parent")
        .join(".github")
        .join("workflows")
        .join("release.yml");
    let text = std::fs::read_to_string(&workflow)
        .unwrap_or_else(|error| panic!("{}: {error}", workflow.display()));

    let marker = "--config '";
    let start = text.find(marker).unwrap_or_else(|| {
        panic!(
            "no `--config '{{...}}'` in {}. If the signed build stopped \
                 passing its config that way, this test is checking nothing and \
                 should be rewritten rather than deleted.",
            workflow.display()
        )
    }) + marker.len();
    let rest = &text[start..];
    let end = rest.find('\'').expect("the --config JSON is not closed");

    // The workflow interpolates the secret. A thumbprint is 40 hex characters;
    // any placeholder would do for a parse, and a realistic one means the test
    // fails for a shape problem rather than for a length nobody promised.
    let json = &rest[..end];
    let secret_start = json
        .find("${{")
        .expect("no secret interpolation in the config");
    let secret_end = json[secret_start..]
        .find("}}")
        .expect("unterminated interpolation")
        + secret_start
        + 2;
    format!(
        "{}{}{}",
        &json[..secret_start],
        "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",
        &json[secret_end..]
    )
}

#[test]
fn the_signed_build_passes_keys_the_config_type_accepts() {
    let filled = signing_config_from_the_workflow();

    let parsed: serde_json::Value = serde_json::from_str(&filled)
        .unwrap_or_else(|error| panic!("the workflow's --config is not JSON: {error}\n{filled}"));

    let windows = parsed
        .get("bundle")
        .and_then(|bundle| bundle.get("windows"))
        .unwrap_or_else(|| panic!("the config sets no bundle.windows: {filled}"));

    // THE ACTUAL CHECK. `deny_unknown_fields` turns a typo into an error here,
    // which is the whole point: `certificateThumprint` would sail through a
    // hand-written key list and die at release time.
    let config: tauri_utils::config::WindowsConfig = serde_json::from_value(windows.clone())
        .unwrap_or_else(|error| {
            panic!(
                "tauri refuses the signing config this workflow would pass it: \
                 {error}\n{windows}"
            )
        });

    assert_eq!(
        config.certificate_thumbprint.as_deref(),
        Some("a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"),
        "the thumbprint did not land in the field tauri reads it from"
    );
    assert!(
        config.timestamp_url.is_some(),
        "a signature with no timestamp expires with the certificate, and every \
         binary already shipped stops verifying on that day"
    );
    assert_eq!(
        config.digest_algorithm.as_deref(),
        Some("sha256"),
        "SHA-1 authenticode has not been accepted since 2016"
    );
}

#[test]
fn the_unsigned_build_passes_no_certificate_at_all() {
    // The other half of "one secret away": with no secret, the workflow must
    // not be quietly building with an empty thumbprint, which some toolchains
    // treat as "sign with whatever is first in the store".
    let workflow = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .join(".github")
        .join("workflows")
        .join("release.yml");
    let text = std::fs::read_to_string(workflow).unwrap();

    let unsigned = text
        .split("Build the bundle (unsigned)")
        .nth(1)
        .expect("no unsigned build step")
        .split("- name:")
        .next()
        .expect("the unsigned step has no body");

    assert!(
        !unsigned.contains("certificateThumbprint"),
        "the unsigned build passes a certificate thumbprint: {unsigned}"
    );
    assert!(
        unsigned.contains("tauri build"),
        "the unsigned step does not build: {unsigned}"
    );
}
