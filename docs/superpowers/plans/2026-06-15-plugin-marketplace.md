# Plugin Marketplace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the `claude-skills` repo into a public plugin marketplace with a CLI installer, GitHub Pages registry, and auto-generated `registry.json` via CI.

**Architecture:** A Python script (`scripts/generate_registry.py`) scans top-level skill directories and emits `registry.json`. A GitHub Actions workflow runs this on every push to `main`, commits the result, then deploys `registry.json` + `install.sh` + `claude-skills` + `index.html` to GitHub Pages. Users bootstrap with a `curl | bash` one-liner that installs the `claude-skills` shell script; the shell script delegates JSON manipulation to inline Python 3 (always available on Claude Code machines).

**Tech Stack:** Python 3 stdlib (json, os, tarfile, urllib.request, datetime), Bash, GitHub Actions, GitHub Pages.

**Spec:** `docs/superpowers/specs/2026-06-15-plugin-marketplace-design.md`

---

## File Map

| File | Status | Responsibility |
|------|--------|----------------|
| `scripts/generate_registry.py` | Create | Parse all SKILL.md frontmatters → emit `registry.json` |
| `scripts/test_generate_registry.py` | Create | unittest suite for the generator |
| `registry.json` | Create (generated) | Machine-readable skill index, served via Pages |
| `.github/workflows/deploy-registry.yml` | Create | Generate + commit registry, deploy Pages on push to main |
| `claude-skills` | Create | Shell script CLI: add/list/install/update/remove/sources |
| `install.sh` | Create | Bootstrap: download CLI, register official source |
| `index.html` | Create | Static HTML catalog that fetches registry.json client-side |
| `README.md` | Modify | Add marketplace install section |

---

## Task 1: Registry Generator — Tests

**Files:**
- Create: `scripts/test_generate_registry.py`

- [ ] **Step 1: Create the test file**

```python
# scripts/test_generate_registry.py
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from generate_registry import parse_frontmatter, discover_skills


class TestParseFrontmatter(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _write(self, content):
        path = os.path.join(self.tmpdir, 'SKILL.md')
        with open(path, 'w') as f:
            f.write(content)
        return path

    def test_valid_frontmatter(self):
        path = self._write('---\nname: my-skill\ndescription: "Does stuff"\n---\n\n# Body\n')
        result = parse_frontmatter(path)
        self.assertEqual(result['name'], 'my-skill')
        self.assertEqual(result['description'], 'Does stuff')

    def test_no_frontmatter_returns_none(self):
        path = self._write('# Just markdown\n')
        self.assertIsNone(parse_frontmatter(path))

    def test_unclosed_frontmatter_returns_none(self):
        path = self._write('---\nname: broken\n')
        self.assertIsNone(parse_frontmatter(path))

    def test_description_without_quotes(self):
        path = self._write('---\nname: my-skill\ndescription: Plain text\n---\n')
        result = parse_frontmatter(path)
        self.assertEqual(result['description'], 'Plain text')


class TestDiscoverSkills(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _make_skill(self, dir_name, skill_name=None, description='Test skill', has_scripts=False):
        if skill_name is None:
            skill_name = dir_name
        skill_dir = os.path.join(self.tmpdir, dir_name)
        os.makedirs(skill_dir)
        with open(os.path.join(skill_dir, 'SKILL.md'), 'w') as f:
            f.write(f'---\nname: {skill_name}\ndescription: "{description}"\n---\n\n# Body\n')
        if has_scripts:
            os.makedirs(os.path.join(skill_dir, 'scripts'))
        return skill_dir

    def test_finds_valid_skill(self):
        self._make_skill('my-skill')
        skills = discover_skills(self.tmpdir)
        self.assertEqual(len(skills), 1)
        self.assertEqual(skills[0]['name'], 'my-skill')

    def test_skill_fields(self):
        self._make_skill('my-skill', description='Helpful skill', has_scripts=True)
        skills = discover_skills(self.tmpdir)
        s = skills[0]
        self.assertEqual(s['name'], 'my-skill')
        self.assertEqual(s['path'], 'my-skill')
        self.assertEqual(s['description'], 'Helpful skill')
        self.assertIsNone(s['version'])
        self.assertTrue(s['has_scripts'])

    def test_has_scripts_false_when_no_scripts_dir(self):
        self._make_skill('my-skill', has_scripts=False)
        skills = discover_skills(self.tmpdir)
        self.assertFalse(skills[0]['has_scripts'])

    def test_excludes_name_mismatch(self):
        # dir is "my-skill" but SKILL.md name is "other"
        self._make_skill('my-skill', skill_name='other')
        skills = discover_skills(self.tmpdir)
        self.assertEqual(len(skills), 0)

    def test_excludes_non_directories(self):
        # A SKILL.md at repo root level (not in a subdir) — shouldn't be found
        # discover_skills only looks at subdirs, so a root-level SKILL.md is never read
        with open(os.path.join(self.tmpdir, 'SKILL.md'), 'w') as f:
            f.write('---\nname: root\ndescription: "Root"\n---\n')
        skills = discover_skills(self.tmpdir)
        self.assertEqual(len(skills), 0)

    def test_excludes_dirs_without_skill_md(self):
        os.makedirs(os.path.join(self.tmpdir, 'not-a-skill'))
        skills = discover_skills(self.tmpdir)
        self.assertEqual(len(skills), 0)

    def test_results_sorted_by_name(self):
        self._make_skill('zebra')
        self._make_skill('apple')
        skills = discover_skills(self.tmpdir)
        self.assertEqual([s['name'] for s in skills], ['apple', 'zebra'])

    def test_multiple_skills(self):
        self._make_skill('skill-a')
        self._make_skill('skill-b')
        skills = discover_skills(self.tmpdir)
        self.assertEqual(len(skills), 2)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail (ImportError expected)**

```bash
cd scripts && python3 -m unittest test_generate_registry -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'parse_frontmatter' from 'generate_registry'` (file doesn't exist yet)

---

## Task 2: Registry Generator — Implementation

**Files:**
- Create: `scripts/generate_registry.py`
- Create (generated): `registry.json`

- [ ] **Step 1: Create the generator script**

```python
#!/usr/bin/env python3
"""Scan top-level skill directories and generate registry.json."""

