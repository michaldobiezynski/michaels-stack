---
name: swift-foundationmodels-macros-plugin-not-found-clt
description: |
  Fix for `swift build` / `make app` failing on a Mac that has only the Command
  Line Tools (no full Xcode) with "external macro implementation type
  'FoundationModelsMacros.GenerableMacro' could not be found for macro
  'Generable(description:)'; plugin for module 'FoundationModelsMacros' not found"
  (same for 'GuideMacro' / '@Guide'), followed by a cascade of misleading errors:
  "requires that X conform to 'Generable'", "generic struct 'Response' requires
  that X conform to 'Generable'", "cannot infer contextual base in reference to
  member", "no 'async' operations occur within 'await' expression", "no calls to
  throwing functions occur within 'try' expression". Use when: (1) building any
  Swift project that imports FoundationModels (Apple Intelligence, macOS 26 /
  iOS 26) and `xcode-select -p` prints /Library/Developer/CommandLineTools,
  (2) the project's CI is green on a macos-26 runner but fails locally,
  (3) you only need to RUN the app and the clone's HEAD sits on a notarised
  GitHub release tag. Root cause: the FoundationModelsMacros compiler plugin
  ships only inside Xcode's toolchain; the CLT SDK has the framework but the CLT
  toolchain lacks the plugin. Fix: install Xcode 26 and xcode-select it.
  Workaround: run the matching notarised release instead of building.
author: Claude Code
version: 1.0.0
date: 2026-09-02
---

# FoundationModels macros need full Xcode, not the Command Line Tools

## Problem

A Swift package that uses Apple's FoundationModels framework (`@Generable`,
`@Guide`, `LanguageModelSession.respond(to:generating:)`) fails to compile
on a machine with only the Command Line Tools installed. The first error
names the real cause, but it is buried under thirty or more downstream
type-inference errors that look like source bugs, so the natural reaction is
to start reading the failing files instead of the toolchain.

## Context / Trigger Conditions

- `swift build` (any config) or a Makefile wrapping it fails; `swift test`
  of a pure-logic target may still pass because only the app target imports
  FoundationModels.
- Error list (sort it with `| grep error: | sort -u`) contains, per macro
  site:
  ```
  error: external macro implementation type 'FoundationModelsMacros.GenerableMacro'
    could not be found for macro 'Generable(description:)'; plugin for module
    'FoundationModelsMacros' not found
  error: external macro implementation type 'FoundationModelsMacros.GuideMacro'
    could not be found for macro 'Guide(description:)'; ...
  ```
  and then, for every use of the annotated types:
  ```
  error: instance method 'respond(to:generating:includeSchemaInPrompt:options:)'
    requires that 'Foo.Verdict' conform to 'Generable'
  error: generic struct 'Response' requires that 'Foo.Verdict' conform to 'Generable'
  error: cannot infer contextual base in reference to member 'instruction'
  warning: no 'async' operations occur within 'await' expression
  warning: no calls to throwing functions occur within 'try' expression
  ```
- `xcode-select -p` prints `/Library/Developer/CommandLineTools`, and
  `xcodebuild -version` says "tool 'xcodebuild' requires Xcode".
- The project's own CI passes on `runs-on: macos-26` (which has Xcode).

## Solution

### Diagnose in one call

```bash
xcode-select -p
ls "$(xcrun --show-sdk-path)/System/Library/Frameworks/" | grep FoundationModels   # framework IS there
ls /Library/Developer/CommandLineTools/usr/lib/swift/host/plugins/               # plugin is NOT
find /Library/Developer /Applications -maxdepth 8 -iname '*FoundationModelsMacros*'
```

On a CLT-only machine the plugins directory holds only
`libObservationMacros.dylib`, `libSwiftMacros.dylib` and `testing/`. The
FoundationModelsMacros plugin lives at
`Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib/swift/host/plugins/`
and nowhere else. A swift.org toolchain does not help: the plugin is
Apple-proprietary and is not part of the open-source toolchain.

### Fix: install Xcode 26 and point the toolchain at it

```bash
# after installing Xcode from the App Store or developer.apple.com/download
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
sudo xcodebuild -license accept
swift build -c release   # or the project's make target
```

