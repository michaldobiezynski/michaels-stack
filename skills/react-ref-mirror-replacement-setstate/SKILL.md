---
name: react-ref-mirror-replacement-setstate
description: |
  Fix lost state updates in a React provider that mirrors useState in a useRef
  (`stateRef.current = state` during render) so imperative callers can read the latest state
  at once. Use when: (1) a function builds the next state from `stateRef.current` and calls
  `setState(nextValue)` so the next call in the same handler can read it (chaining a jump, a
  move and a finish), (2) a change queued elsewhere with `setState(prev => ...)` from a timer,
  a requestAnimationFrame / R3F useFrame callback or a worker message silently disappears when
  such a function runs before React renders, (3) intermittent state loss that grows under load
  (slower renders widen the window), (4) turning an updater-based setter into a synchronous one.
  The fix is a fast-path updater: `setState((s) => (s === before ? after : build(s)))`.
author: Claude Code
version: 1.0.0
date: 2026-10-01
---

# React ref mirror: a replacement setState drops queued updates

## Problem

A provider keeps a ref in step with its state so imperative methods (a game's `play()`,
`goTo()`, `finishNow()`) can read the latest state without waiting for a render:

```ts
const [state, setState] = useState(initial)
const stateRef = useRef(state)
stateRef.current = state // re-synced on every render
```

To let one handler chain calls (jump, then move, then finish at once), a method is changed
from an updater to a synchronous build plus a plain value:

```ts
const after = build(stateRef.current)
stateRef.current = after // the next call reads it at once
setState(after)          // a replacement
```

React applies queued updates in order, and a plain value **replaces whatever the updaters
before it produced** (react.dev, "Queueing a Series of State Updates": replace with 5, then
n => n + 1, then replace with 42 gives 42). `stateRef.current` only catches up at render. So an
updater queued by a timer or animation frame that has not rendered yet (a puff of dust done, a
gust) is applied and then thrown away by the replacement, which was built from the older state.

## Context / trigger conditions

- A `useState` + `useRef` mirror, re-synced during render, with some methods that build from
  the ref and call `setState(value)`, and others (often callbacks from rAF, `useFrame`, timers or
  workers) that queue `setState(prev => ...)`.
- A field an updater changed reverts, or an entry an updater removed lingers (an invisible
  component stays mounted), only sometimes and more often on a slow or loaded machine.
- The code under a flaky end-to-end test was recently switched from an updater to a
  synchronous build. That is a reason to inspect it even if the flake is a known one.

## Solution

Keep the synchronous result for chained callers, but hand React an updater that uses it only
when nothing came in between:

```ts
const line = moves.current.map((m) => m.san) // capture mutable refs at call time
const played = (s: GameState): GameState => ({ ...s, ...buildMove(s, move, line) }) // pure
const before = stateRef.current
const after = played(before)
stateRef.current = after
setState((s) => (s === before ? after : played(s)))
```

- With nothing queued in between, React's running state *is* `before` (the rendered state, or
  the object a previous synchronous replacement put in both the ref and the queue), so the
  result is exactly `after`: chained callers and React agree.
- With an updater queued first, `s !== before` and the move is built again on top of it, as
  the old updater version did.
- `build` must be pure: React may call the updater twice in StrictMode and runs it later than
  the call. Capture at call time anything read from refs that later calls mutate (ids, the
  line of moves). A live mutable object (say a chess.js instance) read inside `build` is only
  safe if any later call that mutates it also queues its own update after this one.
- Apply the same treatment to other synchronous replacement setters where their rebuild is
  pure. Where the rebuild has side effects (starting timers, setting refs), it is not a
  drop-in; weigh the fix against the harm of the lost update.

## Verification

- Reason it through against the queue order: list every `setState(prev => ...)` site and
  which task queues it (event, timer, rAF, worker), then every synchronous replacement and
  who can call it before the next render.
- A deterministic test is hard: it needs an updater queued from a non-React task and the
  synchronous call before React's scheduled render. In a browser test, call both in one
  `page.evaluate` and assert a field only the updater changes. If that field is overwritten
  anyway by the call (a move clears the selection), pick another or rely on review.
- In the case this skill comes from (Chess Explosion `GameContext.play()`, 01/10/2026), a
  fresh-context review against React 19.2.8's source (queue processing, `basicStateReducer`,
  eager state) found no defect, and the unit, extension and site suites stayed green. No test
  reproduced the lost update itself.

## Example

Before (drops a queued `onDustDone` or gust update if a move comes first):

```ts
const s = stateRef.current
const after = { ...s, ...snapshot(chess, applyMove(s.pieces, move, id, seed).pieces, extra) }
stateRef.current = after
setState(after)
```

After: the fast-path updater above. Master's original `setState((s) => ...)` never dropped
anything, but it could not be read synchronously by the next call in the same handler.

## Notes

- `busy` flags that follow the *rendered* state (cleared in an effect) already keep moves
  from starting mid-sequence, so the remaining window is non-sequence updates (dust, gusts,
  selection) plus direct imperative callers (a mirror driven by messages).
- React 19.2 renders updates from clicks, messages, animation-frame callbacks and timers in one
  pass, so a render will not split them by priority and leave the ref at an older state.
  Transitions or deferred updates would need separate thought.
- Related: `zustand-react-state-race` (a synchronous store beside batched React state).

## References

- [React: Queueing a Series of State Updates](https://react.dev/learn/queueing-a-series-of-state-updates)
- [React: useState, updating state based on the previous state](https://react.dev/reference/react/useState#updating-state-based-on-the-previous-state)
