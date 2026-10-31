"""Real Git repositories and isolated HOME; no live desktop or network writes."""
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / 'core/updater'))
from files import Locations, UpdateError, fingerprint, json_write, snapshot
from transaction import Lock, Services, apply, recover, rollback


class UpdateSystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'checkout'
        self.home = self.root / 'home'
        self.repo.mkdir()
        self.home.mkdir()
        self.env = {**os.environ, 'HOME': str(self.home),
                    'XDG_CONFIG_HOME': str(self.home / '.config'),
                    'XDG_DATA_HOME': str(self.home / '.local/share'),
                    'XDG_STATE_HOME': str(self.home / '.local/state'),
                    'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1',
                    'GIT_TERMINAL_PROMPT': '0', 'PYTHONDONTWRITEBYTECODE': '1'}
        self.env.pop('HYPRLAND_INSTANCE_SIGNATURE', None)
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@example.invalid')
        shutil.copy2(ROOT / 'update.sh', self.repo / 'update.sh')
        shutil.copytree(ROOT / 'core/updater', self.repo / 'core/updater', ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(ROOT / 'core/transactions', self.repo / 'core/transactions', ignore=shutil.ignore_patterns('__pycache__'))
        (self.repo / 'manifests').mkdir()
        self.rules = [
            {'component': 'sample', 'source': 'config/sample/*.py', 'destination': 'home:.local/lib/sample/{name}', 'policy': 'managed', 'mode': '0755'},
            {'component': 'sample', 'source': 'config/sample/*.conf', 'destination': 'config:hypr/{name}', 'policy': 'config', 'mode': '0644'},
            {'component': 'optional', 'source': 'config/optional/*', 'destination': 'home:.local/bin/{name}', 'policy': 'managed'},
        ]
        self.write(self.repo, 'manifests/update-files.json', json.dumps({'schema': 1, 'rules': self.rules, 'services': {}, 'packages': {}}))
        self.write(self.repo, 'config/sample/tool.py', 'print("one")\n')
        self.write(self.repo, 'config/sample/session.conf', 'source = managed.conf\n')
        self.write(self.repo, 'config/optional/extra', 'optional\n')
        self.commit(self.repo)
        self.initial = self.git('rev-parse', 'HEAD')
        self.remote = self.root / 'remote.git'
        self.git('init', '--bare', str(self.remote))
        self.git('remote', 'add', 'origin', str(self.remote))
        self.git('push', '-u', 'origin', 'main')
        self.upstream = self.root / 'upstream'
        self.git('clone', '-b', 'main', str(self.remote), str(self.upstream))
        self.git('config', 'user.name', 'Test', cwd=self.upstream)
        self.git('config', 'user.email', 'test@example.invalid', cwd=self.upstream)
        self.locations = Locations(self.repo, self.env)
        self.tool = self.home / '.local/lib/sample/tool.py'
        self.config = self.home / '.config/hypr/session.conf'
        self.write(self.home, '.local/lib/sample/tool.py', 'print("one")\n', 0o755)
        self.write(self.home, '.config/hypr/session.conf', 'source = managed.conf\n')
        self.update('--record-component', 'sample')

    def write(self, root, name, content, mode=0o644):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        path.chmod(mode)
        return path

    def git(self, *args, cwd=None):
        return subprocess.run(['git', '-C', str(cwd or self.repo), *args], env=self.env,
                              capture_output=True, text=True, check=True, timeout=15).stdout.strip()

    def commit(self, root):
        self.git('add', '.', cwd=root)
        self.git('commit', '-m', 'version', cwd=root)

    def publish(self):
        self.commit(self.upstream)
        self.git('push', cwd=self.upstream)
        return self.git('rev-parse', 'HEAD', cwd=self.upstream)

    def update(self, *args, ok=True):
        result = subprocess.run(['bash', str(self.repo / 'update.sh'), *args], env=self.env,
                                cwd=self.root, capture_output=True, text=True, timeout=30)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        return result

    def tree(self):
        return {str(p.relative_to(self.home)): snapshot(p) for p in self.home.rglob('*')
                if p.is_file() or p.is_symlink()}

    def test_no_update_and_five_runs_are_idempotent(self):
        before = self.tool.stat().st_mtime_ns
        for _ in range(5):
            self.assertIn('déjà à jour', self.update().stdout)
        self.assertEqual(self.tool.stat().st_mtime_ns, before)
        self.assertFalse((self.locations.data / 'backups').exists())
        self.assertEqual(self.config.read_text().count('source ='), 1)

    def test_add_modify_delete_and_rename_without_duplicate(self):
        self.write(self.upstream, 'config/sample/new.py', 'print("new")\n')
        self.write(self.upstream, 'config/sample/tool.py', 'print("two")\n')
        self.git('mv', 'config/sample/session.conf', 'config/sample/renamed.conf', cwd=self.upstream)
        latest = self.publish()
        out = self.update().stdout
        self.assertIn('R100', out)
        self.assertFalse(self.config.exists())
        self.assertTrue(self.config.with_name('renamed.conf').exists())
        self.assertEqual(self.tool.read_text(), 'print("two")\n')
        self.assertEqual(self.tool.stat().st_mode & 0o777, 0o755)
        self.assertEqual(json.loads(self.locations.manifest.read_text())['commit'], latest)
        (self.upstream / 'config/sample/new.py').unlink()
        self.publish()
        self.update()
        self.assertFalse(self.tool.with_name('new.py').exists())
        state_mtime = self.locations.manifest.stat().st_mtime_ns
        self.assertIn('déjà à jour', self.update().stdout)
        self.assertEqual(self.locations.manifest.stat().st_mtime_ns, state_mtime)

    def test_custom_config_new_file_and_force_preserve_user(self):
        self.config.write_text('bind = USER\n')
        self.write(self.upstream, 'config/sample/session.conf', 'bind = NEW\n')
        self.publish()
        for args in ((), (), ('--force',)):
            self.update(*args)
            self.assertEqual(self.config.read_text(), 'bind = USER\n')
            self.assertEqual(Path(str(self.config) + '.new').read_text(), 'bind = NEW\n')
        self.assertEqual(len(list(self.config.parent.glob('*.new*'))), 1)

    def test_deleted_custom_file_is_never_removed(self):
        self.tool.write_text('# personal script\n')
        (self.upstream / 'config/sample/tool.py').unlink()
        self.publish()
        self.update('--force')
        self.assertTrue(self.tool.exists())
        self.assertIn('personal', self.tool.read_text())

    def test_unowned_new_destination_is_preserved(self):
        other = self.write(self.home, '.local/lib/sample/new.py', '# user file\n')
        self.write(self.upstream, 'config/sample/new.py', 'print("upstream")\n')
        self.publish()
        self.update('--force')
        self.assertEqual(other.read_text(), '# user file\n')
        self.assertTrue(Path(str(other) + '.new').exists())

    def test_optional_absent_stays_absent_and_present_updates(self):
        self.write(self.upstream, 'config/optional/extra', 'second\n')
        self.publish()
        self.update()
        optional = self.home / '.local/bin/extra'
        self.assertFalse(optional.exists())
        self.write(self.home, '.local/bin/extra', 'second\n')
        self.update('--record-component', 'optional')
        self.write(self.upstream, 'config/optional/extra', 'third\n')
        self.publish()
        self.update()
        self.assertEqual(optional.read_text(), 'third\n')

    def test_check_and_dry_run_do_not_write_home_or_checkout(self):
        self.write(self.upstream, 'config/sample/tool.py', 'print("two")\n')
        self.publish()
        before = self.tree()
        git_before = {str(p.relative_to(self.repo)): p.read_bytes() for p in (self.repo / '.git').rglob('*') if p.is_file()}
        self.assertIn('Mise à jour disponible', self.update('--check').stdout)
        self.assertIn('Fichiers à modifier : 1', self.update('--dry-run').stdout)
        self.assertEqual(before, self.tree())
        self.assertEqual(git_before, {str(p.relative_to(self.repo)): p.read_bytes() for p in (self.repo / '.git').rglob('*') if p.is_file()})

    def test_partial_reset_repairs_without_duplicates(self):
        self.write(self.upstream, 'config/sample/tool.py', 'print("two")\n')
        self.publish()
        self.update()
        self.tool.unlink()
        self.update()
        for _ in range(5):
            self.update()
        self.assertEqual(self.tool.read_text(), 'print("two")\n')
        self.assertEqual(self.config.read_text().count('source ='), 1)
        self.assertEqual(len(list(self.tool.parent.glob('tool*'))), 1)

    def test_failed_validation_leaves_everything_unchanged(self):
        self.write(self.upstream, 'config/sample/tool.py', 'invalid python !\n')
        self.publish()
        before = self.tool.read_bytes()
        manifest = self.locations.manifest.read_bytes()
        self.update(ok=False)
        self.assertEqual(before, self.tool.read_bytes())
        self.assertEqual(manifest, self.locations.manifest.read_bytes())
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.initial)

    def test_manual_rollback_restores_files_and_version(self):
        self.write(self.upstream, 'config/sample/tool.py', 'print("two")\n')
        self.publish()
        self.update()
        self.update('--rollback')
        self.assertEqual(self.tool.read_text(), 'print("one")\n')
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.initial)
        self.assertEqual(json.loads(self.locations.manifest.read_text())['commit'], self.initial)

    def test_rollback_refuses_later_user_edit(self):
        self.write(self.upstream, 'config/sample/tool.py', 'print("two")\n')
        self.publish()
        self.update()
        self.tool.write_text('# personal after update\n')
        self.update('--rollback', ok=False)
        self.assertEqual(self.tool.read_text(), '# personal after update\n')

    def test_lock_prevents_concurrent_writer(self):
        with Lock(self.locations):
            result = self.update(ok=False)
        self.assertIn('déjà en cours', result.stderr)

    def test_parent_symlink_escape_is_refused(self):
        outside = self.root / 'outside'
        outside.mkdir()
        shutil.rmtree(self.tool.parent)
        self.tool.parent.symlink_to(outside, target_is_directory=True)
        self.update('--force', ok=False)
        self.assertEqual(list(outside.iterdir()), [])

    def test_forgotten_component_is_not_reinstalled(self):
        self.update('--forget-component', 'sample')
        self.tool.unlink()
        self.config.unlink()
        self.write(self.upstream, 'config/sample/tool.py', 'print("two")\n')
        self.publish()
        self.update()
        self.assertFalse(self.tool.exists())

    def test_transaction_failure_and_interruption_roll_back(self):
        original = snapshot(self.tool)
        new = {**original, 'value': base64.b64encode(b'print("two")\n').decode()}
        op = {'key': 'home:.local/lib/sample/tool.py', 'before': original, 'after': new, 'action': 'M'}
        for failure in (UpdateError('reload failure'), KeyboardInterrupt()):
            services = Services([])
            services.reload = mock.Mock(side_effect=failure)
            state = json.loads(self.locations.manifest.read_text())
            with self.assertRaises(type(failure)):
                apply(self.locations, [op], state, services, False, self.initial, self.initial, False)
            self.assertEqual(snapshot(self.tool), original)
            self.assertFalse((self.locations.state / 'pending.json').exists())

    def test_pending_journal_recovers_after_killed_process(self):
        original = snapshot(self.tool)
        new = {**original, 'value': base64.b64encode(b'print("two")\n').decode()}
        backup = self.locations.data / 'backups/interrupted'
        json_write(backup / 'journal.json', {
            'status': 'pending', 'operations': [{'key': 'home:.local/lib/sample/tool.py', 'before': original, 'after': new}],
            'services': {}, 'service_bus': False, 'manifest_before': snapshot(self.locations.manifest),
            'version_before': snapshot(self.locations.data / 'version'),
            'old_head': self.initial, 'new_head': self.initial,
        })
        json_write(self.locations.state / 'pending.json', {'backup': 'interrupted'})
        self.tool.write_text('print("two")\n')
        recover(self.locations)
        self.assertEqual(snapshot(self.tool), original)

    def test_systemd_reloads_only_affected_previously_active_units(self):
        calls = []
        def runner(command, **options):
            calls.append(command)
            status = 'active\n' if 'is-active' in command else 'enabled\n' if 'is-enabled' in command else ''
            return subprocess.CompletedProcess(command, 0, status, '')
        with mock.patch('transaction.run', side_effect=runner), mock.patch('transaction.shutil.which', return_value='/bin/systemctl'):
            services = Services(['old.service'], ['old.service'], {'old.service': 'new.service'})
            services.stop()
            services.reload(True)
            self.assertIn(['systemctl', '--user', 'disable', 'old.service'], calls)
            self.assertIn(['systemctl', '--user', 'daemon-reload'], calls)
            self.assertIn(['systemctl', '--user', 'enable', 'new.service'], calls)
            self.assertIn(['systemctl', '--user', 'start', 'new.service'], calls)
            self.assertFalse(any('unrelated.service' in call for call in calls))

    def fake_systemd(self):
        binary = self.root / 'fake-bin'
        binary.mkdir(exist_ok=True)
        trace = self.root / 'systemctl.log'
        self.write(binary, 'systemctl', '#!/bin/sh\nprintf "%s\\n" "$*" >> "$SYSTEMCTL_TRACE"\ncase "$2" in\n is-active) echo active ;;\n is-enabled) echo enabled ;;\nesac\n', 0o755)
        self.env['PATH'] = str(binary) + os.pathsep + self.env['PATH']
        self.env['SYSTEMCTL_TRACE'] = str(trace)
        return trace

    def test_mpvpaper_present_preserves_state_media_and_restarts_only_engine(self):
        trace = self.fake_systemd()
        production = json.loads((ROOT / 'manifests/update-files.json').read_text())
        mapping = {'schema': 1, 'rules': self.rules + [r for r in production['rules'] if r['component'] == 'mpvpaper-engine'],
                   'services': {'mpvpaper-engine': ['mpvpaper-engine.service']}, 'packages': {}}
        self.write(self.upstream, 'manifests/update-files.json', json.dumps(mapping))
        self.write(self.upstream, 'apps/system-apps/mpvpaper-engine/mpvpaper-engine.py', 'print("engine v2")\n')
        self.write(self.upstream, 'apps/system-apps/mpvpaper-engine/mpvpaper_engine/module.py', 'VALUE = 2\n')
        self.write(self.upstream, 'apps/system-apps/mpvpaper-engine/tests/test_engine.py', 'VALUE = 2\n')
        self.write(self.upstream, 'apps/system-apps/mpvpaper-engine/mpvpaper-engine.service', '[Service]\nExecStart=/bin/true\n')
        self.write(self.home, '.local/lib/mpvpaper-engine/mpvpaper-engine.py', 'print("engine v2")\n', 0o755)
        self.write(self.home, '.local/bin/mpvpaper-engine', '#!/bin/sh\n', 0o755)
        state = self.write(self.home, '.config/mpvpaper-engine/config.json', '{"outputs":{"DP-1":{"wallpaper":"personal.mp4"}}}')
        media = self.write(self.home, 'Pictures/Wallpapers/Live/personal.mp4', 'personal media')
        database = self.write(self.home, '.local/share/mpvpaper-engine/library.db', 'personal library')
        previous = [p.read_bytes() for p in (state, media, database)]
        self.publish()
        self.update()
        self.assertTrue((self.home / '.local/lib/mpvpaper-engine/mpvpaper_engine/module.py').exists())
        self.assertTrue((self.home / '.local/lib/mpvpaper-engine/tests/test_engine.py').exists())
        self.assertEqual(previous, [p.read_bytes() for p in (state, media, database)])
        self.assertIn('--user stop mpvpaper-engine.service', trace.read_text())
        self.assertIn('--user daemon-reload', trace.read_text())
        self.assertIn('--user start mpvpaper-engine.service', trace.read_text())
        before = trace.read_text()
        self.update()
        self.assertEqual(trace.read_text(), before)

    def test_mpvpaper_absent_does_not_install_files_or_start_service(self):
        trace = self.fake_systemd()
        production = json.loads((ROOT / 'manifests/update-files.json').read_text())
        self.write(self.upstream, 'manifests/update-files.json', json.dumps(production))
        self.write(self.upstream, 'apps/system-apps/mpvpaper-engine/mpvpaper-engine.py', 'print("engine")\n')
        self.publish()
        self.update()
        self.assertFalse((self.home / '.local/lib/mpvpaper-engine').exists())
        self.assertFalse(trace.exists())

    def test_real_unit_rename_removes_old_and_transfers_enabled_service(self):
        trace = self.fake_systemd()
        rules = self.rules + [{'component': 'sample', 'source': 'config/sample/*.service',
                               'destination': 'config:systemd/user/{name}', 'mode': '0644'}]
        self.write(self.upstream, 'manifests/update-files.json', json.dumps({'schema': 1, 'rules': rules}))
        self.write(self.upstream, 'config/sample/old.service', '[Service]\nExecStart=/bin/true\n')
        self.publish()
        self.update()
        self.git('mv', 'config/sample/old.service', 'config/sample/new.service', cwd=self.upstream)
        self.publish()
        self.update()
        self.assertFalse((self.home / '.config/systemd/user/old.service').exists())
        self.assertTrue((self.home / '.config/systemd/user/new.service').exists())
        self.assertIn('--user disable old.service', trace.read_text())
        self.assertIn('--user enable new.service', trace.read_text())
        self.assertIn('--user start new.service', trace.read_text())

    def test_backup_retention_is_five(self):
        for number in range(6):
            self.write(self.upstream, 'config/sample/tool.py', f'print({number})\n')
            self.publish()
            self.update()
        self.assertEqual(len(list((self.locations.data / 'backups').iterdir())), 5)

    def test_managed_symlink_rename_and_reset(self):
        rules = self.rules + [{'component': 'sample', 'source': 'config/sample/tool.py',
                               'destination': 'home:.local/bin/tool', 'link': 'home:.local/lib/sample/tool.py'}]
        self.write(self.upstream, 'manifests/update-files.json', json.dumps({'schema': 1, 'rules': rules}))
        self.publish()
        self.update()
        link = self.home / '.local/bin/tool'
        self.assertEqual(os.readlink(link), str(self.tool))
        link.unlink()
        self.update()
        self.assertTrue(link.is_symlink())
        rules[-1]['destination'] = 'home:.local/bin/new-tool'
        self.write(self.upstream, 'manifests/update-files.json', json.dumps({'schema': 1, 'rules': rules}))
        self.publish()
        self.update()
        self.assertFalse(link.is_symlink())
        self.assertTrue(link.with_name('new-tool').is_symlink())

    def test_dry_run_reports_missing_packages_without_apt(self):
        self.write(self.upstream, 'manifests/update-files.json', json.dumps({
            'schema': 1, 'rules': self.rules, 'packages': {'sample': ['deblestia-nonexistent-test-package']}}))
        self.publish()
        result = self.update('--dry-run')
        self.assertIn('Paquets à ajouter : deblestia-nonexistent-test-package', result.stdout)
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.initial)

    def test_force_repairs_managed_edit_but_never_personal_config(self):
        self.tool.write_text('# local edit of owned program\n')
        self.config.write_text('bind = PERSONAL\n')
        self.update('--force')
        self.assertEqual(self.tool.read_text(), 'print("one")\n')
        self.assertEqual(self.config.read_text(), 'bind = PERSONAL\n')

    def test_existing_user_new_file_is_preserved(self):
        self.config.write_text('bind = PERSONAL\n')
        proposal = Path(str(self.config) + '.new')
        proposal.write_text('my pending merge\n')
        self.write(self.upstream, 'config/sample/session.conf', 'bind = NEW\n')
        self.publish()
        self.update()
        self.assertEqual(proposal.read_text(), 'my pending merge\n')
        self.assertEqual(len(list(self.config.parent.glob('session.conf.new.*'))), 1)

    def test_nova_patch_updates_preserve_custom_qml_and_restore_removed_patch(self):
        from patches import patch_inventory
        from files import plan_files
        upstream = self.home / '.config/quickshell/test-nova'
        upstream.mkdir(parents=True)
        self.git('init', '-b', 'main', cwd=upstream)
        self.git('config', 'user.name', 'Test', cwd=upstream)
        self.git('config', 'user.email', 'test@example.invalid', cwd=upstream)
        self.write(upstream, 'panel.qml', 'original\n')
        self.commit(upstream)
        group = {'component': 'sample', 'destination': 'config:quickshell/test-nova', 'patches': ['panel.patch']}
        tree = self.root / 'patch-tree'
        tree.mkdir()
        self.write(tree, 'manifests/update-files.json', json.dumps({'schema': 1, 'rules': [], 'patch_sets': [group]}))
        self.write(tree, 'panel.patch', '--- a/panel.qml\n+++ b/panel.qml\n@@ -1 +1 @@\n-original\n+updated\n')
        desired = patch_inventory(tree, self.locations, {'sample'})
        key = 'config:quickshell/test-nova/panel.qml'
        old = {'files': {}, 'components': ['sample']}
        (upstream / 'panel.qml').write_text('personal\n')
        operations, conflicts, state = plan_files(self.locations, old, desired, self.initial)
        self.assertEqual(conflicts, [key])
        self.assertEqual(operations[0]['key'], key + '.new')
        prior = {key: {**desired[key], 'installed': desired[key]['reference']}}
        (tree / 'panel.patch').unlink()
        restored = patch_inventory(tree, self.locations, {'sample'}, prior)
        self.assertEqual(base64.b64decode(restored[key]['reference']['value']), b'original\n')

    def test_compiled_component_builds_once_and_repairs_from_reference(self):
        binary = self.root / 'fake-build-bin'
        binary.mkdir()
        trace = self.root / 'build.log'
        self.write(binary, 'cargo', '''#!/bin/sh
printf 'build\n' >> "$BUILD_TRACE"
for argument in "$@"; do manifest="$argument"; done
root="$(dirname "$manifest")"
mkdir -p "$root/target/release"
printf '#!/bin/sh\necho compiled\n' > "$root/target/release/sample"
chmod 755 "$root/target/release/sample"
''', 0o755)
        self.env['PATH'] = str(binary) + os.pathsep + self.env['PATH']
        self.env['BUILD_TRACE'] = str(trace)
        rule = {'component': 'sample', 'source': 'config/rust/Cargo.toml',
                'destination': 'home:.local/bin/sample', 'build': 'config/rust',
                'binary': 'sample', 'mode': '0755'}
        self.write(self.upstream, 'manifests/update-files.json', json.dumps({'schema': 1, 'rules': self.rules + [rule]}))
        self.write(self.upstream, 'config/rust/Cargo.toml', '[package]\nname="sample"\nversion="0.1.0"\n')
        self.write(self.upstream, 'config/rust/Cargo.lock', '# lock\n')
        self.publish()
        preview = self.update('--dry-run')
        self.assertIn('Fichier à compiler/installer', preview.stdout)
        self.assertFalse(trace.exists())
        self.update()
        installed = self.home / '.local/bin/sample'
        self.assertTrue(installed.exists())
        self.update('--record-component', 'sample')
        self.update()
        installed.unlink()
        self.update()
        self.assertEqual(trace.read_text().splitlines(), ['build'])
        self.assertTrue(installed.exists())

    def signal_during_reload(self, signum):
        trace = self.fake_systemd()
        script = self.root / 'fake-bin/systemctl'
        marker = self.root / 'interrupted-once'
        script.write_text('''#!/bin/sh
printf '%s\n' "$*" >> "$SYSTEMCTL_TRACE"
if [ "$2" = daemon-reload ] && [ ! -e "$INTERRUPTION_MARKER" ]; then
    touch "$INTERRUPTION_MARKER"
    kill -"$INTERRUPTION_SIGNAL" "$PPID"
fi
case "$2" in
 is-active) echo active ;;
 is-enabled) echo enabled ;;
esac
''')
        self.env.update(INTERRUPTION_MARKER=str(marker), INTERRUPTION_SIGNAL=signum)
        rules = self.rules + [{'component': 'sample', 'source': 'config/sample/*.service',
                               'destination': 'config:systemd/user/{name}', 'mode': '0644'}]
        self.write(self.upstream, 'manifests/update-files.json', json.dumps({'schema': 1, 'rules': rules}))
        self.write(self.upstream, 'config/sample/new.service', '[Service]\nExecStart=/bin/true\n')
        self.write(self.upstream, 'config/sample/tool.py', 'print("two")\n')
        self.publish()
        self.update(ok=False)
        return trace

    def test_actual_sigterm_during_reload_restores_files(self):
        self.signal_during_reload('TERM')
        self.assertEqual(self.tool.read_text(), 'print("one")\n')
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.initial)
        self.assertFalse((self.home / '.config/systemd/user/new.service').exists())
        self.assertFalse((self.locations.state / 'pending.json').exists())

    def test_actual_sigkill_is_recovered_on_next_update(self):
        self.signal_during_reload('KILL')
        self.assertTrue((self.locations.state / 'pending.json').exists())
        self.assertEqual(self.tool.read_text(), 'print("two")\n')
        result = self.update()
        self.assertIn('restauration avant nouvelle mise à jour', result.stdout)
        self.assertEqual(self.tool.read_text(), 'print("two")\n')
        self.assertFalse((self.locations.state / 'pending.json').exists())
        self.assertIn('ROLLBACK terminé', (self.locations.state / 'update.log').read_text())
        self.assertIn('déjà à jour', self.update().stdout)

    def test_obsolete_unmodified_proposal_is_removed_with_source(self):
        self.config.write_text('bind = PERSONAL\n')
        self.write(self.upstream, 'config/sample/session.conf', 'bind = NEW\n')
        self.publish()
        self.update()
        proposal = Path(str(self.config) + '.new')
        self.assertTrue(proposal.exists())
        (self.upstream / 'config/sample/session.conf').unlink()
        self.publish()
        self.update()
        self.assertEqual(self.config.read_text(), 'bind = PERSONAL\n')
        self.assertFalse(proposal.exists())

    def test_invalid_unit_is_rejected_before_changing_installed_files(self):
        from files import validate
        for key, content in [('config:systemd/user/bad.service', 'broken unit'),
                             ('home:.local/share/applications/bad.desktop', '[Wrong]\nType=Application')]:
            with self.subTest(key=key), self.assertRaises(UpdateError):
                validate(key, {'kind': 'file', 'mode': 0o644,
                               'value': base64.b64encode(content.encode()).decode()})
