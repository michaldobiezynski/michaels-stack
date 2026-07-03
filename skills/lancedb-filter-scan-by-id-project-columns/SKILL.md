---
name: lancedb-filter-scan-by-id-project-columns
description: |
  Fetch LanceDB rows by an exact id list (metadata filter, no vector search)
  efficiently and safely. Use when: (1) you need a "get rows where id IN (...)"
  hydration helper against a LanceDB table; (2) a LanceDB filter query silently
  returns only ~10 rows (the default search limit); (3) a by-id / where-only
  scan is ~2x slower than expected because it materialises a large embedding
  column you immediately discard; (4) ids contain ':' '#' or other punctuation
  and you are unsure how to quote them safely in a .where() predicate. Covers
  the no-arg table.search() filter scan, the explicit .limit(), .select() to
  drop the dense_vector, and single-quote escaping (not a charset regex).
author: Claude Code
version: 1.0.0
date: 2026-06-04
---

# LanceDB: filter-scan by id + project columns

## Problem
You want `get_rows_by_ids(ids)` from a LanceDB table: a pure metadata filter
(`id IN (...)`), no vector search. Naive attempts (a) miss rows because LanceDB
caps a search at 10 by default, (b) are ~2x slower than needed because the scan
materialises the 1024-dim embedding column you throw away, and (c) tempt you to
charset-guard the ids, which breaks legitimate ids containing `:` or `#`.

## Context / Trigger conditions
- LanceDB (`lancedb` Python) table opened via `db.open_table(name)`.
- An id column whose values contain punctuation (e.g. chunk_id `Naval:VID#0007`).
- A "hydrate these ids into full rows" helper (e.g. bridging a graph store's thin
  `{id, ...}` rows back to full records).

## Solution
```python
PROJECT_COLS = ["id", "title", "url", "text", ...]  # only what you actually use

def get_rows_by_ids(ids: list[str]) -> list[dict]:
    ids = [x for x in (ids or []) if isinstance(x, str) and x]
    if not ids:
        return []
    # Escape single quotes by doubling; do NOT charset-guard (real ids contain ':' '#').
    quoted = ", ".join("'{}'".format(x.replace("'", "''")) for x in ids)
    table = db.open_table(NAME)
    available = {f.name for f in table.schema}          # tolerate optional cols
    cols = [c for c in PROJECT_COLS if c in available]
    rows = (
        table.search()                                  # no-arg => plain filter scan
        .where(f"id IN ({quoted})")
        .select(cols)                                   # skip dense_vector etc.
        .limit(len(ids))                                # default is 10 -- always set it
        .to_list()
    )
    by_id = {r["id"]: r for r in rows}
    return [by_id[x] for x in ids if x in by_id]        # input order, skip missing
```

Key points:
- **`table.search()` with no argument** returns a builder for a metadata-only
  scan; chain `.where(...).select(...).limit(...).to_list()`.
- **Always set `.limit()`** for a filter scan; the implicit default is small
  (10) and silently truncates a larger id list.
- **`.select(cols)`** to avoid materialising the embedding/vector column (e.g.
  1024 floats/row) and other heavy fields. Measured ~2x latency reduction on a
  ~30k-row table; the by-id scan was ~115 ms.
- **Escape, don't regex-guard** ids: `x.replace("'", "''")`. A `[a-z0-9_-]`
  allow-list rejects real ids like `Speaker:VIDEOID#0001`. Doubling single
  quotes is the injection-safe quoting LanceDB's DataFusion predicates expect
  (same approach used for episode-id predicates).
- Build a dict and re-index by the input list to **preserve input order and
  skip missing ids**. Note this is a positional 1:1 map: duplicate input ids
  yield duplicate output rows; dedup the input first if you need distinct rows.

## Verification
- Live read-only check: pass `list(reversed(real_ids)) + ["missing#0"]`, assert
  the output order equals `reversed(real_ids)` and the missing id is absent.
- Assert the returned dict has your projected keys and NOT the vector column.
- Unit test with a fake table exposing `.schema` (objects with `.name`),
  `.search().where().select().limit().to_list()`; capture the `where` string
  and assert a quote was doubled (`"''" in predicate`).

## Notes
- A full-table filter scan is still unindexed. If the helper becomes hot, add a
  scalar index: `table.create_scalar_index("id", index_type="BTREE", replace=True)`
  (a WRITE to the table; do not do this from a read-only path).
- `.select()` of a column absent from an older table's schema errors; intersect
  with `{f.name for f in table.schema}` first, and read optional columns with
  `row.get(...)` in your projection.

## References
- LanceDB Python query/search + scalar index docs (https://lancedb.github.io/lancedb/)
