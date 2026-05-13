---
name: shorts-hook-frame-headline-card
description: |
  Add a 1-2 second static "headline card" overlay at the start of every
  TikTok / Reels / YouTube Shorts clip to stop the FYP scroll. The card
  shows a big-text question or hook that primes the viewer for the
  payoff. Use when:
  (1) building a podcast-clipping pipeline where Shorts open with a
  bare talking head and the first 0.5s of audio isn't enough to retain
  scrollers, (2) you want the same "question-then-answer" framing that
  Opus Clip, Munch, and most pro podcast clippers use, (3) the source
  is an interview where the HOST'S question is often a punchier hook
  than the GUEST'S opening sentence, (4) you're already overlaying
  burned-in captions via the concat-demuxer pattern and want to stack
  a hook card on top without re-architecting the filter graph.
  Covers: which text to put on the card (priority order:
  rephrased-host-question, then clip.hook, then clip.topic), PIL
  rendering at 100+pt over a darkened backdrop, and the ffmpeg overlay
  layer that stacks on top of any existing caption track via
  enable='between(t,0,DURATION)'.
author: Claude Code
version: 1.1.0
date: 2026-05-13
---

# Shorts hook frame: 1.6s headline card to stop the FYP scroll

## Problem

Vertical Shorts that open on a bare talking-head face don't retain
scrollers. The first 0.5 seconds need to communicate "this clip is about
X and here's the question you'll want answered". Generic options like
"music sting" or "logo flash" don't carry the topic; what works is a
huge static text card stating the question or contrarian claim, held
for 1-1.5 seconds while the speaker's audio begins under it.

For a podcast interview, the strongest text on the card is often NOT
the guest's opening sentence. The HOST'S preceding question
("Is Salesforce dead because of AI agents?") is more provocative than
the guest's hedge-heavy first response ("All the traditional SAS
companies are definitely under threat..."). The pipeline needs to
identify and use that.

## Context / Trigger conditions

- You're rendering Shorts from podcast / interview source video.
- An LLM analyses transcripts and picks N clips per episode.
- Output goes to TikTok / Reels / YouTube Shorts; first-second retention
  matters because the FYP is unforgiving.
- You're already overlaying captions; the hook card needs to coexist
  with that overlay chain.
- ffmpeg lacks libass / libfreetype (Homebrew default) so you can't use
  the `subtitles=` or `drawtext` filters with timed expressions.

## Solution

Two-part: (a) ask the LLM for a punchy `preceding_question` per clip in
addition to the speaker's own `hook`; (b) render a fullscreen PNG and
overlay it on the first 1.5-1.7 seconds of the talking head.

### Part 1: extend the analyse prompt

Add a `preceding_question` field to the per-clip JSON contract:

```
"preceding_question": string,
// The host's question in the 15s BEFORE this clip's start, rephrased
// as a punchy headline (max 8 words). Empty string if the clip stands
// alone or the speaker IS the host. This will be used as the on-screen
// hook card.
```

"Max 8 words" matters because the card is rendered at ~100pt; long
questions wrap to 4-5 lines and stop reading like a hook.

### Part 2: pick the hook text

Priority order in the renderer:

```python
def pick_hook_text(clip: dict) -> str:
    q = (clip.get("preceding_question") or "").strip()
    if q:
        return q
    h = (clip.get("hook") or "").strip()
    if h:
        # Truncate at first sentence-end
        for sep in [". ", "? ", "! "]:
            if sep in h:
                h = h.split(sep, 1)[0] + sep.strip()
                break
        return h
    return (clip.get("topic") or "WATCH THIS").strip()
```

