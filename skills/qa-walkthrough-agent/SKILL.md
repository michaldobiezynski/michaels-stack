---
name: qa-walkthrough-agent
description: |
  Run a report-only QA walkthrough agent that clicks through a web app or 3D scene with the real mouse, the
  way the user would, to catch what green e2e suites miss. Use when: (1) a batch of features has landed
  (especially from parallel agents) and the user will review later, (2) the e2e tests drive the app through
  test hooks or probes (a `window.probe.tap(x, z)`, dispatching actions) rather than real pointer input,
  (3) the user's own click-through found bugs the suite passed, (4) before a morning review or a demo.
  Covers the brief, the one-browser/own-port rules, the report shape, and how to triage and route fixes.
author: Claude Code
version: 1.0.0
date: 2026-09-28
---

# QA walkthrough agent

## Problem
Suites that act through probes (a test hook that calls the app's tap handler, a store dispatch) skip the
pointer path entirely. Real bugs live there: an invisible mesh stealing clicks, a camera animation sliding
the drop target, a hazard placed beside an attraction, a message hidden by a hover prompt. The suite stays
green; the user finds them in five minutes.

## Context / Trigger Conditions
- Many features merged in a short time, several by parallel workers.
- The user reviews later ("I will review in the morning"), so a pre-review pass is cheap insurance.

## Solution
1. **Brief a report-only agent** (a fork works well: it knows the probe API and the app): check out the
   latest main in its own worktree, its own dev-server port (`E2E_PORT=...`), headless, one browser, and
   **no code changes**. List the walk explicitly, in the user's words where possible: the user's own
   feedback items, every new feature, the flows between pages (intro, back links, deep links), and
   "anything broken, ugly or confusing". Ask for stills at each step, looked at.
2. **Tell it to use the real mouse** for anything a person clicks, and probes only for setup (placing,
   fast-forwarding), and to wait for the camera to rest before aiming.
3. **Report shape:** numbered problems (exact steps, expected vs seen, still path, Major/Minor/Cosmetic),
   then what worked, then what it could not exercise (sound, phones, framed pages). Under ~500 words.
4. **Triage** like review findings: act on problems with a concrete reproduction; route each fix to whoever
   wrote that code (they know it), in parallel, one branch each; fix your own red-first with the real mouse.
5. **Run a second pass** after the fixes land, by an agent that did not build the parts it walks (fresh
   eyes), covering what the first pass could not see.
6. Keep the GPU quiet for frame-rate claims: other headless Chromes skew them; say so in the report.

## Verification
Each confirmed problem gets an acceptance test that uses the real pointer (red before the fix), and the
second pass confirms the fixes from a visitor's point of view.

## Example
Chess Explosion, 27-28/09/2026: the first pass (on master after eight PRs) found two Majors the green suite
hid: the door to the game could not be clicked (the crown's faded ward mesh, `visible = false`, still
raycast and caught the clicks; every door test used the probe), and drags right after a capture missed (the
attack zoom's ease-back slid the drop square 64-92 px under the pointer). The second pass found a charged
geode beside the owl knocking down visitors who went to see it, and a knock-down line hidden by the hover
prompt. All were fixed with real-mouse tests within the night.

## Notes
- A QA agent's own test mistakes are common (aiming while the camera moves, teleporting the pawn so an
  "arrived" event never fires); ask it to say which failures were its own timing.
- Related: `playwright-3d-canvas-click-tests` (real-mouse canvas tests), `webgl-demo-capture` (stills).
