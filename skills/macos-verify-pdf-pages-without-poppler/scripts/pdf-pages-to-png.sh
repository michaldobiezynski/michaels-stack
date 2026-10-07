#!/bin/bash
# Render every page of a PDF to PNG on macOS with no poppler/ghostscript,
# using Quartz PDFKit (via JXA) to split pages and qlmanage to rasterise.
# Usage: pdf-pages-to-png.sh <file.pdf> [outdir] [size]
set -euo pipefail

pdf="${1:?usage: pdf-pages-to-png.sh <file.pdf> [outdir] [size]}"
outdir="${2:-.}"
size="${3:-1200}"

pdf="$(cd "$(dirname "$pdf")" && pwd)/$(basename "$pdf")"
mkdir -p "$outdir"
cd "$outdir"

pages=$(osascript -l JavaScript -e '
ObjC.import("Quartz");
const doc = $.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath("'"$pdf"'"));
for (let i = 0; i < doc.pageCount; i++) {
  const single = $.PDFDocument.alloc.init;
  single.insertPageAtIndex(doc.pageAtIndex(i), 0);
  single.writeToFile("page-" + (i + 1) + ".pdf");
}
doc.pageCount;
')

qlmanage -t -s "$size" -o . page-*.pdf >/dev/null 2>&1

echo "rendered $pages page(s):"
ls -1 "$PWD"/page-*.pdf.png
