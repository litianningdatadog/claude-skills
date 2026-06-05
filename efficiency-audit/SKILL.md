---
name: efficiency-audit
description: "Analyzes recent Claude Code conversation transcripts to surface recurring inefficiencies, then produces a concrete improvement plan and applies it. Use when the user wants to improve their Claude Code workflow, reduce repeated corrections, eliminate missing-context frustration, or automate recurring patterns. Trigger phrases: 'improve my workflow', 'audit my usage', 'what am I repeating', 'efficiency audit', 'review my conversations', or any request to update CLAUDE.md based on observed patterns."
---

# Efficiency Audit

## Overview

Analyze recent Claude Code conversation history to identify friction patterns, then apply
concrete fixes: CLAUDE.md rule additions, memory entries, hook repairs, and settings
improvements. Pipeline: **analyze → report → propose → apply (with approval)**.

## Pipeline

### Phase 0: Check Intent

Before doing anything else, ask the user:

> "Run the standard efficiency audit, or do you have specific areas you'd like me to focus on?"

If they say "just run it" / "standard" / "as is" — proceed to Phase 1 with defaults.

If they provide ad-hoc requirements, note them and weave them into Phase 2 synthesis:
elevate matching findings to High Impact regardless of frequency, and call out whether
their stated concern is confirmed or not found in the data.

### Phase 1: Analyze

Run the analysis script to extract patterns from the last 30 days of conversations. Default
to scoping the audit to the **current project** so findings reflect the repo you're in —
pass the project's folder name to `--project` (it's matched as a substring of the stored
transcript path, which is the cwd with `/` replaced by `-`, e.g. `claude-skills`):

```bash
python3 ~/.claude/skills/efficiency-audit/scripts/analyze_conversations.py \
  --days 30 \
  --project "$(basename "$PWD")" \
  --output json \
  2>/dev/null
```

For a quick text preview, swap `--output text`:

```bash
python3 ~/.claude/skills/efficiency-audit/scripts/analyze_conversations.py \
  --days 30 \
  --project "$(basename "$PWD")" \
  --output text \
  2>/dev/null
```

To audit **all projects** instead (cross-project personal patterns, global CLAUDE.md or
memory candidates), drop the `--project` flag.

### Phase 2: Synthesize Findings

The script pre-clusters results: each category (`corrections`, `missing_context`,
`slow_start_context`, `automation_candidates`) is a list of groups, each with a `count`
(how many user messages matched), a `sessions` count (across how many distinct sessions),
and up to three `examples`. Groups are sorted by frequency, so the first entries are the
highest-recurrence friction. System-generated noise is already filtered out during
extraction (see "False Positive Filters" below), so every group represents real input.

Interpret each category:

**`corrections`** — Groups of messages where the user redirected or corrected Claude. The
`count`/`sessions` fields already give you the recurring *class* of mistake. Ask: what
CLAUDE.md rule or memory entry would have prevented this?

**`missing_context`** — Messages where the user re-explained context. Ask: what facts are
being re-introduced session after session? These belong in CLAUDE.md project instructions
or in `~/.claude/projects/.../memory/` as persistent memories.

**`slow_start_context`** — Messages that orient Claude at session start. Ask: which facts
are stable (always true) vs. transient (task-specific)? Stable facts go in CLAUDE.md.

**`automation_candidates`** — Messages expressing recurring procedural intent
("always run X before Y", "every time I commit..."). Ask: should this become a hook in
`settings.json`? Use the `hookify:configure` skill for hook additions.

**`hook_errors`** — Failing hooks reduce reliability silently. Each error includes hook
name, failing command, and stderr. Diagnose and fix where possible.

The most common cause is an **unquoted `${CLAUDE_PLUGIN_ROOT}`** in a plugin's `hooks.json`.
Recognize this signature:

```
exit=127  cmd=${CLAUDE_PLUGIN_ROOT}/scripts/<x>.sh
stderr: /bin/sh: /Users/<you>/Library/Application: No such file
```

