---
name: remotion-captions
description: >
  Transcribe video with Whisper and generate animated captions for Remotion.
  Full pipeline: video → Whisper transcription → caption JSON → Remotion component.
trigger: >
  Use when the user asks to add captions, subtitles, or transcription to a
  video for Remotion. Also triggers on: "caption this video", "add subtitles",
  "transcribe and caption", "generate captions".
user_invocable: true
---

# Remotion Captions Skill

Generate word-level captions from video using OpenAI Whisper and render them
as animated overlays in a Remotion composition.

## Prerequisites

- `openai-whisper` installed: `/opt/homebrew/bin/whisper`
- Remotion project at: `/Users/michaldobiezynski/development/projects/my-video`
- `@remotion/captions` package (already installed in project)

## Pipeline Steps

### Step 1: Identify the Video

Ask the user which video file to caption. Accept an absolute path or look in
the current working directory for `.mov`, `.mp4`, `.webm` files.

### Step 2: Transcribe with Whisper

Run Whisper with word-level timestamps:

```bash
whisper "<video_path>" \
  --model medium \
  --language en \
  --output_format json \
  --word_timestamps True \
  --output_dir "/tmp/whisper-captions"
```

**Notes:**
- Use `medium` model for good accuracy/speed balance. Use `turbo` if the user wants faster results.
- The `--word_timestamps True` flag is essential for per-word timing.
- Whisper outputs `<filename>.json` in the output directory.

### Step 3: Convert Whisper JSON to Remotion Caption Format

Whisper JSON structure:
```json
{
  "text": "full transcript",
  "segments": [
    {
      "start": 0.0, "end": 5.0,
      "text": " sentence text",
      "words": [
        { "word": " Hello", "start": 0.0, "end": 0.5, "probability": 0.9 }
      ]
    }
  ]
}
```

Convert to the project's `CaptionSentence[]` format:
```json
[
  {
    "startMs": 0,
    "endMs": 5000,
    "text": "sentence text",
    "words": [
      { "text": "Hello", "startMs": 0, "endMs": 500, "confidence": 0.9 }
    ]
  }
]
```

**Conversion rules:**
- Multiply `start`/`end` by 1000 to get milliseconds
- Map `word` → `text` (trim leading spaces)
- Map `probability` → `confidence`
- Map segment `text` → sentence `text` (trim)
- Use segment boundaries for sentence `startMs`/`endMs`

Write a Node.js script or inline Python script to do this conversion.
Save the output JSON to the Remotion project's `public/` directory with
a descriptive name like `<project-name>-captions.json`.

### Step 4: Create the Caption Component

The project has existing caption types at `src/ChessPromo/types.ts`:
```typescript
export type CaptionWord = { text: string; startMs: number; endMs: number; confidence: number; };
export type CaptionSentence = { startMs: number; endMs: number; text: string; words: CaptionWord[]; };
```

Reuse these types. Create the caption component based on the user's chosen style.

#### Style: Animated Pop-In (default for this project)

Key characteristics:
- Shows phrase groups of 4-6 words at a time (configurable via `WORDS_PER_GROUP`)
- Each group pops in with a spring scale animation (scale 0 → 1 with overshoot)
- Active word within the group is highlighted with a colour change
- Previous group fades out as new group appears
- Dark semi-transparent backdrop with blur
- Positioned at bottom of screen

Component template (`src/<ProjectName>/PopInCaptions.tsx`):

