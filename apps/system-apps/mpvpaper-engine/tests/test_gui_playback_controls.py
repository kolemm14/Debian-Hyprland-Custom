"""GTK callbacks capture their target/value before queuing background work."""
import sys
from pathlib import Path
from types import SimpleNamespace, MethodType
import unittest
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).parents[1]))

class PlaybackCallbacks(unittest.TestCase):
    def test_queued_command_keeps_original_output_and_speed(self):
        try:
            from mpvpaper_engine.gui import EngineWindow
        except (ImportError, ValueError) as error:
            self.skipTest(str(error))
        window=SimpleNamespace(_output=Mock(return_value='DP-1'), _dispatch=Mock(), backend=Mock())
        window._playback_action=MethodType(EngineWindow._playback_action,window)
        dropdown=Mock();dropdown.get_selected.return_value=3
        EngineWindow._speed_changed(window,dropdown,None)
        window._output.return_value='DP-2';dropdown.get_selected.return_value=0
        window._dispatch.call_args.args[0]()
        window.backend.playback.assert_called_once_with('speed','DP-1',1.25)
