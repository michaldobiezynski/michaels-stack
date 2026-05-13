---
name: xcap-linux-system-deps
description: |
  Fix Linux build failures introduced by adding the xcap crate (Rust window
  capture, v0.9.x) to a Tauri/Rust project. Use when: (1) Linux CI/Docker
  build starts failing after `xcap = "0.9"` appears in Cargo.toml, (2) you
  see `The system library 'libpipewire-0.3' required by crate 'libspa-sys'
  was not found`, (3) bindgen panics with `Unable to find libclang`,
  (4) the final link stage fails with `unable to find library -lgbm` or
  missing `-lwayland-client` / `-lwayland-server` / `-lEGL` / `-lxcb`.
  Covers the three distinct missing-package errors that appear sequentially
  as each stage unlocks the next - fixing one reveals the next. Specifically
  targets Debian/Ubuntu Docker images used for cross-compile or CI.
author: Claude Code
version: 1.0.0
date: 2026-04-18
---

# xcap Linux System Dependencies

## Problem

Adding the `xcap` crate (or upgrading past 0.9.0) to a Tauri/Rust project
breaks Linux builds that were previously fine. The break manifests as
**three separate errors in sequence** - each one only appears after the
previous is fixed, because they happen at different build stages:

1. **pkg-config stage**: `libspa-sys` build script fails because
   `libpipewire-0.3` dev headers aren't installed.
2. **bindgen stage**: `libspa-sys` proceeds past pkg-config but panics
   because bindgen needs `libclang.so` at runtime.
3. **link stage**: Rust compiles everything, then `rust-lld` fails the
   final link for lack of `-lgbm`, `-lwayland-*`, `-lEGL`, `-ldrm`.

This is not documented in xcap's README. The root cause is that xcap
depends on `libwayshot-xcap`, which in turn pulls in `pipewire` →
`libspa-sys` → bindgen-generated bindings against the PipeWire/SPA C API,
plus Wayland/EGL/GBM/DRM for the Wayland capture backend.

## Context / Trigger Conditions

Use this skill when ANY of these apply during a Linux build (native or
Docker):

- `Cargo.toml` contains `xcap = "0.9..."` (or any version that pulls in
  `libwayshot-xcap`)
- Error: `The system library 'libpipewire-0.3' required by crate
  'libspa-sys' was not found.`
- Error: `thread 'main' panicked at ... Unable to find libclang:
  "couldn't find any valid shared libraries matching: ['libclang.so',
  'libclang-*.so', ...]"`
- Linker error: `rust-lld: error: unable to find library -lgbm` (or
  `-lwayland-client`, `-lwayland-server`, `-lEGL`, `-ldrm`, `-lxcb`)
- Base image: Ubuntu 22.04 / 24.04 / Debian bookworm (slim variants will
  also hit the `-dev` header errors)
- Build tool: `cargo-tauri` inside Docker, or a GitHub Actions job on
  `ubuntu-latest`

Note: macOS and Windows builds of xcap do **not** need these packages -
this is strictly a Linux concern.

## Solution

Add the following apt packages to your Dockerfile or CI setup step in
**one go** (don't fix errors one-at-a-time - you already know all three
layers):

```dockerfile
RUN apt-get update && apt-get install -y \
    # pkg-config target for libspa-sys build script
    libpipewire-0.3-dev libdbus-1-dev \
    # bindgen needs libclang at runtime
    libclang-dev clang \
    # final link: Wayland / EGL / GBM / DRM / XCB
    libgbm-dev libwayland-dev libegl1-mesa-dev libdrm-dev libxcb1-dev \
    && rm -rf /var/lib/apt/lists/*
```

Minimum set per failure stage, if you prefer to add incrementally:

| Stage | Package(s) | Fixes |
|-------|------------|-------|
| pkg-config | `libpipewire-0.3-dev`, `libdbus-1-dev` | `libspa-sys` build script |
| bindgen | `libclang-dev`, `clang` | `Unable to find libclang` panic |
| link | `libgbm-dev`, `libwayland-dev`, `libegl1-mesa-dev`, `libdrm-dev`, `libxcb1-dev` | `-lgbm`, `-lwayland-*`, `-lEGL`, `-ldrm`, `-lxcb` missing |

### GitHub Actions equivalent

