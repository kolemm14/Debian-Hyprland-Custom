"""Small helpers for the private, per-user MPVpaper Hub webview service."""
from __future__ import annotations

import socket
from pathlib import Path


def available_loopback_port() -> int:
    """Choose an ephemeral port without ever binding the Hub to a public interface."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def locate_hub_directory(module_file: str | Path, home: str | Path) -> Path | None:
    module_path = Path(module_file).resolve()
    home_path = Path(home).expanduser()
    candidates = (
        module_path.parent.parent / "hub",
        home_path / "Debian-Hyprland-Custom" / "apps" / "system-apps" / "mpvpaper-engine" / "hub",
        home_path / ".local" / "lib" / "mpvpaper-engine" / "hub",
    )
    return next((path for path in candidates if
                 (path / "package.json").is_file() and
                 (path / "scripts" / "run-framework.mjs").is_file()), None)


def hub_embedded_url(port: int) -> str:
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("port Hub invalide")
    return f"http://127.0.0.1:{port}/?embedded=engine"


def production_hub_command(hub_dir: str | Path, node_bin: str | Path,
                           port: int, persist_dir: str | Path) -> list[str]:
    """Build a loopback-only Node bridge in front of the prebuilt Hub Worker."""
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("port Hub invalide")
    root = Path(hub_dir)
    required = (
        root / "scripts" / "local-hub-server.mjs",
        root / "scripts" / "sites-env.mjs",
        root / "node_modules" / "wrangler" / "bin" / "wrangler.js",
        root / "dist" / "server" / "wrangler.json",
    )
    missing = [path for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"MPVpaper Hub précompilé incomplet : {missing[0]}")
    return [
        str(node_bin), str(root / "scripts" / "local-hub-server.mjs"),
        str(port), str(Path(persist_dir)),
    ]
