"""Flag generated artefact sections that are still template scaffold.

Structural validators (schema/lint/required-files checks) cannot tell a filled section
from a scaffold stub, so an artefact whose generation stage died after scaffolding but
before filling validates cleanly, ships, and is consumed as garbage. This checks
SUBSTANCE: after stripping generator metadata blocks and headings, a real section
carries prose AND numerals; a stub carries neither.

Adapt CELL / STUB / the glob patterns to your generator's template, then wire this into
whatever function actually ships the artefact so it REFUSES rather than warns.

Usage:
    check_generated_content.py <artefact_dir> [<artefact_dir> ...]
    check_generated_content.py --all --root <dir>

Prints one JSON line per flagged artefact; exits 1 if any stub section is found.
"""
import argparse, glob, json, os, re, sys

# --- adapt these three to your template -------------------------------------------
# Generator metadata blocks to strip before judging (HTML comments, front-matter, ...).
CELL = re.compile(r"<!--\s*(?:trackio-cell|template-cell).*?-->", re.S)

# The generator's OWN boilerplate strings.
# TRAP 1: scaffolds often use typographic dashes ("3–5"), so match the dash
#   permissively ("3.5") — an ASCII-hyphen-only pattern silently passes an empty page.
# TRAP 2: do NOT add bare TODO/PLACEHOLDER. It false-positives on legitimate prose
#   ("the id is a placeholder-format id") and pressures agents into rewording correct
#   content to satisfy the gate.
STUB = re.compile(
    r"Document setup, runs, and results for"
    r"|Write a 3.5 sentence outcome-first summary"
    r"|Summarise the .* outcome here"
    r"|Build a .* poster with"
    r"|replace this cell with"
    r"|_?Replace this with",
    re.I)

# Sections that repeat per item (numeric evidence expected) vs narrative sections.
# Discovery walks the tree rather than globbing, for two reasons: the artefact root is
# rarely the direct parent of the sections (real layout was
# <id>/.trackio/logbook/pages/claim-N/page.md), and — the trap — Python's glob wildcards
# do NOT match hidden directories, so "**/claim-*/page.md" silently returns nothing when
# any path component starts with a dot.
ITEM_DIR_PREFIX = "claim-"          # per-item section directories start with this
SECTION_FILE = "page.md"            # the file inside each section directory
NARRATIVE_NAMES = ("executive-summary", "conclusion")
# ----------------------------------------------------------------------------------

NUM = re.compile(r"\d")
MIN_PROSE = 400   # chars of real body after stripping metadata/headings
MIN_NUMS = 8      # numerals expected in a section that reports measurements
MIN_NARRATIVE = 150


def section_body(path):
    txt = open(path, encoding="utf-8", errors="replace").read()
    txt = CELL.sub("", txt)
    txt = re.sub(r"^#\s.*$", "", txt, flags=re.M)      # headings
    txt = re.sub(r"^-{3,}\s*$", "", txt, flags=re.M)   # rules
    return txt.strip()


def find_sections(adir, item_prefix=ITEM_DIR_PREFIX):
    """Walk adir and return (item_section_files, narrative_section_files)."""
    items, narrative = [], []
    for root, _dirs, files in os.walk(adir):
        if SECTION_FILE not in files:
            continue
        section = os.path.basename(root)
        path = os.path.join(root, SECTION_FILE)
        if section.startswith(item_prefix):
            items.append(path)
        elif section in NARRATIVE_NAMES:
            narrative.append(path)
    return sorted(items), sorted(narrative)


def check(adir, item_prefix=ITEM_DIR_PREFIX):
    name = os.path.basename(adir.rstrip("/"))
    items, narrative = find_sections(adir, item_prefix)
    if not items and not narrative:
        return {"artefact": name, "ok": False, "reason": "no sections found"}

    stubs, thin = [], []
    for p in items:
        b, sec = section_body(p), os.path.basename(os.path.dirname(p))
        if STUB.search(b) or len(b) < 120:
            stubs.append(sec)
        elif len(b) < MIN_PROSE or len(NUM.findall(b)) < MIN_NUMS:
            thin.append(sec)
    for p in narrative:
        b, sec = section_body(p), os.path.basename(os.path.dirname(p))
        if STUB.search(b) or len(b) < MIN_NARRATIVE:
            stubs.append(sec)

    return {"artefact": name, "ok": not stubs, "n_item_sections": len(items),
            "stub_sections": stubs, "thin_sections": thin}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--root", default=".")
    ap.add_argument("--item-prefix", default=ITEM_DIR_PREFIX,
                    help="per-item section directories start with this (default: claim-)")
    a = ap.parse_args()

    if a.all:
        dirs = sorted(d for d in glob.glob(os.path.join(a.root, "*"))
                      if os.path.isdir(d) and any(find_sections(d, a.item_prefix)))
    else:
        dirs = a.dirs
    if not dirs:
        print("no artefact directories matched", file=sys.stderr)
        sys.exit(2)

    bad = 0
    for d in dirs:
        r = check(d, a.item_prefix)
        if not r["ok"] or r.get("thin_sections"):
            print(json.dumps(r))
        if not r["ok"]:
            bad += 1
    print(json.dumps({"checked": len(dirs), "artefacts_with_stub_sections": bad}))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
