# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

A collection of **Claude Code Skills**. Each skill is a self-contained directory that
extends Claude's capabilities with specialized workflows. There is no build system or
dependency manifest — skills are authored as Markdown + supporting scripts and consumed
directly by the Claude Code agent runtime. Scripts that have tests use stdlib `unittest`
(no third-party deps); run them from the script's directory, e.g.:

```bash
cd efficiency-audit/scripts && python3 -m unittest test_analyze_conversations
```

## Skill anatomy

A skill lives in its own top-level directory and consists of:

- `SKILL.md` — required. YAML frontmatter with two fields:
  - `name`: the skill's invocation slug (kebab-case, matches the directory name).
  - `description`: load-bearing. This is the **only** text the agent reads to decide
    whether to activate the skill, so it must pack in concrete trigger phrases and use
    cases. The Markdown body below the frontmatter is loaded *only after* activation and
    becomes the agent's operating instructions.
- `scripts/` — optional supporting code (e.g. Python) that the `SKILL.md` body invokes by
  absolute path. The body references scripts at their *installed* location
  (`~/.claude/skills/<name>/scripts/...`), not their path in this repo.

## Conventions when authoring or editing skills

- Write the body as a procedure for the agent to follow, not as end-user documentation.
  The `efficiency-audit` skill models this: a numbered, phased pipeline
  (analyze → synthesize → report → apply-with-approval).
- Front-load trigger phrases in the `description` — the agent never sees the body until the
  description has already matched.
- Scripts should degrade gracefully on malformed input (the audit script swallows
  `JSONDecodeError`/`OSError` per-line and per-file rather than aborting) since they parse
  user transcripts of unknown shape.
- When a skill mutates user state (CLAUDE.md, memory, `settings.json`, hooks), apply
  changes only after explicit user approval, lowest-blast-radius first.

## Running a skill's scripts during development

Scripts are plain executables and can be run directly for testing. Example:

```bash
python3 efficiency-audit/scripts/analyze_conversations.py --days 30 --output text 2>/dev/null
```

The `analyze_conversations.py` script scans `~/.claude/projects/**/*.jsonl` (Claude Code's
per-session transcript logs). Useful flags: `--days N`, `--project <substring>`,
`--output json|text`. Note the body of `SKILL.md` invokes it from the *installed* path
(`~/.claude/skills/...`), so test against the repo path while developing.
