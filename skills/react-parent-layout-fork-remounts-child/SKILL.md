---
name: react-parent-layout-fork-remounts-child
description: |
  Silent remount trap: a parent component (typically a route layout) branches
  its render between two structurally different trees based on a global-store
  atom (Jotai, Redux, Zustand, Context). Both branches contain the same child
  slot (e.g. `<Outlet />`), but React reconciles by tree position, not by the
  logical identity of the child. When the atom flips, the child is unmounted
  and a fresh instance mounts. Local `useState` and `useRef` inside that child
  are wiped; global-store state survives. Effects that guard on local state
  (`if (!fen || !tabId) return`) then early-return forever. Use when: a UI
  flow that was working during a single mount suddenly stops working after a
  user action that flips a parent-layout atom; local state appears blank
  despite having been set; symptom is stuck placeholder UI with no error and
  no thrown exception. Fix: promote the companion local state to the same
  global store so it survives the remount, OR restructure the parent so the
  child slot sits at the same tree position in both branches.
author: Claude Code
version: 1.1.0
date: 2026-04-23
---

# React parent-layout fork remounts the child

## Problem
A parent layout component conditionally branches its render between two
different element trees. Both branches contain what looks like the same
child — often `<Outlet />` or a named route component — but because React
reconciles children by their position in the element tree, the two
`<Outlet />`s are treated as different nodes. When the branch condition
flips, the old subtree unmounts and a new instance mounts. Local `useState`,
`useRef`, and any non-persistent state inside the child are wiped. Global
store state (Jotai atom, Redux slice, Zustand store) survives because it
lives outside the component. Effects whose guards depend on the now-wiped
local state silently early-return forever. No error, no log, no exception.

## Context / Trigger Conditions
- A parent layout or route shell contains a pattern like:
  ```tsx
  if (isChromeless) {
    return <Outlet />;
  }
  return <AppShell>...<AppShell.Main><Outlet /></AppShell.Main></AppShell>;
  ```
  or the equivalent with any other wrapper (Context.Provider, Suspense
  boundary, theme wrapper, portal).
- The branch condition is a global-store value (atom, selector, hook) that
  some child action is responsible for flipping.
- The child uses a mix of `useState` / `useRef` and global-store values.
- The user performs an action that flips the condition, and afterwards the
  child sits in an impossible state: loading/placeholder UI forever, with
  no thrown error.
- A log inside the relevant effect shows it firing with the global-store
  value true/set, but the local-state guards are null/default.

## Root cause
React's reconciler matches children by position in the rendered element
tree. `<A><B/></A>` and `<B/>` put `<B/>` at different positions even
though `<B/>` is the same component. Switching between them unmounts and
remounts `<B/>`. This is not a bug — it's how React identifies which
components are "the same" across renders.

Global-store values survive because they're owned by the store, not by any
one component instance. Local `useState` / `useRef` are per-instance, so a
remount resets them.

## Solution
Two options, in order of preference:

1. **Restructure the parent so the child sits at the same tree position in
   both branches.** Instead of an `if/else return`, render one tree and
   vary props/children on nested components. For example: always render
   `<AppShell>` and conditionally render `<AppShell.Navbar>` inside it.
   This preserves child identity. Prefer this when layout logic is simple
   and the restructure is low-risk.

2. **Promote the relevant local state to the global store.** Move every
   `useState` / `useRef` that the child needs across the branch flip into
   the same store that drives the branch. The state survives the remount.
   Use this when the parent restructure is risky (e.g. framework
   components like Mantine's `AppShell` have their own reconciliation
   quirks) or when the state is already logically global.

Either way, add a unit test that triggers the branch flip and asserts the
child behaviour is uninterrupted.

## Verification
Add a log at the entry of the affected effect that prints every relevant
guard value. Before the fix: you see the effect fire with the branch-flip
atom set, but companion guards null. After the fix: guards survive the
flip; the effect body runs.

## Example (Pawn au Chocolat, 2026-04)

Parent: `src/routes/__root.tsx` branched on `compactLiveAnalysisModeAtom`:
```tsx
if (isChromeless) {
  return <Outlet />;
}
return (
  <AppShell ...>
    <AppShell.Navbar><SideBar /></AppShell.Navbar>
    <AppShell.Main><Outlet /></AppShell.Main>
  </AppShell>
);
```

