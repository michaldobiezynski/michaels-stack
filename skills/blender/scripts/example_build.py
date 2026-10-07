"""Starter bpy script: replaces the default cube with a metallic sphere and renders it.

Copy this file as the basis for new scenes. It shows the three conventions the
blender skill relies on: argparse after "--", the data API over bpy.ops where
a UI context would be needed, and a single "RESULT <json>" line on stdout.
"""
import argparse
import json
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument("--out", required=True, help="output image path (PNG)")
parser.add_argument("--size", type=int, default=512)
parser.add_argument("--engine", default="CYCLES", choices=["CYCLES", "BLENDER_EEVEE", "BLENDER_WORKBENCH"])
parser.add_argument("--samples", type=int, default=32)
args = parser.parse_args(argv)

cube = bpy.data.objects.get("Cube")
if cube is not None:
    bpy.data.objects.remove(cube, do_unlink=True)

bpy.ops.mesh.primitive_uv_sphere_add(radius=1.2, location=(0, 0, 0))
sphere = bpy.context.active_object
sphere.data.polygons.foreach_set("use_smooth", [True] * len(sphere.data.polygons))

mat = bpy.data.materials.new("Copper")
mat.use_nodes = True
bsdf = mat.node_tree.nodes["Principled BSDF"]
bsdf.inputs["Base Color"].default_value = (0.8, 0.4, 0.2, 1.0)
bsdf.inputs["Metallic"].default_value = 1.0
bsdf.inputs["Roughness"].default_value = 0.25
sphere.data.materials.append(mat)

scene = bpy.context.scene
scene.render.engine = args.engine
if args.engine == "CYCLES":
    scene.cycles.samples = args.samples
    scene.cycles.device = "CPU"
elif args.engine == "BLENDER_EEVEE":
    scene.eevee.taa_render_samples = args.samples
scene.render.resolution_x = scene.render.resolution_y = args.size
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = args.out
bpy.ops.render.render(write_still=True)

print("RESULT " + json.dumps({
    "out": args.out,
    "engine": args.engine,
    "objects": sorted(o.name for o in bpy.data.objects),
    "blender": bpy.app.version_string,
}))
