#!/usr/bin/env bash
# Lists the chainable prompt-transform skill set with descriptions read live from each SKILL.md.
set -euo pipefail

SKILLS_DIR="${HOME}/.claude/skills"

print_group() {
  local title="$1"; shift
  printf '\n%s\n' "$title"
  local name file desc hint short
  for name in "$@"; do
    file="$SKILLS_DIR/$name/SKILL.md"
    if [[ -f "$file" ]]; then
      desc=$(sed -n 's/^description: //p' "$file" | head -1)
      hint=$(sed -n 's/^argument-hint: //p' "$file" | head -1)
      short="${desc%%. Use when*}"
      [[ "$short" != "$desc" ]] && short="${short}."
      printf '  /%-17s %s\n' "$name" "$short"
      [[ -n "$hint" ]] && printf '  %-18s args: %s\n' '' "$hint"
    else
      printf '  /%-17s MISSING (%s not found)\n' "$name" "$file"
    fi
  done
}

print_group 'One-shot explain transforms (argument = topic or text; blank = my previous answer):' \
  eli5 eli12 explain-analogy plain-english

print_group 'Response modes (stackable; "/name off" switches off):' \
  straight-answer red-team fact-check fan-out

print_group 'Engineering modes (stackable; "/name off" switches off):' \
  first-principles honest-report clean-output

printf '\nChain examples:\n'
printf '  /summarize-content <url>   then  /eli12\n'
printf '  /deep-research <question>  then  /fact-check audit\n'
printf '  Stack: /red-team + /straight-answer + /fact-check\n'
printf '  Stack: /first-principles + /honest-report + /clean-output\n'
