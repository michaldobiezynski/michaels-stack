---
name: textual-footer-command-palette-overlap
description: |
  Fix for a Textual `Footer` silently clipping the rightmost bindings on
  narrow terminals (80 cols and under). Use when: (1) you flipped some
  `Binding(..., show=True)` to surface more keys, (2) `BINDINGS` count
  looks fine but on an 80-col terminal the last one or two bindings just
  aren't visible, (3) Pilot-driven `app.export_screenshot(size=(80,24))`
  shows the right-edge bindings overlapped by `^p palette`, (4) you
  notice an automated "count <= N" test passing but users report missing
  keys, (5) you're using Textual 0.50+ which docks the command-palette
  hint on the Footer by default. Root cause: Textual's stock `Footer`
  reserves ~12 columns at the right for the `ctrl+p palette` indicator
  and z-order-docks it OVER any binding that would render in that gutter,
  so each binding silently disappears below it as visible-binding count
  grows. There is no truncation glyph and `Footer` is a non-scrollable
  container with `scrollbar-size: 0 0`, so the user has no visual
  indication that content is hidden.
author: Claude Code
version: 1.0.0
date: 2026-05-18
---

# Textual Footer command-palette overlap clips rightmost bindings

## Problem

A Textual app declares N bindings with `show=True`. Each one looks fine
in isolation. But on a real 80-column terminal (the macOS Terminal
default), only the first ~7 of them render: the rest are hidden behind
the command-palette indicator (`^p palette`) that Textual docks at the
right edge of the `Footer` by default. There is no truncation glyph
and no scrollbar (`Footer` has `scrollbar-size: 0 0`), so the missing
bindings are visually invisible and a count-only test (`len(visible) <= N`)
passes while users hit "where did `q` go?".

Concrete trigger: the rightmost binding is the one users instinctively
look for — `q quit` or `?` help — and it's been pushed to a position
that puts it under the palette key.

## Context / Trigger Conditions

All of:

1. **Textual 0.50+** (`from textual.widgets import Footer`). The
   command-palette hint was added in this range and is on by default.
2. **App has 7+ bindings with `show=True`**, or has bindings whose
   labels are long enough that cumulative width exceeds
   `viewport_width - 12 (palette gutter)`.
3. **A test or quick visual check rules out `BINDINGS` being wrong**:
   e.g. `[b for b in App.BINDINGS if b.show]` returns the expected
   N entries but the rendered footer shows fewer.
4. **Repro at 80 cols**:
   ```python
   async with App().run_test(size=(80, 24)) as pilot:
       await pilot.pause()
       screenshot = app.export_screenshot()
       # the rightmost bindings are absent from the bottom row;
       # the bottom-right shows `^p palette` instead
   ```

If the bindings look right at 200 cols but wrong at 80 cols, this is
the issue. If they're wrong at every width, that's a different bug
(probably a missing `Footer()` in `compose()` or a non-priority
binding being swallowed by a screen).

## Solution

Three options, in order of preference:

### 1. Disable the palette indicator entirely (recommended)

```python
def compose(self) -> ComposeResult:
    yield Header()
    # ... main widgets ...
    yield Footer(show_command_palette=False)
```

