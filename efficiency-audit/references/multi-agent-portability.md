# Multi-Agent Portability Reference

Research conducted 2026-06-17. Covers porting the efficiency-audit skill to Codex CLI and OpenCode.

---

## SKILL.md compatibility

All three agents share the same `SKILL.md` frontmatter convention (`name` + `description`). The skill activation mechanism ports with zero changes. The two things that need adapting per target are:

1. **Transcript parser** — each agent stores conversation history differently.
2. **Instruction-file write target** — the equivalent of `CLAUDE.md` differs.

---

## Codex CLI — Low effort

**Official docs**: https://developers.openai.com/codex/skills

### Paths

| Item | Path |
|---|---|
| Config home | `~/.codex/` (override: `$CODEX_HOME`) |
| Global instruction file | `~/.codex/AGENTS.md` |
| Per-project instruction file | `AGENTS.md` at git root |
| Global skills | `~/.agents/skills/<name>/SKILL.md` |
| Per-project skills | `.agents/skills/<name>/SKILL.md` |
| Session transcripts | `~/.codex/sessions/YYYY/MM/DD/rollout-{ISO_TIMESTAMP}-{UUID}.jsonl` |
| Session index | `~/.codex/state.sqlite` |

### Transcript format

Each line is a JSON object with the envelope:

```json
{"timestamp": "<ISO UTC>", "type": "<event_type>", "payload": {...}}
```

Key `type` values:

| `type` | Payload contents |
|---|---|
| `session_meta` | `model_provider`, `cli_version`, `cwd`, `id`, `git_branch` |
| `event_msg` | Nested `type`: `user_message`, `agent_message`, `agent_reasoning`, `turn_complete` |
| `response_item` | Nested `type`: `message`, `function_call`, `function_call_output` |

Tool calls and outputs are flat paired records linked by `call_id` (no nesting). Completed/cold session files are Zstandard-compressed (`.zst`) — skip them or decompress before parsing.

### Changes required

| Component | Claude Code | Codex CLI |
|---|---|---|
| Skill install path | `~/.claude/skills/efficiency-audit/` | `~/.agents/skills/efficiency-audit/` |
| `PLUGIN_ROOT` resolver in `SKILL.md` | `~/.claude/plugins/cache/litianningdatadog-marketplace/efficiency-audit/*/` | `~/.agents/skills/efficiency-audit/` |
| Transcript glob | `~/.claude/projects/**/*.jsonl` | `~/.codex/sessions/**/*.jsonl` (skip `.zst`) |
| Transcript reader | Claude Code envelope | New reader for `{"timestamp","type","payload"}` envelope |
| Instruction file | `CLAUDE.md` / `~/.claude/CLAUDE.md` | `AGENTS.md` / `~/.codex/AGENTS.md` |
| Routing detection commands | check `CLAUDE.md` existence | check `AGENTS.md` existence |

### `analyze_conversations.py` changes

- Add a new reader function for the Codex envelope (extract `event_msg` records where `payload.type == "user_message"` or `"agent_message"`).
- Update the transcript glob path.
- The categorization, synthesis, and scoring stages are agent-agnostic — no changes needed there.

---

## OpenCode — Medium effort

**Official docs**: https://opencode.ai/docs/

### Paths

| Item | Path |
|---|---|
| Global config | `~/.config/opencode/opencode.json` |
| Global instruction file | `~/.config/opencode/AGENTS.md` (falls back to `~/.claude/CLAUDE.md`) |
| Per-project instruction file | `AGENTS.md` at git root (falls back to `CLAUDE.md`) |
| Global skills | `~/.config/opencode/skills/<name>/SKILL.md` |
| Per-project skills | `.opencode/skills/<name>/SKILL.md` |
| **Claude Code compat skill paths** | `~/.claude/skills/<name>/SKILL.md` and `.claude/skills/<name>/SKILL.md` (explicitly supported fallbacks — works today with zero changes) |
| Session database | `~/.local/share/opencode/opencode.db` (SQLite, WAL mode) |

### Transcript format (SQLite)

