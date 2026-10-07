---
name: github-markdown-repo-to-pdf-book
description: |
  Turn a GitHub docs/notes repo (many chapter READMEs plus local image folders) into a
  single print-ready PDF book with a page-numbered contents list and PDF bookmarks. Use
  when: (1) asked to "make a PDF of all the chapters" of a cloned repo, (2) markdown
  converts but diagrams silently vanish from the output, (3) bullet lists render as one
  run-on paragraph of literal "-" characters, (4) nested 2-space sublists come out flat,
  (5) markdown tables render as plain pipe-separated text, (6) an <img> or <div> tag
  appears as literal escaped text inside a grey code box, (7) you need real page numbers
  in a contents list that a browser print cannot generate, (8) you are considering
  pandoc for a repo whose images are raw <img> HTML. Covers the parser choice that
  prevents all of the above, the pandoc-drops-raw-HTML trap, why optimising source PNGs
  does not shrink a Chrome-printed PDF, and a verified two-pass TOC pipeline.
author: Claude Code
version: 1.0.0
date: 2026-08-13
---

# GitHub markdown repo to PDF book

## Problem

Repos of the form `01. Topic/Readme.md` + `01. Topic/images/*.png` look trivial to
concatenate into a PDF. Every step of the obvious pipeline fails silently: the wrong
markdown parser drops content without erroring, pandoc discards images without warning,
image optimisation does not reduce the PDF, and browsers cannot number a contents list.
Nothing throws, so a broken 350-page book looks finished.

## Context / Trigger conditions

- "Create a PDF from all the chapters in this repo."
- Converted HTML contains `&lt;img` (a diagram rendered as literal text in a code box).
- A `<pre>` block contains prose bullets rather than code.
- The rendered list hierarchy is flat where the source clearly nested it.
- Table count in the output is far below the number of `|---|` rows in the source.

## Solution

### 1. Choose the parser by matching the author's renderer

The author previewed on GitHub, which is CommonMark + GFM. **Use a CommonMark parser**
(`markdown-it-py` with the `gfm-like` preset), not `python-markdown`. In a 28-chapter,
8k-line repo, `python-markdown` (even with `extra` + `sane_lists`) silently produced:

| Defect | python-markdown | markdown-it-py (`gfm-like`) |
| --- | --- | --- |
| 4-space-indented raw `<img>` inside a list | code block, diagram lost (6 lost) | renders |
| List interrupting a paragraph (no blank line) | collapses to run-on prose (232 sites) | renders as list |
| 2-space nested sublists | flattened | nested |
| GFM tables | 13 of 27 parsed | 27 of 27 |

```python
from markdown_it import MarkdownIt
md = MarkdownIt("gfm-like", {"html": True, "linkify": False, "typographer": False})
body = md.render(raw)   # no preprocessing needed
```

`html: True` is mandatory: these repos embed figures as raw
`<div style="margin-left:3rem"><img src="./images/x.png" width="400"></div>`.

Do **not** write preprocessors to patch a non-CommonMark parser (re-indenting HTML lines,
inserting blank lines before lists, reflowing orphaned sublists). All three were written
and all three became unnecessary; the parser swap fixed the same defects and more.

### 2. Never route through pandoc/LaTeX when images are raw HTML

`pandoc -o book.pdf` discards raw HTML blocks when targeting LaTeX, so every
`<img src=...>` disappears and the build still exits 0. A browser engine is the correct
renderer for markdown that contains HTML.

### 3. Render with headless Chrome via puppeteer-core

Use the installed Chrome (`executablePath`), not a 150 MB Chromium download.

- `args: ['--allow-file-access-from-files']` so 300+ `file://` diagrams load.
- `waitUntil: 'networkidle0'` is not sufficient; await `img.decode()` for every image and
  assert `naturalWidth !== 0`, then log broken/failed URLs. This is the only automated
  proof that no diagram is missing.
- Page numbers come from `displayHeaderFooter` + a `footerTemplate` containing
  `<span class="pageNumber"></span>`. Templates ignore page CSS: set font-size and
  padding inline, and they cannot be varied per page.

### 4. Two-pass contents list (browsers cannot number a TOC)

