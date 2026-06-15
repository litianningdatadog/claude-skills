# Plugin Marketplace Conversion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert `claude-marketplace` from a manual-copy skills repo into a valid Claude Code plugin marketplace with one independently installable plugin per skill.

**Architecture:** Add `.claude-plugin/marketplace.json` at the root and `.claude-plugin/plugin.json` inside each skill directory. Move each `SKILL.md` from the skill root into `skills/<name>/SKILL.md` (required by the plugin spec). Update all hardcoded `~/.claude/skills/<name>/` path references in SKILL.md bodies and reference files to use a dynamic plugin-root resolver.

**Tech Stack:** JSON (manifests), Markdown (SKILL.md), Bash (path resolver), `claude plugin validate` (validation)

**Spec:** `docs/superpowers/specs/2026-06-15-plugin-marketplace-design.md`

---

### Task 1: Create the marketplace manifest

**Files:**
- Create: `.claude-plugin/marketplace.json`

- [ ] **Step 1: Create the directory and file**

```bash
mkdir -p .claude-plugin
```

Create `.claude-plugin/marketplace.json` with this exact content:

```json
{
  "name": "claude-marketplace",
  "description": "Claude Code skills for workflow automation, hook repair, and quick notes.",
  "owner": { "name": "Tianning Li" },
  "plugins": [
    {
      "name": "efficiency-audit",
      "source": "./efficiency-audit",
      "description": "Analyzes recent Claude Code transcripts to surface recurring inefficiencies."
    },
    {
      "name": "hook-doctor",
      "source": "./hook-doctor",
      "description": "Inspects and repairs installed plugin hook configurations."
    },
    {
      "name": "quicknotes",
      "source": "./quicknotes",
      "description": "Low-friction quick-note capture and management for Claude Code."
    }
  ]
}
```

- [ ] **Step 2: Validate the JSON is well-formed**

```bash
python3 -c "import json; json.load(open('.claude-plugin/marketplace.json')); print('valid')"
```
Expected: `valid`

- [ ] **Step 3: Commit**

```bash
git add .claude-plugin/marketplace.json
git commit -m "feat: add marketplace.json catalog"
```

---

### Task 2: Create the efficiency-audit plugin manifest

**Files:**
- Create: `efficiency-audit/.claude-plugin/plugin.json`

- [ ] **Step 1: Create the file**

```bash
mkdir -p efficiency-audit/.claude-plugin
```

Create `efficiency-audit/.claude-plugin/plugin.json`:

```json
{
  "name": "efficiency-audit",
  "description": "Analyzes recent Claude Code transcripts to surface recurring inefficiencies."
}
```

- [ ] **Step 2: Validate**

```bash
python3 -c "import json; json.load(open('efficiency-audit/.claude-plugin/plugin.json')); print('valid')"
```
Expected: `valid`

- [ ] **Step 3: Commit**

```bash
git add efficiency-audit/.claude-plugin/plugin.json
git commit -m "feat(efficiency-audit): add plugin.json manifest"
```

---

### Task 3: Relocate and update efficiency-audit SKILL.md

**Files:**
- Move: `efficiency-audit/SKILL.md` → `efficiency-audit/skills/efficiency-audit/SKILL.md`
- Modify: `efficiency-audit/skills/efficiency-audit/SKILL.md` (path references)

The SKILL.md references scripts and reference files via `~/.claude/skills/efficiency-audit/...`. After plugin installation these live at a versioned cache path. The fix: add a path resolver preamble to Phase 1, then use `${PLUGIN_ROOT}` throughout.

- [ ] **Step 1: Create the skills directory and move the file**

```bash
mkdir -p efficiency-audit/skills/efficiency-audit
git mv efficiency-audit/SKILL.md efficiency-audit/skills/efficiency-audit/SKILL.md
```

- [ ] **Step 2: Add the path resolver note to Phase 1**

In `efficiency-audit/skills/efficiency-audit/SKILL.md`, find the Phase 1 section header:

```
### Phase 1: Analyze
```

Immediately after the line `**Session setup check — terminal title:** Read \`references/terminal-title-check.md\`` block (i.e., before the first bash code block), add this resolver definition:

