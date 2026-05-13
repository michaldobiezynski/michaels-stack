---
name: memory-leak-audit-allocation-rate-vs-retention
description: |
  Methodology guard for memory-leak audits, especially when delegating
  parallel investigation to multiple agents. Distinguish between
  ALLOCATION CHURN (X MB allocated per call, freed when the function
  returns) and RETENTION (X MB allocated, stored somewhere long-lived
  so it accumulates). Agents tend to multiply per-call allocation by
  call rate by elapsed time and conclude "this matches the observed
  leak of N GB"; this math is wrong unless retention is independently
  proven. A 33 MB image clone freed at function return does not
  accumulate to 100 GB over 3000 calls — the heap returns to baseline
  after each call. Real retention requires a long-lived owner: a
  static, an Arc held by a long-running task, a struct field, a cache
  map, an atom, a global Vec, a push to an unbounded queue.

  Use when: (1) auditing memory growth in a long-running process,
  (2) reviewing subagent reports that flag candidate leak sites,
  (3) a report contains "per-tick allocation × time = total leak"
  arithmetic, (4) you're tempted to claim "this matches the user's
  observed N GB" based on allocation rate alone, (5) two candidate
  leak sites are flagged and you need to triage which one actually
  retains, (6) building or reviewing audit reports for any
  long-running system (capture loops, polling, streaming pipelines,
  bg workers, web servers).

  Catches the common LLM-agent failure mode of treating churn rate
  as retention rate when synthesising audit findings.
author: Claude Code
version: 1.0.0
date: 2026-05-11
---

# Memory-leak audit: distinguish allocation rate from retention

## Problem

A memory-leak investigation surfaces multiple candidate sites. Each
agent reports "this function allocates X MB per call, called Y times
per second, leak is X·Y·duration GB." The arithmetic adds up to the
user's reported leak size and the report reads convincingly. The
conclusion is wrong: most of those allocations are freed at function
return and never accumulate. The real leak lives in a smaller,
non-obvious retention path that the rate math doesn't surface.

LLM agents are particularly prone to this error. They observe the
allocation site, see large sizes (image buffers, tensors, captured
frames), do plausible arithmetic, and conclude. They miss the
follow-up question: "where does this allocation END UP after the
function returns?".

## Context / trigger conditions

This skill applies when any of these are true:

1. You are auditing memory growth in a long-running process (any
   server, agent loop, capture pipeline, polling worker, GUI app).
2. You are reviewing reports from subagents that audited candidate
   leak sites in parallel.
3. A report contains arithmetic of the form:
   `bytes_per_call × calls_per_second × duration = total_leak_size`,
   especially when the result conveniently matches the observed
   leak.
4. You're about to claim "the math works out to N GB which matches
   the user's observation".
5. Two or more candidate sites are flagged and you need to triage.

The specific failure mode: agents stop at the allocation site
without tracing where the bytes go on return.

## Solution

For each candidate leak claim, run the **owner trace** before
accepting it:

1. **Identify the allocation site.** What line allocates? How big?
   How often?

2. **Trace ownership at the end of the allocating function.** When
   the function returns, what owns the allocated bytes?
   - If they're a local variable / temporary / RAII guard / return
     value passed elsewhere → likely churn. Continue tracing the
     return value.
   - If they're moved into a `static`, a struct field on a
     long-lived object, an `Arc` shared with a long-running task,
     a `HashMap`/`Vec`/`DashMap`, a global cache, an atom, a
     channel buffer, etc. → likely retention. Stop and check
     cleanup paths.

3. **For each retention candidate, check the eviction path.**
   - Is there a removal call when the key is no longer needed?
   - Is the removal actually invoked on the relevant code paths?
   - Cross-side audit: if the key is shared across an IPC boundary,
     does the OTHER side remove the entry when it should? (See
     skill `tauri-cross-ipc-session-id-rotation-leaks-process-pool`
     for one shape of this bug.)

4. **Multiply by time ONLY for confirmed retention paths.** Churn
   rate × time is not a leak. The heap returns to baseline after
   each call. If the user reports 100 GB and the churn rate is
   33 MB at 4 s tick, that means ~33 MB peaks per cycle, not
   100 GB cumulative.

5. **Triage candidates by retention plausibility, not allocation
   size.** A 1 KB string pushed to an unbounded Vec on every event
   beats a 33 MB short-lived image clone for a true leak of 100 GB.

## Verification

Two independent checks confirm whether a candidate is retention or
churn:

1. **Static heap inspection mid-leak.** Take a heap snapshot
   (heaptrack, dhat, valgrind, Instruments, Chrome DevTools heap
   snapshot, etc.) and look for objects matching the candidate
   allocation. If they appear N times after running for a while,
   it's retained. If only a small constant number, it's churn.

2. **Eviction trace.** Add a `log::info!("freed X")` at the
   suspected drop site (Drop impl, removal call, etc.). If you see
   roughly one free per allocation, it's churn. If allocations
   greatly outpace frees, it's retention.

If you cannot run the process and observe heap directly (read-only
agent audits), favour candidates with a CLEAR retention path
(explicit insertion into a long-lived map / static / atom) over
candidates whose only evidence is "big allocation, many calls".

## Worked example

In a 2026-05 audit of a 100 GB memory leak in a Tauri chess
analysis app (live miniboard with auto-refresh), five parallel
agents reported candidates. Two of them conflated churn with
retention:

- **Agent 2 (ONNX detection)** flagged "Image::imageops::resize +
  Array4::<f32>::zeros + try_extract_tensor in detect_pieces:
  6-7 MB per call × 0.25 Hz × 3 hours = 19 GB". Wrong. Every one
  of those allocations was a function-local variable freed at
  function return. The ONNX session is cached in a `static Mutex`
  (verified), so model bytes don't reallocate per call. Heap at
  any moment held one frame's worth, not the cumulative.

- **Agent 4 (capture pipeline)** flagged "RGBA Vec clone in
  `png_bytes()`: 33 MB per tick × 3000 ticks over 3 hours = ~100
  GB". Wrong, in the same way. `CapturedFrame.rgba.clone()` is a
  short-lived clone consumed by PNG encoding then dropped. No
  static, no struct field, no atom. The math accidentally matched
  the leak size; the path was not the cause.

The actual cause was Agent 1's finding (orphaned Stockfish
processes accumulating in a `DashMap<(sessionId, engine_path), …>`
because the JS side rotated `sessionId` per event and the
backend's "stop" command didn't remove the map entry). Each
orphaned process retained 256 MB of Hash table. At ~360 leaked
processes over 3 hours: 92 GB. That's the true retention path.

If I had accepted Agents 2 or 4's math at face value, the fix
would have been: optimise the capture path (replace the clone)
or cache the tensor. Neither would have closed the leak. The
correct fix (stabilise the session id) only became obvious after
running the owner trace and rejecting the rate-times-time
arithmetic.

## Notes

- The 100 GB figure was a red herring in itself. Agents matched
  rate × time to the user's number and stopped. Cross-checking
  with the retention candidates would have shown that Agent 1's
  math (engines × Hash size × elapsed) also reached ~92 GB, with
  a much cleaner retention story.

- This trap is more common in audits done by multiple parallel
  agents than in single-agent audits, because each agent only sees
  its narrow vertical slice. The synthesis step is where the
  churn-vs-retention check has to happen. If the synthesiser also
  skips it, all five agents' findings look equally plausible.

- The corrective question to ask each agent (or yourself):
  > "Where does this allocation end up at the end of the function?"
  > "If it's a temporary, what cleans up the cumulative cost?"

- Don't conflate "fragmentation" with "leak" either. macOS and
  Linux allocators sometimes hold pages for reuse rather than
  returning them to the OS. RSS can grow without being a true
  leak. But fragmentation alone cannot 100x growth; if you're
  seeing 100 GB on a process with ~30 MB of true working set,
  it's retention not fragmentation.

- For Rust audits specifically, a candidate flagged as a clone
  inside a function body is almost never the leak unless one of:
  - The function stashes the clone in a long-lived struct field
    (e.g. `Lazy<Mutex<Vec<…>>>`, `OnceCell`, an `Arc` shared with
    a spawned task).
  - The function pushes to a Vec/HashMap/DashMap field on `&mut self`.
  - The clone escapes into an event payload that's queued at the
    IPC boundary without back-pressure.

  Otherwise it's churn.

## References

- Diagnosed in: pawn-au-chocolat live-miniboard 100 GB leak,
  2026-05-11. See also skill
  `tauri-cross-ipc-session-id-rotation-leaks-process-pool` for the
  specific bug shape this audit surfaced.
- General reading: dhat (Rust heap profiler) docs, Valgrind massif
  output interpretation, Chrome DevTools "Allocations on timeline"
  (which distinguishes "Shallow size" from "Retained size" — the
  same conceptual split).