import json
import os
from datetime import datetime, timezone


def parse_frontmatter(skill_md_path):
    """Return dict of YAML frontmatter fields, or None if not found."""
    with open(skill_md_path) as f:
        content = f.read()
    if not content.startswith('---'):
        return None
    end = content.find('\n---', 3)
    if end == -1:
        return None
    data = {}
    for line in content[3:end].strip().splitlines():
        if ':' in line:
            key, _, value = line.partition(':')
            data[key.strip()] = value.strip().strip('"')
    return data


def discover_skills(repo_root):
    """Return sorted list of skill dicts from top-level directories."""
    skills = []
    for entry in sorted(os.listdir(repo_root)):
        skill_dir = os.path.join(repo_root, entry)
        if not os.path.isdir(skill_dir):
            continue
        skill_md = os.path.join(skill_dir, 'SKILL.md')
        if not os.path.isfile(skill_md):
            continue
        fm = parse_frontmatter(skill_md)
        if fm is None or fm.get('name') != entry:
            continue
        skills.append({
            'name': entry,
            'description': fm.get('description', ''),
            'path': entry,
            'version': None,
            'has_scripts': os.path.isdir(os.path.join(skill_dir, 'scripts')),
        })
    return skills


def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    source_url = 'https://github.com/litianningdatadog/claude-skills'
    output_path = os.path.join(repo_root, 'registry.json')

    skills = discover_skills(repo_root)

    # Preserve updated_at if skills list is unchanged (avoids spurious CI commits)
    preserved_at = None
    if os.path.isfile(output_path):
        try:
            existing = json.load(open(output_path))
            if existing.get('skills') == skills:
                preserved_at = existing.get('updated_at')
        except (json.JSONDecodeError, KeyError):
            pass

    registry = {
        'schema_version': 1,
        'updated_at': preserved_at or datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'source': source_url,
        'skills': skills,
    }

    with open(output_path, 'w') as f:
        json.dump(registry, f, indent=2)
        f.write('\n')

    print(f"Generated {output_path} with {len(skills)} skills")


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Run the tests — all must pass**