```yaml
- name: Install xcap system deps (Linux)
  if: runner.os == 'Linux'
  run: |
    sudo apt-get update
    sudo apt-get install -y \
      libpipewire-0.3-dev libdbus-1-dev \
      libclang-dev clang \
      libgbm-dev libwayland-dev libegl1-mesa-dev libdrm-dev libxcb1-dev
```

## Verification

1. Run your full release build (`cargo tauri build` or equivalent) and
   check it compiles AND links. Compilation-only (`cargo check`) does
   **not** catch the link-stage error because the problem is in the final
   binary link, not in any individual crate's compile.
2. Grep the binary for the expected dynamic libs:
   `ldd target/release/<binary> | grep -E 'gbm|wayland|EGL|pipewire'` -
   all four should resolve to `/usr/lib/x86_64-linux-gnu/lib*.so.*`.
3. If building a Tauri bundle, confirm both the `.deb` and `.rpm`
   complete without link errors - they use the same binary.

## Example

Full Dockerfile that builds a Tauri app using xcap on Ubuntu 24.04:

```dockerfile
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    curl build-essential pkg-config \
    # Standard Tauri deps
    libwebkit2gtk-4.1-dev libappindicator3-dev librsvg2-dev patchelf \
    libssl-dev libglib2.0-dev libgtk-3-dev libsoup-3.0-dev \
    # xcap deps (this skill)
    libpipewire-0.3-dev libdbus-1-dev libxcb1-dev libclang-dev clang \
    libgbm-dev libwayland-dev libegl1-mesa-dev libdrm-dev \
    rpm \
    && rm -rf /var/lib/apt/lists/*

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g pnpm

RUN cargo install tauri-cli --version "^2"
```

## Notes

- **Why three errors, not one**: each stage runs in a different process -
  pkg-config (build.rs), bindgen (also build.rs but later), and the linker
  (after all .rlib files exist). Each probes the system independently, so
  a missing package at one stage doesn't skip the next.
- **libwayshot-xcap vs xcap-sys**: xcap 0.9+ uses `libwayshot-xcap` for
  Wayland, which is what pulls in pipewire/libspa-sys. Older xcap
  (≤ 0.7) used X11-only capture and needed only `libxcb1-dev`. If you
  pin xcap to < 0.8, the pipewire/bindgen/gbm packages are NOT required -
  but you lose Wayland support.
- **libclang needs both packages**: `libclang-dev` provides the headers,
  `clang` provides the runtime driver. Installing just one fails.
- **Alpine / musl**: this package list is for Debian/Ubuntu. Alpine uses
  different names (`clang-dev`, `pipewire-dev`, `libdrm-dev`, `mesa-dev`)
  and may need `LIBCLANG_PATH` set explicitly for bindgen.
- **Cross-compile with `cross`**: `cross`'s prebuilt images do NOT include
  these deps. You either use a custom Dockerfile (as above) or add a
  `[target.x86_64-unknown-linux-gnu]` `pre-build` section to `Cross.toml`.
- **Header-only isn't enough on ubuntu:*-slim**: slim variants drop
  `pkg-config` itself - make sure `pkg-config` is also in the apt list.
- **`CI=false` vs `CI=true`** (tangentially related): release scripts
  often export `CI=false` because Tauri build hates CI mode, but `pnpm
  install` then refuses to remove `node_modules` without a TTY. Fix by
  scoping: `CI=true pnpm install --frozen-lockfile` on install lines,
  let the outer `CI=false` apply to `tauri build`.

## References

- [xcap crate on crates.io](https://crates.io/crates/xcap) - 0.9+ uses
  libwayshot for Wayland capture
- [libwayshot-xcap source](https://github.com/nashaofu/libwayshot-xcap) -
  the transitive dep that pulls in pipewire/gbm/wayland
- [pipewire-rs bindings](https://pipewire.pages.freedesktop.org/pipewire-rs/pipewire/) -
  how libspa-sys bindgen-generates against PipeWire headers
- [rust-bindgen requirements](https://rust-lang.github.io/rust-bindgen/requirements.html) -
  why bindgen needs libclang at build time
- [Tauri Linux prerequisites](https://tauri.app/start/prerequisites/#linux) -
  standard Tauri Linux deps (this skill adds the xcap-specific extras)
