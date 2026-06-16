#!/usr/bin/env python3
"""
quicknotes CLI — capture and manage quick notes.

Capture is the default: any input not starting with a reserved verb becomes a note.

    qn <free text> [#tag …] [--tag T]   capture a note (DEFAULT)
    qn add <free text> [#tag …]         force capture (when text starts with a verb word)
    qn list [--project P] [--tag T]
    qn search <query>
    qn show   <id|fuzzy>
    qn done   <id|fuzzy>           complete a note (DELETES it from disk)
    qn update <id|fuzzy> [--title T] [--tag T ...] [#tag …] [--priority P] [--due ISO] [body...]
    qn due                         notes past their due time
    qn here                        notes for the current project/dir
    qn ref <id|fuzzy> <id|fuzzy>   link two notes

Notes live under $QUICKNOTES_HOME or ~/.quicknotes. Completing a note removes its file.
"""

import sys
from datetime import datetime

import notes_store as ns

RESERVED = {"add", "list", "search", "show", "done", "update",
            "due", "here", "ref", "help", "-h", "--help"}
_MULTI = {"--tag"}  # flags that may repeat


def _extract_opts(words, allowed):
    """Pull `--key value` pairs (allowed set) out of words; return (opts, remaining)."""
    opts, rest, i = {}, [], 0
    while i < len(words):
        w = words[i]
        if w in allowed and i + 1 < len(words):
            val = words[i + 1]
            if w in _MULTI:
                opts.setdefault(w, []).append(val)
            else:
                opts[w] = val
            i += 2
        else:
            rest.append(w)
            i += 1
    return opts, rest


def _display_time(iso_str):
    """Parse a stored UTC ISO timestamp and return it formatted in local time."""
    if not iso_str:
        return iso_str
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%Y-%m-%d %H:%M %Z")
    except (ValueError, AttributeError):
        return iso_str


def _fmt(note):
    tags = (" #" + " #".join(note["tags"])) if note.get("tags") else ""
    pri = f" !{note['priority']}" if note.get("priority") else ""
    due = f" due:{_display_time(note['due'])}" if note.get("due") else ""
    return f"{note['id']}  {note.get('title') or '(untitled)'}" \
           f"  ({note.get('project')}){tags}{pri}{due}"


def _resolve_or_report(home, ref):
    note, cands = ns.resolve(home, ref)
    if note:
        return note
    if cands:
        print(f"Ambiguous '{ref}' — {len(cands)} matches; be more specific or use the id:")
        for n in cands:
            print("  " + _fmt(n))
    else:
        print(f"No note matching '{ref}'.")
    return None


def cmd_capture(words, home):
    opts, rest = _extract_opts(words, {"--tag"})
    text, inline_tags = ns.extract_hashtags(" ".join(rest).strip())
    text = text.strip()
    tags = (opts.get("--tag") or []) + inline_tags
    if not text and not tags:
        print("Nothing to capture. Usage: qn <note text> [#tag …] [--tag T]")
        return 1
    note = ns.capture(text, home=home, tags=tags or None)
    extra = ("  tags: " + ", ".join(note["tags"])) if note.get("tags") else ""
    print(f"✓ noted [{note['id']}] {note.get('title') or ''}".rstrip() + extra)
    return 0


def cmd_list(words, home):
    opts, _rest = _extract_opts(words, {"--project", "--tag"})
    notes = ns.list_notes(home, project=opts.get("--project"), tag=opts.get("--tag"))
    if not notes:
        print("No notes.")
        return 0
    for n in notes:
        print(_fmt(n))
    return 0


def cmd_search(words, home):
    if not words:
        print("Usage: qn search <query>")
        return 1
    results = ns.search(home, " ".join(words))
    if not results:
        print("No matches.")
        return 0
    for n in results:
        print(_fmt(n))
    return 0


