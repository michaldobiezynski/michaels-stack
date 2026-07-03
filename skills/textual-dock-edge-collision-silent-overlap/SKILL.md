---
name: textual-dock-edge-collision-silent-overlap
description: |
  Latent Textual layout trap: two widgets both with `dock: top` (or both
  `dock: bottom`, `dock: left`, `dock: right`) silently overlap at the
  same screen region and one disappears, with no error or warning.
  Classic symptoms: (1) a status line / hint widget never visibly
  renders even though `widget.render()` returns the correct content,
  (2) `widget.region` shows it at the same row/column as the framework
  widget (e.g. Header at y=0 with your `#hint` also at y=0), (3) the
  Footer or Header z-orders on top of your custom docked widget,
  (4) the bug is invisible until you inspect with
  `app.export_screenshot()` and compare widget regions. Use when: (a)
  you've added `dock: top` to a custom Static / Label widget and it
  never appears, (b) you've added `dock: bottom` to a status line and
  the Footer covers it, (c) you can confirm the widget is mounted and
  has correct content via `widget.render()` but it's not in the
  rendered SVG output, (d) widget overlap is confirmed by both
  `header.region` and `your_widget.region` reporting the same Region
  coordinates. Fix: drop the `dock:` rule from your custom widget. The
  Header/Footer keep their docked rows; your widget flows naturally
  between the docked elements and the flex container above/below.
  `height: 1fr` containers shrink to make room.
author: Claude Code
version: 1.0.0
date: 2026-05-18
---

# Textual dock-edge collision silently hides widgets

## Problem

You add a custom Static (or Label, or any widget) and give it
`dock: top` / `dock: bottom` so it sits along an edge of the screen.
The framework's `Header` already docks to `top` and the `Footer`
already docks to `bottom`. Both your widget and the framework
widget claim the same Region; one z-orders over the other; the
loser silently disappears.

The bug is invisible from Pilot tests that just exercise behaviour
(`render()` returns the right text, `update()` was called, the
widget reports `visible=True`), so it can ship undetected.

## Context / Trigger Conditions

All of:

1. **Textual app** has a custom widget in `compose()` with
   `dock: top` or `dock: bottom` in its CSS, AND yields a `Header`
   or `Footer` widget.
2. **The custom widget never appears on screen** at the runtime
   user's terminal, even though:
   - `widget.render()` returns the correct content
   - `widget.visible` is `True`
   - `widget.display` is `True`
   - The widget is mounted (no `NoMatches` exception)
3. **`widget.region` and `Header.region` (or `Footer.region`)
   report the same `Region`**, e.g.:
   ```
   Header region: Region(x=0, y=0, width=100, height=1)
   Hint region:   Region(x=0, y=0, width=100, height=1)
   ```
   or
   ```
   Status region: Region(x=0, y=23, width=100, height=1)
   Footer region: Region(x=0, y=23, width=100, height=1)
   ```
4. **`app.export_screenshot()` shows the framework widget (Header
   or Footer) rendering at that row; your widget is absent.**

## Solution

Drop the `dock:` rule from the custom widget's CSS. Let it flow
naturally in the layout between the docked Header/Footer and the
flex container (`height: 1fr`) above or below.

```python
# Before (bug):
class MyApp(App):
    CSS = """
    #status {
        dock: bottom;       # <- collides with Footer's dock
        height: 1;
        padding: 0 2;
        background: $boost;
    }
    """
    def compose(self):
        yield Header()
        with VerticalScroll(id="content"):
            ...
        yield Static("", id="status")    # docked bottom, hidden by Footer
        yield Footer()                   # also docked bottom, wins

# After (fix):
class MyApp(App):
    CSS = """
    #status {
        height: 1;        # no dock rule
        padding: 0 2;
        background: $boost;
    }
    """
    def compose(self):
        yield Header()
        with VerticalScroll(id="content"):
            ...
        yield Static("", id="status")    # flows naturally above Footer
        yield Footer()                   # docks bottom
```

