---
name: yolo-retrain-matching-existing-onnx-consumer
description: |
  Pattern for retraining a YOLO (or similar) ONNX object detector while
  preserving compatibility with a downstream consumer that has hardcoded
  expectations. Use when: (1) you ship an ONNX file that a non-Python
  runtime (Rust onnxruntime, C++ onnx-runtime, Go onnx-go, mobile
  Core ML / TFLite adapters) loads with a HARDCODED input shape, class
  count, class-name ordering, and output tensor layout, (2) you want to
  retrain / fine-tune and drop-in replace the ONNX without touching the
  consumer code, (3) you only have the `.onnx` file, no trainable `.pt`,
  so you cannot resume the existing weights and must re-train a head
  from a public pretrained base, (4) your detection domain has
  directional semantics (chess boards, UI layouts, document pages) where
  the default ultralytics `fliplr=0.5` augmentation corrupts training
  signal. Covers: reading CLASS_MAP from the consumer source via regex
  as a drift tripwire; choosing YOLOv8n/s/m weights as a fresh base;
  dataset.yaml names ordering; ultralytics anti-flip/anti-mosaic config;
  ONNX export shape verification (1, 4+nc, N_proposals); and a validation
  loop that diffs fixture outcomes before/after.
author: Claude Code
version: 1.0.0
date: 2026-04-24
---

# Retraining a YOLO ONNX to drop-in-replace for a non-Python consumer

## Problem

You ship a YOLO ONNX file that a downstream, non-Python consumer loads
with hardcoded expectations:

- **Input shape**: e.g. `(1, 3, 640, 640)`, NCHW, float32, [0,1].
- **Output shape**: e.g. `(1, 16, 8400)` for 12 classes + 4 bbox at 640.
- **Class-id ordering**: e.g. Rust has `CLASS_MAP = ['b','k','n','p','q','r',
  'B','K','N','P','Q','R']` at indices 0..11. Every downstream decode
  assumes this exact order.
- **Opset / operators**: consumer's ONNX runtime supports up to opset X.
- **Augmentation assumptions**: consumer expects "a1 is always dark" or
  "pages always read left-to-right" or similar directional invariant.

Now your model makes systematic errors that post-processing cannot fix
(a piece type is consistently misclassified, a layout element is
consistently missed). You need to retrain without breaking ANY of the
above. And you only have the `.onnx` — no trainable `.pt`, no original
dataset.

Four traps:

1. **CLASS_MAP drift**: ultralytics uses `dataset.yaml:names` ordering.
   If your yaml differs from the consumer's class list, every decoded
   prediction will be the wrong class — silently, with no error.
2. **Horizontal flip augmentation on a directional domain**: default
   ultralytics training uses `fliplr=0.5`. For chess this mirrors the
   board (a1 becomes a dark square that looks like h1, kings look like
   they're on the queen's file). The model learns the wrong priors.
3. **ONNX output shape drift**: ultralytics export changes operator
   choices across versions; the consumer may reject a new shape silently
   by producing garbage detections.
4. **Resume-from-ONNX is fragile**: converting ONNX back to trainable
   PyTorch via `onnx2pytorch` or `onnx-tf` loses operator-level fidelity.
   It's almost always wrong to do this; start from a fresh COCO-pretrained
   YOLOv8n/s base and retrain the head on your data.

## Context / Trigger conditions

- You're maintaining a YOLO ONNX shipped inside a Rust, Go, C++, or
  mobile app.
- You don't have the `.pt` and recovering weights from the `.onnx` is
  not an option.
- Your domain has a fixed orientation convention (chess a1-dark,
  document top-left, UI screen bounds).
- You can generate synthetic training data programmatically (SVG render,
  headless browser, domain simulator).
- You have or can build a fixture corpus that tests the full inference
  pipeline (image in, decoded prediction out) — to validate no regression.

## Solution

Five steps. Skip none.

### 1. Pin the consumer's assumptions

Read the consumer source and extract its expectations into constants in
your training pipeline:

