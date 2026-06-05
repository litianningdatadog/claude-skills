---
description: Capture or manage a quick note (quicknotes skill)
argument-hint: <note text> | list | search <q> | done <id|fuzzy> | due | here
---

Use the **quicknotes** skill to handle this quick-note request.

Input: `$ARGUMENTS`

Rules:
- If the input is empty, show the quicknotes usage summary.
- If it starts with a management verb (`list`, `search`, `show`, `done`, `update`,
  `due`, `here`, `ref`, `add`), run that management action. Note: `done` deletes the note.
- Otherwise treat the entire input as the text of a NEW note and capture it.

Follow the quicknotes `SKILL.md` procedure (it runs `scripts/qn.py`). Keep the reply terse —
confirm the captured note's id/title, or print the requested list/search/result.