```bash
cd scripts && python3 -m unittest test_generate_registry -v
```

Expected: all tests pass, `OK` at the end.

- [ ] **Step 3: Run the script against the real repo to generate registry.json**

```bash
python3 scripts/generate_registry.py
```

Expected output: `Generated .../registry.json with 3 skills`

- [ ] **Step 4: Verify registry.json content**

```bash
python3 -c "import json; d=json.load(open('registry.json')); print(json.dumps(d, indent=2))"
```

Expected: JSON with `schema_version: 1`, `skills` array containing `efficiency-audit`, `hook-doctor`, `quicknotes`.

- [ ] **Step 5: Commit**

```bash
git add scripts/generate_registry.py scripts/test_generate_registry.py registry.json
git commit -m "feat: add registry generator and initial registry.json"
```

---

## Task 3: GitHub Actions CI/CD Workflow

**Files:**
- Create: `.github/workflows/deploy-registry.yml`

- [ ] **Step 1: Create the workflow directory**

```bash
mkdir -p .github/workflows
```

- [ ] **Step 2: Write the workflow file**

```yaml
# .github/workflows/deploy-registry.yml
name: Deploy Registry

on:
  push:
    branches: [main]

permissions:
  contents: write
  pages: write
  id-token: write

jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Generate registry.json
        run: python3 scripts/generate_registry.py

      - name: Commit updated registry.json if changed
        run: |
          if git diff --quiet registry.json; then
            echo "registry.json unchanged, skipping commit"
          else
            git config user.name "github-actions[bot]"
            git config user.email "github-actions[bot]@users.noreply.github.com"
            git add registry.json
            git commit -m "chore: regenerate registry.json [skip ci]"
            git push
          fi

      - name: Upload registry.json artifact
        uses: actions/upload-artifact@v4
        with:
          name: registry-json
          path: registry.json

  deploy-pages:
    needs: generate
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4
        with:
          ref: main

      - name: Download registry.json from generate job
        uses: actions/download-artifact@v4
        with:
          name: registry-json

      - name: Setup Pages
        uses: actions/configure-pages@v5

      - name: Build Pages artifact
        run: |
          mkdir -p _site
          cp registry.json _site/
          cp install.sh _site/
          cp claude-skills _site/
          cp index.html _site/

      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: _site

      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

- [ ] **Step 3: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy-registry.yml'))" 2>&1
```

Note: requires `pyyaml` — if not installed, skip and rely on GitHub's syntax checker on push. Alternatively:

```bash
python3 -c "
import json, subprocess
result = subprocess.run(['python3', '-c', 'import yaml'], capture_output=True)
print('yaml available' if result.returncode == 0 else 'skip yaml check')
"
```

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/deploy-registry.yml
git commit -m "feat: add GitHub Actions workflow for registry generation and Pages deploy"
```

---

## Task 4: `claude-skills` CLI — Core + Sources Commands

**Files:**
- Create: `claude-skills` (shell script at repo root)

- [ ] **Step 1: Create the shell script with core structure, `add`, and `sources` commands**

```bash
#!/usr/bin/env bash
# claude-skills — plugin marketplace CLI for Claude Code
# Usage: claude-skills <command> [args]

set -euo pipefail

MARKETPLACE_DIR="${HOME}/.claude/marketplace"
SKILLS_DIR="${HOME}/.claude/skills"
SOURCES_FILE="${MARKETPLACE_DIR}/sources.json"
INSTALLED_FILE="${MARKETPLACE_DIR}/installed.json"
TMP_DIR="${MARKETPLACE_DIR}/tmp"
SUPPORTED_SCHEMA_VERSION=1

# ── Helpers ───────────────────────────────────────────────────────────────────

die() { echo "error: $*" >&2; exit 1; }

ensure_dirs() {
    mkdir -p "$MARKETPLACE_DIR" "$SKILLS_DIR" "$TMP_DIR"
}

init_sources() {
    [ -f "$SOURCES_FILE" ] || echo '{"sources":[]}' > "$SOURCES_FILE"
}

init_installed() {
    [ -f "$INSTALLED_FILE" ] || echo '{"installed":[]}' > "$INSTALLED_FILE"
}

