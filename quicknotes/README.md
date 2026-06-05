# quicknotes

Low-friction quick-note capture and management for Claude Code. Jot a thought before you lose
it, then list / search / complete / update it later. Notes are centralized markdown
files enriched with date, project, directory, and git metadata — fuzzy-searchable, with
references and time/location reminders. Completing a note removes it.

> **Canonical behavior lives in [`SKILL.md`](SKILL.md).** This README covers human-facing
> install, the `qn` CLI, the `/qn` command, and tests. If the two disagree, `SKILL.md` wins.

## Four ways in (by latency / context)

| Entry | When | Blocking? |
|-------|------|-----------|
| **`qn …` shell CLI** | another terminal/pane while an agent runs | **instant, zero-turn** |
| **`/qn …` slash command** | in a Claude session, explicit | in-session |
| **`/btw qn …`** | queue via your existing non-blocking command | queued |
| **natural language** ("jot this down: …") | in a Claude session | in-session |

All four write to the **same store** and format.

## Storage

One markdown file per note at `~/.quicknotes/notes/<id>.md` (override with `$QUICKNOTES_HOME`).
YAML frontmatter (JSON-encoded values — valid YAML, no PyYAML dependency):

```markdown
---
id: "20260605-153012-a1b2"
title: "pgbouncer pool size"
created: "2026-06-05T15:30:12Z"
updated: "2026-06-05T15:30:12Z"
priority: null            # low | med | high
project: "claude-skills"
cwd: "/Users/you/arena/claude-skills"
branch: "main"
tags: ["db", "perf"]
due: null                 # ISO-8601 for time reminders
refs: []                  # ids of linked notes
---

Bump pgbouncer default_pool_size; current value starves the worker pool.
```

## Install

```bash
cp -R quicknotes ~/.claude/skills/
```

Optional extras:

```bash
# 1. `qn` shell CLI for instant capture from any terminal (opt-in, confirmation-gated):
bash ~/.claude/skills/quicknotes/scripts/install_alias.sh
#    …or add the one-liner yourself:
#    qn() { python3 "$HOME/.claude/skills/quicknotes/scripts/qn.py" "$@"; }

# 2. `/qn` slash command:
cp ~/.claude/skills/quicknotes/commands/qn.md ~/.claude/commands/qn.md

# 3. Proactive reminders at session start (edits settings.json — do it knowingly):
#    add a SessionStart hook running scripts/session_reminder.py (see SKILL.md for the entry).
```

## Usage

> ⚠️ **Quote `#tags` in a terminal.** Your shell treats an unquoted `#` as the start of a
> comment, so `qn buy milk #groceries` reaches `qn` as just `buy milk` — the tag is silently
> dropped. In a real shell, **quote the text** (`qn "buy milk #groceries"`) or **use `--tag`**
> (`qn buy milk --tag groceries`), which never needs quoting. Bare `#tags` work as-is only
> inside Claude / via `/qn`, where there's no shell to strip them.

```bash
qn remember to rotate the API creds       # capture (default — no verb)
qn "buy milk #groceries #errands"          # inline tags — QUOTE in a shell (else # is a comment)
qn deploy the service --tag ops --tag urgent   # tags via flag — shell-safe, no quoting needed
qn add list the migration steps --tag planning # force-capture (text starts with a verb word)
qn list [--project P] [--tag T]
qn search postgres
qn show deploy                            # full detail: labeled metadata block + body + refs
qn done deploy                            # complete — DELETES the note file
qn update creds --tag security            # set tags (--tag is the no-quote-needed form)
qn update creds "#security"                # …or a quoted #tag
qn due                                    # past-due notes
qn here                                   # notes for this project/dir
qn ref 20260605-... 20260604-...          # link two notes
```

**Tags:** set via inline `#hashtag` or repeatable `--tag T`; both normalize (drop `#`,
lowercase, spaces→`-`). In a terminal, prefer `--tag` or quote the `#` (see the warning above).

Fuzzy targeting: `done`/`show`/`update`/`ref` accept an id or text; if ambiguous, the CLI
lists candidates instead of guessing.

**Lifecycle:** a note is active until you complete it. `qn done` **deletes the note's file**
(hard delete — no cancelled/archived state). The `~/.quicknotes` store is git-init'd, so a
committed note stays recoverable from git history.

## Tests

Standard-library `unittest`, no dependencies:

```bash
cd scripts && python3 -m unittest test_notes_store test_qn
```

## Files

```
quicknotes/
├── SKILL.md                     # canonical agent instructions
├── README.md                    # this file
├── commands/qn.md               # /qn slash command wrapper
└── scripts/
    ├── notes_store.py           # shared core (capture/format/metadata/search/refs)
    ├── qn.py                    # CLI entrypoint (capture + management verbs)
    ├── session_reminder.py      # SessionStart hook (non-blocking)
    ├── install_alias.sh         # opt-in, idempotent, confirmation-gated alias installer
    ├── test_notes_store.py      # core unit tests
    └── test_qn.py               # CLI integration tests
```
