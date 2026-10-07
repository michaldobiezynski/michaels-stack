#!/bin/bash
set -euo pipefail

CLAUDE_DIR="$HOME/.claude"
PLUGIN_DIR="$HOME/development/projects/michaels-stack"

if [[ ! -d "$PLUGIN_DIR/.claude-plugin" ]]; then
    echo "ERROR: Plugin directory not found at $PLUGIN_DIR" >&2
    exit 1
fi

echo "Syncing ~/.claude → michaels-stack plugin..."

# Applied to EVERY rsync — the repo is public, so nothing secret-shaped may sync
EXCLUDES=(
    --exclude='.git'
    --exclude='debug/'
    --exclude='todos/'
    --exclude='projects/'
    --exclude='memory/'
    --exclude='settings.json'
    --exclude='settings.local.json'
    --exclude='credentials*'
    --exclude='.env*'
    --exclude='*.pem'
    --exclude='*.key'
    --exclude='ECC_MANIFEST.md'
    --exclude='*.log'
)

# Skills installed by `npx skills` are third-party, and their ~/.agents symlinks break on any
# other machine; synced/ and .trash/ hold Anthropic's claude.ai skills. No trailing slash on
# the patterns, so symlinks match too. Excluded names also survive --delete, which keeps the
# vendored skills/to-issues copy in place.
SKILL_EXCLUDES=(--exclude='/synced' --exclude='/.trash')
SKILL_LOCK="$HOME/.agents/.skill-lock.json"
if [[ -f "$SKILL_LOCK" ]]; then
    command -v jq >/dev/null || { echo "ERROR: jq is needed to read $SKILL_LOCK" >&2; exit 1; }
    while IFS= read -r name; do
        SKILL_EXCLUDES+=(--exclude="/$name")
    done < <(jq -r '.skills | keys[]' "$SKILL_LOCK")
fi

rsync -a --delete "${EXCLUDES[@]}" "${SKILL_EXCLUDES[@]}" "$CLAUDE_DIR/skills/" "$PLUGIN_DIR/skills/"
echo "  Skills synced"

rsync -a --delete "${EXCLUDES[@]}" "$CLAUDE_DIR/agents/" "$PLUGIN_DIR/agents/"
echo "  Agents synced"

rsync -a --delete "${EXCLUDES[@]}" "$CLAUDE_DIR/commands/" "$PLUGIN_DIR/commands/"
echo "  Commands synced"

rsync -a --delete "${EXCLUDES[@]}" "$CLAUDE_DIR/rules/" "$PLUGIN_DIR/rules/"
echo "  Rules synced"

if [[ -d "$CLAUDE_DIR/reference" ]]; then
    rsync -a --delete "${EXCLUDES[@]}" "$CLAUDE_DIR/reference/" "$PLUGIN_DIR/reference/"
    echo "  Reference synced"
fi

for script in claudeception-activator.sh spec-reminder.sh test-stream-check.sh; do
    if [[ -f "$CLAUDE_DIR/hooks/$script" ]]; then
        cp "$CLAUDE_DIR/hooks/$script" "$PLUGIN_DIR/scripts/$script"
    fi
done
echo "  Hook scripts synced"

cp "$CLAUDE_DIR/CLAUDE.md" "$PLUGIN_DIR/CLAUDE.md"
echo "  CLAUDE.md synced"

cd "$PLUGIN_DIR"

if git diff --quiet && git diff --cached --quiet && [[ -z "$(git ls-files --others --exclude-standard)" ]]; then
    echo "No changes detected — plugin is up to date."
    exit 0
fi

echo ""
echo "Changes detected:"
git status --short

echo ""
echo "To publish: cd $PLUGIN_DIR && git add -A && git commit -m 'chore: (plugin) sync from ~/.claude' && git push"
