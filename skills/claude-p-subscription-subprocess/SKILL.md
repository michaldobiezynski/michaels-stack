---
name: claude-p-subscription-subprocess
description: |
  Build Python subprocess calls to `claude -p` that bill against a claude.ai
  Pro/Max subscription (NOT ANTHROPIC_API_KEY), with the right flags to (1)
  cut per-call cost ~70%, (2) pin the model so persisted labels match the
  call, and (3) parse structured JSON output safely. Use when: building
  Pattern 2 LLM tools (MCP servers, CLIs, agents) that should bill the
  user's subscription instead of API tokens; debugging "why does each call
  cost $0.20+"; debugging "why does my persisted record say sonnet but the
  call actually used opus"; parsing claude -p output for structured JSON
  responses. Covers --bare incompatibility, --system-prompt cost mechanics,
  --output-format json envelope shape, and the auto-mode Haiku 4.5
  classifier turn that always bills. Also covers making the call FULLY
  barebones (no hooks, no MCP servers) via --setting-sources '' and
  --strict-mcp-config, so host-machine settings.json hooks (e.g.
  UserPromptSubmit banners) and MCP servers don't leak into the subprocess.
  Also covers tuning CONCURRENT fan-out for bulk pipelines: parallel
  `claude -p` workers share an input-tokens-per-minute rate limit and start
  returning HTTP 429 when oversubscribed; a single call still succeeding
  while a batch 429s proves it's a RATE limit, not a quota/usage cap, so
  throttle the worker count and retry-with-backoff rather than abort. Use
  when a bulk `claude -p` job stalls with "429"/"rate limit" / "chunks
  un-prefixed", or you're sizing a ThreadPool of subscription calls.
author: Claude Code
version: 1.2.0
date: 2026-06-06
---

# Pattern 2: claude -p subscription subprocess calls

## Problem

You want to invoke an LLM from Python (or another language via subprocess)
without setting `ANTHROPIC_API_KEY`. The user has a claude.ai Pro/Max
subscription and you want the call to bill against that, not API tokens.

Three traps await:

1. **Cost trap**: the naive `claude -p "<prompt>"` invocation costs ~$0.20
   per call even for trivial prompts, because the default Claude Code
   system prompt loads CLAUDE.md, hooks, plugins, skills, and per-machine
   context (~30k cache-creation tokens per call).

2. **Model drift trap**: without `--model`, the CLI defaults to whatever
   the user has configured locally (Opus on many setups). If you persist a
   record saying `model=claude-sonnet-4-6`, the label silently lies about
   what produced the output.

3. **Parsing fragility trap**: parsing raw stdout breaks if the model adds
   prose preamble or trailing text around its structured output.

## Context / Trigger conditions

