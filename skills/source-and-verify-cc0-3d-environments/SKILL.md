---
name: source-and-verify-cc0-3d-environments
description: |
  Find, licence-check and test-fit free 3D environment assets (dungeon, castle, hall, arena
  kits and scenes) for a three.js / R3F / Blender project, and recover the provenance of
  GLBs already sitting in a repo with no attribution. Use when: (1) the user asks for
  reusable Blender-made environments or asset packs, (2) a project folder holds Sketchfab
  GLBs whose attribution line has no licence or author, (3) a research subagent quotes
  licences from store pages that need checking, (4) itch.io or Blend Swap block scripted
  downloads and you need the mirror or the login answer, (5) a headless Blender test render
  of a kit shows floor z-fighting or unhidden helper meshes. Verified 20/09/2026.
author: Claude Code
version: 1.0.0
date: 2026-09-20
---

# Source and verify CC0 3D environments

## Problem

Asset pages overstate what ships (formats, .blend inclusion), research agents mis-quote
licences, "free" listings hide commercial terms, and GLBs already in a repo carry no
licence in their filename. Quoting any of it unverified puts a NonCommercial or
Sketchfab-Standard model into a shipped build.

## Solution

1. **Recover provenance from the GLB header, not the filename.** Sketchfab exports embed
   `asset.extras = {title, author, license, source}`; other exporters leave only
   `asset.generator`. Parse the 12-byte header + first JSON chunk:
   ```python
   with open(f,'rb') as fh:
       fh.read(12); clen,_=struct.unpack('<II',fh.read(8)); js=json.loads(fh.read(clen))
   js['asset'].get('extras'), js['asset'].get('generator')
   ```
   Also count triangles from `accessors[indices].count//3` and images from `len(js['images'])`.
   For a Sketchfab uid, `https://api.sketchfab.com/v3/models/<uid>` returns `license.label`,
   `user.displayName`, `faceCount`, `isDownloadable` without auth.
2. **Fetch real files, not pages:**
   - KayKit packs are plain git repos under `github.com/KayKit-Game-Assets/<Pack>-1.0`
     (no releases; `git clone --depth 1`). Free tier = FBX/GLTF/OBJ + LICENSE.txt (CC0);
     `.blend` only on the paid Source tier.
   - Kenney: the asset page links a direct zip
     (`kenney.nl/media/pages/assets/<kit>/<hash>/kenney_<kit>_<ver>.zip`) with GLB, FBX,
     OBJ and License.txt (CC0).
   - Poly Haven: `https://api.polyhaven.com/info/<id>` confirms an id exists; everything
     on the site is CC0.
   - OpenGameArt: files are direct at `opengameart.org/sites/default/files/<name>.zip`;
     read the bundled readme, packs often mix in third-party textures.
   - Blend Swap: `/blend/<id>/download` returns the login page; the user must download.
   - Blendkit (was BlenderKit): "Royalty Free" bans re-sale as a model or game level;
     only its CC0-tagged assets are unambiguous for a web build.
3. **Measure before assembling.** Compute per-piece bounding boxes from the glTF POSITION
   accessor `min`/`max` (glTF is Y-up; Blender import converts to Z-up). Use them to lay
   out a room around the target (a chess board = 8.6 units) with a bpy script.
4. **Headless test render gotchas** (Blender 5.2, `bpy.ops.import_scene.gltf`):
   - Import each distinct file once, hide the originals, instance with `o.copy()` and
     re-parent; record each original's `hide_render` first, because `o.copy()` of a
     hidden helper mesh (a hull `Icosphere` in the chess piece GLBs) renders as a bubble.
   - `primitive_cube_add(size=1)` then `scale=(…, 0.06)` gives half-height 0.03, not
     0.06; a placeholder board at exactly the tile top z-fights and vanishes. Put its top
     0.1 above the measured floor top.
   - Legacy `.blend` files (2.6/2.7 Blender Internal) open in 5.2 but render grey: the
     materials have no node trees. Budget a re-material pass or skip them.
   - Delete the hidden originals before `export_scene.gltf(use_selection=True)` so only
     instances export; the exporter dedupes shared meshes (124 instances → 13 meshes,
     493 KB).
5. **Report each candidate with** licence as printed in the file, formats actually in the
   archive, tris, texture size and the test render; keep NonCommercial, ShareAlike,
   Sketchfab Standard and "please credit" listings out of the shippable list.

## Verification

20/09/2026: KayKit Dungeon Remastered cloned from GitHub, 203 GLBs, LICENSE.txt "Creative
Commons Zero, CC0"; a 36x36 chamber assembled and exported to a 493 KB GLB that re-imported
with 124 meshes / 40,017 tris. Demo repo GLB headers recovered four CC-BY-4.0 authors, one
CC-BY-NC-SA and one Sketchfab Standard licence the filenames did not show.

## References

- glTF 2.0 asset object: https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html#reference-asset
- Sketchfab Data API v3: https://docs.sketchfab.com/data-api/v3/index.html
- KayKit GitHub org: https://github.com/KayKit-Game-Assets
- Poly Haven API: https://api.polyhaven.com/
