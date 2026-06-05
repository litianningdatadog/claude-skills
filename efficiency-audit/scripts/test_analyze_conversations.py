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


if __name__ == "__main__":
    unittest.main()
