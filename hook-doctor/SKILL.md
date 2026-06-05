---
name: hook-doctor
description: "Inspects and repairs Claude Code hook configurations — plugin hooks.json and project/user settings.json. Use when a hook is failing or misconfigured, when an efficiency audit reports hook_errors, or when the user asks to check, diagnose, or fix hooks. Detects unquoted ${CLAUDE_PLUGIN_ROOT}/${CLAUDE_PROJECT_DIR} commands that fail in agent-mode (exit 127, '/bin/sh: .../Library/Application: No such file'), missing/non-executable scripts, unknown events, and invalid JSON. Trigger phrases: 'fix my hooks', 'hook is broken', 'why did my hook fail', 'check my plugin hooks', 'diagnose hook errors', 'hook exit 127'."
---

# Hook Doctor

## Overview

Diagnose and repair problems in **existing Claude Code hook configurations**. A bundled
script scans the hooks that affect a project — plugin `hooks/hooks.json`, the user's
`~/.claude/settings.json`, and the project's `.claude/settings.json` — reports problems, and
(only with explicit approval) applies safe, idempotent fixes.

This skill is distinct from:
- `hookify` — which *authors new* behavior-prevention hooks from conversation analysis.
- `update-config` — which configures `settings.json` broadly (permissions, env, adding hooks).

Hook Doctor only **inspects and repairs existing hook configs** — it doesn't author new hooks.

## When to use

- A plugin hook is failing or behaving oddly.
- An efficiency audit (or a session) surfaces `hook_errors`, especially `exit=127` with
  stderr like `/bin/sh: /Users/<you>/Library/Application: No such file`.
- The user asks to check, diagnose, or fix their plugin hooks.

## Checks

All checks are **static** (no hooks are executed). Each finding is either *fixable*
(safe automatic repair) or *report-only* (needs human judgment).

| Check | Problem | Fix |
|-------|---------|-----|
| `unquoted_path_var` | A command references `${CLAUDE_PLUGIN_ROOT}` / `${CLAUDE_PROJECT_DIR}` / `${CLAUDE_PLUGIN_DATA}` unquoted. Works in normal Claude Code (no space in the path) but in **agent-mode** the path is under `~/Library/Application Support/Claude/…` — the space makes `/bin/sh` split it → `exit 127`, `No such file`. | **fixable** — quote the *path token* (not the whole command): `python3 "${CLAUDE_PLUGIN_ROOT}/x.py"`. |
| `script_not_executable` | A bare-path command (no interpreter prefix) points at a script lacking the execute bit → silent non-blocking failure. | **fixable** — `chmod +x` (opt-in). |
| `missing_script` | A `${CLAUDE_PLUGIN_ROOT}/…` script referenced by a command does not exist on disk (runtime `ENOENT`). | report-only — can't invent a script. |
| `unknown_event` | The hook event name isn't a recognized Claude Code event, so the hook never fires (usually a typo). | report-only — suggest the intended event. |
| `missing_command_field` | A `type: "command"` handler has no `command` string. | report-only. |
| `invalid_json` | The `hooks.json` doesn't parse — silently disables the whole file. | report-only — fixing needs intent. |

The deepest, most common problem is `unquoted_path_var` (it accounted for the vast majority
of observed hook failures). The quoting fix preserves interpreters, env-var prefixes, and
trailing args — only the path token is wrapped.

New checks are added in `scripts/inspect_hooks.py` (`scan_file`); the structure makes adding
a check straightforward. Add checks only for problems actually observed or that are cheap,
static, and safe — keep `VALID_EVENTS` current so `unknown_event` doesn't flag new events.

## Procedure

### 1. Scan (report — always safe)

By default, inspect the hooks that **affect the current project** — its
`.claude/settings.json` (+ `.local`), the user's `~/.claude/settings.json`, and all
installed plugins:

```bash
python3 ~/.claude/skills/hook-doctor/scripts/inspect_hooks.py 2>/dev/null
```

Scoping options:
- `--project <dir>` — inspect a specific project's effective hooks (default: cwd). This also
  lets `${CLAUDE_PROJECT_DIR}` script paths resolve for the missing-script check.
- `--root <dir>` — inspect **only** a tree of plugin `hooks.json` (skips settings.json
  sources); use for auditing a marketplace or a single plugin in isolation.

Hooks live in three places, and the default scan covers all three: **plugin** hooks
(`~/.claude/plugins/marketplaces/**/hooks/hooks.json`, global), **user** settings
(`~/.claude/settings.json`), and **project** settings (`<project>/.claude/settings.json`).
Note plugin hooks are installed globally, not per-project — they're *active* in a project,
not scoped to it. The script reports each problem grouped by file (check, event, command,
why); with no findings it prints a clean result and exits.

### 2. Present findings and get an explicit fix decision

Summarize what was found. Then — **before changing anything** — make the blast radius
explicit, because fixes edit files **outside the user's project**:

- the edit modifies a **shared/installed plugin**, not the user's repo;
- it is a **local working-tree change** that a plugin update (`git pull`) can revert;
- the **durable fix is upstream** — a PR to the plugin's source repo.

Then offer the choice: **(a)** fix locally now, **(b)** prepare the upstream PR, **(c)** both,
or **(d)** skip. Never edit a marketplace clone or anything under
`~/Library/Application Support/` without that explicit choice — finding a problem is not
permission to modify files the user didn't author.

### 3. Apply (only on opt-in)

If the user chose to fix locally, run with `--apply`:

```bash
python3 ~/.claude/skills/hook-doctor/scripts/inspect_hooks.py --apply 2>/dev/null
```

`--apply` performs the *fixable* repairs only: quoting unquoted path vars (idempotent,
minimal-diff text edits that re-validate JSON before writing) and `chmod +x` on
non-executable bare-path scripts. **Report-only** findings (`missing_script`,
`unknown_event`, `missing_command_field`, `invalid_json`) are never auto-changed — surface
them for manual attention. After applying, the script re-scans and reports what remains. If
the marketplace is a git repo, show `git diff` so the user can review or revert.

Also worth fixing if present: stale **agent-mode snapshots** under
`~/Library/Application Support/Claude/local-agent-mode-sessions/.../hooks/hooks.json` — point
`--root` there. Treat these as caches; new sessions regenerate them from the canonical copy.

### 4. Offer the upstream fix

Local edits don't survive plugin updates. If the user chose (b) or (c), prepare a PR to the
plugin's source repo applying the same quoting fix. Note the same bug often affects many
plugins in a marketplace at once.

## Relationship to efficiency-audit

`efficiency-audit` detects `hook_errors` from past transcripts but defers repair here. When it
reports hook failures, recommend running this skill. Note efficiency-audit findings are
**historical** (from old transcripts) and persist until they age out of its `--days` window;
after fixing, a fresh session plus a small `--days` re-run confirms no *new* failures.
