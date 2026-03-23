# Sync Settings Skill

Syncs Claude Code settings between local configuration and the GitHub backup repository.

## Triggers

- `/sync-settings` - Sync local changes to GitHub
- `/sync-settings pull` - Pull latest from GitHub to local
- "sync my claude settings"
- "backup my settings"
- "push my settings"

## Behaviour

### Default (push to remote)

1. Copy current settings from `~/.claude/` to `~/claude-settings/`
2. Check for changes with `git status`
3. If changes exist:
   - Stage all changes
   - Commit with descriptive message
   - Push to GitHub
4. Report what was synced

### Pull mode (`/sync-settings pull`)

1. Pull latest from GitHub
2. Run `restore.sh` to apply settings
3. Report what was updated

## Files Synced

- `~/.claude/CLAUDE.md` → Global instructions
- `~/.claude/settings.json` → Model, hooks, plugins config
- `~/.claude/settings.local.json` → Local permissions
- `~/.claude/hooks/` → Custom hook scripts
- `~/.claude/skills/` → Custom skills (excluding this one to avoid recursion)
- `~/.agents/skills/` → Agent skills

## Usage Examples

```
User: /sync-settings
Claude: [Copies settings, commits, pushes to GitHub]

User: /sync-settings pull
Claude: [Pulls from GitHub, runs restore.sh]

User: backup my claude settings
Claude: [Same as /sync-settings]
```

## Implementation

When invoked, execute the following:

### For push (default):

```bash
cd ~/claude-settings

# Copy settings
cp ~/.claude/CLAUDE.md .
cp ~/.claude/settings.json .
cp ~/.claude/settings.local.json .
cp -r ~/.claude/hooks/* hooks/
# Copy skills except sync-settings to avoid recursion
rsync -av --exclude='sync-settings' ~/.claude/skills/ skills/
rsync -av ~/.agents/skills/ agents-skills/

# Check for changes
if [ -n "$(git status --porcelain)" ]; then
    git add -A
    git commit -m "feat: (settings) sync settings $(date +%Y-%m-%d)"
    git push
    echo "Settings synced to GitHub"
else
    echo "No changes to sync"
fi
```

### For pull:

```bash
cd ~/claude-settings
git pull
./restore.sh
echo "Settings restored from GitHub"
```

## Notes

- The skill excludes itself from syncing to prevent recursion issues
- Always restart Claude Code after pulling to apply changes
- The GitHub repo must already exist (created during initial setup)
