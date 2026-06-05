# claude-skills

A collection of [Claude Code](https://claude.com/claude-code) **Skills** — self-contained
directories that extend Claude's capabilities with specialized, repeatable workflows.

Each skill is defined by a `SKILL.md` (the instructions Claude follows once the skill
activates) plus any supporting scripts. The `SKILL.md` is the canonical spec for what a
skill does; this README is the entry point for humans browsing or installing the repo.

## Skills

| Skill | What it does |
|-------|--------------|
| [`efficiency-audit`](efficiency-audit/) | Analyzes your recent Claude Code conversation transcripts to surface recurring friction (repeated corrections, re-explained context, failing hooks), then proposes and applies concrete fixes to `CLAUDE.md`, memory, and settings. |

## Installing a skill

Skills are discovered by Claude Code under `~/.claude/skills/`. To install one from this
repo, copy its directory there:

```bash
cp -R <skill> ~/.claude/skills/
```

A skill activates automatically when your request matches the triggers in its `SKILL.md`
frontmatter `description`. See the skill's own README (linked in the table above) for its
triggers, usage, and any flags.

> Note: a `SKILL.md` references its own scripts by their **installed** path
> (`~/.claude/skills/<name>/scripts/...`). When developing in this repo, run scripts from
> the repo path instead.

## Development

No build system or third-party dependencies — skills are Markdown plus scripts. Scripts
that ship tests use the Python standard-library `unittest`, run from the script's
directory. Per-skill setup, CLI usage, and test commands live in each skill's README.

## Contributing a new skill

1. Create a top-level directory named in kebab-case (matches the skill's `name`).
2. Add a `SKILL.md` with frontmatter (`name`, `description`) and a body written as a
   procedure for the agent to follow. Front-load concrete trigger phrases in
   `description` — it's the only text read when deciding whether to activate.
3. Put supporting code under `<skill>/scripts/`; reference it from `SKILL.md` by its
   installed path.
4. Add the skill to the table above.

See [`CLAUDE.md`](CLAUDE.md) for the conventions Claude follows when working in this repo.
