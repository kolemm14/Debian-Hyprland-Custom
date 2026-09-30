# Debian Custom Manager

Native control center for Debian-Hyprland-Custom.

## Why C + GTK3

The project targets older PCs as well as modern Debian/Hyprland systems. The Manager therefore avoids Electron/WebView and does not add a Python runtime dependency. GTK3/GLib provides a mature native interface with a small memory footprint and fast startup.

## Responsibilities

The Manager:

- displays the state of components;
- explains each component in simple language;
- runs update checks and dry-runs;
- delegates installation, update, rollback and repair to existing scripts;
- shows basic dependency status;
- keeps command output in a log view.

It does **not** absorb MPVpaper Engine, Aurora, Nova, MirrorBridge or Pericored.

## Build

```bash
sudo apt install build-essential pkg-config libgtk-3-dev
cd manager
make
make test
./build/debian-custom-manager
```

When run from inside the repository, it automatically finds the Git root. You can also set:

```bash
DHC_REPO_ROOT=/path/to/Debian-Hyprland-Custom ./build/debian-custom-manager
```

## Install for the current user

```bash
cd manager
./scripts/install.sh
```

This installs only the Manager under `~/.local`. It does not modify the desktop components.

## Uninstall the Manager

```bash
cd manager
./scripts/uninstall.sh
```

This removes only the Manager.

## Diagnostic CLI

No graphical session is required for the component diagnostic:

```bash
./build/debian-custom-manager --version
./build/debian-custom-manager --diagnose
```

## Interactive terminal frontend

The same executable also provides a terminal UI; it does not start GTK or require
an active graphical session for read-only operations:

```bash
./build/debian-custom-manager --cli
./build/debian-custom-manager --interactive      # alias
./build/debian-custom-manager --cli --no-animation
NO_COLOR=1 ./build/debian-custom-manager --cli
```

After installing the new build, use `debian-custom-manager --cli` directly.
The default invocation still starts GTK; `--diagnose` and `--version` are unchanged.
No runtime dependency was added. The single executable still **links GTK3**;
GTK libraries must be installed even when using the terminal frontend.
Python 3 (standard library only, already used by the repository) runs the PTY tests.
Object files now build under `build/`, leaving existing source-directory artifacts alone.

### Navigation

- Up/Down and Enter select menu entries. Digits 1–9 and 0 select main menu actions.
- Tab switches between Menu and Assistant. Esc returns; Esc on the menu exits.
- `/` filters menu/components locally; Enter opens the match, Esc clears the filter.
- `:` opens the command palette; `?` opens help; Ctrl+L redraws the screen.
- `q` exits only outside a text field. Ctrl+C / SIGTERM restore terminal settings.
- Logs and documentation: arrows, PageUp/PageDown and Home/End scroll.
- Components: Enter opens descriptions, state, required/optional status and registered
  actions. `i` installs, `r` repairs, `u` uninstalls optional components only, `d`
  previews documentation, `f` refreshes states. Unsupported actions are not offered.
- Overview: `u` applies updates and `r` requests rollback through the existing wrapper.
  These actions show a review screen (`y` launches, Esc cancels) then use the existing
  external-terminal backend, including its sudo prompts. No password is read by the TUI.

Palette: `:overview`, `:components`, `:check`, `:dry-run`, `:dependencies`,
`:diagnose`, `:logs`, `:assistant`, `:help`, `:quit`, `:update`, `:rollback`.

### Local assistant

The assistant is a fixed local router, not a network AI. It normalizes case,
whitespace and accents, then matches known phrases or exact component names/IDs.
Examples: `check updates`, `simulate update`, `show components`, `show dependencies`,
`diagnose system`, `show logs`, `install mpvpaper`, `open mpvpaper`, `help`.
French equivalents include `vérifie les mises à jour`, `simule la mise à jour`,
`montre les composants`, `voir les dépendances`, `diagnostique le système`,
`montre les journaux`, `installer mpvpaper`, `ouvrir mpvpaper`, `aide`.
`open` / `ouvrir` opens the component's action panel; no application launcher is
registered in the current manifest. Unknown text is never passed to a shell.
The last five requests remain available during the session.

### Rendering, jobs and limits

