# Blender headless reference

Everything below was verified on Blender 5.2.1 LTS (Homebrew cask) on an Apple Silicon Mac
unless marked "untested".

## Exit codes and logs

- Bare `blender -b --python x.py` exits 0 even when the script raises. `--python-exit-code 1`
  turns that into exit 1. The wrapper always passes it.
- Log lines are prefixed `HH:MM:SS.mmm  category | message`. The render save line reads
  `... render | Saved: '/path/file.png'`, so grep for `Saved: `, never `^Saved`.
- Your script's final `RESULT <json>` line is the only stdout contract the wrapper relies on.

## Operators versus the data API

Operators (`bpy.ops.*`) act on the active object and selection. In background mode there is no
UI, but the active object still exists (whatever was last added, or the .blend's saved state).
Verified working headless under `--factory-startup`: `mesh.primitive_*_add`, `render.render`,
`wm.save_as_mainfile`, `export_scene.gltf`, `wm.obj_export`, `object.modifier_apply` on the
active object.

To target a specific object rather than "whatever is active", use a context override:

```python
with bpy.context.temp_override(object=obj, active_object=obj, selected_objects=[obj]):
    bpy.ops.object.modifier_apply(modifier="Bevel")
```

If you see `Operator bpy.ops.X.poll() failed, context is incorrect`, either add an override
or switch to the data API. Removal and linking are always cleaner through data:
`bpy.data.objects.remove(obj, do_unlink=True)`, `bpy.data.materials.new(...)`,
`obj.data.materials.append(mat)`.

## Render engines

`blender -b -E help` lists `BLENDER_EEVEE`, `BLENDER_WORKBENCH`, `CYCLES`.

- **Cycles CPU** is the default in `example_build.py`. A simple 512 px scene at 64 samples
  takes about 0.6 s on an M5 Pro.
- **Cycles Metal GPU** must be enabled per run, because preferences are not persisted under
  `--factory-startup`:

  ```python
  prefs = bpy.context.preferences.addons["cycles"].preferences
  prefs.compute_device_type = "METAL"
  prefs.get_devices()
  for d in prefs.devices:
      d.use = d.type == "METAL"
  scene.cycles.device = "GPU"
  ```

  The first GPU render compiles Metal kernels (measured 100 s); subsequent runs took 0.9 s.
  Only worth it for heavy scenes; expect the one-off compile after a Blender upgrade.
- **Eevee** and **Workbench** both render in background mode on macOS. On a display-less Linux
  server Eevee needs a GPU or EGL context; use Cycles or Workbench there (untested here).

## Timing

Startup plus a trivial script is about one second, so one process per run is fine for
iteration. `--python-console` exists for a persistent REPL but is not used by this skill.

## Bundled Python and packages

- Interpreter: `/Applications/Blender.app/Contents/Resources/5.2/python/bin/python3.13`
  (Python 3.13, pip included). Confirm with
  `blender -b --python-expr "import sys; print(sys.executable)"`.
- To use a third-party package inside a script, install it with that interpreter:
  `<interpreter> -m pip install <pkg>` (untested; lands in Blender's own site-packages and is
  lost on a Blender upgrade). Alternatively pass `--python-use-system-env` via `BLENDER_FLAGS`
  so `PYTHONPATH` is honoured.

## Files, imports and exports

```python
bpy.ops.wm.save_as_mainfile(filepath="/abs/scene.blend")
bpy.ops.export_scene.gltf(filepath="/abs/out.glb", export_format="GLB")   # verified
bpy.ops.wm.obj_export(filepath="/abs/out.obj")                            # verified
bpy.ops.export_scene.fbx(filepath="/abs/out.fbx")                         # untested
bpy.ops.import_scene.gltf(filepath="/abs/in.glb")                          # untested
bpy.ops.wm.obj_import(filepath="/abs/in.obj")                              # untested
```

Loading a .blend: `blender_run.sh --blend scene.blend script.py`. The file is opened before the
script runs, `bpy.data.filepath` is set, and `//` relative paths resolve against it.

## Animation

Set `scene.frame_start`, `scene.frame_end`, `scene.render.filepath = "/abs/anim_"` and call
`bpy.ops.render.render(animation=True)`; frames are written as `anim_0001.png` and so on.
Or, without a script: `blender -b scene.blend -o /abs/anim_#### -F PNG -s 1 -e 48 -a`.

## Not headless

The community `blender-mcp` add-on (ahujasid) runs a socket server inside a GUI Blender session
and depends on UI timers, so it does not work under `-b`. For tool-style access from Claude Code
use the MCP server in `mcp/` (see SKILL.md), which shells out to the same headless binary.

## See also

- Cell Fracture from a headless script (install, enable, deterministic cells, GLB export): the `blender-cell-fracture-headless` skill.
