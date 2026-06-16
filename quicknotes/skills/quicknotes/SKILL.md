---
name: quicknotes
description: "Capture and manage quick notes with near-zero friction. Use when the user wants to jot down a thought, make a note, add a to-do/reminder, or list/search/complete/update their notes. Notes are centralized markdown files with date/project/dir metadata, fuzzy-searchable, with references and time/location reminders; completing a note removes it. Trigger phrases: 'qn', 'quicknotes', 'write a quick note', 'quick note', 'jot this down', 'note to self', 'remind me to', 'add a note', 'list my notes', 'mark note done', 'what notes do I have', 'notes for this project'."
---

## Capture

```bash
PLUGIN_ROOT=$(ls -dt ~/.claude/plugins/cache/litianningdatadog-marketplace/quicknotes/*/ 2>/dev/null | head -1)
python3 "${PLUGIN_ROOT}/scripts/qn.py" <note text> [#tag …] [--tag T]
```

Anything that isn't a management verb is the note. Confirm id + title back in one line.

- Tags: inline `#hashtags` in the text or `--tag T` flags (normalized: lowercased, `#` stripped, spaces→`-`). In a raw shell, unquoted `#` is a comment — prefer `--tag` or quote the text.
- Time expressions ("by Friday", "tomorrow 5pm") → convert to ISO-8601 UTC via `qn update <id> --due 2026-06-13T17:00:00Z`.
- Suggest 1–3 tags from context, but don't block capture on tagging.
- May arrive via `/btw qn …` while mid-task — handle it in the same turn.

## Manage

`qn … = python3 "${PLUGIN_ROOT}/scripts/qn.py" …`

```
qn list [--project P] [--tag T]               # newest first
qn search <query>                              # fuzzy across title/body/tags/project
qn show   <id|fuzzy>                           # full metadata + body + refs
qn done   <id|fuzzy>                           # complete — DELETES the file (git history recoverable)
qn update <id|fuzzy> [--title T] [--tag T] [--priority P] [--due ISO] [body…]
qn due                                         # past-due notes
qn here                                        # notes for current project/dir
qn ref <id|fuzzy> <id|fuzzy>                   # link two notes bidirectionally
```

`--tag` in `update` replaces the tag list. `qn done` is destructive — warn if the user may want the note back.
If a fuzzy target is ambiguous, relay the candidate list and ask which.

## Reminders

`qn due` and `qn here` are always available. Proactive session reminders require an opt-in hook — ask before installing:

```json
{ "hooks": { "SessionStart": [ { "hooks": [
  { "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/session_reminder.py\"" }
] } ] } }
```

## Rules

- Don't fabricate ids — let `qn` generate them.
- Note files are confined to `~/.quicknotes`; never read/write outside it.
