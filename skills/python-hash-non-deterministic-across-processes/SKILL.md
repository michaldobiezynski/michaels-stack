---
name: python-hash-non-deterministic-across-processes
description: |
  Python's built-in hash() is salted with PYTHONHASHSEED which defaults to a
  per-process random value, so hash(x) returns DIFFERENT values across
  separate Python invocations. Use when: (1) building deterministic data
  generators (e.g. random.Random(seed=hash(...)) for fixture generation,
  procedural test data, deterministic PRNGs), (2) seeing duplicate or
  inconsistent entries when re-running a script that should have been
  idempotent, (3) noticing your "deterministic" pipeline produces different
  output across runs but the same output WITHIN a run. The fix is to use a
  string-based seed that doesn't go through hash(): random.Random(f"{a}|{b}")
  works because Random accepts strings directly and uses its own stable hash.
author: Claude Code
version: 1.0.0
date: 2026-04-26
---

# Python `hash()` is non-deterministic across processes

## Problem

You write code that uses `hash()` to derive a deterministic seed:

```python
seed = hash((source_id, idx)) & 0xFFFFFFFF
rng = random.Random(seed)
```

You expect `(source_id, idx)` to always produce the same `seed` and therefore
the same `rng` output. It does — within a single Python process. But across
separate Python invocations (e.g. running the script twice), the seed is
DIFFERENT.

The cause: Python sets `PYTHONHASHSEED` to a random value at interpreter
startup (default since Python 3.3 for hash-flooding DoS protection).
`hash(str)`, `hash(tuple)`, `hash(bytes)`, etc. all incorporate this seed.
Only `hash(int)` is stable across runs (and even then only for in-range
integers).

## Symptoms

- A "regenerate fixtures" / "expand corpus" / "seed dataset" script that you
  run twice produces different output the second time, even with the same
  arguments.
- Idempotency assumptions break: re-running a pipeline produces duplicate
  entries with the same nominal key but different content.
- Test fixtures committed to the repo don't reproduce when CI re-renders
  them from the same source.
- Diff-of-output tests fail with "value mismatch" when nothing in the input
  changed.
- A debug print of `hash(("foo", 2))` shows different numbers in different
  python invocations.

## Solution

Don't pass `hash(...)` to a deterministic PRNG. Use a stable string instead.

```python
# WRONG — non-deterministic across runs
rng = random.Random(hash((source_id, idx)) & 0xFFFFFFFF)

# RIGHT — deterministic
rng = random.Random(f"{source_id}|{idx}")
```

`random.Random` accepts a string and runs its own stable internal hash on it,
NOT the salted `hash()`. Same input string → same internal seed → same
PRNG output across all runs.

For non-Random use cases (e.g. building a deterministic key for a dict),
use a stable hash:

```python
import hashlib
key = hashlib.sha256(f"{a}|{b}".encode()).hexdigest()  # or .digest()[:8] for shorter
```

## Verification

In two separate `python3 -c "..."` invocations, run:

```python
import random
print(random.Random("foo|2").random())  # always 0.6394267984578837
print(hash(("foo", 2)))                 # different number each time
```

The `Random` line is identical across runs; the `hash` line varies.

## Workarounds for cases you can't change

If you must use `hash()` (e.g. third-party API), set `PYTHONHASHSEED` to a
fixed value at process launch:

```bash
PYTHONHASHSEED=0 python3 myscript.py
```

This makes hash() deterministic for the duration of that process. But this
is a process-launch-time setting; you can't change it from inside Python
after startup. CI configs and shebang lines are the right places to set it.

## Notes

- The behaviour is documented in [PEP 456](https://peps.python.org/pep-0456/)
  and [Python docs on `PYTHONHASHSEED`](https://docs.python.org/3/using/cmdline.html#envvar-PYTHONHASHSEED).
- `hash(int)` for small ints IS stable (small ints hash to themselves),
  which is misleading because simple test cases work. The bug shows up
  when you hash strings, tuples, or anything else.
- Detector for this footgun: in any script that's expected to be
  idempotent across runs, grep for `hash(` and ensure any uses are not
  feeding deterministic seeds.
- Distinct from `dict` ordering insertion non-determinism (fixed in 3.7+);
  this is purely about `hash()` output, not iteration order.

## Example: chess corpus expansion in pawn-au-chocolat

Original `expand_positions.py`:

```python
def derive_position(source_placement, source_slug, idx):
    seed = hash((source_slug, idx)) & 0xFFFFFFFF
    rng = random.Random(seed)
    # ... random walk ...
```

Symptom: running `expand_positions.py --per-source 5` after a previous
`--per-source 10` run produced derivative slugs that COLLIDED with existing
slugs but had DIFFERENT placements (because the random walk took a
different path).

Fix:

```python
def derive_position(source_placement, source_slug, idx):
    rng = random.Random(f"{source_slug}|{idx}")
    # ... random walk ...
```

Re-running the script now produces the same placements every time, so
re-runs are truly idempotent and the script can be safely invoked
incrementally.

## References

- [PEP 456 — Secure and interchangeable hash algorithm](https://peps.python.org/pep-0456/)
- [Python docs: PYTHONHASHSEED](https://docs.python.org/3/using/cmdline.html#envvar-PYTHONHASHSEED)
- [Python docs: random.Random](https://docs.python.org/3/library/random.html#random.Random)
