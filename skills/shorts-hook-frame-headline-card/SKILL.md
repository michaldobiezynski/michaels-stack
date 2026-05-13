---
name: shorts-hook-frame-headline-card
description: |
  Add a 2-3 second "headline card" intro at the start of every TikTok /
  Reels / YouTube Shorts clip to stop the FYP scroll. The card shows a
  big-text question or hook over a blurred frame from inside the clip,
  then cross-fades into the unblurred body. Use when:
  (1) building a podcast-clipping pipeline where Shorts open with a
  bare talking head and the first 0.5s of audio isn't enough to retain
  scrollers, (2) you want the same "question-then-answer" framing that
  Opus Clip, Munch, and most pro podcast clippers use, (3) the source
  is an interview where the HOST'S question is often a punchier hook
  than the GUEST'S opening sentence, (4) you're already overlaying
  burned-in captions via the concat-demuxer pattern and want to stack
  a hook card on top without re-architecting the filter graph.
  Covers: hook text selection with a fallback chain that prefers
  always-bounded fields over maybe-unbounded ones (preceding_question
  -> topic -> hook), PIL rendering at 100+pt with auto-shrink-to-fit
  in BOTH dimensions, blurred-frame compositing as background, ffmpeg
  xfade as the transition into the body, the topic-as-curiosity-gap
  rule that the LLM must obey, and Paddy-Galloway-style upload
  metadata fields (publishable_title / tiktok_caption / hashtags) that
  ride alongside the on-screen text in the same LLM pass.
author: Claude Code
version: 1.3.0
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

### Part 2: pick the hook text — order by fit, not by quality

Priority in the renderer:

```python
def pick_hook_text(clip: dict) -> str:
    """
    1. preceding_question  - LLM-rephrased headline, <=8 words by prompt
    2. topic               - <=6 words by prompt. Always short enough.
    3. hook                - speaker's opening sentence. LAST resort.
    """
    q = (clip.get("preceding_question") or "").strip()
    if q:
        return q
    t = (clip.get("topic") or "").strip()
    if t:
        return t
    h = (clip.get("hook") or "").strip()
    if h:
        for sep in [". ", "? ", "! "]:
            if sep in h:
                h = h.split(sep, 1)[0] + sep.strip()
                break
        return h
    return "WATCH THIS"
```

