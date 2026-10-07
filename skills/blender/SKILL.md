---
name: blender
description: Drive headless Blender (background mode, no GUI) from Claude Code, either through the blender MCP tools (run_python, render, inspect_blend, export_scene) or by writing a bpy script and running it through scripts/blender_run.sh, then reading the RESULT line and rendered image back. Use when the user mentions Blender, bpy, .blend files, 3D scenes, meshes, materials, rendering stills or animations, or exporting GLB, OBJ or FBX from Blender.
---

# Blender (headless)

Blender 5.x LTS is installed from the Homebrew cask. Binary: `/Applications/Blender.app/Contents/MacOS/Blender`
(`/opt/homebrew/bin/blender` wraps the same binary). Everything runs in `--background` mode:
no GUI, one process per run, about one second of startup on top of the work itself.

## Quick start

```bash
~/.claude/skills/blender/scripts/blender_run.sh \
  ~/.claude/skills/blender/scripts/example_build.py -- --out /tmp/sphere.png --size 512
```

On success the wrapper prints the script's `RESULT {...}` line and any `Saved:` lines.
On failure it prints the tail of the Blender log and exits with Blender's status.
Then open the PNG with the Read tool and check the render visually.

## Workflow

1. Copy `scripts/example_build.py` into the working directory (or the scratchpad) and edit it.
2. Run it: `scripts/blender_run.sh [--blend FILE.blend] SCRIPT.py [-- script args...]`.
3. Parse the `RESULT` line, Read the output image, adjust the script, re-run.
4. Report the command, the RESULT line, and what the render shows. Never report a render as
   done from the exit code alone; look at the image.

## Script contract

- Script arguments follow `--`: `argv = sys.argv[sys.argv.index("--") + 1:]`, then argparse.
- Print exactly one `RESULT <json>` line at the end (paths, object names, counts). The wrapper
  greps for it, so keep other prints off that prefix.
- Prefer the data API where an operator would need a UI context:
  `bpy.data.objects.remove(obj, do_unlink=True)` rather than `bpy.ops.object.delete()`.
  Primitive `_add`, `render.render`, save, import and export operators all work headless.
  For operators that insist on a context (modifier_apply, transform_apply, join) wrap them in
  `bpy.context.temp_override(...)`; see [REFERENCE.md](REFERENCE.md).
- Set the engine explicitly: `CYCLES` (CPU default, Metal GPU optional), `BLENDER_EEVEE`, or
  `BLENDER_WORKBENCH`. All three render headless on this Mac.
- Use absolute output paths. `//` means "relative to the .blend", which is empty for a scratch scene.

## Render an existing .blend without a script

```bash
blender -b scene.blend -E CYCLES -o /tmp/frame_#### -F PNG -f 1      # single frame
blender -b scene.blend -o /tmp/anim_#### -F PNG -s 1 -e 48 -a         # frame range
```

`#` characters become the zero-padded frame number.

## Wrapper environment variables

| Variable | Purpose |
| --- | --- |
| `BLENDER` | Binary path; override for a non-Homebrew install |
| `BLENDER_FLAGS` | Extra flags inserted before `--python`, e.g. `-E CYCLES` or `--addons io_scene_gltf2` |
| `BLENDER_LOG` | Full log path; default is a temp file, always echoed as `log: ...` on stderr |

## MCP server (tool access without the shell)

`mcp/server.py` exposes the same headless binary as MCP tools, registered at user scope as
`blender`. New sessions pick it up automatically; in a running session use `/mcp` to reconnect.

| Tool | Does |
| --- | --- |
| `blender_info` | Version, binary path, bundled Python, render engines |
| `run_python` | Run bpy code (optionally with a .blend loaded); returns the RESULT JSON and any renders as images |
| `render` | Render one frame of a .blend to PNG/JPEG and return the image |
| `inspect_blend` | Objects, materials, modifiers, camera, frame range of a .blend |
| `export_scene` | Export to GLB, glTF, OBJ or FBX, optionally only named objects |

Prefer the MCP tools for look-and-adjust loops (the image comes back in the same result).
Images over 4 MB are not attached; the result lists them under `images_skipped`, so Read the
file or render smaller.
Prefer the wrapper script when the bpy script should live in the repo as a reproducible file.
Re-register if the folder moves:
`claude mcp add --scope user blender -- uv run --script ~/.claude/skills/blender/mcp/server.py`.

## Gotchas and details

See [REFERENCE.md](REFERENCE.md): exit codes, stdout parsing, operator context errors, GPU
rendering, bundled Python and pip, exports, and why the blender-mcp add-on is not for headless use.
