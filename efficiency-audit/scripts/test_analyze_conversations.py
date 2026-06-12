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


class BaselineTests(unittest.TestCase):
    def setUp(self):
        import tempfile, os
        self.tmp = tempfile.mkdtemp()
        self._orig_home = os.environ.get("HOME")
        os.environ["HOME"] = self.tmp

    def tearDown(self):
        import os
        if self._orig_home is not None:
            os.environ["HOME"] = self._orig_home

    def _findings(self, n_corrections=2):
        sessions = [ac.extract_session_data(write_session(
            [user("no, don't do that")] * n_corrections
        ))]
        return ac.analyze(sessions)

    def test_save_and_load_baseline(self):
        findings = self._findings(2)
        ac.save_baseline(findings, days=30, project="proj-a")
        bl = ac.load_baseline(days=30, project="proj-a")
        self.assertIsNotNone(bl)
        self.assertEqual(bl["corrections"], 2)
        self.assertEqual(bl["project"], "proj-a")
        self.assertEqual(bl["days"], 30)

    def test_baseline_scoped_to_project_and_days(self):
        findings = self._findings(2)
        ac.save_baseline(findings, days=30, project="proj-a")
        # Different project → no baseline.
        self.assertIsNone(ac.load_baseline(days=30, project="proj-b"))
        # Different days window → no baseline.
        self.assertIsNone(ac.load_baseline(days=7, project="proj-a"))

    def test_delta_string_shows_change(self):
        self.assertEqual(ac.delta_str(22, 30), "was 30, -27% ↓")
        self.assertEqual(ac.delta_str(30, 22), "was 22, +36% ↑")
        self.assertEqual(ac.delta_str(5, 5), "was 5, no change")
        self.assertIsNone(ac.delta_str(5, None))  # no baseline → no delta

    def test_save_overwrites_previous(self):
        ac.save_baseline(self._findings(2), days=30, project="p")
        ac.save_baseline(self._findings(4), days=30, project="p")
        bl = ac.load_baseline(days=30, project="p")
        self.assertEqual(bl["corrections"], 4)


if __name__ == "__main__":
    unittest.main()
