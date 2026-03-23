#!/bin/bash
set -euo pipefail

CLAUDE_DIR="$HOME/.claude"
PLUGIN_DIR="$HOME/development/projects/michaels-stack"

if [[ ! -d "$PLUGIN_DIR/.claude-plugin" ]]; then
    echo "ERROR: Plugin directory not found at $PLUGIN_DIR" >&2
    exit 1
fi

echo "Syncing ~/.claude → michaels-stack plugin..."

rsync -a --delete --exclude='.git' --exclude='debug/' --exclude='todos/' --exclude='projects/' --exclude='memory/' --exclude='settings.json' --exclude='settings.local.json' --exclude='credentials*' --exclude='ECC_MANIFEST.md' --exclude='*.log' "$CLAUDE_DIR/skills/" "$PLUGIN_DIR/skills/"
echo "  Skills synced"

rsync -a --delete "$CLAUDE_DIR/agents/" "$PLUGIN_DIR/agents/"
echo "  Agents synced"

rsync -a --delete "$CLAUDE_DIR/commands/" "$PLUGIN_DIR/commands/"
echo "  Commands synced"

rsync -a --delete "$CLAUDE_DIR/rules/" "$PLUGIN_DIR/rules/"
echo "  Rules synced"

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