The `VerticalScroll` (`height: 1fr`) shrinks to make room for the
`height: 1` Static, the Footer keeps its docked row, the Static
sits in the gap between them. Same pattern for the top edge with
Header and a custom hint widget.

## Verification

Empirical: spot the bug AND confirm the fix via Pilot.

```python
@pytest.mark.asyncio
async def test_status_does_not_collide_with_footer():
    app = MyApp()
    async with app.run_test(size=(100, 24)) as pilot:
        await pilot.pause()
        status = app.query_one("#status", Static)
        footer = app.query_one(Footer)
        assert status.region != footer.region, (
            f"status and footer both claim {status.region}, "
            "Footer will z-order over status"
        )
```

Confirm via screenshot at a real terminal size:

```python
svg = app.export_screenshot(size=(100, 24))
import re
from collections import defaultdict
rows = defaultdict(list)
for m in re.finditer(r'<text[^>]*y="([\d.]+)"[^>]*>([^<]+)</text>', svg):
    rows[float(m.group(1))].append(m.group(2))
for y in sorted(rows.keys())[-5:]:
    content = ''.join(rows[y])[:120].replace('&#160;', ' ')
    print(f'y={y}: {content!r}')
```

After the fix, the status text and the footer text appear at
different `y` values.

## Example

A real recurrence: `recite` (macOS TUI) had `#status` with
`dock: bottom` in CSS. The framework Footer also docks bottom.
At runtime users saw the Footer but never the status line.
Diagnostic walk:

1. `widget.render()` returned the correct text. So content was fine.
2. `widget.visible == True`. Mounting was fine.
3. `Header region:` and `Footer region:` AND `Status region:`
   inspection showed `Status region: Region(x=0, y=23, ...)` and
   `Footer region: Region(x=0, y=23, ...)`. Same row.
4. The Footer rendered on top, hiding the status.

Fix was one CSS rule deleted:

```diff
 #status {
-    dock: bottom;
     height: 1;
     padding: 0 2;
     background: $boost;
     color: $text;
 }
```

After the fix, `Status region: Region(x=0, y=22, ...)` and
`Footer region: Region(x=0, y=23, ...)`. Different rows.

## Notes

- **Why does Textual not warn?** Two `dock: bottom` widgets is a
  legal layout in Textual's CSS. The framework places them in
  compose order; later-yielded widgets stack on top. There's no
  "you probably didn't mean this" heuristic.

- **Why the framework wins, not your widget**: in our reproduction
  the Footer (yielded last) ended up on top of the Static (yielded
  earlier). If you yield your docked widget LAST, it may end up
  covering the Header / Footer, which is usually worse: the user
  loses keyboard hints. Either way the collision is wrong; the fix
  is to not collide.

- **`dock` is a stylesheet rule, not a Python keyword.** It lives in
  the widget's `DEFAULT_CSS` or the App's `CSS` string. Grep for
  `dock:` in your CSS strings before suspecting a deeper bug.

- **Related anti-pattern**: docking a Container that holds your
  custom widget alongside the framework Footer / Header. Same
  collision, same fix.

- **Pilot tests that don't catch this**: behavioural Pilot tests
  exercise `app.action_X()` or key presses and don't inspect the
  rendered SVG. They pass because state transitions are correct.
  Add a `export_screenshot` round-trip and a `region != ` assertion
  to catch the layout bug.

- **The companion skill `textual-footer-command-palette-overlap`**
  is a narrower instance of the same family: there it's not
  another docked widget but the Footer's own command-palette
  indicator overlapping the rightmost Footer.Binding. The pattern
  ("Textual widgets at the same screen region silently overlap")
  is the same.

## References

- Textual `dock` styles docs: https://textual.textualize.io/styles/dock/
- Textual layout guide: https://textual.textualize.io/guide/layout/
- `App.export_screenshot`: https://textual.textualize.io/api/app/#textual.app.App.export_screenshot