Recovers ~12 cols on the right. The Ctrl+P palette still works
keyboard-wise (it's a built-in App-level binding); just the
visual hint disappears. For apps that don't lean on the palette,
this is a one-line fix.

### 2. Reduce visible binding count

```python
# Before
BINDINGS = [
    Binding("space", "play_pause", "play/pause", show=True),
    Binding("j,right,n", "next", "next", show=True),
    Binding("k,left,p", "prev", "prev", show=True),
    Binding("v", "cycle_voice", "voice", show=True),
    Binding("plus,equals_sign,equal", "faster", "+wpm", show=True),
    Binding("minus,underscore", "slower", "-wpm", show=True),
    Binding("ctrl+n", "new_text", "new", show=True),
    Binding("question_mark", "show_help", "?", show=True),
    Binding("q,escape", "quit", "quit", show=True),
]

# After: surface rare keys via a `?` help modal instead
BINDINGS = [
    Binding("space", "play_pause", "play/pause", show=True),
    Binding("j,right,n", "next", "next", show=True),
    Binding("k,left,p", "prev", "prev", show=True),
    Binding("ctrl+n", "new_text", "new", show=True),
    Binding("question_mark", "show_help", "?", show=True),
    Binding("q,escape", "quit", "quit", show=True),
    # voice and rate are listed in the help modal
    Binding("v", "cycle_voice", "voice", show=False),
    Binding("plus,equals_sign,equal", "faster", "+wpm", show=False),
    Binding("minus,underscore", "slower", "-wpm", show=False),
]
```

Six visible bindings sit comfortably in 80 cols with the palette
indicator still showing.

### 3. Shorten binding labels

Each binding's display string is the third positional arg to
`Binding(...)`. Trim to single letters where the key glyph is
self-explanatory:

```python
Binding("plus,equals_sign,equal", "faster", "+", show=True),  # was "+wpm"
Binding("minus,underscore", "slower", "-", show=True),        # was "-wpm"
Binding("v", "cycle_voice", "v", show=True),                  # was "voice"
```

Saves ~8 cols of label width. Marginal — option 1 is cleaner.

## Verification

After the fix, add a render-level test that locks the regression:

```python
@pytest.mark.asyncio
async def test_footer_fits_80_cols():
    app = MyApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screenshot = app.export_screenshot()
        # the last binding's label should appear in the screenshot
        assert "quit" in screenshot, (
            "rightmost binding is being clipped by the command-palette "
            "indicator at 80 cols"
        )
```

This is the test the project should have. A `len(visible) <= N`
count check is necessary but not sufficient.

## Example

The recite project (a macOS TUI) declared 9 visible bindings:

```
space play/pause | j right n next | k left p prev | v voice |
+ +wpm | - -wpm | ctrl+n new | ? ? | q escape quit
```

At 80 cols, `app.export_screenshot()` rendered only the first 7;
`?` and `q quit` were hidden under `^p palette`. Fix was
`yield Footer(show_command_palette=False)` in `compose()` —
zero behavioural change, palette key still works, all 9 bindings
visible.

## Notes

- **Why no truncation glyph?** Textual's `Footer` docks bindings as
  individual `Footer.Binding` widgets in a horizontal `Container`. When
  layout overflows, the widgets stay in their declared positions and the
  palette indicator's docking `Right` z-orders it on top. There's no
  overflow check.

- **Why no scrollbar?** `Footer` sets `scrollbar-size: 0 0` in its
  default CSS, so even though the container is technically scrollable,
  the user can't see or interact with the overflowed content.

- **Doesn't `Pilot.snapshot` catch this?** It would, if you wrote one
  at 80 cols. Most projects use `run_test()` with the default
  (~80x24 implicit) but never inspect the rendered screen. Inspect the
  rendered output via `app.export_screenshot()` — it returns the SVG
  string of the visible terminal, easy to grep for binding labels.

- **The `show_command_palette` keyword is on `Footer`, not on `App`.**
  Setting `App.ENABLE_COMMAND_PALETTE = False` disables the feature
  entirely (and is a separate decision); `Footer(show_command_palette=False)`
  just hides the hint while keeping the palette functional.

- **The opposite trap:** at 200 cols everything looks fine, so
  bisecting via manual visual check usually starts wide and misses the
  bug. Always test at 80 cols first.

## References

- Textual `Footer` source: https://github.com/Textualize/textual/blob/main/src/textual/widgets/_footer.py
- Textual command palette docs: https://textual.textualize.io/guide/command_palette/
- Textual `App.export_screenshot`: https://textual.textualize.io/api/app/#textual.app.App.export_screenshot
