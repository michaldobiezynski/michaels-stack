---
name: webgl-demo-capture
description: |
  Capture live three.js / WebGL / WebGPU demos for research, headless: screenshots on load and after
  interacting, a short WebM clip, a GPU check and a frame-rate sample, then a structured findings report,
  batched across Sonnet subagents with a ready prompt template. Use when: (1) studying reference or
  competitor 3D sites ("screenshot and record these demos"), (2) auditing your own WebGL page the same way,
  (3) agent-browser's `--args "--ignore-gpu-blocklist,--enable-unsafe-webgpu"` seems ignored with "daemon
  already running", (4) a demo snaps back to its title screen under automated drags, (5) you need
  before/after contact sheets of stills. Pairs with threejs-journey-challenge-research and webgl-award-rubric.
author: Claude Code
version: 1.1.0
date: 2026-09-27
---

# Capturing live WebGL demos

## Problem
Research on 3D sites needs evidence (stills, clips, frame rate, what the GPU was), gathered without
crashing the laptop, interrupting the user with windows, or reporting software-rendered frame rates.

## Context / Trigger Conditions
- The agent-browser CLI is installed (see the `agent-browser` skill for its full command set).
- Several demos to study; each may be heavy, gated behind an Enter button, or fragile under input.

## Solution
1. **One named session per agent, headless, one page at a time:** `agent-browser --session <name> open <url>`,
   and `agent-browser --session <name> close` before the next entry. At most two capture agents at once.
2. **GPU flags only apply when the agent-browser daemon starts.** Later `--args` are silently ignored
   ("daemon already running") and restarting the daemon would kill other agents' sessions. So instead of
   trusting flags, check each page with `eval` (snippets below) and report what the GPU really was.
3. **Per entry:**
   - open, wait ~6 s, `screenshot <dir>/1-load.png`;
   - `record start <dir>/clip.webm`, then 15-25 s of visitor-paced interaction (Enter/Start, slow drags to orbit,
     scroll, WASD/arrows if it walks, clicks on things that look interactive), `record stop`;
   - `screenshot <dir>/2-after.png` (and `3-scene.png` for a distinctly better view);
   - GPU and frame-rate probes, then `ls -la <dir>` to prove every file exists with a non-zero size.
4. **Interact like a person.** Fast, large automated drags and wheel bursts reset several demos to their
   title screen (seen on 10+ entries), and rapid WASD bursts hard-hung the JS thread on two builds by one
   author. Retry slowly before calling it a bug. **Never press Escape** in headless captures: it crashed
   the tab to about:blank on two entries (pointer-lock/fullscreen exit).
5. **Rules for agents:** never log in, pay or grant permissions (camera, microphone); never clone or copy
   code (note linked repos and licences); if a page hangs for 60 s, close it and move on; never visit hosts
   the user has excluded (for example threejs-journey.com, which rate-limits browsers).
6. **Report per entry:** URL; tech (three revision via `window.__THREE__`, WebGL/WebGPU, fps); look
   (palette, lighting, post-processing, materials); feel (onboarding, controls, sound, UI); standout
   techniques with High (seen) / Moderate (inferred) / Low (guess) labels; one or two things to borrow;
   file paths. Then a ranked top five across the batch and any cautions.
7. **Contact sheets** for comparisons: `python3 scripts/contact_sheet.py out.png "Label|a.png|b.png" ...`
   lays each row out as a label over two images (before/after, ours/theirs).

## Probe snippets (for `agent-browser --session <name> eval "..."`)
GPU and three revision:
```js
(() => { const c = document.createElement('canvas'); const gl = c.getContext('webgl2') || c.getContext('webgl');
  const d = gl && gl.getExtension('WEBGL_debug_renderer_info');
  return JSON.stringify({ renderer: d ? gl.getParameter(d.UNMASKED_RENDERER_WEBGL) : null, webgpu: !!navigator.gpu, three: window.__THREE__ || null }) })()
```
Frame rate over two seconds:
```js
new Promise((r) => { let n = 0; const t0 = performance.now(); const f = () => { n++;
  if (performance.now() - t0 < 2000) requestAnimationFrame(f); else r(Math.round(n / ((performance.now() - t0) / 1000))) };
  requestAnimationFrame(f) })
```
A software renderer ("SwiftShader") or single-digit fps means the numbers are not the site's.

## Subagent prompt template
> You are a research agent studying live three.js demos. Work alone (no subagents), British English.
> Context: <your project in two sentences and what you most want to learn>.
> Entries (in order): <n. title URL>...
> Rules: agent-browser headless with your own session `<name>`, one browser open at a time (close after
> each entry); do not restart the daemon; check the GPU per page with eval; never visit <excluded hosts>;
> no logins, payments or permissions; no cloning or copying code; if a page hangs 60 s, move on.
> Per entry: 1-load.png after ~6 s, a 15-25 s clip.webm while interacting at a visitor's pace,
> 2-after.png (3-scene.png optional), a 2 s rAF fps sample, verify files with ls -la. BASE=<dir>.
> Report (under 1200 words): per entry URL, tech, look, feel, standout techniques with confidence labels,
> what to borrow, file paths; then a ranked top five and cautions; say plainly what failed.

## Verification
Every folder the report names contains non-zero `1-load.png`, `2-after.png` and `clip.webm`; the GPU
string names real hardware (for example "ANGLE Metal Renderer: Apple M5 Pro"), not SwiftShader.

## Notes
- Pointer Lock does not engage in headless Chrome, so first-person demos need their start overlay cleared
  and may not respond to mouse-look; that is the harness, not the site.
- A capture agent costs ~200-250k tokens and ~20-25 minutes for nine entries.