# ── cmd: sources ──────────────────────────────────────────────────────────────

cmd_sources() {
    init_sources
    python3 - "$SOURCES_FILE" << 'PYEOF'
import json, sys
data = json.load(open(sys.argv[1]))
sources = data.get('sources', [])
if not sources:
    print('No sources registered.')
else:
    for s in sources:
        print(f"{s['name']}  {s['registry_url']}")
PYEOF
}

# ── cmd: add ─────────────────────────────────────────────────────────────────

cmd_add() {
    local url="${1:-}"
    [ -n "$url" ] || die "Usage: claude-skills add <registry-url>"
    ensure_dirs
    init_sources

    # Fetch registry to validate schema_version and get repo_url
    local tmpfile="${TMP_DIR}/registry_validate.json"
    curl -fsSL "$url" -o "$tmpfile" || die "Failed to fetch registry from ${url}"

    python3 - "$SOURCES_FILE" "$tmpfile" "$url" "$SUPPORTED_SCHEMA_VERSION" << 'PYEOF'
import json, sys
from datetime import datetime, timezone

sources_file, reg_file, url, supported_ver = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
reg = json.load(open(reg_file))
schema_ver = reg.get('schema_version', 0)
if schema_ver != supported_ver:
    print(f"error: unsupported registry schema_version {schema_ver} (expected {supported_ver})", file=sys.stderr)
    sys.exit(1)

repo_url = reg.get('source', '')
# Derive friendly name from domain: litianningdatadog.github.io → litianningdatadog
from urllib.parse import urlparse
host = urlparse(url).netloc
name = host.split('.')[0] if '.' in host else host

data = json.load(open(sources_file))
for s in data['sources']:
    if s['registry_url'] == url:
        print(f"Source '{name}' already registered.")
        sys.exit(0)

data['sources'].append({
    'name': name,
    'registry_url': url,
    'repo_url': repo_url,
    'added_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
})
json.dump(data, open(sources_file, 'w'), indent=2)
print(f"Added source: {name}  ({url})")
PYEOF
    rm -f "$tmpfile"
}

# ── Dispatch ─────────────────────────────────────────────────────────────────

ensure_dirs
init_sources
init_installed

case "${1:-}" in
    add)     cmd_add "${2:-}" ;;
    sources) cmd_sources ;;
    *)
        echo "claude-skills — plugin marketplace CLI for Claude Code"
        echo ""
        echo "Usage:"
        echo "  claude-skills add <registry-url>    Register a marketplace source"
        echo "  claude-skills list                  List available skills"
        echo "  claude-skills install <name>        Install a skill"
        echo "  claude-skills update                Update all CLI-installed skills"
        echo "  claude-skills remove <name>         Remove an installed skill"
        echo "  claude-skills sources               List registered sources"
        ;;
esac
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x claude-skills
```

- [ ] **Step 3: Smoke-test: no args shows usage**

```bash
./claude-skills
```

Expected: prints the usage block with all 6 commands listed.

- [ ] **Step 4: Smoke-test: `sources` with no sources registered**

```bash
./claude-skills sources
```

Expected: `No sources registered.`

- [ ] **Step 5: Commit**

```bash
git add claude-skills
git commit -m "feat: add claude-skills CLI with add/sources commands"
```

---

## Task 5: `claude-skills` CLI — `list`, `install`, `remove` Commands

**Files:**
- Modify: `claude-skills` (add three more commands before the dispatch section)

`★ Insight ─────────────────────────────────────`
The install command downloads a full repo tarball (~few MB) and extracts just one directory. Python's `tarfile` module handles this without any `git` dependency. The key is stripping the `<repo>-main/` prefix that GitHub prepends to all tarball paths.
`─────────────────────────────────────────────────`

- [ ] **Step 1: Add `cmd_list` function** — insert before the `# ── Dispatch` section:

