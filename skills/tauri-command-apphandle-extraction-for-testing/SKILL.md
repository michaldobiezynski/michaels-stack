---
name: tauri-command-apphandle-extraction-for-testing
description: |
  Pattern for making Tauri 2 commands testable when they take
  `tauri::AppHandle` and run heavy synchronous work (ML inference, file
  IO, subprocess orchestration). Use when: (1) you want a `cargo test`
  integration suite to drive a Tauri command without spinning up a real
  app, (2) the command body resolves a resource path via
  `app.path().resolve(..., BaseDirectory::Resource)` then does work,
  (3) the project is a Tauri-2 binary-only crate (no `[lib]` section)
  so `tests/*.rs` integration tests aren't usable, (4) you'd otherwise
  duplicate the pipeline orchestration in tests and risk drift. Covers
  the sync/async split refactor and the in-crate `#[cfg(test)] mod` test
  layout.
author: Claude Code
version: 1.0.0
date: 2026-04-25
---

# Testing Tauri commands that take `AppHandle`

## Problem

You have a Tauri 2 command that looks like this:

```rust
#[tauri::command]
#[specta::specta]
pub async fn detect_position(
    image_data: Vec<u8>,
    app: tauri::AppHandle,
) -> Result<DetectionResult, Error> {
    let model_path = app.path()
        .resolve("resources/models/chess_pieces.onnx", BaseDirectory::Resource)?;
    tokio::task::spawn_blocking(move || -> Result<DetectionResult, Error> {
        // ... 200 lines of pipeline orchestration ...
    })
    .await?
}
```

You want to write integration-style tests that exercise the whole pipeline
against committed fixtures. But:

- `AppHandle` is hard to construct outside a Tauri runtime. `tauri::test`
  helpers exist but won't resolve `BaseDirectory::Resource` to your repo's
  `resources/` dir without bundling.
- The pipeline body is too long to duplicate in a test (drift risk).
- Many Tauri 2 projects are binary-only (no `[lib]` section in
  `Cargo.toml`). `cargo test --test foo` looking for files in
  `tests/foo.rs` requires a library target — adding one is invasive.

## Context / Trigger Conditions

Apply this pattern when ALL of:

1. The command body does NOT need `AppHandle` for anything other than
   resolving paths (or other purely-derivable values).
2. The pipeline is long enough that test-side duplication would drift.
3. You want a `cargo test`-runnable integration test that calls the real
   pipeline.

If the command body genuinely uses `AppHandle` to emit events, talk to
plugins, etc., this pattern is insufficient — use `tauri::test::mock_app()`
with explicit plugin builders instead.

## Solution

### 1. Extract a sync helper that takes concrete inputs

Move the entire body that doesn't need `AppHandle` into a new
`pub(crate)` sync function. Replace `AppHandle`-derived values in the
signature with concrete equivalents (`PathBuf`, `&str`, etc.):

```rust
/// Synchronous core of the detection pipeline. Extracted so the
/// integration corpus can call the pipeline with a plain filesystem
/// model path, bypassing the Tauri `AppHandle` required by the async
/// entry point. Behaviour is identical to what `detect_position_bytes`
/// runs inside its `spawn_blocking` closure.
pub(crate) fn detect_position_sync(
    image_data: Vec<u8>,
    model_path: PathBuf,
) -> Result<DetectionResult, Error> {
    // ... the previous closure body, un-indented one level ...
}
```

The async entry point becomes a thin resolver + `spawn_blocking`:

```rust
pub async fn detect_position_bytes(
    image_data: Vec<u8>,
    app: tauri::AppHandle,
) -> Result<DetectionResult, Error> {
    let model_path = resolve_model_path(&app)?;
    tokio::task::spawn_blocking(move || detect_position_sync(image_data, model_path))
        .await
        .map_err(|e| Error::Custom(format!("Detection task panicked: {e}")))?
}
```

This is mechanically equivalent to before — same code, same outputs —
but now the sync helper is reachable without an `AppHandle`.

### 2. Mirror the existing in-crate test pattern

For binary-only Tauri crates, follow whatever convention the project
already uses for tests. Many projects already have `#[cfg(test)] mod`
modules inside the production tree (e.g. `corpus.rs` next to `mod.rs`).
Add a sibling for the integration-style test:

```rust
// in src/image_detection/mod.rs
#[cfg(test)]
mod corpus;            // existing grid-level tests
#[cfg(test)]
mod image_corpus;      // new image-level tests
```

```rust
// in src/image_detection/image_corpus.rs
#![cfg(test)]

use std::path::PathBuf;
use super::detect_position_sync;

#[test]
fn pipeline_matches_fixtures() {
    let model = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("resources/models/chess_pieces.onnx");
    let bytes = std::fs::read(/* fixture path via CARGO_MANIFEST_DIR */).unwrap();
    let result = detect_position_sync(bytes, model).unwrap();
    assert_eq!(/* ... */);
}
```

