---
name: organise-remotion-videos
description: |
  Organise Remotion video output files into per-project folders. Use when:
  (1) the user asks to organise, move, or sort videos in the my-video/out/ directory,
  (2) new videos have been rendered and need filing into project folders,
  (3) the user asks to "move videos to their own folder" or "organise output".
  Covers the my-video Remotion project where multiple compositions share a single
  out/ directory and need separating by project.
author: Claude Code
version: 1.0.0
date: 2026-02-10
---

# Organise Remotion Video Output

## Problem

The Remotion project (`my-video`) renders all video compositions to a single `out/` directory.
Over time, videos from different projects (chess app, wordsmith, demos, etc.) accumulate and
become difficult to manage. Videos need to be grouped into per-project subfolders.

## Context / Trigger Conditions

- User asks to organise videos in `my-video/out/`
- User says "move videos to their own folder"
- New videos rendered and user wants them filed by project
- The `out/` directory contains a mix of videos from different projects

## Solution

### Step 1: Identify videos and their projects

1. List files in `my-video/out/` with dates: `ls -la my-video/out/`
2. Cross-reference with source compositions in `my-video/src/` to identify project groupings
3. Use file naming patterns and modification dates to group related videos

### Step 2: Ask the user for the project folder name

- The user chooses the folder name (e.g., `pawn-au-chocolat` for chess videos)
- Use kebab-case for folder names

### Step 3: Create project folders and move files

```bash
mkdir -p my-video/out/<project-name>
mv my-video/out/<video1>.mp4 my-video/out/<video2>.mp4 my-video/out/<project-name>/
```

### Step 4: Handle all remaining loose files

- Group related files (videos + previews/thumbnails with matching prefixes)
- Create separate folders for each project
- Don't leave any loose files in `out/`

## Key Mapping: src/ to out/

The `src/` directory contains composition folders that map to output files:

| Source folder     | Output file pattern        |
| ----------------- | -------------------------- |
| `ChessVideos/`    | chess-related names        |
| `WordsmithDemo/`  | `wordsmith-*`              |
| `CommentsDemo/`   | `comments-demo.*`          |
| `ExportDemo/`     | `export-demo.*`            |
| `SmartDetectionDemo/` | `smart-detection-demo.*` |
| `HelloWorld/`     | `HelloWorld.*`             |

## Verification

Run `ls -R my-video/out/` to confirm:
- No loose video files remain in `out/`
- Each subfolder contains only its project's files
- Related assets (thumbnails, previews) are grouped with their videos

## Example

```bash
# Before
out/
  board-analysis.mp4
  wordsmith-demo.mp4
  HelloWorld.mp4

# After
out/
  pawn-au-chocolat/
    board-analysis.mp4
  wordsmith-demo/
    wordsmith-demo.mp4
  hello-world/
    HelloWorld.mp4
```

## Notes

- Always ask the user for the project folder name rather than guessing
- Group related non-video assets (`.png` previews) with their video project
- Use kebab-case for new folder names
- Check modification dates to identify which videos belong to the same render batch
