#!/usr/bin/env python3
"""
Analyze Claude Code conversation transcripts to surface efficiency patterns.

Usage:
    python3 analyze_conversations.py [--days N] [--project PATH] [--output json|text]

Defaults to scanning all projects under ~/.claude/projects/ from the last 30 days.

Output is pre-clustered: each finding category groups user messages by the pattern
they matched and reports a recurrence `count` and distinct-`sessions` count, so the
reader can act on "this class of friction recurred N times" without re-clustering.
System-generated noise (context-compaction notices, slash-command invocations,
security-review and subagent-dispatch boilerplate) is filtered during extraction.
"""

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path


CORRECTION_PATTERNS = [
    r"\bno[,!]?\s+(don'?t|do not|stop|never)\b",
    r"\b(don'?t|do not|stop|never|avoid)\s+(do(ing)?|use|run|add|create|write)\b",
    r"\b(wrong|incorrect|not (right|what I|what we))\b",
    r"\b(I said|I told you|as I mentioned|like I said)\b",
    r"\b(that'?s not|that is not)\s+what\b",
    r"\bplease (don'?t|do not|stop|never)\b",
    r"\b(revert|undo|go back)\b",
    r"\binstead[,\s]+(use|do|run|write)\b",
    r"\b(you should|you need to|you must)\s+not\b",
]

CONTEXT_REQUEST_PATTERNS = [
    r"\b(remember|recall|as I said|as we discussed|from (last|previous|earlier))\b",
    r"\b(context is|the situation is|for context|to clarify)\b",
    r"\b(I('?ve| have) (told|explained|mentioned|said) (you |this |before|already))\b",
    r"\b(again,? (this|the|we|I))\b",
    r"\b(same as|same pattern|same approach)\b",
]

SLOW_START_PATTERNS = [
    r"\b(first[,\s]+(let'?s?|you should|read|check|look at))\b",
    r"\b(before (you|we) (start|begin|do|proceed))\b",
    r"\b(the project (is|uses|has)|this repo(sitory)? (is|uses|has))\b",
    r"\b(we use|we don'?t use|in this project)\b",
    r"\b(always use|never use|make sure (you )?use)\b",
]

AUTOMATION_PATTERNS = [
    r"\b(every time|always (run|check|do|use)|each time|whenever)\b",
    r"\b(after (each|every) (commit|push|build|test))\b",
    r"\b(before (committing|pushing|building|testing|merging))\b",
    # Intent to automate, not incidental mentions of "script"/"hook"/"automatically".
    r"\b(automate|automating)\b",
    r"\b(set up|add|create|write|make) a (hook|alias|shortcut|script|command)\b",
]

# System-generated text that looks like user input but is not real user friction.
# Mirrors the "False Positive Filters" the SKILL.md formerly asked the reader to apply
# by hand; applying them here keeps the JSON clean and the filtering consistent.
NOISE_PATTERNS = [
    r"this session is being continued from a previous conversation",
    r"^\s*<command-(name|message|args)>",
    r"^\s*<local-command-(stdout|caveat)>",
    r"^\s*you are a (security reviewer|subagent)\b",
    # Skill/command bodies injected as pseudo-user messages (observed in real data).
    r"\breview this change for security vulnerabilities\b",
    r"^\s*provide a code review for the given pull request\b",
    r"^\s*base directory for this skill\b",
]


def parse_args():
    p = argparse.ArgumentParser(description="Analyze Claude Code conversations for efficiency patterns")
    p.add_argument("--days", type=int, default=30, help="Scan conversations from last N days (default: 30)")
    p.add_argument("--project", type=str, default=None,
                   help="Restrict to a project. Accepts a real path (/Users/me/repo), the "
                        "folder name (repo), or the encoded dir name; matched tolerant of /.→- encoding")
    p.add_argument("--output", choices=["json", "text"], default="json", help="Output format")
    return p.parse_args()


def project_matches(parent_dir: str, project_filter: str) -> bool:
    """Substring match tolerant of how Claude Code encodes project paths.

    Transcript dirs are the cwd with `/` and `.` replaced by `-` (e.g.
    `-Users-jane-DataDog-foo`). Normalizing both sides the same way lets a user pass
    a real filesystem path (`/Users/jane/DataDog/foo`), the folder basename (`foo`),
    or the raw encoded name and have any of them match.
    """
    norm = lambda s: re.sub(r"[/.]", "-", s)
    return project_filter in parent_dir or norm(project_filter) in norm(parent_dir)


def find_jsonl_files(days: int, project_filter: str | None) -> list[Path]:
    base = Path.home() / ".claude" / "projects"
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    results = []
    for f in base.rglob("*.jsonl"):
        if project_filter and not project_matches(str(f.parent), project_filter):
            continue
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            if mtime >= cutoff:
                results.append(f)
        except OSError:
            pass
    return sorted(results, key=lambda f: f.stat().st_mtime, reverse=True)


