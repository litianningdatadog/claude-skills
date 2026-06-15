# Routing Proposed Rules to the Right CLAUDE.md

Applies to CLAUDE.md rules drafted from transcript patterns (`corrections`,
`missing_context`, `slow_start_context`). Does **not** apply to:
- `settings.json` / hook changes (use `hookify:configure`)
- Terminal-title findings (see `terminal-title-check.md` for its own routing)
- Karpathy merge (Phase 5) — targets whichever CLAUDE.md the user selects
- File bloat remediation — routing determined by which file is over the threshold

For each transcript-derived rule, **always ask the user to confirm the target file**
before adding it to the checklist. Use the data signals to form a recommendation, but
never route silently — writing to `~/.claude/CLAUDE.md` affects every future session
across all projects and requires explicit consent.

## Forming a recommendation

Use the data to suggest a scope, then present it to the user:

- **Recommend global** (`~/.claude/CLAUDE.md`) when: pattern spans 3+ distinct projects,
  or the rule is inherently personal and project-agnostic (commit habits, tone preferences).
- **Recommend project** (`.claude/CLAUDE.md` or root `CLAUDE.md` in `top_project`) when:
  `top_project` accounts for ≥ 70% of matches and the rule reads as repo-specific behaviour.
- **No strong recommendation** when: 2–3 projects, no dominant one, or data is thin.

## Prompt format (always required)

Present the recommendation and wait for confirmation before adding to the checklist:

> "This rule could apply to:
> A) All projects — `~/.claude/CLAUDE.md` ← recommended / not recommended (reason)
> B) Current project only — `<path>/CLAUDE.md` ← recommended / not recommended (reason)
>
> Seen in: `dd-trace-js` (8×), `claude-skills` (1×). Which scope fits best?"

For a clear global recommendation:
> "A) `~/.claude/CLAUDE.md` ← **recommended** (seen across 5 projects — looks like a general habit)
> B) `.claude/CLAUDE.md` (current project only)"

For a clear project recommendation:
> "A) `~/.claude/CLAUDE.md` (would apply everywhere — data suggests this is repo-specific)
> B) `.claude/CLAUDE.md` ← **recommended** (8/10 corrections in dd-trace-js)"

Wait for the user's answer before adding the rule to the checklist.

## Checklist format

Each entry must carry the confirmed target:

```
- [ ] (project: dd-trace-js → .claude/CLAUDE.md) NEVER use worktrees — use the branch directly.
- [ ] (global → ~/.claude/CLAUDE.md) NEVER create a commit unless explicitly instructed.
```
