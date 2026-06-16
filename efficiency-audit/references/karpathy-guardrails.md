# Karpathy Behavioral Guardrails

Source: https://github.com/multica-ai/andrej-karpathy-skills/blob/main/CLAUDE.md

The four principles govern every phase of the audit — not just Phase 5.

1. **Think Before Coding** — State assumptions before acting; stop and ask when ambiguous; flag with `[ASSUMED: ...]`.
2. **Simplicity First** — Write only what was asked; no speculative features, extra abstraction, or configurability.
3. **Surgical Changes** — Touch only what the task requires; note but don't fix unrelated issues.
4. **Goal-Driven Execution** — Define a verifiable outcome before acting; don't declare complete until it can be observed.

The merge procedure (Phase 5) fetches the full upstream text from the source URL above for diffing against the user's CLAUDE.md.

## Flagging violations

If the audit output or any generated content violates the four principles (e.g. a proposed
CLAUDE.md block that adds speculative rules, or a Phase 4 change that touches more than was
asked), call it out explicitly before proceeding: `[GUARDRAIL: ...]`.

---

## Phase 5

### Evidence check

Scan `corrections` and `missing_context` example strings for these signals:

| Signal keyword (substring, case-insensitive) | Guardrail |
|---|---|
| "assumed", "don't guess", "should have asked", "clarify first" | Think Before Coding |
| "over-engineered", "too much", "didn't ask for", "not requested" | Simplicity First |
| "unrelated", "why did you change", "only change X", "didn't touch" | Surgical Changes |
| "does it work", "actually test", "didn't verify", "not confirmed" | Goal-Driven Execution |

Each matching example string = 1 hit toward its guardrail — accumulate across all groups; ignore `count` field.

### Trigger threshold

**Minimum hits to offer guardrails: 2**

Raise to reduce false positives in high-volume audits; lower for earlier detection of emerging patterns.

### Offer templates

When one guardrail triggers:
> "The audit found [N] corrections about [pattern] — the [Guardrail Name] principle directly
> addresses this. Would you like me to merge it into your `CLAUDE.md`? I'll produce a
> structured, deduplicated result — not a blind append."

When multiple guardrails trigger:
> "The audit found evidence for [N] Karpathy guardrails: [N1] corrections about [pattern1]
> (→ [Guardrail 1]), and [N2] about [pattern2] (→ [Guardrail 2]). Would you like me to
> merge the relevant ones into your `CLAUDE.md`? I'll produce a structured, deduplicated
> result — not a blind append."

### Merge procedure

1. **Read** the user's current `CLAUDE.md` (global `~/.claude/CLAUDE.md` or project-level).
2. **Fetch** the Karpathy guidelines from the source URL above (WebFetch; fall back to asking
   the user to paste if unavailable).
3. **Merge** using LLM reasoning — do NOT blindly append:
   - **Deduplicate**: if a user rule already covers a principle, mark it covered and skip.
   - **Preserve** the user's existing rules verbatim — never rephrase or reorder them.
   - **Add only what is genuinely new** — label each added block clearly.
   - **Produce structured output** with headings like `## Coding discipline`,
     `## Task execution`, `## Change scope`.
4. **Show** the full merged result and a diff summary. Wait for approval before writing.
5. Apply via the Plan → Act → Verify cycle (Phase 4 rules apply).