```tsx
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import type { CaptionSentence, CaptionWord } from "../ChessPromo/types";

const WORDS_PER_GROUP = 5;
const HIGHLIGHT_COLOUR = "#FFD700";
const TEXT_COLOUR = "#FFFFFF";
const BG_COLOUR = "rgba(0, 0, 0, 0.75)";

type PopInCaptionsProps = {
  sentences: CaptionSentence[];
};

export const PopInCaptions: React.FC<PopInCaptionsProps> = ({ sentences }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const currentTimeMs = (frame / fps) * 1000;

  const allWords = sentences.flatMap((s) => s.words);

  // Group words into chunks
  const groups: CaptionWord[][] = [];
  for (let i = 0; i < allWords.length; i += WORDS_PER_GROUP) {
    groups.push(allWords.slice(i, i + WORDS_PER_GROUP));
  }

  // Find the active group based on current time
  const activeGroupIndex = groups.findIndex((group) => {
    const groupStart = group[0].startMs;
    const groupEnd = group[group.length - 1].endMs;
    return currentTimeMs >= groupStart && currentTimeMs < groupEnd;
  });

  if (activeGroupIndex === -1) return null;

  const activeGroup = groups[activeGroupIndex];
  const groupStartMs = activeGroup[0].startMs;
  const appearFrame = Math.round((groupStartMs / 1000) * fps);

  // Spring animation for group entry
  const entryProgress = spring({
    frame: frame - appearFrame,
    fps,
    config: { damping: 14, stiffness: 150, mass: 0.5 },
  });

  const scale = interpolate(entryProgress, [0, 1], [0.6, 1]);
  const opacity = interpolate(entryProgress, [0, 1], [0, 1]);
  const translateY = interpolate(entryProgress, [0, 1], [20, 0]);

  return (
    <div
      style={{
        position: "absolute",
        bottom: "8%",
        left: 0,
        right: 0,
        display: "flex",
        justifyContent: "center",
        zIndex: 10,
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          backgroundColor: BG_COLOUR,
          borderRadius: 12,
          padding: "14px 28px",
          backdropFilter: "blur(8px)",
          transform: `scale(${scale}) translateY(${translateY}px)`,
          opacity,
        }}
      >
        <div
          style={{
            fontFamily: "'Inter', system-ui, sans-serif",
            fontSize: 48,
            fontWeight: 800,
            lineHeight: 1.4,
            textAlign: "center",
            whiteSpace: "pre-wrap",
          }}
        >
          {activeGroup.map((word, i) => {
            const isActive =
              currentTimeMs >= word.startMs && currentTimeMs < word.endMs;

            const wordAppearFrame = Math.round((word.startMs / 1000) * fps);
            const wordProgress = spring({
              frame: frame - wordAppearFrame,
              fps,
              config: { damping: 18, stiffness: 120, mass: 0.6 },
            });
            const wordScale = isActive
              ? interpolate(wordProgress, [0, 1], [1, 1.1])
              : 1;

            return (
              <span
                key={`${activeGroupIndex}-${i}`}
                style={{
                  color: isActive ? HIGHLIGHT_COLOUR : TEXT_COLOUR,
                  display: "inline-block",
                  transform: `scale(${wordScale})`,
                  transformOrigin: "center bottom",
                  fontWeight: isActive ? 900 : 700,
                  textShadow: isActive
                    ? `0 0 20px ${HIGHLIGHT_COLOUR}88`
                    : "none",
                }}
              >
                {word.text}{" "}
              </span>
            );
          })}
        </div>
      </div>
    </div>
  );
};
```

#### Style: Karaoke (already exists)

Use the existing `KaraokeCaptions` component at `src/ChessPromo/KaraokeCaptions.tsx`.
This shows full sentences with word-by-word highlighting.

#### Style: 3D Theatrical (already exists)

Use the existing `CaptionedVideo` component at `src/CaptionedVideo/index.tsx`.
This places words at fixed 3D positions around the frame.

### Step 5: Create the Composition

Create the main video component that layers the video with captions:

