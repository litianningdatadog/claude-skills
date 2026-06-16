#!/usr/bin/env python3
"""
Tests for analyze_conversations.py.

Stdlib only. Run with:
    python3 -m unittest efficiency-audit.scripts.test_analyze_conversations
or, from the scripts/ directory:
    python3 -m unittest test_analyze_conversations
"""

import json
import tempfile
import unittest
from pathlib import Path

import analyze_conversations as ac


def write_session(lines: list[dict]) -> Path:
    """Write a list of transcript records to a temp .jsonl and return its path."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
    )
    for rec in lines:
        tmp.write(json.dumps(rec) + "\n")
    tmp.close()
    return Path(tmp.name)


def user(text: str, ts: str = "2026-06-01T00:00:00Z") -> dict:
    return {"type": "user", "timestamp": ts, "message": {"content": text}}


def assistant(text: str, ts: str = "2026-06-01T00:00:00Z") -> dict:
    return {"type": "assistant", "timestamp": ts, "message": {"content": text}}


class NoiseFilterTests(unittest.TestCase):
    def test_session_continuation_is_noise(self):
        self.assertTrue(
            ac.is_noise(
                "This session is being continued from a previous conversation "
                "that ran out of context."
            )
        )

    def test_command_tag_is_noise(self):
        self.assertTrue(ac.is_noise("<command-name>/init</command-name>"))
        self.assertTrue(ac.is_noise("<command-message>model</command-message>"))

    def test_security_review_boilerplate_is_noise(self):
        self.assertTrue(
            ac.is_noise(
                "You are a security reviewer. Analyze the following code changes "
                "for vulnerabilities."
            )
        )

    def test_subagent_dispatch_is_noise(self):
        self.assertTrue(
            ac.is_noise(
                "You are a subagent dispatched to execute the following task."
            )
        )

    def test_real_skill_injection_formats_are_noise(self):
        # Formats observed leaking into real transcripts as pseudo-user messages.
        self.assertTrue(
            ac.is_noise(
                "Review this change for security vulnerabilities.\n\nChanged files "
                "(you may Read these and any other file in the repo):"
            )
        )
        self.assertTrue(
            ac.is_noise("Provide a code review for the given pull request.\n\nTo do this")
        )
        self.assertTrue(
            ac.is_noise("Base directory for this skill: /Users/x/.claude/skills/foo")
        )

    def test_task_workflow_messages_are_noise(self):
        # "Review the X output and fix" — user pasting test/tool output back.
        self.assertTrue(ac.is_noise(
            "review the test run output and fix the script if needed: python3 scripts/x.py"
        ))
        self.assertTrue(ac.is_noise(
            "review the output and fix if needed: some error here"
        ))
        # Message dominated by a code block (pasted tool output).
        self.assertTrue(ac.is_noise(
            "```\nFailed with exit code 1\nsome traceback here\n```"
        ))
        # Messages that are mostly a shell command / file path paste.
        self.assertTrue(ac.is_noise(
            "python3 scripts/analyze_conversations.py \\\n  --days 30 --project /Users/x/repo"
        ))

    def test_context_injection_prefix_is_noise(self):
        # Hooks/skills inject "## Context - ..." into the user message slot.
        self.assertTrue(ac.is_noise(
            "## Context - Current git status: On branch main\nUntracked files: ..."
        ))
        self.assertTrue(ac.is_noise("## Context - relevant info here"))

    def test_genuine_corrections_not_filtered_as_workflow(self):
        self.assertFalse(ac.is_noise("no, don't commit yet, we need to fix the tests first"))
        self.assertFalse(ac.is_noise("please don't create a new commit, amend instead"))

    def test_real_correction_is_not_noise(self):
        self.assertFalse(ac.is_noise("no, don't use that approach, use a hook instead"))


class ExtractionTests(unittest.TestCase):
    def test_preceding_action_captured(self):
        path = write_session([
            assistant("Let me create a worktree for this task."),
            user("no, don't use worktrees, use a branch"),
        ])
        sess = ac.extract_session_data(path)
        msg = sess["user_messages"][0]
        self.assertIn("preceding_action", msg)
        self.assertIn("worktree", msg["preceding_action"])

    def test_preceding_action_none_when_no_prior_assistant(self):
        path = write_session([user("no, don't do that")])
        sess = ac.extract_session_data(path)
        self.assertIsNone(sess["user_messages"][0]["preceding_action"])

    def test_preceding_action_updates_with_latest_assistant(self):
        path = write_session([
            assistant("First assistant turn."),
            user("ok"),
            assistant("Second assistant turn."),
            user("no, don't do that"),
        ])
        sess = ac.extract_session_data(path)
        self.assertIn("Second", sess["user_messages"][1]["preceding_action"])
        self.assertIn("First", sess["user_messages"][0]["preceding_action"])

    def test_correction_group_has_preceding_action(self):
        path = write_session([
            assistant("I'll create a worktree for isolation."),
            user("no, don't use worktrees"),
        ])
        sessions = [ac.extract_session_data(path)]
        findings = ac.analyze(sessions)
        top = findings["corrections"][0]
        self.assertIn("preceding_action", top)
        self.assertIn("worktree", top["preceding_action"])

    def test_noise_user_messages_are_dropped(self):
        path = write_session(
            [
                user("This session is being continued from a previous conversation."),
                user("<command-name>/init</command-name>"),
                user("please run the tests before committing"),
            ]
        )
        sess = ac.extract_session_data(path)
        texts = [m["text"] for m in sess["user_messages"]]
        self.assertEqual(texts, ["please run the tests before committing"])

    def test_hook_errors_from_system_stop_hook_summary(self):
        path = write_session(
            [
                {
                    "type": "system",
                    "subtype": "stop_hook_summary",
                    "hookErrors": [
                        {
                            "hookName": "stop.py",
                            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/stop.py",
                            "exitCode": 1,
                            "stderr": "boom",
                        }
                    ],
                },
                user("hello"),
            ]
        )
        sess = ac.extract_session_data(path)
        self.assertEqual(len(sess["hook_errors"]), 1)
        self.assertEqual(sess["hook_errors"][0]["hook_name"], "stop.py")
        self.assertEqual(sess["hook_errors"][0]["stderr"], "boom")

    def test_empty_system_hook_errors_ignored(self):
        path = write_session(
            [
                {"type": "system", "subtype": "stop_hook_summary", "hookErrors": []},
                user("hello"),
            ]
        )
        sess = ac.extract_session_data(path)
        self.assertEqual(sess["hook_errors"], [])

    def test_non_blocking_hook_error_attachment_still_caught(self):
        path = write_session(
            [
                {
                    "type": "attachment",
                    "attachment": {
                        "type": "hook_non_blocking_error",
                        "hookName": "fmt",
                        "command": "gofmt",
                        "exitCode": 2,
                        "stderr": "bad",
                    },
                },
                user("hello"),
            ]
        )
        sess = ac.extract_session_data(path)
        self.assertEqual(len(sess["hook_errors"]), 1)
        self.assertEqual(sess["hook_errors"][0]["hook_name"], "fmt")

    def test_cancelled_hook_is_not_an_error(self):
        # A cancelled hook (no exit code, e.g. interrupted/timed out) is not a failure.
        path = write_session(
            [
                {
                    "type": "attachment",
                    "attachment": {
                        "type": "hook_cancelled",
                        "hookName": "PreToolUse:Bash",
                        "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/pretooluse.py",
                        "durationMs": "10345",
                    },
                },
                user("hello"),
            ]
        )
        sess = ac.extract_session_data(path)
        self.assertEqual(sess["hook_errors"], [])


class AutomationPatternTests(unittest.TestCase):
    def _is_automation(self, text: str) -> bool:
        return bool(ac.score_message(text)["automation"])

    def test_intent_phrases_match(self):
        self.assertTrue(self._is_automation("every time I commit, run the linter"))
        self.assertTrue(self._is_automation("always run the tests before pushing"))
        self.assertTrue(self._is_automation("let's automate the changelog generation"))
        self.assertTrue(self._is_automation("set up a hook to format on save"))

    def test_incidental_word_mentions_do_not_match(self):
        # Bare mentions of these nouns/adjectives are not automation intent.
        self.assertFalse(self._is_automation("what is the shortcut key to move a window left"))
        self.assertFalse(self._is_automation("the deploy script failed with exit 1"))
        self.assertFalse(self._is_automation("this value is set automatically by the runtime"))
        self.assertFalse(self._is_automation("the automated check posted a comment on the PR"))


class ProjectMatchTests(unittest.TestCase):
    DIR = "-Users-tianning-li-DataDog-datadog-agent-internal"

    def test_real_filesystem_path_matches(self):
        self.assertTrue(
            ac.project_matches(self.DIR, "/Users/tianning.li/DataDog/datadog-agent-internal")
        )

    def test_folder_basename_matches(self):
        self.assertTrue(ac.project_matches(self.DIR, "datadog-agent-internal"))

    def test_encoded_dir_name_matches(self):
        self.assertTrue(ac.project_matches(self.DIR, self.DIR))

    def test_unrelated_project_does_not_match(self):
        self.assertFalse(ac.project_matches(self.DIR, "/Users/tianning.li/DataDog/dd-trace-js"))


class RecurrenceTests(unittest.TestCase):
    def _analyze(self, records_per_session: list[list[dict]]):
        sessions = [ac.extract_session_data(write_session(recs)) for recs in records_per_session]
        return ac.analyze(sessions)

    def test_corrections_grouped_with_count(self):
        findings = self._analyze(
            [
                [user("no, don't do that"), user("no, don't do that either")],
                [user("no, don't run it")],
            ]
        )
        corr = findings["corrections"]
        self.assertTrue(corr, "expected at least one correction group")
        # Each item must carry a recurrence count and example list.
        top = corr[0]
        self.assertIn("count", top)
        self.assertIn("examples", top)
        self.assertGreaterEqual(top["count"], 3)
        # Groups are sorted by frequency descending.
        counts = [item["count"] for item in corr]
        self.assertEqual(counts, sorted(counts, reverse=True))

    def test_example_text_is_single_line(self):
        # Multi-line user messages must be collapsed so they don't break the report layout.
        findings = self._analyze(
            [[user("no, don't do that.\n\nDetermine if ANY of these:\n1. foo\n2. bar")]]
        )
        example = findings["corrections"][0]["examples"][0]
        self.assertNotIn("\n", example)
        self.assertNotIn("  ", example)

    def test_sessions_counted_distinctly(self):
        findings = self._analyze(
            [
                [user("no, don't do that")],
                [user("no, don't do that")],
            ]
        )
        top = findings["corrections"][0]
        self.assertEqual(top["sessions"], 2)

    def test_message_matching_multiple_patterns_counted_once(self):
        # A message that matches two patterns in the same category should only be counted
        # once across all groups — it gets attributed to the first matched pattern only.
        # "please don't do that" matches both "please don't..." and "don't do..."
        findings = self._analyze([[user("please don't do that")]])
        total_counts = sum(g["count"] for g in findings["corrections"])
        # Should be 1, not 2 (one per matched pattern).
        self.assertEqual(total_counts, 1)

    def test_total_count_not_inflated_across_groups(self):
        # With 3 distinct messages that each match one pattern, total should be 3.
        findings = self._analyze([[
            user("no, don't do that"),
            user("that's not what I asked"),
            user("please revert this change"),
        ]])
        total = sum(g["count"] for g in findings["corrections"])
        self.assertEqual(total, 3)


def tool_use_block(id: str, name: str) -> dict:
    return {"type": "tool_use", "id": id, "name": name, "input": {}}


def tool_result_error(tool_use_id: str, text: str) -> dict:
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "is_error": True,
        "content": [{"type": "text", "text": text}],
    }


def assistant_with_tool_use(tool_id: str, tool_name: str) -> dict:
    return {
        "type": "assistant",
        "timestamp": "2026-06-01T00:00:00Z",
        "message": {"content": [tool_use_block(tool_id, tool_name)]},
    }


def user_with_tool_result_error(tool_use_id: str, error_text: str) -> dict:
    return {
        "type": "user",
        "timestamp": "2026-06-01T00:00:01Z",
        "message": {"content": [tool_result_error(tool_use_id, error_text)]},
    }


class ToolFailureExtractionTests(unittest.TestCase):
    def test_unread_write_error_detected(self):
        path = write_session([
            assistant_with_tool_use("id1", "Edit"),
            user_with_tool_result_error("id1", "<tool_use_error>File has not been read yet. Read it first before writing to it.</tool_use_error>"),
        ])
        sess = ac.extract_session_data(path)
        self.assertEqual(len(sess["tool_failures"]), 1)
        tf = sess["tool_failures"][0]
        self.assertEqual(tf["tool"], "Edit")
        self.assertEqual(tf["error_category"], "unread_write")

    def test_bash_file_not_found_classified(self):
        path = write_session([
            assistant_with_tool_use("id2", "Bash"),
            user_with_tool_result_error("id2", "Exit code 128\nfatal: pathspec 'foo/bar.md' did not match any files"),
        ])
        sess = ac.extract_session_data(path)
        self.assertEqual(sess["tool_failures"][0]["error_category"], "file_not_found")

    def test_bash_wrong_context_classified(self):
        path = write_session([
            assistant_with_tool_use("id3", "Bash"),
            user_with_tool_result_error("id3", "Exit code 1\nError: Current directory is not inside a DataDog repository"),
        ])
        sess = ac.extract_session_data(path)
        self.assertEqual(sess["tool_failures"][0]["error_category"], "wrong_context")

    def test_bash_nonzero_generic_classified(self):
        path = write_session([
            assistant_with_tool_use("id4", "Bash"),
            user_with_tool_result_error("id4", "Exit code 1\nsome random error"),
        ])
        sess = ac.extract_session_data(path)
        self.assertEqual(sess["tool_failures"][0]["error_category"], "bash_nonzero")

    def test_tool_name_resolved_from_tool_use(self):
        path = write_session([
            assistant_with_tool_use("abc123", "Write"),
            user_with_tool_result_error("abc123", "<tool_use_error>File has not been read yet.</tool_use_error>"),
        ])
        sess = ac.extract_session_data(path)
        self.assertEqual(sess["tool_failures"][0]["tool"], "Write")

    def test_successful_tool_result_not_counted(self):
        path = write_session([
            assistant_with_tool_use("id5", "Bash"),
            {
                "type": "user",
                "timestamp": "2026-06-01T00:00:01Z",
                "message": {"content": [{"type": "tool_result", "tool_use_id": "id5", "content": [{"type": "text", "text": "ok"}]}]},
            },
        ])
        sess = ac.extract_session_data(path)
        self.assertEqual(sess["tool_failures"], [])

    def test_tool_failures_aggregated_across_sessions(self):
        def make_session():
            return write_session([
                assistant_with_tool_use("x1", "Edit"),
                user_with_tool_result_error("x1", "<tool_use_error>File has not been read yet.</tool_use_error>"),
            ])
        sessions = [ac.extract_session_data(make_session()) for _ in range(3)]
        findings = ac.analyze(sessions)
        self.assertEqual(len(findings["tool_failures"]), 1)
        top = findings["tool_failures"][0]
        self.assertEqual(top["tool"], "Edit")
        self.assertEqual(top["error_category"], "unread_write")
        self.assertEqual(top["count"], 3)
        self.assertEqual(top["sessions"], 3)

    def test_multiple_failure_categories_sorted_by_count(self):
        sessions = []
        # 3x unread_write
        for _ in range(3):
            sessions.append(ac.extract_session_data(write_session([
                assistant_with_tool_use("u1", "Edit"),
                user_with_tool_result_error("u1", "File has not been read yet."),
            ])))
        # 1x file_not_found
        sessions.append(ac.extract_session_data(write_session([
            assistant_with_tool_use("u2", "Bash"),
            user_with_tool_result_error("u2", "Exit code 128\nfatal: pathspec 'x' did not match any files"),
        ])))
        findings = ac.analyze(sessions)
        self.assertGreaterEqual(findings["tool_failures"][0]["count"], findings["tool_failures"][1]["count"])

    def test_tool_failure_example_is_single_line(self):
        # Multi-line error text (e.g. test runner output) must be collapsed so it
        # does not break the text report layout.
        multiline_error = "Exit code 1\n..EEEE.F..\n======\nERROR: test_compute_deltas"
        path = write_session([
            assistant_with_tool_use("id9", "Bash"),
            user_with_tool_result_error("id9", multiline_error),
        ])
        sessions = [ac.extract_session_data(path)]
        findings = ac.analyze(sessions)
        example = findings["tool_failures"][0]["examples"][0]
        self.assertNotIn("\n", example)
        self.assertNotIn("  ", example)

    def test_tool_unknown_when_id_not_matched(self):
        # tool_result references an ID that never appeared in a tool_use block
        path = write_session([
            user_with_tool_result_error("unknown-id", "some error"),
        ])
        sess = ac.extract_session_data(path)
        self.assertEqual(sess["tool_failures"][0]["tool"], "?")


    def test_tool_only_session_included_in_analysis(self):
        # A session with tool failures but no user messages must not be dropped.
        # Subagent sessions often have only tool calls with no conversational input.
        path = write_session([
            assistant_with_tool_use("id1", "Edit"),
            user_with_tool_result_error("id1", "<tool_use_error>File has not been read yet.</tool_use_error>"),
        ])
        sessions = [ac.extract_session_data(path)]
        # Verify extract_session_data captures the failure even with no user_messages
        self.assertEqual(len(sessions[0]["tool_failures"]), 1)
        self.assertEqual(sessions[0]["user_messages"], [])
        # Verify analyze() includes it (simulate the main() guard)
        included = [s for s in sessions if s["user_messages"] or s["tool_failures"] or s["hook_errors"]]
        self.assertEqual(len(included), 1)
        findings = ac.analyze(included)
        self.assertEqual(findings["tool_failures"][0]["count"], 1)


class ClassifyToolErrorTests(unittest.TestCase):
    def test_unread_write(self):
        self.assertEqual(ac.classify_tool_error("Edit", "File has not been read yet. Read it first."), "unread_write")

    def test_file_not_found_pathspec(self):
        self.assertEqual(ac.classify_tool_error("Bash", "fatal: pathspec 'x' did not match any files"), "file_not_found")

    def test_file_not_found_no_such_file(self):
        self.assertEqual(ac.classify_tool_error("Bash", "No such file or directory"), "file_not_found")

    def test_wrong_context(self):
        self.assertEqual(ac.classify_tool_error("Bash", "Error: not inside a git repository"), "wrong_context")

    def test_permission_denied(self):
        self.assertEqual(ac.classify_tool_error("Bash", "Permission denied"), "permission_denied")

    def test_git_error_exit_128(self):
        self.assertEqual(ac.classify_tool_error("Bash", "Exit code 128\nfatal: something"), "git_error")

    def test_bash_nonzero(self):
        self.assertEqual(ac.classify_tool_error("Bash", "Exit code 1\nsome error"), "bash_nonzero")

    def test_generic_fallback(self):
        self.assertEqual(ac.classify_tool_error("Bash", "something completely unknown"), "tool_use_error")


class DeltaTrackingTests(unittest.TestCase):
    def _findings_with_counts(self, corrections=0, missing=0, slow=0, automation=0, hooks=0):
        """Build a minimal findings dict with the given category totals."""
        def _groups(n):
            return [{"count": n, "sessions": 1, "pattern": "x", "top_project": "", "examples": [], "preceding_action": None}] if n else []
        findings = {
            "summary": {"sessions_analyzed": 1, "total_user_messages": 1, "date_range": {"earliest": None, "latest": None}, "projects": {}},
            "corrections": _groups(corrections),
            "missing_context": _groups(missing),
            "slow_start_context": _groups(slow),
            "automation_candidates": _groups(automation),
            "hook_errors": [{"hook_name": "h", "exit_code": 1, "stderr": "", "command": "c"}] * hooks,
        }
        return findings

    def test_compute_deltas_no_baseline_returns_empty(self):
        findings = self._findings_with_counts(corrections=5)
        self.assertEqual(ac.compute_deltas(findings, None), {})

    def test_compute_deltas_improvement(self):
        findings = self._findings_with_counts(corrections=22)
        baseline = {"category_totals": {"corrections": 30, "missing_context": 0, "slow_start_context": 0, "automation_candidates": 0}, "hook_error_count": 0}
        deltas = ac.compute_deltas(findings, baseline)
        d = deltas["corrections"]
        self.assertEqual(d["current"], 22)
        self.assertEqual(d["previous"], 30)
        self.assertEqual(d["delta"], -8)
        self.assertEqual(d["pct_change"], -27)

    def test_compute_deltas_regression(self):
        findings = self._findings_with_counts(corrections=10)
        baseline = {"category_totals": {"corrections": 5, "missing_context": 0, "slow_start_context": 0, "automation_candidates": 0}, "hook_error_count": 0}
        deltas = ac.compute_deltas(findings, baseline)
        d = deltas["corrections"]
        self.assertEqual(d["delta"], 5)
        self.assertEqual(d["pct_change"], 100)

    def test_compute_deltas_no_previous_pct_is_none(self):
        findings = self._findings_with_counts(corrections=3)
        baseline = {"category_totals": {"corrections": 0, "missing_context": 0, "slow_start_context": 0, "automation_candidates": 0}, "hook_error_count": 0}
        deltas = ac.compute_deltas(findings, baseline)
        self.assertIsNone(deltas["corrections"]["pct_change"])

    def test_fmt_delta_improvement(self):
        d = {"current": 22, "previous": 30, "delta": -8, "pct_change": -27}
        self.assertEqual(ac._fmt_delta(d), ", was 30, -27% ↓")

    def test_fmt_delta_regression(self):
        d = {"current": 10, "previous": 5, "delta": 5, "pct_change": 100}
        self.assertEqual(ac._fmt_delta(d), ", was 5, +100% ↑")

    def test_fmt_delta_no_change(self):
        d = {"current": 5, "previous": 5, "delta": 0, "pct_change": 0}
        self.assertEqual(ac._fmt_delta(d), ", was 5, 0% →")

    def test_fmt_delta_none_returns_empty(self):
        self.assertEqual(ac._fmt_delta(None), "")

    def test_save_and_load_baseline_roundtrip(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmp_path = Path(f.name)
        try:
            findings = self._findings_with_counts(corrections=7, hooks=2)
            ac.save_baseline(findings, "myproject", path=tmp_path)
            loaded = ac.load_baseline("myproject", path=tmp_path)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["category_totals"]["corrections"], 7)
            self.assertEqual(loaded["hook_error_count"], 2)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_save_baseline_multiple_keys(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmp_path = Path(f.name)
        try:
            findings_a = self._findings_with_counts(corrections=3)
            findings_b = self._findings_with_counts(corrections=9)
            ac.save_baseline(findings_a, "proj-a", path=tmp_path)
            ac.save_baseline(findings_b, "proj-b", path=tmp_path)
            # Both keys survive independently
            self.assertEqual(ac.load_baseline("proj-a", path=tmp_path)["category_totals"]["corrections"], 3)
            self.assertEqual(ac.load_baseline("proj-b", path=tmp_path)["category_totals"]["corrections"], 9)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_load_baseline_missing_file_returns_none(self):
        self.assertIsNone(ac.load_baseline("x", path=Path("/tmp/nonexistent-baseline-xyz.json")))

    def test_load_baseline_global_key(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmp_path = Path(f.name)
        try:
            findings = self._findings_with_counts(corrections=1)
            ac.save_baseline(findings, None, path=tmp_path)
            loaded = ac.load_baseline(None, path=tmp_path)
            self.assertIsNotNone(loaded)
        finally:
            tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