Database at `~/.local/share/opencode/opencode.db`. Relevant tables:

| Table | Key columns |
|---|---|
| `session` | `id`, `project_id`, `title`, `model`, `tokens`, timestamps |
| `message` | `id`, `session_id`, `info` (full serialized message JSON) |
| `part` | `id`, `session_id`, `message_id`, `type`, `data` (JSON payload) |

Part `type` discriminator values: `text`, `reasoning`, `file`, `tool`, `step-start`, `step-finish`, `compaction`, `subtask`.

Conversation text lives in `part` rows where `type = 'text'`. The actual content is in the JSON `data` column. Query to extract conversation turns:

```sql
SELECT s.title, s.id as session_id, m.id as message_id, json_extract(p.data, '$.content') as content
FROM part p
JOIN message m ON p.message_id = m.id
JOIN session s ON m.session_id = s.id
WHERE p.type = 'text'
ORDER BY p.rowid;
```

Python stdlib `sqlite3` handles this with no extra dependencies.

> **Known issue**: opening multiple OpenCode sessions in the same repo can corrupt `opencode.db` (concurrency bug as of 2026-06-17).

### Changes required

| Component | Claude Code | OpenCode |
|---|---|---|
| Skill install path | `~/.claude/skills/efficiency-audit/` | Already works via compat fallback — no change |
| `PLUGIN_ROOT` resolver | `~/.claude/plugins/cache/...` | `~/.config/opencode/skills/efficiency-audit/` |
| Transcript source | JSONL glob | SQLite query on `~/.local/share/opencode/opencode.db` |
| Transcript reader | `json.loads()` per line | `sqlite3` query (full rewrite of reader function) |
| Instruction file | `CLAUDE.md` | `AGENTS.md` (if `AGENTS.md` exists, `CLAUDE.md` is ignored) |
| Routing detection | check `CLAUDE.md` | check `AGENTS.md` first; fall back to `CLAUDE.md` only if absent |

### `analyze_conversations.py` changes

- Replace the JSONL glob+parse loop with a `sqlite3` connection to `~/.local/share/opencode/opencode.db`.
- Join `PartTable` → `MessageTable` → `SessionTable`, filter `type = 'text'`, reconstruct turn sequence by `rowid` order.
- Categorization, synthesis, and scoring stages: no changes needed.

---

## Recommended implementation strategy

To support all three agents from a single skill, add a **multi-target adapter** in `analyze_conversations.py`:

```
1. Detect which agent is active:
   - If ~/.claude/projects/ exists and has .jsonl files → Claude Code
   - If ~/.codex/sessions/ exists → Codex CLI
   - If ~/.local/share/opencode/opencode.db exists → OpenCode
   (Or accept a --agent flag to force a target)

2. Route to the appropriate reader:
   - Claude Code reader: existing logic
   - Codex reader:  new envelope parser for ~/.codex/sessions/**/*.jsonl
   - OpenCode reader: new sqlite3 query function

3. After reading, normalize all turns into the same internal shape
   the existing categorization and synthesis stages already consume.
```

The instruction-file write target also needs the same detection logic:
- Check for `AGENTS.md` (Codex/OpenCode) before falling back to `CLAUDE.md`.
- Prompt the user if multiple files exist (same A/B prompt pattern as `references/claude-md-routing.md`).

---

## Sources

- Codex CLI skills: https://developers.openai.com/codex/skills
- Codex AGENTS.md: https://developers.openai.com/codex/guides/agents-md
- Codex config: https://developers.openai.com/codex/local-config/
- Codex rollout format: https://deepwiki.com/openai/codex/3.5.2-rollout-persistence-and-replay
- OpenCode skills: https://opencode.ai/docs/skills/
- OpenCode rules: https://opencode.ai/docs/rules/
- OpenCode config: https://opencode.ai/docs/config/
- OpenCode storage: https://deepwiki.com/sst/opencode/2.9-storage-and-database
- OpenCode message structure: https://deepwiki.com/sst/opencode/2.2-message-and-prompt-system
