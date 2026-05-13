---
name: remotion-talking-head-with-broll
description: |
  Remotion pattern for layering muted B-roll clips over a primary talking-head video
  without breaking audio continuity. Use when: (1) you want a single continuous voiceover
  from a talking-head source while showing varied visuals, (2) B-roll clips need to start
  partway through their source file via `startFrom`, (3) audio pops or double-audio artefacts
  appear from stacked `<OffthreadVideo>` components, (4) you need editorial B-roll cuts that
  don't fragment the primary audio track. Covers `OffthreadVideo`, `startFrom`, `muted`,
  `Sequence` positioning, and the single-audio-source invariant.
author: Claude Code
version: 1.0.0
date: 2026-04-15
---

# Remotion Talking-Head + B-Roll Layering

## Problem
A typical explainer video needs one continuous voiceover from a talking-head recording
plus editorial B-roll visuals that cut in and out. Naively dropping multiple
`<OffthreadVideo>` components into a composition produces overlapping audio tracks,
double voices, and choppy transitions because every `OffthreadVideo` plays its own
audio by default.

## Context / Trigger Conditions
- Building a Remotion composition with a primary speaker track plus cutaway footage
- Using `<OffthreadVideo>` for hardware-accelerated off-thread decoding
- B-roll source files are longer than the slot you want to show and need to be entered
  partway through (seek to a specific scene, not the head of the file)
- Symptoms that indicate the wrong pattern:
  - Two voices audible simultaneously
  - Audio volume drops or pops when a B-roll cut begins or ends
  - Seek artefacts when a B-roll clip starts from frame 0 instead of the intended scene

## Solution

### Core rules
1. **Exactly one audio source.** Keep the talking-head `<OffthreadVideo>` as the base
   layer with audio intact. Every B-roll overlay must set `muted` to disable its own
   audio track.
2. **Position the primary clip at frame 0** of the composition (or wrap it in a single
   `<Sequence from={0} durationInFrames={COMP_DURATION}>`) so its audio plays for the
   full composition duration without interruption.
3. **Overlay B-roll inside `<Sequence>`** blocks that control when each clip is visible.
   `from` = composition frame where the B-roll becomes visible;
   `durationInFrames` = how long it stays on screen.
4. **Use `startFrom` on the B-roll** to seek inside its source file. `startFrom` is in
   frames of the source media, not composition frames. This is how you "jump into a
   specific scene" without rendering the head of the clip.
5. **Render order matters.** Later children in JSX paint on top. Place B-roll clips
   after the primary in the tree so they cover the talking head when visible.

### Minimal skeleton

```tsx
import { Composition, OffthreadVideo, Sequence, staticFile } from "remotion";

const FPS = 30;
const DURATION = 30 * FPS;

export const TalkingHeadWithBRoll = () => (
  <>
    {/* Primary track: audio + video, plays for the whole composition */}
    <OffthreadVideo src={staticFile("talking-head.mp4")} />

    {/* B-roll 1: visible from 5s to 10s, seeks into source at 12s */}
    <Sequence from={5 * FPS} durationInFrames={5 * FPS}>
      <OffthreadVideo
        src={staticFile("broll-city.mp4")}
        startFrom={12 * FPS}
        muted
      />
    </Sequence>

    {/* B-roll 2: visible from 18s to 22s, seeks into source at 3s */}
    <Sequence from={18 * FPS} durationInFrames={4 * FPS}>
      <OffthreadVideo
        src={staticFile("broll-office.mp4")}
        startFrom={3 * FPS}
        muted
      />
    </Sequence>
  </>
);
```

### Data-driven variant

For programmatic compositions (scripts, CMS-driven videos), model the B-roll as an array
and map to `<Sequence>` + `<OffthreadVideo>` pairs:

```tsx
type BRollClip = {
  src: string;
  compositionStartFrame: number;
  durationFrames: number;
  sourceStartFrame: number;
};

export const DataDrivenComp = ({ broll }: { broll: BRollClip[] }) => (
  <>
    <OffthreadVideo src={staticFile("talking-head.mp4")} />
    {broll.map((clip, i) => (
      <Sequence
        key={`${clip.src}-${i}`}
        from={clip.compositionStartFrame}
        durationInFrames={clip.durationFrames}
      >
        <OffthreadVideo
          src={staticFile(clip.src)}
          startFrom={clip.sourceStartFrame}
          muted
        />
      </Sequence>
    ))}
  </>
);
```

