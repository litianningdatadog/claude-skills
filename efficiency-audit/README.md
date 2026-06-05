# efficiency-audit

Analyzes recent Claude Code conversation transcripts to surface recurring inefficiencies —
repeated corrections, context you re-explain every session, slow per-session orientation,
automation candidates, and failing hooks — then proposes and applies concrete fixes.

> **Canonical behavior lives in [`SKILL.md`](SKILL.md).** This README covers human-facing
> install, direct CLI usage, and testing. If the two ever disagree, `SKILL.md` wins.

## How it works

Pipeline: **analyze → report → propose → apply (with approval)**. A Python script
(`scripts/analyze_conversations.py`) parses the JSONL transcripts under
`~/.claude/projects/` and emits pre-clustered findings; Claude then synthesizes a
prioritized report and applies approved changes to `CLAUDE.md`, memory, and settings. See
`SKILL.md` for the full four-phase procedure Claude follows.

## Install

```bash
cp -R efficiency-audit ~/.claude/skills/
```

Once installed, trigger it in any Claude Code session with phrases like
"audit my usage", "improve my workflow", or "what am I repeating", or run
`/efficiency-audit` if your client exposes skills as commands.

## Running the analyzer directly

The script is a standalone CLI — useful for previewing findings without invoking the skill.

```bash
# Current project, last 30 days, human-readable preview:
python3 scripts/analyze_conversations.py \
  --days 30 --project "$(basename "$PWD")" --output text 2>/dev/null

# All projects, JSON (what the skill consumes):
python3 scripts/analyze_conversations.py --days 30 --output json 2>/dev/null
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--days N` | `30` | Only scan transcripts modified in the last N days. |
| `--project P` | _(all)_ | Restrict to a project. Accepts a real path (`/Users/me/DataDog/foo`), the folder name (`foo`), or the encoded dir name — matched tolerant of the `/`/`.`→`-` encoding Claude Code uses for transcript dirs. |
| `--output json\|text` | `json` | `json` for the skill to consume; `text` for a quick human preview. |

### Output categories

`corrections`, `missing_context`, `slow_start_context`, and `automation_candidates` are
each a list of groups carrying a recurrence `count`, distinct-`sessions` count, and up to
three `examples`, sorted by frequency. `hook_errors` lists failing hooks (name, exit code,
stderr). `repeated_topics` lists high-frequency keywords. System-generated noise
(context-compaction notices, slash-command and skill-body injections, security-review
boilerplate) is filtered out during extraction.

## Troubleshooting

### `hook_errors` showing `exit=127` / `/bin/sh: …/Library/Application: No such file`

If the audit reports hook errors like:

```
[SessionStart:startup] exit=127 cmd=${CLAUDE_PLUGIN_ROOT}/scripts/on-session-start.sh
  stderr: /bin/sh: /Users/<you>/Library/Application: No such file
```

the cause is an **unquoted `${CLAUDE_PLUGIN_ROOT}`** in a plugin's `hooks.json`.
`${CLAUDE_PLUGIN_ROOT}` is set per-plugin to that plugin's directory. In normal Claude Code
that path has no spaces, so an unquoted command happens to work. In **agent-mode (`sdk-ts`)
sessions** the plugin is materialized under `~/Library/Application Support/Claude/…`, whose
space makes `/bin/sh` split the path at `Application` — hence the `No such file` failure.

**Fix:** quote the path token in the plugin's `hooks/hooks.json` so spaces survive. Quote the
**path**, not the whole command:

```jsonc
// bad
"command": "${CLAUDE_PLUGIN_ROOT}/scripts/on-session-start.sh"
"command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/log.py"
// good
"command": "\"${CLAUDE_PLUGIN_ROOT}/scripts/on-session-start.sh\""
"command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/log.py\""
```

To find and fix every affected `hooks.json` under your plugin marketplace at once:

```bash
cd ~/.claude/plugins/marketplaces/<your-marketplace>
python3 - <<'PY'
import json, glob, re
PAT = re.compile(r'(?<!")(\$\{CLAUDE_PLUGIN_ROOT\}[^\s"]*)')   # quote only the path token
for path in glob.glob("*/hooks/hooks.json"):
    raw = open(path).read(); new = raw
    for c in {h.get("command","") for ev in json.loads(raw).get("hooks",{}).values()
              for b in ev for h in b.get("hooks",[])}:
        nc = PAT.sub(r'"\1"', c)
        if nc != c:
            new = new.replace(json.dumps(c), json.dumps(nc))
    if new != raw:
        json.loads(new)              # validate before writing
        open(path, "w").write(new)
        print("fixed", path)
PY
```

Note: hook errors in the report are **historical** — they come from past transcripts and
remain visible until they age out of the `--days` window. Re-run with a small `--days` after
fixing (and after starting a fresh session) to confirm no *new* failures appear. Editing your
local marketplace clone is also a working-tree change; push it upstream so it survives plugin
updates.

When you run the **skill** (rather than fixing by hand), it treats hook fixes as a separate,
explicit decision because they edit files *outside* your project (a shared plugin clone under
`~/.claude/plugins/marketplaces/…`). It will explain that the change is local-only and
revertible by a plugin update, then ask you to choose: fix locally, prepare the upstream PR,
both, or skip. It won't modify a shared plugin clone (or anything under `~/Library/Application
Support/`) without that explicit choice. See Phase 4 in [`SKILL.md`](SKILL.md).

## Tests

Standard-library `unittest`, no dependencies:

```bash
cd scripts && python3 -m unittest test_analyze_conversations
```

## Files

```
efficiency-audit/
├── SKILL.md                              # canonical agent instructions (the skill spec)
├── README.md                             # this file
└── scripts/
    ├── analyze_conversations.py          # transcript analyzer CLI
    └── test_analyze_conversations.py     # unittest suite
```
