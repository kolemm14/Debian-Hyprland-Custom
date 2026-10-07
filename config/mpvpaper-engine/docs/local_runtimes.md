# MPVpaper / linux-wallpaperengine — local runtimes

## Architecture and scope

Video and Image use the existing MPVpaper playback adapter. Local Scene projects
use optional linux-wallpaperengine (LWE). Web projects can be registered and
inspected but **cannot be launched or restored**. The runtime manager is the
service's authority for apply, stop, replacement and restoration; GUI and CLI
mutations use its existing IPC socket. No additional permanent service exists.

Implementation: `mpvpaper_engine/runtimes/{project_detector,mpv_runtime,
lwe_runtime,runtime_manager}.py`. `service.py` supplies IPC and Hyprland events.
`library.py` registers complete project directories in place. All project
resources remain there; neither a Scene package nor its preview becomes a fake
playable video. Moving that directory later invalidates its registered path.
The SQLite schema migration preserves IDs, favorites, history and playlists.
Library scans skip project resources/previews as separate wallpapers.

The default V2 GUI includes **Ajouter un projet local…** in the inspector,
per-item type/runtime/readiness/compatibility diagnostics and Apply/Stop actions.
MPV-specific controls report an unsupported operation on Scene. Theme extraction
and automatic thumbnail rendering are not performed on Scene/Web directories.
The legacy `--legacy` GUI is not the multi-runtime interface.

## Runtime and process management

One systemd user unit per screen, shared by both backends:
`mpvpaper-engine-wallpaper-<screen>.service`. Commands use argument arrays and
validated output names. Replacement validates the project, runtime and assets
before stopping that screen. An error on another screen never rolls it back.
A failed replacement does not automatically recover the old renderer; the old
saved intent remains available for a later restore. Failed units retain their
exit status for diagnostics and are reset before replacement.

`status(screen)` reports screen, wallpaper, type, runtime, process, unit state
and exit code. Process IDs are volatile and are **not** stored in configuration.
Descriptions identify owned media so repeated restoration does not duplicate
an already-running matching unit. Availability is not proof of rendering.

Apply with a concrete output acts on that screen only. `apply_all()` or
`apply("*")` with no path replays each screen's own assignment, allowing mixed
MPV/LWE. Applying a selected wallpaper to `*` applies that same item independently
to every connected screen. The reply contains success/error for every screen.
An existing legacy global wallpaper unit blocks individual replacement until
explicitly stopped; `stop_all` also stops that old global unit.

## Persistence, restore and hotplug

Configuration remains `~/.config/mpvpaper-engine/config.json`. Each output stores
`wallpaper`, `project_type`, `runtime`, `runtime_options`, `enabled`, `autostart`.
Options currently include Scene FPS (1–240, default 30) and an optional assets
directory. No PID, handle or temporary socket is persisted. The actual project
type is checked again before launch; a stored runtime cannot bypass Web blocking.

At service startup, connected screen names are resolved against saved intent.
Missing monitors keep their assignments without applying to another screen.
The existing service listens to Hyprland's event socket: removal stops only that
screen, return restores its enabled intent. Geometry changes do not require a
new process. There is no process polling loop or continuous library scan.
Explicit Stop disables that screen's restoration; `stop_all(remember=False)`
is available internally for testing a stop/restore cycle without changing intent.

## Diagnostics and assets

Diagnostics distinguish `engine_available` / `runtime_available`,
`runtime_ready`, `missing_requirements`, `wallpaper_compatible`, `compatibility`
and `reason`. Unknown compatibility is represented by null / `unknown`, not by
an optimistic assertion of Scene support. CEF and sandbox remain unverified for
an unavailable/unbuilt runtime; Web is blocked regardless of installed files.

The adapter searches Steam roots:

- `~/.steam/steam`
- `~/.local/share/Steam`
- `~/.var/app/com.valvesoftware.Steam/.local/share/Steam`
- `~/snap/steam/common/.local/share/Steam`
- Extra paths from their `steamapps/libraryfolders.vdf`.

Under `steamapps/common`, it recognizes `wallpaper_engine/assets`,
`Wallpaper Engine/assets` and `wallpaper engine/assets`. An explicit
`--assets-dir` overrides discovery and is persisted with the assignment.
An existing non-empty directory is a prerequisite, **not verification of asset
completeness**. Missing/unreadable assets produce a diagnostic and leave MPV usable.
No official assets are downloaded, generated or redistributed.

## LWE installation audit on this machine

Official source inspected: https://github.com/Almamu/linux-wallpaperengine
revision `b016d7d1fdcf4e5fd2f9c9fa420a8aaa07fee02d` (2026-10-05).
The official source and its declared submodules were retrieved in
`/tmp/mpvpaper-lwe-audit`. First configuration stopped at GLEW. A subsequent
configuration found GLEW, DBus, GLUT, Zlib, SDL2, MPV, LZ4, FFmpeg, PulseAudio
and Freetype and reached the upstream CEF download. `sudo -n true` was denied.
The official build unconditionally downloads a CEF binary distribution, verified
by its upstream CMake hash check, before compiling the application.

