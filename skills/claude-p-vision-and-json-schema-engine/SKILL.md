---
name: claude-p-vision-and-json-schema-engine
description: |
  Drive the `claude -p` CLI as a programmatic PERCEPTION engine from code:
  reading IMAGES (PNG screenshots etc.) and returning SCHEMA-CONSTRAINED JSON,
  safely even when the images are UNTRUSTED. Use when: (1) building a
  Python/other tool that extracts structured data from images via Claude;
  (2) your parse reads the model's prose and misses the data because you parsed
  `result` instead of `structured_output`; (3) a vision call silently stalls or
  returns nothing; (4) intermittent runs return `structured_output: null` with
  the answer as prose/markdown (even a markdown table) in `result`, crashing your
  parser; (5) you need reproducibility but there is no temperature/seed flag;
  (6) untrusted screenshots could prompt-inject the agent into reading other
  files (need a real sandbox, not just a doc note). Verified on claude CLI
  v2.1.179 with model claude-opus-4-8. Complements
  [[claude-p-subscription-subprocess]] (billing/cost/Haiku-turn/--setting-sources)
  and [[workflow-task-output-envelope]].
author: Claude Code
version: 1.1.0
date: 2026-06-17
---

# Using `claude -p` for vision + schema-constrained JSON

## Problem
You want Claude to read an image and return a typed JSON object your code can
consume. There is no `--image` flag; parsing the model's text answer is brittle;
the call sometimes returns no structured output and crashes; and if the image is
untrusted, the obvious recipe hands the model whole-filesystem read access.

## Context / Trigger conditions
- A perception step in a pipeline (screenshot auditing, OCR-like extraction).
- `envelope["result"]` is prose / a markdown table, not your JSON.
- A vision call hangs or returns nothing; or one run works and the next returns
  `structured_output: null`.
- You need determinism but `claude -p --help` shows no `--temperature`/`--seed`.
- The images come from an untrusted party (auditee uploads, scraped pages).

## Solution

### Preferred: inline base64 image + NO tools (sandboxed)
Send the image as a base64 content block over a **stream-json** stdin message and
grant **no tools** (`--allowedTools ""`). With no Read/Bash tool, a prompt-
injecting image cannot read or exfiltrate files. `--input-format stream-json`
requires `--output-format stream-json --verbose`; the outcome is the last line of
type `result`, whose `structured_output` holds your validated object.

```python
import base64, json, os, re, subprocess

_MEDIA = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
          ".gif": "image/gif", ".webp": "image/webp"}

def extract(text: str, image_paths: list[str], schema: dict,
            model="claude-opus-4-8", timeout=600, retries=2) -> dict:
    content = [{"type": "text", "text": text}]
    for p in image_paths:
        with open(p, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode()
        mt = _MEDIA.get(os.path.splitext(p)[1].lower(), "image/png")
        content.append({"type": "image",
                        "source": {"type": "base64", "media_type": mt, "data": b64}})
    stdin_msg = json.dumps({"type": "user",
                            "message": {"role": "user", "content": content}}) + "\n"
    cmd = ["claude", "-p", "--model", model,
           "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
           "--allowedTools", "",                      # no tools -> no filesystem access
           "--json-schema", json.dumps(schema)]
    last = None
    for _ in range(retries + 1):                       # retry transient flakes
        try:
            proc = subprocess.run(cmd, input=stdin_msg, capture_output=True,
                                  text=True, timeout=timeout)
            result = None
            for line in proc.stdout.splitlines():
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(o, dict) and o.get("type") == "result":
                    result = o                          # keep the last result line
            if result is None or result.get("is_error"):
                raise RuntimeError(str((result or {}).get("result"))[:200])
            data = result.get("structured_output") or _recover_json(result.get("result"))
            if not isinstance(data, dict):
                raise RuntimeError(f"no usable JSON: {str(result.get('result'))[:200]}")
            model_id = next((m for m in (result.get("modelUsage") or {})
                             if "haiku" not in m.lower()), model)   # ignore Haiku turn
            return {"data": data, "model_id": model_id}
        except (subprocess.TimeoutExpired, RuntimeError) as e:
            last = e
    raise last
```

### Simpler but UNSAFE: `@path` + Read tool
`claude -p ... --allowedTools "Read" --permission-mode bypassPermissions
--output-format json --json-schema '<schema>'` with an `@"/abs/path.png"` mention
in the prompt also does vision, and `structured_output` lands in the single JSON
envelope. But this grants the model whole-filesystem read access; scoping with
`--allowedTools 'Read(<dir>/**)'` does NOT block out-of-scope reads (Read is
auto-permitted in headless mode, verified). Use this only for trusted images.

### Recover JSON when structured_output is null
The model intermittently answers in prose with `structured_output: null`:

```python
def _recover_json(result):
    if not isinstance(result, str):
        return None
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", result, re.DOTALL)
    cand = m.group(1) if m else (result[result.find("{"): result.rfind("}") + 1] or None)
    try:
        out = json.loads(cand) if cand else None
        return out if isinstance(out, dict) else None
    except json.JSONDecodeError:
        return None
```

### Determinism without a temperature flag
There is no `--temperature`/`--seed`. Rely on the `--json-schema` constraint, run
extraction TWICE and compare the downstream DECISIONS (verdicts), not raw fields:
two passes differing only in confidence (a value vs `null`) should not count as
unstable; only a verdict flip should.

## Verification
- `structured_output` is a parsed dict matching the schema (verified live:
  extracted PR number/author off a GitHub screenshot with `--allowedTools ""`).
- With the inline method and no tools, an instruction inside the image cannot
  read other files (no tool to do so).
- Feeding long base64 on stdin avoids `ARG_MAX`.

## Notes
- Verified on claude CLI **v2.1.179**, model `claude-opus-4-8`; re-check
  `claude -p --help` if a flag is rejected on another version.
- `--input-format stream-json` requires `--output-format stream-json --verbose`.
- Every call also bills a hidden Haiku classifier turn (it appears in
  `modelUsage` alongside your model); pick the non-Haiku key.
- Cost ~ $0.28-0.39 per Opus vision call on a ~1.5 MB screenshot.
- For billing, `--setting-sources ''` to suppress host hooks, and bulk-fanout
  429 handling, see [[claude-p-subscription-subprocess]].
