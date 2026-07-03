---
name: textual-widget-content-pure-builder-test
description: |
  Fix for Pilot tests on a Textual TUI failing with
  `AttributeError: 'Static' object has no attribute 'renderable'. Did you mean: 'render_line'?`
  (or equivalent for Label, Header, Footer, etc.) when trying to read what the
  app's `widget.update(some_string)` call wrote. Use when: (1) writing
  `pytest-asyncio` Pilot tests for a Textual app, (2) you want to assert on
  the current status line / hint / label content without rendering pixels,
  (3) `widget.renderable`, `widget.render_str()`, or `widget._content` all
  feel like reaching into private API and break between Textual versions,
  (4) the assertion uses a string-shaped fact (e.g. "the time clock reads
  `MM:SS / MM:SS` when playing") and faking it via `widget.render()` returns
  a Rich `RenderableType` you'd have to stringify yourself. The fix is to
  refactor the side-effecting `_refresh_X()` method into a pure
  `_build_X_text() -> str` plus a tiny wrapper that calls `widget.update(...)`,
  then have tests call the pure method directly. Survives Textual API
  renames because tests never touch widgets. Verified against Textual 8.2.6;
  applies to all 0.x and current 8.x where `Static.renderable` is gone (or
  has moved between reactive-attribute and method form repeatedly across
  the 0.x line).
author: Claude Code
version: 1.0.0
date: 2026-05-18
---

# Pure-builder pattern for testing Textual widget content

## Problem

Pilot tests want to assert on what a Textual widget is displaying. The
ergonomic-looking option is to read it off the widget after the app's
own `_refresh_status()` (or similar) has updated it:

```python
async def test_status_says_playing(app):
    async with app.run_test() as pilot:
        await pilot.pause()
        app.is_playing = True
        app._refresh_status()
        await pilot.pause()
        text = str(app.query_one("#status", Static).renderable)
        assert "▶ playing" in text
```

This breaks with `AttributeError: 'Static' object has no attribute
'renderable'. Did you mean: 'render_line'?` on current Textual. The
`renderable` reactive attribute that older docs reference is gone (or
renamed); the substitutes (`render()`, `render_line(...)`, `_content`,
`_renderable`) are private, version-fragile, or return a Rich
`RenderableType` rather than a plain string. Working around inside
each test is awkward and brittle.

## Context / Trigger Conditions

All of:

1. **Textual TUI** (`from textual.app import App`) under test with
   `pytest-asyncio` + `async with app.run_test() as pilot`.
2. App composes a `Static`, `Label`, `Header`, `Footer`, or similar
   content widget and updates it via `widget.update(some_string)` from
   a method like `_refresh_status()`, `_refresh_hint()`, etc.
3. A test tries to read that content back and hits one of:
   - `AttributeError: 'Static' object has no attribute 'renderable'`
   - `'NoneType' object has no attribute ...` from `widget._content`
   - A `rich.text.Text` / `RenderableType` from `widget.render()` that
     needs further coaxing to string-compare.
4. The assertion you actually want is shape-of-string ("contains
   `▶ playing`", "matches `\d\d:\d\d / \d\d:\d\d`"), not a pixel diff.

If the test instead wants to assert *rendering* (colour, layout, screen
position), this skill does not apply — use Textual's `app.screen` /
`Pilot.snapshot` instead.

## Solution

Refactor the side-effecting update method into two:

```python
# recite/app.py — before
def _refresh_status(self) -> None:
    bits = []
    if self.is_playing:
        bits.append("▶ playing")
    bits.append(f"{self.current_idx + 1} / {len(self.sentences)}")
    bits.append(f"voice: {self.voices[self.voice_idx]}")
    try:
        self.query_one("#status", Static).update(" · ".join(bits))
    except Exception:
        pass


# recite/app.py — after
def _build_status_text(self) -> str:
    """Compose the status line. Pure: no widget access. Unit-testable."""
    bits = []
    if self.is_playing:
        bits.append("▶ playing")
    bits.append(f"{self.current_idx + 1} / {len(self.sentences)}")
    bits.append(f"voice: {self.voices[self.voice_idx]}")
    return " · ".join(bits)


def _refresh_status(self) -> None:
    try:
        self.query_one("#status", Static).update(self._build_status_text())
    except Exception:
        pass
```

Tests then assert against the pure builder:

```python
@pytest.mark.asyncio
async def test_status_says_playing():
    app = ReciteApp(sentences=["hello"], voice="Daniel", rate=0)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.is_playing = True
        status = app._build_status_text()
    assert "▶ playing" in status
```

No `query_one`, no `Static.renderable`, no `render()` -> string dance.
Tests don't depend on Textual's widget storage at all.

### Generalises to any update-string widget

Same pattern works for hint lines, headers, footers, labels. For each
`widget.update(x)` call:

1. Move composition of `x` into a `_build_<name>_text() -> str`.
2. Have `_refresh_<name>()` call it: `widget.update(self._build_<name>_text())`.
3. Tests assert against `app._build_<name>_text()`.

### Live-update hooks stay in the side-effecting method

Pure builders MUST stay pure (no `query_one`, no widget mutation).
Anything that needs to *trigger* a refresh (e.g. `on_text_area_changed`)
calls `_refresh_<name>()`, not the builder. The builder only reads state
that's already on `self`.

## Verification

After the refactor:

1. Run the failing test — should now pass (it calls the builder, no
   `renderable` access).
2. Run the existing Pilot tests that drive the app normally — they
   should still pass, because the `_refresh_*()` wrapper still calls
   `widget.update(...)` as before.
3. Manually run the TUI — visible status / hint should look unchanged.

If any of those break, the builder probably has a hidden side effect
(`self.foo = ...`, `query_one(...).update(...)`, etc.). Strip them out:
the builder should be callable repeatedly with no observable change to
anything except its own return value.

## Example

A complete before/after for a paste screen's live char/word counter:

```python
# Before — only mutable via the widget
class PasteApp(App[str | None]):
    def compose(self) -> ComposeResult:
        yield Static("paste below — Ctrl+S to start", id="hint")
        yield TextArea(id="paste-area")

    def on_text_area_changed(self, event):
        text = self.query_one(TextArea).text
        chars = len(text)
        words = len(text.split())
        self.query_one("#hint", Static).update(
            f"{chars} chars · {words} words" if text.strip()
            else "paste below — Ctrl+S to start"
        )

# After — pure builder + wrapper
class PasteApp(App[str | None]):
    def compose(self) -> ComposeResult:
        yield Static(self._build_hint_text(), id="hint")
        yield TextArea(id="paste-area")

    def on_text_area_changed(self, event):
        self._refresh_hint()

    def _current_text(self) -> str:
        try:
            return self.query_one(TextArea).text
        except Exception:
            return ""

    def _build_hint_text(self) -> str:
        text = self._current_text()
        if not text.strip():
            return "paste below — Ctrl+S to start"
        chars = len(text)
        words = len(text.split())
        return f"{chars} chars · {words} words"

    def _refresh_hint(self) -> None:
        try:
            self.query_one("#hint", Static).update(self._build_hint_text())
        except Exception:
            pass
```

Test:

```python
@pytest.mark.asyncio
async def test_hint_reports_word_count():
    app = PasteApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.query_one(TextArea).text = "one two three"
        await pilot.pause()
        for _ in range(5):
            await pilot.pause()
        hint = app._build_hint_text()
    assert "3 words" in hint
```

Note `_current_text()` is the only impure bit (it reads from the
TextArea). Wrapping it in try/except means the builder is still safe to
call before the widget tree mounts — useful for the initial `compose()`
call, which runs before `query_one` works reliably.

## Notes

- **Why not `widget.render()`?** It returns a Rich `RenderableType`
  (often `Text` or `str`). On a `Static` with plain string content it
  *does* round-trip, but on a Label or Header it may return a styled
  `Text`. Stringifying it works, but the resulting string includes Rich
  markup escape characters that complicate `assert "▶ playing" in s`.
  Pure builders give plain `str` always.

- **Why not `widget._content`?** Underscored, undocumented, has been
  renamed across Textual minor versions. Tests built on it break on
  every upgrade.

- **The `try/except Exception` in the wrapper** isn't laziness — it
  guards against `query_one` raising during `compose()` (before the
  widget tree is mounted) and during `on_unmount` (after it's gone).
  Both are real scenarios for status-line refreshes triggered by
  reactive state changes.

- **Footer/Header are special.** Textual's `Footer` widget renders
  bindings declared in `BINDINGS` automatically — there's no
  `footer.update(...)` to refactor. Test the bindings list directly:
  `[b for b in App.BINDINGS if b.show]`. Same for the title bar:
  `app.title`, `app.sub_title` are plain `str` reactives, readable
  with no widget-API gymnastics.

- **This pattern doesn't help when you genuinely need to test
  rendering** (e.g. "is this text bold?", "is the cursor on the right
  word?"). For that, use `app.screen.render()` and inspect Rich segments,
  or use Textual's `Pilot.snapshot` for image diffing.

## References

- Textual `Static` widget source (8.x): https://github.com/Textualize/textual/blob/main/src/textual/widgets/_static.py
- Textual Pilot testing docs: https://textual.textualize.io/guide/testing/
- Textual changelog (notes the `renderable` reactive removal): https://github.com/Textualize/textual/blob/main/CHANGELOG.md
