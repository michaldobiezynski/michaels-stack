---
name: cargo-test-python-json-report-bridge
description: |
  Pattern for running a Rust integration test from a Python harness while
  capturing per-case outcomes (not just pass/fail). Use when: (1) you have
  a Rust test that iterates over fixtures and asserts each matches a
  baseline (ratchet corpus, regression manifest), (2) you want a Python
  script to run that test with varying inputs (different model files,
  configs, feature flags) and diff the outcomes between runs,
  (3) "cargo test --lib" returns "no library targets found in package"
  because the crate is a Tauri binary / bin-only crate and you need
  --bin to select it, (4) stdout parsing of test output is fragile and
  you want structured per-case data. Covers two env-var hooks (one for
  swappable input, one for JSON report path), the binary-crate --bin
  requirement, and a Python orchestrator skeleton that runs cargo twice
  and diffs the fixture-by-fixture reports.
author: Claude Code
version: 1.0.0
date: 2026-04-24
---

# Cargo-test → Python harness bridge via env-overrides and a JSON report

## Problem

You have a Rust test that runs a pipeline over many fixtures and asserts
each matches a manifest-driven expectation (an ML regression corpus, a
parser conformance suite, a pixel-comparison image suite). Good:

```rust
#[test]
fn image_corpus_matches_manifest_expectations() {
    for fixture in manifest.fixtures {
        let got = detect(fixture.input);
        if got != fixture.expected && fixture.expected_pass {
            mismatches.push(regression_msg);
        }
        // ...
    }
    if !mismatches.is_empty() { panic!(...); }
}
```

Now you want a Python harness to:

1. Run this test against **model A**, capture per-fixture outcomes.
2. Run it against **model B**, capture per-fixture outcomes.
3. Diff the two runs fixture-by-fixture: `newly_passing`, `newly_failing`,
   `unchanged_pass`, `unchanged_fail`.

Three obstacles:

- The test has a hardcoded input path (`env!("CARGO_MANIFEST_DIR").join(...)`).
  Can't swap at runtime.
- The test's stdout only reports on mismatches, not successes. Parsing
  what DID pass from the panic text is fragile.
- `cargo test --lib` fails with `no library targets found in package`
  when the crate is a Tauri binary, a CLI, or any bin-only setup.

## Context / Trigger conditions

- `cargo test --lib` returns `error: no library targets found in package`.
- You find yourself grep-parsing cargo test stdout for per-case outcomes.
- You want to A/B-test two configs, two models, or two implementations
  against the same fixture corpus.
- The test already has a pass/fail concept but you need finer-grained
  "which specific cases changed" telemetry.

## Solution

Three pieces: (1) two env hooks on the Rust test, (2) the right cargo
incantation, (3) a Python orchestrator that wraps both and diffs.

### 1. Env-override for the swappable input

Add a runtime env-var check in front of the hardcoded path. Three lines:

```rust
fn model_path() -> PathBuf {
    // Override hook for external harnesses: lets us point the test at
    // an alternate input without overwriting the shipped one.
    if let Ok(override_path) = std::env::var("PAWN_IMAGE_CORPUS_MODEL") {
        return PathBuf::from(override_path);
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("resources").join("models").join("chess_pieces.onnx")
}
```

Namespace the env var with your project's prefix so it doesn't collide.
Document the hook in a comment pointing at the consumer.

### 2. JSON-report hook

Inside the fixture loop, build a `Vec<serde_json::Value>` of per-case
outcomes regardless of pass/fail. After the loop, if a second env var
is set, write the vec to that file:

```rust
let mut report_rows: Vec<serde_json::Value> = Vec::with_capacity(manifest.fixtures.len());

for fixture in &manifest.fixtures {
    let matches = detected == fixture.expected;
    report_rows.push(serde_json::json!({
        "slug": fixture.slug,
        "expected_pass": fixture.expected_pass,
        "detected": detected,
        "matches_expected": matches,
    }));
    // ... existing mismatch detection ...
}

if let Ok(report_path) = std::env::var("PAWN_IMAGE_CORPUS_REPORT") {
    let report = serde_json::json!({
        "total": manifest.fixtures.len(),
        "mismatches": mismatches.len(),
        "fixtures": report_rows,
    });
    let _ = std::fs::write(&report_path, serde_json::to_string_pretty(&report).unwrap());
}

if !mismatches.is_empty() {
    panic!("{} mismatches", mismatches.len());  // still panic for CI
}
```

Writing BEFORE the panic is deliberate: the report is always emitted
even when the test fails. Writing to a FILE (not stdout) keeps the
test's normal output clean — external harnesses opt-in by setting the
env var.

### 3. --bin selector for binary-only crates

