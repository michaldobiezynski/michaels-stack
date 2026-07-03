---
name: council-of-thinkers-worktree-testing
description: |
  Run the council-of-thinkers (Sapiens Locus) Python test suite inside a git
  worktree without reinstalling the multi-GB ML stack. Use when: (1) you used
  EnterWorktree / `git worktree add` on council-of-thinkers and `.venv/bin/python`
  is missing in the worktree; (2) `pytest`/`ruff` are not on PATH; (3) ~15
  rerank/balance tests (tests/test_rerank.py, tests/test_server_rerank.py,
  tests/test_explore_speaker.py) FAIL only inside the worktree with the log line
  "Reranker schema check: table 'chunks' not found in .../lancedb/council ...
  Disabling rerank" and assertions like `candidate_count == 5` (got) vs `50`
  (expected overfetch); (4) you are tempted to run `uv sync` in the worktree.
  Root cause: the worktree lacks the gitignored `.venv` AND `lancedb/` corpus.
author: Claude Code
version: 1.0.0
date: 2026-06-22
---

# Running council-of-thinkers tests inside a git worktree

## Problem

A fresh git worktree of `council-of-thinkers` is a clean checkout that does NOT
contain the two gitignored, on-disk-only dependencies the test suite needs:

1. The Python virtualenv (`.venv/`) — so `<worktree>/.venv/bin/python` does not exist.
2. The LanceDB corpus (`lancedb/council/chunks.lance`, ~440 MB) — so any test that
   asks `council_mcp.rerank.is_rerank_enabled()` (which does a real schema check
   against the corpus) sees no `chunks` table, disables rerank, and fails.

Running `uv sync` to recreate the venv works but builds a multi-GB stack
(torch, torchcodec, lancedb, pyannote-audio, sentence-transformers, mlx-whisper)
— slow and unnecessary.

## Context / Trigger conditions

- You created the worktree (e.g. `EnterWorktree`, or `git worktree add .claude/worktrees/<name>`).
- `ls <worktree>/.venv/bin/python` → "No such file or directory".
- Full suite in the worktree: ~15 failures, ALL in `tests/test_rerank.py`
  (`TestSingletonRaceCondition`, `TestResetRerankCache`), `tests/test_server_rerank.py`
  (`TestQueryCouncilImplRerank`, `TestRerankMinScoreThreshold`,
  `TestSynthesiseCouncilRerankWiring`), and `tests/test_explore_speaker.py`
  (`TestBalanceBySpeaker`).
- The captured log shows: `WARNING council_mcp.rerank:rerank.py:NNN Reranker schema
  check: table 'chunks' not found in <worktree>/lancedb/council; cannot verify
  column 'text_for_embedding' exists. Disabling rerank.`
- The SAME tests pass on `master` in the MAIN checkout (so it looks like your
  branch regressed — it did not; it's purely the missing corpus).

## Solution

Both fixes assume `MAIN=/path/to/council-of-thinkers` (the primary checkout) and
that you run from inside the worktree directory.

### 1. Reuse the main checkout's venv (no `uv sync`)

```bash
# Run from the worktree root. Imports of council_mcp/ingest resolve to the
# WORKTREE source (pytest puts the rootdir on sys.path); third-party deps come
# from the shared venv.
$MAIN/.venv/bin/python -m pytest -q
```

Why this is safe: the project is NOT pip-installed into the venv (site-packages
has only `_virtualenv.pth` / `distutils-precedence.pth`, no project `.pth` and no
`__editable__`). So `python -m pytest` run from the worktree imports `council_mcp`
and `ingest` as top-level packages from the current working directory, which is
the worktree. Verify once:

```bash
$MAIN/.venv/bin/python -c "import council_mcp.synthesise as m; print(m.__file__)"
# must print a path UNDER the worktree, not the main checkout
```

`pytest`/`ruff` are not on PATH — always invoke via `$MAIN/.venv/bin/python -m pytest`
(or `uv run pytest`). There is no committed ruff/pytest config and no CI, so the
pytest suite is the only reliable gate.

### 2. Symlink the corpus into the worktree

`DEFAULT_LANCE_PATH = PROJECT_ROOT / "lancedb" / "council"` where
`PROJECT_ROOT = Path(__file__).resolve().parent.parent` (ingest/lance.py), so it
resolves relative to the WORKTREE. Point it at the real corpus:

```bash
rm -rf <worktree>/lancedb           # remove the empty auto-created dir
ln -s $MAIN/lancedb <worktree>/lancedb
ls <worktree>/lancedb/council       # should list chunks.lance
```

The rerank schema check only READS the corpus (and rerank tests monkeypatch
`_construct_reranker`), so a symlink to the shared corpus is read-safe; write
tests use `tmp_path`.

## Verification

```bash
cd <worktree>
$MAIN/.venv/bin/python -m pytest tests/test_rerank.py tests/test_server_rerank.py tests/test_explore_speaker.py -q
# all green
$MAIN/.venv/bin/python -m pytest -q
# ~1420 passed, 6 skipped (baseline master ~1381; the delta is your new tests)
```

## Notes

- The `lancedb/` symlink is gitignored, but a gitignore pattern of `lancedb/`
  (trailing slash, matches a directory) does NOT match a symlink, so
  `git status` shows `?? lancedb`. Never `git add` it — it must not enter a PR.
- This is distinct from the `council-of-thinkers-local-dev` skill, which starts
  the running dev stack (backend :8766 + frontend :3000). This skill is purely
  about running the pytest suite from a worktree.
- If you only need a subset of tests that don't touch rerank/lancedb (e.g.
  test_synthesise, test_synthesis_store, test_http_server, test_server_auth),
  step 1 alone is enough; the symlink (step 2) is only needed for the
  rerank/balance suites.
