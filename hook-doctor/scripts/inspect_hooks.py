#!/usr/bin/env python3
"""
Inspect and repair Claude Code plugin hook configurations.

Scans `hooks/hooks.json` files under installed plugin marketplaces for configuration
problems and (optionally) repairs them.

Usage:
    python3 inspect_hooks.py [--root DIR] [--apply]

Defaults to scanning ~/.claude/plugins/marketplaces/. Reports findings by default;
pass --apply to write fixes. Fixes are safe: text rewrites re-validate JSON before
writing and are idempotent; chmod fixes only add the execute bit.

Checks are intentionally limited to problems with real evidence or that are cheap,
static, and safe. The CHECKS structure below makes adding new ones straightforward.
"""

import argparse
import json
import os
import re
import shlex
import sys
from pathlib import Path


# Path variables Claude Code expands inside hook commands. All resolve to paths that
# may contain spaces (notably ~/Library/Application Support in agent-mode), so an
# unquoted reference is split by /bin/sh.
_PATH_VAR_TOKEN = re.compile(
    r'(?<!")(\$\{(?:CLAUDE_PLUGIN_ROOT|CLAUDE_PROJECT_DIR|CLAUDE_PLUGIN_DATA)\}[^\s"]*)'
)

# Authoritative hook event names (Claude Code docs, mid-2026). Unknown names never fire,
# so an unrecognized event is almost always a typo — but keep this list current to avoid
# false positives on newly added events.
VALID_EVENTS = {
    "SessionStart", "Setup", "UserPromptSubmit", "UserPromptExpansion", "PreToolUse",
    "PermissionRequest", "PermissionDenied", "PostToolUse", "PostToolUseFailure",
    "PostToolBatch", "Notification", "MessageDisplay", "SubagentStart", "SubagentStop",
    "TaskCreated", "TaskCompleted", "Stop", "StopFailure", "TeammateIdle",
    "InstructionsLoaded", "ConfigChange", "CwdChanged", "FileChanged", "WorktreeCreate",
    "WorktreeRemove", "PreCompact", "PostCompact", "Elicitation", "ElicitationResult",
    "SessionEnd",
}

_INTERPRETERS = {"python", "python3", "bash", "sh", "zsh", "node", "deno", "uv",
                 "ruby", "perl", "pwsh", "powershell"}


def quote_path_vars(command: str) -> str:
    """Quote any unquoted ${CLAUDE_*}/… path token. Idempotent."""
    return _PATH_VAR_TOKEN.sub(r'"\1"', command)


def _has_unquoted_path_var(command: str) -> bool:
    return quote_path_vars(command) != command


