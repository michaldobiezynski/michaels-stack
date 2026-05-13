---
name: youtube-auto-vtt-inline-word-timestamps
description: |
  Extract true per-word timing from YouTube auto-generated WebVTT captions
  (downloaded via yt-dlp `--write-auto-sub`) rather than dividing each
  phrase cue's duration proportionally across its words. Use when:
  (1) building TikTok/Shorts-style word-by-word burned captions that
  must sync with the audio, (2) your existing VTT parser strips inline
  `<HH:MM:SS.mmm>` markers as HTML/XML tags and you've fallen back to
  proportional time division per phrase (which sounds OK on a tape
  recorder reading evenly but desyncs badly on natural speech where some
  words take 50ms and others take 800ms), (3) captions appear noticeably
  out of sync (typically lagging or anticipating spoken words by 200-700ms)
  despite the phrase-level cue times being correct. The fix preserves
  YouTube's per-word timestamps which are accurate ASR output.
author: Claude Code
version: 1.0.0
date: 2026-05-12
---

# YouTube auto-VTT inline word-level timestamps

## Problem

You're burning word-level captions into a video clip using YouTube
auto-generated VTT (downloaded with `yt-dlp --write-auto-sub --sub-format vtt`).
Captions are visibly out of sync with the spoken audio - a word's caption
appears 300-700ms before or after the word is heard.

You assumed each VTT phrase cue's duration could be split evenly across
its words, but real speech has dramatically uneven word durations (1-syllable
"the" is 50ms, multi-syllable "responsibility" is 600ms). Proportional
division turns natural speech into uniformly-paced output that desyncs after
3-4 words.

## Context / Trigger conditions

- Source captions come from `yt-dlp --write-auto-sub` (NOT human-uploaded captions)
- Cue body in the VTT contains markers like `<00:00:05.440>` inside the text
- Your parser uses `re.sub(r"<[^>]+>", "", s)` or similar to strip "HTML tags",
  which silently discards the per-word timing
