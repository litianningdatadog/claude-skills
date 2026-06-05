# hook-doctor

Inspects and repairs **Claude Code plugin hook configurations** — the `hooks/hooks.json`
files under `~/.claude/plugins/marketplaces/<marketplace>/<plugin>/`. Scans every installed
plugin for known hook-config problems, reports them, and (with explicit opt-in) applies safe,
idempotent fixes.

> **Canonical behavior lives in [`SKILL.md`](SKILL.md).** This README covers human-facing
> install, direct CLI usage, and testing. If the two ever disagree, `SKILL.md` wins.

Not to be confused with `hookify` (authors *new* behavior-prevention hooks) or `update-config`
(edits `settings.json`). hook-doctor only diagnoses/repairs *existing plugin* hook configs.

## What it checks

All checks are **static** (no hooks are run). Findings are either *fixable* (safe automatic
repair) or *report-only*.

| Check | Problem | Fix |
|-------|---------|-----|
| `unquoted_path_var` | A command uses `${CLAUDE_PLUGIN_ROOT}` / `${CLAUDE_PROJECT_DIR}` / `${CLAUDE_PLUGIN_DATA}` unquoted. Works in normal Claude Code (no space in the path) but fails in **agent-mode** under `~/Library/Application Support/Claude/…` — `/bin/sh` splits at the space → `exit 127`, `/bin/sh: …/Library/Application: No such file`. | fixable — quote the **path token**: `python3 "${CLAUDE_PLUGIN_ROOT}/x.py"`. |
| `script_not_executable` | A bare-path command points at a script without the execute bit (silent failure). | fixable — `chmod +x` (opt-in). |
| `missing_script` | A `${CLAUDE_PLUGIN_ROOT}/…` script doesn't exist on disk (runtime `ENOENT`). | report-only. |
| `unknown_event` | Unrecognized hook event name — the hook never fires (typo). | report-only. |
| `missing_command_field` | A `type: "command"` handler has no `command`. | report-only. |
| `invalid_json` | `hooks.json` doesn't parse (silently disables the file). | report-only. |

More checks can be added in `scan_file` in `scripts/inspect_hooks.py`; only problems
observed in practice or that are cheap/static/safe are implemented. `--apply` performs the
fixable repairs (quoting + `chmod +x`); report-only findings are left for manual attention.

## Install

```bash
cp -R hook-doctor ~/.claude/skills/
```

Trigger it with phrases like "fix my hooks", "why did my hook fail", "check my plugin hooks",
or "hook exit 127" — or run `/hook-doctor` if your client exposes skills as commands.

## Hook sources it inspects

Hooks live in three places, and the default scan covers all of them for the current project:

- **Plugin** hooks — `~/.claude/plugins/marketplaces/**/hooks/hooks.json` (installed globally; active in every project, not scoped to one).
- **User** settings — `~/.claude/settings.json` (+ `.local.json`).
- **Project** settings — `<project>/.claude/settings.json` (+ `.local.json`).

## Running the inspector directly

```bash
# Effective hooks for the current project (dry run — safe): project + user settings + plugins
python3 scripts/inspect_hooks.py

# A specific project's effective hooks (also resolves ${CLAUDE_PROJECT_DIR}):
python3 scripts/inspect_hooks.py --project /path/to/repo

# ONLY a tree of plugin hooks.json (a marketplace, one plugin, or an agent-mode snapshot dir):
python3 scripts/inspect_hooks.py --root ~/.claude/plugins/marketplaces/<marketplace>

# Apply fixes (edits installed/settings files — see caveat below):
python3 scripts/inspect_hooks.py --apply
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--project DIR` | cwd | Inspect a project's *effective* hooks: its `.claude/settings*.json` + user `~/.claude/settings.json` + installed plugins. Resolves `${CLAUDE_PROJECT_DIR}` for the missing-script check. |
| `--root DIR` | _(unset)_ | Inspect **only** this tree of plugin `hooks.json` (skips settings.json sources). For auditing a marketplace, a single plugin, or the agent-mode snapshot dir under `~/Library/Application Support/Claude/local-agent-mode-sessions`. |
| `--apply` | _(off)_ | Write the fixable repairs (quote path vars, `chmod +x`). Without it, report only. Text fixes are idempotent and re-validate JSON before writing. |

## Caveat: where `--apply` writes

`--apply` can touch three kinds of file, with different blast radius:

- **Plugin `hooks.json`** (shared, installed) — *outside* your project. These edits are local
  working-tree changes a plugin update (`git pull`) can revert; the durable fix is a **PR to
  the plugin's source repo**. The same bug often affects many plugins at once.
- **User `~/.claude/settings.json`** — your global config, outside any project.
- **Project `.claude/settings.json`** — inside the project, tracked by its own git.

When run via the skill, hook-doctor makes the target and blast radius explicit and asks before
applying (fix locally / upstream PR / both / skip) — it won't edit shared plugins or anything
under `~/Library/Application Support/` without that choice.

## Tests

Standard-library `unittest`, no dependencies:

```bash
cd scripts && python3 -m unittest test_inspect_hooks
```

## Files

```
hook-doctor/
├── SKILL.md                       # canonical agent instructions (the skill spec)
├── README.md                      # this file
└── scripts/
    ├── inspect_hooks.py           # hook-config inspector/repairer CLI
    └── test_inspect_hooks.py      # unittest suite
```
