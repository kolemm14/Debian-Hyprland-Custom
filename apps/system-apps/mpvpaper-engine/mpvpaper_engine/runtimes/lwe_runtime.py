"""Optional LWE Scene adapter using one systemd user unit per output."""
from dataclasses import asdict, dataclass
from pathlib import Path
import shutil
import subprocess

from ..config import validate_output_name
from ..systemd import SystemdManager, unit_for_output, runtime_description
from .project_detector import Project


@dataclass(frozen=True)
class Capabilities:
    runtime_available: bool
    executable: str | None
    scene_cli: bool
    cef_available: bool | None = None
    assets_dir: str | None = None
    error: str | None = None
    cef_sandbox: str = "unknown"
    web_enabled: bool = False

    def to_dict(self):
        result = asdict(self)
        result.update(engine_available=self.runtime_available,
                      runtime_ready=self.runtime_available and self.scene_cli and bool(self.assets_dir) and not self.error,
                      missing_requirements=([self.error] if self.error else []))
        return result


class LweRuntime:
    def __init__(self, *, executable=None, assets_dir=None, runner=subprocess.run, systemd=None):
        self.executable = executable or 'linux-wallpaperengine'
        self.assets_dir = Path(assets_dir).expanduser().resolve() if assets_dir else None
        self.runner = runner
        self.systemd = systemd or SystemdManager(runner=runner)

    def capabilities(self) -> Capabilities:
        executable = shutil.which(str(self.executable))
        if not executable:
            return Capabilities(False, None, False, error='linux-wallpaperengine is not installed')
        try:
            result = self.runner([executable, '--help'], capture_output=True, text=True,
                                 timeout=5, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            return Capabilities(True, executable, False, error=str(error))
        help_text = result.stdout + result.stderr
        required = ('--screen-root', '--bg', '--assets-dir', '--fps', '--silent')
        supported = result.returncode == 0 and all(flag in help_text for flag in required)
        assets = self.find_assets()
        valid_assets = assets is not None
        error = None if supported else 'LWE command-line capabilities could not be verified'
        if not valid_assets:
            error = error or 'Provide a non-empty official assets directory with --assets-dir'
        return Capabilities(True, executable, supported, assets_dir=str(assets) if valid_assets else None,
                            error=error)

    def find_assets(self):
        home = Path.home()
        roots = [home/p for p in ('.steam/steam', '.local/share/Steam',
                 '.var/app/com.valvesoftware.Steam/.local/share/Steam',
                 'snap/steam/common/.local/share/Steam')]
        # Additional Steam libraries, without importing or downloading Steam content.
        import re
        for root in list(roots):
            manifest = root/'steamapps/libraryfolders.vdf'
            if manifest.is_file():
                try:
                    roots.extend(Path(p) for p in re.findall(r'"path"\s*"([^"\n]+)"', manifest.read_text()))
                except OSError:
                    continue
        candidates = [self.assets_dir] if self.assets_dir else [
            root/'steamapps/common'/name/'assets' for root in roots
            for name in ('wallpaper_engine', 'Wallpaper Engine', 'wallpaper engine')]
        for candidate in candidates:
            try:
                if candidate and candidate.is_dir() and any(candidate.iterdir()):
                    return candidate.resolve()
            except OSError:
                continue
        return None

    def command(self, output: str, project: Project, *, fps=30) -> list[str]:
        if not validate_output_name(output) or output == '*':
            raise ValueError('A concrete output is required; wildcard support is deferred')
        if project.kind != 'scene':
            raise ValueError('LWE currently accepts Scene only; Web execution is disabled')
        if isinstance(fps, bool) or not isinstance(fps, int) or not 1 <= fps <= 240:
            raise ValueError('FPS must be an integer between 1 and 240')
        cap = self.capabilities()
        if cap.error:
            raise RuntimeError(cap.error)
        return [cap.executable, '--assets-dir', cap.assets_dir, '--fps', str(fps),
                '--silent', '--screen-root', output, '--bg', str(project.path)]

    def start_command(self, output: str, command: list[str]):
        # Shared output unit namespace prevents overlapping owned renderers.
        self.systemd._run(['systemd-run', '--user', '--quiet',
                           '--property=Type=exec', f'--unit={unit_for_output(output)}',
                           f'--description={runtime_description("linux-wallpaperengine", command[-1])}',
                           *command], check=True)