```bash
# ── cmd: list ────────────────────────────────────────────────────────────────

cmd_list() {
    init_sources
    python3 - "$SOURCES_FILE" << 'PYEOF'
import json, sys, urllib.request
sources_file = sys.argv[1]
data = json.load(open(sources_file))
sources = data.get('sources', [])
if not sources:
    print("No sources registered. Run: claude-skills add <url>")
    sys.exit(0)

all_skills = []
for source in sources:
    try:
        with urllib.request.urlopen(source['registry_url'], timeout=10) as resp:
            registry = json.loads(resp.read())
        for skill in registry.get('skills', []):
            all_skills.append({'source': source['name'], **skill})
    except Exception as e:
        print(f"warning: failed to fetch {source['registry_url']}: {e}", file=sys.stderr)

# Detect name collisions across sources
name_counts = {}
for s in all_skills:
    name_counts[s['name']] = name_counts.get(s['name'], 0) + 1

for s in all_skills:
    qualified = name_counts[s['name']] > 1
    display = f"{s['source']}/{s['name']}" if qualified else s['name']
    ver = f" ({s['version']})" if s.get('version') else ''
    print(f"{display}{ver}")
    print(f"  {s['description'][:100]}")
    print()
PYEOF
}
```

- [ ] **Step 2: Add `cmd_install` function** — insert after `cmd_list`:

```bash
# ── cmd: install ──────────────────────────────────────────────────────────────

cmd_install() {
    local arg="${1:-}"
    [ -n "$arg" ] || die "Usage: claude-skills install [source/]<name>"
    ensure_dirs
    init_sources
    init_installed
    python3 - "$SOURCES_FILE" "$INSTALLED_FILE" "$SKILLS_DIR" "$TMP_DIR" "$arg" << 'PYEOF'
import json, os, sys, shutil, tarfile, urllib.request
from datetime import datetime, timezone

sources_file, installed_file, skills_dir, tmp_dir, arg = sys.argv[1:]

sources_data = json.load(open(sources_file))
matches = []
for source in sources_data['sources']:
    try:
        with urllib.request.urlopen(source['registry_url'], timeout=10) as resp:
            registry = json.loads(resp.read())
    except Exception as e:
        print(f"warning: failed to fetch {source['registry_url']}: {e}", file=sys.stderr)
        continue
    for skill in registry.get('skills', []):
        qualified = f"{source['name']}/{skill['name']}"
        if arg in (skill['name'], qualified):
            matches.append({'skill': skill, 'source': source,
                            'qualified': qualified,
                            'registry_updated_at': registry.get('updated_at', '')})

if not matches:
    print(f"error: skill '{arg}' not found", file=sys.stderr); sys.exit(1)
if len(matches) > 1:
    names = ', '.join(m['qualified'] for m in matches)
    print(f"error: '{arg}' is ambiguous: {names}", file=sys.stderr)
    print(f"Try: claude-skills install {matches[0]['qualified']}", file=sys.stderr)
    sys.exit(1)

m = matches[0]
skill, source = m['skill'], m['source']
skill_name, skill_path = skill['name'], skill['path']
dest = os.path.join(skills_dir, skill_name)

installed_data = json.load(open(installed_file))
is_managed = any(i['name'] == skill_name for i in installed_data['installed'])
if os.path.exists(dest) and not is_managed:
    print(f"warning: {dest} exists but was not installed by claude-skills — replacing")

repo_url = source['repo_url'].rstrip('/')
repo_name = repo_url.split('/')[-1]
tarball_url = f"{repo_url}/archive/refs/heads/main.tar.gz"

tarball_path = os.path.join(tmp_dir, f"{skill_name}.tar.gz")
print(f"Downloading {skill_name} from {source['name']}...")
with urllib.request.urlopen(tarball_url, timeout=60) as resp:
    with open(tarball_path, 'wb') as f:
        f.write(resp.read())

extract_tmp = os.path.join(tmp_dir, f"{skill_name}_extract")
os.makedirs(extract_tmp, exist_ok=True)
prefix = f"{repo_name}-main/{skill_path}/"

with tarfile.open(tarball_path, 'r:gz') as tf:
    members = []
    for member in tf.getmembers():
        if not member.name.startswith(prefix):
            continue
        member.name = member.name[len(f"{repo_name}-main/"):]
        # Guard against path traversal in untrusted tarballs
        if os.path.isabs(member.name) or '..' in member.name.split('/'):
            continue
        members.append(member)
    tf.extractall(extract_tmp, members=members)

extracted = os.path.join(extract_tmp, skill_path)
if not os.path.isdir(extracted):
    print(f"error: skill directory '{skill_path}' not found in tarball", file=sys.stderr); sys.exit(1)

staging = os.path.join(tmp_dir, f"{skill_name}_staging")
if os.path.exists(staging):
    shutil.rmtree(staging)
shutil.copytree(extracted, staging)

# Atomic replace: move old aside, move new into place, then remove old
old_backup = dest + '.old'
if os.path.exists(old_backup):
    shutil.rmtree(old_backup)
if os.path.exists(dest):
    shutil.move(dest, old_backup)
shutil.move(staging, dest)
if os.path.exists(old_backup):
    shutil.rmtree(old_backup)

now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
installed_data['installed'] = [i for i in installed_data['installed'] if i['name'] != skill_name]
installed_data['installed'].append({'name': skill_name, 'source': source['name'],
                                     'installed_at': now,
                                     'registry_updated_at': m['registry_updated_at']})
json.dump(installed_data, open(installed_file, 'w'), indent=2)

shutil.rmtree(extract_tmp)
os.remove(tarball_path)
print(f"Installed {skill_name} → {dest}")
print("Open a new Claude Code session to activate the skill.")
PYEOF
}
```

