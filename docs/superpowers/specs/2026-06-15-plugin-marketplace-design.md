# Plugin Marketplace Conversion — Design Spec

**Date:** 2026-06-15  
**Status:** Approved

## Problem

The `claude-marketplace` repo currently ships skills as raw directories copied manually into `~/.claude/skills/`. Claude Code's plugin system offers a better distribution model: a `marketplace.json` catalog that lets users add the marketplace once and install individual skills as first-class plugins with version tracking and auto-updates.

## Goal

Convert the repo into a valid Claude Code plugin marketplace so users can:

```bash
/plugin marketplace add litianningdatadog/claude-marketplace
/plugin install efficiency-audit@claude-marketplace
/plugin install hook-doctor@claude-marketplace
/plugin install quicknotes@claude-marketplace
```

Each skill becomes an independently installable plugin. Scripts and reference files within each skill remain in place; only the `SKILL.md` location and its internal path references change.

## Design

### Repo structure

```
claude-marketplace/
├── .claude-plugin/
│   └── marketplace.json              ← NEW: marketplace catalog
├── efficiency-audit/
│   ├── .claude-plugin/
│   │   └── plugin.json               ← NEW: plugin manifest
│   ├── skills/
│   │   └── efficiency-audit/
│   │       └── SKILL.md              ← MOVED from efficiency-audit/SKILL.md
│   ├── references/                   (unchanged — stays at plugin root)
│   └── scripts/                      (unchanged — stays at plugin root)
├── hook-doctor/
│   ├── .claude-plugin/
│   │   └── plugin.json               ← NEW
│   ├── skills/
│   │   └── hook-doctor/
│   │       └── SKILL.md              ← MOVED
│   └── scripts/                      (unchanged — stays at plugin root)
├── quicknotes/
│   ├── .claude-plugin/
│   │   └── plugin.json               ← NEW
│   ├── skills/
│   │   └── quicknotes/
│   │       └── SKILL.md              ← MOVED
│   ├── commands/                     (unchanged)
│   └── scripts/                      (unchanged — stays at plugin root)
├── CLAUDE.md                         ← UPDATED (see below)
└── README.md                         ← UPDATED (see below)
```

**Plugin root definition:** When a plugin is installed, the plugin directory itself (e.g., `efficiency-audit/`) is the root copied to the cache. `scripts/` and `references/` are siblings of `skills/` under that root — so `${PLUGIN_ROOT}/scripts/` and `${PLUGIN_ROOT}/references/` are always valid after installation.

### `.claude-plugin/marketplace.json`

```json
{
  "name": "claude-marketplace",
  "description": "Claude Code skills for workflow automation, hook repair, and quick notes.",
  "owner": { "name": "Tianning Li" },
  "plugins": [
    {
      "name": "efficiency-audit",
      "source": "./efficiency-audit",
      "description": "Analyzes recent Claude Code transcripts to surface recurring inefficiencies."
    },
    {
      "name": "hook-doctor",
      "source": "./hook-doctor",
      "description": "Inspects and repairs installed plugin hook configurations."
    },
    {
      "name": "quicknotes",
      "source": "./quicknotes",
      "description": "Low-friction quick-note capture and management for Claude Code."
    }
  ]
}
```

### Per-plugin `plugin.json`

Each skill directory gets a `.claude-plugin/plugin.json`. No `version` field — every git commit is a new version, which is correct for active development. The `skills/` directory is auto-discovered by convention; no explicit `skills` field needed in `plugin.json`.

```json
{
  "name": "efficiency-audit",
  "description": "Analyzes recent Claude Code transcripts to surface recurring inefficiencies."
}
```

(Replace `name` and `description` for `hook-doctor` and `quicknotes` accordingly.)

### SKILL.md relocation

Each `<skill>/SKILL.md` moves to `<skill>/skills/<skill>/SKILL.md`. Claude Code's plugin runtime auto-discovers skills at `skills/<name>/SKILL.md` within the plugin root; no explicit `skills` path declaration is required.

### SKILL.md script path migration — bash commands

Plugin scripts live at a versioned cache path:

```
~/.claude/plugins/cache/claude-marketplace/<plugin>/<version>/scripts/
```

The version segment is dynamic. Every code block in SKILL.md that invokes a script gains a resolver preamble (note the explicit `/` separator to avoid broken paths if the trailing slash is absent):

```bash
PLUGIN_ROOT=$(ls -dt ~/.claude/plugins/cache/claude-marketplace/efficiency-audit/*/ 2>/dev/null | head -1)
python3 "${PLUGIN_ROOT}/scripts/analyze_conversations.py" ...
```

`ls -dt ... | head -1` selects the most recently installed version directory. The marketplace name and plugin name are stable constants; only the version segment needs dynamic resolution.

Apply the same pattern for `hook-doctor` and `quicknotes`, substituting the plugin name.

### SKILL.md reference file path migration

Reference file paths in SKILL.md prose — currently written as:

> `(installed at ~/.claude/skills/efficiency-audit/references/category-guide.md)`

— become:

> `(installed at ${PLUGIN_ROOT}/references/category-guide.md, where PLUGIN_ROOT is resolved via the preamble above)`

