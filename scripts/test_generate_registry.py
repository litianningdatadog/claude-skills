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
        self._make_skill('my-skill', skill_name='other')
        skills = discover_skills(self.tmpdir)
        self.assertEqual(len(skills), 0)

    def test_excludes_non_directories(self):
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
