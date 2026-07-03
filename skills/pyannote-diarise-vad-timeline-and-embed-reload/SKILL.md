---
name: pyannote-diarise-vad-timeline-and-embed-reload
description: |
  Two pyannote.audio gotchas when reusing a diarisation/embedding stack to cut or
  batch-process audio. (1) TIMELINE: if diarisation is run on a VAD-trimmed wav
  (silence removed), the returned segment timestamps are on the VAD timeline, NOT
  the original file, so any slice you cut with those timestamps must be cut from
  the VAD wav, not the raw m4a/mp3, or the audio is offset/garbage. Use when:
  cutting a clip at diarisation start/end times lands on the wrong audio; a
  speaker slice contains the wrong words; you pass diarise output timestamps to
  ffmpeg -ss/-to against the original download. (2) PERFORMANCE: an embedding
  helper that calls Model.from_pretrained(...) INSIDE the per-call closure
  reloads model weights on every call, so a batch run reloads N times. Use when:
  diarisation/embedding batch jobs are far slower than expected; you see repeated
  "Lightning automatically upgraded checkpoint" / model-load logs per item. Cache
  the loaded Model/Inference once.
author: Claude Code
version: 1.0.0
date: 2026-06-02
---

# pyannote: diarisation runs on the VAD timeline; embed_fn reloads weights per call

## Problem

Two independent traps when building on a pyannote.audio diarisation pipeline.

### 1. Diarisation timestamps are on the VAD-trimmed timeline

A common pipeline runs Voice-Activity-Detection first, writes a VAD wav with the
silences removed, and diarises THAT, e.g.:

```python
def diarise_episode(audio_path, hf_token, ...):
    vad_wav = vad_output_path(audio_path)      # ./vad/<stem>.wav, silence removed
    pipe = Pipeline.from_pretrained("pyannote/speaker-diarization-...")
    output = pipe(str(vad_wav), ...)
    return [(start, end, label) for ... in output]   # times are on the VAD wav
```

The returned `(start, end)` are offsets into the **VAD wav**, not the original
download. If you then cut a speaker slice with `ffmpeg -i original.m4a -ss start
-to end`, you cut the wrong region (everything after the first removed silence is
shifted), and the clip contains the wrong speech, even though nothing errors.

### 2. The embedding function reloads model weights every call

A lazy embedding helper that loads the model inside the closure:

```python
def _default_embed_fn(hf_token, device="cpu"):
    def _embed(wav_path, spans):
        model = Model.from_pretrained("pyannote/embedding", token=hf_token)  # EVERY call!
        inference = Inference(model, window="whole", device=device)
        ...
    return _embed
```

reloads weights on every `_embed(...)`. Fine for a one-shot, but a batch run that
embeds many clusters across many episodes pays the load cost N times (and spams
"Lightning automatically upgraded checkpoint" logs).

## Context / Trigger conditions

- A cut/slice taken at diarisation timestamps contains the wrong audio, or is
  offset, while diarisation itself looks correct.
- You are feeding diarisation output `(start, end)` into `ffmpeg -ss/-to`,
  `yt-dlp --download-sections`, or any slicer.
- A batch diarisation/embedding job is far slower than per-item time x count, or
  logs a model load per item.

## Solution

**Timeline:** cut from the SAME wav the pipeline diarised. If diarisation ran on
the VAD wav, resolve that path (`vad_output_path(audio)`) and cut from it:

```python
vad_wav = vad_output_path(audio)          # the file the timestamps refer to
segments = diarise_episode(audio, tok)    # [(start, end, label)] on VAD timeline
cmd = ["ffmpeg", "-y", "-i", str(vad_wav), "-ss", f"{start:.3f}", "-to",
       f"{end:.3f}", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", out]
```

Cutting from the VAD wav also gives pure speech (silences already removed), which
is what you want for a voice reference anyway. (If you truly need original-file
timestamps, diarise the original and accept the silence, or map VAD->original via
the VAD segment table.)

**Performance:** load the model ONCE and close over it; reuse across calls:

```python
def make_cached_embed_fn(hf_token, device="cpu"):
    model = Model.from_pretrained("pyannote/embedding", token=hf_token)
    inference = Inference(model, window="whole", device=torch.device(device))
    def _embed(wav_path, spans):
        ...                                   # uses the captured inference
    return _embed
```

Also cache the diarisation `Pipeline` (pass a `pipeline_factory=lambda tok: pipe`
if the API supports it) so it is built once for the whole batch.

## Verification

- Timeline: cut one slice, listen / transcribe a few seconds, confirm it is the
  expected speaker's words. A validate step (mono/16k/pcm/duration) confirms
  format but NOT timeline correctness, so spot-check the content.
- Performance: the per-item log should show the model load ONCE at startup, then
  no further "checkpoint upgraded" lines per item.

## Notes

- `Model.from_pretrained(..., token=...)` vs `use_auth_token=...` differs across
  pyannote versions; try/except `TypeError` to support both.
- HF token env var order seen in practice: `HF_TOKEN`, then
  `HUGGINGFACE_TOKEN`, then `HUGGING_FACE_HUB_TOKEN`.
- Gated models (e.g. `pyannote/speaker-diarization-community-1`) need the licence
  accepted for the token, else `from_pretrained` 401s.
- Device `mps` on Apple Silicon was ~roughly an order of magnitude faster than
  `cpu` for a full-episode diarise in practice; it is opt-in.
