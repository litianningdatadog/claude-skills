# Noise Filter Reference

These patterns are applied automatically during extraction (`is_noise()` / `NOISE_PATTERNS`
in `analyze_conversations.py`). They do not appear in JSON output because they are
system-generated, not real user friction.

## Active filters

- "This session is being continued from a previous conversation..." → context-compaction
- Messages starting with `<command-name>` / `<command-message>` / `<local-command-*>` tags
- Security review boilerplate injected by the `dd:mcp-security-review` skill
  ("Review this change for security vulnerabilities...")
- Code-review and skill-body injections ("Provide a code review...", "Base directory for
  this skill:...")
- Context injected by hooks/skills (`## Context -` prefix)
- Task-workflow messages: user pasting tool/test output back ("review the test run output
  and fix...")
- Subagent dispatch messages from workflow orchestration

## Adding a new filter

When a noise format slips through, add its signature to `NOISE_PATTERNS` in
`scripts/analyze_conversations.py` rather than filtering by hand at report time.
