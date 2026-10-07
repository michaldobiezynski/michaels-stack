"""Recover each chapter's real start page from a rendered PDF.

Chrome cannot write page numbers into the contents list itself, so the book is
rendered once, the openers are located by their extracted text, and the numbers
are fed back into the second render. The contents list keeps the same length
between passes, so the page offsets do not shift.
"""

import json
import re
import sys
from pathlib import Path

from pypdf import PdfReader

src = Path(sys.argv[1] if len(sys.argv) > 1 else "book_pass1.pdf")
reader = PdfReader(str(src))
found = {}

for i, page in enumerate(reader.pages, start=1):
    text = " ".join(page.extract_text().split())
    m = re.match(r"CHAPTER\s+(\d+)\b", text)
    if m:
        key = f"ch{int(m.group(1)):02d}"
        found.setdefault(key, i)

Path("pagemap.json").write_text(json.dumps(found, indent=1))
order = [found[k] for k in sorted(found)]
print(f"pages: {len(reader.pages)}  chapters located: {len(found)}  "
      f"ascending: {order == sorted(order)}")
missing = [f"ch{n:02d}" for n in range(1, 29) if f"ch{n:02d}" not in found]
if missing:
    print("NOT LOCATED:", missing)
