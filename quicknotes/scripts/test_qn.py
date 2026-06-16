#!/usr/bin/env python3
"""
Integration tests for the qn CLI dispatch. Stdlib only.

    python3 -m unittest test_qn
"""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

import re

import qn
import notes_store as ns


class CLITests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        os.environ["QUICKNOTES_HOME"] = self.home

    def tearDown(self):
        os.environ.pop("QUICKNOTES_HOME", None)

    def run_cli(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = qn.main(argv)
        return code, buf.getvalue()

    def test_no_verb_captures(self):
        code, out = self.run_cli(["remember", "to", "rotate", "creds"])
        self.assertEqual(code, 0)
        self.assertIn("✓ noted", out)
        self.assertEqual(len(ns.list_notes(self.home)), 1)

    def test_add_forces_capture_of_verb_word(self):
        # "list the steps" starts with a reserved verb; `add` forces capture.
        code, _ = self.run_cli(["add", "list", "the", "migration", "steps"])
        self.assertEqual(code, 0)
        notes = ns.list_notes(self.home)
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["title"], "list the migration steps")

    def test_done_deletes_note(self):
        self.run_cli(["deploy", "the", "service"])
        self.assertEqual(len(ns.list_notes(self.home)), 1)
        code, out = self.run_cli(["done", "deploy"])
        self.assertEqual(code, 0)
        self.assertIn("✓ done (removed)", out)
        self.assertEqual(ns.list_notes(self.home), [])  # file removed

    def test_done_ambiguous_reports_candidates_and_keeps_notes(self):
        self.run_cli(["deploy", "one"])
        self.run_cli(["deploy", "two"])
        code, out = self.run_cli(["done", "deploy"])
        self.assertEqual(code, 1)
        self.assertIn("Ambiguous", out)
        self.assertEqual(len(ns.list_notes(self.home)), 2)  # nothing deleted

    def test_cancel_is_not_a_verb(self):
        # `cancel` was removed; it should be captured as a note, not treated as a command.
        code, _ = self.run_cli(["cancel", "the", "meeting"])
        self.assertEqual(code, 0)
        notes = ns.list_notes(self.home)
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["title"], "cancel the meeting")

    def test_show_prints_labeled_metadata_block(self):
        self.run_cli(["pgbouncer", "pool", "size"])
        nid = ns.list_notes(self.home)[0]["id"]
        self.run_cli(["update", nid, "--priority", "high", "--tag", "db",
                      "--due", "2026-06-12T17:00:00Z"])
        code, out = self.run_cli(["show", nid])
        self.assertEqual(code, 0)
        for label in ("Id:", "Created:", "Updated:", "Priority:",
                      "Due:", "Project:", "Branch:", "Tags:"):
            self.assertIn(label, out)
        self.assertIn("high", out)
        self.assertIn("db", out)
        self.assertIn("pgbouncer pool size", out)  # body present

    def test_capture_inline_hashtags(self):
        code, out = self.run_cli(["buy", "milk", "#groceries", "#Errands"])
        self.assertEqual(code, 0)
        note = ns.list_notes(self.home)[0]
        self.assertEqual(note["title"], "buy milk")          # hashtags stripped from text
        self.assertEqual(note["tags"], ["groceries", "errands"])  # normalized

    def test_capture_tag_flag(self):
        self.run_cli(["deploy", "service", "--tag", "Ops"])
        self.assertEqual(ns.list_notes(self.home)[0]["tags"], ["ops"])

    def test_capture_combines_flag_and_inline(self):
        self.run_cli(["x", "#a", "--tag", "b"])
        self.assertEqual(set(ns.list_notes(self.home)[0]["tags"]), {"a", "b"})

    def test_add_supports_hashtags(self):
        self.run_cli(["add", "list", "the", "steps", "#planning"])
        note = ns.list_notes(self.home)[0]
        self.assertEqual(note["title"], "list the steps")
        self.assertEqual(note["tags"], ["planning"])

    def test_update_inline_hashtag(self):
        self.run_cli(["fix", "the", "deploy"])
        nid = ns.list_notes(self.home)[0]["id"]
        code, _ = self.run_cli(["update", nid, "#urgent"])
        self.assertEqual(code, 0)
        self.assertEqual(ns.get(self.home, nid)["tags"], ["urgent"])

    def test_search(self):
        self.run_cli(["postgres", "connection", "pool"])
        code, out = self.run_cli(["search", "postgres"])
        self.assertEqual(code, 0)
        self.assertIn("postgres", out.lower())

    def test_show_displays_local_time_not_utc(self):
        """Created/Updated/Due must not appear as raw UTC ISO strings."""
        self.run_cli(["pgbouncer", "pool", "size"])
        nid = ns.list_notes(self.home)[0]["id"]
        self.run_cli(["update", nid, "--due", "2026-06-16T20:00:00Z"])
        code, out = self.run_cli(["show", nid])
        self.assertEqual(code, 0)
        created_val = out.split("Created:")[1].split("\n")[0]
        due_val = out.split("Due:")[1].split("\n")[0]
        # Raw ISO date-time separator (digit T digit) must not appear
        self.assertIsNone(re.search(r'\d{2}T\d{2}', created_val),
                          "Created should not contain raw ISO 'T' separator")
        # Raw ISO date-time separator and UTC 'Z' suffix must not appear
        self.assertIsNone(re.search(r'\d{2}T\d{2}', due_val),
                          "Due should not contain raw ISO 'T' separator")
        self.assertFalse(due_val.strip().endswith("Z"),
                         "Due should not end with raw UTC 'Z' suffix")


class DisplayTimeTests(unittest.TestCase):
    def test_utc_string_converts_to_local(self):
        result = qn._display_time("2026-06-16T20:00:00Z")
        # Raw ISO date-time separator must not appear
        self.assertIsNone(re.search(r'\d{2}T\d{2}', result),
                          "Should not contain raw ISO 'T' separator")
        # Raw UTC 'Z' suffix must not appear
        self.assertFalse(result.strip().endswith("Z"),
                         "Should not end with raw UTC 'Z' suffix")
        # Should be a non-empty string
        self.assertTrue(result)

    def test_none_returns_none(self):
        self.assertIsNone(qn._display_time(None))

    def test_empty_string_returns_empty(self):
        self.assertEqual(qn._display_time(""), "")

    def test_malformed_string_returns_as_is(self):
        self.assertEqual(qn._display_time("not-a-date"), "not-a-date")


if __name__ == "__main__":
    unittest.main()