`${CLAUDE_PLUGIN_ROOT}` resolves to the plugin's directory. In normal Claude Code that path
has no spaces so an unquoted command works; in **agent-mode (`sdk-ts`) sessions** the plugin
lives under `~/Library/Application Support/Claude/…`, whose space makes `/bin/sh` split the
path at `Application`. When you see this, tell the user what's happening and propose quoting
the **path token** (not the whole command) in the offending `hooks.json`:

```jsonc
"command": "${CLAUDE_PLUGIN_ROOT}/scripts/x.sh"          // bad
"command": "\"${CLAUDE_PLUGIN_ROOT}/scripts/x.sh\""      // good
"command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/x.py\""  // good: quote path, not command
```

Often the same bug affects *many* plugins in a marketplace — offer to scan and fix all of
them (see the "Troubleshooting" section of this skill's `README.md` for a ready-made script).
Note these errors are **historical**: they come from past transcripts and keep appearing until
they age out of the `--days` window. After fixing, re-run with a small `--days` (and a fresh
session) to confirm no *new* failures appear, and remind the user to push the fix upstream so
it survives plugin updates.

**`repeated_topics`** — High-frequency topic words reveal what the user spends time on.
Cross-reference with other categories to prioritize fixes.

### Phase 3: Produce a Prioritized Improvement Report

Present findings in this structure (omit sections with no findings):

```
## Efficiency Audit Report — <date>

### High Impact (apply immediately)
- Hook errors that fire on every session
- Correction groups with `count` >= 3 (or `sessions` >= 3)

### Medium Impact (apply with user review)
- CLAUDE.md additions for project-specific rules
- Memory entries for stable personal preferences

### Automation Opportunities
- Patterns that could become hooks or custom commands
- List each with proposed hook event and command

### Open Questions
- Patterns needing user input to interpret correctly
```

For each finding include: what was observed (1-2 example message quotes), which file to
change, and the exact proposed change as a diff or new content block.

### Phase 4: Apply Changes (with user approval)

Never apply changes silently. Show each proposed change, state which file it modifies,
then wait for explicit confirmation before writing.

Apply in this order:
1. Hook error fixes (most reliably broken, clearest impact)
2. Memory entries (user-local, lowest blast radius)
3. CLAUDE.md additions (affects all future sessions in the project)
4. settings.json additions (use `hookify:configure` skill for hook changes)

**Hook fixes need their own explicit opt-in.** Unlike CLAUDE.md/memory changes (which stay
inside the user's project or `~/.claude`), fixing a plugin hook edits files *outside* the
project — usually a shared marketplace clone under `~/.claude/plugins/marketplaces/…`. Before
touching those, state plainly that the edit:

- modifies a **shared/installed plugin**, not the user's repo;
- is a **local working-tree change** that a plugin update (`git pull`) can revert;
- has a **durable fix upstream** (a PR to the plugin's repo).

Then let the user choose: **(a)** fix locally now, **(b)** prepare the upstream fix, **(c)**
both, or **(d)** skip. Never edit a shared plugin clone or anything under
`~/Library/Application Support/` without that explicit choice — approval to change the user's
own project does not extend to files they didn't author.

For CLAUDE.md additions, append to the relevant project's CLAUDE.md or the global
`~/.claude/CLAUDE.md`. Use `~/.claude/projects/.../memory/` for personal preferences
that should not appear in a checked-in file.

## False Positive Filters

The script applies these filters automatically during extraction (`is_noise()` /
`NOISE_PATTERNS` in `analyze_conversations.py`), so they should not appear in the JSON.
They are system-generated, not real user friction:

- "This session is being continued from a previous conversation..." → context-compaction
- Messages starting with `<command-name>` / `<command-message>` / `<local-command-*>` tags
- Security review boilerplate injected by the `dd:mcp-security-review` skill
  ("Review this change for security vulnerabilities...")
- Code-review and skill-body injections ("Provide a code review...", "Base directory for
  this skill:...")
- Subagent dispatch messages from workflow orchestration

If a new noise format slips through, add its signature to `NOISE_PATTERNS` rather than
filtering by hand.

## Re-running the Audit

Run every 2–4 weeks to catch new patterns. After applying changes, note the current
baseline counts for `corrections` and `missing_context` so the next run can measure
whether friction decreased in those areas.
