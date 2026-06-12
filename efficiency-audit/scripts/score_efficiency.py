#!/usr/bin/env python3
"""
score_efficiency.py — byte-efficiency scorer for Claude Code configuration files.

Uses piecewise linear interpolation between control points to score how "bloated"
a configuration file is. A score of 1.0 is ideal; 0.0 is a Critical Context Blocker.

Control points (line count → efficiency score):
       0  → 1.00  (optimal — empty or tiny)
     300  → 1.00  (sweet spot ceiling)
     750  → 0.50  (warning threshold)
    5000  → 0.00  (p_zero — Critical Context Blocker)
   >5000  → 0.00  (Critical Context Blocker regardless of content)

Usage:
    python3 score_efficiency.py <file_path> [<file_path> ...]
    python3 score_efficiency.py ~/.claude/CLAUDE.md
    python3 score_efficiency.py ~/.claude/CLAUDE.md ~/.claude/projects/*/CLAUDE.md
"""

import argparse
import sys
from pathlib import Path


# Piecewise linear control points: (line_count, efficiency_score)
CONTROL_POINTS: list[tuple[int, float]] = [
    (0,    1.00),
    (300,  1.00),
    (750,  0.50),
    (5000, 0.00),
]

P_ZERO = 5000  # lines — at or above this → Critical Context Blocker
RECIPE_BOOK_THRESHOLD = 200  # lines — above this → Recipe Book remediation needed


def efficiency_score(lines: int) -> float:
    """Return efficiency score in [0.0, 1.0] via piecewise linear interpolation."""
    if lines >= P_ZERO:
        return 0.0
    for i in range(len(CONTROL_POINTS) - 1):
        x0, y0 = CONTROL_POINTS[i]
        x1, y1 = CONTROL_POINTS[i + 1]
        if x0 <= lines <= x1:
            t = (lines - x0) / (x1 - x0) if x1 != x0 else 0.0
            return round(y0 + t * (y1 - y0), 4)
    return 0.0


def recipe_book_alert(lines: int) -> bool:
    """True when a file has enough rules to warrant the Recipe Book refactor procedure."""
    return lines > RECIPE_BOOK_THRESHOLD


def diagnosis(score: float) -> str:
    if score == 0.0:
        return "Critical Context Blocker"
    if score >= 0.90:
        return "Optimal"
    if score >= 0.70:
        return "Good"
    if score >= 0.50:
        return "Warning — consider trimming"
    return "Critical — significant bloat"


def score_file(path: Path) -> dict | None:
    """Score one file. Returns None if the file cannot be read."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    lines = len(text.splitlines())  # splitlines() counts correctly with or without trailing newline
    score = efficiency_score(lines)
    return {
        "path": str(path),
        "lines": lines,
        "bytes": len(text.encode("utf-8")),
        "score": score,
        "diagnosis": diagnosis(score),
        "recipe_book_alert": recipe_book_alert(lines),
    }


def _bar(score: float, width: int = 20) -> str:
    filled = round(score * width)
    color = "█" * filled + "░" * (width - filled)
    return f"[{color}] {score:.2f}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Score the byte-efficiency of Claude Code config files"
    )
    parser.add_argument("files", nargs="+", help="Files to score")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of text")
    args = parser.parse_args()

    results = []
    for f in args.files:
        r = score_file(Path(f))
        if r is None:
            continue  # non-existent or unreadable — skip silently
        results.append(r)

    if args.json:
        import json
        print(json.dumps(results, indent=2))
        return 0

    if not results:
        return 0  # nothing to score — not an error, just nothing to report

    print(f"\n{'File':<45} {'Lines':>6}  {'Bytes':>8}  Score            Diagnosis")
    print("─" * 100)
    exit_code = 0
    for r in results:
        name = Path(r["path"]).name
        bar = _bar(r["score"])
        print(f"  {name:<43} {r['lines']:>6}  {r['bytes']:>8}  {bar}  {r['diagnosis']}")
        if r["score"] == 0.0:
            exit_code = 1
    print()

    blockers = [r for r in results if r["score"] == 0.0]
    if blockers:
        print(f"⚠️  {len(blockers)} Critical Context Blocker(s) detected!")
        for b in blockers:
            print(f"   → {b['path']} ({b['lines']} lines) — must be trimmed before it is useful.")
        print()

    recipe_alerts = [r for r in results if r.get("recipe_book_alert")]
    if recipe_alerts:
        print(f"📋 Recipe Book remediation needed ({len(recipe_alerts)} file(s) exceed {RECIPE_BOOK_THRESHOLD} lines):")
        for r in recipe_alerts:
            print(f"   → {r['path']} ({r['lines']} lines) — extract domain-scoped rules into .claude/rules/*.md")
        print(f"   Run the efficiency-audit skill for the guided 4-step procedure.")
        print()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
