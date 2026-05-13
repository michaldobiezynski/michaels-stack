---
name: remotion-public-relative-symlink-404
description: >
  Fix Remotion render aborting at frame 0 with "Received a status code of 404
  while downloading file http://localhost:3000/public/<asset>" when the
  public/ folder contains relative symlinks to source assets stored elsewhere
  on disk. Use when: (1) `npx remotion render` fails at frame 0 with a 404
  on an asset referenced via `staticFile()`, (2) the error body mentions a
  path like `/var/folders/.../remotion-webpack-bundle-<hash>/public/<asset>`
  that does not exist, (3) `ls -l public/` shows the asset is a relative
  symlink (e.g. `asset.mp4 -> ../../asset.mp4`), (4) Studio preview works
  but `remotion render` does not, (5) you want to reference source assets
  without copying or modifying them. Root cause: Remotion's bundler copies
  public/ into a temp bundle dir and forwards symlinks verbatim, so
  relative targets fail to resolve from the new location. Fix: replace
  relative symlinks with hard links (`ln` without `-s`). Absolute-path
  symlinks or `--public-dir` also work.
trigger: >
  Use when a Remotion render fails with a 404 on a staticFile() asset and
  the asset is a relative symlink in public/. Also triggers on: "remotion
  404", "remotion-webpack-bundle path could not be found", "remotion
  symlink public folder".
user_invocable: false
---

# Remotion public/ relative symlink 404

## Problem

`npx remotion render` aborts at frame 0 with a 404 on a `staticFile()` asset
that clearly exists in `public/`. Symptom typically only reproduces during
render, not during Studio preview.

## Trigger conditions

The render output contains:

```
An error occurred while rendering frame N:
 Error  Received a status code of 404 while downloading file
 http://localhost:3000/public/<asset>.
The response body was:
---
{"statusCode":404,"message":"The requested path
(/var/folders/.../remotion-webpack-bundle-<hash>/public/<asset>)
could not be found"}
---
```

And `ls -l public/` shows:

```
asset.mp4 -> ../../asset.mp4    (a relative symlink)
```

## Root cause

When Remotion bundles a project it copies `public/` into a temporary bundle
directory at `/var/folders/.../remotion-webpack-bundle-<hash>/public/`. The
bundler forwards symlinks rather than resolving them. A relative symlink
like `../../asset.mp4` is valid from the original location but points to
nothing inside the temp bundle directory. The embedded HTTP server then
serves a 404 for `/public/asset.mp4` and the renderer aborts.

## Fix

Replace relative symlinks with **hard links** — they copy as regular files
and share inodes with the originals on the same filesystem (no disk
duplication, originals untouched):

```bash
cd your-project/remotion/public
rm -f asset.mp4
ln ../../asset.mp4 asset.mp4        # no -s flag => hard link
ls -l                                 # link count becomes 2+
```

Rerun:

```bash
npx remotion render <Composition> <out>
```

Render now progresses past frame 0.

## Alternative fixes

- **Absolute-path symlink**: `ln -s "$(realpath ../../asset.mp4)" asset.mp4`
  survives the copy because the absolute target is valid from anywhere.
- **File copy**: `cp ../../asset.mp4 asset.mp4` — simplest but duplicates
  the file on disk.
- **Custom public dir**: `npx remotion render --public-dir=/abs/path/to/source`
  points Remotion directly at the source folder, skipping the copy of
  `public/` entirely.

## Verification

```bash
# Inode check - both entries share the same inode number:
ls -li remotion/public/asset.mp4 source/asset.mp4

# Render check - no 404s, completes past frame 0:
npx remotion render Concat ../final.mp4
```

The `st_nlink` value (link count) shown by `ls -l` on a hard-linked file is
≥2.

## Notes

- Hard links only work on the **same filesystem**. If source assets are on
  an external drive or network mount, use an absolute symlink or
  `--public-dir`.
- macOS and Linux `ln` without `-s` creates a hard link.
- Symlinks that fail during `remotion render` may still work under
  `remotion studio` because the dev server can serve files directly from
  the project's `public/` without copying first. "Works in studio, fails
  in render" is a strong hint this is the bug.
- The bundler's temp directory path includes `remotion-webpack-bundle-` as
  a prefix — grep that substring in error output to recognise the pattern
  quickly.

## References

- [Remotion: public directory](https://www.remotion.dev/docs/terminology/public-dir)
- [Remotion: importing assets](https://www.remotion.dev/docs/assets)
- [Remotion: bundle terminology](https://www.remotion.dev/docs/terminology/bundle)
- [Remotion bundler source (bundle.ts)](https://github.com/remotion-dev/remotion/blob/main/packages/bundler/src/bundle.ts)
- [Remotion: absolute paths for assets](https://www.remotion.dev/docs/miscellaneous/absolute-paths)
