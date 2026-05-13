---
name: mantine-notifications-vitest-cleanup
description: |
  Fix for Mantine `@mantine/notifications` toast notifications leaking between
  vitest test cases. Use when: (1) a test asserting `expect(...).not.toBeInTheDocument()`
  on a notification fails because the previous test's notification is still
  rendered, (2) you see error like "expected document not to contain element,
  found <div class='m-... mantine-Notification-description'>...", (3) running
  tests in isolation passes but the suite fails. Mantine notifications use a
  shared store that survives React unmounts and persists across vitest test
  cases unless explicitly cleaned. Add `notifications.clean()` to `beforeEach`.
author: Claude Code
version: 1.0.0
date: 2026-04-29
---

# Mantine notifications leak between vitest tests

## Problem

`@mantine/notifications` uses a Mantine store (`createStore`-based) under the
hood. The store is module-level - it lives outside the React tree. When a test
calls `notifications.show(...)`, the toast is added to that store. The next
test renders a fresh `<Notifications />` component, but it still subscribes to
the SAME store, so prior toasts re-mount immediately.

This causes baffling test failures where a "no notification on success" test
fails because a notification from a previous "shows error notification" test is
still in the DOM.

## Context / Trigger Conditions

- Vitest + React Testing Library + Mantine 7.
- Tests that assert no notification appears: `expect(screen.queryByText("error message")).not.toBeInTheDocument()`.
- Test failure looks like:
  ```
  expect(element).not.toBeInTheDocument()
  expected document not to contain element, found <div
    class="m-3d733a3a mantine-Notification-description"
    ...
  ```
- The text it found is from a PRIOR test in the same file, not the current one.
- Running the failing test in isolation (`vitest -t "specific test name"`) passes.

## Solution

Import `notifications` and call `notifications.clean()` in your `beforeEach`:

```ts
import { Notifications, notifications } from "@mantine/notifications";

beforeEach(() => {
  // ... your other resets
  notifications.clean();
});
```

This drops every queued + visible toast from the shared store.

## Verification

- Run the full test file: all tests pass.
- The previously failing "no notification on success" test passes.
- Order independence: shuffle test order, still passes.

## Example

```tsx
// Before fix - flaky test
beforeEach(() => {
  mockHook.mockReset();
});

it("shows error notification on failure", async () => {
  mockHook.mockResolvedValue({ ok: false, reason: "boom" });
  await userEvent.click(button);
  expect(screen.getByText("boom")).toBeInTheDocument(); // OK
});

it("does NOT show notification on success", async () => {
  mockHook.mockResolvedValue({ ok: true });
  await userEvent.click(button);
  // FAILS: previous test's "boom" notification still in DOM
  expect(screen.queryByText("boom")).not.toBeInTheDocument();
});
```

```tsx
// After fix - stable
import { Notifications, notifications } from "@mantine/notifications";

beforeEach(() => {
  mockHook.mockReset();
  notifications.clean(); // <-- the fix
});
```

## Notes

- `notifications.clean()` is sync and safe to call even when the store is
  empty.
- `notifications.cleanQueue()` only drops queued toasts (not visible ones) -
  useless for this scenario.
- React Testing Library's `cleanup()` (auto-called between tests in modern
  RTL) only handles the React tree. Mantine's store survives because it's
  module-level state.
- Same problem affects the modals API (`@mantine/modals`) - the equivalent is
  `modals.closeAll()`.
- If you mount `<Notifications />` inside your test wrapper, you still need
  `notifications.clean()` - the wrapper resets the React subscriber but not
  the store.

## References

- Mantine notifications API: https://mantine.dev/x/notifications/
- Mantine `notifications.clean()` docs (search the page for "clean"):
  https://mantine.dev/x/notifications/#notifications-store