### Workaround when you only need to run the app

If the clone's HEAD is exactly a release tag, the project's notarised
release bundle is the same source already built, signed and notarised by
CI. Verify and use it in place of the local build output:

```bash
git fetch --tags --quiet && git describe --tags --exact-match HEAD   # e.g. v0.30.0
curl -fsSL -o /tmp/App.zip https://github.com/OWNER/REPO/releases/download/<tag>/App.zip
ditto -x -k /tmp/App.zip /tmp/rel && spctl -a -vv -t exec /tmp/rel/App.app   # want: accepted, Notarized Developer ID
mkdir -p build && ditto /tmp/rel/App.app build/App.app && open build/App.app
```

Say explicitly in the report that this is the release bundle, not a
source build. If HEAD is ahead of the tag, list the delta with
`git log --oneline <tag>..HEAD` so the user knows what the release lacks.

### If you own the build script

Gate FoundationModels code paths on Xcode being active, not on the
framework existing in the SDK, because the CLT SDK ships the framework
without the macro plugin. Check `xcode-select -p` resolves inside an
`Xcode.app`, or probe for the plugin dylib, and fall back or fail early
with a clear message.


### Partial typecheck of the app target without the plugin (added 03/09/2026)

You can still typecheck every other app file: list `Sources/App/**/*.swift`
minus the files that `import FoundationModels` into a response file, then run
`swiftc -typecheck -swift-version 5 -sdk "$(xcrun --show-sdk-path)" -target arm64-apple-macos14 -I .build/arm64-apple-macosx/debug/Modules $(cat files.txt)`
(the library module must already be built by `swift build`). Discard errors
that name the excluded types; anything else is a real error in your change.
Pure-logic tests can run through the XCTest shim described in
`swift-xctest-shim-runner-clt-only`.

## Verification

- After installing Xcode: `ls "$(xcode-select -p)/Toolchains/XcodeDefault.xctoolchain/usr/lib/swift/host/plugins/" | grep -i FoundationModels` lists the plugin, and the build's error list no longer contains "plugin for module".
- For the release workaround: `spctl` prints `accepted` and `source=Notarized Developer ID`; the app's `--selftest` (if it has one) passes; `pgrep -x App` shows it running.

## Example

Pawvis (alexandriax/pawvis, 02/09/2026), macOS 26.6.2, Swift 6.3.3, SDK 26.5,
CLT only. `make app` failed after 51 s with 30+ errors across
`WakeRescuer.swift`, `AppNameRescuer.swift`, `AutopilotEngine.swift`; all
traced to three `@Generable` and five `@Guide` sites. HEAD was exactly
`v0.30.0`, so the notarised release zip was verified with `spctl`, copied to
`build/Pawvis.app` (the path `make app` would have produced), passed the
bundle's own `--selftest` (131 checks), and ran.

## Notes

- `swift test` can stay green while `swift build` of the app target fails,
  because packages usually keep FoundationModels out of the unit-tested
  core target. Do not read a green test run as "the toolchain is fine".
- The same shape of failure applies to any Apple-only macro plugin that
  is not in the CLT list above; check the plugins directory first whenever
  the first error says "plugin for module ... not found".
- Installing Xcode is a large download (10 GB+) and a system-state change;
  when running autonomously, deliver the release workaround and give the
  user the Xcode commands rather than installing it unasked.
- A local source build will be ad-hoc signed unless a Developer ID or
  Apple Development identity is in the keychain, so TCC grants
  (Accessibility, Screen Recording) are dropped on every rebuild.

## References

- [Handy issue #1448: build.rs enables Apple Intelligence on Command-Line-Tools-only machines](https://github.com/cjpais/Handy/issues/1448) (same root cause, gating fix)
- [Swift Forums: importing macros without SwiftPM](https://forums.swift.org/t/how-to-import-macros-using-methods-other-than-swiftpm/66645?page=2) (how external macro plugins are located)
- [TCA discussion: "External macro implementation type could not be found"](https://github.com/pointfreeco/swift-composable-architecture/discussions/3419) (the generic form of the error)
