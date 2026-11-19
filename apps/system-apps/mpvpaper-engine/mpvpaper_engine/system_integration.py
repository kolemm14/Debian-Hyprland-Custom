"""Modular Linux system integrations for Lockscreen and Screensaver.

Separates adapters for Hyprland, GNOME, KDE, and provides clean failure
for unsupported desktop environments without assuming a single implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Callable


class SystemIntegrationError(RuntimeError):
    pass


class UnsupportedEnvironmentError(SystemIntegrationError):
    pass


@dataclass(frozen=True)
class DesktopEnvironmentInfo:
    desktop: str
    session_type: str  # wayland, x11, unknown
    lock_supported: bool
    screensaver_supported: bool
    detected_lock_tool: str | None
    detected_idle_tool: str | None
    details: str


def detect_environment(environ: dict[str, str] | None = None, which: Callable[[str], str | None] | None = None) -> DesktopEnvironmentInfo:
    env = environ if environ is not None else os.environ
    _which = which if which is not None else shutil.which

    xdg_desktop = env.get("XDG_CURRENT_DESKTOP", "").strip().lower()
    desktops = [d.strip() for d in xdg_desktop.split(":") if d.strip()]
    session_type = env.get("XDG_SESSION_TYPE", "").strip().lower() or "unknown"

    hyprlock = _which("hyprlock")
    hypridle = _which("hypridle")
    gsettings = _which("gsettings")
    kwriteconfig = _which("kwriteconfig6") or _which("kwriteconfig5")
    swaylock = _which("swaylock")
    loginctl = _which("loginctl")

    is_hyprland = any("hyprland" in d for d in desktops) or bool(env.get("HYPRLAND_INSTANCE_SIGNATURE"))
    is_gnome = any("gnome" in d for d in desktops)
    is_kde = any("kde" in d or "plasma" in d for d in desktops)

    if is_hyprland:
        lock_tool = hyprlock or swaylock or loginctl
        idle_tool = hypridle
        return DesktopEnvironmentInfo(
            desktop="Hyprland",
            session_type="wayland",
            lock_supported=bool(lock_tool),
            screensaver_supported=bool(idle_tool),
            detected_lock_tool="hyprlock" if hyprlock else ("swaylock" if swaylock else ("loginctl" if loginctl else None)),
            detected_idle_tool="hypridle" if hypridle else None,
            details="Hyprland Wayland Compositor (hyprlock / hypridle)",
        )

    if is_gnome:
        return DesktopEnvironmentInfo(
            desktop="GNOME",
            session_type=session_type,
            lock_supported=bool(gsettings),
            screensaver_supported=bool(gsettings),
            detected_lock_tool="gsettings (org.gnome.desktop.screensaver)" if gsettings else None,
            detected_idle_tool="gsettings (org.gnome.desktop.session idle-delay)" if gsettings else None,
            details="GNOME Desktop Environment",
        )

    if is_kde:
        return DesktopEnvironmentInfo(
            desktop="KDE Plasma",
            session_type=session_type,
            lock_supported=bool(kwriteconfig or loginctl),
            screensaver_supported=bool(kwriteconfig),
            detected_lock_tool="kscreenlocker" if kwriteconfig else ("loginctl" if loginctl else None),
            detected_idle_tool="kscreenlocker_greet" if kwriteconfig else None,
            details="KDE Plasma Desktop",
        )

    # Fallback / other
    generic_lock = swaylock or hyprlock or loginctl
    return DesktopEnvironmentInfo(
        desktop=xdg_desktop or "Generic Linux",
        session_type=session_type,
        lock_supported=bool(generic_lock),
        screensaver_supported=False,
        detected_lock_tool="swaylock" if swaylock else ("loginctl" if loginctl else None),
        detected_idle_tool=None,
        details="Environnement Linux générique ou non documenté",
    )


class BaseSystemAdapter:
    def __init__(self, runner: Callable = subprocess.run):
        self.runner = runner

    def get_capabilities(self) -> dict[str, Any]:
        raise NotImplementedError

    def apply_lockscreen(self, wallpaper_path: str, preview_only: bool = False) -> dict[str, Any]:
        raise NotImplementedError

    def apply_screensaver(self, wallpaper_path: str | None, idle_delay_seconds: int = 300, preview_only: bool = False) -> dict[str, Any]:
        raise NotImplementedError


class HyprlandAdapter(BaseSystemAdapter):
    """Hyprland integration using hyprlock and hypridle configuration."""

    def __init__(self, runner: Callable = subprocess.run, config_dir: Path | None = None):
        super().__init__(runner)
        self.config_dir = config_dir or (Path.home() / ".config" / "hypr")

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "desktop": "Hyprland",
            "lockscreen": {
                "supported": True,
                "tool": "hyprlock",
                "custom_wallpaper": True,
                "preview_supported": True,
            },
            "screensaver": {
                "supported": True,
                "tool": "hypridle",
                "idle_delay_adjustable": True,
                "preview_supported": True,
            },
        }

    def apply_lockscreen(self, wallpaper_path: str, preview_only: bool = False) -> dict[str, Any]:
        target = Path(wallpaper_path)
        if not target.exists():
            raise FileNotFoundError(f"Fichier de fond introuvable : {wallpaper_path}")

        rendered_config = f"""# Généré par MPVpaper Hub pour hyprlock
