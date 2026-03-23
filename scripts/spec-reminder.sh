#!/bin/bash
# Soft reminder before code writes.
# Non-blocking (exit 0) — injects a reminder into Claude's context via stderr.
# Claude's skill instructions handle the actual validation logic.

# Read tool input from stdin
INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // empty' 2>/dev/null)

# Only remind for source files, not test files or config
if [[ -n "$FILE_PATH" ]]; then
  # Skip test files — those are expected during TDD
  if [[ "$FILE_PATH" == *test* ]] || [[ "$FILE_PATH" == *spec* ]] || [[ "$FILE_PATH" == *_test.go ]]; then
    exit 0
  fi

  # Skip config and non-source files
  if [[ "$FILE_PATH" == *.json ]] || [[ "$FILE_PATH" == *.yml ]] || \
     [[ "$FILE_PATH" == *.yaml ]] || [[ "$FILE_PATH" == *.toml ]] || \
     [[ "$FILE_PATH" == *.md ]] || [[ "$FILE_PATH" == *.lock ]]; then
    exit 0
  fi

  # Soft reminder for source file writes
  echo "[ATDD] Writing source file: $FILE_PATH — have acceptance criteria been confirmed with the user?" >&2
fi

exit 0
