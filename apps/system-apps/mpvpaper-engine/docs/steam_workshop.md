# Steam Workshop — MPVpaper Engine Architecture

## Overview

MPVpaper Engine resolves Steam Workshop items (Wallpaper Engine) into playable
media using `SteamWorkshopResolver`, a dedicated module at:

```
config/mpvpaper-engine/mpvpaper_engine/steam_workshop.py
```

The resolver handles discovery, type detection, compatibility reporting, and
structured metadata production. It is designed to be provider-neutral so that
additional providers (MPVpaper Hub, direct URLs, local files) can be added
alongside it in the future.

---

## Wallpaper Engine Project Types & Compatibility

| Project type | `project.json` `type` | Compatibility | Renderer |
|---|---|---|---|
| **Video** | `video` | **Full** | `mpvpaper` |
| **Image** | `image` or standalone image | **Full** | `mpvpaper` |
| **Scene** | `scene` | **Partial** | none (not rendered natively) |
| **Web** | `web` | **Preview only** | none |
| **Unknown** | anything else / missing | **Unsupported** | none |

### VIDEO — Full compatibility

- `project.json` → `type: video` → locate the referenced MP4/WebM/etc.
- Validated with `ffprobe` (non-fatal: probe failure is recorded, not fatal).
- Imported into the MPVpaper local library and played via `mpvpaper`.
- Metadata collected: width, height, fps, duration, codec, audio presence,
  file size.

### SCENE — Partial compatibility

Wallpaper Engine Scene projects contain `scene.pkg`, textures, shaders,
particles, and proprietary render data.

**RePKG is an optional asset extractor — not a scene renderer.**

- Scene projects are detected and reported as `PARTIAL`.
- If `scene.pkg` exists (and is inside the source directory), its path is
  recorded in the result.
- If `repkg` is installed, it is noted but **not invoked automatically** during
  resolution.
- No fake rendering is claimed.

> **⚠ Scene wallpapers are not rendered natively by mpvpaper.**
> The architecture is prepared for a future scene renderer but does not
> implement one.

### WEB — Preview only

HTML/JS-based Wallpaper Engine projects are identified and marked
`PREVIEW_ONLY`. Arbitrary Workshop JavaScript is never executed inside
MPVpaper Engine.

---

## Resolution Order

For any Workshop URL or bare item ID, the resolver proceeds in this order:

1. **Validate** the URL / item ID format.
2. **Check local Steam Workshop content** across all detected library roots —
   no network access required when the item is already installed.
3. **Fetch public Steam metadata** (Steam Web API) when useful.
4. **Direct file URL** — use Steam's `file_url` if available.
5. **steamcmd anonymous** — attempt `+login anonymous` download.
6. If Steam requires authentication → return `REQUIRES_AUTH`.
7. **Preview metadata only** — report `PREVIEW_ONLY`, with no playable media.
   Never download or import `preview_url` as a wallpaper.
8. **Failure result** — clear structured error if nothing works.

---

## Steam Libraries

All Steam library roots are discovered automatically, including:

- `~/.local/share/Steam`
- `~/.steam/steam`
- `~/.steam/root`
- Additional paths listed in `libraryfolders.vdf`

The Wallpaper Engine App ID (`431960`) is centralised as a constant.

---

## steamcmd Authentication

Anonymous access is attempted first:

```
steamcmd +login anonymous +workshop_download_item 431960 <ID> validate +quit
```

Anonymous access is **not guaranteed to work** for all Workshop items.

When steamcmd indicates that authentication is required (e.g. `Login Failure`,
`not logged on`, `requires a purchase`), the resolver returns:

```
compatibility: REQUIRES_AUTH
message: "Steam authentication required; run steamcmd manually or subscribe via Steam."
```

MPVpaper Engine:
- **does not store** Steam passwords, Steam Guard codes, or any credentials.
- **does not prompt** for credentials.
- Lets the user manage Steam authentication externally via Steam or steamcmd.

---

## RePKG — Optional Asset Extractor

RePKG is detected via `shutil.which("repkg")` but is **optional**. MPVpaper
Engine works normally without it.

If RePKG is unavailable, Scene projects return:

```
type: SCENE
compatibility: PARTIAL
message: "Scene project detected; RePKG unavailable"
```

If RePKG is used in the future for asset extraction:
- A temporary directory must be used.
- Extracted paths must be validated (no traversal).
- Extracted files must never be executed.
- Timeouts must be applied.

---

## Security Model

Workshop content is treated as **untrusted external input**.