```tsx
import { z } from "zod";
import { AbsoluteFill, OffthreadVideo, staticFile } from "remotion";
import { useEffect, useState } from "react";
import { continueRender, delayRender } from "remotion";
import { PopInCaptions } from "./PopInCaptions";
import type { CaptionSentence } from "../ChessPromo/types";

export const schema = z.object({
  videoSrc: z.string(),
  captionsSrc: z.string(),
});

export const CaptionedComposition: React.FC<z.infer<typeof schema>> = ({
  videoSrc,
  captionsSrc,
}) => {
  const [sentences, setSentences] = useState<CaptionSentence[] | null>(null);
  const [handle] = useState(() => delayRender("Loading captions"));

  useEffect(() => {
    fetch(staticFile(captionsSrc))
      .then((res) => res.json())
      .then((data: CaptionSentence[]) => {
        setSentences(data);
        continueRender(handle);
      })
      .catch((err) => {
        console.error("Failed to load captions:", err);
        continueRender(handle);
      });
  }, [captionsSrc, handle]);

  if (!sentences) return null;

  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      <OffthreadVideo src={staticFile(videoSrc)} />
      <PopInCaptions sentences={sentences} />
    </AbsoluteFill>
  );
};
```

### Step 6: Register in Root.tsx

Add the composition to `src/Root.tsx`:

```tsx
import { Composition } from "remotion";
// ... existing imports
import { CaptionedComposition, schema } from "./<ProjectFolder>";

// Inside RemotionRoot:
<Composition
  id="<CompositionName>"
  component={CaptionedComposition}
  schema={schema}
  durationInFrames={totalFrames}  // Calculate from video duration
  fps={30}
  width={1920}
  height={1080}
  defaultProps={{
    videoSrc: "<video-filename>",
    captionsSrc: "<captions-json-filename>",
  }}
/>
```

### Step 7: Calculate Duration

Get the video duration to set `durationInFrames`:

```bash
ffprobe -v error -show_entries format=duration -of csv=p=0 "<video_path>"
```

Then: `durationInFrames = Math.ceil(durationSeconds * fps)`

## Conversion Script

Use this Python one-liner to convert Whisper JSON to Remotion format:

```bash
python3 -c "
import json, sys
with open(sys.argv[1]) as f:
    data = json.load(f)
sentences = []
for seg in data['segments']:
    words = []
    for w in seg.get('words', []):
        words.append({
            'text': w['word'].strip(),
            'startMs': round(w['start'] * 1000),
            'endMs': round(w['end'] * 1000),
            'confidence': round(w.get('probability', 0), 2)
        })
    if words:
        sentences.append({
            'startMs': round(seg['start'] * 1000),
            'endMs': round(seg['end'] * 1000),
            'text': seg['text'].strip(),
            'words': words
        })
with open(sys.argv[2], 'w') as f:
    json.dump(sentences, f, indent=2)
print(f'Converted {len(sentences)} sentences with {sum(len(s[\"words\"]) for s in sentences)} words')
" /tmp/whisper-captions/<filename>.json <output_path>
```

## Customisation Options

| Parameter | Default | Description |
|-----------|---------|-------------|
| `WORDS_PER_GROUP` | 5 | Words shown per pop-in group |
| `HIGHLIGHT_COLOUR` | `#FFD700` | Colour for the currently spoken word |
| `TEXT_COLOUR` | `#FFFFFF` | Colour for non-active words |
| `BG_COLOUR` | `rgba(0,0,0,0.75)` | Caption backdrop colour |
| `fontSize` | 48 | Base font size in pixels |
| `bottom` | `8%` | Caption vertical position |
| Whisper model | `medium` | `tiny`, `base`, `small`, `medium`, `large`, `turbo` |

## Troubleshooting

- **Remotion 404 on video files**: Remotion's bundler copies `public/` to a temp directory and does NOT follow symlinks. Always use real file copies, not symlinks, for videos in `public/`
- **Whisper runs slowly**: Use `--model turbo` for faster transcription or `--model small` for less accuracy but much faster
- **Poor word timestamps**: Increase model size; `medium` or `large` gives best word boundaries
- **Captions out of sync**: Check that the video fps in the composition matches what you set. Use `ffprobe` to verify the source video fps
- **Missing words in Whisper output**: Some segments may lack `words` array if Whisper confidence is very low; the conversion script skips these gracefully
