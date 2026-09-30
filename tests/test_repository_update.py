from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).parents[1]
OLD = 'kebemouhamet08-gif'  # Legacy input fixtures, never a download target.
NEW = 'kolemm14'
REPO = 'Debian-Hyprland-Custom'


class RepositoryUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.checkout = self.root / 'checkout'
        self.checkout.mkdir()
        self.env = {**os.environ, 'GIT_CONFIG_GLOBAL': os.devnull,
                    'GIT_CONFIG_NOSYSTEM': '1', 'GIT_TERMINAL_PROMPT': '0'}
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Migration test')
        self.git('config', 'user.email', 'test@example.invalid')
        self.env.update(HOME=str(self.root / 'home'),
                        XDG_CONFIG_HOME=str(self.root / 'home/.config'),
                        XDG_DATA_HOME=str(self.root / 'home/.local/share'),
                        XDG_STATE_HOME=str(self.root / 'home/.local/state'))
        self.env.pop('HYPRLAND_INSTANCE_SIGNATURE', None)
        shutil.copy2(ROOT / 'update.sh', self.checkout / 'update.sh')
        shutil.copytree(ROOT / 'core/update', self.checkout / 'core/update', ignore=shutil.ignore_patterns('__pycache__'))
        (self.checkout / 'manifests').mkdir()
        (self.checkout / 'manifests/update-files.json').write_text('{"schema":1,"rules":[]}')

    def git(self, *args, cwd=None):
        return subprocess.run(['git', '-C', str(cwd or self.checkout), *args],
                              env=self.env, capture_output=True, text=True,
                              check=True, timeout=15).stdout.strip()

    def run_update(self, *args):
        return subprocess.run(['bash', str(self.checkout / 'update.sh'), *args],
                              cwd=self.root, env=self.env, capture_output=True,
                              text=True, timeout=15)

    def test_exact_legacy_origins_migrate_and_remain_idempotent(self):
        for prefix in ('https://github.com/', 'git@github.com:', 'ssh://git@github.com/'):
            for suffix in ('', '.git'):
                with self.subTest(prefix=prefix, suffix=suffix):
                    self.git('config', 'remote.origin.url', f'{prefix}{OLD}/{REPO}{suffix}')
                    for _ in range(2):
                        result = self.run_update('--migrate-only')
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(self.git('remote', 'get-url', 'origin'),
                                         f'{prefix}{NEW}/{REPO}.git')

    def test_custom_and_lookalike_remotes_are_preserved(self):
        for url in (f'https://github.com/fork/{REPO}.git',
                    f'https://example.com/{OLD}/{REPO}.git',
                    f'https://github.com/{OLD}/{REPO}-fork.git',
                    f'https://github.com/{NEW}/{REPO}.git'):
            with self.subTest(url=url):
                self.git('config', 'remote.origin.url', url)
                self.assertEqual(self.run_update('--migrate-only').returncode, 0)
                self.assertEqual(self.git('remote', 'get-url', 'origin'), url)

    def test_multiple_origins_and_custom_push_url_are_preserved(self):
        old = f'https://github.com/{OLD}/{REPO}.git'
        custom = 'ssh://example.com/custom.git'
        self.git('remote', 'add', 'origin', old)
        self.git('config', 'remote.origin.pushurl', custom)
        self.assertEqual(self.run_update('--migrate-only').returncode, 0)
        self.assertEqual(self.git('remote', 'get-url', '--push', 'origin'), custom)
        self.git('config', 'remote.origin.url', old)
        self.git('config', '--add', 'remote.origin.url', custom)
        self.assertEqual(self.run_update('--migrate-only').returncode, 0)
        self.assertEqual(self.git('config', '--get-all', 'remote.origin.url'), old + '\n' + custom)

    def test_missing_origin_is_harmless_for_migration(self):
        self.assertEqual(self.run_update('--migrate-only').returncode, 0)
        self.assertEqual(self.git('remote'), '')

    def test_unknown_argument_does_not_change_origin(self):
        old = f'https://github.com/{OLD}/{REPO}.git'
        self.git('remote', 'add', 'origin', old)
        self.assertEqual(self.run_update('--unknown').returncode, 2)
        self.assertEqual(self.git('remote', 'get-url', 'origin'), old)

    def test_real_pull_fast_forwards_and_refuses_divergence(self):
        remote = self.root / 'remote.git'
        upstream = self.root / 'upstream'
        self.git('init', '--bare', str(remote))
        self.git('add', '.')
        self.git('commit', '-m', 'initial')
        self.git('remote', 'add', 'origin', str(remote))
        self.git('push', '-u', 'origin', 'main')
        self.git('clone', '-b', 'main', str(remote), str(upstream))
        self.git('config', 'user.name', 'Migration test', cwd=upstream)
        self.git('config', 'user.email', 'test@example.invalid', cwd=upstream)
        for index in (1, 2):
            (upstream / 'version').write_text(str(index))
            self.git('add', 'version', cwd=upstream)
            self.git('commit', '-m', f'upstream {index}', cwd=upstream)
            self.git('push', cwd=upstream)
            if index == 1:
                result = self.run_update()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((self.checkout / 'version').read_text(), '1')
                (self.checkout / 'local').write_text('local changes')
                self.git('add', 'local')
                self.git('commit', '-m', 'local work')
            else:
                before = self.git('rev-parse', 'HEAD')
                self.assertNotEqual(self.run_update().returncode, 0)
                self.assertEqual(self.git('rev-parse', 'HEAD'), before)
                self.assertEqual((self.checkout / 'local').read_text(), 'local changes')
