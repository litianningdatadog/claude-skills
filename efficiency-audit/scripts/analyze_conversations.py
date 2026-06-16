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


BASELINE_PATH = Path.home() / ".claude" / "efficiency-audit-baseline.json"


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
    # Context injected by hooks/skills into the user message slot.
    r"^\s*##\s+context\s*[-–]",
    # Task-workflow messages: user feeding tool/test output back to Claude.
    # These look like corrections but are really task orchestration.
    r"\breview the (test|script|command|tool|output|run) (run )?output and fix\b",
    r"\breview the output and fix\b",
]


def _is_tool_output_paste(text: str) -> bool:
    """True when a message is dominated by pasted tool/shell output rather than user intent.

    Detects two structural patterns common in development sessions:
    - Opens with a code fence (pasted terminal/test output)
    - Is mostly a shell command invocation (path-heavy, few sentence words)
    """
    stripped = text.strip()
    # Starts with a code block
    if stripped.startswith("```"):
        return True
    # Mostly a shell command: first non-empty line looks like a command
    # (contains a path separator or starts with a known interpreter/tool)
    first = next((l for l in stripped.splitlines() if l.strip()), "")
    if re.match(r"^\s*(python3?|bash|sh|node|ruby|go|cargo|make|cmake|./|/)\s+\S", first):
        # Check that the message has little conversational text (few lowercase words)
        words = re.findall(r"\b[a-z]{4,}\b", text.lower())
        common_verbs = {"please", "this", "that", "with", "from", "have", "will"}
        conversational = [w for w in words if w not in common_verbs]
        if len(conversational) < 8:
            return True
    return False


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
    """True if `text` is system-generated boilerplate or a task-workflow message
    rather than a real user correction/context-request."""
    low = text.lower()
    return (
        any(re.search(pat, low) for pat in NOISE_PATTERNS)
        or _is_tool_output_paste(text)
    )


def _join_text_content(content) -> str:
    """Normalize a message `content` (str or list of blocks) to plain text."""
    if isinstance(content, list):
        parts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
        return " ".join(parts)
    return content or ""


def classify_tool_error(tool_name: str, error_text: str) -> str:
    """Classify a tool failure into a category from error text and tool name."""
    t = error_text.lower()
    if "file has not been read yet" in t or "read it first before writing" in t:
        return "unread_write"
    if "request interrupted by user" in t or "operation was cancelled" in t:
        return "user_interrupted"
    if "permission denied" in t:
        return "permission_denied"
    if ("pathspec" in t and "did not match" in t) or "no such file or directory" in t:
        return "file_not_found"
    if "not inside a" in t and "repository" in t:
        return "wrong_context"
    if "not a git repository" in t:
        return "wrong_context"
    m = re.search(r"exit code (\d+)", t)
    if m:
        return "git_error" if int(m.group(1)) == 128 else "bash_nonzero"
    return "tool_use_error"