- [ ] **Step 3: Add `cmd_remove` function** — insert after `cmd_install`:

```bash
# ── cmd: remove ───────────────────────────────────────────────────────────────

cmd_remove() {
    local name="${1:-}"
    [ -n "$name" ] || die "Usage: claude-skills remove <name>"
    init_installed
    local dest="${SKILLS_DIR}/${name}"
    [ -d "$dest" ] || die "Skill not installed: ${name}"
    rm -rf "$dest"
    python3 - "$INSTALLED_FILE" "$name" << 'PYEOF'
import json, sys
path, name = sys.argv[1], sys.argv[2]
data = json.load(open(path))
before = len(data['installed'])
data['installed'] = [i for i in data['installed'] if i['name'] != name]
json.dump(data, open(path, 'w'), indent=2)
suffix = '' if len(data['installed']) < before else ' (was not CLI-managed)'
print(f"Removed {name}{suffix}")
PYEOF
}
```

- [ ] **Step 4: Update the dispatch block** to include the new commands:

```bash
case "${1:-}" in
    add)     cmd_add "${2:-}" ;;
    list)    cmd_list ;;
    install) cmd_install "${2:-}" ;;
    remove)  cmd_remove "${2:-}" ;;
    sources) cmd_sources ;;
    *)
        echo "claude-skills — plugin marketplace CLI for Claude Code"
        echo ""
        echo "Usage:"
        echo "  claude-skills add <registry-url>    Register a marketplace source"
        echo "  claude-skills list                  List available skills"
        echo "  claude-skills install <name>        Install a skill"
        echo "  claude-skills update                Update all CLI-installed skills"
        echo "  claude-skills remove <name>         Remove an installed skill"
        echo "  claude-skills sources               List registered sources"
        ;;
esac
```

- [ ] **Step 5: Commit**

```bash
git add claude-skills
git commit -m "feat: add list, install, remove commands to claude-skills CLI"
```

---

## Task 6: `claude-skills` CLI — `update` Command

**Files:**
- Modify: `claude-skills` (add `cmd_update` before dispatch)

- [ ] **Step 1: Add `cmd_update` function** — insert after `cmd_remove`:

```bash
# ── cmd: update ───────────────────────────────────────────────────────────────

cmd_update() {
    init_installed
    local names
    names=$(python3 - "$INSTALLED_FILE" << 'PYEOF'
import json, sys
data = json.load(open(sys.argv[1]))
for i in data['installed']:
    print(i['name'])
PYEOF
)
    if [ -z "$names" ]; then
        echo "No CLI-managed skills installed."
        return
    fi
    echo "Updating CLI-managed skills..."
    while IFS= read -r name; do
        echo "  Updating ${name}..."
        cmd_install "$name" || echo "  warning: failed to update ${name}, skipping"
    done <<< "$names"
    echo "Done."
}
```

- [ ] **Step 2: Replace the dispatch block** (the full `case...esac` at the bottom of `claude-skills`) with this complete version:

