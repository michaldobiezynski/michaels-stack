---
name: lr-asd-active-speaker-detection-apple-silicon
description: |
  Get LR-ASD / Light-ASD / TalkNet-ASD (active-speaker detection: which visible
  face is speaking) running on a single local video on macOS Apple Silicon (CPU,
  no CUDA). Use when: (1) `python Columbia_test.py` crashes with
  `ModuleNotFoundError: No module named 'torchvision'` (S3FD imports
  torchvision.transforms), (2) it fails on `S3FD(device='cuda')` / `.cuda()` calls
  on a machine with no GPU, (3) `FileNotFoundError: sfd_face.pth` because the
  built-in `gdown --id <id>` auto-download silently fails, (4)
  `AttributeError: module 'numpy' has no attribute 'int'` (or 'float') from the
  repo's use of removed numpy aliases, (5) scenedetect errors about VideoManager.
  Covers the exact patches, the manual S3FD weight fetch, the demo invocation, and
  the tracks.pckl/scores.pckl output format.
author: Claude Code
version: 1.0.0
date: 2026-07-01
---

# LR-ASD / TalkNet active-speaker detection on Apple Silicon

## Problem

The LR-ASD (`github.com/Junhua-Liao/LR-ASD`, IJCV 2025), Light-ASD and TalkNet-ASD
repos are CUDA-first and pinned to old dependency versions. Running the single-video
demo on a modern Apple-Silicon Python env fails at several points with misleading
errors, none of which are about the actual model.

## Context / Trigger conditions

Running `python Columbia_test.py --videoName X --videoFolder Y` and hitting, in order:
`ModuleNotFoundError: torchvision` -> a `.cuda()`/`device='cuda'` failure ->
`FileNotFoundError: .../sfd_face.pth` -> `AttributeError: module 'numpy' has no
attribute 'int'`.

## Solution

1. **Deps.** Into the venv: `opencv-python`, `scenedetect==0.6.0` (the code uses the
   old `VideoManager`/`SceneManager` API removed in 0.6.2+), `python_speech_features`,
   `gdown`, `scikit-learn`, `tqdm`, and crucially **`torchvision`** (S3FD needs
   `torchvision.transforms`; a torch-only stack is not enough). Installing torchvision
   may patch-bump torch (e.g. 2.12.0 -> 2.12.1), which is harmless.
2. **CPU patch** (no CUDA). In `Columbia_test.py`: `S3FD(device='cuda')` -> `'cpu'`
   and the two `.cuda()` on `inputA`/`inputV` -> `.cpu()`. In `ASD.py`: all `.cuda()`
   -> `.cpu()` and `torch.load(path)` -> `torch.load(path, map_location='cpu')`. Bulk:
   `sed -i '' "s/device='cuda'/device='cpu'/g; s/\.cuda()/.cpu()/g" Columbia_test.py`.
   S3FD's own `__init__.py` already honours its `device` arg. Use `cpu`, not `mps`;
   some S3FD conv/NMS ops break on MPS.
3. **S3FD weight** (~86 MB). The built-in downloader runs `gdown --id <id>` via
   `subprocess`, which fails (the `gdown` console script / `--id` flag is broken in
   current gdown). Fetch manually with the module form:
   `python -m gdown 1KafnHz7ccT-3IyddBsL5yi2xGtxAKypt -O model/faceDetector/s3fd/sfd_face.pth`.
4. **Removed numpy aliases.** `np.int`/`np.float` were removed in numpy >=1.24 but the
   repo still uses them (notably `model/faceDetector/s3fd/box_utils.py` NMS
   `astype(np.int)`, on the face-detection path). Patch to `int`/`float`:
   `grep -rnE "np\.(int|float|bool)[^0-9a-zA-Z_]" --include='*.py' .` then sed each.
5. **Run.** Put the mp4 at `<videoFolder>/<videoName>.mp4` (e.g. `demo/0001.mp4`) and
   run `python Columbia_test.py --videoName 0001 --videoFolder demo`. It re-extracts
   frames at **25 fps** (via `ffmpeg -r 25`), so any input fps is fine. Run from the
   repo root (relative paths to `weight/` and `model/`); the venv python's cwd must be
   the repo dir.

## Verification

`demo/0001/pywork/` contains `scene.pckl`, `faces.pckl`, `tracks.pckl`, `scores.pckl`.
Face detection on CPU dominates runtime (~1-3 min for 60s @ 25 fps here).

## Output format

`tracks.pckl` = list of `{'track': {'frame': ndarray, 'bbox': Nx4}, 'proc_track': ...}`
(one entry per contiguous **per-shot** face track, NOT per person). `scores.pckl` = a
parallel list of per-frame ASD scores; **score >= 0 means that track is speaking**.
Per frame, the active speaker is the track with the max score if that max >= 0, else
none-on-screen. To turn per-shot tracks into per-person labels you still need identity
linking (face recognition) or an oracle mapping.

## Notes

- Track ids do NOT persist across shot cuts, so a 60s clip with many cuts yields many
  tracks (e.g. 16 for two people). Do not assume "2 tracks == 2 people".
- Pair with the evaluation method in
  [[audio-visual-asd-coverage-vs-accuracy-eval]]: on edited footage the limiting factor
  is COVERAGE (speaker on screen), not model accuracy.

## References

- LR-ASD repo: https://github.com/Junhua-Liao/LR-ASD ; Light-ASD:
  https://github.com/Junhua-Liao/Light-ASD ; TalkNet-ASD (dep list):
  https://github.com/TaoRuijie/TalkNet-ASD
