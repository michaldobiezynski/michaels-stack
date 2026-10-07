---
name: lichess-extension-integration
description: |
  Build Chrome extensions that integrate with Lichess analysis, study, and training pages.
  Use when: (1) building a Chrome extension that needs to read/write chess positions on Lichess,
  (2) needing to make moves on the Lichess analysis board programmatically,
  (3) syncing an external board (3D, physical, etc.) with Lichess position state,
  (4) content script can't access window.lichess (isolated world problem),
  (5) SPA navigation breaks extension state when Lichess updates the URL via pushState,
  (6) needing to detect board orientation, last move, or FEN from Lichess,
  (7) window.lichess.analysis is null on /training pages and FEN extraction fails,
  (8) DOM-based FEN reconstruction from chessground piece elements,
  (9) 3D board shows starting position instead of puzzle position on training page,
  (10) an extension iframe works over a local copy of Lichess but on live lichess.org fails
  with net::ERR_BLOCKED_BY_RESPONSE (frame at chrome-error://chromewebdata/), e.g. after
  adding use_dynamic_url, (11) square.last-move / square.check read stale, hidden or
  reversed squares (chessground 10 pools its marks), (12) #page-init-data is missing on the
  live page, (13) squares read wrong on Lichess's 3D (non-square) board, or whose move it is
  cannot be read because the user turned highlights off, (14) window.lichess is undefined on
  the live site (the global is window.site now), (15) moves made by synthetic clicks, drags or
  keys never reach Lichess's board (chessground and the keyboard-move box drop untrusted
  events), (16) making moves from an extension on the analysis board, a study or a puzzle.
  Covers the 3-layer bridge architecture, the window.site.analysis API (window.lichess before),
  making moves from an MV3 worker (chrome.scripting, MAIN world), why puzzles cannot be moved
  by script, DOM-based fallbacks,
  Lichess's cross-origin isolation, chessground 10's pooled marks, and common pitfalls.
author: Claude Code
version: 2.2.0
date: 2026-10-01
---

# Lichess Chrome Extension Integration

## Problem

Building a Chrome extension that bidirectionally syncs with Lichess's analysis board requires
overcoming isolated world restrictions, understanding Lichess's undocumented client-side API,
and handling SPA navigation without breaking extension state.

## Context / Trigger Conditions

- Building any Chrome extension that interacts with Lichess board state
- Content script needs to access `window.site.analysis` (fails due to isolated world)
- `window.lichess` is undefined on the live site (renamed `window.site`)
- Synthetic clicks or drags on Lichess's board do nothing; a puzzle cannot be moved from the extension
- Extension loses state or deactivates when user makes moves (URL changes via pushState)
- Need to programmatically make moves on Lichess analysis board
- Need to read current FEN, last move, or board orientation from Lichess
- 3D/custom board shows starting position instead of puzzle position on `/training`
- `window.site.analysis` returns null/false on training pages

## Solution

### 1. Three-Layer Bridge Architecture

Content scripts run in an isolated world and CANNOT access `window.site` (formerly `window.lichess`). You need three layers:

```
Your UI (iframe/popup)  <--postMessage-->  Content Script (isolated world)  <--postMessage-->  Page Bridge (main world)
                                                                                                    ↕
                                                                                          window.site.analysis
```

**Page Bridge**: Inject a script into the main world via `document.createElement('script')`:

```javascript
// content.js
function injectPageBridge() {
  const script = document.createElement('script');
  script.src = chrome.runtime.getURL('page-bridge.js');
  script.onload = () => script.remove();
  (document.head || document.documentElement).appendChild(script);
}
```

The page-bridge.js file MUST be in `web_accessible_resources` in manifest.json:

```json
"web_accessible_resources": [{
  "resources": ["page-bridge.js"],
  "matches": ["*://*.lichess.org/*"]
}]
```

### 2. Lichess Analysis API (window.site.analysis)

