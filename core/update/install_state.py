"""Versioned installation identity, independent of the development worktree."""
from __future__ import annotations

import configparser
import datetime
import io
import re
from pathlib import Path
from urllib.parse import urlsplit

from files import UpdateError, atomic_write, read_json, run
import base64

OFFICIAL = 'https://github.com/kolemm14/Debian-Hyprland-Custom.git'
FIELDS = ('installed_version', 'installed_commit', 'channel', 'repository', 'branch', 'installed_at')


def validate(state):
    if state.get('schema_version') != '2' or any(not isinstance(state.get(k), str) or not state[k] for k in FIELDS):
        raise UpdateError('InstallState invalide : schéma ou champs manquants')
    if not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', state['installed_commit']):
        raise UpdateError('InstallState invalide : commit')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]*', state['branch']) or '..' in state['branch'] or state['branch'].endswith('/'):
        raise UpdateError('InstallState invalide : branche')
    repository = state['repository']
    # Paths are permitted for offline/private repositories. No option-like URL,
    # shell transport or Git ext helper may be selected by persisted metadata.
    allowed = (Path(repository).is_absolute() or repository.startswith('git@') or
               urlsplit(repository).scheme in ('https', 'ssh', 'file'))
    if not allowed or any(c in repository for c in '\r\n\x00'):
        raise UpdateError('InstallState invalide : repository')
    if any('\n' in state[k] or '\r' in state[k] or '\x00' in state[k] for k in FIELDS):
        raise UpdateError('InstallState invalide : caractères de contrôle')
    return state


def encode(state):
    validate(state)
    parser = configparser.ConfigParser(interpolation=None)
    parser['installation'] = state
    output = io.StringIO()
    parser.write(output, space_around_delimiters=False)
    return output.getvalue()


def write(locations, state):
    value = encode(state).encode()
    atomic_write(locations.data / 'install-state.ini', {
        'kind': 'file', 'value': base64.b64encode(value).decode(), 'mode': 0o600})


def load(locations):
    path = locations.data / 'install-state.ini'
    if not path.exists():
        return None
    try:
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_string(path.read_text())
        return validate(dict(parser['installation']))
    except (configparser.Error, KeyError, UnicodeError) as error:
        raise UpdateError('InstallState invalide ; état conservé pour diagnostic') from error


def version(tree):
    for name in ('VERSION', 'manager/VERSION'):
        path = tree / name
        if path.is_file():
            value = path.read_text().strip()
            if value and '\n' not in value:
                return value
    return 'unknown'


def migrate(repo, locations, *, persist=True):
    current = load(locations)
    if current is not None:
        return current
    legacy = read_json(locations.manifest, {})
    historical = read_json(locations.data / 'version', {})
    commit = legacy.get('commit') or historical.get('commit')
    fallback = not commit
    if not commit:
        commit = run(['git', 'rev-parse', 'HEAD'], cwd=repo).stdout.strip()
    origin = run(['git', 'config', '--get', 'remote.origin.url'], cwd=repo, check=False).stdout.strip()
    if 'kebemouhamet08-gif/Debian-Hyprland-Custom' in origin:
        origin = OFFICIAL
    state = {'schema_version': '2', 'installed_commit': commit,
             'installed_version': legacy.get('version') or historical.get('version') or 'unknown',
             'channel': 'stable', 'repository': origin or OFFICIAL, 'branch': 'main',
             'installed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'migration_source': 'development-fallback' if fallback else 'legacy-manifest'}
    validate(state)
    if persist:
        write(locations, state)
    return state


def next_state(old, commit, tree):
    return {**old, 'installed_commit': commit, 'installed_version': version(tree),
            'installed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'migration_source': 'transaction'}
