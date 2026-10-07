---
name: crashed-agent-artefacts-outlive-return-values
description: |
  When a batch of agents dies mid-pipeline (API 529/overload, timeout, kill), their
  RETURN VALUES are lost but their DISK SIDE EFFECTS survive — and a stage that died
  between "scaffold" and "fill" leaves a structurally-valid but EMPTY artefact that
  downstream validators happily pass. Two plays: RECOVER the orphaned work instead of
  re-running it, and GATE on content rather than structure so an empty artefact never
  ships. Use when: (1) a parallel agent batch reports errors/zero results and you are
  about to re-run it, (2) an artefact you generated and shipped scored zero / came back
  blank / "contains only a header" despite the underlying work having succeeded,
  (3) a schema/structure/lint validator passes but the output is visibly useless,
  (4) you are about to spend a RATE-LIMITED or paid slot (publish quota, deploy,
  submission, email send) on agent-generated content, (5) a job's ledger/manifest count
  disagrees with what is actually on disk. Covers the audit-before-rerun rule, building
  a content gate that resists template boilerplate, and two regex traps that make such a
  gate silently useless or actively harmful.
author: Claude Code
version: 1.0.0
date: 2026-08-01
---

# Crashed agent artefacts outlive return values

## Problem

A multi-stage agent pipeline (generate → assemble → validate → ship) loses agents to
transient API failures. Two failure modes follow, and both look like something else:

1. **Work appears lost but isn't.** The orchestrator sees `agents_error: N` and empty
   results, so the obvious move is to re-run. But each agent had already written files.
   Re-running pays full price for work sitting on disk — and can *overwrite* a complete
   artefact with a partial one from the shorter second run.

2. **Empty artefacts ship looking healthy.** An agent that died between scaffolding a
   template and filling it leaves every required file, heading, and metadata key in
   place. A structural validator passes. The artefact ships and is scored/read/consumed
   as garbage. Nothing errors anywhere.

Real instance: a reproduction logbook whose six claim pages contained only
`Document setup, runs, and results for Claim N` published cleanly and was scored
**0/12** by a downstream judge — while a complete 45KB `run.log` of correct numerics sat
in the same directory. Filling the pages from that log took one agent and no
recomputation, and the artefact re-scored **12/12**.

## Context / Trigger conditions

- A workflow/batch reports `agents_error > 0`, dead agents, or "returned nothing", and
  the instinct is to relaunch the same range.
- A shipped artefact scores zero, renders blank, or a consumer reports "only a header",
  "placeholder text", "no content" — while you have evidence the work itself ran.
- `validate`/`lint`/schema check passes on something you can see is not filled in.
- A manifest, ledger, or DB table has fewer entries than the output directory has
  directories.
- You are about to consume a scarce, non-refundable slot (rate-limited publish, one-shot
  submission, outbound send) with agent-generated content.

## Solution

### Play 1 — Audit the disk before re-running anything

Diff what exists on disk against what your ledger/manifest believes exists:

```sh
# orphans: output dirs with no ledger entry
python - <<'PY'
import json, os
led = set(json.load(open('ledger.json'))['papers'])       # your manifest keys
dirs = {d for d in os.listdir('out') if os.path.isdir(f'out/{d}')}
print('orphans:', sorted(dirs - led))
PY
```

Then classify each orphan by **completeness against the spec**, not by whether it looks
tidy — e.g. count the per-item result markers the generator emits and compare to the
number of items required:

```sh
grep -c '^CLAIM' out/<id>/run.log      # markers produced
```

Three buckets: complete (harvest as-is, no recompute), partial (relaunch the *existing*
script to completion), empty (drop).

**Back up before relaunching.** If the runner's convention is `... | tee run.log`, it
will destroy the partial-but-real log. Redirect the new run elsewhere and keep the old:

```sh
cp out/$d/run.log out/$d/run.log.bak
( cd out/$d && nohup python repro.py > run_complete.log 2>&1 & )
```

This makes recovery strictly additive: worst case you still hold what you started with.

Relaunching a finished script is **compute, not tokens** — it costs nothing from the
model budget and carries no API-failure exposure.

### Play 2 — Gate on content, not structure

Write a checker that strips the template's own scaffolding and asserts the remainder is
real. `scripts/check_generated_content.py` in this skill is a working, generalised
version. The core:

```python
CELL = re.compile(r"<!--\s*template-cell.*?-->", re.S)   # strip generator metadata
def body(path):
    t = CELL.sub("", open(path, encoding="utf-8", errors="replace").read())
    t = re.sub(r"^#\s.*$", "", t, flags=re.M)             # strip headings
    return t.strip()

# a filled page carries prose AND numerals; a stub carries neither
if STUB.search(b) or len(b) < 120:      stub.append(name)
elif len(b) < 400 or len(re.findall(r"\d", b)) < 8:  thin.append(name)
```

Then **wire it into the shipping path so it refuses**, rather than leaving it as a
command someone remembers to run:

```python
chk = subprocess.run([PY, CONTENT_CHECK, outdir], capture_output=True, text=True)
if chk.returncode != 0:
    print(json.dumps({"published_ok": False, "blocked": "stub_pages"}))
    return          # scarce slot NOT consumed
```