```python
# Consumer constants — MIRRORED FROM Rust/C++/Go. Drift detector below.
INPUT_SIZE = 640
NUM_CLASSES = 12
CLASS_MAP = ["b", "k", "n", "p", "q", "r", "B", "K", "N", "P", "Q", "R"]

CONSUMER_CLASS_MAP_RE = re.compile(
    r"const\s+CLASS_MAP\s*:\s*\[char;\s*12\]\s*=\s*\[([^\]]+)\]",
)

def assert_class_map_matches_consumer() -> None:
    src = (REPO / "src-tauri/src/image_detection/fen_generator.rs").read_text()
    m = CONSUMER_CLASS_MAP_RE.search(src)
    if m is None:
        raise SystemExit("CLASS_MAP location moved; update the regex.")
    their_chars = re.findall(r"'([^']+)'", m.group(1))
    if their_chars != CLASS_MAP:
        raise SystemExit(f"drift: consumer={their_chars} vs local={CLASS_MAP}")
```

Call this at the TOP of every script (data generator, trainer, exporter).
It catches silent class-id drift before training wastes hours.

### 2. dataset.yaml with exact ordering

The names list in ultralytics' yaml MUST be in the consumer's class-id
order. Use the list form (or dict with integer keys) — never rely on
implicit alphabetisation:

```yaml
path: ./data
train: train/images
val: val/images
nc: 12
names:
  0: black_bishop    # 'b'  in consumer CLASS_MAP
  1: black_king      # 'k'
  2: black_knight    # 'n'
  3: black_pawn      # 'p'
  4: black_queen     # 'q'
  5: black_rook      # 'r'
  6: white_bishop    # 'B'
  7: white_king      # 'K'
  8: white_knight    # 'N'
  9: white_pawn      # 'P'
  10: white_queen    # 'Q'
  11: white_rook     # 'R'
```

The display names can differ from the consumer's char labels; what
matters is the `0..nc-1` index mapping.

### 3. Start from a public pretrained base, not the shipped ONNX

```python
from ultralytics import YOLO
model = YOLO("yolov8n.pt")   # downloads from ultralytics on first use
model.train(data="dataset.yaml", epochs=50, ...)
```

Ultralytics automatically re-initialises the detection head for the
`nc` in your yaml. You lose any chess-specific pretraining that was in
the shipped ONNX, but you gain trainability. Expect ~1000-2000 images
to recover respectable performance on 12 classes.

### 4. Kill augmentations that break directional semantics

In `model.train(...)` pass:

```python
model.train(
    data="dataset.yaml",
    epochs=50,
    imgsz=640,          # must match consumer input shape
    fliplr=0.0,         # OFF: chess/document/UI boards are not h-symmetric
    flipud=0.0,         # OFF (ultralytics default but be explicit)
    mosaic=0.0,         # OFF: 4-image stitching breaks the "whole board"
                        #      assumption the consumer expects
    # hsv_h, hsv_s, hsv_v: keep at defaults (colour jitter is fine)
    # translate, scale: keep at defaults (small crops are fine)
)
```

Why each:

- `fliplr` mirrors the image horizontally. For chess this swaps a-file
  with h-file, which also swaps light/dark square parity at the corners.
  The model learns that a1 might be light, which contradicts the
  consumer's downstream orientation logic.
- `flipud` mirrors vertically; pieces appear upside down and no longer
  look like pieces. Usually already off by default.
- `mosaic` stitches 4 image crops into one training frame. For full-board
  detection the "board" concept is broken; for crop-based detection
  it's usually fine.

### 5. Export and verify shape

```python
from ultralytics import YOLO
import onnx

exported_str = YOLO(best_pt_path).export(
    format="onnx",
    imgsz=640,
    opset=12,        # match consumer's ONNX runtime
    dynamic=False,
    simplify=True,
)
m = onnx.load(exported_str)
in_shape = tuple(d.dim_value for d in m.graph.input[0].type.tensor_type.shape.dim)
out_shape = tuple(
    d.dim_value if d.dim_value > 0 else -1
    for d in m.graph.output[0].type.tensor_type.shape.dim
)
assert in_shape == (1, 3, 640, 640), f"input shape drift: {in_shape}"
assert out_shape[1] == 4 + NUM_CLASSES, f"output channel drift: {out_shape}"
# out_shape[2] is the proposal count — 8400 for 640x640 YOLOv8.
```

If `out_shape[1]` is not `4 + nc`, either (a) your dataset.yaml has the
wrong `nc` value, or (b) ultralytics changed its export contract between
versions. Don't ship until fixed.