def is_noise(text: str) -> bool:
    """True if `text` is system-generated boilerplate rather than real user input."""
    low = text.lower()
    return any(re.search(pat, low) for pat in NOISE_PATTERNS)


def _join_text_content(content) -> str:
    """Normalize a message `content` (str or list of blocks) to plain text."""
    if isinstance(content, list):
        parts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
        return " ".join(parts)
    return content or ""


def extract_session_data(path: Path) -> dict:
    session = {
        "path": str(path),
        "project": path.parent.name,
        "session_id": path.stem,
        "user_messages": [],
        "hook_errors": [],
        "timestamps": [],
    }

    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue

            t = d.get("type", "")
            ts = d.get("timestamp", "")
            if ts:
                session["timestamps"].append(ts)

            if t == "user":
                content = _join_text_content(d.get("message", {}).get("content", ""))
                if content and not is_noise(content):
                    session["user_messages"].append({"text": content, "ts": ts})

            elif t == "system":
                # Canonical hook-error channel: stop_hook_summary carries a structured
                # `hookErrors` list. Empty list = healthy run, so skip it.
                for he in d.get("hookErrors", []) or []:
                    if isinstance(he, dict):
                        session["hook_errors"].append({
                            "hook_name": he.get("hookName", ""),
                            "exit_code": he.get("exitCode"),
                            "stderr": str(he.get("stderr", ""))[:200],
                            "command": he.get("command", ""),
                        })

            elif t == "attachment":
                att = d.get("attachment", {})
                if not isinstance(att, dict):
                    continue
                att_type = att.get("type", "")
                # Non-blocking hook *failures* surface as their own attachment type.
                # `hook_cancelled` (interrupted/timed-out, no exit code) is not a failure.
                if att_type == "hook_non_blocking_error":
                    session["hook_errors"].append({
                        "hook_name": att.get("hookName", ""),
                        "exit_code": att.get("exitCode"),
                        "stderr": str(att.get("stderr", ""))[:200],
                        "command": att.get("command", ""),
                    })

    return session


def match_patterns(text: str, patterns: list[str]) -> list[str]:
    text_lower = text.lower()
    return [pat for pat in patterns if re.search(pat, text_lower)]


def score_message(text: str) -> dict:
    return {
        "corrections": match_patterns(text, CORRECTION_PATTERNS),
        "context_requests": match_patterns(text, CONTEXT_REQUEST_PATTERNS),
        "slow_start": match_patterns(text, SLOW_START_PATTERNS),
        "automation": match_patterns(text, AUTOMATION_PATTERNS),
    }


def group_by_pattern(scored: list[dict]) -> list[dict]:
    """Cluster matched messages by pattern into recurrence groups.

    `scored` items are {"text", "session", "patterns": [regex, ...]}. A message that
    matches several patterns contributes to each. Output is sorted by count, then by
    distinct-session breadth, both descending.
    """
    groups: dict[str, dict] = {}
    for item in scored:
        for pat in item["patterns"]:
            g = groups.setdefault(pat, {"pattern": pat, "count": 0, "_sessions": set(), "examples": []})
            g["count"] += 1
            g["_sessions"].add(item["session"])
            if len(g["examples"]) < 3:
                # Collapse whitespace so multi-line messages stay on one line in reports.
                g["examples"].append(" ".join(item["text"].split())[:200])

    out = [
        {"pattern": g["pattern"], "count": g["count"], "sessions": len(g["_sessions"]), "examples": g["examples"]}
        for g in groups.values()
    ]
    out.sort(key=lambda x: (x["count"], x["sessions"]), reverse=True)
    return out


# Maps each finding category to the score_message key that feeds it.
CATEGORY_SCORE_KEY = {
    "corrections": "corrections",
    "missing_context": "context_requests",
    "slow_start_context": "slow_start",
    "automation_candidates": "automation",
}


