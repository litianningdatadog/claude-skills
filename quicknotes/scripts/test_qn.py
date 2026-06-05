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

    def test_search(self):
        self.run_cli(["postgres", "connection", "pool"])
        code, out = self.run_cli(["search", "postgres"])
        self.assertEqual(code, 0)
        self.assertIn("postgres", out.lower())


if __name__ == "__main__":
    unittest.main()
