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

**Session setup check — terminal title:** Read `references/terminal-title-check.md`
(installed at `${PLUGIN_ROOT}/references/terminal-title-check.md`) for
the detection commands, outcome interpretation, proposed rule text, and post-apply note.

**Path resolver — run this first to set `PLUGIN_ROOT`:**

```bash
PLUGIN_ROOT=$(ls -dt ~/.claude/plugins/cache/litianningdatadog-marketplace/efficiency-audit/*/ 2>/dev/null | head -1)
```

Use `${PLUGIN_ROOT}` in all subsequent commands to reference scripts and reference files.

Run the analysis script to extract patterns from the last 30 days of conversations. Default
to scoping the audit to the **current project** so findings reflect the repo you're in —
pass the project's folder name to `--project` (matched as a substring of the stored
transcript path, which is the cwd with `/` replaced by `-`, e.g. `claude-marketplace`):

```bash
python3 "${PLUGIN_ROOT}/scripts/analyze_conversations.py" \
  --days 30 \
  --project "$(basename "$PWD")" \
  --output json \
  2>/dev/null
```

To audit **all projects** instead, drop the `--project` flag. For a text preview, swap
`--output text`.

**Also run the file efficiency scorer** on the project's `CLAUDE.md` and `MEMORY.md` (if
they exist). This produces a hard numeric score using piecewise linear interpolation over
line-count control points {0→1.0, 300→1.0, 750→0.5, 5000→0.0}:

```bash
MEMORY_MD=$(python3 "${PLUGIN_ROOT}/scripts/resolve_memory_path.py" 2>/dev/null)
python3 "${PLUGIN_ROOT}/scripts/score_efficiency.py" \
  .claude/CLAUDE.md ~/.claude/CLAUDE.md "$MEMORY_MD" \
  2>/dev/null
```

A score of **1.0** is optimal; **< 0.5** is a warning; **0.0** means the file exceeds
5000 lines and is a *Critical Context Blocker* that must be trimmed before further work.
Include these scores in the Phase 3 report. Any Critical Context Blocker is **High Impact**
regardless of other findings.

### Phase 2: Synthesize Findings

Read `references/category-guide.md` (installed at
`${PLUGIN_ROOT}/references/category-guide.md`) for the interpretation
of each output category (`corrections`, `missing_context`, `slow_start_context`,
`automation_candidates`, `terminal_title_*`, `hook_errors`) and rule-drafting guidance.

### Phase 3: Produce a Prioritized Improvement Report

**Before writing the report**, draft proposed fixes for the top findings:
- For each `corrections` group with `count` >= 3: draft a precise CLAUDE.md rule using
  both `examples` and `preceding_action` (see `references/category-guide.md`).
- For each `missing_context` group with `sessions` >= 3: write a candidate CLAUDE.md fact.
- Show these drafts and ask the user to approve, edit, or skip each. This is the
  highest-value output — don't skip it.

**Routing each proposed rule:** Read `references/claude-md-routing.md` (installed at
`${PLUGIN_ROOT}/references/claude-md-routing.md`) for the three scope
tiers (global / project-specific / ambiguous), when to ask the user, and the checklist
entry format.

Present findings in this structure (omit sections with no findings):

```
## Efficiency Audit Report — <date>

### Proposed CLAUDE.md rules (approve/edit/skip each)
- [ ] (project: dd-trace-js) NEVER use worktrees — always use the branch directly.
- [ ] (global) NEVER create a new commit unless explicitly instructed; amend instead.
- [ ] (ask user) NEVER add debug logging without cleaning up before commit.

### High Impact (apply immediately)
- Hook errors that fire on every session
- `terminal_title_skill_missing` — terminal-title skill not installed; recommend installing and re-running audit
- `terminal_title_not_configured` — terminal-title skill installed but no CLAUDE.md rule enforces it
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

**Plan → Act → Verify** — follow this cycle for every change:
1. **Plan:** State exactly which file will be modified and show the full proposed diff or new
   content block. Do not begin writing until the user confirms.
2. **Act:** Apply only the approved change. Never batch unapproved changes into the same write.
3. **Verify:** After writing, confirm the file contains what was intended and report back.

Never apply changes silently. For each proposed change, state which file it modifies,
then **stop and wait for explicit confirmation** before writing.

Apply in this order:
1. Memory entries (user-local, lowest blast radius)
2. CLAUDE.md additions (affects all future sessions in the project)
3. settings.json additions (use `hookify:configure` skill for hook changes)

**Plugin hook fixes are out of scope here — hand off to `hook-doctor`.** When the audit
surfaces `hook_errors`, recommend running that skill rather than editing `hooks.json` here.

For CLAUDE.md additions, append to the relevant project's CLAUDE.md or the global
`~/.claude/CLAUDE.md`. Use `~/.claude/projects/.../memory/` for personal preferences
that should not appear in a checked-in file.

### Phase 5: Recommend Karpathy Behavioral Guidelines (opt-in)

After Phase 4 is complete (or if the user declines), present this offer **once**:

> "There's a set of Karpathy-inspired behavioral guidelines for Claude Code that address four
> common failure modes: silent assumptions, overengineering, unrelated edits, and unverified
> goals. Would you like me to merge these into your `CLAUDE.md`? I'll produce a structured,
> deduplicated result — not a blind append."

If the user agrees, follow the merge procedure in `references/karpathy-guardrails.md`
(Phase 5 section). If they decline, respect it and do not ask again this session.

## Karpathy Behavioral Guardrails

**Read `references/karpathy-guardrails.md`** (installed at
`${PLUGIN_ROOT}/references/karpathy-guardrails.md`) **whenever you need
to check your own behavior** against the four principles. Flag violations as `[GUARDRAIL: ...]`.
These rules apply to every phase of the audit, not just Phase 5.

## Security & Governance (SOSA™)

**Read `references/governance.md`** (installed at
`${PLUGIN_ROOT}/references/governance.md`) **before executing Phase 4.**
It contains the full SOSA™ rules: protected files, no-batching, show-before-write, and
no-silent-fallbacks. The Plan → Act → Verify cycle above enforces those rules procedurally.

## False Positive Filters

Noise is filtered automatically during extraction. If a new format slips through, read
`references/noise-filters.md` (installed at
`${PLUGIN_ROOT}/references/noise-filters.md`) for the current filter
list and instructions for adding a new pattern to `NOISE_PATTERNS`.

## File Bloat Remediation (Recipe Book Principle)

If `CLAUDE.md` exceeds 200 lines after Phase 1, **read `references/recipe-book.md`**
(installed at `${PLUGIN_ROOT}/references/recipe-book.md`) for the full
4-step procedure. Run this *before* proposing new audit rules.

## Re-running the Audit

Run every 2–4 weeks to catch new patterns. The script automatically saves a baseline after
each text-mode run (`~/.claude/efficiency-audit-baseline.json`) and shows deltas on the next
run (e.g. `CORRECTIONS (22 matches, was 30, -27% ↓)`). Use the delta to confirm that applied
CLAUDE.md rules are actually reducing friction before adding more.