**The global is `window.site` now; `window.lichess` is undefined on the live site** (seen 30/09 and
01/10/2026). Older extensions and write-ups use `window.lichess.analysis`, and their bridges find
nothing there. `window.site.analysis.playUci(uci)` was verified live on 01/10/2026 by making a
move on the analysis board; the other members below (`navigate`, `node`, `chessground`) are carried
over from the `window.lichess` era and were not re-checked under `site`.

**CRITICAL: Only available on `/analysis` and `/study/*` pages. NOT available on `/training`.**

On training/puzzle pages the global has no `analysis` object (re-checked under `window.site`,
01/10/2026); under the old name it held only utility keys:
`initializeDom`, `events`, `socket`, `onlineFriends`, `chat`, `dialog`, `overrides`.
There is NO `analysis` object and NO `puzzle` object exposed to JavaScript.

```javascript
// Make moves (UCI format - only works on /analysis and /study)
window.site.analysis.playUci('e2e4')      // Regular move
window.site.analysis.playUci('e7e8q')     // Promotion

// Navigation
window.site.analysis.navigate.next()
window.site.analysis.navigate.prev()
window.site.analysis.navigate.first()
window.site.analysis.navigate.last()

// Read state
window.site.analysis.node.fen              // Current FEN
window.site.analysis.node.uci              // Last move in UCI
window.site.analysis.chessground.state.lastMove    // ['e2', 'e4']
window.site.analysis.chessground.state.orientation  // 'white' | 'black'
```

### 3. DOM-Based FEN Extraction (Training/Puzzle Fallback)

When `window.site.analysis` is unavailable (training pages), reconstruct the FEN from
chessground's DOM piece elements:

```javascript
function getFenFromDOM() {
  const cgBoard = document.querySelector('cg-board');
  if (!cgBoard) return null;

  const pieces = cgBoard.querySelectorAll('piece');
  if (pieces.length === 0) return null;

  const cgWrap = cgBoard.closest('.cg-wrap');
  const isFlipped = cgWrap && cgWrap.classList.contains('orientation-black');

  const boardRect = cgBoard.getBoundingClientRect();
  const squareSize = boardRect.width / 8;
  if (squareSize <= 0) return null;

  const board = Array.from({ length: 8 }, () => Array(8).fill(null));
  const pieceMap = { pawn: 'p', knight: 'n', bishop: 'b', rook: 'r', queen: 'q', king: 'k' };

  for (const piece of pieces) {
    // MUST skip animated, fading, ghost, and dragged pieces
    if (piece.classList.contains('ghost') || piece.classList.contains('dragging') ||
        piece.classList.contains('anim') || piece.classList.contains('fading')) continue;

    const style = piece.getAttribute('style') || '';
    const match = style.match(/translate\((\d+(?:\.\d+)?)px\s*,\s*(\d+(?:\.\d+)?)px\)/);
    if (!match) continue;

    let fileIdx = Math.round(parseFloat(match[1]) / squareSize);
    let rankIdx = Math.round(parseFloat(match[2]) / squareSize);
    if (fileIdx < 0 || fileIdx > 7 || rankIdx < 0 || rankIdx > 7) continue;

    // Flip coordinates for black orientation
    if (isFlipped) {
      fileIdx = 7 - fileIdx;
      rankIdx = 7 - rankIdx;
    }

    const classes = Array.from(piece.classList);
    const isWhite = classes.includes('white');
    let type = null;
    for (const cls of classes) {
      if (pieceMap[cls]) { type = pieceMap[cls]; break; }
    }
    if (!type) continue;

    board[rankIdx][fileIdx] = isWhite ? type.toUpperCase() : type;
  }

  // Build FEN rows (rankIdx 0 = rank 8 = top of board)
  const rows = [];
  for (let r = 0; r < 8; r++) {
    let row = '';
    let empty = 0;
    for (let f = 0; f < 8; f++) {
      if (board[r][f]) {
        if (empty > 0) { row += empty; empty = 0; }
        row += board[r][f];
      } else { empty++; }
    }
    if (empty > 0) row += empty;
    rows.push(row);
  }

  // Infer castling from king/rook starting squares
  let castling = '';
  if (board[7][4] === 'K') {
    if (board[7][7] === 'R') castling += 'K';
    if (board[7][0] === 'R') castling += 'Q';
  }
  if (board[0][4] === 'k') {
    if (board[0][7] === 'r') castling += 'k';
    if (board[0][0] === 'r') castling += 'q';
  }
  if (!castling) castling = '-';

  return rows.join('/') + ' w ' + castling + ' - 0 1';
}
```