Put the gate in the single function every path calls (the publisher), so scheduled jobs
and cron drains inherit it for free.

### Three traps that decide whether the gate is worth having

0. **Discovery.** Python's `glob` wildcards do **not** match hidden directories, and
   generators love hiding state (`.trackio/`, `.cache/`, `.output/`). A pattern like
   `**/claim-*/page.md` with `recursive=True` returns *nothing* when any path component
   starts with a dot — so the gate reports a clean sweep having examined zero files. Use
   `os.walk` for discovery. This bit during verification: the first version of the helper
   called a known-good artefact a stub and then matched no directories at all.


1. **Typography.** The scaffold wrote `Write a 3–5 sentence summary here` with an **en
   dash**. A pattern containing the ASCII hyphen `3-5` matched nothing, so the gate
   reported "clean" on a wholly-unfilled page. Match boilerplate permissively
   (`3.5 sentence`, or `[-–—]`). A false "clean" is worse than no gate, because it stops
   you looking.

2. **Over-broad tokens.** Matching bare `TODO|PLACEHOLDER` false-positived on a
   legitimate caveat ("the arXiv id is a placeholder-format id") — and an agent told to
   satisfy the gate then **reworded correct prose** to get past it. Match the generator's
   actual boilerplate strings only. A check that pressures agents into editing good
   content is a net negative.

Also check the *narrative* sections, not just the repeated item sections: a consumer
reads the whole artefact, and summary/conclusion pages are filled by a different code
path that can fail independently.

## Verification

**Run both directions — a gate that never fires proves nothing.**

- Gate blocks a known-bad artefact **without** consuming the scarce slot:
  `published_ok: false, blocked: "stub_pages"`.
- Gate passes known-good artefacts (run it on ones already accepted downstream) —
  confirms it is not merely rejecting everything.
- Negative test with a synthetic stub that exercises the traps: put it behind a hidden
  directory and use the generator's typographic boilerplate verbatim. The bundled script
  is verified against `{"checked": 171, "artefacts_with_stub_sections": 0}` on a real
  corpus and exit 1 on such a synthetic stub.
- Beware `cmd | tail` when checking exit codes — the pipe reports `tail`'s status, not
  the checker's. Redirect to a file and test `$?` directly.
- Sweep everything already shipped: `check_generated_content.py --all`. Expect a small
  number of hits; if it flags most of your corpus, the thresholds are wrong.
- After repair, confirm the downstream consumer's score/output actually changed
  (0/12 → 12/12 in the reference case). Structural revalidation proves nothing here.

## Example

Final day of a scored campaign, 154 artefacts already shipped:

1. `ls out/ | diff` against ledger keys → **20 orphan dirs** from a crash two days
   earlier; 14 had complete logs.
2. Harvested 12 with no recomputation → shipped → **+69 pts**.
3. Relaunched 4 partial scripts on CPU → harvested → **+27 pts**.
4. Content sweep of all 155 → 2 stub artefacts, both shipped days ago. Repaired from
   their own on-disk logs → `0/12 → 12/12` and `5/10 → 7/10`.

**Token economics measured the same day** (use this to order levers):

| Lever | Tokens | Points | Per-point |
|---|---|---|---|
| Harvest existing on-disk work | 1.81M | ~96 | best |
| Improve/refine shipped artefacts | 2.86M | 52 | ~2.5x worse |
| Fresh generation from scratch | 1.74M | **0** (all agents died) | ∞ |

Drain the orphan pool **before** starting any refinement or fresh-generation pass.

## Notes

- **Short agents survive what long agents don't.** The harvest agents read a file and
  wrote markdown; 24 ran with 0 errors under the same API conditions that killed every
  60-minute compute agent. Expected cost per delivered unit rises sharply with agent
  duration, so prefer many short checkpointing stages to one mega-agent.
- **Have each agent checkpoint to disk before returning.** Then this whole recovery is
  cheap by construction rather than archaeological.
- **Mid-run checkpoints go stale.** A calibration checkpoint written at 10:22:32 while
  the run finished at 10:23:42 described a truncated log. The downstream agent noticed
  the timestamp skew and used the primary source instead. Have later stages read the
  primary artefact, not only the handoff blob.
- **Process-name polling is unreliable** when concurrent work shares a binary name:
  `until [ "$(pgrep -c -f repro.py)" -eq 0 ]` never fired because refinement agents kept
  spawning their own `repro.py`. Poll the specific output files instead.
- **Subagents given a shell will fix their own blockers, including shared state.** One
  upgraded `transformers` 4.57.1 → 5.14.1 in the venv every other script depended on. It
  reported this clearly; verify the shared environment still works before continuing.
- Related: `audit-cheap-output-before-expensive-downstream-step` (validate a cheap
  stage's output quality before paying for the next one — same family, but that skill is
  about *poor* output, this one about *absent* output that looks present);
  `resumable-llm-batch-incremental-write` (write incrementally so work is never lost in
  the first place).

## References

No external sources — this is an agent-orchestration pattern derived from a measured
run, not a documented library behaviour. The token and score figures above are from
observed tool output, not estimates.
