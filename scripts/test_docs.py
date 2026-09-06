"""B7 regressions against complete disposable project copies; no real secrets."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

from project_data import ROOT, PLAN_PATH, dump, tasks, calc_stats, sync_views


class DocumentationChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='selfevo-doc-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'project'
        shutil.copytree(ROOT, self.root, ignore=shutil.ignore_patterns(
            '.git', '__pycache__', '.backups', '*.local.*', 'node_modules', '.venv', '.cache'))
        p = json.loads((self.root / PLAN_PATH).read_text())
        for t in tasks(p) + p['deliverables']:
            t.update(done=False, completedOn=None, note='', evidence=[])
        for w in p['weeks']:
            w['note'] = ''
        p.update(checkins=[], dailyLogs={}, overrides=[], history=[], _orphans=[])
        p['stats'] = calc_stats(p)
        (self.root / PLAN_PATH).write_text(dump(p))
        sync_views(self.root)
        self.secret = 'SYNTHETIC_' + uuid.uuid4().hex
        (self.root / '01-个人档案.local.md').write_text(
            '| 公开 | 真值（本地） |\n|---|---|\n| 代称 | ' + self.secret + ' |\n')

    def put(self, relative, text):
        f = self.root / relative
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding='utf-8')

    def check(self, expected=0):
        before = self.files()
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
        r = subprocess.run([sys.executable, str(self.root / 'scripts/check-docs.py')],
                           cwd=self.root, env=env, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(r.returncode, expected, r.stdout + r.stderr)
        self.assertNotIn(self.secret, r.stdout + r.stderr)
        self.assertEqual(before, self.files())
        return r

    def files(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*')
                if p.is_file() and '__pycache__' not in p.parts}

    def test_b7_clean_copy_and_upstream_examples_do_not_false_alarm(self):
        self.check()

    def test_b7_hidden_yaml_and_deep_hidden_text_leaks_fail_without_echo(self):
        for relative in ('.github/probe.yml', '.agents/custom/probe.md', '.config/nested/probe.txt'):
            with self.subTest(path=relative):
                self.put(relative, '# ' + self.secret)
                try:
                    r = self.check(expected=1)
                    self.assertIn('隐私', r.stdout)
                finally:
                    (self.root / relative).unlink()

    def test_b7_hidden_real_links_and_code_labels_are_checked(self):
        for filename in ('.agents/probe.md', '.agents/probe.MD'):
            for text in ('[missing](not-here.md)\n', '[`code-label`](not-here.md)\n'):
                with self.subTest(filename=filename, text=text):
                    self.put(filename, text)
                    try:
                        self.assertIn('链接', self.check(expected=1).stdout)
                    finally:
                        (self.root / filename).unlink()

    def test_b7_links_inside_code_are_examples_but_real_links_remain(self):
        self.put('.agents/probe.md',
                 '`[not a link](missing-a.md)`\n\n```markdown\n[x](missing-b.md)\n```\n'
                 '\n~~~markdown\n[x](missing-c.md)\n~~~\n\n[`real`](../README.md)\n')
        self.check()

    def test_b7_fragments_and_encoded_spaces_are_validated(self):
        self.put('.agents/target file.md', '# Heading\n\n## Present\n')
        self.put('.agents/probe.md', '[ok](target%20file.md#present)\n')
        self.check()
        self.put('.agents/probe.md', '[bad](target%20file.md#missing)\n')
        self.assertIn('链接', self.check(expected=1).stdout)

    def test_b7_private_backups_and_dependency_caches_are_not_public(self):
        for relative in ('notes.local.md', '.agents/private.local.md',
                         'progress/.backups/probe.json', 'node_modules/pkg/README.md',
                         '.venv/probe.md', '__pycache__/probe.md'):
            self.put(relative, self.secret + '\n[not public](missing.md)\n')
        self.check()

    def test_b7_supposed_vendor_reference_still_has_privacy_and_link_checks(self):
        self.put('.agents/skills/neat-freak/references/probe.md', self.secret)
        self.assertIn('隐私', self.check(expected=1).stdout)
        self.put('.agents/skills/neat-freak/references/probe.md', '[x](missing.md)\n')
        self.assertIn('链接', self.check(expected=1).stdout)


if __name__ == '__main__':
    unittest.main()
