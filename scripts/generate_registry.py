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
            with open(output_path) as f:
                existing = json.load(f)
            if existing.get('skills') == skills:
                preserved_at = existing.get('updated_at')
        except json.JSONDecodeError:
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