**Why topic comes BEFORE hook in the fallback chain.** The preceding
question is the punchiest option when present. When it's empty, the
intuition says "fall back to the clip's own hook because it's the
actual content". DON'T. The hook is the speaker's opening sentence and
can be 20+ words ("When you select a partner, whether you realize it
or not, you're choosing a whole lifestyle and not just the person").
At 110pt all-caps that wraps to 13+ lines and overflows the canvas
vertically. The `topic` field is constrained to <=6 words by the
analyse prompt and is therefore always short enough to render
cleanly. Order the fallback chain by guarantee-of-fit, not by what
"feels" higher quality - the renderer has an auto-shrink guard for
the hook-fallback case, but picking short text up front avoids the
guard entirely and produces a more readable card.

**Constraint on the `topic` field itself - curiosity gap, not summary.**
Because `topic` is the on-screen fallback, prompt the LLM to phrase it
as a CURIOSITY GAP, not a Wikipedia-section-heading. Strong topics
have contradiction, a named anchor, a specific number, or an open
question. WEAK topics summarise the conversation:

- BAD (summary): "True equality", "Resilience and pity", "Choosing a partner's Tuesday"
- GOOD (curiosity gap): "Why partners hate themselves", "10 years of therapy",
  "Hunter Biden's self-awareness", "Choose your shit sandwich"

A summary topic produces a hook frame that DESCRIBES rather than
TEASES; on the FYP that's a scroll. Add this constraint explicitly
to the prompt's `topic` field description.

### Part 1.5: upload-metadata fields (Paddy Galloway pattern)

The on-screen hook frame is one piece of "packaging"; the upload title
+ caption + hashtags is the other. Add three fields to the per-clip
JSON contract so the LLM produces them in the same pass as the clip
selection - cheaper than a second LLM call later, and the LLM has the
clip context fresh:

```
"publishable_title": string,
// Upload title for YouTube Shorts / TikTok / Reels. Different from
// `topic` (short on-screen overlay text) - this is the longer caption
// in the post's title field. Max 70 chars. Must create a curiosity gap
// the clip's payoff resolves. Strong patterns:
//   "Why X does Y" / "The truth about X" / "X people don't realise Y"
// Honest to the clip, not clickbait.

"tiktok_caption": string,
// Body copy under the title, above hashtags. One or two short sentences
// restating the hook as a teaser. Max 150 chars. No emojis. No leading
// hashtags (those go in `hashtags`).

"hashtags": [string],
// 3-5 lowercase tags WITHOUT the leading "#". Mix one broad
// (psychology, relationships, podcast) with two-three specific tags
// from the clip's content (manson, modernwisdom, dating). Each tag
// <=20 chars, no spaces, no special chars. The poster adds the # at
// post time.
```

These fields don't render onto the video - they ride in the
`shorts_manifest.json` so the poster can paste them into the upload UI
for each clip. The manifest writer (in the shorts pipeline) uses
`{**clip, "order": i, "file": out.name}` to spread the clip JSON into
the manifest entry, so new fields flow through with no code change.

### Part 3: render the PNG with auto-shrink + blurred background

Fullscreen RGBA, blurred-frame background, huge centred caps. The font
auto-shrinks if the wrapped block won't fit in either dimension.

```python
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

W, H = 1080, 1920
HOOK_FONT_SIZE = 110
HOOK_FONT_SIZE_MIN = 60
HOOK_STROKE_WIDTH = 9
HOOK_SIDE_MARGIN = 90       # horizontal breathing room
HOOK_VERT_MARGIN = 160      # vertical breathing room
HOOK_BG_BLUR_SIGMA = 30
HOOK_BG_BRIGHTNESS = 0.35   # darken so text reads cleanly


def _build_blurred_bg(bg_frame_png: Path) -> Image.Image:
    """Scale-cover the frame to W x H, blur, darken. Returns RGBA."""
    bg = Image.open(bg_frame_png).convert("RGBA")
    bg_w, bg_h = bg.size
    target = W / H
    src = bg_w / bg_h
    if src > target:
        new_w = int(bg_h * target)
        left = (bg_w - new_w) // 2
        bg = bg.crop((left, 0, left + new_w, bg_h))
    else:
        new_h = int(bg_w / target)
        top = (bg_h - new_h) // 2
        bg = bg.crop((0, top, bg_w, top + new_h))
    bg = bg.resize((W, H), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=HOOK_BG_BLUR_SIGMA))
    return ImageEnhance.Brightness(bg).enhance(HOOK_BG_BRIGHTNESS)


def render_hook_frame_png(text, out_path, font_path, bg_frame_png=None):
    text_caps = text.strip().upper()
    max_block_h = H - 2 * HOOK_VERT_MARGIN
    max_text_w = W - 2 * HOOK_SIDE_MARGIN

    # Auto-shrink until BOTH dimensions fit. This is the belt-and-braces
    # guard. Two failure modes it catches:
    # (a) Vertical: long fallback text wraps to 10+ lines and overflows
    #     the canvas top/bottom.
    # (b) Horizontal: a single long word (PROCRASTINATION, MANOSPHERE)
    #     is wider than max_text_w on its own. _wrap_by_pixel_width
    #     keeps a too-wide single word on its own line and lets it
    #     overhang; the only fix is shrinking the font.
    size = HOOK_FONT_SIZE
    while True:
        font = ImageFont.truetype(font_path, size)
        wrapped = _wrap_by_pixel_width(text_caps, font, max_text_w) or [text_caps]
        ascent, descent = font.getmetrics()
        line_height = int((ascent + descent) * 1.05)
        block_h = line_height * len(wrapped)
        widest = max((font.getlength(L) for L in wrapped), default=0)
        if (block_h <= max_block_h and widest <= max_text_w) or size <= HOOK_FONT_SIZE_MIN:
            break
        size -= 10

    if bg_frame_png and bg_frame_png.exists():
        img = _build_blurred_bg(bg_frame_png)
    else:
        img = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    draw = ImageDraw.Draw(img)
    stroke_w = max(4, int(HOOK_STROKE_WIDTH * size / HOOK_FONT_SIZE))
    block_top = (H - block_h) // 2

    for i, line in enumerate(wrapped):
        # Per-token rendering with keyword highlighting (yellow on
        # numbers / proper nouns / acronyms, white otherwise).
        # See `tiktok-style-caption-keyword-highlighting` for the
        # is_keyword heuristic and the centred-line draw helper.
        draw_centred_line_with_highlights(
            draw, line, font, W, block_top + i * line_height,
            stroke_width=stroke_w,
        )
    img.save(out_path)


def extract_representative_frame(src: Path, t: float, out_png: Path) -> bool:
    """One PNG frame at `t` seconds. Used as the blurred bg of the hook
    intro. Pick from inside the clip (e.g. clip_start + duration*0.30),
    not the very first frame, so the bg has the same visual mood as
    the body and avoids the speaker mid-blink."""
    cmd = ["ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", str(src),
           "-frames:v", "1", "-q:v", "2", str(out_png)]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return out_png.exists() and out_png.stat().st_size > 0
```

### Part 4: xfade transition from intro into body

The intro is a single PNG (composited from blurred bg + text) looped
to `HOOK_FRAME_DURATION` seconds, cross-faded into the body via
ffmpeg's `xfade` filter. The transition feels much more polished than
a hard cut (which the old concat-only approach produced).

```python
HOOK_FRAME_DURATION = 2.5    # total intro duration
HOOK_XFADE_DURATION = 0.5    # length of the cross-fade

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

if has_hook_frame:
    hook_idx = 2 if has_captions else 1
    parts.append(
        f";[{hook_idx}:v]scale={W}:{H},format=yuv420p,fps=30,"
        "setpts=PTS-STARTPTS[hook_v]"
    )
    # xfade=offset is when the fade STARTS in the intro stream. With
    # intro length = 2.5s and fade = 0.5s, offset = 2.0 means:
    #   t=0..2.0   pure hook
    #   t=2.0..2.5 hook fading out, body fading in
    #   t=2.5..    pure body
    # Total output duration = offset + body_duration = 2.0 + body_dur.
    xfade_offset = HOOK_FRAME_DURATION - HOOK_XFADE_DURATION
    parts.append(
        f";[hook_v][body_norm]xfade=transition=fade:"
        f"duration={HOOK_XFADE_DURATION:.2f}:offset={xfade_offset:.2f}[outv]"
    )
    # Body audio comes in at the START of the fade (offset), so the
    # speaker's first word lands as the body becomes fully visible.
    delay_ms = int(xfade_offset * 1000)
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

The complete intro flow:

1. Pre-extract one source frame via `ffmpeg -ss bg_ts -frames:v 1`
   from inside the clip (e.g. clip_start + duration*0.30).
2. `render_hook_frame_png(text, ..., bg_frame_png=bg_path)` produces
   the composited intro PNG (blurred bg + text on top).
3. Feed that PNG as `-loop 1 -framerate 30 -t HOOK_FRAME_DURATION`.
4. xfade in the filter graph blends intro -> body over the last
   HOOK_XFADE_DURATION seconds of the intro.
5. Body audio is `adelay`'d by `HOOK_FRAME_DURATION - HOOK_XFADE_DURATION`
   so the first word lands when the body is fully visible.

## Verification

Visually:
- Intro holds with text on the blurred bg for ~2s, then cross-fades
  over 0.5s into the unblurred body.
- Background is the studio/scene of the clip, heavily blurred and
  darkened so the foreground text is the clear focal point.
- Text is the rephrased host question for guest clips; the topic for
  host-only clips; the speaker's hook only as a last resort.
- Numbers, proper nouns, and acronyms in the text appear yellow.
- No headline ever clips the canvas edges - the auto-shrink loop
  guarantees this for any input.

Programmatically:
- Grab a frame at `t = HOOK_FRAME_DURATION - HOOK_XFADE_DURATION/2`
  (the middle of the fade). You should see BOTH layers - text partly
  transparent, body partly transparent. If you see only text or only
  body, xfade is misconfigured.
- For every wrapped headline line, assert `font.getlength(line) <=
  max_text_w`. The auto-shrink loop guarantees this.
- Total output duration is `xfade_offset + body_duration`, not
  `HOOK_FRAME_DURATION + body_duration` (xfade overlaps the streams).

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

- The hook intro is a STANDALONE segment, not an overlay. The body
  isn't visible (just its blurred essence) during the solid hold. This
  matters because captions are baked into the body before concat -
  so they don't compete with the headline during the intro, then come
  alive cleanly when the body fades in.
- Background blur sigma (30) and brightness (0.35) are tuned for
  legibility against bright-yellow keyword highlights on white text.
  Adjust both together: a lighter bg needs lower brightness or you'll
  lose contrast.
- Why xfade and not concat: concat hard-cuts from intro to body, which
  looks abrupt. xfade dissolves over HOOK_XFADE_DURATION seconds.
  Cost: 0.5s of effective intro is "lost" to the fade overlap, so the
  pure-hook hold is 2.0s instead of 2.5s. Worth it.
- The bg frame is sampled at clip_start + duration*0.30 by default.
  At t=0 the speaker is often mid-blink or carrying a transitional
  expression from the host's question; 30% in is more representative.
- A "very long single word" (PROCRASTINATION, MANOSPHERE,
  ENTREPRENEURSHIP) cannot be broken across lines and will trigger
  the horizontal auto-shrink. If the word still doesn't fit at the
  60pt floor, consider rephrasing it in the LLM prompt (e.g.
  "manosphere wrong solution" -> "what's wrong with the manosphere").

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
