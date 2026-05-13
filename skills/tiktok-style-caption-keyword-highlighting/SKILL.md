---
name: tiktok-style-caption-keyword-highlighting
description: |
  Render burned-in Shorts/TikTok captions where 1-2 key tokens per cue
  render in a contrasting accent colour (yellow/red/green) while the rest
  stays white. Use when: (1) baseline white-on-black captions feel flat
  compared to Opus Clip / Munch / pro podcast clippers, (2) the source is
  a podcast or interview where the high-signal tokens are NUMBERS, NAMES,
  COMPANIES, and DOLLAR/PERCENT amounts rather than verbs or adjectives,
  (3) you're rendering captions via PIL onto a fullscreen RGBA canvas
  (already needed if you're avoiding libass), (4) you want a simple
  heuristic that flags the right tokens without an LLM pass per cue.
  Covers: the is_keyword() heuristic (numbers, dollar/percent amounts,
  proper nouns, ALL-CAPS acronyms; minus a stopword list), and the
  token-by-token PIL renderer that measures cumulative width and centres
  each line horizontally.
author: Claude Code
version: 1.0.0
date: 2026-05-13
---

# TikTok-style caption keyword highlighting (yellow on white)

## Problem

Baseline burned-in captions are all-white with a black stroke. They're
readable but visually flat. Pro podcast clippers (Opus Clip, Munch,
Submagic) put one or two "key words" per cue in a contrasting accent
colour (most commonly yellow, sometimes red or green). This is the
single biggest visual differentiator between hobby-tier and pro-tier
Shorts.

Doing this naively requires an LLM call per cue to mark which words to
highlight - expensive and slow for 100+ cues per clip. A simple
character-level heuristic works for the kinds of tokens that matter on
podcasts (numbers, names, companies, acronyms, dollar amounts) without
any LLM involvement.

## Context / Trigger conditions

- You're already rendering captions to fullscreen RGBA PNGs (e.g. via
  the related skill `ffmpeg-many-timed-overlays-via-concat-demuxer`),
  not using libass `subtitles=`.
- Source content is conversational English: podcasts, interviews,
  conference talks. The keyword distribution is heavy on proper nouns
  and quantities.
- You want the renderer to make the call, not the LLM.

## Solution

Two pieces: an `is_keyword()` heuristic and a `_draw_centred_line()` helper
that renders tokens left-to-right with per-token colour.

### The heuristic

```python
import re

_STOPWORDS_LOWER = {
    "a", "an", "the", "and", "or", "but", "if", "of", "in", "on", "to", "for",
    "with", "by", "at", "from", "as", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would", "can",
    "could", "should", "may", "might", "must", "i", "you", "he", "she", "it",
    "we", "they", "me", "him", "her", "us", "them", "my", "your", "his", "its",
    "our", "their", "this", "that", "these", "those", "what", "which", "who",
    "whom", "when", "where", "why", "how", "not", "no", "yes", "so", "than",
    "then", "now", "just", "too", "very", "also", "well", "like",
}


def is_keyword(token: str) -> bool:
    """Highlight tokens that carry meaning, skip stopwords and lowercase
    verbs. Strips punctuation so 'Salesforce.' and 'Salesforce' both hit.

    Hits:
    - Numbers ($50M, 78%, 2026, 1.5x)
    - ALL-CAPS acronyms (AI, CRO, SaaS, IPO, RAG, LLM)
    - Proper nouns (Salesforce, Patrick, Legora, Microsoft, Anthropic)

    Misses (correctly):
    - Stopwords starting a sentence (The, I, You, We) - capitalised but
      common, would be too noisy if highlighted.
    - Lowercase verbs and adjectives (interesting, working, growing) -
      these don't pop visually even when they carry meaning.
    """
    core = re.sub(r"[^\w%$]", "", token)
    if not core:
        return False
    if re.search(r"[\d$%]", core):
        return True
    if len(core) >= 2 and core.isupper():
        return True
    if len(core) >= 4 and core[0].isupper() and not core.isupper():
        return core.lower() not in _STOPWORDS_LOWER
    return False
```

Verification on a typical podcast vocabulary:

| Token | is_keyword | Reason |
|---|---|---|
| `Salesforce` | True | Capitalised, 10 chars, not stopword |
| `AI` | True | All-caps acronym |
| `CRO` | True | All-caps acronym |
| `$50M` | True | Contains digit and $ |
| `78%` | True | Contains digit and % |
| `Patrick` | True | Capitalised proper noun |
| `dead` | False | Lowercase verb |
| `the` | False | Stopword |
| `The` | False | Stopword (even capitalised) |
| `I` | False | Stopword (too short anyway) |
| `enterprise` | False | Lowercase |

