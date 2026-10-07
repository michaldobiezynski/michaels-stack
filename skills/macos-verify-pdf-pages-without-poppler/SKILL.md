---
name: macos-verify-pdf-pages-without-poppler
description: |
  Visually verify every page of a generated multi-page PDF on macOS when poppler is not
  installed, without changing system state. FIRST try a plain full-file Read with NO pages
  parameter: it renders every page natively for small PDFs (verified up to 6 pages; the
  ~10-page limit forces the pages parameter beyond that). Use this skill's workaround when:
  (1) the Read tool's `pages` parameter fails with "pdftoppm is not installed. Install
  poppler-utils (e.g. `brew install poppler` ...)" and the PDF is too large for a full read,
  (2) qlmanage -t or sips silently render only page 1 of a multi-page PDF, (3) you generated
  a PDF (headless Chrome, drawio export, etc.) and need to check later pages for orphaned
  headers, overflow, or missing content, (4) you want a zero-install HTML-to-PDF path on a
  Mac (no wkhtmltopdf/pandoc/weasyprint). Workaround: split the PDF into single-page PDFs
  via osascript JXA + Quartz PDFDocument, thumbnail each with qlmanage, Read the PNGs.
author: Claude Code
version: 1.1.0
date: 2026-07-12
---

# Verify multi-page PDFs on macOS without poppler

## Problem

Agent sessions on macOS frequently generate PDFs (headless Chrome print, drawio export)
and must verify the result visually before reporting done. Three gotchas stack:

1. The Read tool's `pages` parameter cannot render without poppler and errors with
   `pdftoppm is not installed. Install poppler-utils ...`. A plain full-file Read (no
   `pages`) DOES render every page natively for small PDFs, but PDFs past roughly 10
   pages require `pages`, and installing poppler changes system state just to verify
   output.
2. The obvious built-in fallbacks only show the FIRST page: `qlmanage -t file.pdf` and
   `sips -s format png file.pdf` both silently drop pages 2+. A two-page PDF looks fine
   from page 1 while page 2 is broken.
3. There is no built-in CLI page splitter (`pdfseparate` is poppler; ghostscript is
   usually absent).

## Context / Trigger conditions

- Read tool on a `.pdf` returns the pdftoppm error above.
- You need to see pages beyond page 1 (pagination bugs: orphaned section headers,
  content cut at page break, blank trailing pages).
- `which pdftoppm pdfseparate gs mutool` all come back empty.

## Solution

Step 0: try `Read(file.pdf)` with no `pages` parameter. On small PDFs (verified on 3-,
5- and 6-page files, 12/07/2026) this returns full visual renders of every page with no
poppler, and you are done. Fall through to the split only when the PDF is too large for
a full read or the full read fails.

Otherwise, split the PDF into single-page PDFs using JXA with the Quartz (PDFKit) framework, which
ships with macOS, then thumbnail each page and Read the PNGs:

```bash
cd "$SCRATCHPAD" && osascript -l JavaScript -e '
ObjC.import("Quartz");
const url = $.NSURL.fileURLWithPath("/absolute/path/to/file.pdf");
const doc = $.PDFDocument.alloc.initWithURL(url);
for (let i = 0; i < doc.pageCount; i++) {
  const single = $.PDFDocument.alloc.init;
  single.insertPageAtIndex(doc.pageAtIndex(i), 0);
  single.writeToFile("page-" + (i+1) + ".pdf");
}
"pages: " + doc.pageCount;
'
qlmanage -t -s 1200 -o . page-*.pdf   # emits page-N.pdf.png per page
```

Then Read each `page-N.pdf.png` (the Read tool handles PNGs natively).

Helper: `scripts/pdf-pages-to-png.sh <file.pdf> [outdir] [size]` does both steps.

Related one-liners from the same zero-install pipeline:

- Page count without opening anything: `mdls -name kMDItemNumberOfPages file.pdf`
- Zero-install HTML to PDF (Chrome is near-universal on macOS):
  ```bash
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
    --headless --disable-gpu --no-pdf-header-footer \
    --print-to-pdf=out.pdf "file:///abs/path/page.html"
  ```
- Fixing what verification finds: a section header orphaned at the bottom of a page is
  cured with `section { break-inside: avoid; }` (plus `@page { size: A4; margin: ...; }`
  and `print-color-adjust: exact` for backgrounds) in the print CSS, then re-render.

## Verification

Ran end-to-end on 06/07/2026: a 2-page Chrome-printed A4 PDF split into `page-1.pdf` and
`page-2.pdf`, qlmanage produced both PNGs, Read displayed them, and the page-2 view exposed
an orphaned-header layout bug that `break-inside: avoid` then fixed (confirmed by
re-rendering and re-inspecting both pages).

## Notes

- JXA `PDFDocument.writeToFile` resolves relative paths against the shell cwd; cd to the
  scratchpad first or pass absolute paths.
- `qlmanage -t -s 1200` sets the long-edge pixel size; 1200 is comfortably readable for A4.
- `insertPageAtIndex(page, 0)` into a fresh document is enough; no copy needed, the page
  object can be inserted into another document directly.
- If poppler IS installed, just Read the PDF directly with the `pages` parameter; this
  skill is the no-install fallback.
- Only the `pages` parameter depends on pdftoppm; do not conclude from its error that the
  PDF is unreadable. A same-session full-file Read of the same PDF succeeded right after
  `pages: "4-5"` returned the pdftoppm error (12/07/2026).
- Quick Look can lag on freshly written files; if qlmanage produces no PNG, retry once.