```bash
case "${1:-}" in
    add)     cmd_add "${2:-}" ;;
    list)    cmd_list ;;
    install) cmd_install "${2:-}" ;;
    update)  cmd_update ;;
    remove)  cmd_remove "${2:-}" ;;
    sources) cmd_sources ;;
    *)
        echo "claude-skills — plugin marketplace CLI for Claude Code"
        echo ""
        echo "Usage:"
        echo "  claude-skills add <registry-url>    Register a marketplace source"
        echo "  claude-skills list                  List available skills"
        echo "  claude-skills install <name>        Install a skill"
        echo "  claude-skills update                Update all CLI-installed skills"
        echo "  claude-skills remove <name>         Remove an installed skill"
        echo "  claude-skills sources               List registered sources"
        ;;
esac
```

- [ ] **Step 3: Commit**

```bash
git add claude-skills
git commit -m "feat: add update command to claude-skills CLI"
```

---

## Task 7: Bootstrap `install.sh`

**Files:**
- Create: `install.sh`

- [ ] **Step 1: Write install.sh**

```bash
#!/usr/bin/env bash
# install.sh — bootstrap the claude-skills CLI
# Usage: curl -fsSL https://litianningdatadog.github.io/claude-skills/install.sh | bash

set -euo pipefail

INSTALL_DIR="${HOME}/.local/bin"
SCRIPT_NAME="claude-skills"
PAGES_BASE="https://litianningdatadog.github.io/claude-skills"
REGISTRY_URL="${PAGES_BASE}/registry.json"

echo "Installing claude-skills..."

# 1. Create install directory
mkdir -p "$INSTALL_DIR"

# 2. Download the claude-skills script
curl -fsSL "${PAGES_BASE}/claude-skills" -o "${INSTALL_DIR}/${SCRIPT_NAME}"
chmod +x "${INSTALL_DIR}/${SCRIPT_NAME}"

# 3. Check PATH
if ! echo ":${PATH}:" | grep -q ":${INSTALL_DIR}:"; then
    echo ""
    echo "NOTE: ${INSTALL_DIR} is not on your PATH."
    echo "Add this line to your shell config (~/.zshrc or ~/.bashrc):"
    echo ""
    echo "  export PATH=\"\${HOME}/.local/bin:\${PATH}\""
    echo ""
    echo "Then restart your terminal or run: source ~/.zshrc"
    echo ""
fi

# 4. Register the official source
"${INSTALL_DIR}/${SCRIPT_NAME}" add "$REGISTRY_URL"

# 5. Done
echo ""
echo "claude-skills installed successfully!"
echo ""
echo "  claude-skills list              # browse available skills"
echo "  claude-skills install <name>    # install a skill"
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x install.sh
```

- [ ] **Step 3: Dry-run sanity check (verify the script parses cleanly)**

```bash
bash -n install.sh && echo "Syntax OK"
```

Expected: `Syntax OK`

- [ ] **Step 4: Commit**

```bash
git add install.sh
git commit -m "feat: add install.sh bootstrap script"
```

---

## Task 8: Static Catalog `index.html`

**Files:**
- Create: `index.html`

