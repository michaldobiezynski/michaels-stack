---
name: remotion-broll-overlay-talking-head
description: |
  Compose a Paddy-Galloway-style YouTube video in Remotion by layering a muted
  B-roll OffthreadVideo on top of a primary talking-head OffthreadVideo so the
  talking head's audio keeps playing while the visual cuts to animated B-roll.
  Use when: (1) combining a recorded talking-head .mov with Remotion-rendered
  animated clips into one composition, (2) cutting to B-roll visuals without
  losing voiceover from the underlying clip, (3) jumping into a specific scene
  of a longer pre-rendered Remotion B-roll (e.g. skip the title card, land on
  the "drop zone" scene), (4) building chapter/section intros between talking
  head segments, (5) trimming silence/hand-waves at head and tail of a
  talking-head clip without re-encoding the source, (6) aligning B-roll
  cutaways to exact spoken phrases using Whisper word-level timestamps,
  (7) fixing "B-roll cutaway freezes on the source's closing title card"
  which is caused by `OffthreadVideo` with `startFrom` inheriting the
  parent Sequence's current frame and running past the source end.
  Covers the `muted`, `startFrom`, and `objectFit: cover` props together with
  Sequence offset arithmetic for non-overlapping segments, trim-in/trim-out
  patterns, Whisper-driven cue alignment, and the MANDATORY
  `<Sequence from={start} durationInFrames={duration}>` wrapper around any
  OffthreadVideo that uses `startFrom` inside an already-offset parent Sequence.
author: Claude Code
version: 1.2.0
date: 2026-04-15
---

# Remotion B-roll Overlay Over Talking Head

## Problem

You have two kinds of inputs:

1. A recorded talking-head `.mov` with baked-in audio (the voiceover).
2. A library of pre-rendered Remotion feature videos (animated app walkthroughs)
   that have no audio.

You want one composite YouTube video where the talking head plays continuously
(so the voiceover never drops) but the picture periodically cuts to full-screen
animated B-roll from the feature videos, Paddy-Galloway-style. The B-roll
should land on a specific scene of the source clip, not the title card at the
start.

The non-obvious parts:

- Does the underlying audio keep playing when the visual is covered?
- How do you make the B-roll start at scene 3 of a longer pre-rendered clip?
- How do you avoid the B-roll clip's own (silent) audio track fighting with the
  talking head?

## Context / Trigger Conditions

- Building a release recap, tutorial, or "feature walkthrough" video in Remotion
- Source assets: one or more `.mov` talking-head clips + multiple pre-rendered
  Remotion composition `.mp4`s used as B-roll
- Paddy Galloway / MKBHD / YouTube-style editing with fast cuts, big text
  overlays, and section intros
- Need to preserve the talking-head audio across the whole segment

## Solution

### 1. Put every asset in `public/` and load with `staticFile()`

Remotion's `OffthreadVideo` needs either a `staticFile()` path or a remote URL.
Copy both the talking-head `.mov` and the B-roll `.mp4`s into `public/` with
predictable names:

```
public/
  release018-intro.mov            # talking head
  release018-image-import.mov     # talking head
  release018-broll-image-import.mp4   # pre-rendered Remotion B-roll
```

### 2. Primary layer: talking-head `OffthreadVideo` (with audio)

Render the talking head as the bottom layer inside an `AbsoluteFill`. Use
`objectFit: cover` so 16:9 sources fill a 1920x1080 composition cleanly.

```tsx
<AbsoluteFill style={{ background: COLORS.background }}>
  <OffthreadVideo
    src={staticFile("release018-image-import.mov")}
    startFrom={IMAGE_TRIM_IN}   // skip head silence / hand-wave
    style={{ width: "100%", height: "100%", objectFit: "cover" }}
  />
  {/* overlays go here, see below */}
</AbsoluteFill>
```

Do NOT pass `muted` here — you want the voiceover.

**`startFrom` on the PRIMARY clip trims head silence**: recorded takes usually
have 1-3 seconds of hand-wave / throat-clear / settling before the first
spoken word. Set `startFrom={N}` to skip straight to speech. Cap the tail by
putting this OffthreadVideo inside a `<Sequence durationInFrames={TRIM_DUR}>`
where `TRIM_DUR` ends a few frames after the last spoken word. You never need
to re-encode the source — trimming is purely composition-time.

```tsx
const IMAGE_TRIM_IN = 60;      // 2.00s — first word starts at ~2.05s
const IMAGE_TRIM_DUR = 1224;   // 40.80s — last word ends at ~40.6s

<Sequence from={IMAGE_START} durationInFrames={IMAGE_TRIM_DUR}>
  <OffthreadVideo
    src={staticFile("release018-image-import.mov")}
    startFrom={IMAGE_TRIM_IN}
    style={{ width: "100%", height: "100%", objectFit: "cover" }}
  />
</Sequence>
```

