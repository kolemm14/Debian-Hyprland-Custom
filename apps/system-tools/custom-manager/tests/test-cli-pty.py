#!/usr/bin/env python3
"""Terminal integration tests. Backend actions run only inside a temporary fixture."""
import fcntl
import hashlib
import os
from pathlib import Path
import pty
import re
import select
import signal
import struct
import subprocess
import tempfile
import termios
import time
import unicodedata

BINARY = str(Path('build/debian-custom-manager').resolve())


class Session:
    def __init__(self, root, *args, color=True, locale='C.UTF-8', colorterm='truecolor'):
        self.master, self.slave = pty.openpty()
        self.before = termios.tcgetattr(self.slave)
        self.resize(120, 30, notify=False)
        env = dict(os.environ, TERM='xterm-256color', COLORTERM=colorterm, LC_ALL=locale,
                   DHC_REPO_ROOT=str(root), DCM_COMPONENTS_FILE=str(root / 'apps/system-tools/custom-manager/data/components.ini'))
        if not color:
            env['NO_COLOR'] = '1'
        else:
            env.pop('NO_COLOR', None)
        self.process = subprocess.Popen([BINARY, *args], stdin=self.slave,
                                        stdout=self.slave, stderr=self.slave, env=env)
        self.output = b''
        self.wait_for(b'DEBIAN CUSTOM MANAGER')

    def read(self, duration=0.15):
        end = time.monotonic() + duration
        chunk = b''
        while time.monotonic() < end:
            if select.select([self.master], [], [], max(0, end-time.monotonic()))[0]:
                chunk += os.read(self.master, 65536)
        self.output += chunk
        return chunk

    def wait_for(self, text, timeout=4):
        start = len(self.output)
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.read(0.05)
            if text in re.sub(rb'\x1b\[[0-9;]*m', b'', self.output[start:]):
                return
        raise AssertionError((text, self.output[-2500:]))

    def send(self, text):
        os.write(self.master, text)

    def resize(self, cols, rows, notify=True):
        fcntl.ioctl(self.slave, termios.TIOCSWINSZ, struct.pack('HHHH', rows, cols, 0, 0))
        if notify:
            self.process.send_signal(signal.SIGWINCH)

    def screen(self):
        """Decode renderer cursor/erase/SGR sequences without a terminal dependency."""
        grid = {}
        row = col = 0
        for part in re.split(r'(\x1b\[[0-9;?]*[A-Za-z])', self.output.decode('utf-8', 'replace')):
            if part.startswith('\x1b['):
                if part == '\x1b[2J':
                    grid = {}
                elif part == '\x1b[2K':
                    grid[row] = {}
                elif part.endswith('H'):
                    y, x = part[2:-1].split(';')
                    row, col = int(y)-1, int(x)-1
                continue
            for char in part:
                if char.isprintable() and not unicodedata.combining(char):
                    grid.setdefault(row, {})[col] = char
                    col += 2 if unicodedata.east_asian_width(char) in 'WF' else 1
        return [''.join(grid.get(y, {}).get(x, ' ') for x in range(max(grid.get(y, {}), default=-1)+1))
                for y in range(max(grid, default=-1)+1)]

    def close(self, sig=None):
        if sig:
            self.process.send_signal(sig)
        else:
            self.send(b'q')
        # Drain animated output while waiting: a PTY has a small output buffer.
        deadline = time.monotonic() + 4
        while self.process.poll() is None and time.monotonic() < deadline:
            self.read(0.05)
        code = self.process.wait(timeout=1)
        self.read()
        assert code == (128 + sig if sig else 0), code
        assert termios.tcgetattr(self.slave) == self.before, 'termios not restored'
        assert b'\x1b[?25h\x1b[?1049l' in self.output, 'screen/cursor not restored'
        os.close(self.master)
        os.close(self.slave)


