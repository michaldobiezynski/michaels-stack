---
name: fastmcp-tool-decorator-returns-callable
description: |
  Test FastMCP @mcp.tool()-decorated functions by calling them directly. Use
  when: (1) writing pytest coverage for a FastMCP tool wrapper and unsure if you
  can invoke/monkeypatch it; (2) you are about to justify a missing test with
  "FastMCP wraps the decorated function so it is not directly callable" (this is
  FALSE in FastMCP 3.x); (3) a codebase uses separate `_impl` functions "to
  bypass FastMCP middleware" and you assumed the public @mcp.tool() name is a
  non-callable Tool object. In FastMCP 3.x, @mcp.tool() RETURNS THE ORIGINAL
  FUNCTION (registration is a side effect), so the decorated name is a plain
  callable you can call and monkeypatch in tests.
author: Claude Code
version: 1.0.0
date: 2026-06-22
---

# FastMCP @mcp.tool() returns the original callable

## Problem

It is easy to assume `@mcp.tool()` replaces a function with a non-callable
`Tool`/`FunctionTool` object (the way some frameworks' decorators do), and
therefore to skip unit-testing the wrapper's behaviour with a comment like
"verified by inspection, since FastMCP wraps the decorated function so it is not
directly callable." That assumption is wrong for FastMCP 3.x and leads to a real
coverage gap: a wrapper that drops/changes an argument would regress silently.

## Context / Trigger conditions

- Writing tests for code shaped like:
  ```python
  @mcp.tool()
  def my_tool(a, b):
      return _my_impl(a, b, created_by=_resolve_thing())
  ```
- You want to assert the wrapper threads a resolved/injected value into the impl.
- The repo has a convention of importing `_impl` functions directly in tests
  "to bypass any FastMCP middleware" — useful, but NOT because the wrapper is
  uncallable.

## Solution

In FastMCP 3.x (verified against fastmcp 3.3.1) `@mcp.tool()` returns the
original function; registering it with the server is a side effect. So the
module-level name remains a plain callable:

```python
from council_mcp import server as srv
type(srv.my_tool)            # <class 'function'>
callable(srv.my_tool)        # True
hasattr(srv.my_tool, "fn")   # False
srv.my_tool(3, 4)            # runs the wrapper body directly
```

Therefore you can unit-test the wrapper directly: monkeypatch its dependencies
and assert it threads the resolved value:

```python
def test_wrapper_threads_resolved_value(monkeypatch):
    captured = {}
    monkeypatch.setattr(srv, "_resolve_thing", lambda: "SENTINEL")
    monkeypatch.setattr(srv, "_my_impl", lambda *a, **k: captured.update(k) or {})
    srv.my_tool("a", "b")
    assert captured["created_by"] == "SENTINEL"
```

If you genuinely need to know for a different FastMCP version, introspect rather
than assume:

```bash
python -c "import mymodule as m; print(type(m.my_tool), callable(m.my_tool), hasattr(m.my_tool,'fn'))"
```

## Verification

The wrapper call runs the real body (you can confirm by monkeypatching its
callee and observing the captured kwargs). `type(...) is function` and
`callable(...) is True` confirm it is not a wrapped Tool object.

## Notes

- Keeping a separate `_impl` seam is still worthwhile: it lets tests bypass any
  FastMCP middleware/auth and avoids running real retrieval. But the
  justification is "avoid middleware / heavy deps", NOT "the wrapper can't be
  called".
- Do not write a test docstring that asserts the wrapper is uncallable — it is a
  false statement that discourages the next maintainer from adding the guard.
- Behaviour could differ in a future major (FastMCP 4.x); re-introspect if the
  pinned version changes.