## Verification

After rendering, confirm:
1. **Single continuous audio track** from start to end of the render. No drops at
   B-roll boundaries.
2. **B-roll starts at the intended scene**, not frame 0 of the source file.
   Scrub the timeline preview in the Remotion Studio to eyeball this.
3. **No audio doubling**: play the rendered MP4 and listen for echo during
   B-roll overlap windows. If you hear the B-roll's own audio, a `muted` prop
   is missing.
4. **B-roll appears for exactly the intended duration**. The `<Sequence>` window
   is authoritative; content outside it is hidden even if `durationInFrames` on
   the source is longer.

## Example

A product demo where the presenter speaks for 30 seconds and three B-roll clips
illustrate different features:

```tsx
const DemoVideo = () => (
  <>
    <OffthreadVideo src={staticFile("host-30s.mp4")} />

    {/* Feature 1 callout: show dashboard B-roll from its 8s mark */}
    <Sequence from={3 * FPS} durationInFrames={4 * FPS}>
      <OffthreadVideo src={staticFile("dashboard.mp4")} startFrom={8 * FPS} muted />
    </Sequence>

    {/* Feature 2 callout: mobile view starts at source 0s */}
    <Sequence from={12 * FPS} durationInFrames={5 * FPS}>
      <OffthreadVideo src={staticFile("mobile.mp4")} startFrom={0} muted />
    </Sequence>

    {/* Feature 3 callout: analytics B-roll starts mid-animation */}
    <Sequence from={22 * FPS} durationInFrames={5 * FPS}>
      <OffthreadVideo src={staticFile("analytics.mp4")} startFrom={15 * FPS} muted />
    </Sequence>
  </>
);
```

The host's voiceover runs uninterrupted for the full 30 seconds; the three B-roll
clips appear on top at their scheduled windows, each entering its source file at the
right scene.

## Notes

- **`startFrom` is in source frames, not composition frames.** Multiply the source
  second offset by the source file's FPS if it differs from the composition FPS.
  `OffthreadVideo` interpolates across FPS mismatches, but the `startFrom` unit is
  always source frames.
- **`muted` is required on every B-roll clip.** Forgetting it on even one overlay
  leaks audio. If you need a B-roll clip to carry its own audio and duck the main
  voiceover, use `<Audio>` with `volume` keyframes instead of stacking audio-bearing
  `<OffthreadVideo>` layers.
- **Transitions**: use `@remotion/transitions` or opacity interpolation wrapped
  around the B-roll `<Sequence>` children, not around the primary clip, or you will
  interrupt the voiceover.
- **Fallback for Chromium seek bugs**: if B-roll preview shows a frozen first frame
  at small `startFrom` values, bump `startFrom` by one frame or pre-render the clip
  to its trimmed range via the Remotion CLI (`@remotion/renderer`).
- **Performance**: `OffthreadVideo` runs decoding in a separate thread. It is the
  correct primitive for this pattern. `<Video>` (the player-thread variant) also
  works but blocks the main thread on slower machines when multiple clips overlap.
- **Single-source-of-truth audio**: if the talking-head recording is audio-only plus a
  static portrait, use `<Audio>` for the voice and `<OffthreadVideo muted>` for the
  visuals. The rule "exactly one audio source" becomes "exactly one `<Audio>` or one
  unmuted `<OffthreadVideo>`".
- **Seeking precision**: Remotion snaps to the nearest keyframe internally. If you
  need frame-accurate B-roll scene entries for very short windows (under ~10 frames),
  re-encode the source with a shorter GOP (`-g 1` in ffmpeg) so every frame is a
  keyframe.

## References

- [Remotion `<OffthreadVideo>` docs](https://www.remotion.dev/docs/offthreadvideo)
- [Remotion `<Sequence>` docs](https://www.remotion.dev/docs/sequence)
- [Remotion `startFrom` / `endAt` reference](https://www.remotion.dev/docs/offthreadvideo#startfrom)
- [Remotion `<Audio>` vs `<Video>` audio handling](https://www.remotion.dev/docs/audio)
