---
name: remotion-broll-overlay-audio-continuity
description: |
  Pattern for Remotion videos that combine a continuous primary talking-head
  clip (with audio) with muted B-roll overlays that jump into arbitrary scenes
  of other source videos via startFrom/trimBefore. Use when: (1) building a
  vlog/tutorial-style composition where the narrator's audio must never cut,
  (2) overlaying B-roll footage sourced from a single long video at different
  timestamps, (3) you see audio stutter / double-audio / primary audio
  disappearing when B-roll appears, (4) you need scene-specific cuts into a
  reference video without pre-trimming the source file.
author: Claude Code
version: 1.0.0
date: 2026-04-16
---

# Remotion B-Roll Overlay with Audio Continuity

## Problem

When building a Remotion composition with a primary talking-head video plus
overlay B-roll clips, the naive approach (nesting each B-roll inside its own
Sequence with audio enabled) causes three issues:

1. **Double audio** - primary and B-roll audio play simultaneously
2. **Audio cuts** - if you stop the primary and start the B-roll, narration
   breaks mid-sentence
3. **Pre-trimming waste** - physically trimming source videos into per-scene
   files duplicates data and invalidates when scenes shift

The fix is structural, not a prop tweak: the primary video must run the full
composition duration at the bottom of the layer stack with audio on, and
every B-roll must be `muted` and positioned with both a timeline `from`
(when it appears in the *final* video) and a `startFrom` / `trimBefore`
(where inside the *source* video playback begins).

## Context / Trigger Conditions

Use this pattern when any of these apply:
- The composition has one long primary audio track (talking head, voiceover,
  music bed) that must play uninterrupted
- B-roll content lives inside a single long source video (e.g. a recorded
  screen capture, a stock clip reel, a raw interview) and different moments
  are reused at different points in the final cut
- You see narration audio stutter, duplicate, or drop when B-roll appears
- You're wrapping each B-roll in its own `<OffthreadVideo>` without `muted`
- Your current approach pre-renders trimmed MP4s per scene (waste - use
  `trimBefore` instead)

## Solution

### Layer structure

```
AbsoluteFill (composition root)
├─ OffthreadVideo (primary, full duration, audio ON)          ← bottom layer
├─ Sequence from=F1 durationInFrames=D1
│   └─ OffthreadVideo (b-roll #1, muted, trimBefore=S1)
├─ Sequence from=F2 durationInFrames=D2
│   └─ OffthreadVideo (b-roll #2, muted, trimBefore=S2)
└─ ... (more overlays)
```

Key rules:
1. **Primary has no `Sequence` wrapper** (or `from={0}` and the full
   duration) - it plays for the entire composition.
2. **Every B-roll is `muted`** - no exceptions. Audio continuity comes from
   the primary layer; overlays are visual-only.
3. **Two separate time references per B-roll:**
   - `Sequence.from` = when in the *final video* the overlay appears
   - `OffthreadVideo.trimBefore` (or legacy `startFrom`) = where in the
     *source video* playback begins
4. **`Sequence.durationInFrames`** unmounts the B-roll when its scene ends,
   revealing the primary video underneath again.

### Canonical implementation

```tsx
import {
  AbsoluteFill,
  OffthreadVideo,
  Sequence,
  staticFile,
} from 'remotion';

type BRoll = {
  /** Frame in the final video where this overlay starts */
  from: number;
  /** How many frames the overlay is visible */
  durationInFrames: number;
  /** Frame inside the source video where playback begins */
  sourceStart: number;
  src: string;
};

export const TalkingHeadWithBRoll: React.FC<{
  primarySrc: string;
  brolls: BRoll[];
}> = ({primarySrc, brolls}) => {
  return (
    <AbsoluteFill>
      {/* Primary layer - audio source of truth, runs the full duration */}
      <OffthreadVideo src={staticFile(primarySrc)} />

      {/* B-roll overlays - muted, each jumps into its source scene */}
      {brolls.map((b, i) => (
        <Sequence
          key={i}
          from={b.from}
          durationInFrames={b.durationInFrames}
        >
          <OffthreadVideo
            src={staticFile(b.src)}
            trimBefore={b.sourceStart}
            muted
          />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
```

### Version-specific prop naming

| Remotion version | Prop name    | Notes                                                                 |
| ---------------- | ------------ | --------------------------------------------------------------------- |
| < 4.0.319        | `startFrom`  | Still works in later versions                                         |
| ≥ 4.0.319        | `trimBefore` | Preferred. Do not mix `startFrom` and `trimBefore` on the same clip.  |

`endAt` → `trimAfter` follows the same rename. If a B-roll source has
content you don't want past a certain frame, pair `trimBefore` with
`trimAfter`.

### Why `Sequence.from` and `trimBefore` are independent

`Sequence.from` remaps the child's `useCurrentFrame()` origin to 0 at
`from`. `OffthreadVideo.trimBefore` tells the decoder to skip the first N
frames of the source file. They compose cleanly:

