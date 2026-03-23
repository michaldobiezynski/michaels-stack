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
  (9) 3D board shows starting position instead of puzzle position on training page.
  Covers the 3-layer bridge architecture, window.lichess.analysis API, DOM-based fallbacks,
  and common pitfalls.
author: Claude Code
version: 2.0.0
date: 2026-02-24
---

# Lichess Chrome Extension Integration

## Problem

Building a Chrome extension that bidirectionally syncs with Lichess's analysis board requires
overcoming isolated world restrictions, understanding Lichess's undocumented client-side API,
and handling SPA navigation without breaking extension state.

## Context / Trigger Conditions

- Building any Chrome extension that interacts with Lichess board state
- Content script needs to access `window.lichess.analysis` (fails due to isolated world)
- Extension loses state or deactivates when user makes moves (URL changes via pushState)
- Need to programmatically make moves on Lichess analysis board
- Need to read current FEN, last move, or board orientation from Lichess
- 3D/custom board shows starting position instead of puzzle position on `/training`
- `window.lichess.analysis` returns null/false on training pages

## Solution

### 1. Three-Layer Bridge Architecture

Content scripts run in an isolated world and CANNOT access `window.lichess`. You need three layers:

```
Your UI (iframe/popup)  <--postMessage-->  Content Script (isolated world)  <--postMessage-->  Page Bridge (main world)
                                                                                                    ↕
                                                                                          window.lichess.analysis
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

### 2. Lichess Analysis API (window.lichess.analysis)

**CRITICAL: Only available on `/analysis` and `/study/*` pages. NOT available on `/training`.**

On training/puzzle pages, `window.lichess` only contains utility keys:
`initializeDom`, `events`, `socket`, `onlineFriends`, `chat`, `dialog`, `overrides`.
There is NO `analysis` object and NO `puzzle` object exposed to JavaScript.

```javascript
// Make moves (UCI format - only works on /analysis and /study)
window.lichess.analysis.playUci('e2e4')      // Regular move
window.lichess.analysis.playUci('e7e8q')     // Promotion

// Navigation
window.lichess.analysis.navigate.next()
window.lichess.analysis.navigate.prev()
window.lichess.analysis.navigate.first()
window.lichess.analysis.navigate.last()

// Read state
window.lichess.analysis.node.fen              // Current FEN
window.lichess.analysis.node.uci              // Last move in UCI
window.lichess.analysis.chessground.state.lastMove    // ['e2', 'e4']
window.lichess.analysis.chessground.state.orientation  // 'white' | 'black'
```

### 3. DOM-Based FEN Extraction (Training/Puzzle Fallback)

When `window.lichess.analysis` is unavailable (training pages), reconstruct the FEN from
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
| Last move squares | `square.last-move` | Highlighted from/to squares |
| FEN display | Input with FEN-like value | Below the board (analysis only) |
| Move list | `.analyse__moves`, `.tview2` | Clickable move tree |

## Lichess API Availability by Page

| Page | `window.lichess.analysis` | `playUci` | FEN source |
|------|---------------------------|-----------|------------|
| `/analysis` | Yes | Yes | API: `analysis.node.fen` |
| `/study/*` | Yes | Yes | API: `analysis.node.fen` |
| `/training` | **NO** | **NO** | DOM piece extraction only |
| `/tv`, `/game` | No | No | DOM piece extraction only |

## Notes

- `window.lichess.analysis` may not be available immediately on page load; poll for it
- The `playUci` function is not officially documented but is stable and widely used
- Lichess is open source (github.com/lichess-org/lila) — check source for API changes
- For puzzle pages, move-making falls back to DOM event simulation (`mousedown`/`mouseup`)
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
- [Chessground render.ts (piece classes)](https://github.com/lichess-org/chessground/blob/master/src/render.ts)
- [Chessground util.ts (posToTranslate)](https://github.com/lichess-org/chessground/blob/master/src/util.ts)
- [Chrome MV3: Content Script Isolated World](https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts#isolated_world)
