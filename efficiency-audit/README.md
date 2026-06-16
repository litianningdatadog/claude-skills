# efficiency-audit

Analyzes recent Claude Code conversation transcripts to surface recurring inefficiencies —
repeated corrections, context you re-explain every session, slow per-session orientation,
automation candidates, and failing hooks — then proposes and applies concrete fixes.

> **Canonical behavior lives in [`SKILL.md`](skills/efficiency-audit/SKILL.md).** This README covers human-facing
> install, direct CLI usage, and testing. If the two ever disagree, `SKILL.md` wins.

## How it works

Pipeline: **analyze + score files → synthesize rules → report → plan → act → verify → (opt-in) Karpathy merge**.
Phase 1 runs three checks: a terminal-title setup check, `analyze_conversations.py` scanning
transcripts for friction patterns (corrections, missing context, tool-call failures, automation
candidates), and `score_efficiency.py` scoring your `CLAUDE.md` / `MEMORY.md` on a 0.0–1.0
efficiency scale (files ≥ 5000 lines are flagged as Critical Context Blockers). `synthesize_findings.py`
then pipes the findings through the Claude CLI to produce pre-drafted CLAUDE.md rules ranked by
estimated token savings — skipping the manual Phase 2 synthesis step when it succeeds. Rules are
written via `apply_rules.py` using idempotent marker blocks (`<!-- efficiency-audit:start/end -->`),
so re-running the audit replaces rules in-place rather than accumulating duplicates. Changes are
applied following a strict **Plan → Act → Verify** cycle. Phase 5 offers an opt-in smart merge of
[Karpathy-inspired behavioral guidelines](https://github.com/multica-ai/andrej-karpathy-skills/blob/main/CLAUDE.md)
into your `CLAUDE.md` (deduplicated against your existing rules — not blindly appended).

> **Governance (SOSA™):** The skill requires explicit human approval before writing to
> `CLAUDE.md`, `MEMORY.md`, or any `.claude/rules/` file. Each change is shown in full
> before execution; approving one change does not authorize any other. See
> [`references/governance.md`](references/governance.md) for the full rules.

See `SKILL.md` for the full five-phase procedure Claude follows.

## Install

```
/plugin marketplace add litianningdatadog/claude-marketplace
/plugin install efficiency-audit@litianningdatadog-marketplace
```

Once installed, trigger it in any Claude Code session with phrases like
"audit my usage", "improve my workflow", or "what am I repeating", or run
`/efficiency-audit` if your client exposes skills as commands.

Updates are applied automatically — run `/plugin marketplace update` to pull the latest version.

## Running the scripts directly

### Analyzer

```bash
# Current project, last 30 days, human-readable preview:
python3 scripts/analyze_conversations.py \
  --days 30 --project "$(basename "$PWD")" --output text 2>/dev/null

# All projects, JSON (pipe to synthesize_findings.py):
python3 scripts/analyze_conversations.py --days 30 --output json 2>/dev/null
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--days N` | `30` | Only scan transcripts modified in the last N days. |
| `--project P` | _(all)_ | Restrict to a project. Accepts a real path, the folder name, or the encoded dir name — matched tolerant of the `/`/`.`→`-` encoding Claude Code uses. |
| `--output json\|text` | `json` | `json` for skill/synthesis consumption; `text` for a quick human preview. |

After every run a baseline is saved to `~/.claude/efficiency-audit-baseline.json` (keyed by
project filter). Subsequent runs show deltas inline — e.g. `CORRECTIONS (22 matches, was 30, -27% ↓)`.

### LLM synthesis

```bash
python3 scripts/analyze_conversations.py --days 30 --output json 2>/dev/null \
| python3 scripts/synthesize_findings.py
```

Produces a ranked JSON array of `{proposed_rule, estimated_tokens_saved, scope, evidence, confidence}`.
Use `--dry-run` to print the digest sent to the LLM without making a call; `--model` to override the model.

### Applying rules (idempotent marker blocks)

```bash
python3 scripts/apply_rules.py --read ~/.claude/CLAUDE.md          # print existing block
python3 scripts/apply_rules.py --dry-run ~/.claude/CLAUDE.md '["r1"]'  # preview diff
python3 scripts/apply_rules.py ~/.claude/CLAUDE.md '["r1", "r2"]'  # write
```

Writes into a `<!-- efficiency-audit:start/end -->` block. Re-running replaces the block in-place — no duplicates.

### Scoring CLAUDE.md / MEMORY.md for bloat

`score_efficiency.py` applies piecewise linear interpolation to give any file a 0.0–1.0 score.
The skill resolves the project `MEMORY.md` path automatically via `resolve_memory_path.py`,
which honours the `autoMemoryDirectory` setting and derives the project key from the git root
(not `cwd`, so subdirectory runs still find the right memory directory).

```bash
python3 scripts/score_efficiency.py ~/.claude/CLAUDE.md        # single file
python3 scripts/score_efficiency.py ~/.claude/CLAUDE.md --json  # machine-readable
```

| Lines | Score | Diagnosis | Alert |
|-------|-------|-----------|-------|
| 0–300 | 1.00 | Optimal | — |
| 300–750 | 1.00→0.50 | Good / Warning | — |
| > 200 | any | — | 📋 **Recipe Book** — domain rules should move to `.claude/rules/` |
| 750–5000 | 0.50→0.00 | Critical | — |
| ≥ 5000 | **0.00** | **Critical Context Blocker** — exits 1 | — |

Two independent signals: the **efficiency score** (continuous, 0–5000 lines) and the **Recipe Book alert** (structural, fires above 200 lines regardless of score). A 250-line file can score 1.00 Optimal *and* trigger the Recipe Book alert — the score measures size, the alert measures structure.

Files scoring 0.0 are treated as **High Impact** in the Phase 3 report. Recipe Book alerts prompt the guided 4-step extraction procedure in [`references/recipe-book.md`](references/recipe-book.md).

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

`tool_failures` lists tool-call errors extracted from `tool_use`/`tool_result` pairs, grouped
by `(tool, error_category)`. Categories: `unread_write` (Edit/Write without prior Read),
`file_not_found`, `wrong_context`, `git_error` (exit 128), `bash_nonzero`, `permission_denied`,
`user_interrupted`, `tool_use_error` (generic).

`terminal_title_skill_missing` and `terminal_title_not_configured` surface terminal-title
setup gaps (see [`references/terminal-title-check.md`](references/terminal-title-check.md)
for detection logic and known limitations with conflicting plugins).

`hook_errors` lists failing hooks (name, exit code, stderr). System-generated noise
(context-compaction notices, slash-command and skill-body injections, security-review
boilerplate, context-injection headers, and tool-output pastes) is filtered out during
extraction — every group in the output represents real user input.

`deltas` compares current counts to the previous baseline keyed by project filter, showing
per-category `{current, previous, delta, pct_change}`. Also included in the `--output text`
inline headers.

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
cd scripts && python3 -m unittest test_analyze_conversations test_score_efficiency \
  test_synthesize_findings test_apply_rules
```

## Files

```
efficiency-audit/
├── .claude-plugin/
│   └── plugin.json                       # plugin manifest
├── skills/
│   └── efficiency-audit/
│       └── SKILL.md                      # canonical agent instructions (5-phase procedure)
├── README.md                             # this file
├── references/
│   ├── category-guide.md                 # Phase 2 category interpretation (loaded during synthesis)
│   ├── claude-md-routing.md              # routing tiers + always-ask confirmation (loaded in Phase 3)
│   ├── governance.md                     # SOSA™ rules — loaded by agent before Phase 4
│   ├── karpathy-guardrails.md            # 4 behavioral principles + Phase 5 merge procedure
│   ├── noise-filters.md                  # false-positive filter catalog — loaded when adding filters
│   ├── recipe-book.md                    # 4-step CLAUDE.md refactor procedure — loaded when >200 lines
│   └── terminal-title-check.md           # terminal-title detection, conflict check, hook proposal
└── scripts/
    ├── analyze_conversations.py          # transcript analyzer CLI (patterns + tool failures + deltas)
    ├── apply_rules.py                    # idempotent marker-block writer for CLAUDE.md rules
    ├── resolve_memory_path.py            # resolves project MEMORY.md path (git root + autoMemoryDirectory)
    ├── score_efficiency.py               # file byte-efficiency scorer (piecewise linear)
    ├── synthesize_findings.py            # LLM synthesis: findings JSON → ranked CLAUDE.md rules
    ├── test_analyze_conversations.py     # unittest suite
    ├── test_apply_rules.py               # unittest suite for apply_rules
    ├── test_score_efficiency.py          # unittest suite for scorer
    └── test_synthesize_findings.py       # unittest suite for synthesize_findings
```