- Building an MCP tool, agent, or CLI that uses Claude from a subscription
- User explicitly forbids `ANTHROPIC_API_KEY` setup ("I want to use my own
  subscription for everything")
- Subscribed user wants cost predictability per tool call
- Tool persists a `model` field that should match reality
- Need structured JSON output (block arrays, JSON object responses) from
  Claude reliably

## Solution

### 1. Flag combination

Use this canonical command line:

```python
cmd = [
    "claude",
    "-p",
    "--model", "claude-sonnet-4-6",      # pin model; mirror in persisted record
    "--system-prompt", SYSTEM_PROMPT,    # REPLACES default Claude Code prompt
    "--disable-slash-commands",          # skip skill discovery
    "--output-format", "json",           # envelope with cost + model usage
    user_message,
]
```

DO NOT use `--bare`. It requires `ANTHROPIC_API_KEY` (skips OAuth/keychain)
and is incompatible with subscription billing.

### 1b. Fully barebones: also strip hooks and MCP servers

`--system-prompt` + `--disable-slash-commands` replace the prompt and skip
skill discovery, but they do NOT stop the user's **hooks** or **MCP servers**
from loading. In a worker subprocess you usually want neither: a
`UserPromptSubmit` hook can inject banners into the prompt, and MCP servers add
startup latency and tool noise. Two more flags make the session truly barebones:

```python
cmd = [
    "claude", "-p",
    "--model", model,
    "--system-prompt", system,
    "--setting-sources", "",     # load NO user/project/local settings -> no hooks
    "--strict-mcp-config",       # with no --mcp-config -> load NO MCP servers
    "--disable-slash-commands",  # no skills
    "--output-format", "json",
    user_message,
]
```

- `--setting-sources` takes a comma-separated subset of `user,project,local`.
  Passing an **empty string** loads none of them, so nothing in any
  `settings.json` (hooks included) takes effect for that call. This is the
  non-obvious bit: `--help` only lists the three source names; that empty =
  "load nothing" is what disables hooks.
- `--strict-mcp-config` means "only use MCP servers from `--mcp-config`";
  supply no `--mcp-config` and you get zero MCP servers. It does not error when
  `--mcp-config` is absent.

Verified on Claude Code CLI 2.1.158 (May 2026). For a trivial classify-from-
title call this lands at ~$0.04 with `claude-haiku-4-5`, ~3-5s, subscription-
billed, with no host hooks/skills/MCP leaking into the worker.

### 2. Cost mechanics (verified empirically May 2026)

| Flags | Cost / call | Cache-creation tokens |
|---|---|---|
| `claude -p <prompt>` (none) | ~$0.20 | ~31,000 |
| `+ --system-prompt` | ~$0.09 | ~23,800 |
| `+ --system-prompt + --disable-slash-commands` | ~$0.06 | ~16,000 |

`--system-prompt` REPLACES the default Claude Code system prompt entirely;
it does not append. Your prompt becomes the entire system context, which
is what cuts cache-creation tokens.

Two models always bill per call when `--output-format json` is used:
- **Haiku 4.5** for the internal auto-mode classifier turn (~$0.0005, negligible)
- **The model you picked via `--model`** for the actual reply

### 3. Envelope shape from --output-format json

`claude -p --output-format json` writes ONE JSON object to stdout:

```json
{
  "type": "result",
  "subtype": "success",
  "result": "<string containing the model's reply>",
  "total_cost_usd": 0.0626,
  "duration_ms": 14950,
  "usage": { ... },
  "modelUsage": {
    "claude-haiku-4-5-20251001": { "input_tokens": 442, "output_tokens": 11, ... },
    "claude-sonnet-4-6": { "input_tokens": 23866, "output_tokens": 412, ... }
  },
  "is_error": false,
  "session_id": "..."
}
```

`envelope["result"]` is a STRING containing the model's reply. If you asked
for JSON output in your system prompt, `result` is a string of JSON that
you then `json.loads()` separately. Two parse steps:

```python
envelope = json.loads(proc.stdout)
model_reply_str = envelope["result"]
structured_output = json.loads(model_reply_str)  # if you prompted for JSON
```

Markdown fences (` ```json ... ``` `) sometimes still wrap the result string
even when you ask for raw JSON in the system prompt. Defence-in-depth:
strip them before the second `json.loads()`.

### 4. Error mapping (subprocess Python)

| Exception | Cause | User-facing message |
|---|---|---|
| `FileNotFoundError` | `claude` not on PATH | "Install Claude Code at https://claude.com/code" |
| `subprocess.TimeoutExpired` | Synthesis hung | "claude -p timed out after Ns" |
| `subprocess.CalledProcessError` | Non-zero exit | Include `e.stderr[:300]` |
| `envelope.is_error == true` | Claude reported error | Surface `envelope["result"]` |
| `json.JSONDecodeError` on stdout | Envelope malformed | First 200 chars of stdout |
| `json.JSONDecodeError` on result | Model produced non-JSON | First 200 chars of result; consider regex fallback |

### 5. Python skeleton

```python
import json
import subprocess

SYSTEM_PROMPT = """Your task-specific system prompt here.
Reply with a JSON array. No prose. No markdown fences."""

def call_claude(user_message: str, model: str = "claude-sonnet-4-6") -> dict:
    cmd = [
        "claude", "-p",
        "--model", model,
        "--system-prompt", SYSTEM_PROMPT,
        "--disable-slash-commands",
        "--output-format", "json",
        user_message,
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            timeout=180, check=True,
        )
    except FileNotFoundError as e:
        raise RuntimeError(
            "`claude` CLI not on PATH. Install from https://claude.com/code"
        ) from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"claude -p exit {e.returncode}: {(e.stderr or '')[:300]}") from e

    envelope = json.loads(proc.stdout)
    if envelope.get("is_error"):
        raise RuntimeError(f"claude reported is_error: {envelope.get('result')!r}")

    cost = envelope.get("total_cost_usd")
    if cost is not None:
        print(f"cost ~${cost:.4f} model={model} duration_ms={envelope.get('duration_ms')}")

    return json.loads(envelope["result"])  # if you prompted for JSON output
```

### 6. Concurrency: the 429 input-tokens-per-minute ceiling

Fanning `claude -p` out across a thread pool is how you win throughput on a
bulk job (per-chunk prefixing, per-item classification). But every call is
heavy on INPUT tokens even when barebones — the `--system-prompt` is
re-sent each call and lands as ~15k cache-creation/cache-read tokens. So N
concurrent workers push ~N×15k input tokens/burst, and the subscription's
**input-tokens-per-minute (ITPM)** ceiling, not the per-day/weekly quota, is
what you hit first.

**Symptom:** mid-run, calls start failing with `CalledProcessError` whose
stderr/`is_error` mention `429` or `rate limit`. A bulk driver that gates on
"too many items still unprocessed" stalls (e.g. council-of-thinkers logs
`N/N chunks un-prefixed (likely claude rate limit); holding ... for a clean
retry`). Errors climb while completed-count flatlines.

**The key diagnostic — rate limit vs quota cap:** run ONE fresh
`claude -p` probe by hand. If the single call **succeeds** (`is_error:false`,
exit 0) while the batch is 429ing, it's a per-minute RATE limit from
oversubscription — there's quota left, you're just calling too fast. If the
single probe ALSO fails with a usage/limit message, you've hit the actual
quota cap (wait for reset). These need opposite responses: throttle vs stop.

**Fix for the rate limit: throttle total concurrent workers.** Measured on a
Max subscription, June 2026, barebones Sonnet calls:

| Total concurrent `claude -p` | Result |
|---|---|
| ~18 (e.g. two pools, 10 + 8) | sustained 429s within ~1h; episodes stall/error |
| ~8 (e.g. 5 + 3) | stable for hours; only rare transient 429s, absorbed by retry |

Count workers GLOBALLY, not per pool: if two independent stages each fan out
(e.g. a prefixer at 10 and a concept-extractor at 8), they share the same
account ceiling and sum to 18. Size to the sum.

**Make transient 429s non-fatal** — retry with backoff, and on persistent
failure leave the item unprocessed for an idempotent re-run rather than
aborting the batch:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess, time

def gen_resilient(item):
    for attempt in range(3):
        try:
            return call_claude(item)          # the section-5 skeleton
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            if attempt == 2:
                return None                    # leave undone; a later pass retries
            time.sleep(2 * (attempt + 1))      # 2s, 4s backoff
    return None

with ThreadPoolExecutor(max_workers=5) as pool:   # GLOBAL budget, not per stage
    futures = {pool.submit(gen_resilient, it): it for it in pending}
    for fut in as_completed(futures):
        result = fut.result()
        if result is None:
            continue                            # skipped; idempotent re-run picks it up
        ...
```

Pair this with a resume mechanism (skip already-done items on re-run) so a
rate-limit wave costs time, not correctness. Note a quota cap tends to hit
HARDEST right before its reset boundary — a long bulk run timed to "use up
quota before reset" will 429-storm in its final stretch; that's expected, not
a bug, and the work resumes cleanly on fresh quota.

## Verification

1. **Cost dropped**: log `total_cost_usd` from envelope. Should be ~$0.06
   for short prompts, NOT $0.20.
2. **Model pinned**: log `envelope["modelUsage"]` keys. Should include
   your `--model` choice, not whatever Opus the user has configured.
3. **`claude -p --help`**: shows your flag set is supported by the
   current CLI version.

## Example

Real case from `council-of-thinkers` PR #7 (May 2026):

**Before** (naive `subprocess.run(["claude", "-p", prompt])`):
- $0.20 per synthesis call
- Persisted `model=claude-sonnet-4-6` but actual call used Opus 4.7
- Parsing the raw stdout broke when the model added intro prose

**After** (flag set above):
- $0.063 per call (70% drop, verified by `total_cost_usd`)
- Pinned to `claude-sonnet-4-6`, matches persisted label
- Envelope.result parses reliably as a JSON array

## Notes

- **DO NOT use `--bare`**: requires `ANTHROPIC_API_KEY`, incompatible with
  the whole point of Pattern 2.
- **`--system-prompt` length**: still counts towards cache-creation, so
  keep it focused. Don't paste 5k characters of instructions.
- **Race in pasted prompts with null bytes**: CPython's `subprocess` will
  reject argv strings with `\x00`. Catch `ValueError` and surface a clear
  error.
- **The auto-mode Haiku 4.5 turn ALWAYS bills** when `--output-format json`
  is used, even for trivial prompts. It's a fixed ~$0.0005 floor that you
  cannot eliminate while keeping JSON envelopes. Not worth optimising.
- **Argv length limit**: macOS argv max is ~1MB; Linux is typically 128KB.
  For prompts approaching these limits, pipe via stdin instead of argv
  (use `--input-format text` or whatever the current CLI exposes).
- **Subprocess credentials**: the `claude` CLI reads OAuth tokens from
  the user's keychain; the subprocess inherits this naturally. No
  environment variable plumbing needed.
- **Logging cost per call** is essential during development; the
  envelope makes it trivial. Log it at INFO level so the user can watch
  their subscription burn.

## When this skill DOES NOT apply

- API-billed tools (you want `ANTHROPIC_API_KEY` + Anthropic SDK directly)
- Tools that need streaming output (use `--output-format stream-json` instead)
- Tools that need multi-turn conversations within one process (use the
  `--continue` flag pattern or the SDK)
- Production servers where subprocess overhead matters more than auth
  ergonomics (API path is faster + more parallelisable)

## References

Empirically gathered May 2026 from:
- `claude -p --help` output
- `claude -p --output-format json` envelope inspection
- Cost measurement across flag combinations
- council-of-thinkers PR #7 implementation:
  https://github.com/michaldobiezynski/council-of-thinkers/pull/7

Official documentation: https://docs.claude.com/en/docs/claude-code/ (check
for the current CLI flag set; this skill reflects the CLI as of May 2026).