def extract_session_data(path: Path) -> dict:
    session = {
        "path": str(path),
        "project": path.parent.name,
        "session_id": path.stem,
        "user_messages": [],
        "hook_errors": [],
        "tool_failures": [],
        "timestamps": [],
    }

    last_assistant: str | None = None
    # Maps tool_use id → tool name; populated from assistant turns, consumed in user turns.
    pending_tool_uses: dict[str, str] = {}

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

            if t == "assistant":
                raw = d.get("message", {}).get("content", "")
                if isinstance(raw, list):
                    for block in raw:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            pending_tool_uses[block["id"]] = block.get("name", "?")
                content = _join_text_content(raw)
                if content:
                    # Keep a short snippet — enough to understand what Claude did
                    last_assistant = " ".join(content.split())[:300]

            elif t == "user":
                raw = d.get("message", {}).get("content", "")
                if isinstance(raw, list):
                    for block in raw:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") == "tool_result" and block.get("is_error"):
                            tool_name = pending_tool_uses.get(block.get("tool_use_id", ""), "?")
                            inner = block.get("content", [])
                            if isinstance(inner, list):
                                error_text = " ".join(c.get("text", "") for c in inner if isinstance(c, dict))
                            else:
                                error_text = str(inner)
                            session["tool_failures"].append({
                                "tool": tool_name,
                                "error_category": classify_tool_error(tool_name, error_text),
                                "error_text": error_text[:300],
                            })
                content = _join_text_content(raw)
                if content and not is_noise(content):
                    session["user_messages"].append({
                        "text": content,
                        "ts": ts,
                        "preceding_action": last_assistant,
                    })

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

    `scored` items are {"text", "session", "project", "patterns": [regex, ...]}. Each
    message is attributed to its FIRST matched pattern only — a message that matches several
    patterns contributes exactly one count to exactly one group, preventing inflation.
    Output is sorted by count, then by distinct-session breadth, both descending.
    """
    groups: dict[str, dict] = {}
    for item in scored:
        # First pattern wins — prevents double-counting across groups.
        pat = item["patterns"][0]
        g = groups.setdefault(pat, {"pattern": pat, "count": 0, "_sessions": set(),
                                    "_projects": Counter(), "examples": [],
                                    "preceding_action": None})
        g["count"] += 1
        g["_sessions"].add(item["session"])
        g["_projects"][item.get("project", "")] += 1
        if len(g["examples"]) < 3:
            # Collapse whitespace so multi-line messages stay on one line in reports.
            g["examples"].append(" ".join(item["text"].split())[:200])
        # Keep the first preceding_action we encounter (highest-frequency example).
        if g["preceding_action"] is None and item.get("preceding_action"):
            g["preceding_action"] = item["preceding_action"][:200]

    out = [
        {
            "pattern": g["pattern"], "count": g["count"],
            "sessions": len(g["_sessions"]),
            "top_project": g["_projects"].most_common(1)[0][0] if g["_projects"] else "",
            "examples": g["examples"],
            "preceding_action": g.get("preceding_action"),
        }
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
        "tool_failures": [],
    }

    all_timestamps = []
    scored = {key: [] for key in CATEGORY_SCORE_KEY}

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
                    scored[cat].append({
                        "text": text,
                        "session": sess["session_id"],
                        "project": proj,
                        "patterns": scores[score_key],
                        "preceding_action": msg.get("preceding_action"),
                    })

        findings["hook_errors"].extend({**he, "session": sess["session_id"]} for he in sess["hook_errors"])

    for cat in CATEGORY_SCORE_KEY:
        findings[cat] = group_by_pattern(scored[cat])

    if all_timestamps:
        all_timestamps.sort()
        findings["summary"]["date_range"]["earliest"] = all_timestamps[0]
        findings["summary"]["date_range"]["latest"] = all_timestamps[-1]

    findings["hook_errors"] = _dedupe_hook_errors(findings["hook_errors"])
    findings["tool_failures"] = _aggregate_tool_failures(sessions)

    return findings


def _aggregate_tool_failures(sessions: list[dict]) -> list[dict]:
    groups: dict[tuple, dict] = {}
    for sess in sessions:
        for tf in sess.get("tool_failures", []):
            key = (tf["tool"], tf["error_category"])
            g = groups.setdefault(key, {
                "tool": tf["tool"],
                "error_category": tf["error_category"],
                "count": 0,
                "_sessions": set(),
                "examples": [],
            })
            g["count"] += 1
            g["_sessions"].add(sess["session_id"])
            if len(g["examples"]) < 3:
                g["examples"].append(" ".join(tf["error_text"].split()))
    out = [
        {
            "tool": g["tool"],
            "error_category": g["error_category"],
            "count": g["count"],
            "sessions": len(g["_sessions"]),
            "examples": g["examples"],
        }
        for g in groups.values()
    ]
    out.sort(key=lambda x: (x["count"], x["sessions"]), reverse=True)
    return out


def _dedupe_hook_errors(errors: list[dict]) -> list[dict]:
    seen, out = set(), []
    for he in errors:
        key = he.get("command", "") or he.get("hook_name", "")
        if key not in seen:
            seen.add(key)
            out.append(he)
    return out


def _baseline_key(project_filter: str | None) -> str:
    return project_filter or "global"


def load_baseline(project_filter: str | None, path: Path = BASELINE_PATH) -> dict | None:
    key = _baseline_key(project_filter)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get(key)
    except (OSError, json.JSONDecodeError):
        return None


def save_baseline(findings: dict, project_filter: str | None, path: Path = BASELINE_PATH):
    key = _baseline_key(project_filter)
    try:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        data[key] = {
            "saved_at": datetime.now(tz=timezone.utc).isoformat(),
            "sessions_analyzed": findings["summary"]["sessions_analyzed"],
            "category_totals": {
                cat: sum(g["count"] for g in findings[cat])
                for cat in CATEGORY_SCORE_KEY
            },
            "hook_error_count": len(findings["hook_errors"]),
            "tool_failure_count": sum(g["count"] for g in findings.get("tool_failures", [])),
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass  # non-fatal


def compute_deltas(findings: dict, baseline: dict | None) -> dict:
    """Per-category deltas vs a prior baseline. Returns {} when no baseline exists."""
    if not baseline:
        return {}
    deltas = {}
    prev_totals = baseline.get("category_totals", {})
    for cat in CATEGORY_SCORE_KEY:
        current = sum(g["count"] for g in findings[cat])
        previous = prev_totals.get(cat, 0)
        diff = current - previous
        pct = round(100 * diff / previous) if previous else None
        deltas[cat] = {"current": current, "previous": previous, "delta": diff, "pct_change": pct}
    current_hooks = len(findings["hook_errors"])
    prev_hooks = baseline.get("hook_error_count", 0)
    diff_hooks = current_hooks - prev_hooks
    deltas["hook_errors"] = {
        "current": current_hooks,
        "previous": prev_hooks,
        "delta": diff_hooks,
        "pct_change": round(100 * diff_hooks / prev_hooks) if prev_hooks else None,
    }
    current_tf = sum(g["count"] for g in findings.get("tool_failures", []))
    prev_tf = baseline.get("tool_failure_count", 0)
    diff_tf = current_tf - prev_tf
    deltas["tool_failures"] = {
        "current": current_tf,
        "previous": prev_tf,
        "delta": diff_tf,
        "pct_change": round(100 * diff_tf / prev_tf) if prev_tf else None,
    }
    return deltas


def _fmt_delta(delta: dict | None) -> str:
    """Return a compact delta suffix, e.g. ', was 30, -27% ↓'."""
    if not delta:
        return ""
    prev = delta["previous"]
    pct = delta["pct_change"]
    if pct is None:
        return f", was {prev}"
    d = delta["delta"]
    arrow = "↓" if d < 0 else "↑" if d > 0 else "→"
    sign = "+" if d > 0 else ""
    return f", was {prev}, {sign}{pct}% {arrow}"


def print_text_report(findings: dict, deltas: dict | None = None):
    deltas = deltas or {}
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
        delta_str = _fmt_delta(deltas.get(key))
        print(f"--- {title} ({total} matches{delta_str} across {len(groups)} patterns) ---")
        print(f"    {desc}")
        for g in groups[:5]:
            proj = f" ({g['top_project']})" if g.get("top_project") else ""
            print(f"    [{g['count']}x / {g['sessions']} sessions{proj}] e.g. {g['examples'][0][:140]}")
            if key == "corrections" and g.get("preceding_action"):
                print(f"      ↳ Claude did: {g['preceding_action'][:120]}")
        print()

    if findings.get("tool_failures"):
        total_tf = sum(g["count"] for g in findings["tool_failures"])
        delta_str = _fmt_delta(deltas.get("tool_failures"))
        print(f"--- TOOL CALL FAILURES ({total_tf} total{delta_str}, {len(findings['tool_failures'])} unique patterns) ---")
        for g in findings["tool_failures"][:5]:
            print(f"    [{g['tool']}/{g['error_category']}] {g['count']}x / {g['sessions']} sessions")
            if g["examples"]:
                print(f"      e.g. {g['examples'][0][:140]}")
        print()

    if findings["hook_errors"]:
        delta_str = _fmt_delta(deltas.get("hook_errors"))
        print(f"--- HOOK ERRORS ({len(findings['hook_errors'])} unique{delta_str}) ---")
        for he in findings["hook_errors"][:5]:
            print(f"    [{he['hook_name']}] exit={he['exit_code']} cmd={he['command'][:60]}")
            if he["stderr"]:
                print(f"      stderr: {he['stderr'][:100]}")
        print()



def main():
    args = parse_args()
    files = find_jsonl_files(args.days, args.project)
    print(f"Scanning {len(files)} conversation files from last {args.days} days...", file=sys.stderr)

    baseline = load_baseline(args.project)
    if baseline:
        print(f"Baseline found (saved {baseline.get('saved_at', '?')[:10]})", file=sys.stderr)

    sessions = []
    for f in files:
        try:
            sess = extract_session_data(f)
            if sess["user_messages"] or sess["tool_failures"] or sess["hook_errors"]:
                sessions.append(sess)
        except Exception as e:
            print(f"  Warning: could not parse {f}: {e}", file=sys.stderr)

    print(f"Parsed {len(sessions)} sessions with user messages", file=sys.stderr)
    findings = analyze(sessions)
    deltas = compute_deltas(findings, baseline)

    if args.output == "json":
        findings["deltas"] = deltas
        print(json.dumps(findings, indent=2, default=str))
    else:
        print_text_report(findings, deltas)

    save_baseline(findings, args.project)
    print(f"Baseline saved to {BASELINE_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