`CARGO_MANIFEST_DIR` resolves to the crate root at compile time, which
gives you a stable anchor for fixtures even though the test isn't in
`tests/`.

### 3. Optionally expose a model-path override for retrain workflows

If a Python (or other) harness wants to swap models without rebuilding,
add an env var override at the top of the model-path lookup:

```rust
fn model_path() -> PathBuf {
    if let Ok(override_path) = std::env::var("PAWN_IMAGE_CORPUS_MODEL") {
        return PathBuf::from(override_path);
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("resources/models/chess_pieces.onnx")
}
```

This pairs well with the `cargo-test-python-json-report-bridge` skill
for retrain-validate loops.

### 4. Feature-gate consistently with the production module

If the production module is feature-gated (e.g.
`#[cfg(feature = "onnx-detection")] mod image_detection;` in `main.rs`),
the test module inside it is automatically gated too. No additional
`#[cfg]` is needed on the test file itself beyond `#![cfg(test)]`.

Confirm by running both gated and ungated builds:

```bash
cargo check --no-default-features --features custom-protocol  # ungated
cargo test  --features onnx-detection                          # gated test
```

## Verification

- The async command's behaviour is unchanged: same `cargo run` outputs,
  same `tauri::specta` codegen, same error messages.
- `cargo test --features <gate>` runs the new in-crate test against
  real fixtures and produces deterministic results.
- Running with the env override (`PAWN_IMAGE_CORPUS_MODEL=/tmp/cand.onnx
  cargo test ...`) picks up the candidate model.

## Example: full refactor diff shape

Before:

```rust
pub async fn detect_position_bytes(
    image_data: Vec<u8>,
    app: tauri::AppHandle,
) -> Result<DetectionResult, Error> {
    let model_path = resolve_model_path(&app)?;
    let start = std::time::Instant::now();

    tokio::task::spawn_blocking(move || -> Result<DetectionResult, Error> {
        let board = board_detector::detect_board(&image_data)?;
        // ... 200 lines ...
        Ok(DetectionResult { /* ... */ })
    })
    .await
    .map_err(|e| Error::Custom(format!("Detection task panicked: {e}")))?
}
```

After:

```rust
pub(crate) fn detect_position_sync(
    image_data: Vec<u8>,
    model_path: PathBuf,
) -> Result<DetectionResult, Error> {
    let start = std::time::Instant::now();
    let board = board_detector::detect_board(&image_data)?;
    // ... 200 lines, un-indented ...
    Ok(DetectionResult { /* ... */ })
}

pub async fn detect_position_bytes(
    image_data: Vec<u8>,
    app: tauri::AppHandle,
) -> Result<DetectionResult, Error> {
    let model_path = resolve_model_path(&app)?;
    tokio::task::spawn_blocking(move || detect_position_sync(image_data, model_path))
        .await
        .map_err(|e| Error::Custom(format!("Detection task panicked: {e}")))?
}
```

Three changes:
1. Body of the closure becomes the body of `detect_position_sync` (un-
   indented one level, signature with concrete `PathBuf`).
2. The original async fn's body shrinks to two lines.
3. Visibility: `pub(crate)` on the sync helper so siblings (test
   modules in the same crate) can reach it without leaking it through
   the public API.

## Notes

- **Don't make the helper `pub`**: it's an internal seam, not a public
  surface. `pub(crate)` keeps the API clean while letting tests reach in.
- **Match existing test conventions**: if the project already has
  `#[cfg(test)] mod foo;` next to a module's `mod.rs`, follow that.
  Don't reach for `tests/` integration tests in a binary-only crate.
- **Don't add a `[lib]` target just for testing**: it changes the crate
  shape, breaks `cargo run`, complicates `tauri::Builder` registration,
  and confuses tooling. The in-crate `#[cfg(test)] mod` is lighter and
  achieves the same coverage.
- **`spawn_blocking` overhead is negligible**: the wrapper above adds
  microseconds. Don't worry about test-perf differences from sync vs
  async path.
- **Keep `start = Instant::now()` inside the sync helper** if you want
  the timing to reflect just the pipeline (which is what `pipeline_ms`
  in your result struct probably means). Moving it into the wrapper
  would include `spawn_blocking` setup time.

## References

- [Tauri 2 commands](https://v2.tauri.app/develop/calling-rust/)
- [Tauri 2 path API](https://v2.tauri.app/reference/javascript/api/namespacepath/)
- [`#[cfg(test)] mod` pattern](https://doc.rust-lang.org/book/ch11-03-test-organization.html)
- Related skills: `cargo-test-python-json-report-bridge` (driving a
  Rust integration test from a Python harness while capturing per-case
  outcomes — the natural pair for this extraction pattern).
