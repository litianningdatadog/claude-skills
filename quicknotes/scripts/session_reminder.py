#!/usr/bin/env python3
"""
quicknotes SessionStart hook.

Prints a one-line reminder summary at session start: time-due notes and open notes for the
current project/dir. Designed to be non-blocking and safe — it ALWAYS exits 0 and never
raises into the session, even if the notes store is missing or malformed.

Wire it up (with the user's consent) as a SessionStart hook whose command is:
    python3 "${HOME}/.claude/skills/quicknotes/scripts/session_reminder.py"
"""

import sys


def main() -> int:
    try:
        import notes_store as ns
        home = ns.default_home()
        if not ns.notes_dir(home).exists():
            return 0
        due = ns.due_notes(home)
        here = ns.here_notes(home)
        bits = []
        if due:
            bits.append(f"{len(due)} due")
        if here:
            bits.append(f"{len(here)} open for this project")
        if bits:
            print("📝 quicknotes: " + ", ".join(bits) + "  (run `qn due` / `qn here`)")
            for n in due[:5]:
                print(f"   • due: {n.get('title') or n['id']}")
    except Exception:
        # A reminder hook must never break the session.
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