- Output captions are word-level (you've already split phrases into words) but
  visually desynced from audio
- The phrase-level cue times match audio correctly, only word-level division
  is wrong

## Root cause

YouTube auto-VTT cues come in TWO formats:

1. **Plain phrase-level** (human-uploaded captions or post-processed):

```
00:00:10.000 --> 00:00:14.500
The subtle art of not giving a damn
```

2. **Inline word-timestamped** (raw ASR output from `--write-auto-sub`):

```
00:00:05.120 --> 00:00:09.350 align:start position:0%

The<00:00:05.440><c> subtle</c><00:00:05.839><c> art</c><00:00:06.400><c> of</c><00:00:06.720><c> not</c><00:00:07.120><c> giving</c><00:00:07.440><c> a</c><00:00:07.680><c> [&nbsp;__&nbsp;]</c>
```

Each inline `<HH:MM:SS.mmm>` is the start time of the FOLLOWING word. The
first word in a cue uses the cue's own start time. The last word ends at
the cue's end time.

A typical regex like `re.sub(r"<[^>]+>", "", text)` strips BOTH the `<c>`
tags (intended) AND the `<HH:MM:SS.mmm>` markers (unintended). The parser
then sees "The subtle art of not giving a [__]" with no word-level timing,
falls back to even-division, and produces output desynced from speech.

## Solution

Detect inline timestamps, preserve them, and emit per-word cues whose
start/end come from the timestamps rather than from proportional division.

```python
import re
from pathlib import Path


def vtt_time_to_seconds(t: str) -> float:
    parts = t.strip().split(":")
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h, m, s = "0", parts[0], parts[1]
    else:
        return 0.0
    return int(h) * 3600 + int(m) * 60 + float(s.replace(",", "."))


def parse_vtt_word_cues(vtt_path: Path) -> list[dict]:
    """Return per-word cues from a VTT with inline <HH:MM:SS> timestamps.
    Empty list if the file lacks inline timestamps (caller should fall back)."""
    text = vtt_path.read_text(encoding="utf-8", errors="ignore")
    if not re.search(r"<\d+:\d+:[\d.]+>", text):
        return []

    cues = []
    for block in text.split("\n\n"):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if len(lines) < 2:
            continue
        time_line = next((ln for ln in lines if "-->" in ln), None)
        if not time_line:
            continue
        try:
            cue_start, cue_end = [
                vtt_time_to_seconds(t.split()[0])
                for t in time_line.split("-->")[:2]
            ]
        except (ValueError, IndexError):
            continue
        # Skip the 10ms placeholder cues YouTube emits between real ones.
        if cue_end - cue_start < 0.05:
            continue

        body_lines = [
            ln for ln in lines
            if "-->" not in ln
            and not ln.startswith(("WEBVTT", "Kind:", "Language:"))
        ]
        raw = "\n".join(body_lines)
        # Skip cues that lack inline timestamps - they're carryover duplicates.
        if not re.search(r"<\d+:\d+:[\d.]+>", raw):
            continue

        # Strip <c> tags but KEEP <HH:MM:SS> timestamps; decode entities.
        cleaned = re.sub(r"</?c[^>]*>", "", raw)
        cleaned = cleaned.replace("&nbsp;", " ").replace("&amp;", "&")
        cleaned = re.sub(r"[ \t]+", " ", cleaned)

        # The "first new word" is the LAST whitespace token before the
        # first inline timestamp. Everything before that is carryover text
        # from earlier cues (YouTube auto-VTT repeats context).
        first_ts = re.search(r"<\d+:\d+:[\d.]+>", cleaned)
        prelude = cleaned[: first_ts.start()].replace("\n", " ").strip()
        first_word = prelude.split()[-1] if prelude.split() else ""

        # Split on inline timestamps to get a list of (word, ts) pairs.
        parts = re.split(r"<(\d+:\d+:[\d.]+)>", cleaned)
        current_start = cue_start
        current_text = first_word

        for i in range(1, len(parts), 2):
            ts = vtt_time_to_seconds(parts[i])
            if current_text.strip():
                cues.append({
                    "start": current_start,
                    "end": ts,
                    "text": current_text.strip(),
                })
            current_start = ts
            current_text = parts[i + 1] if i + 1 < len(parts) else ""

        if current_text.strip():
            cues.append({
                "start": current_start,
                "end": cue_end,
                "text": current_text.strip(),
            })

    # Drop redaction placeholders (YouTube replaces profanity with "[ __ ]")
    # and deduplicate consecutive same-word entries that arise at cue boundaries.
    out = []
    for w in cues:
        t = w["text"]
        if not t or "[" in t or "]" in t or "__" in t:
            continue
        if out and out[-1]["text"] == t and abs(out[-1]["start"] - w["start"]) < 0.05:
            continue
        out.append(w)
    return out
```

Key points about the format:

- **Cue header**: `00:00:05.120 --> 00:00:09.350 align:start position:0%`.
  The `align:start position:0%` modifiers are cosmetic; ignore them.
- **Body line**: First word, then `<HH:MM:SS.mmm><c> word</c>` per subsequent word.
- **Carryover cues**: Each "real" cue is followed by a 10ms placeholder cue
  with the same text but NO inline timestamps. Skip these by checking
  `cue_end - cue_start < 0.05`.
- **Continuation cues**: When a new cue extends an old one, the new cue
  body starts with the OLD text (multi-line), then new words with new
  timestamps. The "first new word" is the last whitespace-token before
  the first inline `<HH:MM:SS>` marker.
- **Profanity redaction**: YouTube replaces flagged words with `[ __ ]`.
  Drop these.

## Verification

```python
words = parse_vtt_word_cues(Path("video.en.vtt"))
durations = [w["end"] - w["start"] for w in words]
print(f"words: {len(words)}")
print(f"dur range: {min(durations):.3f}s - {max(durations):.3f}s")
print(f"first 10: {words[:10]}")
```

Healthy output:
- Word count matches roughly transcript-word-count
- Duration range varies meaningfully (e.g. 50ms-800ms)
- Adjacent word `end[i]` and `start[i+1]` typically differ (real silences
  between words appear as small gaps)

Unhealthy output (proportional-division fallback hit):
- All durations within 10-20% of each other
- Words exactly fill phrase cues with no inter-word gaps
- Word count = phrase count × average-words-per-phrase

## Example

In a Shorts caption pipeline:

```python
def cues_in_window(vtt_path, clip_start, clip_end):
    words = parse_vtt_word_cues(vtt_path)
    if words:
        # Use true word-level timing
        ...
    else:
        # Fall back to phrase-level + proportional split (degraded sync but
        # acceptable for human-uploaded VTTs that lack inline timing)
        ...
```

Sample output difference for a 1-minute clip:

| Approach | First 5 chunks |
|---|---|
| Proportional split | `"the" 0.0-0.4s, "feedback" 0.4-0.8s, "loop" 0.8-1.2s, "from" 1.2-1.6s, "hell" 1.6-2.0s` (uniform, desynced) |
| Inline timestamps | `"the" 0.0-0.05s, "feedback" 0.05-0.62s, "loop" 0.62-0.84s, "from" 0.84-0.91s, "hell" 0.91-1.40s` (matches audio) |

The captions visibly sync with the lip movements once inline timestamps
are used.

## Notes

- **Format detection**: Test for `<\d+:\d+:[\d.]+>` in the file. If present,
  use the word-level parser; if absent, fall back to phrase-level.
- **Performance**: Parsing a 60-minute video's VTT takes ~50ms - negligible.
- **yt-dlp flags**: To get inline timestamps you MUST use `--write-auto-sub`
  (NOT `--write-sub`, which fetches human-uploaded captions that typically
  lack inline timing). Format: `--sub-format vtt`. Language: `--sub-lang en.*`.
- **Cross-check**: The very last word in a cue ends at the cue's end time.
  If you see suspicious "last word stretches forever" output, you're
  probably reading the cue end time wrong.
- This applies to YouTube's ASR output specifically. Whisper-generated VTTs
  use a different convention (per-segment phrase cues, no inline word
  timestamps - you'd need word-level Whisper output via `whisperx` or
  `--word_timestamps` to get the same fidelity).

## References

- [WebVTT spec](https://www.w3.org/TR/webvtt1/#webvtt-cue-timings-and-settings) -
  the official cue header and body format
- [yt-dlp subtitles options](https://github.com/yt-dlp/yt-dlp#subtitle-options) -
  `--write-auto-sub` vs `--write-sub` semantics
