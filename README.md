# claude-skills

A collection of [Claude Code](https://claude.com/claude-code) **Skills** — self-contained
directories that extend Claude's capabilities with specialized, repeatable workflows.

Each skill is defined by a `SKILL.md` (the instructions Claude follows once the skill
activates) plus any supporting scripts. The `SKILL.md` is the canonical spec for what a
skill does; this README is the entry point for humans browsing or installing the repo.

## Skills

| Skill | What it does |
|-------|--------------|
| [`efficiency-audit`](efficiency-audit/) | Analyzes recent Claude Code transcripts to surface recurring friction — corrections, re-explained context, failing hooks — grouped by recurrence count and dominant project. Drafts concrete proposed `CLAUDE.md` rules for top findings before applying them with your approval. |
| [`hook-doctor`](hook-doctor/) | Inspects and repairs installed plugin hook configurations (`hooks.json`). Detects unquoted `${CLAUDE_PLUGIN_ROOT}` commands that fail in agent-mode, reports them, and applies safe idempotent fixes with explicit opt-in. |
| [`quicknotes`](quicknotes/) | Low-friction quick-note capture and management. Centralized markdown notes (`~/.quicknotes`) with date/project/dir metadata, tags, fuzzy search, references, and time/location reminders; completing a note deletes it. Capture via the `qn` CLI (instant), `/qn`, or natural language. |

## Marketplace

This repo is a public skill marketplace. Browse skills at **https://litianningdatadog.github.io/claude-skills/**

### Install the CLI (one-time)

```bash
curl -fsSL https://litianningdatadog.github.io/claude-skills/install.sh | bash
```

### Install a skill

```bash
claude-skills list                   # browse available skills
claude-skills install efficiency-audit
```

Skills are installed to `~/.claude/skills/` and activate automatically in the next Claude Code session.

### Commands

```bash
claude-skills add <url>      # add a marketplace source
claude-skills list           # list skills from all sources
claude-skills install <name> # install a skill
claude-skills update         # update all CLI-installed skills
claude-skills remove <name>  # remove a skill
claude-skills sources        # list registered sources
```

### Manual install (no CLI)

```bash
cp -R <skill-dir> ~/.claude/skills/
```

## Development

No build system or third-party dependencies — skills are Markdown plus scripts. Scripts
that ship tests use the Python standard-library `unittest`, run from the script's
directory. Per-skill setup, CLI usage, and test commands live in each skill's README.

## Contributing a new skill

1. Create a top-level directory named in kebab-case (matches the skill's `name`).
2. Add a `SKILL.md` with frontmatter (`name`, `description`) and a body written as a
   procedure for the agent to follow. Front-load concrete trigger phrases in
   `description` — it's the only text read when deciding whether to activate.
3. Put supporting code under `<skill>/scripts/`; reference it from `SKILL.md` by its
   installed path.
4. Add the skill to the table in the Skills section above.

See [`CLAUDE.md`](CLAUDE.md) for the conventions Claude follows when working in this repo.
