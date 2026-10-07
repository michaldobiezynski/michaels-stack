#!/usr/bin/env bash
# Run a bpy script in headless Blender and surface only what matters.
#
# Usage: blender_run.sh [--blend FILE.blend] SCRIPT.py [-- script args...]
# Env:   BLENDER        path to the Blender binary (default: Homebrew cask location)
#        BLENDER_FLAGS  extra Blender flags inserted before --python (e.g. "-E CYCLES")
#        BLENDER_LOG    where to write the full Blender log (default: a temp file)
#
# Exit status is Blender's own. --python-exit-code 1 makes a Python exception
# exit non-zero; without it Blender exits 0 even when the script crashes.
set -uo pipefail

BLENDER="${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}"

blend=""
if [[ "${1:-}" == "--blend" ]]; then
  blend="${2:?--blend needs a path}"
  shift 2
fi
script="${1:?usage: blender_run.sh [--blend FILE.blend] SCRIPT.py [-- args...]}"
shift
[[ "${1:-}" == "--" ]] && shift

if [[ ! -x "$BLENDER" ]]; then
  echo "Blender binary not found at $BLENDER (set BLENDER=/path/to/Blender)" >&2
  exit 127
fi
if [[ ! -f "$script" ]]; then
  echo "Script not found: $script" >&2
  exit 2
fi

log="${BLENDER_LOG:-$(mktemp -t blender_run)}"

args=(-b --factory-startup)
[[ -n "$blend" ]] && args+=("$blend")
# shellcheck disable=SC2206  # BLENDER_FLAGS is intentionally word-split
args+=(${BLENDER_FLAGS:-} --python-exit-code 1 --python "$script" -- "$@")

"$BLENDER" "${args[@]}" >"$log" 2>&1
status=$?

if [[ $status -eq 0 ]]; then
  grep -E '^RESULT |\| Saved: ' "$log" || echo "(script printed no RESULT line; see $log)"
else
  echo "Blender exited $status. Last 40 lines of $log:" >&2
  tail -n 40 "$log" >&2
fi
echo "log: $log" >&2
exit "$status"