### 3. B-roll overlay: muted `OffthreadVideo` inside its own `Sequence`

Wrap each B-roll in its **own** `<Sequence from={start} durationInFrames={duration}>`
— not just in an `AbsoluteFill` — so the `OffthreadVideo`'s `startFrom` is
measured from the Sequence's own frame 0, not from the outer segment's current
frame. Skipping this wrapper is the #1 failure mode of this pattern (see §3a).

While the overlay is at opacity 1, it visually covers the talking head, but
the talking head's audio keeps playing because its component is still mounted
in the tree.

Key props on the overlay:

- `muted` — prevents the B-roll's (silent) audio from touching the track mix
- `startFrom={N}` — jump into frame N of the B-roll source; skip the title card
- `style={{ objectFit: "cover" }}` — fill the composition without letterboxing

Split the overlay into two components: an inner `BRollContent` that reads
`useCurrentFrame()` relative to the wrapping Sequence, and an outer
`BRollOverlay` that places `BRollContent` inside
`<Sequence from={start} durationInFrames={duration}>`:

```tsx
const BRollContent: React.FC<{
  src: string;
  duration: number;
  startFrom: number;
}> = ({ src, duration, startFrom }) => {
  const frame = useCurrentFrame();   // 0 at Sequence start
  const enter = interpolate(frame, [0, 6], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  const exit = interpolate(frame, [duration - 6, duration], [1, 0], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill style={{ opacity: Math.min(enter, exit) }}>
      <OffthreadVideo
        src={staticFile(src)}
        startFrom={startFrom}
        muted
        style={{ width: "100%", height: "100%", objectFit: "cover" }}
      />
    </AbsoluteFill>
  );
};

const BRollOverlay: React.FC<{
  src: string;
  start: number;       // frame in the segment where the cutaway begins
  duration: number;    // how many frames the cutaway stays up
  startFrom: number;   // frame inside the B-roll source to jump to
}> = ({ src, start, duration, startFrom }) => (
  <Sequence from={start} durationInFrames={duration}>
    <BRollContent src={src} duration={duration} startFrom={startFrom} />
  </Sequence>
);
```

### 3a. Critical gotcha: wrap OffthreadVideo with startFrom in its own Sequence

**Symptom**: B-roll cutaways in deep-segment positions render as the source's
*closing title card* (not the intended scene), often as a single frozen frame.
Early-segment cutaways may look correct while late ones look broken. Also
appears as B-roll "text cards" that you meant to skip showing up anyway.

**Cause**: `OffthreadVideo`'s effective source frame is
`startFrom + current_parent_Sequence_frame`. If you put
`<OffthreadVideo startFrom={N} />` directly inside an outer Sequence offset
`X`, then at outer frame `X + k` the displayed source frame is `N + k`. When
`N + k` exceeds the source's length, OffthreadVideo clamps to the last frame
(usually the closing title of your pre-rendered B-roll).

Gating an overlay with
`if (frame - start < 0 || frame - start > duration) return null` does **not**
fix this — the `OffthreadVideo`'s timeline is governed by its parent Sequence,
not by conditional rendering of the React subtree.

**Fix**: wrap the overlay in its own
`<Sequence from={start} durationInFrames={duration}>`. This creates a fresh
time origin so the `OffthreadVideo` sees its parent Sequence starting at
`start`; at that moment its internal time is 0, and `startFrom={N}` correctly
shows source frame `N` (not `N + start`).

```tsx
// ❌ BUG: source frame shown = startFrom + outer_frame
<AbsoluteFill style={{ opacity }}>
  <OffthreadVideo startFrom={130} muted ... />
</AbsoluteFill>

// ✅ FIX: new Sequence time origin, OffthreadVideo sees time = 0 at start
<Sequence from={start} durationInFrames={duration}>
  <AbsoluteFill style={{ opacity }}>
    <OffthreadVideo startFrom={130} muted ... />
  </AbsoluteFill>
</Sequence>
```

**How to spot this in the wild**: extract a frame from the rendered mp4 at
the cutaway's start and compare to the B-roll source at frame `startFrom`.
If the rendered frame matches `source[startFrom + start]` instead of
`source[startFrom]`, you've hit this bug. For cutaways where
`startFrom + start` exceeds the source length, you'll see the source's final
frame frozen on screen.