```markdown
**Path resolver — run this first to set `PLUGIN_ROOT`:**

```bash
PLUGIN_ROOT=$(ls -dt ~/.claude/plugins/cache/claude-marketplace/efficiency-audit/*/ 2>/dev/null | head -1)
```

Use `${PLUGIN_ROOT}` in all subsequent commands to reference scripts and reference files.
```

- [ ] **Step 3: Update the analyze_conversations script block**

Find:
```bash
python3 ~/.claude/skills/efficiency-audit/scripts/analyze_conversations.py \
  --days 30 \
  --project "$(basename "$PWD")" \
  --output json \
  2>/dev/null
```

Replace with:
```bash
python3 "${PLUGIN_ROOT}/scripts/analyze_conversations.py" \
  --days 30 \
  --project "$(basename "$PWD")" \
  --output json \
  2>/dev/null
```

- [ ] **Step 4: Update the score_efficiency script block**

Find:
```bash
MEMORY_MD=$(python3 ~/.claude/skills/efficiency-audit/scripts/resolve_memory_path.py 2>/dev/null)
python3 ~/.claude/skills/efficiency-audit/scripts/score_efficiency.py \
  .claude/CLAUDE.md ~/.claude/CLAUDE.md "$MEMORY_MD" \
  2>/dev/null
```

Replace with:
```bash
MEMORY_MD=$(python3 "${PLUGIN_ROOT}/scripts/resolve_memory_path.py" 2>/dev/null)
python3 "${PLUGIN_ROOT}/scripts/score_efficiency.py" \
  .claude/CLAUDE.md ~/.claude/CLAUDE.md "$MEMORY_MD" \
  2>/dev/null
```

- [ ] **Step 5: Update all prose "(installed at ...)" reference paths**

There are seven of these. Do a global find-and-replace of `~/.claude/skills/efficiency-audit/` → `${PLUGIN_ROOT}/` throughout the file. After replacement, verify all seven reference mentions read like:

- `(installed at \`${PLUGIN_ROOT}/references/terminal-title-check.md\`)`
- `(installed at \`${PLUGIN_ROOT}/references/category-guide.md\`)`
- `(installed at \`${PLUGIN_ROOT}/references/claude-md-routing.md\`)`
- `(installed at \`${PLUGIN_ROOT}/references/karpathy-guardrails.md\`)`
- `(installed at \`${PLUGIN_ROOT}/references/governance.md\`)`
- `(installed at \`${PLUGIN_ROOT}/references/noise-filters.md\`)`
- `(installed at \`${PLUGIN_ROOT}/references/recipe-book.md\`)`

Verify with:
```bash
grep -n "claude/skills" efficiency-audit/skills/efficiency-audit/SKILL.md
```
Expected: no output (zero remaining old-style paths).

- [ ] **Step 6: Commit**

```bash
git add efficiency-audit/skills/efficiency-audit/SKILL.md
git commit -m "feat(efficiency-audit): move SKILL.md into skills/ and update path references"
```

---

### Task 4: Update efficiency-audit reference files

**Files:**
- Modify: `efficiency-audit/references/category-guide.md`
- Modify: `efficiency-audit/references/terminal-title-check.md`

These files contain detection shell commands that check for plugins at `~/.claude/skills/...` — after migration that path won't exist.

- [ ] **Step 1: Update the hook-doctor detection command in category-guide.md**

Find (in `efficiency-audit/references/category-guide.md`, the `hook_errors` section):

```bash
ls ~/.claude/skills/hook-doctor/SKILL.md 2>/dev/null && echo "installed" || echo "not_installed"
```

Replace with:
```bash
ls ~/.claude/plugins/cache/claude-marketplace/hook-doctor/*/skills/hook-doctor/SKILL.md 2>/dev/null | grep -q . && echo "installed" || echo "not_installed"
```

- [ ] **Step 2: Update the hook-doctor install instruction in category-guide.md**

Find:
```
> the [claude-marketplace repo](https://github.com/litianningdatadog/claude-marketplace) by copying
> `hook-doctor/` to `~/.claude/skills/`, then re-run `/efficiency-audit`."
```

Replace with:
```
> the [claude-marketplace repo](https://github.com/litianningdatadog/claude-marketplace): run
> `/plugin install hook-doctor@claude-marketplace`, then re-run `/efficiency-audit`."
```

- [ ] **Step 3: Update the terminal-title detection command in terminal-title-check.md**

Find (in the `## Detection (Phase 1)` section):

```bash
# Is the skill installed?
ls ~/.claude/skills/terminal-title/scripts/set_title.sh 2>/dev/null && echo "installed" || echo "not_installed"
```

Replace with:
```bash
# Is the skill installed? (checks both legacy skills path and plugin cache)
if ls ~/.claude/skills/terminal-title/scripts/set_title.sh 2>/dev/null \
   || ls ~/.claude/plugins/cache/*/terminal-title/*/scripts/set_title.sh 2>/dev/null | grep -q .; then
  echo "installed"
else
  echo "not_installed"
fi
```

- [ ] **Step 4: Verify no stale `~/.claude/skills/` references remain in reference files**

```bash
grep -rn "claude/skills" efficiency-audit/references/
```
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add efficiency-audit/references/category-guide.md efficiency-audit/references/terminal-title-check.md
git commit -m "fix(efficiency-audit): update plugin detection commands for marketplace install paths"
```

---

### Task 5: Create the hook-doctor plugin manifest

**Files:**
- Create: `hook-doctor/.claude-plugin/plugin.json`

- [ ] **Step 1: Create the file**

```bash
mkdir -p hook-doctor/.claude-plugin
```

Create `hook-doctor/.claude-plugin/plugin.json`:

```json
{
  "name": "hook-doctor",
  "description": "Inspects and repairs installed plugin hook configurations."
}
```

- [ ] **Step 2: Validate**

```bash
python3 -c "import json; json.load(open('hook-doctor/.claude-plugin/plugin.json')); print('valid')"
```
Expected: `valid`

- [ ] **Step 3: Commit**

```bash
git add hook-doctor/.claude-plugin/plugin.json
git commit -m "feat(hook-doctor): add plugin.json manifest"
```

---

### Task 6: Relocate and update hook-doctor SKILL.md

**Files:**
- Move: `hook-doctor/SKILL.md` → `hook-doctor/skills/hook-doctor/SKILL.md`
- Modify: `hook-doctor/skills/hook-doctor/SKILL.md` (two script path references)

- [ ] **Step 1: Move the file**

```bash
mkdir -p hook-doctor/skills/hook-doctor
git mv hook-doctor/SKILL.md hook-doctor/skills/hook-doctor/SKILL.md
```

- [ ] **Step 2: Add path resolver and update the scan command**

In `hook-doctor/skills/hook-doctor/SKILL.md`, find the `### 1. Scan` section:

```markdown
### 1. Scan

```bash
python3 ~/.claude/skills/hook-doctor/scripts/inspect_hooks.py 2>/dev/null
```
```

Replace the bash block with:

```bash
PLUGIN_ROOT=$(ls -dt ~/.claude/plugins/cache/claude-marketplace/hook-doctor/*/ 2>/dev/null | head -1)
python3 "${PLUGIN_ROOT}/scripts/inspect_hooks.py" 2>/dev/null
```

- [ ] **Step 3: Update the apply command in step 3**

Find (in the `### 3. Apply` section):

```bash
python3 ~/.claude/skills/hook-doctor/scripts/inspect_hooks.py --apply 2>/dev/null
```

Replace with:

```bash
PLUGIN_ROOT=$(ls -dt ~/.claude/plugins/cache/claude-marketplace/hook-doctor/*/ 2>/dev/null | head -1)
python3 "${PLUGIN_ROOT}/scripts/inspect_hooks.py" --apply 2>/dev/null
```

Each SKILL.md code block runs in its own shell process so `PLUGIN_ROOT` from the scan block is not available here. The resolver must be repeated unconditionally.

- [ ] **Step 4: Verify no stale paths remain**

```bash
grep -n "claude/skills" hook-doctor/skills/hook-doctor/SKILL.md
```
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add hook-doctor/skills/hook-doctor/SKILL.md
git commit -m "feat(hook-doctor): move SKILL.md into skills/ and update path references"
```

---

### Task 7: Create the quicknotes plugin manifest

**Files:**
- Create: `quicknotes/.claude-plugin/plugin.json`

- [ ] **Step 1: Create the file**

```bash
mkdir -p quicknotes/.claude-plugin
```

Create `quicknotes/.claude-plugin/plugin.json`:

```json
{
  "name": "quicknotes",
  "description": "Low-friction quick-note capture and management for Claude Code."
}
```

- [ ] **Step 2: Validate**

```bash
python3 -c "import json; json.load(open('quicknotes/.claude-plugin/plugin.json')); print('valid')"
```
Expected: `valid`

- [ ] **Step 3: Commit**

```bash
git add quicknotes/.claude-plugin/plugin.json
git commit -m "feat(quicknotes): add plugin.json manifest"
```

---

### Task 8: Relocate and update quicknotes SKILL.md

**Files:**
- Move: `quicknotes/SKILL.md` → `quicknotes/skills/quicknotes/SKILL.md`
- Modify: `quicknotes/skills/quicknotes/SKILL.md` (two bash path references + session hook template)

- [ ] **Step 1: Move the file**

```bash
mkdir -p quicknotes/skills/quicknotes
git mv quicknotes/SKILL.md quicknotes/skills/quicknotes/SKILL.md
```

- [ ] **Step 2: Add path resolver and update the capture command**

Find the capture bash block:

```bash
python3 ~/.claude/skills/quicknotes/scripts/qn.py <the note text> [#tag …] [--tag T]
```

Replace with:

```bash
PLUGIN_ROOT=$(ls -dt ~/.claude/plugins/cache/claude-marketplace/quicknotes/*/ 2>/dev/null | head -1)
python3 "${PLUGIN_ROOT}/scripts/qn.py" <the note text> [#tag …] [--tag T]
```

- [ ] **Step 3: Update the manage section inline reference**

Find the line:

```
(`qn …` above = `python3 ~/.claude/skills/quicknotes/scripts/qn.py …`.)
```

Replace with:

```
(`qn …` above = `python3 "${PLUGIN_ROOT}/scripts/qn.py" …`, where `PLUGIN_ROOT` is resolved via the preamble above.)
```

- [ ] **Step 4: Update the SessionStart hook template**

The session hook JSON snippet currently hardcodes the old skills path. Find:

```json
{ "type": "command", "command": "python3 \"${HOME}/.claude/skills/quicknotes/scripts/session_reminder.py\"" }
```

Replace with:

```json
{ "type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/scripts/session_reminder.py" }
```

Note: `${CLAUDE_PLUGIN_ROOT}` is expanded by the Claude Code hook runtime (unlike SKILL.md prose), so this correctly resolves to the installed plugin path at hook execution time.

- [ ] **Step 5: Verify no stale paths remain**

```bash
grep -n "claude/skills" quicknotes/skills/quicknotes/SKILL.md
```
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add quicknotes/skills/quicknotes/SKILL.md
git commit -m "feat(quicknotes): move SKILL.md into skills/ and update path references"
```

---

### Task 9: Update README.md

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace the title and intro**

Change the H1 from any description of the old install model to reflect the marketplace:

The `## Installing a skill` section currently reads:

```markdown
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
```

Replace that entire section with:

```markdown
## Installing plugins

This repo is a Claude Code plugin marketplace. Add it once, then install skills à la carte:

```bash
# Add the marketplace (once per machine)
/plugin marketplace add litianningdatadog/claude-marketplace

# Install skills
/plugin install efficiency-audit@claude-marketplace
/plugin install hook-doctor@claude-marketplace
/plugin install quicknotes@claude-marketplace
```

Plugins auto-update when you run `/plugin marketplace update`. Each skill activates
automatically when your request matches the triggers in its `SKILL.md` description.
```

- [ ] **Step 2: Update the Contributing section**

The `## Contributing a new skill` section references the old structure. Update step 2 from:

```markdown
2. Add a `SKILL.md` with frontmatter (`name`, `description`) and a body written as a
   procedure for the agent to follow. Front-load concrete trigger phrases in
   `description` — it's the only text read when deciding whether to activate.
3. Put supporting code under `<skill>/scripts/`; reference it from `SKILL.md` by its
   installed path.
4. Add the skill to the table above.
```

To:

```markdown
2. Add a `.claude-plugin/plugin.json` with `name` and `description`.
3. Add `skills/<name>/SKILL.md` as the agent procedure. Front-load trigger phrases in
   the frontmatter `description` — it's the only text read when deciding whether to activate.
   Reference supporting scripts via `${PLUGIN_ROOT}/scripts/...` (resolved dynamically at runtime).
4. Put supporting code under `<skill>/scripts/` (stays at the plugin root).
5. Add the plugin entry to `.claude-plugin/marketplace.json` and the skill to the table above.
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: update README for plugin marketplace install model"
```

---

### Task 10: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the "Skill anatomy" section**

Replace the entire `## Skill anatomy` section:

```markdown
## Plugin anatomy

A plugin lives in its own top-level directory and consists of:

- `.claude-plugin/plugin.json` — required. Plugin manifest with `name` and `description`.
- `skills/<name>/SKILL.md` — required. YAML frontmatter with two fields:
  - `name`: the skill's invocation slug (kebab-case, matches the directory name).
  - `description`: load-bearing. This is the **only** text the agent reads to decide
    whether to activate the skill, so it must pack in concrete trigger phrases and use
    cases. The Markdown body below the frontmatter is loaded *only after* activation and
    becomes the agent's operating instructions.
- `scripts/` — optional supporting code (e.g. Python) that the `SKILL.md` body invokes.
  Reference scripts via a dynamic plugin-root resolver (not a hardcoded path), since
  plugins are installed to a versioned cache at
  `~/.claude/plugins/cache/claude-marketplace/<name>/<version>/`:

  ```bash
  PLUGIN_ROOT=$(ls -dt ~/.claude/plugins/cache/claude-marketplace/<name>/*/ 2>/dev/null | head -1)
  python3 "${PLUGIN_ROOT}/scripts/<script>.py"
  ```

  In hook config (not SKILL.md prose), use `${CLAUDE_PLUGIN_ROOT}` instead — it is
  expanded by the hook runtime to the correct installed path.
```

- [ ] **Step 2: Update the development run example**

Find:

```markdown
Note the body of `SKILL.md` invokes it from the *installed* path
(`~/.claude/skills/...`), so test against the repo path while developing.
```

Replace with:

```markdown
Note the body of `SKILL.md` invokes it via the `PLUGIN_ROOT` resolver above (installed
path). When developing, run scripts directly from the repo path instead.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for plugin anatomy and resolver pattern"
```

---

### Task 11: Validate the marketplace

- [ ] **Step 1: Validate marketplace manifest**

```bash
claude plugin validate .
```

Expected output: no errors. Warnings about missing descriptions are acceptable; errors are not.

If `claude` CLI is not on PATH, run from within Claude Code:
```
/plugin validate .
```

- [ ] **Step 2: Validate each plugin individually**

```bash
claude plugin validate ./efficiency-audit
claude plugin validate ./hook-doctor
claude plugin validate ./quicknotes
```

Expected: no errors for any plugin.

- [ ] **Step 3: Smoke-test by adding the marketplace locally**

```
/plugin marketplace add ./
/plugin install efficiency-audit@claude-marketplace
```

Verify the skill loads (it should appear in `/skills` list after install).

- [ ] **Step 4: Commit if clean, or fix and re-validate**

If validation passes with no errors:
```bash
git add -A
git status  # should be clean; if not, stage any last-minute fixes
git commit -m "chore: post-validation clean-up" --allow-empty-if-no-changes 2>/dev/null || true
```

---

### Task 12: Pre-PR verification gate (required — do not skip)

> These steps are the only check that catches stale `~/.claude/skills/` references remaining in prose after `claude plugin validate` passes (the validator checks manifest structure, not file content). Complete all steps before opening the PR.

- [ ] **Step 1: Confirm nothing stale remains**

```bash
grep -rn "claude/skills" \
  efficiency-audit/skills/ \
  hook-doctor/skills/ \
  quicknotes/skills/ \
  efficiency-audit/references/ \
  README.md CLAUDE.md
```
Expected: no output.

- [ ] **Step 2: Confirm all plugin manifests exist**

```bash
ls .claude-plugin/marketplace.json \
   efficiency-audit/.claude-plugin/plugin.json \
   hook-doctor/.claude-plugin/plugin.json \
   quicknotes/.claude-plugin/plugin.json
```
Expected: all four paths listed without error.

- [ ] **Step 3: Confirm SKILL.md files are at new locations**

```bash
ls efficiency-audit/skills/efficiency-audit/SKILL.md \
   hook-doctor/skills/hook-doctor/SKILL.md \
   quicknotes/skills/quicknotes/SKILL.md
```
Expected: all three paths listed without error.

- [ ] **Step 4: Confirm old SKILL.md locations are gone**

```bash
ls efficiency-audit/SKILL.md hook-doctor/SKILL.md quicknotes/SKILL.md 2>&1
```
Expected: all three return "No such file or directory".

- [ ] **Step 5: Push and open PR**

```bash
git push
```

Then open a PR with title: `feat: convert repo to Claude Code plugin marketplace`
