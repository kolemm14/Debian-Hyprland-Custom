"""Audited installation mappings and conservative per-file ownership."""
from __future__ import annotations

import base64
import configparser
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile


class UpdateError(RuntimeError):
    pass


def run(args, *, cwd=None, check=True, timeout=300):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode:
        # Do not include remote URLs or subprocess output, which can contain tokens.
        raise UpdateError(f"Échec de {Path(args[0]).name} (code {result.returncode})")
    return result


def read_json(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def snapshot(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(info.st_mode):
        return {'kind': 'link', 'value': os.readlink(path)}
    if not stat.S_ISREG(info.st_mode):
        raise UpdateError(f"Destination non régulière : {path}")
    if info.st_size > 32 * 1024 * 1024:
        raise UpdateError(f"Fichier trop volumineux pour une transaction : {path}")
    return {'kind': 'file', 'value': base64.b64encode(path.read_bytes()).decode(),
            'mode': stat.S_IMODE(info.st_mode)}


def source_snapshot(path):
    value = snapshot(path)
    if value and value['kind'] == 'file':
        value['mode'] = 0o755 if value['mode'] & 0o111 else 0o644
    return value


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def atomic_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if value is None:
        path.unlink(missing_ok=True)
        return
    temporary = path.parent / ('.' + path.name + f'.update-{os.getpid()}')
    try:
        if value['kind'] == 'link':
            temporary.symlink_to(value['value'])
        else:
            with temporary.open('xb') as stream:
                stream.write(base64.b64decode(value['value']))
                stream.flush()
                os.fsync(stream.fileno())
            temporary.chmod(value['mode'])
        os.replace(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def json_write(path, value):
    atomic_write(path, {'kind': 'file', 'value': base64.b64encode(
        (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()).decode(), 'mode': 0o600})


class Locations:
    def __init__(self, repo, env=None):
        env = os.environ if env is None else env
        home = Path(env.get('HOME', str(Path.home()))).resolve()
        self.roots = {'home': home, 'repo': Path(repo).resolve(),
                      'config': Path(env.get('XDG_CONFIG_HOME', home / '.config')).resolve(),
                      'data': Path(env.get('XDG_DATA_HOME', home / '.local/share')).resolve(),
                      'state': Path(env.get('XDG_STATE_HOME', home / '.local/state')).resolve(),
                      'cache': Path(env.get('XDG_CACHE_HOME', home / '.cache')).resolve()}
        self.data = self.roots['data'] / 'debian-hyprland-custom'
        self.state = self.roots['state'] / 'debian-hyprland-custom'
        self.manifest = self.data / 'installed-files.json'
        self.cache = self.roots['cache'] / 'debian-hyprland-custom'
        self.runtime = self.data / 'runtime'

    def path(self, key):
        root, relative = key.split(':', 1)
        if root not in self.roots or Path(relative).is_absolute() or '..' in Path(relative).parts:
            raise UpdateError('Destination hors du périmètre autorisé')
        base = self.roots[root]
        path = base / relative
        # Leaf symlinks are objects to replace, never followed. Parent symlinks
        # would redirect writes and are refused, including during rollback.
        for parent in path.parents:
            if parent == base:
                break
            if parent.is_symlink():
                raise UpdateError(f"Parent symbolique non géré : {parent}")
        return path


def recipe(tree):
    data = read_json(tree / 'manifests/update-files.json', {'schema': 1, 'rules': [], 'services': {}, 'packages': {}})
    if data.get('schema') != 1:
        raise UpdateError('Version inconnue du manifest de destinations')
    return data


def inventory(tree, locations, components):
    result = {}
    for rule in recipe(tree)['rules']:
        if rule['component'] not in components:
            continue
        if Path(rule['source']).is_absolute() or '..' in Path(rule['source']).parts:
            raise UpdateError('Source hors dépôt')
        for field in ('strip', 'build'):
            if field in rule and (Path(rule[field]).is_absolute() or '..' in Path(rule[field]).parts):
                raise UpdateError('Chemin de manifest hors dépôt')
        for source in sorted(tree.glob(rule['source'])):
            if not source.parent.resolve().is_relative_to(tree.resolve()):
                raise UpdateError('Parent source hors dépôt')
            if source.is_dir() or any(x in source.parts for x in ('__pycache__', '.venv', 'target', '.git')):
                continue
            relative = str(source.relative_to(tree))
            tail = relative.removeprefix(rule.get('strip', ''))
            if tail in rule.get('exclude', []):
                continue
            key = rule['destination'].format(relative=tail, name=source.name)
            locations.path(key)
            value = snapshot(source)
            if 'link' in rule:
                value = {'kind': 'link', 'value': str(locations.path(rule['link']))}
            elif 'generate' in rule:
                root = locations.path('home:.local/lib/debian-next-v3')
                # Shell-quote HOME paths, which may contain spaces or apostrophes.
                import shlex
                text = '#!/bin/sh\nif [ "$#" -gt 0 ]; then\n    exec python3 ' + shlex.quote(str(root / 'periphx.py')) + ' "$@"\nfi\nexec python3 ' + shlex.quote(str(root / 'device-center.py')) + ' "$@"\n'
                value = {'kind': 'file', 'value': base64.b64encode(text.encode()).decode(), 'mode': 0o755}
            elif value and value['kind'] == 'link':
                # Only relative, in-tree asset symlinks are accepted from Git.
                target = source.parent / value['value']
                if Path(value['value']).is_absolute() or not target.resolve().is_relative_to(tree.resolve()):
                    raise UpdateError(f"Lien source hors dépôt : {relative}")
            if value and value['kind'] == 'file':
                value['mode'] = 0o755 if value['mode'] & 0o111 else 0o644
                if 'mode' in rule:
                    value['mode'] = int(rule['mode'], 8)
                elif rule.get('script_mode') and source.suffix in ('.py', '.sh'):
                    value['mode'] = 0o755
            entry = {'source': relative, 'component': rule['component'],
                     'policy': rule.get('policy', 'managed'), 'reference': value}
            if 'build' in rule:
                build_root = tree / rule['build']
                hashes = {str(p.relative_to(build_root)): fingerprint(source_snapshot(p)) for p in sorted(build_root.rglob('*'))
                          if p.is_file() and not any(x in p.relative_to(build_root).parts for x in ('target', '.git'))}
                entry.update(build=rule['build'], binary=rule['binary'], inputs=fingerprint(hashes))
                entry['reference'] = None
            if key in result and result[key]['reference'] != entry['reference']:
                raise UpdateError(f"Destinations concurrentes : {key}")
            result[key] = entry
    return result


def detect_components(locations, recorded):
    selected = set(recorded)
    legacy = locations.roots['state'] / 'deblestia/setup/components'
    if legacy.exists():
        selected.update(legacy.read_text().splitlines())
    sentinels = {
        'mpvpaper-engine': 'home:.local/lib/mpvpaper-engine/mpvpaper-engine.py',
        'periphx': 'home:.local/lib/debian-next-v3/device-center.py',
        'mirrorbridge': 'home:.local/share/applications/io.github.kebemouhamet08.MirrorBridge.desktop',
        'deblestia-shell': 'config:debian-immersive-v2/state',
        'deblestia-nova': 'state:deblestia-nova/last-backup',
        'aurora-core': 'home:.local/bin/aurora',
    }
    for component, key in sentinels.items():
        path = locations.path(key)
        if not (path.is_file() or path.is_symlink()):
            continue
        companions = {
            'mpvpaper-engine': 'home:.local/bin/mpvpaper-engine',
            'periphx': 'home:.local/bin/periphx',
            'mirrorbridge': 'home:.local/bin/mirrorbridge',
        }
        if component in companions:
            other = locations.path(companions[component])
            if not (other.is_file() or other.is_symlink()):
                continue
        if component == 'aurora-core' and (not path.is_symlink() or path.resolve() != locations.path('repo:bin/aurora')):
            continue
        selected.add(component)
    mode = locations.path('state:deblestia/ui-mode')
    if mode.exists():
        selected.update({'bar': ['deblestia-bar'], 'nova-lite': ['deblestia-nova-lite'],
                         'nova2': ['nova2'], 'nova-shell': ['deblestia-nova'],
                         'immersive': ['deblestia-shell']}.get(mode.read_text().strip(), []))
    return selected


def baseline(tree, locations, components, commit):
    entries = {}
    for key, entry in inventory(tree, locations, components).items():
        actual = snapshot(locations.path(key))
        # Legacy files are adopted only with exact source evidence. A binary
        # cannot be attributed from its name, nor can an edited configuration.
        if actual is not None and actual == entry['reference']:
            entries[key] = {**entry, 'installed': actual, 'commit': commit}
    return {'schema': 1, 'commit': commit, 'components': sorted(components), 'files': entries, 'proposals': {}}


def validate(key, value):
    if not value or value['kind'] != 'file':
        return
    contents = base64.b64decode(value['value'])
    if key.endswith('.py'):
        compile(contents, key, 'exec')
    elif key.endswith(('.service', '.timer', '.desktop')):
        parser = configparser.RawConfigParser(strict=False)
        try:
            parser.read_string(contents.decode())
        except (configparser.Error, UnicodeError) as error:
            raise UpdateError(f'Unité/launcher invalide : {key}') from error
        section = 'Service' if key.endswith('.service') else 'Timer' if key.endswith('.timer') else 'Desktop Entry'
        if not parser.has_section(section):
            raise UpdateError(f'Section [{section}] absente : {key}')
    elif key.endswith('.json'):
        json.loads(contents)
    elif key.endswith('.sh') or contents.startswith((b'#!/usr/bin/env bash', b'#!/bin/sh', b'#!/bin/bash')):
        with tempfile.NamedTemporaryFile() as staged:
            staged.write(contents)
            staged.flush()
            run(['bash', '-n', staged.name])


def plan_files(locations, old, desired, commit, force=False):
    operations, conflicts, entries = [], [], {}
    proposals = dict(old.get('proposals', {}))
    for key, entry in desired.items():
        path = locations.path(key)
        if path.exists() and not path.is_symlink() and path.stat().st_uid != os.geteuid():
            raise UpdateError(f'Propriétaire différent : {path} ; corrigez les droits avant mise à jour.')
        actual = snapshot(path)
        prior = old['files'].get(key)
        target = entry['reference']
        if target is None:  # Build is planned separately; never claim a source as an executable.
            continue
        validate(key, target)
        if actual == target:
            entries[key] = {**entry, 'installed': actual, 'commit': commit}
        elif actual is None or (prior and (actual == prior['installed'] or (force and entry['policy'] == 'managed' and actual.get('kind') == prior['installed']['kind']))):
            operations.append({'key': key, 'before': actual, 'after': target, 'action': 'A' if actual is None else 'M'})
            entries[key] = {**entry, 'installed': target, 'commit': commit}
        else:
            # No speculative text merge: .new also handles overlapping JSON,
            # CSS and Hyprland changes without generating an invalid config.
            conflicts.append(key)
            if prior:
                entries[key] = prior
            proposal = key + '.new'
            current = snapshot(locations.path(proposal))
            if current is not None and current != target and current != proposals.get(proposal):
                proposal += '.' + fingerprint(target)[:12]
                current = snapshot(locations.path(proposal))
                if current is not None and current != target:
                    raise UpdateError(f"Proposition existante non gérée : {proposal}")
            if current != target:
                operations.append({'key': proposal, 'before': current, 'after': target, 'action': 'CONFLICT'})
            proposals[proposal] = target
    for key, prior in old['files'].items():
        if key in desired:
            continue
        actual = snapshot(locations.path(key))
        if actual is None:
            continue
        if prior.get('external'):
            # Never delete third-party QML when a local patch stops mentioning it.
            conflicts.append(key + ' (ancien patch externe à réviser)')
            entries[key] = prior
        elif actual == prior['installed']:
            operations.append({'key': key, 'before': actual, 'after': None, 'action': 'D'})
        else:
            # A renamed/deleted file edited by the user remains their data.
            conflicts.append(key + ' (suppression conservée)')
            entries[key] = prior
    for key, expected in list(proposals.items()):
        original = key.rsplit('.new', 1)[0]
        if original not in desired or (original in entries and entries[original]['reference'] == expected and snapshot(locations.path(original)) == expected):
            actual = snapshot(locations.path(key))
            if actual == expected:
                operations.append({'key': key, 'before': actual, 'after': None, 'action': 'D'})
            proposals.pop(key)
    return operations, conflicts, {**old, 'schema': 1, 'commit': commit, 'files': entries, 'proposals': proposals}
