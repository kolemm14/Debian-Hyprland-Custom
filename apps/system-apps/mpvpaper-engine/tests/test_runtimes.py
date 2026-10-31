import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mpvpaper_engine.runtimes.project_detector import detect_project
from mpvpaper_engine.runtimes.lwe_runtime import LweRuntime
from mpvpaper_engine.runtimes.runtime_manager import RuntimeManager


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root/'project'
        self.project.mkdir()
        (self.project/'scene.pkg').write_bytes(b'scene')
        self.manifest('scene', 'scene.pkg')
        self.assets = self.root/'assets'
        self.assets.mkdir()
        (self.assets/'test').touch()
        self.systemd = Mock()
        self.systemd.unit_status.return_value = 'inactive'
        self.systemd.details.return_value = {'state': 'inactive', 'description': '', 'process': 0}
        self.runner = Mock(return_value=subprocess.CompletedProcess([], 0,
            '--screen-root --bg --assets-dir --fps --silent', ''))
        self.lwe = LweRuntime(executable='/usr/bin/lwe', assets_dir=self.assets,
                              runner=self.runner, systemd=self.systemd)
        self.mpv = Mock()
        from mpvpaper_engine.monitors import MonitorInfo
        self.manager = RuntimeManager(lwe=self.lwe, mpv=self.mpv, systemd=self.systemd,
            monitor_detector=lambda: [MonitorInfo('eDP-1'), MonitorInfo('HDMI-A-1')])
        self.which = patch('shutil.which', side_effect=lambda x: str(x))
        self.which.start()
        self.addCleanup(self.which.stop)

    def manifest(self, kind, entry):
        (self.project/'project.json').write_text(json.dumps({'type':kind, 'file':entry}))

    def test_scene_command_and_output(self):
        self.assertEqual(self.manager.apply('HDMI-A-1', self.project), 'linux-wallpaperengine')
        command = self.systemd._run.call_args.args[0]
        self.assertIn('--unit=mpvpaper-engine-wallpaper-HDMI-A-1.service', command)
        self.assertEqual(command[-4:], ['--screen-root', 'HDMI-A-1', '--bg', str(self.project)])
        self.mpv.start.assert_not_called()

    def test_video_and_scene_independent(self):
        media = self.root/'movie.mp4'
        media.touch()
        self.manager.apply('eDP-1', media)
        self.manager.apply('HDMI-A-1', self.project)
        self.assertEqual(self.mpv.start.call_args.args[0], 'eDP-1')
        self.assertEqual(self.mpv.start.call_args.args[1].media, media)
        self.assertNotIn('eDP-1', str(self.systemd._run.call_args_list))

    def test_web_blocked_before_any_command(self):
        self.manifest('web', 'scene.pkg')
        with self.assertRaisesRegex(ValueError, 'Web execution'):
            self.manager.apply('HDMI-A-1', self.project)
        self.runner.assert_not_called()
        self.systemd._run.assert_not_called()

    def test_missing_runtime_preserves_previous(self):
        with patch('shutil.which', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'not installed'):
                self.manager.apply('HDMI-A-1', self.project)
        self.systemd._run.assert_not_called()

    def test_missing_assets_preserves_previous(self):
        self.lwe.assets_dir = self.root/'absent'
        with self.assertRaisesRegex(RuntimeError, 'assets'):
            self.manager.apply('HDMI-A-1', self.project)
        self.systemd._run.assert_not_called()

    def test_incompatible_cli_and_timeout(self):
        self.runner.return_value.stdout = '--screen-root'
        self.assertFalse(self.lwe.capabilities().scene_cli)
        self.runner.side_effect = subprocess.TimeoutExpired('lwe', 5)
        self.assertIsNotNone(self.lwe.capabilities().error)

    def test_unknown_compatibility_and_cef(self):
        diagnostic = self.manager.diagnose(self.project)
        self.assertTrue(diagnostic['runtime_available'])
        self.assertIsNone(diagnostic['wallpaper_compatible'])
        self.assertIsNone(diagnostic['cef_available'])

    def test_traversal_and_symlink_rejected(self):
        outside = self.root/'outside.mp4'; outside.touch()
        self.manifest('video', '../outside.mp4')
        with self.assertRaises(ValueError): detect_project(self.project)
        (self.project/'linked.mp4').symlink_to(outside)
        self.manifest('video', 'linked.mp4')
        with self.assertRaises(ValueError): detect_project(self.project)

    def test_no_preview_fallback(self):
        self.manifest('video', 'absent.mp4')
        (self.project/'preview.jpg').touch()
        with self.assertRaises(FileNotFoundError): detect_project(self.project)

    def test_wildcard_rejected_and_existing_wildcard_preserved(self):
        result = self.manager.apply('*', self.project)
        self.assertTrue(all(v['ok'] for v in result.values()))
        self.systemd.reset_mock()
        self.systemd.unit_status.return_value = 'active'
        with self.assertRaisesRegex(RuntimeError, 'wildcard'):
            self.manager.apply('HDMI-A-1', self.project)
        self.systemd._run.assert_not_called()

    def test_replacement_stops_only_selected_output(self):
        self.systemd.unit_status.side_effect = lambda output: 'active' if output=='HDMI-A-1' else 'inactive'
        self.manager.apply('HDMI-A-1', self.project)
        self.systemd.stop_checked.assert_called_once_with('HDMI-A-1')

    def test_failed_stop_does_not_launch(self):
        self.systemd.unit_status.side_effect = lambda output: 'active' if output=='HDMI-A-1' else 'inactive'
        self.systemd.stop_checked.side_effect = RuntimeError('stop failed')
        with self.assertRaisesRegex(RuntimeError, 'stop failed'):
            self.manager.apply('HDMI-A-1', self.project)
        self.systemd._run.assert_not_called()
