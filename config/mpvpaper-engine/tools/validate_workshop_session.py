#!/usr/bin/env python3
"""Opt-in real Hyprland smoke test, with isolated state and transient units.

Uses generated local Workshop fixtures unless two installed Workshop IDs are
supplied. Does not restart Hyprland: restoration here is an engine restart.
"""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mpvpaper_download import import_workshop_item
from mpvpaper_engine.config import load_config, save_config
from mpvpaper_engine.gui_backend import GuiBackend
from mpvpaper_engine.monitors import detect_monitors
from mpvpaper_engine.paths import EnginePaths
from mpvpaper_engine.playback import MpvClient, PlaybackError
from mpvpaper_engine.service import EngineService
from mpvpaper_engine.steam_workshop import SteamWorkshopResolver
from mpvpaper_engine.systemd import SystemdManager, UNIT_PREFIX


class PreserveDesktopProviders:
    def stop_conflicting(self):
        # This test's surfaces disappear at cleanup; keep the user's provider alive.
        return []


def fixture(root, item_id, kind):
    item = root / "steamapps/workshop/content/431960" / item_id
    item.mkdir(parents=True)
    media = item / ("original.mp4" if kind == "video" else "original.png")
    options = ["-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p"] if kind == "video" else ["-frames:v", "1", "-threads", "1"]
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
        "testsrc2=size=640x360:rate=24", *options, str(media),
    ], check=True, timeout=30)
    (item / "preview.png").write_bytes(b"This must never be selected")
    (item / "project.json").write_text(json.dumps({
        "type": kind, "file": media.name, "preview": "preview.png",
        "title": f"Validation {kind}",
    }))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", action="store_true")
    parser.add_argument("--video-id")
    parser.add_argument("--image-id")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if not args.fixtures and not (args.video_id and args.image_id):
        parser.error("supply --fixtures or both --video-id and --image-id")
    monitors = detect_monitors()
    if not monitors:
        raise RuntimeError("No active Hyprland outputs")
    inventory = json.loads(subprocess.run(["hyprctl", "-j", "monitors"], capture_output=True, text=True, check=True, timeout=5).stdout)
    report = {"hyprland_outputs": [{k: m.get(k) for k in ("name", "description", "width", "height")} for m in inventory], "source": "generated fixtures" if args.fixtures else "installed Workshop items",
              "monitors": [asdict(m) for m in monitors], "checks": [],
              "two_physical_outputs": "not verified", "session_restart": "not performed"}
    prefix = f"mpvpaper-workshop-validation-{os.getpid()}"

    def runner(command, **kwargs):
        command = [part.replace(UNIT_PREFIX, prefix) for part in command]
        return subprocess.run(command, **kwargs)

    systemd = SystemdManager(runner=runner)
    service = None
    try:
        with tempfile.TemporaryDirectory(prefix="mpv-we-") as directory:
            root = Path(directory)
            paths = EnginePaths.from_environment({
                "XDG_CONFIG_HOME": str(root / "c"), "XDG_DATA_HOME": str(root / "d"),
                "XDG_CACHE_HOME": str(root / "a"), "XDG_RUNTIME_DIR": str(root / "r"),
            })
            config = load_config(paths)
            config.outputs = {}
            config.ui["hud"] = {"enabled": False}
            save_config(config, paths)
            if args.fixtures:
                fixture(root, "900000001", "video")
                fixture(root, "900000002", "image")
                resolver = SteamWorkshopResolver(library_roots_fn=lambda: [root])
                ids = ["900000001", "900000002"]
            else:
                resolver = SteamWorkshopResolver()
                ids = [args.video_id, args.image_id]
            backend = GuiBackend(paths, library_roots=(root / "library",))
            wallpapers = []
            for item_id, kind in zip(ids, ("video", "image")):
                local = resolver.find_local(item_id)
                if local is None:
                    raise RuntimeError(f"Workshop {item_id} must be installed locally")
                result = resolver.resolve(item_id)
                assert result.project_type.value == kind, result.to_dict()
                assert result.renderer == "mpvpaper", result.to_dict()
                imported = import_workshop_item(local, root / "library", item_id)
                assert imported and imported.read_bytes() == result.media.read_bytes()
                wallpapers.append(backend.library.import_file(imported))
                report["checks"].append({"resolve": result.to_dict(), "import": "original bytes match"})

            def start():
                current = EngineService(paths)
                current.playback.systemd = systemd
                current.runtimes.systemd = systemd
                current.runtimes.lwe.systemd = systemd
                current.playback.provider_manager = PreserveDesktopProviders()
                current.start()
                return current

            def verify(output, wallpaper):
                client = MpvClient(paths.mpv_socket(output))
                deadline = time.monotonic() + 15
                while True:
                    try:
                        actual = client.get_property("path")
                        video = client.get_property("video-params")
                        if actual == str(wallpaper.path) and video:
                            break
                    except PlaybackError:
                        pass
                    if time.monotonic() > deadline:
                        raise RuntimeError(f"MPV did not decode {wallpaper.path} on {output}")
                    time.sleep(0.1)
                return {"output": output, "path": actual, "decoded": video}

            service = start()
            first = monitors[0].name
            for wallpaper in wallpapers:
                backend.apply(wallpaper.id, first)
                report["checks"].append({"apply": verify(first, wallpaper)})
            if len(monitors) >= 2:
                backend.apply(wallpapers[0].id, first)
                backend.apply(wallpapers[1].id, monitors[1].name)
                report["checks"].append({"independent": [verify(first, wallpapers[0]), verify(monitors[1].name, wallpapers[1])]})
                report["two_physical_outputs"] = "check monitor descriptions; independent playback passed"
            backend.apply(wallpapers[0].id, "*")
            report["checks"].append({"apply_star": [verify(m.name, wallpapers[0]) for m in monitors]})
            service.shutdown()
            service = None
            for monitor in monitors:
                systemd.stop_output(monitor.name)
            service = start()
            report["checks"].append({"engine_restart": [verify(m.name, wallpapers[0]) for m in monitors]})
            backend.apply(wallpapers[1].id, first)
            service.shutdown()
            service = None
            for monitor in monitors:
                systemd.stop_output(monitor.name)
            service = start()
            report["checks"].append({"independent_restart_after_star": [
                verify(m.name, wallpapers[1] if m.name == first else wallpapers[0])
                for m in monitors
            ]})
            before = {m.name: systemd.details(m.name)["process"] for m in monitors}
            restored = backend.client.request("runtime_restore", {})
            after = {m.name: systemd.details(m.name)["process"] for m in monitors}
            assert before == after and all(before.values()), (before, after)
            report["checks"].append({"idempotent_restore": restored, "same_live_processes": True})
            report["status"] = "passed available checks"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        raise
    finally:
        if service is not None:
            service.shutdown()
        for monitor in monitors:
            systemd.stop_output(monitor.name)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"status": report.get("status"), "report": str(args.report), "outputs": [m.name for m in monitors], "error": report.get("error")}))


if __name__ == "__main__":
    main()
