---
name: macos-httpserver-getfqdn-stall
description: |
  Fix a ~35s silent stall when constructing Python's http.server.HTTPServer (or
  anything built on it) on macOS. Use when: (1) a test or script using HTTPServer
  is mysteriously slow (tens of seconds) with no error, (2) profiling shows the
  time is in server construction/bind, not in request handling, (3) TestCase
  round-trips against a local server take ~35s while GET/POST themselves are
  milliseconds. Cause: HTTPServer.server_bind calls socket.getfqdn(), whose
  reverse-DNS lookup can hang until timeout on macOS. Fix: subclass and skip it.
author: Claude Code
version: 1.0.0
date: 2026-08-28
---

# macOS HTTPServer getfqdn stall

## Problem

`http.server.HTTPServer(("127.0.0.1", port), Handler)` can take ~35 seconds to construct on macOS with certain DNS configurations. Nothing errors; the process just sits in `server_bind`. Requests, once serving, are fast - so the symptom usually presents as "this test takes 35s" and gets misattributed to the request path.

## Context / Trigger Conditions

- A pytest using a threaded local HTTPServer reports ~35s for one test; `--durations` points at it; timing the pieces shows construction ~35s, GET/POST ~0.01s.
- Any script that binds a local stdlib HTTP server appears to hang for tens of seconds at startup.

## Solution

`HTTPServer.server_bind` calls `socket.getfqdn(host)` to populate `server_name`; the reverse-DNS lookup blocks. For loopback-only servers, skip it:

```python
import socketserver
from http.server import HTTPServer

class LocalHTTPServer(HTTPServer):
    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name = self.server_address[0]
        self.server_port = self.server_address[1]
```

Related stdlib trap in the same family: `BaseHTTPRequestHandler.address_string()` also does reverse DNS on some paths - override `log_message`/`address_string` if per-request logging is slow rather than construction.

## Verification

Verified 28/08/2026: test suite dropped from 35.9s to 0.89s after the subclass; direct timing showed `make_server` 35.00s before, GET 0.01s, POST 0.00s.

## Notes

- Diagnose by timing construction, first request and shutdown separately before touching handler code; the stall location is counter-intuitive.
- Binding `""` or `"0.0.0.0"` for non-loopback use: still safe to skip getfqdn - `server_name` only feeds CGI-style environment fields most handlers never use.
