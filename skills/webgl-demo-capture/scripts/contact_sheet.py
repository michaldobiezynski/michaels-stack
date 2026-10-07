#!/usr/bin/env python3
"""Lay out rows of labelled image pairs (before/after, ours/theirs) on one dark sheet.

Usage: contact_sheet.py OUT.png "Label|a.png|b.png" ["Label|c.png|d.png" ...]
A row may name one image or several; each is scaled to the same cell size.
"""
import sys

from PIL import Image, ImageDraw, ImageFont

CELL_W, CELL_H, PAD, LABEL_H = 640, 400, 12, 34


def font():
    for path in ("/System/Library/Fonts/Supplemental/Georgia.ttf", "/Library/Fonts/Arial.ttf"):
        try:
            return ImageFont.truetype(path, 22)
        except OSError:
            continue
    return ImageFont.load_default()


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    out, rows = sys.argv[1], [r.split("|") for r in sys.argv[2:]]
    cols = max(len(r) - 1 for r in rows)
    sheet = Image.new("RGB", (cols * CELL_W + (cols + 1) * PAD, len(rows) * (CELL_H + LABEL_H + PAD) + PAD), (18, 14, 11))
    draw, face = ImageDraw.Draw(sheet), font()
    for i, (label, *paths) in enumerate(rows):
        y = PAD + i * (CELL_H + LABEL_H + PAD)
        draw.text((PAD, y + 4), label, fill=(229, 217, 191), font=face)
        for j, path in enumerate(paths):
            image = Image.open(path).convert("RGB").resize((CELL_W, CELL_H), Image.LANCZOS)
            sheet.paste(image, (PAD + j * (CELL_W + PAD), y + LABEL_H))
    sheet.save(out)
    print(f"{out} {sheet.size[0]}x{sheet.size[1]}")


if __name__ == "__main__":
    main()
