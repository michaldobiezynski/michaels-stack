"""Build a single print-ready HTML book from the system-design-notes repo.

Pass 1 emits placeholder dots in the contents list; pass 2 re-runs with a
{chapter_key: page_number} map recovered from the pass-1 PDF.
"""

import html
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

from markdown_it import MarkdownIt

REPO = Path(__file__).parent / "system-design-notes"
OUT = Path(__file__).parent / "book.html"

# Author markup sizes figures with width="400"-style attributes intended for a
# ~900px web column. On a 174mm print column those read small, so scale up but
# never past the text block (650px) or the source resolution.
FIG_SCALE = 1.45
FIG_MAX_PX = 650

CSS = """
:root {
  --ink: #14181d;
  --ink-soft: #4a545f;
  --accent: #0d4f5c;
  --accent-warm: #b5551f;
  --rule: #d4d9de;
  --code-bg: #f4f2ed;
}
@page { size: A4; margin: 20mm 18mm 18mm 18mm; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body {
  font-family: "Charter", "Georgia", serif;
  font-size: 10.6pt;
  line-height: 1.52;
  color: var(--ink);
  margin: 0;
  text-rendering: optimizeLegibility;
}
h1, h2, h3, h4, h5 {
  font-family: "Avenir Next", "Helvetica Neue", sans-serif;
  color: var(--accent);
  line-height: 1.2;
  break-after: avoid;
  page-break-after: avoid;
}
h1 { font-size: 21pt; font-weight: 600; letter-spacing: -0.01em; margin: 0 0 1.4rem; }
h2 {
  font-size: 14pt; font-weight: 600; margin: 1.9rem 0 0.7rem;
  padding-bottom: 0.28rem; border-bottom: 1.5px solid var(--rule);
}
h3 { font-size: 11.6pt; font-weight: 600; margin: 1.35rem 0 0.45rem; color: var(--ink); }
h4 { font-size: 10.6pt; font-weight: 600; margin: 1rem 0 0.35rem; color: var(--accent-warm); }
p { margin: 0 0 0.72rem; orphans: 2; widows: 2; }
ul, ol { margin: 0 0 0.72rem; padding-left: 1.4rem; }
li { margin-bottom: 0.22rem; }
li > ul, li > ol { margin-top: 0.22rem; }
li > p { margin: 0 0 0.3rem; }
li > p:last-child { margin-bottom: 0; }
strong { font-weight: 700; color: #0a0d11; }
a { color: var(--accent); text-decoration: none; }
code {
  font-family: "Menlo", monospace; font-size: 0.85em;
  background: var(--code-bg); padding: 0.08em 0.32em; border-radius: 3px;
}
pre {
  background: var(--code-bg); border-left: 3px solid var(--accent);
  padding: 0.7rem 0.9rem; overflow-x: hidden; border-radius: 3px;
  break-inside: avoid; page-break-inside: avoid; margin: 0 0 0.9rem;
}
pre code { background: none; padding: 0; font-size: 8.4pt; line-height: 1.42; white-space: pre-wrap; }
blockquote {
  margin: 0 0 0.9rem; padding: 0.15rem 0 0.15rem 0.9rem;
  border-left: 3px solid var(--accent-warm); color: var(--ink-soft);
}
table {
  border-collapse: collapse; width: 100%; margin: 0.4rem 0 1rem;
  font-size: 9.2pt; break-inside: avoid; page-break-inside: avoid;
}
th {
  background: var(--accent); color: #fff; text-align: left;
  font-family: "Avenir Next", sans-serif; font-weight: 600;
  padding: 0.36rem 0.5rem; font-size: 8.8pt;
}
td { border-bottom: 1px solid var(--rule); padding: 0.34rem 0.5rem; vertical-align: top; }
tr:nth-child(even) td { background: #faf9f6; }
hr { border: none; border-top: 1px solid var(--rule); margin: 1.5rem 0; }

/* Figures: the source wraps images in indented divs; centre them instead. */
img { max-width: 100%; height: auto; display: block; margin: 0 auto; }
div[style*="margin-left"], div[style*="margin-Left"] {
  margin-left: 0 !important; text-align: center;
}
p:has(> img), div:has(> img) {
  break-inside: avoid; page-break-inside: avoid;
  margin: 1rem auto 1.15rem; text-align: center;
}

/* Front matter */
.title-page {
  height: 247mm; display: flex; flex-direction: column; justify-content: center;
  break-after: page; page-break-after: always; text-align: left;
}
.title-rule { height: 6px; background: var(--accent); width: 78px; margin-bottom: 2.2rem; }
.title-page h1 {
  font-size: 40pt; line-height: 1.06; letter-spacing: -0.025em;
  margin: 0 0 1rem; color: var(--ink);
}
.title-page .sub {
  font-family: "Avenir Next", sans-serif; font-size: 13pt; font-weight: 500;
  color: var(--accent); margin-bottom: 2.6rem;
}
.title-page .meta {
  font-family: "Avenir Next", sans-serif; font-size: 9.5pt; color: var(--ink-soft);
  line-height: 1.9; border-top: 1px solid var(--rule); padding-top: 1.1rem;
}
.title-page .meta b { color: var(--ink); font-weight: 600; }

.toc { break-after: page; page-break-after: always; }
.toc h1 { font-size: 24pt; margin-bottom: 1.6rem; }
.toc ol { list-style: none; padding: 0; margin: 0; }
.toc li { margin: 0; padding: 0.42rem 0; border-bottom: 1px dotted var(--rule); }
.toc a { display: flex; align-items: baseline; gap: 0.5rem; color: var(--ink); }
.toc .num {
  font-family: "Avenir Next", sans-serif; font-size: 9pt; font-weight: 600;
  color: var(--accent); min-width: 2.1rem;
}
.toc .name { flex: 1; font-size: 10.4pt; }
.toc .page {
  font-family: "Avenir Next", sans-serif; font-size: 9pt; color: var(--ink-soft);
}

/* Chapter openers */
.chapter { break-before: page; page-break-before: always; }
.chapter-label {
  font-family: "Avenir Next", sans-serif; font-size: 8.6pt; font-weight: 600;
  letter-spacing: 0.16em; text-transform: uppercase; color: var(--accent-warm);
  margin-bottom: 0.5rem;
}
.chapter > h1 { padding-bottom: 0.9rem; border-bottom: 3px solid var(--accent); }
"""

