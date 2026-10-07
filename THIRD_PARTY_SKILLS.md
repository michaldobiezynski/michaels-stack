# Third-party skills

Some commands here call skills from [mattpocock/skills](https://github.com/mattpocock/skills) (MIT). They are not copied into this repo. Install them with:

```bash
npx skills@latest add mattpocock/skills -g -a claude-code --skill grill-me grill-with-docs improve-codebase-architecture prototype setup-matt-pocock-skills tdd triage pr retro writing-for-agents diagnosing-bugs
```

`/feature` needs `pr` for its Phase 5 PR body. It also needs `to-issues` for Phase 8, which upstream removed in v1.1.0. A copy of `to-issues` lives in `skills/to-issues/` with its MIT licence.
