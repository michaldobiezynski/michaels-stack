"""Add PDF bookmarks and metadata, then verify the finished book.

Verification is the point of this script: it re-derives chapter start pages
from the final render and checks them against the numbers printed in the
contents list, so a stale or shifted TOC cannot ship silently.
"""

import json
import re
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter

SRC = Path("book.pdf")
DEST = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("system-design-notes.pdf")

reader = PdfReader(str(SRC))
pages = len(reader.pages)

# Re-derive openers from the FINAL render, not the pass-1 map.
actual = {}
for i, page in enumerate(reader.pages, start=1):
    m = re.match(r"CHAPTER\s+(\d+)\b", " ".join(page.extract_text().split()))
    if m:
        actual.setdefault(f"ch{int(m.group(1)):02d}", i)

# Bookmark labels come from the source headings, not from extracted glyphs.
titles = {}
for d in Path("system-design-notes").iterdir():
    if not (d.is_dir() and re.match(r"\d+\.", d.name)):
        continue
    md = next(p for p in d.iterdir() if p.name.lower() == "readme.md")
    h1 = re.search(r"^#\s+(.+)$", md.read_text(encoding="utf-8"), re.M)
    num = int(re.match(r"(\d+)", d.name).group(1))
    raw = h1.group(1).strip() if h1 else d.name
    titles[f"ch{num:02d}"] = re.sub(r"^Chapter\s+\d+\s*:\s*", "", raw).strip()

claimed = json.loads(Path("pagemap.json").read_text())
drift = {k: (claimed.get(k), v) for k, v in actual.items() if claimed.get(k) != v}

writer = PdfWriter(clone_from=str(SRC))
writer.add_outline_item("Title Page", 0)
writer.add_outline_item("Contents", 1)
for key in sorted(actual):
    writer.add_outline_item(f"{int(key[2:])}. {titles[key]}", actual[key] - 1)

writer.add_metadata({
    "/Title": "System Design Notes - An Insider's Guide, Volumes 1 & 2",
    "/Author": "liquidslr (github.com/liquidslr/system-design-notes)",
    "/Subject": "Condensed notes on System Design Interview by Alex Xu, 28 chapters",
    "/Keywords": "system design, distributed systems, scalability, interview",
    "/Creator": "headless Chrome + python-markdown",
})
with DEST.open("wb") as fh:
    writer.write(fh)

links = sum(
    1
    for p in PdfReader(str(DEST)).pages
    for a in (p.get("/Annots") or [])
    if a.get_object().get("/Subtype") == "/Link"
)
print(json.dumps({
    "output": str(DEST),
    "size_mb": round(DEST.stat().st_size / 1e6, 1),
    "pages": pages,
    "chapters_bookmarked": len(actual),
    "toc_page_number_drift": drift or "none",
    "link_annotations": links,
    "first_pages": {k: actual[k] for k in sorted(actual)[:4]},
}, indent=2))