Child `LiveAnalysisView` called `setCompactMode(true)` (Jotai atom) plus
four local `useState` setters (`compactFen`, `compactTabId`, `compactCrop`,
`compactConfidence`). The parent tree flipped, `LiveAnalysisView`
remounted, the four locals reset to null. The engine-start effect ran on
the new instance with `compactMode=true` but `compactFen=null`,
`compactTabId=null` — early-returned forever. UI stuck on "Analysing..."
with no error.

Fix: option 2 (promote to atoms). Added `compactLiveAnalysisCropAtom`,
`compactLiveAnalysisFenAtom`, `compactLiveAnalysisConfidenceAtom`,
`compactLiveAnalysisTabIdAtom` alongside the existing mode atom. Swapped
the four `useState` for `useAtom`. The engine-start effect now sees all
four guards populated on remount.

## Sub-pattern: "flip atom + navigate in same handler" = wrong-route mount race

A related failure mode surfaces when a component OUTSIDE the branch-flipping
route triggers both the flip AND a router navigation in the same event
handler. Example: a button on route `/` calls both `setCompactMode(true)`
(which makes `__root`'s `isChromeless` flip) and `navigate({ to: "/live" })`
(which changes the route). Both updates batch, but the intermediate commits
still matter:

1. Atom commits first → `__root` re-renders chromeless at route `/` → the
   `/` route's tree (e.g. BoardAnalysis) remounts in the chromeless branch.
2. Router commits → Outlet re-renders with `/live` → LiveAnalysisView
   mounts.

In practice, the Jotai atom subscriber ordering + React's batched-update
scheduling sometimes end up with LiveAnalysisView mounting with
`compactMode=false` already — the atom flip briefly bounced back via the
intermediate unmount cleanup on a sibling component, or the order-of-
operations swapped. User-visible symptom: target route renders in its
pre-compact state (window-picker / placeholder), not the compact view.

**Fix: hand the state off via a pending-signal atom consumed on the target
route's mount.** Concretely, instead of the button doing `setCompactMode(true)
+ navigate('/live')`, it does `setPendingCompactReturn({fen, orientation})
+ navigate('/live')`. LiveAnalysisView mounts at `/live`, reads the pending
atom in a mount effect, runs its own enterCompactMode-equivalent (resize,
set the compact atoms, flip `compactMode=true`), and clears the signal.

This mirrors the `pendingEditingTabIdAtom` pattern already used for the
reverse direction (compact → edit tab). The key property: state mutations
that would cause a remount happen on the ROUTE that renders the target
component, not on a peer route, so the branch-flip happens once and cleanly.

Trigger indicators for this sub-pattern:
- Button / handler sits on route A.
- Handler sets a store value that controls the parent-layout branch AND
  calls `navigate({ to: "B" })`.
- Target route B's root component renders the layout's non-default branch.
- User reports landing on the "wrong" version of route B (the pre-flip
  branch's rendering of it).

## Notes
- Distinct from `tauri-specta-listener-emit-race` (listener attached too
  late) and `tauri-specta-overstrict-payload-filter` (listener's guard
  rejects every payload). All three produce the same user-visible symptom
  (stuck placeholder UI with no error), but have different causes and
  different fixes. Triage by: (a) is the effect firing at all? (b) does
  the Rust emit log fire? (c) what do the guard values look like on the
  JS side?
- Watch for parent layouts that branch on ANY global-store value — feature
  flags, theme variants, authenticated-vs-not, compact-mode, full-screen.
- In React 18 StrictMode, the double-mount on initial mount can mask this
  bug during development: the first mount looks fine. The bug only appears
  after a user action that flips the branch.
- `AppShell` from Mantine, `Layout` slots in Next.js, and custom layout
  components with conditional wrappers are common offenders.
- If you pick option 1 (restructure), test carefully — some layout libs
  reshuffle internal nodes when top-level props change, which can still
  cause remounts. Option 2 is more conservative.

## References
- React reconciliation docs: https://react.dev/learn/preserving-and-resetting-state
- Jotai atom scope: https://jotai.org/docs/guides/initialize-atom-on-render