**Key details:**
- Chessground positions pieces via `transform: translate(Xpx, Ypx)` on inline styles
- Square size = `boardRect.width / 8` (typically 77px for a 616px board)
- For white orientation: x=0 is file a, y=0 is rank 8
- For black orientation: coordinates are inverted (x=0 is file h, y=0 is rank 1)
- `getAttribute('style')` returns the target position even during CSS transitions

**Piece classes to ALWAYS filter:**
- `ghost` — placeholder during drag
- `dragging` — piece being dragged by user
- `anim` — piece mid-animation (has offset position via chessground animation system)
- `fading` — captured piece fading out

### 4. DOM-Based Last Move Detection

When the analysis API is unavailable, read highlighted squares:

```javascript
function getLastMoveFromDOM() {
  const cgBoard = document.querySelector('cg-board');
  if (!cgBoard) return null;

  const squares = cgBoard.querySelectorAll('square.last-move');
  if (squares.length < 2) return null;

  // Same pixel-to-square conversion as getFenFromDOM()
  // Note: DOM order of square elements may not match from/to order
}
```

### 5. FEN Metadata Mismatch (Critical for chess.js Integration)

DOM-extracted FEN has approximate metadata (turn, castling inferred heuristically).
When comparing DOM FEN against chess.js internal FEN, the metadata parts will differ.

**Problem:** A 3-part FEN comparison (pieces + turn + castling) fails because DOM says
`w -` while chess.js says `b KQkq`, even though pieces match. This breaks animated
move detection (`findSingleMoveTo`) and causes full board rebuilds every poll cycle.

**Solution:** Use piece-placement-only comparison as a fallback:

```javascript
const currentPieces = chess.fen().split(' ')[0];  // Just piece placement
const newPieces = incomingFen.split(' ')[0];

if (currentPieces === newPieces) {
  // Same position, just metadata differs — skip rebuild
  return;
}

// Try 3-part comparison first for move detection
let move = findSingleMoveTo(chess.fen(), incomingFen);

// If that fails (metadata mismatch), normalise and retry
if (!move) {
  const normalised = newPieces + ' ' + chess.fen().split(' ').slice(1).join(' ');
  move = findSingleMoveTo(chess.fen(), normalised);
}

// Final fallback: full board rebuild
if (!move) {
  chess.load(incomingFen);
  rebuildBoard();
}
```

### 6. Position Polling (Page Bridge)

Poll at 150ms intervals from the page bridge, posting changes to the content script:

```javascript
setInterval(() => {
  const fen = getCurrentFen();  // Tries API first, then DOM fallback
  if (fen && fen !== lastKnownFen) {
    lastKnownFen = fen;
    window.postMessage({ type: 'my-ext-position', fen, ... }, '*');
  }
}, 150);
```

### 7. SPA Navigation Pitfall (CRITICAL)

**Bug**: Using `MutationObserver` on `document.body` to detect URL changes will fire on
EVERY DOM mutation, not just navigation. Lichess updates the URL with `pushState` after
every move (appending FEN to `/analysis/standard/...`). This causes the observer to detect
a "navigation" and tear down extension state.

**Fix**: Compare only the base path, not the full URL:

```javascript
let lastPathBase = location.pathname.split('/').slice(0, 2).join('/');
const observer = new MutationObserver(() => {
  if (location.href !== lastUrl) {
    lastUrl = location.href;
    const newBase = location.pathname.split('/').slice(0, 2).join('/');
    // Only react when base path changes: /analysis -> /play
    // NOT when FEN changes: /analysis -> /analysis/standard/fen...
    if (newBase !== lastPathBase) {
      lastPathBase = newBase;
      handleNavigation();
    }
  }
});
```

