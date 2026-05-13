---
name: ort-apple-silicon-kleidiai-leak-coreml-fix
description: |
  Fix for severe memory leak in ONNX Runtime (`ort` crate, version 2.0.0-rc.12
  and adjacent) on macOS Apple Silicon: the CPU execution provider routes
  convolution ops through ARM's KleidiAI matmul library, and
  `ArmKleidiAI::MlasConv` retains ~91 KB per call indefinitely. In tight
  inference loops with VARYING inputs (image-detection corpus tests,
  any-frame-different YOLO/CNN inference) RSS climbs ~5 MB per inference,
  hitting multi-GB after a few thousand iterations. Same-input loops do
  NOT show the leak (KleidiAI reuses the warm cache).

  Use when: (1) Rust process using `ort` 2.x on Apple Silicon (M1/M2/M3/M4)
  shows linear RSS growth in inference loops, (2) `heap <pid>` output
  attributes mid-size mallocs to `ArmKleidiAI::MlasConv` or
  `MlasConv`, (3) same-fixture loops are clean but varying-fixture loops
  leak, (4) `Session::with_memory_pattern(false)`, intra-threads(1),
  session-recycling, mimalloc all fail to bound the growth.

  Solution: register CoreML execution provider on macOS so convolutions
  route through Apple's Core ML framework instead of MlasConv. Bypasses
  KleidiAI entirely. CPU EP remains as fallback for unsupported ops.

  Also documents the diagnostic technique: bisect with isolated stress
  tests, then `heap(1)` on a long-running process to attribute leaks
  to a specific C++/native symbol.
author: Claude Code
version: 1.0.0
date: 2026-05-12
---

# ORT + Apple Silicon `ArmKleidiAI::MlasConv` memory leak → CoreML EP fix

## Problem

A Rust process using the `ort` crate (Microsoft ONNX Runtime bindings) for
inference on Apple Silicon shows linear RSS growth across tight inference
loops. Symptoms in the pawn-au-chocolat image-corpus test:

- 11,757 fixtures × 1 inference each
- Pre-fix RSS climbed from ~280 MB at warm-up to 19 GB at 2 hours
- Growth rate ~140-150 MB/min, completely linear
- System swapping kicked in around the 30-minute mark
- Same workload completed cleanly on a fresh process (no accumulator)
  but blew past available memory in the long-running test

The leak is invisible in single-fixture stress loops (calling the SAME
fixture N times shows zero growth) because KleidiAI's per-call cache
reuses warm allocations. It only manifests when consecutive calls have
DIFFERING input data, which causes KleidiAI to allocate fresh kernel
workspaces that don't get freed.

## Context / Trigger Conditions

- Rust binary on macOS arm64 (M1/M2/M3/M4) using `ort = "2.0.0-rc.12"`
  or any ort 2.x that ships ONNX Runtime ≥ 1.20 (when KleidiAI was added).
- Tight inference loop: thousands of `Session::run` calls back-to-back.
- Inputs vary call-to-call (image frames, document patches, etc.); a
  fixed-input loop would not surface the leak.
- `heap <pid>` output ranked by COUNT shows a row like:
  ```
  10736  979421216  91227.8  malloc in ArmKleidiAI::MlasConv(...)
                                                              ^^^^^^^^^^^^^
                                            ~91 KB per call, ~10k outstanding
  ```
- The leak survives **all** of these mitigations (each verified ineffective
  in this codebase before landing the CoreML fix):
  - `SessionBuilder::with_memory_pattern(false)`
  - `SessionBuilder::with_intra_threads(1)`
  - Session recycling (drop + re-`commit_from_file` every N calls)
  - mimalloc as the global allocator
  - Reusing the input `Array4<f32>` buffer across calls
  - Removing per-call debug PNG dumps

Because no allocator-level or session-level workaround bounds the leak,
it's not in ORT's session arena nor in macOS allocator retention — it's
inside the KleidiAI workspace allocator, which is process-scoped and
opaque to ORT's session lifecycle.

## Diagnostic technique (bisection + heap)

If you don't already have a smoking-gun heap report, run the workload
under `MallocStackLogging=1` and use `heap(1)`:

1. **Isolate via stress tests.** Write progressively-deeper isolation
   stress tests as `#[ignore]`'d cargo tests so they don't run in CI:
   ```
   - leak_stress (same fixture, N iters): baseline
   - leak_stress_only_read (different fixtures, fs::read only)
   - leak_stress_read_and_decode (+ PNG decode)
   - leak_stress_through_resize (+ image resize)
   - leak_stress_through_yolo (+ Session::run)
   ```
   Run each at PAWN_LEAK_STRESS_ITERS=300 and watch RSS via
   `ps -o rss=`. The leak fires when you reach the offending step.