- `<Sequence from={90}>` means "this overlay appears at final-video frame 90"
- `<OffthreadVideo trimBefore={300}>` means "start playback at source-video
  frame 300 (= 10s at 30fps)"

So a B-roll appearing at final frame 90 for 60 frames, showing source
content from 10s onward, is:

```tsx
<Sequence from={90} durationInFrames={60}>
  <OffthreadVideo src={staticFile('source.mp4')} trimBefore={300} muted />
</Sequence>
```

### Audio-ducking variant (optional)

If the B-roll *does* have audio you want to mix in (e.g. ambient crowd
noise under the narration), drop `muted` and use a per-frame `volume`
function on both layers. Keep the primary at 1.0 and the B-roll at ~0.15:

```tsx
<OffthreadVideo src={...} trimBefore={300} volume={0.15} />
```

Default to `muted` unless you have a concrete reason - it also skips the
audio-extraction step during render and is meaningfully faster.

## Verification

1. **Render a short test** (`npx remotion render --frames=0-120`) covering at
   least one overlay boundary.
2. **Audio check**: Play the output. The primary narration must be
   continuous - no cuts, no echo, no volume dip at B-roll boundaries.
3. **Visual check**: The B-roll appears exactly at `from` and disappears at
   `from + durationInFrames`. The first frame shown matches source frame
   `trimBefore` (compare against the source file at that timestamp).
4. **Studio preview**: scrub the timeline in `npx remotion studio` - the
   B-roll should mount/unmount at the right frames without audio artifacts.

If audio stutters at overlay boundaries: check that no B-roll is missing
`muted`. If the B-roll starts from the wrong content: `trimBefore` is in
frames, not seconds - multiply seconds by fps.

## Example

Build a 20-second (600 frame at 30fps) vlog where the narrator is on screen
continuously, with two B-roll cutaways:

- B-roll A: frames 60–180 (2s–6s), showing source-video content from 10s
- B-roll B: frames 300–420 (10s–14s), showing source-video content from 45s

```tsx
export const Vlog: React.FC = () => (
  <AbsoluteFill>
    <OffthreadVideo src={staticFile('narrator.mp4')} />

    <Sequence from={60} durationInFrames={120}>
      <OffthreadVideo
        src={staticFile('broll.mp4')}
        trimBefore={300}  // 10s * 30fps
        muted
      />
    </Sequence>

    <Sequence from={300} durationInFrames={120}>
      <OffthreadVideo
        src={staticFile('broll.mp4')}
        trimBefore={1350}  // 45s * 30fps
        muted
      />
    </Sequence>
  </AbsoluteFill>
);
```

Note both B-rolls reference the same source file - `trimBefore` makes
repeat-use of one source video trivial.

## Notes

- **AbsoluteFill children stack in DOM order** - the primary must come
  first in the JSX so B-roll overlays render on top. If your B-roll
  appears *behind* the narrator, you've reversed the order.
- **Frame units everywhere**. `from`, `durationInFrames`, `trimBefore`,
  `trimAfter` are all in frames. Compute with `fps` from
  `useVideoConfig()` when values are authored in seconds.
- **`muted` is not just a render optimisation** - during `remotion studio`
  preview it also silences the overlay, which is what you want for
  iteration.
- **Avoid `<Video>`** for B-roll overlays - `<OffthreadVideo>` renders via
  FFmpeg off the main thread and produces deterministic frames at any
  seek target, which is exactly what `trimBefore` needs. `<Video>` relies
  on the browser video element and can desync on seeks.
- **Overlapping B-rolls**: if two overlays overlap in time (A ends at 180,
  B starts at 160), the later-declared one wins visually. If that's not
  what you want, split them so they don't overlap, or use explicit
  `zIndex` on the wrapper.
- **Transitions**: for cross-fades between primary and B-roll, wrap the
  B-roll `<OffthreadVideo>` in an `<AbsoluteFill>` with an `opacity`
  driven by `interpolate(frame, [0, 15], [0, 1])` - don't try to fade the
  primary.

## References

- [OffthreadVideo docs](https://www.remotion.dev/docs/offthreadvideo) -
  full prop reference including `trimBefore`/`trimAfter` (v4.0.319+)
- [Sequence docs](https://www.remotion.dev/docs/sequence) - `from` and
  `durationInFrames` semantics
- [OffthreadVideo vs Video](https://www.remotion.dev/docs/video-vs-offthreadvideo) -
  why OffthreadVideo for deterministic seek
- [Recorder B-roll feature](https://www.remotion.dev/docs/recorder/editing/b-roll) -
  the Remotion Recorder's opinionated implementation of this same pattern
- [Overlay rendering config](https://www.remotion.dev/docs/overlay) -
  alpha-channel export when you need to composite in an external NLE instead
