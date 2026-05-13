---
name: browser-use-ollama-local-setup
description: |
  Fix Browser Use 0.12.x + Ollama local model integration issues. Use when:
  (1) ChatOllama rejects num_ctx parameter — must use ollama_options dict instead,
  (2) LLM call timed out after 75 seconds with local models — increase llm_timeout to 300+,
  (3) Agent hits "5 consecutive failures" due to timeouts with large DOM content,
  (4) Setting up browser automation with local Ollama models (Qwen 3, Llama, etc.) on Apple Silicon.
  Covers ChatOllama API differences, timeout tuning for local inference, and step_timeout configuration.
author: Claude Code
version: 1.0.0
date: 2026-03-30
---

# Browser Use 0.12.x + Ollama Local Model Setup

## Problem
Browser Use's ChatOllama wrapper has a different API than langchain-ollama's ChatOllama.
Additionally, default timeouts (75s llm_timeout, 180s step_timeout) are far too short for
local models running on consumer hardware, causing cascading failures during DOM-heavy steps.

## Context / Trigger Conditions
- Using Browser Use 0.12.x with Ollama for local LLM inference
- Error: `TypeError` on `num_ctx` parameter to ChatOllama
- Error: `LLM call timed out after 75 seconds. Keep your thinking and output short.`
- Error: `Stopping due to N consecutive failures` — all failures are timeouts
- Using 32B+ parameter models on Apple Silicon (M1/M2/M3/M4/M5 Pro/Max/Ultra)
- Agent works for initial simple steps but fails after clicking into complex pages

## Solution

### 1. ChatOllama API — use `ollama_options` for model parameters

Browser Use's native ChatOllama does NOT accept `num_ctx` as a direct parameter.
Use `ollama_options` dict instead:

```python
# WRONG — will raise TypeError
from browser_use import ChatOllama
llm = ChatOllama(model="qwen3:32b", num_ctx=32000)

# CORRECT — Browser Use 0.12.x
from browser_use import ChatOllama
llm = ChatOllama(
    model="qwen3:32b",
    ollama_options={"num_ctx": 32000},
)
```

Check the actual signature:
```python
import inspect
from browser_use import ChatOllama
print(inspect.signature(ChatOllama.__init__))
# (self, model, host, timeout, client_params, ollama_options)
```

### 2. Increase llm_timeout for local models

Local 32B models on Apple Silicon run at ~13 tokens/s. After the agent reads a large
DOM (e.g., a complex SPA page), the model needs to process thousands of input tokens
and generate a structured tool-call response. The default 75s is insufficient.

```python
agent = Agent(
    task=instructions,
    llm=llm,
    browser_session=browser_session,
    controller=controller,
    use_vision=False,
    llm_timeout=300,      # 300s for 32B models (default: 75s)
    step_timeout=360,     # Must be > llm_timeout (default: 180s)
    max_failures=5,
)
```

### 3. Timeout guidelines by model size

| Model Size | Apple Silicon | llm_timeout | step_timeout |
|-----------|--------------|-------------|-------------|
| 7-8B      | M1+          | 120s        | 180s        |
| 14B       | M1 Pro+      | 180s        | 240s        |
| 32B       | M2 Pro+ (32GB+) | 300s     | 360s        |
| 70B       | M2 Ultra+ (128GB+) | 600s  | 720s        |

### 4. Warm up the model before first attempt

First inference after model load takes significantly longer (loading into GPU memory):

```bash
ollama run qwen3:32b "Reply with only: OK" --verbose
```

This pre-loads the model and gives you actual tokens/sec for timeout tuning.

## Verification

After applying fixes, run a single attempt. You should see:
- No `TypeError` on ChatOllama construction
- Steps completing without timeout errors
- `error: none` in the output (even if the challenge isn't solved)

```
result: failed      # OK — plumbing works
time_seconds: ...
steps_taken: ...
error: none         # THIS is the key indicator — no crashes
```

## Example

Full working setup for Browser Use 0.12.5 + Qwen 3 32B:

```python
from browser_use import Agent, ChatOllama, Controller
from browser_use.browser.session import BrowserSession

llm = ChatOllama(
    model="qwen3:32b",
    ollama_options={"num_ctx": 32000},
)

browser_session = BrowserSession(headless=True)
controller = Controller()

agent = Agent(
    task="Navigate to example.com and read the page title",
    llm=llm,
    browser_session=browser_session,
    controller=controller,
    use_vision=False,
    max_actions_per_step=3,
    max_failures=5,
    llm_timeout=300,
    step_timeout=360,
)

history = await agent.run(max_steps=15)
```

## Notes
- `use_vision=False` is mandatory for Ollama — vision models cannot do tool calling
  simultaneously (ollama/ollama#8626)
- Browser Use's `ChatOllama` is different from `langchain_ollama.ChatOllama` — check
  which one you're importing
- The `ollama_options` dict accepts any Ollama API option: `num_ctx`, `temperature`,
  `top_p`, `num_predict`, etc.
- If `from browser_use import ChatOllama` fails, fall back to `langchain_ollama` which
  DOES accept `num_ctx` directly: `uv add langchain-ollama`
- `step_timeout` must always be greater than `llm_timeout` or you get step-level kills
  before the LLM has a chance to respond

## References
- Browser Use GitHub: https://github.com/browser-use/browser-use
- Ollama vision + tool calling limitation: https://github.com/ollama/ollama/issues/8626
- Qwen 3 model card: https://ollama.com/library/qwen3
