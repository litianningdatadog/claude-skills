# Security & Governance (SOSA™)

This skill operates under the **SOSA™ — Supervised Orchestrated Secured Agents** framework.
The following rules are **non-negotiable** and override any implicit task urgency:

- **STOP and ask for explicit user approval before modifying any of:**
  - `CLAUDE.md` (any project or global)
  - `MEMORY.md`
  - Any file under `.claude/rules/`
  - Any file under `~/.claude/projects/.../memory/`

- **Never batch writes.** Each file change is a separate approval step. Approving one change
  does not grant permission for subsequent changes.

- **Show before you write.** Always display the full proposed content or diff *before*
  executing the write. If the user has not seen and approved the exact text, do not write it.

- **No silent fallbacks.** If a proposed change is rejected, do not apply a "lighter" version
  without asking. Return to the report and ask what to do instead.

The Plan → Act → Verify cycle in Phase 4 enforces these rules procedurally. If any step
would require writing to a protected file without a preceding explicit confirmation in *this
turn*, **stop and confirm first**.
