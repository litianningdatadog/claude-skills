#!/usr/bin/env python3
"""
Tests for synthesize_findings.py.

Stdlib only. Run with:
    python3 -m unittest test_synthesize_findings
"""

import json
import unittest

import synthesize_findings as sf


def _findings(
    sessions=5,
    corrections=None,
    missing=None,
    tool_failures=None,
    deltas=None,
    hook_errors=None,
):
    def _groups(items):
        return items or []

    return {
        "summary": {
            "sessions_analyzed": sessions,
            "total_user_messages": sessions * 3,
            "date_range": {"earliest": "2026-06-01T00:00:00Z", "latest": "2026-06-16T00:00:00Z"},
            "projects": {},
        },
        "corrections": _groups(corrections),
        "missing_context": _groups(missing),
        "slow_start_context": [],
        "automation_candidates": [],
        "tool_failures": _groups(tool_failures),
        "hook_errors": _groups(hook_errors),
        "deltas": deltas or {},
    }


def _correction(count=3, sessions=2, example="no, don't commit", preceding="I committed as abc123"):
    return {
        "pattern": r"\bno[,!]?\s+don't\b",
        "count": count,
        "sessions": sessions,
        "top_project": "myrepo",
        "examples": [example],
        "preceding_action": preceding,
    }


def _tool_failure(tool="Edit", category="unread_write", count=7, sessions=2):
    return {
        "tool": tool,
        "error_category": category,
        "count": count,
        "sessions": sessions,
        "examples": ["<tool_use_error>File has not been read yet.</tool_use_error>"],
    }


class BuildDigestTests(unittest.TestCase):
    def test_summary_included(self):
        digest = sf.build_digest(_findings(sessions=24))
        self.assertIn("Sessions: 24", digest)

    def test_date_range_included(self):
        digest = sf.build_digest(_findings())
        self.assertIn("2026-06-01", digest)
        self.assertIn("2026-06-16", digest)

    def test_corrections_section_present(self):
        f = _findings(corrections=[_correction(count=5)])
        digest = sf.build_digest(f)
        self.assertIn("Corrections", digest)
        self.assertIn("5x", digest)

    def test_preceding_action_included_for_corrections(self):
        f = _findings(corrections=[_correction(preceding="I ran git commit -m 'fix'")])
        digest = sf.build_digest(f)
        self.assertIn("I ran git commit", digest)

    def test_tool_failures_section_present(self):
        f = _findings(tool_failures=[_tool_failure(count=7)])
        digest = sf.build_digest(f)
        self.assertIn("Tool Failures", digest)
        self.assertIn("Edit/unread_write", digest)
        self.assertIn("7x", digest)

    def test_no_sections_when_empty(self):
        f = _findings()
        digest = sf.build_digest(f)
        self.assertNotIn("Corrections", digest)
        self.assertNotIn("Tool Failures", digest)

    def test_delta_section_present_when_has_previous(self):
        f = _findings(deltas={
            "corrections": {"current": 5, "previous": 10, "delta": -5, "pct_change": -50},
        })
        digest = sf.build_digest(f)
        self.assertIn("Changes vs previous audit", digest)
        self.assertIn("corrections", digest)

    def test_delta_section_absent_when_no_previous(self):
        f = _findings(deltas={
            "corrections": {"current": 5, "previous": 0, "delta": 5, "pct_change": None},
        })
        digest = sf.build_digest(f)
        self.assertNotIn("Changes vs previous audit", digest)

    def test_hook_errors_section_present(self):
        f = _findings(hook_errors=[{"hook_name": "stop.py", "exit_code": 1, "command": "python3 stop.py", "stderr": ""}])
        digest = sf.build_digest(f)
        self.assertIn("Hook Errors", digest)
        self.assertIn("stop.py", digest)

    def test_digest_capped_at_max_chars(self):
        # Build findings with many long entries to exceed the cap
        big_example = "x" * 200
        corrections = [_correction(count=i, example=big_example) for i in range(1, 50)]
        f = _findings(corrections=corrections)
        digest = sf.build_digest(f)
        self.assertLessEqual(len(digest), sf.MAX_DIGEST_CHARS)

    def test_empty_findings_does_not_crash(self):
        digest = sf.build_digest({})
        self.assertIsInstance(digest, str)


class ExtractJsonTests(unittest.TestCase):
    def test_clean_json_parsed(self):
        raw = '{"recommendations": [{"proposed_rule": "NEVER commit", "estimated_tokens_saved": 200}]}'
        result = sf.extract_json(raw)
        self.assertEqual(result["recommendations"][0]["proposed_rule"], "NEVER commit")

    def test_json_with_markdown_fences_stripped(self):
        raw = "```json\n{\"recommendations\": []}\n```"
        result = sf.extract_json(raw)
        self.assertEqual(result["recommendations"], [])

    def test_json_with_leading_prose_extracted(self):
        raw = "Here are the recommendations:\n\n{\"recommendations\": [{\"proposed_rule\": \"NEVER ...\"}]}"
        result = sf.extract_json(raw)
        self.assertEqual(len(result["recommendations"]), 1)

    def test_no_json_raises_value_error(self):
        with self.assertRaises(ValueError):
            sf.extract_json("Sorry, I cannot help with that.")

    def test_invalid_json_raises_decode_error(self):
        with self.assertRaises((ValueError, Exception)):
            sf.extract_json("{bad json here}")

    def test_nested_json_preserved(self):
        raw = '{"recommendations": [{"proposed_rule": "x", "estimated_tokens_saved": 100, "scope": "global", "target": "CLAUDE.md", "evidence": "y", "confidence": "high"}]}'
        result = sf.extract_json(raw)
        rec = result["recommendations"][0]
        self.assertEqual(rec["confidence"], "high")
        self.assertEqual(rec["scope"], "global")


if __name__ == "__main__":
    unittest.main()
