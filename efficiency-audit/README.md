# efficiency-audit

Analyzes recent Claude Code conversation transcripts to surface recurring inefficiencies —
repeated corrections, context you re-explain every session, slow per-session orientation,
automation candidates, and failing hooks — then proposes and applies concrete fixes.

> **Canonical behavior lives in [`SKILL.md`](SKILL.md).** This README covers human-facing
> install, direct CLI usage, and testing. If the two ever disagree, `SKILL.md` wins.

## How it works

Pipeline: **analyze → draft rules → report → plan → act → verify**. A Python script
(`scripts/analyze_conversations.py`) parses the JSONL transcripts under `~/.claude/projects/`
and emits pre-clustered findings grouped by recurrence count and dominant project. Claude then
**drafts concrete proposed `CLAUDE.md` rules** for the top correction groups (approve/edit/skip),
synthesizes a prioritized report, and applies approved changes to `CLAUDE.md`, memory, and
settings following a strict **Plan → Act → Verify** cycle.

> **Governance (SOSA™):** The skill requires explicit human approval before writing to
> `CLAUDE.md`, `MEMORY.md`, or any `.claude/rules/` file. Each change is shown in full
> before execution; approving one change does not authorize any other. See the
> [Security & Governance section in SKILL.md](SKILL.md) for the full rules.

See `SKILL.md` for the full four-phase procedure Claude follows.

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

The `--output text` mode automatically saves a baseline to `~/.claude/efficiency-audit-baseline.json`
after each run and shows deltas on the next run — e.g. `CORRECTIONS (22 matches, was 30, -27% ↓)`.
This lets you measure whether CLAUDE.md fixes are actually reducing friction over time.

### Output categories

`corrections`, `missing_context`, `slow_start_context`, and `automation_candidates` are
each a list of groups sorted by frequency. Each group carries:

| Field | Meaning |
|-------|---------|
| `count` | How many user messages matched |
| `sessions` | Distinct sessions where the pattern appeared |
| `top_project` | The project where this friction occurred most |
| `examples` | Up to 3 representative messages (whitespace-collapsed) |
| `preceding_action` | What Claude said immediately before the correction (`corrections` only) — the causal trigger used to draft targeted CLAUDE.md rules |

`hook_errors` lists failing hooks (name, exit code, stderr). System-generated noise
(context-compaction notices, slash-command and skill-body injections, security-review
boilerplate, context-injection headers, and tool-output pastes) is filtered out during
extraction — every group in the output represents real user input.

## Troubleshooting

### `hook_errors` in the report

The audit *detects* failing hooks but does not repair them. The most common is `exit=127`
with stderr like `/bin/sh: …/Library/Application: No such file` — an unquoted
`${CLAUDE_PLUGIN_ROOT}` in a plugin's `hooks.json` that breaks in agent-mode. To diagnose and
fix this (across all installed plugins, with an explicit opt-in before editing shared plugin
files), use the **[`hook-doctor`](../hook-doctor/)** skill.

Hook errors here are **historical** — they come from past transcripts and remain visible until
they age out of the `--days` window. After fixing, re-run with a small `--days` (and a fresh
session) to confirm no *new* failures appear.

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