If `cargo test --lib` says `no library targets found`, the crate has
only a `[[bin]]` target. Tauri apps, CLIs, and binary utilities all
behave this way. Select the binary explicitly:

```bash
cargo test --bin <crate-name> <test-name-filter> -- --nocapture
```

Find the binary name via `cargo metadata | jq '.packages[0].targets[]
| select(.kind[] | contains("bin")) | .name'` or by looking at
`[[bin]]` in `Cargo.toml`.

### 4. Python orchestrator skeleton

```python
import json, os, subprocess, tempfile
from pathlib import Path

def run_corpus(model_path: Path) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        report_path = Path(tmp.name)
    try:
        env = {
            **os.environ,
            "PAWN_IMAGE_CORPUS_MODEL": str(model_path.resolve()),
            "PAWN_IMAGE_CORPUS_REPORT": str(report_path),
        }
        result = subprocess.run(
            ["cargo", "test", "--manifest-path", "path/to/Cargo.toml",
             "--features", "your-feature",
             "--bin", "your-crate-name",
             "image_corpus_matches_manifest_expectations",
             "--", "--nocapture"],
            env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, check=False,  # don't raise on non-zero exit
        )
        if not report_path.exists() or report_path.stat().st_size == 0:
            raise SystemExit(f"report not written. stderr: {result.stderr[-500:]}")
        with report_path.open() as f:
            return json.load(f)
    finally:
        report_path.unlink(missing_ok=True)

def diff(old: dict, new: dict) -> dict:
    old_by_slug = {f["slug"]: f for f in old["fixtures"]}
    newly_passing, newly_failing = [], []
    for nrow in new["fixtures"]:
        orow = old_by_slug.get(nrow["slug"])
        if orow is None: continue
        o_ok = orow["detected"] == orow["expected_placement"]
        n_ok = nrow["detected"] == nrow["expected_placement"]
        if not o_ok and n_ok: newly_passing.append(nrow["slug"])
        if o_ok and not n_ok: newly_failing.append(nrow["slug"])
    return {"newly_passing": newly_passing, "newly_failing": newly_failing}
```

## Verification

1. Run cargo test without env vars — behaves exactly as before, no
   file written.
2. Run cargo test with `PAWN_IMAGE_CORPUS_REPORT=/tmp/out.json` — JSON
   written to that path regardless of pass/fail.
3. Run the Python orchestrator with the same model path twice — diff
   must be all-zero (no flips).
4. Point the orchestrator at a deliberately-broken variant (random
   weights, empty config) — diff must show massive `newly_failing`,
   zero `newly_passing`.

## Example

pawn-au-chocolat (chess screenshot detection, Tauri+Rust+Python):

- `src-tauri/src/image_detection/image_corpus.rs` — the Rust test with
  both env hooks.
- `scripts/retrain-yolo/validate.py` — the Python orchestrator using
  `--compare OLD NEW`, printing per-slug diff, exit code 1 on regression.
- Baseline run: 56/70 pass, 0 regressions, 0 ratchets.
- Smoke model (1-epoch training on 20 images) run through the same
  harness: 0/70 pass, 56 regressions, 0 ratchets, exit 1.

Full pipeline runs end-to-end in ~100s on the 70-fixture corpus.

## Notes

- **Don't parse cargo stdout.** It's tempting when you see the panic
  text "REGRESSION: ..." but the format is unstable and doesn't cover
  the silently-passing cases.
- **Pretty-print the JSON.** Diffing reports by eye during development
  is invaluable; a one-line JSON dump is painful. `to_string_pretty` is
  the right default.
- **Name env vars with a project prefix.** `CORPUS_MODEL` would collide
  with other tools; `PAWN_IMAGE_CORPUS_MODEL` is obviously scoped.
- **The override should default to the committed path.** Never assume
  the env var is set; the Rust test should still work for vanilla
  `cargo test`.
- **--bin works for binary crates; integration tests use --test.** If
  your test lives in `tests/*.rs`, use `--test <filename-without-.rs>`.
  If it lives alongside `src/main.rs` with `#[cfg(test)]`, use `--bin
  <crate-name>`.
- **tempfile with delete=False then unlink in finally.** On macOS/Linux
  passing a delete=True NamedTemporaryFile to cargo sometimes closes
  the handle too early; opening for write then letting the subprocess
  overwrite is safer.

## References

- [Cargo book: Selecting tests to run](https://doc.rust-lang.org/cargo/commands/cargo-test.html#target-selection)
  — `--lib`, `--bin`, `--test`, `--example` flags.
- [serde_json macros](https://docs.rs/serde_json/latest/serde_json/macro.json.html)
  — `json!` macro for building reports inline.
- Sibling skill: `detection-greedy-legality-repair-by-confidence-demotion`
  — describes the ratchet-discipline manifest pattern this bridge is
  designed to feed into.
