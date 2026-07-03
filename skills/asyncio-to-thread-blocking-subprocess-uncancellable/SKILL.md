---
name: asyncio-to-thread-blocking-subprocess-uncancellable
description: |
  `asyncio.to_thread(subprocess.run, ...)` looks like a cancellable async
  wrapper around a blocking subprocess call, but it is NOT. Cancelling the
  awaiting task unblocks the await, but the worker thread keeps running and
  the child process keeps consuming wall time. asyncio cannot cancel work
  inside `to_thread` because Python threads have no portable cancellation
  primitive. Use when: (1) an asyncio app has a slow shutdown that waits
  seconds for a previous subprocess call to finish naturally, (2) cancelling
  a task that called `asyncio.to_thread(subprocess.run, ...)` leaves the
  subprocess visible in `ps` after the cancel awaits return, (3) a Textual
  TUI or other long-running asyncio service wraps `subprocess.run` in
  to_thread and quit feels laggy or unresponsive, (4) you are writing
  pre-render / background pipelines that spawn external CLIs (`say`, `ffmpeg`,
  `whisper`, `aeneas`) and need prompt shutdown on user quit. Fix: replace
  `subprocess.run` inside the worker with `subprocess.Popen`, expose the
  Popen handle to the event loop via shared state guarded by a `threading.Lock`
  (NOT `asyncio.Lock` — the worker thread can't await), then have the
  cancel/shutdown path kill the subprocess externally so the worker's
  `proc.wait()` returns promptly. Includes the lock ordering and the
  `_cancelled` re-check after the wait.
author: Claude Code
version: 1.0.0
date: 2026-05-17
---

# asyncio.to_thread + subprocess.run is uncancellable

## Problem

A common pattern for running a blocking subprocess from asyncio:

```python
await asyncio.to_thread(
    subprocess.run, args, check=False,
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
```

This looks safe — the synchronous `subprocess.run` runs on a worker thread, so
the event loop stays responsive. But cancellation behaviour is surprising:

- `task.cancel()` causes the awaiting coroutine to raise `CancelledError`.
- The worker thread keeps running. `subprocess.run` blocks until the child
  exits naturally.
- The child process keeps consuming CPU / wall time / audio output / etc.
- Any `await self._task` in your cancel/shutdown path returns "quickly"
  (because the asyncio future is cancelled) — but the side-effects of the
  thread are still in flight.

Symptoms in practice:

- A TUI app where `q`/quit feels laggy: the UI tears down but audio keeps
  playing, or a long-running `ffmpeg`/`whisper`/`say` call finishes
  in the background.
- Shutdown handlers that "await cancel" then `shutil.rmtree(tempdir)` — and
  rmtree fails or races because the worker thread is still writing to it.
- `ps aux | grep <tool>` shows the child process alive after the Python
  process appears to have shut down asyncio cleanly.

## Trigger conditions

- asyncio code that spawns external tools via
  `asyncio.to_thread(subprocess.run, ...)`.
- A shutdown / cancel path that calls `task.cancel()` and `await task`.
- Symptom: shutdown completes "in asyncio time" but the child process is
  still running.

## Solution

Replace `subprocess.run` inside the thread with `subprocess.Popen`, and expose
the Popen handle to the event loop so cancel() can kill it directly. The
event loop and the worker thread share the handle, so guard it with a
`threading.Lock` (not `asyncio.Lock` — the worker thread cannot await).

```python
import asyncio
import subprocess
import threading


class Worker:
    def __init__(self) -> None:
        # Shared between event loop and worker thread. Guard with threading.Lock.
        self._current_proc: subprocess.Popen[bytes] | None = None
        self._proc_lock = threading.Lock()
        self._cancelled = False
        self._task: asyncio.Task[None] | None = None

    async def cancel(self) -> None:
        self._cancelled = True
        # Kill any in-flight subprocess so the worker thread's proc.wait()
        # returns promptly. Without this, shutdown stalls until the child
        # exits naturally.
        self._kill_current_proc()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    def _kill_current_proc(self) -> None:
        with self._proc_lock:
            proc = self._current_proc
            if proc and proc.poll() is None:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass

    async def _render(self, args: list[str]) -> None:
        await asyncio.to_thread(self._run_blocking, args)
        if self._cancelled:
            return
        # ... post-process the subprocess output ...

    def _run_blocking(self, args: list[str]) -> None:
        """Spawn the child and block until it exits. Killable via cancel()."""
        with self._proc_lock:
            # Re-check cancellation under the lock — cancel() may have run
            # between scheduling this thread and the thread actually starting.
            if self._cancelled:
                return
            proc = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._current_proc = proc
        try:
            proc.wait()
        finally:
            with self._proc_lock:
                # Identity check: a newer Popen may have replaced ours.
                if self._current_proc is proc:
                    self._current_proc = None
```

Key points:

1. **`threading.Lock`, not `asyncio.Lock`.** The worker thread cannot
   `await`. Use a thread-safe primitive.
2. **Re-check `_cancelled` under the lock** inside `_run_blocking` so that a
   cancel that races the thread start is honoured before `Popen` is called.
3. **Identity check** in the `finally` block (`if self._current_proc is proc`)
   so a newer subprocess from a subsequent `_run_blocking` call isn't
   accidentally cleared.
4. **`_render` re-checks `_cancelled`** after the to_thread call returns, so
   it doesn't proceed to post-processing when the child was killed.
5. **`ProcessLookupError` is benign** in `_kill_current_proc` — the child may
   have exited between the `poll()` and the `kill()`.

## Verification

Time the cancel call while a long subprocess is in flight:

```python
import asyncio, time

async def run():
    worker = Worker()
    worker._task = asyncio.create_task(worker._render(["sleep", "10"]))
    await asyncio.sleep(0.2)  # let the subprocess get going
    t0 = time.monotonic()
    await worker.cancel()
    elapsed = time.monotonic() - t0
    print(f"cancel returned in {elapsed*1000:.0f} ms (expect < 100 ms)")

asyncio.run(run())
```

Before the fix: cancel waits for `sleep` to complete, ~10 seconds. After the
fix: <10 ms typically.

Also `ps aux | grep <tool>` after shutdown should show no orphaned children.

## Example

Observed in recite, a TUI text-to-speech app. The synth pre-render pool used:

```python
await asyncio.to_thread(
    subprocess.run, ["say", "-o", path, sentence],
    check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
```

Pressing `q` (quit) triggered `on_unmount` → `synth.cancel()` → `await self._task`.
The await returned promptly in asyncio time, but the `say` child kept running
until it finished synthesising the current sentence. For long sentences this
was multi-second lag where the TUI looked frozen. Patched to the Popen pattern
above; cancel now returns in **0 ms** while `say` is mid-flight (measured by
timing `await synth.cancel()`).

## Notes

- The same pattern applies to ANY blocking external call wrapped in
  `to_thread` — not just `subprocess.run`. If the inner call has no
  "interrupt me" handle, you cannot cancel it cleanly.
- Python 3.13's experimental free-threaded build does not change this:
  cancellation of thread work is still cooperative; you need an external
  kill primitive (signal, file handle close, process kill).
- For non-subprocess blocking work (e.g. a long-running pure-Python
  computation), the same trick doesn't apply — there is no Popen handle to
  kill. You'd need to chunk the work and check a cancellation flag at chunk
  boundaries.
- If you must use `subprocess.run` (e.g. you want its built-in timeout
  handling), pass `timeout=...` and let the call raise, then re-raise
  CancelledError from the wrapping coroutine. But Popen is more flexible
  and aligns with the cancellation model you actually want.
- `asyncio.create_subprocess_exec` is the "right" async-native primitive for
  subprocess work. It returns a process whose `wait()` is awaitable and
  whose `kill()` integrates with the event loop. Prefer it over the
  to_thread + Popen pattern when starting fresh. The Popen pattern is the
  correct fix when you're already on the to_thread approach and want a
  minimal-diff change.

## References

- Python docs on `asyncio.to_thread`: <https://docs.python.org/3/library/asyncio-task.html#asyncio.to_thread>
  ("Note: Due to the GIL, asyncio.to_thread() can typically only be used to
  make IO-bound functions non-blocking. ... cannot cancel the call inside
  the thread.")
- Python docs on `asyncio.create_subprocess_exec` (preferred for new code):
  <https://docs.python.org/3/library/asyncio-subprocess.html>
- `subprocess.Popen` reference: <https://docs.python.org/3/library/subprocess.html#popen-constructor>
