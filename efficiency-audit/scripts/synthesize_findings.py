#!/usr/bin/env python3
"""
synthesize_findings.py — LLM-powered synthesis of efficiency audit findings.

Reads analyze_conversations.py JSON output from stdin (or --input), builds a
compact digest, calls the Claude CLI to produce ranked CLAUDE.md recommendations
with estimated token savings, and writes structured JSON to stdout.

Usage:
    python3 analyze_conversations.py --output json | python3 synthesize_findings.py
    python3 synthesize_findings.py --input findings.json
    python3 synthesize_findings.py --input findings.json --model claude-sonnet-4-6
    python3 synthesize_findings.py --dry-run   # print digest only, no LLM call
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


MAX_DIGEST_CHARS = 30_000
DEFAULT_MODEL = "claude-sonnet-4-6"

_SYNTHESIS_PROMPT = """\
You are analyzing Claude Code session data to produce workflow improvements.

Given efficiency audit findings, produce ranked CLAUDE.md rules that prevent the observed friction.

Good rule properties:
- Imperative and specific: "NEVER create a commit without explicit instruction" not "avoid committing"
- Targets the root cause (use preceding_action field), not just the symptom
- Scoped: global (user behavior across all projects) or project (repo-specific conventions)

For tool failures (unread_write, wrong_context, file_not_found, etc.): propose rules that
prevent the mistake pattern. E.g. unread_write → "Always Read a file before calling Edit or Write on it."

For corrections: draft rules from the example + preceding_action pair.
For missing_context: write stable facts that belong in CLAUDE.md.
For automation_candidates: propose hooks or alias commands.

Evidence threshold: only recommend when count >= 2 or sessions >= 2.

Return ONLY valid JSON — no prose, no markdown fences:
{
  "recommendations": [
    {
      "proposed_rule": "NEVER ...",
      "estimated_tokens_saved": 300,
      "scope": "global",
      "target": "CLAUDE.md",
      "evidence": "Edit/unread_write: 7x across 2 sessions",
      "confidence": "high"
    }
  ]
}

Sort by estimated_tokens_saved descending.
Token savings estimate: corrections ~100/occurrence, tool retries ~300/occurrence, missing_context ~200/occurrence.
Confidence: "high" if count >= 5 or sessions >= 3; "medium" if count >= 2; "low" otherwise.

---

"""


def build_digest(findings: dict) -> str:
    """Build a compact text digest from findings for LLM consumption."""
    lines = []

    s = findings.get("summary", {})
    lines.append("## Session Summary")
    lines.append(f"Sessions: {s.get('sessions_analyzed', 0)}, Messages: {s.get('total_user_messages', 0)}")
    dr = s.get("date_range", {})
    if dr.get("earliest"):
        lines.append(f"Date range: {dr['earliest'][:10]} → {dr.get('latest', '')[:10]}")
    lines.append("")

    sections = [
        ("Corrections", "corrections"),
        ("Missing Context (re-explained each session)", "missing_context"),
        ("Slow Start (per-session orientation)", "slow_start_context"),
        ("Automation Candidates", "automation_candidates"),
    ]
    for title, key in sections:
        groups = findings.get(key, [])
        if not groups:
            continue
        total = sum(g["count"] for g in groups)
        lines.append(f"## {title} ({total} total, {len(groups)} patterns)")
        for g in groups[:8]:
            proj = f" ({g['top_project']})" if g.get("top_project") else ""
            lines.append(f"- [{g['count']}x / {g['sessions']} sessions{proj}]")
            if g.get("examples"):
                lines.append(f"  Example: {g['examples'][0][:150]}")
            if key == "corrections" and g.get("preceding_action"):
                lines.append(f"  Claude did: {g['preceding_action'][:120]}")
        lines.append("")

    tool_failures = findings.get("tool_failures", [])
    if tool_failures:
        total = sum(g["count"] for g in tool_failures)
        lines.append(f"## Tool Failures ({total} total, {len(tool_failures)} patterns)")
        for g in tool_failures[:8]:
            lines.append(f"- [{g['tool']}/{g['error_category']}] {g['count']}x / {g['sessions']} sessions")
            if g.get("examples"):
                lines.append(f"  e.g. {g['examples'][0][:150]}")
        lines.append("")

    deltas = findings.get("deltas", {})
    if any(d.get("previous") for d in deltas.values()):
        lines.append("## Changes vs previous audit")
        for k, d in deltas.items():
            if d.get("previous"):
                sign = "↓" if d["delta"] < 0 else ("↑" if d["delta"] > 0 else "→")
                pct = d.get("pct_change") or 0
                lines.append(f"- {k}: {d['current']} (was {d['previous']}, {pct:+d}% {sign})")
        lines.append("")

    hook_errors = findings.get("hook_errors", [])
    if hook_errors:
        lines.append(f"## Hook Errors ({len(hook_errors)} unique)")
        for he in hook_errors[:5]:
            lines.append(f"- [{he.get('hook_name', '?')}] exit={he.get('exit_code')} cmd={str(he.get('command', ''))[:80]}")
        lines.append("")

    return "\n".join(lines)[:MAX_DIGEST_CHARS]


def extract_json(text: str) -> dict:
    """Extract a JSON object from LLM output, tolerating markdown fences and leading prose."""
    cleaned = re.sub(r"```json\s*", "", text)
    cleaned = re.sub(r"```\s*", "", cleaned)
    m = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not m:
        raise ValueError("No JSON object found in LLM output")
    return json.loads(m.group(0))


def call_claude(prompt: str, model: str) -> str:
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--model", model],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        raise RuntimeError("'claude' CLI not found — ensure Claude Code is installed and 'claude' is in PATH")
    except subprocess.TimeoutExpired:
        raise RuntimeError("claude CLI timed out after 120s")
    if result.returncode != 0:
        raise RuntimeError(f"claude CLI exited {result.returncode}: {result.stderr[:300]}")
    return result.stdout


def parse_args():
    p = argparse.ArgumentParser(description="LLM synthesis of efficiency audit findings")
    p.add_argument("--input", type=str, default="-",
                   help="Path to findings JSON from analyze_conversations.py (default: stdin)")
    p.add_argument("--model", type=str, default=DEFAULT_MODEL,
                   help=f"Claude model to use (default: {DEFAULT_MODEL})")
    p.add_argument("--dry-run", action="store_true",
                   help="Print digest only without making an LLM call")
    return p.parse_args()


def main():
    args = parse_args()

    if args.input == "-":
        try:
            findings = json.load(sys.stdin)
        except json.JSONDecodeError as e:
            print(f"Error: invalid JSON on stdin: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        try:
            findings = json.loads(Path(args.input).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"Error reading {args.input}: {e}", file=sys.stderr)
            sys.exit(1)

    digest = build_digest(findings)
    print(f"Digest: {len(digest)} chars", file=sys.stderr)

    if args.dry_run:
        print(digest)
        sys.exit(0)

    full_prompt = _SYNTHESIS_PROMPT + digest
    print(f"Calling Claude CLI (model: {args.model})...", file=sys.stderr)

    try:
        raw = call_claude(full_prompt, args.model)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        result = extract_json(raw)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"Warning: could not parse LLM output as JSON: {e}", file=sys.stderr)
        print(f"Raw output:\n{raw}", file=sys.stderr)
        sys.exit(1)

    result["model_used"] = args.model
    result["digest_chars"] = len(digest)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
