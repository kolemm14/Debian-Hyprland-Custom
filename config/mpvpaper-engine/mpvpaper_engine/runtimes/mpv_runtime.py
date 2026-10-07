"""Reuse MPVpaper's existing playback controller for simple media."""
from ..config import load_config
from ..playback import PlaybackController


class MpvRuntime:
    def __init__(self, playback=None):
        self.playback = playback or PlaybackController(load_config())

    def start(self, output, project):
        if project.kind not in {'video', 'image'} or project.media is None:
            raise ValueError('MPV requires original video or image media')
        return self.playback.play(output, project.media)
