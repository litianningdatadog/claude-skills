#!/usr/bin/env python3
"""
Tests for score_efficiency.py. Stdlib only.

    python3 -m unittest test_score_efficiency
"""

import tempfile
import unittest
from pathlib import Path

import score_efficiency as se


def write_lines(n: int) -> Path:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False)
    tmp.write("\n".join(["x"] * n) + "\n")
    tmp.close()
    return Path(tmp.name)


class InterpolationTests(unittest.TestCase):
    def test_zero_lines_is_perfect(self):
        self.assertAlmostEqual(se.efficiency_score(0), 1.0)

    def test_within_sweet_spot_is_perfect(self):
        self.assertAlmostEqual(se.efficiency_score(150), 1.0)
        self.assertAlmostEqual(se.efficiency_score(300), 1.0)

    def test_midpoint_warning_zone(self):
        # midpoint of [300, 750] → midpoint of [1.0, 0.5] = 0.75
        self.assertAlmostEqual(se.efficiency_score(525), 0.75)

    def test_warning_threshold(self):
        self.assertAlmostEqual(se.efficiency_score(750), 0.5)

    def test_midpoint_danger_zone(self):
        # midpoint of [750, 5000] → midpoint of [0.5, 0.0] = 0.25
        self.assertAlmostEqual(se.efficiency_score(2875), 0.25)

    def test_at_p_zero(self):
        self.assertAlmostEqual(se.efficiency_score(5000), 0.0)

    def test_beyond_p_zero_is_zero(self):
        self.assertAlmostEqual(se.efficiency_score(9999), 0.0)
        self.assertAlmostEqual(se.efficiency_score(1_000_000), 0.0)

    def test_score_decreases_monotonically(self):
        checkpoints = [0, 100, 300, 400, 600, 750, 1000, 2000, 5000, 6000]
        scores = [se.efficiency_score(n) for n in checkpoints]
        for i in range(len(scores) - 1):
            self.assertGreaterEqual(scores[i], scores[i + 1])


class DiagnosisTests(unittest.TestCase):
    def test_optimal_label(self):
        self.assertEqual(se.diagnosis(1.0), "Optimal")

    def test_good_label(self):
        self.assertEqual(se.diagnosis(0.85), "Good")

    def test_warning_label(self):
        self.assertEqual(se.diagnosis(0.6), "Warning — consider trimming")

    def test_critical_label(self):
        self.assertEqual(se.diagnosis(0.3), "Critical — significant bloat")

    def test_blocker_label(self):
        self.assertEqual(se.diagnosis(0.0), "Critical Context Blocker")


class RecipeBookAlertTests(unittest.TestCase):
    def test_no_alert_below_threshold(self):
        self.assertFalse(se.recipe_book_alert(199))
        self.assertFalse(se.recipe_book_alert(200))

    def test_alert_above_threshold(self):
        self.assertTrue(se.recipe_book_alert(201))
        self.assertTrue(se.recipe_book_alert(5000))

    def test_score_file_includes_recipe_book_alert(self):
        path = write_lines(50)
        result = se.score_file(path)
        self.assertIn("recipe_book_alert", result)
        self.assertFalse(result["recipe_book_alert"])

    def test_score_file_recipe_book_alert_fires_over_200(self):
        path = write_lines(201)
        result = se.score_file(path)
        self.assertTrue(result["recipe_book_alert"])

    def test_text_report_shows_recipe_book_warning(self):
        # The CLI text output should mention the Recipe Book when alert fires.
        path = write_lines(201)
        import subprocess, sys
        out = subprocess.run(
            [sys.executable, "score_efficiency.py", str(path)],
            capture_output=True, text=True
        ).stdout
        self.assertIn("Recipe Book", out)

    def test_text_report_no_recipe_book_warning_when_healthy(self):
        path = write_lines(50)
        import subprocess, sys
        out = subprocess.run(
            [sys.executable, "score_efficiency.py", str(path)],
            capture_output=True, text=True
        ).stdout
        self.assertNotIn("Recipe Book", out)


class FileTests(unittest.TestCase):
    def test_score_file_counts_lines(self):
        path = write_lines(400)
        result = se.score_file(path)
        self.assertEqual(result["lines"], 400)

    def test_score_file_counts_lines_without_trailing_newline(self):
        # Files without a trailing newline must not undercount by 1.
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False)
        tmp.write("\n".join(["x"] * 400))  # no trailing newline
        tmp.close()
        result = se.score_file(Path(tmp.name))
        self.assertEqual(result["lines"], 400)
        self.assertLess(result["score"], 1.0)
        self.assertGreater(result["score"], 0.5)

    def test_score_file_includes_bytes(self):
        path = write_lines(10)
        result = se.score_file(path)
        self.assertIn("bytes", result)
        self.assertGreater(result["bytes"], 0)

    def test_score_file_missing_returns_none(self):
        # score_file returns None for missing files — callers skip silently, no output.
        self.assertIsNone(se.score_file(Path("/nonexistent/file.md")))

    def test_critical_blocker_flag(self):
        path = write_lines(5001)
        result = se.score_file(path)
        self.assertEqual(result["score"], 0.0)
        self.assertIn("Critical Context Blocker", result["diagnosis"])


if __name__ == "__main__":
    unittest.main()