FOOTNOTE = (
    "Notes compiled from the open-source repository "
    '<b>github.com/liquidslr/system-design-notes</b>, which summarises '
    "<i>System Design Interview: An Insider's Guide</i> (Vol. 1 &amp; 2) by Alex Xu."
)


def natural_key(path: Path) -> int:
    return int(re.match(r"(\d+)", path.name).group(1))


def find_chapters():
    dirs = sorted(
        (d for d in REPO.iterdir() if d.is_dir() and re.match(r"\d+\.", d.name)),
        key=natural_key,
    )
    chapters = []
    for d in dirs:
        md = next((p for p in d.iterdir() if p.name.lower() == "readme.md"), None)
        if md is None:
            print(f"WARN: no readme in {d.name}", file=sys.stderr)
            continue
        chapters.append((natural_key(d), d, md))
    return chapters


def scale_widths(html_text: str) -> str:
    def repl(m):
        w = int(m.group(1))
        return f'width="{min(int(w * FIG_SCALE), FIG_MAX_PX)}"'

    return re.sub(r'width="(\d+)"', repl, html_text)


def rewrite_images(html_text: str, chapter_dir: Path, missing: list) -> str:
    def repl(m):
        prefix, src, suffix = m.group(1), m.group(2), m.group(3)
        if src.startswith(("http://", "https://", "data:", "file://")):
            return m.group(0)
        target = (chapter_dir / src.lstrip("./")).resolve()
        if not target.exists():
            missing.append(f"{chapter_dir.name} -> {src}")
            return m.group(0)
        return f"{prefix}file://{quote(str(target))}{suffix}"

    return re.sub(r'(<img[^>]*?src=")([^"]+)(")', repl, html_text)


def build(page_map: dict) -> tuple:
    md = MarkdownIt("gfm-like", {"html": True, "linkify": False, "typographer": False})
    chapters = find_chapters()
    missing, bodies, toc_rows = [], [], []
    figures = 0

    for num, cdir, mdfile in chapters:
        raw = mdfile.read_text(encoding="utf-8")
        first_h1 = re.search(r"^#\s+(.+)$", raw, re.M)
        full_title = first_h1.group(1).strip() if first_h1 else cdir.name
        title = re.sub(r"^Chapter\s+\d+\s*:\s*", "", full_title).strip()
        raw = re.sub(r"^#\s+.+$", "", raw, count=1, flags=re.M)
        body = md.render(raw)
        body = scale_widths(body)
        body = rewrite_images(body, cdir, missing)
        figures += body.count("<img")

        anchor = f"ch{num:02d}"
        bodies.append(
            f'<section class="chapter" id="{anchor}">'
            f'<div class="chapter-label">Chapter {num}</div>'
            f"<h1>{html.escape(title)}</h1>\n{body}\n</section>"
        )
        page = page_map.get(anchor)
        toc_rows.append(
            f'<li><a href="#{anchor}"><span class="num">{num:02d}</span>'
            f'<span class="name">{html.escape(title)}</span>'
            f'<span class="page">{page if page else "&middot;&middot;"}</span></a></li>'
        )

    doc = f"""<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8">
<title>System Design Notes</title><style>{CSS}</style></head><body>
<div class="title-page">
  <div class="title-rule"></div>
  <h1>System Design<br>Notes</h1>
  <div class="sub">An Insider's Guide &middot; Volumes 1 &amp; 2, condensed</div>
  <div class="meta">
    <b>{len(chapters)} chapters</b> &middot; {figures} diagrams<br>
    {FOOTNOTE}
  </div>
</div>
<div class="toc"><h1>Contents</h1><ol>{"".join(toc_rows)}</ol></div>
{"".join(bodies)}
</body></html>"""

    OUT.write_text(doc, encoding="utf-8")
    return chapters, missing, figures


if __name__ == "__main__":
    pmap = {}
    if len(sys.argv) > 1 and Path(sys.argv[1]).exists():
        pmap = json.loads(Path(sys.argv[1]).read_text())
    chs, miss, figs = build(pmap)
    print(f"chapters: {len(chs)}  figures: {figs}  "
          f"html: {OUT.stat().st_size / 1024:.0f} KB  toc pages resolved: {len(pmap)}")
    if miss:
        print(f"MISSING IMAGES ({len(miss)}):")
        for m in miss:
            print("  ", m)
    else:
        print("all image references resolved on disk")
