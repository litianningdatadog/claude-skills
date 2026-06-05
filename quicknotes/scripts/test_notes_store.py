#!/usr/bin/env python3
"""
Tests for notes_store.py. Stdlib only.

Run from the scripts/ directory:
    python3 -m unittest test_notes_store
"""

import re
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

import notes_store as ns


def home() -> Path:
    return Path(tempfile.mkdtemp())


DT = datetime(2026, 6, 5, 15, 30, 12, tzinfo=timezone.utc)


class IdTests(unittest.TestCase):
    def test_format(self):
        self.assertEqual(ns.new_id(now=DT, rand="a1b2"), "20260605-153012-a1b2")

    def test_default_matches_pattern(self):
        self.assertRegex(ns.new_id(), r"^\d{8}-\d{6}-[0-9a-f]{4}$")


class CaptureTests(unittest.TestCase):
    def test_capture_writes_file_and_metadata(self):
        h = home()
        note = ns.capture("pgbouncer pool size\nbump default_pool_size", home=h, now=DT,
                          project="claude-skills", cwd="/x/claude-skills", branch="main",
                          rand="a1b2")
        self.assertEqual(note["id"], "20260605-153012-a1b2")
        self.assertEqual(note["project"], "claude-skills")
        self.assertEqual(note["title"], "pgbouncer pool size")  # auto-derived from first line
        self.assertTrue((h / "notes" / "20260605-153012-a1b2.md").is_file())

    def test_explicit_title_and_tags(self):
        h = home()
        note = ns.capture("body text", home=h, now=DT, title="Custom", tags=["db", "perf"],
                          priority="high", cwd="/x/p", project="p", branch=None, rand="0000")
        self.assertEqual(note["title"], "Custom")
        self.assertEqual(note["tags"], ["db", "perf"])
        self.assertEqual(note["priority"], "high")

    def test_frontmatter_roundtrip(self):
        h = home()
        note = ns.capture("line one: with colon\nmore", home=h, now=DT,
                          tags=["a", "b"], cwd="/x/p", project="p", branch="feat/x", rand="0000")
        reloaded = ns.get(h, note["id"])
        for k in ("id", "title", "project", "cwd", "branch", "tags", "due", "refs"):
            self.assertEqual(reloaded[k], note[k], k)
        self.assertEqual(reloaded["body"], "line one: with colon\nmore")


class ListSearchTests(unittest.TestCase):
    def _seed(self):
        h = home()
        ns.capture("alpha deploy note", home=h, now=DT, project="proj-a", tags=["deploy"],
                   cwd="/x/proj-a", branch=None, rand="0001")
        ns.capture("beta db note", home=h, now=DT + timedelta(seconds=1), project="proj-b",
                   tags=["db"], cwd="/x/proj-b", branch=None, rand="0002")
        return h

    def test_list_newest_first(self):
        h = self._seed()
        ids = [n["id"] for n in ns.list_notes(h)]
        self.assertEqual(ids, sorted(ids, reverse=True))

    def test_list_filters(self):
        h = self._seed()
        self.assertEqual(len(ns.list_notes(h, project="proj-a")), 1)
        self.assertEqual(len(ns.list_notes(h, tag="db")), 1)

    def test_search_ranks_match(self):
        h = self._seed()
        results = ns.search(h, "db")
        self.assertTrue(results)
        self.assertIn("db", (results[0]["title"] + " ".join(results[0]["tags"])).lower())

    def test_malformed_file_skipped(self):
        h = self._seed()
        (h / "notes" / "garbage.md").write_text("not a note")
        self.assertEqual(len(ns.list_notes(h)), 2)  # garbage ignored, no crash


