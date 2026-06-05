---
name: quicknotes
description: "Capture and manage quick notes with near-zero friction. Use when the user wants to jot down a thought, make a note, add a to-do/reminder, or list/search/complete/update their notes. Notes are centralized markdown files with date/project/dir metadata, fuzzy-searchable, with references and time/location reminders; completing a note removes it. Trigger phrases: 'qn', 'quicknotes', 'write a quick note', 'quick note', 'jot this down', 'note to self', 'remind me to', 'add a note', 'list my notes', 'mark note done', 'what notes do I have', 'notes for this project'."
---

# Quick Notes

## Overview

Capture fleeting thoughts before they're lost, then list/search/complete/update them later.
Notes are one markdown file per note under `~/.quicknotes/notes/<id>.md` (override with
`$QUICKNOTES_HOME`), with YAML frontmatter carrying date, project, cwd, branch, tags,
priority, due, and references. All operations go through `scripts/qn.py` (backed by
`scripts/notes_store.py`) — never hand-edit note files; let the script keep metadata correct.

This skill is the **management + capture** surface used inside Claude. For **instant,
zero-turn** capture while an agent is mid-task, the user runs the standalone `qn` shell CLI in
another terminal (see README) — same store, no Claude round-trip.

## When to use

- The user wants to record a thought/to-do/reminder ("jot this down", "note to self", `qn …`).
- The user wants to review/act on notes ("list my notes", "what's due", "mark the deploy note
  done", "notes for this project").
- Often invoked queued via their `/btw` command (e.g. `/btw qn …`) so capture doesn't interrupt
  a running task — handle it the same way when the turn runs.

## Capture (the default)

Capture is frictionless: anything that isn't a management verb is the note. Run:

```bash
python3 ~/.claude/skills/quicknotes/scripts/qn.py <the note text> [#tag …] [--tag T]
```

Tags can be set at capture two ways: **inline `#hashtags`** in the text (stripped from the
body, stored as tags) or repeated **`--tag T`** flags. Both are normalized (leading `#`
dropped, lowercased, spaces→`-`). Note: in a raw shell, an unquoted `#` is a comment — inside
Claude/`/qn` it's fine, but when guiding shell use, prefer `--tag` or quote the text.

Then confirm the id + title (and any tags) back in one line. Enrichment guidance:
- The script auto-fills date, `project`, `cwd`, `branch`, and derives a `title` from the first
  line. You may **suggest 1–3 tags** inferred from the text/project (pass them as `#tag` or
  `--tag`) — but keep capture instant; don't block on tagging.
- If the user states a time ("by Friday", "tomorrow 5pm"), convert it to an ISO-8601 UTC
  instant via an update: `qn update <id> --due 2026-06-12T17:00:00Z`.
- `update` accepts `#hashtags` and `--tag` too; both **replace** the note's tag list.

## Manage

Run the matching verb (all support fuzzy targeting — an id, or text matching title/body; if
ambiguous the script lists candidates, so relay them and ask which):

```bash
qn list [--project P] [--tag T]   # newest first
qn search <query>                 # fuzzy across title/body/tags/project
qn show   <id|fuzzy>              # full labeled metadata block + body + refs
qn done   <id|fuzzy>             # complete a note — DELETES its file
qn update <id|fuzzy> [--title T] [--tag T] [--priority P] [--due ISO] [body…]
qn due                           # past-due notes (time reminders)
qn here                          # notes for the current project/dir (location reminders)
qn ref <id|fuzzy> <id|fuzzy>     # link two notes (bidirectional)
```

(`qn …` above = `python3 ~/.claude/skills/quicknotes/scripts/qn.py …`.)

Lifecycle is simple: a note is **active** until it's done. `qn done` **removes the note file
from disk** (a hard delete — there is no cancelled/archived state). The `~/.quicknotes` store
is git-init'd, so a committed note remains recoverable from git history; warn the user that
`done` is destructive if they ask to complete something they may want back.

## Reminders

- **Manual (always available):** `qn due` and `qn here`.
- **Proactive (opt-in hook):** a `SessionStart` hook (`scripts/session_reminder.py`) surfaces
  due + current-project notes when a session starts. Installing it edits the user's
  `settings.json`, so **ask first and explain** before adding it (same blast-radius care as any
  hook change). Propose this hook entry, and install only on explicit approval:

  ```json
  { "hooks": { "SessionStart": [ { "hooks": [
    { "type": "command", "command": "python3 \"${HOME}/.claude/skills/quicknotes/scripts/session_reminder.py\"" }
  ] } ] } }
  ```

  The hook is non-blocking and exits 0 even on error, so it can't break a session.
- OS/desktop notifications are out of scope (future extension).

## Notes for the agent

- Don't fabricate ids — let `qn` generate and report them.
- On ambiguous fuzzy targets, present the candidate list rather than guessing.
- Note files are confined to the notes home; never read/write note paths outside it.
- The standalone `qn` shell CLI (README) shares this exact store and format — capture from
  either path is interchangeable.
