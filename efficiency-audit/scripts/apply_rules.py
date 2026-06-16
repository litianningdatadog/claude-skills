#!/usr/bin/env python3
"""
apply_rules.py — Idempotent marker-block writer for efficiency-audit rules.

Writes approved rules into a <!-- efficiency-audit:start/end --> block in a
CLAUDE.md file. On subsequent runs the block is replaced in-place rather than
appended, preventing duplicate rule accumulation.

Usage:
    # Read existing block (prints rules as JSON)
    python3 apply_rules.py --read ~/.claude/CLAUDE.md

    # Preview proposed change without writing (shows old vs new block)
    python3 apply_rules.py --dry-run ~/.claude/CLAUDE.md '["rule 1", "rule 2"]'

    # Write / update the block
    python3 apply_rules.py ~/.claude/CLAUDE.md '["rule 1", "rule 2"]'
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


MARKER_START = "<!-- efficiency-audit:start -->"
MARKER_END = "<!-- efficiency-audit:end -->"


def read_marker_block(text: str) -> list[str]:
    """Extract rules from an existing marker block. Returns [] if no block present."""
    start = text.find(MARKER_START)
    end = text.find(MARKER_END)
    if start == -1 or end == -1 or end <= start:
        return []
    inner = text[start + len(MARKER_START) : end]
    return [
        line.strip()[2:]
        for line in inner.splitlines()
        if line.strip().startswith("- ")
    ]


def _build_block(rules: list[str], timestamp: str) -> str:
    lines = [
        MARKER_START,
        f"<!-- Last updated: {timestamp} by efficiency-audit skill -->",
        "",
    ]
    if rules:
        lines.append("## Efficiency Audit Rules")
        lines.append("")
        for rule in rules:
            lines.append(f"- {rule}")
    else:
        lines.append("<!-- No rules approved yet -->")
    lines.append("")
    lines.append(MARKER_END)
    return "\n".join(lines)


def write_marker_block(text: str, rules: list[str], timestamp: str) -> str:
    """Return updated file text with the marker block written or replaced in-place."""
    block = _build_block(rules, timestamp)
    start = text.find(MARKER_START)
    end = text.find(MARKER_END)
    if start != -1 and end != -1 and end > start:
        # Replace existing block, preserving surrounding content exactly
        before = text[:start].rstrip("\n")
        after = text[end + len(MARKER_END) :].lstrip("\n")
        parts = [before, block]
        if after:
            parts.append(after)
        return "\n\n".join(parts) + "\n"
    else:
        # No existing block — append at end
        return text.rstrip("\n") + "\n\n" + block + "\n"


def _diff_blocks(old_rules: list[str], new_rules: list[str]) -> str:
    removed = [r for r in old_rules if r not in new_rules]
    added = [r for r in new_rules if r not in old_rules]
    kept = [r for r in old_rules if r in new_rules]
    lines = []
    for r in kept:
        lines.append(f"  - {r}")
    for r in removed:
        lines.append(f"- - {r}  [removed]")
    for r in added:
        lines.append(f"+ - {r}  [new]")
    return "\n".join(lines) if lines else "  (no rules)"


def parse_args():
    p = argparse.ArgumentParser(description="Write efficiency-audit rules into a CLAUDE.md marker block")
    p.add_argument("path", help="Path to CLAUDE.md file")
    p.add_argument("rules_json", nargs="?", default=None,
                   help='JSON array of rule strings, e.g. \'["NEVER commit without...", ...]\'')
    p.add_argument("--read", action="store_true",
                   help="Read and print the existing marker block rules as JSON")
    p.add_argument("--dry-run", action="store_true",
                   help="Show proposed change without writing")
    return p.parse_args()


def main():
    args = parse_args()
    path = Path(args.path)

    existing_text = path.read_text(encoding="utf-8") if path.exists() else ""
    existing_rules = read_marker_block(existing_text)

    if args.read:
        print(json.dumps(existing_rules, indent=2))
        return

    if args.rules_json is None:
        print("Error: rules_json argument required unless --read is specified", file=sys.stderr)
        sys.exit(1)

    try:
        new_rules = json.loads(args.rules_json)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON in rules_json: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(new_rules, list):
        print("Error: rules_json must be a JSON array", file=sys.stderr)
        sys.exit(1)

    timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    updated_text = write_marker_block(existing_text, new_rules, timestamp)

    action = "replace" if existing_rules else "append"
    print(f"{'[dry-run] ' if args.dry_run else ''}Will {action} marker block in {path}")
    print(f"  Rules: {len(existing_rules)} existing → {len(new_rules)} new")
    print()
    print(_diff_blocks(existing_rules, new_rules))

    if args.dry_run:
        print("\n--- Proposed block ---")
        start = updated_text.find(MARKER_START)
        end = updated_text.find(MARKER_END)
        if start != -1 and end != -1:
            print(updated_text[start : end + len(MARKER_END)])
        return

    path.write_text(updated_text, encoding="utf-8")
    print(f"\nWrote {len(new_rules)} rule(s) to {path}")


if __name__ == "__main__":
    main()
