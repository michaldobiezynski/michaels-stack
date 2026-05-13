---
name: vitest-captured-callback-needs-act-wrap
description: |
  React Testing Library + vitest: when you mock a child component via
  `vi.mock` and capture its props (usually with `vi.hoisted`) so a test
  can invoke a callback like `onMove` / `onChange` / `onSubmit`
  synchronously, React state updates triggered inside that callback won't
  flush and subsequent DOM queries fail. Use when: (1) `getByTestId` or
  `queryByTestId` throws "Unable to find an element" for UI that SHOULD
  have appeared after the callback ran, (2) assertions that depend on a
  re-render after invoking a captured callback pass individually in debug
  but fail in the test, (3) `@testing-library/react` warns "An update to
  X inside a test was not wrapped in act(...)". Fix: wrap the synchronous
  invocation in `act(() => { captured.current.onMove("e2e4") })`.
author: Claude Code
version: 1.0.0
date: 2026-04-24
---

# Captured callback invocation from a mocked child needs `act()`

## Problem

You mock a React child component with `vi.mock` so tests can run without
a real Chessground / chart / editor instance. The mock captures the
latest rendered props (typically via `vi.hoisted` so the reference is
available across hoisted mocks), and your test invokes one of those
captured callbacks synchronously to simulate a user event:

```ts
act(() => captured.current.onMove("e2e4")); // needs act()
```

Without `act()`, any React state update that the callback triggers -
`setState`, `setXAtom`, etc. - is not flushed to the DOM before the next
assertion runs. Your subsequent `getByTestId("promotion-modal")` throws
"Unable to find an element" even though the callback fired and the
setter was called.

## Context / Trigger Conditions

- Test mocks a child component via `vi.mock("./Child", () => ({ Child:
  (props) => { captured.current = props; return <div .../> } }))`.
- Test retrieves the captured callback and invokes it outside any
  `fireEvent` / `userEvent` call: `captured.current.onSomething(...)`.
- The component under test responds to the callback by updating state
  (e.g. `setPendingMove(move)` to open a modal, `setCount(n+1)` to
  re-render a counter).
- Immediately after invoking the callback, the test asserts on DOM that
  only exists after the re-render and the assertion fails with
  "Unable to find an element by: [data-testid='...']".
- `@testing-library/react` may emit: "Warning: An update to <Component>
  inside a test was not wrapped in act(...)".

## Root cause

React 18 batches state updates and defers their commit. `fireEvent` and
`userEvent` internally wrap their work in `act()` so updates flush
before returning. A raw function call captured from a mocked component
has no such wrapper - the state update is queued but never committed
before your next query runs. The DOM you're querying is the pre-update
DOM.

`await waitFor(...)` doesn't help here because the commit never happens:
waitFor retries the query repeatedly against the same stale DOM.

## Solution

Wrap the synchronous callback invocation in `act()` from
`@testing-library/react`:

```ts
import { act } from "@testing-library/react";

// before - silent failure, getByTestId throws
captured.current.onMove("e7e8");
expect(screen.getByTestId("promotion-modal")).toBeInTheDocument(); // fails

// after - state flushes, DOM updated before the assertion
act(() => {
  captured.current.onMove("e7e8");
});
expect(screen.getByTestId("promotion-modal")).toBeInTheDocument(); // passes
```

If the callback is async (e.g. triggers an async effect), use
`await act(async () => { await captured.current.onMove(...); })`. For
purely synchronous state updates, the sync form is enough.

## Verification

Before the fix: the test fails with
`TestingLibraryElementError: Unable to find an element by: [data-testid=...]`,
and the rendered DOM dump in the error shows the pre-update state.

After the fix: the same assertion passes. If an "update not wrapped in
act(...)" warning was being emitted before, it disappears.

## Example

From a chess app where a mocked mini-board captures its `onMove` prop
so tests can invoke moves without driving a real chessground instance:

```tsx
const chessgroundLastProps = vi.hoisted(() => ({ current: null as any }));

vi.mock("@/chessground/Chessground", () => ({
  Chessground: (props: any) => {
    chessgroundLastProps.current = props;
    return <div data-testid="chessground-mock" />;
  },
}));

// ...
it("opens the promotion modal on pawn reaching the last rank", () => {
  const onMove = vi.fn();
  renderBoard({ fen: "7k/4P3/8/8/8/8/8/K7 w - - 0 1", onMove });
  act(() => {
    chessgroundLastProps.current.movable.events.after("e7", "e8", {});
  });
  expect(screen.getByTestId("promotion-modal-mock")).toBeInTheDocument();
});
```

Note that `fireEvent.click(screen.getByTestId("promotion-queen"))` in
the SAME test does NOT need explicit `act()` because `fireEvent`
internally wraps its work in `act()`. Only the imperative
`captured.current.callback(...)` invocation needs the wrapper.

## Notes

- Passes through equally to components captured via a plain
  module-level ref or a class field - `vi.hoisted` just makes the ref
  accessible from hoisted `vi.mock` factories.
- If you hit this across many tests, a tiny helper keeps the noise
  down: `const invoke = (fn, ...args) => act(() => fn(...args));` then
  `invoke(captured.current.onMove, "e2e4")`.
- Testing `useEffect` that fires after the state update may still
  need `await waitFor(...)`. `act()` flushes the current commit; an
  effect triggered by that commit runs on a later microtask.
- React 19's upcoming auto-act changes may relax this, but as of
  vitest 2.x + @testing-library/react 16.x, `act()` is still required.

## References

- [React Testing Library: `act`](https://testing-library.com/docs/react-testing-library/api/#act)
- [Fix the "not wrapped in act(...)" warning](https://kentcdodds.com/blog/fix-the-not-wrapped-in-act-warning)
- [React 18 automatic batching](https://react.dev/blog/2022/03/29/react-v18#new-feature-automatic-batching)
