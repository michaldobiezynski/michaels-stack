---
name: mcp-python-sdk-v2-mcpserver-api
description: |
  Write or smoke-test a Python MCP server against the official `mcp` SDK 2.x, where FastMCP
  was renamed and result fields went snake_case. Use when: (1) `from mcp.server.fastmcp import
  FastMCP` raises "No module named 'mcp.server.fastmcp'. This is mcp 2.x, where FastMCP was
  renamed to MCPServer", (2) writing a new stdio MCP server for Claude Code in Python with uv,
  (3) a tool must return text plus images (ImageContent) in one result, (4) you need a stdio
  client to test the server end to end (stdio_client + ClientSession), (5) `uv run --script
  server.py` seems to hang. Covers MCPServer, @tool(structured_output=False) for CallToolResult
  returns, mime_type / is_error / structured_content names, run(transport="stdio"), PEP 723
  inline dependencies and `claude mcp add --scope user`.
author: Claude Code
version: 1.0.0
date: 2026-09-10
---

# Official Python MCP SDK 2.x: MCPServer API

## Problem

Every tutorial and most training data show `from mcp.server.fastmcp import FastMCP`. On
`mcp>=2` that import raises a ModuleNotFoundError pointing at a migration guide, and several
field names and decorator options changed alongside the rename. Writing v1-style code wastes a
round of debugging; pinning `mcp<2` works but leaves you on a dead branch.

## Context / Trigger Conditions

- `ModuleNotFoundError: No module named 'mcp.server.fastmcp'. This is mcp 2.x, where FastMCP
  was renamed to MCPServer (from mcp.server.mcpserver import MCPServer) ...`
- Building a local stdio MCP server for Claude Code in Python (typically run with uv).
- A tool needs to return an image and a JSON summary in the same result.
- You want a scripted client to exercise the server rather than trusting `claude mcp get`.

Not for the third-party `fastmcp` package by jlowin, which is a different library with its own
API (see the fastmcp-* skills).

## Solution

### Server skeleton (single file, PEP 723 dependencies)

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=2,<3"]
# ///
from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, ImageContent, TextContent

mcp = MCPServer("name", instructions="one paragraph the client sees at initialise")

@mcp.tool()
def info() -> dict:                      # dict return -> structured_content automatically
    """Docstring becomes the tool description."""
    return {"ok": True}

@mcp.tool(structured_output=False)       # required when you return CallToolResult yourself
def render(path: str) -> CallToolResult:
    png = open(path, "rb").read()
    return CallToolResult(
        content=[
            TextContent(type="text", text="{...json...}"),
            ImageContent(type="image", data=base64.b64encode(png).decode(), mime_type="image/png"),
        ],
        is_error=False,
    )

if __name__ == "__main__":
    mcp.run(transport="stdio")           # transport moved from the constructor to run()
```

Verified names (introspect with `inspect.signature` and `Model.model_fields` if unsure):

| v1 | v2 |
| --- | --- |
| `mcp.server.fastmcp.FastMCP` | `mcp.server.mcpserver.MCPServer` |
| `FastMCP(..., transport=)` in constructor | `mcp.run(transport="stdio" or "sse" or "streamable-http")` |
| `ImageContent(mimeType=)` | `ImageContent(type="image", data=..., mime_type=)` |
| `CallToolResult(isError=)` | `CallToolResult(content=[...], is_error=, structured_content=)` |
| `Image(data=, format=)` helper | still exists as `mcp.server.mcpserver.Image(path= or data=, format=)` |

Sync `def` tools run on worker threads in v2, so blocking `subprocess.run` inside them is
fine; `asyncio.get_running_loop()` inside a sync tool is not.

### Register with Claude Code

```bash
claude mcp add --scope user NAME -- uv run --script /abs/path/server.py
claude mcp get NAME        # "Status: ✔ Connected" proves the process starts and initialises
```

### Scripted client smoke test

```python
import asyncio
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

async def main():
    params = StdioServerParameters(command="uv", args=["run", "--script", "/abs/server.py"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            print([t.name for t in (await s.list_tools()).tools])
            res = await s.call_tool("render", {"path": "/abs/x.png"})
            print(res.is_error, [c.type for c in res.content])   # e.g. False ['text', 'image']

asyncio.run(main())
```

Run it with `uv run --with 'mcp>=2,<3' python test_client.py`.

## Verification

- `claude mcp get NAME` shows Connected.
- The client script lists the tools and a call returns `is_error=False` with the content types
  you expect; a deliberately failing call returns `is_error=True`.

## Notes

- `uv run --script server.py` with no client attached starts the server on stdio and blocks
  forever; it is not a syntax check. Check syntax with `ast.parse` instead.
- Migrating from v1 without the pin: the error message names the new import; the field renames
  are the part that silently breaks (pydantic rejects `mimeType` and `isError`).
- Verified with mcp 2.2.0 on macOS with uv 0.10.

## References

- Migration guide: https://py.sdk.modelcontextprotocol.io/v2/migration/
- Worked example: ~/.claude/skills/blender/mcp/server.py (headless Blender server built on this API)