### 8. Analysis Mode: Both Sides Can Move

In analysis mode, both colours can move freely. If your board uses chess.js for validation,
you must bypass turn enforcement:

```javascript
// Show valid moves for either colour
const piece = chess.get(square);
if (piece && piece.color !== chess.turn()) {
  const fen = chess.fen();
  const parts = fen.split(' ');
  parts[1] = piece.color; // Flip turn temporarily
  const temp = new Chess(parts.join(' '));
  moves = temp.moves({ square, verbose: true });
}
```

### 9. Preventing Desync After Own Moves

When your extension makes a move via `playUci`, the position poll will detect the change
and try to update your board again (causing a flash/rebuild). Track pending moves:

```javascript
let pendingMoveUci = null;

// When making a move
pendingMoveUci = 'e2e4';
sendToBridge('playMove', { uci: pendingMoveUci });

// When poll detects position change
if (pendingMoveUci) {
  // This is our own move - skip full rebuild, just update highlights
  pendingMoveUci = null;
} else {
  // External change - full position update
  updateBoard(newFen);
}
```

### 10. State Reset on Navigation and Deactivation

When navigating between pages or deactivating the extension, reset ALL state:

```javascript
function resetState() {
  bridgeReady = false;
  iframeReady = false;
  initSyncDone = false;
  hasPlayUci = false;  // MUST reset — stale true from /analysis breaks /training
  clearPendingMove();
}
```

### 11. Reading Chessground 10 Reliably (verified on live lichess.org, 30/09/2026)

- **Pooled square marks.** Chessground 10 never removes a `square` mark it no longer needs:
  it hides it (`style.display = 'none'`, class and transform kept) and reuses a hidden one of
  the same class later. `querySelectorAll('square.last-move')` therefore returns stale marks
  too: skip `el.style.display === 'none'`. A last-move square a piece could take on can carry
  a compound class (`last-move move-dest oc`) while the plain `last-move` element for that
  square sits hidden.
