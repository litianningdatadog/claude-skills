---
name: efficiency-audit
description: "Analyzes recent Claude Code conversation transcripts to surface recurring inefficiencies, then produces a concrete improvement plan and applies it. Use when the user wants to improve their Claude Code workflow, reduce repeated corrections, eliminate missing-context frustration, or automate recurring patterns. Trigger phrases: 'improve my workflow', 'audit my usage', 'what am I repeating', 'efficiency audit', 'review my conversations', or any request to update CLAUDE.md based on observed patterns."
governance: "SOSA™ — Supervised Orchestrated Secured Agents. All writes to CLAUDE.md, MEMORY.md, and .claude/rules/ require explicit human approval before execution."
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

**Also run the file efficiency scorer** on the project's `CLAUDE.md` and `MEMORY.md` (if
they exist). This produces a hard numeric score using piecewise linear interpolation over
line-count control points {0→1.0, 300→1.0, 750→0.5, 5000→0.0}:

```bash
python3 ~/.claude/skills/efficiency-audit/scripts/score_efficiency.py \
  .claude/CLAUDE.md ~/.claude/CLAUDE.md ~/.claude/MEMORY.md \
  2>/dev/null
```

A score of **1.0** is optimal; **< 0.5** is a warning; **0.0** means the file exceeds
5000 lines and is a *Critical Context Blocker* that must be trimmed before further work.
Include these scores in the Phase 3 report alongside the friction findings. Any file
flagged as a Critical Context Blocker should be treated as **High Impact** regardless of
other findings.

### Phase 2: Synthesize Findings

The script pre-clusters results: each category (`corrections`, `missing_context`,
`slow_start_context`, `automation_candidates`) is a list of groups, each with a `count`
(how many user messages matched), a `sessions` count (across how many distinct sessions),
and up to three `examples`. Groups are sorted by frequency, so the first entries are the
highest-recurrence friction. System-generated noise is already filtered out during
extraction (see "False Positive Filters" below), so every group represents real input.

Interpret each category:

**`corrections`** — Groups of messages where the user redirected or corrected Claude. Each
group carries:
- `count`/`sessions` — how often and how broadly this class of mistake recurred.
- `top_project` — where it happened most; use this to route the CLAUDE.md fix.
- `preceding_action` — what Claude said or did *immediately before* the correction (the
  causal trigger). This is the most actionable field: use it to write a rule that targets
  the *specific behavior* rather than just the general topic.

For each high-count group, **draft a concrete proposed CLAUDE.md rule** using both the
correction text *and* the `preceding_action`. For example:

- correction: "don't commit yet"
- preceding_action: "Committed as `abc123`..."
- → rule: `NEVER create a git commit without explicit instruction. Finish the task, show a diff, then ask.`

Rules should be in imperative form, specific enough to prevent the observed behavior, and
scoped to the right project or global CLAUDE.md based on `top_project`.

**`missing_context`** — Messages where the user re-explained context. Ask: what facts are
being re-introduced session after session? These belong in CLAUDE.md project instructions
or in `~/.claude/projects/.../memory/` as persistent memories. Use `top_project` to route
the fix to the right CLAUDE.md.

**`slow_start_context`** — Messages that orient Claude at session start. Ask: which facts
are stable (always true) vs. transient (task-specific)? Stable facts go in CLAUDE.md.

**`automation_candidates`** — Messages expressing recurring procedural intent
("always run X before Y", "every time I commit..."). Ask: should this become a hook in
`settings.json`? Use the `hookify:configure` skill for hook additions.

**`hook_errors`** — Failing hooks reduce reliability silently. Each error includes hook
name, failing command, and stderr. A common signature is `exit=127` with stderr like
`/bin/sh: /Users/<you>/Library/Application: No such file` (an unquoted `${CLAUDE_PLUGIN_ROOT}`
that breaks in agent-mode). **Don't repair hooks from here** — recommend the **`hook-doctor`**
skill, which scans all installed plugins, explains the blast radius, and applies fixes with
explicit opt-in. Note these errors are **historical** (from past transcripts) and persist
until they age out of the `--days` window; after fixing, a fresh session plus a small
`--days` re-run confirms no *new* failures appear.

### Phase 3: Produce a Prioritized Improvement Report

**Before writing the report**, draft proposed fixes for the top findings:
- For each `corrections` group with `count` >= 3: use both `examples` and `preceding_action`
  to write a precise CLAUDE.md rule. The rule should name what Claude was *doing* when the
  correction fired, not just what the user said. Example:

  > correction: "don't commit, push to remote instead"
  > preceding_action: "Committed on `tianning.li/dd-trace-secure-random-test`"
  > → rule: `NEVER push to remote after committing unless explicitly asked. Commit and stop; let the user decide whether to push.`