1. Render once with placeholder dots.
2. Recover chapter start pages with `pypdf`, matching the opener text
   (`re.match(r"CHAPTER\s+(\d+)\b", " ".join(page.extract_text().split()))`; CSS
   `text-transform: uppercase` is baked into extracted glyphs).
3. Rebuild the HTML with real numbers and re-render. Offsets do not shift because the
   contents list keeps the same line count between passes.
4. **Verify**: re-derive the page map from the *final* render and diff it against the
   numbers printed in the contents list. Expect zero drift; a non-empty diff means the
   TOC grew a page and needs another pass.

Add bookmarks with `PdfWriter(clone_from=...)` + `add_outline_item(title, page - 1)`.
Take bookmark titles from the source `# ` headings, not from PDF text extraction (a lazy
regex over extracted glyphs truncates them to "1. Scale from").

### 5. Do not bother optimising the source images

Measured on 387 PNGs (83.9 MB):

| Action | Images | Resulting PDF |
| --- | --- | --- |
| baseline | 83.9 MB | 68 MB |
| downscale to 1300px (`sips`) | 81.6 MB | **70 MB (larger)** |
| 256-colour quantise + lossless (PIL) | 52.7 MB | 67 MB (unchanged) |

Chrome re-encodes on embed, so source-side savings do not propagate. Skip this step;
if the user needs a smaller file, post-process the PDF instead.

## Verification

Assert these before reporting done (all cheap, all catch silent failures):

```python
h.count("<img")            # == count of image refs in the markdown
h.count("&lt;img")         # == 0   (diagram rendered as literal text)
re.findall(r'<p>[^<]*\n\s*[-*]\s+\S', h)   # == []  (collapsed lists)
[b for b in pre_blocks if re.match(r'\s*[-*]\s+[A-Z]', b)]  # == []  (prose in code box)
```

Plus: puppeteer reports `broken: []` and `failed: []`; TOC drift is `none`; and probe
that the first/middle/last long line of every chapter appears in the extracted PDF text
(strip list markers and `[text](url)` from probes first, or you get false positives).

Finally **look at the pages** — see `macos-verify-pdf-pages-without-poppler` for the
JXA + `qlmanage` split. Visual review caught the flattened list nesting that every
automated count had passed.

## Example

Full working pipeline for `NN. Chapter Name/README.md` repos is in `scripts/`:

```bash
python build_html.py                    # markdown -> book.html (placeholder TOC)
node   render.js book_pass1.pdf         # pass 1
python extract_pages.py book_pass1.pdf  # -> pagemap.json
python build_html.py pagemap.json       # rebuild with real page numbers
node   render.js book.pdf               # pass 2
python finalise.py out.pdf              # bookmarks, metadata, drift check
```

Result on liquidslr/system-design-notes: 28 chapters, 363 pages, 387 diagrams, 0 broken,
0 TOC drift.

## Notes

- Case-insensitive readme matching is required: such repos mix `Readme.md` and
  `README.md`. A `[Rr]eadme.md` glob silently skips half the chapters.
- Chapter dir names contain spaces and double spaces (`27.  Digital Wallet`); percent-encode
  paths with `urllib.parse.quote` when rewriting `src` to `file://`.
- Sort chapter dirs by `int(re.match(r"(\d+)", name).group(1))`, never lexicographically.
- Author `width="400"` attributes target a wide web column; scale ~1.45x capped at the
  print text block (~650px at A4 with 18mm margins), with `img { max-width: 100% }`.
- Set `break-inside: avoid` on figure wrappers, `break-after: avoid` on headings.
- A clipped diagram may be clipped in the source PNG. Open the source before "fixing" it.
- macOS system fonts that suit a technical book: Charter (body serif), Avenir Next
  (headings), Menlo (code). All present by default; no download needed.
- Verified 13/08/2026 with markdown-it-py 4.x, pypdf 6.15, Chrome 151, Python 3.14.

## References

- CommonMark spec (what GitHub implements): https://spec.commonmark.org/
- `markdown-it-py` presets: the `gfm-like` preset enables tables, strikethrough and HTML
  passthrough; it needs `mdit-py-plugins` and `linkify-it-py` installed.
- Related: `macos-verify-pdf-pages-without-poppler` for visual page verification.
