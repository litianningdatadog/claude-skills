#!/usr/bin/env python3
"""
Tests for inspect_hooks.py.

Stdlib only. Run from the scripts/ directory:
    python3 -m unittest test_inspect_hooks
"""

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

import inspect_hooks as ih


def write_plugin(hooks: dict, scripts: dict | None = None, raw: str | None = None) -> Path:
    """Create a temp plugin dir and return the path to its hooks/hooks.json.

    `hooks` maps event -> command (string). `scripts` maps a path relative to the
    plugin root -> (content, executable_bool); those files are created on disk.
    `raw` overrides the hooks.json content verbatim (for invalid-JSON tests).
    """
    plugin = Path(tempfile.mkdtemp()) / "plugin"
    (plugin / "hooks").mkdir(parents=True)
    path = plugin / "hooks" / "hooks.json"
    if raw is not None:
        path.write_text(raw)
    else:
        d = {"hooks": {ev: [{"hooks": [{"type": "command", "command": cmd}]}]
                       for ev, cmd in hooks.items()}}
        path.write_text(json.dumps(d, indent=2) + "\n")
    for rel, (content, executable) in (scripts or {}).items():
        sp = plugin / rel
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(content)
        mode = sp.stat().st_mode
        sp.chmod(mode | 0o111 if executable else mode & ~0o111)
    return path


def checks_of(findings):
    return {f["check"] for f in findings}


class QuoteTransformTests(unittest.TestCase):
    def test_plugin_root_bare_path(self):
        self.assertEqual(
            ih.quote_path_vars("${CLAUDE_PLUGIN_ROOT}/scripts/x.sh"),
            '"${CLAUDE_PLUGIN_ROOT}/scripts/x.sh"',
        )

    def test_project_dir_is_also_quoted(self):
        self.assertEqual(
            ih.quote_path_vars("bash ${CLAUDE_PROJECT_DIR}/.claude/h.sh"),
            'bash "${CLAUDE_PROJECT_DIR}/.claude/h.sh"',
        )

    def test_plugin_data_is_also_quoted(self):
        self.assertEqual(
            ih.quote_path_vars("${CLAUDE_PLUGIN_DATA}/state.sh"),
            '"${CLAUDE_PLUGIN_DATA}/state.sh"',
        )

    def test_interpreter_prefix(self):
        self.assertEqual(
            ih.quote_path_vars("python3 ${CLAUDE_PLUGIN_ROOT}/hooks/x.py"),
            'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/x.py"',
        )

    def test_path_with_args(self):
        self.assertEqual(
            ih.quote_path_vars("${CLAUDE_PLUGIN_ROOT}/hooks/notify.sh idle"),
            '"${CLAUDE_PLUGIN_ROOT}/hooks/notify.sh" idle',
        )

    def test_already_quoted_unchanged_and_idempotent(self):
        once = ih.quote_path_vars("python3 ${CLAUDE_PLUGIN_ROOT}/x.py")
        self.assertEqual(ih.quote_path_vars(once), once)

    def test_no_path_var_unchanged(self):
        self.assertEqual(ih.quote_path_vars("echo hello"), "echo hello")


class UnquotedCheckTests(unittest.TestCase):
    def test_detects_unquoted_command(self):
        path = write_plugin({"SessionStart": "${CLAUDE_PLUGIN_ROOT}/scripts/x.sh"},
                            scripts={"scripts/x.sh": ("#!/bin/sh\n", True)})
        findings = ih.scan_file(path)
        self.assertIn("unquoted_path_var", checks_of(findings))

    def test_quoted_command_clean(self):
        path = write_plugin({"SessionStart": '"${CLAUDE_PLUGIN_ROOT}/scripts/x.sh"'},
                            scripts={"scripts/x.sh": ("#!/bin/sh\n", True)})
        self.assertNotIn("unquoted_path_var", checks_of(ih.scan_file(path)))


class MissingScriptTests(unittest.TestCase):
    def test_missing_script_reported(self):
        path = write_plugin({"SessionStart": '"${CLAUDE_PLUGIN_ROOT}/scripts/gone.sh"'})
        findings = ih.scan_file(path)
        self.assertIn("missing_script", checks_of(findings))

    def test_existing_script_not_reported(self):
        path = write_plugin({"SessionStart": '"${CLAUDE_PLUGIN_ROOT}/scripts/here.sh"'},
                            scripts={"scripts/here.sh": ("#!/bin/sh\n", True)})
        self.assertNotIn("missing_script", checks_of(ih.scan_file(path)))

    def test_project_dir_not_resolved_statically(self):
        # ${CLAUDE_PROJECT_DIR} can't be resolved at lint time → no missing_script finding.
        path = write_plugin({"SessionStart": '"${CLAUDE_PROJECT_DIR}/x.sh"'})
        self.assertNotIn("missing_script", checks_of(ih.scan_file(path)))


class ExecutableTests(unittest.TestCase):
    def test_bare_path_non_executable_reported(self):
        path = write_plugin({"Stop": '"${CLAUDE_PLUGIN_ROOT}/scripts/x.sh"'},
                            scripts={"scripts/x.sh": ("#!/bin/sh\n", False)})
        self.assertIn("script_not_executable", checks_of(ih.scan_file(path)))

    def test_interpreter_prefixed_non_executable_ok(self):
        # `python3 .../x.py` doesn't require x.py to be executable.
        path = write_plugin({"Stop": 'python3 "${CLAUDE_PLUGIN_ROOT}/x.py"'},
                            scripts={"x.py": ("print(1)\n", False)})
        self.assertNotIn("script_not_executable", checks_of(ih.scan_file(path)))

    def test_chmod_fix_makes_executable(self):
        path = write_plugin({"Stop": '"${CLAUDE_PLUGIN_ROOT}/scripts/x.sh"'},
                            scripts={"scripts/x.sh": ("#!/bin/sh\n", False)})
        finding = next(f for f in ih.scan_file(path) if f["check"] == "script_not_executable")
        ih.apply_chmod(finding)
        self.assertTrue(os.access(finding["target"], os.X_OK))
        self.assertNotIn("script_not_executable", checks_of(ih.scan_file(path)))