ANSI/VT100, termios and poll handle rendering/input, with three layouts: large
(100x24+), medium (65x22+) and small (40x16+). Smaller terminals show a resize hint.
The ASCII logo uses a cyan/blue/violet/pink/red sweep, slow pulse and subtle shimmer
at at most 10 FPS. Only changed rows are painted. Truecolor falls back to 256 or
standard colors. `NO_COLOR` removes color; `--no-animation` stops idle redraws.
Non-TTY streams and `TERM=dumb` receive a plain diagnostic hint and exit code 2.
Terminal settings, alternate screen and cursor are restored on normal exit,
SIGINT, SIGTERM and SIGHUP. SIGKILL cannot be handled by an application.

Checks and simulations run in a worker using the shared runner; the interface
remains navigable. Completed output is shown in Logs (not streamed live). Capture
retains the last 256 KiB; the session log also stays bounded at 256 KiB. Terminal
control characters in external text are neutralized. Documentation previews are
limited to 64 KiB. Component states are cached between explicit refreshes; detection
uses the existing synchronous backend. Long rows wrap in detail/log/help screens;
menu labels and the input/status bars are clipped on narrow terminals.

Dirty/divergent checkout messages receive an explanation without any automatic Git
repair. Exact backend output is retained. Apply/rollback/install completion and
errors remain in the external terminal, as in the GTK frontend. Logs are session
local; separate GUI and CLI processes do not share an in-memory log buffer.
Cancelling a captured job terminates the direct child; descendants independently
spawned by a backend are not managed as a process group.

### Validation

`make clean all test` compiles both frontends and runs the existing shell tests,
GLib unit tests, and Python PTY integration tests. PTY tests use an isolated temporary
repository with a harmless fake updater; they never apply a real update or run a
real installer. Tests cover routing, option parsing, injection rejection, bounded
capture/cancellation, keyboard actions, resizing, animation, color, non-TTY output,
and terminal restoration after normal and signal-driven exits.

## HYPRDEBIAN visual identity

`data/hyprdebian-logo.svg` preserves the exact official SVG supplied for this
project, including its dark background and glow. It is a documentation/reference
asset; the terminal never loads or rasterizes it. No image protocol or graphics
package is required.

`src/cli_logo.c` keeps the image-reference `HYPRDEBIAN_LOGO` 36x36
matrix private. With explicit authorization, the earlier supplied matrix was
replaced by a hand-traced mask matching the screenshot: a narrower open blade,
a separate inner arc and a hollow Debian coil. See `tests/logo-image-match.md`. Zero is transparent; regions 1–5 guide cyan, blue, violet, pink
and red. No image conversion or geometry generation is performed at runtime.
The large terminal logo is exactly 36 columns by 18 rows, including the matrix's
transparent margins. Compact and mini retain their independent small masks.

Two vertical pixels share a terminal cell: `▀` for top only, `▄` for bottom only,
and `▀` with separate foreground/background for both. The lower-pixel background
is reset before transparent or single-pixel cells, and styling ends at the logo
row boundary. No global background is set. Monochrome uses `▀`, `▄`, and `█`;
non-UTF-8 locales use aligned ASCII characters.

The five spatial stops are `#00F2FE`, `#5B8CFF`, `#8A2BE2`, `#FF62B0`,
and `#E6004C`. Region values dominate the base color (90%); normalized x/y add
10% spatial variation. A monotonic clock drives a seven-second, ±0.04 gradient
oscillation, a 0.88–1.00 pulse, and a diagonal shimmer of at most 8%. The gradient
never rotates through the entire palette: cyan, violet and red remain visible
simultaneously. `--no-animation` disables every temporal effect.

Truecolor emits separate RGB foreground/background values. ANSI 256 uses the
nearest levels in the xterm color cube; basic ANSI approximates cyan, blue,
magenta and red. `NO_COLOR` removes logo color escapes while retaining the
high-resolution silhouette (TUI positioning still uses VT100 controls).
Non-TTY behavior stays unchanged: a plain diagnostic hint, without escapes.

Large is preferred from 86x30; compact fits 65x22; smaller usable terminals show
the mini mark. Content stays near the top within 90 columns, with 36 logo columns
and a four-column gap. The existing poll loop caps animation at 10 FPS and idle
`--no-animation` blocks on input. Each logo row is buffered in a GString; color
codes are emitted only when a foreground/background changes, not reset per pixel.

Tests check all 36 source rows and their 36 values, the 0–5 range and a checksum
of all 1296 image-reference values, plus crest and negative-space checks. Deterministic color tests cover explicit phases,
periodicity, spatial diversity, half-block cases, odd-height protection,
transparency, ASCII/monochrome/truecolor/256-color output, and static rendering.
PTY tests continue to cover navigation, resizing, restoration and real layouts.
