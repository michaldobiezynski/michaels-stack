---
name: r3f-drag-and-drop-animated-camera
description: |
  Drag-and-drop of objects (chess pieces, tokens, cards) on a board in React Three Fiber when the camera can
  animate (drei CameraControls / camera-controls). Use when: (1) releasing a camera drag over a square
  "clicks" it and moves a piece, (2) a drag started right after an animation (a zoom on a capture, a focus
  move) lifts the piece but drops it on the wrong square or nowhere, (3) letting go above the horizon plays
  the last hovered square, (4) a piece picked up in one view is still "in hand" in another view that shares
  ids, (5) a drop is refused because a stale selection turns it into a second tap.
author: Claude Code
version: 1.0.0
date: 2026-09-28
---

# Drag and drop on an R3F board with an animated camera

## Problem
Drag-and-drop works in a still scene and breaks around camera motion and R3F's click semantics.

## Context / Trigger Conditions
- R3F objects with `onClick`, a board of squares, drei `CameraControls` that also moves programmatically
  (attack zooms, overview returns). Often the camera is "locked" (user input off) but still animated by code.

## Solution
1. **A drag is not a tap.** R3F fires `onClick` on whatever the press hit, however far the pointer moved.
   Check `e.delta > SLOP_PX` (about 6 px) in every click handler that selects or acts (squares, pieces,
   choosers). A timer that "swallows the next click" after a drag is fragile (the release may land off the
   canvas and the timer eats the next real tap); delete it once the delta check is in.
2. **Hold the view still while something is carried.** On lift, freeze any transition in progress and
   remember where it was going: compare `controls.getPosition(v, true)` (the end) with
   `getPosition(v, false)` (now), and if they differ, `setLookAt(now..., false)`. Defer moves due meanwhile
   (returns to an overview, new-game resets). On drop, resume the remembered move, unless the drop starts a
   new animation of its own. Without this the square under the pointer slides during the carry.
3. **Project onto the board plane each move**, and treat a miss (a ray above the horizon) as off the board:
   never fall back to the last on-board point.
4. **Route the drop through the same select/move path a tap uses** (one source of move logic: legality,
   promotion choosers, castling by king-onto-rook).
5. **Clear state at the edges:** drop anything in hand when the view unmounts (another view may reuse the
   same piece ids), when the game changes under the drag (new game, take-back), and reset any selection
   refs on every move played, or the lift's select reads as a second tap.
6. **Let a piece on its way home be picked up again at once:** refuse a new press only while lifted or
   dropped, not while it eases back.

## Verification
Acceptance tests with the real mouse: a camera drag released over a square moves nothing; drags started at
several times into a camera animation land on the intended square with the view steady within a pixel while
held; a release above the horizon plays nothing; each guard mutation-checked (remove it, see red).

## Example
Chess Explosion, 27-28/09/2026 (`src/scene/useDragMoves.ts`, `drag.ts`, `dropTarget.ts`, Director): a
drag at 0.9 s and 1.2 s into the attack zoom's ease-back missed (d5 slid 92 and 64 px; a square is 79 px);
fixed by holding the view while a piece is in hand. A fresh-context review also found the pre-existing
camera-drag-release click (fixed with `e.delta`), a stale `selection.current` after the engine moved, and a
spotlight pawn sharing the id `wp1` pulled towards an old drop point.

## Notes
- Related: `playwright-3d-canvas-click-tests` (real-mouse tests, camera rest), `qa-walkthrough-agent`.
