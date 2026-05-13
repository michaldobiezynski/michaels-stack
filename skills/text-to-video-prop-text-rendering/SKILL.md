---
name: text-to-video-prop-text-rendering
description: |
  Fix for garbled or illegible text on in-scene props (T-shirts, caps, mugs,
  signs, screens, billboards, merch) in generative video tools. Use when:
  (1) a Seedance 2.0 / Sora / Veo / Kling / Runway prompt specifies custom
  text on a prop and the render comes back mangled, (2) planning a shot
  where a quote, slogan, or branding must be legible on a wearable or object,
  (3) building merch-reveal, sign-reading, or screen-playback beats for
  short-form video. Covers three reliability tiers: text-to-video shortening
  (best-effort), image-to-video with pre-rendered still (high-reliability),
  and blank-prop render + post-production tracked overlay (100% reliable).
author: Claude Code
version: 1.0.0
date: 2026-04-17
---

# Text-to-Video Prop Text Rendering

## Problem

Most text-to-video models (Seedance 2.0, Sora 2, Veo 3, Kling 2.1, Runway Gen-4, Luma Ray 2) struggle to render legible custom text on in-scene props: T-shirts, caps, mugs, billboards, phone screens, whiteboards, street signs. Long phrases come back as garbled lookalike lettering almost every time. Short phrases render correctly only 60-70% of the time.

**Exception: Grok Imagine (xAI)** reliably renders long phrases (7+ words) legibly and spelled correctly on props, verified 2026-04. If the creative requires a long on-prop string and the tool choice is flexible, Grok is the first tool to try. Tradeoff: Grok Imagine defaults to 1:1 square output (560×560), not 9:16 vertical, so it needs cropping or padding for Shorts/Reels feed.

This matters because a common social-video pattern has a punchline that depends on a merch item, sign, or screen displaying a specific quote. Writing the prompt naively ("T-shirt printed with the quote 'X'") produces gibberish in most tools and destroys the payoff.

## Context / Trigger Conditions

Apply this skill when a prompt needs any of these:

- Merch-reveal beats (T-shirts, caps, mugs, totes displaying a slogan)
- Sign-reading beats (shop signs, billboards, handwritten placards)
- Screen playback beats (phone showing a text message, laptop showing a tweet)
- Graffiti, posters, book covers, album art in-scene
- Any prop where text legibility is essential to the joke or emotional beat

Symptoms of the problem:

- Lettering renders as squiggles, mirrored letters, or nonsense words
- Text is inconsistent frame-to-frame (morphs during camera move)
- Letters visible but the actual string is wrong (e.g. "WOKE UP A LOVER" instead of "WOKE UP A LOSER")
- Different merch items in the same scene render different strings

## Solution

Four reliability tiers. Pick the lowest tier that meets your quality bar.

### Tier 0: Try Grok Imagine first if the tool is negotiable

If the creative brief allows any tool, and the text matters, start in Grok Imagine. As of 2026-04 it renders long quoted phrases (verified with 7-word strings) legibly and stably across frames, with correct spelling. Bold italic sans-serif is its default typeface and it looks good on fabric.

Caveats:

- Square output only (1:1, 560×560). For 9:16 feeds, crop or pad in post.
- Realistic / photographic aesthetic is its strength; stylised animation (Pixar, anime) is weaker.
- Fewer content restrictions than OpenAI / Google models but still blocks real public figures.

If Grok doesn't fit the aesthetic or aspect requirement, drop to Tier 1.

### Tier 1: Text-to-video shortening in other tools (~60-70% hit rate)

Use when text legibility is nice-to-have, not punchline-critical.

**Shorten the string:**

- Target: ≤3-4 words, ≤15 characters total
- All caps. Bold sans-serif. High contrast (black on cream, white on navy)
- Avoid: lowercase, script fonts, thin weights, long phrases, punctuation-heavy strings
- If the brief needs a longer line, split it: the short punchy version goes on the prop, the full line goes on a post-production end-card

**Describe the lettering explicitly in the prompt.** Don't just say "a T-shirt with the quote"; the model allocates more pixels to typography when you spell it out:

> "...a cream cotton T-shirt with the words **NOT A LOSER** printed across the chest in large bold black all-caps sans-serif lettering, clearly legible."

Include: exact text (quoted or bolded), placement, size, weight, case, typeface class, colour contrast, and the word "legible".

**Regenerate 2-3 times with seed variation.** Seed variation fixes 30-40% of mangled renders for free.

### Tier 2: Image-to-video with pre-rendered still (high-reliability)

Use when the text matters but you want speed over perfection.

