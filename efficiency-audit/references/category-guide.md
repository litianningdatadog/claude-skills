# Phase 2 Category Interpretation Guide

The script pre-clusters results into categories. Groups are sorted by frequency; the first
entries are the highest-recurrence friction. Noise is filtered before extraction, so every
group is real input.

## `corrections`

Messages where the user redirected Claude. Each group carries:
- `count`/`sessions` — frequency and breadth.
- `top_project` — where it happened most; use to route the CLAUDE.md fix.
- `preceding_action` — what Claude did *immediately before* the correction (the causal
  trigger). **Use this** to write a rule targeting the specific behavior, not just the topic.

Draft a CLAUDE.md rule per high-count group using both `examples` and `preceding_action`:

> correction: "don't commit yet"  
> preceding_action: "Committed as `abc123`..."  
> → rule: `NEVER create a git commit without explicit instruction. Finish the task, show a diff, then ask.`

Rules must be imperative, specific, and scoped to the right CLAUDE.md via `top_project`.

## `missing_context`

Messages where the user re-explained stable facts. Candidates for CLAUDE.md project
instructions or `~/.claude/projects/.../memory/` entries. Use `top_project` to route.

## `slow_start_context`

Messages that orient Claude at session start. Ask: stable (always true) or transient
(task-specific)? Stable facts go in CLAUDE.md.

## `automation_candidates`

Recurring procedural intent ("always run X before Y"). Candidates for `settings.json`
hooks — use the `hookify:configure` skill.

## `terminal_title_not_configured` / `terminal_title_skill_missing`

See `references/terminal-title-check.md` for proposed rule text, routing, and post-apply note.

## `hook_errors`

Failing hooks (e.g. `exit=127`, unquoted `${CLAUDE_PLUGIN_ROOT}`). **Don't repair here.**
First check whether the `hook-doctor` skill is installed:

```bash
ls ~/.claude/plugins/cache/litianningdatadog-marketplace/hook-doctor/*/skills/hook-doctor/SKILL.md 2>/dev/null | grep -q . && echo "installed" || echo "not_installed"
```

- **Installed** → recommend running `/hook-doctor`. It scans all plugins, explains the blast
  radius, and applies fixes with explicit opt-in.
- **Not installed** → surface in Phase 3:
  > "Hook errors were found but the `hook-doctor` skill is not installed. Install it from
  > the [claude-marketplace repo](https://github.com/litianningdatadog/claude-marketplace): run
  > `/plugin install hook-doctor@claude-marketplace`, then re-run `/efficiency-audit`."

Errors are historical — they persist until they age out of the `--days` window. After
fixing, a fresh session plus a small `--days` re-run confirms no new failures appear.
