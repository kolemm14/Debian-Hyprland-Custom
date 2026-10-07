"""Exercise async Steam wait callbacks without opening Steam or real windows."""
import sys
from pathlib import Path
from types import SimpleNamespace, MethodType
import unittest
from unittest import mock
sys.path.insert(0, str(Path(__file__).parents[1]))


class SteamWaitTests(unittest.TestCase):
    def setUp(self):
        try:
            from mpvpaper_engine.gui import EngineWindow, GLib
        except (ImportError, ValueError) as error:
            self.skipTest(str(error))
        self.glib = GLib
        self.window = SimpleNamespace(
            _steam_wait_token=None, _steam_wait_timer=0,
            steam_cancel_button=mock.Mock(), browser_firefox_retry=mock.Mock(),
            browser_status=mock.Mock(), tasks=mock.Mock(), backend=mock.Mock(),
            reload=mock.Mock(), select=mock.Mock())
        for name in ('_watch_steam_local', '_cancel_steam_wait'):
            setattr(self.window, name, MethodType(getattr(EngineWindow, name), self.window))
        self.addCleanup(lambda: self.window._cancel_steam_wait(silent=True))

    def test_complete_project_is_selected_without_apply(self):
        self.window._watch_steam_local('123')
        operation, success, failure = self.window.tasks.run.call_args.args
        item = SimpleNamespace(title='Scene', media_type=SimpleNamespace(value='scene'))
        self.window.backend.import_steam_local.return_value = item
        success(operation())
        self.window.select.assert_called_once_with(item)
        self.window.reload.assert_called_once_with(scan=False)
        self.assertIsNone(self.window._steam_wait_token)
        self.assertIn('linux-wallpaperengine', self.window.browser_status.set_text.call_args.args[0])

    def test_cancel_ignores_inflight_completion(self):
        self.window._watch_steam_local('123')
        success = self.window.tasks.run.call_args.args[1]
        self.window._cancel_steam_wait()
        success(SimpleNamespace(title='late'))
        self.window.select.assert_not_called()
        self.window.reload.assert_not_called()

    def test_new_request_ignores_old_request(self):
        self.window._watch_steam_local('123')
        success = self.window.tasks.run.call_args.args[1]
        self.window._watch_steam_local('456')
        success(None)
        self.assertEqual(self.window._steam_wait_timer, 0)
        self.window.select.assert_not_called()

    def test_pending_check_schedules_only_one_timer(self):
        self.window._watch_steam_local('123')
        self.window.tasks.run.call_args.args[1](None)
        self.assertGreater(self.window._steam_wait_timer, 0)
        self.window._cancel_steam_wait()
        self.assertEqual(self.window._steam_wait_timer, 0)

    def test_timeout_stops_watching(self):
        with mock.patch.object(self.glib, 'get_monotonic_time', side_effect=[0, 301_000_000]):
            self.window._watch_steam_local('123')
            self.window.tasks.run.call_args.args[1](None)
        self.assertIsNone(self.window._steam_wait_token)
        self.assertEqual(self.window._steam_wait_timer, 0)


if __name__ == '__main__':
    unittest.main()