- For each `missing_context` group with `sessions` >= 3: write a candidate CLAUDE.md fact.
- Show these drafts and ask the user to approve, edit, or skip each before proceeding to
  the full report. This is the highest-value output of the audit — don't skip it.

Present findings in this structure (omit sections with no findings):

```
## Efficiency Audit Report — <date>

### Proposed CLAUDE.md rules (approve/edit/skip each)
- [ ] (project: dd-trace-js) NEVER use worktrees — always use the branch directly.
- [ ] (global) NEVER create a new commit unless explicitly instructed; amend instead.

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

**Plugin hook fixes are out of scope here — hand off to `hook-doctor`.** Repairing a plugin
hook edits files *outside* the user's project (a shared marketplace clone), which is a
distinct blast radius with its own explicit opt-in. When the audit surfaces `hook_errors`,
recommend running the `hook-doctor` skill rather than editing `hooks.json` from this skill.

For CLAUDE.md additions, append to the relevant project's CLAUDE.md or the global
`~/.claude/CLAUDE.md`. Use `~/.claude/projects/.../memory/` for personal preferences
that should not appear in a checked-in file.

### Phase 5: Recommend Karpathy Behavioral Guidelines (opt-in)

After Phase 4 is complete (or if the user declines Phase 4 changes), present this offer
**once** — do not repeat it if already declined this session:

> "There's a set of Karpathy-inspired behavioral guidelines for Claude Code that address four
> common failure modes: silent assumptions, overengineering, unrelated edits, and unverified
> goals. They're based on Andrej Karpathy's observations — you can review them at:
> https://github.com/multica-ai/andrej-karpathy-skills/blob/main/CLAUDE.md
>
> Would you like me to merge these into your `CLAUDE.md`? I'll read your existing rules and
> the Karpathy guidelines and produce a structured, deduplicated result — not a blind append."

**If the user agrees, follow this merge procedure exactly:**

1. **Read** the user's current `CLAUDE.md` (global `~/.claude/CLAUDE.md` or project-level).
2. **Fetch** the Karpathy guidelines from
   `https://github.com/multica-ai/andrej-karpathy-skills/blob/main/CLAUDE.md`
   (use the WebFetch tool; fall back to asking the user to paste it if unavailable).
3. **Merge** using LLM reasoning — do NOT blindly append. The merge must:
   - **Deduplicate**: if the user already has a rule covering the same principle (e.g.
     "NEVER commit without asking" already covers "think before acting"), mark it as covered
     and skip adding the Karpathy variant.
   - **Preserve the user's existing rules verbatim** — never rephrase or reorder them.
   - **Add only what is genuinely new** — each Karpathy principle that isn't already covered
     by the user's rules gets added as a clearly-labelled block.
   - **Produce structured output** — the merged CLAUDE.md must have clear sections, not a
     flat list. Prefer grouping under headings like `## Coding discipline`,
     `## Task execution`, `## Change scope`.
4. **Show the full merged result** and a summary of what was added vs. already covered.
   Wait for the user to approve, edit, or reject before writing.
5. Apply via the Plan → Act → Verify cycle (Phase 4 rules apply here too).

**If the user declines**, respect it and do not ask again this session.

## Karpathy Behavioral Guardrails

**Read `references/karpathy-guardrails.md`** (installed at
`~/.claude/skills/efficiency-audit/references/karpathy-guardrails.md`) **whenever you need
to check your own behavior** against the four principles: Think Before Coding, Simplicity
First, Surgical Changes, Goal-Driven Execution. Flag violations inline as `[GUARDRAIL: ...]`.
These rules apply to every phase of the audit, not just Phase 5.

## Security & Governance (SOSA™)

**Read `references/governance.md`** (installed at
`~/.claude/skills/efficiency-audit/references/governance.md`) **before executing Phase 4.**
It contains the full SOSA™ rules: protected files, no-batching, show-before-write, and
no-silent-fallbacks. The Plan → Act → Verify cycle above enforces those rules procedurally.

## False Positive Filters

Noise is filtered automatically during extraction. If a new format slips through, read
`references/noise-filters.md` (installed at
`~/.claude/skills/efficiency-audit/references/noise-filters.md`) for the current filter
list and instructions for adding a new pattern to `NOISE_PATTERNS`.

## Re-running the Audit

Run every 2–4 weeks to catch new patterns. The script automatically saves a baseline after
each text-mode run (`~/.claude/efficiency-audit-baseline.json`) and shows deltas on the next
run (e.g. `CORRECTIONS (22 matches, was 30, -27% ↓)`). Use the delta to confirm that applied
CLAUDE.md rules are actually reducing friction before adding more.
