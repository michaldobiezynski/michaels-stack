"""Minimal streamable-HTTP MCP client for the council-of-thinkers server.

Use when the session's mcp__council-of-thinkers__* tools are not connected but the
backend is running on :8766. Responses are SSE; we read the `data:` line.

Usage:
    python3 mcp_http_call.py tools
    python3 mcp_http_call.py call <tool_name> '<json-args>'
"""
import json, sys, urllib.request

URL = "http://127.0.0.1:8766/mcp"
HEADERS = {"Content-Type": "application/json",
           "Accept": "application/json, text/event-stream"}


def _post(body, session=None):
    h = dict(HEADERS)
    if session:
        h["mcp-session-id"] = session
    req = urllib.request.Request(URL, data=json.dumps(body).encode(),
                                 headers=h, method="POST")
    resp = urllib.request.urlopen(req, timeout=120)
    sid = resp.headers.get("mcp-session-id")
    out = None
    for line in resp.read().decode().splitlines():
        if line.startswith("data:"):
            out = json.loads(line[5:].strip())
    return out, sid


def session():
    body = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "curl", "version": "0"}}}
    _, sid = _post(body)
    h = dict(HEADERS); h["mcp-session-id"] = sid
    req = urllib.request.Request(
        URL,
        data=json.dumps({"jsonrpc": "2.0",
                         "method": "notifications/initialized"}).encode(),
        headers=h, method="POST")
    try:
        urllib.request.urlopen(req, timeout=30)
    except Exception:
        pass
    return sid


def call(method, params=None, sid=None):
    if sid is None:
        sid = session()
    out, _ = _post({"jsonrpc": "2.0", "id": 2, "method": method,
                    "params": params or {}}, sid)
    return out, sid


if __name__ == "__main__":
    cmd = sys.argv[1]
    sid = session()
    if cmd == "tools":
        out, _ = call("tools/list", {}, sid)
        for t in out["result"]["tools"]:
            print(t["name"], "::", (t.get("description") or "")[:90])
    elif cmd == "call":
        tool = sys.argv[2]
        args = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
        out, _ = call("tools/call", {"name": tool, "arguments": args}, sid)
        print(json.dumps(out))