def analyze(sessions: list[dict]) -> dict:
    findings = {
        "summary": {
            "sessions_analyzed": len(sessions),
            "total_user_messages": 0,
            "date_range": {"earliest": None, "latest": None},
            "projects": Counter(),
        },
        "corrections": [],
        "missing_context": [],
        "slow_start_context": [],
        "automation_candidates": [],
        "hook_errors": [],
        "repeated_topics": [],
    }

    all_timestamps = []
    scored = {key: [] for key in CATEGORY_SCORE_KEY}
    topic_counter = Counter()

    for sess in sessions:
        proj = sess["project"]
        findings["summary"]["projects"][proj] += 1

        for msg in sess["user_messages"]:
            findings["summary"]["total_user_messages"] += 1
            text = msg["text"]
            if msg["ts"]:
                all_timestamps.append(msg["ts"])

            scores = score_message(text)
            for cat, score_key in CATEGORY_SCORE_KEY.items():
                if scores[score_key]:
                    scored[cat].append({"text": text, "session": sess["session_id"], "patterns": scores[score_key]})

            for w in _topic_words(text):
                topic_counter[w] += 1

        findings["hook_errors"].extend({**he, "session": sess["session_id"]} for he in sess["hook_errors"])

    for cat in CATEGORY_SCORE_KEY:
        findings[cat] = group_by_pattern(scored[cat])

    if all_timestamps:
        all_timestamps.sort()
        findings["summary"]["date_range"]["earliest"] = all_timestamps[0]
        findings["summary"]["date_range"]["latest"] = all_timestamps[-1]

    findings["repeated_topics"] = [
        {"topic": w, "count": c} for w, c in topic_counter.most_common(30) if c >= 3
    ]

    findings["hook_errors"] = _dedupe_hook_errors(findings["hook_errors"])

    return findings


_STOP_WORDS = {
    "that", "this", "with", "from", "have", "will", "what", "when", "which", "your",
    "just", "also", "then", "than", "been", "were", "they", "them", "into", "does",
    "make", "need", "want", "sure", "like", "some", "each", "please", "here", "there",
    "more", "very", "would", "could", "should", "about", "after", "before", "added",
    "used", "using", "file", "code", "line", "lines", "change",
}


def _topic_words(text: str) -> list[str]:
    words = re.findall(r"\b[a-z][a-z_\-]{3,}\b", text.lower())
    return [w for w in words if w not in _STOP_WORDS]


def _dedupe_hook_errors(errors: list[dict]) -> list[dict]:
    seen, out = set(), []
    for he in errors:
        key = he.get("command", "") or he.get("hook_name", "")
        if key not in seen:
            seen.add(key)
            out.append(he)
    return out


def print_text_report(findings: dict):
    s = findings["summary"]
    print("=== Claude Code Efficiency Audit ===")
    print(f"Sessions analyzed: {s['sessions_analyzed']}")
    print(f"User messages: {s['total_user_messages']}")
    dr = s["date_range"]
    print(f"Date range: {dr['earliest'][:10] if dr['earliest'] else 'N/A'} → {dr['latest'][:10] if dr['latest'] else 'N/A'}")
    print(f"Projects: {dict(s['projects'].most_common(5))}")
    print()

    sections = [
        ("CORRECTIONS / REDIRECTIONS", "corrections",
         "Recurring classes of correction (grouped by pattern)"),
        ("MISSING CONTEXT (re-explained)", "missing_context",
         "Context you re-introduced that Claude should already know"),
        ("SLOW START (per-session orientation)", "slow_start_context",
         "Orientation that could live in CLAUDE.md"),
        ("AUTOMATION CANDIDATES", "automation_candidates",
         "Recurring procedural intent that could become a hook"),
    ]

    for title, key, desc in sections:
        groups = findings[key]
        total = sum(g["count"] for g in groups)
        print(f"--- {title} ({total} matches across {len(groups)} patterns) ---")
        print(f"    {desc}")
        for g in groups[:5]:
            print(f"    [{g['count']}x / {g['sessions']} sessions] e.g. {g['examples'][0][:140]}")
        print()

    if findings["hook_errors"]:
        print(f"--- HOOK ERRORS ({len(findings['hook_errors'])} unique) ---")
        for he in findings["hook_errors"][:5]:
            print(f"    [{he['hook_name']}] exit={he['exit_code']} cmd={he['command'][:60]}")
            if he["stderr"]:
                print(f"      stderr: {he['stderr'][:100]}")
        print()

    if findings["repeated_topics"]:
        print("--- TOP RECURRING TOPICS ---")
        topics = [(t["topic"], t["count"]) for t in findings["repeated_topics"][:15]]
        print("    " + ", ".join(f"{t}({c})" for t, c in topics))
        print()


def main():
    args = parse_args()
    files = find_jsonl_files(args.days, args.project)
    print(f"Scanning {len(files)} conversation files from last {args.days} days...", file=sys.stderr)

    sessions = []
    for f in files:
        try:
            sess = extract_session_data(f)
            if sess["user_messages"]:
                sessions.append(sess)
        except Exception as e:
            print(f"  Warning: could not parse {f}: {e}", file=sys.stderr)

    print(f"Parsed {len(sessions)} sessions with user messages", file=sys.stderr)
    findings = analyze(sessions)

    if args.output == "json":
        print(json.dumps(findings, indent=2, default=str))
    else:
        print_text_report(findings)


if __name__ == "__main__":
    main()
