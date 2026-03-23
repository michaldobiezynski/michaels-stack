#!/bin/bash
# Stop hook — fires when Claude finishes responding.
# Checks the transcript for evidence of both test streams.
# Non-blocking soft reminder via stderr.

INPUT=$(cat)
TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)

if [[ -z "$TRANSCRIPT" ]] || [[ ! -f "$TRANSCRIPT" ]]; then
  exit 0
fi

# Look for test execution evidence in the transcript
HAS_ACCEPTANCE=$(grep -cil -E '(acceptance|e2e|integration).*(test|spec|pass|fail)' "$TRANSCRIPT" 2>/dev/null)
HAS_UNIT=$(grep -cil -E '(unit|describe|it\(|test\(|func Test).*(test|spec|pass|fail)' "$TRANSCRIPT" 2>/dev/null)
HAS_SOURCE_EDIT=$(grep -cil -E '(Edit|Write|MultiEdit).*\.(ts|tsx|js|jsx|py|go)' "$TRANSCRIPT" 2>/dev/null)

# Only remind if source code was edited but tests might be missing
if [[ -n "$HAS_SOURCE_EDIT" ]]; then
  if [[ -z "$HAS_ACCEPTANCE" ]]; then
    echo "[ATDD] Source code was modified but no acceptance tests were detected in this session." >&2
  fi
  if [[ -z "$HAS_UNIT" ]]; then
    echo "[ATDD] Source code was modified but no unit tests were detected in this session." >&2
  fi
fi

exit 0