class SchemaTests(unittest.TestCase):
    def test_invalid_json_reported(self):
        path = write_plugin({}, raw='{"hooks": {bad json}')
        self.assertIn("invalid_json", checks_of(ih.scan_file(path)))

    def test_missing_command_field_reported(self):
        raw = json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command"}]}]}})
        path = write_plugin({}, raw=raw)
        self.assertIn("missing_command_field", checks_of(ih.scan_file(path)))

    def test_unknown_event_reported(self):
        path = write_plugin({"NotARealEvent": '"${CLAUDE_PLUGIN_ROOT}/x.sh"'},
                            scripts={"x.sh": ("#!/bin/sh\n", True)})
        self.assertIn("unknown_event", checks_of(ih.scan_file(path)))

    def test_known_newer_events_not_flagged(self):
        # PreCompact and SessionEnd are valid (newer) events — must not false-positive.
        for ev in ("PreCompact", "SessionEnd"):
            path = write_plugin({ev: '"${CLAUDE_PLUGIN_ROOT}/x.sh"'},
                                scripts={"x.sh": ("#!/bin/sh\n", True)})
            self.assertNotIn("unknown_event", checks_of(ih.scan_file(path)), ev)


def write_settings(hooks: dict, scripts: dict | None = None, name: str = "settings.json"):
    """Create a temp project with .claude/<name>; return (project_dir, settings_path)."""
    proj = Path(tempfile.mkdtemp())
    (proj / ".claude").mkdir()
    path = proj / ".claude" / name
    d = {"hooks": {ev: [{"hooks": [{"type": "command", "command": cmd}]}]
                   for ev, cmd in hooks.items()}}
    path.write_text(json.dumps(d, indent=2))
    for rel, (content, executable) in (scripts or {}).items():
        sp = proj / rel
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(content)
        mode = sp.stat().st_mode
        sp.chmod(mode | 0o111 if executable else mode & ~0o111)
    return proj, path


class ProjectScopeTests(unittest.TestCase):
    def test_project_dir_resolves_missing_script(self):
        proj, path = write_settings({"SessionStart": '"${CLAUDE_PROJECT_DIR}/.claude/gone.sh"'})
        # With the project dir known, ${CLAUDE_PROJECT_DIR} resolves → missing_script fires.
        self.assertIn("missing_script", checks_of(ih.scan_file(path, project_dir=proj)))

    def test_project_dir_existing_script_ok(self):
        proj, path = write_settings(
            {"SessionStart": '"${CLAUDE_PROJECT_DIR}/.claude/here.sh"'},
            scripts={".claude/here.sh": ("#!/bin/sh\n", True)},
        )
        self.assertNotIn("missing_script", checks_of(ih.scan_file(path, project_dir=proj)))

    def test_settings_unquoted_project_dir_flagged(self):
        proj, path = write_settings({"Stop": "${CLAUDE_PROJECT_DIR}/.claude/h.sh"})
        self.assertIn("unquoted_path_var", checks_of(ih.scan_file(path, project_dir=proj)))

    def test_find_settings_files_includes_project(self):
        proj, path = write_settings({"Stop": "echo done"})
        found = ih.find_settings_files(proj)
        self.assertIn(path.resolve(), {p.resolve() for p in found})


class FixFileTests(unittest.TestCase):
    def test_fix_quotes_and_validates(self):
        path = write_plugin({
            "SessionStart": "${CLAUDE_PLUGIN_ROOT}/scripts/x.sh",
            "PreToolUse": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/y.py",
        }, scripts={"scripts/x.sh": ("#!/bin/sh\n", True), "hooks/y.py": ("print(1)\n", False)})
        self.assertEqual(ih.fix_file(path), 2)
        json.loads(path.read_text())  # still valid
        self.assertNotIn("unquoted_path_var", checks_of(ih.scan_file(path)))

    def test_fix_idempotent(self):
        path = write_plugin({"SessionStart": "${CLAUDE_PLUGIN_ROOT}/scripts/x.sh"},
                            scripts={"scripts/x.sh": ("#!/bin/sh\n", True)})
        self.assertEqual(ih.fix_file(path), 1)
        self.assertEqual(ih.fix_file(path), 0)

    def test_fix_preserves_unrelated(self):
        path = write_plugin({"Stop": "echo done"})
        before = path.read_text()
        self.assertEqual(ih.fix_file(path), 0)
        self.assertEqual(path.read_text(), before)


class DedupTests(unittest.TestCase):
    def test_find_dedupes_by_realpath(self):
        # A symlinked duplicate of a plugin dir must not be scanned twice.
        path = write_plugin({"Stop": "echo done"})
        root = path.parent.parent.parent  # tmp dir containing "plugin"
        link = root / "plugin-link"
        try:
            os.symlink(path.parent.parent, link)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        files = ih.find_hooks_files(root)
        self.assertEqual(len(files), 1)


if __name__ == "__main__":
    unittest.main()
