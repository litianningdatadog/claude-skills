---
name: hook-doctor
description: "Inspects and repairs Claude Code hook configurations — plugin hooks.json and project/user settings.json. Use when a hook is failing or misconfigured, when an efficiency audit reports hook_errors, or when the user asks to check, diagnose, or fix hooks. Detects unquoted ${CLAUDE_PLUGIN_ROOT}/${CLAUDE_PROJECT_DIR} commands that fail in agent-mode (exit 127, '/bin/sh: .../Library/Application: No such file'), missing/non-executable scripts, unknown events, and invalid JSON. Trigger phrases: 'fix my hooks', 'hook is broken', 'why did my hook fail', 'check my plugin hooks', 'diagnose hook errors', 'hook exit 127'."
---

# Hook Doctor

Diagnose and repair **existing** Claude Code hook configs — plugin `hooks.json`,
`~/.claude/settings.json`, project `.claude/settings.json`. Not for authoring new hooks
(`hookify`) or broad settings changes (`update-config`).

## Checks

All checks are **static** (no hooks executed). Findings are *fixable* or *report-only*.

| Check | Problem | Fix |
|-------|---------|-----|
| `unquoted_path_var` | `${CLAUDE_PLUGIN_ROOT}` / `${CLAUDE_PROJECT_DIR}` / `${CLAUDE_PLUGIN_DATA}` unquoted. In agent-mode the path contains a space (`~/Library/Application Support/…`) → `/bin/sh` splits it → `exit 127`. | **fixable** — wrap the path token: `python3 "${CLAUDE_PLUGIN_ROOT}/x.py"`. |
| `script_not_executable` | Bare-path script lacks the execute bit → silent failure. | **fixable** — `chmod +x` (opt-in). |
| `missing_script` | Referenced script doesn't exist on disk. | report-only. |
| `unknown_event` | Event name not recognized — hook never fires (usually a typo). | report-only — suggest intended event. |
| `missing_command_field` | `type: "command"` handler has no `command` string. | report-only. |
| `invalid_json` | `hooks.json` fails to parse — silently disables the whole file. | report-only. |

## Procedure

### 0. Check Intent

Ask before scanning:
> "Diagnose-only, or apply fixes if found? All hooks or a specific plugin/error?"

- **Diagnose-only**: Step 1 → present findings → stop.
- **Fix locally**: Steps 1–3 (explicit approval before Step 3).
- **Upstream PR**: Steps 1–4.

### 1. Scan

```bash
PLUGIN_ROOT=$(ls -dt ~/.claude/plugins/cache/litianningdatadog-marketplace/hook-doctor/*/ 2>/dev/null | head -1)
python3 "${PLUGIN_ROOT}/scripts/inspect_hooks.py" 2>/dev/null
```

Flags: `--project <dir>` (default: cwd) · `--root <dir>` (plugin tree only, skips settings.json).

### 2. Present findings — get explicit fix decision

State the blast radius: fixes touch **shared/installed plugin files**, not the user's repo.
A `git pull` can revert them; the durable fix is upstream.

Offer: **(a)** fix locally · **(b)** upstream PR · **(c)** both · **(d)** skip. Never edit without this choice.

### 3. Apply (Plan → Act → Verify)

1. **Plan**: Name the file and the change. Stop and wait for confirmation.
2. **Act**:

```bash
PLUGIN_ROOT=$(ls -dt ~/.claude/plugins/cache/litianningdatadog-marketplace/hook-doctor/*/ 2>/dev/null | head -1)
python3 "${PLUGIN_ROOT}/scripts/inspect_hooks.py" --apply 2>/dev/null
```

Applies fixable repairs only (`unquoted_path_var`, `script_not_executable`). Report-only
findings are never auto-changed — surface them for manual attention.

3. **Verify**: Script re-scans after applying. If the target is a git repo, show `git diff`.
Do not declare success before the re-scan confirms the finding is gone.

For stale agent-mode snapshots under
`~/Library/Application Support/Claude/local-agent-mode-sessions/…/hooks/hooks.json`,
point `--root` there (treat as caches; new sessions regenerate from the canonical copy).

### 4. Upstream fix (if chosen)

Local edits don't survive plugin updates. Prepare a PR to the plugin's source repo with the
same fix. The same bug often affects multiple plugins in a marketplace at once.

## Relationship to efficiency-audit

`efficiency-audit` detects `hook_errors` historically but defers repair here. After fixing,
a fresh session plus a short `--days` re-run confirms no new failures.