- [ ] **Step 1: Write index.html**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Claude Skills Marketplace</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 800px; margin: 2rem auto; padding: 0 1rem; color: #222; }
    h1 { font-size: 1.5rem; margin-bottom: 0.25rem; }
    .subtitle { color: #555; margin-bottom: 2rem; }
    .install-box { background: #f5f5f5; border-radius: 6px; padding: 1rem 1.25rem; margin-bottom: 2rem; font-size: 0.9rem; }
    .install-box code { font-family: monospace; }
    .skill { border: 1px solid #e0e0e0; border-radius: 6px; padding: 1rem 1.25rem; margin-bottom: 0.75rem; }
    .skill h2 { font-size: 1rem; margin: 0 0 0.4rem; font-family: monospace; color: #0070f3; }
    .skill p { margin: 0 0 0.5rem; color: #444; font-size: 0.9rem; line-height: 1.5; }
    .skill-meta { font-size: 0.8rem; color: #888; }
    .skill-meta code { font-family: monospace; background: #f0f0f0; padding: 1px 4px; border-radius: 3px; }
    #status { color: #666; margin-top: 1rem; }
  </style>
</head>
<body>
  <h1>Claude Skills Marketplace</h1>
  <p class="subtitle">Specialized workflows for <a href="https://claude.ai/code">Claude Code</a>.</p>

  <div class="install-box">
    <strong>Get started:</strong><br>
    <code>curl -fsSL https://litianningdatadog.github.io/claude-skills/install.sh | bash</code>
  </div>

  <div id="status">Loading skills...</div>
  <div id="skills"></div>

  <script>
    fetch('./registry.json')
      .then(r => { if (!r.ok) throw new Error(r.statusText); return r.json(); })
      .then(data => {
        document.getElementById('status').textContent =
          `${data.skills.length} skill${data.skills.length !== 1 ? 's' : ''} available · updated ${data.updated_at.slice(0, 10)}`;
        const container = document.getElementById('skills');
        for (const s of data.skills) {
          const div = document.createElement('div');
          div.className = 'skill';

          const h2 = document.createElement('h2');
          h2.textContent = s.name;
          div.appendChild(h2);

          const p = document.createElement('p');
          p.textContent = s.description;
          div.appendChild(p);

          const meta = document.createElement('div');
          meta.className = 'skill-meta';
          const code = document.createElement('code');
          code.textContent = `claude-skills install ${s.name}`;
          meta.appendChild(code);
          if (s.has_scripts) meta.appendChild(document.createTextNode(' · includes scripts'));
          div.appendChild(meta);

          container.appendChild(div);
        }
        if (!data.skills.length)
          container.textContent = 'No skills published yet.';
      })
      .catch(e => {
        document.getElementById('status').textContent = 'Failed to load registry: ' + e.message;
      });
  </script>
</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add index.html
git commit -m "feat: add GitHub Pages skill catalog"
```

---

## Task 9: Update README.md

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace the "Installing a skill" section** with a new Marketplace section. Open `README.md` and replace everything from `## Installing a skill` through the end of that section with:

```markdown
## Marketplace

This repo is a public skill marketplace. Browse skills at **https://litianningdatadog.github.io/claude-skills/**

### Install the CLI (one-time)

```bash
curl -fsSL https://litianningdatadog.github.io/claude-skills/install.sh | bash
```

### Install a skill

```bash
claude-skills list                   # browse available skills
claude-skills install efficiency-audit
```

Skills are installed to `~/.claude/skills/` and activate automatically in the next Claude Code session.

### Commands

```bash
claude-skills add <url>      # add a marketplace source
claude-skills list           # list skills from all sources
claude-skills install <name> # install a skill
claude-skills update         # update all CLI-installed skills
claude-skills remove <name>  # remove a skill
claude-skills sources        # list registered sources
```

### Manual install (no CLI)

```bash
cp -R <skill-dir> ~/.claude/skills/
```
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update README with marketplace install instructions"
```

---

## Task 10: One-Time GitHub Setup (Manual)

These steps require clicking in the GitHub UI — they cannot be scripted.

- [ ] **Step 1:** Go to the repo on GitHub → **Settings → Pages → Source** → set to **"GitHub Actions"** → Save.

- [ ] **Step 2:** Go to **Settings → Actions → General → Workflow permissions** → select **"Read and write permissions"** → Save.

- [ ] **Step 3 (if `main` has branch protection):** Go to **Settings → Branches → main** → add `github-actions[bot]` to "Allow specified actors to bypass required pull request reviews".

- [ ] **Step 4:** Push any commit to `main` (e.g. `git push`) and watch the Actions tab to confirm the workflow runs successfully.

- [ ] **Step 5:** Visit `https://litianningdatadog.github.io/claude-skills/` to confirm the catalog page loads and skills are listed.

- [ ] **Step 6:** Run the bootstrap locally to verify end-to-end:

```bash
curl -fsSL https://litianningdatadog.github.io/claude-skills/install.sh | bash
claude-skills list
claude-skills install quicknotes
ls ~/.claude/skills/quicknotes/
```

Expected: `quicknotes/SKILL.md` present, skill visible in next Claude Code session.
