# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=2,<3"]
# ///
"""Headless Blender MCP server.

Every tool shells out to the Blender binary in --background mode with --factory-startup, so
nothing here needs a GUI and no state survives between calls. Tools return a JSON text block
plus any rendered PNG/JPEG images as image content.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shlex
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, ImageContent, TextContent

BLENDER = os.environ.get("BLENDER", "/Applications/Blender.app/Contents/MacOS/Blender")
WORK_DIR = Path(os.environ.get("BLENDER_MCP_DIR", Path(tempfile.gettempdir()) / "blender-mcp"))
RESULT_RE = re.compile(r"^RESULT (.+)$", re.MULTILINE)
SAVED_RE = re.compile(r"\| Saved: '([^']+)'")
MAX_IMAGES = 4
MAX_IMAGE_BYTES = 4_000_000

Engine = Literal["CYCLES", "BLENDER_EEVEE", "BLENDER_WORKBENCH"]

GPU_LINES = [
    "prefs = bpy.context.preferences.addons['cycles'].preferences",
    "prefs.compute_device_type = 'METAL'",
    "prefs.get_devices()",
    "for d in prefs.devices: d.use = d.type == 'METAL'",
    "scene.cycles.device = 'GPU'",
]

INSPECT_CODE = """
import bpy, json
scene = bpy.context.scene
objs = []
for o in bpy.data.objects:
    objs.append({
        "name": o.name, "type": o.type,
        "location": [round(v, 3) for v in o.location],
        "dimensions": [round(v, 3) for v in o.dimensions],
        "materials": [s.material.name for s in o.material_slots if s.material],
        "modifiers": [m.type for m in o.modifiers],
        "parent": o.parent.name if o.parent else None,
        "hide_render": o.hide_render,
    })