| Threat | Protection |
|---|---|
| Path traversal (`../../etc/passwd`) | `_safe_candidate()` resolves and rejects paths outside `source_root` |
| Symlink escape | Symlink real path is checked against `source_root` |
| Malformed JSON | `json.JSONDecodeError` is caught; graceful fallback |
| Subprocess injection | Argument arrays only — never `shell=True` |
| Subprocess hangs | Explicit `timeout` on every subprocess call |
| Oversized responses | Byte limits on all network reads |
| Credential leakage | No credentials in code, config, or logs |
| Executing Workshop files | Never — `.sh`, `.py`, `.js`, `.exe`, AppImages are never run |
| Archive path traversal | `zipfile` member paths validated before extraction |

---

## Structured Result Model

`WorkshopResult` is a dataclass with a `.to_dict()` method that produces a
JSON-serializable dict for future MPVpaper Hub API communication:

```json
{
  "id": "2704773569",
  "provider": "steam-workshop",
  "type": "video",
  "compatibility": "full",
  "title": "Night City",
  "media": "/path/to/media.mp4",
  "preview": "https://cdn.steam.../preview.jpg",
  "source_dir": "/path/to/workshop/item",
  "package": null,
  "renderer": "mpvpaper",
  "message": ""
}
```

For Scene:

```json
{
  "id": "1234567890",
  "provider": "steam-workshop",
  "type": "scene",
  "compatibility": "partial",
  "title": "Aurora",
  "media": null,
  "preview": "https://cdn.steam.../preview.jpg",
  "source_dir": "/path/to/workshop/item",
  "package": "/path/to/workshop/item/scene.pkg",
  "renderer": null,
  "message": "Scene project: not natively rendered by mpvpaper"
}
```

---

## MPVpaper Hub — Future Integration

MPVpaper Hub will be an open-source community platform. The Hub stores
provider references, not media files:

```json
{
  "provider": "steam-workshop",
  "provider_id": "2704773569"
}
```

MPVpaper Engine resolves this locally via `SteamWorkshopResolver`. The Hub
does **not** need to mirror Steam Workshop content.

Future providers (not yet implemented):
- `mpvpaper-hub`
- `direct`
- `local`
- `youtube`

The `provider` field in `WorkshopResult` is already provider-neutral.

---

## Backwards Compatibility

The following public functions from `mpvpaper_download.py` remain unchanged:

- `steam_workshop_id(uri)`
- `steam_file_details(item_id, opener)`
- `steam_library_roots(home)`
- `find_workshop_item(item_id, roots)`
- `import_workshop_item(item_dir, library_dir, item_id, title)`
- `force_steam_workshop_download(uri, library_dir, target_height, runner)`

`steam_workshop.py` imports from `mpvpaper_download` and falls back to inline
stubs if the script is not on `sys.path`.

A convenience wrapper is provided:

```python
from mpvpaper_engine.steam_workshop import resolve_workshop_url

result = resolve_workshop_url("https://steamcommunity.com/sharedfiles/filedetails/?id=2704773569")
print(result.compatibility)  # "full"
print(result.to_dict())      # JSON-ready dict
```


## Session acceptance test

Run from the repository root inside Hyprland:

```sh
python3 config/mpvpaper-engine/tools/validate_workshop_session.py \
  --fixtures --report /tmp/workshop-session-report.json
```

This opt-in test displays generated video/image fixtures through real MPVpaper,
using the repository's resolver, library, GUI Apply backend, engine IPC and
systemd user units. It checks original file bytes, MPV's actual `path` and
`video-params`, individual outputs, Apply("*"), engine restart, and restoring an
individual selection after Apply("*"). Configuration and runtime files are
isolated in a temporary directory; test units are stopped afterwards. Existing
wallpaper providers are preserved, so provider handoff and visual stacking still
need a separate acceptance check.

For installed real Workshop content, replace `--fixtures` with
`--video-id VIDEO_ID --image-id IMAGE_ID`. The image must be an original image
project or standalone image, not a Scene preview. This mode requires local Steam
subscriptions; it does not test Steam authentication or remote downloads.

A full logout/login is a separate gate: install the revised engine, apply the
real items to both outputs, save open work, log out and log back in, then verify
the saved paths and screen assignments using the engine state and MPV IPC.
Repeat for Apply("*") followed by a selection on just one output. An engine
restart alone does not validate compositor startup, environment propagation,
or the installed user service's ordering.

See [the recorded session results](steam_workshop_validation.md) for what has
actually been checked and what remains pending.