def _tokens(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def _resolve_script_path(command: str, plugin_root: Path | None,
                         project_dir: Path | None) -> Path | None:
    """Resolve the script path a command references, if it can be resolved statically.

    ${CLAUDE_PLUGIN_ROOT} is anchored to the plugin dir; ${CLAUDE_PROJECT_DIR} to the
    project dir (known only when a project is being inspected). Anything else (relative
    paths, $HOME, unknown vars) is not resolvable here — return None.
    """
    for tok in _tokens(command):
        if "${CLAUDE_PLUGIN_ROOT}" in tok and plugin_root is not None:
            return plugin_root / tok.replace("${CLAUDE_PLUGIN_ROOT}", "").lstrip("/")
        if "${CLAUDE_PROJECT_DIR}" in tok and project_dir is not None:
            return Path(project_dir) / tok.replace("${CLAUDE_PROJECT_DIR}", "").lstrip("/")
    return None


def _is_bare_path_command(command: str) -> bool:
    """True if the command executes a script directly (no interpreter prefix)."""
    for tok in _tokens(command):
        if "=" in tok and not tok.startswith("$") and "/" not in tok.split("=")[0]:
            continue  # leading ENV=val assignment
        return tok not in _INTERPRETERS
    return False


# --- traversal ---------------------------------------------------------------------------

def iter_commands(data: dict):
    """Yield (event, handler_dict) for every hook handler in a parsed hooks.json."""
    for event, blocks in (data.get("hooks") or {}).items():
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            for h in (block.get("hooks", []) if isinstance(block, dict) else []):
                if isinstance(h, dict):
                    yield event, h


def _finding(path, event, command, check, why, fix=None, target=None):
    return {"file": str(path), "event": event, "command": command,
            "check": check, "why": why, "fix": fix, "target": target}


def scan_file(path: Path, project_dir: Path | None = None) -> list[dict]:
    """Return findings for one hook-config file (no mutation).

    Handles both plugin `hooks/hooks.json` and `settings.json` (user/project). `project_dir`,
    when given, lets ${CLAUDE_PROJECT_DIR} script paths resolve.
    """
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return [_finding(path, None, None, "invalid_json", f"file is not valid JSON: {e}")]

    # ${CLAUDE_PLUGIN_ROOT} only applies to plugin hooks.json (<plugin>/hooks/hooks.json).
    is_plugin = path.name == "hooks.json" and path.parent.name == "hooks"
    plugin_root = path.parent.parent if is_plugin else None
    findings = []
    for event, handler in iter_commands(data):
        if event not in VALID_EVENTS:
            findings.append(_finding(path, event, None, "unknown_event",
                                     f"'{event}' is not a recognized hook event — it will never fire"))
        cmd = handler.get("command")
        if handler.get("type") == "command" and not isinstance(cmd, str):
            findings.append(_finding(path, event, None, "missing_command_field",
                                     "handler has type 'command' but no 'command' string"))
            continue
        if not isinstance(cmd, str):
            continue  # non-command handler types (http/prompt/agent/mcp_tool) — out of scope

        if _has_unquoted_path_var(cmd):
            findings.append(_finding(path, event, cmd, "unquoted_path_var",
                                     "unquoted ${CLAUDE_*} path — breaks where the path has a space (agent-mode)",
                                     fix="rewrite"))

        script = _resolve_script_path(cmd, plugin_root, project_dir)
        if script is not None:
            if not script.exists():
                findings.append(_finding(path, event, cmd, "missing_script",
                                         f"referenced script does not exist: {script}", target=str(script)))
            elif _is_bare_path_command(cmd) and not os.access(script, os.X_OK):
                findings.append(_finding(path, event, cmd, "script_not_executable",
                                         f"script is not executable (chmod +x needed): {script}",
                                         fix="chmod", target=str(script)))
    return findings


def fix_file(path: Path) -> int:
    """Apply 'rewrite' fixes (path-var quoting) to one hooks.json. Returns commands changed.

    Surgical raw-text replacement keeps diffs minimal; re-parses to guarantee validity.
    """
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return 0
    replacements = {}
    for _event, handler in iter_commands(data):
        cmd = handler.get("command")
        if isinstance(cmd, str):
            new = quote_path_vars(cmd)
            if new != cmd:
                replacements[cmd] = new
    if not replacements:
        return 0
    new_raw = raw
    for old, new in replacements.items():
        new_raw = new_raw.replace(json.dumps(old), json.dumps(new))
    json.loads(new_raw)  # validate before writing
    path.write_text(new_raw, encoding="utf-8")
    return len(replacements)


def apply_chmod(finding: dict) -> bool:
    """Add the execute bit for a script_not_executable finding. Returns success."""
    target = finding.get("target")
    if not target or not Path(target).exists():
        return False
    p = Path(target)
    p.chmod(p.stat().st_mode | 0o111)
    return True


def find_hooks_files(root: Path) -> list[Path]:
    """All plugin hooks/hooks.json under root, deduped by realpath (symlinks/nested copies)."""
    seen, out = set(), []
    for f in sorted(Path(root).rglob("hooks/hooks.json")):
        real = f.resolve()
        if real not in seen:
            seen.add(real)
            out.append(f)
    return out


def find_settings_files(project_dir: Path) -> list[Path]:
    """Existing settings.json hook sources: user-level + the given project's, deduped."""
    candidates = [
        Path.home() / ".claude" / "settings.json",
        Path.home() / ".claude" / "settings.local.json",
        Path(project_dir) / ".claude" / "settings.json",
        Path(project_dir) / ".claude" / "settings.local.json",
    ]
    seen, out = set(), []
    for c in candidates:
        if c.is_file():
            real = c.resolve()
            if real not in seen:
                seen.add(real)
                out.append(c)
    return out


# --- CLI ---------------------------------------------------------------------------------

_REPORT_ONLY = {"missing_script", "invalid_json", "missing_command_field", "unknown_event"}


def parse_args():
    p = argparse.ArgumentParser(description="Inspect and repair Claude Code hook configs")
    p.add_argument("--project", type=str, default=None,
                   help="Project whose effective hooks to inspect (default: cwd). Scans the "
                        "project's & user's settings.json plus installed plugins, and resolves "
                        "${CLAUDE_PROJECT_DIR}.")
    p.add_argument("--root", type=str, default=None,
                   help="Scan ONLY this tree of plugin hooks.json (skips settings.json sources).")
    p.add_argument("--apply", action="store_true",
                   help="Write fixes (quote path vars, chmod +x). Without it, report only.")
    return p.parse_args()


def gather_sources(args) -> tuple[list[tuple[Path, Path | None]], str]:
    """Return [(file, project_dir_for_resolution)] and a human description of the scope."""
    if args.root:
        root = Path(args.root).expanduser()
        project = Path(args.project).expanduser() if args.project else None
        return ([(f, project) for f in find_hooks_files(root)],
                f"plugin hooks under {root}")
    project = Path(args.project).expanduser() if args.project else Path.cwd()
    settings = find_settings_files(project)
    plugins = find_hooks_files(Path.home() / ".claude" / "plugins" / "marketplaces")
    sources = [(f, project) for f in settings + plugins]
    return (sources,
            f"effective hooks for {project} "
            f"({len(settings)} settings file(s) + {len(plugins)} installed plugin(s))")


def main():
    args = parse_args()
    sources, scope = gather_sources(args)
    print(f"Scanning {len(sources)} hook-config file(s) — {scope}", file=sys.stderr)

    all_findings = [f for path, pdir in sources for f in scan_file(path, pdir)]
    if not all_findings:
        print("No hook configuration problems found. ✓")
        return

    by_file: dict[str, list[dict]] = {}
    for f in all_findings:
        by_file.setdefault(f["file"], []).append(f)

    fixable = sum(1 for f in all_findings if f["fix"])
    print(f"\nFound {len(all_findings)} problem(s) in {len(by_file)} file(s) "
          f"({fixable} auto-fixable, {len(all_findings) - fixable} report-only):\n")
    for path, findings in by_file.items():
        print(path)
        for f in findings:
            loc = f["event"] or "—"
            tag = "fixable" if f["fix"] else "report"
            print(f"  [{f['check']}/{tag}] {loc}: {f['command'] or ''}")
            print(f"      → {f['why']}")
        print()

    if not args.apply:
        print("Dry run — re-run with --apply to fix auto-fixable items "
              "(this edits installed plugin files). Report-only items need manual attention.")
        return

    pdir_of = {str(path): pdir for path, pdir in sources}
    quoted = sum(fix_file(Path(p)) for p in by_file)
    chmodded = sum(1 for f in all_findings if f["fix"] == "chmod" and apply_chmod(f))
    remaining = sum(len(scan_file(Path(p), pdir_of.get(p))) for p in by_file)
    print(f"Quoted {quoted} command(s); chmod +x on {chmodded} script(s). "
          f"Remaining problems: {remaining} (report-only items are not auto-fixed).")
    print("Note: these are local edits to installed plugins — push upstream to persist.")


if __name__ == "__main__":
    main()