print("RESULT " + json.dumps({
    "file": bpy.data.filepath, "scene": scene.name, "engine": scene.render.engine,
    "camera": scene.camera.name if scene.camera else None,
    "frame_range": [scene.frame_start, scene.frame_end], "fps": scene.render.fps,
    "resolution": [scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage],
    "objects": objs,
    "materials": [m.name for m in bpy.data.materials],
    "collections": [c.name for c in bpy.data.collections],
}))
"""

mcp = MCPServer(
    "blender",
    instructions=(
        "Headless Blender (background mode, no GUI). run_python executes bpy code in a fresh "
        "--factory-startup session, optionally with a .blend loaded first; print a final "
        "'RESULT <json>' line to return data. Renders referenced by RESULT['out'] (or reported "
        "as Saved by Blender) come back as images. Use absolute output paths."
    ),
)


def _text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode(errors="replace") if isinstance(value, bytes) else value


def _write_script(name: str, code: str) -> Path:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f"{name}_{int(time.time())}_", suffix=".py", dir=WORK_DIR)
    os.close(fd)
    path = Path(raw)
    path.write_text(code)
    return path


def _run_blender(script: Path, blend: str | None, args: list[str], flags: list[str], timeout: int) -> dict:
    cmd = [BLENDER, "-b", "--factory-startup"]
    if blend:
        cmd.append(str(Path(blend).expanduser()))
    cmd += [*flags, "--python-exit-code", "1", "--python", str(script), "--", *args]
    log = script.with_suffix(".log")
    started = time.time()
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        log.write_text(_text(exc.stdout))
        return {"status": "timeout", "timeout_seconds": timeout, "command": shlex.join(cmd),
                "script": str(script), "log": str(log)}
    output = proc.stdout
    log.write_text(output)
    info = {
        "status": proc.returncode,
        "seconds": round(time.time() - started, 2),
        "command": shlex.join(cmd),
        "script": str(script),
        "log": str(log),
        "saved": SAVED_RE.findall(output),
    }
    matches = RESULT_RE.findall(output)
    if matches:
        try:
            info["result"] = json.loads(matches[-1])
        except json.JSONDecodeError:
            info["result"] = matches[-1]
    if proc.returncode != 0:
        info["log_tail"] = "\n".join(output.splitlines()[-40:])
    return info


def _image_paths(info: dict) -> list[str]:
    paths = list(info.get("saved", []))
    result = info.get("result")
    if isinstance(result, dict):
        for key in ("out", "image", "images"):
            value = result.get(key)
            if isinstance(value, str):
                paths.append(value)
            elif isinstance(value, list):
                paths.extend(v for v in value if isinstance(v, str))
    return list(dict.fromkeys(paths))


def _image_blocks(paths: list[str], skipped: list[dict]) -> list[ImageContent]:
    blocks: list[ImageContent] = []
    for raw in paths:
        path = Path(raw)
        suffix = path.suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg"} or not path.is_file():
            continue
        size = path.stat().st_size
        if size > MAX_IMAGE_BYTES or len(blocks) == MAX_IMAGES:
            skipped.append({"path": raw, "bytes": size, "reason": "too large" if size > MAX_IMAGE_BYTES else "image cap"})
            continue
        mime = "image/png" if suffix == ".png" else "image/jpeg"
        blocks.append(ImageContent(type="image", data=base64.b64encode(path.read_bytes()).decode(), mime_type=mime))
    return blocks


def _tool_result(info: dict, return_images: bool) -> CallToolResult:
    images: list[ImageContent] = []
    if return_images and info.get("status") == 0:
        skipped: list[dict] = []
        images = _image_blocks(_image_paths(info), skipped)
        if skipped:
            info["images_skipped"] = skipped
    content: list = [TextContent(type="text", text=json.dumps(info, indent=2)), *images]
    return CallToolResult(content=content, is_error=info.get("status") != 0)


@mcp.tool()
def blender_info() -> dict:
    """Report the Blender binary, version, bundled Python interpreter and available render engines."""
    version = subprocess.run([BLENDER, "--version"], capture_output=True, text=True, timeout=60).stdout
    engines_out = subprocess.run([BLENDER, "-b", "-E", "help"], capture_output=True, text=True, timeout=60).stdout
    probe = subprocess.run(
        [BLENDER, "-b", "--python-expr", "import sys; print('PYEXE', sys.executable, sys.version.split()[0])"],
        capture_output=True, text=True, timeout=120,
    ).stdout
    engines = [ln.strip() for ln in engines_out.splitlines() if ln.startswith("\t")]
    python = next((ln.split(" ", 1)[1] for ln in probe.splitlines() if ln.startswith("PYEXE ")), None)
    return {
        "binary": BLENDER,
        "version": version.strip().splitlines()[0] if version.strip() else None,
        "bundled_python": python,
        "engines": engines,
        "work_dir": str(WORK_DIR),
    }


@mcp.tool(structured_output=False)
def run_python(
    code: str,
    blend: str | None = None,
    args: list[str] | None = None,
    extra_flags: list[str] | None = None,
    timeout_seconds: int = 600,
    return_images: bool = True,
) -> CallToolResult:
    """Run bpy code in a fresh headless Blender session and return its RESULT line plus any renders.

    The code runs after `blend` (if given) is loaded, under --factory-startup with no GUI, so
    prefer the data API (bpy.data) over operators that need a UI context. `args` arrive in
    sys.argv after "--". Print a final line `RESULT <json>` to return data; if it contains
    "out", "image" or "images" pointing at PNG/JPEG files, those are returned as images, as is
    anything Blender reports as Saved. Use absolute output paths.
    """
    script = _write_script("run", code)
    info = _run_blender(script, blend, args or [], extra_flags or [], timeout_seconds)
    return _tool_result(info, return_images)


@mcp.tool(structured_output=False)
def render(
    blend: str,
    out: str,
    frame: int = 1,
    engine: Engine = "CYCLES",
    samples: int | None = None,
    width: int | None = None,
    height: int | None = None,
    camera: str | None = None,
    gpu: bool = False,
    timeout_seconds: int = 1800,
) -> CallToolResult:
    """Render one frame of a .blend to `out` (PNG, or JPEG by extension) and return the image.

    `gpu=True` enables Cycles on Metal; the first GPU render after an install compiles kernels
    and can take minutes, later ones are fast. Width/height override the file's resolution.
    """
    fmt = "JPEG" if Path(out).suffix.lower() in {".jpg", ".jpeg"} else "PNG"
    lines = ["import bpy, json", "scene = bpy.context.scene", f"scene.render.engine = {engine!r}"]
    if camera:
        lines.append(f"scene.camera = bpy.data.objects[{camera!r}]")
    if width or height:
        lines.append("scene.render.resolution_percentage = 100")
    if width:
        lines.append(f"scene.render.resolution_x = {int(width)}")
    if height:
        lines.append(f"scene.render.resolution_y = {int(height)}")
    if samples is not None and engine == "CYCLES":
        lines.append(f"scene.cycles.samples = {int(samples)}")
    if samples is not None and engine == "BLENDER_EEVEE":
        lines.append(f"scene.eevee.taa_render_samples = {int(samples)}")
    if gpu and engine == "CYCLES":
        lines.extend(GPU_LINES)
    lines += [
        f"scene.frame_set({int(frame)})",
        f"scene.render.image_settings.file_format = {fmt!r}",
        f"scene.render.filepath = {out!r}",
        "bpy.ops.render.render(write_still=True)",
        "print('RESULT ' + json.dumps({'out': " + repr(out) + ", 'engine': scene.render.engine, "
        "'frame': scene.frame_current, 'camera': scene.camera.name if scene.camera else None, "
        "'resolution': [scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage]}))",
    ]
    script = _write_script("render", "\n".join(lines) + "\n")
    return _tool_result(_run_blender(script, blend, [], [], timeout_seconds), True)


@mcp.tool(structured_output=False)
def inspect_blend(blend: str, timeout_seconds: int = 300) -> CallToolResult:
    """Summarise a .blend: scene settings, camera, frame range, objects with materials and modifiers."""
    script = _write_script("inspect", INSPECT_CODE)
    return _tool_result(_run_blender(script, blend, [], [], timeout_seconds), False)


@mcp.tool(structured_output=False)
def export_scene(
    blend: str,
    out: str,
    format: Literal["GLB", "GLTF", "OBJ", "FBX"] = "GLB",
    objects: list[str] | None = None,
    timeout_seconds: int = 600,
) -> CallToolResult:
    """Export a .blend (or only the named objects) to GLB, glTF (separate files), OBJ or FBX."""
    lines = ["import bpy, json, os"]
    selected = bool(objects)
    if selected:
        lines += [
            f"wanted = set({list(objects)!r})",
            "for o in bpy.data.objects: o.select_set(o.name in wanted)",
        ]
    if format in {"GLB", "GLTF"}:
        gltf_format = "GLB" if format == "GLB" else "GLTF_SEPARATE"
        lines.append(f"bpy.ops.export_scene.gltf(filepath={out!r}, export_format={gltf_format!r}, use_selection={selected})")
    elif format == "OBJ":
        lines.append(f"bpy.ops.wm.obj_export(filepath={out!r}, export_selected_objects={selected})")
    else:
        lines.append(f"bpy.ops.export_scene.fbx(filepath={out!r}, use_selection={selected})")
    lines.append(
        "print('RESULT ' + json.dumps({'out': " + repr(out) + ", 'format': " + repr(format) + ", "
        "'bytes': os.path.getsize(" + repr(out) + ") if os.path.exists(" + repr(out) + ") else None}))"
    )
    script = _write_script("export", "\n".join(lines) + "\n")
    return _tool_result(_run_blender(script, blend, [], [], timeout_seconds), False)


if __name__ == "__main__":
    mcp.run(transport="stdio")
