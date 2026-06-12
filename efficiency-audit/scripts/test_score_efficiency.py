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


class FileTests(unittest.TestCase):
    def test_score_file_counts_lines(self):
        path = write_lines(400)
        result = se.score_file(path)
        self.assertEqual(result["lines"], 400)
        self.assertLess(result["score"], 1.0)
        self.assertGreater(result["score"], 0.5)

    def test_score_file_includes_bytes(self):
        path = write_lines(10)
        result = se.score_file(path)
        self.assertIn("bytes", result)
        self.assertGreater(result["bytes"], 0)

    def test_score_file_missing_returns_none(self):
        self.assertIsNone(se.score_file(Path("/nonexistent/file.md")))

    def test_critical_blocker_flag(self):
        path = write_lines(5001)
        result = se.score_file(path)
        self.assertEqual(result["score"], 0.0)
        self.assertIn("Critical Context Blocker", result["diagnosis"])


if __name__ == "__main__":
    unittest.main()