```bash
# Rendered frame at composition time t=90.1s (≈2703 frames @ 30fps)
ffmpeg -ss 90.1 -i out/release.mp4 -frames:v 1 rendered-2703.png

# Intended B-roll source frame startFrom=570
ffmpeg -i public/release018-broll-puzzle-from-position.mp4 \
  -vf "select=eq(n\,570)" -vframes 1 expected-570.png

# If rendered-2703.png shows the source's closing title card,
# the Sequence wrapper is missing around the OffthreadVideo.
```

### 4. Pick `startFrom` values by knowing the B-roll scene layout

The Remotion B-roll videos typically have scenes laid out with `<Sequence>` at
known frame offsets — e.g. title 0-90, scene 2 at 90-270, scene 3 at 270-480.
To cut to "scene 2" (drop zone demo), use `startFrom={120}` (a bit after scene
start so its spring animation is already into its arc, not mid-fade-in).

Rule of thumb: `startFrom = sceneStartFrame + 30` feels right — you skip the
first second of entrance animation so the B-roll lands already looking
"settled." Landing mid-spring looks like an "uncanny valley" blurry/warping
moment — always land on steady-state frames.

**Audit the TARGET scene's content, not just its timing.** Pre-rendered
Remotion B-roll clips often include explainer scenes that are *pure text
cards* (e.g. "Tweak before you import", "Drag any piece to fix detection")
sitting on a solid background. Landing a cutaway there is technically
settled but visually identical to a SlamText overlay — viewers perceive it
as "just text on a background" and ask why you bothered cutting at all.