class LifecycleTests(unittest.TestCase):
    def test_complete_deletes_file(self):
        h = home()
        n = ns.capture("x", home=h, now=DT, cwd="/x/p", project="p", branch=None, rand="0000")
        path = Path(h) / "notes" / (n["id"] + ".md")
        self.assertTrue(path.is_file())
        returned = ns.complete(h, n["id"])
        self.assertEqual(returned["id"], n["id"])      # returns the note pre-delete
        self.assertFalse(path.is_file())               # file gone
        self.assertIsNone(ns.get(h, n["id"]))
        self.assertEqual(ns.list_notes(h), [])

    def test_complete_missing_returns_none(self):
        h = home()
        self.assertIsNone(ns.complete(h, "20990101-000000-zzzz"))

    def test_update_edits_fields(self):
        h = home()
        n = ns.capture("x", home=h, now=DT, cwd="/x/p", project="p", branch=None, rand="0000")
        up = ns.update(h, n["id"], now=DT, tags=["new"], priority="low", body="edited")
        self.assertEqual(up["tags"], ["new"])
        self.assertEqual(up["priority"], "low")
        self.assertEqual(ns.get(h, n["id"])["body"], "edited")

    def test_refs_are_bidirectional(self):
        h = home()
        a = ns.capture("a", home=h, now=DT, cwd="/x/p", project="p", branch=None, rand="000a")
        b = ns.capture("b", home=h, now=DT, cwd="/x/p", project="p", branch=None, rand="000b")
        self.assertTrue(ns.add_ref(h, a["id"], b["id"]))
        self.assertIn(b["id"], ns.get(h, a["id"])["refs"])
        self.assertIn(a["id"], ns.get(h, b["id"])["refs"])


class RemindersTests(unittest.TestCase):
    def test_due_selects_past_due_open(self):
        h = home()
        ns.capture("overdue", home=h, now=DT, due="2026-06-01T00:00:00Z",
                   cwd="/x/p", project="p", branch=None, rand="0001")
        ns.capture("future", home=h, now=DT, due="2099-01-01T00:00:00Z",
                   cwd="/x/p", project="p", branch=None, rand="0002")
        due = ns.due_notes(h, now=DT)
        self.assertEqual([n["title"] for n in due], ["overdue"])

    def test_here_matches_project(self):
        h = home()
        ns.capture("in proj", home=h, now=DT, project="claude-skills",
                   cwd="/x/claude-skills", branch=None, rand="0001")
        ns.capture("elsewhere", home=h, now=DT, project="other",
                   cwd="/x/other", branch=None, rand="0002")
        here = ns.here_notes(h, project="claude-skills", cwd="/x/claude-skills")
        self.assertEqual([n["title"] for n in here], ["in proj"])


class TargetingTests(unittest.TestCase):
    def test_resolve_exact_id(self):
        h = home()
        n = ns.capture("deploy the thing", home=h, now=DT, cwd="/x/p", project="p",
                       branch=None, rand="0000")
        note, cands = ns.resolve(h, n["id"])
        self.assertEqual(note["id"], n["id"])

    def test_resolve_unique_fuzzy(self):
        h = home()
        ns.capture("deploy the thing", home=h, now=DT, cwd="/x/p", project="p",
                   branch=None, rand="0000")
        note, cands = ns.resolve(h, "deploy")
        self.assertIsNotNone(note)

    def test_resolve_ambiguous_returns_candidates(self):
        h = home()
        ns.capture("deploy one", home=h, now=DT, cwd="/x/p", project="p", branch=None, rand="0001")
        ns.capture("deploy two", home=h, now=DT, cwd="/x/p", project="p", branch=None, rand="0002")
        note, cands = ns.resolve(h, "deploy")
        self.assertIsNone(note)
        self.assertEqual(len(cands), 2)


class SecurityTests(unittest.TestCase):
    def test_get_rejects_path_traversal(self):
        h = home()
        ns.capture("x", home=h, now=DT, cwd="/x/p", project="p", branch=None, rand="0000")
        self.assertIsNone(ns.get(h, "../../etc/passwd"))
        self.assertIsNone(ns.get(h, "/etc/passwd"))


if __name__ == "__main__":
    unittest.main()