Compilation was stopped before filling small filesystems: roughly 0.5 GiB free
in home, 0.7 GiB in /tmp and 0.5 GiB in /var after cleanup; the previously used
external disk path was not accessible for a build. Partial build downloads were
removed. No binary was installed and no successful `LWE --help` is claimed.
The source audit confirmed the CLI flags used by the adapter; runtime probing
will verify the installed executable before use.

To resume once a sufficiently large writable build location is available:

```sh
cmake -S /tmp/mpvpaper-lwe-audit -B /path/with/space/lwe-build -DCMAKE_BUILD_TYPE=Release
cmake --build /path/with/space/lwe-build -j2
/path/with/space/lwe-build/output/linux-wallpaperengine --help
```

Keep the build's support files alongside the executable as upstream specifies.
Do not substitute an arbitrary downloadable binary. If /tmp was cleared, clone
the official source with its submodules again. Missing dependencies must be
installed from Debian repositories with administrator access.

## CEF security audit — Web BLOCKED

The inspected CMake selects CEF/Chromium 135. `WebBrowserContext.cpp` sets
`settings.no_sandbox = true` when `CEF_NO_SANDBOX` is defined. `BrowserApp.cpp`
requests `disable-web-security`, disables site isolation and allows remote
origins broadly. `WPSchemeHandler.cpp` serves project resources through its asset
loader. CEF creates browser/renderer subprocesses and executes wallpaper JS.
No network-denial policy or proven filesystem sandbox was established by this
source audit. The actual compiled sandbox is unknown because the build was not
completed. These are source findings, **not runtime security test results**.
Web remains blocked for explicit launch and autostart; no sandbox override was
used. A validated policy and explicit confirmation are prerequisites for a
future Web milestone.

## Commands

Run from the repository root, after deploying the modules and restarting the
existing engine service. The service must respond; the CLI does not fall back
to an independent process manager.

```sh
export PYTHONPATH="$PWD/config/mpvpaper-engine"
python3 -m mpvpaper_engine.runtimes diagnose /path/to/scene --assets-dir /path/to/assets
python3 -m mpvpaper_engine.runtimes apply /path/to/video.mp4 --output eDP-1
python3 -m mpvpaper_engine.runtimes apply /path/to/scene --output HDMI-A-1 --assets-dir /path/to/assets --fps 30
python3 -m mpvpaper_engine.runtimes status --output HDMI-A-1
python3 -m mpvpaper_engine.runtimes apply-all
python3 -m mpvpaper_engine.runtimes stop --output HDMI-A-1
python3 -m mpvpaper_engine.runtimes restore
```

## Validation (2026-10-05)

Baseline: 367 tests succeeded before changes. See `runtime_validation.json` for
final counts and deployment evidence, and `runtime_session_report.json` for
actual MPV paths/decoded parameters. New tests cover mixed backends, inversion,
partial failures, crash/dead status, replacement, persistence without PIDs,
missing screens, hotplug, idempotent restore, Scene library migration and GUI IPC.

- **PASS real:** MPV video and image on the physical `eDP-1`, replacing media,
  Apply("*") on this single connected screen, service stop/start restoration,
  repeated restore retaining the same process. Tests use real systemd/MPV IPC
  with isolated transient unit names, generated media and isolated config.
- **PASS real:** GTK window construction, local project registration and a live
  IPC diagnostic showing missing LWE. This is not Scene rendering validation.
- **PASS mock:** two runtimes/two screens, inversion, crash isolation,
  disappeared/returned screen, mixed Apply("*"), Scene persistence and restore.
- **BLOCKED:** LWE Scene rendering and mixed MPV/LWE physical outputs: no built
  LWE, no official assets/local Scene, only one connected monitor.
- **SKIPPED:** physical cable removal/reconnection, full graphical logout and
  reboot. The active development session was preserved.
- **BLOCKED by policy:** Web launch and restoration. Source CEF audit completed;
  actual sandbox/network/filesystem behavior remains unverified.

Reproducible tests:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s config/mpvpaper-engine/tests
python3 config/mpvpaper-engine/tools/validate_workshop_session.py --fixtures --report /tmp/runtime-report.json
python3 config/mpvpaper-engine/tools/validate_runtime_gui.py /tmp/gui-report.json
```

The two smoke tools are opt-in and briefly display test surfaces/windows. They
preserve desktop providers and clean up their test units. They do not certify
handoff from every external wallpaper application. Next real acceptance gate:
provide a build location, official assets and a local Scene, connect a second
screen, and exercise the mixed setup in both directions before claiming LWE
compatibility. No Web support is implied by successful Scene rendering.