The preceding question is the strongest hook when present (host frames
the topic, viewer wants the guest's answer). The clip's own hook is
fine when the speaker IS the host or no clean setup exists. Topic is
the bare fallback.

### Part 3: render the PNG

Fullscreen RGBA, semi-opaque dark backdrop, huge centred caps:

```python
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920  # Shorts vertical
HOOK_FONT_SIZE = 110
HOOK_STROKE_WIDTH = 9
HOOK_SIDE_MARGIN = 90      # pixel margin each side; wrap by pixel width not char count
HOOK_BG_ALPHA = 200        # 0-255 darkening

def render_hook_frame_png(text: str, out_path, font_path):
    text_caps = text.strip().upper()
    font = ImageFont.truetype(font_path, HOOK_FONT_SIZE)
    # CRITICAL: wrap by pixel width, not character count. textwrap.wrap
    # underestimates line width because glyphs vary (W is ~3x wider than i
    # at 110pt all-caps), so a 14-char limit overflows 1080px on words like
    # WORKPLACE. See sibling skill pil-pixel-aware-word-wrap-large-fonts.
    lines = _wrap_by_pixel_width(text_caps, font, W - 2 * HOOK_SIDE_MARGIN) or [text_caps]

    img = Image.new("RGBA", (W, H), (0, 0, 0, HOOK_BG_ALPHA))
    draw = ImageDraw.Draw(img)
    ascent, descent = font.getmetrics()
    line_height = int((ascent + descent) * 1.05)
    block_top = (H - line_height * len(lines)) // 2

    for i, line in enumerate(lines):
        # Per-token rendering with keyword highlighting (yellow for numbers,
        # proper nouns, acronyms; white for everything else). See related
        # skill `tiktok-style-caption-keyword-highlighting` for the
        # is_keyword heuristic and centred-line draw helper.
        draw_centred_line_with_highlights(
            draw, line, font, W, block_top + i * line_height,
            stroke_width=HOOK_STROKE_WIDTH,
        )
    img.save(out_path)
```

### Part 4: concat as a silent intro (preferred) or overlay on the body

Two implementation choices, with different feel:

**Option A (preferred, v1.1+): STANDALONE SILENT INTRO.** Prepend the
hook PNG as its own video segment for `HOOK_FRAME_DURATION` seconds.
Body audio is delayed by the same amount via `adelay`. Captions are
baked into the body before concat, so they don't play during the intro
either. Result: viewer reads the headline in silence for 2-3 seconds,
then the talking head begins with audio and captions in sync.

**Option B (v1.0 legacy, ok for very short holds <1.5s): TIMELINE OVERLAY.**
Overlay the hook PNG on top of the talking head for the first 1.5s
with `enable='between(t,0,1.5)'`. Audio and captions play under the
hook frame so the speaker is mid-sentence when the card disappears.
Faster perceived pace; worse for hooks longer than 4-5 words because
the viewer doesn't have time to read.

The A/B trade-off: A is preferred when you want the viewer to fully
process the headline before audio starts (the standard pro-clipper
look). B is preferred when you want a tighter "drop-in" feel and the
hook text is very short (e.g. 2-3 words).

#### Option A: silent intro concat (preferred)

Render the hook PNG with SOLID background (alpha 255) since it stands
alone, not as an overlay. Feed it as an extra input with `-loop 1
-framerate 30 -t HOOK_FRAME_DURATION` so it arrives at the filter
graph as a fixed-duration video stream. Then in the filter graph:

```python
HOOK_FRAME_DURATION = 2.5  # seconds of silent hold

# Body: blur-bg + talking head + captions (if any)
body = (
    "[0:v]setpts=PTS-STARTPTS,split=2[m_in][b_in];"
    f"[b_in]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
    "gblur=sigma=22[bg];"
    f"[m_in]scale={W}:-2[main];"
    f"[bg][main]overlay=(W-w)/2:(H-h)/2[clip_v]"
)
parts = [body]
if has_captions:
    parts.append(";[clip_v][1:v]overlay=0:0:shortest=0[body]")
else:
    parts.append(";[clip_v]null[body]")
parts.append(";[body]format=yuv420p,fps=30[body_norm]")

# Hook intro: PNG already arrives as a HOOK_FRAME_DURATION-second video
# (because of the -loop/-framerate/-t flags on its input). Just scale,
# normalise the pixel format, then concat with the body.
if has_hook_frame:
    hook_idx = 2 if has_captions else 1
    parts.append(
        f";[{hook_idx}:v]scale={W}:{H},format=yuv420p,fps=30,"
        "setpts=PTS-STARTPTS[hook_v]"
    )
    parts.append(";[hook_v][body_norm]concat=n=2:v=1:a=0[outv]")
    # Pad HOLD seconds of silence at the start of the body audio.
    delay_ms = int(HOOK_FRAME_DURATION * 1000)
    parts.append(
        ";[0:a]aresample=async=1:first_pts=0,asetpts=PTS-STARTPTS,"
        f"adelay={delay_ms}|{delay_ms}[outa]"
    )
    audio_map = "[outa]"
else:
    parts.append(";[body_norm]null[outv]")
    audio_map = "0:a"

filter_complex = "".join(parts)

cmd = [
    "ffmpeg", "-y",
    "-ss", f"{clip_start:.3f}", "-t", f"{duration:.3f}",
    "-i", str(source_video),
]
if has_captions:
    cmd += ["-f", "concat", "-safe", "0", "-i", str(caption_concat_list)]
if has_hook_frame:
    # Crucially: -loop 1 -framerate 30 -t makes the PNG arrive as a
    # HOOK_FRAME_DURATION-second 30fps stream.
    cmd += [
        "-loop", "1",
        "-framerate", "30",
        "-t", f"{HOOK_FRAME_DURATION:.2f}",
        "-i", str(hook_frame_png),
    ]
cmd += [
    "-filter_complex", filter_complex,
    "-map", "[outv]", "-map", audio_map,
    # ... encode flags
]
```

Total output duration becomes `HOOK_FRAME_DURATION + body_duration`. The
hook frame is ONE concat input regardless of how many caption switches
happen in the body. Filter graph stays small.

#### Option B: timeline-gated overlay (legacy)

Render the hook PNG with SEMI-OPAQUE background (alpha ~200/255) so a
sliver of the talking head shows through. Overlay it for the first
1.5s of the body via `enable='between(t,0,1.5)'`. Audio and captions
play through the overlay unchanged. Useful for tight 2-3 word hooks
where reading time isn't a concern.

```python
HOOK_FRAME_DURATION = 1.5  # short hold; audio runs underneath

# Stack hook on top of (captions on top of (talking head))
parts.append(
    f";{layered}[{hook_idx}:v]"
    f"overlay=0:0:enable='between(t,0,{HOOK_FRAME_DURATION:.2f})'[clip_hooked]"
)
```

## Verification

Visually:
- Card holds for 1.5-1.7s at the start, then disappears cleanly to
  reveal the talking head + captions underneath.
- The text is the rephrased host question for guest clips; the
  speaker's own hook for host clips.
- Numbers, proper nouns, and acronyms in the card text appear in yellow
  against white.

Programmatically:
- `ffprobe -show_entries format=duration` matches `clip_end - clip_start`
  (lead-out included) within 50ms.
- Filter graph node count stays at 3 overlay nodes total (blur-bg main,
  captions, hook), independent of caption cue count.
- Hook frame PNG is ~50-150 KB (mostly-transparent + bold text compresses well).

## Example

In a 20VC podcast clipper test on a Patrick Forquer (CRO of Legora)
interview:

| Clip topic | Hook frame text (from `preceding_question`) |
|---|---|
| AI startup pace | "Should you leave SAS for an AI startup?" |
| Selling against incumbents | "How do you win against a tough competitor?" |
| Salesforce vs AI agents | "Is Salesforce dead because of AI agents?" |
| Sales rep attainment | "What percent of reps should hit quota?" |
| Career choice advice | "Did you make the right career move?" |

For 2 of 11 clips where the speaker IS the host (Harry Stebbings),
`preceding_question` came back empty and the renderer fell back to
the clip's own `hook` field. Both fallbacks landed.

## Notes

- The hook card OBSCURES the talking head and any captions underneath
  for its duration. That's intentional - the whole frame is the
  headline, not a small banner. The viewer reads, the audio starts
  primed, the card fades and the speaker appears.
- The card backdrop is semi-opaque (alpha 200/255) rather than fully
  black so a sliver of the talking head shows through, which feels less
  jarring than a hard cut from black to face. Adjust HOOK_BG_ALPHA to
  taste.
- Animation (fade-in, fade-out, scale-bounce) is intentionally OMITTED.
  A static 1.6s hold with a hard appear/disappear is what most viral
  podcast clippers do. Animation can be added with the `fade` filter
  but adds complexity for marginal gain.
- For clips where `preceding_question` is empty AND `hook` starts with
  a hedge ("I think", "you know"), consider rephrasing the hook to a
  question in a post-process step before rendering. Out of scope for v1.

## Related skills

- `ffmpeg-many-timed-overlays-via-concat-demuxer` - the captions layer
  this stacks on top of.
- `tiktok-style-caption-keyword-highlighting` - the per-token colour
  heuristic shared between captions and hook frame.
- `pil-pixel-aware-word-wrap-large-fonts` - REQUIRED for the wrap step;
  textwrap.wrap silently overflows the canvas on long all-caps lines
  at this font size. The hook-frame renderer uses
  `_wrap_by_pixel_width` from that skill, NOT `textwrap.wrap`.

## References

- [ffmpeg overlay enable expressions](https://ffmpeg.org/ffmpeg-filters.html#overlay-1) -
  the `enable='between(t,X,Y)'` timeline gating syntax.
- [Pillow ImageDraw multiline_textbbox](https://pillow.readthedocs.io/en/stable/reference/ImageDraw.html) -
  text measurement for vertical centring.
