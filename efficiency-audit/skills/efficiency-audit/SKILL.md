---
name: efficiency-audit
description: "Analyzes recent Claude Code conversation transcripts to surface recurring inefficiencies, then produces a concrete improvement plan and applies it. Use when the user wants to improve their Claude Code workflow, reduce repeated corrections, eliminate missing-context frustration, or automate recurring patterns. Trigger phrases: 'improve my workflow', 'audit my usage', 'what am I repeating', 'efficiency audit', 'review my conversations', or any request to update CLAUDE.md based on observed patterns."
---

## Phase 0: Check Intent

Ask: "Standard audit, or specific areas to focus on?" Elevate ad-hoc requirements to High Impact in Phase 3.

## Phase 1: Analyze

```bash
PLUGIN_ROOT=$(ls -dt ~/.claude/plugins/cache/litianningdatadog-marketplace/efficiency-audit/*/ 2>/dev/null | head -1)
```

```bash
python3 "${PLUGIN_ROOT}/scripts/analyze_conversations.py" \
  --days 30 --project "$(basename "$PWD")" --output json 2>/dev/null \
| python3 "${PLUGIN_ROOT}/scripts/synthesize_findings.py" 2>/dev/null
```

If synthesis succeeds → `recommendations` has `proposed_rule`, `estimated_tokens_saved`, `scope`, `evidence` — skip Phase 2, go to Phase 3.
If synthesis fails → re-run analysis with `--output json` and proceed to Phase 2.

```bash
MEMORY_MD=$(python3 "${PLUGIN_ROOT}/scripts/resolve_memory_path.py" 2>/dev/null)
python3 "${PLUGIN_ROOT}/scripts/score_efficiency.py" \
  .claude/CLAUDE.md ~/.claude/CLAUDE.md "$MEMORY_MD" 2>/dev/null
```

Score < 0.5 → warning; 0.0 → Critical Context Blocker (run recipe-book before adding rules).
Also check terminal title: `references/terminal-title-check.md`.

## Phase 2: Synthesize

Read `references/category-guide.md` for category interpretation and rule-drafting guidance.

## Phase 3: Report

- `corrections` count ≥ 3 → draft CLAUDE.md rule from `examples` + `preceding_action`.
- `missing_context` sessions ≥ 3 → write candidate CLAUDE.md fact.
- `tool_failures` count ≥ 2 → draft a CLAUDE.md rule preventing the error pattern (e.g. `unread_write` → "Always Read before Edit/Write").

Route per `references/claude-md-routing.md`. Present as: proposed rules (approve/edit/skip) → High Impact → Medium Impact → Automation Opportunities → Open Questions.

## Phase 4: Apply

Read `references/governance.md`. Plan → Act → Verify; never batch. Order: memory → CLAUDE.md → settings.json.
Hook fixes → hand off to `hook-doctor`.

Use the marker-block writer for CLAUDE.md (prevents duplicates across re-runs):

```bash
python3 "${PLUGIN_ROOT}/scripts/apply_rules.py" --read <path>              # see existing
python3 "${PLUGIN_ROOT}/scripts/apply_rules.py" --dry-run <path> '["..."]' # preview
python3 "${PLUGIN_ROOT}/scripts/apply_rules.py" <path> '["r1", "r2"]'     # write
```

## Phase 5: Karpathy Guardrails (opt-in)

Run evidence check in `references/karpathy-guardrails.md`. Surface offer if threshold met; skip if declined.
Read at every phase; flag violations as `[GUARDRAIL: ...]`.

## Utilities

- Noise false positives: `references/noise-filters.md`
- CLAUDE.md > 200 lines: run `references/recipe-book.md` *before* proposing rules
- Re-run every 2–4 weeks; baseline delta confirms rules are reducing friction