- **Last-move order.** The two last-move marks come in no reliable order. Order them by
  occupancy: the square the move reached holds a piece, the one it left is empty (a castling
  king's origin too). A swapped pair breaks en passant and anything keyed on `from`.
- **Non-square boards.** Lichess's 3D board setting draws a board shorter than it is wide.
  Use `getBoundingClientRect()` width and height separately: file from `x / (width / 8)`,
  rank from `y / (height / 8)`.
- **Highlights off.** With the "highlight last move and check" preference off there are no
  last-move or check marks, so whose move it is cannot be read off the board. Treat it as
  unknown and compare piece placement only (a legal move that reaches the placement settles
  it) rather than guessing white.
- **The analysis address.** `/analysis/<fen, spaces as underscores>` carries the side to move.
  Decode the path first (`decodeURIComponent` in a try/catch: a malformed escape throws).
- **Boot data is gone.** Lichess removes `#page-init-data` as its page script boots, before a
  content script at `document_idle` runs. Tell the page's kind from marks that outlast boot:
  the `main` element's classes (`analyse`, `round`, `puzzle`, `tv-single`), the
  `variant-<key>` class (on `main` for analysis, on `.round__app` for games), the address (a
  12-character player id is the visitor's own game, 8 characters a watched one), and
  `.rcontrols` (the player's round controls).

### 12. Framing an Extension Page into Lichess (verified live, Chromium 153, 30/09/2026)

- Lichess's pages are **cross-origin isolated in Chrome**: `Cross-Origin-Embedder-Policy:
  credentialless` (TV, analysis) and `Cross-Origin-Opener-Policy: same-origin`. The header
  varies by client: curl gets `require-corp` on /analysis and /training and nothing on /tv.
  Read the headers from a real browser (Playwright `response.headers()`), not curl.
- A content script's iframe of a web-accessible extension page at the **fixed**
  `chrome-extension://<id>/` address loads under that isolation (and under Lichess's CSP meta,
  whose `frame-src` does not name `chrome-extension:`).
- With `"use_dynamic_url": true` the per-session address is **blocked**:
  `net::ERR_BLOCKED_BY_RESPONSE`, the frame lands on `chrome-error://chromewebdata/`. Giving
  the extension pages their own `cross_origin_embedder_policy` in the manifest does not help.
  To keep a per-install ID out of the page (an unpacked extension's ID derives from its
  folder's path, often with the user's name in it), put a public `key` in the manifest
  instead: every install then shares one ID.
- **Test stand-ins must carry the isolation.** Playwright stand-ins for lichess.org
  (`context.route(...)` + `route.fulfill`) served without COEP/COOP let a `use_dynamic_url`
  build pass offline and fail live. Serve them with
  `headers: { 'Cross-Origin-Embedder-Policy': 'credentialless', 'Cross-Origin-Opener-Policy': 'same-origin' }`.
- Chrome stops drawing a hidden cross-origin frame: an overlay held at `visibility: hidden`
  until its scene is ready never becomes ready. Hold it at `opacity: 0` instead.

### 13. Making Moves: What Lichess Accepts (verified live, 01/10/2026)

**Synthetic input is ignored.** chessground returns early from a pointer event unless it is
trusted: `if (!(s.trustAllEvents || e.isTrusted)) return` (`drag.ts`), and Lichess's
keyboard-move box ignores untrusted keys too. `dispatchEvent` clicks, drags and key presses
from a content script or a page script are all untrusted, so they never move a piece. An old
extension that 'clicks' a puzzle move fails silently: its move simply never arrives.

**Analysis board and studies: call the controller in the page's own world.** In MV3 the clean
route is a worker running the call with `chrome.scripting.executeScript`, on the content
script's request:

```javascript
// background.js (manifest: "background": {"service_worker": "background.js"},
// "permissions": ["scripting"], "host_permissions": ["https://lichess.org/*"])
chrome.runtime.onMessage.addListener((request, sender, reply) => {
  const tabId = sender.tab?.id
  // Only a well-formed move, only from a lichess.org tab.
  if (request?.type !== 'play' || !/^[a-h][1-8][a-h][1-8][qrbn]?$/.test(request.uci)
      || tabId === undefined || !sender.url?.startsWith('https://lichess.org/')) return false
  chrome.scripting.executeScript({
    target: { tabId, frameIds: [sender.frameId ?? 0] },
    world: 'MAIN',
    func: (uci) => {
      const analysis = window.site?.analysis
      if (typeof analysis?.playUci !== 'function') return false
      analysis.playUci(uci)
      return true
    },
    args: [request.uci],
  }).then(([done]) => reply(done?.result === true), () => reply(false))
  return true // reply asynchronously
})

// content script
chrome.runtime.sendMessage({ type: 'play', uci: 'e7e8q' })
```

Lichess then shows the move on its own board, so a mirror that follows Lichess's position
sees it come back, a beat late (the worker hop plus chessground's slide). A mirror that
plays the move itself should give Lichess a while to show it (the Chess Explosion extension
waits up to 1.5 s) before taking Lichess's unchanged position as 'move not taken'; stepping
back at once rewinds and replays a move Lichess did take.

**Puzzles (`/training`): there is no supported way to move by script.** No controller is
published, and untrusted input is dropped. What worked: let the visitor move on Lichess's
own board. When it is their turn and the mirror has finished animating, fade the overlay out
(`opacity: 0; pointer-events: none`), and fade it back on the next position Lichess shows.
Settle the solver's colour once per puzzle (by its URL), not from the board's orientation each
time, or flipping the board breaks the hand-over. Generating trusted input (for example
`chrome.debugger` with CDP `Input.dispatchMouseEvent`) defeats the protection Lichess put there
on purpose. An attempt at it was refused by Claude Code's automated safety check
(01/10/2026), so don't use it.

**Live games: never make moves from the extension** (fair play; Lichess's rules).

## Verification

- Extension loads on lichess.org/analysis without errors
- 3D/custom board shows correct position matching Lichess
- Making moves on custom board triggers `playUci` and Lichess updates (PGN, opening book, engine)
- Arrow key navigation on Lichess updates custom board
- **Training page shows puzzle position, NOT starting position**
- Making multiple moves for both sides doesn't deactivate the extension
- Navigating away from /analysis and back works correctly

## Lichess DOM Reference

| Element | Selector | Purpose |
|---------|----------|---------|
| Board | `cg-board` | Main board element (Chessground) |
| Board wrapper | `.cg-wrap` | Container with orientation class |
| Orientation | `.cg-wrap.orientation-black` | Board flipped for black |
| Pieces | `cg-board piece` | Individual pieces with classes like `white king` |
| Piece position | `piece { transform: translate(Xpx, Ypx) }` | CSS positioning |
| Ghost piece | `piece.ghost` | Placeholder shown during drag |
| Animating piece | `piece.anim` | Piece mid-move animation (offset position!) |
| Fading piece | `piece.fading` | Captured piece fading out |
| Last move squares | `square.last-move` | Highlighted from/to squares (pooled: skip `display: none` ones; order by occupancy) |
| Page kind | `main.analyse` / `main.round` / `main.puzzle` / `.tv-single` / `.rcontrols` | `#page-init-data` is removed at boot |
| Variant | `.variant-<key>` on `main` (analysis) or `.round__app` (games) | Standard only: `variant-standard` |
| FEN display | Input with FEN-like value | Below the board (analysis only) |
| Move list | `.analyse__moves`, `.tview2` | Clickable move tree |

## Lichess API Availability by Page

| Page | `window.site.analysis` | `playUci` | FEN source |
|------|---------------------------|-----------|------------|
| `/analysis` | Yes | Yes | API: `analysis.node.fen` |
| `/study/*` | Yes | Yes | API: `analysis.node.fen` |
| `/training` | **NO** | **NO** | DOM piece extraction only |
| `/tv`, `/game` | No | No | DOM piece extraction only |

## Notes

- `window.site.analysis` may not be available immediately on page load; poll for it
- The `playUci` function is not officially documented but is stable and widely used
- Lichess is open source (github.com/lichess-org/lila) — check source for API changes
- Puzzle pages cannot be moved by script: DOM event simulation (`mousedown`/`mouseup`) is
  dropped by chessground's `isTrusted` check (section 13)
- DOM-extracted FEN lacks accurate turn/castling/en-passant — use piece-placement-only
  comparison when integrating with chess.js
- chess.js v1.4.0 only records en passant square when capture is actually possible,
  unlike Lichess which always records it — use 3-part FEN comparison (parts 0-2) to
  avoid false mismatches, or piece-placement-only (part 0) for DOM-extracted FEN
- `getAttribute('style')` returns the target position even during CSS transitions,
  but pieces with the `anim` class have their transform offset by chessground's
  animation system — always filter these out

## References

- [Lichess Source (lila)](https://github.com/lichess-org/lila)
- [Chessground Library](https://github.com/lichess-org/chessground)
- [Chessground drag.ts (the isTrusted check)](https://github.com/lichess-org/chessground/blob/master/src/drag.ts)
- [Chrome: chrome.scripting (executeScript, world MAIN)](https://developer.chrome.com/docs/extensions/reference/api/scripting)
- [Chessground render.ts (piece classes)](https://github.com/lichess-org/chessground/blob/master/src/render.ts)
- [Chessground util.ts (posToTranslate)](https://github.com/lichess-org/chessground/blob/master/src/util.ts)
- [Chrome MV3: Content Script Isolated World](https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts#isolated_world)
- [Chrome: web_accessible_resources (use_dynamic_url)](https://developer.chrome.com/docs/extensions/reference/manifest/web-accessible-resources)
- [Chrome: manifest key](https://developer.chrome.com/docs/extensions/reference/manifest/key)
- See also the `chrome-extension-development` skill, Part 13 (use_dynamic_url and framed extension pages).