def _detail(note):
    """Full labeled metadata block + body for `show`."""
    rows = [
        ("Id", note.get("id")),
        ("Title", note.get("title") or "(untitled)"),
        ("Priority", note.get("priority") or "—"),
        ("Due", _display_time(note.get("due")) or "—"),
        ("Created", _display_time(note.get("created")) or "—"),
        ("Updated", _display_time(note.get("updated")) or "—"),
        ("Project", note.get("project") or "—"),
        ("Branch", note.get("branch") or "—"),
        ("Cwd", note.get("cwd") or "—"),
        ("Tags", ", ".join(note.get("tags") or []) or "—"),
        ("Refs", ", ".join(note.get("refs") or []) or "—"),
    ]
    width = max(len(k) for k, _ in rows)
    lines = [f"{k + ':':<{width + 1}} {v}" for k, v in rows]
    lines.append("")
    lines.append("─" * 40)
    lines.append(note.get("body") or "")
    return "\n".join(lines)


def cmd_show(words, home):
    if not words:
        print("Usage: qn show <id|fuzzy>")
        return 1
    note = _resolve_or_report(home, " ".join(words))
    if not note:
        return 1
    print(_detail(note))
    return 0


def cmd_done(words, home):
    if not words:
        print("Usage: qn done <id|fuzzy>")
        return 1
    note = _resolve_or_report(home, " ".join(words))
    if not note:
        return 1
    ns.complete(home, note["id"])
    print(f"✓ done (removed): [{note['id']}] {note.get('title') or ''}".rstrip())
    return 0


def cmd_update(words, home):
    opts, rest = _extract_opts(words, {"--title", "--tag", "--priority", "--due"})
    if not rest:
        print("Usage: qn update <id|fuzzy> [--title T] [--tag T] [--priority P] [--due ISO] [body]")
        return 1
    ref, body_words = rest[0], rest[1:]
    note = _resolve_or_report(home, ref)
    if not note:
        return 1
    body_text, inline_tags = ns.extract_hashtags(" ".join(body_words))
    changes = {}
    if "--title" in opts:
        changes["title"] = opts["--title"]
    if opts.get("--tag") or inline_tags:
        changes["tags"] = (opts.get("--tag") or []) + inline_tags
    if "--priority" in opts:
        changes["priority"] = opts["--priority"]
    if "--due" in opts:
        changes["due"] = opts["--due"]
    body = body_text.strip() or None
    ns.update(home, note["id"], body=body, **changes)
    print(f"✓ updated [{note['id']}]")
    return 0


def cmd_due(words, home):
    notes = ns.due_notes(home)
    if not notes:
        print("Nothing due.")
        return 0
    print(f"{len(notes)} due:")
    for n in notes:
        print("  " + _fmt(n))
    return 0


def cmd_here(words, home):
    notes = ns.here_notes(home)
    if not notes:
        print("No open notes for this project/dir.")
        return 0
    print(f"{len(notes)} open note(s) here:")
    for n in notes:
        print("  " + _fmt(n))
    return 0


def cmd_ref(words, home):
    if len(words) < 2:
        print("Usage: qn ref <id|fuzzy> <id|fuzzy>")
        return 1
    a = _resolve_or_report(home, words[0])
    b = _resolve_or_report(home, words[1])
    if not a or not b:
        return 1
    if ns.add_ref(home, a["id"], b["id"]):
        print(f"✓ linked {a['id']} ↔ {b['id']}")
        return 0
    print("Could not link (same note?).")
    return 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    home = ns.default_home()
    if not argv:
        print(__doc__.strip())
        return 0
    verb, rest = argv[0], argv[1:]
    if verb in ("help", "-h", "--help"):
        print(__doc__.strip())
        return 0
    if verb not in RESERVED:
        return cmd_capture(argv, home)        # no verb → capture everything
    return {
        "add": lambda: cmd_capture(rest, home),
        "list": lambda: cmd_list(rest, home),
        "search": lambda: cmd_search(rest, home),
        "show": lambda: cmd_show(rest, home),
        "done": lambda: cmd_done(rest, home),
        "update": lambda: cmd_update(rest, home),
        "due": lambda: cmd_due(rest, home),
        "here": lambda: cmd_here(rest, home),
        "ref": lambda: cmd_ref(rest, home),
    }[verb]()


if __name__ == "__main__":
    sys.exit(main())
