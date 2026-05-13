---
name: zustand-react-state-race
description: |
  Race condition when mixing zustand (synchronous) and React state (batched)
  in the same component. Use when: (1) a useEffect fires with stale React state
  after a zustand store update, (2) puzzle/game completion resets unexpectedly
  after transitioning to a new item, (3) position/tree resets trigger unintended
  side effects in useEffect watchers, (4) state from jotai atoms or useState
  appears stale inside effects triggered by zustand changes.
  Common in apps that use zustand for tree/game state alongside React state
  (jotai, useState, useSessionStorage) for UI/metadata.
author: Claude Code
version: 1.0.0
date: 2026-04-09
---

# Zustand + React State Race Condition

## Problem
When a component uses both zustand (for synchronous state like a game tree)
and React state (jotai atoms, useState, useSessionStorage for UI metadata),
a useEffect watching zustand-derived values can fire before React has applied
batched state updates. This causes the effect to see stale React state while
reacting to fresh zustand state.

## Context / Trigger Conditions
- Component uses both `useStore(store, selector)` (zustand) and `useAtom()`
  or `useState()` for related state
- A useEffect watches a zustand-derived value (e.g. `position.length`)
- The effect also reads React state (e.g. `isPuzzleComplete` derived from
  `puzzles[currentPuzzle].completion`)
- A single user action triggers both a zustand update AND React state updates
- The zustand update changes a value the useEffect watches
- The React state updates haven't been applied yet when the effect fires

## Concrete Example (pawn-au-chocolat puzzle bug)

```
1. User solves puzzle correctly
2. changeCompletion("correct") called → queues React state update
3. generatePuzzle() called → starts async fetch
4. Async resolves → setPuzzles() and setCurrentPuzzle() queued (React)
5. setPuzzleState() calls setFen() → zustand store updates SYNCHRONOUSLY
6. position.length drops from N to 0 (tree reset)
7. useEffect fires because position.length changed
8. isPuzzleComplete is STILL TRUE (React hasn't applied step 4 yet)
9. Effect sees: position decreased + puzzle complete → resets to "incomplete"
10. The just-solved puzzle loses its "correct" completion ← BUG
```

## Solution: Transition Guard Ref

Use a mutable ref as a guard flag to skip the effect during transitions:

```typescript
const isTransitioningRef = useRef(false);

useEffect(() => {
  // Skip during transitions (zustand resets while React catches up)
  if (isTransitioningRef.current) {
    prevPositionLengthRef.current = position.length;
    return;
  }

  // Normal backward-navigation detection
  if (currLength < prevLength && isPuzzleComplete) {
    changeCompletion("incomplete");
  }
  prevPositionLengthRef.current = position.length;
}, [position.length, isPuzzleComplete]);

// Set guard BEFORE triggering the transition
function transitionToNext() {
  isTransitioningRef.current = true;
  setReactState(newValue);     // queued (React)
  zustandAction();             // immediate (zustand)
  requestAnimationFrame(() => {
    isTransitioningRef.current = false;  // clear after React commits
  });
}
```

## Why requestAnimationFrame?
- React 18 batches state updates within the same event handler
- The batched updates are committed in the next microtask/render cycle
- `requestAnimationFrame` fires after the browser paint, ensuring React
  state has been applied before the guard is lowered
- `setTimeout(fn, 0)` also works but rAF is more semantically correct

## Verification
1. Solve a puzzle correctly with "jump to next immediately" enabled
2. The solved puzzle should show a green checkmark (not yellow dot)
3. Navigate history by clicking old puzzles — their completions should persist
4. Going backward on the CURRENT puzzle should still reset to incomplete

## Notes
- This pattern applies anywhere zustand and React state interact in effects
- The core issue is that zustand updates are synchronous while React batches
- Alternative: move ALL related state into zustand (eliminates the mismatch)
- Alternative: use `useSyncExternalStore` with a custom store that batches
- The ref approach is simplest when you can't restructure the state architecture
- Always guard BOTH directions: generating new items AND navigating history
