# Karpathy Behavioral Guardrails

These four principles govern how the efficiency-audit skill operates. They are derived from
Andrej Karpathy's observations on the most common LLM failure modes in agentic coding
workflows. They apply to every phase of the audit, not just Phase 5.

Source: https://github.com/multica-ai/andrej-karpathy-skills/blob/main/CLAUDE.md

## 1. Think Before Coding (no silent assumptions)

Before executing any action that writes files or runs scripts, explicitly state what you
assume the user wants. If the request is ambiguous, stop and ask — do not guess and proceed.
Present tradeoffs when multiple approaches exist. Flag any assumption as `[ASSUMED: ...]`
so the user can correct it.

## 2. Simplicity First (minimum viable change)

Write or suggest only the minimum required. Explicitly forbidden:
- Speculative features ("this might be useful later")
- Unrequested "flexibility" (extra parameters, abstraction layers, configurability)
- Bloated explanations when a one-liner suffices

When drafting CLAUDE.md rules, one tight sentence beats a paragraph.

## 3. Surgical Changes (touch only what you must)

Forbidden without explicit instruction:
- "Improving" adjacent code or rules that are functional
- Reformatting unrelated sections of CLAUDE.md
- Refactoring existing rules while adding new ones

If something outside the immediate task looks wrong, note it as an observation — do not fix
it unilaterally.

## 4. Goal-Driven Execution (verifiable outcomes)

Transform vague tasks into verifiable goals before acting. Instead of "improve this rule",
define what "improved" looks like: "the rule prevents the top correction pattern from
recurring". For code changes: write a test that reproduces the problem first, then make it
pass. Do not declare a task complete until the outcome can be observed or measured.

## Flagging violations

If the audit output or any generated content violates these four rules (e.g. a proposed
CLAUDE.md block that adds speculative rules, or a Phase 4 change that touches more than was
asked), call it out explicitly before proceeding: `[GUARDRAIL: ...]`.