For each planned cutaway, open the B-roll source's component file and check
what the target scene actually renders. If it's predominantly text/words,
pick a different scene (usually the prior or following one that shows the
real UI/board/animation). If NO scene in the current B-roll has visual
content matching the narration, **cross-source from another B-roll** that
does — e.g. in an Image Import segment where the speaker says "I've also
introduced a button that will allow you to build a puzzle", use the
*puzzle-from-position* B-roll (which shows that toolbar+button) instead of
the image-import B-roll (which doesn't).

```tsx
{/* Cross-source cutaway: narration about a feature shown in a different B-roll */}
<BRollOverlay
  src="release018-broll-puzzle-from-position.mp4"
  start={462} duration={130} startFrom={130}  // scene 2 = toolbar + button
/>
```

### 4b. Align B-roll cutaways to spoken phrases via Whisper word timestamps

The common failure mode of this pattern is B-roll that shows up while the
speaker is talking about something *else*. To eliminate this, transcribe each
talking-head clip at word level with Whisper and drive cue points from the
JSON:

```bash
whisper clip.mov --word_timestamps True --output_format json \
  --model small.en --output_dir /tmp/transcripts
```

The resulting JSON contains `words: [{word, start, end}]`. For each B-roll
cutaway, note the source-clip seconds during which the matching phrase is
spoken, then convert to segment-local frames:

```tsx
// User says "drop in images of a chess position" from 5.0-8.6s of source.
// Segment starts at IMAGE_START with startFrom=2.0s, so segment-local
// frame = (source_seconds - 2.0) * 30 fps.
// 5.0s → 90, 13.6s → 348. Duration 258 frames.
<BRollOverlay
  src="release018-broll-image-import.mp4"
  start={90} duration={260} startFrom={130}  // scene 2 settled
/>
```

Budget the `start` to lead the phrase by 3-5 frames (the human eye catches up
faster than the ear), and let `duration` cover to a natural beat-end word like
"now" or "them" rather than cutting mid-clause.

Also use first-word and last-word timestamps to set `TRIM_IN` and `TRIM_DUR`:

```
first word "First" @ 2.420s  → TRIM_IN  = round(2.00 * 30) = 60
last  word "now."  @ 42.300s → TRIM_DUR = round((42.80 - 2.00) * 30) = 1224
```

Subtract 0.2-0.5s from first-word start and add 0.3-0.5s after last-word end
so the clip breathes (don't cut on the exact consonant).

### 5. Chapter cards BETWEEN segments, not overlapping

For section intros (`01 · IMAGE IMPORT`), don't overlay — *replace*. Place each
talking-head segment and each chapter card in non-overlapping `Sequence`s with
manual offset arithmetic:

```tsx
const INTRO_DUR = 433;      // duration of talking head A
const SECTION_DUR = 45;      // chapter card
const IMAGE_DUR = 1290;      // duration of talking head B

const INTRO_START = 0;
const SEC1_START  = INTRO_START + INTRO_DUR;     // 433
const IMAGE_START = SEC1_START  + SECTION_DUR;   // 478
```

Get the exact duration of each talking-head clip from ffprobe:

```bash
ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 clip.mov
# → 43.000000
# → 43.000000 * 30 fps = 1290 frames
```

### 6. Text overlays ("slam-in") also sit inside the segment AbsoluteFill

For Paddy-Galloway slam-in text, use `spring({..., damping: 10, stiffness: 220})`
for entrance and `interpolate(local, [duration-8, duration], [1, 0])` for exit,
combined with `Math.min(enter, exit)` so late entrances still fade cleanly at
the end.

## Verification

- `ffprobe` the rendered output and confirm both video (h264) and audio (aac)
  streams exist and match expected duration.
- Scrub through the mp4: during an overlay window the picture should show B-roll
  but the voiceover continues uninterrupted. If audio drops during overlays,
  you forgot to keep the bottom `OffthreadVideo` mounted.
- If the B-roll plays its own unwanted audio, add `muted` to the overlay's
  `OffthreadVideo`.
- **If a cutaway displays the B-roll source's closing title card instead of
  the intended scene (or a single frozen frame), you're missing the
  `<Sequence from={start} durationInFrames={duration}>` wrapper around the
  `OffthreadVideo` — see §3a.** Extract the rendered frame at the cutaway's
  `start` and compare against `source[startFrom]` with ffmpeg to confirm.

## Example

Full skeleton for a segment with one talking head + three B-roll cutaways +
a lower-third caption:

```tsx
const ImageImportSegment: React.FC = () => (
  <AbsoluteFill style={{ background: COLORS.background }}>
    {/* Primary: talking head with audio */}
    <OffthreadVideo
      src={staticFile("release018-image-import.mov")}
      style={{ width: "100%", height: "100%", objectFit: "cover" }}
    />

    {/* B-roll cutaways — audio from talking head keeps playing */}
    <BRollOverlay src="release018-broll-image-import.mp4"
      start={240} duration={210} startFrom={120} />
    <BRollOverlay src="release018-broll-image-import.mp4"
      start={540} duration={240} startFrom={290} />
    <BRollOverlay src="release018-broll-image-import.mp4"
      start={870} duration={260} startFrom={500} />

    {/* Lower-third caption at beginning */}
    <LowerThird title="Image Import" subtitle="Photo to position"
      start={30} duration={180} />
  </AbsoluteFill>
);
```

## Notes

- `OffthreadVideo` vs `Video`: prefer `OffthreadVideo` in Remotion — it decodes
  off the main thread and gives more reliable frame accuracy for compositions
  with multiple stacked video layers.
- `Audio` component: if you need to *replace* the talking-head audio with a
  separate track (e.g. swap voiceover), use `<Audio muted={someCondition} />`
  on the talking-head OffthreadVideo via the `muted` prop instead of trying to
  remove it.
- Rendering a ~170s composition with 4 video tracks and dozens of overlays
  takes about 1-2 minutes on an M1/M2 with `--concurrency=8`.
- The resulting mp4 will have both h264 video and aac audio streams by default
  when the primary OffthreadVideo has audio.

### Visual softness pitfalls ("uncanny valley B-roll")

If overlays look blurry, hazy, or "wrong" during playback, the cause is
almost always one of these:

- **`backdrop-filter: blur(Npx)`** on text overlays softens the entire
  underlying frame and makes crisp B-roll look smeared. Drop the backdrop
  blur and use a solid high-contrast background behind text instead.
- **`transform: scale(1.04)` or similar gentle zoom** on B-roll overlays
  looks "drifty" at 30 fps — viewers read it as motion blur. Keep overlays
  at scale 1 and let the B-roll content itself animate.
- **Landing mid-entrance-spring via `startFrom`** captures the B-roll while
  its own components are mid-interpolation (half-faded text, pieces sliding
  in). Bump `startFrom` by +30 to +40 frames past `sceneStart` so you land
  on a settled frame.
- **`rgba()` backgrounds on slam-in text** let the talking head bleed
  through. Use `COLORS.background` solid — the point of slam text is a hard
  cut, not a tint.
- **Timing mismatch to voiceover** (B-roll about topic A while speaker is
  now on topic B) reads as "uncanny valley" even when visuals are sharp.
  The Whisper-word-timestamp alignment in §4b is the fix — don't eyeball it.
- **Cutaway frozen on source's closing frame** (or showing a text card you
  never intended) means the `OffthreadVideo`'s `startFrom` is being measured
  from the wrong origin because no `<Sequence from={start}>` wraps it — see
  §3a. This bug only surfaces for late cutaways where
  `startFrom + start > source_length`, so early cutaways can mask it.

## References

- [Remotion OffthreadVideo docs](https://www.remotion.dev/docs/offthreadvideo)
- [Remotion Sequence docs](https://www.remotion.dev/docs/sequence)
- [Remotion staticFile docs](https://www.remotion.dev/docs/staticfile)
- Paddy Galloway — [@PaddyG96 on YouTube](https://www.youtube.com/@PaddyGalloway) (style reference)