1. Generate a clean still of the scene in an image tool that renders text well:
   - **Ideogram** (purpose-built for typography, most reliable)
   - Midjourney v7
   - ChatGPT image mode
   - Photoshop with stock assets
2. Feed that still to the video model's image-to-video endpoint as the conditioning image.
3. The text is baked into the source pixels, so it survives the animation as long as motion doesn't heavily distort the surface.

Seedance 2.0, Runway Gen-4, and Kling 2.1 all support image-to-video. Use this path whenever the tool allows it.

### Tier 3: Blank-prop render + tracked overlay in post (100% reliable)

Use when the text IS the punchline (merch reveals, sign gags, callback payoffs).

1. Prompt the video model for a **plain unmarked** prop ("plain cream T-shirt, no print", "blank ceramic mug").
2. In post, track the prop surface with a planar tracker:
   - After Effects: **Mocha AE** (built-in, handles fabric curvature)
   - DaVinci Resolve: **Fusion** planar tracker
   - Nuke: **PlanarTracker** node
3. Apply the text as a clean PNG or title layer bonded to the tracker.
4. The text deforms naturally with the fabric. Takes 5-10 minutes per clip.

This is the professional VFX approach. Every commercial with perfect logo placement does this. Guaranteed legible text every frame.

## Verification

Good render (Tier 1 or 2):

- Text readable at thumbnail size (check on phone, 9:16 at 20% zoom)
- String matches exactly, including spelling
- Lettering stays stable across the camera move (no morphing)
- If multiple merch items in the scene, all render the same string

Bad render (regenerate or drop to next tier):

- Letters visible but spell something different
- Text wobbles, warps, or re-spells itself during motion
- Inconsistent between frames or between props in the same shot

## Example

**Failing prompt (text-to-video, long string):**

> "Close-up of a T-shirt printed with the quote 'You're not talking to somebody who woke up a loser.'"

Result: garbled gibberish across the chest, completely illegible. Seedance will not produce legible 10-word phrases.

**Tier 1 fix (shortened + explicit):**

> "Close-up of a cream cotton T-shirt with the words **NOT A LOSER** printed across the chest in large bold black all-caps sans-serif lettering, clearly legible. Golden-hour side light, shallow depth of field, Pixar 3D style."

Regenerate 2-3 times, pick the cleanest.

**Tier 2 fix (image-to-video):**

1. In Ideogram, generate "Pixar-style 3D render, cream cotton T-shirt with NOT A LOSER printed in bold black sans-serif, golden-hour lighting".
2. Feed the chosen still to Seedance 2.0 image-to-video with the animation prompt (camera move, character action).

**Tier 3 fix (blank + post):**

1. Seedance prompt: "plain cream cotton T-shirt, no print, clean fabric".
2. In After Effects, Mocha-track the chest surface.
3. Overlay a `NOT A LOSER` PNG bonded to the tracker.
4. Render. Text is perfect, every frame.

**Combining tiers for a multi-shot edit:** use Tier 3 for the hero merch close-up, Tier 1 or 2 for background / B-roll shots where the merch is incidental. Saves time without sacrificing the punchline.

## Notes

- **Aspect ratio, duration, resolution, and fps go in tool UI settings, not in the prompt text.** Writing `9:16 vertical` or `15 seconds` in the prompt is mostly ignored by Dreamina / Seedance / Sora / Runway / Kling. Verified 2026-04-17: a Dreamina prompt explicitly starting with "9:16 vertical" rendered as 1280×720 landscape because the UI aspect setting was left at 16:9. Always check the tool's aspect-ratio dropdown before hitting generate.
- As of 2026, text rendering in generative video remains an open research problem. Improvements ship fast; re-test with the latest model version every few months.
- Image-to-video is always more reliable than text-to-video for typography because the text is already pixels, not a prompt instruction.
- Known-brand logos (Nike, Coca-Cola, Apple) are often blocked by IP filters. Use generic stylised typography for merch, or design your own serial logo.
- For recurring series, lock the short-form slogan and typography into a visual bible so it stays consistent across episodes.
- For moving props (windblown flags, crumpled paper), Mocha tracking still works but may need multiple surfaces tracked separately. Static or gently moving props are fastest.
- End-card overlays are free accessibility captions: add the full quote as a title card at the end of the clip for viewers with sound off.

## References

- Seedance 2.0 prompting and image-to-video documentation: https://seed.bytedance.com/en/seedance
- Ideogram (typography-specialised image generator): https://ideogram.ai
- Mocha AE planar tracking guide: https://borisfx.com/products/mocha-pro/
- Text rendering in diffusion video models remains an open problem in the research literature as of 2026.
