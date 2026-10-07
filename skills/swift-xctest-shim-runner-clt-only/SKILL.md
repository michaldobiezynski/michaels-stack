---
name: swift-xctest-shim-runner-clt-only
description: |
  Run a SwiftPM package's real XCTest test files on a Mac that has only the
  Command Line Tools (no Xcode, so `swift test` fails with "no such module
  'XCTest'"), by compiling them against a tiny shim module named XCTest in a
  scratch package with a generated runner. Use when: (1) `swift test` says
  "error: no such module 'XCTest'" and `xcrun --find xctest` fails, (2) you
  need a red/green loop for pure-logic targets before CI can run, (3) the
  app target cannot build either (FoundationModels macro plugin missing) and
  you still want the library tests exercised. Also covers a partial
  `swiftc -typecheck` of the app module with the unbuildable files excluded.
  Verified 03/09/2026 on 193 XCTest cases of alexandriax/pawvis.
author: Claude Code
version: 1.0.0
date: 2026-09-03
---

# XCTest shim runner for CLT-only Macs

## Problem

The Command Line Tools ship no XCTest (and no Swift Testing) module, so
`swift test` dies at emit-module time for every test target. Installing
Xcode (10 GB+) is the real fix, but an autonomous session often cannot do
that. The library under test usually compiles fine; only the harness is missing.

## Context / Trigger Conditions

- `swift test` output: `error: no such module 'XCTest'` (first test file, line 1).
- `xcrun --find xctest` prints `unable to find utility "xctest"`.
- `xcode-select -p` is `/Library/Developer/CommandLineTools`; `ls /Applications/Xcode*.app` is empty.
- The package's test files are plain XCTest (`import XCTest`, `@testable import Lib`).

## Solution

Scratch package (outside the repo) with three targets: a copy of the library
target, a module literally named `XCTest` (the shim), and an executable runner.

1. `Package.swift` targets: `.target(name: "Lib")`, `.target(name: "XCTest")`,
   `.executableTarget(name: "xctrun", dependencies: ["Lib", "XCTest"])`. Keep the
   library's `swiftLanguageMode` so `@testable import` (debug builds enable
   testability) and internal helpers resolve.
2. Shim `Sources/XCTest/XCTest.swift`, essentials:
   - `@_exported import Foundation` (the real XCTest re-exports it; repo test
     files rely on `TimeInterval`, `Data` without importing Foundation).
   - `open class XCTestCase { public required init() {}; open func setUp() {} }`
   - free functions `XCTAssertTrue/False/Equal/NotEqual/Nil/NotNil/GreaterThan/
     GreaterThanOrEqual/LessThan/LessThanOrEqual`, an `XCTAssertEqual(_:_:accuracy:)`
     overload for Double, `XCTFail`, and `XCTUnwrap` that throws. Each prints
     `FAIL line N` and bumps a global counter.
3. Runner script (zsh: `setopt +o nomatch` first, or an empty glob aborts it):
   rsync the library sources in, copy the requested test files plus shared
   fixtures (e.g. `SyntheticHands.swift`), then generate `main.swift`:
   - class name from `grep -o 'final class [A-Za-z0-9_]*'`;
   - methods from `grep -E '^[[:space:]]*func test[A-Za-z0-9_]*\(\)'` (instance,
     zero-arg only: a `static func testConfig()` helper is not a test);
   - per test: `let t = Cls(); t.setUp(); let call: () throws -> Void = t.m; do { try call() } catch {...}`
     (the function-reference cast keeps `try` legal for non-throwing tests
     without "no calls to throwing functions" warnings).
4. `rm -f .build/debug/xctrun` before `swift build --product xctrun`, and refuse
   to run if the binary is absent: otherwise a failed build silently reruns the
   stale binary and prints an old "ALL GREEN". Grep build output for `error:`
   with the colon; plain `error` also matches "no errors are thrown" warnings.

Partial typecheck of an app target whose FoundationModels files cannot compile:
`find Sources/App -name '*.swift' | grep -vE 'FileA|FileB' > files.txt`, then
`swiftc -typecheck -swift-version 5 -sdk "$(xcrun --show-sdk-path)" -target arm64-apple-macos14 -I .build/arm64-apple-macosx/debug/Modules $(cat files.txt)`
and drop every error mentioning the excluded types. Build the list to a file:
inline `$(find ...)` word-splitting corrupted the last path once.

## Verification

- Runner prints one `PASS Class.method` per test and `ALL GREEN`; a deliberately
  broken assertion prints `FAIL line N` and a non-zero exit.
- When Xcode later became available, the real `swift test` agreed with the shim
  on every case (765 tests, 0 failures).

## Notes

- `swift build` piped to `tail` masks failure; check for the literal
  `Build complete` string, not the exit code of the pipeline.
- The shim is not XCTest: no `expectation`, `XCTAssertThrowsError`, `setUpWithError`,
  `tearDown`. Add stubs as the suite needs them; a missing one is a compile error.
- Related: `swift-foundationmodels-macros-plugin-not-found-clt` (why the app target
  itself cannot build without Xcode).