Where `${PLUGIN_ROOT}` is set via the resolver defined in any preceding code block. For standalone references not adjacent to a script block, add the resolver inline:

```bash
PLUGIN_ROOT=$(ls -dt ~/.claude/plugins/cache/claude-marketplace/efficiency-audit/*/ 2>/dev/null | head -1)
# Read: ${PLUGIN_ROOT}/references/category-guide.md
```

### `efficiency-audit/references/` file updates

Several reference files contain detection commands that check for skills at `~/.claude/skills/<name>/`. After migration, plugins install to `~/.claude/plugins/cache/`. These detection commands must be updated:

**`category-guide.md`** — the `hook_errors` section has:
```bash
ls ~/.claude/skills/hook-doctor/SKILL.md 2>/dev/null && echo "installed" || echo "not_installed"
```
Update to check the plugin cache path:
```bash
ls ~/.claude/plugins/cache/claude-marketplace/hook-doctor/*/SKILL.md 2>/dev/null | head -1 | grep -q . && echo "installed" || echo "not_installed"
```
Also update the install instruction URL from the old skills README to the new plugin install command:
> Install it from the [claude-marketplace repo](https://github.com/litianningdatadog/claude-marketplace): `/plugin install hook-doctor@claude-marketplace`

**`terminal-title-check.md`** — detection checks `~/.claude/skills/terminal-title/`. The `terminal-title` skill is not in this repo; update the detection to check both locations (legacy skills path and plugin cache) so the audit works regardless of how `terminal-title` was installed:
```bash
if ls ~/.claude/skills/terminal-title/scripts/set_title.sh 2>/dev/null \
   || ls ~/.claude/plugins/cache/*/terminal-title/*/scripts/set_title.sh 2>/dev/null | grep -q .; then
  echo "installed"
else
  echo "not_installed"
fi
```

### quicknotes hook template path

The quicknotes `SKILL.md` contains a proposed `SessionStart` hook JSON snippet with a hardcoded path:
```
${HOME}/.claude/skills/quicknotes/scripts/session_reminder.py
```

Hook config fields DO expand `${CLAUDE_PLUGIN_ROOT}`, unlike SKILL.md prose. Update the hook snippet to:
```json
{
  "type": "command",
  "command": "${CLAUDE_PLUGIN_ROOT}/scripts/session_reminder.py"
}
```

### README update

Replace the manual `cp -R` install instructions with:

```bash
# Add the marketplace (once per machine)
/plugin marketplace add litianningdatadog/claude-marketplace

# Install skills à la carte
/plugin install efficiency-audit@claude-marketplace
/plugin install hook-doctor@claude-marketplace
/plugin install quicknotes@claude-marketplace
```

Keep the skill description table and contributing guide. Remove the old per-skill `cp -R` install section. Add a note that `SKILL.md` still references its own scripts by their installed path; `${PLUGIN_ROOT}` resolves automatically when the plugin is installed from the marketplace.

### CLAUDE.md update

Replace the "Skill anatomy" section's description of the old raw-skills layout with the new plugin structure:

- Update the directory anatomy to show `.claude-plugin/plugin.json` and `skills/<name>/SKILL.md` as required components
- Update the note about installed path from `~/.claude/skills/<name>/scripts/...` to `${PLUGIN_ROOT}/scripts/...` (resolved dynamically via the `ls -dt` resolver described in SKILL.md bodies)
- Keep the "Contributing a new skill" section but update step 2 to: "Add a `.claude-plugin/plugin.json` with `name` and `description`, and a `skills/<name>/SKILL.md` as the agent procedure. Add the plugin entry to `.claude-plugin/marketplace.json`."
- Update the example `cp -R` install command to `/plugin install <name>@claude-marketplace`

## Files changed

| Action | File |
|--------|------|
| CREATE | `.claude-plugin/marketplace.json` |
| CREATE | `efficiency-audit/.claude-plugin/plugin.json` |
| MOVE + UPDATE | `efficiency-audit/SKILL.md` → `efficiency-audit/skills/efficiency-audit/SKILL.md` (script + reference paths) |
| UPDATE | `efficiency-audit/references/category-guide.md` (hook-doctor detection command + install URL) |
| UPDATE | `efficiency-audit/references/terminal-title-check.md` (terminal-title detection command) |
| CREATE | `hook-doctor/.claude-plugin/plugin.json` |
| MOVE + UPDATE | `hook-doctor/SKILL.md` → `hook-doctor/skills/hook-doctor/SKILL.md` (script paths) |
| CREATE | `quicknotes/.claude-plugin/plugin.json` |
| MOVE + UPDATE | `quicknotes/SKILL.md` → `quicknotes/skills/quicknotes/SKILL.md` (script paths + SessionStart hook template) |
| UPDATE | `README.md` |
| UPDATE | `CLAUDE.md` |

## Out of scope

- Converting the `quicknotes` CLI (`qn` alias) setup — `install_alias.sh` hardcodes `~/.claude/skills/...` but this is opt-in user-side tooling, not the skill itself.
- Adding new skills.
- Setting up CI validation (`claude plugin validate`), though recommended after implementation.
