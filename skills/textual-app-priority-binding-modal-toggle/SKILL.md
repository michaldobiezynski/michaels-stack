---
name: textual-app-priority-binding-modal-toggle
description: |
  Fix for a Textual TUI where pressing a single key to toggle a help/about/
  command-palette modal (e.g. `?` opens it, `?` again should close it)
  ends up stacking multiple copies of the modal instead of dismissing.
  Use when: (1) you have an App-level `Binding(..., priority=True)` that
  pushes a `ModalScreen` via `self.push_screen(MyModal())`, (2) the same
  key is bound on the ModalScreen (also priority=True) to dismiss, and
  the dismissal doesn't fire — pressing the key while the modal is open
  pushes ANOTHER instance on top of the existing one, (3) you confirm via
  Pilot that `type(app.screen).__name__` stays `MyModal` after pressing
  the toggle key a second time. Root cause: App-level priority bindings
  fire BEFORE screen-level bindings (even on a ModalScreen that nominally
  "blocks" events), so the App's push handler runs every time and the
  screen's dismiss handler never gets a chance. Fix: collapse the
  open-and-close to a single App-level action method that checks
  `isinstance(self.screen, MyModal)` and calls `self.pop_screen()` when
  the modal is already on top, otherwise pushes. Don't bind the toggle
  key on the modal at all.
author: Claude Code
version: 1.0.0
date: 2026-05-18
---

# Textual: App-level priority binding can't be dismissed by a same-key modal binding

## Problem

You want a single key to toggle a modal (help screen, command palette,
about box). The natural Textual setup is:

- `App.BINDINGS` includes `Binding("question_mark", "show_help", "?", priority=True)`,
  and `action_show_help` calls `self.push_screen(HelpScreen())`.
- `HelpScreen.BINDINGS` includes `Binding("question_mark", "dismiss_help", "close", priority=True)`,
  and `action_dismiss_help` calls `self.dismiss()`.

You'd expect: press `?`, modal opens. Press `?` again, modal closes. In
practice: pressing `?` again pushes ANOTHER `HelpScreen` on top of the
existing one (sometimes silently — the UI looks unchanged because
both modals render identically). After N presses, you have N modals
stacked, and `pop_screen` only removes them one at a time.

Pilot test reveals the issue:

```python
async with app.run_test() as pilot:
    await pilot.press("question_mark")
    print(type(app.screen).__name__)  # "HelpScreen"  ← good
    await pilot.press("question_mark")
    print(type(app.screen).__name__)  # "HelpScreen"  ← STILL HelpScreen, not dismissed
```

## Trigger conditions

ALL of:

- Textual app (any version 0.x or 1.x+ — confirmed on 8.2.6).
- App-level binding for the toggle key, marked `priority=True`.
- Action method calls `self.push_screen(SomeModalScreen())`.
- The ModalScreen also has a binding for the same key (priority or not),
  calling `self.dismiss()`.
- Symptom: pressing the toggle key a second time does not dismiss.
- Pilot inspection of `app.screen` confirms the modal stays on top.

## Root cause

Textual's binding dispatch checks **App-level priority bindings first**,
before any screen-level bindings — even when a `ModalScreen` is on top.
A ModalScreen "blocks" input from reaching screens BELOW it on the stack,
but it does not stop App-level priority bindings from firing. So the
App's `show_help` action runs every time, pushing a fresh modal.

The ModalScreen's own `question_mark` binding never gets a chance to
fire because the App-level one already consumed the keystroke.

(This is the documented binding-cascade order; it just doesn't match
the intuitive expectation that "the topmost modal eats keys first".)

## Solution

Collapse the open/close logic into the App-level action method. Check
whether the modal is currently on top; if so, pop it; otherwise push it.
**Do not bind the toggle key on the modal at all.**

```python
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static


class HelpScreen(ModalScreen[None]):
    """No BINDINGS for the toggle key — the App's action handles both
    open and close to avoid the priority-binding-can't-be-dismissed trap."""

    def compose(self) -> ComposeResult:
        yield Static("help content here")


class MyApp(App[None]):
    BINDINGS = [
        Binding("question_mark", "toggle_help", "?", priority=True),
    ]

    async def action_toggle_help(self) -> None:
        # App-level priority bindings fire even when a ModalScreen is on
        # top, so we must toggle here rather than rely on the modal's own
        # dismiss binding.
        if isinstance(self.screen, HelpScreen):
            self.pop_screen()
        else:
            await self.push_screen(HelpScreen())
```

## Verification

Pilot test that the modal toggles cleanly across repeated presses:

```python
import asyncio
from your_module import MyApp

async def run():
    app = MyApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert type(app.screen).__name__ == "Screen"

        await pilot.press("question_mark")
        await pilot.pause()
        assert type(app.screen).__name__ == "HelpScreen"

        await pilot.press("question_mark")
        await pilot.pause()
        assert type(app.screen).__name__ == "Screen", "modal did not dismiss!"

        await pilot.press("question_mark")
        await pilot.pause()
        assert type(app.screen).__name__ == "HelpScreen"

asyncio.run(run())
```

Without the fix, the second `pilot.press("question_mark")` leaves
`app.screen` as `HelpScreen` (modal stacked, not dismissed).

## Notes

- This bites you for ANY single-key toggle bound at the App level with
  priority — `?` for help, `:` for command palette, `Ctrl+P` for
  palette, `Ctrl+\\` for a search bar, etc.
- Multi-key dismissal that doesn't share a key with the App-level
  trigger (e.g. App binds `?` to open, modal binds `Esc` to close)
  works as expected — the conflict is only when the SAME key is bound
  in both places.
- If you must keep the binding on the modal (for documentation purposes,
  to show in the modal's own footer), set `priority=False` on the
  modal's binding — it won't fire anyway, but it documents the key for
  the user.
- Beware: dropping the App-level binding's `priority=True` doesn't fix
  the problem either, because the App-level binding still fires (just
  later in dispatch). The fix is structural — toggle in the action,
  not via two competing bindings.
- Same pattern applies to `App.action_toggle_dark`, sidebar-toggle
  bindings, etc. — anywhere a single key should flip state.

## Example

Real-world fix from recite (a Textual TUI text-to-speech player).
Before — pressing `?` stacked `HelpScreen`s:

```python
class HelpScreen(ModalScreen):
    BINDINGS = [Binding("question_mark", "dismiss_help", "close", priority=True)]
    def action_dismiss_help(self) -> None:
        self.dismiss()

class ReciteApp(App[None]):
    BINDINGS = [
        ...,
        Binding("question_mark", "show_help", "?", priority=True),
    ]
    async def action_show_help(self) -> None:
        await self.push_screen(HelpScreen())
```

Pilot output: `?` × 2 → screen still `HelpScreen`. After the fix
(removed the modal's binding, made the App action toggle):

```python
class HelpScreen(ModalScreen):
    # no toggle binding here
    ...

class ReciteApp(App[None]):
    BINDINGS = [..., Binding("question_mark", "show_help", "?", priority=True)]

    async def action_show_help(self) -> None:
        if isinstance(self.screen, HelpScreen):
            self.pop_screen()
        else:
            await self.push_screen(HelpScreen())
```

Pilot output: `?` × 4 → screen alternates Screen / HelpScreen / Screen / HelpScreen.
Works.

## References

- Textual `Binding` priority docs: <https://textual.textualize.io/guide/input/#bindings>
- Textual `ModalScreen` docs: <https://textual.textualize.io/api/screen/#textual.screen.ModalScreen>
- Verified on Textual 8.2.6 (released 2025).