2. **Attach `heap` mid-run.** Once you've narrowed to the leaky step,
   build the test binary, run it backgrounded with `MallocStackLogging=1`,
   and after enough iterations to accumulate noticeable retention:
   ```
   PAWN_LEAK_STRESS_ITERS=500 MallocStackLogging=1 \
     ./target/debug/deps/<crate>-<hash> <test_name> \
     --include-ignored --nocapture 2>&1 > /tmp/stress.out &
   STRESS_PID=$!
   sleep 120   # let RSS climb so the leak signal is large
   heap $STRESS_PID 2>&1 | head -80
   kill $STRESS_PID
   ```

3. **Read the heap report top by COUNT.** The first few rows show which
   symbol is retaining the most allocations. A row like
   `10736 979421216 91227.8 malloc in <SymbolName>` means 10,736
   outstanding mallocs averaging 91 KB each, all attributed to that
   call site. That's your leak.

The bisection lets you DISCARD upstream parts of the pipeline (don't
spend hours profiling the test scaffolding when the leak is in
`session.run`). The `heap` step then pins the EXACT native symbol.

## Solution

Register the CoreML execution provider on macOS so convolutions route
through Apple's Core ML framework. CoreML uses Apple Neural Engine /
GPU / CPU adaptively — none of those paths use KleidiAI.

### Cargo.toml

```toml
[dependencies]
ort = { version = "2.0.0-rc.12", features = ["download-binaries", "coreml"] }
```

### Session builder

```rust
let mut builder = ort::session::Session::builder()?;

#[cfg(target_os = "macos")]
{
    builder = builder.with_execution_providers([
        ort::execution_providers::CoreMLExecutionProvider::default().build()
    ])?;
}

let session = builder
    .with_optimization_level(ort::session::builder::GraphOptimizationLevel::Level3)?
    .commit_from_file(model_path)?;
```

The order matters: register CoreML BEFORE setting other options. ORT
registers EPs in the order they're provided; CoreML will claim ops it
supports, and the CPU EP (still implicitly registered) handles the
remainder.

## Verification

Re-run the stress loop. RSS should plateau early and stay flat:

```
[yolo] BASELINE        RSS_MB=28
[yolo] iter=  0        RSS_MB=362   (warm-up)
[yolo] iter=  75       RSS_MB=270   (decreasing — allocator returning)
[yolo] iter=  100-1000 RSS_MB=270-272  (stable)
```

vs pre-fix at the same iteration counts: 800 MB at iter=75, 1.7 GB at
iter=200, climbing without bound.

Also verify detection accuracy is preserved on a regression test set —
CoreML and CPU EPs can differ slightly in operator implementations,
but for standard YOLOv8-style models the outputs are typically
indistinguishable.

## Example

In pawn-au-chocolat, the image_corpus test went from 2+ hours (and
killing the host with swap pressure) to 30-40 minutes with stable RSS
under 500 MB. Commit message excerpt:

```
fix: (piece_detector) use CoreML execution provider on macOS to bound
ORT memory leak

Root cause diagnosed via heap(1) on a 200-iteration stress loop: the
ORT 2.0.0-rc.12 CPU execution provider on Apple Silicon routes
convolution ops to ArmKleidiAI. heap report at iter 200 showed 10,736
outstanding mallocs totalling 979 MB all attributed to a single
symbol -- ArmKleidiAI::MlasConv. The KleidiAI kernel retains ~91 KB
per call and never releases it.

Fix: register the CoreML execution provider on macOS so YOLO
convolutions route through Apple's Core ML framework instead of
MlasConv.
```

## Notes

- **Platform-gate the EP registration.** Only macOS builds get CoreML;
  Linux/Windows builds continue using the CPU EP, which doesn't have
  the KleidiAI path (KleidiAI is ARM64-specific) and doesn't leak.
- **Coreml feature pulls in Core ML at build time.** Build size grows
  slightly. On macOS this is fine because Core ML is part of the OS
  framework.
- **Operator coverage.** CoreML supports most standard YOLO operators
  (Conv, MaxPool, Resize, NMS, etc.). For exotic models, check the
  ONNX-CoreML operator coverage list before relying on this fix.
- **Don't conflate this with ORT's session-arena memory growth.** A
  separate, similarly-shaped leak exists when the ORT session's memory
  pattern is mismatched with input shapes — that one is fixable with
  `with_memory_pattern(false)`. The KleidiAI leak is INSIDE the
  KleidiAI kernel and untouched by any SessionBuilder option.
- **Apple has shipped KleidiAI fixes upstream.** Newer versions of
  ONNX Runtime (>1.24, post-2026) may have addressed this. Check the
  ORT release notes and the kleidiai-microkernels repo before assuming
  this skill still applies on later ort versions.

## References

- ONNX Runtime CoreML execution provider: https://onnxruntime.ai/docs/execution-providers/CoreML-ExecutionProvider.html
- ARM KleidiAI library: https://gitlab.arm.com/kleidi/kleidiai
- ort crate (Rust bindings): https://github.com/pykeio/ort
- macOS `heap(1)` man page: `man heap`
