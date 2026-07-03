---
name: audio-visual-asd-coverage-vs-accuracy-eval
description: |
  How to decide whether audio-visual active-speaker detection (ASD) will actually
  improve speaker attribution on EDITED interview / podcast video (as opposed to a
  Zoom-style always-on per-person camera). Use when: (1) audio-only diarisation is
  poor on rapid-fire / overlap and someone proposes "just use the video / lip
  motion", (2) evaluating ASD on YouTube interview footage with cuts, reaction
  shots and wide two-shots, (3) an ASD model scores well on-screen but its
  standalone number is unimpressive and you need to know why. The key idea: measure
  COVERAGE (fraction of speech where the speaker's face is on screen AND detected)
  SEPARATELY from ACCURACY-WHEN-COVERED, because standalone ASD is capped by
  reaction shots / off-screen speaker, and the real win is audio+video FUSION.
author: Claude Code
version: 1.0.0
date: 2026-07-01
---

# Evaluating audio-visual ASD on edited interview footage

## Problem

When audio-only diarisation fails on rapid-fire two-person speech, the tempting fix
is "use the video, attribute speech to whoever's lips move" (like Zoom). But Zoom's
edge is separate per-person streams/cameras, not better modelling. On an EDITED
single-feed video (YouTube interview), the director cuts to reaction shots and wide
angles, so the speaker is frequently off-screen or too small to detect. A raw ASD
accuracy number hides this and leads to wrong conclusions ("ASD is no better than
audio" or "ASD is great") depending on the footage.

## Context / Trigger conditions

- Deciding whether to build an AV pipeline to fix diarisation on interview podcasts.
- An ASD model (LR-ASD / TalkNet, see [[lr-asd-active-speaker-detection-apple-silicon]])
  produces per-frame active-speaker labels and you want a fair verdict.
- The footage has cuts, reaction shots (camera on the listener), and wide two-shots.

## Solution: split the metric

Against a hand-labelled (ear-verified) reference, compute THREE numbers, not one:

1. **Coverage** = fraction of labelled speech time where ASD found ANY active
   on-screen face. This is the reaction-shot / off-screen / face-detection ceiling.
   It is largely model-independent, so it tells you the best any ASD could do here.
2. **Accuracy-when-covered** = of the covered time, how often ASD picked the right
   person. Map per-shot face tracks to identities with face recognition, or as an
   upper bound use an ORACLE mapping (label each track by its reference majority) and
   flag it as optimistic.
3. **Standalone accuracy** = accuracy-when-covered x coverage (off-screen counts
   wrong). This is what ASD alone delivers, and it is usually disappointing.

Then estimate **fusion**: `coverage x accuracy_when_covered + (1 - coverage) x
audio_accuracy`. Fusion (video when the speaker is visible, audio otherwise) is the
only thing that beats either modality alone on edited footage.

## Verification / worked result

On the deliberately-hardest 60 s of a 20VC episode (two-person, edited), against an
ear-verified gold: **coverage 67%**, **accuracy-when-covered 88%** (oracle upper
bound), **standalone ASD 59%**. Audio-only on the same window was ~62-69%. So
standalone video ~= audio, but fusion estimated ~80%. Conclusion: video is a strong
signal WHEN the speaker is on screen, but reaction shots cap coverage, so only fusion
pays off, and only if that hard fraction of content is worth the pipeline.

## Notes

- Sanity-check the footage first by extracting a few frames at reference speaker
  changes; if reaction shots put the speaker off-screen, coverage will be < 100% no
  matter how good the model is. This can save you the whole build.
- Weight the decision by how much of the corpus is actually the hard case. If
  rapid-fire is ~2% of an episode, a 15-point fusion gain on 2% is often not worth a
  video + face-recognition + fusion pipeline; a cheap transcript/LLM tiebreak may do.
- Zoom/Meet-level per-utterance labelling is easy for them because each participant is
  a separate stream; you cannot obtain isolated source tracks for a scraped/published
  mixed-feed show, so mixed-audio + edited-video is the real constraint.
