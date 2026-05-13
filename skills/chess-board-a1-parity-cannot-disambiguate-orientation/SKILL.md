---
name: chess-board-a1-parity-cannot-disambiguate-orientation
description: |
  Counterintuitive finding: the "a1 is dark" board-colour convention
  cannot be used to infer whether a chess-board screenshot is rendered
  from white's or black's perspective. Use when: (1) you're designing
  an orientation-detection pipeline for screenshot-sourced chess
  positions and someone suggests "sample bottom-left square brightness
  to decide orientation", (2) you're reviewing orientation code that
  looks at corner parity, (3) you're about to spend time implementing
  `a1_parity_vote` or similar. Don't - the diagonal corners a1/h8 share
  a colour and h1/a8 share the opposite, so 180 degree rotation leaves
  corner parity invariant. Real signals for orientation: coordinate
  digit OCR, piece-distribution heuristics, king-rank inference,
  in-board coordinate labels. Covers the geometry, why it fails, and
  what to use instead.
author: Claude Code
version: 1.0.0
date: 2026-04-24
---

# a1-parity cannot tell you which side is white's

## Problem

When building a chess-board orientation detector for screenshots
(Lichess, Chess.com, ChessTempo, etc.), the "a1 must be a dark square"
convention looks like free orientation info. It isn't. A 180 degree
rotation leaves corner parity invariant because the diagonal corners
share a colour, so the same parity holds regardless of which side is
at the bottom. Writing an `a1_parity_vote` is wasted effort.

## Context / Trigger Conditions

- Designing or reviewing a digital-chess-board detection pipeline that
  has to infer board orientation from an image alone.
- Seeing suggestions like "sample bottom-left square mean brightness,
  if dark → white-bottom" or "compare brightness of bottom-left vs
  bottom-right square to decide orientation".
- Orientation heuristic mixes corner-parity-check with coordinate OCR
  and piece-distribution voting.
- Reviewing a multi-vote orientation combine function and someone
  proposes adding a corner-colour voter.
- Bug reports where your orientation heuristic "always agrees with
  piece counting even on puzzles with no pieces" - could be symptom
  of corner-colour voter silently tautological.

## Root cause (geometry)

The chess board has the canonical colouring:

- `a1` is dark (file a = 1, rank = 1, sum 2, even)
- `h1` is light (file h = 8, rank = 1, sum 9, odd)
- `a8` is light (sum 9, odd)
- `h8` is dark (sum 16, even)

Diagonally opposite corners share a colour: `a1`/`h8` dark, `h1`/`a8`
light.

From white's perspective, the bottom-left physical corner of the image
is `a1` (dark) and the bottom-right is `h1` (light).

From black's perspective (board rotated 180 degrees), the bottom-left
physical corner is now `h8` (still dark) and the bottom-right is `a8`
(still light).

Net: "bottom-left corner is dark, bottom-right is light" is true in
**both** orientations. The parity check distinguishes "is this a valid
board image" from "not a board image", but never white-bottom from
black-bottom.

## Solution

Do not implement corner-parity as an orientation voter. Use any
combination of these real signals instead:

1. **Coordinate digit OCR** (rank labels `1`/`8` on the edge). Lichess
   and Chess.com both render these. Authoritative when readable.
2. **Piece-distribution heuristic** - count pieces in top vs bottom
   halves, weighted by colour. Needs ≥6 pieces to be reliable.
3. **King-rank vote** - whichever king sits closer to the bottom row
   tells you the perspective. Works even in sparse endgames where
   piece-distribution is inconclusive.
4. **File letter OCR** (`a`/`h` in the margins) - same idea as rank
   digits but with letters; many sites render these too.
5. **Ask the user** via a flip toggle as a final fallback. Chessvision.ai
   ships exactly this.

If you must use corner sampling for anything, it's as a sanity check
that the crop is actually a chess board (expect alternating squares),
not as an orientation voter.

## Verification

After removing/not implementing the parity voter, your orientation
combine function should produce identical results on a given image
rotated 180 degrees - only the piece / king / label signals should
flip. Add a unit test:

```rust
#[test]
fn rotated_board_flips_orientation_without_parity_noise() {
    let upright = white_bottom_grid();
    let rotated = correct_orientation(&upright); // 180 deg
    let up_vote = combine_signals(detect_labels(&upright), piece_heur(&upright), king_rank_vote(&upright));
    let ro_vote = combine_signals(detect_labels(&rotated), piece_heur(&rotated), king_rank_vote(&rotated));
    assert_eq!(up_vote.0, !ro_vote.0, "orientation vote must invert with rotation");
}
```

## Example

Incident from a session where the agent proposed "add a1-parity as a
third orientation voter alongside labels and pieces". The reasoning
sounded clean: "a1 is always dark, so checking bottom-left square
colour tells us which side is down." Writing the test exposed the
bug: the proposed voter returned the same vote for the original and
180-degree-rotated grid, because both still have a dark square in the
bottom-left corner. Dropped the idea; added `king_rank_vote` instead,
which DID correctly invert on rotation.

## Notes

- Corner parity IS useful for detecting "this is a chess board"
  vs "this is not" (expect alternating squares, 4 dark + 4 light on
  each edge). Don't conflate that with orientation.
- If a board theme paints a1 light (some custom themes / 3D boards
  with dark wood throughout), the parity-as-sanity-check also fails.
  Prefer detecting alternation rather than absolute colour.
- The OCR + piece + king-rank trio already covers the 3-voter case
  elegantly. Adding a fourth invariant voter would dilute confidence
  calculations without adding information.
- This finding applies to any 2D rotation-symmetric pattern, not just
  chess: if your "disambiguation signal" is invariant under the
  transformation you're trying to detect, it can't help you.

## References

- [FEN - Wikipedia (board coordinate system)](https://en.wikipedia.org/wiki/Forsyth%E2%80%93Edwards_Notation)
- [Chess.com: which side has the dark square?](https://www.chessworld.net/chessclubs/chessboardsetup.asp)
- [Chessvision.ai FAQ - manual flip button](https://chessvision.ai/docs/browser-extension/faq/)