background {{
    monitor =
    path = {target.resolve()}
    blur_passes = 1
    blur_size = 5
}}

input-field {{
    monitor =
    size = 200, 50
    outline_thickness = 3
    dots_size = 0.33
    fade_on_empty = false
}}
"""
        if preview_only:
            return {
                "ok": True,
                "preview_only": True,
                "adapter": "Hyprland",
                "target_wallpaper": str(target.resolve()),
                "generated_config": rendered_config,
            }

        target_file = self.config_dir / "hyprlock-mpvpaper.conf"
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(rendered_config, encoding="utf-8")

        return {
            "ok": True,
            "preview_only": False,
            "adapter": "Hyprland",
            "configured_file": str(target_file),
            "target_wallpaper": str(target.resolve()),
        }

    def apply_screensaver(self, wallpaper_path: str | None, idle_delay_seconds: int = 300, preview_only: bool = False) -> dict[str, Any]:
        if idle_delay_seconds <= 0:
            raise ValueError("Le délai d'inactivité doit être positif.")

        rendered_config = f"""# Configuration hypridle générée par MPVpaper Hub
general {{
    lock_cmd = pidof hyprlock || hyprlock
    before_sleep_cmd = loginctl lock-session
}}

listener {{
    timeout = {idle_delay_seconds}
    on-timeout = hyprctl dispatch dpms off
    on-resume = hyprctl dispatch dpms on
}}
"""
        if preview_only:
            return {
                "ok": True,
                "preview_only": True,
                "adapter": "Hyprland",
                "idle_delay_seconds": idle_delay_seconds,
                "wallpaper": wallpaper_path,
                "generated_config": rendered_config,
            }

        target_file = self.config_dir / "hypridle-mpvpaper.conf"
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(rendered_config, encoding="utf-8")

        return {
            "ok": True,
            "preview_only": False,
            "adapter": "Hyprland",
            "configured_file": str(target_file),
            "idle_delay_seconds": idle_delay_seconds,
        }


class GnomeAdapter(BaseSystemAdapter):
    """GNOME integration using gsettings."""

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "desktop": "GNOME",
            "lockscreen": {
                "supported": True,
                "tool": "gsettings org.gnome.desktop.screensaver",
                "custom_wallpaper": True,
                "preview_supported": True,
            },
            "screensaver": {
                "supported": True,
                "tool": "gsettings org.gnome.desktop.session",
                "idle_delay_adjustable": True,
                "preview_supported": True,
            },
        }

    def apply_lockscreen(self, wallpaper_path: str, preview_only: bool = False) -> dict[str, Any]:
        target = Path(wallpaper_path)
        if not target.exists():
            raise FileNotFoundError(f"Fichier de fond introuvable : {wallpaper_path}")

        uri = target.resolve().as_uri()
        cmd = ["gsettings", "set", "org.gnome.desktop.screensaver", "picture-uri", uri]

        if preview_only:
            return {"ok": True, "preview_only": True, "adapter": "GNOME", "command": cmd, "uri": uri}

        res = self.runner(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            raise SystemIntegrationError(f"Échec gsettings lockscreen : {res.stderr.strip()}")

        return {"ok": True, "preview_only": False, "adapter": "GNOME", "uri": uri}

    def apply_screensaver(self, wallpaper_path: str | None, idle_delay_seconds: int = 300, preview_only: bool = False) -> dict[str, Any]:
        if idle_delay_seconds <= 0:
            raise ValueError("Le délai d'inactivité doit être positif.")

        cmd = ["gsettings", "set", "org.gnome.desktop.session", "idle-delay", str(idle_delay_seconds)]

        if preview_only:
            return {"ok": True, "preview_only": True, "adapter": "GNOME", "command": cmd, "idle_delay": idle_delay_seconds}

        res = self.runner(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            raise SystemIntegrationError(f"Échec gsettings idle-delay : {res.stderr.strip()}")

        return {"ok": True, "preview_only": False, "adapter": "GNOME", "idle_delay": idle_delay_seconds}


class KdeAdapter(BaseSystemAdapter):
    """KDE Plasma integration."""

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "desktop": "KDE Plasma",
            "lockscreen": {
                "supported": True,
                "tool": "kscreenlockerrc",
                "custom_wallpaper": True,
                "preview_supported": True,
            },
            "screensaver": {
                "supported": True,
                "tool": "kscreenlockerrc Timeout",
                "idle_delay_adjustable": True,
                "preview_supported": True,
            },
        }

    def apply_lockscreen(self, wallpaper_path: str, preview_only: bool = False) -> dict[str, Any]:
        target = Path(wallpaper_path)
        if not target.exists():
            raise FileNotFoundError(f"Fichier de fond introuvable : {wallpaper_path}")

        bin_name = "kwriteconfig6" if shutil.which("kwriteconfig6") else "kwriteconfig5"
        cmd = [bin_name, "--file", "kscreenlockerrc", "--group", "Greeter", "--group", "Wallpaper", "--group", "org.kde.image", "--group", "General", "--key", "Image", str(target.resolve())]

        if preview_only:
            return {"ok": True, "preview_only": True, "adapter": "KDE Plasma", "command": cmd}

        res = self.runner(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            raise SystemIntegrationError(f"Échec configuration KDE lockscreen : {res.stderr.strip()}")

        return {"ok": True, "preview_only": False, "adapter": "KDE Plasma", "path": str(target.resolve())}

    def apply_screensaver(self, wallpaper_path: str | None, idle_delay_seconds: int = 300, preview_only: bool = False) -> dict[str, Any]:
        minutes = max(1, idle_delay_seconds // 60)
        bin_name = "kwriteconfig6" if shutil.which("kwriteconfig6") else "kwriteconfig5"
        cmd = [bin_name, "--file", "kscreenlockerrc", "--group", "Daemon", "--key", "Timeout", str(minutes)]

        if preview_only:
            return {"ok": True, "preview_only": True, "adapter": "KDE Plasma", "command": cmd, "minutes": minutes}

        res = self.runner(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            raise SystemIntegrationError(f"Échec configuration KDE screensaver : {res.stderr.strip()}")

        return {"ok": True, "preview_only": False, "adapter": "KDE Plasma", "minutes": minutes}


class UnsupportedAdapter(BaseSystemAdapter):
    """Fallback adapter that cleanly reports unsupported status."""

    def __init__(self, desktop_name: str):
        super().__init__()
        self.desktop_name = desktop_name

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "desktop": self.desktop_name,
            "lockscreen": {
                "supported": False,
                "reason": f"Gestionnaire de verrouillage non géré pour l'environnement '{self.desktop_name}'.",
                "preview_supported": False,
            },
            "screensaver": {
                "supported": False,
                "reason": f"Gestionnaire d'inactivité non géré pour l'environnement '{self.desktop_name}'.",
                "preview_supported": False,
            },
        }

    def apply_lockscreen(self, wallpaper_path: str, preview_only: bool = False) -> dict[str, Any]:
        raise UnsupportedEnvironmentError(
            f"L'environnement de bureau '{self.desktop_name}' ne permet pas la configuration automatisée du verrouillage."
        )

    def apply_screensaver(self, wallpaper_path: str | None, idle_delay_seconds: int = 300, preview_only: bool = False) -> dict[str, Any]:
        raise UnsupportedEnvironmentError(
            f"L'environnement de bureau '{self.desktop_name}' ne permet pas la configuration automatisée de l'écran de veille."
        )


def get_adapter(environ: dict[str, str] | None = None, runner: Callable = subprocess.run) -> BaseSystemAdapter:
    info = detect_environment(environ)
    if info.desktop == "Hyprland":
        return HyprlandAdapter(runner=runner)
    if info.desktop == "GNOME":
        return GnomeAdapter(runner=runner)
    if info.desktop == "KDE Plasma":
        return KdeAdapter(runner=runner)
    return UnsupportedAdapter(desktop_name=info.desktop)