### The token-by-token renderer

PIL's `multiline_text` only takes one `fill` colour for the whole text.
For per-token colour you have to measure cumulative width and draw each
token separately:

```python
from PIL import ImageDraw, ImageFont

def _draw_centred_line(
    draw: ImageDraw.ImageDraw,
    line: str,
    font: ImageFont.FreeTypeFont,
    canvas_w: int,
    y: int,
    stroke_width: int,
    stroke_fill: tuple[int, int, int, int],
    default_fill: tuple[int, int, int, int],
    highlight_fill: tuple[int, int, int, int],
) -> None:
    """Render one line, tokens left-to-right, centred horizontally,
    with `is_keyword` tokens in `highlight_fill`."""
    tokens = line.split(" ")
    if not tokens:
        return
    space_width = font.getlength(" ")
    token_widths = [font.getlength(t) for t in tokens]
    total = sum(token_widths) + space_width * max(0, len(tokens) - 1)
    x = (canvas_w - int(total)) // 2
    for tok, w in zip(tokens, token_widths):
        fill = highlight_fill if is_keyword(tok) else default_fill
        draw.text(
            (x, y), tok, font=font,
            fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill,
        )
        x += int(w) + int(space_width)
```

Wrap the whole text first with `textwrap.wrap`, then call
`_draw_centred_line` per line:

```python
import textwrap
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
CAPTION_FONT_SIZE = 64
CAPTION_STROKE_WIDTH = 6
CAPTION_MAX_LINE_CHARS = 22
CAPTION_BOTTOM_MARGIN = 360
WHITE = (255, 255, 255, 255)
YELLOW = (255, 220, 0, 255)
BLACK = (0, 0, 0, 255)


def render_caption_png(text: str, out_path, font_path):
    lines = textwrap.wrap(text, width=CAPTION_MAX_LINE_CHARS) or [text]
    font = ImageFont.truetype(font_path, CAPTION_FONT_SIZE)

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    ascent, descent = font.getmetrics()
    line_height = ascent + descent
    block_top = H - line_height * len(lines) - CAPTION_BOTTOM_MARGIN

    for i, line in enumerate(lines):
        _draw_centred_line(
            draw, line, font, W, block_top + i * line_height,
            stroke_width=CAPTION_STROKE_WIDTH,
            stroke_fill=BLACK,
            default_fill=WHITE,
            highlight_fill=YELLOW,
        )
    img.save(out_path)
```

## Verification

Visually:
- Numbers, $/% amounts, names, and acronyms pop in yellow.
- "The/I/You/We/My/Your" remain white even when they start a sentence.
- Stroke renders cleanly on both colours (yellow stays readable on busy
  backgrounds because of the 6px black halo).

Programmatically:
- `is_keyword('Salesforce')`, `is_keyword('AI')`, `is_keyword('$50M')`,
  `is_keyword('78%')` → True
- `is_keyword('the')`, `is_keyword('The')`, `is_keyword('and')`,
  `is_keyword('dead')`, `is_keyword('enterprise')` → False

## Notes

- The heuristic is deliberately conservative. False positives (random
  lowercase verbs getting highlighted) are worse than false negatives
  (a noun missed) because flickering yellow distracts more than absent
  emphasis. Tune toward fewer hits, not more.
- For domains other than podcasts (e.g. cookery, gaming, fashion), the
  set of "meaningful" tokens is different. You'd add domain-specific
  keyword regexes (cooking measurements, game stats, brand names) on
  top of this baseline rather than replacing it.
- This pairs naturally with the concat-demuxer caption track pattern:
  the per-token coloured rendering still produces ONE PNG per cue,
  still flows through one overlay node. Filter graph complexity
  doesn't change.
- An alternative is to have the LLM mark `highlighted_words: [...]`
  per cue at analyse time. More accurate but adds latency and token
  cost per clip. Heuristic wins for podcast content where the
  high-value tokens are mechanically identifiable.

## Related skills

- `ffmpeg-many-timed-overlays-via-concat-demuxer` - the underlying
  caption pipeline this colours.
- `shorts-hook-frame-headline-card` - reuses the same heuristic and
  `_draw_centred_line` helper for the headline card text.
- `youtube-auto-vtt-inline-word-timestamps` - source of the word-level
  caption cues this colours.

## References

- [Pillow ImageFont.getlength](https://pillow.readthedocs.io/en/stable/reference/ImageFont.html#PIL.ImageFont.FreeTypeFont.getlength) -
  per-token width measurement for centring.
- [Opus Clip caption style](https://www.opus.pro/) - the visual reference
  this skill emulates (yellow/red accent words on white).
