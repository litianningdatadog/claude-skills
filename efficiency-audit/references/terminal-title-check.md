# Terminal Title Check

Verifies that the `terminal-title` skill is wired up so session titles are set automatically.

## Detection (Phase 1)

```bash
# Is the skill installed?
ls ~/.claude/skills/terminal-title/scripts/set_title.sh 2>/dev/null && echo "installed" || echo "not_installed"

# Does the iterm2-notifications plugin also own the terminal title?
# If yes, any UserPromptSubmit hook will be overridden and the feature is blocked.
ls ~/.claude/plugins/cache/datadog-claude-plugins/iterm2-notifications 2>/dev/null \
  && echo "iterm2_conflict" || echo "no_conflict"

# Is a UserPromptSubmit hook already calling set_title.sh?
python3 -c "
import json, os
for p in ['~/.claude/settings.json', '.claude/settings.json', '.claude/settings.local.json']:
    try:
        d = json.load(open(os.path.expanduser(p)))
        for group in d.get('hooks', {}).get('UserPromptSubmit', []):
            for h in group.get('hooks', []):
                if 'set_title' in h.get('command', ''):
                    print('hook_exists'); raise SystemExit
    except (FileNotFoundError, json.JSONDecodeError):
        pass
print('hook_missing')
"
```

## Outcomes

**Skill not installed → Medium Impact**

> "The `terminal-title` skill is not installed. Copy it to `~/.claude/skills/terminal-title/`
> (or install via your plugin marketplace), then re-run `/efficiency-audit`."

Do **not** propose any hook — a hook referencing a missing script will error every session.

**Skill installed + `iterm2_conflict` → Low Impact / Known Limitation**

The `iterm2-notifications` plugin registers its own `UserPromptSubmit` hook that sets the
terminal title (badge, tab color, and `]0;` title) on every prompt. Plugin hooks run after
user hooks, so any `UserPromptSubmit` hook for `set_title.sh` will be overridden immediately.

Surface as an informational note in Phase 3, not as a fixable finding:

> "The `terminal-title` skill is installed, but the `iterm2-notifications` plugin already
> manages the terminal title via its own `UserPromptSubmit` hook and will override any
> hook you add. Task-specific titles (e.g. `Debug: Auth Flow`) are available by invoking
> the terminal-title skill manually mid-session."

**Skill installed + no conflict + `hook_missing` → High Impact (`terminal_title_not_configured`)**

Before drafting the checklist entry, **stop and ask the user**:

> "The hook would set a project+branch title (e.g. `claude-skills | main`) on every session
> start — reliable but not task-specific. Task-specific titles still require invoking the
> skill manually mid-session.
>
> Should I add the hook to:
> A) Global — `~/.claude/settings.json` (recommended — covers all projects)
> B) Current project only — `.claude/settings.local.json`"

Wait for the answer, then add to the **Proposed settings.json changes** section using
the `hookify:configure` skill pattern:

```json
"UserPromptSubmit": [
  {
    "matcher": "",
    "hooks": [
      {
        "type": "command",
        "command": "bash ~/.claude/skills/terminal-title/scripts/set_title.sh \"$(git branch --show-current 2>/dev/null || echo 'Session')\"",
        "timeout": 5
      }
    ]
  }
]
```

Route to **Automation Opportunities** in the Phase 3 report. Treat as **High Impact**.

After applying, add this post-apply note:

> "The hook takes effect immediately on the **next session start**. The title will show
> `<project> | <branch>` (e.g. `claude-skills | main`). For task-specific titles, invoke
> the `terminal-title` skill manually mid-session."

**Skill installed + no conflict + `hook_exists` → no finding.**
