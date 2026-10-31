"""Single per-screen authority, durable intentions and independent runtime failures."""
import logging
from pathlib import Path
import shutil
import threading

from ..config import validate_output_name, save_config, load_config
from ..models import OutputMode, PlaybackStatus
from ..systemd import SystemdManager, runtime_description
from .project_detector import detect_project
from .lwe_runtime import LweRuntime
from .mpv_runtime import MpvRuntime

LOGGER = logging.getLogger(__name__)


class RuntimeManager:
    def __init__(self, *, mpv=None, lwe=None, systemd=None, config=None, paths=None,
                 monitor_detector=None, persist=False):
        self.systemd = systemd or SystemdManager()
        self.mpv = mpv or MpvRuntime()
        self.lwe = lwe or LweRuntime(systemd=self.systemd)
        self.config, self.paths, self.persist = config, paths, persist
        self.monitor_detector = monitor_detector
        self.records = {}
        self._connected = set()
        self._lock = threading.RLock()

    def connected(self):
        if self.monitor_detector is None:
            from ..monitors import detect_monitors
            return {m.name for m in detect_monitors()}
        return {m.name for m in self.monitor_detector()}

    @staticmethod
    def validate_output(output):
        if not validate_output_name(output) or output == '*':
            raise ValueError('A concrete monitor name is required')

    def diagnose(self, path, *, options=None):
        try:
            project = detect_project(path)
        except (ValueError, OSError) as error:
            return {'type': 'unknown', 'runtime': None, 'engine_available': False,
                    'runtime_available': False, 'runtime_ready': False,
                    'wallpaper_compatible': False, 'compatibility': 'incompatible',
                    'reason': str(error), 'missing_requirements': [str(error)], 'web_enabled': False}
        if project.kind in {'video', 'image'}:
            available = shutil.which('mpvpaper') is not None
            return {'type': project.kind, 'runtime': 'mpvpaper',
                    'engine_available': available, 'runtime_available': available,
                    'runtime_ready': available, 'wallpaper_compatible': None,
                    'compatibility': 'unknown', 'web_enabled': False,
                    'missing_requirements': [] if available else ['mpvpaper missing'],
                    'reason': 'Media rendering not yet verified' if available else 'mpvpaper missing'}
        caps = self._lwe(options).capabilities().to_dict()
        reason = 'Web blocked: CEF security policy not validated' if project.kind == 'web' else caps['error']
        return {**caps, 'type': project.kind, 'runtime': 'linux-wallpaperengine',
                'wallpaper_compatible': None, 'compatibility': 'unknown',
                'runtime_ready': caps['runtime_ready'] and project.kind != 'web',
                'reason': reason, 'blocked_reason': reason}

    def _lwe(self, options):
        if options and options.get('assets_dir'):
            return LweRuntime(executable=self.lwe.executable, assets_dir=options['assets_dir'],
                              runner=self.lwe.runner, systemd=self.systemd)
        return self.lwe

    def _intent(self, output):
        if self.config is None:
            return {}
        return self.config.outputs.get(output, {})

    def _save(self):
        if self.persist and self.config is not None:
            # GUI may have saved HUD/theme settings since this service started.
            current = load_config(self.paths)
            for section in ('ui', 'theme_sync', 'cache', 'automation'):
                setattr(self.config, section, getattr(current, section))
            save_config(self.config, self.paths)

    def apply(self, output, path=None, *, fps=30, options=None, remember=True):
        if output == '*':
            return self.apply_all(path, options=options, remember=remember)
        self.validate_output(output)
        with self._lock:
            if output not in self.connected():
                raise ValueError(f'Monitor disconnected: {output}')
            project = detect_project(path)
            if project.kind == 'web':
                raise ValueError('Web execution is disabled pending CEF security validation')
            runtime = 'linux-wallpaperengine' if project.kind == 'scene' else 'mpvpaper'
            options = dict(options or {})
            options = {'fps': options.get('fps', fps), **({'assets_dir': options['assets_dir']} if options.get('assets_dir') else {})}
            lwe = self._lwe(options)
            command = lwe.command(output, project, fps=options['fps']) if project.kind == 'scene' else None
            if command is None and shutil.which('mpvpaper') is None:
                raise RuntimeError('mpvpaper is not installed')
            if self.systemd.unit_status('*') in {'active', 'activating', 'deactivating'}:
                raise RuntimeError('Stop the legacy wildcard wallpaper before using per-screen runtimes')
            before = self.status(output)
            same = before['state'] == 'active' and before.get('description') == runtime_description(runtime, project.path)
            if same:
                same = before.get('runtime_options', {'fps': 30}) == options
            strategy = 'unchanged'
            if not same:
                self.systemd.stop_checked(output)
                try:
                    if command:
                        lwe.start_command(output, command)
                        strategy = runtime
                    else:
                        strategy = self.mpv.start(output, project)
                except (RuntimeError, ValueError, OSError) as error:
                    self.records[output] = {'screen': output, 'wallpaper': str(project.path),
                        'runtime': runtime, 'project_type': project.kind, 'state': 'failed', 'reason': str(error)}
                    raise
            self.records[output] = {'screen': output, 'wallpaper': str(project.path),
                'runtime': runtime, 'project_type': project.kind, 'runtime_options': options}
            if remember and self.config is not None:
                self.config.mode = OutputMode.INDEPENDENT
                self.config.outputs.pop('*', None)
                self.config.outputs[output] = {**self._intent(output),
                    'wallpaper': str(project.path), 'project_type': project.kind,
                    'runtime': runtime, 'runtime_options': options, 'enabled': True, 'autostart': True}
                self._save()
            return strategy

    def apply_all(self, path=None, *, options=None, remember=True):
        results = {}
        for output in sorted(self.connected()):
            intent = self._intent(output)
            wallpaper = path or intent.get('wallpaper')
            if not wallpaper or (path is None and not intent.get('enabled', intent.get('autostart', True))):
                results[output] = {'ok': True, 'state': 'skipped'}
                continue
            try:
                strategy = self.apply(output, wallpaper, options=options if path else intent.get('runtime_options'), remember=remember)
                results[output] = {'ok': True, 'strategy': strategy}
            except (RuntimeError, ValueError, OSError) as error:
                LOGGER.warning('Runtime apply failed for %s: %s', output, error)
                results[output] = {'ok': False, 'error': str(error)}
        return results

    def stop(self, output, *, remember=True):
        if output == '*':
            return self.stop_all(remember=remember)
        self.validate_output(output)
        with self._lock:
            self.systemd.stop_checked(output)
            self.records.pop(output, None)
            if remember and self.config is not None and output in self.config.outputs:
                self.config.outputs[output]['enabled'] = False
                self.config.outputs[output]['autostart'] = False
                self._save()
        return {'ok': True}

    def stop_all(self, *, remember=True):
        outputs = set(self.records) | (set(self.config.outputs) if self.config else set()) | self.connected()
        results = {}
        for output in outputs:
            if output == '*':
                continue
            try:
                results[output] = self.stop(output, remember=remember)
            except (RuntimeError, OSError) as error:
                results[output] = {'ok': False, 'error': str(error)}
        # Also clean up pre-multi-runtime wildcard unit, explicitly requested here.
        try:
            self.systemd.stop_checked('*')
        except (RuntimeError, OSError) as error:
            results['*'] = {'ok': False, 'error': str(error)}
        if remember and self.config is not None and '*' in self.config.outputs:
            self.config.outputs['*'].update(enabled=False, autostart=False)
            self._save()
        return results

    def status(self, output):
        self.validate_output(output)
        details = self.systemd.details(output)
        record = self.records.get(output, self._intent(output))
        return {**record, **details, 'screen': output}

    def restore(self):
        with self._lock:
            if self.config is None or self.config.mode == OutputMode.DISABLED:
                return {}
            self._connected = self.connected()
            wildcard = self.config.outputs.get('*', {})
            if self.config.mode == OutputMode.SAME and wildcard:
                if not wildcard.get('enabled', wildcard.get('autostart', True)):
                    return {}
                return self.apply_all(wildcard.get('wallpaper'), options=wildcard.get('runtime_options'), remember=False)
            return self.apply_all(remember=False)

    def reconcile(self):
        """Called on Hyprland monitor events, never a continuous process scan."""
        with self._lock:
            current = self.connected()
            results = {}
            for output in self._connected - current:
                try:
                    results[output] = self.stop(output, remember=False)
                except (RuntimeError, OSError) as error:
                    results[output] = {'ok': False, 'error': str(error)}
            for output in current - self._connected:
                intent = self._intent(output)
                if self.config and self.config.mode == OutputMode.SAME:
                    intent = self.config.outputs.get('*', {})
                if intent.get('wallpaper') and intent.get('enabled', intent.get('autostart', True)):
                    try:
                        results[output] = {'ok': True, 'strategy': self.apply(output, intent['wallpaper'],
                            options=intent.get('runtime_options'), remember=False)}
                    except (RuntimeError, ValueError, OSError) as error:
                        results[output] = {'ok': False, 'error': str(error)}
            self._connected = current
            return results
