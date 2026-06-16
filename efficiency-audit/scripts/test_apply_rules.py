#!/usr/bin/env python3
"""
Tests for apply_rules.py.

Stdlib only. Run with:
    python3 -m unittest test_apply_rules
"""

import unittest

import apply_rules as ar

TIMESTAMP = "2026-06-16T12:00:00Z"


class ReadMarkerBlockTests(unittest.TestCase):
    def test_returns_empty_when_no_block(self):
        self.assertEqual(ar.read_marker_block("# CLAUDE.md\n\nSome content.\n"), [])

    def test_returns_empty_on_empty_string(self):
        self.assertEqual(ar.read_marker_block(""), [])

    def test_reads_rules_from_block(self):
        text = (
            "# CLAUDE.md\n\n"
            f"{ar.MARKER_START}\n"
            "<!-- Last updated: 2026-06-01 -->\n\n"
            "## Efficiency Audit Rules\n\n"
            "- NEVER commit without instruction\n"
            "- Always Read before Edit\n\n"
            f"{ar.MARKER_END}\n"
        )
        rules = ar.read_marker_block(text)
        self.assertEqual(rules, ["NEVER commit without instruction", "Always Read before Edit"])

    def test_ignores_non_rule_lines_inside_block(self):
        text = (
            f"{ar.MARKER_START}\n"
            "<!-- comment -->\n"
            "## Some header\n"
            "- actual rule\n"
            f"{ar.MARKER_END}\n"
        )
        self.assertEqual(ar.read_marker_block(text), ["actual rule"])

    def test_returns_empty_when_only_start_marker(self):
        text = f"{ar.MARKER_START}\n\nno end marker here"
        self.assertEqual(ar.read_marker_block(text), [])

    def test_returns_empty_when_only_end_marker(self):
        text = f"no start marker\n{ar.MARKER_END}\n"
        self.assertEqual(ar.read_marker_block(text), [])

    def test_returns_empty_block_with_no_rules(self):
        text = (
            f"{ar.MARKER_START}\n"
            "<!-- No rules approved yet -->\n"
            f"{ar.MARKER_END}\n"
        )
        self.assertEqual(ar.read_marker_block(text), [])


class WriteMarkerBlockTests(unittest.TestCase):
    def _write(self, text, rules):
        return ar.write_marker_block(text, rules, TIMESTAMP)

    def test_appends_block_when_none_exists(self):
        text = "# CLAUDE.md\n\nExisting content.\n"
        result = self._write(text, ["NEVER commit"])
        self.assertIn(ar.MARKER_START, result)
        self.assertIn(ar.MARKER_END, result)
        self.assertIn("NEVER commit", result)
        self.assertIn("Existing content.", result)

    def test_replaces_existing_block_in_place(self):
        original = (
            "# Header\n\n"
            f"{ar.MARKER_START}\n"
            "<!-- Last updated: 2026-06-01 -->\n"
            "- Old rule\n"
            f"{ar.MARKER_END}\n"
        )
        result = self._write(original, ["New rule"])
        self.assertIn("New rule", result)
        self.assertNotIn("Old rule", result)
        self.assertIn("# Header", result)

    def test_content_before_block_preserved(self):
        text = "# Pre-existing\n\nDo not touch this.\n\n" + ar.MARKER_START + "\n- old\n" + ar.MARKER_END + "\n"
        result = self._write(text, ["new rule"])
        self.assertIn("Do not touch this.", result)

    def test_content_after_block_preserved(self):
        text = (
            ar.MARKER_START + "\n- old\n" + ar.MARKER_END + "\n"
            "\nSome trailing content.\n"
        )
        result = self._write(text, ["new rule"])
        self.assertIn("Some trailing content.", result)

    def test_exactly_one_start_marker_after_replace(self):
        text = "Before\n\n" + ar.MARKER_START + "\n- r\n" + ar.MARKER_END + "\n"
        result = self._write(text, ["r2"])
        self.assertEqual(result.count(ar.MARKER_START), 1)
        self.assertEqual(result.count(ar.MARKER_END), 1)

    def test_exactly_one_start_marker_after_append(self):
        result = self._write("# File\n", ["rule"])
        self.assertEqual(result.count(ar.MARKER_START), 1)
        self.assertEqual(result.count(ar.MARKER_END), 1)

    def test_timestamp_written_to_block(self):
        result = self._write("", ["rule"])
        self.assertIn(TIMESTAMP, result)

    def test_empty_rules_writes_placeholder(self):
        result = self._write("# File\n", [])
        self.assertIn("No rules approved yet", result)
        self.assertNotIn("## Efficiency Audit Rules", result)

    def test_multiple_rules_all_written(self):
        rules = ["Rule A", "Rule B", "Rule C"]
        result = self._write("", rules)
        for r in rules:
            self.assertIn(r, result)

    def test_append_does_not_duplicate_on_empty_file(self):
        result = self._write("", ["rule"])
        self.assertEqual(result.count(ar.MARKER_START), 1)


class RoundTripTests(unittest.TestCase):
    def test_write_then_read_returns_same_rules(self):
        rules = ["NEVER commit without instruction", "Always Read before Edit"]
        text = ar.write_marker_block("# File\n", rules, TIMESTAMP)
        recovered = ar.read_marker_block(text)
        self.assertEqual(recovered, rules)

    def test_second_write_replaces_first(self):
        rules_v1 = ["Rule 1"]
        rules_v2 = ["Rule 2", "Rule 3"]
        text = ar.write_marker_block("# File\n", rules_v1, TIMESTAMP)
        text = ar.write_marker_block(text, rules_v2, TIMESTAMP)
        recovered = ar.read_marker_block(text)
        self.assertEqual(recovered, rules_v2)

    def test_three_rewrites_stable(self):
        text = "# File\n"
        for i in range(3):
            rules = [f"Rule {i}A", f"Rule {i}B"]
            text = ar.write_marker_block(text, rules, TIMESTAMP)
        self.assertEqual(text.count(ar.MARKER_START), 1)
        self.assertEqual(ar.read_marker_block(text), ["Rule 2A", "Rule 2B"])


if __name__ == "__main__":
    unittest.main()
