#!/usr/bin/env python3
"""Which files changed since BASE can each HTML page reach through its imports?

usage: reach.py REPO BASE PAGE.html [PAGE.html ...]

Reads the working tree (check out the branch's tip first). Follows relative imports from each page's
<script src="/..."> entry: `import ... from`, `export ... from`, `import('...')` and bare `import '...'`,
resolving .ts/.tsx/.js/.jsx/.mjs and index files. Package imports are not followed (they did not change);
path aliases (`@/x`) are not resolved, so add them to ALIASES if the repo uses them.
"""
import os, re, subprocess, sys

ALIASES = {}  # e.g. {'@/': 'src/'}
IMPORT = re.compile(r"""(?:import|export)\s[^'"]*?from\s*['"]([^'"]+)['"]|import\s*\(\s*['"]([^'"]+)['"]\s*\)|import\s*['"]([^'"]+)['"]""")
EXTS = ('', '.ts', '.tsx', '.js', '.jsx', '.mjs', '/index.ts', '/index.tsx', '/index.js')

def resolve(repo, importer, spec):
    for alias, target in ALIASES.items():
        if spec.startswith(alias):
            spec, base = target + spec[len(alias):], ''
            break
    else:
        if not spec.startswith('.'):
            return None
        base = os.path.dirname(importer)
    path = os.path.normpath(os.path.join(base, spec))
    for ext in EXTS:
        if os.path.isfile(os.path.join(repo, path + ext)):
            return path + ext
    return None

def reach(repo, entry):
    seen, stack = set(), [entry]
    while stack:
        f = stack.pop()
        if f in seen:
            continue
        seen.add(f)
        if not re.search(r'\.(m?js|jsx|ts|tsx)$', f):
            continue
        for m in IMPORT.finditer(open(os.path.join(repo, f), encoding='utf-8').read()):
            r = resolve(repo, f, next(g for g in m.groups() if g))
            if r:
                stack.append(r)
    return seen

def main():
    repo, base, pages = sys.argv[1], sys.argv[2], sys.argv[3:]
    diff = subprocess.run(['git', '-C', repo, 'diff', '--name-only', f'{base}...HEAD'], capture_output=True, text=True, check=True)
    changed = set(diff.stdout.split())
    for page in pages:
        html = open(os.path.join(repo, page), encoding='utf-8').read()
        entries = [s.lstrip('/') for s in re.findall(r'<script[^>]*\bsrc="(/[^"]+)"', html)]
        reached = set().union(*(reach(repo, e) for e in entries)) if entries else set()
        hit = sorted(reached & changed)
        print(f"{page}: {len(reached)} modules from {entries}; changed among them: {hit if hit else 'none'}")

if __name__ == '__main__':
    main()