def main():
    source = Path('src/cli_logo.c').read_text()
    matrix = source.split('HYPRDEBIAN_LOGO[LOGO_HEIGHT][LOGO_WIDTH] = {', 1)[1].split('};', 1)[0]
    rows = [[int(value) for value in row.split(',')] for row in re.findall(r'\{([^{}]+)\}', matrix)]
    assert len(rows) == 36
    assert all(len(row) == 36 for row in rows)
    assert all(0 <= value <= 5 for row in rows for value in row)
    assert hashlib.sha256(bytes(value for row in rows for value in row)).hexdigest() == (
        'fbcd7b3c5005d5a5cde2c9b07dd89674afc07a0d28d24b8985de0b612a05d858')
    # The screenshot has an open crest, a narrow silhouette and a hollow interior.
    occupied = [(x, y) for y, row in enumerate(rows) for x, value in enumerate(row) if value]
    assert (min(x for x, y in occupied), max(x for x, y in occupied)) == (3, 31)
    assert rows[1][15] and rows[1][19] and not any(rows[1][16:19])
    assert sum(bool(rows[y][x]) for y in range(13, 29) for x in range(12, 28)) <= 80
    assert rows[22][21] == 0  # black centre of the inner coil
    assert any(rows[y][x] for y in range(18, 26) for x in range(18, 24))
    print('PASS image-reference 36x36 matrix, row lengths, region values, checksum')
    with tempfile.TemporaryDirectory(prefix='dcm-cli-test-') as folder:
        root = Path(folder)
        (root / 'apps/system-tools/custom-manager/data').mkdir(parents=True)
        (root / 'install.sh').write_text('#!/bin/sh\nexit 0\n')
        (root / 'update.sh').write_text('#!/bin/sh\nprintf "backend argument: %s\\n" "$1"\n')
        (root / 'update.sh').chmod(0o755)
        (root / 'apps/system-tools/custom-manager/data/components.ini').write_text(
            '[component:core]\nname=Test Core\nrequired=true\ndetect_all=$REPO/install.sh\n'
            'install_script=install.sh\ndescription=Required test fixture\n'
            '[component:mpvpaper-engine]\nname=MPVpaper Engine\nrequired=false\n'
            'description=Animated wallpapers fixture\ninstall_script=install.sh\n')
        s = Session(root, '--cli')
        assert b'38;2;' in s.output
        s.resize(180, 45)
        s.read()
        screen = s.screen()
        assert any('╭─ Actions' in row for row in screen)
        assert any('› Overview' in row for row in screen)
        assert not any('1. Overview' in row for row in screen)
        assert any('DEBIAN × HYPR' in row for row in screen)
        assert all(not row.strip() or (len(row)-len(row.lstrip()) >= 45 and len(row.rstrip()) <= 135)
                   for row in screen), 'large layout must remain centered within 90 columns'
        assert sum('Navigate' in row for row in screen) == 1
        s.resize(120, 30)
        s.read()
        frames = s.read(0.35)
        assert b'38;2;' in frames and b'\x1b[2J' not in frames, 'animation must update rows only'
        s.send(b'\x1b[B\r')
        s.wait_for(b'Test Core')
        s.send(b'/mpvpaper\r')
        s.wait_for(b'Animated wallpapers fixture')
        s.send(b'i')
        s.wait_for(b'Launch interactive repository action?')
        s.send(b'\x1b')
        s.wait_for(b'Animated wallpapers fixture')
        s.send(b'\x1b')
        s.read()
        s.send(b'\t')
        s.wait_for(b'local command router')
        screen = s.screen()
        assert any('Ask Debian Custom Manager...' in row for row in screen)
        assert any('✦ Assistant' in row for row in screen)
        s.send('voir les dépendances\r'.encode())
        s.wait_for(b'System & dependencies')
        s.send(b':diagnose\r')
        s.wait_for(b'Component diagnosis')
        s.send(b':check\r')
        s.wait_for(b'backend argument: --check')
        s.send(b':dry-run\r')
        s.wait_for(b'backend argument: --dry-run')
        s.send(b':help\r')
        s.wait_for(b'Keyboard & local assistant')
        s.send(b'\x1b[6~\x1b[5~\x1b[F\x1b[H\x0c')
        s.read()
        for cols, rows in [(80, 24), (45, 18), (20, 10), (120, 30)]:
            s.resize(cols, rows)
            s.read()
            screen = s.screen()
            assert all(len(row.rstrip()) < cols for row in screen)
            assert all(not row.strip() for row in screen[rows:]), 'render exceeds terminal height'
        assert b'Terminal too small.' in s.output
        s.close()
        print('PASS PTY navigation, assistant, filter, palette, actions, logs, resize, animation, restoration')

        for args, color, sig in [
            (('--interactive', '--no-animation'), True, signal.SIGINT),
            (('--cli', '--no-animation'), False, signal.SIGTERM),
        ]:
            s = Session(root, *args, color=color)
            assert not s.read(0.25), 'disabled animation redrew while idle'
            if not color:
                assert not re.search(rb'\x1b\[[0-9;]*m', s.output), 'NO_COLOR emitted SGR'
            s.close(sig)
        print('PASS aliases, no-animation, NO_COLOR, SIGINT/SIGTERM restoration')

        s = Session(root, '--cli', '--no-animation', color=False, locale='C')
        assert all(byte < 128 for byte in s.output), 'ASCII locale emitted Unicode decoration'
        assert b'+- Actions' in s.output
        s.close()
        print('PASS centered panels, single footer, assistant input card, ASCII decoration fallback')

        s = Session(root, '--cli', '--no-animation')
        assert b'\x1b[38;2;0;242;254m' in s.output, 'static official cyan missing'
        for cols, rows, mark in [
            (120, 30, '▄   ▄'),
            (80, 24, '│    ││ │◉╯│ │'),
            (45, 18, '╱╭@╮│'),
        ]:
            s.resize(cols, rows)
            s.read()
            screen = s.screen()
            assert any(mark in row for row in screen), 'logo mask clipped or absent'
            assert any('DEBIAN × HYPR' in row for row in screen)
        s.close()
        s = Session(root, '--cli', '--no-animation', colorterm='')
        assert b'\x1b[38;5;' in s.output and b'\x1b[38;2;' not in s.output
        s.close()
        s = Session(root, '--cli', color=False)
        assert not re.search(rb'\x1b\[[0-9;]*m', s.output)
        assert any('▄   ▄' in row for row in s.screen())
        s.close()
        print('PASS logo sizes, no clipping, official static gradient, 256 colors, monochrome mask')

        # Untrusted input must never reach a shell or a component installer.
        s = Session(root, '--cli', '--no-animation')
        s.send(b'\t')
        s.wait_for(b'local command router')
        marker = root / 'injected'
        s.send(f'install mpvpaper; touch {marker}\r'.encode())
        s.wait_for(b'Unknown request')
        assert not marker.exists()
        s.send(b'\x1b')
        s.read()
        s.close()
        print('PASS unknown/injection rejection')

        for message, explanation in [
            ('Checkout modifié : sauvegardez vos changements.', b'Local changes detected'),
            ('Historique divergent ou avance locale.', b'Development checkout detected'),
        ]:
            (root / 'update.sh').write_text(f"#!/bin/sh\nprintf '%s\\n' '{message}'\nexit 1\n")
            s = Session(root, '--cli', '--no-animation')
            s.send(b':check\r')
            s.wait_for(explanation)
            s.close()
        print('PASS dirty/divergent checkout explanations')

        # A running captured job must not prevent termination or terminal restoration.
        (root / 'update.sh').write_text('#!/bin/sh\nexec sleep 30\n')
        s = Session(root, '--cli', '--no-animation')
        s.send(b':check\r')
        s.wait_for(b'Checking for updates')
        s.close(signal.SIGTERM)
        print('PASS cancellation during slow backend action')

    p = subprocess.run([BINARY, '--cli'], capture_output=True)
    assert p.returncode == 2 and b'--diagnose' in p.stderr and b'\x1b' not in p.stderr
    print('PASS non-TTY fallback')


if __name__ == '__main__':
    main()