## Verification

1. **Class-map tripwire**: deliberately reorder your local CLASS_MAP
   list and run the generator; the assert should fire immediately with
   a clear error citing both lists.
2. **Shape-check tripwire**: export with the wrong `nc` in yaml; the
   assert should reject before the file is copied anywhere.
3. **End-to-end regression**: run your fixture corpus against the
   shipped model, then against a smoke-trained 1-epoch model. The smoke
   model should regress MOST fixtures (it's untrained); zero-regression
   requires a real training run. This verifies the harness plumbing.
4. **End-to-end improvement**: full 50-epoch training run. Exactly
   zero regressions on previously-passing fixtures, at least one flip
   from fail to pass. If you can't meet both bars, don't ship — the
   retraining didn't actually help on net.

## Example

pawn-au-chocolat (chess screenshot detection, Tauri+Rust+ONNX):

- `src-tauri/src/image_detection/fen_generator.rs` — Rust consumer's
  `CLASS_MAP`.
- `scripts/retrain-yolo/dataset.yaml` — names list in matching order.
- `scripts/retrain-yolo/generate_training_data.py` — renders 640x640
  PNGs via python-chess + cairosvg with programmatic bboxes; asserts
  CLASS_MAP match at startup.
- `scripts/retrain-yolo/train.py` — ultralytics wrapper with
  `fliplr=0.0, flipud=0.0, mosaic=0.0`.
- `scripts/retrain-yolo/export_onnx.py` — exports at opset 12,
  verifies (1, 3, 640, 640) in and (1, 16, 8400) out before accepting.
- `scripts/retrain-yolo/validate.py` — diffs shipped vs retrained
  against 70-fixture image corpus.

Smoke-tested end-to-end: 1-epoch training on 20 synthetic images,
export, shape check, cargo-test diff — all pieces wired up correctly.
Full retraining is a user-side run on their hardware.

## Notes

- **SVG-rendered training data has a domain gap.** Real Chess.com /
  Lichess screenshots have anti-aliasing, highlights, last-move boxes,
  coordinate labels, and cursor overlays that your python-chess SVG
  doesn't. Synthetic-only training can overfit; mix in hand-labelled
  real screenshots for the final push. CVAT and Label Studio are the
  standard labellers.
- **Seed positions are cheap diversity.** For chess, `chess.Board()`
  with a random move walk gives you thousands of distinct positions
  for free. For other domains the equivalent is: random-permute your
  DOM structure, random-position your UI elements, random-zoom your
  document page.
- **Horizontal flip is often OK for non-chess detection.** If your
  objects are rotation-invariant (people, cars, generic objects),
  `fliplr=0.5` helps. The gate is whether your consumer cares about
  left/right ordering.
- **Opset choice matters for C++ / Rust runtimes.** onnxruntime-cpu
  1.15+ supports opset 20+, but many Rust crates pin to 12-15. Check
  the consumer's opset ceiling before picking.
- **The shipped ONNX is NOT the trainable model.** A common mistake
  is treating `chess_pieces.onnx` as a checkpoint you can resume from.
  You can't — ONNX is an inference IR, not a training checkpoint. You
  need the `.pt` (PyTorch), `.safetensors`, or `.pth`. If you don't
  have one, accept that you're retraining from a public base.
- **Keep the old ONNX as a backup during rollout.** `validate.py`
  should write to `staging/` and require a manual copy on success —
  automatic overwrite makes rolling back hard when the retrained model
  has a subtle regression discovered in production.

## References

- [ultralytics YOLOv8 docs: training configuration](https://docs.ultralytics.com/modes/train/)
  — flags for augmentation, optimiser, schedule.
- [ONNX opset versioning](https://github.com/onnx/onnx/blob/main/docs/Versioning.md)
  — opset-to-runtime compatibility table.
- Sibling skills:
  - `yolo-chess-colour-correction` — post-processing fix for the same
    class of error this pipeline addresses at training time.
  - `detection-top2-disambiguation-gated-by-pattern` — the
    post-processing layer that complements a retrained model.
  - `cargo-test-python-json-report-bridge` — the validation infrastructure
    that lets this pipeline prove no regression before shipping.
