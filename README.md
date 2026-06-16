# claude-marketplace

A collection of [Claude Code](https://claude.com/claude-code) **plugins** — installable via the `litianningdatadog-marketplace` plugin marketplace. Each plugin delivers a skill that extends Claude's capabilities with a specialized, repeatable workflow.

Each plugin has a `.claude-plugin/plugin.json` manifest and a `skills/<name>/SKILL.md` that becomes Claude's operating instructions once the skill activates. Supporting scripts live under `<plugin>/scripts/`. This README is the entry point for humans browsing or installing the repo.

## Plugins

| Skill | What it does |
|-------|--------------|
| [`efficiency-audit`](efficiency-audit/) | Analyzes recent Claude Code transcripts to surface recurring friction — corrections, re-explained context, tool-call failures, failing hooks — grouped by recurrence count and dominant project. LLM synthesis drafts ranked `CLAUDE.md` rules with token-savings estimates; idempotent marker blocks prevent duplicate accumulation across re-runs. |
| [`hook-doctor`](hook-doctor/) | Inspects and repairs installed plugin hook configurations (`hooks.json`). Detects unquoted `${CLAUDE_PLUGIN_ROOT}` commands that fail in agent-mode, reports them, and applies safe idempotent fixes with explicit opt-in. |
| [`quicknotes`](quicknotes/) | Low-friction quick-note capture and management. Centralized markdown notes (`~/.quicknotes`) with date/project/dir metadata, tags, fuzzy search, references, and time/location reminders; completing a note deletes it. Capture via the `qn` CLI (instant), `/qn`, or natural language. |

## Installing plugins

This repo is a Claude Code plugin marketplace. Add it once, then install skills à la carte:

```bash
# Add the marketplace (once per machine)
/plugin marketplace add litianningdatadog/claude-marketplace

# Install skills
/plugin install efficiency-audit@litianningdatadog-marketplace
/plugin install hook-doctor@litianningdatadog-marketplace
/plugin install quicknotes@litianningdatadog-marketplace
```

Plugins auto-update when you run `/plugin marketplace update`. Each skill activates
automatically when your request matches the triggers in its `SKILL.md` description.

## Development

No build system or third-party dependencies — skills are Markdown plus scripts. Scripts
that ship tests use the Python standard-library `unittest`, run from the script's
directory. Per-skill setup, CLI usage, and test commands live in each skill's README.

## Contributing a new skill

1. Create a top-level directory named in kebab-case (matches the skill's `name`).
2. Add a `.claude-plugin/plugin.json` with `name` and `description`.
3. Add `skills/<name>/SKILL.md` as the agent procedure. Front-load trigger phrases in
   the frontmatter `description` — it's the only text read when deciding whether to activate.
   Reference supporting scripts via `${PLUGIN_ROOT}/scripts/...` (resolved dynamically at runtime).
4. Put supporting code under `<skill>/scripts/` (stays at the plugin root).
5. Add the plugin entry to `.claude-plugin/marketplace.json` and the skill to the table above.

See [`CLAUDE.md`](CLAUDE.md) for the conventions Claude follows when working in this repo.
